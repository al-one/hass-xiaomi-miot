"""Support time entity for Xiaomi Miot."""
import logging

from homeassistant.components.time import (
    DOMAIN as ENTITY_DOMAIN,
    TimeEntity as BaseEntity,
)

from . import (
    DOMAIN,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    HassEntry,
    XEntity,
    async_setup_config_entry,
    bind_services_to_entries,
)

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    HassEntry.init(hass, config_entry).new_adder(ENTITY_DOMAIN, async_add_entities)
    await async_setup_config_entry(hass, config_entry, async_setup_platform, async_add_entities, ENTITY_DOMAIN)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data[DOMAIN]['add_entities'][ENTITY_DOMAIN] = async_add_entities
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class TimeEntity(XEntity, BaseEntity):
    _attr_native_value = None

    def get_state(self) -> dict:
        return {self.attr: self._attr_native_value}

    def set_state(self, data: dict):
        val = self.conv.value_from_dict(data)
        if val is not None:
            self._attr_native_value = val

    async def async_set_value(self, value):
        await self.device.async_write({self.attr: value})


XEntity.CLS[ENTITY_DOMAIN] = TimeEntity
