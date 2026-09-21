import base64
import hashlib
import json
import zlib

import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from custom_components.xiaomi_miot.core.xiaomi_vacuum_map import (
    decrypt_xiaomi_vacuum_map,
    vacuum_map_object_name,
    vacuum_room_from_map,
)


_MAP_IV = b'ABCDEF1234123412'


def _encrypt_xiaomi_vacuum_map(payload, model, did):
    """Build a synthetic map using the inverse of the Xiaomi app's decoder."""
    model_key = model[-16:].encode('latin1')
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    seed = padder.update(model_key + did.encode('latin1')) + padder.finalize()
    encryptor = Cipher(
        algorithms.AES(model_key), modes.CBC(_MAP_IV), backend=default_backend()
    ).encryptor()
    encrypted_seed = encryptor.update(seed) + encryptor.finalize()
    key = hashlib.md5(encrypted_seed, usedforsecurity=False).digest()

    compressed = zlib.compress(json.dumps(payload).encode())
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(compressed) + padder.finalize()
    encryptor = Cipher(
        algorithms.AES(key), modes.CBC(_MAP_IV), backend=default_backend()
    ).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return json.dumps({
        'version': 2,
        'data': base64.b64encode(ciphertext).decode(),
    }).encode()


def test_decrypt_xiaomi_vacuum_map_round_trip():
    model = 'xiaomi.vacuum.d102gl'
    did = '1234567890'
    payload = {'map_id': 3, 'position': {'x': 244, 'y': -19, 'yaw': 7853}}

    raw = _encrypt_xiaomi_vacuum_map(payload, model, did)

    assert decrypt_xiaomi_vacuum_map(raw, model, did) == payload


def test_decrypt_xiaomi_vacuum_map_rejects_unknown_version():
    with pytest.raises(ValueError, match='Unsupported Xiaomi map version'):
        decrypt_xiaomi_vacuum_map(b'{"version": 1}', 'xiaomi.vacuum.d102gl', '1')


def test_vacuum_room_from_map():
    cells = bytes([
        1, 3, 3,
        1, 7, 7,
    ])
    data = {
        'width': 3,
        'height': 2,
        'resolution': 50,
        'origin_x': 100,
        'origin_y': -50,
        'position': {'x': 151, 'y': 1, 'yaw': 90},
        'map_data': base64.b64encode(zlib.compress(cells)).decode(),
        'map_room_info': [{'grid_id': 7, 'room_id': 16}],
        'room_attrs': [{'id': 16, 'room_name': 'Office'}],
    }

    assert vacuum_room_from_map(data) == {
        'id': 16,
        'name': 'Office',
        'x': 151,
        'y': 1,
        'yaw': 90,
    }


@pytest.mark.parametrize('changes', [
    {'position': {'x': 99, 'y': 1}},
    {'map_data': base64.b64encode(zlib.compress(bytes([1]))).decode()},
    {'map_data': 'not-base64'},
    {'resolution': 0},
])
def test_vacuum_room_from_map_rejects_unknown_location(changes):
    data = {
        'width': 1,
        'height': 1,
        'resolution': 50,
        'origin_x': 100,
        'origin_y': -50,
        'position': {'x': 101, 'y': -49},
        'map_data': base64.b64encode(zlib.compress(bytes([3]))).decode(),
    }
    data.update(changes)

    assert vacuum_room_from_map(data) is None


@pytest.mark.parametrize(('value', 'expected'), [
    ('user/device/0', 'user/device/0'),
    ('"user/device/0"', 'user/device/0'),
    ('{"obj_name":"user/device/0"}', 'user/device/0'),
    ({'obj_name': 'user/device/0'}, 'user/device/0'),
    ('', None),
    ('[]', None),
])
def test_vacuum_map_object_name(value, expected):
    assert vacuum_map_object_name(value) == expected
