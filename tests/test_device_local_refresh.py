"""Tests for refreshing stale Xiaomi local addresses."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from custom_components.xiaomi_miot.core.device import Device, DeviceInfo, MiotDevice
from custom_components.xiaomi_miot.core.utils import DeviceException


def make_device(hass, cloud_info):
    entry = SimpleNamespace(
        id="test-entry",
        hass=hass,
        cloud=SimpleNamespace(user_id="test-user"),
        get_config=lambda key=None, default=None: default,
        get_cloud_device=AsyncMock(return_value=cloud_info),
    )
    info = DeviceInfo({
        "did": "123456",
        "mac": "aa:bb:cc:dd:ee:ff",
        "name": "Test Air Conditioner",
        "model": "xiaomi.aircondition.test",
        "pid": 0,
        "localip": "192.0.2.1",
        "token": "0" * 32,
    })
    device = Device(info, entry)
    device.local = MiotDevice.from_device(device)
    return device, entry


async def test_refresh_local_device_rebuilds_client_after_ip_change(hass):
    device, entry = make_device(hass, {
        "did": "123456",
        "mac": "aa:bb:cc:dd:ee:ff",
        "localip": "192.0.2.2",
        "token": "0" * 32,
    })
    old_local = device.local
    device._local_fails = 3
    device._local_state = False

    assert await device.async_refresh_local_device() is True
    assert device.info.host == "192.0.2.2"
    assert device.local.host == "192.0.2.2"
    assert device.local is not old_local
    assert device._local_fails == 0
    assert device._local_state is None
    entry.get_cloud_device.assert_awaited_once_with(did="123456", renew=True)


async def test_refresh_local_device_keeps_client_when_address_is_unchanged(hass):
    device, entry = make_device(hass, {
        "did": "123456",
        "mac": "aa:bb:cc:dd:ee:ff",
        "localip": "192.0.2.1",
        "token": "0" * 32,
    })
    old_local = device.local

    assert await device.async_refresh_local_device() is False
    assert device.local is old_local
    entry.get_cloud_device.assert_awaited_once_with(did="123456", renew=True)


async def test_refresh_local_device_keeps_old_client_when_new_info_is_invalid(hass):
    device, _ = make_device(hass, {
        "did": "123456",
        "mac": "aa:bb:cc:dd:ee:ff",
        "localip": "0.0.0.0",
        "token": "0" * 32,
    })
    old_info = device.info
    old_local = device.local

    assert await device.async_refresh_local_device() is False
    assert device.info is old_info
    assert device.local is old_local


async def test_third_local_failure_refreshes_address_and_retries(hass):
    device, _ = make_device(hass, {})
    device._local_fails = 2
    device.async_refresh_local_device = AsyncMock(return_value=True)
    device.local = SimpleNamespace(
        get_max_properties=lambda mapping: 1,
        async_get_properties_for_mapping=AsyncMock(side_effect=[
            DeviceException("offline"),
            [{"did": "123456", "siid": 2, "piid": 1, "code": 0, "value": True}],
        ]),
    )
    mapping = {"switch.on": {"siid": 2, "piid": 1}}

    result = await device.update_miot_status(
        mapping=mapping,
        use_local=True,
        use_cloud=False,
        auto_cloud=False,
        max_properties=1,
    )

    assert result.is_valid
    device.async_refresh_local_device.assert_awaited_once_with()
    assert device.local.async_get_properties_for_mapping.await_count == 2
    assert device.available is True
    assert device._local_fails == 0
