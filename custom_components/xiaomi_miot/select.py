"""Support select entity for Xiaomi Miot."""
import logging
import time

from homeassistant.const import *  # noqa: F401
from homeassistant.components.select import (
    DOMAIN as ENTITY_DOMAIN,
    SelectEntity,
)

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    MiotEntity,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
    MiotProperty,
    MiotAction,
)
from .sensor import MiotSensorSubEntity

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
            entities.append(MiotSelectEntity(config, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotSelectEntity(MiotEntity, SelectEntity):
    def __init__(self, config, miot_service: MiotService):
        super().__init__(miot_service, config=config, logger=_LOGGER)
        self._state_attrs.update({'entity_class': self.__class__.__name__})

    def select_option(self, option):
        """Change the selected option."""
        raise NotImplementedError()


class MiotSelectSubEntity(MiotSensorSubEntity, SelectEntity):
    def __init__(self, parent, miot_property: MiotProperty, option=None):
        super().__init__(parent, miot_property, option)
        self._attr_options = miot_property.list_descriptions()

    def update(self):
        super().update()
        if not self._available:
            return
        val = self._miot_property.from_dict(self._state_attrs)
        if val is None:
            self._attr_current_option = None
        else:
            self._attr_current_option = self._miot_property.list_description(val)

    def select_option(self, option):
        """Change the selected option."""
        val = self._miot_property.list_value(option)
        if val is not None:
            return self.set_parent_property(val)
        return False


class MiotActionSelectSubEntity(MiotSelectSubEntity):
    def __init__(self, parent, miot_action: MiotAction, miot_property: MiotProperty, option=None):
        super().__init__(parent, miot_property, option)
        self._miot_action = miot_action
        self._attr_options = miot_property.list_descriptions()
        self._extra_actions = self._option.get('extra_actions') or {}
        if self._extra_actions:
            self._attr_options.extend(self._extra_actions.keys())

        self.update_attrs({
            'miot_action': miot_action.full_name,
        }, update_parent=False)

    def update(self):
        self._available = True
        time.sleep(0.2)
        self._attr_current_option = None

    def select_option(self, option):
        """Change the selected option."""
        ret = None
        val = self._miot_property.list_value(option)
        if val is None:
            act = self._extra_actions.get(option)
            if isinstance(act, MiotAction):
                ret = self.call_parent('call_action', act)
            else:
                return False
        if ret is None:
            pms = [val] if self._miot_action.ins else []
            ret = self.call_parent('call_action', self._miot_action, pms)
        if ret:
            self._attr_current_option = option
            self.async_write_ha_state()
        return ret
