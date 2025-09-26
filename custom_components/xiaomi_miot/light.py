"""Support for Xiaomi lights."""
import logging

from homeassistant.components.light import (
    DOMAIN as ENTITY_DOMAIN,
    LightEntity as BaseEntity,
    LightEntityFeature,  # v2022.5
    ColorMode,
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ATTR_EFFECT,
)
from homeassistant.helpers.restore_state import RestoreEntity

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
from .core.converters import (
    MiotBrightnessConv,
    MiotColorTempConv,
    MiotRgbColorConv,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
    MiotProperty,
)

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'

SERVICE_TO_METHOD = {}
ATTR_COLOR_TEMP = 'color_temp'


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
        for srv in spec.get_services('ir_light_control'):
            if srv.name in ['ir_light_control']:
                entities.append(MiirLightEntity(config, srv))
                continue
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class LightEntity(XEntity, BaseEntity, RestoreEntity):
    _attr_names = None
    _brightness_for_on = None
    _brightness_for_off = None

    def on_init(self):
        self._attr_names = {}
        self._brightness_for_on = self.custom_config_number('brightness_for_on')
        self._brightness_for_off = self.custom_config_number('brightness_for_off')
        mode_property = self.custom_config('mode_property', 'mode')
        color_property = self.custom_config('color_property', 'color')
        color_temp_property = self.custom_config('color_temp_property', 'color_temp')
        brightness_property = self.custom_config('brightness_property', 'brightness')
        self._attr_color_mode = ColorMode.ONOFF

        modes = set()
        for attr in self.conv.attrs:
            conv = self.device.find_converter(attr)
            prop = getattr(conv, 'prop', None) if conv else None
            if not isinstance(prop, MiotProperty):
                continue
            if prop.in_list(['brightness', brightness_property]) or isinstance(conv, MiotBrightnessConv):
                self._attr_names[ATTR_BRIGHTNESS] = attr
                self._attr_color_mode = ColorMode.BRIGHTNESS
            elif prop.in_list(['color_temperature', color_temp_property]) or isinstance(conv, MiotColorTempConv):
                self._attr_color_mode = ColorMode.COLOR_TEMP
                modes.add(ColorMode.COLOR_TEMP)

                # percentage may be incorrectly declared as kelvin
                # e.g. https://home.miot-spec.com/spec/mrbond.airer.m33a
                if prop.unit == 'percentage' or prop.range_max() == 100:
                    self._attr_min_color_temp_kelvin = MiotColorTempConv.percentage_to_kelvin(prop.range_max())
                    self._attr_max_color_temp_kelvin = MiotColorTempConv.percentage_to_kelvin(prop.range_min())
                    self._attr_names[ATTR_COLOR_TEMP_KELVIN] = attr
                elif prop.unit in ['kelvin']:
                    self._attr_min_color_temp_kelvin = prop.range_min()
                    self._attr_max_color_temp_kelvin = prop.range_max()
                    self._attr_names[ATTR_COLOR_TEMP_KELVIN] = attr
                else:
                    self._attr_min_mireds = prop.range_min()
                    self._attr_max_mireds = prop.range_max()
                    self._attr_names[ATTR_COLOR_TEMP] = attr
            elif prop.in_list(['color', color_property]) or isinstance(conv, MiotRgbColorConv):
                self._attr_names[ATTR_RGB_COLOR] = attr
                modes.add(ColorMode.RGB)
            elif prop.in_list(['mode', 'color_mode', mode_property]):
                self._attr_names[ATTR_EFFECT] = attr
                self._attr_effect_list = prop.list_descriptions()
                self._attr_supported_features |= LightEntityFeature.EFFECT

        self._attr_supported_color_modes = modes if modes else {self._attr_color_mode}

    def get_state(self) -> dict:
        return {
            self.attr: self._attr_is_on,
            ATTR_BRIGHTNESS: self._attr_brightness,
            ATTR_COLOR_TEMP: self._attr_color_temp,
        }

    def set_state(self, data: dict):
        val = data.get(self.attr)
        if val is not None:
            self._attr_is_on = bool(val)

        if (val := data.get(self._attr_names.get(ATTR_BRIGHTNESS))) is not None:
            self._attr_brightness = val
            if self._brightness_for_on is not None:
                self._attr_is_on = val >= self._brightness_for_on
        if (val := data.get(self._attr_names.get(ATTR_COLOR_TEMP_KELVIN))) is not None:
            if val != self._attr_color_temp_kelvin:
                self._attr_color_temp_kelvin = val
                self._attr_color_mode = ColorMode.COLOR_TEMP
        elif (val := data.get(self._attr_names.get(ATTR_COLOR_TEMP))) is not None:
            if val != self._attr_color_temp:
                self._attr_color_temp = val
                self._attr_color_mode = ColorMode.COLOR_TEMP
        if (val := data.get(self._attr_names.get(ATTR_RGB_COLOR))) is not None:
            if val != self._attr_rgb_color:
                self._attr_rgb_color = val
                self._attr_color_mode = ColorMode.RGB
        if (val := data.get(self._attr_names.get(ATTR_EFFECT))) is not None:
            self._attr_effect = val

    async def async_turn_on(self, **kwargs):
        dat = {self.attr: True}
        if self._brightness_for_on is not None:
            dat[self.attr] = self._brightness_for_on
        for k, v in kwargs.items():
            if attr := self._attr_names.get(k):
                dat[attr] = v
        await self.device.async_write(dat)

    async def async_turn_off(self, **kwargs):
        dat = {self.attr: False}
        if self._brightness_for_off is not None:
            dat[self.attr] = self._brightness_for_off
        await self.device.async_write(dat)


XEntity.CLS[ENTITY_DOMAIN] = LightEntity


class MiirLightEntity(MiirToggleEntity, BaseEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(miot_service, config=config, logger=_LOGGER)

        self._act_bright_up = miot_service.get_action('brightness_up')
        self._act_bright_dn = miot_service.get_action('brightness_down')
        if self._act_bright_up or self._act_bright_dn:
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
            self._attr_brightness = 127

        self._supported_features = LightEntityFeature.EFFECT
        self._attr_effect_list = []
        for a in miot_service.actions.values():
            if a.ins:
                continue
            self._attr_effect_list.append(a.friendly_desc)

    async def async_turn_on(self, **kwargs):
        """Turn the entity on."""
        bright = kwargs.get(ATTR_BRIGHTNESS)
        if bright is None:
            pass
        elif bright > self._attr_brightness and self._act_bright_up:
            return await self.async_call_action(self._act_bright_up)
        elif bright < self._attr_brightness and self._act_bright_dn:
            return await self.async_call_action(self._act_bright_dn)

        effect = kwargs.get(ATTR_EFFECT)
        if act := self._miot_service.get_action(effect):
            return await self.async_call_action(act)

        return await super().async_turn_on(**kwargs)
