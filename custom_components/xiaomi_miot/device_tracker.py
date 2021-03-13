"""Support for Xiaomi device tracker."""
import logging
from datetime import timedelta

from homeassistant.const import *  # noqa: F401
from homeassistant.components.device_tracker import (
    DOMAIN as ENTITY_DOMAIN,
)
from homeassistant.components.device_tracker.config_entry import TrackerEntity

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
)
from .binary_sensor import MiotBinarySensorSubEntity

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'
SCAN_INTERVAL = timedelta(seconds=60)

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    await async_setup_config_entry(hass, config_entry, async_setup_platform, async_add_entities, ENTITY_DOMAIN)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data.setdefault(DATA_KEY, {})
    hass.data[DOMAIN]['add_entities'][ENTITY_DOMAIN] = async_add_entities
    model = str(config.get(CONF_MODEL) or '')
    if model.find('mirror') >= 0:
        _LOGGER.debug('Setup device_tracker: %s', config)
    entities = []
    miot = config.get('miot_type')
    if miot:
        spec = await MiotSpec.async_from_type(hass, miot)
        for srv in spec.get_services('rearview_mirror'):
            if not srv.get_property('latitude', 'longitude'):
                continue
            cfg = {
                **config,
                'name': f"{config.get('name')} {srv.description}"
            }
            entities.append(MiotTrackerEntity(cfg, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotTrackerEntity(MiotEntity, TrackerEntity):
    def __init__(self, config, miot_service: MiotService):
        super().__init__(miot_service, config=config)
        self._state_attrs.update({'entity_class': self.__class__.__name__})

    async def async_update(self):
        await super().async_update()
        if not self._available:
            return
        add_binary_sensors = self._add_entities.get('binary_sensor')
        for p in self._miot_service.get_properties('driving_status'):
            if p.full_name in self._subs:
                self._subs[p.full_name].update()
            elif add_binary_sensors and p.format == 'bool':
                self._subs[p.full_name] = MiotBinarySensorSubEntity(self, p)
                add_binary_sensors([self._subs[p.full_name]])

    @property
    def should_poll(self):
        """No polling for entities that have location pushed."""
        return True

    @property
    def source_type(self):
        """Return the source type, eg gps or router, of the device."""
        return 'gps'

    @property
    def latitude(self):
        """Return latitude value of the device."""
        prop = self._miot_service.get_property('latitude')
        if prop:
            return prop.from_dict(self._state_attrs)
        return NotImplementedError

    @property
    def longitude(self):
        """Return longitude value of the device."""
        prop = self._miot_service.get_property('longitude')
        if prop:
            return prop.from_dict(self._state_attrs)
        return NotImplementedError

    @property
    def location_name(self):
        """Return a location name for the current location of the device."""
        prop = self._miot_service.get_property('current_address')
        if prop:
            return prop.from_dict(self._state_attrs)
        return None

    @property
    def location_accuracy(self):
        """Return the location accuracy of the device.
        Value in meters.
        """
        return 0

    @property
    def battery_level(self):
        """Return the battery level of the device."""
        sls = [self._miot_service, *self._miot_service.spec.get_services('battery')]
        for srv in sls:
            prop = srv.get_property('battery_level')
            if prop:
                return prop.from_dict(self._state_attrs)
        return None
