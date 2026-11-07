"""Support number entity for Xiaomi Miot."""
import logging
import math

from homeassistant.components.number import (
    DOMAIN as ENTITY_DOMAIN,
    RestoreNumber,
    NumberMode,
)
from homeassistant.helpers.event import async_call_later
from homeassistant.exceptions import ServiceValidationError

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


class NumberEntity(XEntity, RestoreNumber):
    _attr_mode = NumberMode.AUTO

    def on_init(self):
        if self._miot_property:
            self._attr_native_step = self._miot_property.range_step()
            self._attr_native_max_value = self._miot_property.range_max()
            self._attr_native_min_value = self._miot_property.range_min()
            self._attr_native_unit_of_measurement = self._miot_property.unit_of_measurement

    def get_state(self) -> dict:
        return {self.attr: self._attr_native_value}

    def set_state(self, data: dict):
        val = self.conv.value_from_dict(data)
        if val is None:
            return
        self._attr_native_value = val

    def _validated_native_value(self, value: float):
        if not math.isfinite(value):
            raise ServiceValidationError('Number value must be finite')
        if self._miot_property and self._miot_property.is_integer:
            if not math.isclose(value, round(value), rel_tol=0, abs_tol=1e-9):
                raise ServiceValidationError('Number value must be an integer')
            # Avoid truncating floating-point representation noise in the converter.
            value = round(value)
        step = self.native_step
        if step and step > 0:
            position = (value - self.native_min_value) / step
            if not math.isclose(position, round(position), rel_tol=0, abs_tol=1e-7):
                raise ServiceValidationError('Number value does not match the native step')
        return value

    async def async_set_native_value(self, value: float):
        value = self._validated_native_value(value)
        await self.device.async_write({self.attr: value})

        if self._miot_action:
            self._attr_native_value = None
            async_call_later(self.hass, 0.5, self.schedule_update_ha_state)


XEntity.CLS[ENTITY_DOMAIN] = NumberEntity
