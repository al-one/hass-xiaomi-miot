"""Regression tests for PR #2871; all device I/O is mocked.

The fixture is the public MIOT v2 spec, retrieved 2026-09-30 from:
https://miot-spec.org/miot-spec-v2/instance?type=urn:miot-spec-v2:device:gateway:0000A019:lumi-mitw01:2
Run with the upstream requirements_test_min.txt dependencies and:
python -m pytest -q -o asyncio_mode=auto tests/test_lumi_gateway_mitw01.py
"""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest

from custom_components.xiaomi_miot import DOMAIN, init_integration_data
from custom_components.xiaomi_miot.core.const import DATA_CUSTOMIZE
from custom_components.xiaomi_miot.core.device import Device, DeviceInfo
from custom_components.xiaomi_miot.core.device_customizes import DEVICE_CUSTOMIZES
from custom_components.xiaomi_miot.core.miio2miot import Miio2MiotHelper
from custom_components.xiaomi_miot.core.miio2miot_specs import set_callback_via_param_index
from custom_components.xiaomi_miot.core.miot_spec import MiotSpec
from custom_components.xiaomi_miot.core.utils import get_customize_via_model
from custom_components.xiaomi_miot.light import LightEntity
from custom_components.xiaomi_miot.number import NumberEntity
from custom_components.xiaomi_miot.switch import SwitchEntity

MODEL = "lumi.gateway.mitw01"
ROOT = Path(__file__).resolve().parents[1]
# (siid, piid): (miio property, set method, sample value, native min, native max)
NUMBERS = {
    (3, 2): ("alarming_volume", "set_alarming_volume", 40, 0, 100),
    (6, 1): ("rgb", "set_rgb", 1694498815, 0, 1694498815),
    (6, 2): ("night_light_rgb", "set_night_light_rgb", 1694498815, 0, 1694498815),
    (6, 3): ("arm_wait_time", "set_arm_wait_time", 20, 0, 60),
    (6, 4): ("alarm_time_len", "set_device_prop", 30, 0, 3600),
    (6, 5): ("en_alarm_light", "set_device_prop", 4, 0, 59),
    (6, 6): ("doorbell_volume", "set_doorbell_volume", 45, 0, 100),
    (6, 7): ("gateway_volume", "set_gateway_volume", 55, 0, 100),
}
SWITCHES = {
    (3, 1): ("arming", "set_arming"),
    (6, 8): ("doorbell_push", "set_doorbell_push"),
    (6, 9): ("corridor_light", "set_corridor_light"),
}


@pytest.fixture
async def gateway_device(hass, monkeypatch):
    """Use shipped customizes and the real get_spec -> init_converters path."""
    init_integration_data(hass)
    hass.data[DOMAIN]["config"] = {}
    hass.data.setdefault(DATA_CUSTOMIZE, {})
    with (ROOT / "tests/fixtures/lumi.gateway.mitw01.json").open() as file:
        spec = MiotSpec(hass, json.load(file))
    with (ROOT / "custom_components/xiaomi_miot/core/miot_specs_extend.json").open() as file:
        extensions = json.load(file)[MODEL]
    # Mirror async_setup's extension injection, without network/HA startup.
    monkeypatch.setitem(DEVICE_CUSTOMIZES, MODEL, {
        **DEVICE_CUSTOMIZES.get(MODEL, {}), "extend_miot_specs": extensions,
    })
    hass.data[DOMAIN]["miot_specs"][MODEL] = spec
    entry = SimpleNamespace(
        hass=hass, cloud=None, id="gateway-test", adders={},
        get_config=lambda key=None, default=None: default,
    )
    device = Device(DeviceInfo({
        "did": "test-gateway", "mac": "aa:bb:cc:dd:ee:ff",
        "name": "Test Gateway", "model": MODEL, "urn": spec.type,
    }), entry)
    device._exclude_miot_services = []
    device._exclude_miot_properties = []
    device._unreadable_properties = False
    await device.get_spec()
    device.miio2miot = Miio2MiotHelper.from_model(hass, MODEL, device.spec)
    device.miio2miot.miio_props_values = dict.fromkeys(device.miio2miot.miio_props, 0)
    device.local = SimpleNamespace(async_send=AsyncMock(return_value=["ok"]))
    device._local_state = True
    for domain in ("number", "switch"):
        entry.adders[domain] = lambda entities, update_before_add=False: None
        device.add_entities(domain)
    return device


def entity_for(device, domain, siid, piid):
    matches = [entity for entity in device.entities.values()
               if entity.conv.domain == domain
               and entity.conv.prop.unique_prop == f"prop.{siid}.{piid}"]
    assert len(matches) == 1
    return matches[0]


def test_all_gateway_controls_have_entity_entry_points(gateway_device):
    device = gateway_device
    for key, (_, _, _, minimum, maximum) in NUMBERS.items():
        entity = entity_for(device, "number", *key)
        assert isinstance(entity, NumberEntity)
        assert (entity.native_min_value, entity.native_max_value, entity.native_step) == (minimum, maximum, 1)
    for key in SWITCHES:
        assert isinstance(entity_for(device, "switch", *key), SwitchEntity)
    assert len(device.entities) == len(NUMBERS) + len(SWITCHES)
    assert len({entity.unique_id for entity in device.entities.values()}) == len(device.entities)
    assert any(c.domain == "light" and c.prop.unique_prop == "prop.4.1" for c in device.converters)
    assert any(c.domain == "sensor" and c.prop.unique_prop == "prop.5.1" for c in device.converters)
    for piid in (101, 102):
        assert any(c.prop.unique_prop == f"prop.4.{piid}" for c in device.converters if getattr(c, "prop", None))


def test_gateway_customization_is_model_specific():
    for model in ("lumi.gateway.v3", "lumi.gateway.mcn001"):
        customize = get_customize_via_model(model)
        for key in ("number_properties", "switch_properties"):
            assert "legacy_gateway" not in customize.get(key, "")


async def test_light_packed_rgb_updates_without_a_poll(gateway_device):
    device = gateway_device
    converter = next(c for c in device.converters if c.domain == "light")
    entity = LightEntity(device, converter)
    initial = (25 << 24) | 0x112233
    brightness = (50 << 24) | 0x112233
    final = (50 << 24) | 0x445566
    device.miio2miot.miio_props_values["rgb"] = initial
    await entity.async_turn_on(brightness=128, rgb_color=(68, 85, 102))
    assert device.local.async_send.await_args_list == [
        call("set_rgb", [initial]), call("set_rgb", [brightness]), call("set_rgb", [final]),
    ]
    assert device.miio2miot.miio_props_values["rgb"] == final


@pytest.mark.parametrize("key", NUMBERS)
@pytest.mark.parametrize("use_zero", [False, True])
async def test_number_entity_writes_reach_miio_and_update_cache(gateway_device, key, use_zero):
    device = gateway_device
    prop, method, value, _, _ = NUMBERS[key]
    if use_zero:
        value = 0
    entity = entity_for(device, "number", *key)
    await entity.async_set_native_value(value)
    params = {"sid": "lumi.0", prop: value} if method == "set_device_prop" else [value]
    device.local.async_send.assert_awaited_once_with(method, params)
    assert device.miio2miot.miio_props_values[prop] == value


@pytest.mark.parametrize("key", SWITCHES)
@pytest.mark.parametrize("enabled", [False, True])
async def test_switch_entity_writes_reach_miio_and_update_cache(gateway_device, key, enabled):
    device = gateway_device
    prop, method = SWITCHES[key]
    entity = entity_for(device, "switch", *key)
    await (entity.async_turn_on() if enabled else entity.async_turn_off())
    value = "on" if enabled else "off"
    device.local.async_send.assert_awaited_once_with(method, [value])
    assert device.miio2miot.miio_props_values[prop] == value


@pytest.mark.parametrize("key", [(6, 4), (6, 5), (6, 7)])
async def test_failed_write_preserves_cache(gateway_device, key):
    device = gateway_device
    prop, _, value, _, _ = NUMBERS[key]
    device.miio2miot.miio_props_values[prop] = 42
    device.local.async_send.return_value = ["error"]
    await entity_for(device, "number", *key).async_set_native_value(value)
    assert device.miio2miot.miio_props_values[prop] == 42


@pytest.mark.parametrize("params", [{"sid": "lumi.0"}, [{"sid": "lumi.0"}], ({"sid": "lumi.0"},)])
def test_missing_dict_key_preserves_cached_value(params):
    props = {"alarm_time_len": 42}
    set_callback_via_param_index(0, key="alarm_time_len")(
        prop="alarm_time_len", params=params, props=props,
    )
    assert props == {"alarm_time_len": 42}


@pytest.mark.parametrize("value", [30, 0, False, None])
@pytest.mark.parametrize("container", [lambda p: p, lambda p: [p], lambda p: (p,)])
def test_present_dict_key_retains_value_semantics(value, container):
    props = {"cached": 42}
    set_callback_via_param_index(0, key="wire_key")(
        prop="cached", params=container({"wire_key": value}), props=props,
    )
    assert props["cached"] is value


@pytest.mark.parametrize("params", [None, 1, "bad", [], ()])
def test_unsupported_or_empty_params_preserve_cache(params):
    props = {"cached": 42}
    set_callback_via_param_index(0)(prop="cached", params=params, props=props)
    assert props == {"cached": 42}


@pytest.mark.parametrize("params, expected", [
    ({}, 42), ({"cached": 0}, 0), ({"cached": None}, None),
    ([0], 0), ((False,), False), ([None], None), ([{"other": 1}], {"other": 1}),
])
def test_no_key_callback_backwards_compatibility(params, expected):
    props = {"cached": 42}
    set_callback_via_param_index(0)(prop="cached", params=params, props=props)
    assert props == {"cached": expected}


def test_nonzero_index_and_uncached_property():
    callback = set_callback_via_param_index(1, key="wire_key")
    props = {"cached": 42}
    callback(prop="cached", params=[{"wire_key": 7}], props=props)
    assert props == {"cached": 42}
    callback(prop="cached", params=[0, {"wire_key": 8}], props=props)
    assert props == {"cached": 8}
    callback(prop="absent", params={"wire_key": 9}, props=props)
    assert props == {"cached": 8}
