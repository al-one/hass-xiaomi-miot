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
    DEFAULT_MAX_HUMIDITY,
    DEFAULT_MIN_HUMIDITY,
    HVACAction,
    HVACMode,
)
from homeassistant.components.climate import (
    DOMAIN as ENTITY_DOMAIN,
    ClimateEntity,
    ClimateEntityFeature,  # v2022.5
)
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.helpers.restore_state import RestoreEntity

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    MiotEntity,
    MiotToggleEntity,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
    MiotProperty,
)
from .fan import (
    MiotModesSubEntity,
    FanEntityFeature,
)

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'

DEFAULT_MIN_TEMP = 16.0
DEFAULT_MAX_TEMP = 31.0

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    await async_setup_config_entry(hass, config_entry, async_setup_platform, async_add_entities, ENTITY_DOMAIN)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data.setdefault(DATA_KEY, {})
    hass.data[DOMAIN]['add_entities'][ENTITY_DOMAIN] = async_add_entities
    config['hass'] = hass
    model = str(config.get(CONF_MODEL) or '')
    spec = hass.data[DOMAIN]['miot_specs'].get(model)
    entities = []
    if isinstance(spec, MiotSpec):
        for srv in spec.get_services(
            ENTITY_DOMAIN, 'air_conditioner', 'air_condition_outlet',
            'ir_aircondition_control', 'thermostat', 'heater', 'ptc_bath_heater',
        ):
            if srv.name in ['ir_aircondition_control']:
                entities.append(MiirClimateEntity(config, srv))
            elif srv.get_property('on', 'mode', 'target_temperature'):
                entities.append(MiotClimateEntity(config, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class SwingModes(Enum):
    off = 0
    vertical = 1
    horizontal = 2
    both = 3


class BaseClimateEntity(MiotEntity, ClimateEntity):
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
                _LOGGER.info('%s: Got bound state from %s: %s, state invalid', self.name_model, bse, sta.state)
            if num is not None:
                cls = sta.attributes.get(ATTR_DEVICE_CLASS)
                unit = sta.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
                if cls == SensorDeviceClass.TEMPERATURE.value or unit in [UnitOfTemperature.CELSIUS, UnitOfTemperature.KELVIN, UnitOfTemperature.FAHRENHEIT]:
                    ext[ATTR_CURRENT_TEMPERATURE] = self.hass.config.units.temperature(num, unit)
                elif cls == SensorDeviceClass.HUMIDITY.value:
                    ext[ATTR_CURRENT_HUMIDITY] = num
        if ext:
            self.update_attrs(ext)
            _LOGGER.debug('%s: Got bound state from %s: %s', self.name_model, bss, ext)


class MiotClimateEntity(MiotToggleEntity, BaseClimateEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(miot_service, config=config, logger=_LOGGER)

        self._prop_power = miot_service.bool_property('on')
        self._prop_mode = miot_service.get_property('mode')
        self._prop_heater = miot_service.bool_property('heater')
        self._prop_target_temp = miot_service.get_property('target_temperature')
        self._prop_target_humi = miot_service.get_property('target_humidity')
        self._prop_fan_level = miot_service.get_property('fan_level', 'heat_level')
        self._prev_target_temp = None

        self._environment = miot_service.spec.get_service('environment')
        self._prop_temperature = miot_service.get_property('indoor_temperature', 'temperature')
        self._prop_humidity = miot_service.get_property('relative_humidity', 'humidity')

        self._fan_control = miot_service.spec.get_service('fan_control')
        self._prop_fan_power = None
        self._prop_horizontal_swing = None
        self._prop_vertical_swing = None
        if self._fan_control:
            self._prop_fan_power = self._fan_control.get_property('on')
            self._prop_fan_level = self._fan_control.get_property('fan_level', 'heat_level') or self._prop_fan_level
            self._prop_horizontal_swing = self._fan_control.get_property('horizontal_swing')
            self._prop_horizontal_angle = self._fan_control.get_property('horizontal_angle')
            self._prop_vertical_swing = self._fan_control.get_property('vertical_swing')
            self._prop_vertical_angle = self._fan_control.get_property('vertical_angle')
            if not self._prop_mode:
                self._prop_mode = self._fan_control.get_property('mode')

        for s in [self._environment, self._fan_control]:
            if not s:
                continue
            if not self._prop_temperature:
                self._prop_temperature = s.get_property('indoor_temperature', 'temperature')
            if not self._prop_humidity:
                self._prop_humidity = s.get_property('relative_humidity', 'humidity')

        if miot_service.name in ['water_dispenser']:
            if not self._prop_fan_level:
                self._prop_fan_level = miot_service.get_property('heat_level', 'water_level')

        if self._prop_power:
            if hasattr(ClimateEntityFeature, 'TURN_ON'): # v2024.2
                self._supported_features |= ClimateEntityFeature.TURN_ON
            if hasattr(ClimateEntityFeature, 'TURN_OFF'):
                self._supported_features |= ClimateEntityFeature.TURN_OFF
        if self._prop_target_temp:
            self._supported_features |= ClimateEntityFeature.TARGET_TEMPERATURE
        if self._prop_target_humi:
            self._supported_features |= ClimateEntityFeature.TARGET_HUMIDITY
        if self.fan_modes or (self._prop_mode and self._prop_mode.list_first('Fan') is not None):
            self._supported_features |= ClimateEntityFeature.FAN_MODE
        if self._prop_horizontal_swing or self._prop_vertical_swing:
            self._supported_features |= ClimateEntityFeature.SWING_MODE

        self._power_modes = []
        if miot_service.get_property('heat_level'):
            self._power_modes.append('heater')
        self._hvac_modes = {
            HVACMode.OFF:  {'list': ['Off', 'Idle', 'None'], 'action': HVACAction.OFF},
            HVACMode.AUTO: {'list': ['Auto', 'Manual', 'Normal']},
            HVACMode.COOL: {'list': ['Cool'], 'action': HVACAction.COOLING},
            HVACMode.HEAT: {'list': ['Heat'], 'action': HVACAction.HEATING},
            HVACMode.DRY:  {'list': ['Dry'], 'action': HVACAction.DRYING},
            HVACMode.FAN_ONLY: {'list': ['Fan'], 'action': HVACAction.FAN},
        }
        self._preset_modes = {}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._vars['turn_on_hvac'] = self.custom_config('turn_on_hvac')

        if self.custom_config_bool('ignore_fan_switch'):
            self._prop_fan_power = None
        if prop := self.custom_config('current_temp_property'):
            if prop := self._miot_service.spec.get_property(prop):
                self._prop_temperature = prop

        if self._prop_mode:
            mvs = []
            dls = []
            for mk, mv in self._hvac_modes.items():
                val = self._prop_mode.list_first(*(mv.get('list') or []))
                if val is not None:
                    self._hvac_modes[mk]['value'] = val
                    mvs.append(val)
                elif mk != HVACMode.OFF:
                    dls.append(mk)
            for k in dls:
                self._hvac_modes.pop(k, None)
            fst = None
            for v in self._prop_mode.value_list:
                fst = fst or v
                val = v.get('value')
                if val not in mvs:
                    des = self._prop_mode.get_translation(v.get('description'))
                    self._preset_modes[val] = des
            if self._prop_mode.value_range:
                for val in self._prop_mode.list_descriptions():
                    des = self._prop_mode.get_translation(val)
                    self._preset_modes[val] = des
            if fst and len(self._hvac_modes) <= 1:
                self._hvac_modes[HVACMode.AUTO] = {
                    'list':  [fst.get('description')],
                    'value': fst.get('value'),
                }

        if self._preset_modes:
            self._supported_features |= ClimateEntityFeature.PRESET_MODE

    async def async_update(self):
        await super().async_update()
        if self._available:
            self.update_bind_sensor()
            add_fans = self._add_entities.get('fan')
            for m in self._power_modes:
                p = self._miot_service.bool_property(m)
                if m in self._subs:
                    self._subs[m].update_from_parent()
                elif add_fans and p:
                    self._subs[m] = ClimateModeSubEntity(self, p)
                    add_fans([self._subs[m]], update_before_add=True)
            off = self._hvac_modes.get(HVACMode.OFF, {}).get('value')
            for val, des in self._preset_modes.items():
                if des in self._subs:
                    self._subs[des].update_from_parent()
                elif add_fans and self._prop_mode and self._miot_service.name in ['ptc_bath_heater']:
                    self._subs[des] = ClimateModeSubEntity(self, self._prop_mode, {
                        'unique_id':  f'{self.unique_id}-{self._prop_mode.full_name}-{val}',
                        'name':       f'{self.name} {des}',
                        'value_on':   val,
                        'value_off':  off,
                        'prop_speed': self._prop_fan_level,
                    })
                    add_fans([self._subs[des]], update_before_add=True)

            add_switches = self._add_entities.get('switch')
            for p in self._miot_service.properties.values():
                if not (p.format == 'bool' and p.readable and p.writeable):
                    continue
                if p.name in self._power_modes:
                    continue
                if self._prop_power and self._prop_power.name == p.name:
                    continue
                self._update_sub_entities(p, None, 'switch')

            if self._miot_service.name in ['ptc_bath_heater']:
                self._update_sub_entities(None, ['light', 'light_bath_heater'], domain='light')

            if self._miot_service.get_action('start_wash'):
                pnm = 'action_wash'
                prop = self._miot_service.get_property('status')
                if pnm in self._subs:
                    self._subs[pnm].update_from_parent()
                elif add_switches and prop:
                    from .switch import MiotWasherActionSubEntity
                    self._subs[pnm] = MiotWasherActionSubEntity(self, prop)
                    add_switches([self._subs[pnm]], update_before_add=True)

    @property
    def is_on(self):
        ret = None
        if self._prop_power and not ret:
            ret = self._prop_power.from_dict(self._state_attrs) and True
        if self._prop_fan_power and not ret:
            ret = self._prop_fan_power.from_dict(self._state_attrs) and True
        if ret is not None:
            return ret
        for m in self._power_modes:
            p = self._miot_service.bool_property(m)
            if not p:
                continue
            if self._state_attrs.get(p.full_name):
                return True
        if self._prop_mode:
            off = self._hvac_modes.get(HVACMode.OFF, {}).get('value')
            if off is not None:
                return off != self._prop_mode.from_dict(self._state_attrs)
        power = self._state_attrs.get('power')
        if power is not None:
            return not not power
        return None

    def turn_on(self, **kwargs):
        ret = None
        if self._prop_power:
            ret = self.set_property(self._prop_power, True)
        if self._prop_fan_power:
            ret = self.set_property(self._prop_fan_power, True)
        if ret is not None:
            return ret
        srv = self._miot_service.spec.get_service('viomi_bath_heater')
        if srv:
            act = srv.get_action('power_on')
            if act:
                ret = self.miot_action(srv.iid, act.iid)
                if ret:
                    self.update_attrs({'power': True})
                    return ret
        if not kwargs.get('without_modes'):
            for m in self._power_modes:
                p = self._miot_service.bool_property(m)
                if not p:
                    continue
                return self.set_property(p, True)
            for mode in (HVACMode.HEAT_COOL, HVACMode.AUTO, HVACMode.HEAT, HVACMode.COOL):
                if mode not in self.hvac_modes:
                    continue
                return self.set_hvac_mode(mode)
        return False

    def turn_off(self, **kwargs):
        if self._prop_power:
            if self._prop_fan_power:
                self.set_property(self._prop_fan_power, False)
            return self.set_property(self._prop_power, False)
        if self._prop_mode:
            off = self._hvac_modes.get(HVACMode.OFF, {}).get('value')
            if off is not None:
                return self.set_property(self._prop_mode, off)
        act = self._miot_service.get_action('stop_working', 'power_off')
        if act:
            ret = self.miot_action(self._miot_service.iid, act.iid)
            if ret:
                self.update_attrs({'power': False})
                return ret
        ret = None
        for m in self._power_modes:
            p = self._miot_service.bool_property(m)
            if not p:
                continue
            ret = self.set_property(p, False)
        if ret is not None:
            return ret
        if self._prop_fan_power:
            return self.set_property(self._prop_fan_power, False)
        return False

    @property
    def state(self):
        sta = self.hvac_mode
        if sta is None and self._prop_mode:
            val = self._prop_mode.from_dict(self._state_attrs)
            if val is not None:
                sta = self._prop_mode.list_description(val)
            if sta:
                sta = str(sta).lower()
        return sta

    @property
    def hvac_mode(self):
        if not self.is_on:
            return HVACMode.OFF
        if self._prop_mode:
            acm = self._prop_mode.from_dict(self._state_attrs)
            try:
                acm = -1 if acm is None else int(acm or 0)
            except TypeError:
                acm = -1
            for mk, mv in self._hvac_modes.items():
                if acm == mv.get('value'):
                    return mk
        if self._prop_power:
            if mod := self._vars.get('turn_on_hvac'):
                return mod
            return HVACMode.AUTO
        return None

    @property
    def hvac_modes(self):
        hms = []
        if self._prop_mode:
            for mk, mv in self._hvac_modes.items():
                if mv.get('value') is None:
                    continue
                hms.append(mk)
        if self._prop_power:
            mod = self._vars.get('turn_on_hvac') or HVACMode.AUTO
            if mod and mod not in hms:
                hms.append(mod)
        if HVACMode.OFF not in hms:
            hms.append(HVACMode.OFF)
        return hms

    def set_hvac_mode(self, mode: str):
        return self.set_preset_mode(mode)

    @property
    def hvac_action(self):
        """Return the current running hvac operation if supported.
        Need to be one of HVACAction.*.
        """
        if not self.is_on:
            return HVACAction.OFF
        if self._miot_service.name in ['heater']:
            return HVACAction.HEATING
        hvac = self.hvac_mode
        if hvac is None:
            return HVACAction.IDLE
        return self._hvac_modes.get(hvac, {}).get('action')

    @property
    def preset_mode(self):
        if not self.is_on:
            return HVACMode.OFF
        if self._preset_modes and self._prop_mode:
            acm = self._prop_mode.from_dict(self._state_attrs)
            acm = -1 if acm is None else acm
            return self._preset_modes.get(acm)
        return None

    @property
    def preset_modes(self):
        pms = []
        if self._preset_modes:
            for mk, mv in self._preset_modes.items():
                pms.append(mv)
        if HVACMode.OFF not in pms:
            pms.append(HVACMode.OFF)
        return pms

    def set_preset_mode(self, mode: str):
        if mode == HVACMode.OFF:
            return self.turn_off()
        if not self.is_on:
            self.turn_on(without_modes=True)
        if self._prop_power and mode == self._vars.get('turn_on_hvac'):
            return True
        if not self._prop_mode:
            return False
        val = self._hvac_modes.get(mode, {}).get('value')
        if val is None:
            if self._prop_mode.value_list:
                val = self._prop_mode.list_first(mode)
            elif self._prop_mode.value_range:
                for k, v in self._preset_modes.items():
                    if v != mode:
                        continue
                    try:
                        val = int(k)
                        break
                    except (TypeError, ValueError):
                        val = None
        if val is None:
            return False
        return self.set_property(self._prop_mode, val)

    @property
    def temperature_unit(self):
        prop = self._prop_temperature or self._prop_target_temp
        if prop:
            if prop.unit in ['celsius', UnitOfTemperature.CELSIUS]:
                return UnitOfTemperature.CELSIUS
            if prop.unit in ['fahrenheit', UnitOfTemperature.FAHRENHEIT]:
                return UnitOfTemperature.FAHRENHEIT
            if prop.unit in ['kelvin', UnitOfTemperature.KELVIN]:
                return UnitOfTemperature.KELVIN
        return UnitOfTemperature.CELSIUS

    @property
    def current_temperature(self):
        if self.custom_config('target2current_temp') is True and self.is_on:
            return self.target_temperature
        if ATTR_CURRENT_TEMPERATURE in self._state_attrs:
            return float(self._state_attrs[ATTR_CURRENT_TEMPERATURE] or 0)
        if self._prop_temperature:
            return float(self._prop_temperature.from_dict(self._state_attrs) or 0)
        return None

    @property
    def min_temp(self):
        if self._prop_target_temp:
            return self._prop_target_temp.range_min()
        return DEFAULT_MIN_TEMP

    @property
    def max_temp(self):
        if self._prop_target_temp:
            return self._prop_target_temp.range_max()
        return DEFAULT_MAX_TEMP

    @property
    def target_temperature(self):
        if self._prop_target_temp:
            val = float(self._prop_target_temp.from_dict(self._state_attrs) or 0)
            if val:
                self._prev_target_temp = val
            elif self._prev_target_temp:
                val = self._prev_target_temp
            return val
        return None

    @property
    def target_temperature_step(self):
        if self._prop_target_temp:
            return self._prop_target_temp.range_step()
        return 1

    @property
    def target_temperature_high(self):
        return self.max_temp

    @property
    def target_temperature_low(self):
        return self.min_temp

    def set_temperature(self, **kwargs):
        ret = False
        if ATTR_HVAC_MODE in kwargs:
            ret = self.set_hvac_mode(kwargs[ATTR_HVAC_MODE])
        if ATTR_TEMPERATURE in kwargs:
            val = kwargs[ATTR_TEMPERATURE]
            if val < self.min_temp:
                val = self.min_temp
            if val > self.max_temp:
                val = self.max_temp
            stp = self.target_temperature_step
            if stp is not None and stp >= 1:
                val = int(round(val / stp) * stp)
            ret = self.set_property(self._prop_target_temp, val)
            if ret:
                self._prev_target_temp = val
        return ret

    @property
    def current_humidity(self):
        if ATTR_CURRENT_HUMIDITY in self._state_attrs:
            return float(self._state_attrs[ATTR_CURRENT_HUMIDITY] or 0)
        if self._prop_humidity:
            return int(self._prop_humidity.from_dict(self._state_attrs) or 0)
        return None

    @property
    def target_humidity(self):
        if self._prop_target_humi:
            return int(self._prop_target_humi.from_dict(self._state_attrs) or 0)
        return None

    @property
    def min_humidity(self):
        if self._prop_target_humi:
            return self._prop_target_humi.range_min()
        return DEFAULT_MIN_HUMIDITY

    @property
    def max_humidity(self):
        if self._prop_target_humi:
            return self._prop_target_humi.range_max()
        return DEFAULT_MAX_HUMIDITY

    def set_humidity(self, humidity):
        if self._prop_target_humi:
            return self.set_property(self._prop_target_humi, humidity)
        return False

    @property
    def fan_mode(self):
        des = None
        if self._prop_fan_level:
            val = self._prop_fan_level.from_dict(self._state_attrs)
            if val is not None:
                des = self._prop_fan_level.list_description(val)
            if des is not None:
                des = f'{des}'.lower()
        return des

    @property
    def fan_modes(self):
        if self._prop_fan_level:
            return [
                f'{des}'.lower()
                for des in self._prop_fan_level.list_description(None) or []
            ]
        return None

    def set_fan_mode(self, fan_mode: str):
        if not self.is_on and HVACMode.FAN_ONLY in self._hvac_modes:
            self.set_hvac_mode(HVACMode.FAN_ONLY)
        if self._prop_fan_level:
            val = self._prop_fan_level.list_value(fan_mode)
            return self.set_property(self._prop_fan_level, val)
        return False

    @property
    def swing_mode(self):
        val = 0
        pvs = self._prop_vertical_swing
        phs = self._prop_horizontal_swing
        if pvs and pvs.from_dict(self._state_attrs, False):
            val |= 1
        if phs and phs.from_dict(self._state_attrs, False):
            val |= 2
        return SwingModes(val).name

    @property
    def swing_modes(self):
        lst = [SwingModes(0).name]
        pvs = self._prop_vertical_swing
        phs = self._prop_horizontal_swing
        if pvs:
            lst.append(SwingModes(1).name)
        if phs:
            lst.append(SwingModes(2).name)
        if pvs and phs:
            lst.append(SwingModes(3).name)
        return lst

    def set_swing_mode(self, swing_mode: str):
        ret = None
        ver = None
        hor = None
        val = SwingModes[swing_mode].value
        if val & 1:
            ver = True
            if val == 1:
                hor = False
        if val & 2:
            hor = True
            if val == 2:
                ver = False
        if val == 0:
            ver = False
            hor = False
        swm = {}
        if self._prop_vertical_swing:
            swm[self._prop_vertical_swing.full_name] = ver
        if self._prop_horizontal_swing:
            swm[self._prop_horizontal_swing.full_name] = hor
        for mk, mv in swm.items():
            old = self._state_attrs.get(mk, None)
            if old is None or mv is None:
                continue
            if mv == old:
                continue
            ret = self.set_property(mk, mv)
        return ret

    @property
    def is_aux_heat(self):
        """Return true if aux heater."""
        if self._prop_heater:
            return self._prop_heater.from_dict(self._state_attrs) and self.hvac_mode in [
                HVACMode.AUTO,
                HVACMode.HEAT,
                HVACMode.HEAT_COOL,
            ]
        raise NotImplementedError

    def turn_aux_heat_on(self):
        """Turn auxiliary heater on."""
        if self._prop_heater:
            return self.set_property(self._prop_heater, True)
        return False

    def turn_aux_heat_off(self):
        """Turn auxiliary heater off."""
        if self._prop_heater:
            return self.set_property(self._prop_heater, False)
        return False


class ClimateModeSubEntity(MiotModesSubEntity):
    def __init__(self, parent: MiotClimateEntity, miot_property: MiotProperty, option=None):
        super().__init__(parent, miot_property, option)
        self._prop_power = None
        if miot_property.format == 'bool':
            self._prop_power = miot_property
        self._value_on = self._option.get('value_on')
        self._value_off = self._option.get('value_off')

        self._prop_speed = self._option.get('prop_speed')
        if miot_property.name in ['heater']:
            self._prop_speed = miot_property.service.get_property('heat_level') or self._prop_speed
        if self._prop_speed:
            self._option['keys'] = [self._prop_speed.full_name, *(self._option.get('keys') or [])]

        self._supported_features = 0
        if self.speed_list:
            self._supported_features |= FanEntityFeature.PRESET_MODE

    def update(self, data=None):
        super().update(data)
        if self._available:
            attrs = self._state_attrs
            if self._value_on is not None:
                self._state = attrs.get(self._attr) == self._value_on
            else:
                self._state = attrs.get(self._attr) and True

    def turn_on(self, speed=None, percentage=None, preset_mode=None, **kwargs):
        ret = False
        if self._prop_power:
            ret = self.call_parent('set_property', self._prop_power.full_name, True)
        elif self._value_on is not None:
            ret = self.call_parent('set_property', self._miot_property.full_name, self._value_on)
        if speed:
            ret = self.set_speed(speed)
        return ret

    def turn_off(self, **kwargs):
        if self._prop_power:
            return self.call_parent('set_property', self._prop_power.full_name, False)
        if self._value_off is not None:
            return self.call_parent('set_property', self._miot_property.full_name, self._value_off)
        return False

    @property
    def preset_mode(self):
        if self._prop_speed:
            val = self._prop_speed.from_dict(self._state_attrs)
            if val is not None:
                return self._prop_speed.list_description(val)
        return self._parent.fan_mode

    @property
    def preset_modes(self):
        if self._prop_speed:
            return self._prop_speed.list_descriptions()
        return self._parent.fan_modes or []

    def set_preset_mode(self, preset_mode):
        if self._prop_speed:
            val = self._prop_speed.list_first(preset_mode)
            return self.call_parent('set_property', self._prop_speed.full_name, val)
        return self.call_parent('set_fan_mode', preset_mode)


class MiirClimateEntity(BaseClimateEntity, RestoreEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(miot_service, config=config, logger=_LOGGER)
        self._available = True

        self._act_turn_on = miot_service.get_action('turn_on')
        self._act_turn_off = miot_service.get_action('turn_off')

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

    def turn_on(self, **kwargs):
        """Turn the entity on."""
        if not self._act_turn_on:
            raise NotImplementedError()
        if ret := self.call_action(self._act_turn_on):
            self._attr_hvac_mode = HVACMode.AUTO
        return ret

    def turn_off(self, **kwargs):
        """Turn the entity off."""
        if not self._act_turn_off:
            raise NotImplementedError()
        if ret := self.call_action(self._act_turn_off):
            self._attr_hvac_mode = HVACMode.OFF
        return ret

    def set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        if hvac_mode == HVACMode.OFF:
            return self.turn_off()
        if not self._prop_mode:
            raise NotImplementedError()
        val = self._hvac_modes.get(hvac_mode, {}).get('value')
        if val is None:
            return False
        if ret := self.set_property(self._prop_mode, val):
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

    def set_temperature(self, **kwargs):
        """Set new target temperature."""
        if ATTR_HVAC_MODE in kwargs:
            try:
                self.set_hvac_mode(kwargs[ATTR_HVAC_MODE])
            except (Exception, NotImplementedError):
                pass
        if not self._prop_temperature:
            raise NotImplementedError()
        ret = False
        if ATTR_TEMPERATURE in kwargs:
            val = kwargs.get(ATTR_TEMPERATURE)
            if ret := self.set_property(self._prop_temperature, val):
                self._attr_target_temperature = val
        return ret

    def set_fan_mode(self, fan_mode):
        """Set new target fan mode."""
        if not self._attr_fan_modes:
            raise NotImplementedError()
        ret = False
        if act := self._fan_modes.get(fan_mode):
            ret = self.call_action(act)
        return ret
