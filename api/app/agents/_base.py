"""Shared types + protocol for agent nodes in the LangGraph DAG.

Each agent node takes the pipeline state (a TypedDict) and returns a
partial update containing only its own slice of outputs. LangGraph fans
the three agent nodes out in parallel from `load` and fans them in at
`merge`; because each agent writes a distinct top-level key no reducers
are required.
"""
from __future__ import annotations

from typing import Protocol, TypedDict


class DecisionData(TypedDict):
    title: str
    rationale: str
    source_quote: str


class ActionItemData(TypedDict):
    title: str
    owner: str | None
    due_date: str | None
    source_quote: str


class SummaryData(TypedDict):
    tldr: str
    highlights: list[str]


class PipelineState(TypedDict, total=False):
    meeting_id: str
    transcript: str
    decisions: list[DecisionData]
    action_items: list[ActionItemData]
    summary: SummaryData | None


class AgentNode(Protocol):
    """A LangGraph node — pure function from full state to partial update."""

    def __call__(self, state: PipelineState) -> PipelineState: ...


def empty_summary() -> SummaryData:
    """Placeholder summary used by T10; T13 replaces with Claude output."""
    return {"tldr": "", "highlights": []}
