"""GET /meetings — list meetings scoped to a user_id, newest first."""
from __future__ import annotations

import time
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.db import models
from app.db.session import SessionLocal
from app.main import app
from app.queue import get_queue_name, set_queue_name

pytestmark = pytest.mark.usefixtures("db_url", "redis_url", "truncate_meetings")


@pytest.fixture
def client(queue_name) -> TestClient:
    previous = get_queue_name()
    set_queue_name(queue_name)
    try:
        yield TestClient(app)
    finally:
        set_queue_name(previous)


def _seed(user_id: str, title: str, status: str = "queued") -> UUID:
    with SessionLocal() as session:
        meeting = models.Meeting(
            user_id=user_id,
            title=title,
            source_type="text",
            source_filename="t.txt",
            transcript="hello",
            status=status,
        )
        session.add(meeting)
        session.commit()
        session.refresh(meeting)
        return meeting.id


def test_get_meetings_returns_only_caller_meetings(client) -> None:
    mine_a = _seed("u-alice", "alpha")
    _seed("u-bob", "bob meeting")
    mine_b = _seed("u-alice", "beta", status="complete")

    response = client.get("/meetings", params={"user_id": "u-alice"})

    assert response.status_code == 200, response.text
    body = response.json()
    ids = {item["id"] for item in body}
    assert ids == {str(mine_a), str(mine_b)}


def test_get_meetings_orders_newest_first(client) -> None:
    first = _seed("u-c", "first")
    time.sleep(0.01)  # ensure distinct created_at
    second = _seed("u-c", "second")

    response = client.get("/meetings", params={"user_id": "u-c"})

    assert response.status_code == 200
    ordered_ids = [item["id"] for item in response.json()]
    assert ordered_ids == [str(second), str(first)]


def test_get_meetings_returns_empty_list_for_unknown_user(client) -> None:
    _seed("u-someone", "hi")

    response = client.get("/meetings", params={"user_id": "u-nobody"})

    assert response.status_code == 200
    assert response.json() == []


def test_get_meetings_requires_user_id(client) -> None:
    response = client.get("/meetings")
    assert response.status_code == 422


def test_meeting_summary_payload_shape(client) -> None:
    _seed("u-k", "shape check")

    response = client.get("/meetings", params={"user_id": "u-k"})
    item = response.json()[0]

    assert set(item.keys()) == {"id", "title", "status", "source_type", "created_at"}
    assert item["title"] == "shape check"
    assert item["status"] == "queued"
    assert item["source_type"] == "text"
