"""MISS cryptography primitives.

This module provides:
  * Curve25519 key pair generation.
  * NaCl-compatible shared-key derivation (X25519 + HSalsa20).
  * MISS ChaCha20 encode/decode helpers using a 12-byte nonce built as
    `b"\\x00\\x00\\x00\\x00" + nonce8`.

The encryption is unauthenticated by protocol definition; MISS relies
on its own envelope format for authenticity and exposes a fixed 8-byte
nonce prefix per encoded payload.
"""

from __future__ import annotations

import os

from nacl.bindings import crypto_box_beforenm
from nacl.public import PrivateKey
from Crypto.Cipher import ChaCha20

from . import MissError, MissErrorCategory


_INVALID_DETAIL = "crypto_input_invalid"


def _require_length(value: bytes, expected: int, label: str) -> None:
    if not isinstance(value, (bytes, bytearray)) or len(value) != expected:
        raise MissError(MissErrorCategory.AUTH, _INVALID_DETAIL)


def generate_key_pair() -> tuple[bytes, bytes]:
    """Return a fresh `(private_key, public_key)` pair as 32-byte strings."""

    private = PrivateKey.generate()
    return private.encode(), private.public_key.encode()


def derive_shared_key(private_key: bytes, peer_public_key: bytes) -> bytes:
    """Derive the 32-byte shared key using `crypto_box_beforenm`."""

    _require_length(private_key, 32, "private_key")
    _require_length(peer_public_key, 32, "peer_public_key")
    return crypto_box_beforenm(bytes(peer_public_key), bytes(private_key))


def miss_encode(key: bytes, plaintext: bytes, nonce8: bytes | None = None) -> bytes:
    """Encode `plaintext` under MISS ChaCha20.

    Returns `nonce8 + ciphertext`. When `nonce8` is omitted a fresh
    random 8-byte prefix is generated.
    """

    _require_length(key, 32, "key")
    if nonce8 is None:
        nonce8 = os.urandom(8)
    _require_length(nonce8, 8, "nonce8")

    cipher = ChaCha20.new(key=bytes(key), nonce=b"\x00\x00\x00\x00" + bytes(nonce8))
    cipher.seek(0)
    return bytes(nonce8) + cipher.encrypt(bytes(plaintext))


def miss_decode(key: bytes, payload: bytes) -> bytes:
    """Decode a MISS ChaCha20 payload previously produced by `miss_encode`."""

    _require_length(key, 32, "key")
    if len(payload) < 8:
        raise MissError(MissErrorCategory.AUTH, _INVALID_DETAIL)
    nonce8 = payload[:8]
    ciphertext = payload[8:]
    cipher = ChaCha20.new(key=bytes(key), nonce=b"\x00\x00\x00\x00" + nonce8)
    cipher.seek(0)
    return cipher.decrypt(ciphertext)


__all__ = [
    "derive_shared_key",
    "generate_key_pair",
    "miss_decode",
    "miss_encode",
]