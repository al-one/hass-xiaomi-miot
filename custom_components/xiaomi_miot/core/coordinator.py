import asyncio
import inspect
import logging
import time
from typing import TYPE_CHECKING

from homeassistant.core import HassJob, HassJobType
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

if TYPE_CHECKING:
    from .device import Device

_LOGGER = logging.getLogger(__name__)

# Minimum gap in seconds between physical device polls, including
# write-initiated refreshes that bypass the HA debouncer. Bursts of writes
# are coalesced with a trailing edge: the confirmed poll still runs, just
# not sooner than this gap after the previous one. The scheduled cadence
# stays bound by update_interval.
MIN_DEVICE_POLL_GAP_SECONDS = 3.0

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

        config_entry = getattr(device.entry, 'entry', getattr(device, 'entry', None)) if hasattr(device, 'entry') else None
        if config_entry and 'config_entry' in inspect.signature(DataUpdateCoordinator.__init__).parameters:
            kwargs.setdefault('config_entry', config_entry)
        self._device_update_method = update_method
        self._device_update_lock = asyncio.Lock()
        self._device_update_tasks = set()
        self._last_poll_monotonic = None

        super().__init__(
            device.hass,
            logger=device.log,
            name=f'{device.unique_id}-{name}',
            update_method=self._async_update if callable(update_method) else None,
            **kwargs,
        )
        self.device = device
        self._unsub_setup_refresh = None
        if not hasattr(self, 'setup_method'):
            # hass v2024.7-
            self.async_add_listener(self.coordinator_updated)

    async def _async_update(self):
        task = asyncio.current_task()
        if self._shutdown_requested:
            if task:
                task.cancel()
            raise asyncio.CancelledError
        if task:
            self._device_update_tasks.add(task)
        try:
            async with self._device_update_lock:
                if self._shutdown_requested:
                    if task:
                        task.cancel()
                    raise asyncio.CancelledError
                if self._device_update_method is None:
                    raise NotImplementedError('Update method not implemented')
                if self._last_poll_monotonic is not None:
                    delay = MIN_DEVICE_POLL_GAP_SECONDS - (time.monotonic() - self._last_poll_monotonic)
                    if delay > 0:
                        _LOGGER.debug('%s: Coalesce device poll for %.1fs', self.device.name_model, delay)
                        await asyncio.sleep(delay)
                try:
                    return await self._device_update_method()
                finally:
                    self._last_poll_monotonic = time.monotonic()
        finally:
            if task:
                self._device_update_tasks.discard(task)

    async def async_setup(self, index=0):
        await self._async_setup()

        job = HassJob(self._async_refresh_later, job_type=HassJobType.Coroutinefunction)
        self._unsub_setup_refresh = async_call_later(self.hass, index, job)

    async def async_shutdown(self):
        if self._unsub_setup_refresh:
            self._unsub_setup_refresh()
            self._unsub_setup_refresh = None
        await super().async_shutdown()
        tasks = self._device_update_tasks - {asyncio.current_task()}
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _async_setup(self):
        """Set up coordinator."""
        self.async_add_listener(self.coordinator_updated)

    def coordinator_updated(self):
        _LOGGER.debug('%s: Coordinator updated: %s', self.device.name_model, [self.name, self.data])

    async def _async_refresh_later(self, _=None):
        await self.async_request_refresh()
