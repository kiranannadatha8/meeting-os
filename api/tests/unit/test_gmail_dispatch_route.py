"""Unit tests for the Gmail dispatch route.

These swap a fake `GmailClient` in via DI so no real network runs.
The route's job is:
  1. Validate the meeting exists
  2. Pull the encrypted refresh_token from `MCPClient`
  3. Compose the email body (TL;DR + highlights + selected action items)
  4. Return the draft id/URL
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.db import models
from app.db.session import get_db
from app.main import app
from app.mcp.dependencies import get_mcp_client
from app.mcp.gmail import DraftResult, GmailAuthError, GmailError
from app.routes.dispatch import get_gmail_client, get_google_oauth_app


class _StubMCPClient:
    def __init__(self, key: str | None) -> None:
        self._key = key

    def get_integration_key(self, user_id: str, provider: str) -> str | None:
        return self._key


class _FakeGmailClient:
    def __init__(
        self,
        *,
        result: DraftResult | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._result = result
        self._raises = raises
        self.last_kwargs: dict | None = None

    def create_draft(
        self,
        *,
        to: list[str],
        subject: str,
        body_text: str,
    ) -> DraftResult:
        self.last_kwargs = {"to": to, "subject": subject, "body_text": body_text}
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
    items = [
        models.ActionItem(
            id=action_item_ids[0],
            meeting_id=meeting_id,
            title="Write migration",
            source_quote="let's write the migration",
            owner="Kiran",
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
    summary = models.Summary(
        meeting_id=meeting_id,
        tldr="We decided to ship the migration this quarter.",
        highlights=["Owner: platform team", "Timeline: by 2026-05-01"],
    )
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
    meeting.summary = summary
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


def _install(fake_client: _FakeGmailClient, *, mcp_key: str | None) -> None:
    app.dependency_overrides[get_mcp_client] = lambda: _StubMCPClient(mcp_key)
    app.dependency_overrides[get_gmail_client] = lambda: (
        lambda refresh_token, client_id, client_secret: fake_client
    )
    app.dependency_overrides[get_google_oauth_app] = lambda: ("cid", "sec")


def _clear() -> None:
    app.dependency_overrides.pop(get_mcp_client, None)
    app.dependency_overrides.pop(get_gmail_client, None)
    app.dependency_overrides.pop(get_google_oauth_app, None)


def test_creates_draft_with_tldr_highlights_and_selected_items(
    client: TestClient, meeting_id: UUID, action_item_ids: list[UUID]
) -> None:
    fake = _FakeGmailClient(
        result=DraftResult(draft_id="d1", message_id="m1", thread_id="t1")
    )
    _install(fake, mcp_key="rt_test")
    try:
        resp = client.post(
            f"/meetings/{meeting_id}/dispatch/gmail",
            json={
                "user_id": "kiran@example.com",
                "recipients": ["team@example.com"],
                "action_item_ids": [str(i) for i in action_item_ids],
            },
        )
    finally:
        _clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["draft_id"] == "d1"
    assert body["draft_url"] == "https://mail.google.com/mail/u/0/#drafts?compose=m1"

    kwargs = fake.last_kwargs
    assert kwargs is not None
    assert kwargs["to"] == ["team@example.com"]
    # Default subject format uses the meeting title
    assert kwargs["subject"] == "Follow-up: Migration planning"
    text = kwargs["body_text"]
    assert "We decided to ship the migration this quarter." in text
    assert "Owner: platform team" in text
    assert "Write migration" in text
    assert "Send recap" in text


def test_accepts_custom_subject(
    client: TestClient, meeting_id: UUID, action_item_ids: list[UUID]
) -> None:
    fake = _FakeGmailClient(
        result=DraftResult(draft_id="d1", message_id="m1", thread_id="t1")
    )
    _install(fake, mcp_key="rt_test")
    try:
        resp = client.post(
            f"/meetings/{meeting_id}/dispatch/gmail",
            json={
                "user_id": "kiran@example.com",
                "recipients": ["a@example.com"],
                "subject": "Custom subject",
                "action_item_ids": [str(action_item_ids[0])],
            },
        )
    finally:
        _clear()
    assert resp.status_code == 200
    assert fake.last_kwargs["subject"] == "Custom subject"
    # Only one action item should appear
    text = fake.last_kwargs["body_text"]
    assert "Write migration" in text
    assert "Send recap" not in text


def test_returns_409_when_gmail_not_configured(
    client: TestClient, meeting_id: UUID, action_item_ids: list[UUID]
) -> None:
    fake = _FakeGmailClient(
        result=DraftResult(draft_id="d1", message_id="m1", thread_id="t1")
    )
    _install(fake, mcp_key=None)
    try:
        resp = client.post(
            f"/meetings/{meeting_id}/dispatch/gmail",
            json={
                "user_id": "kiran@example.com",
                "recipients": ["a@example.com"],
                "action_item_ids": [str(action_item_ids[0])],
            },
        )
    finally:
        _clear()
    assert resp.status_code == 409
    assert "gmail" in resp.json()["detail"].lower()


def test_surfaces_auth_error_as_401(
    client: TestClient, meeting_id: UUID, action_item_ids: list[UUID]
) -> None:
    fake = _FakeGmailClient(raises=GmailAuthError("invalid_grant"))
    _install(fake, mcp_key="rt_stale")
    try:
        resp = client.post(
            f"/meetings/{meeting_id}/dispatch/gmail",
            json={
                "user_id": "kiran@example.com",
                "recipients": ["a@example.com"],
                "action_item_ids": [str(action_item_ids[0])],
            },
        )
    finally:
        _clear()
    assert resp.status_code == 401


def test_surfaces_transport_error_as_502(
    client: TestClient, meeting_id: UUID, action_item_ids: list[UUID]
) -> None:
    fake = _FakeGmailClient(raises=GmailError("service unavailable"))
    _install(fake, mcp_key="rt_test")
    try:
        resp = client.post(
            f"/meetings/{meeting_id}/dispatch/gmail",
            json={
                "user_id": "kiran@example.com",
                "recipients": ["a@example.com"],
                "action_item_ids": [str(action_item_ids[0])],
            },
        )
    finally:
        _clear()
    assert resp.status_code == 502


def test_rejects_action_items_that_dont_belong_to_meeting(
    client: TestClient, meeting_id: UUID
) -> None:
    fake = _FakeGmailClient(
        result=DraftResult(draft_id="d1", message_id="m1", thread_id="t1")
    )
    _install(fake, mcp_key="rt_test")
    try:
        resp = client.post(
            f"/meetings/{meeting_id}/dispatch/gmail",
            json={
                "user_id": "kiran@example.com",
                "recipients": ["a@example.com"],
                "action_item_ids": [str(uuid4())],
            },
        )
    finally:
        _clear()
    assert resp.status_code == 422


def test_returns_409_when_google_app_credentials_missing(
    client: TestClient, meeting_id: UUID, action_item_ids: list[UUID]
) -> None:
    """User has a refresh token, but the server hasn't been configured
    with GOOGLE_CLIENT_ID/SECRET — we can't refresh. Fail up front."""
    fake = _FakeGmailClient(
        result=DraftResult(draft_id="d1", message_id="m1", thread_id="t1")
    )
    app.dependency_overrides[get_mcp_client] = lambda: _StubMCPClient("rt_test")
    app.dependency_overrides[get_gmail_client] = lambda: (
        lambda refresh_token, client_id, client_secret: fake
    )
    app.dependency_overrides[get_google_oauth_app] = lambda: ("", "")
    try:
        resp = client.post(
            f"/meetings/{meeting_id}/dispatch/gmail",
            json={
                "user_id": "kiran@example.com",
                "recipients": ["a@example.com"],
                "action_item_ids": [str(action_item_ids[0])],
            },
        )
    finally:
        _clear()
    assert resp.status_code == 409
    assert "google" in resp.json()["detail"].lower()
