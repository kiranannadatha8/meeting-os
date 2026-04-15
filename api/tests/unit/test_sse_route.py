"""Unit tests for `GET /meetings/{id}/events` (SSE).

The route polls the DB at a small interval and emits a `status` SSE
event whenever the meeting's status (or error_message) changes. It
closes the stream as soon as the status is terminal (`complete` or
`failed`). A fake session factory drives the test without Postgres.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes.sse import get_session_factory


class _FakeMeeting:
    def __init__(self, status: str, error_message: str | None = None) -> None:
        self.status = status
        self.error_message = error_message


class _ScriptState:
    """Shared state: every opened session pulls from the same queue."""

    def __init__(self, script: list[_FakeMeeting | None]) -> None:
        self._script = list(script)
        self._last: _FakeMeeting | None = None

    def next(self) -> _FakeMeeting | None:
        if not self._script:
            return self._last  # freeze at last known value
        self._last = self._script.pop(0)
        return self._last


class _FakeSession:
    """Context-managed session whose `get()` walks a scripted list."""

    def __init__(self, state: _ScriptState) -> None:
        self._state = state

    def get(self, _model, _ident):  # noqa: ANN001
        return self._state.next()

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *exc: object) -> None:  # noqa: D401
        pass


def _install_factory(script: list[_FakeMeeting | None]) -> None:
    """All opened sessions share a single script-walker."""
    state = _ScriptState(script)

    def _factory() -> _FakeSession:
        return _FakeSession(state)

    app.dependency_overrides[get_session_factory] = lambda: _factory


def _clear() -> None:
    app.dependency_overrides.pop(get_session_factory, None)


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


def _parse_events(raw: str) -> list[dict]:
    """Very small SSE parser — only handles `event:` + `data:` pairs."""
    events: list[dict] = []
    current: dict[str, str] = {}
    for line in raw.splitlines():
        if line == "":
            if current:
                events.append(current)
                current = {}
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            current[key.strip()] = value.lstrip(" ")
    if current:
        events.append(current)
    return events


def test_streams_initial_status_then_closes_on_complete(client: TestClient) -> None:
    meeting_id = uuid4()
    _install_factory([_FakeMeeting("processing"), _FakeMeeting("complete")])
    try:
        with client.stream(
            "GET",
            f"/meetings/{meeting_id}/events",
            params={"poll_interval": "0"},
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            body = "".join(resp.iter_text())
    finally:
        _clear()

    events = _parse_events(body)
    # Two distinct status events (processing, then complete)
    status_events = [e for e in events if e.get("event") == "status"]
    assert len(status_events) == 2
    assert json.loads(status_events[0]["data"])["status"] == "processing"
    assert json.loads(status_events[1]["data"])["status"] == "complete"


def test_emits_single_event_when_already_complete(client: TestClient) -> None:
    meeting_id = uuid4()
    _install_factory([_FakeMeeting("complete")])
    try:
        with client.stream(
            "GET",
            f"/meetings/{meeting_id}/events",
            params={"poll_interval": "0"},
        ) as resp:
            body = "".join(resp.iter_text())
    finally:
        _clear()

    status_events = [e for e in _parse_events(body) if e.get("event") == "status"]
    assert len(status_events) == 1
    assert json.loads(status_events[0]["data"])["status"] == "complete"


def test_emits_failed_status_with_error_message(client: TestClient) -> None:
    meeting_id = uuid4()
    _install_factory([_FakeMeeting("failed", "agents went sideways")])
    try:
        with client.stream(
            "GET",
            f"/meetings/{meeting_id}/events",
            params={"poll_interval": "0"},
        ) as resp:
            body = "".join(resp.iter_text())
    finally:
        _clear()

    status_events = [e for e in _parse_events(body) if e.get("event") == "status"]
    assert len(status_events) == 1
    payload = json.loads(status_events[0]["data"])
    assert payload["status"] == "failed"
    assert payload["error_message"] == "agents went sideways"


def test_404_for_unknown_meeting(client: TestClient) -> None:
    _install_factory([None])
    try:
        resp = client.get(f"/meetings/{uuid4()}/events", params={"poll_interval": "0"})
    finally:
        _clear()
    assert resp.status_code == 404


def test_does_not_duplicate_when_status_unchanged_between_polls(
    client: TestClient,
) -> None:
    """If the DB reports the same status twice, only one event is emitted."""
    meeting_id = uuid4()
    _install_factory(
        [
            _FakeMeeting("processing"),
            _FakeMeeting("processing"),  # same — no event
            _FakeMeeting("complete"),
        ]
    )
    try:
        with client.stream(
            "GET",
            f"/meetings/{meeting_id}/events",
            params={"poll_interval": "0"},
        ) as resp:
            body = "".join(resp.iter_text())
    finally:
        _clear()

    status_events = [e for e in _parse_events(body) if e.get("event") == "status"]
    assert [json.loads(e["data"])["status"] for e in status_events] == [
        "processing",
        "complete",
    ]
