import logging
from typing import TYPE_CHECKING

from homeassistant.core import HassJob, HassJobType
from homeassistant.helpers.event import async_call_later
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
        if not hasattr(self, 'setup_method'):
            # hass v2024.7-
            self.async_add_listener(self.coordinator_updated)

    async def async_setup(self, index=0):
        await self._async_setup()

        job = HassJob(self._async_refresh_later, job_type=HassJobType.Coroutinefunction)
        async_call_later(self.hass, index, job)

    async def _async_setup(self):
        """Set up coordinator."""
        self.async_add_listener(self.coordinator_updated)

    def coordinator_updated(self):
        _LOGGER.debug('%s: Coordinator updated: %s', self.device.name_model, [self.name, self.data])

    async def _async_refresh_later(self, _=None):
        await self.async_request_refresh()
