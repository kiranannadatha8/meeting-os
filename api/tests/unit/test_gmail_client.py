"""Unit tests for the Gmail MCP tool wrapper.

We exercise the OAuth refresh → draft-create HTTP contract using
`httpx.MockTransport`. No real network, but the full client path runs.
"""
from __future__ import annotations

import base64
import email
import json

import httpx
import pytest

from app.mcp.gmail import (
    DraftResult,
    GmailAuthError,
    GmailClient,
    GmailError,
)


def _make_client(
    handler,
    *,
    refresh_token: str = "rt_test",
    client_id: str = "cid",
    client_secret: str = "sec",
) -> GmailClient:
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    return GmailClient(
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        http=http,
    )


def _token_response(access_token: str = "access_token_xyz") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "access_token": access_token,
            "expires_in": 3599,
            "token_type": "Bearer",
        },
    )


def _draft_response(draft_id: str = "draft-1", message_id: str = "msg-1") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": draft_id,
            "message": {
                "id": message_id,
                "threadId": "thread-1",
                "labelIds": ["DRAFT"],
            },
        },
    )


def test_create_draft_refreshes_token_then_posts_draft() -> None:
    """Two HTTP calls expected: token refresh, then draft create."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if "oauth2.googleapis.com" in str(request.url):
            return _token_response()
        return _draft_response()

    client = _make_client(handler)
    result: DraftResult = client.create_draft(
        to=["alice@example.com"],
        subject="Follow-up: Q3 planning",
        body_text="Hi there,\n\nHere are the notes.",
    )

    assert len(captured) == 2
    # First call: OAuth refresh
    token_req = captured[0]
    assert "oauth2.googleapis.com/token" in str(token_req.url)
    form = dict(httpx.QueryParams(token_req.content.decode()))
    assert form["grant_type"] == "refresh_token"
    assert form["refresh_token"] == "rt_test"
    assert form["client_id"] == "cid"
    assert form["client_secret"] == "sec"

    # Second call: draft create
    draft_req = captured[1]
    assert "gmail.googleapis.com/gmail/v1/users/me/drafts" in str(draft_req.url)
    assert draft_req.headers["authorization"] == "Bearer access_token_xyz"
    body = json.loads(draft_req.content)
    raw = body["message"]["raw"]
    decoded = base64.urlsafe_b64decode(raw + "==")
    msg = email.message_from_bytes(decoded)
    assert msg["To"] == "alice@example.com"
    assert msg["Subject"] == "Follow-up: Q3 planning"
    # Body content reaches the wire
    assert "Here are the notes." in decoded.decode("utf-8")

    assert result.draft_id == "draft-1"
    assert result.message_id == "msg-1"
    assert result.thread_id == "thread-1"


def test_create_draft_supports_multiple_recipients() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if "oauth2" in str(request.url):
            return _token_response()
        return _draft_response()

    client = _make_client(handler)
    client.create_draft(
        to=["a@example.com", "b@example.com", "c@example.com"],
        subject="Hi",
        body_text="body",
    )

    draft_body = json.loads(captured[1].content)
    decoded = base64.urlsafe_b64decode(draft_body["message"]["raw"] + "==")
    msg = email.message_from_bytes(decoded)
    # Gmail accepts a comma-joined To header
    assert msg["To"] == "a@example.com, b@example.com, c@example.com"


def test_create_draft_raises_auth_error_on_refresh_failure() -> None:
    """400 from the token endpoint means the stored refresh_token is no
    good — surface that distinctly so the UI can prompt a reconnect."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth2" in str(request.url):
            return httpx.Response(400, json={"error": "invalid_grant"})
        return _draft_response()

    client = _make_client(handler)
    with pytest.raises(GmailAuthError):
        client.create_draft(
            to=["a@example.com"], subject="s", body_text="b"
        )


def test_create_draft_raises_auth_error_on_drafts_401() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth2" in str(request.url):
            return _token_response()
        return httpx.Response(401, json={"error": {"message": "Invalid Credentials"}})

    client = _make_client(handler)
    with pytest.raises(GmailAuthError):
        client.create_draft(
            to=["a@example.com"], subject="s", body_text="b"
        )


def test_create_draft_raises_generic_error_on_5xx() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth2" in str(request.url):
            return _token_response()
        return httpx.Response(503, text="service unavailable")

    client = _make_client(handler)
    with pytest.raises(GmailError):
        client.create_draft(
            to=["a@example.com"], subject="s", body_text="b"
        )


def test_create_draft_requires_at_least_one_recipient() -> None:
    """Empty `to` is a caller bug — fail fast rather than create an
    un-sendable draft."""

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no HTTP should be issued")

    client = _make_client(handler)
    with pytest.raises(ValueError):
        client.create_draft(to=[], subject="s", body_text="b")
