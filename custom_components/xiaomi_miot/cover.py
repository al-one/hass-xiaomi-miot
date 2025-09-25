"""Support for Curtain and Airer."""
import logging
from datetime import timedelta

from homeassistant.components.cover import (
    DOMAIN as ENTITY_DOMAIN,
    CoverEntity as BaseEntity,
    CoverEntityFeature,
    CoverDeviceClass,
)

from . import (
    DOMAIN,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    HassEntry,
    XEntity,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.miot_spec import MiotProperty
from .core.converters import MiotPropConv, MiotTargetPositionConv

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'
SCAN_INTERVAL = timedelta(seconds=60)

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    HassEntry.init(hass, config_entry).new_adder(ENTITY_DOMAIN, async_add_entities)
    await async_setup_config_entry(hass, config_entry, async_setup_platform, async_add_entities, ENTITY_DOMAIN)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data.setdefault(DATA_KEY, {})
    hass.data[DOMAIN]['add_entities'][ENTITY_DOMAIN] = async_add_entities
    config['hass'] = hass
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class CoverEntity(XEntity, BaseEntity):
    _attr_is_closed = None
    _attr_device_class = None
    _attr_target_cover_position = None
    _attr_supported_features = CoverEntityFeature(0)
    _conv_status = None
    _conv_motor: MiotPropConv = None
    _conv_current_position = None
    _conv_target_position = None
    _current_range = None
    _target_range = (0, 100)
    _is_airer = None
    _motor_reverse = None
    _position_reverse = None
    _open_texts = ['open', 'up']
    _close_texts = ['close', 'down']
    _closed_position = 0
    _deviated_position = 0
    _target_position_props = None
    _cover_position_mapping = None
    _target2current_position = None

    def on_init(self):
        self._attr_available = self.device.available

        models = f'{self.device.model} {self.device.info.urn}'
        self._is_airer = 'airer' in models
        if self._is_airer:
            self._position_reverse = True
        elif 'curtain' in models:
            self._attr_device_class = CoverDeviceClass.CURTAIN
        elif 'wopener' in models or 'window-opener' in models:
            self._attr_device_class = CoverDeviceClass.WINDOW

        self._motor_reverse = self.custom_config_bool('motor_reverse', self._motor_reverse)
        self._position_reverse = self.custom_config_bool('position_reverse', self._position_reverse)
        self._open_texts = self.custom_config_list('open_texts', self._open_texts)
        self._close_texts = self.custom_config_list('close_texts', self._close_texts)
        if self._motor_reverse:
            self._open_texts, self._close_texts = self._close_texts, self._open_texts
        self._target_position_props = self.custom_config_list('target_position_props') or []
        self._cover_position_mapping = self.custom_config_json('cover_position_mapping') or {}

        if not self.conv.attrs:
            self.conv.attrs.append(self.conv.full_name)
        for attr in self.conv.attrs:
            conv = self.device.find_converter(attr)
            prop = getattr(conv, 'prop', None) if conv else None
            if not isinstance(prop, MiotProperty):
                continue
            elif prop.in_list(['status']):
                self._conv_status = conv
            elif prop.in_list(['motor_control']):
                self._conv_motor = conv
                self._attr_supported_features |= CoverEntityFeature.OPEN
                self._attr_supported_features |= CoverEntityFeature.CLOSE
                if prop.list_first('Stop', 'Pause') is not None:
                    self._attr_supported_features |= CoverEntityFeature.STOP
            elif prop.in_list(['current_position']):
                if prop.value_range:
                    self._conv_current_position = conv
                    self._current_range = (prop.range_min(), prop.range_max())
                    self.log.debug('current_position: %s', conv)
                elif prop.value_list and self._cover_position_mapping and not self._conv_current_position:
                    self._conv_current_position = conv
                    self._current_range = (0, 100)
                    self.log.debug('current_position: %s', conv)
            elif prop.value_range and isinstance(conv, MiotTargetPositionConv):
                self._conv_target_position = conv
                self._target_range = conv.ranged
                self._attr_supported_features |= CoverEntityFeature.SET_POSITION
            elif prop.value_range and prop.in_list(self._target_position_props):
                self._conv_target_position = conv
                self._target_range = (prop.range_min(), prop.range_max())
                self._attr_supported_features |= CoverEntityFeature.SET_POSITION

        if self.custom_config_bool('disable_target_position'):
            self._conv_target_position = None
            self._attr_supported_features &= ~CoverEntityFeature.SET_POSITION

        self._deviated_position = self.custom_config_integer('deviated_position', 2)
        if self._current_range:
            pos = self._current_range[0] + self._deviated_position
            self._closed_position = self.custom_config_integer('closed_position', pos)
        self._target2current_position = self.custom_config_bool('target2current_position', not self._conv_current_position)

        if self._motor_reverse or self._position_reverse:
            self._attr_extra_state_attributes.update({
                'motor_reverse': self._motor_reverse,
                'position_reverse': self._position_reverse,
            })
        if self._closed_position:
            self._attr_extra_state_attributes.update({
                'closed_position': self._closed_position,
                'deviated_position': self._deviated_position,
            })

    def set_state(self, data: dict):
        prop_status = getattr(self._conv_status, 'prop', None) if self._conv_status else None
        if prop_status:
            val = self._conv_status.value_from_dict(data)
            if val is not None:
                self._attr_is_closed = None
                self._attr_is_opening = None
                self._attr_is_closing = None
            if val in prop_status.list_search('Closed'):
                self._attr_is_closed = True
            elif val in prop_status.list_search('Opened'):
                self._attr_is_closed = False
            elif val in prop_status.list_search('Opening'):
                self._attr_is_opening = True
            elif val in prop_status.list_search('Closing'):
                self._attr_is_closing = True
            elif val in prop_status.list_search('Rising'):
                self._attr_is_closing = self._position_reverse
            elif val in prop_status.list_search('Falling', 'Dropping'):
                self._attr_is_opening = self._position_reverse
            elif val in prop_status.list_search('Stop Lower Limit', 'Stop At Lowest', 'Floor'):
                self._attr_is_closed = not self._position_reverse
            elif val in prop_status.list_search('Stop Upper Limit', 'Stop At Highest', 'Ceiling'):
                self._attr_is_closed = self._position_reverse
            elif self._is_airer and val in prop_status.list_search('Down'):
                self._attr_is_closed = False
        if self._conv_current_position:
            val = self._conv_current_position.value_from_dict(data)
            if val is not None:
                val = int(val)
                if self._cover_position_mapping:
                    val = self._cover_position_mapping.get(val, val)
                if self._position_reverse:
                    val = self._current_range[1] - val
                self._attr_current_cover_position = val
        if self._conv_target_position:
            val = self._conv_target_position.value_from_dict(data)
            if val is not None:
                val = int(val)
                if self._position_reverse:
                    val = self._target_range[1] - val
                self._attr_target_cover_position = val
        if self._target2current_position:
            self._attr_current_cover_position = self._attr_target_cover_position
            self._attr_extra_state_attributes.update({
                'target2current_position': True,
            })
        if (val := self._attr_current_cover_position) is not None:
            closed = val <= self._closed_position
            if self._deviated_position is None:
                pass
            elif val <= self._deviated_position:
                self._attr_current_cover_position = 0
                closed = not self._is_airer
            elif val >= (100 - self._deviated_position):
                self._attr_current_cover_position = 100
                closed = self._is_airer
            if self._attr_is_closed is None or not prop_status:
                self._attr_is_closed = closed
        self._attr_extra_state_attributes.update({
            'state_is_closed': self._attr_is_closed,
        })

    async def async_open_cover(self, **kwargs):
        if conv := self._conv_motor:
            val = conv.prop.list_first(*self._open_texts)
            if val is not None:
                await self.device.async_write({conv.full_name: val})
                return
            self.log.warning('No open command found in motor control property: %s', self._open_texts)
        await self.async_set_cover_position(0 if self._position_reverse else 100)

    async def async_close_cover(self, **kwargs):
        if conv := self._conv_motor:
            val = conv.prop.list_first(*self._close_texts)
            if val is not None:
                await self.device.async_write({conv.full_name: val})
                return
            self.log.warning('No close command found in motor control property: %s', [self._close_texts, conv.prop.value_list])
        await self.async_set_cover_position(100 if self._position_reverse else 0)

    async def async_stop_cover(self, **kwargs):
        if not self._conv_motor:
            return
        val = self._conv_motor.prop.list_first('Stop', 'Pause')
        if val is not None:
            await self.device.async_write({self._conv_motor.full_name: val})

    async def async_set_cover_position(self, position, **kwargs):
        if not self._conv_target_position:
            return
        if self._position_reverse:
            position = self._target_range[1] - position
        await self.device.async_write({self._conv_target_position.full_name: position})


XEntity.CLS[ENTITY_DOMAIN] = CoverEntity
