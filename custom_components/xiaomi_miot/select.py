"""Support select entity for Xiaomi Miot."""
import logging

from homeassistant.components.select import (
    DOMAIN as ENTITY_DOMAIN,
    SelectEntity as BaseEntity,
)
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.event import async_call_later

from . import (
    DOMAIN,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    HassEntry,
    XEntity,
    BaseSubEntity,
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
    hass.data.setdefault(DATA_KEY, {})
    hass.data[DOMAIN]['add_entities'][ENTITY_DOMAIN] = async_add_entities
    config['hass'] = hass
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class SelectEntity(XEntity, BaseEntity, RestoreEntity):
    _attr_current_option = None
    _attr_options = []

    def on_init(self):
        if self._miot_property:
            self._attr_options = self._miot_property.list_descriptions()
        if self._miot_action:
            self._attr_options.insert(0, '')
        if lst := getattr(self.conv, 'options', None):
            self._attr_options = lst
        self._attr_available = True

    def get_state(self) -> dict:
        return {self.attr: self._attr_current_option}

    def set_state(self, data: dict):
        val = self.conv.value_from_dict(data)
        if val is None:
            return
        self._attr_current_option = val

    async def async_select_option(self, option: str):
        if self._miot_action and option == '':
            return

        await self.device.async_write({self.attr: option})

        if self._miot_action:
            self._attr_current_option = ''
            async_call_later(self.hass, 0.5, self.schedule_update_ha_state)


XEntity.CLS[ENTITY_DOMAIN] = SelectEntity


class SelectSubEntity(BaseEntity, BaseSubEntity):
    def __init__(self, parent, attr, option=None):
        BaseSubEntity.__init__(self, parent, attr, option)
        self._available = True
        self._attr_current_option = None
        self._attr_options = self._option.get('options') or []
        self._select_option = self._option.get('select_option')
        self._async_select_option = self._option.get('async_select_option')

    def update(self, data=None):
        super().update(data)
        self._attr_current_option = self._attr_state
        self.schedule_update_ha_state()

    def select_option(self, option):
        """Change the selected option."""
        if self._select_option:
            kws = {
                'attr': self._attr,
                'option': self._option,
            }
            if ret := self._select_option(option, **kws):
                self._attr_current_option = option
                self.schedule_update_ha_state()
            return ret
        raise NotImplementedError()

    async def async_select_option(self, option: str):
        """Change the selected option."""
        if self._async_select_option:
            kws = {
                'attr': self._attr,
                'option': self._option,
            }
            if ret := await self._async_select_option(option, **kws):
                self._attr_current_option = option
                self.schedule_update_ha_state()
            return ret
        raise NotImplementedError()

    def update_options(self, options: list):
        self._attr_options = options
