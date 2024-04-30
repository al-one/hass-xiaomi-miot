"""Support number entity for Xiaomi Miot."""
import logging

from homeassistant.components.number import (
    DOMAIN as ENTITY_DOMAIN,
    NumberEntity,
    RestoreNumber,
)

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    MiotEntity,
    MiotPropertySubEntity,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
    MiotProperty,
    MiotAction,
)

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    await async_setup_config_entry(hass, config_entry, async_setup_platform, async_add_entities, ENTITY_DOMAIN)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data.setdefault(DATA_KEY, {})
    hass.data[DOMAIN]['add_entities'][ENTITY_DOMAIN] = async_add_entities
    config['hass'] = hass
    model = str(config.get(CONF_MODEL) or '')
    spec = hass.data[DOMAIN]['miot_specs'].get(model)
    entities = []
    if isinstance(spec, MiotSpec):
        for srv in spec.get_services('none_service'):
            if not srv.get_property('none_property'):
                continue
            entities.append(MiotNumberEntity(config, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotNumberEntity(MiotEntity, NumberEntity):

    def __init__(self, config, miot_service: MiotService):
        super().__init__(miot_service, config=config, logger=_LOGGER)
        self._attr_native_value = 0
        self._attr_native_unit_of_measurement = None


class MiotNumberSubEntity(MiotPropertySubEntity, RestoreNumber):

    def __init__(self, parent, miot_property: MiotProperty, option=None):
        super().__init__(parent, miot_property, option, domain=ENTITY_DOMAIN)
        self._attr_native_max_value = self._miot_property.range_max()
        self._attr_native_min_value = self._miot_property.range_min()
        self._attr_native_step = self._miot_property.range_step()
        self._attr_native_value = 0
        self._attr_native_unit_of_measurement = self._miot_property.unit_of_measurement
        self._is_restore = False

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._is_restore = self.custom_config_bool('restore_state')
        if self._is_restore:
            if restored := await self.async_get_last_number_data():
                self._attr_native_value = restored.native_value

    def update(self, data=None):
        super().update(data)
        val = self.native_value
        if val is not None:
            self._attr_native_value = val

    @property
    def native_value(self):
        val = self._miot_property.from_dict(self._state_attrs)
        return val

    def cast_value(self, val, default=None):
        try:
            val = round(float(val), 6)
            if self._miot_property.is_integer:
                val = int(val)
        except (TypeError, ValueError):
            val = default
        return val

    def set_native_value(self, value):
        """Set new value."""
        if self._miot_property.is_integer:
            value = int(value)
        return self.set_parent_property(value)


class MiotNumberActionSubEntity(MiotNumberSubEntity):
    def __init__(self, parent, miot_property: MiotProperty, miot_action: MiotAction, option=None):
        super().__init__(parent, miot_property, option)
        self._miot_action = miot_action
        self._state_attrs.update({
            'miot_action': miot_action.full_name,
        })

    def update(self, data=None):
        self._available = True
        self._attr_native_value = 0

    def set_native_value(self, value):
        """Set new value."""
        val = int(value)
        ret = self.call_parent('call_action', self._miot_action, [val])
        if ret:
            self._attr_native_value = val
            self.schedule_update_ha_state()
        return ret
