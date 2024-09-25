import logging
from typing import TYPE_CHECKING

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

if TYPE_CHECKING:
    from .device import Device

_LOGGER = logging.getLogger(__name__)

class DataCoordinator(DataUpdateCoordinator):
    def __init__(self, device: 'Device', name, **kwargs):
        super().__init__(device.hass, _LOGGER, name=f'{device.unique_id}-{name}', **kwargs)
        self.device = device
        method = getattr(device, name, None)
        if not self.update_method and method:
            self.update_method = method
