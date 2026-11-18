"""exclude_miot_services must also apply to the converters built by async_init."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.xiaomi_miot import DOMAIN
from custom_components.xiaomi_miot.core.device import Device, DeviceInfo
from custom_components.xiaomi_miot.core.device_customizes import DEVICE_CUSTOMIZES
from custom_components.xiaomi_miot.core.miot_spec import MiotSpec

MODEL = "test.light.occupancy"
URN = "urn:miot-spec-v2:device:light:0000A001:test-occupancy:1"


def _spec(hass):
    return MiotSpec(hass, {
        "type": URN,
        "description": "Light",
        "services": [
            {
                "iid": 2,
                "type": "urn:miot-spec-v2:service:light:00007802:test-occupancy:1",
                "description": "Light",
                "properties": [
                    {
                        "iid": 1,
                        "type": "urn:miot-spec-v2:property:on:00000006:test-occupancy:1",
                        "description": "Switch Status",
                        "format": "bool",
                        "access": ["read", "write", "notify"],
                    },
                ],
            },
            {
                "iid": 6,
                "type": "urn:miot-spec-v2:service:occupancy-sensor:0000780F:test-occupancy:1",
                "description": "Occupancy Sensor",
                "properties": [
                    {
                        "iid": 1,
                        "type": "urn:miot-spec-v2:property:occupancy-status:0000008B:test-occupancy:1",
                        "description": "Occupancy Status",
                        "format": "uint8",
                        "access": ["read", "notify"],
                        "value-list": [
                            {"value": 0, "description": "No One"},
                            {"value": 1, "description": "Has One"},
                        ],
                    },
                ],
            },
        ],
    })


@pytest.fixture
def customize():
    original = DEVICE_CUSTOMIZES.get(MODEL)

    def _set(cfg):
        DEVICE_CUSTOMIZES[MODEL] = cfg

    yield _set
    if original is None:
        DEVICE_CUSTOMIZES.pop(MODEL, None)
    else:
        DEVICE_CUSTOMIZES[MODEL] = original


async def _init_device(hass):
    hass.data[DOMAIN]["miot_specs"][MODEL] = _spec(hass)
    config = {"username": "test-user", "conn_mode": "cloud"}
    entry = SimpleNamespace(
        hass=hass,
        cloud=None,
        id="test-entry",
        adders={},
        get_config=lambda key=None, default=None: config.get(key, default),
    )
    device = Device(DeviceInfo({
        "did": "test-device",
        "mac": "aa:bb:cc:dd:ee:ff",
        "name": "Test Light",
        "model": MODEL,
        "urn": URN,
    }), entry)
    with patch.object(device, "init_coordinators", new=AsyncMock()), patch(
        "custom_components.xiaomi_miot.core.device.async_track_time_interval"
    ):
        await device.async_init()
    return device


def _service_names(device):
    return {
        conv.prop.service.name
        for conv in device.converters
        if getattr(conv, "prop", None)
    }


async def test_occupancy_converters_created_without_exclusion(hass, customize):
    customize({})
    device = await _init_device(hass)

    assert "occupancy_sensor" in _service_names(device)


async def test_excluded_service_creates_no_converters(hass, customize):
    customize({"exclude_miot_services": "occupancy_sensor"})
    device = await _init_device(hass)

    names = _service_names(device)
    assert "light" in names
    assert "occupancy_sensor" not in names
