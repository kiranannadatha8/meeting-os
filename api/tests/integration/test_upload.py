"""POST /meetings — upload a transcript, persist a row, enqueue a job."""
from __future__ import annotations

import json
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import models
from app.main import app
from app.queue import get_queue_name, set_queue_name

pytestmark = pytest.mark.usefixtures(
    "db_url", "redis_url", "truncate_meetings", "cleanup_queue"
)


@pytest.fixture
def client(queue_name) -> TestClient:
    """Real DB + Redis; isolation comes from per-test queue name + truncate."""
    previous = get_queue_name()
    set_queue_name(queue_name)
    try:
        yield TestClient(app)
    finally:
        set_queue_name(previous)


def test_valid_txt_upload_returns_201_with_queued_status(client) -> None:
    files = {"file": ("notes.txt", b"Alice: hello\nBob: hi", "text/plain")}
    data = {"title": "Sync 2026-04-14", "user_id": "u-1"}

    response = client.post("/meetings", files=files, data=data)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "queued"
    UUID(body["id"])  # must be a parseable UUID


def test_valid_vtt_upload_persists_normalised_transcript(client, engine) -> None:
    vtt = (
        b"WEBVTT\n\n"
        b"00:00:01.000 --> 00:00:02.000\n"
        b"Just a line.\n"
    )
    files = {"file": ("call.vtt", vtt, "text/vtt")}
    data = {"title": "Cap call", "user_id": "u-2"}

    response = client.post("/meetings", files=files, data=data)
    assert response.status_code == 201
    meeting_id = UUID(response.json()["id"])

    with engine.connect() as conn:
        row = conn.execute(
            select(models.Meeting.transcript, models.Meeting.status, models.Meeting.user_id)
            .where(models.Meeting.id == meeting_id)
        ).one()

    assert row.transcript.strip() == "Just a line."
    assert row.status == "queued"
    assert row.user_id == "u-2"


def test_unsupported_extension_returns_422(client) -> None:
    files = {"file": ("notes.pdf", b"%PDF-1.4 fake", "application/pdf")}
    data = {"title": "Bad", "user_id": "u-1"}

    response = client.post("/meetings", files=files, data=data)
    assert response.status_code == 422


def test_redis_queue_contains_job_with_meeting_id(
    client, redis_client, queue_name
) -> None:
    files = {"file": ("notes.txt", b"hello", "text/plain")}
    data = {"title": "Quick sync", "user_id": "u-3"}

    response = client.post("/meetings", files=files, data=data)
    assert response.status_code == 201
    meeting_id = response.json()["id"]

    # BullMQ stores waiting job IDs in `bull:<queue>:wait` (LIST)
    job_ids = redis_client.lrange(f"bull:{queue_name}:wait", 0, -1)
    assert job_ids, "no jobs landed in the BullMQ wait list"

    # Job hash at `bull:<queue>:<id>` has a `data` field with our payload
    payloads = []
    for jid in job_ids:
        raw = redis_client.hget(f"bull:{queue_name}:{jid}", "data")
        if raw:
            payloads.append(json.loads(raw))

    assert any(p.get("meeting_id") == meeting_id for p in payloads), payloads
