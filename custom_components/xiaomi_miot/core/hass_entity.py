import logging
from typing import TYPE_CHECKING, Callable

from homeassistant.helpers.entity import Entity, DeviceInfo

from .miot_spec import MiotService, MiotProperty

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
        if isinstance(attr, MiotProperty):
            self.attr = attr.full_name
            self._attr_translation_key = attr.friendly_name
            self.entity_id = attr.generate_entity_id(self, conv.domain)
        elif isinstance(attr, MiotService):
            self.attr = attr.name
            self._attr_translation_key = attr.name
            self.entity_id = attr.generate_entity_id(self, conv.domain)
        else:
            self.attr = attr
            self._attr_translation_key = attr

        self.on_init()

    @property
    def unique_mac(self):
        return self.device.info.unique_id

    def on_init(self):
        """Run on class init."""

    def on_device_update(self, data: dict):
        pass

    def get_state(self) -> dict:
        """Run before entity remove if entity is subclass from RestoreEntity."""
        return {}

    def set_state(self, data: dict):
        """Run on data from device."""
        self._attr_state = data.get(self.attr)

    async def async_added_to_hass(self) -> None:
        self.device.add_listener(self.on_device_update)

    async def async_will_remove_from_hass(self) -> None:
        self.device.remove_listener(self.on_device_update)
