"""Support number entity for Xiaomi Miot."""
import logging

from homeassistant.const import *  # noqa: F401
from homeassistant.components.number import (
    DOMAIN as ENTITY_DOMAIN,
    NumberEntity,
)

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    MiotEntity,
    MiotSensorSubEntity,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
    MiotProperty,
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
        for srv in spec.get_services('none_service'):
            if not srv.get_property('none_property'):
                continue
            cfg = {
                **config,
                'name': f"{config.get('name')} {srv.description}"
            }
            entities.append(MiotNumberEntity(cfg, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotNumberEntity(MiotEntity, NumberEntity):
    def __init__(self, config, miot_service: MiotService):
        super().__init__(miot_service, config=config)
        self._state_attrs.update({'entity_class': self.__class__.__name__})

    @property
    def value(self):
        """Return the entity value to represent the entity state."""
        return 0

    def set_value(self, value: float):
        """Set new value."""
        raise NotImplementedError()


class MiotNumberSubEntity(MiotSensorSubEntity, NumberEntity):
    def __init__(self, parent, miot_property: MiotProperty, option=None):
        super().__init__(parent, miot_property, option)

    @property
    def value(self):
        """Return the entity value to represent the entity state."""
        val = self._miot_property.from_dict(self._state_attrs)
        try:
            val = float(val)
        except (TypeError, ValueError):
            val = 0
        return val

    def set_value(self, value: float):
        """Set new value."""
        return self.set_parent_property(value)

    @property
    def min_value(self):
        """Return the minimum value."""
        return self._miot_property.range_min()

    @property
    def max_value(self):
        """Return the maximum value."""
        return self._miot_property.range_max()

    @property
    def step(self):
        """Return the increment/decrement step."""
        return self._miot_property.range_step()
