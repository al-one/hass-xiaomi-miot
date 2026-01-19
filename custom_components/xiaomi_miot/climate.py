"""Support for Xiaomi Aircondition."""
import logging
from enum import Enum

from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_TEMPERATURE,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.components.climate.const import (
    ATTR_CURRENT_HUMIDITY,
    ATTR_CURRENT_TEMPERATURE,
    ATTR_HVAC_MODE,
    ATTR_FAN_MODE,
    HVACAction,
    HVACMode,
)
from homeassistant.components.climate import (
    DOMAIN as ENTITY_DOMAIN,
    ClimateEntity as BaseEntity,
    ClimateEntityFeature,
    SWING_ON,
    SWING_OFF,
)
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.helpers.restore_state import RestoreEntity

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    HassEntry,
    XEntity,
    MiotEntity,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
    MiotProperty,
)

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'

DEFAULT_MIN_TEMP = 16.0
DEFAULT_MAX_TEMP = 31.0

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    HassEntry.init(hass, config_entry).new_adder(ENTITY_DOMAIN, async_add_entities)
    await async_setup_config_entry(hass, config_entry, async_setup_platform, async_add_entities, ENTITY_DOMAIN)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data.setdefault(DATA_KEY, {})
    hass.data[DOMAIN]['add_entities'][ENTITY_DOMAIN] = async_add_entities
    config['hass'] = hass
    model = str(config.get(CONF_MODEL) or '')
    spec = hass.data[DOMAIN]['miot_specs'].get(model)
    entities = []
    if isinstance(spec, MiotSpec):
        for srv in spec.get_services('ir_aircondition_control'):
            if srv.name in ['ir_aircondition_control']:
                entities.append(MiirClimateEntity(config, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class SwingModes(Enum):
    off = 0
    vertical = 1
    horizontal = 2
    both = 3


class BaseClimateEntity(BaseEntity):
    _hvac_modes = None
    _attr_is_on = None
    _attr_device_class = None
    _attr_fan_mode = None
    _attr_fan_modes = None
    _attr_hvac_mode = None
    _attr_preset_mode = None
    _attr_swing_mode = None
    _attr_swing_modes = None
    _attr_swing_horizontal_mode = None
    _attr_swing_horizontal_modes = None
    _attr_max_temp = None
    _attr_min_temp = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def on_init(self):
        self._attr_hvac_modes = []
        self._hvac_modes = {
            HVACMode.OFF:  {'list': ['Off', 'Idle', 'None'], 'action': HVACAction.OFF},
            HVACMode.AUTO: {'list': ['Auto', 'Manual', 'Normal'], 'action': HVACAction.IDLE},
            HVACMode.COOL: {'list': ['Cool'], 'action': HVACAction.COOLING},
            HVACMode.HEAT: {'list': ['Heat'], 'action': HVACAction.HEATING},
            HVACMode.DRY:  {'list': ['Dry'], 'action': HVACAction.DRYING},
            HVACMode.FAN_ONLY: {'list': ['Fan'], 'action': HVACAction.FAN},
        }

    def prop_temperature_unit(self, prop: MiotProperty):
        if prop:
            if prop.unit in ['celsius', UnitOfTemperature.CELSIUS]:
                return UnitOfTemperature.CELSIUS
            if prop.unit in ['fahrenheit', UnitOfTemperature.FAHRENHEIT]:
                return UnitOfTemperature.FAHRENHEIT
            if prop.unit in ['kelvin', UnitOfTemperature.KELVIN]:
                return UnitOfTemperature.KELVIN
        return UnitOfTemperature.CELSIUS

    def update_bind_sensor(self):
        bss = self.custom_config_list('bind_sensor') or []
        ext = {}
        for bse in bss:
            bse = f'{bse}'.strip()
            if not bse:
                continue
            sta = self.hass.states.get(bse)
            if not sta or not sta.state or sta.state == STATE_UNKNOWN:
                continue
            try:
                num = float(sta.state)
            except ValueError:
                num = None
                self.log.info('Got bound state from %s: %s, state invalid', bse, sta.state)
            if num is not None:
                cls = sta.attributes.get(ATTR_DEVICE_CLASS)
                unit = sta.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
                if cls == SensorDeviceClass.TEMPERATURE.value or unit in [
                    UnitOfTemperature.CELSIUS,
                    UnitOfTemperature.KELVIN,
                    UnitOfTemperature.FAHRENHEIT,
                ]:
                    ext[ATTR_CURRENT_TEMPERATURE] = self.hass.config.units.temperature(num, unit)
                elif cls == SensorDeviceClass.HUMIDITY.value:
                    ext[ATTR_CURRENT_HUMIDITY] = num
        if ext:
            self.update_attrs(ext)
            self.log.debug('Got bound state from %s: %s', bss, ext)


class ClimateEntity(XEntity, BaseClimateEntity):
    _conv_power = None
    _conv_mode = None
    _conv_speed = None
    _conv_swing = None
    _conv_swing_h = None
    _conv_target_temp = None
    _conv_current_temp = None
    _conv_target_humidity = None
    _conv_current_humidity = None
    _prop_temperature_name = None

    def on_init(self):
        BaseClimateEntity.on_init(self)

        self._prop_temperature_name = self.custom_config('current_temp_property') or 'indoor_temperature'

        hvac_modes = set()
        for attr in self.conv.attrs:
            conv = self.device.find_converter(attr)
            prop = getattr(conv, 'prop', None) if conv else None
            if not isinstance(prop, MiotProperty):
                continue
            elif prop.in_list(['on']):
                self._conv_power = conv
                self._attr_supported_features |= ClimateEntityFeature.TURN_ON
                self._attr_supported_features |= ClimateEntityFeature.TURN_OFF
                hvac_modes.add(HVACMode.OFF)
                hvac_modes.add(HVACMode.AUTO)
            elif prop.in_list(['mode']):
                self._conv_mode = conv
                self._attr_preset_modes = prop.list_descriptions()
                for mk, mv in self._hvac_modes.items():
                    val = prop.list_first(*(mv.get('list') or []))
                    if val is not None:
                        des = prop.list_description(val)
                        hvac_modes.add(mk)
                        self._hvac_modes[mk]['value'] = val
                        self._hvac_modes[mk]['description'] = des
                        if mk != HVACMode.OFF:
                            self._attr_preset_modes.remove(des)
                if self._attr_preset_modes:
                    self._attr_supported_features |= ClimateEntityFeature.PRESET_MODE
            elif prop.in_list(['fan_level', 'speed_level', 'heat_level']):
                self._conv_speed = conv
                self._attr_fan_modes = prop.list_descriptions(lower=True)
                self._attr_supported_features |= ClimateEntityFeature.FAN_MODE
            elif prop.in_list(['vertical_swing']):
                self._conv_swing = conv
                self._attr_swing_modes = [SWING_ON, SWING_OFF]
                self._attr_supported_features |= ClimateEntityFeature.SWING_MODE
            elif prop.in_list(['horizontal_swing']):
                if hasattr(ClimateEntityFeature, 'SWING_HORIZONTAL_MODE'): # v2024.12
                    self._conv_swing_h = conv
                    self._attr_swing_horizontal_modes = [SWING_ON, SWING_OFF]
                    self._attr_supported_features |= ClimateEntityFeature.SWING_HORIZONTAL_MODE
            elif prop.in_list(['target_temperature']):
                self._conv_target_temp = conv
                self._attr_min_temp = prop.range_min()
                self._attr_max_temp = prop.range_max()
                self._attr_target_temperature_step = prop.range_step()
                self._attr_temperature_unit = self.prop_temperature_unit(prop)
                self._attr_supported_features |= ClimateEntityFeature.TARGET_TEMPERATURE
            elif prop.in_list([self._prop_temperature_name, 'temperature']):
                if prop.in_list([self._prop_temperature_name]):
                    self._conv_current_temp = conv
                elif not self._conv_current_temp:
                    self._conv_current_temp = conv
                else:
                    continue
                self._attr_temperature_unit = self.prop_temperature_unit(prop)
            elif prop.in_list(['relative_humidity', 'humidity']):
                self._conv_current_humidity = conv
            elif prop.in_list(['target_humidity']):
                self._conv_target_humidity = conv
                if prop.value_range:
                    self._attr_min_humidity = prop.range_min()
                    self._attr_max_humidity = prop.range_max()
                self._attr_supported_features |= ClimateEntityFeature.TARGET_HUMIDITY

        self._attr_hvac_modes = list(hvac_modes)

    def set_state(self, data: dict):
        if self._conv_mode:
            val = self._conv_mode.value_from_dict(data)
            if val in self._attr_preset_modes:
                self._attr_preset_mode = val
            if val is not None:
                for mk, mv in self._hvac_modes.items():
                    if val == mv.get('description'):
                        self._attr_hvac_mode = mk
                        self._attr_hvac_action = mv.get('action')
                        self._attr_preset_mode = None
                        break
        if self._conv_power:
            val = self._conv_power.value_from_dict(data)
            if val is not None:
                self._attr_is_on = val
            if val in [False, 0]:
                self._attr_hvac_mode = HVACMode.OFF
                self._attr_hvac_action = HVACAction.OFF
                self._attr_preset_mode = None
            elif val and self._attr_hvac_mode in [None, HVACMode.OFF]:
                self._attr_hvac_mode = HVACMode.AUTO
            if val and self._miot_service.name in ['heater'] and self._attr_hvac_action is None:
                self._attr_hvac_action = HVACAction.HEATING
        self._attr_state = self._attr_hvac_mode

        if self._conv_speed:
            val = self._conv_speed.value_from_dict(data)
            if val is not None:
                self._attr_fan_mode = val
        if self._conv_swing:
            val = self._conv_swing.value_from_dict(data)
            if val is not None:
                self._attr_swing_mode = SWING_ON if val else SWING_OFF
        if self._conv_swing_h:
            val = self._conv_swing_h.value_from_dict(data)
            if val is not None:
                self._attr_swing_horizontal_mode = SWING_ON if val else SWING_OFF

        self.update_bind_sensor()
        if self._conv_target_temp:
            val = self._conv_target_temp.value_from_dict(data)
            if val is not None:
                self._attr_target_temperature = val
        if self._conv_current_temp:
            val = self._conv_current_temp.value_from_dict(data)
            if val is not None:
                self._attr_current_temperature = val

        if self._conv_target_humidity:
            val = self._conv_target_humidity.value_from_dict(data)
            if val is not None:
                self._attr_target_humidity = val
        if self._conv_current_humidity:
            val = self._conv_current_humidity.value_from_dict(data)
            if val is not None:
                self._attr_current_humidity = val

    def update_attrs(self, attrs):
        temp = attrs.get(ATTR_CURRENT_TEMPERATURE)
        if temp is not None:
            self._attr_current_temperature = temp
        humi = attrs.get(ATTR_CURRENT_HUMIDITY)
        if humi is not None:
            self._attr_current_humidity = humi

    async def async_turn_on(self):
        if self._conv_power:
            await self.async_turn_switch(True)
            return
        await super().async_turn_on()

    async def async_turn_off(self):
        if self._conv_power:
            await self.async_turn_switch(False)
            return
        await super().async_turn_off()

    async def async_turn_switch(self, state):
        if self._conv_power:
            await self.device.async_write({self._conv_power.full_name: state})

    async def async_set_hvac_mode(self, hvac_mode: HVACMode):
        await self.async_set_temperature(**{ATTR_HVAC_MODE: hvac_mode})

    async def async_set_preset_mode(self, preset_mode: str):
        if self._conv_mode:
            await self.device.async_write({self._conv_mode.full_name: preset_mode})

    async def async_set_temperature(self, **kwargs):
        dat = {}
        hvac = kwargs.get(ATTR_HVAC_MODE)
        if hvac == HVACMode.OFF and self._conv_power:
            await self.async_turn_switch(False)
            return

        if hvac and self._conv_power and self._attr_is_on is False:
            dat[self._conv_power.full_name] = True

        if hvac and hvac != self._attr_hvac_mode and self._conv_mode:
            mode = self._hvac_modes.get(hvac)
            if not mode:
                self.log.warning('Unsupported hvac mode: %s', hvac)
            elif (desc := mode.get('description')) is not None:
                dat[self._conv_mode.full_name] = desc
                if self._conv_target_temp and self._attr_target_temperature and hvac in [HVACMode.HEAT, HVACMode.COOL]:
                    dat[self._conv_target_temp.full_name] = self._attr_target_temperature

        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp and self._conv_target_temp:
            prop = self._conv_target_temp.prop
            if not isinstance(prop, MiotProperty):
                pass
            elif prop.is_integer or prop.range_step() == 1:
                temp = int(temp)
            dat[self._conv_target_temp.full_name] = temp

        fan_mode = kwargs.get(ATTR_FAN_MODE)
        if fan_mode and self._conv_speed:
            dat[self._conv_speed.full_name] = fan_mode

        await self.device.async_write(dat)

    async def async_set_humidity(self, humidity: int):
        if not self._conv_target_humidity:
            return
        await self.device.async_write({self._conv_target_humidity.full_name: humidity})

    async def async_set_fan_mode(self, fan_mode: str):
        if not self._conv_speed:
            return
        dat = {
            ATTR_FAN_MODE: fan_mode,
        }
        if self._attr_is_on is False and HVACMode.FAN_ONLY in self.hvac_modes:
            dat[ATTR_HVAC_MODE] = HVACMode.FAN_ONLY
        await self.async_set_temperature(**dat)

    async def async_set_swing_mode(self, swing_mode: str):
        if not self._conv_swing:
            return
        await self.device.async_write({self._conv_swing.full_name: swing_mode == SWING_ON})

    async def async_set_swing_horizontal_mode(self, swing_horizontal_mode: str):
        if not self._conv_swing_h:
            return
        await self.device.async_write({self._conv_swing_h.full_name: swing_horizontal_mode == SWING_ON})


XEntity.CLS[ENTITY_DOMAIN] = ClimateEntity


class MiirClimateEntity(MiotEntity, BaseClimateEntity, RestoreEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(miot_service, config=config, logger=_LOGGER)
        self._available = True

        self._act_turn_on = miot_service.get_action('turn_on')
        self._act_turn_off = miot_service.get_action('turn_off')

        # Add turn on/off features if actions are available
        if self._act_turn_on:
            if hasattr(ClimateEntityFeature, 'TURN_ON'):  # v2024.2+
                self._supported_features |= ClimateEntityFeature.TURN_ON
        if self._act_turn_off:
            if hasattr(ClimateEntityFeature, 'TURN_OFF'):  # v2024.2+
                self._supported_features |= ClimateEntityFeature.TURN_OFF

        self._attr_hvac_mode = None
        self._hvac_modes = {
            HVACMode.OFF:  {'list': ['Off', 'Idle', 'None'], 'action': HVACAction.OFF},
            HVACMode.AUTO: {'list': ['Auto', 'Manual', 'Normal']},
            HVACMode.COOL: {'list': ['Cool'], 'action': HVACAction.COOLING},
            HVACMode.HEAT: {'list': ['Heat'], 'action': HVACAction.HEATING},
            HVACMode.DRY:  {'list': ['Dry'], 'action': HVACAction.DRYING},
            HVACMode.FAN_ONLY: {'list': ['Fan'], 'action': HVACAction.FAN},
        }
        self._attr_hvac_modes = []
        self._prop_mode = miot_service.get_property('ir_mode')
        if self._prop_mode:
            for mk, mv in self._hvac_modes.items():
                val = self._prop_mode.list_first(*(mv.get('list') or []))
                if val is not None:
                    self._hvac_modes[mk]['value'] = val
                    self._attr_hvac_modes.append(mk)
                elif mk == HVACMode.OFF:
                    self._attr_hvac_modes.append(mk)

        self._attr_current_temperature = None
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_max_temp = DEFAULT_MAX_TEMP
        self._attr_min_temp = DEFAULT_MIN_TEMP
        self._attr_target_temperature_step = 1
        self._prop_temperature = miot_service.get_property('ir_temperature')
        if self._prop_temperature:
            self._supported_features |= ClimateEntityFeature.TARGET_TEMPERATURE
            self._attr_temperature_unit = self._prop_temperature.unit_of_measurement
            self._attr_target_temperature_step = self._prop_temperature.range_step() or 1
            self._attr_max_temp = self._prop_temperature.range_max() or DEFAULT_MAX_TEMP
            self._attr_min_temp = self._prop_temperature.range_min() or DEFAULT_MIN_TEMP
        self._attr_target_temperature_high = self._attr_max_temp
        self._attr_target_temperature_low = self._attr_min_temp
        self._attr_target_temperature = int((self._attr_max_temp - self._attr_min_temp) / 1.2) + self._attr_min_temp

        self._fan_modes = {}
        self._attr_fan_modes = []
        self._attr_fan_mode = None
        self._act_fan_down = miot_service.get_action('fan_speed_down')
        if self._act_fan_down:
            self._fan_modes[self._act_fan_down.friendly_desc] = self._act_fan_down
        self._act_fan_up = miot_service.get_action('fan_speed_up')
        if self._act_fan_up:
            self._fan_modes[self._act_fan_up.friendly_desc] = self._act_fan_up
        if self._fan_modes:
            self._supported_features |= ClimateEntityFeature.FAN_MODE
            self._attr_fan_modes = list(self._fan_modes.keys())

    async def async_added_to_hass(self):
        await super().async_added_to_hass()

        if hasattr(self, 'async_get_last_state'):
            if state := await self.async_get_last_state():
                self._attr_hvac_mode = state.state
        if self._attr_hvac_mode not in self._hvac_modes:
            self._attr_hvac_mode = None

    async def async_update(self):
        self.update_bind_sensor()
        if ATTR_CURRENT_TEMPERATURE in self._state_attrs:
            self._attr_current_temperature = self._state_attrs.get(ATTR_CURRENT_TEMPERATURE)

    @property
    def is_on(self):
        return self.hvac_mode not in [None, HVACMode.OFF]

    async def async_turn_on(self, **kwargs):
        """Turn the entity on."""
        if not self._act_turn_on:
            raise NotImplementedError()
        if ret := await self.async_call_action(self._act_turn_on):
            self._attr_hvac_mode = HVACMode.AUTO
        return ret

    async def async_turn_off(self, **kwargs):
        """Turn the entity off."""
        if not self._act_turn_off:
            raise NotImplementedError()
        if ret := await self.async_call_action(self._act_turn_off):
            self._attr_hvac_mode = HVACMode.OFF
        return ret

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        if hvac_mode == HVACMode.OFF:
            return await self.async_turn_off()
        if not self._prop_mode:
            raise NotImplementedError()
        val = self._hvac_modes.get(hvac_mode, {}).get('value')
        if val is None:
            return False
        if ret := await self.async_set_property(self._prop_mode, val):
            self._attr_hvac_mode = hvac_mode
        return ret

    @property
    def hvac_action(self):
        """Return the current running hvac operation if supported.
        Need to be one of HVACAction.*.
        """
        if not self.is_on:
            return HVACAction.OFF
        hvac = self.hvac_mode
        if hvac is None:
            return HVACAction.IDLE
        return self._hvac_modes.get(hvac, {}).get('action')

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        if ATTR_HVAC_MODE in kwargs:
            try:
                await self.async_set_hvac_mode(kwargs[ATTR_HVAC_MODE])
            except (Exception, NotImplementedError):
                pass
        if not self._prop_temperature:
            raise NotImplementedError()
        ret = False
        if ATTR_TEMPERATURE in kwargs:
            val = kwargs.get(ATTR_TEMPERATURE)
            if ret := await self.async_set_property(self._prop_temperature, val):
                self._attr_target_temperature = val
        return ret

    async def async_set_fan_mode(self, fan_mode):
        """Set new target fan mode."""
        if not self._attr_fan_modes:
            raise NotImplementedError()
        ret = False
        if act := self._fan_modes.get(fan_mode):
            ret = await self.async_call_action(act)
        return ret
