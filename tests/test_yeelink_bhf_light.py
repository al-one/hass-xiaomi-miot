from unittest.mock import AsyncMock, MagicMock
import pytest

from custom_components.xiaomi_miot.core.device_customizes import DEVICE_CUSTOMIZES
from custom_components.xiaomi_miot.core.miio2miot import Miio2MiotHelper
from custom_components.xiaomi_miot.core.miot_spec import MiotSpec
from custom_components.xiaomi_miot.core.utils import DeviceException


V6_SPEC_DICT = {
    "urn": "urn:miot-spec-v2:device:bath-heater:0000A028:yeelink-v6:2",
    "services": [
        {
            "iid": 2,
            "type": "urn:miot-spec-v2:service:light:00007802:yeelink-v6:2",
            "description": "Light",
            "properties": [
                {
                    "iid": 1,
                    "type": "urn:miot-spec-v2:property:on:00000006:yeelink-v6:2",
                    "description": "Switch Status",
                    "format": "bool",
                    "access": ["read", "write", "notify"],
                },
                {
                    "iid": 2,
                    "type": "urn:miot-spec-v2:property:mode:00000008:yeelink-v6:2",
                    "description": "Mode",
                    "format": "uint8",
                    "access": ["read", "write", "notify"],
                    "value-list": [
                        {"value": 0, "description": "Day"},
                        {"value": 1, "description": "Night"},
                    ],
                },
                {
                    "iid": 3,
                    "type": "urn:miot-spec-v2:property:brightness:0000000D:yeelink-v6:2",
                    "description": "Brightness",
                    "format": "uint8",
                    "access": ["read", "write", "notify"],
                    "value-range": [1, 100, 1],
                },
            ],
        },
        {
            "iid": 3,
            "type": "urn:miot-spec-v2:service:ptc-bath-heater:00007834:yeelink-v6:2",
            "description": "PTC Bath Heater",
            "properties": [
                {
                    "iid": 1,
                    "type": "urn:miot-spec-v2:property:mode:00000008:yeelink-v6:2",
                    "description": "Mode",
                    "format": "uint8",
                    "access": ["read", "write", "notify"],
                    "value-list": [
                        {"value": 0, "description": "Idle"},
                        {"value": 1, "description": "Quick Heat"},
                        {"value": 2, "description": "Quick Defog"},
                        {"value": 3, "description": "Quick Vent"},
                        {"value": 4, "description": "Quick Dry"},
                    ],
                },
                {
                    "iid": 101,
                    "type": "urn:miot-spec-v2:property:fan-level:00000016:yeelink-v6:2",
                    "description": "Fan Level",
                    "format": "uint8",
                    "access": ["read", "write"],
                    "value-list": [
                        {"value": 1, "description": "Level1"},
                        {"value": 2, "description": "Level2"},
                        {"value": 3, "description": "Level3"},
                    ],
                },
                {
                    "iid": 111,
                    "type": "urn:miot-spec-v2:property:heat-mode:00000000:yeelink-v6:2",
                    "description": "Heat Mode",
                    "format": "uint8",
                    "access": ["read", "write"],
                    "value-list": [
                        {"value": 0, "description": "Off"},
                        {"value": 1, "description": "Low"},
                        {"value": 2, "description": "High"},
                    ],
                },
                {
                    "iid": 112,
                    "type": "urn:miot-spec-v2:property:cold-mode:00000000:yeelink-v6:2",
                    "description": "Cold Mode",
                    "format": "uint8",
                    "access": ["read", "write"],
                    "value-list": [
                        {"value": 0, "description": "Off"},
                        {"value": 1, "description": "Low"},
                        {"value": 3, "description": "High"},
                    ],
                },
                {
                    "iid": 113,
                    "type": "urn:miot-spec-v2:property:vent-mode:00000000:yeelink-v6:2",
                    "description": "Vent Mode",
                    "format": "uint8",
                    "access": ["read", "write"],
                    "value-list": [
                        {"value": 0, "description": "Off"},
                        {"value": 1, "description": "Low"},
                        {"value": 3, "description": "High"},
                    ],
                },
            ],
            "actions": [
                {
                    "iid": 1,
                    "type": "urn:miot-spec-v2:action:stop-working:00002825:yeelink-v6:2",
                    "description": "Stop Working",
                    "in": [0],
                    "out": [],
                }
            ],
        },
    ],
}


@pytest.mark.parametrize("model", ["yeelink.bhf_light.v5", "yeelink.bhf_light.v6"])
def test_device_customizes_has_non_optimistic(model):
    custom = DEVICE_CUSTOMIZES.get(model)
    assert custom is not None
    assert custom.get("non_optimistic") is True
    assert custom.get("select_properties") == "heat_mode,cold_mode,vent_mode"


def test_miio_props_does_not_contain_unreadable_gear_properties(hass):
    spec = MiotSpec(hass, V6_SPEC_DICT)
    helper = Miio2MiotHelper.from_model(hass, "yeelink.bhf_light.v6", spec)
    assert helper is not None
    assert "warmwind_gear" not in helper.miio_props
    assert "coolwind_gear" not in helper.miio_props
    assert "venting_gear" not in helper.miio_props
    assert "bh_mode" in helper.miio_props
    assert "fan_speed_idx" in helper.miio_props


def test_v5_miio_props_does_not_contain_unreadable_gear_properties(hass):
    spec = MiotSpec(hass, V6_SPEC_DICT)
    helper = Miio2MiotHelper.from_model(hass, "yeelink.bhf_light.v5", spec)
    assert helper is not None
    assert "warmwind_gear" not in helper.miio_props
    assert "coolwind_gear" not in helper.miio_props
    assert "venting_gear" not in helper.miio_props
    assert "bh_mode" in helper.miio_props
    assert "fan_speed_idx" in helper.miio_props


@pytest.mark.parametrize("model", ["yeelink.bhf_light.v5", "yeelink.bhf_light.v6"])
async def test_decimal_gear_decoding_all_matrix_states(hass, model):
    """Verify that decimal gear decoding correctly maps composite states and Idle state for v5 and v6."""
    spec = MiotSpec(hass, V6_SPEC_DICT)
    helper = Miio2MiotHelper.from_model(hass, model, spec)
    assert helper is not None

    mapping = {
        "heat_mode": {"did": "test", "siid": 3, "piid": 111},
        "cold_mode": {"did": "test", "siid": 3, "piid": 112},
        "vent_mode": {"did": "test", "siid": 3, "piid": 113},
    }

    class MockDev:
        def __init__(self, props):
            self.props = props
            self.mapping = mapping

        async def async_get_prop(self, keys, max_properties=None):
            return [self.props.get(k) for k in keys]

    # 1. Baseline Idle: bh_off, fan_speed_idx=0 -> heat=0, cold=0, vent=0
    res_idle = await helper.async_get_miot_props(MockDev({"bh_mode": "bh_off", "fan_speed_idx": 0}))
    res_map = {f"{r['siid']}.{r['piid']}": r["value"] for r in res_idle}
    assert res_map.get("3.111") == 0
    assert res_map.get("3.112") == 0
    assert res_map.get("3.113") == 0

    # 2. Composite Air Low + Vent High: coolwind|venting, fan_speed_idx=13 -> heat=0, cold=1, vent=3
    res_airlow = await helper.async_get_miot_props(MockDev({"bh_mode": "coolwind|venting", "fan_speed_idx": 13}))
    res_map = {f"{r['siid']}.{r['piid']}": r["value"] for r in res_airlow}
    assert res_map.get("3.111") == 0
    assert res_map.get("3.112") == 1  # cold Low
    assert res_map.get("3.113") == 3  # vent High

    # 3. Composite Air High + Vent Low: coolwind|venting, fan_speed_idx=31 -> heat=0, cold=3, vent=1
    res_airhigh = await helper.async_get_miot_props(MockDev({"bh_mode": "coolwind|venting", "fan_speed_idx": 31}))
    res_map = {f"{r['siid']}.{r['piid']}": r["value"] for r in res_airhigh}
    assert res_map.get("3.111") == 0
    assert res_map.get("3.112") == 3  # cold High
    assert res_map.get("3.113") == 1  # vent Low

    # 4. Composite Warm Low + Vent High: warmwind|venting, fan_speed_idx=103 -> heat=1, cold=0, vent=3
    res_warmlow = await helper.async_get_miot_props(MockDev({"bh_mode": "warmwind|venting", "fan_speed_idx": 103}))
    res_map = {f"{r['siid']}.{r['piid']}": r["value"] for r in res_warmlow}
    assert res_map.get("3.111") == 1  # heat Low
    assert res_map.get("3.112") == 0
    assert res_map.get("3.113") == 3  # vent High

    # 5. Composite Warm High + Vent Low: warmwind|venting, fan_speed_idx=201 -> heat=2, cold=0, vent=1
    res_warmhigh = await helper.async_get_miot_props(MockDev({"bh_mode": "warmwind|venting", "fan_speed_idx": 201}))
    res_map = {f"{r['siid']}.{r['piid']}": r["value"] for r in res_warmhigh}
    assert res_map.get("3.111") == 2  # heat High
    assert res_map.get("3.112") == 0
    assert res_map.get("3.113") == 1  # vent Low


@pytest.mark.parametrize("model", ["yeelink.bhf_light.v5", "yeelink.bhf_light.v6"])
async def test_select_property_setters(hass, model):
    """Verify that select property setters generate correct targeted setter payloads for v5 and v6."""
    spec = MiotSpec(hass, V6_SPEC_DICT)
    helper = Miio2MiotHelper.from_model(hass, model, spec)
    assert helper is not None

    sent_commands = []

    class MockDev:
        async def async_send(self, method, params):
            sent_commands.append((method, params))
            return ["ok"]

    mock_dev = MockDev()

    # Heat mode (3.111)
    helper.miio_props_values = {"bh_mode": "bh_off"}
    await helper.async_set_property(mock_dev, 3, 111, 1)
    assert sent_commands[-1] == ("set_bh_mode", ["warmwind", 1])

    await helper.async_set_property(mock_dev, 3, 111, 2)
    assert sent_commands[-1] == ("set_bh_mode", ["warmwind", 2])

    helper.miio_props_values = {"bh_mode": "warmwind|venting"}
    await helper.async_set_property(mock_dev, 3, 111, 0)
    assert sent_commands[-1] == ("set_bh_mode", ["windoff"])

    # Cold mode (3.112)
    helper.miio_props_values = {"bh_mode": "bh_off"}
    await helper.async_set_property(mock_dev, 3, 112, 1)
    assert sent_commands[-1] == ("set_bh_mode", ["coolwind", 1])

    await helper.async_set_property(mock_dev, 3, 112, 3)
    assert sent_commands[-1] == ("set_bh_mode", ["coolwind", 3])

    helper.miio_props_values = {"bh_mode": "coolwind|venting"}
    await helper.async_set_property(mock_dev, 3, 112, 0)
    assert sent_commands[-1] == ("set_bh_mode", ["windoff"])

    # Vent mode (3.113)
    helper.miio_props_values = {"bh_mode": "bh_off"}
    await helper.async_set_property(mock_dev, 3, 113, 1)
    assert sent_commands[-1] == ("set_bh_mode", ["venting", 1])

    await helper.async_set_property(mock_dev, 3, 113, 3)
    assert sent_commands[-1] == ("set_bh_mode", ["venting", 3])

    helper.miio_props_values = {"bh_mode": "coolwind|venting"}
    await helper.async_set_property(mock_dev, 3, 113, 0)
    assert sent_commands[-1] == ("set_bh_mode", ["ventingoff"])


async def test_non_optimistic_async_write_does_not_dispatch_on_success(make_device, hass):
    spec = MiotSpec(hass, V6_SPEC_DICT)
    device = make_device(spec, model="yeelink.bhf_light.v6")

    assert device.custom_config_bool("non_optimistic") is True

    dispatched = []
    device.add_listener(lambda data, only_info=False: dispatched.append(data))

    # Mock encode to simulate a command payload
    device.encode = MagicMock(return_value={
        "method": "set_properties",
        "params": [{"did": "test-device", "siid": 3, "piid": 1, "value": 0}],
    })
    device.async_set_properties = AsyncMock(return_value=[{"code": 0}])
    device.update_main_status = AsyncMock()

    payload = {"ptc_bath_heater.mode": "Idle"}
    await device.async_write(payload)

    # In non_optimistic mode, optimistic payload must NOT be dispatched directly
    assert payload not in dispatched
    # update_main_status must be called to fetch real confirmed readback
    device.update_main_status.assert_awaited_once()


async def test_write_failure_still_triggers_readback_without_optimistic_dispatch(make_device, hass):
    spec = MiotSpec(hass, V6_SPEC_DICT)
    device = make_device(spec, model="yeelink.bhf_light.v6")

    dispatched = []
    device.add_listener(lambda data, only_info=False: dispatched.append(data))

    device.encode = MagicMock(return_value={
        "method": "set_properties",
        "params": [{"did": "test-device", "siid": 3, "piid": 1, "value": 0}],
    })
    device.async_set_properties = AsyncMock(side_effect=DeviceException("Timeout"))
    device.update_main_status = AsyncMock()

    payload = {"ptc_bath_heater.mode": "Idle"}
    with pytest.raises(DeviceException):
        await device.async_write(payload)

    # Optimistic payload must NOT be dispatched on failure
    assert payload not in dispatched
    # Forced readback confirmation must still run in finally block
    device.update_main_status.assert_awaited_once()
