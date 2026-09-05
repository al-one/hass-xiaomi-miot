"""Decrypts the xiaomi.vacuum.ov42gl (H50 Pro) vacuum map, downloaded from
Xiaomi's cloud. No Home Assistant imports - see vacuum_zones.py/vacuum_maps.py
for the same pattern; `cryptography` is a core Home Assistant dependency
(used for TLS), so it doesn't need declaring separately in manifest.json.

Reverse-engineered from the "1027146/1063063" React Native plugin bundle
(pulled from a rooted emulator's app data). The manufacturer behind this
device is 3iRobotics; this format is unrelated to Roborock/Dreame/Viomi map
formats, which is why community tools (Xiaomi Cloud Map Extractor) don't
support it - see the fuller writeup in the project's own investigation notes
(kept outside this repo) if this ever needs re-deriving for a different
model/manufacturer.

Pipeline: download JSON envelope -> base64-decode "data" -> AES-128-CBC
decrypt (fixed IV, key derived from device model+id, no account secret
needed) -> zlib inflate -> JSON.
"""
import base64
import hashlib
import json
import zlib

from cryptography.hazmat.primitives import padding as sympad
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# Hardcoded in the plugin's JS (CryptoAes module), identical for every
# device using this plugin - not device-specific.
MAP_AES_IV = b"ABCDEF1234123412"


def _aes_cbc_encrypt(plaintext: bytes, key: bytes) -> bytes:
    padder = sympad.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(MAP_AES_IV)).encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def _aes_cbc_decrypt(ciphertext: bytes, key: bytes) -> bytes:
    decryptor = Cipher(algorithms.AES(key), modes.CBC(MAP_AES_IV)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = sympad.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def derive_map_key(model: str, device_id: str) -> bytes:
    """AES_MODEL = Device.model.slice(-16); key = MD5(AES-CBC-encrypt(
    AES_MODEL + did, key=AES_MODEL, iv=MAP_AES_IV)). No account/session
    secret involved - only the device's own model string and did."""
    model_key = model[-16:].encode("utf8")
    original_work = model_key + device_id.encode("utf8")
    enc = _aes_cbc_encrypt(original_work, model_key)
    return hashlib.md5(enc).digest()


def decrypt_map_payload(raw_bytes: bytes, model: str, device_id: str) -> dict:
    """raw_bytes is the exact content served by get_interim_file_url_pro:
    `{"version": 2, "data": "<base64>"}`. Returns the parsed map JSON
    (map_data/map_room_info/fb_walls/... - see vacuum_map_render.py)."""
    envelope = json.loads(raw_bytes)
    if envelope.get("version") != 2:
        raise ValueError(f"unsupported map envelope version: {envelope.get('version')}")
    ciphertext = base64.b64decode(envelope["data"])
    key = derive_map_key(model, device_id)
    plain = _aes_cbc_decrypt(ciphertext, key)
    inflated = zlib.decompress(plain)
    return json.loads(inflated)
