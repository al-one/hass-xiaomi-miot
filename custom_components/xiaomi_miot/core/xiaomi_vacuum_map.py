"""Helpers for Xiaomi JSON vacuum maps."""
from __future__ import annotations

import base64
import hashlib
import json
import math
import zlib

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


_MAP_IV = b'ABCDEF1234123412'
_ROOM_GRID_MIN = 3
_ROOM_GRID_MAX = 63

# These maps use the version-2 JSON envelope and key derivation implemented
# below. Other MIoT vacuums may expose map_obj_name with incompatible formats.
XIAOMI_JSON_MAP_MODELS = frozenset({
    'xiaomi.vacuum.d102gl',
})


def decrypt_xiaomi_vacuum_map(raw: bytes, model: str, did: str) -> dict:
    """Decrypt a version-2 Xiaomi vacuum map downloaded from the cloud."""
    envelope = json.loads(raw)
    if envelope.get('version') != 2:
        raise ValueError(f'Unsupported Xiaomi map version: {envelope.get("version")!r}')

    model_key = model[-16:].encode('latin1')
    if len(model_key) != 16:
        raise ValueError('Xiaomi map model key must be 16 bytes')

    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    seed = padder.update(model_key + str(did).encode('latin1')) + padder.finalize()
    encryptor = Cipher(
        algorithms.AES(model_key), modes.CBC(_MAP_IV), backend=default_backend()
    ).encryptor()
    encrypted_seed = encryptor.update(seed) + encryptor.finalize()

    decrypt_key = hashlib.md5(encrypted_seed, usedforsecurity=False).digest()

    decryptor = Cipher(
        algorithms.AES(decrypt_key), modes.CBC(_MAP_IV), backend=default_backend()
    ).decryptor()
    padded = decryptor.update(base64.b64decode(envelope['data'])) + decryptor.finalize()
    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    compressed = unpadder.update(padded) + unpadder.finalize()
    return json.loads(zlib.decompress(compressed))


def vacuum_room_from_map(data: dict) -> dict | None:
    """Return the room containing the vacuum's current map position."""
    try:
        width = int(data['width'])
        height = int(data['height'])
        resolution = float(data['resolution'])
        origin_x = float(data['origin_x'])
        origin_y = float(data['origin_y'])
        position = data['position']
        x = float(position['x'])
        y = float(position['y'])
        cells = zlib.decompress(base64.b64decode(data['map_data']))
    except (KeyError, TypeError, ValueError, zlib.error):
        return None

    if resolution <= 0 or len(cells) < width * height:
        return None
    column = math.floor((x - origin_x) / resolution)
    row = math.floor((y - origin_y) / resolution)
    if not (0 <= column < width and 0 <= row < height):
        return None

    grid_id = cells[row * width + column]
    if not _ROOM_GRID_MIN <= grid_id <= _ROOM_GRID_MAX:
        return None

    grid_to_room = {}
    for item in data.get('map_room_info') or []:
        try:
            grid_to_room[int(item['grid_id'])] = int(item['room_id'])
        except (KeyError, TypeError, ValueError):
            continue
    room_id = grid_to_room.get(grid_id, grid_id)

    room_name = None
    for item in data.get('room_attrs') or []:
        try:
            if int(item['id']) == room_id:
                room_name = item.get('room_name') or None
                break
        except (KeyError, TypeError, ValueError):
            continue

    result = {
        'id': room_id,
        'name': str(room_name or room_id),
        'x': position['x'],
        'y': position['y'],
    }
    if position.get('yaw') is not None:
        result['yaw'] = position['yaw']
    return result


def vacuum_map_object_name(value) -> str | None:
    """Extract the cloud object name from the MIoT map property."""
    if not value:
        return None
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return value
        if isinstance(parsed, dict):
            return parsed.get('obj_name')
        if isinstance(parsed, str):
            return parsed
        return None
    if isinstance(value, dict):
        return value.get('obj_name')
    return None
