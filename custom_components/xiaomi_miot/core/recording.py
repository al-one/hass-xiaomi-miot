"""Download and remux finite Xiaomi cloud alarm recordings."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


MAX_PLAYLIST_BYTES = 1024 * 1024
MAX_SEGMENT_BYTES = 32 * 1024 * 1024
MAX_RECORDING_BYTES = 128 * 1024 * 1024
MAX_THUMBNAIL_BYTES = 8 * 1024 * 1024
MAX_SEGMENTS = 512
MAX_REDIRECTS = 5
REQUEST_TIMEOUT = (5, 20)
FFMPEG_TIMEOUT = 120
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_SAFE_HOST = re.compile(r"(?:^|\.)io\.mi\.com\Z", re.IGNORECASE)


class RecordingError(Exception):
    """A safe, user-facing recording error without upstream URL details."""


@dataclass(frozen=True, slots=True)
class PlaylistSegment:
    """A single finite playlist segment and its active AES-128 parameters."""

    url: str
    sequence: int
    key_url: str | None
    iv: bytes | None


def recording_identity(source_url: str, motion_time: str | None) -> str:
    """Return a non-reversible cache identity for the current alarm recording."""
    try:
        encoded_data = parse_qs(urlsplit(source_url).query).get("data", [None])[0]
        payload = json.loads(encoded_data) if encoded_data else {}
        file_id = payload.get("fileId") if isinstance(payload, dict) else None
    except (TypeError, ValueError):
        file_id = None

    identity = (
        f"file:{file_id}\ntime:{motion_time or ''}"
        if file_id
        else f"url:{hashlib.sha256(source_url.encode('utf-8')).hexdigest()}"
        f"\ntime:{motion_time or ''}"
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def camera_cache_key(entity_id: str) -> str:
    """Return a filesystem-safe, opaque per-camera cache key."""
    return hashlib.sha256(entity_id.encode("utf-8")).hexdigest()


def parse_playlist(text: str, playlist_url: str) -> list[PlaylistSegment]:
    """Parse a finite AES-128 media playlist without following untrusted URIs."""
    lines = [line.strip() for line in text.splitlines()]
    if not lines or lines[0] != "#EXTM3U":
        raise RecordingError("Invalid Xiaomi recording playlist")

    media_sequence = 0
    key_url: str | None = None
    explicit_iv: bytes | None = None
    segments: list[PlaylistSegment] = []
    ended = False

    for line in lines[1:]:
        if not line:
            continue
        if line == "#EXT-X-ENDLIST":
            ended = True
            continue
        if line.startswith("#EXT-X-STREAM-INF:"):
            raise RecordingError("Xiaomi recording URL is not a media playlist")
        if line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            try:
                media_sequence = int(line.partition(":")[2])
            except ValueError as err:
                raise RecordingError("Invalid Xiaomi recording playlist") from err
            if media_sequence < 0:
                raise RecordingError("Invalid Xiaomi recording playlist")
            continue
        if line.startswith("#EXT-X-KEY:"):
            attributes = _parse_attribute_list(line.partition(":")[2])
            method = attributes.get("METHOD")
            if method == "NONE":
                key_url = None
                explicit_iv = None
            elif method == "AES-128":
                raw_key_url = attributes.get("URI")
                if not raw_key_url:
                    raise RecordingError("Invalid Xiaomi recording encryption")
                key_url = urljoin(playlist_url, raw_key_url)
                _validate_xiaomi_url(key_url)
                explicit_iv = _parse_iv(attributes.get("IV"))
            else:
                raise RecordingError("Unsupported Xiaomi recording encryption")
            continue
        if line.startswith("#"):
            continue

        if ended:
            raise RecordingError("Invalid Xiaomi recording playlist")
        if len(segments) >= MAX_SEGMENTS:
            raise RecordingError("Xiaomi recording has too many segments")
        segment_url = urljoin(playlist_url, line)
        _validate_xiaomi_url(segment_url)
        sequence = media_sequence + len(segments)
        iv = explicit_iv if explicit_iv is not None else _sequence_iv(sequence)
        segments.append(
            PlaylistSegment(segment_url, sequence, key_url, iv if key_url else None)
        )

    if not ended or not segments:
        raise RecordingError("Xiaomi recording playlist is incomplete")
    return segments


def download_and_remux_recording(
    playlist_url: str,
    cache_path: Path,
    ffmpeg_binary: str,
    transcode: bool = True,
) -> Path:
    """Fetch and decrypt every segment; transcode for browsers, or stream-copy when transcode is False."""
    _validate_xiaomi_url(playlist_url)
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(cache_path.parent, 0o700)
    except OSError:
        raise RecordingError("Unable to secure the Xiaomi recording cache") from None

    output_tmp: Path | None = None
    try:
        playlist_bytes = _read_limited_url(playlist_url, MAX_PLAYLIST_BYTES)
        try:
            playlist_text = playlist_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raise RecordingError("Invalid Xiaomi recording playlist") from None
        segments = parse_playlist(playlist_text, playlist_url)

        with tempfile.TemporaryDirectory(prefix="xiaomi-recording-") as temp_name:
            temp_dir = Path(temp_name)
            concat_file = temp_dir / "segments.ffconcat"
            key_cache: dict[str, bytes] = {}
            segment_paths: list[Path] = []
            total_bytes = 0

            for index, segment in enumerate(segments):
                encrypted = _read_limited_url(segment.url, MAX_SEGMENT_BYTES)
                total_bytes += len(encrypted)
                if total_bytes > MAX_RECORDING_BYTES:
                    raise RecordingError("Xiaomi recording exceeds the size limit")

                if segment.key_url:
                    key = key_cache.get(segment.key_url)
                    if key is None:
                        key = _read_limited_url(segment.key_url, 16)
                        if len(key) != 16:
                            raise RecordingError("Invalid Xiaomi recording key")
                        key_cache[segment.key_url] = key
                    if segment.iv is None:
                        raise RecordingError("Invalid Xiaomi recording encryption")
                    data = _decrypt_segment(encrypted, key, segment.iv)
                else:
                    data = encrypted

                total_bytes += len(data) - len(encrypted)
                if total_bytes > MAX_RECORDING_BYTES:
                    raise RecordingError("Xiaomi recording exceeds the size limit")
                segment_path = temp_dir / f"segment-{index:04d}.mp4"
                segment_path.write_bytes(data)
                segment_paths.append(segment_path)

            concat_file.write_text(
                "".join(f"file '{path.name}'\n" for path in segment_paths),
                encoding="utf-8",
            )
            # Output must be on the cache filesystem for atomic replacement.
            output_tmp = cache_path.with_name(
                f".{cache_path.stem}.{os.urandom(12).hex()}.tmp.mp4"
            )
            try:
                subprocess.run(
                    [
                        ffmpeg_binary,
                        "-nostdin",
                        "-v",
                        "error",
                        "-f",
                        "concat",
                        "-safe",
                        "0",
                        "-i",
                        str(concat_file),
                        *_codec_args(transcode),
                        "-movflags",
                        "+faststart",
                        "-y",
                        str(output_tmp),
                    ],
                    cwd=temp_dir,
                    check=True,
                    timeout=FFMPEG_TIMEOUT,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except (OSError, subprocess.SubprocessError):
                raise RecordingError("Unable to assemble Xiaomi recording") from None

        if (
            not output_tmp.is_file()
            or not 0 < output_tmp.stat().st_size <= MAX_RECORDING_BYTES
        ):
            raise RecordingError("Invalid assembled Xiaomi recording")
        os.chmod(output_tmp, 0o600)
        os.replace(output_tmp, cache_path)
        output_tmp = None
        return cache_path
    except RecordingError:
        raise
    except Exception:
        # requests and filesystem errors may include the signed URL in their text.
        raise RecordingError("Unable to load Xiaomi alarm recording") from None
    finally:
        if output_tmp is not None:
            try:
                output_tmp.unlink(missing_ok=True)
            except OSError:
                pass


def _codec_args(transcode: bool) -> list[str]:
    if not transcode:
        return ["-map", "0", "-c", "copy"]
    return [
        "-map",
        "0",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-threads",
        "2",
        "-fps_mode",
        "vfr",
        "-c:a",
        "copy",
    ]


def archive_name(created_ms: object, event_type: object, file_id: object) -> str:
    """Return the UTC start time, event type and fileId stem used for archived clips."""
    try:
        started = datetime.fromtimestamp(int(created_ms) / 1000, UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        raise RecordingError("Invalid Xiaomi alarm event time") from None
    return f"{started:%Y%m%dT%H%M%SZ}_{_safe_token(event_type, 'event', 32)}_{_safe_token(file_id, 'clip', 64)}"


def _safe_token(value: object, default: str, limit: int) -> str:
    token = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "")).strip("-")[:limit]
    return token or default


def archive_clip(playlist_url: str, clip_path: Path, ffmpeg_binary: str) -> Path:
    """Stream-copy one finite recording to clip_path unless it is already archived."""
    clip_path = Path(clip_path)
    if clip_path.is_file() and clip_path.stat().st_size > 0:
        return clip_path
    return download_and_remux_recording(playlist_url, clip_path, ffmpeg_binary, transcode=False)


def download_thumbnail(image_url: str, key: bytes, iv: bytes, output_path: Path) -> Path:
    """Fetch and decrypt one cloud JPEG thumbnail unless it is already archived."""
    output_path = Path(output_path)
    if output_path.is_file() and output_path.stat().st_size > 0:
        return output_path
    if len(key) != 16 or len(iv) != 16:
        raise RecordingError("Invalid Xiaomi thumbnail key")
    data = _decrypt_segment(_read_limited_url(image_url, MAX_THUMBNAIL_BYTES), key, iv)
    if not data.startswith(b"\xff\xd8\xff"):
        raise RecordingError("Invalid Xiaomi thumbnail")
    temp_path = output_path.with_name(f".{output_path.stem}.{os.urandom(6).hex()}.tmp")
    try:
        temp_path.write_bytes(data)
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, output_path)
    except OSError:
        temp_path.unlink(missing_ok=True)
        raise RecordingError("Unable to write Xiaomi thumbnail") from None
    return output_path


def _parse_attribute_list(value: str) -> dict[str, str]:
    """Parse the quoted/unquoted attribute list used by EXT-X-KEY."""
    result: dict[str, str] = {}
    index = 0
    while index < len(value):
        while index < len(value) and value[index] in ", \t":
            index += 1
        start = index
        while index < len(value) and value[index] not in "=,":
            index += 1
        key = value[start:index].strip()
        if not key or index >= len(value) or value[index] != "=":
            raise RecordingError("Invalid Xiaomi recording playlist")
        index += 1
        if index < len(value) and value[index] == '"':
            index += 1
            start = index
            while index < len(value) and value[index] != '"':
                index += 1
            if index >= len(value):
                raise RecordingError("Invalid Xiaomi recording playlist")
            item = value[start:index]
            index += 1
        else:
            start = index
            while index < len(value) and value[index] != ",":
                index += 1
            item = value[start:index].strip()
        result[key] = item
        if index < len(value) and value[index] != ",":
            raise RecordingError("Invalid Xiaomi recording playlist")
    return result


def _parse_iv(value: str | None) -> bytes | None:
    if value is None:
        return None
    if not value.lower().startswith("0x"):
        raise RecordingError("Invalid Xiaomi recording encryption")
    try:
        iv = bytes.fromhex(value[2:])
    except ValueError:
        raise RecordingError("Invalid Xiaomi recording encryption") from None
    if len(iv) != 16:
        raise RecordingError("Invalid Xiaomi recording encryption")
    return iv


def _sequence_iv(sequence: int) -> bytes:
    return sequence.to_bytes(16, byteorder="big", signed=False)


def _decrypt_segment(data: bytes, key: bytes, iv: bytes) -> bytes:
    if not data or len(data) % 16:
        raise RecordingError("Invalid encrypted Xiaomi recording segment")
    try:
        decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        padded = decryptor.update(data) + decryptor.finalize()
        unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
        return unpadder.update(padded) + unpadder.finalize()
    except ValueError:
        raise RecordingError("Invalid encrypted Xiaomi recording segment") from None


def _validate_xiaomi_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError:
        raise RecordingError("Untrusted Xiaomi recording URL") from None
    if (
        parsed.scheme != "https"
        or not host
        or not _SAFE_HOST.search(host)
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        raise RecordingError("Untrusted Xiaomi recording URL")


def _read_limited_url(url: str, max_bytes: int) -> bytes:
    """Read one trusted HTTPS resource while validating every redirect."""
    current_url = url
    for redirect_count in range(MAX_REDIRECTS + 1):
        _validate_xiaomi_url(current_url)
        try:
            response = requests.get(
                current_url,
                allow_redirects=False,
                stream=True,
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException:
            raise RecordingError("Unable to load Xiaomi alarm recording") from None

        try:
            if response.status_code in _REDIRECT_STATUSES:
                location = response.headers.get("Location")
                if not location or redirect_count == MAX_REDIRECTS:
                    raise RecordingError("Untrusted Xiaomi recording redirect")
                next_url = urljoin(current_url, location)
                _validate_xiaomi_url(next_url)
                current_url = next_url
                continue
            if response.status_code != 200:
                raise RecordingError("Unable to load Xiaomi alarm recording")

            content_length = response.headers.get("Content-Length")
            if content_length:
                try:
                    if int(content_length) > max_bytes:
                        raise RecordingError("Xiaomi recording exceeds the size limit")
                except ValueError:
                    pass
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                size += len(chunk)
                if size > max_bytes:
                    raise RecordingError("Xiaomi recording exceeds the size limit")
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            response.close()
    raise RecordingError("Too many Xiaomi recording redirects")
