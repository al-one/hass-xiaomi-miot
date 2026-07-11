from unittest.mock import AsyncMock

import pytest
from homeassistant.components.climate.const import HVACAction, HVACMode
from homeassistant.components.fan import FanEntityFeature
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.util.percentage import ordered_list_item_to_percentage

from custom_components.xiaomi_miot import button, sensor, switch  # noqa: F401
from custom_components.xiaomi_miot.climate import ClimateEntity
from custom_components.xiaomi_miot.fan import FanEntity
from custom_components.xiaomi_miot.core.converters import MiotClimateConv, MiotFanConv
from custom_components.xiaomi_miot.core.hass_entity import convert_unique_id

MODEL = "cnhdm.airrtc.wkq01"


def model_device(make_device, load_miot_spec):
    return make_device(
        load_miot_spec("cnhdm.airrtc.wkq01.json"),
        model=MODEL,
        customizes=None,
    )


def test_exact_model_converter_mapping(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    climates = [c for c in device.converters if isinstance(c, MiotClimateConv)]
    fans = [c for c in device.converters if isinstance(c, MiotFanConv)]

    assert len(climates) == 2
    assert len(fans) == 1

    air_conditioner = next(c for c in climates if convert_unique_id(c) == 2)
    floor_heating = device.find_converter("climate.floor_heating")
    fresh_air = device.find_converter("fan.fresh_air")

    def unique_props(parent):
        return {
            device.find_converter(attr).prop.unique_prop
            for attr in parent.attrs
        }

    assert unique_props(air_conditioner) == {
        "prop.2.3", "prop.2.1", "prop.2.5", "prop.2.2", "prop.3.1",
    }
    assert unique_props(floor_heating) == {"prop.2.10", "prop.2.8", "prop.3.1"}
    assert unique_props(fresh_air) == {"prop.2.9", "prop.2.7"}

    assert all(
        device.find_converter(attr).domain is None
        for parent in [*climates, *fans]
        for attr in parent.attrs
    )
    assert device.find_converter("button.info") is not None
    assert len([
        c for c in device.converters
        if c.domain == "sensor" and c.prop.unique_prop == "prop.3.1"
    ]) == 1
    assert len([
        c for c in device.converters
        if c.domain == "switch" and c.prop.unique_prop == "prop.5.1"
    ]) == 1
    assert not any(
        getattr(c, "prop", None) and c.prop.service.iid == 4
        for c in device.converters
    )


def test_parent_entity_metadata_and_identity(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    climates = [c for c in device.converters if isinstance(c, MiotClimateConv)]
    air_converter = next(c for c in climates if convert_unique_id(c) == 2)
    floor_converter = device.find_converter("climate.floor_heating")
    fan_converter = device.find_converter("fan.fresh_air")

    air = ClimateEntity(device, air_converter)
    floor = ClimateEntity(device, floor_converter)
    fresh = FanEntity(device, fan_converter)

    assert [air.unique_id, floor.unique_id, fresh.unique_id] == [
        f"{device.unique_id}-2",
        f"{device.unique_id}-floor_heating",
        f"{device.unique_id}-fresh_air",
    ]
    assert len({air.unique_id, floor.unique_id, fresh.unique_id}) == 3
    assert air._attr_name == "Air Conditioner"
    assert floor._attr_name == "Floor Heating"
    assert fresh._attr_name == "Fresh Air"
    assert air._attr_translation_key is None
    assert floor._attr_translation_key is None
    assert fresh._attr_translation_key is None
    assert "thermostat" in air.entity_id
    assert floor.entity_id.endswith("_floor_heating")
    assert fresh.entity_id.endswith("_fresh_air")


def collect_entities(device):
    collected = {
        domain: []
        for domain in ["button", "climate", "fan", "sensor", "switch"]
    }
    for domain, entities in collected.items():
        device.entry.adders[domain] = (
            lambda new, update_before_add=False, bucket=entities: bucket.extend(new)
        )
        device.add_entities(domain)
    return collected


def test_complete_entity_set(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    entities = collect_entities(device)

    converter_domains = sorted(
        converter.domain
        for converter in device.converters
        if converter.domain is not None
    )
    assert converter_domains == ["button", "climate", "climate", "fan", "sensor", "switch"]
    assert {domain: len(values) for domain, values in entities.items()} == {
        "button": 1,
        "climate": 2,
        "fan": 1,
        "sensor": 1,
        "switch": 1,
    }
    assert sorted(entity._attr_name for entity in entities["climate"]) == [
        "Air Conditioner",
        "Floor Heating",
    ]
    assert entities["fan"][0]._attr_name == "Fresh Air"
    assert entities["sensor"][0]._miot_property.unique_prop == "prop.3.1"
    assert entities["switch"][0]._miot_property.unique_prop == "prop.5.1"
    assert len(device.entities) == 6


def control_entities(device):
    climates = [
        ClimateEntity(device, converter)
        for converter in device.converters
        if isinstance(converter, MiotClimateConv)
    ]
    air = next(entity for entity in climates if entity.unique_id.endswith("-2"))
    floor = next(
        entity for entity in climates
        if entity.unique_id.endswith("-floor_heating")
    )
    fresh = FanEntity(device, device.find_converter("fan.fresh_air"))
    return air, floor, fresh


def test_air_conditioner_modes_and_ventilation_preset(make_device, load_miot_spec):
    air, _, _ = control_entities(model_device(make_device, load_miot_spec))

    assert set(air.hvac_modes) == {
        HVACMode.OFF,
        HVACMode.AUTO,
        HVACMode.COOL,
        HVACMode.HEAT,
    }
    assert "Ventilation" in air.preset_modes


def test_floor_heating_power_state_and_partial_updates(make_device, load_miot_spec):
    _, floor, _ = control_entities(model_device(make_device, load_miot_spec))
    assert set(floor.hvac_modes) == {HVACMode.OFF, HVACMode.HEAT}

    for power, mode, action in [
        (True, HVACMode.HEAT, HVACAction.HEATING),
        (True, HVACMode.HEAT, HVACAction.HEATING),
        (False, HVACMode.OFF, HVACAction.OFF),
        (False, HVACMode.OFF, HVACAction.OFF),
        (True, HVACMode.HEAT, HVACAction.HEATING),
    ]:
        floor.set_state({floor._conv_power.full_name: power})
        assert (floor._attr_is_on, floor.hvac_mode, floor.hvac_action) == (
            power,
            mode,
            action,
        )

    floor.set_state({floor._conv_target_temp.full_name: 28})
    assert (
        floor._attr_is_on,
        floor.hvac_mode,
        floor.hvac_action,
        floor.target_temperature,
    ) == (True, HVACMode.HEAT, HVACAction.HEATING, 28)
    floor.set_state({
        floor._conv_power.full_name: False,
        floor._conv_target_temp.full_name: 21,
    })
    assert (
        floor._attr_is_on,
        floor.hvac_mode,
        floor.hvac_action,
        floor.target_temperature,
    ) == (False, HVACMode.OFF, HVACAction.OFF, 21)


@pytest.mark.asyncio
async def test_floor_heating_writes_only_assigned_properties(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    _, floor, _ = control_entities(device)
    device.async_set_properties = AsyncMock(return_value=[{"code": 0}])

    await floor.async_turn_on()
    device.async_set_properties.assert_awaited_once_with([
        {"did": device.did, "siid": 2, "piid": 10, "value": True},
    ])

    device.async_set_properties.reset_mock()
    floor._attr_is_on = True
    await floor.async_set_hvac_mode(HVACMode.HEAT)
    device.async_set_properties.assert_awaited_once_with([
        {"did": device.did, "siid": 2, "piid": 10, "value": True},
    ])

    device.async_set_properties.reset_mock()
    await floor.async_set_temperature(**{ATTR_TEMPERATURE: 27})
    device.async_set_properties.assert_awaited_once_with([
        {"did": device.did, "siid": 2, "piid": 8, "value": 27},
    ])


@pytest.mark.asyncio
async def test_air_conditioner_writes_only_assigned_properties(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    air, _, _ = control_entities(device)
    device.async_set_properties = AsyncMock(return_value=[{"code": 0}])
    payloads = []

    await air.async_turn_on()
    device.async_set_properties.assert_awaited_once_with([
        {"did": device.did, "siid": 2, "piid": 3, "value": True},
    ])
    payloads.append(device.async_set_properties.await_args.args[0])

    device.async_set_properties.reset_mock()
    air._attr_is_on = True
    air._attr_hvac_mode = HVACMode.HEAT
    await air.async_set_hvac_mode(HVACMode.COOL)
    device.async_set_properties.assert_awaited_once_with([
        {"did": device.did, "siid": 2, "piid": 1, "value": 0},
    ])
    payloads.append(device.async_set_properties.await_args.args[0])

    device.async_set_properties.reset_mock()
    await air.async_set_temperature(**{ATTR_TEMPERATURE: 25})
    device.async_set_properties.assert_awaited_once_with([
        {"did": device.did, "siid": 2, "piid": 5, "value": 25},
    ])
    payloads.append(device.async_set_properties.await_args.args[0])

    device.async_set_properties.reset_mock()
    await air.async_set_fan_mode("high")
    device.async_set_properties.assert_awaited_once_with([
        {"did": device.did, "siid": 2, "piid": 2, "value": 3},
    ])
    payloads.append(device.async_set_properties.await_args.args[0])

    assert {item["piid"] for params in payloads for item in params} == {1, 2, 3, 5}
    assert all(
        item["piid"] not in {7, 8, 9, 10}
        for params in payloads
        for item in params
    )


def test_fresh_air_speed_mapping(make_device, load_miot_spec):
    _, _, fan = control_entities(model_device(make_device, load_miot_spec))

    assert fan._conv_power.prop.unique_prop == "prop.2.9"
    assert fan._conv_speed.prop.unique_prop == "prop.2.7"
    assert fan.speed_count == 3
    assert fan.supported_features & FanEntityFeature.SET_SPEED

    for raw, description in [(1, "Low"), (2, "Medium"), (3, "High")]:
        fan.set_state({
            fan._conv_speed.full_name: description,
            fan._conv_power.full_name: True,
        })
        assert fan.percentage == ordered_list_item_to_percentage(
            ["Low", "Medium", "High"],
            description,
        )
        encoded = fan.device.encode({fan._conv_speed.full_name: description})
        assert encoded["params"][0]["value"] == raw


@pytest.mark.asyncio
async def test_fresh_air_write_matrix(make_device, load_miot_spec):
    device = model_device(make_device, load_miot_spec)
    _, _, fan = control_entities(device)
    device.async_set_properties = AsyncMock(return_value=[{"code": 0}])
    payloads = []

    fan._attr_is_on = True
    await fan.async_set_percentage(1)
    device.async_set_properties.assert_awaited_once_with([
        {"did": device.did, "siid": 2, "piid": 7, "value": 1},
    ])
    payloads.append(device.async_set_properties.await_args.args[0])

    device.async_set_properties.reset_mock()
    await fan.async_set_percentage(100)
    device.async_set_properties.assert_awaited_once_with([
        {"did": device.did, "siid": 2, "piid": 7, "value": 3},
    ])
    payloads.append(device.async_set_properties.await_args.args[0])

    device.async_set_properties.reset_mock()
    fan._attr_is_on = False
    await fan.async_set_percentage(66)
    device.async_set_properties.assert_awaited_once_with([
        {"did": device.did, "siid": 2, "piid": 9, "value": True},
        {"did": device.did, "siid": 2, "piid": 7, "value": 2},
    ])
    payloads.append(device.async_set_properties.await_args.args[0])

    device.async_set_properties.reset_mock()
    await fan.async_set_percentage(0)
    device.async_set_properties.assert_awaited_once_with([
        {"did": device.did, "siid": 2, "piid": 9, "value": False},
    ])
    payloads.append(device.async_set_properties.await_args.args[0])

    device.async_set_properties.reset_mock()
    fan._attr_is_on = False
    await fan.async_turn_on()
    device.async_set_properties.assert_awaited_once_with([
        {"did": device.did, "siid": 2, "piid": 9, "value": True},
    ])
    payloads.append(device.async_set_properties.await_args.args[0])

    device.async_set_properties.reset_mock()
    await fan.async_turn_off()
    device.async_set_properties.assert_awaited_once_with([
        {"did": device.did, "siid": 2, "piid": 9, "value": False},
    ])
    payloads.append(device.async_set_properties.await_args.args[0])

    assert all(
        item["piid"] not in {2, 3}
        for params in payloads
        for item in params
    )
