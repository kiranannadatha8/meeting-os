"""Pipeline state transitions: queued → processing → complete (or failed).

Also covers T07 chunk + embedding persistence — the real chunker runs but the
embedder is patched so OpenAI is never called.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.db import models
from app.db.session import SessionLocal
from app.ingestion.embedder import EMBEDDING_DIM, EmbeddingError
from app.pipeline import process_meeting

pytestmark = pytest.mark.usefixtures("db_url", "truncate_meetings")


def _seed_meeting(transcript: str = "hello") -> UUID:
    """Insert a queued meeting via the production session factory."""
    with SessionLocal() as session:
        meeting = models.Meeting(
            user_id=f"u-{uuid4().hex[:6]}",
            title="Test meeting",
            source_type="text",
            source_filename="t.txt",
            transcript=transcript,
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


def test_successful_run_transitions_queued_to_complete(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.pipeline.embed_chunks",
        lambda chunks: [[0.0] * EMBEDDING_DIM for _ in chunks],
    )
    meeting_id = _seed_meeting()

    process_meeting(str(meeting_id))

    assert _status(meeting_id) == "complete"
    assert _error_message(meeting_id) is None


def test_failed_run_marks_meeting_failed_with_error_message(monkeypatch) -> None:
    meeting_id = _seed_meeting()

    def _boom(*_: object) -> None:
        raise RuntimeError("agents went sideways")

    monkeypatch.setattr("app.pipeline._run_agents", _boom)

    with pytest.raises(RuntimeError):
        process_meeting(str(meeting_id))

    assert _status(meeting_id) == "failed"
    assert _error_message(meeting_id) == "agents went sideways"


def test_unknown_meeting_id_raises() -> None:
    with pytest.raises(LookupError):
        process_meeting(str(uuid4()))


def test_pipeline_persists_chunks_with_embeddings(monkeypatch) -> None:
    transcript = "word " * 1500  # ~1500 tokens → multiple chunks at 500/50
    meeting_id = _seed_meeting(transcript=transcript)

    captured: dict[str, list[str]] = {}

    def _fake_embed(chunks: list[str]) -> list[list[float]]:
        captured["chunks"] = chunks
        return [[0.01 * (i + 1)] * EMBEDDING_DIM for i in range(len(chunks))]

    monkeypatch.setattr("app.pipeline.embed_chunks", _fake_embed)

    process_meeting(str(meeting_id))

    with SessionLocal() as session:
        rows = session.execute(
            select(models.Chunk)
            .where(models.Chunk.meeting_id == meeting_id)
            .order_by(models.Chunk.chunk_index)
        ).scalars().all()

    assert len(rows) == len(captured["chunks"]) >= 2
    assert [r.chunk_index for r in rows] == list(range(len(rows)))
    assert all(r.embedding is not None and len(r.embedding) == EMBEDDING_DIM for r in rows)
    assert _status(meeting_id) == "complete"


def test_pipeline_persists_placeholder_summary_row(monkeypatch) -> None:
    """T10: graph runs on every meeting and writes a (placeholder) Summary row."""
    monkeypatch.setattr(
        "app.pipeline.embed_chunks",
        lambda chunks: [[0.0] * EMBEDDING_DIM for _ in chunks],
    )
    meeting_id = _seed_meeting(transcript="hello world")

    process_meeting(str(meeting_id))

    with SessionLocal() as session:
        summary = session.execute(
            select(models.Summary).where(models.Summary.meeting_id == meeting_id)
        ).scalar_one()
    assert summary.tldr == ""
    assert summary.highlights == []


def test_pipeline_marks_failed_when_embedding_exhausts_retries(monkeypatch) -> None:
    meeting_id = _seed_meeting(transcript="word " * 100)

    def _always_fail(_: list[str]) -> list[list[float]]:
        raise EmbeddingError("OpenAI is down")

    monkeypatch.setattr("app.pipeline.embed_chunks", _always_fail)

    with pytest.raises(EmbeddingError):
        process_meeting(str(meeting_id))

    assert _status(meeting_id) == "failed"
    assert _error_message(meeting_id) == "OpenAI is down"
