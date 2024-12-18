"""Support for Curtain and Airer."""
import logging
from datetime import timedelta

from homeassistant.components.cover import (
    DOMAIN as ENTITY_DOMAIN,
    CoverEntity as BaseEntity,
    CoverEntityFeature,  # v2022.5
    CoverDeviceClass,
    ATTR_POSITION,
)

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    HassEntry,
    XEntity,
    MiotEntity,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
    MiotProperty,
)
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
    model = str(config.get(CONF_MODEL) or '')
    spec = hass.data[DOMAIN]['miot_specs'].get(model)
    entities = []
    if isinstance(spec, MiotSpec):
        for srv in spec.get_services(ENTITY_DOMAIN, 'curtain', 'airer', 'window_opener', 'motor_controller'):
            if not srv.get_property('motor_control'):
                continue
            entities.append(MiotCoverEntity(config, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class CoverEntity(XEntity, BaseEntity):
    _attr_is_closed = None
    _attr_target_cover_position = None
    _attr_supported_features = CoverEntityFeature(0)
    _conv_status = None
    _conv_motor: MiotPropConv = None
    _conv_current_position = None
    _conv_target_position = None
    _current_range = None
    _target_range = None

    def on_init(self):
        for conv in self.device.converters:
            prop = getattr(conv, 'prop', None)
            if not isinstance(prop, MiotProperty):
                continue
            elif prop.in_list(['status']):
                self._conv_status = conv
            elif prop.in_list(['motor_control']):
                self._conv_motor = conv
            elif prop.in_list(['current_position']) and prop.value_range:
                self._conv_current_position = conv
                self._current_range = (prop.range_min, prop.range_max)
            elif prop.value_range and isinstance(conv, MiotTargetPositionConv):
                self._conv_target_position = conv
                self._target_range = conv.ranged
                self._attr_supported_features |= CoverEntityFeature.SET_POSITION
            elif prop.value_range and prop.in_list(['target_position']):
                self._conv_target_position = conv
                self._target_range = (prop.range_min(), prop.range_max())
                self._attr_supported_features |= CoverEntityFeature.SET_POSITION

    def set_state(self, data: dict):
        if self._conv_current_position:
            val = self._conv_current_position.value_from_dict(data)
            if val is not None:
                self._attr_current_cover_position = int(val)
        if self._conv_target_position:
            val = self._conv_target_position.value_from_dict(data)
            if val is not None:
                self._attr_target_cover_position = int(val)
                if not self._conv_current_position:
                    self._attr_current_cover_position = self._attr_target_cover_position

    async def async_open_cover(self, **kwargs):
        if self._conv_motor:
            val = self._conv_motor.prop.list_first('Open', 'Up')
            if val is not None:
                await self.device.async_write({self._conv_motor.full_name: val})
                return
        await self.async_set_cover_position(100)

    async def async_close_cover(self, **kwargs):
        if self._conv_motor:
            val = self._conv_motor.prop.list_first('Close', 'Down')
            if val is not None:
                await self.device.async_write({self._conv_motor.full_name: val})
                return
        await self.async_set_cover_position(0)

    async def async_set_cover_position(self, position, **kwargs):
        if not self._conv_target_position:
            return
        await self.device.async_write({self._conv_target_position.full_name: position})

XEntity.CLS[ENTITY_DOMAIN] = CoverEntity


class MiotCoverEntity(MiotEntity, BaseEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(miot_service, config=config, logger=_LOGGER)

        self._prop_status = miot_service.get_property('status')
        self._prop_motor_control = miot_service.get_property('motor_control')
        self._prop_current_position = None
        for p in miot_service.get_properties('current_position'):
            self._prop_current_position = p
            if p.value_range:
                # https://home.miot-spec.com/spec/hyd.airer.lyjpro
                break
        self._prop_target_position = miot_service.get_property('target_position')

        self._motor_reverse = False
        self._position_reverse = False
        self._target2current = False
        self._open_texts = []
        self._close_texts = []
        self._supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if self._prop_target_position:
            if not self.custom_config_bool('disable_target_position'):
                self._supported_features |= CoverEntityFeature.SET_POSITION
            else:
                self._prop_target_position = None
        if self._prop_motor_control.list_first('Pause', 'Stop') is not None:
            self._supported_features |= CoverEntityFeature.STOP

        self._target2current = self.custom_config_bool('target2current_position')
        if self._target2current and self._prop_target_position:
            self._prop_current_position = self._prop_target_position

        self._motor_reverse = self.custom_config_bool('motor_reverse', False)
        self._position_reverse = self.custom_config_bool('position_reverse', self._motor_reverse)
        self._open_texts = self.custom_config_list('open_texts', ['Opening', 'Opened', 'Open', 'Up', 'Rising', 'Risen', 'Rise'])
        self._close_texts = self.custom_config_list('close_texts', ['Closing', 'Closed', 'Close', 'Down', 'Falling', 'Descent'])
        if self._motor_reverse:
            self._open_texts, self._close_texts = self._close_texts, self._open_texts

    @property
    def device_class(self):
        if cls := self.get_device_class(CoverDeviceClass):
            return cls
        typ = f'{self.model} {self._miot_service.spec.type}'
        if 'curtain' in typ:
            return CoverDeviceClass.CURTAIN
        if 'window_opener' in typ:
            return CoverDeviceClass.WINDOW
        return None

    async def async_update(self):
        await super().async_update()
        if not self._available:
            return
        if prop_reverse := self._miot_service.get_property('motor_reverse'):
            if prop_reverse.from_device(self.device):
                if self.custom_config_bool('auto_position_reverse'):
                    self._position_reverse = True

    @property
    def current_cover_position(self):
        pos = -1
        if self._prop_current_position:
            try:
                cur = round(self._prop_current_position.from_device(self.device), 2)
            except (TypeError, ValueError):
                cur = None
            if cur is None:
                return None
            pos = cur
            range_max = self._prop_current_position.range_max()
            dic = self.custom_config_json('cover_position_mapping')
            if dic:
                if cur in dic:
                    pos = dic.get(cur, cur)
            elif self._prop_current_position.value_list:
                # mrbond.airer.m53c
                for v in self._prop_current_position.value_list:
                    if cur != v.get('value'):
                        continue
                    des = str(v.get('description')).lower()
                    if 'top' in des:
                        pos = 100
                    elif 'middle' in des:
                        pos = 50
                    elif 'button' in des:
                        pos = 0
            elif range_max != 100:
                pos = cur / range_max * 100
        if pos < 0:
            # If the motor controller is stopped, generate fake middle position
            if self._prop_status:
                sta = int(self._prop_status.from_device(self.device) or -1)
                if sta in self._prop_status.list_search('Stopped'):
                    return 50
            return None
        dev = int(self.custom_config_integer('deviated_position', 1) or 0)
        if pos <= dev:
            pos = 0
        elif pos >= 100 - dev:
            pos = 100
        if self._position_reverse:
            pos = 100 - pos
        return pos

    @property
    def target_cover_position(self):
        pos = None
        if not self._prop_target_position:
            return pos
        pos = self._prop_target_position.from_device(self.device)
        if pos is None:
            return pos
        pos = int(pos)
        if self._position_reverse:
            pos = 100 - pos
        return pos

    def set_cover_position(self, **kwargs):
        pos = round(kwargs.get(ATTR_POSITION) or 0)
        if self._position_reverse and self._target2current:
            pos = 100 - pos
        srv = self._miot_service
        for p in srv.get_properties('target_position'):
            if not p.value_range:
                continue
            if p.range_min() <= pos <= p.range_max():
                return self.set_miot_property(srv.iid, p.iid, pos)
        cur = self.current_cover_position or 50
        if pos > cur:
            return self.open_cover()
        if pos < cur:
            return self.close_cover()
        return False

    @property
    def is_closed(self):
        cur = self.current_cover_position
        if cur is not None:
            pos = self.custom_config_number('closed_position', 1)
            return cur <= pos
        if self._prop_status:
            sta = int(self._prop_status.from_device(self.device) or -1)
            cvs = self.custom_config_list('closed_status') or []
            if cvs:
                return sta in cvs or f'{sta}' in cvs
        return None

    @property
    def is_closing(self):
        if not self._prop_status:
            return None
        sta = int(self._prop_status.from_device(self.device) or -1)
        return sta in self._prop_status.list_search(*self._close_texts)

    @property
    def is_opening(self):
        if not self._prop_status:
            return None
        sta = int(self._prop_status.from_device(self.device) or -1)
        return sta in self._prop_status.list_search(*self._open_texts)

    def motor_control(self, open_cover=True, **kwargs):
        tls = self._open_texts if open_cover else self._close_texts
        val = self.custom_config_integer('open_cover_value' if open_cover else 'close_cover_value')
        if val is None:
            val = self._prop_motor_control.list_first(*tls)
        if val is None:
            _LOGGER.error('Motor control value is invalid for %s', self.name)
            return False
        ret = self.set_property(self._prop_motor_control, val)
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
        val = self.custom_config_integer('stop_cover_value', val)
        return self.set_property(self._prop_motor_control, val)
