"""Unit tests for the dispatch route's HTTP shape.

We swap in a fake `LinearClient` via `app.dependency_overrides` so no
network layer is exercised here — the route's own logic (selecting a
subset of action items, mapping results back to IDs, returning 409
when no credential is configured) is the contract under test.

Database interactions go through a stubbed `MCPClient` so these tests
stay DB-free; the full loop with real Postgres is in
`tests/integration/test_linear.py`.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.db import models
from app.db.session import get_db
from app.main import app
from app.mcp.dependencies import get_mcp_client
from app.mcp.linear import (
    ActionItemInput,
    DispatchError,
    DispatchResult,
    LinearAuthError,
    LinearIssue,
)
from app.routes.dispatch import get_linear_client


class _StubMCPClient:
    def __init__(self, key: str | None) -> None:
        self._key = key

    def get_integration_key(self, user_id: str, provider: str) -> str | None:
        return self._key


class _FakeLinearClient:
    """Captures calls + returns scripted `DispatchResult` (or raises)."""

    def __init__(
        self,
        *,
        result: DispatchResult | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._result = result
        self._raises = raises
        self.calls: list[tuple[list[ActionItemInput], str, str]] = []

    def create_issues(
        self,
        items: list[ActionItemInput],
        *,
        team_id: str,
    ) -> DispatchResult:
        self.calls.append((items, team_id, "called"))
        if self._raises is not None:
            raise self._raises
        assert self._result is not None
        return self._result


@pytest.fixture
def meeting_id() -> UUID:
    return uuid4()


@pytest.fixture
def action_item_ids() -> list[UUID]:
    return [uuid4(), uuid4()]


@pytest.fixture
def stub_meeting(meeting_id: UUID, action_item_ids: list[UUID]):
    """A fake meeting object with two action items — used by the route's
    `db.get(...)` lookup. We only expose the attributes the route touches."""
    items = [
        models.ActionItem(
            id=action_item_ids[0],
            meeting_id=meeting_id,
            title="Write migration",
            source_quote="we should write the migration",
            owner=None,
            due_date=None,
        ),
        models.ActionItem(
            id=action_item_ids[1],
            meeting_id=meeting_id,
            title="Send recap",
            source_quote="kiran will send a recap",
            owner="Kiran",
            due_date=None,
        ),
    ]
    meeting = models.Meeting(
        id=meeting_id,
        user_id="kiran@example.com",
        title="Migration planning",
        source_type="text",
        source_filename="t.txt",
        transcript="...",
        status="complete",
    )
    meeting.action_items = items
    return meeting


@pytest.fixture
def override_db(stub_meeting):
    class _Session:
        def get(self, _model, ident):  # noqa: ANN001
            if ident == stub_meeting.id:
                return stub_meeting
            return None

    def _override():
        yield _Session()

    app.dependency_overrides[get_db] = _override
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client(override_db) -> TestClient:
    with TestClient(app) as c:
        yield c


def _override_mcp(key: str | None) -> None:
    app.dependency_overrides[get_mcp_client] = lambda: _StubMCPClient(key)


def _override_linear(fake: _FakeLinearClient) -> None:
    app.dependency_overrides[get_linear_client] = lambda: (lambda api_key: fake)


def _clear_overrides() -> None:
    app.dependency_overrides.pop(get_mcp_client, None)
    app.dependency_overrides.pop(get_linear_client, None)


def test_dispatch_creates_issues_for_selected_action_items(
    client: TestClient,
    meeting_id: UUID,
    action_item_ids: list[UUID],
) -> None:
    """Happy path: both items succeed, payload contains resulting URLs
    keyed by the originating action-item id."""
    fake = _FakeLinearClient(
        result=DispatchResult(
            created=[
                LinearIssue(id="1", identifier="ENG-1", url="https://linear.app/1"),
                LinearIssue(id="2", identifier="ENG-2", url="https://linear.app/2"),
            ],
            errors=[],
        )
    )
    _override_mcp("lin_api_real")
    _override_linear(fake)
    try:
        resp = client.post(
            f"/meetings/{meeting_id}/dispatch/linear",
            json={
                "user_id": "kiran@example.com",
                "team_id": "team-uuid",
                "action_item_ids": [str(i) for i in action_item_ids],
            },
        )
    finally:
        _clear_overrides()

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["created"]) == 2
    assert body["errors"] == []
    assert body["created"][0]["action_item_id"] == str(action_item_ids[0])
    assert body["created"][0]["url"] == "https://linear.app/1"
    assert body["created"][1]["identifier"] == "ENG-2"
    # The fake saw exactly the two titles we asked for
    items, team_id, _ = fake.calls[0]
    assert [i.title for i in items] == ["Write migration", "Send recap"]
    assert team_id == "team-uuid"


def test_dispatch_returns_409_when_linear_not_configured(
    client: TestClient, meeting_id: UUID, action_item_ids: list[UUID]
) -> None:
    """No stored Linear key → refuse up front, don't silently succeed
    with nothing."""
    _override_mcp(None)
    _override_linear(_FakeLinearClient(result=DispatchResult()))
    try:
        resp = client.post(
            f"/meetings/{meeting_id}/dispatch/linear",
            json={
                "user_id": "kiran@example.com",
                "team_id": "team-uuid",
                "action_item_ids": [str(action_item_ids[0])],
            },
        )
    finally:
        _clear_overrides()

    assert resp.status_code == 409
    assert "linear" in resp.json()["detail"].lower()


def test_dispatch_rejects_ids_that_dont_belong_to_meeting(
    client: TestClient, meeting_id: UUID
) -> None:
    """Can't dispatch action items that aren't on this meeting — otherwise
    a spoofed request could exfiltrate IDs across meetings."""
    _override_mcp("lin_api_real")
    _override_linear(_FakeLinearClient(result=DispatchResult()))
    try:
        resp = client.post(
            f"/meetings/{meeting_id}/dispatch/linear",
            json={
                "user_id": "kiran@example.com",
                "team_id": "team-uuid",
                "action_item_ids": [str(uuid4())],  # random, not on meeting
            },
        )
    finally:
        _clear_overrides()

    assert resp.status_code == 422


def test_dispatch_surfaces_auth_error_as_401(
    client: TestClient, meeting_id: UUID, action_item_ids: list[UUID]
) -> None:
    """LinearAuthError means the stored key is bad — surface as 401 so
    the UI tells the user to reconnect."""
    fake = _FakeLinearClient(raises=LinearAuthError("bad key"))
    _override_mcp("lin_api_real")
    _override_linear(fake)
    try:
        resp = client.post(
            f"/meetings/{meeting_id}/dispatch/linear",
            json={
                "user_id": "kiran@example.com",
                "team_id": "team-uuid",
                "action_item_ids": [str(action_item_ids[0])],
            },
        )
    finally:
        _clear_overrides()

    assert resp.status_code == 401


def test_dispatch_returns_per_item_errors_alongside_successes(
    client: TestClient, meeting_id: UUID, action_item_ids: list[UUID]
) -> None:
    fake = _FakeLinearClient(
        result=DispatchResult(
            created=[
                LinearIssue(id="1", identifier="ENG-1", url="https://linear.app/1"),
            ],
            errors=[DispatchError(action_item_title="Send recap", message="no team")],
        )
    )
    _override_mcp("lin_api_real")
    _override_linear(fake)
    try:
        resp = client.post(
            f"/meetings/{meeting_id}/dispatch/linear",
            json={
                "user_id": "kiran@example.com",
                "team_id": "team-uuid",
                "action_item_ids": [str(i) for i in action_item_ids],
            },
        )
    finally:
        _clear_overrides()

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["created"]) == 1
    assert len(body["errors"]) == 1
    # Error matched back to the right action item by title lookup
    assert body["errors"][0]["action_item_id"] == str(action_item_ids[1])
    assert body["errors"][0]["message"] == "no team"


def test_dispatch_returns_404_for_unknown_meeting(client: TestClient) -> None:
    _override_mcp("lin_api_real")
    _override_linear(_FakeLinearClient(result=DispatchResult()))
    try:
        resp = client.post(
            f"/meetings/{uuid4()}/dispatch/linear",
            json={
                "user_id": "kiran@example.com",
                "team_id": "team-uuid",
                "action_item_ids": [str(uuid4())],
            },
        )
    finally:
        _clear_overrides()

    assert resp.status_code == 404
