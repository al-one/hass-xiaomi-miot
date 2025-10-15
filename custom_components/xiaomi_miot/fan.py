"""Support for Xiaomi fans."""
import logging

from homeassistant.components.fan import (
    DOMAIN as ENTITY_DOMAIN,
    FanEntity as BaseEntity,
    FanEntityFeature,
)

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    HassEntry,
    XEntity,
    MiirToggleEntity,
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
        speed_property = self.custom_config('speed_property', 'speed')
        percentage_property = self.custom_config('percentage_property', 'fan_percent')
        for attr in self.conv.attrs:
            conv = self.device.find_converter(attr)
            prop = getattr(conv, 'prop', None) if conv else None
            if not isinstance(prop, MiotProperty):
                continue
            elif prop.in_list(['on']):
                self._conv_power = conv
                if hasattr(FanEntityFeature, 'TURN_ON'):  # v2024.8
                    self._attr_supported_features |= FanEntityFeature.TURN_ON
                if hasattr(FanEntityFeature, 'TURN_OFF'):
                    self._attr_supported_features |= FanEntityFeature.TURN_OFF
            elif prop.in_list(['mode']):
                self._conv_mode = conv
                self._attr_preset_modes = prop.list_descriptions()
                self._attr_supported_features |= FanEntityFeature.PRESET_MODE
            elif prop.in_list(['fan_level', 'speed_level', 'stepless_fan_level', speed_property, percentage_property]):
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
                    self._attr_percentage = ranged_value_to_percentage(self._speed_range, float(val))
                if self._speed_list and val in self._speed_list:
                    self._attr_percentage = ordered_list_item_to_percentage(self._speed_list, val)
                elif self._speed_list and des in self._speed_list:
                    self._attr_percentage = ordered_list_item_to_percentage(self._speed_list, des)
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
            if self._speed_range:
                dat[self._conv_speed.full_name] = percentage_to_ranged_value(self._speed_range, percentage)
            elif self._speed_list:
                des = percentage_to_ordered_list_item(self._speed_list, percentage)
                dat[self._conv_speed.full_name] = des
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

        if self._act_turn_on and hasattr(FanEntityFeature, 'TURN_ON'):  # v2024.8
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

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs):
        """Turn the entity on."""
        if percentage is None:
            pass
        elif percentage > self._attr_percentage and self._act_speed_up:
            return await self.async_call_action(self._act_speed_up)
        elif percentage < self._attr_percentage and self._act_speed_dn:
            return await self.async_call_action(self._act_speed_dn)

        if preset_mode is None:
            pass
        elif act := self._miot_service.get_action(preset_mode):
            return await self.async_call_action(act)

        return await super().async_turn_on(**kwargs)

    async def async_set_percentage(self, percentage: int):
        """Set the speed of the fan, as a percentage."""
        return await self.async_turn_on(percentage=percentage)

    async def async_set_preset_mode(self, preset_mode):
        """Set new preset mode."""
        return await self.async_turn_on(preset_mode=preset_mode)

    async def async_oscillate(self, oscillating):
        """Oscillate the fan."""
        ret = None
        if not oscillating and self._act_swing_off:
            ret = await self.async_call_action(self._act_swing_off)
        elif oscillating and self._act_swing_on:
            ret = await self.async_call_action(self._act_swing_on)
        if ret:
            self._attr_oscillating = oscillating
        return ret
