"""Support for Xiaomi lights."""
from homeassistant.components.light import *

from . import (
    DOMAIN,
    CONF_MODEL,
    ToggleSubEntity,
    bind_services_to_entries,
)

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'light.{DOMAIN}'

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    config = hass.data[DOMAIN]['configs'].get(config_entry.entry_id, config_entry.data)
    await async_setup_platform(hass, config, async_add_entities)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    if DATA_KEY not in hass.data:
        hass.data[DATA_KEY] = {}
    hass.data[DOMAIN]['add_entities']['light'] = async_add_entities
    model = config.get(CONF_MODEL)
    entities = []
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class LightSubEntity(ToggleSubEntity, LightEntity):
    _brightness = None
    _color_temp = None

    def update(self):
        super().update()
        if self._available:
            attrs = self._state_attrs
            self._brightness = attrs.get('brightness', 0)
            self._color_temp = attrs.get('color_temp', 0)

    def turn_on(self, **kwargs):
        self.call_parent(['turn_on_light', 'turn_on'], **kwargs)

    def turn_off(self, **kwargs):
        self.call_parent(['turn_off_light', 'turn_off'], **kwargs)

    @property
    def brightness(self):
        return self._brightness

    @property
    def color_temp(self):
        return self._color_temp
