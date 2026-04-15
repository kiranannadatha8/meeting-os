"""GET /meetings/{id} — full detail payload (T15).

Returns decisions, action items, summary, and LangSmith run IDs. The
results UI depends on this shape — keep it tight.

Also covers POST /meetings/{id}/retry, which re-queues a failed meeting
by flipping its status back to `queued` and re-enqueueing the job. Only
`failed` meetings can be retried — anything else returns 409.
"""
from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.db import models
from app.db.session import SessionLocal
from app.main import app
from app.queue import get_queue_name, set_queue_name

pytestmark = pytest.mark.usefixtures("db_url", "redis_url", "truncate_meetings")


@pytest.fixture
def client(queue_name) -> TestClient:
    previous = get_queue_name()
    set_queue_name(queue_name)
    try:
        yield TestClient(app)
    finally:
        set_queue_name(previous)


def _seed_complete_meeting(
    *,
    user_id: str = "u-detail",
    title: str = "Quarterly planning",
    langsmith_run_ids: list[str] | None = None,
) -> UUID:
    with SessionLocal() as session:
        meeting = models.Meeting(
            user_id=user_id,
            title=title,
            source_type="text",
            source_filename="planning.txt",
            transcript="we will ship on friday",
            status="complete",
            langsmith_run_ids=langsmith_run_ids,
        )
        session.add(meeting)
        session.flush()
        session.add(
            models.Decision(
                meeting_id=meeting.id,
                title="Adopt pgvector",
                rationale="Fits our scale and simplifies ops",
                source_quote="we'll adopt pgvector",
            )
        )
        session.add(
            models.ActionItem(
                meeting_id=meeting.id,
                title="Write ADR",
                owner="kiran",
                due_date=date(2026, 5, 1),
                source_quote="kiran will write the ADR",
            )
        )
        session.add(
            models.Summary(
                meeting_id=meeting.id,
                tldr="Team decided to adopt pgvector and ship on Friday",
                highlights=["Adopt pgvector", "Ship on Friday", "Write the ADR"],
            )
        )
        session.commit()
        return meeting.id


def test_get_meeting_detail_returns_full_payload(client) -> None:
    meeting_id = _seed_complete_meeting(langsmith_run_ids=["run-a", "run-b"])

    response = client.get(f"/meetings/{meeting_id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(meeting_id)
    assert body["status"] == "complete"
    assert body["title"] == "Quarterly planning"
    assert body["transcript"] == "we will ship on friday"
    assert body["langsmith_run_ids"] == ["run-a", "run-b"]

    assert len(body["decisions"]) == 1
    assert body["decisions"][0]["title"] == "Adopt pgvector"
    assert body["decisions"][0]["rationale"].startswith("Fits")

    assert len(body["action_items"]) == 1
    assert body["action_items"][0]["owner"] == "kiran"
    assert body["action_items"][0]["due_date"] == "2026-05-01"

    assert body["summary"]["tldr"].startswith("Team decided")
    assert body["summary"]["highlights"] == [
        "Adopt pgvector",
        "Ship on Friday",
        "Write the ADR",
    ]


def test_get_meeting_detail_returns_404_for_unknown_id(client) -> None:
    response = client.get(f"/meetings/{uuid4()}")
    assert response.status_code == 404


def test_get_meeting_detail_returns_422_for_invalid_uuid(client) -> None:
    response = client.get("/meetings/not-a-uuid")
    assert response.status_code == 422


def test_get_meeting_detail_returns_empty_collections_for_queued_meeting(client) -> None:
    with SessionLocal() as session:
        meeting = models.Meeting(
            user_id="u-x",
            title="Fresh",
            source_type="text",
            source_filename="f.txt",
            transcript="hi",
            status="queued",
        )
        session.add(meeting)
        session.commit()
        session.refresh(meeting)
        meeting_id = meeting.id

    response = client.get(f"/meetings/{meeting_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert body["decisions"] == []
    assert body["action_items"] == []
    assert body["summary"] is None
    assert body["langsmith_run_ids"] is None


def _seed_meeting_with_status(status: str) -> UUID:
    with SessionLocal() as session:
        meeting = models.Meeting(
            user_id="u-retry",
            title="Retry me",
            source_type="text",
            source_filename="r.txt",
            transcript="hi",
            status=status,
            error_message="agents went sideways" if status == "failed" else None,
        )
        session.add(meeting)
        session.commit()
        session.refresh(meeting)
        return meeting.id


def test_retry_re_queues_a_failed_meeting(client) -> None:
    meeting_id = _seed_meeting_with_status("failed")

    response = client.post(f"/meetings/{meeting_id}/retry")

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["id"] == str(meeting_id)
    assert body["status"] == "queued"

    with SessionLocal() as session:
        row = session.get(models.Meeting, meeting_id)
        assert row.status == "queued"
        assert row.error_message is None


def test_retry_rejects_non_failed_meeting(client) -> None:
    meeting_id = _seed_meeting_with_status("processing")

    response = client.post(f"/meetings/{meeting_id}/retry")

    assert response.status_code == 409


def test_retry_returns_404_for_unknown_id(client) -> None:
    response = client.post(f"/meetings/{uuid4()}/retry")
    assert response.status_code == 404
