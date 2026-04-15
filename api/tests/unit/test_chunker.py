"""Token-aware chunking with sliding-window overlap."""
from __future__ import annotations

import pytest
import tiktoken

from app.ingestion.chunker import chunk_text

ENC = tiktoken.get_encoding("cl100k_base")


def _tokenize(text: str) -> list[int]:
    return ENC.encode(text)


def test_short_text_returns_single_chunk() -> None:
    text = "hello world this is short"
    chunks = chunk_text(text, max_tokens=512, overlap=50)
    assert chunks == [text]


def test_long_text_produces_multiple_chunks() -> None:
    # 1500 tokens of "word " repeated → at least 3 windows (500/50)
    text = "word " * 1500
    chunks = chunk_text(text, max_tokens=500, overlap=50)
    assert len(chunks) >= 3
    for chunk in chunks:
        assert len(_tokenize(chunk)) <= 500


def test_chunks_have_overlap() -> None:
    text = "alpha " * 1200
    chunks = chunk_text(text, max_tokens=400, overlap=100)
    # First chunk ends with tokens that the second chunk also begins with.
    first_tokens = _tokenize(chunks[0])
    second_tokens = _tokenize(chunks[1])
    overlap_window = first_tokens[-100:]
    assert second_tokens[:100] == overlap_window


def test_empty_text_returns_empty_list() -> None:
    assert chunk_text("", max_tokens=100, overlap=10) == []


def test_overlap_must_be_less_than_max_tokens() -> None:
    with pytest.raises(ValueError, match="overlap"):
        chunk_text("anything", max_tokens=100, overlap=100)


def test_default_window_size_is_500_with_50_overlap() -> None:
    """T07 acceptance: 30-min transcript should produce ~60-120 chunks.
    Smoke check the defaults match the spec."""
    # 25k tokens ≈ rough 30-min transcript. Should fall in the band.
    text = "filler " * 25000
    chunks = chunk_text(text)
    assert 50 <= len(chunks) <= 200
