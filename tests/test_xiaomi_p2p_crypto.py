"""Tests for MISS cryptographic primitives.

The crypto layer exposes NaCl-compatible shared-key derivation and
MISS ChaCha20 encode/decode helpers. Fixed vectors come from
`tests/fixtures/xiaomi_p2p/crypto_vectors.json`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.xiaomi_miot.core.xiaomi_p2p import MissError
from custom_components.xiaomi_miot.core.xiaomi_p2p.crypto import (
    derive_shared_key,
    generate_key_pair,
    miss_decode,
    miss_encode,
)


FIXTURES = Path(__file__).parent / "fixtures" / "xiaomi_p2p"


def _load_vectors():
    with (FIXTURES / "crypto_vectors.json").open(encoding="utf-8") as fp:
        return json.load(fp)["vectors"]


def test_miss_nonce_layout_and_round_trip(monkeypatch):
    key = bytes(range(32))
    nonce8 = bytes.fromhex("0102030405060708")
    encoded = miss_encode(key, b"miss command", nonce8=nonce8)
    assert encoded[:8] == nonce8
    assert miss_decode(key, encoded) == b"miss command"


def test_miss_decode_rejects_short_nonce():
    with pytest.raises(MissError, match="crypto_input_invalid"):
        miss_decode(bytes(32), b"1234567")


def test_miss_decode_rejects_short_key():
    with pytest.raises(MissError, match="crypto_input_invalid"):
        miss_decode(bytes(31), bytes(8))


def test_miss_encode_rejects_short_key():
    with pytest.raises(MissError, match="crypto_input_invalid"):
        miss_encode(bytes(31), b"x")


def test_miss_encode_rejects_long_nonce():
    key = bytes(32)
    with pytest.raises(MissError, match="crypto_input_invalid"):
        miss_encode(key, b"x", nonce8=bytes(9))


def test_generate_key_pair_returns_32_byte_keys():
    private, public = generate_key_pair()
    assert len(private) == 32
    assert len(public) == 32
    assert private != public


def test_derive_shared_key_matches_nacl_beforenm():
    private, _ = generate_key_pair()
    from nacl.public import PrivateKey

    peer = PrivateKey.generate()
    shared = derive_shared_key(private, peer.public_key.encode())
    from nacl.bindings import crypto_box_beforenm

    expected = crypto_box_beforenm(peer.public_key.encode(), private)
    assert shared == expected


def test_derive_shared_key_rejects_short_inputs():
    with pytest.raises(MissError, match="crypto_input_invalid"):
        derive_shared_key(bytes(31), bytes(32))
    with pytest.raises(MissError, match="crypto_input_invalid"):
        derive_shared_key(bytes(32), bytes(31))


@pytest.mark.parametrize("vector", _load_vectors())
def test_fixed_vector_round_trip(vector):
    private_key = bytes.fromhex(vector["private_key_hex"])
    peer_public = bytes.fromhex(vector["peer_public_key_hex"])
    expected_shared = bytes.fromhex(vector["precomputed_key_hex"])
    nonce8 = bytes.fromhex(vector["nonce8_hex"])
    plaintext = bytes.fromhex(vector["plaintext_hex"])
    expected_payload = bytes.fromhex(vector["payload_hex"])

    shared = derive_shared_key(private_key, peer_public)
    assert shared == expected_shared

    encoded = miss_encode(expected_shared, plaintext, nonce8=nonce8)
    assert encoded == expected_payload
    assert miss_decode(expected_shared, encoded) == plaintext


@pytest.mark.parametrize("vector", _load_vectors())
def test_fixed_vector_random_nonce_is_random_per_call(vector):
    expected_shared = bytes.fromhex(vector["precomputed_key_hex"])
    plaintext = bytes.fromhex(vector["plaintext_hex"])
    encoded1 = miss_encode(expected_shared, plaintext)
    encoded2 = miss_encode(expected_shared, plaintext)
    assert encoded1[:8] != encoded2[:8]
    assert encoded1[8:] != encoded2[8:]
    assert miss_decode(expected_shared, encoded1) == plaintext
    assert miss_decode(expected_shared, encoded2) == plaintext