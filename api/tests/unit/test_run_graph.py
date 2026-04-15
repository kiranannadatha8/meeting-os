"""LangSmith tracing wiring (T14).

`run_graph` is the tracing-aware wrapper around `build_agent_graph().invoke()`.
It tags every invocation with the `meeting_id` so LangSmith dashboards can
filter by meeting, and returns the list of LangSmith run IDs captured during
the call so the pipeline can persist them for later lookup.
"""
from __future__ import annotations

from typing import Any

from app.graph import run_graph


class _RecordingGraph:
    def __init__(self, return_state: dict) -> None:
        self._return_state = return_state
        self.calls: list[dict[str, Any]] = []

    def invoke(self, state: dict, config: dict | None = None) -> dict:
        self.calls.append({"state": state, "config": config})
        return self._return_state


def test_run_graph_tags_invocation_with_meeting_id_metadata(monkeypatch) -> None:
    fake = _RecordingGraph(return_state={"meeting_id": "m1"})
    monkeypatch.setattr("app.graph.build_agent_graph", lambda: fake)

    run_graph({"meeting_id": "m1", "transcript": "t"}, meeting_id="m1")

    cfg = fake.calls[0]["config"]
    assert cfg["metadata"]["meeting_id"] == "m1"
    assert "meeting:m1" in cfg["tags"]


def test_run_graph_forwards_input_state_to_invoke(monkeypatch) -> None:
    fake = _RecordingGraph(return_state={})
    monkeypatch.setattr("app.graph.build_agent_graph", lambda: fake)

    run_graph({"meeting_id": "m2", "transcript": "hello"}, meeting_id="m2")

    assert fake.calls[0]["state"] == {"meeting_id": "m2", "transcript": "hello"}


def test_run_graph_returns_empty_run_ids_when_graph_does_not_emit_callbacks(monkeypatch) -> None:
    """`collect_runs` only sees runs from LangChain-instrumented invocations.
    The fake graph here bypasses all callbacks, so run_ids is empty — proving
    we read from the collector rather than fabricating IDs."""
    fake = _RecordingGraph(return_state={"meeting_id": "m1"})
    monkeypatch.setattr("app.graph.build_agent_graph", lambda: fake)

    _, run_ids = run_graph({"meeting_id": "m1", "transcript": "t"}, meeting_id="m1")

    assert run_ids == []


def test_run_graph_returns_graph_state_unchanged(monkeypatch) -> None:
    expected = {
        "meeting_id": "m3",
        "decisions": [],
        "action_items": [],
        "summary": {"tldr": "t", "highlights": ["a", "b", "c"]},
    }
    fake = _RecordingGraph(return_state=expected)
    monkeypatch.setattr("app.graph.build_agent_graph", lambda: fake)

    state, _ = run_graph({"meeting_id": "m3", "transcript": "t"}, meeting_id="m3")

    assert state == expected
