"""Support for Xiaomi Miot."""
import logging
import asyncio
import socket
from datetime import timedelta
from functools import partial
import voluptuous as vol

from homeassistant import (
    core as hass_core,
    config_entries,
)
from homeassistant.const import *
from homeassistant.config import DATA_CUSTOMIZE
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity import (
    Entity,
    ToggleEntity,
)
from homeassistant.helpers.entity_component import EntityComponent
import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.config_validation as cv

from miio import (
    Device as MiioDevice,  # noqa: F401
    DeviceException,
)
from miio.device import DeviceInfo as MiioInfo
from miio.miot_device import MiotDevice as MiotDeviceBase

from .core.miot_spec import (
    MiotSpec,
    MiotService,
)
from .core.xiaomi_cloud import (
    MiotCloud,
    MiCloudException,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'xiaomi_miot'
SCAN_INTERVAL = timedelta(seconds=60)
DEFAULT_NAME = 'Xiaomi Miot'
CONF_MODEL = 'model'

SUPPORTED_DOMAINS = [
    "sensor",
    "switch",
    "light",
    "fan",
    "climate",
    "cover",
    "humidifier",
    "media_player",
    "camera",
]

XIAOMI_CONFIG_SCHEMA = cv.PLATFORM_SCHEMA_BASE.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_TOKEN): vol.All(cv.string, vol.Length(min=32, max=32)),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_MODEL, default=''): cv.string,
        vol.Optional(CONF_MODE, default=[]): cv.ensure_list,
    }
)

XIAOMI_MIIO_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
    },
)

SERVICE_TO_METHOD_BASE = {
    'send_command': {
        'method': 'async_command',
        'schema': XIAOMI_MIIO_SERVICE_SCHEMA.extend(
            {
                vol.Required('method'): cv.string,
                vol.Optional('params', default=[]): cv.ensure_list,
            },
        ),
    },
    'set_property': {
        'method': 'async_set_property',
        'schema': XIAOMI_MIIO_SERVICE_SCHEMA.extend(
            {
                vol.Required('field'): cv.string,
                vol.Required('value'): cv.match_all,
            },
        ),
    },
    'set_miot_property': {
        'method': 'async_set_miot_property',
        'schema': XIAOMI_MIIO_SERVICE_SCHEMA.extend(
            {
                vol.Optional('did'): cv.string,
                vol.Required('siid'): int,
                vol.Required('piid'): int,
                vol.Required('value'): cv.match_all,
            },
        ),
    },
    'get_properties': {
        'method': 'async_get_properties',
        'schema': XIAOMI_MIIO_SERVICE_SCHEMA.extend(
            {
                vol.Required('mapping'): dict,
            },
        ),
    },
    'call_action': {
        'method': 'async_miot_action',
        'schema': XIAOMI_MIIO_SERVICE_SCHEMA.extend(
            {
                vol.Optional('did'): cv.string,
                vol.Required('siid'): int,
                vol.Required('aiid'): int,
                vol.Optional('params', default=[]): cv.ensure_list,
            },
        ),
    },
}

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_USERNAME): cv.string,
                vol.Optional(CONF_PASSWORD): cv.string,
                vol.Optional('server_country'): cv.string,
            },
            extra=vol.ALLOW_EXTRA,
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass, hass_config: dict):
    hass.data.setdefault(DOMAIN, {})
    config = hass_config.get(DOMAIN) or {}
    hass.data[DOMAIN]['config'] = config
    hass.data[DOMAIN].setdefault('entities', {})
    hass.data[DOMAIN].setdefault('configs', {})
    component = EntityComponent(_LOGGER, DOMAIN, hass, SCAN_INTERVAL)
    hass.data[DOMAIN]['component'] = component
    await component.async_setup(config)
    bind_services_to_entries(hass, SERVICE_TO_METHOD_BASE)

    if config.get('username') and config.get('password'):
        try:
            mic = MiotCloud(
                hass,
                config.get('username'),
                config.get('password'),
                config.get('server_country'),
            )
            await mic.async_login()
            hass.data[DOMAIN]['xiaomi_cloud'] = mic
            hass.data[DOMAIN]['devices_by_mac'] = await mic.async_get_devices_by_key('mac') or {}
            _LOGGER.debug('Setup xiaomi cloud for user: %s', config.get('username'))
        except MiCloudException as exc:
            _LOGGER.info('Setup xiaomi cloud for user: %s failed:', config.get('username'), exc)

    return True


async def async_setup_entry(hass: hass_core.HomeAssistant, config_entry: config_entries.ConfigEntry):
    entry_id = config_entry.entry_id
    unique_id = config_entry.unique_id
    info = config_entry.data.get('miio_info') or {}
    config = {}
    for k in [CONF_HOST, CONF_TOKEN, CONF_NAME, CONF_MODEL, CONF_MODE]:
        config[k] = config_entry.data.get(k)
    model = str(config.get(CONF_MODEL) or info.get(CONF_MODEL) or '')
    config[CONF_MODEL] = model
    modes = config.get(CONF_MODE, [])
    if not isinstance(modes, list):
        modes = str(modes).split(',')
    modes = [
        m
        for m in modes
        if m in SUPPORTED_DOMAINS
    ]
    config[CONF_MODE] = modes
    if 'miot_type' in config_entry.data:
        config['miot_type'] = config_entry.data.get('miot_type')
    else:
        config['miot_type'] = await MiotSpec.async_get_model_type(hass, model)
    config['miio_info'] = info
    config['config_entry'] = config_entry
    hass.data[DOMAIN]['configs'][entry_id] = config
    hass.data[DOMAIN]['configs'][unique_id] = config
    _LOGGER.debug('Xiaomi Miot async_setup_entry %s', {
        'entry_id': entry_id,
        'unique_id': unique_id,
        'config': config,
        'miio': info,
    })
    for d in SUPPORTED_DOMAINS:
        hass.async_create_task(hass.config_entries.async_forward_entry_setup(config_entry, d))
    return True


def bind_services_to_entries(hass, services):
    async def async_service_handler(service):
        method = services.get(service.service)
        fun = method['method']
        params = {
            key: value
            for key, value in service.data.items()
            if key != ATTR_ENTITY_ID
        }
        target_devices = []
        entity_ids = service.data.get(ATTR_ENTITY_ID)
        if entity_ids:
            target_devices = [
                dvc
                for dvc in hass.data[DOMAIN]['entities'].values()
                if dvc.entity_id in entity_ids
            ]
        _LOGGER.debug('Xiaomi Miot async_service_handler %s', {
            'targets': [dvc.entity_id for dvc in target_devices],
            'method': fun,
            'params': params,
        })
        update_tasks = []
        for dvc in target_devices:
            if not hasattr(dvc, fun):
                _LOGGER.info('%s have no method: %s', dvc.entity_id, fun)
                continue
            await getattr(dvc, fun)(**params)
            update_tasks.append(dvc.async_update_ha_state(True))
        if update_tasks:
            await asyncio.wait(update_tasks)

    for srv, obj in services.items():
        schema = obj.get('schema', XIAOMI_MIIO_SERVICE_SCHEMA)
        hass.services.async_register(DOMAIN, srv, async_service_handler, schema=schema)


class MiotDevice(MiotDeviceBase):
    def get_properties_for_mapping(self) -> list:
        properties = [{'did': k, **v} for k, v in self.mapping.items()]
        return self.get_properties(
            properties, property_getter='get_properties', max_properties=12
        )


class MiioEntity(Entity):
    def __init__(self, name, device, miio_info=None):
        self._device = device
        try:
            if miio_info and isinstance(miio_info, dict):
                miio_info = MiioInfo(miio_info)
            self._miio_info = miio_info if isinstance(miio_info, MiioInfo) else device.info()
        except DeviceException as exc:
            _LOGGER.error("Device %s unavailable or token incorrect: %s", name, exc)
            raise PlatformNotReady from exc
        except socket.gaierror as exc:
            _LOGGER.error("Device %s unavailable: %s", name, exc)
            raise PlatformNotReady from exc
        self._unique_did = dr.format_mac(self._miio_info.mac_address)
        self._unique_id = self._unique_did
        self._name = name
        self._model = self._miio_info.model or ''
        self._state = None
        self._available = False
        self._state_attrs = {
            CONF_MODEL: self._model,
            'lan_ip': self._miio_info.network_interface.get('localIp'),
            'mac_address': self._miio_info.mac_address,
            'firmware_version': self._miio_info.firmware_version,
            'hardware_version': self._miio_info.hardware_version,
            'entity_class': self.__class__.__name__,
        }
        self._supported_features = 0
        self._props = ['power']
        self._success_result = ['ok']

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def name(self):
        return self._name

    @property
    def available(self):
        return self._available

    @property
    def is_on(self):
        return self._state

    @property
    def device_state_attributes(self):
        ext = self.state_attributes or {}
        return {**self._state_attrs, **ext}

    @property
    def supported_features(self):
        return self._supported_features

    @property
    def device_info(self):
        return {
            'identifiers': {(DOMAIN, self._unique_did)},
            'name': self._name,
            'model': self._model,
            'manufacturer': (self._model or 'Xiaomi').split('.', 1)[0],
            'sw_version': self._miio_info.firmware_version,
        }

    async def _try_command(self, mask_error, func, *args, **kwargs):
        try:
            result = await self.hass.async_add_executor_job(partial(func, *args, **kwargs))
            _LOGGER.debug('Response received from miio %s: %s', self.name, result)
            return result == self._success_result
        except DeviceException as exc:
            if self._available:
                _LOGGER.error(mask_error, exc)
                self._available = False
            return False

    def send_command(self, method, params=None):
        _LOGGER.debug('Send miio command to %s: %s(%s)', self.name, method, params)
        try:
            result = self._device.send(method, params if params is not None else [])
        except DeviceException as ex:
            _LOGGER.error('Send miio command to %s: %s(%s) failed: %s', self.name, method, params, ex)
            return False
        ret = result == self._success_result
        if not ret:
            _LOGGER.info('Send miio command to %s failed: %s(%s), result: %s', self.name, method, params, result)
        return ret

    async def async_command(self, method, params=None):
        return await self.hass.async_add_executor_job(partial(self.send_command, method, params))

    async def async_update(self):
        try:
            attrs = await self.hass.async_add_executor_job(partial(self._device.get_properties, self._props))
        except DeviceException as ex:
            if self._available:
                self._available = False
            _LOGGER.error('Got exception while fetching the state for %s (%s): %s', self.name, self._props, ex)
            return
        attrs = dict(zip(self._props, attrs))
        _LOGGER.debug('Got new state from %s: %s', self.name, attrs)
        self._available = True
        self._state = attrs.get('power') == 'on'
        self.update_attrs(attrs)

    def turn_on(self, **kwargs):
        ret = self._device.on()
        if ret:
            self._state = True
            self.update_attrs({'power': 'on'})
        return ret

    def turn_off(self, **kwargs):
        ret = self._device.off()
        if ret:
            self._state = False
            self.update_attrs({'power': 'off'})
        return ret

    def update_attrs(self, attrs: dict, update_parent=False):
        self._state_attrs.update(attrs or {})
        if update_parent and hasattr(self, '_parent'):
            if self._parent and hasattr(self._parent, 'update_attrs'):
                getattr(self._parent, 'update_attrs')(attrs or {}, update_parent=False)
        return self._state_attrs

    def global_config(self, key=None):
        if not self.hass:
            return None
        cfg = self.hass.data[DOMAIN]['config'] or {}
        return cfg if key is None else cfg.get(key)

    def custom_config(self, key=None):
        if not self.hass:
            return None
        if not self.entity_id:
            return None
        cfg = self.hass.data[DATA_CUSTOMIZE].get(self.entity_id)
        return cfg if key is None else cfg.get(key)


class MiotEntity(MiioEntity):
    def __init__(self, name, device, miot_service=None, miio_info=None):
        super().__init__(name, device, miio_info)
        self._success_code = 0

        self._miot_service = miot_service
        if isinstance(miot_service, MiotService):
            self._unique_id = f'{self._unique_id}-{miot_service.iid}'

    @property
    def miot_did(self):
        did = self.custom_config('miot_did')
        if self.entity_id and not did:
            mac = self._miio_info.mac_address
            dvs = self.hass.data[DOMAIN].get('devices_by_mac') or {}
            if mac in dvs:
                return dvs[mac].get('did')
        return did

    @property
    def miot_cloud(self):
        if self.hass and self.miot_did and self.custom_config('miot_cloud'):
            return self.hass.data[DOMAIN].get('xiaomi_cloud')
        return None

    @property
    def miot_mapping(self):
        return self._device.mapping

    async def _try_command(self, mask_error, func, *args, **kwargs):
        result = None
        try:
            results = await self.hass.async_add_executor_job(partial(func, *args, **kwargs)) or []
            for result in results:
                break
            _LOGGER.debug('Response received from miot %s: %s', self.name, result)
            if isinstance(result, dict):
                return dict(result or {}).get('code', 1) == self._success_code
            else:
                return result == self._success_result
        except DeviceException as exc:
            if self._available:
                _LOGGER.error(mask_error, exc)
                self._available = False
            return False

    async def async_update(self):
        updater = 'lan'
        try:
            if self.miot_cloud:
                results = await self.hass.async_add_executor_job(
                    partial(self.miot_cloud.get_properties_for_mapping, self.miot_did, self.miot_mapping)
                )
                updater = 'cloud'
            else:
                results = await self.hass.async_add_executor_job(
                    partial(self._device.get_properties_for_mapping)
                )
        except DeviceException as exc:
            if self._available:
                self._available = False
            _LOGGER.error('Got exception while fetching the state for %s: %s', self.name, exc)
            return
        except MiCloudException as exc:
            if self._available:
                self._available = False
            _LOGGER.error('Got exception while fetching the state from cloud for %s: %s', self.name, exc)
            return
        attrs = {
            prop.get('did'): prop.get('value') if prop.get('code') == 0 else None
            for prop in results
            if isinstance(prop, dict) and 'did' in prop
        }
        _LOGGER.debug('Got new state from %s: %s, updater: %s', self.name, attrs, updater)
        self._available = True
        self._state = True if attrs.get('power') else False
        self.update_attrs(attrs)

    def get_properties(self, mapping: dict):
        if not self._miio_info:
            return
        dvc = MiotDevice(
            mapping,
            self._miio_info.network_interface.get('localIp'),
            self._miio_info.data.get('token'),
        )
        try:
            results = dvc.get_properties_for_mapping()
        except DeviceException as exc:
            _LOGGER.error('Got exception while get properties from %s: %s, mapping: %s', self.name, exc, mapping)
            return
        attrs = {
            prop['did']: prop['value'] if prop['code'] == 0 else None
            for prop in results
        }
        _LOGGER.info('Get miot properties from %s: %s', self.name, results)
        return attrs

    async def async_get_properties(self, mapping):
        return await self.hass.async_add_executor_job(partial(self.get_properties, mapping))

    def set_property(self, field, value):
        try:
            ext = self.miot_mapping.get(field) or {}
            if ext:
                result = self.set_miot_property(ext['siid'], ext['piid'], value)
            else:
                _LOGGER.warning('Set miot property to %s: %s(%s) failed: property not found', self.name, field, value)
                return False
        except DeviceException as exc:
            _LOGGER.error('Set miot property to %s: %s(%s) failed: %s', self.name, field, value, exc)
            return False
        except MiCloudException as exc:
            _LOGGER.error('Set miot property to cloud for %s: %s(%s) failed: %s', self.name, field, value, exc)
            return False
        ret = dict(result or {}).get('code', 1) == self._success_code
        if ret:
            if field in self._state_attrs:
                self.update_attrs({
                    field: value,
                }, update_parent=False)
            _LOGGER.debug('Set miot property to %s: %s(%s), result: %s', self.name, field, value, result)
        else:
            _LOGGER.info('Set miot property to %s failed: %s(%s), result: %s', self.name, field, value, result)
        return ret

    async def async_set_property(self, field, value):
        return await self.hass.async_add_executor_job(partial(self.set_property, field, value))

    def set_miot_property(self, siid, piid, value, did=None):
        ret = None
        pms = {
            'did':  did or self.miot_did or f'property-{siid}-{piid}',
            'siid': siid,
            'piid': piid,
            'value': value,
        }
        try:
            exc = None
            if self.miot_cloud:
                results = self.miot_cloud.set_props([pms])
            else:
                results = self._device.send('set_properties', [pms])
            for ret in (results or []):
                break
        except DeviceException as exc:
            pass
        except MiCloudException as exc:
            pass
        if ret:
            _LOGGER.debug('Set miot property to %s (%s), result: %s', self.name, pms, ret)
        else:
            _LOGGER.warning('Set miot property to %s (%s) failed: %s', self.name, pms, exc)
        return ret

    async def async_set_miot_property(self, siid, piid, value, did=None):
        return await self.hass.async_add_executor_job(partial(self.set_miot_property, siid, piid, value, did))

    def miot_action(self, siid, aiid, params=None, did=None):
        ret = None
        pms = {
            'did':  did or self.miot_did or f'action-{siid}-{aiid}',
            'siid': siid,
            'aiid': aiid,
            'in':   params or [],
        }
        try:
            exc = None
            if self.miot_cloud:
                ret = self.miot_cloud.do_action(pms)
            else:
                ret = self._device.send('action', pms)
        except DeviceException as exc:
            pass
        except MiCloudException as exc:
            pass
        if ret:
            _LOGGER.debug('Call miot action to %s (%s), result: %s', self.name, pms, ret)
        else:
            _LOGGER.warning('Call miot action to %s (%s) failed: %s', self.name, pms, exc)
        return ret

    async def async_miot_action(self, siid, aiid, params=None, did=None):
        return await self.hass.async_add_executor_job(partial(self.miot_action, siid, aiid, params, did))

    def turn_on(self, **kwargs):
        ret = self.set_property('power', True)
        if ret:
            self._state = True
        return ret

    def turn_off(self, **kwargs):
        ret = self.set_property('power', False)
        if ret:
            self._state = False
        return ret


class MiotToggleEntity(MiotEntity, ToggleEntity):
    def __init__(self, name, device, miot_service: MiotService, miio_info=None):
        super().__init__(name, device, miio_info)
        self._miot_service = miot_service
        self._prop_power = miot_service.get_property('on', 'power', 'switch')

    @property
    def is_on(self):
        if self._prop_power:
            return self._state_attrs.get(self._prop_power.full_name) and True
        return None

    def turn_on(self, **kwargs):
        if self._prop_power:
            return self.set_property(self._prop_power.full_name, True)
        return False

    def turn_off(self, **kwargs):
        if self._prop_power:
            return self.set_property(self._prop_power.full_name, False)
        return False


class BaseSubEntity(Entity):
    def __init__(self, parent, attr, option=None):
        self._unique_id = f'{parent.unique_id}-{attr}'
        self._name = f'{parent.name} {attr}'
        self._state = STATE_UNKNOWN
        self._available = False
        self._parent = parent
        self._attr = attr
        self._option = dict(option or {})
        if self._option.get('unique_id'):
            self._unique_id = self._option.get('unique_id')
        if self._option.get('name'):
            self._name = self._option.get('name')
        self._supported_features = int(self._option.get('supported_features', 0))
        self._state_attrs = {}

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def available(self):
        return self._available

    @property
    def supported_features(self):
        return self._supported_features

    @property
    def device_state_attributes(self):
        return self._state_attrs

    @property
    def device_class(self):
        return self._option.get('device_class', self._option.get('class'))

    @property
    def device_info(self):
        return self._parent.device_info

    @property
    def icon(self):
        return self._option.get('icon')

    @property
    def unit_of_measurement(self):
        return self._option.get('unit')

    def update(self):
        attrs = self._parent.device_state_attributes or {}
        if self._attr in attrs:
            self._available = True
            self._state = attrs.get(self._attr)
            keys = self._option.get('keys', [])
            if isinstance(keys, list):
                keys.append(self._attr)
            self._state_attrs = {}.update(attrs) if keys is True else {
                k: v
                for k, v in attrs.items()
                if k in keys
            }

    def update_attrs(self, attrs: dict, update_parent=True):
        self._state_attrs.update(attrs or {})
        if update_parent:
            if self._parent and hasattr(self._parent, 'update_attrs'):
                getattr(self._parent, 'update_attrs')(attrs or {}, update_parent=False)
        return self._state_attrs

    def call_parent(self, method, *args, **kwargs):
        ret = None
        for f in cv.ensure_list(method):
            if hasattr(self._parent, f):
                ret = getattr(self._parent, f)(*args, **kwargs)
                break
        if ret:
            self.update()
        return ret


class ToggleSubEntity(BaseSubEntity, ToggleEntity):
    def __init__(self, parent, attr='power', option=None):
        super().__init__(parent, attr, option)

    def update(self):
        super().update()
        if self._available:
            attrs = self._state_attrs
            self._state = attrs.get(self._attr) == STATE_ON

    @property
    def state(self):
        return STATE_ON if self._state else STATE_OFF

    @property
    def is_on(self):
        return self._state

    def turn_on(self, **kwargs):
        self.call_parent('turn_on', **kwargs)

    def turn_off(self, **kwargs):
        self.call_parent('turn_off', **kwargs)
