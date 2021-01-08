"""Support for Xiaomi switches."""
from homeassistant.components.switch import *

from . import (
    DOMAIN,
    CONF_MODEL,
    ToggleSubEntity,
    bind_services_to_entries,
)

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'switch.{DOMAIN}'

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    config = hass.data[DOMAIN]['configs'].get(config_entry.entry_id, dict(config_entry.data))
    await async_setup_platform(hass, config, async_add_entities)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data.setdefault(DATA_KEY, {})
    config.setdefault('add_entities', {})
    config['add_entities']['switch'] = async_add_entities
    model = config.get(CONF_MODEL)
    entities = []
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class SwitchSubEntity(ToggleSubEntity, SwitchEntity):
    def update(self):
        super().update()
