"""End-to-end: enqueue → worker consumes → meeting status transitions."""
from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.db import models
from app.db.session import SessionLocal
from app.queue import enqueue_meeting_job, get_queue_name, set_queue_name
from app.worker import build_worker

pytestmark = pytest.mark.usefixtures(
    "db_url", "redis_url", "truncate_meetings", "cleanup_queue"
)


@pytest.fixture
def isolated_queue(queue_name):
    previous = get_queue_name()
    set_queue_name(queue_name)
    yield queue_name
    set_queue_name(previous)


def _seed_meeting() -> UUID:
    with SessionLocal() as session:
        meeting = models.Meeting(
            user_id=f"u-{uuid4().hex[:6]}",
            title="Worker test",
            source_type="text",
            source_filename="t.txt",
            transcript="hello",
            status="queued",
        )
        session.add(meeting)
        session.commit()
        session.refresh(meeting)
        return meeting.id


def _read_status(meeting_id: UUID) -> str:
    with SessionLocal() as session:
        return session.execute(
            select(models.Meeting.status).where(models.Meeting.id == meeting_id)
        ).scalar_one()


async def _wait_for_status(meeting_id: UUID, target: str, timeout: float = 5.0) -> str:
    """Poll until the meeting reaches the target status or timeout."""
    deadline = asyncio.get_event_loop().time() + timeout
    last = ""
    while asyncio.get_event_loop().time() < deadline:
        last = _read_status(meeting_id)
        if last == target:
            return last
        await asyncio.sleep(0.05)
    return last


async def _run_worker_until(meeting_id: UUID, target: str) -> str:
    worker = build_worker()
    try:
        return await _wait_for_status(meeting_id, target)
    finally:
        await worker.close()


async def test_worker_processes_job_and_marks_complete(
    isolated_queue, monkeypatch
) -> None:
    from app.ingestion.embedder import EMBEDDING_DIM

    monkeypatch.setattr(
        "app.pipeline.embed_chunks",
        lambda chunks: [[0.0] * EMBEDDING_DIM for _ in chunks],
    )

    meeting_id = _seed_meeting()
    await enqueue_meeting_job(str(meeting_id))

    final = await _run_worker_until(meeting_id, "complete")

    assert final == "complete"


async def test_worker_marks_failed_when_pipeline_raises(
    isolated_queue, monkeypatch
) -> None:
    def _boom(*_: object) -> None:
        raise RuntimeError("worker boom")

    monkeypatch.setattr("app.pipeline._run_agents", _boom)

    meeting_id = _seed_meeting()
    await enqueue_meeting_job(str(meeting_id))

    final = await _run_worker_until(meeting_id, "failed")

    assert final == "failed"
    with SessionLocal() as session:
        err = session.execute(
            select(models.Meeting.error_message).where(models.Meeting.id == meeting_id)
        ).scalar_one()
    assert err == "worker boom"
