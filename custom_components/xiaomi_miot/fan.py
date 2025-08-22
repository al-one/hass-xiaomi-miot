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
        for attr in self.conv.attrs:
            conv = self.device.find_converter(attr)
            prop = getattr(conv, 'prop', None) if conv else None
            if not isinstance(prop, MiotProperty):
                continue
            elif prop.in_list(['on']):
                self._conv_power = conv
                if hasattr(FanEntityFeature, 'TURN_ON'): # v2024.8
                    self._attr_supported_features |= FanEntityFeature.TURN_ON
                if hasattr(FanEntityFeature, 'TURN_OFF'):
                    self._attr_supported_features |= FanEntityFeature.TURN_OFF
            elif prop.in_list(['mode']):
                self._conv_mode = conv
                self._attr_preset_modes = prop.list_descriptions()
                self._attr_supported_features |= FanEntityFeature.PRESET_MODE
            elif prop.in_list(['fan_level', 'speed_level', 'speed']):
                if prop.value_range:
                    self.set_percentage_property(prop)
                elif prop.value_list and not self._conv_speed:
                    self.set_speeds_property(prop)
                else:
                    continue
                self._conv_speed = conv
            elif prop.in_list(['horizontal_swing', 'vertical_swing']) and not self._conv_oscillate:
                self._conv_oscillate = conv
                self._attr_supported_features |= FanEntityFeature.OSCILLATE

        if self._miot_service:
            if prop := self.custom_config('speed_property'):
                self._prop_speed = self._miot_service.spec.get_property(prop)
                self.set_speeds_property(self._prop_speed)
            if prop := self.custom_config('percentage_property'):
                self.set_percentage_property(self._miot_service.spec.get_property(prop))

        # issues/617
        if self.custom_config_bool('disable_preset_modes'):
            self._attr_supported_features &= ~FanEntityFeature.PRESET_MODE
            self._attr_preset_modes = []
        elif dpm := self.custom_config_list('disable_preset_modes'):
            self._attr_preset_modes = [
                mode
                for mode in self._attr_preset_modes
                if mode not in dpm
            ]

    def set_percentage_property(self, prop):
        if not prop or not prop.value_range:
            return
        self._prop_percentage = prop
        _min = prop.range_min()
        _max = prop.range_max()
        _stp = prop.range_step()
        self._speed_range = (_min, _max)
        self._attr_speed_count = (_max - _min) / _stp + 1
        self._attr_supported_features |= FanEntityFeature.SET_SPEED

    def set_speeds_property(self, prop):
        if not prop:
            return
        self._speed_list = prop.list_descriptions()
        self._attr_speed_count = len(self._speed_list)
        self._attr_extra_state_attributes['speed_list'] = self._speed_list
        self._attr_supported_features |= FanEntityFeature.SET_SPEED

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
            dat[self._conv_power.full_name] = True
        if percentage is not None:
            if self._prop_percentage:
                await self.device.async_set_property(self._prop_percentage, percentage)
            elif self._prop_speed:
                des = percentage_to_ordered_list_item(self._speed_list, percentage)
                val = self._prop_speed.list_value(des)
                if val is not None:
                    await self.device.async_set_property(self._prop_speed, val)
            elif self._speed_range:
                dat[self._conv_speed.full_name] = percentage_to_ranged_value(self._speed_range, percentage)
            elif self._speed_list:
                des = percentage_to_ordered_list_item(self._speed_list, percentage)
                dat[self._conv_speed.full_name] = self._conv_speed.prop.list_value(des)
        if preset_mode is not None:
            dat[self._conv_mode.full_name] = preset_mode
        if dat:
            await self.device.async_write(dat)

    async def async_turn_off(self, **kwargs):
        if not self._conv_power:
            return
        await self.device.async_write({self._conv_power.full_name: False})

    async def async_set_percentage(self, percentage: int):
        if percentage == 0 and self._conv_power:
            await self.async_turn_off()
            return
        await self.async_turn_on(percentage=percentage)

    async def async_set_preset_mode(self, preset_mode: str):
        if not self._conv_mode:
            return
        await self.device.async_write({self._conv_mode.full_name: preset_mode})

    async def async_oscillate(self, oscillating: bool):
        if not self._conv_oscillate:
            return
        await self.device.async_write({self._conv_oscillate.full_name: oscillating})

XEntity.CLS[ENTITY_DOMAIN] = FanEntity


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
