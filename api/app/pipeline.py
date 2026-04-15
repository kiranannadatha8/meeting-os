"""Per-meeting processing pipeline.

For W1 this is a stub: load the meeting, mark it processing, run agents
(no-op until T10–T13), mark it complete. Crashes get logged and the
meeting is marked failed with the error message captured.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select

from app.db import models
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def process_meeting(meeting_id: str) -> None:
    """Process one meeting end-to-end. Synchronous; called by the worker.

    State machine: queued → processing → (complete | failed).
    Re-raises after marking failed so BullMQ can apply its own retry policy.
    """
    target_id = UUID(meeting_id)

    with SessionLocal() as session:
        meeting = session.execute(
            select(models.Meeting).where(models.Meeting.id == target_id)
        ).scalar_one_or_none()
        if meeting is None:
            raise LookupError(f"Meeting not found: {meeting_id}")

        meeting.status = "processing"
        meeting.error_message = None
        session.commit()

    try:
        _run_agents(meeting_id)
    except Exception as exc:
        logger.exception("Pipeline failed for meeting %s", meeting_id)
        with SessionLocal() as session:
            session.execute(
                models.Meeting.__table__.update()
                .where(models.Meeting.id == target_id)
                .values(status="failed", error_message=str(exc))
            )
            session.commit()
        raise

    with SessionLocal() as session:
        session.execute(
            models.Meeting.__table__.update()
            .where(models.Meeting.id == target_id)
            .values(status="complete", error_message=None)
        )
        session.commit()


def _run_agents(meeting_id: str) -> None:
    """No-op stub for W1 — replaced by the LangGraph DAG in T10."""
    logger.info("Stub agent run for meeting %s", meeting_id)
