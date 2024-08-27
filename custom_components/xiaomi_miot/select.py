"""Support select entity for Xiaomi Miot."""
import logging

from homeassistant.components.select import (
    DOMAIN as ENTITY_DOMAIN,
    SelectEntity,
)

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    MiotEntity,
    BaseSubEntity,
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
        for srv in spec.get_services('ir_aircondition_control'):
            if not srv.actions:
                continue
            entities.append(MiotActionsEntity(config, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotSelectEntity(MiotEntity, SelectEntity):
    def __init__(self, config, miot_service: MiotService):
        super().__init__(miot_service, config=config, logger=_LOGGER)
        self._attr_current_option = None

    def select_option(self, option):
        """Change the selected option."""
        raise NotImplementedError()


class MiotActionsEntity(MiotSelectEntity):
    def __init__(self, config, miot_service: MiotService):
        super().__init__(config, miot_service)
        als = []
        for a in miot_service.actions.values():
            anm = a.friendly_desc or a.name
            als.append(anm)
        self._attr_options = als

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if p := self._miot_service.get_property('ir_mode'):
            self._state_attrs[p.full_name] = None
            self._update_sub_entities([p.name], domain='select', whatever=True)
        if p := self._miot_service.get_property('ir_temperature'):
            self._state_attrs[p.full_name] = None
            self._update_sub_entities([p.name], domain='number', whatever=True)

    def select_option(self, option):
        """Change the selected option."""
        ret = False
        act = self._miot_service.search_action(option)
        if act:
            if ret := self.call_action(act):
                self._attr_current_option = option
                self.schedule_update_ha_state()
                self._attr_current_option = None
        return ret


class MiotSelectSubEntity(SelectEntity, MiotPropertySubEntity):
    def __init__(self, parent, miot_property: MiotProperty, option=None):
        MiotPropertySubEntity.__init__(self, parent, miot_property, option, domain=ENTITY_DOMAIN)
        self._attr_options = miot_property.list_descriptions()

    def update(self, data=None):
        super().update(data)
        if not self._available:
            return
        val = self._miot_property.from_dict(self._state_attrs)
        if val is None:
            self._attr_current_option = None
        else:
            des = self._miot_property.list_description(val)
            stp = self._miot_property.range_step()
            if stp and stp % 1 > 0:
                des = float(des)
            self._attr_current_option = str(des)

    def select_option(self, option):
        """Change the selected option."""
        val = self._miot_property.list_value(option)
        if val is not None:
            if bfs := self._option.get('before_select'):
                bfs(self._miot_property, option)
            return self.set_parent_property(val)
        return False


class MiotActionSelectSubEntity(MiotSelectSubEntity):
    def __init__(self, parent, miot_action: MiotAction, miot_property: MiotProperty = None, option=None):
        if not miot_property:
            miot_property = miot_action.in_properties()[0] if miot_action.ins else None
        super().__init__(parent, miot_property, option)
        self._miot_action = miot_action
        self._attr_current_option = None
        self._attr_options = miot_property.list_descriptions()
        self._extra_actions = self._option.get('extra_actions') or {}
        if self._extra_actions:
            self._attr_options.extend(self._extra_actions.keys())

        self._state_attrs.update({
            'miot_action': miot_action.full_name,
        })

    def update(self, data=None):
        self._available = True
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
            self.schedule_update_ha_state()
        return ret


class SelectSubEntity(SelectEntity, BaseSubEntity):
    def __init__(self, parent, attr, option=None):
        BaseSubEntity.__init__(self, parent, attr, option)
        self._available = True
        self._attr_current_option = None
        self._attr_options = self._option.get('options') or []
        self._select_option = self._option.get('select_option')

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

    def update_options(self, options: list):
        self._attr_options = options
