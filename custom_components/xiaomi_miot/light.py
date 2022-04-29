"""Support for Xiaomi lights."""
import logging
from functools import partial

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

try:
    # hass 2021.4.0b0+
    from homeassistant.components.light import (
        COLOR_MODE_ONOFF,
        COLOR_MODE_BRIGHTNESS,
        COLOR_MODE_COLOR_TEMP,
        COLOR_MODE_HS,
    )
except ImportError:
    COLOR_MODE_ONOFF = 'onoff'
    COLOR_MODE_BRIGHTNESS = 'brightness'
    COLOR_MODE_COLOR_TEMP = 'color_temp'
    COLOR_MODE_HS = 'hs'

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'

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
    if model.find('mrbond.airer') >= 0:
        pass
    elif isinstance(spec, MiotSpec):
        for srv in spec.get_services(ENTITY_DOMAIN, 'light_bath_heater'):
            if not srv.get_property('on'):
                continue
            elif srv.name in ['light_bath_heater'] and spec.get_service('ptc_bath_heater'):
                continue
            entities.append(MiotLightEntity(config, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotLightEntity(MiotToggleEntity, LightEntity):
    def __init__(self, config: dict, miot_service: MiotService, **kwargs):
        kwargs.setdefault('logger', _LOGGER)
        super().__init__(miot_service, config=config, **kwargs)

        self._prop_power = miot_service.get_property('on')
        self._prop_mode = miot_service.get_property('mode')
        self._prop_brightness = miot_service.get_property('brightness')
        self._prop_color_temp = miot_service.get_property('color_temperature')
        self._prop_color = miot_service.get_property('color')

        self._srv_ambient_custom = miot_service.spec.get_service('ambient_light_custom')
        if self._srv_ambient_custom:
            if not self._prop_color:
                self._prop_color = self._srv_ambient_custom.get_property('color')

        self._attr_supported_color_modes = set()
        if self._prop_power:
            self._attr_supported_color_modes.add(COLOR_MODE_ONOFF)
        if self._prop_brightness:
            self._supported_features |= SUPPORT_BRIGHTNESS
            self._attr_supported_color_modes.add(COLOR_MODE_BRIGHTNESS)
        if self._prop_color_temp:
            self._supported_features |= SUPPORT_COLOR_TEMP
            self._attr_supported_color_modes.add(COLOR_MODE_COLOR_TEMP)
            self._vars['color_temp_min'] = self._prop_color_temp.range_min() or 3000
            self._vars['color_temp_max'] = self._prop_color_temp.range_max() or 5700
            self._attr_min_mireds = self.translate_mired(self._vars['color_temp_max'])
            self._attr_max_mireds = self.translate_mired(self._vars['color_temp_min'])
            self._vars['color_temp_sum'] = self._vars['color_temp_min'] + self._vars['color_temp_max']
            self._vars['mireds_sum'] = self._attr_min_mireds + self._attr_max_mireds
        if self._prop_color:
            self._supported_features |= SUPPORT_COLOR
            self._attr_supported_color_modes.add(COLOR_MODE_HS)
        if self._prop_mode:
            self._supported_features |= SUPPORT_EFFECT

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._vars['color_temp_reverse'] = self.custom_config_bool('color_temp_reverse')
        self._vars['yeelight_smooth_on'] = self.custom_config_integer('yeelight_smooth_on')
        self._vars['yeelight_smooth_off'] = self.custom_config_integer('yeelight_smooth_off')
        if self._prop_brightness:
            self._vars['brightness_for_on'] = self.custom_config_integer('brightness_for_on')
            self._vars['brightness_for_off'] = self.custom_config_integer('brightness_for_off')

    @property
    def is_on(self):
        if self._prop_brightness:
            val = self._prop_brightness.from_dict(self._state_attrs)
            bri = self._vars.get('brightness_for_on')
            if bri is not None:
                return val == bri
        return super().is_on

    def turn_on(self, **kwargs):
        ret = False
        if not self.is_on:
            if (num := self._vars.get('yeelight_smooth_on')) and self._local_state:
                if ret := self.send_miio_command('set_power', ['on', 'smooth', num]):
                    self._vars['delay_update'] = num / 1000
            elif (bri := self._vars.get('brightness_for_on')) is not None:
                ret = self.set_property(self._prop_brightness, bri)
            else:
                ret = self.set_property(self._prop_power, True)

        if self._prop_brightness and ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs[ATTR_BRIGHTNESS]
            per = brightness / 255
            val = per * 100
            if self._prop_brightness.value_range:
                val = per * self._prop_brightness.range_max()
            _LOGGER.debug('%s: Setting light brightness: %s %s%%', self.name_model, brightness, per * 100)
            ret = self.set_property(self._prop_brightness, int(val))

        if self._prop_color_temp and ATTR_COLOR_TEMP in kwargs:
            mired = kwargs[ATTR_COLOR_TEMP]
            color_temp = self.translate_mired(mired)
            if self._vars.get('color_temp_reverse'):
                color_temp = self._vars.get('color_temp_sum') - color_temp
            _LOGGER.debug('%s: Setting light color temperature: %s mireds, %s ct', self.name_model, mired, color_temp)
            ret = self.set_property(self._prop_color_temp, color_temp)

        if self._prop_color and ATTR_HS_COLOR in kwargs:
            rgb = color.color_hs_to_RGB(*kwargs[ATTR_HS_COLOR])
            num = rgb_to_int(rgb)
            _LOGGER.debug('%s: Setting light color: %s', self.name_model, rgb)
            ret = self.set_property(self._prop_color, num)

        if self._prop_mode and ATTR_EFFECT in kwargs:
            val = self._prop_mode.list_value(kwargs[ATTR_EFFECT])
            _LOGGER.debug('%s: Setting light effect: %s(%s)', self.name_model, kwargs[ATTR_EFFECT], val)
            ret = self.set_property(self._prop_mode, val)

        return ret

    def turn_off(self, **kwargs):
        if (num := self._vars.get('yeelight_smooth_off')) and self._local_state:
            if ret := self.send_miio_command('set_power', ['off', 'smooth', num]):
                self._vars['delay_update'] = num / 1000
        elif (bri := self._vars.get('brightness_for_off')) is not None:
            ret = self.set_property(self._prop_brightness, bri)
        else:
            ret = super().turn_off()
        return ret

    @property
    def brightness(self):
        """Return the brightness of this light between 0..255."""
        val = None
        if self._prop_brightness:
            val = self._prop_brightness.from_dict(self._state_attrs)
        if val is None:
            return None
        rmx = 100
        if self._prop_brightness.value_range:
            rmx = self._prop_brightness.range_max()
        return round(255 / rmx * int(val))

    @property
    def hs_color(self):
        """Return the hue and saturation color value [float, float]."""
        rgb = self.rgb_color
        if rgb is not None:
            return color.color_RGB_to_hs(*rgb)
        return None

    @property
    def rgb_color(self):
        """Return the rgb color value [int, int, int]."""
        if self._prop_color:
            num = int(self._prop_color.from_dict(self._state_attrs) or 0)
            return int_to_rgb(num)
        return None

    @property
    def color_temp(self):
        if not self._prop_color_temp:
            return None
        num = self._prop_color_temp.from_dict(self._state_attrs) or 3000
        if self._vars.get('color_temp_reverse'):
            num = self._vars.get('color_temp_sum') - num
        return self.translate_mired(num)

    @staticmethod
    def translate_mired(num):
        try:
            return round(1000000 / num)
        except TypeError:
            return round(1000000 / 2700)

    @property
    def effect_list(self):
        if self._prop_mode:
            return self._prop_mode.list_descriptions()
        return None

    @property
    def effect(self):
        if self._prop_mode:
            val = self._prop_mode.from_dict(self._state_attrs)
            if val is not None:
                return self._prop_mode.list_description(val)
        return None


class MiotLightSubEntity(MiotLightEntity, ToggleSubEntity):
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
        ToggleSubEntity.__init__(self, parent, attr, {
            **(option or {}),
            'keys': keys,
        })
        MiotLightEntity.__init__(self, {
            **parent.miot_config,
            'name': f'{parent.device_name}',
        }, miot_service, device=parent.miot_device)
        self.entity_id = miot_service.generate_entity_id(self)
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
        await self.hass.async_add_executor_job(partial(self.update))

    def set_property(self, field, value):
        return self.set_parent_property(value, field)


class LightSubEntity(ToggleSubEntity, LightEntity):
    _brightness = None
    _color_temp = None

    def update(self, data=None):
        super().update(data)
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
