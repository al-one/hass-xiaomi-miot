import asyncio
import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.xiaomi_miot.climate import ClimateEntity
from custom_components.xiaomi_miot.core.converters import MiotClimateConv
from custom_components.xiaomi_miot.core.coordinator import DataCoordinator
from custom_components.xiaomi_miot.core.device_customizes import DEVICE_CUSTOMIZES
from custom_components.xiaomi_miot.core.miio2miot import Miio2MiotHelper
from custom_components.xiaomi_miot.core.miot_spec import MiotResult, MiotSpec
from custom_components.xiaomi_miot.core.utils import DeviceException

EXTEND_SPECS_FILE = (
    Path(__file__).parent.parent
    / "custom_components"
    / "xiaomi_miot"
    / "core"
    / "miot_specs_extend.json"
)

V6_RAW_CLOUD_SPEC = {
    "type": "urn:miot-spec-v2:device:bath-heater:0000A028:yeelink-v6:2",
    "description": "Bath Heater",
    "services": [
        {
            "iid": 1,
            "type": "urn:miot-spec-v2:service:device-information:00007801:yeelink-v6:1",
            "description": "Device Information",
            "properties": [
                {
                    "iid": 1,
                    "type": "urn:miot-spec-v2:property:manufacturer:00000001:yeelink-v6:1",
                    "description": "Device Manufacturer",
                    "format": "string",
                    "access": ["read"],
                },
                {
                    "iid": 2,
                    "type": "urn:miot-spec-v2:property:model:00000002:yeelink-v6:1",
                    "description": "Device Model",
                    "format": "string",
                    "access": ["read"],
                },
                {
                    "iid": 3,
                    "type": "urn:miot-spec-v2:property:serial-number:00000003:yeelink-v6:1",
                    "description": "Device Serial Number",
                    "format": "string",
                    "access": ["read"],
                },
                {
                    "iid": 4,
                    "type": "urn:miot-spec-v2:property:firmware-revision:00000005:yeelink-v6:1",
                    "description": "Current Firmware Version",
                    "format": "string",
                    "access": ["read"],
                },
            ],
        },
        {
            "iid": 2,
            "type": "urn:miot-spec-v2:service:light:00007802:yeelink-v6:1",
            "description": "Light",
            "properties": [
                {
                    "iid": 1,
                    "type": "urn:miot-spec-v2:property:on:00000006:yeelink-v6:1",
                    "description": "Switch Status",
                    "format": "bool",
                    "access": ["read", "write", "notify"],
                    "unit": "none",
                },
                {
                    "iid": 2,
                    "type": "urn:miot-spec-v2:property:mode:00000008:yeelink-v6:1",
                    "description": "Mode",
                    "format": "uint8",
                    "access": ["read", "write", "notify"],
                    "unit": "none",
                    "value-list": [
                        {"value": 0, "description": "Day"},
                        {"value": 1, "description": "Night"},
                    ],
                },
                {
                    "iid": 3,
                    "type": "urn:miot-spec-v2:property:brightness:0000000D:yeelink-v6:1",
                    "description": "Brightness",
                    "format": "uint8",
                    "access": ["read", "write", "notify"],
                    "unit": "percentage",
                    "value-range": [1, 100, 1],
                },
            ],
        },
        {
            "iid": 3,
            "type": "urn:miot-spec-v2:service:ptc-bath-heater:0000783B:yeelink-v6:1",
            "description": "PTC Bath Heater",
            "properties": [
                {
                    "iid": 1,
                    "type": "urn:miot-spec-v2:property:mode:00000008:yeelink-v6:1",
                    "description": "Mode",
                    "format": "uint8",
                    "access": ["read", "write", "notify"],
                    "unit": "none",
                    "value-list": [
                        {"value": 0, "description": "Idle"},
                        {"value": 1, "description": "Fan"},
                        {"value": 2, "description": "Heat"},
                        {"value": 3, "description": "Ventilate"},
                        {"value": 4, "description": "Dry"},
                    ],
                },
                {
                    "iid": 2,
                    "type": "urn:miot-spec-v2:property:target-temperature:00000021:yeelink-v6:1",
                    "description": "Target Temperature",
                    "format": "uint8",
                    "access": ["read", "write", "notify"],
                    "unit": "celsius",
                    "value-range": [25, 45, 1],
                },
                {
                    "iid": 3,
                    "type": "urn:miot-spec-v2:property:temperature:00000020:yeelink-v6:1",
                    "description": "Temperature",
                    "format": "uint8",
                    "access": ["read", "notify"],
                    "unit": "celsius",
                    "value-range": [0, 50, 1],
                },
            ],
            "actions": [
                {
                    "iid": 1,
                    "type": "urn:miot-spec-v2:action:stop-working:00002825:yeelink-v6:1",
                    "description": "Stop Working",
                    "in": [],
                    "out": [],
                }
            ],
        },
        {
            "iid": 4,
            "type": "urn:yeelink-spec:service:notify:00007801:yeelink-v6:1",
            "description": "notify",
            "events": [
                {
                    "iid": 1,
                    "type": "urn:yeelink-spec:event:fan-error:00005001:yeelink-v6:1",
                    "description": "fan-error",
                    "arguments": [],
                },
                {
                    "iid": 2,
                    "type": "urn:yeelink-spec:event:venting-keep:00005002:yeelink-v6:1",
                    "description": "venting-keep",
                    "arguments": [],
                },
                {
                    "iid": 3,
                    "type": "urn:yeelink-spec:event:overtime:00005003:yeelink-v6:1",
                    "description": "overtime",
                    "arguments": [],
                },
                {
                    "iid": 4,
                    "type": "urn:yeelink-spec:event:delayoff:00005004:yeelink-v6:1",
                    "description": "delayoff",
                    "arguments": [],
                },
                {
                    "iid": 5,
                    "type": "urn:yeelink-spec:event:over-temperature:00005005:yeelink-v6:1",
                    "description": "over-temperature",
                    "arguments": [],
                },
            ],
        },
    ],
}


def test_v6_raw_cloud_fixture_matches_published_v2():
    assert V6_RAW_CLOUD_SPEC["type"] == (
        "urn:miot-spec-v2:device:bath-heater:0000A028:yeelink-v6:2"
    )
    assert "urn" not in V6_RAW_CLOUD_SPEC
    services = {service["iid"]: service for service in V6_RAW_CLOUD_SPEC["services"]}
    assert set(services) == {1, 2, 3, 4}
    heater = services[3]
    assert heater["type"] == (
        "urn:miot-spec-v2:service:ptc-bath-heater:0000783B:yeelink-v6:1"
    )
    properties = {prop["iid"]: prop for prop in heater["properties"]}
    assert properties[1]["value-list"] == [
        {"value": 0, "description": "Idle"},
        {"value": 1, "description": "Fan"},
        {"value": 2, "description": "Heat"},
        {"value": 3, "description": "Ventilate"},
        {"value": 4, "description": "Dry"},
    ]
    assert properties[2]["value-range"] == [25, 45, 1]
    assert properties[3]["format"] == "uint8"
    assert properties[3]["value-range"] == [0, 50, 1]
    assert heater["actions"][0]["in"] == []


def get_v6_extended_spec(hass, version=2) -> MiotSpec:
    """Apply the production v6 extension to an official unextended cloud spec."""
    raw_spec = copy.deepcopy(V6_RAW_CLOUD_SPEC)
    raw_spec["type"] = (
        f"urn:miot-spec-v2:device:bath-heater:0000A028:yeelink-v6:{version}"
    )
    spec = MiotSpec(hass, raw_spec)
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



def test_v5_fixture_matches_published_instance(load_miot_spec):
    spec = load_miot_spec("yeelink.bhf_light.v5.json")
    assert spec.type == "urn:miot-spec-v2:device:bath-heater:0000A028:yeelink-v5:1"
    heater = spec.services[3]
    assert heater.name == "ptc_bath_heater"
    assert heater.properties[1].value_list[4]["description"] == "Idle"
    assert heater.actions[1].name == "stop_working"

def test_v5_miio_props_does_not_contain_unreadable_gear_properties(
    hass, load_miot_spec,
):
    spec = load_miot_spec("yeelink.bhf_light.v5.json")
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

    # 6. Warm with stale Air High digit: Air stays Off because coolwind is inactive
    res_stale_air = await helper.async_get_miot_props(
        MockDev({"bh_mode": "warmwind|venting", "fan_speed_idx": 131})
    )
    res_map = {f"{r['siid']}.{r['piid']}": r["value"] for r in res_stale_air}
    assert res_map.get("3.111") == 1
    assert res_map.get("3.112") == 0
    assert res_map.get("3.113") == 1

    # 7. Air with stale Warm Low digit: Heat stays Off because warmwind is inactive
    res_stale_warm = await helper.async_get_miot_props(
        MockDev({"bh_mode": "coolwind|venting", "fan_speed_idx": 131})
    )
    res_map = {f"{r['siid']}.{r['piid']}": r["value"] for r in res_stale_warm}
    assert res_map.get("3.111") == 0
    assert res_map.get("3.112") == 3
    assert res_map.get("3.113") == 1

    # 8. Similar substrings are not valid bh_mode tokens
    res_unknown_token = await helper.async_get_miot_props(
        MockDev({"bh_mode": "warmwind_extra|venting", "fan_speed_idx": 103})
    )
    res_map = {f"{r['siid']}.{r['piid']}": r["value"] for r in res_unknown_token}
    assert res_map.get("3.111") == 0
    assert res_map.get("3.112") == 0
    assert res_map.get("3.113") == 3

    # 9. An active token without a readable gear stays unknown rather than becoming Off
    for bh_mode, piid in [
        ("warmwind", 111),
        ("coolwind", 112),
        ("venting", 113),
    ]:
        res_missing_gear = await helper.async_get_miot_props(
            MockDev({"bh_mode": bh_mode, "fan_speed_idx": None})
        )
        res_map = {f"{r['siid']}.{r['piid']}": r["value"] for r in res_missing_gear}
        assert res_map.get(f"3.{piid}") is None

async def test_v6_select_property_setters(hass):
    """Verify v6 selector payloads against its extended MIOT spec."""
    spec = get_v6_extended_spec(hass)
    helper = Miio2MiotHelper.from_model(hass, "yeelink.bhf_light.v6", spec)
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


async def test_v5_switch_property_setters(hass, load_miot_spec):
    """Verify v5 switch payloads against its published MIOT properties."""
    spec = load_miot_spec("yeelink.bhf_light.v5.json")
    helper = Miio2MiotHelper.from_model(hass, "yeelink.bhf_light.v5", spec)
    assert helper is not None
    sent_commands = []

    class MockDev:
        async def async_send(self, method, params):
            sent_commands.append((method, params))
            return ["ok"]

    mock_dev = MockDev()
    for piid, on, off in [
        (2, "warmwind", "windoff"),
        (3, "coolwind", "windoff"),
        (4, "venting", "ventingoff"),
    ]:
        await helper.async_set_property(mock_dev, 3, piid, True)
        assert sent_commands[-1] == ("set_bh_mode", [on])
        await helper.async_set_property(mock_dev, 3, piid, False)
        assert sent_commands[-1] == ("set_bh_mode", [off])


async def test_v5_select_property_setters(hass, load_miot_spec):
    """Verify v5 synthetic selector payloads against its extended official spec."""
    spec = load_miot_spec("yeelink.bhf_light.v5.json")
    with EXTEND_SPECS_FILE.open(encoding="utf-8") as file:
        extended_specs = json.load(file)
    spec.extend_specs(services=extended_specs.get("yeelink.bhf_light.v5") or [])
    helper = Miio2MiotHelper.from_model(hass, "yeelink.bhf_light.v5", spec)
    assert helper is not None
    sent_commands = []

    class MockDev:
        async def async_send(self, method, params):
            sent_commands.append((method, params))
            return ["ok"]

    mock_dev = MockDev()
    for piid, mode, levels, off in [
        (111, "warmwind", [1, 2], "windoff"),
        (112, "coolwind", [1, 3], "windoff"),
        (113, "venting", [1, 3], "ventingoff"),
    ]:
        for level in levels:
            await helper.async_set_property(mock_dev, 3, piid, level)
            assert sent_commands[-1] == ("set_bh_mode", [mode, level])
        await helper.async_set_property(mock_dev, 3, piid, 0)
        assert sent_commands[-1] == ("set_bh_mode", [off])


async def test_v5_select_readback_gates_stale_inactive_gears(hass, load_miot_spec):
    """Verify inactive decimal digits do not activate v5 synthetic selectors."""
    spec = load_miot_spec("yeelink.bhf_light.v5.json")
    with EXTEND_SPECS_FILE.open(encoding="utf-8") as file:
        extended_specs = json.load(file)
    spec.extend_specs(services=extended_specs.get("yeelink.bhf_light.v5") or [])
    helper = Miio2MiotHelper.from_model(hass, "yeelink.bhf_light.v5", spec)
    assert helper is not None
    mapping = {
        "heat_mode": {"did": "test", "siid": 3, "piid": 111},
        "cold_mode": {"did": "test", "siid": 3, "piid": 112},
        "vent_mode": {"did": "test", "siid": 3, "piid": 113},
    }

    class MockDev:

        async def async_get_prop(self, keys, max_properties=None):
            values = {"bh_mode": "warmwind|venting", "fan_speed_idx": 131}
            return [values.get(key) for key in keys]

    mock_device = MockDev()
    mock_device.mapping = mapping

    results = await helper.async_get_miot_props(mock_device)
    states = {result["piid"]: result["value"] for result in results}
    assert states[111] == 1
    assert states[112] == 0
    assert states[113] == 1


@pytest.mark.parametrize("version", [1, 2])
def test_v6_spec_extension_in_specs_extend_json(hass, version):
    """Verify exact synthetic switch metadata against both published v6 revisions."""
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
    spec = get_v6_extended_spec(hass, version)
    assert spec.type == (
        f"urn:miot-spec-v2:device:bath-heater:0000A028:yeelink-v6:{version}"
    )
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
        ("warmwind_extra", False, False, False),
        ("coolwind_backup", False, False, False),
        ("venting-extra", False, False, False),
        (None, None, None, None),
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
    device.async_call_action = AsyncMock(
        return_value=MiotResult({}, code=-1, error="Device unavailable")
    )
    device.update_main_status = AsyncMock()

    with pytest.raises(DeviceException, match="Device unavailable"):
        await device.async_write({"ptc_bath_heater.stop_working": True})

    device.update_main_status.assert_awaited_once_with(immediate=True)

async def test_concurrent_non_optimistic_writes_each_wait_for_fresh_poll(make_device, hass):
    spec = get_v6_extended_spec(hass)
    device = make_device(spec, model="yeelink.bhf_light.v6")
    device.entry.entry = MagicMock()

    first_poll_started = asyncio.Event()
    first_poll_finished = asyncio.Event()
    release_first_poll = asyncio.Event()
    second_poll_started = asyncio.Event()
    second_poll_finished = asyncio.Event()
    release_second_poll = asyncio.Event()
    second_write_finished = asyncio.Event()
    overlap_detected = False
    poll_count = 0
    write_count = 0

    async def update_method():
        nonlocal overlap_detected, poll_count
        poll_count += 1
        if poll_count == 1:
            first_poll_started.set()
            await release_first_poll.wait()
            first_poll_finished.set()
        elif poll_count == 2:
            overlap_detected = not first_poll_finished.is_set()
            second_poll_started.set()
            await release_second_poll.wait()
            second_poll_finished.set()
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
    first_write = None
    second_write = None

    try:
        first_write = hass.async_create_task(
            device.async_write({"ptc_bath_heater.mode": "Heat"}),
            "first bath heater write",
        )
        await asyncio.wait_for(first_poll_started.wait(), timeout=1)
        second_write = hass.async_create_task(
            device.async_write({"ptc_bath_heater.mode": "Fan"}),
            "second bath heater write",
        )
        await asyncio.wait_for(second_write_finished.wait(), timeout=1)
        assert not first_write.done()
        assert not second_write.done()

        release_first_poll.set()
        await asyncio.wait_for(second_poll_started.wait(), timeout=1)
        assert first_poll_finished.is_set()
        assert not second_write.done()

        release_second_poll.set()
        await asyncio.wait_for(
            asyncio.gather(first_write, second_write),
            timeout=1,
        )
    finally:
        release_first_poll.set()
        release_second_poll.set()
        for task in (first_write, second_write):
            if task and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in (first_write, second_write) if task),
            return_exceptions=True,
        )
        await coordinator.async_shutdown()

    assert poll_count == 2
    assert second_poll_finished.is_set()
    assert overlap_detected is False


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


async def test_data_coordinator_serializes_direct_device_updates(make_device, hass):
    spec = get_v6_extended_spec(hass)
    device = make_device(spec, model="yeelink.bhf_light.v6")
    device.entry.entry = MagicMock()
    first_update_started = asyncio.Event()
    release_first_update = asyncio.Event()
    update_active = False
    overlap_detected = False

    async def update_method():
        nonlocal overlap_detected, update_active
        if update_active:
            overlap_detected = True
        update_active = True
        first_update_started.set()
        await release_first_update.wait()
        update_active = False
        return {}

    coordinator = DataCoordinator(device, update_method)
    first_update = None
    second_update = None
    try:
        first_update = hass.async_create_task(
            coordinator._async_update(),
            "first direct coordinator update",
        )
        await asyncio.wait_for(first_update_started.wait(), timeout=1)
        second_update = hass.async_create_task(
            coordinator._async_update(),
            "second direct coordinator update",
        )
        await asyncio.sleep(0)
        assert overlap_detected is False

        release_first_update.set()
        await asyncio.wait_for(
            asyncio.gather(first_update, second_update),
            timeout=1,
        )
    finally:
        release_first_update.set()
        for task in (first_update, second_update):
            if task and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in (first_update, second_update) if task),
            return_exceptions=True,
        )
        await coordinator.async_shutdown()

    assert overlap_detected is False


async def test_data_coordinator_shutdown_cancels_queued_refreshes(
    make_device, hass, monkeypatch,
):
    spec = get_v6_extended_spec(hass)
    device = make_device(spec, model="yeelink.bhf_light.v6")
    device.entry.entry = MagicMock()
    first_update_started = asyncio.Event()
    release_first_update = asyncio.Event()
    second_refresh_started = asyncio.Event()
    update_count = 0

    async def update_method():
        nonlocal update_count
        update_count += 1
        if update_count == 1:
            first_update_started.set()
            await release_first_update.wait()
        return {"poll": update_count}

    async def uncoordinated_refresh(self):
        await self._async_refresh()

    coordinator = DataCoordinator(device, update_method)
    coordinator.data = {"poll": 0}
    listener_updates = []
    coordinator.async_add_listener(lambda: listener_updates.append(coordinator.data))
    update_method_calls = 0
    original_update_method = coordinator.update_method

    async def tracked_update_method():
        nonlocal update_method_calls
        update_method_calls += 1
        if update_method_calls == 2:
            second_refresh_started.set()
        return await original_update_method()

    coordinator.update_method = tracked_update_method
    monkeypatch.setattr(DataUpdateCoordinator, "async_refresh", uncoordinated_refresh)
    first_refresh = None
    second_refresh = None
    try:
        first_refresh = hass.async_create_task(
            coordinator.async_refresh(),
            "active coordinator refresh",
        )
        await asyncio.wait_for(first_update_started.wait(), timeout=1)
        second_refresh = hass.async_create_task(
            coordinator.async_refresh(),
            "queued coordinator refresh",
        )
        await asyncio.wait_for(second_refresh_started.wait(), timeout=1)
        await coordinator.async_shutdown()
    finally:
        release_first_update.set()
        for task in (first_refresh, second_refresh):
            if task and not task.done():
                task.cancel()
        results = await asyncio.gather(
            *(task for task in (first_refresh, second_refresh) if task),
            return_exceptions=True,
        )
        await coordinator.async_shutdown()

    assert update_count == 1
    assert coordinator.data == {"poll": 0}
    assert listener_updates == []
    assert all(isinstance(result, asyncio.CancelledError) for result in results)


def test_data_coordinator_omits_config_entry_on_legacy_home_assistant(
    make_device, hass, monkeypatch,
):
    spec = get_v6_extended_spec(hass)
    device = make_device(spec, model="yeelink.bhf_light.v6")
    device.entry.entry = MagicMock()
    init_kwargs = {}

    def legacy_init(self, hass, logger, name, update_method, *, always_update):
        init_kwargs.update(
            hass=hass,
            logger=logger,
            name=name,
            update_method=update_method,
            always_update=always_update,
        )
        self.setup_method = None

    monkeypatch.setattr(DataUpdateCoordinator, "__init__", legacy_init)

    DataCoordinator(device, lambda: None)

    assert init_kwargs["always_update"] is True


async def test_data_coordinator_missing_string_method_raises_not_implemented(
    make_device, hass,
):
    spec = get_v6_extended_spec(hass)
    device = make_device(spec, model="yeelink.bhf_light.v6")
    device.entry.entry = MagicMock()
    coordinator = DataCoordinator(device, "missing_update_method")

    with pytest.raises(NotImplementedError):
        await coordinator._async_update_data()


@pytest.mark.parametrize(
    ("customizes", "immediate", "expected_request", "expected_refresh"),
    [
        ({}, False, 0, 0),
        ({"non_optimistic": True}, False, 0, 0),
        ({"non_optimistic": True}, True, 0, 1),
    ],
)
async def test_update_main_status_falls_back_only_for_immediate_non_optimistic(
    make_device, hass, customizes, immediate, expected_request, expected_refresh,
):
    spec = get_v6_extended_spec(hass)
    device = make_device(spec, customizes=customizes)
    coordinator = MagicMock()
    coordinator.async_request_refresh = AsyncMock()
    coordinator.async_refresh = AsyncMock()
    device.coordinators = [coordinator]
    device.main_coordinators = []

    await device.update_main_status(immediate=immediate)

    assert coordinator.async_request_refresh.await_count == expected_request
    assert coordinator.async_refresh.await_count == expected_refresh


async def test_optimistic_successful_write_dispatches_payload(make_device, hass):
    spec = get_v6_extended_spec(hass)
    device = make_device(spec, customizes={})
    dispatched = []
    device.add_listener(lambda data, only_info=False: dispatched.append(data))
    device.encode = MagicMock(return_value={
        "method": "set_properties",
        "params": [{"did": "test-device", "siid": 3, "piid": 1, "value": 0}],
    })
    device.async_set_properties = AsyncMock(return_value=[{"code": 0}])

    payload = {"ptc_bath_heater.mode": "Idle"}
    await device.async_write(payload)

    assert dispatched == [payload]


async def test_optimistic_write_error_preserves_legacy_result(make_device, hass):
    spec = get_v6_extended_spec(hass)
    device = make_device(spec, customizes={})
    result = [{"code": -1, "siid": 3, "piid": 1}]
    device.encode = MagicMock(return_value={
        "method": "set_properties",
        "params": [{"did": "test-device", "siid": 3, "piid": 1, "value": 0}],
    })
    device.async_set_properties = AsyncMock(return_value=result)

    assert await device.async_write({"ptc_bath_heater.mode": "Idle"}) == result


async def test_optimistic_action_error_preserves_legacy_result(make_device, hass):
    spec = get_v6_extended_spec(hass)
    device = make_device(spec, customizes={})
    result = MiotResult({}, code=-1, error="Device unavailable")
    device.encode = MagicMock(return_value={
        "method": "action",
        "param": {"siid": 3, "aiid": 1},
    })
    device.async_call_action = AsyncMock(return_value=result)

    returned = await device.async_write({"ptc_bath_heater.stop_working": True})

    assert returned is result


YEELINK_BHF_MODELS = ["yeelink.bhf_light.v5", "yeelink.bhf_light.v6"]


@pytest.fixture(autouse=True)
def disable_device_poll_gap(monkeypatch):
    """Keep unrelated tests instant; the throttle test opts back in."""
    from custom_components.xiaomi_miot.core import coordinator as coordinator_module

    monkeypatch.setattr(coordinator_module, "MIN_DEVICE_POLL_GAP_SECONDS", 0)


def get_extended_spec(hass, load_miot_spec, model) -> MiotSpec:
    """Official spec (fixture for v5, published cloud JSON for v6) + production extension."""
    if model == "yeelink.bhf_light.v5":
        spec = load_miot_spec("yeelink.bhf_light.v5.json")
    else:
        spec = MiotSpec(hass, copy.deepcopy(V6_RAW_CLOUD_SPEC))
    with EXTEND_SPECS_FILE.open(encoding="utf-8") as f:
        extended_specs = json.load(f)
    spec.extend_specs(services=extended_specs.get(model) or [])
    return spec


class MiioMockDev:
    def __init__(self, props=None, send_result=None):
        self.props = props or {}
        self.mapping = {}
        self.sent_commands = []
        self.send_result = send_result if send_result is not None else ["ok"]

    async def async_get_prop(self, keys, max_properties=None):
        return [self.props.get(k) for k in keys]

    async def async_send(self, method, params):
        self.sent_commands.append((method, params))
        return self.send_result


@pytest.mark.parametrize("model", YEELINK_BHF_MODELS)
def test_paired_select_and_fan_level_value_lists_with_auto(hass, load_miot_spec, model):
    """Spec 4.1/4.2: options and order Off/Low/Auto/High, fan level Low/Auto/High."""
    spec = get_extended_spec(hass, load_miot_spec, model)
    heater = spec.services[3]
    expected = {
        101: [(1, "Low"), (2, "Auto"), (3, "High")],
        111: [(0, "Off"), (1, "Low"), (3, "Auto"), (2, "High")],
        112: [(0, "Off"), (1, "Low"), (2, "Auto"), (3, "High")],
        113: [(0, "Off"), (1, "Low"), (2, "Auto"), (3, "High")],
    }
    for iid, want in expected.items():
        prop = heater.properties[iid]
        got = [(v["value"], v["description"]) for v in prop.value_list]
        assert got == want
    for iid in (111, 112, 113):
        assert heater.properties[iid].list_descriptions() == ["Off", "Low", "Auto", "High"]
    assert heater.properties[101].list_descriptions(lower=True) == ["low", "auto", "high"]


SINGLETON_DECODE_MATRIX = [
    ("warmwind", 100, 1),   # Warm Low
    ("warmwind", 300, 2),   # Warm Auto
    ("warmwind", 200, 3),   # Warm High
    ("coolwind", 10, 1),    # Cold Low
    ("coolwind", 20, 2),    # Cold Auto
    ("coolwind", 30, 3),    # Cold High
    ("venting", 1, 1),      # Vent Low
    ("venting", 2, 2),      # Vent Auto
    ("venting", 3, 3),      # Vent High
]


@pytest.mark.parametrize("model", YEELINK_BHF_MODELS)
@pytest.mark.parametrize("bh_mode,fan_speed_idx,want", SINGLETON_DECODE_MATRIX)
async def test_fan_level_singleton_decode_matrix(
    hass, load_miot_spec, model, bh_mode, fan_speed_idx, want,
):
    """Spec 4.2: mode-aware decode (active token, physical gear) -> logical fan mode."""
    spec = get_extended_spec(hass, load_miot_spec, model)
    helper = Miio2MiotHelper.from_model(hass, model, spec)
    mapping = {"fan_level": {"did": "test", "siid": 3, "piid": 101}}
    mock_dev = MiioMockDev({"bh_mode": bh_mode, "fan_speed_idx": fan_speed_idx})
    mock_dev.mapping = mapping

    res = await helper.async_get_miot_props(mock_dev)
    res_map = {f"{r['siid']}.{r['piid']}": r["value"] for r in res}
    assert res_map.get("3.101") == want


@pytest.mark.parametrize("model", YEELINK_BHF_MODELS)
@pytest.mark.parametrize(
    "bh_mode,fan_speed_idx",
    [
        ("warmwind|venting", 300),   # composite Warm Auto + Vent
        ("coolwind|venting", 20),    # composite Cold Auto + Vent
        ("warmwind|venting", 101),
        ("bh_off", 0),               # idle
        ("warmwind", 900),           # out-of-domain warm gear
        ("venting", 4),              # out-of-domain vent gear
        ("warmwind", None),          # unreadable gear
    ],
)
async def test_fan_level_decode_never_falls_back_for_ambiguous_states(
    hass, load_miot_spec, model, bh_mode, fan_speed_idx,
):
    """Spec 4.2/10.8: composite, idle and unknown codes decode to none, never Off/Low."""
    spec = get_extended_spec(hass, load_miot_spec, model)
    helper = Miio2MiotHelper.from_model(hass, model, spec)
    mapping = {"fan_level": {"did": "test", "siid": 3, "piid": 101}}
    mock_dev = MiioMockDev({"bh_mode": bh_mode, "fan_speed_idx": fan_speed_idx})
    mock_dev.mapping = mapping

    res = await helper.async_get_miot_props(mock_dev)
    res_map = {f"{r['siid']}.{r['piid']}": r["value"] for r in res}
    assert res_map.get("3.101") is None


SINGLETON_ENCODE_MATRIX = [
    ("warmwind", 1, ["warmwind", 1]),
    ("warmwind", 2, ["warmwind", 3]),
    ("warmwind", 3, ["warmwind", 2]),
    ("coolwind", 1, ["coolwind", 1]),
    ("coolwind", 2, ["coolwind", 2]),
    ("coolwind", 3, ["coolwind", 3]),
    ("venting", 1, ["venting", 1]),
    ("venting", 2, ["venting", 2]),
    ("venting", 3, ["venting", 3]),
]


@pytest.mark.parametrize("model", YEELINK_BHF_MODELS)
@pytest.mark.parametrize("bh_mode,logical,want", SINGLETON_ENCODE_MATRIX)
async def test_fan_level_singleton_encode_matrix(
    hass, load_miot_spec, model, bh_mode, logical, want,
):
    """Spec 5.1: mode-aware encode (active token, logical fan mode) -> physical gear."""
    spec = get_extended_spec(hass, load_miot_spec, model)
    helper = Miio2MiotHelper.from_model(hass, model, spec)
    mock_dev = MiioMockDev()
    helper.miio_props_values = {"bh_mode": bh_mode}

    await helper.async_set_property(mock_dev, 3, 101, logical)
    assert mock_dev.sent_commands[-1] == ("set_bh_mode", want)


@pytest.mark.parametrize(
    "model,modes",
    [
        ("yeelink.bhf_light.v5", [(6, ["warmwind", 2]), (7, ["coolwind", 3]), (8, ["venting", 3])]),
        ("yeelink.bhf_light.v6", [(2, ["warmwind", 2]), (1, ["coolwind", 3]), (3, ["venting", 3])]),
    ],
)
async def test_climate_mode_default_payloads_stay_high(hass, load_miot_spec, model, modes):
    """Spec 5.2: enabling a climate mode without fan mode keeps the High default."""
    spec = get_extended_spec(hass, load_miot_spec, model)
    helper = Miio2MiotHelper.from_model(hass, model, spec)
    mock_dev = MiioMockDev()
    for value, want in modes:
        helper.miio_props_values = {"bh_mode": "bh_off"}
        await helper.async_set_property(mock_dev, 3, 1, value)
        assert mock_dev.sent_commands[-1] == ("set_bh_mode", want)


@pytest.mark.parametrize("model", YEELINK_BHF_MODELS)
@pytest.mark.parametrize(
    "piid,auto_value,want",
    [
        (111, 3, ["warmwind", 3]),
        (112, 2, ["coolwind", 2]),
        (113, 2, ["venting", 2]),
    ],
)
async def test_select_auto_option_setters(hass, load_miot_spec, model, piid, auto_value, want):
    """Spec 4.1/5.1: paired selects accept Auto with mode-specific raw gear values."""
    spec = get_extended_spec(hass, load_miot_spec, model)
    helper = Miio2MiotHelper.from_model(hass, model, spec)
    mock_dev = MiioMockDev()
    helper.miio_props_values = {"bh_mode": "bh_off"}

    await helper.async_set_property(mock_dev, 3, piid, auto_value)
    assert mock_dev.sent_commands[-1] == ("set_bh_mode", want)


V5_SWITCH_DECODE_MATRIX = [
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
    ("warmwind_extra", False, False, False),
    ("coolwind_backup", False, False, False),
    ("venting-extra", False, False, False),
    (None, None, None, None),
]


@pytest.mark.parametrize(
    "bh_mode,expected_heating,expected_blow,expected_vent", V5_SWITCH_DECODE_MATRIX,
)
async def test_v5_switch_state_decoding(hass, load_miot_spec, bh_mode, expected_heating, expected_blow, expected_vent):
    """Spec 10.5: v5 official bools decode from exact bh_mode tokens only."""
    spec = load_miot_spec("yeelink.bhf_light.v5.json")
    helper = Miio2MiotHelper.from_model(hass, "yeelink.bhf_light.v5", spec)
    mapping = {
        "heating": {"did": "test", "siid": 3, "piid": 2},
        "blow": {"did": "test", "siid": 3, "piid": 3},
        "ventilation": {"did": "test", "siid": 3, "piid": 4},
    }
    mock_dev = MiioMockDev({"bh_mode": bh_mode, "fan_speed_idx": 0})
    mock_dev.mapping = mapping

    res = await helper.async_get_miot_props(mock_dev)
    res_map = {f"{r['siid']}.{r['piid']}": r["value"] for r in res}
    assert res_map.get("3.2") is expected_heating
    assert res_map.get("3.3") is expected_blow
    assert res_map.get("3.4") is expected_vent


def test_v5_converters_include_switch_properties(make_device, hass, load_miot_spec):
    """Spec 10.11: v5 converter discovery uses the official bool properties."""
    spec = get_extended_spec(hass, load_miot_spec, "yeelink.bhf_light.v5")
    device = make_device(spec, model="yeelink.bhf_light.v5")
    switch_converters = [c for c in device.converters if c.domain == "switch"]
    switch_prop_names = [c.prop.name for c in switch_converters]
    assert "heating" in switch_prop_names
    assert "blow" in switch_prop_names
    assert "ventilation" in switch_prop_names


def make_climate_entity(make_device, hass, load_miot_spec, model, bh_mode, gears=None):
    spec = get_extended_spec(hass, load_miot_spec, model)
    device = make_device(spec, model=model)
    helper = Miio2MiotHelper.from_model(hass, model, spec)
    values = {"bh_mode": bh_mode} if bh_mode is not None else {}
    values.update(gears or {})
    helper.miio_props_values = values
    device.miio2miot = helper
    conv = next(c for c in device.converters if isinstance(c, MiotClimateConv))
    return ClimateEntity(device, conv)


@pytest.mark.parametrize("model", YEELINK_BHF_MODELS)
def test_climate_fan_modes_are_low_auto_high(make_device, hass, load_miot_spec, model):
    """Spec 4.2: climate publishes logical fan modes low/auto/high."""
    entity = make_climate_entity(make_device, hass, load_miot_spec, model, "bh_off")
    assert entity._attr_fan_modes == ["low", "auto", "high"]


@pytest.mark.parametrize("model", YEELINK_BHF_MODELS)
@pytest.mark.parametrize(
    "decoded,want",
    [("Low", "low"), ("Auto", "auto"), ("High", "high")],
)
def test_climate_singleton_fan_mode_round_trip(make_device, hass, load_miot_spec, model, decoded, want):
    entity = make_climate_entity(make_device, hass, load_miot_spec, model, "warmwind")
    entity.set_state({entity._conv_speed.full_name: decoded})
    assert entity._attr_fan_mode == want
    assert "effective_fan_mode" not in entity._attr_extra_state_attributes


@pytest.mark.parametrize("model", YEELINK_BHF_MODELS)
@pytest.mark.parametrize("bh_mode", ["warmwind|venting", "coolwind|venting"])
def test_climate_composite_fan_mode_unavailable(make_device, hass, load_miot_spec, model, bh_mode):
    """Spec 6.1/6.5: composite unconditionally hides fan_mode, even for stale data."""
    entity = make_climate_entity(make_device, hass, load_miot_spec, model, bh_mode)
    entity.set_state({entity._conv_speed.full_name: "High"})
    assert entity._attr_fan_mode is None
    assert entity._attr_extra_state_attributes["effective_fan_mode"] == "high"

    entity.set_state({entity._conv_speed.full_name: None})
    assert entity._attr_fan_mode is None
    assert entity._attr_extra_state_attributes["effective_fan_mode"] == "high"


@pytest.mark.parametrize("model", YEELINK_BHF_MODELS)
async def test_climate_composite_set_fan_mode_rejected_without_write(
    make_device, hass, load_miot_spec, model,
):
    """Spec 6.2: climate.set_fan_mode is rejected without any device write in composite."""
    entity = make_climate_entity(make_device, hass, load_miot_spec, model, "warmwind|venting")
    entity.device.async_write = AsyncMock()

    with pytest.raises(HomeAssistantError):
        await entity.async_set_fan_mode("low")
    entity.device.async_write.assert_not_called()


@pytest.mark.parametrize("model", YEELINK_BHF_MODELS)
def test_climate_idle_fan_mode_unavailable_without_effective(make_device, hass, load_miot_spec, model):
    entity = make_climate_entity(make_device, hass, load_miot_spec, model, "bh_off")
    entity.set_state({entity._conv_speed.full_name: None})
    assert entity._attr_fan_mode is None
    assert "effective_fan_mode" not in entity._attr_extra_state_attributes
    assert "raw_fan_gear" not in entity._attr_extra_state_attributes


@pytest.mark.parametrize("model", YEELINK_BHF_MODELS)
@pytest.mark.parametrize(
    "bh_mode,gear_key,raw",
    [
        ("warmwind", "warmwind_gear", 9),
        ("coolwind", "coolwind_gear", 7),
        ("venting", "venting_gear", 0),
    ],
)
def test_climate_unknown_gear_publishes_raw_code(
    make_device, hass, load_miot_spec, model, bh_mode, gear_key, raw,
):
    """Spec 4.2: out-of-domain singleton gear stays diagnosable via raw_fan_gear."""
    entity = make_climate_entity(
        make_device, hass, load_miot_spec, model, bh_mode, gears={gear_key: raw},
    )
    entity.set_state({entity._conv_speed.full_name: None})
    assert entity._attr_fan_mode is None
    assert entity._attr_extra_state_attributes["raw_fan_gear"] == raw
    assert "effective_fan_mode" not in entity._attr_extra_state_attributes


@pytest.mark.parametrize("model", YEELINK_BHF_MODELS)
def test_climate_valid_gear_drops_raw_code(make_device, hass, load_miot_spec, model):
    entity = make_climate_entity(
        make_device, hass, load_miot_spec, model, "warmwind", gears={"warmwind_gear": 2},
    )
    entity.set_state({entity._conv_speed.full_name: None})
    entity._attr_extra_state_attributes["raw_fan_gear"] = 9  # stale from a previous poll
    entity.set_state({entity._conv_speed.full_name: "High"})
    assert entity._attr_fan_mode == "high"
    assert "raw_fan_gear" not in entity._attr_extra_state_attributes


@pytest.mark.parametrize("model", YEELINK_BHF_MODELS)
def test_climate_composite_drops_raw_code(make_device, hass, load_miot_spec, model):
    entity = make_climate_entity(
        make_device, hass, load_miot_spec, model, "warmwind|venting",
        gears={"warmwind_gear": 9},
    )
    entity.set_state({entity._conv_speed.full_name: None})
    assert entity._attr_fan_mode is None
    assert entity._attr_extra_state_attributes["effective_fan_mode"] == "high"
    assert "raw_fan_gear" not in entity._attr_extra_state_attributes


@pytest.mark.parametrize("model", YEELINK_BHF_MODELS)
async def test_climate_singleton_set_fan_mode_writes(make_device, hass, load_miot_spec, model):
    entity = make_climate_entity(make_device, hass, load_miot_spec, model, "warmwind")
    entity.device.async_write = AsyncMock()

    await entity.async_set_fan_mode("auto")
    entity.device.async_write.assert_awaited_once()
    payload = entity.device.async_write.await_args.args[0]
    assert payload[entity._conv_speed.full_name] == "auto"


@pytest.mark.parametrize("model", YEELINK_BHF_MODELS)
async def test_miio_setter_failure_surfaces_as_error_code(hass, load_miot_spec, model):
    """F1: a non-['ok'] miio reply must never be reported as code 1 (success)."""
    spec = get_extended_spec(hass, load_miot_spec, model)
    helper = Miio2MiotHelper.from_model(hass, model, spec)
    helper.miio_props_values = {"bh_mode": "bh_off"}
    mock_dev = MiioMockDev(send_result=["error"])

    result = await helper.async_set_property(mock_dev, 3, 1, 2)
    assert result["code"] == -1
    assert "error" in result
    assert not MiotResult(result).is_success


@pytest.mark.parametrize("model", YEELINK_BHF_MODELS)
async def test_non_optimistic_write_raises_on_miio_setter_error(make_device, hass, load_miot_spec, model):
    """F1 regression: real async_set_properties path raises on an ['error'] reply."""
    spec = get_extended_spec(hass, load_miot_spec, model)
    device = make_device(spec, model=model)
    helper = Miio2MiotHelper.from_model(hass, model, spec)
    helper.miio_props_values = {"bh_mode": "bh_off"}
    device.miio2miot = helper
    device._local_state = True
    device.local = MiioMockDev(send_result=["error"])

    with pytest.raises(DeviceException):
        await device.async_write({"ptc_bath_heater.mode": "Heat"})
    assert device.local.sent_commands[-1][0] == "set_bh_mode"


async def test_coordinator_throttles_burst_refreshes(make_device, hass, load_miot_spec, monkeypatch):
    """Spec 11.2: write-initiated polls coalesce behind a short trailing-edge gap."""
    import time
    from datetime import timedelta

    from custom_components.xiaomi_miot.core import coordinator as coordinator_module

    monkeypatch.setattr(coordinator_module, "MIN_DEVICE_POLL_GAP_SECONDS", 0.2)
    spec = get_extended_spec(hass, load_miot_spec, "yeelink.bhf_light.v6")
    device = make_device(spec, model="yeelink.bhf_light.v6")
    device.entry.entry = MagicMock()
    polls = []

    async def update_method():
        polls.append(time.monotonic())
        return {"poll": len(polls)}

    # The scheduled cadence (30s for v5/v6) must not gate write-initiated
    # confirmed refreshes; only the short gap does.
    coordinator = DataCoordinator(device, update_method, update_interval=timedelta(seconds=30))
    await coordinator.async_refresh()
    await coordinator.async_refresh()

    assert len(polls) == 2
    assert 0.2 <= polls[1] - polls[0] < 30


@pytest.mark.parametrize("model", YEELINK_BHF_MODELS)
@pytest.mark.parametrize("bh_mode", ["bh_off", "drying"])
async def test_climate_idle_set_fan_mode_rejected_without_write(
    make_device, hass, load_miot_spec, model, bh_mode,
):
    """F3: fan mode writes are rejected when no warm/cold/vent channel is active."""
    entity = make_climate_entity(make_device, hass, load_miot_spec, model, bh_mode)
    entity.device.async_write = AsyncMock()

    with pytest.raises(HomeAssistantError):
        await entity.async_set_fan_mode("low")
    entity.device.async_write.assert_not_called()
