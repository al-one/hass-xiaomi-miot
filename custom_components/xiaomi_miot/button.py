"""Support button entity for Xiaomi Miot."""
import logging

from homeassistant.const import *  # noqa: F401
from homeassistant.components.button import (
    DOMAIN as ENTITY_DOMAIN,
    ButtonEntity,
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
            entities.append(MiotButtonEntity(config, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotButtonEntity(MiotEntity, ButtonEntity):
    def __init__(self, config, miot_service: MiotService):
        super().__init__(miot_service, config=config, logger=_LOGGER)

    def press(self) -> None:
        """Press the button."""
        raise NotImplementedError()


class MiotButtonSubEntity(MiotPropertySubEntity, ButtonEntity):
    def __init__(self, parent, miot_property: MiotProperty, value, option=None):
        super().__init__(parent, miot_property, option)
        self._miot_property_value = value
        self._miot_property_desc = None
        if miot_property.value_list:
            self._miot_property_desc = miot_property.list_description(value)
        if self._miot_property_desc is None:
            self._miot_property_desc = value
        self._name = f'{self._name} {self._miot_property_desc}'.strip()
        self.entity_id = f'{self.entity_id}_{self._miot_property_value}'.strip()
        self._unique_id = f'{self._unique_id}-value{self._miot_property_value}'.strip()
        self._extra_attrs.update({
            'property_value': self._miot_property_value,
            'value_description': self._miot_property_desc,
        })
        self._available = True

    def update(self, data=None):
        if data:
            self.update_attrs(data, update_parent=False)

    def press(self):
        """Press the button."""
        return self.set_parent_property(self._miot_property_value)
