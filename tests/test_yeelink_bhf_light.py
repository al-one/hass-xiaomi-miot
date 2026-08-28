import asyncio
import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest

from custom_components.xiaomi_miot.core.device_customizes import DEVICE_CUSTOMIZES
from custom_components.xiaomi_miot.core.coordinator import DataCoordinator
from custom_components.xiaomi_miot.core.miio2miot import Miio2MiotHelper
from custom_components.xiaomi_miot.core.miot_spec import MiotSpec
from custom_components.xiaomi_miot.core.utils import DeviceException

EXTEND_SPECS_FILE = (
    Path(__file__).parent.parent
    / "custom_components"
    / "xiaomi_miot"
    / "core"
    / "miot_specs_extend.json"
)

V6_RAW_CLOUD_SPEC = {
    "urn": "urn:miot-spec-v2:device:bath-heater:0000A028:yeelink-v6:2",
    "services": [
        {
            "iid": 1,
            "type": "urn:miot-spec-v2:service:device-information:00007801:yeelink-v6:2",
            "description": "Device Information",
            "properties": [
                {
                    "iid": 1,
                    "type": "urn:miot-spec-v2:property:manufacturer:00000001:yeelink-v6:2",
                    "format": "string",
                    "access": ["read"],
                },
                {
                    "iid": 2,
                    "type": "urn:miot-spec-v2:property:model:00000002:yeelink-v6:2",
                    "format": "string",
                    "access": ["read"],
                },
            ],
        },
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
                    "iid": 2,
                    "type": "urn:miot-spec-v2:property:target-temperature:00000021:yeelink-v6:2",
                    "description": "Target Temperature",
                    "format": "uint8",
                    "access": ["read", "write", "notify"],
                    "value-range": [16, 35, 1],
                },
                {
                    "iid": 3,
                    "type": "urn:miot-spec-v2:property:temperature:00000020:yeelink-v6:2",
                    "description": "Temperature",
                    "format": "float",
                    "access": ["read", "notify"],
                    "unit": "celsius",
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


def get_v6_extended_spec(hass) -> MiotSpec:
    """Create a MiotSpec from the raw unextended cloud spec and apply production miot_specs_extend.json."""
    spec = MiotSpec(hass, copy.deepcopy(V6_RAW_CLOUD_SPEC))
    with EXTEND_SPECS_FILE.open(encoding="utf-8") as f:
        extended_specs = json.load(f)
    v6_extend = extended_specs.get("yeelink.bhf_light.v6") or []
    spec.extend_specs(services=v6_extend)
    return spec


@pytest.mark.parametrize("model", ["yeelink.bhf_light.v5", "yeelink.bhf_light.v6"])
def test_device_customizes_has_non_optimistic(model):
    custom = DEVICE_CUSTOMIZES.get(model)
    assert custom is not None
    assert custom.get("non_optimistic") is True
    assert custom.get("select_properties") == "heat_mode,cold_mode,vent_mode"


def test_miio_props_does_not_contain_unreadable_gear_properties(hass):
    spec = get_v6_extended_spec(hass)
    helper = Miio2MiotHelper.from_model(hass, "yeelink.bhf_light.v6", spec)
    assert helper is not None
    assert "warmwind_gear" not in helper.miio_props
    assert "coolwind_gear" not in helper.miio_props
    assert "venting_gear" not in helper.miio_props
    assert "heating" not in helper.miio_props
    assert "blow" not in helper.miio_props
    assert "ventilation" not in helper.miio_props
    assert "bh_mode" in helper.miio_props
    assert "fan_speed_idx" in helper.miio_props


def test_v5_miio_props_does_not_contain_unreadable_gear_properties(hass):
    spec = get_v6_extended_spec(hass)
    helper = Miio2MiotHelper.from_model(hass, "yeelink.bhf_light.v5", spec)
    assert helper is not None
    assert "warmwind_gear" not in helper.miio_props
    assert "coolwind_gear" not in helper.miio_props
    assert "venting_gear" not in helper.miio_props
    assert "heating" not in helper.miio_props
    assert "blow" not in helper.miio_props
    assert "ventilation" not in helper.miio_props
    assert "bh_mode" in helper.miio_props
    assert "fan_speed_idx" in helper.miio_props

async def test_decimal_gear_decoding_all_matrix_states(hass):
    """Verify that decimal gear decoding correctly maps composite states and Idle state for v6."""
    spec = get_v6_extended_spec(hass)
    helper = Miio2MiotHelper.from_model(hass, "yeelink.bhf_light.v6", spec)
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
    spec = get_v6_extended_spec(hass)
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


def test_v6_spec_extension_in_specs_extend_json(hass):
    """Verify that miot_specs_extend.json contains v6 synthetic switches with exact IID, type, format, and access."""
    with EXTEND_SPECS_FILE.open(encoding="utf-8") as f:
        extended = json.load(f)
    v6_extend = extended.get("yeelink.bhf_light.v6")
    assert v6_extend is not None, "yeelink.bhf_light.v6 missing from miot_specs_extend.json"
    v6_service3 = next((s for s in v6_extend if s.get("iid") == 3), None)
    assert v6_service3 is not None, "Service 3 missing from yeelink.bhf_light.v6 extension"

    props = {p["iid"]: p for p in v6_service3.get("properties", [])}

    # Verify IID 114 (Heating)
    assert 114 in props
    p114 = props[114]
    assert p114.get("type") == "urn:miot-spec-v2:property:heating"
    assert p114.get("description") == "Heating"
    assert p114.get("format") == "bool"
    assert p114.get("access") == ["read", "write"]

    # Verify IID 115 (Blow)
    assert 115 in props
    p115 = props[115]
    assert p115.get("type") == "urn:miot-spec-v2:property:blow"
    assert p115.get("description") == "Blow"
    assert p115.get("format") == "bool"
    assert p115.get("access") == ["read", "write"]

    # Verify IID 116 (Ventilation)
    assert 116 in props
    p116 = props[116]
    assert p116.get("type") == "urn:miot-spec-v2:property:ventilation"
    assert p116.get("description") == "Ventilation"
    assert p116.get("format") == "bool"
    assert p116.get("access") == ["read", "write"]

    # Verify properties after dynamic extension of cloud spec
    spec = get_v6_extended_spec(hass)
    heating_prop = spec.services[3].properties.get(114)
    assert heating_prop is not None
    assert heating_prop.name == "heating"
    assert heating_prop.format == "bool"
    assert heating_prop.readable is True
    assert heating_prop.writeable is True

    blow_prop = spec.services[3].properties.get(115)
    assert blow_prop is not None
    assert blow_prop.name == "blow"
    assert blow_prop.format == "bool"
    assert blow_prop.readable is True
    assert blow_prop.writeable is True

    vent_prop = spec.services[3].properties.get(116)
    assert vent_prop is not None
    assert vent_prop.name == "ventilation"
    assert vent_prop.format == "bool"
    assert vent_prop.readable is True
    assert vent_prop.writeable is True


def test_v6_converters_include_switch_properties(make_device, hass):
    """Verify that device converters for v6 include heating, blow, and ventilation switches."""
    spec = get_v6_extended_spec(hass)
    device = make_device(spec, model="yeelink.bhf_light.v6")
    switch_converters = [c for c in device.converters if c.domain == "switch"]
    switch_prop_names = [c.prop.name for c in switch_converters]
    assert "heating" in switch_prop_names
    assert "blow" in switch_prop_names
    assert "ventilation" in switch_prop_names


@pytest.mark.parametrize(
    "bh_mode,expected_heating,expected_blow,expected_vent",
    [
        ("bh_off", False, False, False),
        ("warmwind", True, False, False),
        ("coolwind", False, True, False),
        ("venting", False, False, True),
        ("warmwind|venting", True, False, True),
        ("coolwind|venting", False, True, True),
        ("drying", False, False, False),
        ("defog", False, False, False),
        ("fastwarm", False, False, False),
        ("fastdefog", False, False, False),
    ],
)
async def test_v6_switch_state_decoding(hass, bh_mode, expected_heating, expected_blow, expected_vent):
    """Verify that v6 switch states are decoded correctly from bh_mode for single and composite states."""
    spec = get_v6_extended_spec(hass)
    helper = Miio2MiotHelper.from_model(hass, "yeelink.bhf_light.v6", spec)
    assert helper is not None

    mapping = {
        "heating": {"did": "test", "siid": 3, "piid": 114},
        "blow": {"did": "test", "siid": 3, "piid": 115},
        "ventilation": {"did": "test", "siid": 3, "piid": 116},
    }

    class MockDev:
        def __init__(self, props):
            self.props = props
            self.mapping = mapping

        async def async_get_prop(self, keys, max_properties=None):
            return [self.props.get(k) for k in keys]

    res = await helper.async_get_miot_props(MockDev({"bh_mode": bh_mode, "fan_speed_idx": 0}))
    res_map = {f"{r['siid']}.{r['piid']}": r["value"] for r in res}
    assert res_map.get("3.114") is expected_heating
    assert res_map.get("3.115") is expected_blow
    assert res_map.get("3.116") is expected_vent


async def test_v6_switch_property_setters(hass):
    """Verify that v6 switch property setters generate correct targeted set_bh_mode commands."""
    spec = get_v6_extended_spec(hass)
    helper = Miio2MiotHelper.from_model(hass, "yeelink.bhf_light.v6", spec)
    assert helper is not None

    sent_commands = []

    class MockDev:
        async def async_send(self, method, params):
            sent_commands.append((method, params))
            return ["ok"]

    mock_dev = MockDev()

    # Heating switch (3.114): on -> warmwind, off -> windoff
    helper.miio_props_values = {"bh_mode": "bh_off"}
    await helper.async_set_property(mock_dev, 3, 114, True)
    assert sent_commands[-1] == ("set_bh_mode", ["warmwind"])

    helper.miio_props_values = {"bh_mode": "warmwind|venting"}
    await helper.async_set_property(mock_dev, 3, 114, False)
    assert sent_commands[-1] == ("set_bh_mode", ["windoff"])

    # Blow switch (3.115): on -> coolwind, off -> windoff
    helper.miio_props_values = {"bh_mode": "bh_off"}
    await helper.async_set_property(mock_dev, 3, 115, True)
    assert sent_commands[-1] == ("set_bh_mode", ["coolwind"])

    helper.miio_props_values = {"bh_mode": "coolwind|venting"}
    await helper.async_set_property(mock_dev, 3, 115, False)
    assert sent_commands[-1] == ("set_bh_mode", ["windoff"])

    # Ventilation switch (3.116): on -> venting, off -> ventingoff
    helper.miio_props_values = {"bh_mode": "bh_off"}
    await helper.async_set_property(mock_dev, 3, 116, True)
    assert sent_commands[-1] == ("set_bh_mode", ["venting"])

    helper.miio_props_values = {"bh_mode": "coolwind|venting"}
    await helper.async_set_property(mock_dev, 3, 116, False)
    assert sent_commands[-1] == ("set_bh_mode", ["ventingoff"])

async def test_non_optimistic_async_write_does_not_dispatch_on_success(make_device, hass):
    spec = get_v6_extended_spec(hass)
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
    device.update_main_status.assert_awaited_once_with(immediate=True)


async def test_write_failure_still_triggers_readback_without_optimistic_dispatch(make_device, hass):
    spec = get_v6_extended_spec(hass)
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
    # Confirmed readback must still run in the finally block.
    device.update_main_status.assert_awaited_once_with(immediate=True)



async def test_non_optimistic_action_confirms_without_optimistic_dispatch(make_device, hass):
    spec = get_v6_extended_spec(hass)
    device = make_device(spec, model="yeelink.bhf_light.v6")
    dispatched = []
    device.add_listener(lambda data, only_info=False: dispatched.append(data))
    device.encode = MagicMock(return_value={
        "method": "action",
        "param": {"siid": 3, "aiid": 1},
    })
    device.async_call_action = AsyncMock(return_value=MagicMock(is_success=True))
    device.update_main_status = AsyncMock()

    payload = {"ptc_bath_heater.stop_working": True}
    await device.async_write(payload)

    assert payload not in dispatched
    device.update_main_status.assert_awaited_once_with(immediate=True)


async def test_non_optimistic_action_failure_still_confirms_readback(make_device, hass):
    spec = get_v6_extended_spec(hass)
    device = make_device(spec, model="yeelink.bhf_light.v6")
    device.encode = MagicMock(return_value={
        "method": "action",
        "param": {"siid": 3, "aiid": 1},
    })
    device.async_call_action = AsyncMock(side_effect=DeviceException("Timeout"))
    device.update_main_status = AsyncMock()

    with pytest.raises(DeviceException, match="Timeout"):
        await device.async_write({"ptc_bath_heater.stop_working": True})

    device.update_main_status.assert_awaited_once_with(immediate=True)

async def test_concurrent_non_optimistic_writes_each_wait_for_fresh_poll(make_device, hass):
    spec = get_v6_extended_spec(hass)
    device = make_device(spec, model="yeelink.bhf_light.v6")
    device.entry.entry = MagicMock()

    first_poll_started = asyncio.Event()
    release_first_poll = asyncio.Event()
    first_poll_finished = asyncio.Event()
    second_write_finished = asyncio.Event()
    poll_count = 0
    write_count = 0

    async def update_method():
        nonlocal poll_count
        poll_count += 1
        if poll_count == 1:
            first_poll_started.set()
            await release_first_poll.wait()
            first_poll_finished.set()
        else:
            assert first_poll_finished.is_set()
        return {}

    async def set_properties(_):
        nonlocal write_count
        write_count += 1
        if write_count == 2:
            second_write_finished.set()
        return [{"code": 0}]

    coordinator = DataCoordinator(device, update_method)
    device.coordinators = [coordinator]
    device.main_coordinators = [coordinator]
    device.encode = MagicMock(return_value={
        "method": "set_properties",
        "params": [{"did": "test-device", "siid": 3, "piid": 1, "value": 0}],
    })
    device.async_set_properties = AsyncMock(side_effect=set_properties)

    try:
        first_write = hass.async_create_task(
            device.async_write({"ptc_bath_heater.mode": "Heat"}),
            "first bath heater write",
        )
        await first_poll_started.wait()
        second_write = hass.async_create_task(
            device.async_write({"ptc_bath_heater.mode": "Fan"}),
            "second bath heater write",
        )
        await second_write_finished.wait()
        release_first_poll.set()
        await asyncio.gather(first_write, second_write)
    finally:
        await coordinator.async_shutdown()

    assert poll_count == 2


async def test_nonzero_write_result_raises_after_confirmed_readback(make_device, hass):
    spec = get_v6_extended_spec(hass)
    device = make_device(spec, model="yeelink.bhf_light.v6")
    device.encode = MagicMock(return_value={
        "method": "set_properties",
        "params": [{"did": "test-device", "siid": 3, "piid": 1, "value": 0}],
    })
    device.async_set_properties = AsyncMock(return_value=[{
        "code": -1,
        "siid": 3,
        "piid": 1,
    }])
    device.update_main_status = AsyncMock()

    with pytest.raises(DeviceException, match="-1"):
        await device.async_write({"ptc_bath_heater.mode": "Idle"})

    device.update_main_status.assert_awaited_once_with(immediate=True)


async def test_non_optimistic_update_status_refreshes_once(make_device, hass):
    spec = get_v6_extended_spec(hass)
    device = make_device(spec, model="yeelink.bhf_light.v6")
    device.encode = MagicMock(return_value={"method": "update_status"})
    device.update_main_status = AsyncMock()

    await device.async_write({"info": True})

    device.update_main_status.assert_awaited_once()
