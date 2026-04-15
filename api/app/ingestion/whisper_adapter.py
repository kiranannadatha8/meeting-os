"""Whisper transcription adapter.

Wraps the OpenAI audio transcription endpoint with bounded retries and an
upfront 25MB size cap (the OpenAI documented limit at the time of writing).
The OpenAI client is injectable so unit tests run offline.

Audio bytes are passed through as-is and dropped after transcription — they
are never written to disk by this module.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol

from app.config import get_settings

AUDIO_SIZE_LIMIT_BYTES = 25 * 1024 * 1024  # 25 MiB — OpenAI Whisper API cap
DEFAULT_MODEL = "whisper-1"
DEFAULT_MAX_RETRIES = 3

logger = logging.getLogger(__name__)


class TranscriptionError(RuntimeError):
    """Raised when transcription fails after exhausting retries."""


class AudioTooLargeError(ValueError):
    """Raised before any API call when the audio payload exceeds the cap."""


class _AudioClient(Protocol):
    """Structural type matching the surface we use of `openai.OpenAI`."""

    audio: Any


def _default_client() -> _AudioClient:
    from openai import OpenAI  # local import keeps unit tests offline

    return OpenAI(api_key=get_settings().openai_api_key)


def transcribe_audio(
    audio: bytes,
    *,
    filename: str,
    client: _AudioClient | None = None,
    model: str = DEFAULT_MODEL,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> str:
    """Transcribe `audio` via Whisper and return the plain-text transcript.

    Raises `AudioTooLargeError` immediately if `audio` is over the documented
    Whisper limit (avoids a wasted upload and a 4xx round-trip). Transient
    errors are retried up to `max_retries` times; persistent failures raise
    `TranscriptionError` so the caller can mark the meeting failed.
    """
    if len(audio) > AUDIO_SIZE_LIMIT_BYTES:
        raise AudioTooLargeError(
            f"Audio payload {len(audio)} bytes exceeds {AUDIO_SIZE_LIMIT_BYTES} byte limit"
        )

    if client is None:
        client = _default_client()

    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            response = client.audio.transcriptions.create(
                model=model,
                file=(filename, audio),
            )
            return response.text
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Whisper attempt %d/%d failed: %s", attempt, max_retries, exc
            )

    raise TranscriptionError(
        f"Transcription failed after {max_retries} attempts: {last_exc}"
    ) from last_exc
