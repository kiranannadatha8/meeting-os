"""Eval runner — orchestrates fixture discovery, graph invocation, and scoring.

Usage (CLI):
    python -m app.eval.run \
        --fixtures fixtures/eval \
        --baseline fixtures/eval_baseline.json \
        --output scorecard.json

Exit code 1 when the aggregate overall score regresses more than
DEFAULT_REGRESSION_THRESHOLD_PP (5 percentage points) vs baseline, which is
what the CI job keys off of. Exit 0 on match-or-better, or when no baseline
is present (bootstrap run).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.eval.scorer import FixtureResult, score_fixture

DEFAULT_REGRESSION_THRESHOLD_PP: float = 5.0

RunFn = Callable[[str], dict[str, Any]]


@dataclass(frozen=True)
class FixturePair:
    fixture_id: str
    transcript_path: Path
    expected_path: Path


def discover_fixtures(fixtures_dir: Path) -> list[FixturePair]:
    """Return sorted (transcript, expected) pairs that share the same suffix.

    Files must follow `transcript_<id>.txt` and `expected_<id>.json` naming.
    Unpaired files are skipped silently (the runner ignores stray drafts).
    """
    pairs: list[FixturePair] = []
    for transcript_path in sorted(fixtures_dir.glob("transcript_*.txt")):
        fixture_id = transcript_path.stem.removeprefix("transcript_")
        expected_path = fixtures_dir / f"expected_{fixture_id}.json"
        if not expected_path.exists():
            continue
        pairs.append(
            FixturePair(
                fixture_id=fixture_id,
                transcript_path=transcript_path,
                expected_path=expected_path,
            )
        )
    return pairs


def _default_run_fn(transcript: str) -> dict[str, Any]:
    """Invoke the real LangGraph pipeline. Lazy import so tests that never
    touch Anthropic can import this module without pulling in langgraph."""
    from app.graph import run_graph

    state, _run_ids = run_graph(
        {"meeting_id": "eval-run", "transcript": transcript},
        meeting_id="eval-run",
    )
    return {
        "decisions": state.get("decisions", []),
        "action_items": state.get("action_items", []),
        "summary": state.get("summary") or {"tldr": "", "highlights": []},
    }


def _result_to_dict(r: FixtureResult) -> dict[str, Any]:
    return asdict(r)


def aggregate_scorecard(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    """Average per-fixture metrics into a single aggregate row.

    Empty input is treated as a perfect run (nothing to score) — that case
    never arises in practice because we commit five fixtures, but it keeps
    the tests stable.
    """
    if not fixtures:
        return {
            "decisions": {"precision": 1.0, "recall": 1.0, "f1": 1.0},
            "action_items": {"precision": 1.0, "recall": 1.0, "f1": 1.0},
            "summary": {"tldr_ratio": 1.0, "highlight_recall": 1.0},
            "overall": 1.0,
        }

    n = float(len(fixtures))

    def mean(path: list[str]) -> float:
        total = 0.0
        for f in fixtures:
            node: Any = f
            for key in path:
                node = node[key]
            total += float(node)
        return total / n

    return {
        "decisions": {
            "precision": mean(["decisions", "precision"]),
            "recall": mean(["decisions", "recall"]),
            "f1": mean(["decisions", "f1"]),
        },
        "action_items": {
            "precision": mean(["action_items", "precision"]),
            "recall": mean(["action_items", "recall"]),
            "f1": mean(["action_items", "f1"]),
        },
        "summary": {
            "tldr_ratio": mean(["summary", "tldr_ratio"]),
            "highlight_recall": mean(["summary", "highlight_recall"]),
        },
        "overall": mean(["overall"]),
    }


def run_eval(
    fixtures_dir: Path,
    *,
    run_fn: RunFn | None = None,
) -> dict[str, Any]:
    """Run the pipeline against every fixture and return a scorecard dict."""
    fn = run_fn or _default_run_fn
    pairs = discover_fixtures(fixtures_dir)

    per_fixture: list[dict[str, Any]] = []
    for pair in pairs:
        transcript = pair.transcript_path.read_text()
        expected = json.loads(pair.expected_path.read_text())
        predicted = fn(transcript)
        result = score_fixture(pair.fixture_id, predicted, expected)
        per_fixture.append(_result_to_dict(result))

    return {
        "fixtures": per_fixture,
        "aggregate": aggregate_scorecard(per_fixture),
    }


def detect_regression(
    current: dict[str, Any],
    baseline: dict[str, Any] | None,
    *,
    threshold_pp: float = DEFAULT_REGRESSION_THRESHOLD_PP,
) -> dict[str, Any]:
    """Compare current aggregate against baseline; flag regression."""
    current_overall = float(current["aggregate"]["overall"])

    if baseline is None:
        return {
            "regression": False,
            "drop_pp": 0.0,
            "threshold_pp": threshold_pp,
            "current_overall": current_overall,
            "baseline_overall": None,
        }

    baseline_overall = float(baseline["aggregate"]["overall"])
    drop_pp = (baseline_overall - current_overall) * 100.0
    return {
        "regression": drop_pp > threshold_pp,
        "drop_pp": drop_pp,
        "threshold_pp": threshold_pp,
        "current_overall": current_overall,
        "baseline_overall": baseline_overall,
    }


def _load_baseline(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the MeetingOS eval harness.")
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path("fixtures/eval"),
        help="Directory containing transcript_*.txt and expected_*.json",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("fixtures/eval_baseline.json"),
        help="Baseline scorecard to compare against",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the scorecard JSON",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Overwrite the baseline with the current run (bootstrap/intentional bumps)",
    )
    args = parser.parse_args(argv)

    scorecard = run_eval(args.fixtures)
    baseline = _load_baseline(args.baseline)
    regression = detect_regression(scorecard, baseline)
    scorecard["regression"] = regression

    out_text = json.dumps(scorecard, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(out_text)
    print(out_text)

    if args.update_baseline:
        baseline_payload = {
            "aggregate": scorecard["aggregate"],
            "fixtures": scorecard["fixtures"],
        }
        args.baseline.write_text(json.dumps(baseline_payload, indent=2, sort_keys=True))

    return 1 if regression["regression"] else 0


if __name__ == "__main__":
    sys.exit(main())
