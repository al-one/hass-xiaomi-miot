"""Support for Xiaomi Miot."""
import logging
import asyncio
import socket
import re
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
from homeassistant.components import persistent_notification
from homeassistant.helpers.entity_component import EntityComponent
import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.config_validation as cv

from miio import (
    Device as MiioDevice,  # noqa: F401
    DeviceException,
)
from miio.device import DeviceInfo as MiioInfoBase
from miio.miot_device import MiotDevice as MiotDeviceBase

from .core.miot_spec import (
    MiotSpec,
    MiotService,
    MiotProperty,
    MiotAction,
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
CONF_SERVER_COUNTRY = 'server_country'
CONF_CONFIG_VERSION = 'config_version'

SUPPORTED_DOMAINS = [
    'sensor',
    'binary_sensor',
    'switch',
    'light',
    'fan',
    'climate',
    'cover',
    'humidifier',
    'media_player',
    'camera',
    'vacuum',
    'air_quality',
    'water_heater',
    'device_tracker',
    'number',
]

XIAOMI_CONFIG_SCHEMA = cv.PLATFORM_SCHEMA_BASE.extend(
    {
        vol.Optional(CONF_HOST): cv.string,
        vol.Optional(CONF_TOKEN): vol.All(cv.string, vol.Length(min=32, max=32)),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_MODEL, default=''): cv.string,
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
                vol.Optional('throw', default=False): cv.boolean,
            },
        ),
    },
    'call_action': {
        'method': 'async_miot_action',
        'schema': XIAOMI_MIIO_SERVICE_SCHEMA.extend(
            {
                vol.Required('siid'): int,
                vol.Required('aiid'): int,
                vol.Optional('did'): cv.string,
                vol.Optional('params', default=[]): cv.ensure_list,
                vol.Optional('throw', default=False): cv.boolean,
            },
        ),
    },
    'get_device_data': {
        'method': 'async_get_device_data',
        'schema': XIAOMI_MIIO_SERVICE_SCHEMA.extend(
            {
                vol.Optional('type', default='prop'): cv.string,
                vol.Required('key'): cv.string,
                vol.Optional('did'): cv.string,
                vol.Optional('time_start'): int,
                vol.Optional('time_end'): int,
                vol.Optional('limit'): int,
                vol.Optional('group'): cv.string,
                vol.Optional('throw', default=False): cv.boolean,
            },
        ),
    },
    'get_token': {
        'method': 'async_get_token',
        'schema': XIAOMI_MIIO_SERVICE_SCHEMA.extend(
            {
                vol.Optional('name', default=''): cv.string,
                vol.Optional('throw', default=False): cv.boolean,
            },
        ),
    },
    'get_bindkey': {
        'method': 'async_get_bindkey',
        'schema': XIAOMI_MIIO_SERVICE_SCHEMA.extend(
            {
                vol.Optional('did', default=''): cv.string,
                vol.Optional('throw', default=False): cv.boolean,
            },
        ),
    },
    'request_xiaomi_api': {
        'method': 'async_request_xiaomi_api',
        'schema': XIAOMI_MIIO_SERVICE_SCHEMA.extend(
            {
                vol.Required('api'): cv.string,
                vol.Optional('params', default={}): dict,
                vol.Optional('throw', default=False): cv.boolean,
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
    hass.data[DOMAIN].setdefault('configs', {})
    hass.data[DOMAIN].setdefault('entities', {})
    hass.data[DOMAIN].setdefault('add_entities', {})
    hass.data[DOMAIN].setdefault('sub_entities', {})
    component = EntityComponent(_LOGGER, DOMAIN, hass, SCAN_INTERVAL)
    hass.data[DOMAIN]['component'] = component
    await component.async_setup(config)
    bind_services_to_entries(hass, SERVICE_TO_METHOD_BASE)

    if config.get('username') and config.get('password'):
        try:
            mic = MiotCloud(
                hass,
                config.get(CONF_USERNAME),
                config.get(CONF_PASSWORD),
                config.get('server_country'),
            )
            if not await mic.async_login():
                raise MiCloudException('Login failed')
            hass.data[DOMAIN]['xiaomi_cloud'] = mic
            hass.data[DOMAIN]['devices_by_mac'] = await mic.async_get_devices_by_key('mac') or {}
            cnt = len(hass.data[DOMAIN]['devices_by_mac'])
            _LOGGER.debug('Setup xiaomi cloud for user: %s, %s devices', config.get(CONF_USERNAME), cnt)
        except MiCloudException as exc:
            _LOGGER.warning('Setup xiaomi cloud for user: %s failed: %s', config.get(CONF_USERNAME), exc)

    return True


async def async_setup_entry(hass: hass_core.HomeAssistant, config_entry: config_entries.ConfigEntry):
    hass.data.setdefault(DOMAIN, {})
    entry_id = config_entry.entry_id
    unique_id = config_entry.unique_id

    if config_entry.data.get(CONF_USERNAME):
        await async_setup_xiaomi_cloud(hass, config_entry)
    else:
        info = config_entry.data.get('miio_info') or {}
        config = dict(config_entry.data)
        config.update(config_entry.options or {})
        model = str(config.get(CONF_MODEL) or info.get(CONF_MODEL) or '')
        config[CONF_MODEL] = model

        if 'miot_type' not in config:
            config['miot_type'] = await MiotSpec.async_get_model_type(hass, model)
        config['miio_info'] = info
        config['config_entry'] = config_entry
        hass.data[DOMAIN][entry_id] = config
        _LOGGER.debug('Xiaomi Miot setup config entry: %s', {
            'entry_id': entry_id,
            'unique_id': unique_id,
            'config': config,
        })

    if not config_entry.update_listeners:
        config_entry.add_update_listener(async_update_options)

    for sd in SUPPORTED_DOMAINS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(config_entry, sd)
        )
    return True


async def async_setup_xiaomi_cloud(hass: hass_core.HomeAssistant, config_entry: config_entries.ConfigEntry):
    entry_id = config_entry.entry_id
    entry = {**config_entry.data, **config_entry.options}
    config = {
        'entry_id': entry_id,
        'config_entry': config_entry,
        'configs': [],
    }
    try:
        mic = await MiotCloud.from_token(hass, entry)
        await mic.async_check_auth(notify=True)
        config['xiaomi_cloud'] = mic
        config['devices_by_mac'] = await mic.async_get_devices_by_key('mac', filters=entry) or {}
    except MiCloudException as exc:
        _LOGGER.error('Setup xiaomi cloud for user: %s failed: %s', entry.get(CONF_USERNAME), exc)
        return False
    if not config.get('devices_by_mac'):
        _LOGGER.warning('None device in xiaomi cloud: %s', entry.get(CONF_USERNAME))
    else:
        cnt = len(config['devices_by_mac'])
        _LOGGER.debug('Setup xiaomi cloud for user: %s, %s devices', entry.get(CONF_USERNAME), cnt)
    for mac, d in config['devices_by_mac'].items():
        model = d.get(CONF_MODEL)
        if not model:
            continue
        urn = await MiotSpec.async_get_model_type(hass, model)
        if not urn:
            _LOGGER.info('Xiaomi device: %s has no urn', [d.get('name'), model])
            continue
        mif = {
            'ap':     {'ssid': d.get('ssid'), 'bssid': d.get('bssid'), 'rssi': d.get('rssi')},
            'netif':  {'localIp': d.get('localip'), 'gw': '', 'mask': ''},
            'fw_ver': d.get('extra', {}).get('fw_version', ''),
            'hw_ver': d.get('extra', {}).get('hw_version', ''),
            'mac':    d.get('mac'),
            'model':  model,
            'token':  d.get(CONF_TOKEN),
        }
        cfg = {
            CONF_NAME: d.get(CONF_NAME) or DEFAULT_NAME,
            CONF_HOST: d.get('localip') or '',
            CONF_TOKEN: d.get('token') or '',
            CONF_MODEL: model,
            'miot_did': d.get('did') or '',
            'miot_type': urn,
            'miio_info': mif,
            'miot_cloud': True,
            'entry_id': entry_id,
            CONF_CONFIG_VERSION: entry.get(CONF_CONFIG_VERSION) or 0,
        }
        config['configs'].append(cfg)
        _LOGGER.debug('Xiaomi cloud device: %s', {**cfg, CONF_TOKEN: '****'})
    hass.data[DOMAIN][entry_id] = config
    return True


async def async_update_options(hass: hass_core.HomeAssistant, config_entry: config_entries.ConfigEntry):
    entry = {**config_entry.data, **config_entry.options}
    entry.pop(CONF_TOKEN, None)
    entry.pop(CONF_PASSWORD, None)
    entry.pop('service_token', None)
    entry.pop('ssecurity', None)
    _LOGGER.debug('Xiaomi Miot update options: %s', entry)
    hass.data[DOMAIN]['sub_entities'] = {}
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(hass: hass_core.HomeAssistant, config_entry: config_entries.ConfigEntry):
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(config_entry, sd)
                for sd in SUPPORTED_DOMAINS
            ]
        )
    )
    if unload_ok:
        hass.data[DOMAIN].pop(config_entry.entry_id, None)
    return unload_ok


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
        _LOGGER.debug('Xiaomi Miot service handler: %s', {
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


async def async_setup_config_entry(hass, config_entry, async_setup_platform, async_add_entities, domain=None):
    eid = config_entry.entry_id
    cfg = hass.data[DOMAIN].get(eid) or {}
    if not cfg:
        hass.data[DOMAIN].setdefault(eid, {})
    if domain:
        hass.data[DOMAIN][eid].setdefault('add_entities', {})
        hass.data[DOMAIN][eid]['add_entities'][domain] = async_add_entities
    cls = cfg.get('configs')
    if not cls:
        cls = [
            hass.data[DOMAIN].get(eid, dict(config_entry.data)),
        ]
    for c in cls:
        await async_setup_platform(hass, c, async_add_entities)
    return cls


class MiioInfo(MiioInfoBase):
    @property
    def firmware_version(self):
        """Firmware version if available."""
        return self.data.get('fw_ver')

    @property
    def hardware_version(self):
        """Hardware version if available."""
        return self.data.get('hw_ver')


class MiotDevice(MiotDeviceBase):
    def get_properties_for_mapping(self, *, max_properties=12, mapping=None) -> list:
        if mapping is None:
            mapping = self.mapping
        properties = [{'did': k, **v} for k, v in mapping.items()]
        return self.get_properties(
            properties,
            property_getter='get_properties',
            max_properties=max_properties,
        )


class BaseEntity(Entity):
    _config = None

    def global_config(self, key=None, default=None):
        if not self.hass:
            return default
        cfg = self.hass.data[DOMAIN]['config'] or {}
        return cfg if key is None else cfg.get(key, default)

    def custom_config(self, key=None, default=None):
        if not self.hass:
            return default
        if not self.entity_id:
            return default
        cfg = self.hass.data[DATA_CUSTOMIZE].get(self.entity_id) or {}
        return cfg if key is None else cfg.get(key, default)

    def entry_config(self, key=None, default=None):
        if not self.hass:
            return default
        cfg = self.hass.data[DOMAIN] or {}
        eid = None
        if self._config:
            eid = self._config.get('entry_id')
        if not eid and self.platform.config_entry:
            eid = self.platform.config_entry.entry_id
        if eid:
            cfg = {**cfg, **(self.hass.data[DOMAIN].get(eid) or {})}
        return cfg if key is None else cfg.get(key, default)

    def update_custom_scan_interval(self, only_custom=False):
        if not self.platform:
            return
        sec = self.custom_config('interval_seconds')
        if not sec and not only_custom:
            sec = self.entry_config(CONF_SCAN_INTERVAL)
        try:
            sec = int(sec or 0)
        except (TypeError, ValueError):
            sec = 0
        tim = timedelta(seconds=sec)
        if sec > 0 and tim != self.platform.scan_interval:
            self.platform.scan_interval = tim
            _LOGGER.debug('Update custom scan interval: %s for %s', tim, self.name)


class MiioEntity(BaseEntity):
    def __init__(self, name, device, **kwargs):
        self._device = device
        self._config = dict(kwargs.get('config') or {})
        try:
            miio_info = kwargs.get('miio_info', self._config.get('miio_info'))
            if miio_info and isinstance(miio_info, dict):
                miio_info = MiioInfo(miio_info)
            self._miio_info = miio_info if isinstance(miio_info, MiioInfo) else device.info()
        except DeviceException as exc:
            _LOGGER.error("Device %s unavailable or token incorrect: %s", name, exc)
            raise PlatformNotReady from exc
        except socket.gaierror as exc:
            _LOGGER.error("Device %s unavailable: socket.gaierror %s", name, exc)
            raise PlatformNotReady from exc
        self._unique_did = self.unique_did
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
        self._add_entities = {}
        self._vars = {}

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def unique_did(self):
        did = dr.format_mac(self._miio_info.mac_address)
        eid = self._config.get('entry_id')
        ver = self._config.get(CONF_CONFIG_VERSION) or 0
        if eid and ver > 0:
            did = f'{did}-{eid}'
        return did

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

    async def async_added_to_hass(self):
        if not self.hass:
            self._add_entities = self.hass.data[DOMAIN].get('add_entities') or {}
            return
        if self.platform:
            self.update_custom_scan_interval()
            if self.platform.config_entry:
                eid = self.platform.config_entry.entry_id
                self._add_entities = self.hass.data[DOMAIN][eid].get('add_entities') or {}

    async def _try_command(self, mask_error, func, *args, **kwargs):
        try:
            result = await self.hass.async_add_executor_job(partial(func, *args, **kwargs))
            _LOGGER.debug('Response received from miio %s: %s', self.name, result)
            return result == self._success_result
        except DeviceException as exc:
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


class MiotEntityInterface:
    _miot_service = None
    _model = ''
    _state_attrs = {}
    _supported_features = 0

    def set_property(self, *args, **kwargs):
        raise NotImplementedError()

    def set_miot_property(self, *args, **kwargs):
        raise NotImplementedError()

    def miot_action(self, *args, **kwargs):
        raise NotImplementedError()

    def update_attrs(self, *args, **kwargs):
        raise NotImplementedError()


class MiotEntity(MiioEntity):
    def __init__(self, miot_service=None, device=None, **kwargs):
        self._config = dict(kwargs.get('config') or {})
        self._miot_mapping = dict(kwargs.get('mapping') or {})
        self._miot_service = miot_service if isinstance(miot_service, MiotService) else None
        if not self._miot_mapping and self._miot_service:
            dic = miot_service.mapping() or {}
            self._miot_mapping = miot_service.spec.services_mapping() or {}
            self._miot_mapping = {**dic, **self._miot_mapping, **dic}

        name = self._config.get(CONF_NAME) or ''
        _LOGGER.info('Initializing miot device: %s, mapping: %s', name, self._miot_mapping)
        super().__init__(name, device, **kwargs)
        if self._miot_service:
            self._unique_id = f'{self._unique_id}-{self._miot_service.iid}'
            self._state_attrs['miot_type'] = self._miot_service.spec.type
        self._success_code = 0
        self._subs = {}

    @property
    def miot_device(self):
        if self.hass and not self._device and CONF_TOKEN in self._config:
            host = self._config.get(CONF_HOST) or ''
            token = self._config.get(CONF_TOKEN) or None
            device = None
            try:
                device = MiotDevice(ip=host, token=token)
                device.mapping = self._miot_mapping
            except TypeError as exc:
                if f'{exc}'.find('mapping') >= 0:
                    # for python-miio <= v0.5.4
                    device = MiotDevice(self._miot_mapping, host, token)  # noqa
            except ValueError as exc:
                _LOGGER.warning('Initializing with host %s (%s) failed: %s', host, self.name, exc)
            if device:
                self._device = device
        return self._device

    @property
    def miot_did(self):
        did = self.custom_config('miot_did') or self._config.get('miot_did')
        if self.entity_id and not did:
            mac = self._miio_info.mac_address
            dvs = self.entry_config('devices_by_mac') or {}
            if mac in dvs:
                return dvs[mac].get('did')
        return did

    @property
    def miot_cloud(self):
        isc = False
        if self.miot_local:
            isc = False
        elif self._config.get('miot_cloud'):
            isc = True
        elif self.custom_config('miot_cloud'):
            isc = True
        if isc and self.hass and self.miot_did:
            return self.entry_config('xiaomi_cloud')
        return None

    @property
    def miot_cloud_write(self):
        isc = False
        if self.custom_config('miot_cloud_write'):
            isc = True
        if isc and self.hass and self.miot_did:
            return self.entry_config('xiaomi_cloud')
        return self.miot_cloud

    @property
    def miot_cloud_action(self):
        isc = False
        if self.custom_config('miot_cloud_action'):
            isc = True
        if isc and self.hass and self.miot_did:
            return self.entry_config('xiaomi_cloud')
        return self.miot_cloud

    @property
    def miot_local(self):
        if self.custom_config('miot_local'):
            return self.miot_device
        return None

    @property
    def miot_config(self):
        return self._config or {}

    @property
    def miot_mapping(self):
        if not self._miot_mapping:
            if self.miot_mapping:
                return self.miot_device.mapping
        return self._miot_mapping

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
            _LOGGER.error(mask_error, exc)
            self._available = False
        return False

    async def async_update(self):
        if self._vars.get('delay_update'):
            await asyncio.sleep(self._vars.get('delay_update'))
            self._vars.pop('delay_update', 0)
        updater = 'lan'
        results = []
        rmp = {}
        try:
            if self.miot_cloud:
                updater = 'cloud'
                results = await self.hass.async_add_executor_job(
                    partial(self.miot_cloud.get_properties_for_mapping, self.miot_did, self.miot_mapping)
                )
                if self.custom_config('check_lan'):
                    if self.miot_device:
                        await self.hass.async_add_executor_job(self.miot_device.info)
                    else:
                        self._available = False
                        return
            elif self.miot_device:
                for k, v in self.miot_mapping.items():
                    s = v.get('siid')
                    p = v.get('piid')
                    rmp[f'{s}{p}'] = k
                max_properties = self.custom_config('chunk_properties', 12)
                try:
                    max_properties = int(max_properties)
                except (TypeError, ValueError):
                    max_properties = 10
                results = await self.hass.async_add_executor_job(
                    partial(self.miot_device.get_properties_for_mapping, max_properties=max_properties)
                )
            else:
                _LOGGER.error('Local device and miot cloud not ready %s', self.name)
        except DeviceException as exc:
            self._available = False
            _LOGGER.error(
                'Got MiioException while fetching the state for %s: %s, mapping: %s',
                self.name, exc, self.miot_mapping,
            )
            return
        except MiCloudException as exc:
            self._available = False
            _LOGGER.error('Got MiCloudException while fetching the state for %s: %s', self.name, exc)
            return
        attrs = {}
        for prop in results or []:
            if not isinstance(prop, dict):
                continue
            s = prop.get('siid')
            p = prop.get('piid')
            k = rmp.get(f'{s}{p}', prop.get('did'))
            if k is None:
                continue
            e = prop.get('code')
            ek = f'{k}.error'
            if e == 0:
                attrs[k] = prop.get('value')
                if ek in self._state_attrs:
                    self._state_attrs.pop(ek, None)
            else:
                attrs[ek] = e
        self._available = True
        self._state = True if attrs.get('power') else False
        attrs['state_updater'] = updater

        if self._miot_service:
            for d in ['sensor', 'binary_sensor', 'switch', 'number', 'fan', 'cover']:
                pls = str(self.custom_config(f'{d}_properties') or '').split(',')
                if pls:
                    self._update_sub_entities(pls, '*', domain=d)
            self._update_sub_entities(
                [
                    'temperature', 'indoor_temperature', 'relative_humidity', 'humidity',
                    'pm2_5_density', 'pm10_density', 'co2_density', 'air_quality', 'air_quality_index',
                    'illumination', 'motion_state', 'motion_detection',
                ],
                ['environment', 'illumination_sensor', 'motion_detection'],
                domain='sensor',
            )
            self._update_sub_entities(
                ['filter_life_level', 'filter_left_time', 'filter_used_time', 'filter_left_flow', 'filter_used_flow'],
                ['filter'],
                domain='sensor',
            )
            self._update_sub_entities(
                [
                    'battery_level', 'charging_state', 'voltage', 'power_consumption', 'electric_current',
                    'leakage_current', 'surge_power', 'electric_power', 'elec_count',
                ],
                ['battery', 'power_consumption', 'electricity'],
                domain='sensor',
            )
            self._update_sub_entities(
                ['tds_in', 'tds_out'],
                ['tds_sensor'],
                domain='sensor',
            )
            self._update_sub_entities(
                ['brush_life_level', 'brush_left_time'],
                ['brush_cleaner'],
                domain='sensor',
            )
            self._update_sub_entities(
                'physical_controls_locked',
                ['physical_controls_locked', self._miot_service.name],
                domain='switch',
            )
            self._update_sub_entities(None, ['indicator_light', 'night_light'], domain='light')
        if self._subs:
            attrs['sub_entities'] = list(self._subs.keys())
        self.update_attrs(attrs)
        _LOGGER.debug('Got new state from %s: %s', self.name, attrs)

    def get_properties(self, mapping: dict, throw=False, **kwargs):
        if not self.miot_device:
            return
        try:
            results = self.miot_device.get_properties_for_mapping(mapping=mapping)
        except (ValueError, DeviceException) as exc:
            if throw:
                raise exc
            _LOGGER.error(
                'Got exception while get properties from %s: %s, mapping: %s, miio: %s',
                self.name, exc, mapping, self._miio_info.data,
            )
            return
        attrs = {
            prop['did']: prop['value'] if prop['code'] == 0 else None
            for prop in results
        }
        _LOGGER.info('Get miot properties from %s: %s', self.name, results)
        if throw:
            persistent_notification.create(
                self.hass,
                f'{results}',
                'Miot properties',
                f'{DOMAIN}-debug',
            )
            raise Warning(f'Miot properties: {results}')
        return attrs

    async def async_get_properties(self, mapping, **kwargs):
        return await self.hass.async_add_executor_job(
            partial(self.get_properties, mapping, **kwargs)
        )

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

    async def async_set_property(self, *args, **kwargs):
        if not self.hass:
            _LOGGER.info('Set miot property (%s) to %s failed: hass not ready.', args, self.name)
            return False
        return await self.hass.async_add_executor_job(partial(self.set_property, *args, **kwargs))

    def set_miot_property(self, siid, piid, value, did=None):
        if did is None:
            did = self.miot_did or f'property-{siid}-{piid}'
        pms = {
            'did':  str(did),
            'siid': siid,
            'piid': piid,
            'value': value,
        }
        ret = None
        try:
            mcw = self.miot_cloud_write
            if isinstance(mcw, MiotCloud):
                results = mcw.set_props([pms])
            else:
                results = self.miot_device.send('set_properties', [pms])
            for ret in (results or []):
                break
        except DeviceException as exc:
            _LOGGER.warning('Set miot property to %s (%s) failed: %s', self.name, pms, exc)
        except MiCloudException as exc:
            _LOGGER.warning('Set miot property to cloud for %s (%s) failed: %s', self.name, pms, exc)
        if ret:
            self._vars['delay_update'] = 2
            _LOGGER.debug('Set miot property to %s (%s), result: %s', self.name, pms, ret)
        return ret

    async def async_set_miot_property(self, siid, piid, value, did=None):
        return await self.hass.async_add_executor_job(partial(self.set_miot_property, siid, piid, value, did))

    def call_action(self, action: MiotAction, params=None, did=None, **kwargs):
        aiid = action.iid
        siid = action.service.iid
        pms = params or []
        if not self.miot_cloud_action:
            pms = action.in_params(params or [])
        return self.miot_action(siid, aiid, pms, did, **kwargs)

    def miot_action(self, siid, aiid, params=None, did=None, **kwargs):
        if did is None:
            did = self.miot_did or f'action-{siid}-{aiid}'
        pms = {
            'did':  str(did),
            'siid': siid,
            'aiid': aiid,
            'in':   params or [],
        }
        ret = None
        try:
            mca = self.miot_cloud_action
            if isinstance(mca, MiotCloud):
                ret = mca.do_action(pms)
            else:
                ret = self.miot_device.send('action', pms)
        except DeviceException as exc:
            _LOGGER.warning('Call miot action to %s (%s) failed: %s', self.name, pms, exc)
        except MiCloudException as exc:
            _LOGGER.warning('Call miot action to cloud for %s (%s) failed: %s', self.name, pms, exc)
        if ret:
            self._vars['delay_update'] = 2
            _LOGGER.debug('Call miot action to %s (%s), result: %s', self.name, pms, ret)
        self._state_attrs['miot_action_result'] = ret
        if kwargs.get('throw'):
            persistent_notification.create(
                self.hass,
                f'{ret}',
                'Miot action result',
                f'{DOMAIN}-debug',
            )
            raise Warning(f'Miot action result: {ret}')
        return ret

    async def async_miot_action(self, siid, aiid, params=None, did=None, **kwargs):
        return await self.hass.async_add_executor_job(
            partial(self.miot_action, siid, aiid, params, did, **kwargs)
        )

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

    def _update_sub_entities(self, properties, services=None, domain=None, option=None):
        from .binary_sensor import MiotBinarySensorSubEntity
        from .switch import MiotSwitchSubEntity
        from .light import MiotLightSubEntity
        from .fan import MiotModesSubEntity
        from .cover import MiotCoverSubEntity
        from .number import MiotNumberSubEntity
        if isinstance(services, MiotService):
            sls = [services]
        elif services == '*':
            sls = self._miot_service.spec.services
        elif services:
            sls = self._miot_service.spec.get_services(*cv.ensure_list(services))
        else:
            sls = [self._miot_service]
        add_sensors = self._add_entities.get('sensor')
        add_binary_sensors = self._add_entities.get('binary_sensor')
        add_switches = self._add_entities.get('switch')
        add_lights = self._add_entities.get('light')
        add_fans = self._add_entities.get('fan')
        add_covers = self._add_entities.get('cover')
        add_numbers = self._add_entities.get('number')
        for s in sls:
            if not properties:
                fnm = s.unique_name
                tms = self._check_same_sub_entity(fnm, domain)
                new = True
                if fnm in self._subs:
                    new = False
                    self._subs[fnm].update()
                    self._check_same_sub_entity(fnm, domain, add=1)
                elif tms > 0:
                    if tms <= 1:
                        _LOGGER.info('Device %s sub entity %s: %s already exists.', self.name, domain, fnm)
                elif add_lights and domain == 'light':
                    pon = s.get_property('on')
                    if pon and pon.full_name in self._state_attrs:
                        self._subs[fnm] = MiotLightSubEntity(self, s)
                        add_lights([self._subs[fnm]])
                if new and fnm in self._subs:
                    self._check_same_sub_entity(fnm, domain, add=1)
                    _LOGGER.debug('Added sub entity %s: %s for %s.', domain, fnm, self.name)
                continue
            pls = s.get_properties(*cv.ensure_list(properties))
            for p in pls:
                if p.full_name not in self._state_attrs:
                    continue
                fnm = p.unique_name
                tms = self._check_same_sub_entity(fnm, domain)
                new = True
                if fnm in self._subs:
                    new = False
                    self._subs[fnm].update()
                    self._check_same_sub_entity(fnm, domain, add=1)
                elif tms > 0:
                    if tms <= 1:
                        _LOGGER.info('Device %s sub entity %s: %s already exists.', self.name, domain, fnm)
                elif add_switches and domain == 'switch' and p.format == 'bool' and p.writeable:
                    self._subs[fnm] = MiotSwitchSubEntity(self, p, option=option)
                    add_switches([self._subs[fnm]])
                elif add_binary_sensors and domain == 'binary_sensor' and p.format == 'bool':
                    self._subs[fnm] = MiotBinarySensorSubEntity(self, p, option=option)
                    add_binary_sensors([self._subs[fnm]])
                elif add_sensors and domain == 'sensor':
                    self._subs[fnm] = MiotSensorSubEntity(self, p, option=option)
                    add_sensors([self._subs[fnm]])
                elif add_fans and domain == 'fan':
                    self._subs[fnm] = MiotModesSubEntity(self, p, option=option)
                    add_fans([self._subs[fnm]])
                elif add_covers and domain == 'cover':
                    self._subs[fnm] = MiotCoverSubEntity(self, p, option=option)
                    add_covers([self._subs[fnm]])
                elif add_numbers and domain == 'number':
                    self._subs[fnm] = MiotNumberSubEntity(self, p, option=option)
                    add_numbers([self._subs[fnm]])
                if new and fnm in self._subs:
                    self._check_same_sub_entity(fnm, domain, add=1)
                    _LOGGER.debug('Added sub entity %s: %s for %s.', domain, fnm, self.name)

    def _check_same_sub_entity(self, name, domain=None, add=0):
        uni = f'{self._unique_did}-{name}-{domain}'
        pre = int(self.hass.data[DOMAIN]['sub_entities'].get(uni) or 0)
        if add and pre < 999999:
            self.hass.data[DOMAIN]['sub_entities'][uni] = pre + add
        return pre

    async def async_get_device_data(self, key, did=None, throw=False, **kwargs):
        if did is None:
            did = self.miot_did
        mic = self.miot_cloud
        if not isinstance(mic, MiotCloud):
            return None
        result = await self.hass.async_add_executor_job(
            partial(mic.get_user_device_data, did, key, raw=True, **kwargs)
        )
        persistent_notification.async_create(
            self.hass,
            f'{result}',
            f'Miot device data: {self.name}',
            f'{DOMAIN}-debug',
        )
        if throw:
            raise Warning(f'Miot device data for {self.name}: {result}')
        else:
            _LOGGER.debug('Miot device data for %s: %s', self.name, result)
        return result

    async def async_get_token(self, name=None, throw=False):
        if name:
            cld = self.entry_config('xiaomi_cloud')
            dvs = (await cld.async_get_devices() or []) if isinstance(cld, MiotCloud) else []
            cnt = len(dvs)
            lst = [
                {
                    'did': d.get('did'),
                    CONF_NAME: d.get('name'),
                    CONF_HOST: d.get('localip'),
                    CONF_TOKEN: d.get('token'),
                    CONF_MODEL: d.get('model'),
                }
                for d in dvs
                if isinstance(d, dict) and name in d.get('name')
            ] or [f'Not Found in {cnt} devices.']
        else:
            lst = [
                {
                    CONF_NAME: self._name,
                    CONF_HOST: self._miio_info.network_interface.get('localIp'),
                    CONF_TOKEN: self._miio_info.data.get('token'),
                    CONF_MODEL: self._miio_info.model,
                }
            ]
        msg = '\n\n'.join(map(lambda v: f'{v}', lst))
        persistent_notification.async_create(
            self.hass,
            msg,
            'Miot device',
            f'{DOMAIN}-debug',
        )
        if throw:
            raise Warning(f'Miot device: {msg}')
        else:
            _LOGGER.warning('Miot device: %s', msg)
        return self._miio_info.data.get('token')

    async def async_get_bindkey(self, did=None, throw=False):
        mic = self.miot_cloud
        if not isinstance(mic, MiotCloud):
            return None
        dat = {'did': did or self.miot_did, 'pdid': 1}
        result = await self.hass.async_add_executor_job(
            partial(mic.request_miot_api, 'v2/device/blt_get_beaconkey', dat)
        )
        persistent_notification.async_create(
            self.hass,
            f'{result}',
            f'Miot bindkey: {self.name}',
            f'{DOMAIN}-debug',
        )
        if throw:
            raise Warning(f'Miot bindkey for {self.name}: {result}')
        else:
            _LOGGER.warning('Miot bindkey for %s: %s', self.name, result)
        return (result or {}).get('beaconkey')

    async def async_request_xiaomi_api(self, api, params=None, throw=False):
        mic = self.miot_cloud
        if not isinstance(mic, MiotCloud):
            return None
        result = await self.hass.async_add_executor_job(
            partial(mic.request_miot_api, str(api).lstrip('/'), params)
        )
        persistent_notification.async_create(
            self.hass,
            f'{result}',
            f'Xiaomi Api: {api}',
            f'{DOMAIN}-debug',
        )
        if throw:
            raise Warning(f'Xiaomi Api {api}: {result}')
        else:
            _LOGGER.debug('Xiaomi Api %s: %s', api, result)
        return result


class MiotToggleEntity(MiotEntity, ToggleEntity):
    def __init__(self, miot_service=None, device=None, **kwargs):
        super().__init__(miot_service, device, **kwargs)
        self._prop_power = miot_service.bool_property('on', 'power', 'switch')

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
        act = self._miot_service.get_action('stop_working', 'power_off')
        if act:
            return self.miot_action(self._miot_service.iid, act.iid)
        return False


class BaseSubEntity(BaseEntity):
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
        self._parent_attrs = {}

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def name(self):
        return self._name

    def format_name_by_property(self, prop: MiotProperty):
        nam = str(self._name).lower()
        nam = re.sub(r'\W+', '_', nam)
        if nam.find(prop.service.name):
            return f'{self._parent.name} {prop.name}'
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

    async def async_added_to_hass(self):
        if self.platform:
            self.update_custom_scan_interval(only_custom=True)

    def update(self):
        attrs = self._parent.device_state_attributes or {}
        self._parent_attrs = attrs
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

    async def async_update(self):
        await self.hass.async_add_executor_job(self.update)

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
            _LOGGER.info('Parent entity of %s has no method: %s', self.name, f)
        if ret:
            self.update()
        return ret

    def set_parent_property(self, val, prop):
        ret = self.call_parent('set_property', prop, val)
        if ret:
            self.update_attrs({
                prop: val,
            })
        return ret


class ToggleSubEntity(BaseSubEntity, ToggleEntity):
    def __init__(self, parent, attr='power', option=None):
        self._prop_power = None
        super().__init__(parent, attr, option)

    def update(self):
        super().update()
        if self._available:
            attrs = self._state_attrs
            self._state = cv.boolean(attrs.get(self._attr) or False)

    @property
    def state(self):
        return STATE_ON if self.is_on else STATE_OFF

    @property
    def is_on(self):
        return self._state

    def turn_on(self, **kwargs):
        if self._prop_power:
            ret = self.call_parent('set_property', self._prop_power.full_name, True)
            if ret:
                self._state = True
            return ret
        return self.call_parent('turn_on', **kwargs)

    def turn_off(self, **kwargs):
        if self._prop_power:
            ret = self.call_parent('set_property', self._prop_power.full_name, False)
            if ret:
                self._state = False
            return ret
        return self.call_parent('turn_off', **kwargs)


class MiotSensorSubEntity(BaseSubEntity):
    def __init__(self, parent, miot_property: MiotProperty, option=None):
        self._miot_service = miot_property.service
        self._miot_property = miot_property
        super().__init__(parent, miot_property.full_name, option)
        self._name = self.format_name_by_property(miot_property)
        if not self._option.get('unique_id'):
            self._unique_id = f'{parent.unique_did}-{miot_property.unique_name}'

        self._prop_battery = None
        for s in self._miot_service.spec.get_services('battery', self._miot_service.name):
            p = s.get_property('battery_level')
            if p:
                self._prop_battery = p
        if self._prop_battery:
            self._option['keys'] = [*(self._option.get('keys') or []), self._prop_battery.full_name]

        unit = miot_property.unit
        if unit in ['celsius', TEMP_CELSIUS]:
            self._option['unit'] = TEMP_CELSIUS
        elif unit in ['fahrenheit', TEMP_FAHRENHEIT]:
            self._option['unit'] = TEMP_FAHRENHEIT
        elif unit in ['kelvin', TEMP_KELVIN]:
            self._option['unit'] = TEMP_KELVIN
        elif unit in ['percentage', PERCENTAGE]:
            self._option['unit'] = PERCENTAGE
        elif unit in ['μg/m3', CONCENTRATION_MICROGRAMS_PER_CUBIC_METER]:
            self._option['unit'] = CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
        elif unit and unit not in ['none']:
            self._option['unit'] = unit

        if 'temperature' in miot_property.full_name:
            self._option['device_class'] = DEVICE_CLASS_TEMPERATURE
        elif 'humidity' in miot_property.full_name:
            self._option['device_class'] = DEVICE_CLASS_HUMIDITY
        elif 'battery' in miot_property.full_name:
            self._option['device_class'] = DEVICE_CLASS_BATTERY
        elif 'illumination' in miot_property.full_name:
            self._option['device_class'] = DEVICE_CLASS_ILLUMINANCE
        elif 'voltage' in miot_property.full_name:
            self._option['device_class'] = DEVICE_CLASS_VOLTAGE
        elif 'electric_current' in miot_property.full_name:
            self._option['device_class'] = DEVICE_CLASS_CURRENT
        elif 'electric_power' in miot_property.full_name:
            self._option['device_class'] = DEVICE_CLASS_POWER

    def update(self):
        super().update()
        if not self._available:
            return
        self._miot_property.description_to_dict(self._state_attrs)

    @property
    def state(self):
        key = f'{self._miot_property.full_name}_desc'
        if key in self._state_attrs:
            return f'{self._state_attrs[key]}'.lower()
        return self._miot_property.from_dict(self._state_attrs, STATE_UNKNOWN)

    def set_parent_property(self, val, prop=None):
        if prop is None:
            prop = self._miot_property
        ret = self.call_parent('set_miot_property', prop.service.iid, prop.iid, val)
        if ret and prop.readable:
            self.update_attrs({
                prop.full_name: val,
            })
        return ret
