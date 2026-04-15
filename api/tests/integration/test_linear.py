"""Integration test that hits the real Linear API.

Skipped unless both `LINEAR_TEST_API_KEY` and `LINEAR_TEST_TEAM_ID`
are provided — we don't want CI charging unknown Linear workspaces
with throwaway tickets.

Run it locally with:
    LINEAR_TEST_API_KEY=lin_api_xxx LINEAR_TEST_TEAM_ID=<uuid> \
        .venv/bin/python -m pytest tests/integration/test_linear.py -v
"""
from __future__ import annotations

import os

import pytest

from app.mcp.linear import ActionItemInput, LinearClient

LINEAR_API_KEY = os.environ.get("LINEAR_TEST_API_KEY")
LINEAR_TEAM_ID = os.environ.get("LINEAR_TEST_TEAM_ID")

pytestmark = pytest.mark.skipif(
    not (LINEAR_API_KEY and LINEAR_TEAM_ID),
    reason="LINEAR_TEST_API_KEY + LINEAR_TEST_TEAM_ID not configured",
)


def test_create_two_issues_real_workspace() -> None:
    """Verifies round-trip against Linear: two unique titles land as two
    issues with valid identifiers + URLs. The caller is expected to clean
    up the created tickets."""
    client = LinearClient(api_key=LINEAR_API_KEY)  # type: ignore[arg-type]
    result = client.create_issues(
        [
            ActionItemInput(
                title="MeetingOS integration test — write spec",
                description="This is a throwaway ticket; safe to delete.",
            ),
            ActionItemInput(
                title="MeetingOS integration test — send update",
                description=None,
            ),
        ],
        team_id=LINEAR_TEAM_ID,  # type: ignore[arg-type]
    )

    assert result.errors == []
    assert len(result.created) == 2
    for issue in result.created:
        assert issue.identifier  # e.g. "ENG-42"
        assert issue.url.startswith("https://linear.app/")
