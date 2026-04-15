"""AES-GCM symmetric encryption for stored integration credentials.

The ciphertext layout is `nonce(12) || tag(16) || ct`, base64-encoded so it
fits cleanly in a `TEXT` column. The authenticator tag is produced by GCM
itself — any mutation to the blob will cause `decrypt_secret` to raise.

The key comes from the `MEETING_OS_ENCRYPTION_KEY` env var (32 raw bytes,
base64-encoded). Rotation = re-encrypt all rows with the new key; out of
scope for T17 but the format is stable.
"""
from __future__ import annotations

import base64
import os
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEY_BYTES = 32  # AES-256
_NONCE_BYTES = 12  # GCM standard


class CryptoError(Exception):
    """Raised when a ciphertext is corrupt, truncated, or decrypted with
    the wrong key. We collapse every failure mode into one exception so
    callers can't distinguish authenticator failures from key mismatches
    (and leak information through error handling)."""


def generate_key() -> str:
    """Generate a fresh 32-byte key, base64-encoded for env storage."""
    return base64.b64encode(secrets.token_bytes(_KEY_BYTES)).decode("ascii")


def _load_key(key_b64: str) -> bytes:
    try:
        raw = base64.b64decode(key_b64, validate=True)
    except (ValueError, base64.binascii.Error) as exc:  # type: ignore[attr-defined]
        raise CryptoError("encryption key is not valid base64") from exc
    if len(raw) != _KEY_BYTES:
        raise CryptoError(
            f"encryption key must be {_KEY_BYTES} bytes; got {len(raw)}"
        )
    return raw


def encrypt_secret(plaintext: str, key_b64: str) -> str:
    """Encrypt `plaintext` and return a base64-encoded blob."""
    key = _load_key(key_b64)
    nonce = secrets.token_bytes(_NONCE_BYTES)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt_secret(ciphertext_b64: str, key_b64: str) -> str:
    """Inverse of `encrypt_secret`. Raises `CryptoError` on any failure."""
    key = _load_key(key_b64)
    try:
        raw = base64.b64decode(ciphertext_b64, validate=True)
    except (ValueError, base64.binascii.Error) as exc:  # type: ignore[attr-defined]
        raise CryptoError("ciphertext is not valid base64") from exc
    if len(raw) < _NONCE_BYTES + 16:  # nonce + min GCM tag
        raise CryptoError("ciphertext is truncated")
    nonce, ct = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
    try:
        pt = AESGCM(key).decrypt(nonce, ct, associated_data=None)
    except InvalidTag as exc:
        raise CryptoError("ciphertext authentication failed") from exc
    return pt.decode("utf-8")


def get_active_key() -> str:
    """Fetch the encryption key from the environment.

    Dev fallback: if `MEETING_OS_ENCRYPTION_KEY` is unset and we're running
    in non-production, generate a stable ephemeral key for the process so
    local dev doesn't need to `openssl rand`. This never runs in prod
    because `APP_ENV` is checked.
    """
    key = os.environ.get("MEETING_OS_ENCRYPTION_KEY")
    if key:
        return key
    if os.environ.get("APP_ENV", "development") == "production":
        raise CryptoError(
            "MEETING_OS_ENCRYPTION_KEY must be set in production",
        )
    return _dev_key()


_dev_cache: str | None = None


def _dev_key() -> str:
    global _dev_cache
    if _dev_cache is None:
        _dev_cache = generate_key()
    return _dev_cache
