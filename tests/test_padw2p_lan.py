"""Direct LAN routing, without sending commands to a real protection switch."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from custom_components.xiaomi_miot.core.device import MiotDevice
from custom_components.xiaomi_miot.core.device_customizes import DEVICE_CUSTOMIZES
from custom_components.xiaomi_miot.core.miot_local_devices import MIOT_LOCAL_MODELS


MODEL = "iot.switch.padw2p"


def test_padw2p_is_a_direct_lan_model():
    assert MODEL in MIOT_LOCAL_MODELS


def test_padw2p_keeps_existing_cloud_energy_source():
    customizes = DEVICE_CUSTOMIZES[MODEL]
    assert customizes["auto_cloud"] is True
    assert customizes["stat_power_cost_key"] == "3.1"
    assert customizes["stat_power_cost_type"] == "stat_day_v3"
    assert customizes["sensor_attributes"] == "power_cost_today,power_cost_month"


async def test_lan_mapping_uses_existing_chunking(hass):
    responses = [
        {"did": "test-device", "siid": 3, "piid": p, "code": 0, "value": p * 10}
        for p in (2, 3, 4)
    ]
    miio = SimpleNamespace(send=AsyncMock(side_effect=[
        {"result": responses[:2]}, {"result": responses[2:]},
    ]))
    local = MiotDevice(hass, miio)
    mapping = {str(p): {"siid": 3, "piid": p} for p in (2, 3, 4)}
    result = await local.async_get_properties_for_mapping(
        did="test-device", mapping=mapping, max_properties=2,
    )
    assert result == responses
    assert miio.send.await_args_list[0].args == (
        "get_properties", [
            {"did": "test-device", "siid": 3, "piid": 2},
            {"did": "test-device", "siid": 3, "piid": 3},
        ],
    )
    assert miio.send.await_args_list[1].args[1] == [
        {"did": "test-device", "siid": 3, "piid": 4},
    ]
