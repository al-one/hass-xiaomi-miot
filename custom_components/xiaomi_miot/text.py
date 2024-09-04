"""Support text entity for Xiaomi Miot."""
import logging
import time

from homeassistant.components.text import (
    DOMAIN as ENTITY_DOMAIN,
    TextEntity,
)

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    MiotEntity,
    MiotPropertySubEntity,
    BaseSubEntity,
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
            entities.append(MiotTextEntity(config, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotTextEntity(MiotEntity, TextEntity):
    _attr_native_value = ''

    def __init__(self, config, miot_service: MiotService):
        super().__init__(miot_service, config=config, logger=_LOGGER)

    def set_value(self, value):
        """Change the value."""
        self._attr_native_value = value
        raise NotImplementedError()


class MiotTextSubEntity(MiotPropertySubEntity, TextEntity):
    _attr_native_value = ''

    def update(self, data=None):
        super().update(data)
        if not self._available:
            return
        self._attr_native_value = self._attr_state

    def set_value(self, value):
        """Change the value."""
        self._attr_native_value = value
        return self.set_parent_property(value)


class MiotTextActionSubEntity(BaseSubEntity, TextEntity):
    _attr_native_value = ''

    def __init__(self, parent, miot_action: MiotAction, option=None):
        self._miot_action = miot_action
        super().__init__(parent, miot_action.full_name, option, domain=ENTITY_DOMAIN)
        self._name = f'{parent.device_name} {miot_action.friendly_desc}'.strip()
        self._unique_id = f'{parent.unique_did}-{miot_action.unique_name}'
        self.entity_id = miot_action.service.spec.generate_entity_id(self, miot_action.name)
        self._extra_attrs.update({
            'service_description': miot_action.service.description,
            'action_description': miot_action.description,
        })
        self._available = True

    def update(self, data=None):
        if data:
            self.update_attrs(data, update_parent=False)

    def set_value(self, value):
        """Change the value."""
        if self._miot_action.name in ['execute_text_directive']:
            silent = self.custom_config_integer('silent_execution', 0)
            ret = self.call_parent('intelligent_speaker', value, True, silent)
        else:
            ret = self.call_parent('call_action', self._miot_action, [value])

        if ret:
            self._attr_native_value = value
            self.schedule_update_ha_state()
            time.sleep(0.5)
            self._attr_native_value = ''
        return ret
