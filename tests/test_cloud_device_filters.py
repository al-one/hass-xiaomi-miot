"""Device filtering must not report a cloud inventory failure."""
from unittest.mock import AsyncMock

import pytest

from custom_components.xiaomi_miot.core.xiaomi_cloud import MiotCloud


@pytest.mark.parametrize("devices, expected_warning", [([], True), ([{"did": "one", "model": "test.device"}], False)])
async def test_empty_inventory_warning_precedes_device_filters(hass, caplog, devices, expected_warning):
    cloud = MiotCloud(hass, "test-user", "test-password", "cn")
    cloud.async_get_devices = AsyncMock(return_value=devices)

    result = await cloud.async_get_devices_by_key(
        "did", filters={"filter_did": "exclude", "did_list": ["one"]},
    )

    assert result == {}
    assert ("No devices returned by Xiaomi cloud" in caplog.text) is expected_warning
    cloud.async_get_devices.assert_awaited_once_with(renew=False)


async def test_matching_device_is_retained(hass, caplog):
    cloud = MiotCloud(hass, "test-user", "test-password", "cn")
    cloud.async_get_devices = AsyncMock(return_value=[{"did": "one", "model": "test.device"}])

    result = await cloud.async_get_devices_by_key(
        "did", filters={"filter_did": "include", "did_list": ["one"]},
    )

    assert list(result) == ["one"]
    assert "No devices returned by Xiaomi cloud" not in caplog.text
