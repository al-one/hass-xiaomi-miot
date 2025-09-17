"""Support text entity for Xiaomi Miot."""
import logging

from homeassistant.components.text import (
    DOMAIN as ENTITY_DOMAIN,
    TextEntity as BaseEntity,
)

from . import (
    DOMAIN,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    HassEntry,
    XEntity,
    async_setup_config_entry,
)

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    HassEntry.init(hass, config_entry).new_adder(ENTITY_DOMAIN, async_add_entities)
    await async_setup_config_entry(hass, config_entry, async_setup_platform, async_add_entities, ENTITY_DOMAIN)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data.setdefault(DATA_KEY, {})


class TextEntity(XEntity, BaseEntity):
    _attr_native_value = ''

    def get_state(self) -> dict:
        return {self.attr: self._attr_native_value}

    def set_state(self, data: dict):
        val = self.conv.value_from_dict(data)
        if val is None:
            return
        if isinstance(val, list):
            val = val[0] if val else None
            if val is None:
                val = ''
        self._attr_native_value = val

    async def async_set_value(self, value: str):
        if self._miot_action and self._miot_action.name == 'execute_text_directive':
            silent = self.custom_config_integer('silent_execution', 0)
            silent_prop = self._miot_service.get_property('silent_execution')
            if silent_prop:
                """
                xiaomi.wifispeaker.07g  bool
                xiaomi.wifispeaker.16b  bool
                xiaomi.wifispeaker.l04m 0:On 1:Off
                xiaomi.wifispeaker.l05b bool
                xiaomi.wifispeaker.l05c bool
                xiaomi.wifispeaker.l05g bool
                xiaomi.wifispeaker.l06a 0:On 1:Off
                xiaomi.wifispeaker.l09a 0:On 1:Off
                xiaomi.wifispeaker.l09b bool
                xiaomi.wifispeaker.l15a bool
                xiaomi.wifispeaker.l16a bool
                xiaomi.wifispeaker.l17a bool
                xiaomi.wifispeaker.l7a  0:On 1:Off
                xiaomi.wifispeaker.lx01 0:On 1:Off
                xiaomi.wifispeaker.lx04 0:On 1:Off
                xiaomi.wifispeaker.lx05 bool
                xiaomi.wifispeaker.lx06 bool
                xiaomi.wifispeaker.lx5a bool
                xiaomi.wifispeaker.m03a bool
                xiaomi.wifispeaker.s12  bool
                xiaomi.wifispeaker.x08a 0:On 1:Off
                xiaomi.wifispeaker.x08c 0:On 1:Off
                xiaomi.wifispeaker.x08e bool
                xiaomi.wifispeaker.x10a bool
                xiaomi.wifispeaker.x6a  bool
                xiaomi.wifispeaker.x8f  bool
                xiaomi.wifispeaker.x8s  bool
                """
                if silent_prop.value_list:
                    val = silent_prop.list_value('On' if silent else 'Off')
                    if val is None:
                        val = 0 if silent else 1
                    silent = val
                value = [value, silent]

        await self.device.async_write({self.attr: value})

        if self._miot_action:
            self._attr_native_value = ''
            self.schedule_update_ha_state()


XEntity.CLS[ENTITY_DOMAIN] = TextEntity
