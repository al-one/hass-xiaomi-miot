"""Model-specific cloud energy and local property mapping for xiaomi.plug.04.

The fixture is a readable-property subset of the public 0000D032 instance:
https://miot-spec.org/miot-spec-v2/instance?type=urn:miot-spec-v2:device:outlet:0000A002:xiaomi-04:1:0000D032
"""

import logging
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import EntityPlatform
from homeassistant.util import dt as dt_util

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
EXPOSED_PROPERTIES = {
    "prop.2.2", "prop.3.1", "prop.3.2", "prop.3.3",
    "prop.4.3", "prop.4.4", "prop.4.5", "prop.4.6", "prop.4.7", "prop.4.8",
    "prop.5.1", "prop.8.1", "prop.8.2", "prop.8.4", "prop.8.5",
    "prop.8.6", "prop.8.7", "prop.8.8", "prop.8.9", "prop.9.4",
    "prop.10.1", "prop.10.2", "prop.10.3", "prop.11.2", "prop.11.3",
}


def on_off_entities(device):
    return [
        SwitchEntity(device, next(c for c in device.converters
                                 if c.domain == "switch" and c.prop.unique_prop == key))
        for key in ON_OFF
    ]


async def test_plug_04_local_mode_does_not_fall_back_to_cloud(hass, make_device, load_miot_spec):
    device = make_device(load_miot_spec("xiaomi.plug.04.json"), model=MODEL)
    config = {"username": "test-user", "conn_mode": "local"}
    device.entry.get_config = lambda key=None, default=None: config.get(key, default)
    device.local = SimpleNamespace(
        async_get_properties_for_mapping=AsyncMock(side_effect=DeviceException("offline")),
    )
    device.cloud = SimpleNamespace(async_get_properties_for_mapping=AsyncMock(return_value=[]))
    await device.update_miot_status(
        mapping={"switch.on": {"siid": 2, "piid": 1}}, max_properties=1,
    )
    device.cloud.async_get_properties_for_mapping.assert_not_awaited()


def test_plug_04_uses_cloud_daily_energy_without_local_counter(make_device, load_miot_spec):
    device = make_device(load_miot_spec("xiaomi.plug.04.json"), model=MODEL)
    assert device.custom_config("miot_local") is True
    assert device.custom_config("auto_cloud") is True
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
    config = {"username": "test-user", "conn_mode": "auto"}
    device.entry.get_config = lambda key=None, default=None: config.get(key, default)
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


async def test_plug_04_exposed_entities_keep_spec_names_units_and_write_targets(make_device, load_miot_spec):
    device = make_device(load_miot_spec("xiaomi.plug.04.json"), model=MODEL)

    async def write_properties(params):
        return [{**param, "code": 0} for param in params]

    device.async_set_properties = AsyncMock(side_effect=write_properties)
    classes = {"sensor": SensorEntity, "number": NumberEntity, "switch": SwitchEntity,
               "select": SelectEntity, "binary_sensor": BinarySensorEntity}
    checked = set()
    for conv in device.converters:
        prop = getattr(conv, "prop", None)
        if conv.domain not in classes or not prop or prop.unique_prop not in EXPOSED_PROPERTIES:
            continue
        entity = classes[conv.domain](device, conv)
        checked.add(prop.unique_prop)
        assert entity.unique_id == f"{device.unique_id}-{prop.unique_name}"
        assert entity.name == prop.friendly_desc
        assert entity.name
        if conv.domain == "number":
            assert entity.native_min_value == prop.range_min()
            assert entity.native_max_value == prop.range_max()
            assert entity.native_step == prop.range_step()
            assert entity.native_unit_of_measurement == (
                "kWh" if prop.unique_prop == "prop.10.3" else prop.unit_of_measurement
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
    assert checked == EXPOSED_PROPERTIES


@pytest.mark.parametrize("reverse", [False, True])
def test_plug_04_on_off_ids_are_distinct_and_order_independent(make_device, load_miot_spec, reverse):
    spec = load_miot_spec("xiaomi.plug.04.json")
    if reverse:
        spec.services = dict(reversed(list(spec.services.items())))
    device = make_device(spec, model=MODEL)
    entities = on_off_entities(device)
    assert len({e.entity_id for e in entities}) == 3
    assert len({e.name for e in entities}) == 3
    assert [e.entity_id for e in entities] == [
        "switch.xiaomi_04_eeff_charging_protection_4_on_off_8",
        "switch.xiaomi_04_eeff_quick_countdown_8_on_off_1",
        "switch.xiaomi_04_eeff_over_use_ele_alert_10_on_off_1",
    ]


@pytest.mark.parametrize("language", ["en", "zh-Hans"])
def test_plug_04_names_use_spec_translations(hass, make_device, load_miot_spec, language):
    hass.config.language = language
    names = (["Charging protection enabled", "Quick countdown enabled", "Energy alerts enabled"]
             if language == "en" else ["充电保护设置生效", "快捷倒计时关闭启用", "用电超限提醒启用"])
    raw = load_miot_spec("xiaomi.plug.04.json").raw
    translations = {language: {
        MiotSpec.spec_lang_key(int(key.split(".")[1]), piid=int(key.split(".")[2])): name
        for key, name in zip(ON_OFF, names)
    }}
    device = make_device(MiotSpec(hass, raw, translations=translations), model=MODEL)
    assert [e.name for e in on_off_entities(device)] == names


async def test_plug_04_registry_keeps_existing_ids_and_user_names(hass, make_device, load_miot_spec):
    device = make_device(load_miot_spec("xiaomi.plug.04.json"), model=MODEL)
    entities = on_off_entities(device)
    registry = er.async_get(hass)
    old_ids = ["xiaomi_04_eeff_on_off", "xiaomi_04_eeff_on_off_2", "custom_energy_warning"]
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
        assert [e.entity_id for e in entities] == ["switch." + old_id for old_id in old_ids]
        for entity in entities:
            entry = registry.async_get(entity.entity_id)
            assert entry.unique_id == entity.unique_id
            assert entry.name == "User chosen name"
            assert hass.states.get(entity.entity_id).attributes["friendly_name"].endswith("User chosen name")
    finally:
        await platform.async_reset()
