from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from homeassistant.components.climate import ClimateEntity as HAClimate
from homeassistant.components.climate.const import HVACMode
from homeassistant.const import UnitOfTemperature
from homeassistant.components.water_heater import WaterHeaterEntityFeature
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM
from custom_components.xiaomi_miot.climate import ClimateEntity
from custom_components.xiaomi_miot.water_heater import MiotWaterHeaterEntity
from custom_components.xiaomi_miot.core.converters import MiotClimateConv

C = UnitOfTemperature.CELSIUS
F = UnitOfTemperature.FAHRENHEIT
K = UnitOfTemperature.KELVIN
NEW_API = hasattr(HAClimate, "native_temperature_unit")


def value(entity, prop):
    return getattr(entity, ("native_" if NEW_API else "") + prop)


def climate(make_device, load_miot_spec, unit=C):
    device = make_device(
        load_miot_spec("cnhdm.airrtc.wkq01.json"),
        model="cnhdm.airrtc.wkq01",
        customizes=None,
    )
    for conv in device.converters:
        prop = getattr(conv, "prop", None)
        if prop and prop.in_list(
            ["target_temperature", "temperature", "indoor_temperature"]
        ):
            prop.unit = unit
    conv = next(c for c in device.converters if isinstance(c, MiotClimateConv))
    return ClimateEntity(device, conv)


@pytest.mark.parametrize(
    "unit,current,target,system,shown_current,shown_target",
    [
        (C, 20, 25, METRIC_SYSTEM, 20, 25),
        (C, 20, 25, US_CUSTOMARY_SYSTEM, 68, 77),
        (F, 68, 77, METRIC_SYSTEM, 20, 25),
        (F, 68, 77, US_CUSTOMARY_SYSTEM, 68, 77),
        (K, 293.15, 298.15, METRIC_SYSTEM, 20, 25),
    ],
)
def test_climate_native_and_display_units(
    hass,
    make_device,
    load_miot_spec,
    unit,
    current,
    target,
    system,
    shown_current,
    shown_target,
):
    hass.config.units = system
    entity = climate(make_device, load_miot_spec, unit)
    entity.set_state(
        {
            entity._conv_current_temp.full_name: current,
            entity._conv_target_temp.full_name: target,
        }
    )
    assert value(entity, "temperature_unit") == unit
    assert value(entity, "current_temperature") == pytest.approx(current)
    assert value(entity, "target_temperature") == pytest.approx(target)
    attrs = entity.state_attributes
    assert attrs["current_temperature"] == pytest.approx(shown_current)
    assert attrs["temperature"] == pytest.approx(shown_target)
    if NEW_API:
        assert attrs["temperature_unit"] == system.temperature_unit
    entity.set_state(
        {
            entity._conv_current_temp.full_name: current + 1,
            entity._conv_target_temp.full_name: target + 1,
        }
    )
    assert value(entity, "current_temperature") == pytest.approx(current + 1)
    assert value(entity, "target_temperature") == pytest.approx(target + 1)


@pytest.mark.parametrize(
    "native,sensor_unit,sensor_temp,expected,system",
    [
        (C, F, 68, 20, US_CUSTOMARY_SYSTEM),
        (F, C, 20, 68, METRIC_SYSTEM),
        (C, C, 20, 20, METRIC_SYSTEM),
        (K, C, 20, 293.15, METRIC_SYSTEM),
    ],
)
def test_bound_sensor_keeps_device_unit(
    hass,
    make_device,
    load_miot_spec,
    native,
    sensor_unit,
    sensor_temp,
    expected,
    system,
):
    hass.config.units = system
    entity = climate(make_device, load_miot_spec, native)
    entity.custom_config_list = lambda key: (
        ["sensor.bound_temperature"] if key == "bind_sensor" else []
    )
    hass.states.async_set(
        "sensor.bound_temperature",
        sensor_temp,
        {"device_class": "temperature", "unit_of_measurement": sensor_unit},
    )
    entity.update_bind_sensor()
    assert value(entity, "current_temperature") == pytest.approx(expected)


@pytest.mark.asyncio
async def test_mode_change_keeps_native_target(hass, make_device, load_miot_spec):
    hass.config.units = US_CUSTOMARY_SYSTEM
    entity = climate(make_device, load_miot_spec)
    entity.device.async_write = AsyncMock()
    entity.set_state(
        {
            entity._conv_power.full_name: True,
            entity._conv_mode.full_name: entity._hvac_modes[HVACMode.HEAT][
                "description"
            ],
            entity._conv_target_temp.full_name: 25,
        }
    )
    assert entity.state_attributes["temperature"] == 77
    await entity.async_set_hvac_mode(HVACMode.COOL)
    assert (
        entity.device.async_write.await_args.args[0][entity._conv_target_temp.full_name]
        == 25
    )


def heater(hass, unit, current, target):
    entity = object.__new__(MiotWaterHeaterEntity)
    entity.hass = hass
    entity.device = SimpleNamespace()
    entity._supported_features = WaterHeaterEntityFeature.TARGET_TEMPERATURE
    entity._prop_temperature = SimpleNamespace(
        unit=unit, from_device=lambda device: current
    )
    entity._prop_target_temp = SimpleNamespace(
        unit=unit,
        from_device=lambda device: target,
        range_min=lambda: 10,
        range_max=lambda: 100,
        range_step=lambda: 1,
    )
    entity._prev_target_temp = None
    return entity


@pytest.mark.parametrize(
    "unit,current,target,system,display_current,display_target",
    [
        (C, 20, 25, METRIC_SYSTEM, 20, 25),
        (C, 20, 25, US_CUSTOMARY_SYSTEM, 68, 77),
        (F, 68, 77, METRIC_SYSTEM, 20, 25),
        (F, 68, 77, US_CUSTOMARY_SYSTEM, 68, 77),
        (K, 293.15, 298.15, METRIC_SYSTEM, 20, 25),
    ],
)
def test_water_heater_native_values_ranges_and_display(
    hass, unit, current, target, system, display_current, display_target
):
    hass.config.units = system
    entity = heater(hass, unit, current, target)
    assert value(entity, "current_temperature") == pytest.approx(current)
    assert value(entity, "target_temperature") == pytest.approx(target)
    assert value(entity, "target_temperature_low") == 10
    assert value(entity, "target_temperature_high") == 100
    assert entity.min_temp == 10
    assert entity.max_temp == 100
    assert entity.state_attributes["current_temperature"] == pytest.approx(
        display_current
    )
    assert entity.state_attributes["temperature"] == pytest.approx(display_target)
    entity._prop_target_temp.from_device = lambda device: 0
    assert value(entity, "target_temperature") == pytest.approx(target)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "step,previous,requested,expected",
    [(1, None, 25.4, 25), (1, 25, 25.4, 26), (1, 26, 25.4, 25), (5, None, 27, 25)],
)
async def test_water_heater_setpoint_rounding(
    hass, step, previous, requested, expected
):
    entity = heater(hass, C, 20, 25)
    entity._prop_target_temp.range_step = lambda: step
    entity._prev_target_temp = previous
    entity.async_set_property = AsyncMock(return_value=True)
    assert await entity.async_set_temperature(temperature=requested)
    entity.async_set_property.assert_awaited_once_with(
        entity._prop_target_temp, expected
    )
    assert entity._prev_target_temp == expected


def test_missing_water_heater_properties(hass):
    entity = heater(hass, C, 20, 25)
    entity._prop_temperature = None
    entity._prop_target_temp = None
    assert value(entity, "current_temperature") is None
    assert value(entity, "target_temperature") is None
    assert value(entity, "temperature_unit") == C
    assert entity.min_temp == 40 and entity.max_temp == 65


@pytest.mark.asyncio
async def test_ir_climate_initial_values_and_setpoint(
    hass, make_device, load_miot_spec
):
    from unittest.mock import patch
    from homeassistant.components.climate import ClimateEntityFeature
    from custom_components.xiaomi_miot.climate import MiirClimateEntity
    from custom_components.xiaomi_miot import MiotEntity

    prop = climate(make_device, load_miot_spec)._conv_target_temp.prop

    def init(self, service, config=None, logger=None):
        self.hass = hass
        self._supported_features = ClimateEntityFeature(0)
        self._state_attrs = {}

    service = SimpleNamespace(
        get_action=lambda *args: None,
        get_property=lambda name: prop if name == "ir_temperature" else None,
    )
    with patch.object(MiotEntity, "__init__", init):
        entity = MiirClimateEntity({}, service)
    assert value(entity, "temperature_unit") == C
    assert value(entity, "current_temperature") is None
    entity.async_set_property = AsyncMock(return_value=True)
    assert await entity.async_set_temperature(temperature=25)
    assert value(entity, "target_temperature") == 25
    assert value(entity, "target_temperature_low") == entity.min_temp
    assert value(entity, "target_temperature_high") == entity.max_temp


@pytest.mark.asyncio
@pytest.mark.parametrize("step", ["user", "token", "cloud"])
async def test_config_flow_forms_without_connection_class_warning(hass, caplog, step):
    import uuid
    from custom_components.xiaomi_miot.config_flow import XiaomiMiotFlowHandler

    flow = XiaomiMiotFlowHandler()
    flow.hass = hass
    flow.handler = "xiaomi_miot"
    flow.context = {"source": "user"}
    flow.flow_id = uuid.uuid4().hex
    result = await getattr(flow, "async_step_" + step)()
    assert result["type"] == "form"
    assert result["step_id"] == step
    assert not any(
        "deprecated constant CONN_CLASS" in r.getMessage() for r in caplog.records
    )
