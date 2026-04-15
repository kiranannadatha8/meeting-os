"""End-to-end tests for the `/integrations` route handlers.

These use a real Postgres (via `db_session`) and a real encryption key
so the full save → status → delete loop is exercised.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import models
from app.db.session import get_db
from app.main import app
from app.mcp.crypto import decrypt_secret, generate_key


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = generate_key()
    monkeypatch.setenv("MEETING_OS_ENCRYPTION_KEY", key)
    return key


@pytest.fixture
def client(db_session: Session) -> TestClient:
    """Override the DB dependency so the route sees the rollback-safe session."""
    def _override() -> Session:
        return db_session

    app.dependency_overrides[get_db] = _override
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_put_integration_persists_encrypted_key(
    client: TestClient,
    db_session: Session,
    _encryption_key: str,
) -> None:
    resp = client.put(
        "/integrations",
        json={
            "user_id": "kiran@example.com",
            "provider": "linear",
            "api_key": "lin_api_plaintext",
        },
    )
    assert resp.status_code == 200

    row = (
        db_session.query(models.Integration)
        .filter_by(user_id="kiran@example.com", provider="linear")
        .one()
    )
    # Stored ciphertext is not plaintext, and decrypts cleanly.
    assert row.encrypted_key != "lin_api_plaintext"
    assert decrypt_secret(row.encrypted_key, _encryption_key) == "lin_api_plaintext"


def test_status_reflects_configured_providers(client: TestClient) -> None:
    client.put(
        "/integrations",
        json={
            "user_id": "kiran@example.com",
            "provider": "linear",
            "api_key": "k",
        },
    )
    resp = client.get(
        "/integrations/status", params={"user_id": "kiran@example.com"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"linear": True, "gmail": False}


def test_delete_integration_removes_row(
    client: TestClient, db_session: Session
) -> None:
    client.put(
        "/integrations",
        json={
            "user_id": "kiran@example.com",
            "provider": "linear",
            "api_key": "k",
        },
    )
    resp = client.delete(
        "/integrations",
        params={"user_id": "kiran@example.com", "provider": "linear"},
    )
    assert resp.status_code == 204

    rows = (
        db_session.query(models.Integration)
        .filter_by(user_id="kiran@example.com", provider="linear")
        .all()
    )
    assert rows == []


def test_delete_missing_integration_is_idempotent(client: TestClient) -> None:
    resp = client.delete(
        "/integrations",
        params={"user_id": "kiran@example.com", "provider": "linear"},
    )
    assert resp.status_code == 204


def test_put_rejects_unknown_provider(client: TestClient) -> None:
    resp = client.put(
        "/integrations",
        json={
            "user_id": "kiran@example.com",
            "provider": "jira",
            "api_key": "k",
        },
    )
    assert resp.status_code == 422


def test_status_defaults_all_false_when_no_integrations(
    client: TestClient,
) -> None:
    resp = client.get(
        "/integrations/status", params={"user_id": "nobody@example.com"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"linear": False, "gmail": False}


def test_put_upserts_on_repeat(client: TestClient, db_session: Session) -> None:
    client.put(
        "/integrations",
        json={
            "user_id": "kiran@example.com",
            "provider": "linear",
            "api_key": "old",
        },
    )
    client.put(
        "/integrations",
        json={
            "user_id": "kiran@example.com",
            "provider": "linear",
            "api_key": "new",
        },
    )
    rows = (
        db_session.query(models.Integration)
        .filter_by(user_id="kiran@example.com", provider="linear")
        .all()
    )
    assert len(rows) == 1
