"""Per-meeting processing pipeline.

Loads the meeting, marks it `processing`, chunks the transcript and embeds
each chunk via OpenAI, persists the chunk rows, then marks `complete`.
Crashes log with traceback and the meeting is marked `failed` with the
error message captured for the UI.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.db.session import SessionLocal
from app.ingestion.chunker import chunk_text
from app.ingestion.embedder import embed_chunks

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
        transcript = meeting.transcript

    try:
        _run_agents(target_id, transcript)
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


def _run_agents(meeting_id: UUID, transcript: str) -> None:
    """T07: chunk + embed + persist. T10 will replace this with the LangGraph DAG."""
    chunks = chunk_text(transcript)
    if not chunks:
        logger.info("Meeting %s has empty transcript; skipping chunk persistence", meeting_id)
        return

    embeddings = embed_chunks(chunks)
    if len(embeddings) != len(chunks):
        raise RuntimeError(
            f"Embedding count mismatch: {len(embeddings)} vectors for {len(chunks)} chunks"
        )

    with SessionLocal() as session:
        _persist_chunks(session, meeting_id, chunks, embeddings)
        session.commit()


def _persist_chunks(
    session: Session,
    meeting_id: UUID,
    chunks: list[str],
    embeddings: list[list[float]],
) -> None:
    rows = [
        models.Chunk(
            meeting_id=meeting_id,
            chunk_index=i,
            content=content,
            embedding=embedding,
        )
        for i, (content, embedding) in enumerate(zip(chunks, embeddings, strict=True))
    ]
    session.add_all(rows)
