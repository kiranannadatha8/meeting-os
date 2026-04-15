"""Integration-test fixtures: real Postgres + Redis from docker-compose.

Tests are skipped if either service is unreachable so the suite stays
green in environments without docker-compose running.
"""
from __future__ import annotations

import socket
import uuid
from collections.abc import Generator
from urllib.parse import urlparse

import pytest
import redis
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db import models  # noqa: F401  — registers ORM models on Base.metadata


def _is_reachable(url: str) -> bool:
    parsed = urlparse(url)
    if not parsed.hostname or not parsed.port:
        return False
    try:
        with socket.create_connection((parsed.hostname, parsed.port), timeout=0.5):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture(scope="session")
def db_url(settings) -> str:
    if not _is_reachable(settings.database_url):
        pytest.skip("Postgres not reachable — start docker compose to run integration tests")
    return settings.database_url


@pytest.fixture(scope="session")
def redis_url(settings) -> str:
    if not _is_reachable(settings.redis_url):
        pytest.skip("Redis not reachable — start docker compose to run integration tests")
    return settings.redis_url


@pytest.fixture(scope="session")
def engine(db_url):
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    eng = create_engine(sync_url, future=True)
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine) -> Generator[Session, None, None]:
    """Wrap each test in a transaction that gets rolled back."""
    connection = engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(  # noqa: N806 — SQLAlchemy session factory class convention
        bind=connection, autoflush=False, autocommit=False, future=True
    )
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def redis_client(redis_url) -> Generator[redis.Redis, None, None]:
    client = redis.Redis.from_url(redis_url, decode_responses=True)
    yield client
    client.close()


@pytest.fixture
def queue_name() -> str:
    """Unique BullMQ queue name per test for isolation."""
    return f"test-meetings-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def cleanup_queue(redis_client, queue_name) -> Generator[None, None, None]:
    yield
    keys = redis_client.keys(f"bull:{queue_name}:*")
    if keys:
        redis_client.delete(*keys)


@pytest.fixture
def truncate_meetings(engine) -> Generator[None, None, None]:
    """Wipe the meetings table after the test commits (route handler creates
    its own session and commits, so transaction-rollback isolation won't help)."""
    yield
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE meetings RESTART IDENTITY CASCADE"))
