"""Pipeline state transitions: queued → processing → complete (or failed)."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.db import models
from app.db.session import SessionLocal
from app.pipeline import process_meeting

pytestmark = pytest.mark.usefixtures("db_url", "truncate_meetings")


def _seed_meeting() -> UUID:
    """Insert a queued meeting via the production session factory."""
    with SessionLocal() as session:
        meeting = models.Meeting(
            user_id=f"u-{uuid4().hex[:6]}",
            title="Test meeting",
            source_type="text",
            source_filename="t.txt",
            transcript="hello",
            status="queued",
        )
        session.add(meeting)
        session.commit()
        session.refresh(meeting)
        return meeting.id


def _status(meeting_id: UUID) -> str:
    with SessionLocal() as session:
        return session.execute(
            select(models.Meeting.status).where(models.Meeting.id == meeting_id)
        ).scalar_one()


def _error_message(meeting_id: UUID) -> str | None:
    with SessionLocal() as session:
        return session.execute(
            select(models.Meeting.error_message).where(models.Meeting.id == meeting_id)
        ).scalar_one()


def test_successful_run_transitions_queued_to_complete() -> None:
    meeting_id = _seed_meeting()

    process_meeting(str(meeting_id))

    assert _status(meeting_id) == "complete"
    assert _error_message(meeting_id) is None


def test_failed_run_marks_meeting_failed_with_error_message(monkeypatch) -> None:
    meeting_id = _seed_meeting()

    def _boom(_: str) -> None:
        raise RuntimeError("agents went sideways")

    monkeypatch.setattr("app.pipeline._run_agents", _boom)

    with pytest.raises(RuntimeError):
        process_meeting(str(meeting_id))

    assert _status(meeting_id) == "failed"
    assert _error_message(meeting_id) == "agents went sideways"


def test_unknown_meeting_id_raises() -> None:
    with pytest.raises(LookupError):
        process_meeting(str(uuid4()))
