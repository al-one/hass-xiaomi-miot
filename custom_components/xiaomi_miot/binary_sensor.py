"""Support for Xiaomi binary sensors."""
import logging

from homeassistant.const import *  # noqa: F401
from homeassistant.components.binary_sensor import (
    DOMAIN as ENTITY_DOMAIN,
    BinarySensorEntity,
    DEVICE_CLASS_MOTION,
    DEVICE_CLASS_DOOR,
    DEVICE_CLASS_SAFETY,
)

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    MiotToggleEntity,
    ToggleSubEntity,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
    MiotProperty,
)
from .fan import MiotModesSubEntity
from .switch import SwitchSubEntity

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
        for srv in spec.get_services('toilet', 'motion_sensor', 'magnet_sensor', 'submersion_sensor'):
            if not srv.mapping():
                continue
            cfg = {
                **config,
                'name': f"{config.get('name')} {srv.description}"
            }
            if srv.name in ['toilet']:
                entities.append(MiotToiletEntity(cfg, srv))
            else:
                entities.append(MiotBinarySensorEntity(cfg, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotBinarySensorEntity(MiotToggleEntity, BinarySensorEntity):
    def __init__(self, config, miot_service: MiotService, **kwargs):
        super().__init__(miot_service, config=config, **kwargs)

        pls = []
        if len(miot_service.properties) > 0:
            first_property = list(miot_service.properties.values() or [])[0].name
            if first_property:
                pls.append(first_property)
        self._prop_state = miot_service.get_property(*pls)

        if miot_service.name in ['motion_sensor']:
            self._prop_state = miot_service.get_property('motion_state') or self._prop_state
            self._vars['device_class'] = DEVICE_CLASS_MOTION

        if miot_service.name in ['magnet_sensor']:
            self._prop_state = miot_service.get_property('contact_state') or self._prop_state
            self._vars['device_class'] = DEVICE_CLASS_DOOR

        if miot_service.name in ['submersion_sensor']:
            self._prop_state = miot_service.get_property('submersion_state') or self._prop_state
            self._vars['device_class'] = DEVICE_CLASS_SAFETY

        self._state_attrs.update({
            'entity_class': self.__class__.__name__,
            'state_property': self._prop_state.full_name if self._prop_state else None,
        })

    async def async_update(self):
        await super().async_update()
        if not self._available:
            return
        self._update_sub_entities(['illumination', 'no_motion_duration'], domain='sensor')

    @property
    def is_on(self):
        if self._prop_state:
            return self._prop_state.from_dict(self._state_attrs) and True
        return None

    @property
    def state(self):
        iso = self.is_on
        if iso is None:
            return STATE_UNKNOWN
        return STATE_ON if iso else STATE_OFF

    @property
    def device_class(self):
        return self._vars.get('device_class')


class MiotToiletEntity(MiotBinarySensorEntity):
    def __init__(self, config, miot_service: MiotService):
        mapping = None
        model = f'{config.get(CONF_MODEL)}'
        if model.find('xjx.toilet.') >= 0:
            mapping = miot_service.spec.services_mapping('toilet', 'seat')
        super().__init__(config, miot_service, mapping=mapping)
        self._prop_state = miot_service.get_property('seating_state')
        if not self._prop_state:
            self._prop_state = miot_service.get_property(
                'mode', self._prop_state.name if self._prop_state else 'status',
            )
        self._state_attrs.update({
            'entity_class': self.__class__.__name__,
            'state_property': self._prop_state.full_name if self._prop_state else None,
        })

    async def async_update(self):
        await super().async_update()
        if not self._available:
            return
        add_fans = self._add_entities.get('fan')
        pls = self._miot_service.get_properties(
            'mode', 'washing_strength', 'nozzle_position', 'heat_level',
        )
        seat = self._miot_service.spec.get_service('seat')
        if seat:
            prop = seat.get_property('heat_level')
            if prop:
                pls.append(prop)
        for p in pls:
            if not p.value_list and not p.value_range:
                continue
            if p.name in self._subs:
                self._subs[p.name].update()
            elif add_fans:
                opt = None
                if p.name in ['heat_level']:
                    opt = {
                        'power_property': p.service.bool_property('heating'),
                    }
                self._subs[p.name] = MiotModesSubEntity(self, p, opt)
                add_fans([self._subs[p.name]])

        add_switches = self._add_entities.get('switch')
        if self._prop_power:
            pnm = self._prop_power.full_name
            if pnm in self._subs:
                self._subs[pnm].update()
            elif add_switches:
                self._subs[pnm] = SwitchSubEntity(self, pnm)
                add_switches([self._subs[pnm]])

    @property
    def icon(self):
        return 'mdi:toilet'


class MiotBinarySensorSubEntity(ToggleSubEntity, BinarySensorEntity):
    def __init__(self, parent, miot_property: MiotProperty, option=None):
        super().__init__(parent, miot_property.full_name, option)
        self._name = self.format_name_by_property(miot_property)
        self._miot_service = miot_property.service
        self._miot_property = miot_property
