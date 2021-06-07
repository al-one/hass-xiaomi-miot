"""Support for Curtain and Airer."""
import logging
import time
from enum import Enum
from functools import partial

from homeassistant.const import *  # noqa: F401
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.components.cover import (
    DOMAIN as ENTITY_DOMAIN,
    CoverEntity,
    SUPPORT_OPEN,
    SUPPORT_CLOSE,
    SUPPORT_STOP,
    SUPPORT_SET_POSITION,
    DEVICE_CLASS_CURTAIN,
    DEVICE_CLASS_WINDOW,
    ATTR_POSITION,
)
from homeassistant.helpers.event import async_track_utc_time_change

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    MiioEntity,
    MiotEntity,
    MiotSensorSubEntity,
    MiioDevice,
    DeviceException,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
    MiotProperty,
)
from .light import LightSubEntity
from .fan import (
    FanSubEntity,
    SUPPORT_SET_SPEED,
    SUPPORT_PRESET_MODE,
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
        entity = MrBondAirerProEntity(config)
        entities.append(entity)
    else:
        miot = config.get('miot_type')
        if miot:
            spec = await MiotSpec.async_from_type(hass, miot)
            for srv in spec.get_services(ENTITY_DOMAIN, 'curtain', 'airer', 'window_opener'):
                if not srv.get_property('motor_control'):
                    continue
                cfg = {
                    **config,
                    'name': f"{config.get('name')} {srv.description}"
                }
                entities.append(MiotCoverEntity(cfg, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotCoverEntity(MiotEntity, CoverEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(miot_service, config=config)

        self._prop_status = miot_service.get_property('status')
        self._prop_motor_control = miot_service.get_property('motor_control')
        self._prop_current_position = miot_service.get_property('current_position')
        self._prop_target_position = miot_service.get_property('target_position')

        self._motor_reverse = miot_service.name in ['airer']
        self._open_texts = []
        self._close_texts = []
        self._state_attrs.update({'entity_class': self.__class__.__name__})

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._supported_features = SUPPORT_OPEN | SUPPORT_CLOSE
        if self._prop_target_position and not self.custom_config('disable_target_position'):
            self._supported_features |= SUPPORT_SET_POSITION
        if self._prop_motor_control.list_first('Pause', 'Stop') is not None:
            self._supported_features |= SUPPORT_STOP
        if cv.boolean(self.custom_config('motor_reverse')):
            self._motor_reverse = True
        self._open_texts = [
            *str(self.custom_config('open_texts') or '').split(','),
            'Opening', 'Opened', 'Open', 'Up',
        ]
        self._close_texts = [
            *str(self.custom_config('close_texts') or '').split(','),
            'Closing', 'Closed', 'Close', 'Down',
        ]
        if self._motor_reverse:
            ols = self._open_texts
            self._open_texts = self._close_texts
            self._close_texts = ols

    @property
    def device_class(self):
        typ = f'{self._model} {self._miot_service.spec.type}'
        if typ.find('curtain') >= 0:
            return DEVICE_CLASS_CURTAIN
        if typ.find('window_opener') >= 0:
            return DEVICE_CLASS_WINDOW
        return None

    async def async_update(self):
        await super().async_update()
        if not self._available:
            return
        self._update_sub_entities(['dryer'], domain='switch')

    @property
    def current_cover_position(self):
        pos = -1
        if self._prop_current_position:
            pos = int(self._prop_current_position.from_dict(self._state_attrs, -1) or 0)
            range_max = self._prop_current_position.range_max()
            if not range_max:
                pos = -1
            elif range_max != 100 and pos >= 0:
                pos = pos / range_max * 100
        return pos

    def set_cover_position(self, **kwargs):
        pos = round(kwargs.get(ATTR_POSITION) or 0)
        srv = self._miot_service
        for p in srv.get_properties('target_position'):
            if not p.value_range:
                continue
            if p.range_min() <= pos <= p.range_max():
                return self.set_miot_property(srv.iid, p.iid, pos)
        raise NotImplementedError()

    @property
    def is_closed(self):
        pos = self.current_cover_position
        if pos < 0:
            return None
        pos = self.custom_config('closed_position', 1)
        isc = self.current_cover_position <= pos
        if self._motor_reverse:
            isc = not isc
        return isc

    @property
    def is_closing(self):
        if not self._prop_status:
            return None
        sta = int(self._prop_status.from_dict(self._state_attrs) or -1)
        return sta in self._prop_status.list_search(*self._close_texts)

    @property
    def is_opening(self):
        if not self._prop_status:
            return None
        sta = int(self._prop_status.from_dict(self._state_attrs) or -1)
        return sta in self._prop_status.list_search(*self._open_texts)

    def motor_control(self, open_cover=True, **kwargs):
        tls = self._open_texts if open_cover else self._close_texts
        val = self._prop_motor_control.list_first(*tls)
        ret = self.set_property(self._prop_motor_control.full_name, val)
        if ret and self._prop_status:
            self.update_attrs({
                self._prop_status.full_name: self._prop_status.list_first(*tls)
            })
        return ret

    def open_cover(self, **kwargs):
        return self.motor_control(open_cover=True, **kwargs)

    def close_cover(self, **kwargs):
        return self.motor_control(open_cover=False, **kwargs)

    def stop_cover(self, **kwargs):
        val = self._prop_motor_control.list_first('Pause', 'Stop')
        return self.set_property(self._prop_motor_control.full_name, val)


class MiotCoverSubEntity(MiotSensorSubEntity, CoverEntity):
    def __init__(self, parent, miot_property: MiotProperty, option=None):
        super().__init__(parent, miot_property, option)
        self._prop_status = self._option.get('status_property')
        if self._prop_status:
            self._option['keys'] = [*(self._option.get('keys') or []), self._prop_status.full_name]
        self._prop_target_position = self._miot_service.get_property('target_position')
        self._value_open = self._miot_property.list_first('Open', 'Up', 'All-up')
        self._value_close = self._miot_property.list_first('Close', 'Down', 'All-down')
        self._value_stop = self._miot_property.list_first('Pause', 'Stop')
        if self._value_open is not None:
            self._supported_features |= SUPPORT_OPEN
        if self._value_close is not None:
            self._supported_features |= SUPPORT_CLOSE
        if self._value_stop is not None:
            self._supported_features |= SUPPORT_STOP
        if self._prop_target_position:
            self._supported_features |= SUPPORT_SET_POSITION
        if self._miot_property.value_range:
            self._supported_features |= SUPPORT_OPEN | SUPPORT_CLOSE | SUPPORT_SET_POSITION

    @property
    def current_cover_position(self):
        """Return current position of cover.
        None is unknown, 0 is closed, 100 is fully open.
        """
        if self._miot_property.value_range:
            val = round(self._miot_property.from_dict(self._state_attrs) or -1, 2)
            top = self._miot_property.range_max()
            return round(val / top * 100)
        prop = self._miot_service.get_property('current_position')
        if prop:
            return round(prop.from_dict(self._state_attrs) or -1)
        return None

    def set_cover_position(self, **kwargs):
        """Move the cover to a specific position."""
        pos = round(kwargs.get(ATTR_POSITION) or 0)
        if self._prop_target_position:
            return self.set_parent_property(pos, self._prop_target_position)
        if self._miot_property.value_range:
            stp = self._miot_property.range_step()
            top = self._miot_property.range_max()
            pos = round(top * (pos / 100) / stp) * stp
            return self.set_parent_property(pos)
        raise NotImplementedError()

    @property
    def is_closed(self):
        """Return if the cover is closed or not."""
        if self._prop_status:
            val = self._prop_status.from_dict(self._state_attrs)
            vls = self._prop_status.list_search('Closed', 'Down')
            if vls and val is not None:
                return val in vls
        pos = self.current_cover_position
        if pos is not None and pos >= 0:
            return pos <= 0
        return None

    def open_cover(self, **kwargs):
        """Open the cover."""
        val = None
        if self._miot_property.value_list:
            val = self._value_open
        elif self._miot_property.value_range:
            val = self._miot_property.range_max()
        if val is not None:
            return self.set_parent_property(val)
        raise NotImplementedError()

    def close_cover(self, **kwargs):
        """Close cover."""
        val = None
        if self._miot_property.value_list:
            val = self._value_close
        elif self._miot_property.value_range:
            val = self._miot_property.range_min()
        if val is not None:
            return self.set_parent_property(val)
        raise NotImplementedError()

    def stop_cover(self, **kwargs):
        """Stop the cover."""
        val = None
        if self._miot_property.value_list:
            val = self._value_stop
        if val is not None:
            return self.set_parent_property(val)
        raise NotImplementedError()


class MiioCoverEntity(MiioEntity, CoverEntity):
    def __init__(self, name, device):
        super().__init__(name, device)
        self._device_class = None
        self._position = None
        self._set_position = None
        self._unsub_listener_cover = None
        self._is_opening = False
        self._is_closing = False
        self._requested_closing = True

    @property
    def current_cover_position(self):
        return self._position

    @property
    def is_closed(self):
        if self._position is not None:
            return self._position <= 0
        return None

    @property
    def is_closing(self):
        return self._is_closing

    @property
    def is_opening(self):
        return self._is_opening

    @property
    def device_class(self):
        return self._device_class

    def open_cover(self, **kwargs):
        pass

    def close_cover(self, **kwargs):
        pass

    @callback
    def _listen_cover(self):
        if self._unsub_listener_cover is None:
            self._unsub_listener_cover = async_track_utc_time_change(
                self.hass, self._time_changed_cover  # noqa
            )

    async def _time_changed_cover(self, now):
        if self._requested_closing:
            self._position -= 10 if self._position >= 10 else 0
        else:
            self._position += 10 if self._position <= 90 else 0
        if self._position in (100, 0, self._set_position):
            self._unsub_listener_cover()
            self._unsub_listener_cover = None
            self._set_position = None
        self.async_write_ha_state()
        _LOGGER.debug('cover process %s: %s', self.entity_id, {
            'position': self._position,
            'set_position': self._set_position,
            'requested_closing': self._requested_closing,
        })


class MrBondAirerProEntity(MiotEntity, MiioCoverEntity):
    def __init__(self, config):
        name = config[CONF_NAME]
        host = config[CONF_HOST]
        token = config[CONF_TOKEN]
        _LOGGER.info('Initializing with host %s (token %s...)', host, token[:5])

        self._device = MiioDevice(host, token)
        super().__init__(name, self._device)
        self._supported_features = SUPPORT_OPEN | SUPPORT_CLOSE | SUPPORT_STOP
        self._state_attrs.update({'entity_class': self.__class__.__name__})
        self._props = ['dry', 'led', 'motor', 'drytime', 'airer_location']
        self._subs = {}

    def get_single_prop(self, prop):
        rls = self._device.get_properties([prop]) or [None]
        return rls[0]

    async def async_get_single_prop(self, prop):
        return await self.hass.async_add_executor_job(partial(self.get_single_prop, prop))

    async def async_update(self):
        attrs = []
        try:
            attrs = await self.hass.async_add_executor_job(
                partial(self._device.send, 'get_prop', self._props, extra_parameters={
                    'id': int(time.time() % 86400 * 1000),
                })
            )
            self._available = True
        except DeviceException as ex:
            err = '%s' % ex
            if err.find('-10000') > 0:
                # Unknown Error: {'code': -10000, 'message': 'error'}
                try:
                    attrs = [
                        await self.async_get_single_prop('dry'),
                        await self.async_get_single_prop('led'),
                        await self.async_get_single_prop('motor'),
                        None,
                        None,
                    ]
                    self._available = True
                except DeviceException as exc:
                    if self._available:
                        self._available = False
                    _LOGGER.error(
                        'Got exception while fetching the state for %s (%s): %s %s',
                        self.entity_id, self._props, ex, exc
                    )
            else:
                _LOGGER.error(
                    'Got exception while fetching the state for %s (%s): %s',
                    self.entity_id, self._props, ex
                )
        if self._available:
            attrs = dict(zip(self._props, attrs))
            _LOGGER.debug('Got new state from %s: %s', self.entity_id, attrs)
            self._state_attrs.update(attrs)
            self._is_opening = int(attrs.get('motor', 0)) == 1
            self._is_closing = int(attrs.get('motor', 0)) == 2
            self._position = None
            loc = attrs.get('airer_location', None)
            if loc is None:
                if self._is_opening:
                    self._position = 100
                if self._is_closing:
                    self._position = 0
            else:
                if loc == 1:
                    self._position = 100
                if loc == 2:
                    self._position = 0
            self._state_attrs.update({
                'position': self._position,
                'closed':   self.is_closed,
                'stopped':  bool(not self._is_opening and not self._is_closing),
            })

            add_lights = self._add_entities.get('light')
            if 'light' in self._subs:
                self._subs['light'].update()
            elif add_lights and 'led' in attrs:
                self._subs['light'] = MrBondAirerProLightEntity(self)
                add_lights([self._subs['light']])

            add_fans = self._add_entities.get('fan')
            if 'fan' in self._subs:
                self._subs['fan'].update()
            elif add_fans and 'dry' in attrs:
                self._subs['fan'] = MrBondAirerProDryEntity(self, option={'keys': ['drytime']})
                add_fans([self._subs['fan']])

    def set_motor(self, val):
        ret = self.send_command('set_motor', [val])
        if ret:
            self.update_attrs({'motor': val})
            self._is_opening = val == 1
            self._is_closing = val == 2
            if self._is_opening:
                self._position = 100
            if self._is_closing:
                self._position = 0
        return ret

    def open_cover(self, **kwargs):
        return self.set_motor(1)

    def close_cover(self, **kwargs):
        return self.set_motor(2)

    def stop_cover(self, **kwargs):
        return self.set_motor(0)

    def set_led(self, val):
        ret = self.send_command('set_led', [val])
        if ret:
            self.update_attrs({'led': val})
        return ret

    def set_dry(self, lvl):
        if lvl == 0:
            ret = self.send_command('set_dryswitch', [0])
        elif lvl >= 4:
            ret = self.send_command('set_dryswitch', [1])
        else:
            ret = self.send_command('set_dry', [lvl])
        if ret:
            self.update_attrs({'dry': lvl})
        return ret

    @property
    def icon(self):
        return 'mdi:hanger'


class MrBondAirerProLightEntity(LightSubEntity):
    def __init__(self, parent: MrBondAirerProEntity, attr='led', option=None):
        super().__init__(parent, attr, option)

    def update(self):
        super().update()
        if self._available:
            attrs = self._state_attrs
            self._state = int(attrs.get(self._attr, 0)) >= 1

    def turn_on(self, **kwargs):
        return self.call_parent('set_led', 1)

    def turn_off(self, **kwargs):
        return self.call_parent('set_led', 0)


class MrBondAirerProDryEntity(FanSubEntity):
    def __init__(self, parent: MrBondAirerProEntity, attr='dry', option=None):
        super().__init__(parent, attr, option)
        self._supported_features = SUPPORT_PRESET_MODE or SUPPORT_SET_SPEED

    def update(self):
        super().update()
        if self._available:
            attrs = self._state_attrs
            self._state = int(attrs.get(self._attr, 0)) >= 1

    def turn_on(self, speed=None, percentage=None, preset_mode=None, **kwargs):
        return self.set_speed(speed or MrBondAirerProDryLevels(1).name)

    def turn_off(self, **kwargs):
        return self.set_speed(MrBondAirerProDryLevels(0).name)

    @property
    def speed(self):
        return self.preset_mode

    @property
    def speed_list(self):
        return self.preset_modes

    def set_speed(self, speed: str):
        return self.set_preset_mode(speed)

    @property
    def preset_mode(self):
        return MrBondAirerProDryLevels(int(self._state_attrs.get(self._attr, 0))).name

    @property
    def preset_modes(self):
        return [v.name for v in MrBondAirerProDryLevels]

    def set_preset_mode(self, speed: str):
        lvl = MrBondAirerProDryLevels[speed].value
        return self.call_parent('set_dry', lvl)


class MrBondAirerProDryLevels(Enum):
    Off = 0
    Dry30Minutes = 1
    Dry60Minutes = 2
    Dry90Minutes = 3
    Dry120Minutes = 4
