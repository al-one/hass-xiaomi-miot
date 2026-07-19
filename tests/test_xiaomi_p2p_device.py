"""Device-side P2P eligibility, profile resolution, and dual-lens expansion.

Verifies that ``Device._async_init_p2p()`` only activates native streaming
for converter-backed cameras whose MIoT spec declares ``p2p-stream``, whose
``Device`` belongs to a Xiaomi account entry, and whose setup-time preflight
returns vendor ``4``. The matrix also locks down the merged profile behavior
and the dual-lens converter expansion that ``mxiang.camera.c500ch`` requires.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.xiaomi_miot.core.const import CONF_CONN_MODE
from custom_components.xiaomi_miot.core.converters import MiotCameraConv
from custom_components.xiaomi_miot.core.device import Device, DeviceInfo
from custom_components.xiaomi_miot.core.miot_spec import MiotSpec
from custom_components.xiaomi_miot.core.xiaomi_p2p import (
    DEFAULT_P2P_PROFILE,
    P2P_PROFILES,
)


# ---------------------------------------------------------------------------
# Eligibility matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("conn_mode", ["local", "auto", "cloud"])
async def test_account_candidate_activates_after_vendor_four(
    make_p2p_device, conn_mode
):
    device = await make_p2p_device(
        "generic.camera.p2p.json",
        account=True,
        conn_mode=conn_mode,
        vendor=4,
        model="generic.camera.p2p",
    )
    assert device.p2p_enabled is True
    assert device.p2p_profile == DEFAULT_P2P_PROFILE
    assert device.p2p_vendor == 4
    assert device.p2p_lens == "primary"


async def test_host_token_candidate_never_preflights(make_p2p_device):
    device = await make_p2p_device(
        "generic.camera.p2p.json",
        account=False,
        vendor=4,
        model="generic.camera.p2p",
    )
    assert device.p2p_enabled is False
    assert device.p2p_vendor is None
    assert device.p2p_profile == DEFAULT_P2P_PROFILE
    device.entry.p2p_cache.get_or_probe.assert_not_awaited()


async def test_spec_without_p2p_stream_service_stays_inactive(hass):
    """A spec that omits the ``p2p-stream`` marker must never preflight.

    Build the device inline so the fixture URN can stay the same as the
    generic P2P fixture; the eligibility gate inspects only the resolved
    spec's services, not the model name.
    """
    spec = MiotSpec(
        hass,
        {
            "type": "urn:miot-spec-v2:device:camera:0000A016:generic-p2p:1",
            "description": "No p2p",
            "services": [
                {
                    "iid": 1,
                    "type": (
                        "urn:miot-spec-v2:service:device-information:00007801:"
                        "generic-p2p:1"
                    ),
                    "description": "Device Information",
                    "properties": [
                        {
                            "iid": 1,
                            "type": (
                                "urn:miot-spec-v2:property:manufacturer:00000001:"
                                "generic-p2p:1"
                            ),
                            "description": "Manufacturer",
                            "format": "string",
                            "access": ["read", "notify"],
                        }
                    ],
                    "actions": [],
                    "events": [],
                },
                {
                    "iid": 2,
                    "type": (
                        "urn:miot-spec-v2:service:camera-control:00007851:"
                        "generic-p2p:1"
                    ),
                    "description": "Camera Control",
                    "properties": [
                        {
                            "iid": 1,
                            "type": (
                                "urn:miot-spec-v2:property:on:00000006:"
                                "generic-p2p:1"
                            ),
                            "description": "Switch Status",
                            "format": "bool",
                            "access": ["read", "write", "notify"],
                        }
                    ],
                    "actions": [],
                    "events": [],
                },
            ],
        },
    )

    cache = MagicMock(name="p2p_cache")
    cache.get_or_probe = AsyncMock(
        side_effect=AssertionError("should not probe")
    )

    config = {CONF_CONN_MODE: "auto", "username": "account-user"}

    def _get(key=None, default=None):
        if key is None:
            return config
        return config.get(key, default)

    entry = SimpleNamespace(
        hass=hass,
        cloud=MagicMock(default_server="cn"),
        id="test-entry",
        adders={},
        get_config=_get,
        p2p_cache=cache,
    )
    info = DeviceInfo(
        {
            "did": "device-did",
            "mac": "aa:bb:cc:dd:ee:ff",
            "name": "No P2P Camera",
            "model": "generic.camera.p2p",
            "urn": spec.type,
            "localip": "192.168.1.20",
        }
    )
    device = Device(info, entry)
    device.spec = spec
    await device.async_init()

    assert device.p2p_enabled is False
    assert device.p2p_vendor is None
    cache.get_or_probe.assert_not_awaited()


async def test_non_four_vendor_leaves_p2p_disabled(make_p2p_device):
    device = await make_p2p_device(
        "generic.camera.p2p.json",
        account=True,
        vendor=2,
        model="generic.camera.p2p",
    )
    assert device.p2p_enabled is False
    # Only vendor 4 is CS2-eligible; the device layer treats any other
    # result as "not a CS2 camera" and clears ``p2p_vendor``.
    assert device.p2p_vendor is None
    assert device.p2p_profile == DEFAULT_P2P_PROFILE


async def test_failed_preflight_disables_p2p(make_p2p_device):
    """A probe that returns a sentinel ``-1`` must disable P2P cleanly.

    The device-side probe wrapper converts ``MissError`` into ``-1`` so
    a failed preflight is observable without leaking exception text into
    the device state.
    """
    device = await make_p2p_device(
        "generic.camera.p2p.json",
        account=True,
        vendor=-1,
        model="generic.camera.p2p",
    )
    assert device.p2p_enabled is False
    # The failed preflight is a non-4 result, so p2p_vendor is cleared
    # and only p2p_profile (the model profile resolution) survives.
    assert device.p2p_vendor is None
    assert device.p2p_profile == DEFAULT_P2P_PROFILE


async def test_account_candidate_uses_entry_id_did_region_keys(make_p2p_device):
    device = await make_p2p_device(
        "generic.camera.p2p.json",
        account=True,
        vendor=4,
        model="generic.camera.p2p",
        did="unique-did",
        entry_id="entry-A",
    )
    call = device.entry.p2p_cache.get_or_probe.await_args
    assert call is not None
    # ``(entry_id, region, did)`` are the documented cache key parts.
    assert call.args[0] == "entry-A"
    assert call.args[2] == "unique-did"
    # ``region`` is derived from the cloud's ``default_server`` (lowercased).
    assert call.args[1] == "cn"


async def test_did_isolation_across_entries(make_p2p_device):
    """The same DID resolved through two entries must stay isolated.

    Each entry is responsible for its own ``(entry_id, region, did)``
    cache lookup; one entry's preflight outcome must not leak to another
    even when they share a DID.
    """
    a = await make_p2p_device(
        "generic.camera.p2p.json",
        account=True,
        vendor=4,
        did="shared-did",
        entry_id="entry-A",
    )
    b = await make_p2p_device(
        "generic.camera.p2p.json",
        account=True,
        vendor=4,
        did="shared-did",
        entry_id="entry-B",
    )
    a_call = a.entry.p2p_cache.get_or_probe.await_args
    b_call = b.entry.p2p_cache.get_or_probe.await_args
    assert a_call is not None
    assert b_call is not None
    a_entry_id = a_call.args[0]
    b_entry_id = b_call.args[0]
    a_did = a_call.args[2]
    b_did = b_call.args[2]
    assert a_entry_id == "entry-A"
    assert b_entry_id == "entry-B"
    assert a_entry_id != b_entry_id
    assert a_did == b_did == "shared-did"


# ---------------------------------------------------------------------------
# Profile resolution
# ---------------------------------------------------------------------------


async def test_default_profile_when_model_not_in_registry(make_p2p_device):
    device = await make_p2p_device(
        "generic.camera.p2p.json",
        account=True,
        vendor=4,
        model="generic.camera.p2p",
    )
    assert device.p2p_profile == DEFAULT_P2P_PROFILE
    assert device.p2p_profile.lenses == ("primary",)
    assert device.p2p_profile.transport == "auto"
    assert device.p2p_profile.raw_quality == 0


async def test_exact_model_overrides_for_isa_hlc7(make_p2p_device):
    device = await make_p2p_device(
        "isa.camera.hlc7.json",
        account=True,
        vendor=4,
        model="isa.camera.hlc7",
    )
    assert device.p2p_profile == P2P_PROFILES["isa.camera.hlc7"]
    profile = device.p2p_profile
    assert profile.transport == "prefer_udp"
    assert profile.raw_quality == 2
    assert profile.request_audio is True
    assert profile.required_video_codec == 5
    assert profile.required_audio_codec == 1027


async def test_exact_model_overrides_for_chuangmi_039c01(make_p2p_device):
    device = await make_p2p_device(
        "chuangmi.camera.039c01.json",
        account=True,
        vendor=4,
        model="chuangmi.camera.039c01",
    )
    profile = device.p2p_profile
    assert profile.transport == "prefer_tcp"
    assert profile.raw_quality == 2
    assert profile.required_video_codec == 5
    assert profile.required_audio_codec == 1032


async def test_unknown_support_config_keys_are_ignored(make_p2p_device):
    """The merge must only read the documented ``p2p_overrides`` keys.

    A model customizes payload with extra unknown fields must not bleed
    into the resolved ``P2PProfile`` or raise during resolution.
    """
    from custom_components.xiaomi_miot.core.device_customizes import (
        DEVICE_CUSTOMIZES,
    )

    saved = DEVICE_CUSTOMIZES.get("generic.camera.p2p")
    DEVICE_CUSTOMIZES["generic.camera.p2p"] = {
        "p2p_overrides": {
            "lenses": ["primary"],
            "raw_quality": 0,
            "support_config": {"force": True},
            "vendor_specific": 99,
        },
    }
    try:
        device = await make_p2p_device(
            "generic.camera.p2p.json",
            account=True,
            vendor=4,
            model="generic.camera.p2p",
        )
        profile = device.p2p_profile
        assert profile.lenses == ("primary",)
        assert not hasattr(profile, "support_config")
        assert not hasattr(profile, "vendor_specific")
    finally:
        if saved is None:
            DEVICE_CUSTOMIZES.pop("generic.camera.p2p", None)
        else:
            DEVICE_CUSTOMIZES["generic.camera.p2p"] = saved


async def test_optional_codecs_default_to_none(make_p2p_device):
    device = await make_p2p_device(
        "generic.camera.p2p.json",
        account=True,
        vendor=4,
        model="generic.camera.p2p",
    )
    assert device.p2p_profile.required_video_codec is None
    assert device.p2p_profile.required_audio_codec is None


# ---------------------------------------------------------------------------
# Dual-lens converter expansion
# ---------------------------------------------------------------------------


def _camera_converters(device):
    return [c for c in device.converters if isinstance(c, MiotCameraConv)]


async def test_mxiang_c500ch_creates_two_camera_converters(make_p2p_device):
    device = await make_p2p_device(
        "mxiang.camera.c500ch.json",
        account=True,
        vendor=4,
        model="mxiang.camera.c500ch",
    )
    cameras = _camera_converters(device)
    assert len(cameras) == 2
    attrs = [c.attr for c in cameras]
    # The original camera converter (from the camera_control service) is
    # preserved unchanged and one secondary clone is appended per extra
    # lens declared in the profile.
    assert any("secondary" in a for a in attrs)


async def test_dual_lens_secondary_has_unique_id_suffix(make_p2p_device):
    device = await make_p2p_device(
        "mxiang.camera.c500ch.json",
        account=True,
        vendor=4,
        model="mxiang.camera.c500ch",
    )
    cameras = _camera_converters(device)
    assert len(cameras) == 2
    primary = cameras[0]
    secondary = cameras[1]
    assert primary.attr != secondary.attr
    assert "secondary" in secondary.attr
    # The secondary carries an explicit ``unique_id`` option so the
    # entity layer can register it without colliding with the primary.
    assert secondary.option.get("use_unique_attr") is True
    assert secondary.option.get("unique_id") == secondary.attr


async def test_dual_lens_inactive_when_preflight_fails(make_p2p_device):
    device = await make_p2p_device(
        "mxiang.camera.c500ch.json",
        account=True,
        vendor=2,
        model="mxiang.camera.c500ch",
    )
    assert device.p2p_enabled is False
    # Only the original camera converter from init_converters survives.
    cameras = _camera_converters(device)
    assert len(cameras) == 1
    assert all("secondary" not in c.attr for c in cameras)


async def test_single_lens_profile_does_not_clone_converter(make_p2p_device):
    """A profile with one lens must not duplicate the camera converter."""
    device = await make_p2p_device(
        "isa.camera.hlc7.json",
        account=True,
        vendor=4,
        model="isa.camera.hlc7",
    )
    cameras = _camera_converters(device)
    assert len(cameras) == 1
    assert all("secondary" not in c.attr for c in cameras)
