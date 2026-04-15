"""Embedder: thin OpenAI wrapper with retry + injectable client."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from app.ingestion.embedder import EMBEDDING_DIM, EmbeddingError, embed_chunks


@dataclass
class _FakeEmbedding:
    embedding: list[float]


@dataclass
class _FakeResponse:
    data: list[_FakeEmbedding]


class _FakeEmbeddingsAPI:
    def __init__(self, vectors_per_call: list[list[list[float]]] | None = None,
                 errors: list[Exception] | None = None) -> None:
        self._vectors = list(vectors_per_call or [])
        self._errors = list(errors or [])
        self.calls: list[dict[str, Any]] = []

    def create(self, *, model: str, input: list[str]) -> _FakeResponse:  # noqa: A002
        self.calls.append({"model": model, "input": list(input)})
        if self._errors:
            raise self._errors.pop(0)
        if not self._vectors:
            raise AssertionError("FakeEmbeddingsAPI: no canned vectors left")
        return _FakeResponse(data=[_FakeEmbedding(embedding=v) for v in self._vectors.pop(0)])


class _FakeClient:
    def __init__(self, embeddings: _FakeEmbeddingsAPI) -> None:
        self.embeddings = embeddings


def _vec(seed: float) -> list[float]:
    return [seed] * EMBEDDING_DIM


def test_embed_chunks_returns_one_vector_per_chunk() -> None:
    api = _FakeEmbeddingsAPI(vectors_per_call=[[_vec(0.1), _vec(0.2)]])
    client = _FakeClient(api)

    out = embed_chunks(["chunk one", "chunk two"], client=client)

    assert len(out) == 2
    assert all(len(v) == EMBEDDING_DIM for v in out)
    assert api.calls[0]["model"] == "text-embedding-3-small"
    assert api.calls[0]["input"] == ["chunk one", "chunk two"]


def test_empty_input_short_circuits_without_calling_openai() -> None:
    api = _FakeEmbeddingsAPI()
    client = _FakeClient(api)

    out = embed_chunks([], client=client)

    assert out == []
    assert api.calls == []


def test_retries_then_succeeds_on_transient_error() -> None:
    api = _FakeEmbeddingsAPI(
        vectors_per_call=[[_vec(0.5)]],
        errors=[RuntimeError("boom-1"), RuntimeError("boom-2")],
    )
    client = _FakeClient(api)

    out = embed_chunks(["only"], client=client, max_retries=3)

    assert len(out) == 1
    assert len(api.calls) == 3  # 2 failures + 1 success


def test_raises_embedding_error_after_exceeding_retry_budget() -> None:
    api = _FakeEmbeddingsAPI(
        errors=[RuntimeError("boom")] * 4,
    )
    client = _FakeClient(api)

    with pytest.raises(EmbeddingError):
        embed_chunks(["only"], client=client, max_retries=3)

    assert len(api.calls) == 3  # max_retries attempts total
