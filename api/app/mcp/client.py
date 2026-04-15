"""MCP client wiring — integration credential store + provider registry.

This file is the seam that T18 (Linear) and T19 (Gmail) plug into. Agents
retrieve decrypted credentials via `MCPClient.get_integration_key`; the
route handlers in `app.routes.integrations` call `save_integration` and
`get_status`.

Keep this thin — provider-specific wiring lives in
`app.mcp.linear` and `app.mcp.gmail`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

from app.mcp.crypto import decrypt_secret, encrypt_secret

Provider = Literal["linear", "gmail"]
SUPPORTED_PROVIDERS: tuple[Provider, ...] = ("linear", "gmail")


class UnknownProviderError(ValueError):
    """Raised when a non-whitelisted provider is passed in."""


@dataclass(frozen=True)
class IntegrationRecord:
    """Minimal store row shape. DB-backed stores map this 1:1 to the
    `integrations` table; the fake store in unit tests holds them in a dict."""

    id: UUID
    user_id: str
    provider: Provider
    encrypted_key: str
    metadata: dict[str, Any] | None = field(default=None)


class IntegrationStore(Protocol):
    """Storage protocol — `DbIntegrationStore` is the prod implementation,
    `FakeStore` in unit tests keeps these tests DB-free."""

    def upsert(self, record: IntegrationRecord) -> IntegrationRecord: ...
    def get(self, user_id: str, provider: str) -> IntegrationRecord | None: ...
    def list_for_user(self, user_id: str) -> list[IntegrationRecord]: ...
    def delete(self, user_id: str, provider: str) -> bool: ...


def _validate_provider(provider: str) -> Provider:
    if provider not in SUPPORTED_PROVIDERS:
        raise UnknownProviderError(
            f"Unsupported provider '{provider}'; expected one of {SUPPORTED_PROVIDERS}"
        )
    return provider


class MCPClient:
    """Thin facade over the integration store.

    Responsibilities:
    - Encrypt/decrypt keys at the boundary
    - Enforce the provider whitelist
    - Provide a per-user configured-providers view for the UI
    """

    def __init__(self, store: IntegrationStore, encryption_key: str) -> None:
        self._store = store
        self._key = encryption_key

    def save_integration(
        self,
        *,
        user_id: str,
        provider: str,
        api_key: str,
        metadata: dict[str, Any] | None = None,
    ) -> IntegrationRecord:
        provider_t = _validate_provider(provider)
        existing = self._store.get(user_id, provider_t)
        record = IntegrationRecord(
            id=existing.id if existing is not None else uuid4(),
            user_id=user_id,
            provider=provider_t,
            encrypted_key=encrypt_secret(api_key, self._key),
            metadata=metadata,
        )
        return self._store.upsert(record)

    def get_integration_key(self, user_id: str, provider: str) -> str | None:
        provider_t = _validate_provider(provider)
        record = self._store.get(user_id, provider_t)
        if record is None:
            return None
        return decrypt_secret(record.encrypted_key, self._key)

    def get_status(self, user_id: str) -> dict[str, bool]:
        """`{"linear": True, "gmail": False}` — one bool per supported provider.

        The UI uses this to toggle connect/connected states. Unsupported
        providers are never surfaced (they aren't in `SUPPORTED_PROVIDERS`)."""
        configured = {r.provider for r in self._store.list_for_user(user_id)}
        return {p: (p in configured) for p in SUPPORTED_PROVIDERS}

    def delete_integration(self, user_id: str, provider: str) -> bool:
        provider_t = _validate_provider(provider)
        return self._store.delete(user_id, provider_t)
