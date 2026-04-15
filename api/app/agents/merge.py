"""Post-merge reference enrichment (T13).

Fan-in step: after decision/action/summary agents produce output, tag
matching summary spans with `[[decision:N]]` and `[[action:N]]` markers
that the UI resolves to cards. Uses `difflib.SequenceMatcher.ratio()` —
stdlib, good enough at this scale; can be swapped for `rapidfuzz` later
without changing the interface.

Marker indices are positional into the respective list as returned from
the graph. The UI tolerates unresolved markers, so this step is
best-effort — if similarity is ambiguous we simply don't link.
"""
from __future__ import annotations

from difflib import SequenceMatcher

from app.agents._base import (
    ActionItemData,
    DecisionData,
    PipelineState,
    SummaryData,
    empty_summary,
)

DEFAULT_THRESHOLD = 0.8


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _markers_for(
    text: str,
    decisions: list[DecisionData],
    action_items: list[ActionItemData],
    threshold: float,
) -> list[str]:
    markers: list[str] = []
    for i, decision in enumerate(decisions):
        if _ratio(text, decision["source_quote"]) >= threshold:
            markers.append(f"[[decision:{i}]]")
    for i, item in enumerate(action_items):
        if _ratio(text, item["source_quote"]) >= threshold:
            markers.append(f"[[action:{i}]]")
    return markers


def _append(text: str, markers: list[str]) -> str:
    if not markers:
        return text
    return f"{text} {' '.join(markers)}"


def enrich_summary(
    summary: SummaryData,
    *,
    decisions: list[DecisionData],
    action_items: list[ActionItemData],
    threshold: float = DEFAULT_THRESHOLD,
) -> SummaryData:
    """Return a new summary with reference markers appended where quotes
    overlap above `threshold`. Leaves summary untouched when empty or when
    no markers apply."""
    if not summary.get("tldr") and not summary.get("highlights"):
        return summary
    if not decisions and not action_items:
        return summary

    tldr_markers = _markers_for(summary.get("tldr", ""), decisions, action_items, threshold)
    enriched_tldr = _append(summary.get("tldr", ""), tldr_markers)

    enriched_highlights = [
        _append(bullet, _markers_for(bullet, decisions, action_items, threshold))
        for bullet in summary.get("highlights", [])
    ]

    return {"tldr": enriched_tldr, "highlights": enriched_highlights}


def merge_node(state: PipelineState) -> PipelineState:
    """LangGraph merge node: enrich the summary with references to the
    other agents' outputs. Tolerates missing summary (upstream agent
    failure) by substituting an empty summary so the pipeline still
    persists a row."""
    summary = state.get("summary") or empty_summary()
    enriched = enrich_summary(
        summary,
        decisions=state.get("decisions") or [],
        action_items=state.get("action_items") or [],
    )
    return {"summary": enriched}
