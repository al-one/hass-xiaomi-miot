"""Support for Xiaomi fans."""
import logging

from homeassistant.components.fan import (
    DOMAIN as ENTITY_DOMAIN,
    FanEntity as BaseEntity,
    FanEntityFeature,
    DIRECTION_FORWARD,
    DIRECTION_REVERSE,
)

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    HassEntry,
    XEntity,
    MiotToggleEntity,
    MiirToggleEntity,
    MiotPropertySubEntity,
    ToggleSubEntity,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
    MiotProperty,
)
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
    ranged_value_to_percentage,
    percentage_to_ranged_value,
)

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'
SERVICE_TO_METHOD = {}

SPEED_OFF = 'off'
OFF_SPEED_VALUES = [SPEED_OFF, None]


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
        for srv in spec.get_services('ir_fan_control'):
            entities.append(MiirFanEntity(config, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class FanEntity(XEntity, BaseEntity):
    _attr_device_class = None
    _conv_power = None
    _conv_mode = None
    _conv_speed = None
    _speed_list = None
    _speed_range = None
    _conv_oscillate = None
    _prop_speed = None
    _prop_percentage = None

    def on_init(self):
        if self._miot_service:
            if prop := self.custom_config('speed_property'):
                self._prop_speed = self._miot_service.spec.get_property(prop)
                if self._prop_speed:
                    self._speed_list = self._prop_speed.list_descriptions()
                    self._attr_supported_features |= FanEntityFeature.SET_SPEED
            if prop := self.custom_config('percentage_property'):
                self._prop_percentage = self._miot_service.spec.get_property(prop)
                if self._prop_percentage:
                    self._attr_supported_features |= FanEntityFeature.SET_SPEED

        for attr in self.conv.attrs:
            conv = self.device.find_converter(attr)
            prop = getattr(conv, 'prop', None) if conv else None
            if not isinstance(prop, MiotProperty):
                continue
            elif prop.in_list(['on']):
                self._conv_power = conv
                self._attr_supported_features |= FanEntityFeature.TURN_ON
                self._attr_supported_features |= FanEntityFeature.TURN_OFF
            elif prop.in_list(['mode']):
                self._conv_mode = conv
                self._attr_preset_modes = prop.list_descriptions()
                self._attr_supported_features |= FanEntityFeature.PRESET_MODE
            elif prop.in_list(['fan_level', 'speed_level']):
                if prop.value_range:
                    _min = prop.range_min()
                    _max = prop.range_max()
                    _stp = prop.range_step()
                    self._speed_range = (_min, _max)
                    self._attr_speed_count = (_max - _min) / _stp + 1
                    self._attr_supported_features |= FanEntityFeature.SET_SPEED
                elif prop.value_list and not self._conv_speed:
                    self._speed_list = prop.list_descriptions()
                    self._attr_speed_count = len(prop.value_list)
                    self._attr_extra_state_attributes['speed_list'] = self._speed_list
                else:
                    continue
                self._conv_speed = conv
                self._attr_supported_features |= FanEntityFeature.SET_SPEED
            elif prop.in_list(['horizontal_swing', 'vertical_swing']) and not self._conv_oscillate:
                self._conv_oscillate = conv
                self._attr_supported_features |= FanEntityFeature.OSCILLATE

        # issues/617
        if self.custom_config_bool('disable_preset_modes'):
            self._supported_features &= ~FanEntityFeature.PRESET_MODE
            self._attr_preset_modes = []
        elif dpm := self.custom_config_list('disable_preset_modes'):
            self._attr_preset_modes = [
                mode
                for mode in self._attr_preset_modes
                if mode not in dpm
            ]

    def set_state(self, data: dict):
        if self._conv_speed:
            val = self._conv_speed.value_from_dict(data)
            if val is not None:
                des = self._conv_speed.prop.list_description(val)
                if self._speed_range:
                    self._attr_percentage = ranged_value_to_percentage(self._speed_range, val)
                elif self._speed_list and des in self._speed_list:
                    self._attr_percentage = ordered_list_item_to_percentage(self._speed_list, des)
        if self._prop_speed:
            val = self._prop_speed.from_device(self.device)
            if val is not None:
                des = self._prop_speed.list_description(val)
                self._attr_percentage = ordered_list_item_to_percentage(self._speed_list, des)
        if self._prop_percentage:
            val = self._prop_percentage.from_device(self.device)
            if val is not None:
                self._attr_percentage = val
        if self._conv_power:
            val = self._conv_power.value_from_dict(data)
            if val is not None:
                self._attr_is_on = bool(val)
                if not self._attr_is_on:
                    self._attr_percentage = 0
        if self._conv_mode:
            val = self._conv_mode.value_from_dict(data)
            if val is not None:
                self._attr_preset_mode = val
        if self._conv_oscillate:
            val = self._conv_oscillate.value_from_dict(data)
            if val is not None:
                self._attr_oscillating = bool(val)

    @property
    def is_on(self):
        if self._conv_power:
            return self._attr_is_on
        return self.percentage is not None and self.percentage > 0

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs):
        dat = {}
        if self._conv_power and not self.is_on:
            dat[self._conv_power.attr] = True
        if percentage is not None:
            if self._prop_percentage:
                await self.device.async_set_property(self._prop_percentage, percentage)
            elif self._prop_speed:
                des = percentage_to_ordered_list_item(self._speed_list, percentage)
                val = self._prop_speed.list_value(des)
                if val is not None:
                    await self.device.async_set_property(self._prop_speed, val)
            elif self._speed_range:
                dat[self._conv_speed.attr] = percentage_to_ranged_value(self._speed_range, percentage)
            elif self._speed_list:
                des = percentage_to_ordered_list_item(self._speed_list, percentage)
                dat[self._conv_speed.attr] = self._conv_speed.prop.list_value(des)
        if preset_mode is not None:
            dat[self._conv_mode.attr] = preset_mode
        if dat:
            await self.device.async_write(dat)

    async def async_turn_off(self, **kwargs):
        if not self._conv_power:
            return
        await self.device.async_write({self._conv_power.attr: False})

    async def async_set_percentage(self, percentage: int):
        if percentage == 0 and self._conv_power:
            await self.async_turn_off()
            return
        await self.async_turn_on(percentage=percentage)

    async def async_set_preset_mode(self, preset_mode: str):
        if not self._conv_mode:
            return
        await self.device.async_write({self._conv_mode.attr: preset_mode})

    async def async_oscillate(self, oscillating: bool):
        if not self._conv_oscillate:
            return
        await self.device.async_write({self._conv_oscillate.attr: oscillating})

XEntity.CLS[ENTITY_DOMAIN] = FanEntity


class MiotFanEntity(MiotToggleEntity, BaseEntity):
    def __init__(self, config: dict, miot_service: MiotService, **kwargs):
        kwargs.setdefault('logger', _LOGGER)
        super().__init__(miot_service, config=config, **kwargs)

        self._prop_power = miot_service.get_property('on', 'dryer')
        self._prop_speed = miot_service.get_property('fan_level', 'drying_level')
        self._prop_mode = miot_service.get_property('mode')
        self._prop_direction = miot_service.get_property('horizontal_angle', 'vertical_angle')
        self._prop_oscillate = miot_service.get_property('horizontal_swing', 'vertical_swing')

        if self._prop_power:
            if hasattr(FanEntityFeature, 'TURN_ON'): # v2024.8
                self._supported_features |= FanEntityFeature.TURN_ON
            if hasattr(FanEntityFeature, 'TURN_OFF'):
                self._supported_features |= FanEntityFeature.TURN_OFF

        self._fan_control = miot_service.spec.get_service('fan_control')
        if self._fan_control:
            if not self._prop_speed:
                self._prop_speed = self._fan_control.get_property('fan_level')
            if not self._prop_direction:
                self._prop_direction = self._fan_control.get_property(
                    'horizontal_swing_included_angle', 'horizontal_angle',
                    'vertical_swing_included_angle', 'vertical_angle',
                )
            if not self._prop_oscillate:
                self._prop_oscillate = self._fan_control.get_property('horizontal_swing', 'vertical_swing')

        self._prop_percentage = None
        for s in miot_service.spec.get_services():
            for p in s.get_properties('speed_level', 'wind_speed', 'fan_level'):
                if not p.value_range:
                    continue
                if p.range_max() < 90:
                    continue
                self._prop_percentage = p
                break

        if self._prop_speed or self._prop_percentage:
            self._supported_features |= FanEntityFeature.SET_SPEED
            if self._prop_speed and self._prop_percentage:
                if self._prop_speed.unique_name == self._prop_percentage.unique_name:
                    self._prop_speed = None
        if self._prop_direction:
            self._supported_features |= FanEntityFeature.DIRECTION
        if self._prop_oscillate:
            self._supported_features |= FanEntityFeature.OSCILLATE

        self._attr_preset_modes = []
        if self._prop_mode:
            self._supported_features |= FanEntityFeature.PRESET_MODE
            self._attr_preset_modes = self._prop_mode.list_descriptions()

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if spd := self.custom_config('speed_property'):
            if prop := self._miot_service.spec.get_property(spd):
                self._prop_speed = prop
                self._supported_features |= FanEntityFeature.SET_SPEED

        if per := self.custom_config('percentage_property'):
            if prop := self._miot_service.spec.get_property(per):
                self._prop_percentage = prop
                self._supported_features |= FanEntityFeature.SET_SPEED

        # issues/617
        if self.custom_config_bool('disable_preset_modes'):
            self._supported_features &= ~FanEntityFeature.PRESET_MODE
            self._attr_preset_modes = []
        elif dpm := self.custom_config_list('disable_preset_modes'):
            self._attr_preset_modes = [
                mode
                for mode in self._attr_preset_modes
                if mode not in dpm
            ]

    def turn_on(self, speed=None, percentage=None, preset_mode=None, **kwargs):
        ret = False
        if not self.is_on and percentage != 0:
            ret = self.set_property(self._prop_power, True)
        if self._prop_percentage:
            if not percentage and speed:
                percentage = ordered_list_item_to_percentage(self.speed_list, speed)
            if percentage:
                ret = self.set_property(self._prop_percentage, percentage)
            elif percentage is not None:
                _LOGGER.warning('%s: Set fan speed percentage failed: %s', self.name_model, {
                    'speed': speed,
                    'percentage': percentage,
                })
        elif self._prop_speed:
            if not speed and percentage:
                speed = percentage_to_ordered_list_item(self.speed_list, percentage)
            val = self._prop_speed.list_first(speed) if speed else None
            if val is None and self._prop_speed.value_range:
                if speed is not None:
                    val = int(speed)
            if val is not None:
                ret = self.set_property(self._prop_speed, val)
            elif speed is not None:
                _LOGGER.warning('%s: Set fan speed level failed: %s', self.name_model, {
                    'speed': speed,
                    'percentage': percentage,
                    'value': val,
                })
        if preset_mode and self._prop_mode:
            val = self._prop_mode.list_first(preset_mode)
            if val is not None:
                ret = self.set_property(self._prop_mode, val)
        return ret

    @property
    def speed(self):
        if not self.is_on:
            return SPEED_OFF
        if self._prop_speed:
            spd = int(self._prop_speed.from_device(self.device, 0))
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
        lst = [v for v in self.speed_list if v not in OFF_SPEED_VALUES]
        return len(lst)

    @property
    def percentage(self):
        """Return the current speed as a percentage."""
        if self._prop_percentage:
            val = self._prop_percentage.from_device(self.device)
            if val is not None:
                return val
        lst = [v for v in self.speed_list if v not in OFF_SPEED_VALUES]
        try:
            return ordered_list_item_to_percentage(lst, self.speed)
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
        if percentage == 0:
            return self.turn_off()
        return self.turn_on(percentage=percentage)

    @property
    def preset_mode(self):
        """Return the current preset mode, e.g., auto, smart, interval, favorite."""
        if self._prop_mode:
            val = self._prop_mode.from_device(self.device)
            if val is not None:
                return self._prop_mode.list_description(val)
        return None

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
        if self._prop_direction.value_range:
            step = self._prop_direction.range_step()
            rmax = self._prop_direction.range_max()
            rmin = self._prop_direction.range_min()
            if step < 10:
                step = 10
            if direction == DIRECTION_REVERSE:
                step = 0 - step
            num += step
            if num > rmax:
                num = rmax
            if num < rmin:
                num = rmin
        else:
            for v in self._prop_direction.value_list:
                n = int(v.get('value', -1))
                if n < 0:
                    continue
                if direction == DIRECTION_REVERSE:
                    if n < num:
                        num = n
                        break
                else:
                    if n > num:
                        num = n
                        break
        _LOGGER.debug('%s: Setting direction: %s(%s)', self.name_model, direction, num)
        return self.set_property(self._prop_direction, num)

    @property
    def oscillating(self):
        return self._state_attrs.get(self._prop_oscillate.full_name) and True

    def oscillate(self, oscillating: bool):
        return self.set_property(self._prop_oscillate, oscillating)


class MiirFanEntity(MiirToggleEntity, FanEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(miot_service, config=config, logger=_LOGGER)

        if self._act_turn_on and hasattr(FanEntityFeature, 'TURN_ON'): # v2024.8
            self._supported_features |= FanEntityFeature.TURN_ON
        if self._act_turn_off and hasattr(FanEntityFeature, 'TURN_OFF'):
            self._supported_features |= FanEntityFeature.TURN_OFF

        self._attr_percentage = 50
        self._act_speed_up = miot_service.get_action('fan_speed_up')
        self._act_speed_dn = miot_service.get_action('fan_speed_down')
        if self._act_speed_up or self._act_speed_dn:
            self._supported_features |= FanEntityFeature.SET_SPEED

        self._act_swing_on = miot_service.get_action('horizontal_swing_on')
        self._act_swing_off = miot_service.get_action('horizontal_swing_off')
        if self._act_swing_on or self._act_swing_off:
            self._supported_features |= FanEntityFeature.OSCILLATE

        self._supported_features |= FanEntityFeature.PRESET_MODE
        self._attr_preset_mode = None
        self._attr_preset_modes = []
        for a in miot_service.actions.values():
            if a.ins:
                continue
            self._attr_preset_modes.append(a.friendly_desc)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # issues/617
        if self.custom_config_bool('disable_preset_modes'):
            self._supported_features &= ~FanEntityFeature.PRESET_MODE
            self._attr_preset_modes = []
        elif dpm := self.custom_config_list('disable_preset_modes'):
            self._attr_preset_modes = [
                mode
                for mode in self._attr_preset_modes
                if mode not in dpm
            ]

    def turn_on(self, percentage=None, preset_mode=None, **kwargs):
        """Turn the entity on."""
        if percentage is None:
            pass
        elif percentage > self._attr_percentage and self._act_speed_up:
            return self.call_action(self._act_speed_up)
        elif percentage < self._attr_percentage and self._act_speed_dn:
            return self.call_action(self._act_speed_dn)

        if preset_mode is None:
            pass
        elif act := self._miot_service.get_action(preset_mode):
            return self.call_action(act)

        return super().turn_on(**kwargs)

    def set_percentage(self, percentage: int):
        """Set the speed of the fan, as a percentage."""
        return self.turn_on(percentage=percentage)

    def set_preset_mode(self, preset_mode):
        """Set new preset mode."""
        return self.turn_on(preset_mode=preset_mode)

    def oscillate(self, oscillating):
        """Oscillate the fan."""
        ret = None
        if not oscillating and self._act_swing_off:
            ret = self.call_action(self._act_swing_off)
        elif oscillating and self._act_swing_on:
            ret = self.call_action(self._act_swing_on)
        if ret:
            self._attr_oscillating = oscillating
        return ret


class MiotFanSubEntity(MiotFanEntity, ToggleSubEntity):
    def __init__(self, parent, miot_service: MiotService, option=None):
        parent_power = None
        prop_power = miot_service.get_property('on')
        if prop_power:
            attr = prop_power.full_name
        else:
            attr = miot_service.desc_name
            for s in miot_service.spec.services.values():
                if p := s.get_property('on'):
                    parent_power = p
                    break
        keys = list((miot_service.mapping() or {}).keys())
        if parent_power:
            keys.append(parent_power.full_name)
        self._fan_control = miot_service.spec.get_service('fan_control')
        if self._fan_control:
            keys.extend(list((self._fan_control.mapping() or {}).keys()))
        ToggleSubEntity.__init__(self, parent, attr, {
            **(option or {}),
            'keys': keys,
        })
        MiotFanEntity.__init__(self, {
            **parent.miot_config,
            'name': f'{parent.device_name}',
        }, miot_service, device=parent.miot_device)

        self.entity_id = miot_service.generate_entity_id(self, domain=ENTITY_DOMAIN)
        self._prop_power = prop_power
        if parent_power:
            self._prop_power = parent_power
            self._available = True

    @property
    def available(self):
        return self._available and self._parent.available

    def update(self, data=None):
        super().update(data)
        if not self._available:
            return

    async def async_update(self):
        await self.hass.async_add_executor_job(self.update)

    def set_property(self, field, value):
        return self.set_parent_property(value, field)


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


class MiotModesSubEntity(MiotPropertySubEntity, FanSubEntity):
    def __init__(self, parent, miot_property: MiotProperty, option=None):
        FanSubEntity.__init__(self, parent, miot_property.full_name, option)
        super().__init__(parent, miot_property, option, domain=ENTITY_DOMAIN)
        self._prop_power = self._option.get('power_property')
        if self._prop_power:
            self._option['keys'] = [self._prop_power.full_name, *(self._option.get('keys') or [])]
        if self._miot_property.value_range and self.modes_count > 20:
            self._supported_features |= FanEntityFeature.SET_SPEED
        else:
            self._supported_features |= FanEntityFeature.PRESET_MODE

    @property
    def icon(self):
        return self._miot_property.entity_icon or super().icon

    def update(self, data=None):
        super().update(data)
        self._miot_property.description_to_dict(self._state_attrs)

    @property
    def is_on(self):
        if self._prop_power:
            return self._prop_power.from_device(self.device) and True
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
            val = self._miot_property.from_device(self.device)
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
        val = self._miot_property.from_device(self.device)
        if val is not None:
            return self._miot_property.list_description(val)
        return None

    @property
    def preset_modes(self):
        """Return a list of available preset modes."""
        if self._supported_features & FanEntityFeature.PRESET_MODE:
            return self._miot_property.list_descriptions()
        return None

    def set_preset_mode(self, preset_mode: str):
        if self._miot_property.value_range:
            stp = self._miot_property.range_step()
            try:
                val = round(float(preset_mode) / stp) * stp
            except ValueError as exc:
                val = None
                _LOGGER.warning('%s: Switch mode: %s failed: %s', self.name_model, preset_mode, exc)
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
