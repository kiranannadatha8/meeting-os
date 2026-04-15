"""Eval runner contract (T16).

The runner:

1. Discovers fixture pairs in a directory (transcript_N.txt + expected_N.json).
2. Runs the LangGraph pipeline against each transcript.
3. Scores the output via app.eval.scorer.
4. Emits a scorecard dict with per-fixture + aggregate metrics.
5. Given a baseline, detects whether the aggregate dropped more than a threshold
   (default 5 percentage points) and returns a regression flag.

Agent invocations are injectable via run_fn so tests never hit Anthropic.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.eval.run import (
    DEFAULT_REGRESSION_THRESHOLD_PP,
    aggregate_scorecard,
    detect_regression,
    discover_fixtures,
    run_eval,
)


@pytest.fixture()
def fixtures_dir(tmp_path: Path) -> Path:
    transcript = "we will adopt pgvector and ship on friday"
    expected = {
        "decisions": [
            {"title": "Adopt pgvector", "rationale": "r", "source_quote": "q"}
        ],
        "action_items": [
            {
                "title": "Ship on Friday",
                "owner": None,
                "due_date": None,
                "source_quote": "q",
            }
        ],
        "summary": {
            "tldr": "adopt pgvector and ship on friday",
            "highlights": ["Adopt pgvector", "Ship on Friday"],
        },
    }
    (tmp_path / "transcript_01.txt").write_text(transcript)
    (tmp_path / "expected_01.json").write_text(json.dumps(expected))
    return tmp_path


def _graph_perfect(transcript: str) -> dict:
    """Fake graph that echoes the gold output back."""
    return {
        "decisions": [
            {"title": "Adopt pgvector", "rationale": "r", "source_quote": "q"}
        ],
        "action_items": [
            {
                "title": "Ship on Friday",
                "owner": None,
                "due_date": None,
                "source_quote": "q",
            }
        ],
        "summary": {
            "tldr": "adopt pgvector and ship on friday",
            "highlights": ["Adopt pgvector", "Ship on Friday"],
        },
    }


def _graph_empty(transcript: str) -> dict:
    return {"decisions": [], "action_items": [], "summary": {"tldr": "", "highlights": []}}


def test_discover_fixtures_returns_sorted_pairs(fixtures_dir: Path) -> None:
    (fixtures_dir / "transcript_02.txt").write_text("t")
    (fixtures_dir / "expected_02.json").write_text("{}")

    pairs = discover_fixtures(fixtures_dir)

    assert [p.fixture_id for p in pairs] == ["01", "02"]
    assert pairs[0].transcript_path.name == "transcript_01.txt"
    assert pairs[0].expected_path.name == "expected_01.json"


def test_discover_fixtures_skips_unpaired_files(tmp_path: Path) -> None:
    (tmp_path / "transcript_03.txt").write_text("t")
    # No matching expected_03.json.

    assert discover_fixtures(tmp_path) == []


def test_run_eval_with_perfect_graph_scores_1_0(fixtures_dir: Path) -> None:
    scorecard = run_eval(fixtures_dir, run_fn=_graph_perfect)

    assert scorecard["aggregate"]["overall"] == pytest.approx(1.0)
    assert len(scorecard["fixtures"]) == 1
    assert scorecard["fixtures"][0]["fixture_id"] == "01"


def test_run_eval_with_empty_graph_scores_zero(fixtures_dir: Path) -> None:
    scorecard = run_eval(fixtures_dir, run_fn=_graph_empty)

    assert scorecard["aggregate"]["overall"] == pytest.approx(0.0)


def test_aggregate_scorecard_averages_fixtures() -> None:
    fixtures = [
        {
            "fixture_id": "a",
            "decisions": {"precision": 1.0, "recall": 1.0, "f1": 1.0},
            "action_items": {"precision": 0.0, "recall": 0.0, "f1": 0.0},
            "summary": {"tldr_ratio": 1.0, "highlight_recall": 1.0},
            "overall": 0.75,
        },
        {
            "fixture_id": "b",
            "decisions": {"precision": 0.5, "recall": 0.5, "f1": 0.5},
            "action_items": {"precision": 1.0, "recall": 1.0, "f1": 1.0},
            "summary": {"tldr_ratio": 0.8, "highlight_recall": 0.8},
            "overall": 0.775,
        },
    ]

    aggregate = aggregate_scorecard(fixtures)

    assert aggregate["decisions"]["f1"] == pytest.approx(0.75)
    assert aggregate["action_items"]["f1"] == pytest.approx(0.5)
    assert aggregate["summary"]["tldr_ratio"] == pytest.approx(0.9)
    assert aggregate["overall"] == pytest.approx((0.75 + 0.775) / 2)


def test_detect_regression_flags_large_drop() -> None:
    baseline = {"aggregate": {"overall": 0.80}}
    current = {"aggregate": {"overall": 0.70}}

    result = detect_regression(current, baseline)

    assert result["regression"] is True
    assert result["drop_pp"] == pytest.approx(10.0)
    assert result["threshold_pp"] == DEFAULT_REGRESSION_THRESHOLD_PP


def test_detect_regression_tolerates_small_drop() -> None:
    baseline = {"aggregate": {"overall": 0.80}}
    current = {"aggregate": {"overall": 0.78}}

    result = detect_regression(current, baseline)

    assert result["regression"] is False
    assert result["drop_pp"] == pytest.approx(2.0)


def test_detect_regression_allows_improvement() -> None:
    baseline = {"aggregate": {"overall": 0.80}}
    current = {"aggregate": {"overall": 0.90}}

    result = detect_regression(current, baseline)

    assert result["regression"] is False
    assert result["drop_pp"] == pytest.approx(-10.0)


def test_detect_regression_without_baseline_never_regresses() -> None:
    result = detect_regression({"aggregate": {"overall": 0.10}}, baseline=None)
    assert result["regression"] is False
