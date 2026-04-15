"""Post-merge reference enrichment (T13).

Contract: after the three agents fan-in, the summary is enriched with
`[[decision:N]]` / `[[action:N]]` markers where any decision's or action's
`source_quote` overlaps a summary highlight (or the TL;DR) above the
similarity threshold. Markers are positional references into the respective
list — they decay gracefully if a later step drops an entry, since the UI
simply ignores markers without a resolvable target.
"""
from __future__ import annotations

from app.agents.merge import DEFAULT_THRESHOLD, enrich_summary, merge_node


def _mkdec(title: str, quote: str) -> dict:
    return {"title": title, "rationale": "because", "source_quote": quote}


def _mkaction(title: str, quote: str) -> dict:
    return {"title": title, "owner": None, "due_date": None, "source_quote": quote}


def test_enrich_attaches_decision_marker_to_matching_highlight() -> None:
    summary = {
        "tldr": "A short tldr",
        "highlights": ["We will adopt pgvector for vector storage", "Unrelated highlight"],
    }
    decisions = [_mkdec("pgvector", "we will adopt pgvector for vector storage")]

    out = enrich_summary(summary, decisions=decisions, action_items=[])

    assert out["highlights"][0].endswith("[[decision:0]]")
    assert out["highlights"][1] == "Unrelated highlight"


def test_enrich_attaches_action_marker_to_matching_highlight() -> None:
    summary = {"tldr": "x", "highlights": ["Kiran will write the ADR by Friday"]}
    actions = [_mkaction("Write ADR", "kiran will write the ADR by Friday")]

    out = enrich_summary(summary, decisions=[], action_items=actions)

    assert out["highlights"][0].endswith("[[action:0]]")


def test_enrich_supports_multiple_markers_on_single_highlight() -> None:
    summary = {"tldr": "x", "highlights": ["Adopt pgvector and ship on Railway"]}
    decisions = [
        _mkdec("pgvector", "adopt pgvector and ship on Railway"),
        _mkdec("railway", "adopt pgvector and ship on Railway"),
    ]

    out = enrich_summary(summary, decisions=decisions, action_items=[])

    assert "[[decision:0]]" in out["highlights"][0]
    assert "[[decision:1]]" in out["highlights"][0]


def test_enrich_skips_below_threshold_overlap() -> None:
    summary = {"tldr": "x", "highlights": ["completely unrelated text"]}
    decisions = [_mkdec("x", "entirely different subject matter")]

    out = enrich_summary(summary, decisions=decisions, action_items=[])

    assert out["highlights"][0] == "completely unrelated text"


def test_enrich_attaches_marker_to_tldr_when_matching() -> None:
    summary = {
        "tldr": "We will adopt pgvector for vector storage",
        "highlights": ["a", "b", "c"],
    }
    decisions = [_mkdec("pgvector", "we will adopt pgvector for vector storage")]

    out = enrich_summary(summary, decisions=decisions, action_items=[])

    assert out["tldr"].endswith("[[decision:0]]")


def test_enrich_returns_empty_summary_untouched() -> None:
    summary = {"tldr": "", "highlights": []}

    out = enrich_summary(summary, decisions=[_mkdec("x", "y")], action_items=[])

    assert out == {"tldr": "", "highlights": []}


def test_enrich_with_no_decisions_or_actions_is_a_noop() -> None:
    summary = {"tldr": "unchanged", "highlights": ["also unchanged"]}

    out = enrich_summary(summary, decisions=[], action_items=[])

    assert out == summary


def test_threshold_constant_is_80_percent() -> None:
    assert DEFAULT_THRESHOLD == 0.8


def test_merge_node_enriches_summary_from_state() -> None:
    state = {
        "summary": {"tldr": "x", "highlights": ["Kiran will write the ADR by Friday"]},
        "decisions": [],
        "action_items": [_mkaction("Write ADR", "kiran will write the ADR by Friday")],
    }

    update = merge_node(state)

    assert update["summary"]["highlights"][0].endswith("[[action:0]]")


def test_merge_node_handles_missing_summary_gracefully() -> None:
    """If a previous step failed and `summary` is missing, merge must not crash."""
    update = merge_node({"decisions": [], "action_items": []})

    assert update["summary"] == {"tldr": "", "highlights": []}
