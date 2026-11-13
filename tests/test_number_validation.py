"""Exercise MIoT number validation through Home Assistant services."""
from unittest.mock import AsyncMock

import pytest

from homeassistant.components.number import DATA_COMPONENT
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component

from custom_components.xiaomi_miot.number import NumberEntity


async def add_number(hass, *, minimum=0, maximum=10, step=1, integer=True):
    assert await async_setup_component(hass, "number", {})
    # Use the integration setter and HA entity/service lifecycle, with no device IO.
    entity = object.__new__(NumberEntity)
    entity.hass = hass
    entity.entity_id = "number.test_value"
    entity.attr = "number.test_value"
    entity._attr_available = True
    entity._attr_native_value = minimum
    entity._attr_native_min_value = minimum
    entity._attr_native_max_value = maximum
    entity._attr_native_step = step
    entity._attr_native_unit_of_measurement = None
    from types import SimpleNamespace
    entity._miot_property = SimpleNamespace(is_integer=integer)
    entity._miot_action = None
    entity.device = SimpleNamespace(async_write=AsyncMock(), remove_listener=lambda cb: None)
    entity.async_added_to_hass = AsyncMock()
    await hass.data[DATA_COMPONENT].async_add_entities([entity])
    return entity


@pytest.mark.parametrize("value", [float("nan"), 1.5])
async def test_invalid_value_never_reaches_transport(hass, value):
    entity = await add_number(hass)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("number", "set_value", {
            "entity_id": entity.entity_id, "value": value,
        }, blocking=True)
    entity.device.async_write.assert_not_awaited()


@pytest.mark.parametrize("value", [-1, 11, float("inf"), -float("inf")])
async def test_ha_already_rejects_out_of_range(hass, value):
    entity = await add_number(hass)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("number", "set_value", {
            "entity_id": entity.entity_id, "value": value,
        }, blocking=True)
    entity.device.async_write.assert_not_awaited()


@pytest.mark.parametrize("minimum,step,value", [(0, 0.1, 0.1 + 0.2), (0.1, 0.2, 0.7), (-1, 0.5, -0.5)])
async def test_valid_float_grid_values(hass, minimum, step, value):
    entity = await add_number(hass, minimum=minimum, step=step, integer=False)
    await hass.services.async_call("number", "set_value", {
        "entity_id": entity.entity_id, "value": value,
    }, blocking=True)
    entity.device.async_write.assert_awaited_once_with({entity.attr: value})


async def test_off_step_float_rejected(hass):
    entity = await add_number(hass, step=0.2, integer=False)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("number", "set_value", {
            "entity_id": entity.entity_id, "value": 0.3,
        }, blocking=True)
    entity.device.async_write.assert_not_awaited()


@pytest.mark.parametrize("value,expected", [(0.0, 0), (10.0, 10), (0.3 / 0.1, 3)])
async def test_integer_commands_preserve_representation_noise(hass, value, expected):
    entity = await add_number(hass)
    await hass.services.async_call("number", "set_value", {
        "entity_id": entity.entity_id, "value": value,
    }, blocking=True)
    entity.device.async_write.assert_awaited_once_with({entity.attr: expected})
