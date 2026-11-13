"""Download and decrypt the map file uploaded to Xiaomi's cloud by the
xiaomi.vacuum.ov42gl (H50 Pro) robot vacuum.

This model is manufactured by 3iRobotics, not Roborock/Dreame/Viomi, so its
map format is unrelated to those and isn't recognized by the community's
Xiaomi Cloud Map Extractor project. The pipeline was reverse-engineered from
the vendor's own Xiaomi Home Android app for interoperability (its React
Native plugin bundle for this specific robot, running on a rooted emulator,
signed into a real account): download an encrypted JSON envelope -> base64
-> AES-128-CBC decrypt (fixed IV, key derived only from the device's own
model string and `did`, no account/session secret needed) -> zlib inflate ->
JSON.

This module intentionally stops at the decoded JSON - it doesn't render
anything. `Device.update_vacuum_map`/`Device.vacuum_map_property` (in
device.py) call `decrypt_map_payload` and stash the result on
`Device.data['vacuum_map']` on their own polling schedule; a future camera
entity (or any other consumer) only needs to read that dict - the decoded
JSON has `map_data`/`map_room_info` (the room/wall grid, base64+zlib, 1 byte
per pixel), `fb_regions`/`fb_walls` (restricted zones/virtual walls),
`position` (robot pose) and `paths` (cleaning trail), all already used
elsewhere in this integration's own zone/room logic where applicable.
"""
import base64
import hashlib
import json
import zlib

from cryptography.hazmat.primitives import padding as sympad
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# Cloud endpoint that resolves a map `obj_name` (e.g. "<uid>/<did>/0") into a
# temporary signed download URL. The generic `/v2/home/get_interim_file_url`
# rejects this device ("invalid config for fds"); the `_pro` suffix is the
# one that actually works for it.
MAP_FILE_URL_API = '/v2/home/get_interim_file_url_pro'

# Hardcoded in the plugin's own JS (its CryptoAes module), identical for
# every device sharing this plugin - not specific to any one robot.
MAP_AES_IV = b'ABCDEF1234123412'


def _aes_cbc_decrypt(ciphertext: bytes, key: bytes) -> bytes:
    decryptor = Cipher(algorithms.AES(key), modes.CBC(MAP_AES_IV)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = sympad.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def _aes_cbc_encrypt(plaintext: bytes, key: bytes) -> bytes:
    padder = sympad.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(MAP_AES_IV)).encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def derive_map_key(model: str, did: str) -> bytes:
    """AES_MODEL = model.slice(-16); key = MD5(AES-CBC-encrypt(AES_MODEL +
    did, key=AES_MODEL, iv=MAP_AES_IV)). Only the device's own `model` and
    `did` are involved - no account/session secret - so this is safe to
    derive from `Device.model`/`Device.did`, already available for any
    entity of this integration."""
    model_key = model[-16:].encode('utf8')
    original_work = model_key + did.encode('utf8')
    encrypted = _aes_cbc_encrypt(original_work, model_key)
    return hashlib.md5(encrypted).digest()


def decrypt_map_payload(raw_bytes: bytes, model: str, did: str) -> dict:
    """`raw_bytes` is the exact content served by MAP_FILE_URL_API's signed
    download URL: `{"version": 2, "data": "<base64>"}`. Returns the decoded
    map JSON - see the module docstring above for the fields it carries."""
    envelope = json.loads(raw_bytes)
    if envelope.get('version') != 2:
        raise ValueError(f'unsupported map envelope version: {envelope.get("version")}')
    ciphertext = base64.b64decode(envelope['data'])
    key = derive_map_key(model, did)
    plain = _aes_cbc_decrypt(ciphertext, key)
    inflated = zlib.decompress(plain)
    return json.loads(inflated)
