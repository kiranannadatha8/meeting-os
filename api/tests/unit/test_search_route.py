"""Unit tests for `GET /search`.

The route embeds the query via an injected callable, queries chunks by
cosine distance scoped to `user_id`, and returns the top-k results with
their originating meeting's title. Both seams (the embedder and the DB
session) are overridden so no network or database is touched here; the
integration test in `tests/integration/test_search.py` drives the real
pgvector path.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from app.routes.search import DEFAULT_LIMIT, get_query_embedder


class _FakeEmbedder:
    """Records the query it was given and returns a fixed vector."""

    def __init__(self, vector: list[float]) -> None:
        self._vector = vector
        self.calls: list[str] = []

    def __call__(self, query: str) -> list[float]:
        self.calls.append(query)
        return self._vector


class _FakeResult:
    def __init__(self, rows: Iterable[tuple]) -> None:
        self._rows = list(rows)

    def all(self) -> list[tuple]:
        return self._rows


class _FakeSession:
    def __init__(self, rows: Iterable[tuple]) -> None:
        self._rows = list(rows)
        self.executed: list[object] = []

    def execute(self, stmt):  # noqa: ANN001
        self.executed.append(stmt)
        return _FakeResult(self._rows)


@pytest.fixture
def override_db():
    captured: dict[str, _FakeSession] = {}

    def _install(rows: Iterable[tuple]) -> _FakeSession:
        session = _FakeSession(rows)
        captured["session"] = session

        def _gen():
            yield session

        app.dependency_overrides[get_db] = _gen
        return session

    yield _install
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def override_embedder():
    def _install(vector: list[float]) -> _FakeEmbedder:
        embedder = _FakeEmbedder(vector)
        app.dependency_overrides[get_query_embedder] = lambda: embedder
        return embedder

    yield _install
    app.dependency_overrides.pop(get_query_embedder, None)


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


def _row(
    *,
    meeting_id: UUID,
    title: str,
    content: str,
    distance: float,
    created_at: datetime | None = None,
) -> tuple:
    return (
        meeting_id,
        title,
        created_at or datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
        content,
        distance,
    )


def test_returns_top_chunks_with_meeting_metadata(
    client: TestClient, override_db, override_embedder
) -> None:
    m1, m2 = uuid4(), uuid4()
    rows = [
        _row(meeting_id=m1, title="Pricing sync", content="we raised prices", distance=0.12),
        _row(meeting_id=m2, title="Retro", content="pricing came up again", distance=0.25),
    ]
    session = override_db(rows)
    embedder = override_embedder([0.1] * 1536)

    resp = client.get("/search", params={"q": "pricing", "user_id": "kiran@example.com"})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["results"]) == 2
    assert body["results"][0]["meeting_id"] == str(m1)
    assert body["results"][0]["meeting_title"] == "Pricing sync"
    assert body["results"][0]["chunk_content"] == "we raised prices"
    assert body["results"][0]["distance"] == pytest.approx(0.12)
    assert body["results"][1]["meeting_id"] == str(m2)
    # Embedder called exactly once with the query text
    assert embedder.calls == ["pricing"]
    # DB was asked for rows (the statement itself is opaque here)
    assert len(session.executed) == 1


def test_empty_query_returns_422(client: TestClient) -> None:
    resp = client.get("/search", params={"q": "", "user_id": "kiran@example.com"})
    assert resp.status_code == 422


def test_missing_user_id_returns_422(client: TestClient) -> None:
    resp = client.get("/search", params={"q": "pricing"})
    assert resp.status_code == 422


def test_no_matches_returns_empty_list(
    client: TestClient, override_db, override_embedder
) -> None:
    override_db([])
    override_embedder([0.0] * 1536)

    resp = client.get("/search", params={"q": "nothing matches", "user_id": "kiran@example.com"})

    assert resp.status_code == 200
    assert resp.json() == {"results": []}


def test_accepts_limit_query_param(
    client: TestClient, override_db, override_embedder
) -> None:
    """`limit` is clamped to a sane range and passed into the SQL LIMIT."""
    override_db([])
    override_embedder([0.0] * 1536)

    resp = client.get(
        "/search",
        params={"q": "pricing", "user_id": "kiran@example.com", "limit": 3},
    )
    assert resp.status_code == 200

    # Out-of-range limit is rejected
    resp = client.get(
        "/search",
        params={"q": "pricing", "user_id": "kiran@example.com", "limit": 0},
    )
    assert resp.status_code == 422


def test_default_limit_is_five(
    client: TestClient, override_db, override_embedder
) -> None:
    """Acceptance says top-5: verify the default LIMIT constant."""
    assert DEFAULT_LIMIT == 5
