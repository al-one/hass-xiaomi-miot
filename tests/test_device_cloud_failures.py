"""Tests for logging of repeated cloud update failures."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

from custom_components.xiaomi_miot.core.device import Device, DeviceInfo
from custom_components.xiaomi_miot.core.xiaomi_cloud import MiCloudException

LOGGER = "custom_components.xiaomi_miot.core.device"
MAPPING = {"switch.on": {"siid": 2, "piid": 1}}
RESULT = [{"did": "123456", "siid": 2, "piid": 1, "code": 0, "value": True}]
OUTAGE = MiCloudException("Cloud API returned None response, possible timeout or empty data")


def make_device(hass, *responses):
    entry = SimpleNamespace(
        id="test-entry",
        hass=hass,
        cloud=SimpleNamespace(
            user_id="test-user",
            async_get_properties_for_mapping=AsyncMock(side_effect=list(responses)),
        ),
        get_config=lambda key=None, default=None: default,
    )
    info = DeviceInfo({
        "did": "123456",
        "mac": "aa:bb:cc:dd:ee:ff",
        "name": "Test Humidifier",
        "model": "xiaomi.humidifier.test",
        "pid": 0,
        "token": "0" * 32,
    })
    return Device(info, entry)


async def poll(device, times):
    for _ in range(times):
        await device.update_miot_status(
            mapping=MAPPING,
            use_local=False,
            use_cloud=True,
            check_lan=False,
        )


def records(caplog, level, text):
    return [
        r for r in caplog.records
        if r.name.startswith(LOGGER) and r.levelno == level and text in r.getMessage()
    ]


async def test_cloud_outage_logs_error_once(hass, caplog):
    device = make_device(hass, *[OUTAGE] * 8)

    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await poll(device, 8)

    assert device.available is False
    assert device._cloud_fails == 8
    assert len(records(caplog, logging.INFO, "will retry")) == 3
    errors = records(caplog, logging.ERROR, "marking unavailable")
    assert len(errors) == 1
    assert "failed 4 times" in errors[0].getMessage()
    assert len(records(caplog, logging.DEBUG, "marking unavailable")) == 4


async def test_cloud_recovery_logs_once_and_rearms_error(hass, caplog):
    device = make_device(hass, *[OUTAGE] * 5, RESULT, *[OUTAGE] * 4)

    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await poll(device, 6)
        assert device.available is True
        assert device._cloud_fails == 0
        recovered = records(caplog, logging.INFO, "succeeded again")
        assert len(recovered) == 1
        assert "after 5 failures" in recovered[0].getMessage()

        await poll(device, 4)

    assert device.available is False
    assert len(records(caplog, logging.ERROR, "marking unavailable")) == 2


async def test_cloud_success_without_outage_logs_nothing(hass, caplog):
    device = make_device(hass, OUTAGE, RESULT)

    with caplog.at_level(logging.INFO, logger=LOGGER):
        await poll(device, 2)

    assert device.available is True
    assert not records(caplog, logging.INFO, "succeeded again")
