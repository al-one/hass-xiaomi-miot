"""Support for Xiaomi Aircondition."""
import logging
from enum import Enum

from homeassistant.const import *
from homeassistant.components.climate import (
    DOMAIN as ENTITY_DOMAIN,
    ClimateEntity,
)
from homeassistant.components.climate.const import *

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    MiotDevice,
    MiotToggleEntity,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
    MiotProperty,
)
from .switch import SwitchSubEntity

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'

DEFAULT_MIN_TEMP = 16.0
DEFAULT_MAX_TEMP = 31.0
HVAC_MODE_DEFOG = 'defog'

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    config = hass.data[DOMAIN]['configs'].get(config_entry.entry_id, dict(config_entry.data))
    await async_setup_platform(hass, config, async_add_entities)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data.setdefault(DATA_KEY, {})
    config.setdefault('add_entities', {})
    config['add_entities'][ENTITY_DOMAIN] = async_add_entities
    model = str(config.get(CONF_MODEL) or '')
    entities = []
    miot = config.get('miot_type')
    if miot:
        spec = await MiotSpec.async_from_type(hass, miot)
        for srv in spec.get_services(
            ENTITY_DOMAIN, 'air_conditioner', 'air_condition_outlet',
            'air_purifier', 'heater', 'ptc_bath_heater', 'light_bath_heater',
        ):
            if not srv.get_property('on', 'mode'):
                continue
            cfg = {
                **config,
                'name': f"{config.get('name')} {srv.description}"
            }
            entities.append(MiotClimateEntity(cfg, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class SwingModes(Enum):
    Off = 0
    Vertical = 1
    Horizontal = 2
    Steric = 3


class MiotClimateEntity(MiotToggleEntity, ClimateEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        name = config[CONF_NAME]
        host = config[CONF_HOST]
        token = config[CONF_TOKEN]

        self._miot_service = miot_service
        mapping = miot_service.spec.services_mapping(
            'air_conditioner', 'fan_control', 'environment', 'indicator_light',
            'air_purifier', 'filter_time', 'motor_speed', 'aqi', 'rfid', 'physical_controls_locked',
            'electricity', 'maintenance', 'alarm', 'enhance', 'countdown', 'others', 'private_service',
            'power_consumption', 'ac_function', 'device_protect', 'device_info', 'arming',
        ) or {}
        mapping.update(miot_service.mapping())
        _LOGGER.info('Initializing with host %s (token %s...), miot mapping: %s', host, token[:5], mapping)

        self._device = MiotDevice(mapping, host, token)
        super().__init__(name, self._device, miot_service)
        self._add_entities = config.get('add_entities') or {}

        self._prop_power = miot_service.get_property('on')
        self._prop_mode = miot_service.get_property('mode')
        self._prop_target_temp = miot_service.get_property('target_temperature')
        self._prop_target_humi = miot_service.get_property('target_humidity')
        self._prop_fan_level = miot_service.get_property('fan_level')
        self._prop_blow = miot_service.get_property('blow')
        self._prop_heating = miot_service.get_property('heating')
        self._prop_ventilation = miot_service.get_property('ventilation')

        self._environment = miot_service.spec.get_service('environment')
        self._prop_temperature = miot_service.get_property('temperature')
        self._prop_humidity = miot_service.get_property('relative_humidity', 'humidity')
        if self._environment:
            self._prop_temperature = self._environment.get_property('temperature')
            self._prop_humidity = self._environment.get_property('relative_humidity', 'humidity')

        self._fan_control = miot_service.spec.get_service('fan_control')
        self._prop_fan_power = None
        self._prop_horizontal_swing = None
        self._prop_vertical_swing = None
        if self._fan_control:
            self._prop_fan_power = self._fan_control.get_property('on')
            self._prop_fan_level = self._fan_control.get_property('fan_level')
            self._prop_horizontal_swing = self._fan_control.get_property('horizontal_swing')
            self._prop_horizontal_angle = self._fan_control.get_property('horizontal_angle')
            self._prop_vertical_swing = self._fan_control.get_property('vertical_swing')
            self._prop_vertical_angle = self._fan_control.get_property('vertical_angle')

        self._supported_features = 0
        if self._prop_target_temp:
            self._supported_features |= SUPPORT_TARGET_TEMPERATURE
        if self._prop_target_humi:
            self._supported_features |= SUPPORT_TARGET_HUMIDITY
        if self.fan_modes or self._prop_mode.list_first('Fan') is not None:
            self._supported_features |= SUPPORT_FAN_MODE
        if self._prop_horizontal_swing or self._prop_vertical_swing:
            self._supported_features |= SUPPORT_SWING_MODE

        self._state_attrs.update({'entity_class': self.__class__.__name__})
        self._power_modes = ['blow', 'heating', 'ventilation']
        self._hvac_modes = {
            HVAC_MODE_OFF:  ['Off', 'Idle', 'None'],
            HVAC_MODE_AUTO: ['Auto'],
            HVAC_MODE_COOL: ['Cool'],
            HVAC_MODE_HEAT: ['Heat', 'Quick Heat'],
            HVAC_MODE_DRY:  ['Dry'],
            HVAC_MODE_DEFOG: ['Defog', 'Quick Defog'],
            HVAC_MODE_FAN_ONLY: ['Fan'],
        }
        self._subs = {}

    async def async_update(self):
        await super().async_update()
        if self._available:
            add_switches = self._add_entities.get('switch', None)
            for m in self._power_modes:
                p = self._miot_service.bool_property(m)
                if m in self._subs:
                    self._subs[m].update()
                elif add_switches and p:
                    self._subs[m] = ClimateModeSubEntity(self, p)
                    add_switches([self._subs[m]])

    @property
    def is_on(self):
        if self._prop_power:
            return self._state_attrs.get(self._prop_power.full_name) and True
        for m in self._power_modes:
            p = self._miot_service.bool_property(m)
            if not p:
                continue
            if self._state_attrs.get(p.full_name):
                return True
        return None

    def turn_on(self, **kwargs):
        if self._prop_power:
            return self.set_property(self._prop_power.full_name, True)
        for m in self._power_modes:
            p = self._miot_service.bool_property(m)
            if not p:
                continue
            return self.set_property(p.full_name, True)
        if self._prop_fan_power:
            return self.set_property(self._prop_fan_power.full_name, True)
        srv = self._miot_service.spec.get_service('viomi_bath_heater')
        if srv:
            act = srv.get_action('power_on')
            if act:
                return self.miot_action(srv.iid, act.iid)
        for mode in (HVAC_MODE_HEAT_COOL, HVAC_MODE_AUTO, HVAC_MODE_HEAT, HVAC_MODE_COOL):
            if mode not in self.hvac_modes:
                continue
            return self.set_hvac_mode(mode)
        return False

    def turn_off(self, **kwargs):
        if self._prop_power:
            return self.set_property(self._prop_power.full_name, False)
        act = self._miot_service.get_action('stop_working', 'power_off')
        if act:
            return self.miot_action(self._miot_service.iid, act.iid)
        ret = None
        for m in self._power_modes:
            p = self._miot_service.bool_property(m)
            if not p:
                continue
            ret = self.set_property(p.full_name, False)
        if ret is not None:
            return ret
        if self._prop_fan_power:
            return self.set_property(self._prop_fan_power.full_name, False)
        return False

    @property
    def state(self):
        return self.hvac_mode

    @property
    def hvac_mode(self):
        if not self.is_on:
            return HVAC_MODE_OFF
        acm = int(self._prop_mode.from_dict(self._state_attrs) or -1)
        for mk, mv in self._hvac_modes.items():
            if acm in self._prop_mode.list_search(*mv):
                return mk
        return None

    @property
    def hvac_modes(self):
        hms = []
        for mk, mv in self._hvac_modes.items():
            if self._prop_mode.list_search(*mv):
                hms.append(mk)
        if HVAC_MODE_OFF not in hms:
            hms.append(HVAC_MODE_OFF)
        return hms

    def set_hvac_mode(self, hvac_mode: str):
        if hvac_mode == HVAC_MODE_OFF:
            return self.turn_off()
        if not self._prop_mode:
            return False
        val = self._prop_mode.list_first(*(self._hvac_modes.get(hvac_mode) or []))
        if val is None:
            return False
        if self._prop_power:
            return self.set_property(self._prop_power.full_name, True)
        return self.set_property(self._prop_mode.full_name, val)

    @property
    def temperature_unit(self):
        prop = self._prop_temperature or self._prop_target_temp
        if prop:
            if prop.unit in ['celsius', TEMP_CELSIUS]:
                return TEMP_CELSIUS
            if prop.unit in ['fahrenheit', TEMP_FAHRENHEIT]:
                return TEMP_FAHRENHEIT
            if prop.unit in ['kelvin', TEMP_KELVIN]:
                return TEMP_KELVIN
        return None

    @property
    def current_temperature(self):
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
            return float(self._prop_target_temp.from_dict(self._state_attrs) or 0)
        return None

    @property
    def target_temperature_step(self):
        if self._prop_target_temp:
            return self._prop_target_temp.range_step()
        return 1

    @property
    def target_temperature_high(self):
        return DEFAULT_MAX_TEMP

    @property
    def target_temperature_low(self):
        return DEFAULT_MIN_TEMP

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
            ret = self.set_property(self._prop_target_temp.full_name, val)
        return ret

    @property
    def current_humidity(self):
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
            return self.set_property(self._prop_target_humi.full_name, humidity)
        return False

    @property
    def fan_mode(self):
        if self._prop_fan_level:
            val = self._prop_fan_level.from_dict(self._state_attrs)
            if val is not None:
                return self._prop_fan_level.list_description(val)
        return None

    @property
    def fan_modes(self):
        if self._prop_fan_level:
            return self._prop_fan_level.list_description(None) or []
        return None

    def set_fan_mode(self, fan_mode: str):
        if self._prop_fan_level:
            val = self._prop_fan_level.list_value(fan_mode)
            return self.set_property(self._prop_fan_level.full_name, val)
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

    def set_swing_mode(self, swing_mode: str) -> None:
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
            swm[self._prop_vertical_swing.name] = ver
        if self._prop_horizontal_swing:
            swm[self._prop_horizontal_swing.name] = hor
        for mk, mv in swm.items():
            old = self._state_attrs.get(mk, None)
            if old is None or mv is None:
                continue
            if mv == old:
                continue
            ret = self.set_property(mk, mv)
        return ret


class ClimateModeSubEntity(SwitchSubEntity):
    def __init__(self, parent, miot_property: MiotProperty, option=None):
        self._prop_power = miot_property
        super().__init__(parent, miot_property.full_name, option)

    def update(self):
        super().update()
        if self._available:
            attrs = self._state_attrs
            self._state = attrs.get(self._attr) and True

    def turn_on(self, **kwargs):
        if self._prop_power:
            return self._parent.set_property(self._prop_power.full_name, True)
        return False

    def turn_off(self, **kwargs):
        if self._prop_power:
            return self._parent.set_property(self._prop_power.full_name, False)
        return False
