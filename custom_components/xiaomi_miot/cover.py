"""Support for Curtain and Airer."""
import logging
from datetime import timedelta

from homeassistant.components.cover import (
    DOMAIN as ENTITY_DOMAIN,
    CoverEntity,
    CoverEntityFeature,  # v2022.5
    CoverDeviceClass,
    ATTR_POSITION,
)

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    MiotEntity,
    MiotPropertySubEntity,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
    MiotProperty,
)

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'
SCAN_INTERVAL = timedelta(seconds=60)

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
    if isinstance(spec, MiotSpec):
        for srv in spec.get_services(ENTITY_DOMAIN, 'curtain', 'airer', 'window_opener', 'motor_controller'):
            if not srv.get_property('motor_control'):
                continue
            entities.append(MiotCoverEntity(config, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotCoverEntity(MiotEntity, CoverEntity):
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
        typ = f'{self._model} {self._miot_service.spec.type}'
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
            if prop_reverse.from_dict(self._state_attrs):
                if self.custom_config_bool('auto_position_reverse'):
                    self._position_reverse = True

    @property
    def current_cover_position(self):
        pos = -1
        if self._prop_current_position:
            try:
                cur = round(self._prop_current_position.from_dict(self._state_attrs), 2)
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
                sta = int(self._prop_status.from_dict(self._state_attrs) or -1)
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
        pos = self._prop_target_position.from_dict(self._state_attrs)
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
            sta = int(self._prop_status.from_dict(self._state_attrs) or -1)
            cvs = self.custom_config_list('closed_status') or []
            if cvs:
                return sta in cvs or f'{sta}' in cvs
        return None

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


class MiotCoverSubEntity(MiotPropertySubEntity, CoverEntity):
    def __init__(self, parent, miot_property: MiotProperty, option=None):
        super().__init__(parent, miot_property, option, domain=ENTITY_DOMAIN)
        self._prop_status = self._option.get('status_property')
        if self._prop_status:
            self._option['keys'] = [*(self._option.get('keys') or []), self._prop_status.full_name]
        self._prop_target_position = self._miot_service.get_property('target_position')
        self._value_open = self._miot_property.list_first('Open', 'Up', 'All-up', 'Rise')
        self._value_close = self._miot_property.list_first('Close', 'Down', 'All-down')
        self._value_stop = self._miot_property.list_first('Pause', 'Stop')
        if self._value_open is not None:
            self._supported_features |= CoverEntityFeature.OPEN
        if self._value_close is not None:
            self._supported_features |= CoverEntityFeature.CLOSE
        if self._value_stop is not None:
            self._supported_features |= CoverEntityFeature.STOP
        if self._prop_target_position:
            self._supported_features |= CoverEntityFeature.SET_POSITION
        if self._miot_property.value_range:
            self._supported_features |= CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE
            self._supported_features |= CoverEntityFeature.SET_POSITION

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
        if self.custom_config_bool('target2current_position'):
            prop = self._miot_service.get_property('target_position') or prop
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
