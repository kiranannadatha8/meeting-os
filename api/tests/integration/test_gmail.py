"""Integration test that hits the real Gmail API.

Skipped unless `GMAIL_TEST_REFRESH_TOKEN` + `GOOGLE_CLIENT_ID` +
`GOOGLE_CLIENT_SECRET` are set. The draft stays in the test Gmail
account's drafts folder — the test does NOT send it. The caller is
expected to delete it when done.

Run locally with:
    GMAIL_TEST_REFRESH_TOKEN=... \
    GOOGLE_CLIENT_ID=... \
    GOOGLE_CLIENT_SECRET=... \
    .venv/bin/python -m pytest tests/integration/test_gmail.py -v
"""
from __future__ import annotations

import os

import pytest

from app.mcp.gmail import GmailClient

REFRESH_TOKEN = os.environ.get("GMAIL_TEST_REFRESH_TOKEN")
CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")

pytestmark = pytest.mark.skipif(
    not (REFRESH_TOKEN and CLIENT_ID and CLIENT_SECRET),
    reason="GMAIL_TEST_REFRESH_TOKEN/GOOGLE_CLIENT_ID/SECRET not configured",
)


def test_creates_draft_in_test_account() -> None:
    client = GmailClient(
        refresh_token=REFRESH_TOKEN,  # type: ignore[arg-type]
        client_id=CLIENT_ID,  # type: ignore[arg-type]
        client_secret=CLIENT_SECRET,  # type: ignore[arg-type]
    )
    result = client.create_draft(
        to=["test@example.com"],
        subject="MeetingOS integration test — follow-up draft",
        body_text=(
            "TL;DR\nThis is a throwaway draft from the test suite.\n\n"
            "Action items\n- Delete this draft"
        ),
    )
    assert result.draft_id
    assert result.message_id
    assert result.thread_id
