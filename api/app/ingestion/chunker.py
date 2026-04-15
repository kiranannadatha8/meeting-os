"""Token-aware sliding-window chunker for transcripts.

Defaults match SPEC: 500-token windows with 50-token overlap, encoded with
`cl100k_base` (the tokenizer used by `text-embedding-3-small`).
"""
from __future__ import annotations

from functools import lru_cache

import tiktoken

DEFAULT_MAX_TOKENS = 500
DEFAULT_OVERLAP = 50
ENCODER_NAME = "cl100k_base"


@lru_cache(maxsize=1)
def _encoder() -> tiktoken.Encoding:
    return tiktoken.get_encoding(ENCODER_NAME)


def chunk_text(
    text: str,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    """Split text into overlapping token-bounded chunks.

    Each chunk has at most `max_tokens` tokens; consecutive chunks share
    `overlap` tokens. Returns `[]` for empty input.
    """
    if overlap >= max_tokens:
        raise ValueError("overlap must be strictly less than max_tokens")
    if not text:
        return []

    enc = _encoder()
    tokens = enc.encode(text)
    if not tokens:
        return []

    step = max_tokens - overlap
    chunks: list[str] = []
    start = 0
    while start < len(tokens):
        window = tokens[start : start + max_tokens]
        chunks.append(enc.decode(window))
        if start + max_tokens >= len(tokens):
            break
        start += step
    return chunks
