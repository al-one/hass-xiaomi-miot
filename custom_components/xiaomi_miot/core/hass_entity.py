import logging
from typing import TYPE_CHECKING, Callable

from homeassistant.helpers.entity import Entity

from .miot_spec import MiotService, MiotProperty, MiotAction

if TYPE_CHECKING:
    from .device import Device
    from .converters import BaseConv

_LOGGER = logging.getLogger(__package__)

class XEntity(Entity):
    CLS: dict[str, Callable] = {}

    log = _LOGGER
    added = False
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, device: 'Device', conv: 'BaseConv'):
        self.device = device
        self.hass = device.hass
        self.conv = conv
        attr = conv.attr

        if isinstance(attr, (MiotProperty, MiotAction)):
            self.attr = attr.full_name
            self.entity_id = attr.generate_entity_id(self, conv.domain)
            self._attr_name = attr.friendly_desc
            self._attr_translation_key = attr.friendly_name
        elif isinstance(attr, MiotService):
            self.attr = attr.name
            self.entity_id = attr.generate_entity_id(self, conv.domain)
            self._attr_name = attr.friendly_desc
            self._attr_translation_key = attr.name
        else:
            self.attr = attr
            prefix = device.spec.generate_entity_id(self)
            self.entity_id = f'{prefix}_{attr}'
            self._attr_name = attr.replace('_', '').title()
            self._attr_translation_key = attr
        self.listen_attrs: set = {self.attr}
        self._attr_unique_id = f'{device.info.unique_id}-{convert_unique_id(conv)}'
        self._attr_device_info = self.device.hass_device_info

        self.on_init()

    @property
    def unique_mac(self):
        return self.device.info.unique_id

    def on_init(self):
        """Run on class init."""

    def on_device_update(self, data: dict):
        state_change = False
        _LOGGER.info('%s: Device updated: %s', self.entity_id, [self.listen_attrs, data])

        if self.listen_attrs & data.keys():
            self.set_state(data)
            state_change = True

        if state_change and self.added:
            self._async_write_ha_state()

    def get_state(self) -> dict:
        """Run before entity remove if entity is subclass from RestoreEntity."""
        return {}

    def set_state(self, data: dict):
        """Run on data from device."""
        self._attr_state = data.get(self.attr)

    async def async_added_to_hass(self) -> None:
        self.added = True
        self.device.add_listener(self.on_device_update)

    async def async_will_remove_from_hass(self) -> None:
        self.device.remove_listener(self.on_device_update)


def convert_unique_id(conv: 'BaseConv'):
    attr = conv.attr
    if isinstance(attr, (MiotService, MiotProperty, MiotAction)):
        return attr.unique_name
    return attr
