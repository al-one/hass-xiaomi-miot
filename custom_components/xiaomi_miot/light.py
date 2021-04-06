"""Support for Xiaomi lights."""
import logging

from homeassistant.const import *  # noqa: F401
from homeassistant.components.light import (
    DOMAIN as ENTITY_DOMAIN,
    LightEntity,
    SUPPORT_BRIGHTNESS,
    SUPPORT_COLOR_TEMP,
    SUPPORT_COLOR,
    SUPPORT_EFFECT,
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_HS_COLOR,
    ATTR_EFFECT,
)
from homeassistant.util import color

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
)
from miio.utils import (
    rgb_to_int,
    int_to_rgb,
)

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'

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
            for srv in spec.get_services(ENTITY_DOMAIN):
                if not srv.get_property('on'):
                    continue
                cfg = {
                    **config,
                    'name': f"{config.get('name')} {srv.description}"
                }
                entities.append(MiotLightEntity(cfg, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotLightEntity(MiotToggleEntity, LightEntity):
    def __init__(self, config: dict, miot_service: MiotService, **kwargs):
        super().__init__(miot_service, config=config, **kwargs)

        self._prop_power = miot_service.get_property('on')
        self._prop_brightness = miot_service.get_property('brightness')
        self._prop_color_temp = miot_service.get_property('color_temperature')
        self._prop_color = miot_service.get_property('color')
        self._prop_mode = miot_service.get_property('mode')

        if self._prop_brightness:
            self._supported_features |= SUPPORT_BRIGHTNESS
        if self._prop_color_temp:
            self._supported_features |= SUPPORT_COLOR_TEMP
        if self._prop_color:
            self._supported_features |= SUPPORT_COLOR
        if self._prop_mode:
            self._supported_features |= SUPPORT_EFFECT

        self._state_attrs.update({'entity_class': self.__class__.__name__})

    def turn_on(self, **kwargs):
        ret = False
        if not self.is_on:
            ret = self.set_property(self._prop_power.full_name, True)

        if self.supported_features & SUPPORT_BRIGHTNESS and ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs[ATTR_BRIGHTNESS]
            percent_brightness = round(100 * brightness / 255)
            _LOGGER.debug('Setting light: %s brightness: %s %s%%', self.name, brightness, percent_brightness)
            ret = self.set_property(self._prop_brightness.full_name, percent_brightness)

        if self.supported_features & SUPPORT_COLOR_TEMP and ATTR_COLOR_TEMP in kwargs:
            mired = kwargs[ATTR_COLOR_TEMP]
            color_temp = self.translate_mired(mired)
            _LOGGER.debug('Setting light: %s color temperature: %s mireds, %s ct', self.name, mired, color_temp)
            ret = self.set_property(self._prop_color_temp.full_name, color_temp)

        if self.supported_features & SUPPORT_COLOR and ATTR_HS_COLOR in kwargs:
            rgb = color.color_hs_to_RGB(*kwargs[ATTR_HS_COLOR])
            num = rgb_to_int(rgb)
            _LOGGER.debug('Setting light: %s color: %s', self.name, rgb)
            ret = self.set_property(self._prop_color.full_name, num)

        if self.supported_features & SUPPORT_EFFECT and ATTR_EFFECT in kwargs:
            val = self._prop_mode.list_value(kwargs[ATTR_EFFECT])
            _LOGGER.debug('Setting light: %s effect: %s(%s)', self.name, kwargs[ATTR_EFFECT], val)
            ret = self.set_property(self._prop_mode.full_name, val)

        return ret

    @property
    def brightness(self):
        return round(255 / 100 * int(self._state_attrs.get(self._prop_brightness.full_name) or 0))

    @property
    def hs_color(self):
        if self._prop_color:
            num = round(self._prop_color.from_dict(self._state_attrs) or 0)
            rgb = int_to_rgb(num)
            return color.color_RGB_to_hs(*rgb)
        return None

    @property
    def color_temp(self):
        return self.translate_mired(self._state_attrs.get(self._prop_color_temp.full_name) or 2700)

    @property
    def min_mireds(self):
        return self.translate_mired(self._prop_color_temp.value_range[1] or 5700)

    @property
    def max_mireds(self):
        return self.translate_mired(self._prop_color_temp.value_range[0] or 2700)

    @staticmethod
    def translate_mired(num):
        return round(1000000 / num)

    @property
    def effect_list(self):
        if self._prop_mode:
            return [
                v.get('description')
                for v in self._prop_mode.value_list
                if isinstance(v, dict)
            ]
        return None

    @property
    def effect(self):
        if self._prop_mode:
            val = self._prop_mode.from_dict(self._state_attrs)
            if val is not None:
                return self._prop_mode.list_description(val)
        return None


class MiotLightSubEntity(ToggleSubEntity, MiotLightEntity):
    def __init__(self, parent, miot_service: MiotService):
        prop_power = miot_service.get_property('on')
        ToggleSubEntity.__init__(self, parent, prop_power.full_name, {
            'keys': list((miot_service.mapping() or {}).keys()),
        })
        MiotLightEntity.__init__(self, {
            **parent.miot_config,
            'name': f'{parent.name} {miot_service.description}',
        }, miot_service, device=parent.miot_device)
        self._prop_power = prop_power

    def update(self):
        super().update()
        self._state_attrs.update({'entity_class': self.__class__.__name__})
        if not self._available:
            return


class LightSubEntity(ToggleSubEntity, LightEntity):
    _brightness = None
    _color_temp = None

    def update(self):
        super().update()
        if self._available:
            attrs = self._state_attrs
            self._brightness = attrs.get('brightness', 0)
            self._color_temp = attrs.get('color_temp', 0)

    def turn_on(self, **kwargs):
        self.call_parent(['turn_on_light', 'turn_on'], **kwargs)

    def turn_off(self, **kwargs):
        self.call_parent(['turn_off_light', 'turn_off'], **kwargs)

    @property
    def brightness(self):
        return self._brightness

    @property
    def color_temp(self):
        return self._color_temp
