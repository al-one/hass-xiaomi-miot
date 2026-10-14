"""Expose the latest Xiaomi cloud alarm clip as authenticated media."""

from __future__ import annotations

import asyncio
import logging
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import override

from aiohttp import web

from homeassistant.components.ffmpeg import DATA_FFMPEG
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.media_player import BrowseError, MediaClass, MediaType
from homeassistant.components.media_source import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
    Unresolvable,
)
from homeassistant.core import HomeAssistant

from . import DOMAIN
from .core.recording import (
    RecordingError,
    camera_cache_key,
    download_and_remux_recording,
    recording_identity,
)

_LOGGER = logging.getLogger(__name__)
_STORE_KEY = "alarm_recording_media_source"
_VIEW_URL = "/api/xiaomi_miot/recording/{opaque_id}.mp4"


@dataclass(slots=True)
class _Recording:
    entity_id: str
    identity: str
    opaque_id: str
    path: Path


@dataclass(slots=True)
class _RecordingStore:
    root: Path
    locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    by_camera: dict[str, _Recording] = field(default_factory=dict)
    by_id: dict[str, _Recording] = field(default_factory=dict)
    view_registered: bool = False


async def async_get_media_source(hass: HomeAssistant) -> XiaomiRecordingSource:
    """Set up the platform and its authenticated recording view."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    store = domain_data.get(_STORE_KEY)
    if store is None:
        root = Path(hass.config.path(".storage", DOMAIN, "alarm_clips"))
        store = domain_data[_STORE_KEY] = _RecordingStore(root)
    if not store.view_registered:
        hass.http.register_view(XiaomiRecordingView(hass, store))
        store.view_registered = True
    return XiaomiRecordingSource(hass, store)


class XiaomiRecordingSource(MediaSource):
    """Resolve only recordings owned by loaded Xiaomi camera entities."""

    name = "Xiaomi recordings"

    def __init__(self, hass: HomeAssistant, store: _RecordingStore) -> None:
        super().__init__(DOMAIN)
        self.hass = hass
        self.store = store

    @override
    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        if not item.identifier:
            children = [
                self._browse_camera(camera) for camera in _recorded_cameras(self.hass)
            ]
            return BrowseMediaSource(
                domain=DOMAIN,
                identifier=None,
                media_class=MediaClass.APP,
                media_content_type=MediaType.VIDEO,
                title=self.name,
                can_play=False,
                can_expand=True,
                children_media_class=MediaClass.VIDEO,
                children=children,
            )

        camera = _camera_by_entity_id(self.hass, item.identifier)
        if camera is None:
            raise BrowseError("Xiaomi camera recording is unavailable")
        return self._browse_camera(camera)

    @override
    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        camera = _camera_by_entity_id(self.hass, item.identifier)
        if camera is None:
            raise Unresolvable("Xiaomi camera recording is unavailable")

        source_url = getattr(camera, "_attr_stream_source", None)
        if not _is_recorded_camera(camera) or not isinstance(source_url, str):
            raise Unresolvable("Xiaomi camera recording is unavailable")
        cache_key = camera_cache_key(camera.entity_id)
        cache_path = self.store.root / f"{cache_key}.mp4"
        lock = self.store.locks.setdefault(camera.entity_id, asyncio.Lock())

        async with lock:
            source_url = getattr(camera, "_attr_stream_source", None)
            if not _is_recorded_camera(camera) or not isinstance(source_url, str):
                raise Unresolvable("Xiaomi camera recording is unavailable")
            identity = recording_identity(source_url, _motion_time(camera))
            current = self.store.by_camera.get(camera.entity_id)
            if (
                current is not None
                and current.identity == identity
                and _is_current_file(current.path, self.store.root)
            ):
                return PlayMedia(_play_url(current.opaque_id), "video/mp4")

            if current is not None:
                self.store.by_id.pop(current.opaque_id, None)
                self.store.by_camera.pop(camera.entity_id, None)

            manager = self.hass.data.get(DATA_FFMPEG)
            ffmpeg_binary = getattr(manager, "binary", None)
            if not ffmpeg_binary:
                _remove_file(cache_path)
                raise Unresolvable("Xiaomi recording support is unavailable")

            try:
                await self.hass.async_add_executor_job(
                    download_and_remux_recording,
                    source_url,
                    cache_path,
                    ffmpeg_binary,
                )
            except RecordingError:
                _remove_file(cache_path)
                raise Unresolvable(
                    "Unable to load the latest Xiaomi recording"
                ) from None

            if (
                not _is_recorded_camera(camera)
                or recording_identity(
                    getattr(camera, "_attr_stream_source", ""),
                    _motion_time(camera),
                )
                != identity
            ):
                _remove_file(cache_path)
                raise Unresolvable("Xiaomi recording changed while it was loading")

            opaque_id = secrets.token_urlsafe(24)
            recording = _Recording(camera.entity_id, identity, opaque_id, cache_path)
            self.store.by_camera[camera.entity_id] = recording
            self.store.by_id[opaque_id] = recording
            return PlayMedia(_play_url(opaque_id), "video/mp4")

    @override
    async def async_search_media(self, item, query):
        raise NotImplementedError

    @staticmethod
    def _browse_camera(camera) -> BrowseMediaSource:
        motion_time = _motion_time(camera)
        title = camera.name or camera.entity_id
        if motion_time:
            title = f"{title} — {motion_time}"
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=camera.entity_id,
            media_class=MediaClass.VIDEO,
            media_content_type=MediaType.VIDEO,
            title=title,
            can_play=True,
            can_expand=False,
        )


class XiaomiRecordingView(HomeAssistantView):
    """Serve current provider-owned MP4s with HA auth and HTTP Range support."""

    url = _VIEW_URL
    name = "api:xiaomi_miot:recording"
    requires_auth = True

    def __init__(self, hass: HomeAssistant, store: _RecordingStore) -> None:
        self.hass = hass
        self.store = store

    async def get(self, request: web.Request, opaque_id: str) -> web.FileResponse:
        recording = self.store.by_id.get(opaque_id)
        camera = (
            _camera_by_entity_id(self.hass, recording.entity_id)
            if recording is not None
            else None
        )
        if (
            recording is None
            or camera is None
            or recording_identity(
                getattr(camera, "_attr_stream_source", ""),
                _motion_time(camera),
            )
            != recording.identity
            or self.store.by_camera.get(recording.entity_id) is not recording
            or not _is_current_file(recording.path, self.store.root)
        ):
            raise web.HTTPNotFound
        return web.FileResponse(recording.path, headers={"Content-Type": "video/mp4"})


def _recorded_cameras(hass: HomeAssistant) -> list:
    entities = hass.data.get(DOMAIN, {}).get("entities", {})
    return [camera for camera in entities.values() if _is_recorded_camera(camera)]


def _camera_by_entity_id(hass: HomeAssistant, entity_id: str):
    return next(
        (camera for camera in _recorded_cameras(hass) if camera.entity_id == entity_id),
        None,
    )


def _is_recorded_camera(camera) -> bool:
    return bool(
        getattr(camera, "entity_id", None)
        and getattr(camera, "is_cloud_alarm_recording", False)
        and isinstance(getattr(camera, "_attr_stream_source", None), str)
    )


def _motion_time(camera) -> str | None:
    attributes = getattr(camera, "_attr_extra_state_attributes", {}) or {}
    value = attributes.get("motion_video_time")
    return str(value) if value is not None else None


def _play_url(opaque_id: str) -> str:
    return f"/api/xiaomi_miot/recording/{opaque_id}.mp4"


def _is_current_file(path: Path, root: Path) -> bool:
    try:
        resolved_root = root.resolve(strict=True)
        resolved_path = path.resolve(strict=True)
        return resolved_path.parent == resolved_root and resolved_path.is_file()
    except OSError:
        return False


def _remove_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        _LOGGER.debug("Could not remove an obsolete Xiaomi recording cache file")
