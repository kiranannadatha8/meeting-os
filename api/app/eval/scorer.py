"""Eval scorer — compares graph output against gold fixtures.

Matches decisions and action items by *title* using rapidfuzz ratio ≥ 80.
Titles are short, distinctive, and robust to LLM paraphrasing of the quote.
Summary is scored via tldr-ratio (fuzzy string similarity) and highlight recall.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rapidfuzz import fuzz

DEFAULT_MATCH_THRESHOLD: int = 80


@dataclass(frozen=True)
class FixtureResult:
    fixture_id: str
    decisions: dict[str, float]
    action_items: dict[str, float]
    summary: dict[str, float]
    overall: float


def _title(item: dict[str, Any]) -> str:
    return str(item.get("title", "")).strip()


def _match(predicted_title: str, expected_title: str, threshold: int) -> bool:
    if not predicted_title or not expected_title:
        return False
    return fuzz.token_set_ratio(predicted_title, expected_title) >= threshold


def _prf(
    predicted: list[dict[str, Any]],
    expected: list[dict[str, Any]],
    threshold: int,
) -> dict[str, float]:
    if not predicted and not expected:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}

    if not expected:
        return {"precision": 0.0, "recall": 1.0, "f1": 0.0}

    if not predicted:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    predicted_titles = [_title(p) for p in predicted]
    expected_titles = [_title(e) for e in expected]

    matched_predicted: set[int] = set()
    matched_expected: set[int] = set()
    for pi, pt in enumerate(predicted_titles):
        for ei, et in enumerate(expected_titles):
            if ei in matched_expected:
                continue
            if _match(pt, et, threshold):
                matched_predicted.add(pi)
                matched_expected.add(ei)
                break

    precision = len(matched_predicted) / len(predicted_titles)
    recall = len(matched_expected) / len(expected_titles)
    f1 = (
        (2 * precision * recall) / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    return {"precision": precision, "recall": recall, "f1": f1}


def score_decisions(
    predicted: list[dict[str, Any]],
    expected: list[dict[str, Any]],
    threshold: int = DEFAULT_MATCH_THRESHOLD,
) -> dict[str, float]:
    return _prf(predicted, expected, threshold)


def score_action_items(
    predicted: list[dict[str, Any]],
    expected: list[dict[str, Any]],
    threshold: int = DEFAULT_MATCH_THRESHOLD,
) -> dict[str, float]:
    return _prf(predicted, expected, threshold)


def score_summary(
    predicted: dict[str, Any],
    expected: dict[str, Any],
    threshold: int = DEFAULT_MATCH_THRESHOLD,
) -> dict[str, float]:
    predicted_tldr = str(predicted.get("tldr", "")).strip()
    expected_tldr = str(expected.get("tldr", "")).strip()

    if not predicted_tldr:
        tldr_ratio = 0.0
    elif not expected_tldr:
        tldr_ratio = 0.0
    else:
        tldr_ratio = fuzz.ratio(predicted_tldr, expected_tldr) / 100.0

    predicted_highlights = [str(h).strip() for h in predicted.get("highlights", [])]
    expected_highlights = [str(h).strip() for h in expected.get("highlights", [])]

    if not expected_highlights:
        highlight_recall = 1.0 if not predicted_highlights else 1.0
    elif not predicted_highlights:
        highlight_recall = 0.0
    else:
        matched = 0
        used: set[int] = set()
        for eh in expected_highlights:
            for pi, ph in enumerate(predicted_highlights):
                if pi in used:
                    continue
                if fuzz.token_set_ratio(eh, ph) >= threshold:
                    matched += 1
                    used.add(pi)
                    break
        highlight_recall = matched / len(expected_highlights)

    return {"tldr_ratio": tldr_ratio, "highlight_recall": highlight_recall}


def score_fixture(
    fixture_id: str,
    predicted_state: dict[str, Any],
    expected: dict[str, Any],
    threshold: int = DEFAULT_MATCH_THRESHOLD,
) -> FixtureResult:
    decisions = score_decisions(
        predicted_state.get("decisions", []),
        expected.get("decisions", []),
        threshold,
    )
    action_items = score_action_items(
        predicted_state.get("action_items", []),
        expected.get("action_items", []),
        threshold,
    )
    summary = score_summary(
        predicted_state.get("summary", {}) or {},
        expected.get("summary", {}) or {},
        threshold,
    )

    overall = (
        decisions["f1"]
        + action_items["f1"]
        + summary["tldr_ratio"]
        + summary["highlight_recall"]
    ) / 4.0

    return FixtureResult(
        fixture_id=fixture_id,
        decisions=decisions,
        action_items=action_items,
        summary=summary,
        overall=overall,
    )
