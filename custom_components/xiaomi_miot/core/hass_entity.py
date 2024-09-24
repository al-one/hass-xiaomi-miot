import logging
import json
import voluptuous as vol
from typing import TYPE_CHECKING, Optional, Callable
from functools import cached_property

from homeassistant.helpers.entity import Entity
from homeassistant.helpers.restore_state import ExtraStoredData, RestoredExtraData
import homeassistant.helpers.config_validation as cv

from .utils import get_customize_via_entity, wildcard_models
from .miot_spec import MiotService, MiotProperty, MiotAction
from .converters import BaseConv, MiotPropConv, MiotActionConv

if TYPE_CHECKING:
    from .device import Device

_LOGGER = logging.getLogger(__package__)


class BasicEntity(Entity):
    device: 'Device' = None

    def custom_config(self, key=None, default=None):
        return get_customize_via_entity(self, key, default)

    def custom_config_bool(self, key=None, default=None):
        val = self.custom_config(key, default)
        try:
            val = cv.boolean(val)
        except vol.Invalid:
            val = default
        return val

    def custom_config_number(self, key=None, default=None):
        num = default
        val = self.custom_config(key)
        if val is not None:
            try:
                num = float(f'{val}')
            except (TypeError, ValueError):
                num = default
        return num

    def custom_config_integer(self, key=None, default=None):
        num = self.custom_config_number(key, default)
        if num is not None:
            num = int(num)
        return num

    def custom_config_list(self, key=None, default=None):
        lst = self.custom_config(key)
        if lst is None:
            return default
        if not isinstance(lst, list):
            lst = f'{lst}'.split(',')
            lst = list(map(lambda x: x.strip(), lst))
        return lst

    def custom_config_json(self, key=None, default=None):
        dic = self.custom_config(key)
        if dic:
            if not isinstance(dic, (dict, list)):
                try:
                    dic = json.loads(dic or '{}')
                except (TypeError, ValueError):
                    dic = None
            if isinstance(dic, (dict, list)):
                return dic
        return default


class XEntity(BasicEntity):
    CLS: dict[str, Callable] = {}

    log = _LOGGER
    added = False
    _attr_available = False
    _attr_should_poll = False
    _attr_has_entity_name = True
    _miot_service: Optional[MiotService] = None
    _miot_property: Optional[MiotProperty] = None
    _miot_action: Optional[MiotAction] = None

    def __init__(self, device: 'Device', conv: 'BaseConv'):
        self.device = device
        self.hass = device.hass
        self.conv = conv
        self.attr = conv.attr

        if isinstance(conv, MiotPropConv):
            self.entity_id = conv.prop.generate_entity_id(self, conv.domain)
            self._attr_name = str(conv.prop.friendly_desc)
            self._attr_translation_key = conv.prop.friendly_name
            self._miot_service = conv.prop.service
            self._miot_property = conv.prop

        elif isinstance(conv, MiotActionConv):
            self.entity_id = device.spec.generate_entity_id(self, conv.action.name, conv.domain)
            self._attr_name = str(conv.action.friendly_desc)
            self._attr_translation_key = conv.action.friendly_name
            self._miot_service = conv.action.service
            self._miot_action = conv.action
            self._miot_property = conv.prop
            self._attr_available = True

        else:
            prefix = device.spec.generate_entity_id(self, self.attr)
            self.entity_id = f'{prefix}_{self.attr}'
            self._attr_name = self.attr.replace('_', '').title()
            self._attr_translation_key = self.attr

        self.listen_attrs: set = {self.attr}
        self._attr_unique_id = f'{device.info.unique_id}-{convert_unique_id(conv)}'
        self._attr_device_info = self.device.hass_device_info
        self._attr_extra_state_attributes = {
            'converter': f'{conv}'.replace('custom_components.xiaomi_miot.core.miot_spec.', ''), # TODO
        }

        self.on_init()

    @property
    def unique_mac(self):
        return self.device.info.unique_id

    def on_init(self):
        """Run on class init."""

    def on_device_update(self, data: dict):
        state_change = False
        self._attr_available = True

        if keys := self.listen_attrs & data.keys():
            self.set_state(data)
            state_change = True
            for key in keys:
                if key == self.attr:
                    continue
                self._attr_extra_state_attributes[key] = data.get(key)

        if state_change and self.added:
            self._async_write_ha_state()

    def get_state(self) -> dict:
        """Run before entity remove if entity is subclass from RestoreEntity."""
        return {}

    def set_state(self, data: dict):
        """Run on data from device."""
        self._attr_state = data.get(self.attr)

    @property
    def extra_restore_state_data(self) -> ExtraStoredData | None:
        # filter None values
        if state := {k: v for k, v in self.get_state().items() if v is not None}:
            return RestoredExtraData(state)
        return None

    async def async_added_to_hass(self) -> None:
        self.added = True
        self.device.add_listener(self.on_device_update)

        if call := getattr(self, 'async_get_last_extra_data', None):
            data: RestoredExtraData = await call()
            if data and self.listen_attrs & data.as_dict().keys():
                self.set_state(data.as_dict())


    async def async_will_remove_from_hass(self) -> None:
        self.device.remove_listener(self.on_device_update)

    @cached_property
    def customize_keys(self):
        keys = []
        for mod in wildcard_models(self.device.model):
            if isinstance(self.conv.attr, (MiotProperty, MiotAction)):
                keys.append(f'{mod}:{self.conv.attr.full_name}')
                keys.append(f'{mod}:{self.conv.attr.name}')
            elif self.attr:
                keys.append(f'{mod}:{self.attr}')
        return keys


def convert_unique_id(conv: 'BaseConv'):
    attr = conv.attr
    if isinstance(attr, (MiotService, MiotProperty, MiotAction)):
        return attr.unique_name
    return attr
