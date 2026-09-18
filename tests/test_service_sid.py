"""Tests for async_request_xiaomi_api SID validation and unavailable-cloud error."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.xiaomi_miot import init_integration_data
from custom_components.xiaomi_miot.core.hass_entity import BasicEntity
from custom_components.xiaomi_miot.core.xiaomi_cloud import MiotCloud


def _make_cloud(sid, **attrs):
    cloud = MiotCloud.__new__(MiotCloud)
    cloud.sid = sid
    for k, v in attrs.items():
        setattr(cloud, k, v)
    return cloud


class _FakeDevice:
    hass = None
    model = "test.device"


def _entity(hass, cloud):
    dev = _FakeDevice()
    dev.hass = hass
    dev.cloud = cloud
    init_integration_data(hass)
    ent = BasicEntity.__new__(BasicEntity)
    ent.device = dev
    return ent, dev


async def test_request_xiaomi_api_unsupported_sid_raises_without_xiaomi_call(hass):
    cloud = _make_cloud(
        "xiaomiio",
        async_request_api=AsyncMock(return_value={"ok": True}),
        async_change_sid=AsyncMock(),
    )
    ent, dev = _entity(hass, cloud)
    with pytest.raises(HomeAssistantError):
        await ent.async_request_xiaomi_api("home/device_list", sid="not-a-sid")
    dev.cloud.async_request_api.assert_not_awaited()
    dev.cloud.async_change_sid.assert_not_awaited()


async def test_request_xiaomi_api_micoapi_when_cloud_none_raises_unavailable(hass):
    cloud = _make_cloud(
        "micoapi",
        async_change_sid=AsyncMock(return_value=None),
        async_request_api=AsyncMock(),
    )
    ent, dev = _entity(hass, cloud)
    with pytest.raises(HomeAssistantError) as exc:
        await ent.async_request_xiaomi_api("home/device_list", sid="micoapi")
    assert str(exc.value) == "Xiaomi cloud is unavailable"
    dev.cloud.async_request_api.assert_not_awaited()


async def test_request_xiaomi_api_imicom_via_owner_lookup(hass):
    imicom_cloud = _make_cloud(
        "i.mi.com",
        async_request_api=AsyncMock(return_value={"ok": True}),
    )
    cloud = _make_cloud(
        "xiaomiio",
        async_change_sid=AsyncMock(return_value=imicom_cloud),
        async_request_api=AsyncMock(),
    )
    ent, dev = _entity(hass, cloud)
    out = await ent.async_request_xiaomi_api("home/device_list", sid="i.mi.com")
    assert out == {"ok": True}


async def test_request_xiaomi_api_default_sid_routes_via_change_sid(hass):
    target = _make_cloud(
        "xiaomiio",
        async_request_api=AsyncMock(return_value={"default": 1}),
    )
    cloud = _make_cloud(
        "xiaomiio",
        async_change_sid=AsyncMock(return_value=target),
        async_request_api=AsyncMock(),
    )
    ent, dev = _entity(hass, cloud)
    out = await ent.async_request_xiaomi_api("home/device_list")
    assert out == {"default": 1}


async def test_request_xiaomi_api_non_miotcloud_raises(hass):
    ent, dev = _entity(hass, SimpleNamespace(sid="xiaomiio"))
    with pytest.raises(HomeAssistantError):
        await ent.async_request_xiaomi_api("home/device_list")


async def test_request_xiaomi_api_mismatched_sid_after_change_raises_unavailable(hass):
    wrong = _make_cloud(
        "xiaomiio",
        async_request_api=AsyncMock(),
    )
    cloud = _make_cloud(
        "xiaomiio",
        async_change_sid=AsyncMock(return_value=wrong),
        async_request_api=AsyncMock(),
    )
    ent, dev = _entity(hass, cloud)
    with pytest.raises(HomeAssistantError) as exc:
        await ent.async_request_xiaomi_api("home/device_list", sid="micoapi")
    assert str(exc.value) == "Xiaomi cloud is unavailable"