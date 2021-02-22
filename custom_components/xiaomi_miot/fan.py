"""Support for Xiaomi fans."""
import logging

from homeassistant.const import *
from homeassistant.components.fan import (
    DOMAIN as ENTITY_DOMAIN,
    FanEntity,
    SUPPORT_SET_SPEED,
    SUPPORT_DIRECTION,
    SUPPORT_OSCILLATE,
    SPEED_OFF,
    DIRECTION_FORWARD,
    DIRECTION_REVERSE,
)

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    MiotDevice,
    MiotToggleEntity,
    ToggleSubEntity,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
    MiotProperty,
)

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'

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
    if model.find('mrbond.airer') >= 0:
        pass
    else:
        miot = config.get('miot_type')
        if miot:
            spec = await MiotSpec.async_from_type(hass, miot)
            for srv in spec.get_services(ENTITY_DOMAIN, 'ceiling_fan', 'hood', 'airer'):
                if srv.name in ['airer'] and not srv.get_property('dryer'):
                    continue
                elif not srv.get_property('on'):
                    continue
                cfg = {
                    **config,
                    'name': f"{config.get('name')} {srv.description}"
                }
                entities.append(MiotFanEntity(cfg, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotFanEntity(MiotToggleEntity, FanEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        name = config[CONF_NAME]
        host = config[CONF_HOST]
        token = config[CONF_TOKEN]
        _LOGGER.info('Initializing %s with host %s (token %s...)', name, host, token[:5])

        mapping = miot_service.spec.services_mapping(
            ENTITY_DOMAIN, 'fan_control', 'yl_fan', 'off_delay_time',
            'indicator_light', 'environment',
            'motor_controller', 'physical_controls_locked',
            'stove', 'bluetooth', 'function',
        ) or {}
        mapping.update(miot_service.mapping())
        self._device = MiotDevice(mapping, host, token)
        super().__init__(name, self._device, miot_service, config=config)
        self._add_entities = config.get('add_entities') or {}

        self._prop_power = miot_service.get_property('on', 'dryer')
        self._prop_speed = miot_service.get_property('fan_level', 'drying_level')
        self._prop_direction = miot_service.get_property('horizontal_angle', 'vertical_angle')
        self._prop_oscillate = miot_service.get_property('horizontal_swing', 'vertical_swing')

        self._fan_control = miot_service.spec.get_service('fan_control')
        if self._fan_control:
            if not self._prop_speed:
                self._prop_speed = self._fan_control.get_property('fan_level')
            if not self._prop_direction:
                self._prop_direction = self._fan_control.get_property('horizontal_angle', 'vertical_angle')
            if not self._prop_oscillate:
                self._prop_oscillate = self._fan_control.get_property('horizontal_swing', 'vertical_swing')

        if self._prop_speed:
            self._supported_features |= SUPPORT_SET_SPEED
        if self._prop_direction:
            self._supported_features |= SUPPORT_DIRECTION
        if self._prop_oscillate:
            self._supported_features |= SUPPORT_OSCILLATE

        self._state_attrs.update({'entity_class': self.__class__.__name__})

    def turn_on(self, speed=None, **kwargs):
        ret = False
        if not self.is_on:
            ret = self.set_property(self._prop_power.full_name, True)
        if speed:
            ret = self.set_speed(speed)
        return ret

    @property
    def speed(self):
        if not self.is_on:
            return SPEED_OFF
        spd = int(self._state_attrs.get(self._prop_speed.full_name, 0))
        for s in self._prop_speed.value_list:
            if spd == s.get('value'):
                return s.get('description')
        return SPEED_OFF

    @property
    def speed_list(self):
        lst = [
            s.get('description')
            for s in self._prop_speed.value_list
            if isinstance(s, dict) and 'description' in s
        ]
        return [SPEED_OFF, *lst]

    def set_speed(self, speed):
        spd = None
        for s in self._prop_speed.value_list:
            if speed == s.get('description'):
                spd = int(s.get('value', 0))
                break
        if spd is not None:
            _LOGGER.debug('Setting speed to %s: %s(%s)', self.name, speed, spd)
            return self.set_property(self._prop_speed.full_name, spd)
        _LOGGER.info('Setting speed to %s failed: %s(%s)', self.name, speed, spd)
        return False

    @property
    def current_direction(self):
        num = int(self._state_attrs.get(self._prop_direction.full_name) or 0)
        vls = [
            int(v.get('value'))
            for v in self._prop_direction.value_list
            if v.get('value')
        ] or [-1]
        if num <= min(vls):
            return DIRECTION_REVERSE
        if num >= max(vls):
            return DIRECTION_FORWARD
        return None

    def set_direction(self, direction):
        num = int(self._state_attrs.get(self._prop_direction.full_name) or 0)
        for v in self._prop_direction.value_list:
            n = int(v.get('value') or -1)
            if n < 0:
                continue
            if direction == DIRECTION_REVERSE:
                if n < num:
                    num = n
            else:
                if n > num:
                    num = n
        _LOGGER.debug('Setting direction to %s: %s(%s)', self.name, direction, num)
        return self.set_property(self._prop_direction.full_name, num)

    @property
    def oscillating(self):
        return self._state_attrs.get(self._prop_oscillate.full_name) and True

    def oscillate(self, oscillating: bool):
        return self.set_property(self._prop_oscillate.full_name, oscillating)


class FanSubEntity(ToggleSubEntity, FanEntity):

    def turn_on(self, speed=None, **kwargs):
        ret = False
        if not self.is_on:
            ret = self.call_parent('turn_on', **kwargs)
        if speed:
            ret = self.set_speed(speed)
        return ret

    @property
    def speed(self):
        return self._state_attrs.get(self._attr)

    @property
    def speed_list(self):
        return list(self._option.get('speed_list') or [])

    def set_speed(self, speed: str):
        self.call_parent('set_speed', speed)

    def set_direction(self, direction: str):
        self.call_parent('set_direction', direction)

    def oscillate(self, oscillating: bool):
        self.call_parent('oscillate', oscillating)


class MiotModesSubEntity(FanSubEntity):
    def __init__(self, parent, miot_property: MiotProperty, option=None):
        super().__init__(parent, miot_property.full_name, option)
        self._miot_property = miot_property
        self._miot_service = miot_property.service
        self._supported_features = SUPPORT_SET_SPEED

    @property
    def icon(self):
        if self._miot_property.name in ['mode']:
            return 'mdi:menu'
        return super().icon

    @property
    def is_on(self):
        if self._parent.is_on is False:
            return False
        sta = self._state_attrs.get(self._attr)
        if sta is not None:
            tvs = self._option.get('values_on')
            fvs = self._option.get('values_off')
            if tvs and isinstance(tvs, list):
                return sta in self._miot_property.list_search(*tvs)
            if fvs and isinstance(fvs, list):
                return sta not in self._miot_property.list_search(*fvs)
        return True

    def turn_on(self, speed=None, **kwargs):
        ret = False
        if not self._parent.is_on:
            ret = self.call_parent('turn_on', **kwargs)
        if speed:
            ret = self.set_speed(speed)
        return ret

    @property
    def speed(self):
        val = self._miot_property.from_dict(self._state_attrs)
        return self._miot_property.list_description(val)

    @property
    def speed_list(self):
        return self._miot_property.list_description(None)

    def set_speed(self, speed: str):
        val = self._miot_property.list_first(speed)
        if val is not None:
            return self.call_parent('set_property', self._miot_property.full_name, val)
        return False


class MiotCookerSubEntity(MiotModesSubEntity):
    def __init__(self, parent, miot_property: MiotProperty, prop_status: MiotProperty, option=None):
        super().__init__(parent, miot_property, option)
        self._prop_status = prop_status
        self._option['keys'] = [prop_status.full_name, *(self._option.get('keys') or [])]
        self._values_on = self._option.get('values_on') or []
        self._values_off = self._option.get('values_off') or []

    @property
    def is_on(self):
        return self._parent.is_on

    def set_speed(self, speed: str):
        if not self._miot_property.writeable:
            ret = False
            act = self._miot_service.get_action('start_cook')
            val = self._miot_property.list_first(speed)
            if act and val is not None:
                ret = self.call_parent('miot_action', self._miot_service.iid, act.iid, [val])
                sta = self._values_on[0] if self._values_on else None
                if ret and sta is not None:
                    self.update_attrs({
                        self._prop_status.full_name: sta,
                        self._attr: val,
                    })
            return ret
        return super().set_speed(speed)


class MiotWasherSubEntity(MiotModesSubEntity):

    @property
    def icon(self):
        if self._miot_property.name in ['spin_speed']:
            return 'mdi:speedometer'
        if self._miot_property.name in ['target_temperature']:
            return 'mdi:coolant-temperature'
        if self._miot_property.name in ['target_water_level']:
            return 'mdi:water-plus'
        if self._miot_property.name in ['drying_level']:
            return 'mdi:tumble-dryer'
        return super().icon

    @property
    def is_on(self):
        if not self._parent.is_on:
            return False
        sta = self._state_attrs.get(self._attr)
        if self._miot_property.name in ['spin_speed']:
            return sta not in self._miot_property.list_search('no spin')
        if self._miot_property.name in ['target_temperature']:
            return sta not in self._miot_property.list_search('cold')
        if self._miot_property.name in ['drying_level']:
            return sta not in self._miot_property.list_search('none')
        return True
