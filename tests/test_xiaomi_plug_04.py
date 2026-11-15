"""Model-specific cloud energy and local property mapping for xiaomi.plug.04.

The fixture is a readable-property subset of the public 0000D032 instance:
https://miot-spec.org/miot-spec-v2/instance?type=urn:miot-spec-v2:device:outlet:0000A002:xiaomi-04:1:0000D032
"""

import copy
import json
import logging
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import EntityPlatform
from homeassistant.util import dt as dt_util

from custom_components.xiaomi_miot import DOMAIN
from custom_components.xiaomi_miot.binary_sensor import BinarySensorEntity
from custom_components.xiaomi_miot.core.device_customizes import DEVICE_CUSTOMIZES
from custom_components.xiaomi_miot.core.miot_spec import MiotSpec
from custom_components.xiaomi_miot.core.utils import DeviceException
from custom_components.xiaomi_miot.number import NumberEntity
from custom_components.xiaomi_miot.select import SelectEntity
from custom_components.xiaomi_miot.sensor import SensorEntity
from custom_components.xiaomi_miot.switch import SwitchEntity


MODEL = "xiaomi.plug.04"
ON_OFF = ("prop.4.8", "prop.8.1", "prop.10.1")
PROPERTY_IDS = {
    "sensor": {(2, 3), (8, 8), (8, 9)},
    "binary_sensor": {(11, 3)},
    "switch": {(3, 1), (4, 7), (4, 8), (5, 1), (8, 1), (8, 4), (8, 6), (10, 1)},
    "number": {(3, 2), (3, 3), (4, 3), (4, 4), (4, 5), (4, 6),
               (8, 2), (8, 5), (8, 7), (9, 4), (10, 2), (10, 3)},
    "select": {(2, 2)},
}


@pytest.fixture
def plug_device(hass, make_device, load_miot_spec):
    async def create(mode="auto", translations=None):
        raw = copy.deepcopy(load_miot_spec("xiaomi.plug.04.json").raw)
        spec = MiotSpec(hass, raw, translations=translations)
        path = Path("custom_components/xiaomi_miot/core/miot_specs_extend.json")
        extension = json.loads(path.read_text(encoding="utf-8"))[MODEL]
        device = make_device(spec, model=MODEL, customizes={
            **DEVICE_CUSTOMIZES[MODEL], "extend_miot_specs": extension,
        })
        config = {"username": "test-user", "conn_mode": mode}
        device.entry.get_config = lambda key=None, default=None: config.get(key, default)
        # Exercise the real extension gate on a fresh cached spec, without I/O.
        hass.data[DOMAIN]["miot_specs"][MODEL] = spec
        device.spec = None
        device.converters.clear()
        await device.get_spec()
        assert device.conn_mode == mode
        return device
    return create


def on_off_entities(device):
    return [
        SwitchEntity(device, next(c for c in device.converters
                                 if c.domain == "switch" and c.prop.unique_prop == key))
        for key in ON_OFF
    ]


@pytest.mark.parametrize("offset", [0, 20])
def test_plug_04_selection_follows_property_names(hass, make_device, load_miot_spec, offset):
    raw = copy.deepcopy(load_miot_spec("xiaomi.plug.04.json").raw)
    for service in raw["services"]:
        for prop in service["properties"]:
            prop["iid"] += offset
    spec = MiotSpec(hass, raw)
    for domain, ids in PROPERTY_IDS.items():
        selectors = DEVICE_CUSTOMIZES[MODEL][f"{domain}_properties"].split(",")
        assert all(not selector.startswith("prop.") for selector in selectors)
        assert {(p.siid, p.iid) for p in spec.get_properties(*selectors)} == {
            (sid, pid + offset) for sid, pid in ids
        }
    # The unit customization must follow the property name as well.
    device = make_device(spec, model=MODEL)
    conv = next(c for c in device.converters
                if c.domain == "number" and c.prop.name == "over_ele_month")
    assert NumberEntity(device, conv).native_unit_of_measurement == "kWh"


async def test_plug_04_local_mode_does_not_fall_back_to_cloud(plug_device):
    device = await plug_device("local")
    device.local = SimpleNamespace(
        async_get_properties_for_mapping=AsyncMock(side_effect=DeviceException("offline")),
    )
    device.cloud = SimpleNamespace(async_get_properties_for_mapping=AsyncMock(return_value=[]))
    await device.update_miot_status(
        mapping={"switch.on": {"siid": 2, "piid": 1}}, max_properties=1,
    )
    device.cloud.async_get_properties_for_mapping.assert_not_awaited()


async def test_plug_04_uses_cloud_daily_energy_without_local_counter(plug_device):
    device = await plug_device()
    assert device.custom_config("miot_local") is True
    mapping = device.miot_mapping()
    assert {"siid": 11, "piid": 1} not in mapping.values()
    assert {"siid": 11, "piid": 2} in mapping.values()
    assert any(c.domain == "binary_sensor" and c.prop.unique_prop == "prop.11.3"
               for c in device.converters if getattr(c, "prop", None))
    command = device.cloud_statistics_commands[0]
    assert command["key"] == "11.1"
    assert command["type"] == "stat_day_v3"
    assert device.custom_config("sensor_attributes") == "power_cost_today,power_cost_month"
    assert DEVICE_CUSTOMIZES[f"{MODEL}:power_cost_today"]["value_ratio"] == 1
    assert DEVICE_CUSTOMIZES[f"{MODEL}:power_cost_month"]["value_ratio"] == 1
    device.local = SimpleNamespace()
    device.cloud = SimpleNamespace()
    assert device.use_local is True
    assert device.auto_cloud is True


async def test_plug_04_cloud_values_are_already_kwh(hass, make_device):
    today = dt_util.now().replace(hour=0, minute=0, second=0, microsecond=0)
    device = make_device(MiotSpec(hass, {
        "type": "urn:miot-spec-v2:device:outlet:0000A002:xiaomi-04:1",
        "services": [],
    }), model=MODEL)
    device.cloud = SimpleNamespace(async_request_api=AsyncMock(return_value={
        "code": 0, "result": [{"time": int(today.timestamp()), "value": "[0.35]"}],
    }))
    assert await device.update_cloud_statistics() == {
        "power_cost_today": 0.35, "power_cost_month": 0.35,
    }
    api, params = device.cloud.async_request_api.await_args.args
    assert api == "v2/user/statistics"
    assert params["key"] == "11.1"
    assert params["data_type"] == "stat_day_v3"
    assert params["limit"] == 31


@pytest.mark.parametrize("mode", ["auto", "local", "cloud"])
async def test_plug_04_entities_keep_spec_names_units_and_write_targets(plug_device, mode):
    device = await plug_device(mode)

    async def write_properties(params):
        return [{**param, "code": 0} for param in params]

    device.async_set_properties = AsyncMock(side_effect=write_properties)
    classes = {"sensor": SensorEntity, "number": NumberEntity, "switch": SwitchEntity,
               "select": SelectEntity, "binary_sensor": BinarySensorEntity}
    checked = set()
    expected = (set.union(*PROPERTY_IDS.values()) - {(2, 3)}) | {(11, 2)}
    for conv in device.converters:
        prop = getattr(conv, "prop", None)
        if conv.domain not in classes or not prop or (prop.siid, prop.iid) not in expected:
            continue
        entity = classes[conv.domain](device, conv)
        checked.add((prop.siid, prop.iid))
        assert entity.unique_id == f"{device.unique_id}-{prop.unique_name}"
        assert entity.name == prop.friendly_desc
        assert entity.name
        if conv.domain == "number":
            assert entity.native_min_value == prop.range_min()
            assert entity.native_max_value == prop.range_max()
            assert entity.native_step == prop.range_step()
            assert entity.native_unit_of_measurement == (
                "kWh" if prop.name == "over_ele_month" else prop.unit_of_measurement
            )
            value = entity.native_min_value
            await entity.async_set_native_value(value)
        elif conv.domain == "switch":
            value = True
            await entity.async_turn_on()
        elif conv.domain == "select":
            value = 1
            await entity.async_select_option(entity.options[1])
        else:
            continue
        params = device.async_set_properties.await_args.args[0]
        assert params == [{"did": device.did, "siid": prop.siid, "piid": prop.iid, "value": value}]
    assert checked == expected


@pytest.mark.parametrize("language", ["en", "zh-Hans"])
async def test_plug_04_names_use_spec_translations(hass, plug_device, language):
    hass.config.language = language
    names = (["Charging protection enabled", "Quick countdown enabled", "Energy alerts enabled"]
             if language == "en" else ["充电保护设置生效", "快捷倒计时关闭启用", "用电超限提醒启用"])
    translations = {language: {
        MiotSpec.spec_lang_key(int(key.split(".")[1]), piid=int(key.split(".")[2])): name
        for key, name in zip(ON_OFF, names)
    }}
    device = await plug_device(translations=translations)
    assert [e.name for e in on_off_entities(device)] == names


@pytest.mark.parametrize("mode", ["auto", "local", "cloud"])
@pytest.mark.parametrize("existing", [False, True])
async def test_plug_04_registry_keeps_distinct_entities_and_existing_names(hass, plug_device, mode, existing):
    device = await plug_device(mode)
    entities = on_off_entities(device)
    defaults = [e.entity_id for e in entities]
    if mode == "cloud":
        # Upstream deliberately skips local spec extensions in cloud-only mode.
        assert defaults == ["switch.xiaomi_04_eeff_on_off"] * 3
    else:
        assert defaults == ["switch.xiaomi_04_eeff_" + suffix for suffix in
                            ["charging_protection", "quick_countdown", "energy_alert"]]
    registry = er.async_get(hass)
    old_ids = ["xiaomi_04_eeff_on_off", "xiaomi_04_eeff_on_off_2", "custom_energy_warning"]
    if existing:
        for entity, old_id in zip(entities, old_ids):
            entry = registry.async_get_or_create(
                "switch", "xiaomi_miot", entity.unique_id, suggested_object_id=old_id,
            )
            registry.async_update_entity(entry.entity_id, name="User chosen name")
    platform = EntityPlatform(
        hass=hass, logger=logging.getLogger(__name__), domain="switch",
        platform_name="xiaomi_miot",
        platform=SimpleNamespace(async_setup_platform=AsyncMock()),
        scan_interval=timedelta(seconds=30), entity_namespace=None,
    )
    try:
        await platform.async_setup({})
        await platform.async_add_entities(entities)
        assert len({e.entity_id for e in entities}) == 3
        assert len({e.unique_id for e in entities}) == 3
        if existing:
            assert [e.entity_id for e in entities] == ["switch." + old_id for old_id in old_ids]
        for entity in entities:
            entry = registry.async_get(entity.entity_id)
            assert entry.unique_id == entity.unique_id
            assert hass.states.get(entity.entity_id) is not None
            if existing:
                assert entry.name == "User chosen name"
                assert hass.states.get(entity.entity_id).attributes["friendly_name"].endswith("User chosen name")
    finally:
        await platform.async_reset()
    assert all(e.on_device_update not in device.listeners for e in entities)
