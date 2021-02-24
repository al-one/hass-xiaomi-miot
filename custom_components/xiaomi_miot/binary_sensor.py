"""Support for Xiaomi binary sensors."""
import logging

from homeassistant.const import *
from homeassistant.components.binary_sensor import (
    DOMAIN as ENTITY_DOMAIN,
    BinarySensorEntity,
)

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    MiotDevice,
    MiotToggleEntity,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
)
from .fan import MiotModesSubEntity
from .switch import SwitchSubEntity

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
        for srv in spec.get_services('toilet'):
            if not srv.mapping():
                continue
            cfg = {
                **config,
                'name': f"{config.get('name')} {srv.description}"
            }
            entities.append(MiotBinarySensorEntity(cfg, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotBinarySensorEntity(MiotToggleEntity, BinarySensorEntity):
    def __init__(self, config, miot_service: MiotService, **kwargs):
        name = config[CONF_NAME]
        host = config[CONF_HOST]
        token = config[CONF_TOKEN]
        _LOGGER.info('Initializing with host %s (token %s...)', host, token[:5])

        self._miot_service = miot_service
        mapping = dict(kwargs.get('mapping') or {})
        mapping.update(miot_service.mapping())
        self._device = MiotDevice(mapping, host, token)
        super().__init__(name, self._device, miot_service, config=config)
        self._add_entities = config.get('add_entities') or {}

        self._state_attrs.update({'entity_class': self.__class__.__name__})
        self._subs = {}

        pls = []
        if len(miot_service.properties) > 0:
            first_property = list(miot_service.properties.values() or [])[0].name
            if first_property:
                pls.append(first_property)
        self._prop_state = miot_service.get_property(*pls)

    @property
    def is_on(self):
        if self._prop_state:
            return self._prop_state.from_dict(self._state_attrs) and True
        return None

    @property
    def state(self):
        return STATE_ON if self.is_on else STATE_OFF

    @property
    def device_class(self):
        return None


class MiotToiletEntity(MiotBinarySensorEntity):
    def __init__(self, config, miot_service: MiotService):
        mapping = miot_service.spec.services_mapping('seat') or {}
        super().__init__(config, miot_service, mapping=mapping)
        self._prop_state = miot_service.get_property('seating_state')
        if not self._prop_state:
            self._prop_state = miot_service.get_property(
                'mode', self._prop_state.name if self._prop_state else 'status',
            )

    async def async_update(self):
        await super().async_update()
        if not self._available:
            return
        add_fans = self._add_entities.get('fan')
        pls = self._miot_service.get_properties(
            'mode', 'washing_strength', 'nozzle_position',
        )
        for p in pls:
            if not p.value_list:
                continue
            if p.name in self._subs:
                self._subs[p.name].update()
            elif add_fans:
                self._subs[p.name] = MiotModesSubEntity(self, p)
                add_fans([self._subs[p.name]])

            add_switches = self._add_entities.get('switch')
            if self._prop_power:
                pnm = self._prop_state.full_name
                if pnm in self._subs:
                    self._subs[pnm].update()
                elif add_switches:
                    self._subs[pnm] = SwitchSubEntity(self, pnm)
                    add_switches([self._subs[pnm]])
