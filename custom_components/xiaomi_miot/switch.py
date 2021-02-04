"""Support for Xiaomi switches."""
import logging

from homeassistant.const import *
from homeassistant.components.switch import (
    DOMAIN as ENTITY_DOMAIN,
    SwitchEntity,
    DEVICE_CLASS_SWITCH,
    DEVICE_CLASS_OUTLET,
)

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    MiotDevice,
    MiotToggleEntity,
    ToggleSubEntity,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
    MiotProperty,
)
from .fan import MiotWasherSubEntity

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    config = hass.data[DOMAIN]['configs'].get(config_entry.entry_id, dict(config_entry.data))
    await async_setup_platform(hass, config, async_add_entities)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data.setdefault(DATA_KEY, {})
    config.setdefault('add_entities', {})
    config['add_entities'][ENTITY_DOMAIN] = async_add_entities
    model = str(config.get(CONF_MODEL) or '')
    entities = []
    miot = config.get('miot_type')
    if miot:
        spec = await MiotSpec.async_from_type(hass, miot)
        for srv in spec.get_services(ENTITY_DOMAIN, 'outlet', 'washer'):
            if not srv.get_property('on'):
                continue
            cfg = {
                **config,
                'name': f"{config.get('name')} {srv.description}"
            }
            entities.append(MiotSwitchEntity(cfg, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotSwitchEntity(MiotToggleEntity, SwitchEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        name = config[CONF_NAME]
        host = config[CONF_HOST]
        token = config[CONF_TOKEN]
        _LOGGER.info('Initializing %s with host %s (token %s...)', name, host, token[:5])

        mapping = miot_service.spec.services_mapping(ENTITY_DOMAIN, 'indicator_light', 'switch_control') or {}
        mapping.update(miot_service.mapping())
        self._device = MiotDevice(mapping, host, token)
        super().__init__(name, self._device, miot_service)
        self._add_entities = config.get('add_entities') or {}

        self._state_attrs.update({'entity_class': self.__class__.__name__})
        self._subs = {}

    @property
    def device_class(self):
        typ = f'{self._model} {self._miot_service.spec.type}'
        if typ.find('outlet') >= 0:
            return DEVICE_CLASS_OUTLET
        return DEVICE_CLASS_SWITCH

    @property
    def icon(self):
        if self._miot_service.name in ['washer']:
            return 'mdi:washing-machine'
        return super().icon

    async def async_update(self):
        await super().async_update()
        if self._available:
            if self._miot_service.name in ['washer']:
                add_fans = self._add_entities.get('fan')
                pls = self._miot_service.get_properties(
                    'mode', 'spin_speed', 'drying_level',
                    'target_temperature', 'target_water_level',
                )
                for p in pls:
                    if not p.value_list:
                        continue
                    if p.name in self._subs:
                        self._subs[p.name].update()
                    elif add_fans:
                        self._subs[p.name] = MiotWasherSubEntity(self, p)
                        add_fans([self._subs[p.name]])


class SwitchSubEntity(ToggleSubEntity, SwitchEntity):
    def update(self):
        super().update()


class MiotWasherActionSubEntity(SwitchSubEntity):
    def __init__(self, parent, miot_property: MiotProperty, option=None):
        super().__init__(parent, miot_property.full_name, option)
        self._miot_property = miot_property
        self._miot_service = miot_property.service
        self._values_on = miot_property.list_search('Busy', 'Delay')
        self._values_off = miot_property.list_search('Off', 'Idle', 'Pause', 'Fault')

    def update(self):
        super().update()
        if self._available:
            sta = self._state_attrs.get(self._attr)
            self._state = sta not in self._values_off

    def turn_on(self, **kwargs):
        val = self._values_on[0] if self._values_on else None
        return self.miot_action('start_wash', val)

    def turn_off(self, **kwargs):
        val = self._values_off[0] if self._values_off else None
        return self.miot_action('pause', val)

    def miot_action(self, act, sta=None):
        ret = False
        act = self._miot_service.get_action(act)
        if act:
            ret = self.call_parent('miot_action', self._miot_service.iid, act.iid)
            if ret and sta is not None:
                self.update_attrs({
                    self._attr: sta,
                })
        return ret

    @property
    def icon(self):
        return 'mdi:play-box'
