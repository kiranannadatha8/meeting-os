"""AES-GCM encryption for integration keys.

These tests are the security contract for at-rest encryption of API keys
in the `integrations` table. The encrypted blob must be self-contained
(nonce embedded), non-deterministic, and authenticated.
"""
from __future__ import annotations

import base64

import pytest

from app.mcp.crypto import (
    CryptoError,
    decrypt_secret,
    encrypt_secret,
    generate_key,
)


def test_encrypt_decrypt_round_trip() -> None:
    key = generate_key()
    plaintext = "lin_api_sk_abc123"

    ciphertext = encrypt_secret(plaintext, key)
    assert ciphertext != plaintext
    assert decrypt_secret(ciphertext, key) == plaintext


def test_ciphertext_is_nondeterministic() -> None:
    """A fresh nonce each call → same plaintext never yields same ciphertext."""
    key = generate_key()
    a = encrypt_secret("hello", key)
    b = encrypt_secret("hello", key)
    assert a != b


def test_decrypt_with_wrong_key_raises() -> None:
    correct = generate_key()
    tampered = generate_key()
    ciphertext = encrypt_secret("hello", correct)

    with pytest.raises(CryptoError):
        decrypt_secret(ciphertext, tampered)


def test_decrypt_tampered_ciphertext_raises() -> None:
    """GCM auth tag should reject modified ciphertext."""
    key = generate_key()
    ciphertext = encrypt_secret("hello", key)

    raw = base64.b64decode(ciphertext)
    tampered = raw[:-1] + bytes([raw[-1] ^ 0x01])
    tampered_b64 = base64.b64encode(tampered).decode("ascii")

    with pytest.raises(CryptoError):
        decrypt_secret(tampered_b64, key)


def test_generate_key_produces_32_bytes() -> None:
    """AES-256-GCM requires a 32-byte key."""
    key = generate_key()
    assert len(base64.b64decode(key)) == 32


def test_empty_plaintext_roundtrips() -> None:
    key = generate_key()
    assert decrypt_secret(encrypt_secret("", key), key) == ""
