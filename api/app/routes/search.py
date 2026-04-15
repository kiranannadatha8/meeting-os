"""Semantic search over persisted chunks.

`GET /search?q=<text>&user_id=<email>&limit=<n>` embeds the query, ranks
chunks by pgvector cosine distance scoped to the caller's meetings, and
returns the top-k hits with their meeting metadata. The embedder is
injected as a dependency so tests can drive the route without hitting
OpenAI; the DB session is the standard `get_db` dependency.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.db.session import get_db
from app.ingestion.embedder import embed_chunks
from app.models.io import SearchResponse, SearchResult

DEFAULT_LIMIT = 5
MAX_LIMIT = 25

QueryEmbedder = Callable[[str], list[float]]

router = APIRouter(tags=["search"])


def _default_embedder(query: str) -> list[float]:
    return embed_chunks([query])[0]


def get_query_embedder() -> QueryEmbedder:
    """Default: single-shot OpenAI embedding. Overridden in tests."""
    return _default_embedder


@router.get("/search", response_model=SearchResponse)
def search(
    db: Annotated[Session, Depends(get_db)],
    embedder: Annotated[QueryEmbedder, Depends(get_query_embedder)],
    q: Annotated[str, Query(min_length=1, max_length=500)],
    user_id: Annotated[str, Query(min_length=1, max_length=255)],
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> SearchResponse:
    vector = embedder(q)
    distance = models.Chunk.embedding.cosine_distance(vector)
    stmt = (
        select(
            models.Meeting.id,
            models.Meeting.title,
            models.Meeting.created_at,
            models.Chunk.content,
            distance.label("distance"),
        )
        .join(models.Meeting, models.Chunk.meeting_id == models.Meeting.id)
        .where(
            models.Meeting.user_id == user_id,
            models.Chunk.embedding.is_not(None),
        )
        .order_by(distance)
        .limit(limit)
    )
    rows = db.execute(stmt).all()
    results = [
        SearchResult(
            meeting_id=row[0],
            meeting_title=row[1],
            meeting_created_at=row[2],
            chunk_content=row[3],
            distance=float(row[4]),
        )
        for row in rows
    ]
    return SearchResponse(results=results)
