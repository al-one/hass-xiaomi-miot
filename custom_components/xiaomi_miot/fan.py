"""Support for Xiaomi fans."""
import logging

from homeassistant.const import *  # noqa: F401
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
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    MiotToggleEntity,
    ToggleSubEntity,
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

try:
    # hass 2021.3.0b0+
    from homeassistant.components.fan import SUPPORT_PRESET_MODE
except ImportError:
    SUPPORT_PRESET_MODE = None

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    await async_setup_config_entry(hass, config_entry, async_setup_platform, async_add_entities, ENTITY_DOMAIN)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data.setdefault(DATA_KEY, {})
    hass.data[DOMAIN]['add_entities'][ENTITY_DOMAIN] = async_add_entities
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
        super().__init__(miot_service, config=config)

        self._prop_power = miot_service.get_property('on', 'dryer')
        self._prop_speed = miot_service.get_property('fan_level', 'drying_level')
        self._prop_mode = miot_service.get_property('mode')
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

        self._prop_percentage = None
        for s in miot_service.spec.get_services():
            for p in s.get_properties('speed_level', 'wind_speed'):
                if not p.value_range:
                    continue
                self._prop_percentage = p
                break

        if self._prop_speed:
            self._supported_features |= SUPPORT_SET_SPEED
        if self._prop_direction:
            self._supported_features |= SUPPORT_DIRECTION
        if self._prop_oscillate:
            self._supported_features |= SUPPORT_OSCILLATE
        if self._prop_mode and SUPPORT_PRESET_MODE:
            self._supported_features |= SUPPORT_PRESET_MODE

        self._state_attrs.update({'entity_class': self.__class__.__name__})

    def turn_on(self, speed=None, percentage=None, preset_mode=None, **kwargs):
        ret = False
        if not self.is_on:
            ret = self.set_property(self._prop_power.full_name, True)
        if self._prop_percentage:
            if not percentage and speed:
                percentage = ordered_list_item_to_percentage(self.speed_list, speed)
            if percentage:
                ret = self.set_property(self._prop_percentage.full_name, percentage)
        elif self._prop_speed:
            if not speed and percentage:
                speed = percentage_to_ordered_list_item(self.speed_list, percentage)
            val = self._prop_speed.list_first(speed) if speed else None
            if val is not None:
                ret = self.set_property(self._prop_speed.full_name, val)
        if preset_mode and self._prop_mode:
            val = self._prop_mode.list_first(preset_mode)
            if val is not None:
                ret = self.set_property(self._prop_mode.full_name, val)
        return ret

    @property
    def speed(self):
        if not self.is_on:
            return SPEED_OFF
        if self._prop_speed:
            spd = int(self._prop_speed.from_dict(self._state_attrs, 0))
            return self._prop_speed.list_description(spd)
        return None

    @property
    def speed_list(self):
        lst = []
        if self._prop_speed:
            lst = self._prop_speed.list_descriptions()
            if self._prop_speed.list_first(SPEED_OFF) is None:
                lst = [SPEED_OFF, *lst]
        return lst

    def set_speed(self, speed):
        return self.turn_on(speed=speed)

    @property
    def speed_count(self):
        """Return the number of speeds the fan supports."""
        if self._prop_percentage:
            return round(self._prop_percentage.range_max() / self._prop_percentage.range_step())
        return super().speed_count

    @property
    def percentage(self):
        """Return the current speed as a percentage."""
        if self._prop_percentage:
            return self._prop_percentage.from_dict(self._state_attrs)
        try:
            return super().percentage
        except ValueError:
            return None

    @property
    def percentage_step(self):
        """Return the step size for percentage."""
        if self._prop_percentage:
            return self._prop_percentage.range_step()
        return round(super().percentage_step)

    def set_percentage(self, percentage: int):
        """Set the speed of the fan, as a percentage."""
        return self.turn_on(percentage=percentage)

    @property
    def preset_mode(self):
        """Return the current preset mode, e.g., auto, smart, interval, favorite."""
        if self._prop_mode:
            val = self._prop_mode.from_dict(self._state_attrs)
            if val is not None:
                return self._prop_mode.list_description(val)
        return None

    @property
    def preset_modes(self):
        """Return a list of available preset modes."""
        lst = []
        if self._prop_mode:
            lst = self._prop_mode.list_descriptions()
        return lst

    def set_preset_mode(self, preset_mode: str):
        """Set new preset mode."""
        return self.turn_on(preset_mode=preset_mode)

    @property
    def current_direction(self):
        num = int(self._state_attrs.get(self._prop_direction.full_name) or 0)
        vls = [-1]
        if self._prop_direction.value_list:
            vls = [
                int(v.get('value'))
                for v in self._prop_direction.value_list
                if v.get('value')
            ]
        elif self._prop_direction.value_range:
            vls = [
                self._prop_direction.range_min(),
                self._prop_direction.range_max(),
            ]
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

    def turn_on(self, speed=None, percentage=None, preset_mode=None, **kwargs):
        ret = False
        if not self.is_on:
            ret = self.call_parent('turn_on', **kwargs)
        if speed:
            ret = self.set_speed(speed)
        return ret

    @property
    def percentage(self):
        """Return the current speed as a percentage."""
        try:
            return super().percentage
        except ValueError:
            return None

    @property
    def percentage_step(self):
        """Return the step size for percentage."""
        return round(super().percentage_step)

    def set_percentage(self, percentage: int):
        """Set the speed of the fan, as a percentage."""
        return False

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
        self._name = self.format_name_by_property(miot_property)
        self._miot_property = miot_property
        self._miot_service = miot_property.service
        self._prop_power = self._option.get('power_property')
        if self._prop_power:
            self._option['keys'] = [self._prop_power.full_name, *(self._option.get('keys') or [])]
        if self._miot_property.value_range and self.modes_count > 20:
            self._supported_features |= SUPPORT_SET_SPEED
        else:
            self._supported_features |= SUPPORT_PRESET_MODE or SUPPORT_SET_SPEED

    @property
    def icon(self):
        if self._miot_property.name in ['heat_level']:
            if self._miot_property.service.name in ['seat']:
                return 'mdi:car-seat-heater'
            return 'mdi:radiator'
        if self._miot_property.name in ['washing_strength']:
            return 'mdi:waves'
        if self._miot_property.name in ['nozzle_position']:
            return 'mdi:spray'
        if self._miot_property.name in ['mode']:
            return 'mdi:menu'
        return super().icon

    @property
    def is_on(self):
        if self._prop_power:
            return self._prop_power.from_dict(self._state_attrs) and True
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
        if self._miot_property.value_range:
            return round(sta) > self._miot_property.range_min()
        return True

    def turn_on(self, speed=None, percentage=None, preset_mode=None, **kwargs):
        ret = False
        if self._prop_power:
            ret = self.call_parent('set_property', self._prop_power.full_name, True)
        else:
            if not self._parent.is_on:
                ret = self.call_parent('turn_on', **kwargs)
        if percentage is not None:
            ret = self.set_percentage(percentage)
        elif speed:
            ret = self.set_speed(speed)
        if preset_mode:
            ret = self.set_preset_mode(preset_mode)
        return ret

    def turn_off(self, **kwargs):
        if self._prop_power:
            return self.call_parent('set_property', self._prop_power.full_name, True)
        return self.call_parent('turn_off', **kwargs)

    @property
    def speed(self):
        return self.preset_mode

    @property
    def speed_list(self):
        return self.preset_modes

    def set_speed(self, speed: str):
        return self.set_preset_mode(speed)

    @property
    def percentage(self):
        """Return the current speed as a percentage."""
        if self._miot_property.value_range:
            val = self._miot_property.from_dict(self._state_attrs)
            if val is not None:
                return round(val / self._miot_property.range_max() * 100, 2)
        return super().percentage

    @property
    def percentage_step(self):
        """Return the step size for percentage."""
        if self._miot_property.value_range:
            stp = self._miot_property.range_step()
            return round(stp / self._miot_property.range_max() * 100, 2)
        return super().percentage_step

    def set_percentage(self, percentage: int):
        """Set the speed of the fan, as a percentage."""
        if self._miot_property.value_range:
            stp = self._miot_property.range_step()
            top = self._miot_property.range_max()
            val = round(top * (percentage / 100) / stp) * stp
            return self.call_parent('set_property', self._miot_property.full_name, val)
        return False

    @property
    def preset_mode(self):
        val = self._miot_property.from_dict(self._state_attrs)
        if val is not None:
            return self._miot_property.list_description(val)
        return None

    @property
    def preset_modes(self):
        """Return a list of available preset modes."""
        if self._supported_features & SUPPORT_PRESET_MODE:
            return self._miot_property.list_descriptions()
        return None

    def set_preset_mode(self, preset_mode: str):
        if self._miot_property.value_range:
            stp = self._miot_property.range_step()
            try:
                val = round(float(preset_mode) / stp) * stp
            except ValueError as exc:
                val = None
                _LOGGER.warning('Switch mode: %s to %s failed: %s', preset_mode, self.name, exc)
        else:
            val = self._miot_property.list_first(preset_mode)
        if val is not None:
            return self.call_parent('set_property', self._miot_property.full_name, val)
        return False

    @property
    def modes_count(self):
        if self._miot_property.value_range:
            return int(self._miot_property.range_max() / self._miot_property.range_step())
        if self._miot_property.value_list:
            return len(self._miot_property.value_list)
        return 0


class MiotCookerSubEntity(MiotModesSubEntity):
    def __init__(self, parent, miot_property: MiotProperty, prop_status: MiotProperty, option=None):
        super().__init__(parent, miot_property, option)
        if not miot_property.readable:
            self._attr = prop_status.full_name
        self._prop_status = prop_status
        self._option['keys'] = [prop_status.full_name, *(self._option.get('keys') or [])]
        self._values_on = self._option.get('values_on') or []
        self._values_off = self._option.get('values_off') or []

    @property
    def is_on(self):
        return self._parent.is_on

    def set_preset_mode(self, preset_mode: str):
        if not self._miot_property.writeable:
            ret = False
            act = self._miot_service.get_action('start_cook')
            val = self._miot_property.list_first(preset_mode)
            if act and val is not None:
                ret = self.call_parent('miot_action', self._miot_service.iid, act.iid, [val])
                sta = self._values_on[0] if self._values_on else None
                if ret and sta is not None:
                    self.update_attrs({
                        self._prop_status.full_name: sta,
                        self._attr: val,
                    })
            return ret
        return super().set_preset_mode(preset_mode)


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
