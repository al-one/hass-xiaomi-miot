"""Pure-logic tests for the xiaomi.vacuum.ov42gl (H50 Pro) map decrypt
pipeline - core/vacuum_map_codec.py only imports `cryptography` (a core
Home Assistant dependency), no Home Assistant imports of its own, so these
run standalone.
"""
import base64
import json
import zlib

import pytest

from custom_components.xiaomi_miot.core import vacuum_map_codec as mc

MODEL = "xiaomi.vacuum.ov42gl"
DEVICE_ID = "1190919101"


def _make_envelope(payload: dict, model=MODEL, device_id=DEVICE_ID, version=2) -> bytes:
    """Builds a fake cloud envelope the same way the real
    get_interim_file_url_pro endpoint would (deflate -> AES-128-CBC encrypt
    -> base64 -> JSON-wrap), so the round trip below exercises the whole
    pipeline without needing a real captured cloud payload on hand."""
    key = mc.derive_map_key(model, device_id)
    deflated = zlib.compress(json.dumps(payload).encode("utf8"))
    ciphertext = mc._aes_cbc_encrypt(deflated, key)
    return json.dumps({"version": version, "data": base64.b64encode(ciphertext).decode("ascii")}).encode("utf8")


def test_derive_map_key_is_16_bytes():
    assert len(mc.derive_map_key(MODEL, DEVICE_ID)) == 16


def test_derive_map_key_is_deterministic():
    assert mc.derive_map_key(MODEL, DEVICE_ID) == mc.derive_map_key(MODEL, DEVICE_ID)


def test_derive_map_key_differs_per_device_id():
    assert mc.derive_map_key(MODEL, DEVICE_ID) != mc.derive_map_key(MODEL, "9999999999")


def test_derive_map_key_differs_per_model():
    assert mc.derive_map_key(MODEL, DEVICE_ID) != mc.derive_map_key("xiaomi.vacuum.other", DEVICE_ID)


def test_decrypt_map_payload_round_trips_the_original_dict():
    original = {"width": 10, "height": 10, "resolution": 50, "origin_x": -100, "origin_y": -100}
    envelope = _make_envelope(original)
    assert mc.decrypt_map_payload(envelope, MODEL, DEVICE_ID) == original


def test_decrypt_map_payload_rejects_unsupported_version():
    envelope = _make_envelope({"a": 1}, version=1)
    with pytest.raises(ValueError):
        mc.decrypt_map_payload(envelope, MODEL, DEVICE_ID)


def test_decrypt_map_payload_fails_with_wrong_device_id():
    envelope = _make_envelope({"a": 1})
    with pytest.raises(Exception):
        mc.decrypt_map_payload(envelope, MODEL, "0000000000")
