import logging
from typing import TYPE_CHECKING

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

if TYPE_CHECKING:
    from .device import Device

_LOGGER = logging.getLogger(__name__)

class DataCoordinator(DataUpdateCoordinator):
    def __init__(self, device: 'Device', update_method, **kwargs):
        kwargs.setdefault('always_update', True)

        if callable(update_method):
            name = update_method.__name__
        elif isinstance(update_method, str):
            name = update_method
            update_method = getattr(device, name, None)
        else:
            raise ValueError('Invalid update method')
        name = kwargs.pop('name', name)

        super().__init__(
            device.hass,
            logger=device.log,
            name=f'{device.unique_id}-{name}',
            update_method=update_method,
            **kwargs,
        )
        self.device = device

    async def _async_setup(self):
        """Set up coordinator."""
        self.async_add_listener(self.coordinator_updated)

    def coordinator_updated(self):
        _LOGGER.debug('%s: Coordinator updated: %s', self.device.name_model, [self.name, self.data])
