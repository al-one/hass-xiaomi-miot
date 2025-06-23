"""Support for Xiaomi lights."""
import logging
from functools import partial

from homeassistant.components.light import (
    DOMAIN as ENTITY_DOMAIN,
    LightEntity as BaseEntity,
    LightEntityFeature,  # v2022.5
    ColorMode,
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ATTR_HS_COLOR,
    ATTR_EFFECT,
    ATTR_TRANSITION,
)
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import color

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    HassEntry,
    XEntity,
    MiotToggleEntity,
    MiirToggleEntity,
    ToggleSubEntity,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.converters import (
    MiotColorTempConv,
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
            elif not srv.get_property('on'):
                continue
            elif ptc := spec.get_service('ptc_bath_heater'):
                if spec.get_service('switch') or ptc.get_property('on', 'mode', 'target_temperature'):
                    # only sub light
                    continue
            entities.append(MiotLightEntity(config, srv))
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
        self._attr_color_mode = ColorMode.ONOFF

        modes = set()
        for attr in self.conv.attrs:
            prop = self._miot_service.spec.get_property(attr) if self._miot_service else None
            if not prop:
                continue
            if prop.in_list(['brightness']):
                self._attr_names[ATTR_BRIGHTNESS] = attr
                self._attr_color_mode = ColorMode.BRIGHTNESS
            elif prop.in_list(['color_temperature', 'color_temp']):
                self._attr_color_mode = ColorMode.COLOR_TEMP
                modes.add(ColorMode.COLOR_TEMP)

                # percentage may be incorrectly declared as kelvin
                # e.g. https://home.miot-spec.com/spec/mrbond.airer.m33a
                if prop.unit != 'percentage' and prop.range_max() == 100:
                    prop.unit = 'percentage'
                if prop.unit == 'percentage':
                    self._is_percentage_color_temp = True
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
            elif prop.in_list(['color']):
                self._attr_names[ATTR_RGB_COLOR] = attr
                modes.add(ColorMode.RGB)
            elif prop.in_list(['mode']):
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


class MiotLightEntity(MiotToggleEntity, BaseEntity):
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

        if prop := self.custom_config('power_property'):
            if prop := self._miot_service.spec.get_property(prop):
                self._prop_power = prop
        if prop := self.custom_config('mode_property'):
            if prop := self._miot_service.spec.get_property(prop):
                self._prop_mode = prop
        if prop := self.custom_config('brightness_property'):
            if prop := self._miot_service.spec.get_property(prop):
                self._prop_brightness = prop
        if prop := self.custom_config('color_temp_property'):
            if prop := self._miot_service.spec.get_property(prop):
                self._prop_color_temp = prop
        if prop := self.custom_config('color_property'):
            if prop := self._miot_service.spec.get_property(prop):
                self._prop_color = prop

        self._attr_color_mode = None
        self._attr_supported_color_modes = set()
        if self._prop_color_temp:
            self._attr_supported_color_modes.add(ColorMode.COLOR_TEMP)
            self._vars['color_temp_min'] = self._prop_color_temp.range_min() or 3000
            self._vars['color_temp_max'] = self._prop_color_temp.range_max() or 5700
            self._attr_min_mireds = self.translate_mired(self._vars['color_temp_max'])
            self._attr_max_mireds = self.translate_mired(self._vars['color_temp_min'])
            self._vars['color_temp_sum'] = self._vars['color_temp_min'] + self._vars['color_temp_max']
            self._vars['mireds_sum'] = self._attr_min_mireds + self._attr_max_mireds
        if self._prop_color:
            self._attr_supported_color_modes.add(ColorMode.HS)
        if self._prop_brightness and not self._attr_supported_color_modes:
            self._attr_supported_color_modes.add(ColorMode.BRIGHTNESS)
        if self._prop_power and not self._attr_supported_color_modes:
            self._attr_supported_color_modes.add(ColorMode.ONOFF)

        self._supported_features = LightEntityFeature(0)
        if self._prop_mode:
            self._supported_features |= LightEntityFeature.EFFECT
        self._is_yeelight = 'yeelink.' in f'{self.model}'
        if self._is_yeelight:
            self._supported_features |= LightEntityFeature.TRANSITION

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
            val = self._prop_brightness.from_device(self.device)
            bri = self._vars.get('brightness_for_on')
            if bri is not None:
                return val >= bri
        return super().is_on

    def turn_on(self, **kwargs):
        ret = False
        trs = kwargs.get(ATTR_TRANSITION)
        if trs is not None:
            trs *= 1000
        else:
            trs = self._vars.get('yeelight_smooth_on')
        if not (self._is_yeelight and self._local_state):
            # only yeelight in local mode
            trs = None

        if not self.is_on:
            if trs:
                trs = int(trs)
                if ret := self.send_miio_command('set_power', ['on', 'smooth', trs]):
                    self._vars['delay_update'] = trs / 1000
            elif (bri := self._vars.get('brightness_for_on')) is not None:
                ret = self.set_property(self._prop_brightness, bri)
            else:
                ret = self.set_property(self._prop_power, True)
        self._attr_color_mode = None

        if self._prop_brightness and ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs[ATTR_BRIGHTNESS]
            per = brightness / 255
            if self._prop_brightness.value_range:
                val = per * self._prop_brightness.range_max()
            else:
                val = per * 100
            val = int(val)
            self.logger.debug('%s: Setting light brightness: %s %s%%', self.name_model, brightness, val)
            if trs:
                ret = self.send_miio_command('set_bright', [val, 'smooth', trs])
            else:
                ret = self.set_property(self._prop_brightness, val)

        if self._prop_color_temp and ATTR_COLOR_TEMP in kwargs:
            mired = kwargs[ATTR_COLOR_TEMP]
            color_temp = self.translate_mired(mired)
            if self._vars.get('color_temp_reverse'):
                color_temp = self._vars.get('color_temp_sum') - color_temp
            self.logger.debug('%s: Setting light color temperature: %s mireds, %s ct', self.name_model, mired, color_temp)
            if trs:
                ret = self.send_miio_command('set_ct_abx', [color_temp, 'smooth', trs])
            else:
                ret = self.set_property(self._prop_color_temp, color_temp)
            self._attr_color_mode = ColorMode.COLOR_TEMP

        if self._prop_color and ATTR_HS_COLOR in kwargs:
            rgb = color.color_hs_to_RGB(*kwargs[ATTR_HS_COLOR])
            num = rgb_to_int(rgb)
            self.logger.debug('%s: Setting light color: %s', self.name_model, rgb)
            ret = self.set_property(self._prop_color, num)
            self._attr_color_mode = ColorMode.HS

        if self._prop_mode and ATTR_EFFECT in kwargs:
            mode = kwargs[ATTR_EFFECT]
            val = self._prop_mode.list_value(mode)
            self.logger.debug('%s: Setting light effect: %s(%s)', self.name_model, mode, val)
            ret = self.set_property(self._prop_mode, val)

        return ret

    def turn_off(self, **kwargs):
        trs = kwargs.get(ATTR_TRANSITION)
        if trs is not None:
            trs *= 1000
        else:
            trs = self._vars.get('yeelight_smooth_off')
        if not (self._is_yeelight and self._local_state):
            # only yeelight in local mode
            trs = None

        if trs:
            trs = int(trs)
            if ret := self.send_miio_command('set_power', ['off', 'smooth', trs]):
                self._vars['delay_update'] = trs / 1000
        elif (bri := self._vars.get('brightness_for_off')) is not None:
            ret = self.set_property(self._prop_brightness, bri)
        else:
            ret = super().turn_off()
        self.logger.info('%s: Turn off light result: %s, transition: %s', self.name_model, ret, trs)
        return ret

    @property
    def brightness(self):
        """Return the brightness of this light between 0..255."""
        val = None
        if self._prop_brightness:
            val = self._prop_brightness.from_device(self.device)
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
            num = int(self._prop_color.from_device(self.device) or 0)
            return int_to_rgb(num)
        return None

    @property
    def color_temp(self):
        if not self._prop_color_temp:
            return None
        num = self._prop_color_temp.from_device(self.device) or 3000
        if self._vars.get('color_temp_reverse'):
            num = self._vars.get('color_temp_sum') - num
        return self.translate_mired(num)

    @property
    def color_mode(self):
        """Return the color mode of the light."""
        if self._attr_color_mode is not None:
            return self._attr_color_mode
        supported = self.supported_color_modes
        if ColorMode.HS in supported and self.hs_color is not None:
            return ColorMode.HS
        if ColorMode.COLOR_TEMP in supported and self.color_temp_kelvin is not None:
            return ColorMode.COLOR_TEMP
        if ColorMode.BRIGHTNESS in supported and self.brightness is not None:
            return ColorMode.BRIGHTNESS
        if ColorMode.ONOFF in supported:
            return ColorMode.ONOFF
        return ColorMode.UNKNOWN

    def translate_mired(self, num):
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
            val = self._prop_mode.from_device(self.device)
            if val is not None:
                return self._prop_mode.list_description(val)
        return None


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

    def turn_on(self, **kwargs):
        """Turn the entity on."""
        bright = kwargs.get(ATTR_BRIGHTNESS)
        if bright is None:
            pass
        elif bright > self._attr_brightness and self._act_bright_up:
            return self.call_action(self._act_bright_up)
        elif bright < self._attr_brightness and self._act_bright_dn:
            return self.call_action(self._act_bright_dn)

        effect = kwargs.get(ATTR_EFFECT)
        if act := self._miot_service.get_action(effect):
            return self.call_action(act)

        return super().turn_on(**kwargs)


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

        self.entity_id = miot_service.generate_entity_id(self, domain=ENTITY_DOMAIN)
        self._prop_power = prop_power
        if parent_power:
            self._prop_power = parent_power
            self._available = True
            if not self._attr_supported_color_modes:
                self._attr_supported_color_modes.add(ColorMode.ONOFF)

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
