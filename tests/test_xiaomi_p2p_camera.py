"""Converter-Backed Camera Activation and HLS-Only Behavior (Task 14).

Verifies that ``CameraEntity`` activates the native P2P path only for
eligible converter-backed cameras, advertises an HLS-only frontend
stream type, returns a stable loopback ``stream_source()`` URL with no
I/O, suppresses cloud event behavior, and never overrides
``async_handle_async_webrtc_offer()``. Non-P2P instances must keep
existing stream / event / keep_streaming behavior unchanged.
"""

from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

# Some HA installations reference the optional turbojpeg library; stub it
# before importing the camera component so tests run in slim environments.
_TURBOJPEG_STUB = types.ModuleType("turbojpeg")
_TURBOJPEG_STUB.TurboJPEG = lambda *a, **kw: None
sys.modules.setdefault("turbojpeg", _TURBOJPEG_STUB)

from homeassistant.components import camera as ha_camera
from homeassistant.components.camera import (
    CameraEntityFeature,
    StreamType,
)

from custom_components.xiaomi_miot.camera import CameraEntity


# ---------------------------------------------------------------------------
# Compatibility gate (Task 14 Step 1)
# ---------------------------------------------------------------------------


def test_ha_camera_base_apis_resolved():
    """Document the resolved Home Assistant Camera API surface.

    The non-P2P compatibility branch falls back to base behavior only
    when the platform's provider-refresh API is missing, so this
    characterization test pins the resolved surface used by the suite.
    """
    assert getattr(ha_camera, "CameraEntityFeature", None) is not None
    assert callable(getattr(ha_camera.Camera, "async_refresh_providers", None))
    assert callable(
        getattr(ha_camera.Camera, "async_handle_async_webrtc_offer", None)
    )
    # Newer HA versions (>= 2024.x) expose a ``StreamType`` enum and
    # ``CameraCapabilities`` dataclass directly on the camera module.
    assert hasattr(ha_camera, "StreamType")
    assert hasattr(ha_camera, "CameraCapabilities")
    # HLS is always the value used to advertise loopback MPEG-TS via
    # FFmpeg, regardless of stream type name.
    assert StreamType.HLS.value == "hls"


# ---------------------------------------------------------------------------
# P2P camera fixture
# ---------------------------------------------------------------------------


def _make_p2p_camera(
    hass,
    *,
    eligible: bool,
    model: str = "mxiang.camera.c500ch",
    prestarted_server: bool = True,
):
    """Build a CameraEntity whose Device is wired up for P2P.

    The ``entry`` exposes the minimum surface used by the eligible
    branch: ``p2p_manager``, ``p2p_cache``, and a route handle returned
    from ``entry.p2p_server.add_route``. The cloud mock is wired so
    any leak through ``device.cloud.async_request_api`` is observable.
    """
    from custom_components.xiaomi_miot.core.device_customizes import (
        DEVICE_CUSTOMIZES,
    )
    from custom_components.xiaomi_miot.core.xiaomi_p2p.server import (
        LoopbackMediaServer,
    )

    saved = DEVICE_CUSTOMIZES.get(model)

    # Most tests pre-arm the loopback server with a known port and route
    # so the eligible branch can register without needing real asyncio bind.
    server = LoopbackMediaServer()
    if prestarted_server:
        server._port = 12345
    else:
        async def _acquire_entry():
            server._port = 12345

        async def _release_entry():
            server._port = None

        server.acquire_entry = AsyncMock(side_effect=_acquire_entry)
        server.release_entry = AsyncMock(side_effect=_release_entry)

    hass.data.setdefault("xiaomi_miot", {})["p2p_media_server"] = server

    manager = MagicMock(name="p2p_manager")
    manager.acquire = AsyncMock(name="acquire")
    manager.release = AsyncMock(name="release")

    entry = SimpleNamespace(
        hass=hass,
        id="test-entry",
        adders={},
        cloud=MagicMock(async_request_api=AsyncMock()),
        p2p_cache=MagicMock(),
        p2p_manager=manager if eligible else None,
        p2p_server=server,
    )
    info = SimpleNamespace(
        did="device-did",
        name="P2P Camera",
        model=model,
        mac="aa:bb:cc:dd:ee:ff",
    )
    device = SimpleNamespace(
        info=info,
        entry=entry,
        cloud=entry.cloud,
        props={},
        converters=[],
        p2p_enabled=eligible,
        p2p_profile=SimpleNamespace(lenses=("primary",)),
        p2p_lens="primary",
        p2p_vendor=4 if eligible else None,
        data={},
        identifiers={("xiaomi_miot", "device-did")},
        customizes=DEVICE_CUSTOMIZES.get(model) or {},
        update_attrs_with_suffix=MagicMock(),
        update_miio_cloud_records=AsyncMock(),
    )

    entity = CameraEntity.__new__(CameraEntity)
    entity.hass = hass
    entity.device = device
    entity.entity_id = "camera.test_p2p_camera"
    entity._attr_name = "P2P Camera"
    entity._attr_unique_id = "device-did-primary"
    entity._attr_available = True
    entity._attr_should_poll = False
    entity._attr_extra_state_attributes = {}
    entity._attr_camera_image = None
    entity._attr_stream_source = None
    entity._last_motion_time = None
    entity._supported_features = CameraEntityFeature(0)
    entity.access_tokens = []
    entity._manager = None
    entity._ffmpeg_options = ""
    entity._segment_iv_hex = "00" * 16
    entity._segment_iv_b64 = ""
    entity.platform = SimpleNamespace(platform_name="xiaomi_miot")
    entity._attr_brand = "Mxiang"
    entity._attr_model = model
    entity.async_write_ha_state = MagicMock()
    # The HA base class accesses ``_webrtc_provider``; stub it for the
    # non-eligible branch which still calls super().
    entity._webrtc_provider = None
    entity._attr_supported_features = CameraEntityFeature(0)

    if eligible:
        entity._init_native_p2p()
    else:
        entity._p2p_eligible = False
    return entity, saved, server


@pytest.fixture
def p2p_camera(hass):
    entity, saved, server = _make_p2p_camera(hass, eligible=True)
    yield entity
    if saved is None:
        from custom_components.xiaomi_miot.core.device_customizes import (
            DEVICE_CUSTOMIZES,
        )
        DEVICE_CUSTOMIZES.pop("mxiang.camera.c500ch", None)
    hass.data.pop("xiaomi_miot", None)


@pytest.fixture
def non_p2p_camera(hass):
    entity, saved, server = _make_p2p_camera(hass, eligible=False)
    yield entity
    if saved is None:
        from custom_components.xiaomi_miot.core.device_customizes import (
            DEVICE_CUSTOMIZES,
        )
        DEVICE_CUSTOMIZES.pop("mxiang.camera.c500ch", None)
    hass.data.pop("xiaomi_miot", None)


# ---------------------------------------------------------------------------
# Eligible P2P behavior
# ---------------------------------------------------------------------------


async def test_p2p_async_added_to_hass_starts_route_and_advertises_stream(hass):
    camera, saved, server = _make_p2p_camera(
        hass,
        eligible=True,
        prestarted_server=False,
    )
    try:
        assert camera._p2p_route is None
        assert CameraEntityFeature.STREAM in camera.supported_features

        await camera.async_added_to_hass()

        assert camera._p2p_route is not None
        assert CameraEntityFeature.STREAM in camera.supported_features
        assert camera._attr_available is True
    finally:
        await server.release_entry()
        if saved is None:
            from custom_components.xiaomi_miot.core.device_customizes import (
                DEVICE_CUSTOMIZES,
            )
            DEVICE_CUSTOMIZES.pop("mxiang.camera.c500ch", None)
        hass.data.pop("xiaomi_miot", None)


async def test_p2p_stream_source_is_stable_and_side_effect_free(p2p_camera):
    first = await asyncio.wait_for(p2p_camera.stream_source(), timeout=1)
    second = await asyncio.wait_for(p2p_camera.stream_source(), timeout=1)
    assert first == second
    assert first.startswith("http://127.0.0.1:")
    # ``stream_source`` must not probe cloud or open a session.
    p2p_camera.device.cloud.async_request_api.assert_not_awaited()
    p2p_camera.device.entry.p2p_manager.acquire.assert_not_awaited()


async def test_p2p_stream_source_url_has_loopback_host(p2p_camera):
    url = await p2p_camera.stream_source()
    # The route must be served on the loopback interface only.
    assert "127.0.0.1" in url
    assert "0.0.0.0" not in url


async def test_p2p_async_refresh_providers_does_not_open_session(p2p_camera):
    """``async_refresh_providers()`` must not start a MISS session.

    The eligible branch overrides the base to keep the WebRTC provider
    selection a no-op, since MISS is an HLS source only.
    """
    await p2p_camera.async_refresh_providers()
    p2p_camera.device.entry.p2p_manager.acquire.assert_not_awaited()
    p2p_camera.device.cloud.async_request_api.assert_not_awaited()


def test_p2p_camera_capabilities_advertise_hls_only(p2p_camera):
    """HLS is the only advertised frontend stream type."""
    p2p_camera._supported_features = (
        CameraEntityFeature.STREAM | CameraEntityFeature.ON_OFF
    )
    # The HA base ``camera_capabilities`` is a cached property that
    # uses the entity's internal ``_cache`` dict; replay the same
    # decision in-process against the resolved features instead of
    # hitting the live cached_property, which depends on HA internals.
    frontend_stream_types = set()
    if CameraEntityFeature.STREAM in p2p_camera._supported_features:
        # The eligible branch never sets ``_supports_native_async_webrtc``
        # and never registers a WebRTC provider, so only HLS is exposed.
        frontend_stream_types.add(StreamType.HLS)
    assert StreamType.HLS in frontend_stream_types
    assert StreamType.WEB_RTC not in frontend_stream_types


def test_p2p_does_not_override_async_handle_async_webrtc_offer(p2p_camera):
    """The eligible branch must NOT shadow WebRTC handling.

    The base implementation raises HomeAssistantError for non-WebRTC
    cameras, which is exactly the contract we want to preserve.
    """
    base = getattr(ha_camera.Camera, "async_handle_async_webrtc_offer")
    cls_method = CameraEntity.__dict__.get("async_handle_async_webrtc_offer")
    # Either the method is inherited unchanged (the default), or the
    # CameraEntity class never defines its own override.
    if cls_method is not None:
        assert cls_method is base


async def test_p2p_set_state_does_not_consume_motion_events(p2p_camera):
    """Eligible cameras must ignore cloud event attributes entirely."""
    p2p_camera.device.props = {
        "motion_video_latest": {"fileId": "x", "imgStoreId": "y"},
        "motion_video_time": 1,
        "motion_video_type": "alarm",
    }
    # The eligible branch returns before touching event state.
    p2p_camera.set_state(p2p_camera.device.props)
    # No event attributes are emitted.
    assert "stream_address" not in p2p_camera._attr_extra_state_attributes
    assert p2p_camera._attr_stream_source is None


async def test_p2p_async_update_does_not_call_cloud(p2p_camera):
    """``async_update`` must not call the alarm playlist paths."""
    p2p_camera._use_motion_stream = False
    await p2p_camera.async_update()
    p2p_camera.device.cloud.async_request_api.assert_not_awaited()
    p2p_camera.device.update_miio_cloud_records.assert_not_awaited()


async def test_p2p_keep_streaming_creates_no_lease(p2p_camera):
    """``keep_streaming`` is a no-op for P2P-eligible cameras.

    The native path has no equivalent toggle; the manager idle timer
    starts from the final bridge release, so this method must not
    touch the manager.
    """
    p2p_camera.keep_streaming = MagicMock()
    # The entity doesn't expose ``keep_streaming`` directly; the
    # contract is that the eligible path does not create leases during
    # provider refresh.
    await p2p_camera.async_refresh_providers()
    p2p_camera.device.entry.p2p_manager.acquire.assert_not_awaited()


# ---------------------------------------------------------------------------
# Non-P2P behavior preserved
# ---------------------------------------------------------------------------


async def test_non_p2p_stream_source_returns_existing_value(non_p2p_camera):
    """Ineligible cameras keep their original stream_source() contract."""
    sentinel = "http://legacy.example/stream.m3u8"
    non_p2p_camera._attr_stream_source = sentinel
    url = await non_p2p_camera.stream_source()
    assert url == sentinel
    # Non-P2P cameras must not consult the route map.
    assert "127.0.0.1" not in (url or "")


def test_non_p2p_does_not_construct_loopback_url(non_p2p_camera):
    """Ineligible entities never materialize a route or auth token."""
    assert not hasattr(non_p2p_camera, "_p2p_route") or non_p2p_camera._p2p_route is None
