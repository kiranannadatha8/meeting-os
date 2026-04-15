"""Whisper adapter: thin OpenAI wrapper with retry + injectable client + size cap.

Mirrors the embedder pattern. Audio bytes never touch disk — they're streamed
into the OpenAI client and dropped after transcription.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from app.ingestion.whisper_adapter import (
    AUDIO_SIZE_LIMIT_BYTES,
    AudioTooLargeError,
    TranscriptionError,
    transcribe_audio,
)


@dataclass
class _FakeTranscription:
    text: str


class _FakeTranscriptionsAPI:
    def __init__(
        self,
        texts: list[str] | None = None,
        errors: list[Exception] | None = None,
    ) -> None:
        self._texts = list(texts or [])
        self._errors = list(errors or [])
        self.calls: list[dict[str, Any]] = []

    def create(
        self,
        *,
        model: str,
        file: tuple[str, bytes, str] | tuple[str, bytes],
        **kwargs: Any,
    ) -> _FakeTranscription:
        # Capture metadata only — never store the audio bytes themselves
        # (we only check the filename + size to assert the call was correctly
        # framed; storing the bytes would defeat the whole "no disk" claim).
        filename = file[0]
        size = len(file[1])
        self.calls.append({"model": model, "filename": filename, "size": size, **kwargs})
        if self._errors:
            raise self._errors.pop(0)
        if not self._texts:
            raise AssertionError("FakeTranscriptionsAPI: no canned text left")
        return _FakeTranscription(text=self._texts.pop(0))


class _FakeAudioAPI:
    def __init__(self, transcriptions: _FakeTranscriptionsAPI) -> None:
        self.transcriptions = transcriptions


class _FakeClient:
    def __init__(self, audio: _FakeAudioAPI) -> None:
        self.audio = audio


def _client_with(*, texts: list[str] | None = None, errors: list[Exception] | None = None) -> _FakeClient:
    api = _FakeTranscriptionsAPI(texts=texts, errors=errors)
    return _FakeClient(_FakeAudioAPI(api))


def test_transcribe_audio_returns_text_for_supported_file() -> None:
    client = _client_with(texts=["hello from whisper"])

    out = transcribe_audio(b"\x00\x01\x02fake-mp3", filename="meeting.mp3", client=client)

    assert out == "hello from whisper"
    call = client.audio.transcriptions.calls[0]  # type: ignore[attr-defined]
    assert call["model"] == "whisper-1"
    assert call["filename"] == "meeting.mp3"
    assert call["size"] == len(b"\x00\x01\x02fake-mp3")


def test_transcribe_audio_rejects_files_above_size_limit() -> None:
    client = _client_with(texts=["unused"])
    oversized = b"\x00" * (AUDIO_SIZE_LIMIT_BYTES + 1)

    with pytest.raises(AudioTooLargeError):
        transcribe_audio(oversized, filename="big.mp3", client=client)

    # The OpenAI client must NOT be called when the file is rejected up front.
    assert client.audio.transcriptions.calls == []  # type: ignore[attr-defined]


def test_transcribe_audio_retries_then_succeeds_on_transient_error() -> None:
    client = _client_with(
        texts=["recovered"],
        errors=[RuntimeError("net-1"), RuntimeError("net-2")],
    )

    out = transcribe_audio(b"audio", filename="x.wav", client=client, max_retries=3)

    assert out == "recovered"
    assert len(client.audio.transcriptions.calls) == 3  # type: ignore[attr-defined]


def test_transcribe_audio_raises_after_exceeding_retry_budget() -> None:
    client = _client_with(errors=[RuntimeError("boom")] * 4)

    with pytest.raises(TranscriptionError):
        transcribe_audio(b"audio", filename="x.wav", client=client, max_retries=3)

    assert len(client.audio.transcriptions.calls) == 3  # type: ignore[attr-defined]
