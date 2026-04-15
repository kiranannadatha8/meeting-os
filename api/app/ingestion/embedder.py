"""Embedder: thin wrapper over OpenAI embeddings with bounded retries.

The OpenAI client is injectable so unit tests can run without network access
or API credentials. Retries cover transient errors (rate limits, network
flakes); after `max_retries` attempts we raise `EmbeddingError` so the
caller (the pipeline) can mark the meeting `failed`.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol

from app.config import get_settings

EMBEDDING_DIM = 1536
DEFAULT_MODEL = "text-embedding-3-small"
DEFAULT_MAX_RETRIES = 3

logger = logging.getLogger(__name__)


class EmbeddingError(RuntimeError):
    """Raised when embedding fails after exhausting retries."""


class _EmbeddingsClient(Protocol):
    """Structural type matching the surface we use of `openai.OpenAI`."""

    embeddings: Any


def _default_client() -> _EmbeddingsClient:
    from openai import OpenAI  # local import keeps unit tests offline

    return OpenAI(api_key=get_settings().openai_api_key)


def embed_chunks(
    chunks: list[str],
    *,
    client: _EmbeddingsClient | None = None,
    model: str = DEFAULT_MODEL,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> list[list[float]]:
    """Embed `chunks` in a single batched call. Retry up to `max_retries`."""
    if not chunks:
        return []

    if client is None:
        client = _default_client()

    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            response = client.embeddings.create(model=model, input=chunks)
            return [item.embedding for item in response.data]
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Embedding attempt %d/%d failed: %s", attempt, max_retries, exc
            )

    raise EmbeddingError(
        f"Embedding failed after {max_retries} attempts: {last_exc}"
    ) from last_exc
