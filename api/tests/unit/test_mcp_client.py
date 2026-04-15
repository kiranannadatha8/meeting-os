"""MCP client wiring: save, fetch, status, delete.

These unit tests use an in-memory `FakeIntegrationStore` rather than a
real DB session — the `store` protocol is the only boundary the client
cares about, and keeping these small makes the suite fast.
"""
from __future__ import annotations

from app.mcp.client import (
    IntegrationRecord,
    MCPClient,
    UnknownProviderError,
)
from app.mcp.crypto import generate_key


class FakeStore:
    """Minimal in-memory upsert store matching the `IntegrationStore` protocol."""

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], IntegrationRecord] = {}

    def upsert(self, record: IntegrationRecord) -> IntegrationRecord:
        self._rows[(record.user_id, record.provider)] = record
        return record

    def get(self, user_id: str, provider: str) -> IntegrationRecord | None:
        return self._rows.get((user_id, provider))

    def list_for_user(self, user_id: str) -> list[IntegrationRecord]:
        return [r for (uid, _), r in self._rows.items() if uid == user_id]

    def delete(self, user_id: str, provider: str) -> bool:
        return self._rows.pop((user_id, provider), None) is not None


def _client() -> tuple[MCPClient, FakeStore]:
    store = FakeStore()
    return MCPClient(store=store, encryption_key=generate_key()), store


def test_save_integration_encrypts_before_storage() -> None:
    client, store = _client()
    client.save_integration(
        user_id="kiran@example.com",
        provider="linear",
        api_key="lin_api_plaintext",
    )
    row = store.get("kiran@example.com", "linear")
    assert row is not None
    assert row.encrypted_key != "lin_api_plaintext"


def test_get_integration_key_round_trips() -> None:
    client, _ = _client()
    client.save_integration(
        user_id="kiran@example.com",
        provider="linear",
        api_key="lin_api_plaintext",
    )
    assert (
        client.get_integration_key("kiran@example.com", "linear")
        == "lin_api_plaintext"
    )


def test_get_integration_key_returns_none_when_missing() -> None:
    client, _ = _client()
    assert client.get_integration_key("kiran@example.com", "linear") is None


def test_save_integration_rejects_unknown_provider() -> None:
    client, _ = _client()
    try:
        client.save_integration(
            user_id="kiran@example.com",
            provider="jira",  # type: ignore[arg-type]
            api_key="whatever",
        )
    except UnknownProviderError:
        return
    raise AssertionError("expected UnknownProviderError")


def test_get_status_reports_configured_providers() -> None:
    client, _ = _client()
    client.save_integration(
        user_id="kiran@example.com",
        provider="linear",
        api_key="k",
    )
    status = client.get_status("kiran@example.com")
    assert status == {"linear": True, "gmail": False}


def test_delete_integration_removes_key() -> None:
    client, _ = _client()
    client.save_integration(
        user_id="kiran@example.com",
        provider="linear",
        api_key="k",
    )
    assert client.delete_integration("kiran@example.com", "linear") is True
    assert client.get_integration_key("kiran@example.com", "linear") is None
    # Idempotent: deleting a missing integration returns False, not an error.
    assert client.delete_integration("kiran@example.com", "linear") is False


def test_save_integration_updates_existing_record() -> None:
    """Second save for the same (user, provider) overwrites, not duplicates."""
    client, store = _client()
    client.save_integration(
        user_id="kiran@example.com",
        provider="linear",
        api_key="old",
    )
    client.save_integration(
        user_id="kiran@example.com",
        provider="linear",
        api_key="new",
    )
    assert len(store.list_for_user("kiran@example.com")) == 1
    assert client.get_integration_key("kiran@example.com", "linear") == "new"


def test_save_integration_persists_metadata() -> None:
    """Gmail needs a client_id/client_secret/refresh_token triple; Linear
    only needs the key. The metadata dict keeps that provider-specific
    shape out of the column layout."""
    client, _ = _client()
    client.save_integration(
        user_id="kiran@example.com",
        provider="gmail",
        api_key="refresh_token_value",
        metadata={"client_id": "abc", "scopes": ["gmail.compose"]},
    )
    status = client.get_status("kiran@example.com")
    assert status["gmail"] is True
