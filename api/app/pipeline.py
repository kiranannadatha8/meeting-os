"""Per-meeting processing pipeline.

Loads the meeting, marks it `processing`, chunks the transcript and embeds
each chunk via OpenAI, persists the chunk rows, then marks `complete`.
Crashes log with traceback and the meeting is marked `failed` with the
error message captured for the UI.
"""
from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.db.session import SessionLocal
from app.graph import build_agent_graph
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
    """T07 chunks + embeds; T10 runs the LangGraph DAG and persists agent output."""
    chunks = chunk_text(transcript)
    if chunks:
        embeddings = embed_chunks(chunks)
        if len(embeddings) != len(chunks):
            raise RuntimeError(
                f"Embedding count mismatch: {len(embeddings)} vectors for {len(chunks)} chunks"
            )
    else:
        logger.info("Meeting %s has empty transcript; skipping chunk persistence", meeting_id)
        embeddings = []

    graph = build_agent_graph()
    state = graph.invoke({"meeting_id": str(meeting_id), "transcript": transcript})

    with SessionLocal() as session:
        if chunks:
            _persist_chunks(session, meeting_id, chunks, embeddings)
        _persist_agent_output(session, meeting_id, state)
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


def _persist_agent_output(session: Session, meeting_id: UUID, state: dict) -> None:
    """Write decisions, action items, and the summary row from graph state.

    T10 ships with no-op agents so `decisions` / `action_items` are empty;
    the summary row is always written so the results UI can assume it exists.
    """
    for decision in state.get("decisions") or []:
        session.add(
            models.Decision(
                meeting_id=meeting_id,
                title=decision["title"],
                rationale=decision["rationale"],
                source_quote=decision["source_quote"],
            )
        )
    for item in state.get("action_items") or []:
        due = item.get("due_date")
        session.add(
            models.ActionItem(
                meeting_id=meeting_id,
                title=item["title"],
                owner=item.get("owner"),
                due_date=date.fromisoformat(due) if isinstance(due, str) else due,
                source_quote=item["source_quote"],
            )
        )
    summary = state.get("summary") or {"tldr": "", "highlights": []}
    session.add(
        models.Summary(
            meeting_id=meeting_id,
            tldr=summary.get("tldr", ""),
            highlights=list(summary.get("highlights") or []),
        )
    )
