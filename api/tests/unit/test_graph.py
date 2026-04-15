"""LangGraph agent DAG skeleton (T10).

T10 ships with no-op agent nodes that return empty structured output.
These tests lock the DAG shape so T11–T13 can swap in real Claude calls
without re-plumbing the graph.
"""
from __future__ import annotations

from app.graph import build_agent_graph


def test_graph_runs_and_produces_empty_agent_outputs() -> None:
    graph = build_agent_graph()

    result = graph.invoke({"meeting_id": "mid-1", "transcript": "hello world"})

    assert result["decisions"] == []
    assert result["action_items"] == []
    assert result["summary"] == {"tldr": "", "highlights": []}


def test_graph_preserves_inputs_through_pipeline() -> None:
    graph = build_agent_graph()

    result = graph.invoke({"meeting_id": "m42", "transcript": "line one\nline two"})

    assert result["meeting_id"] == "m42"
    assert result["transcript"] == "line one\nline two"


def test_graph_executes_all_three_agents_in_parallel() -> None:
    """Swap each agent for a tracker to prove every node fires exactly once."""
    from app import graph as graph_module

    calls: dict[str, int] = {"decision": 0, "action": 0, "summary": 0}

    def _decision(state):
        calls["decision"] += 1
        return {"decisions": []}

    def _action(state):
        calls["action"] += 1
        return {"action_items": []}

    def _summary(state):
        calls["summary"] += 1
        return {"summary": {"tldr": "", "highlights": []}}

    compiled = graph_module.build_agent_graph(
        decision_node=_decision,
        action_node=_action,
        summary_node=_summary,
    )
    compiled.invoke({"meeting_id": "m", "transcript": "t"})

    assert calls == {"decision": 1, "action": 1, "summary": 1}
