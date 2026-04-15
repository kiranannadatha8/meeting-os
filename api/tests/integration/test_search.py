"""End-to-end test for `GET /search` — hits real Postgres with pgvector.

We seed three meetings under the same user with distinct, orthogonal
embeddings (one-hot vectors). Each canned query returns a vector close
to exactly one meeting; the API must rank that meeting's chunks first.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db import models
from app.db.session import SessionLocal
from app.ingestion.embedder import EMBEDDING_DIM
from app.main import app
from app.routes.search import get_query_embedder

pytestmark = pytest.mark.usefixtures("db_url", "truncate_meetings")


def _one_hot(index: int, dim: int = EMBEDDING_DIM) -> list[float]:
    v = [0.0] * dim
    v[index] = 1.0
    return v


@pytest.fixture
def seeded_meetings() -> tuple[str, list[tuple[str, str, list[float]]]]:
    """Insert three meetings with one-hot embeddings, return (user_id, [(id, title, vec)])."""
    user_id = f"user-{uuid4().hex[:6]}@example.com"
    meetings: list[tuple[str, str, list[float]]] = []

    with SessionLocal() as session:
        for idx, (title, chunk_text) in enumerate(
            [
                ("Pricing sync", "we raised prices across tiers"),
                ("Hiring review", "we interviewed three senior engineers"),
                ("Roadmap alignment", "q3 roadmap focuses on mobile"),
            ]
        ):
            m = models.Meeting(
                user_id=user_id,
                title=title,
                source_type="text",
                source_filename=f"{title.lower().replace(' ', '_')}.txt",
                transcript=chunk_text,
                status="complete",
            )
            session.add(m)
            session.flush()
            vec = _one_hot(idx)
            session.add(
                models.Chunk(
                    meeting_id=m.id,
                    chunk_index=0,
                    content=chunk_text,
                    embedding=vec,
                )
            )
            meetings.append((str(m.id), title, vec))
        session.commit()

    return user_id, meetings


def test_each_canned_query_surfaces_the_expected_meeting_first(
    seeded_meetings: tuple[str, list[tuple[str, str, list[float]]]],
) -> None:
    user_id, meetings = seeded_meetings

    for idx, (expected_id, expected_title, vec) in enumerate(meetings):
        app.dependency_overrides[get_query_embedder] = (
            lambda v=vec: (lambda _query: v)
        )
        try:
            with TestClient(app) as client:
                resp = client.get(
                    "/search",
                    params={"q": expected_title, "user_id": user_id, "limit": 3},
                )
        finally:
            app.dependency_overrides.pop(get_query_embedder, None)

        assert resp.status_code == 200, resp.text
        results = resp.json()["results"]
        assert len(results) >= 1
        # Top-1 must be the meeting whose one-hot vector matches the query
        assert results[0]["meeting_id"] == expected_id, (
            f"Query #{idx} expected {expected_title} first, got {results[0]}"
        )
        assert results[0]["meeting_title"] == expected_title
        # Distance to the matching meeting's own embedding is near zero
        assert results[0]["distance"] == pytest.approx(0.0, abs=1e-6)


def test_search_scopes_results_to_user(
    seeded_meetings: tuple[str, list[tuple[str, str, list[float]]]],
) -> None:
    _, meetings = seeded_meetings
    _expected_id, _expected_title, vec = meetings[0]

    other_user = f"other-{uuid4().hex[:6]}@example.com"
    app.dependency_overrides[get_query_embedder] = lambda: (lambda _q: vec)
    try:
        with TestClient(app) as client:
            resp = client.get(
                "/search",
                params={"q": "pricing", "user_id": other_user, "limit": 5},
            )
    finally:
        app.dependency_overrides.pop(get_query_embedder, None)

    assert resp.status_code == 200
    assert resp.json()["results"] == []


def test_created_at_round_trip_is_iso(
    seeded_meetings: tuple[str, list[tuple[str, str, list[float]]]],
) -> None:
    """Response `meeting_created_at` parses as a timezone-aware ISO string."""
    user_id, meetings = seeded_meetings
    _id, _title, vec = meetings[0]

    app.dependency_overrides[get_query_embedder] = lambda: (lambda _q: vec)
    try:
        with TestClient(app) as client:
            resp = client.get(
                "/search",
                params={"q": "pricing", "user_id": user_id, "limit": 1},
            )
    finally:
        app.dependency_overrides.pop(get_query_embedder, None)

    iso = resp.json()["results"][0]["meeting_created_at"]
    parsed = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert parsed <= datetime.now(UTC)
