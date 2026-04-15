"""Unit tests for the Linear MCP tool wrapper.

We exercise the GraphQL shape + error-surface contract by intercepting
the HTTP layer with `httpx.MockTransport` — no real network calls, but
the full client path runs.
"""
from __future__ import annotations

import json

import httpx
import pytest

from app.mcp.linear import (
    ActionItemInput,
    DispatchResult,
    LinearAuthError,
    LinearClient,
    LinearError,
)

TEAM_ID = "team-uuid-1"


def _make_client(
    handler,  # type: ignore[no-untyped-def]
    *,
    api_key: str = "lin_api_test",
) -> LinearClient:
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport, base_url="https://api.linear.app")
    return LinearClient(api_key=api_key, http=http)


def _success_response(items: list[dict[str, str]]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "data": {
                "issueCreate": {
                    "success": True,
                    "issue": items[0] if items else None,
                }
            }
        },
    )


def test_create_issues_posts_one_mutation_per_item() -> None:
    """Each action item becomes its own issueCreate call so partial failures
    don't take down the whole batch — we want per-item error granularity."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        idx = len(captured)
        return _success_response(
            [
                {
                    "id": f"issue-{idx}",
                    "identifier": f"ENG-{idx}",
                    "url": f"https://linear.app/eng/issue/ENG-{idx}",
                }
            ]
        )

    client = _make_client(handler)
    items = [
        ActionItemInput(title="Write spec", description="for the migration"),
        ActionItemInput(title="Send update", description=None),
    ]

    result: DispatchResult = client.create_issues(items, team_id=TEAM_ID)

    assert len(captured) == 2
    first = json.loads(captured[0].content)
    assert "issueCreate" in first["query"]
    assert first["variables"]["input"]["teamId"] == TEAM_ID
    assert first["variables"]["input"]["title"] == "Write spec"
    assert first["variables"]["input"]["description"] == "for the migration"

    assert len(result.created) == 2
    assert result.errors == []
    assert result.created[0].url == "https://linear.app/eng/issue/ENG-1"
    assert result.created[1].identifier == "ENG-2"


def test_create_issues_sets_authorization_header() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _success_response(
            [{"id": "1", "identifier": "A-1", "url": "https://linear.app/a/A-1"}]
        )

    client = _make_client(handler, api_key="lin_api_secret")
    client.create_issues([ActionItemInput(title="x")], team_id=TEAM_ID)

    # Linear accepts the personal API key directly in the Authorization header
    # (no "Bearer" prefix). See https://developers.linear.app/docs/graphql/working-with-the-graphql-api
    assert captured[0].headers["authorization"] == "lin_api_secret"


def test_create_issues_collects_per_item_errors() -> None:
    """GraphQL can return `success: false` on a per-call basis. Those land
    in `errors` rather than raising — the caller can still show which
    items succeeded."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 2:
            return httpx.Response(
                200,
                json={
                    "data": {"issueCreate": {"success": False, "issue": None}},
                    "errors": [{"message": "teamId not found"}],
                },
            )
        return _success_response(
            [{"id": "1", "identifier": "A-1", "url": "https://linear.app/a/A-1"}]
        )

    client = _make_client(handler)
    result = client.create_issues(
        [
            ActionItemInput(title="Good item"),
            ActionItemInput(title="Bad item"),
        ],
        team_id=TEAM_ID,
    )

    assert len(result.created) == 1
    assert result.created[0].identifier == "A-1"
    assert len(result.errors) == 1
    assert result.errors[0].action_item_title == "Bad item"
    assert "teamId" in result.errors[0].message


def test_create_issues_raises_on_auth_failure() -> None:
    """401 is fatal — it means the API key is wrong, so don't retry the
    rest of the batch against a broken credential."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Invalid API key"})

    client = _make_client(handler)

    with pytest.raises(LinearAuthError):
        client.create_issues([ActionItemInput(title="x")], team_id=TEAM_ID)


def test_create_issues_raises_on_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    client = _make_client(handler)

    with pytest.raises(LinearError):
        client.create_issues([ActionItemInput(title="x")], team_id=TEAM_ID)


def test_create_issues_empty_list_is_noop() -> None:
    """No calls = no side effects; guard against silly callers."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _success_response([])

    client = _make_client(handler)
    result = client.create_issues([], team_id=TEAM_ID)

    assert captured == []
    assert result.created == []
    assert result.errors == []
