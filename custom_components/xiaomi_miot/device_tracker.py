"""Support for Xiaomi device tracker."""
import logging
import time
from datetime import timedelta

from homeassistant.components.device_tracker import (
    DOMAIN as ENTITY_DOMAIN,
)
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity, ScannerEntity

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
from .core.coord_transform import gcj02_to_wgs84, bd09_to_wgs84

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'
SCAN_INTERVAL = timedelta(seconds=60)

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
        for srv in spec.get_services('watch', 'rearview_mirror', 'head_up_display'):
            if 'xiaoxun.watch.' in model:
                entities.append(XiaoxunWatchTrackerEntity(config, srv))
            elif srv.get_property('latitude', 'longitude'):
                entities.append(MiotTrackerEntity(config, srv))
    if not entities and ('xiaoxun.watch.' in model or 'xiaoxun.tracker.' in model):
        # xiaoxun.watch.sw763
        # xiaoxun.tracker.v1
        entities.append(XiaoxunWatchTrackerEntity(config))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotTrackerEntity(MiotEntity, TrackerEntity):
    _attr_latitude = None
    _attr_longitude = None
    _attr_location_name = None
    _attr_location_accuracy = 0
    _disable_location_name = False

    def __init__(self, config, miot_service: MiotService = None):
        super().__init__(miot_service, config=config, logger=_LOGGER)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._disable_location_name = self.custom_config_bool('disable_location_name')

    async def async_update(self):
        await super().async_update()
        if not self._available or not self._miot_service:
            return

        if prop := self._miot_service.get_property('latitude'):
            self._attr_latitude = prop.from_dict(self._state_attrs)
        if prop := self._miot_service.get_property('longitude'):
            self._attr_longitude = prop.from_dict(self._state_attrs)
        if prop := self._miot_service.get_property('current_address'):
            self._attr_location_name = prop.from_dict(self._state_attrs)
        await self.transform_coord()

        for p in self._miot_service.get_properties('driving_status'):
            self._update_sub_entities(p, None, 'binary_sensor')

    async def transform_coord(self, default=None):
        if not (self._attr_latitude or self._attr_longitude):
            return
        typ = self.custom_config('coord_type') or default
        if not typ:
            return
        typ = f'{typ}'.lower()
        if typ == 'gcj02':
            self._attr_longitude, self._attr_latitude = gcj02_to_wgs84(self._attr_longitude, self._attr_latitude)
        if typ == 'bd09':
            self._attr_longitude, self._attr_latitude = bd09_to_wgs84(self._attr_longitude, self._attr_latitude)

    @property
    def should_poll(self):
        """No polling for entities that have location pushed."""
        return True

    @property
    def source_type(self):
        """Return the source type, eg gps or router, of the device."""
        return SourceType.GPS

    @property
    def latitude(self):
        """Return latitude value of the device."""
        return self._attr_latitude

    @property
    def longitude(self):
        """Return longitude value of the device."""
        return self._attr_longitude

    @property
    def location_name(self):
        """Return a location name for the current location of the device."""
        if self._disable_location_name:
            return None
        return self._attr_location_name

    @property
    def location_accuracy(self):
        """Return the location accuracy of the device.
        Value in meters.
        """
        return self._attr_location_accuracy

    @property
    def battery_level(self):
        """Return the battery level of the device."""
        if not self._miot_service:
            return None
        sls = [self._miot_service, *self._miot_service.spec.get_services('battery')]
        for srv in sls:
            prop = srv.get_property('battery_level')
            if prop:
                return prop.from_dict(self._state_attrs)
        return None


class XiaoxunWatchTrackerEntity(MiotTrackerEntity):
    def __init__(self, config, miot_service: MiotService = None, miot_spec: MiotSpec = None):
        self._miot_spec = miot_spec
        super().__init__(config=config, miot_service=miot_service)

    @property
    def device_eid(self):
        did = f'{self.miot_did}'
        return did.replace('xiaoxun.', '')

    async def async_update(self):
        await super().async_update()
        await self.update_location()

    async def update_location(self):
        did = f'{self.miot_did}'
        mic = self.xiaomi_cloud
        if not did or not mic:
            return
        pms = {
            'app_id': '10025',
            'dids': [did],
            'params': {
                'CID': 50031,
                'model': self._model,
                'SN': int(time.time() / 1000),
                'PL': {
                    'Size': 1,
                    'Key': '78999898989898998',
                    'EID': self.device_eid,
                },
            },
        }
        rdt = await mic.async_request_api('third/api', pms) or {}
        loc = {}
        for v in (rdt.get('result') or {}).get('PL', {}).get('List', {}).values():
            if loc := v.get('result') or {}:
                loc.setdefault('device', v)
                loc.setdefault('timestamp', v.get('timestamp', ''))
                break
        if not loc:
            self.logger.warning('%s: Got xiaoxun watch location faild: %s', self.name_model, rdt)
            return
        self.logger.debug('%s: Got xiaoxun watch location: %s', self.name_model, rdt)
        dvc = loc.get('device') or {}
        gps = f"{loc.get('location', '')},".split(',')
        self._attr_latitude = float(gps[1])
        self._attr_longitude = float(gps[0])
        self._attr_location_name = loc.get('desc')
        self._attr_location_accuracy = int(loc.get('radius') or 0)
        await self.transform_coord(default='gcj02')
        self.update_attrs({
            'sos': dvc.get('SOS', 0),
            'steps': dvc.get('steps', 0),
            'home_wifi': dvc.get('home_wifi', 0),
            'imei': dvc.get('imei'),
            'adcode': loc.get('adcode'),
            'country': loc.get('country'),
            'province': loc.get('province'),
            'city': loc.get('province'),
            'district': loc.get('district'),
            'township': loc.get('township'),
            'road': loc.get('road'),
            'street': loc.get('street'),
        })
        if tim := loc.get('timestamp', ''):
            self.update_attrs({
                'timestamp': f'{tim[0:4]}-{tim[4:6]}-{tim[6:8]} {tim[8:10]}:{tim[10:12]}:{tim[12:14]}',
            })


class MiotScannerSubEntity(MiotPropertySubEntity, ScannerEntity):

    def __init__(self, parent, miot_property: MiotProperty, option=None):
        super().__init__(parent, miot_property, option, domain=ENTITY_DOMAIN)

    @property
    def source_type(self):
        """Return the source type, eg gps or router, of the device."""
        return SourceType.ROUTER

    @property
    def is_connected(self):
        """Return true if the device is connected to the network."""
        return self._attr_state in [True, 1]
