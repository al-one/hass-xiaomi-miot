"""Pure-logic tests for the xiaomi.vacuum.ov42gl (H50 Pro) cloud map decode
pipeline - core/vacuum_map.py doesn't import Home Assistant at all, so these
run without the `hass`/`make_device` fixtures used by
test_xiaomi_vacuum_ov42gl.py. There's no rendering here (see the README's
"About the map" note) - this only covers download/decrypt.
"""
import base64
import json
import zlib

from custom_components.xiaomi_miot.core import vacuum_map


def test_derive_map_key_is_16_bytes_and_deterministic():
    key = vacuum_map.derive_map_key("xiaomi.vacuum.ov42gl", "123456789")
    assert len(key) == 16
    assert key == vacuum_map.derive_map_key("xiaomi.vacuum.ov42gl", "123456789")
    # Different did/model must derive a different key.
    assert key != vacuum_map.derive_map_key("xiaomi.vacuum.ov42gl", "999")


def test_decrypt_map_payload_round_trips_with_derive_map_key():
    model, did = "xiaomi.vacuum.ov42gl", "123456789"
    key = vacuum_map.derive_map_key(model, did)
    map_data = {
        "width": 4, "height": 4, "resolution": 50,
        "origin_x": 0, "origin_y": 0,
        "fb_regions": [{"fb_point": [0, 0, 1, 1], "fb_attr": 0}],
        "fb_walls": [],
    }

    compressed = zlib.compress(json.dumps(map_data).encode())
    ciphertext = vacuum_map._aes_cbc_encrypt(compressed, key)
    envelope = json.dumps({"version": 2, "data": base64.b64encode(ciphertext).decode()}).encode()

    decoded = vacuum_map.decrypt_map_payload(envelope, model, did)
    assert decoded == map_data


def test_decrypt_map_payload_rejects_unsupported_envelope_version():
    envelope = json.dumps({"version": 1, "data": ""}).encode()
    try:
        vacuum_map.decrypt_map_payload(envelope, "xiaomi.vacuum.ov42gl", "123456789")
        assert False, "expected ValueError for an unsupported envelope version"
    except ValueError:
        pass
