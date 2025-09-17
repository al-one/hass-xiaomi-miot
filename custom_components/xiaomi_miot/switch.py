"""Support for Xiaomi switches."""
import logging

from homeassistant.components.switch import (
    DOMAIN as ENTITY_DOMAIN,
    SwitchEntity as BaseEntity,
    SwitchDeviceClass,
)
from homeassistant.helpers.restore_state import RestoreEntity

from . import (
    DOMAIN,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    HassEntry,
    XEntity,
    MiotToggleEntity,
    ToggleSubEntity,
    async_setup_config_entry,
)
from .core.miot_spec import MiotService

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'


async def async_setup_entry(hass, config_entry, async_add_entities):
    HassEntry.init(hass, config_entry).new_adder(ENTITY_DOMAIN, async_add_entities)
    await async_setup_config_entry(hass, config_entry, async_setup_platform, async_add_entities, ENTITY_DOMAIN)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data.setdefault(DATA_KEY, {})
    hass.data[DOMAIN]['add_entities'][ENTITY_DOMAIN] = async_add_entities
    config['hass'] = hass


class SwitchEntity(XEntity, BaseEntity, RestoreEntity):
    def get_state(self) -> dict:
        return {self.attr: self._attr_is_on}

    def set_state(self, data: dict):
        val = self.conv.value_from_dict(data)
        if val is None:
            return
        self._attr_is_on = bool(val)

    async def async_turn_on(self):
        await self.device.async_write({self.attr: True})

    async def async_turn_off(self):
        await self.device.async_write({self.attr: False})


XEntity.CLS[ENTITY_DOMAIN] = SwitchEntity


class MiotSwitchEntity(MiotToggleEntity, BaseEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(miot_service, config=config, logger=_LOGGER)
        self._attr_icon = self._miot_service.entity_icon

    @property
    def device_class(self):
        if cls := self.get_device_class(SwitchDeviceClass):
            return cls
        typ = f'{self.model} {self._miot_service.spec.type}'
        if 'outlet' in typ or '.plug.' in typ:
            return SwitchDeviceClass.OUTLET
        return SwitchDeviceClass.SWITCH


class SwitchSubEntity(ToggleSubEntity, BaseEntity):
    def __init__(self, parent, attr='switch', option=None, **kwargs):
        kwargs.setdefault('domain', ENTITY_DOMAIN)
        super().__init__(parent, attr, option, **kwargs)

    def update(self, data=None):
        super().update(data)
