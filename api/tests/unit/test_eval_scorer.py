"""Eval scorer contract (T16).

The scorer compares graph output to human-labeled expectations using
fuzzy string matching (rapidfuzz ratio ≥ 80). It produces:

- per-fixture precision / recall / f1 for decisions + action items
- per-fixture TL;DR coverage score (tldr ratio) + highlight recall
- an overall aggregate

Matching is title-only for decisions and action items (the quote is a
secondary signal, not required for a match — LLMs paraphrase).
"""
from __future__ import annotations

from app.eval.scorer import (
    DEFAULT_MATCH_THRESHOLD,
    FixtureResult,
    score_action_items,
    score_decisions,
    score_fixture,
    score_summary,
)


def _dec(title: str, quote: str = "q") -> dict:
    return {"title": title, "rationale": "r", "source_quote": quote}


def _act(title: str, owner: str | None = None, quote: str = "q") -> dict:
    return {"title": title, "owner": owner, "due_date": None, "source_quote": quote}


def test_decisions_perfect_match_scores_1_0() -> None:
    predicted = [_dec("Adopt pgvector"), _dec("Deploy to Railway")]
    expected = [_dec("Adopt pgvector"), _dec("Deploy to Railway")]

    out = score_decisions(predicted, expected)

    assert out["precision"] == 1.0
    assert out["recall"] == 1.0
    assert out["f1"] == 1.0


def test_decisions_fuzzy_match_above_threshold_counts() -> None:
    predicted = [_dec("Adopt pgvector for vector storage")]
    expected = [_dec("Adopt pgvector")]

    out = score_decisions(predicted, expected)

    assert out["recall"] == 1.0


def test_decisions_below_threshold_does_not_match() -> None:
    predicted = [_dec("Completely unrelated decision")]
    expected = [_dec("Adopt pgvector")]

    out = score_decisions(predicted, expected)

    assert out["recall"] == 0.0
    assert out["precision"] == 0.0


def test_decisions_partial_recall() -> None:
    predicted = [_dec("Adopt pgvector")]
    expected = [_dec("Adopt pgvector"), _dec("Ship on Friday")]

    out = score_decisions(predicted, expected)

    assert out["precision"] == 1.0
    assert out["recall"] == 0.5


def test_decisions_empty_expected_and_empty_predicted_is_perfect() -> None:
    out = score_decisions([], [])
    assert out == {"precision": 1.0, "recall": 1.0, "f1": 1.0}


def test_decisions_predicted_but_none_expected_is_zero_precision() -> None:
    out = score_decisions([_dec("x")], [])
    assert out["precision"] == 0.0
    assert out["recall"] == 1.0
    assert out["f1"] == 0.0


def test_action_items_match_by_title() -> None:
    predicted = [_act("Write the ADR by Friday")]
    expected = [_act("Write ADR")]

    out = score_action_items(predicted, expected)

    assert out["recall"] == 1.0


def test_summary_tldr_ratio_captures_semantic_similarity() -> None:
    predicted = {
        "tldr": "Team agreed to adopt pgvector and ship on Friday",
        "highlights": ["Adopt pgvector", "Ship on Friday"],
    }
    expected = {
        "tldr": "Team adopts pgvector and ships Friday",
        "highlights": ["Adopt pgvector", "Ship on Friday"],
    }

    out = score_summary(predicted, expected)

    assert out["tldr_ratio"] >= DEFAULT_MATCH_THRESHOLD / 100
    assert out["highlight_recall"] == 1.0


def test_summary_missing_predicted_scores_zero() -> None:
    out = score_summary(
        {"tldr": "", "highlights": []},
        {"tldr": "t", "highlights": ["a"]},
    )
    assert out["tldr_ratio"] == 0.0
    assert out["highlight_recall"] == 0.0


def test_score_fixture_aggregates_all_dimensions() -> None:
    predicted_state = {
        "decisions": [_dec("Adopt pgvector")],
        "action_items": [_act("Write ADR")],
        "summary": {
            "tldr": "Team adopts pgvector",
            "highlights": ["Adopt pgvector", "Write ADR"],
        },
    }
    expected = {
        "decisions": [_dec("Adopt pgvector")],
        "action_items": [_act("Write ADR")],
        "summary": {
            "tldr": "Team adopts pgvector",
            "highlights": ["Adopt pgvector", "Write ADR"],
        },
    }

    result = score_fixture("fixture-1", predicted_state, expected)

    assert isinstance(result, FixtureResult)
    assert result.fixture_id == "fixture-1"
    assert result.decisions["f1"] == 1.0
    assert result.action_items["f1"] == 1.0
    assert result.summary["tldr_ratio"] >= 0.9
    assert result.overall >= 0.9
