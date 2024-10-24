import logging
from typing import TYPE_CHECKING

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

if TYPE_CHECKING:
    from .device import Device

_LOGGER = logging.getLogger(__name__)

class DataCoordinator(DataUpdateCoordinator):
    def __init__(self, device: 'Device', name, **kwargs):
        kwargs.setdefault('always_update', True)
        super().__init__(device.hass, _LOGGER, name=f'{device.unique_id}-{name}', **kwargs)

        self.device = device
        method = getattr(device, name, None)
        if not self.update_method and method:
            self.update_method = method

    async def _async_setup(self):
        """Set up coordinator."""
        self.async_add_listener(self.coordinator_updated)

    def coordinator_updated(self):
        _LOGGER.debug('%s: Coordinator updated: %s', self.device.name_model, [self.name, self.data])
