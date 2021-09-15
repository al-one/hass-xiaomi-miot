"""Support remote entity for Xiaomi Miot."""
import logging
import time
from functools import partial

from homeassistant.const import *  # noqa: F401
from homeassistant.components import remote
from homeassistant.components.remote import (
    DOMAIN as ENTITY_DOMAIN,
    RemoteEntity,
)

from miio.chuangmi_ir import (
    ChuangmiIr,
    DeviceException,
)

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    MiotEntity,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
)

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    await async_setup_config_entry(hass, config_entry, async_setup_platform, async_add_entities, ENTITY_DOMAIN)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data.setdefault(DATA_KEY, {})
    hass.data[DOMAIN]['add_entities'][ENTITY_DOMAIN] = async_add_entities
    model = str(config.get(CONF_MODEL) or '')
    entities = []
    miot = config.get('miot_type')
    if miot:
        spec = await MiotSpec.async_from_type(hass, miot)
        if spec.name in ['remote_control', 'ir_remote_control']:
            if 'chuangmi.remote.' in model:
                entities.append(MiotRemoteEntity(config, spec))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotRemoteEntity(MiotEntity, RemoteEntity):
    def __init__(self, config, miot_spec: MiotSpec):
        self._miot_spec = miot_spec
        super().__init__(miot_service=None, config=config, logger=_LOGGER)
        host = config.get(CONF_HOST)
        token = config.get(CONF_TOKEN)
        self._device = ChuangmiIr(host, token)
        self._attr_should_poll = False
        self._state_attrs.update({'entity_class': self.__class__.__name__})

    def is_on(self):
        return True

    def send_remote_command(self, command, **kwargs):
        """Send commands to a device."""
        repeat = kwargs.get(remote.ATTR_NUM_REPEATS, remote.DEFAULT_NUM_REPEATS)
        delays = kwargs.get(remote.ATTR_DELAY_SECS, remote.DEFAULT_DELAY_SECS)
        for _ in range(repeat):
            for cmd in command:
                try:
                    ret = self._device.play(cmd)
                    self.logger.debug('%s: Send IR command %s(%s) result: %s', self.name, cmd, kwargs, ret)
                except DeviceException as exc:
                    self.logger.error('%s: Send IR command %s(%s) failed: %s', self.name, cmd, kwargs, exc)
                time.sleep(delays)

    async def async_send_command(self, command, **kwargs):
        """Send commands to a device."""
        await self.hass.async_add_executor_job(
            partial(self.send_remote_command, command, **kwargs)
        )

    def learn_command(self, **kwargs):
        """Learn a command from a device."""
        raise NotImplementedError()

    def delete_command(self, **kwargs):
        """Delete commands from the database."""
        raise NotImplementedError()
