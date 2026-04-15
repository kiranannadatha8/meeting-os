"""POST /meetings — audio path: Whisper transcription wired into the upload route.

Whisper itself is monkeypatched so the test runs offline; what we actually
verify is the route's behaviour around it: source_type tagging, 422 on
oversized payloads, and that transcribed text feeds the rest of the pipeline
(i.e. lands as the meeting's `transcript` column).
"""
from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import models
from app.ingestion.whisper_adapter import AUDIO_SIZE_LIMIT_BYTES
from app.main import app
from app.queue import get_queue_name, set_queue_name

pytestmark = pytest.mark.usefixtures(
    "db_url", "redis_url", "truncate_meetings", "cleanup_queue"
)


@pytest.fixture
def client(queue_name):
    previous = get_queue_name()
    set_queue_name(queue_name)
    try:
        yield TestClient(app)
    finally:
        set_queue_name(previous)


def _stub_transcribe(text: str = "Stubbed Whisper transcript."):
    """Return a function with the same signature as `transcribe_audio` that
    records its call and never touches the network."""
    calls: list[dict[str, object]] = []

    def _impl(audio: bytes, *, filename: str, **_: object) -> str:
        calls.append({"size": len(audio), "filename": filename})
        return text

    return _impl, calls


def test_mp3_upload_transcribes_and_persists_with_audio_source(
    client, engine, monkeypatch
) -> None:
    stub, calls = _stub_transcribe("Hello from the meeting.")
    monkeypatch.setattr("app.routes.meetings.transcribe_audio", stub)

    files = {"file": ("call.mp3", b"\x00fake-mp3-bytes", "audio/mpeg")}
    data = {"title": "Recorded sync", "user_id": "u-audio-1"}

    response = client.post("/meetings", files=files, data=data)
    assert response.status_code == 201, response.text

    meeting_id = UUID(response.json()["id"])

    with engine.connect() as conn:
        row = conn.execute(
            select(
                models.Meeting.transcript,
                models.Meeting.source_type,
                models.Meeting.source_filename,
            ).where(models.Meeting.id == meeting_id)
        ).one()

    assert row.transcript == "Hello from the meeting."
    assert row.source_type == "audio"
    assert row.source_filename == "call.mp3"
    # Whisper called exactly once with the raw bytes from the upload.
    assert len(calls) == 1
    assert calls[0]["filename"] == "call.mp3"
    assert calls[0]["size"] == len(b"\x00fake-mp3-bytes")


def test_wav_upload_uses_audio_path(client, monkeypatch) -> None:
    stub, calls = _stub_transcribe("wav transcript")
    monkeypatch.setattr("app.routes.meetings.transcribe_audio", stub)

    files = {"file": ("clip.wav", b"RIFFfake", "audio/wav")}
    data = {"title": "Wav meet", "user_id": "u-audio-2"}

    response = client.post("/meetings", files=files, data=data)
    assert response.status_code == 201
    assert len(calls) == 1
    assert calls[0]["filename"] == "clip.wav"


def test_audio_above_25mb_returns_413_and_does_not_call_whisper(
    client, monkeypatch
) -> None:
    stub, calls = _stub_transcribe()
    monkeypatch.setattr("app.routes.meetings.transcribe_audio", stub)

    oversized = b"\x00" * (AUDIO_SIZE_LIMIT_BYTES + 1)
    files = {"file": ("big.mp3", oversized, "audio/mpeg")}
    data = {"title": "Too big", "user_id": "u-audio-3"}

    response = client.post("/meetings", files=files, data=data)

    assert response.status_code == 413
    assert calls == []
