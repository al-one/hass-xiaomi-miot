import logging
from typing import TYPE_CHECKING, Optional, Callable
from functools import partial, cached_property

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity, EntityCategory
from homeassistant.helpers.restore_state import ExtraStoredData, RestoredExtraData

from .const import DOMAIN
from .utils import get_customize_via_entity, wildcard_models, CustomConfigHelper
from .miot_spec import MiotService, MiotProperty, MiotAction
from .converters import BaseConv, InfoConv, MiotServiceConv, MiotPropConv, MiotActionConv

if TYPE_CHECKING:
    from .device import Device

_LOGGER = logging.getLogger(__name__)


class BasicEntity(Entity, CustomConfigHelper):
    hass: HomeAssistant = None
    device: 'Device' = None
    conv: 'BaseConv' = None

    def custom_config(self, key=None, default=None):
        return get_customize_via_entity(self, key, default)

    async def async_get_properties(self, mapping, update_entity=False, **kwargs):
        return await self.device.async_get_properties(mapping, update_entity, **kwargs)

    async def async_set_property(self, field, value):
        return await self.hass.async_add_executor_job(self.device.set_property, field, value)

    async def async_set_miot_property(self, siid, piid, value, **kwargs):
        return await self.hass.async_add_executor_job(
            partial(self.device.set_miot_property, siid, piid, value, **kwargs)
        )

    async def async_call_action(self, siid, aiid, params=None, **kwargs):
        return await self.hass.async_add_executor_job(
            partial(self.device.call_action, siid, aiid, params, **kwargs)
        )

    async def async_miio_command(self, method, params=None, **kwargs):
        if not self.device.local:
            return {'error': 'Unsupported'}
        if params is None:
            params = []
        _LOGGER.debug('%s: Send miio command: %s(%s)', self.device.name_model, method, params)
        return await self.device.local.async_send(method, params)


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
        self.log = device.log

        if isinstance(conv, MiotPropConv):
            self.entity_id = conv.prop.generate_entity_id(self, conv.domain)
            self._attr_name = str(conv.prop.friendly_desc)
            self._attr_translation_key = conv.prop.friendly_name
            self._miot_service = conv.prop.service
            self._miot_property = conv.prop
            if not conv.prop.readable:
                self._attr_available = True

        elif isinstance(conv, MiotActionConv):
            self.entity_id = device.spec.generate_entity_id(self, conv.action.name, conv.domain)
            self._attr_name = str(conv.action.friendly_desc)
            self._attr_translation_key = conv.action.friendly_name
            self._miot_service = conv.action.service
            self._miot_action = conv.action
            self._miot_property = conv.prop
            self._attr_available = True

        elif isinstance(conv, MiotServiceConv):
            self.entity_id = conv.service.generate_entity_id(self, conv.domain)
            self._attr_name = str(conv.service.friendly_desc)
            self._attr_translation_key = conv.service.name
            self._miot_service = conv.service
            self._miot_property = conv.prop

        else:
            self.entity_id = device.spec.generate_entity_id(self, self.attr, conv.domain)
            # self._attr_name = self.attr.replace('_', '').title()
            self._attr_translation_key = self.attr
            if isinstance(conv, InfoConv):
                self._attr_available = True

        self.listen_attrs = {self.attr} | set(conv.attrs)
        if getattr(self, '_attr_name', None):
            self._attr_name = self._attr_name.replace(device.name, '').strip()
        self._attr_unique_id = f'{device.unique_id}-{convert_unique_id(conv)}'
        self._attr_device_info = self.device.hass_device_info
        self._attr_extra_state_attributes = {}

        self._attr_icon = conv.option.get('icon')
        self._attr_device_class = self.custom_config('device_class') or conv.option.get('device_class')

        if self._attr_translation_key:
            self._attr_translation_key = ( # hassfest
                self._attr_translation_key
                .replace(':', '-')
                .replace('.', '-')
            )

        cate = self.custom_config('entity_category') or conv.option.get('entity_category')
        if isinstance(cate, str):
            try:
                cate = EntityCategory(cate)
            except Exception:
                cate = None
        if cate:
            self._attr_entity_category = cate
        else:
            cats = {
                'configuration_entities': EntityCategory.CONFIG,
                'diagnostic_entities': EntityCategory.DIAGNOSTIC,
            }
            for k, v in cats.items():
                names = self.custom_config_list(k) or []
                if self._miot_property and self._miot_property.in_list(names):
                    self._attr_entity_category = v
                    break
                if self._miot_action and self._miot_action.in_list(names):
                    self._attr_entity_category = v
                    break

        self.on_init()
        self.device.add_listener(self.on_device_update)

    @cached_property
    def model(self):
        return self.device.model

    @cached_property
    def unique_mac(self):
        return self.device.info.unique_id

    def on_init(self):
        """Run on class init."""

    async def async_update(self):
        await self.device.update_status()

    def on_device_update(self, data: dict, only_info=False):
        state_change = False
        self._attr_available = self.device.available

        if isinstance(self.conv, InfoConv):
            self._attr_available = True
            self._attr_icon = data.get('icon', self._attr_icon)
            self._attr_extra_state_attributes.update(data)
        elif only_info:
            return

        if keys := self.listen_attrs & data.keys():
            self.set_state(data)
            state_change = True
            for key in keys:
                if key == self.attr:
                    continue
                self._attr_extra_state_attributes[key] = data.get(key)

        if state_change and self.added:
            self._async_write_ha_state()
            _LOGGER.debug('%s: Entity state updated: %s', self.entity_id, data.get(self.attr))

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
        self.hass.data[DOMAIN]['entities'][self.entity_id] = self

        if call := getattr(self, 'async_get_last_extra_data', None):
            data: RestoredExtraData = await call()
            if data and self.listen_attrs & data.as_dict().keys():
                self.set_state(data.as_dict())

    async def async_will_remove_from_hass(self) -> None:
        self.device.remove_listener(self.on_device_update)

    @cached_property
    def customize_keys(self):
        keys = []
        prop = getattr(self.conv, 'prop', None)
        action = getattr(self.conv, 'action', None)
        for mod in wildcard_models(self.device.model):
            if isinstance(action, MiotAction):
                keys.append(f'{mod}:{action.full_name}')
                keys.append(f'{mod}:{action.name}')
            if isinstance(prop, MiotProperty):
                keys.append(f'{mod}:{prop.full_name}')
                keys.append(f'{mod}:{prop.name}')
            if self.attr and not (prop or action):
                keys.append(f'{mod}:{self.attr}')
        return keys


def convert_unique_id(conv: 'BaseConv'):
    service = getattr(conv, 'service', None)
    if isinstance(conv, MiotServiceConv) and isinstance(service, MiotService):
        return service.iid

    action = getattr(conv, 'action', None)
    if isinstance(action, MiotAction):
        return action.unique_name

    prop = getattr(conv, 'prop', None)
    if isinstance(prop, MiotProperty):
        return prop.unique_name

    return conv.attr
