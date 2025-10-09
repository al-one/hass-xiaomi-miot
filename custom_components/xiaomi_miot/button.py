"""Support button entity for Xiaomi Miot."""
import logging

from homeassistant.components.button import (
    DOMAIN as ENTITY_DOMAIN,
    ButtonEntity as BaseEntity,
)

from . import (
    DOMAIN,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    HassEntry,
    XEntity,
    BaseSubEntity,
    async_setup_config_entry,
)
from .core.templates import template

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    HassEntry.init(hass, config_entry).new_adder(ENTITY_DOMAIN, async_add_entities)
    await async_setup_config_entry(hass, config_entry, async_setup_platform, async_add_entities, ENTITY_DOMAIN)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data.setdefault(DATA_KEY, {})


class ButtonEntity(XEntity, BaseEntity):
    def on_init(self):
        self._attr_available = True
        if des := getattr(self.conv, 'description', None):
            self._attr_name = f'{self._attr_name} {des}'

    def set_state(self, data: dict):
        pass

    async def async_press(self):
        pms = getattr(self.conv, 'value', None)
        if self._miot_action and self._miot_action.ins:
            pms = self.custom_config_list('action_params', pms)
            if pms:
                vars = {
                    'attrs': self.device.props,
                }
                pms = [
                    v if not isinstance(v, str) else template(v, self.hass).async_render(vars)
                    for v in pms
                ]
        await self.device.async_write({self.attr: pms})


XEntity.CLS[ENTITY_DOMAIN] = ButtonEntity


class ButtonSubEntity(BaseEntity, BaseSubEntity):
    def __init__(self, parent, attr, option=None):
        BaseSubEntity.__init__(self, parent, attr, option)
        self._available = True
        self._async_action = self._option.get('async_press_action')
        self._press_action = self._option.get('press_action')
        self._press_kwargs = {
            'attr': self._attr,
            **(self._option.get('press_kwargs') or {}),
        }
        self._state_attrs = self._option.get('state_attrs') or {}

    def update(self, data=None):
        return

    def press(self):
        """Press the button."""
        if not self._press_action:
            raise NotImplementedError()
        if ret := self._press_action(**self._press_kwargs):
            self.schedule_update_ha_state()
        return ret

    async def async_press(self):
        if self._async_action:
            if ret := await self._async_action(**self._press_kwargs):
                self.schedule_update_ha_state()
            return ret
        await super().async_press()
