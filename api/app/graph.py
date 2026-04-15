"""LangGraph DAG for the meeting processing pipeline.

    load ──┬── decision ─┐
           ├── action   ─┼── merge
           └── summary  ─┘

T10 wires up the shape with no-op agent nodes. T11–T13 swap in real
Claude-backed implementations against the same `AgentNode` contract.
Keeping `build_agent_graph` parameterised by node callables lets tests
inject trackers without touching production code paths.
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.agents._base import AgentNode, PipelineState, empty_summary


def _load_transcript(state: PipelineState) -> PipelineState:
    """Pass-through today; reserved for pre-agent preparation in later tasks."""
    return {}


def _noop_decision(state: PipelineState) -> PipelineState:
    return {"decisions": []}


def _noop_action(state: PipelineState) -> PipelineState:
    return {"action_items": []}


def _noop_summary(state: PipelineState) -> PipelineState:
    return {"summary": empty_summary()}


def _merge(state: PipelineState) -> PipelineState:
    """Fan-in point. T13 will enrich summary text with decision/action refs."""
    return {}


def build_agent_graph(
    *,
    decision_node: AgentNode | None = None,
    action_node: AgentNode | None = None,
    summary_node: AgentNode | None = None,
):
    """Compile the LangGraph DAG. Agent nodes are injectable for testing."""
    graph = StateGraph(PipelineState)
    graph.add_node("load", _load_transcript)
    graph.add_node("decision", decision_node or _noop_decision)
    graph.add_node("action", action_node or _noop_action)
    graph.add_node("summary", summary_node or _noop_summary)
    graph.add_node("merge", _merge)

    graph.set_entry_point("load")
    graph.add_edge("load", "decision")
    graph.add_edge("load", "action")
    graph.add_edge("load", "summary")
    graph.add_edge("decision", "merge")
    graph.add_edge("action", "merge")
    graph.add_edge("summary", "merge")
    graph.add_edge("merge", END)

    return graph.compile()
