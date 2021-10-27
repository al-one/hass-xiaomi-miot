"""Support for Xiaomi Miot."""
import logging
import asyncio
import socket
import json
import time
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

from .core.const import *
from .core.utils import async_analytics_track_event
from .core.miot_spec import (
    MiotSpec,
    MiotService,
    MiotProperty,
    MiotAction,
    MiotResults,
)
from .core.xiaomi_cloud import (
    MiotCloud,
    MiCloudException,
)
from .core.templates import CUSTOM_TEMPLATES

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=60)

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
                vol.Optional('throw', default=False): cv.boolean,
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
                vol.Optional('throw', default=False): cv.boolean,
            },
        ),
    },
    'get_properties': {
        'method': 'async_get_properties',
        'schema': XIAOMI_MIIO_SERVICE_SCHEMA.extend(
            {
                vol.Required('mapping'): dict,
                vol.Optional('throw', default=True): cv.boolean,
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
                vol.Optional('data', default={}): vol.Any(dict, list),
                vol.Optional('params', default={}): vol.Any(dict, list, None),  # deprecated
                vol.Optional('method', default='POST'): cv.string,
                vol.Optional('crypt', default=False): cv.boolean,
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
                vol.Optional(CONF_SERVER_COUNTRY): cv.string,
            },
            extra=vol.ALLOW_EXTRA,
        ),
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
    await async_setup_component_services(hass)
    bind_services_to_entries(hass, SERVICE_TO_METHOD_BASE)

    if lang := config.get('language'):
        dic = TRANSLATION_LANGUAGES.get(lang)
        if isinstance(dic, dict):
            TRANSLATION_LANGUAGES.update(dic)
    if dic := config.get('translations') or {}:
        if isinstance(dic, dict):
            TRANSLATION_LANGUAGES.update(dic)

    if config.get(CONF_USERNAME) and config.get(CONF_PASSWORD):
        try:
            mic = MiotCloud(
                hass,
                config.get(CONF_USERNAME),
                config.get(CONF_PASSWORD),
                config.get(CONF_SERVER_COUNTRY),
            )
            if not await mic.async_login():
                raise MiCloudException('Login failed')
            hass.data[DOMAIN][CONF_XIAOMI_CLOUD] = mic
            hass.data[DOMAIN]['devices_by_mac'] = await mic.async_get_devices_by_key('mac') or {}
            cnt = len(hass.data[DOMAIN]['devices_by_mac'])
            _LOGGER.debug('Setup xiaomi cloud for user: %s, %s devices', config.get(CONF_USERNAME), cnt)
        except MiCloudException as exc:
            _LOGGER.warning('Setup xiaomi cloud for user: %s failed: %s', config.get(CONF_USERNAME), exc)

    await _handle_device_registry_event(hass)
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
        config[CONF_CONN_MODE] = 'local'
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
        config[CONF_XIAOMI_CLOUD] = mic
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
        conn = entry.get(CONF_CONN_MODE, DEFAULT_CONN_MODE)
        cfg = {
            CONF_NAME: d.get(CONF_NAME) or DEFAULT_NAME,
            CONF_HOST: d.get('localip') or '',
            CONF_TOKEN: d.get('token') or '',
            CONF_MODEL: model,
            'miot_did': d.get('did') or '',
            'miot_type': urn,
            'miio_info': mif,
            CONF_CONN_MODE: conn,
            'miot_cloud': conn != 'local',
            'entry_id': entry_id,
            CONF_CONFIG_VERSION: entry.get(CONF_CONFIG_VERSION) or 0,
        }
        if conn == 'auto' and model in MIOT_LOCAL_MODELS:
            cfg['miot_cloud'] = False
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
        hass.data[DOMAIN]['sub_entities'] = {}
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
                _LOGGER.info('Entity %s have no method: %s', dvc.entity_id, fun)
                continue
            await getattr(dvc, fun)(**params)
            update_tasks.append(dvc.async_update_ha_state(True))
        if update_tasks:
            await asyncio.wait(update_tasks)

    for srv, obj in services.items():
        schema = obj.get('schema', XIAOMI_MIIO_SERVICE_SCHEMA)
        hass.services.async_register(DOMAIN, srv, async_service_handler, schema=schema)


async def async_setup_component_services(hass):

    async def async_get_token(call):
        nam = call.data.get('name')
        kwd = f'{nam}'.strip().lower()
        cls = []
        for k, v in hass.data[DOMAIN].items():
            if isinstance(v, dict):
                v = v.get(CONF_XIAOMI_CLOUD)
            if isinstance(v, MiotCloud):
                cls.append(v)
        cnt = 0
        lst = []
        dls = {}
        for cld in cls:
            dvs = await cld.async_get_devices() or []
            for d in dvs:
                if not isinstance(d, dict):
                    continue
                did = d.get('did') or ''
                if dls.get(did):
                    continue
                dnm = f"{d.get('name') or ''}"
                dip = d.get('localip') or ''
                dmd = d.get('model') or ''
                if kwd in dnm.lower() or kwd == dip or kwd in dmd:
                    lst.append({
                        'did': did,
                        CONF_NAME: dnm,
                        CONF_HOST: dip,
                        CONF_MODEL: dmd,
                        CONF_TOKEN: d.get('token'),
                    })
                dls[did] = 1
                cnt += 1
        if not lst:
            lst = [f'Not Found "{nam}" in {cnt} devices.']
        msg = '\n\n'.join(map(lambda vv: f'{vv}', lst))
        persistent_notification.async_create(
            hass, msg, 'Miot device', f'{DOMAIN}-debug',
        )
        return lst

    hass.services.async_register(
        DOMAIN, 'get_token', async_get_token,
        schema=XIAOMI_MIIO_SERVICE_SCHEMA.extend(
        {
            vol.Required('name', default=''): cv.string,
        }),
    )


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


async def _handle_device_registry_event(hass: hass_core.HomeAssistant):
    async def updated(event: hass_core.Event):
        if event.data['action'] != 'update':
            return
        registry = hass.data['device_registry']
        device = registry.async_get(event.data['device_id'])
        if not device or not device.identifiers:
            return
        identifier = next(iter(device.identifiers))
        if identifier[0] != DOMAIN:
            return
        if device.name_by_user in ['delete', 'remove', '删除']:
            # remove from Hass
            registry.async_remove_device(device.id)
    hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, updated)


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
    def get_properties_for_mapping(self, *, max_properties=12, did=None, mapping=None) -> list:
        if mapping is None:
            mapping = self.mapping
        properties = [
            {'did': f'prop.{v["siid"]}.{v["piid"]}' if did is None else str(did), **v}
            for k, v in mapping.items()
        ]
        return self.get_properties(
            properties,
            property_getter='get_properties',
            max_properties=max_properties,
        )


class BaseEntity(Entity):
    _config = None
    _model = None

    def global_config(self, key=None, default=None):
        if not self.hass:
            return default
        cfg = self.hass.data[DOMAIN]['config'] or {}
        return cfg if key is None else cfg.get(key, default)

    @property
    def wildcard_models(self):
        if not self._model:
            return []
        wil = re.sub(r'\.[^.]+$', '.*', self._model)
        return [
            self._model,
            wil,
            re.sub(r'^[^.]+\.', '*.', wil),
        ]

    def custom_config(self, key=None, default=None):
        if not self.hass:
            return default
        if not self.entity_id:
            return default
        cfg = self.hass.data[DATA_CUSTOMIZE].get(self.entity_id) or {}
        return cfg if key is None else cfg.get(key, default)

    @property
    def conn_mode(self):
        return self._config.get(CONF_CONN_MODE)

    @property
    def entry_config_version(self):
        return self._config.get(CONF_CONFIG_VERSION) or 0

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

    def custom_config_bool(self, key=None, default=None):
        val = self.custom_config(key, default)
        try:
            val = cv.boolean(val)
        except vol.Invalid:
            val = default
        return val

    def custom_config_number(self, key=None, default=None):
        num = default
        val = self.custom_config(key)
        if val is not None:
            try:
                num = float(f'{val}')
            except (TypeError, ValueError):
                num = default
        return num

    def custom_config_integer(self, key=None, default=None):
        num = self.custom_config_number(key, default)
        if num is not None:
            num = int(num)
        return num

    def custom_config_list(self, key=None, default=None):
        lst = self.custom_config(key)
        if lst is None:
            return default
        if not isinstance(lst, list):
            lst = f'{lst}'.split(',')
        return lst

    def custom_config_json(self, key=None, default=None):
        dic = self.custom_config(key)
        if dic:
            if not isinstance(dic, dict):
                try:
                    dic = json.loads(dic or '{}')
                except (TypeError, ValueError):
                    dic = None
            if isinstance(dic, dict):
                return dic
        return default

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
            _LOGGER.debug('%s: Update custom scan interval: %s', self.name, tim)


class MiioEntity(BaseEntity):
    def __init__(self, name, device, **kwargs):
        self._device = device
        self._config = dict(kwargs.get('config') or {})
        self.logger = kwargs.get('logger') or _LOGGER
        try:
            miio_info = kwargs.get('miio_info', self._config.get('miio_info'))
            if miio_info and isinstance(miio_info, dict):
                miio_info = MiioInfo(miio_info)
            self._miio_info = miio_info if isinstance(miio_info, MiioInfo) else device.info()
        except DeviceException as exc:
            self.logger.error('%s: Device unavailable or token incorrect: %s', name, exc)
            raise PlatformNotReady from exc
        except socket.gaierror as exc:
            self.logger.error("%s: Device unavailable: socket.gaierror %s", name, exc)
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
        self._subs = {}

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def unique_mac(self):
        mac = self._miio_info.mac_address
        if not mac and self.entry_config_version >= 0.2:
            mac = self._config.get('miot_did')
        return mac

    @property
    def unique_did(self):
        did = dr.format_mac(self.unique_mac)
        eid = self._config.get('entry_id')
        if eid and self.entry_config_version >= 0.1:
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
    def extra_state_attributes(self):
        ext = self.state_attributes or {}
        return {**self._state_attrs, **ext}

    @property
    def supported_features(self):
        return self._supported_features

    @property
    def device_name(self):
        return self._config.get(CONF_NAME) or self._name

    @property
    def device_info(self):
        return {
            'identifiers': {(DOMAIN, self._unique_did)},
            'name': self.device_name,
            'model': self._model,
            'manufacturer': (self._model or 'Xiaomi').split('.', 1)[0],
            'sw_version': self._miio_info.firmware_version,
        }

    async def async_added_to_hass(self):
        if self.platform:
            self.update_custom_scan_interval()
            if self.platform.config_entry:
                eid = self.platform.config_entry.entry_id
                self._add_entities = self.hass.data[DOMAIN][eid].get('add_entities') or {}

    def custom_config(self, key=None, default=None):
        ret = super().custom_config(key)
        if key is not None:
            if ret is not None:
                return ret
            cfg = {}
        else:
            cfg = ret or {}
        if self._model:
            gcs = GLOBAL_CUSTOMIZES['models']
            ucs = self.global_config('device_customizes') or {}
            if ucs and isinstance(ucs, dict):
                gcs.update(ucs)
            for m in self.wildcard_models:
                cus = gcs.get(m) or {}
                if key is not None and key not in cus:
                    continue
                if cus:
                    cfg = {**cus, **cfg}
        return cfg if key is None else cfg.get(key, default)

    async def _try_command(self, mask_error, func, *args, **kwargs):
        try:
            result = await self.hass.async_add_executor_job(partial(func, *args, **kwargs))
            self.logger.debug('%s: Response received from miio: %s', self.name, result)
            return result == self._success_result
        except DeviceException as exc:
            self.logger.error(mask_error, exc)
            self._available = False
        return False

    def send_miio_command(self, method, params=None, **kwargs):
        self.logger.debug('%s: Send miio command: %s(%s)', self.name, method, params)
        try:
            result = self._device.send(method, params if params is not None else [])
        except DeviceException as ex:
            self.logger.error('%s: Send miio command: %s(%s) failed: %s', self.name, method, params, ex)
            return False
        ret = result == self._success_result
        if not ret:
            self.logger.info('%s: Send miio command: %s(%s) failed, result: %s', self.name, method, params, result)
        if kwargs.get('throw'):
            persistent_notification.create(
                self.hass,
                f'{result}',
                'Miio command result',
                f'{DOMAIN}-debug',
            )
        return ret

    def send_command(self, method, params=None, **kwargs):
        return self.send_miio_command(method, params, **kwargs)

    async def async_command(self, method, params=None, **kwargs):
        return await self.hass.async_add_executor_job(
            partial(self.send_miio_command, method, params, **kwargs)
        )

    async def async_update(self):
        try:
            attrs = await self.hass.async_add_executor_job(
                partial(self._device.get_properties, self._props)
            )
        except DeviceException as ex:
            self._available = False
            self.logger.error('%s: Got exception while fetching the state %s: %s', self.name, self._props, ex)
            return
        attrs = dict(zip(self._props, attrs))
        self.logger.debug('%s: Got new state: %s', self.name, attrs)
        self._available = True
        self._state = attrs.get('power') == 'on'
        self.update_attrs(attrs)

    def _update_attr_sensor_entities(self, attrs, option=None):
        domain = 'sensor'
        add_sensors = self._add_entities.get(domain)
        opt = {**(option or {})}
        for a in attrs:
            p = a
            if ':' in a:
                p = a
                kys = a.split(':')
                a = kys[0]
                opt['dict_key'] = kys[1]
            if a not in self._state_attrs:
                continue
            tms = self._check_same_sub_entity(p, domain)
            if p in self._subs and hasattr(self._subs[p], 'update'):
                self._subs[p].update()
                self._check_same_sub_entity(p, domain, add=1)
            elif tms > 0:
                if tms <= 1:
                    self.logger.info('%s: Device sub entity %s: %s already exists.', self.name, domain, p)
                continue
            elif add_sensors:
                from .sensor import BaseSensorSubEntity
                option = {'unique_id': f'{self._unique_did}-{p}', **opt}
                self._subs[p] = BaseSensorSubEntity(self, a, option=option)
                add_sensors([self._subs[p]])
                self._check_same_sub_entity(p, domain, add=1)

    def _check_same_sub_entity(self, name, domain=None, add=0):
        uni = f'{self._unique_did}-{name}-{domain}'
        pre = int(self.hass.data[DOMAIN]['sub_entities'].get(uni) or 0)
        if add and pre < 999999:
            self.hass.data[DOMAIN]['sub_entities'][uni] = pre + add
        return pre

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
        pls = self.custom_config_list('sensor_attributes')
        if pls:
            self._update_attr_sensor_entities(pls)
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
        name = kwargs.get(CONF_NAME) or self._config.get(CONF_NAME) or ''
        self._miot_service = miot_service if isinstance(miot_service, MiotService) else None
        if self._miot_service:
            name = f'{name} {self._miot_service.friendly_desc}'
            kwargs['miot_service'] = self._miot_service
        super().__init__(name, device, **kwargs)

        self._miot_mapping = dict(kwargs.get('mapping') or {})
        if self._miot_service:
            if custom := DEVICE_CUSTOMIZES.get(self._model, {}).get('miot_mapping'):
                miot_service.spec.set_custom_mapping(custom)
            if not self._miot_mapping:
                dic = miot_service.mapping() or {}
                self._miot_mapping = miot_service.spec.services_mapping(excludes=[self._miot_service.name]) or {}
                self._miot_mapping = {**dic, **self._miot_mapping, **dic}
            self._unique_id = f'{self._unique_id}-{self._miot_service.iid}'
            self._state_attrs['miot_type'] = self._miot_service.spec.type
            self.entity_id = self._miot_service.generate_entity_id(self)
        if self._model in MIOT_LOCAL_MODELS:
            self._vars['track_miot_error'] = True
        self._success_code = 0
        self.logger.info('%s: Initializing miot device with mapping: %s', name, self._miot_mapping)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if not self._miot_service:
            return
        if dic := self.custom_config_json('miot_mapping'):
            self._miot_service.spec.set_custom_mapping(dic)
        self._vars['exclude_services'] = self.custom_config_list('exclude_miot_services') or []

    @property
    def miot_device(self):
        if self.hass and not self._device and CONF_TOKEN in self._config:
            host = self._config.get(CONF_HOST) or ''
            token = self._config.get(CONF_TOKEN) or None
            device = None
            mapping = self.custom_config_json('miot_local_mapping')
            if not mapping:
                mapping = self.miot_mapping
            elif self._miot_service:
                self._miot_service.spec.set_custom_mapping(mapping)
                self._vars['has_local_mapping'] = True
            try:
                device = MiotDevice(ip=host, token=token, mapping=mapping)
            except TypeError as exc:
                err = f'{exc}'
                if 'mapping' in err:
                    if 'unexpected keyword argument' in err:
                        # for python-miio <= v0.5.5.1
                        device = MiotDevice(host, token)
                        device.mapping = mapping
                    elif 'required positional argument' in err:
                        # for python-miio <= v0.5.4
                        # https://github.com/al-one/hass-xiaomi-miot/issues/44#issuecomment-815474650
                        device = MiotDevice(mapping, host, token)  # noqa
            except ValueError as exc:
                self.logger.warning('%s: Initializing with host %s failed: %s', host, self.name, exc)
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
    def xiaomi_cloud(self):
        if self.hass:
            return self.entry_config(CONF_XIAOMI_CLOUD)
        return None

    @property
    def miot_cloud(self):
        isc = False
        if self.miot_local:
            isc = False
        elif self._config.get('miot_cloud'):
            isc = True
        elif self.custom_config_bool('miot_cloud'):
            isc = True
        if isc and self.miot_did:
            return self.xiaomi_cloud
        return None

    @property
    def miot_cloud_write(self):
        isc = False
        if self.custom_config_bool('miot_cloud_write'):
            isc = True
        if isc and self.hass and self.miot_did:
            return self.entry_config(CONF_XIAOMI_CLOUD)
        return self.miot_cloud

    @property
    def miot_cloud_action(self):
        isc = False
        if self.custom_config_bool('miot_cloud_action'):
            isc = True
        if isc and self.hass and self.miot_did:
            return self.entry_config(CONF_XIAOMI_CLOUD)
        return self.miot_cloud

    @property
    def miot_local(self):
        if self.custom_config_bool('miot_local'):
            return self.miot_device
        return None

    @property
    def miot_config(self):
        return self._config or {}

    @property
    def miot_mapping(self):
        mmp = None
        if self._miot_mapping:
            mmp = self._miot_mapping
        elif self._device and hasattr(self._device, 'mapping'):
            mmp = self._device.mapping

        exs = self._vars.get('exclude_services') or []
        if exs and mmp and self._miot_service:
            sls = self._miot_service.spec.get_services(*exs)
            sis = map(lambda x: x.iid, sls)
            if sis:
                mmp = {
                    k: v
                    for k, v in mmp.items()
                    if v.get('siid') not in sis
                }
        return mmp

    @property
    def entity_id_prefix(self):
        if not self._miot_service:
            return None
        return self._miot_service.spec.generate_entity_id(self)

    async def _try_command(self, mask_error, func, *args, **kwargs):
        result = None
        try:
            results = await self.hass.async_add_executor_job(partial(func, *args, **kwargs)) or []
            for result in results:
                break
            self.logger.debug('%s: Response received from miot: %s', self.name, result)
            if isinstance(result, dict):
                return dict(result or {}).get('code', 1) == self._success_code
            else:
                return result == self._success_result
        except DeviceException as exc:
            self.logger.error(mask_error, exc)
            self._available = False
        return False

    def send_miio_command(self, method, params=None, **kwargs):
        if self.miot_device:
            return super().send_miio_command(method, params, **kwargs)
        self.logger.error('%s: None local device for send miio command %s(%s)', self.name, method, params)

    async def async_update(self):
        if self._vars.get('delay_update'):
            await asyncio.sleep(self._vars.get('delay_update'))
            self._vars.pop('delay_update', 0)
        updater = 'none'
        results = None
        mapping = self.miot_mapping
        max_properties = 10
        try:
            if not mapping:
                results = []
            elif mic := self.miot_cloud:
                updater = 'cloud'
                results = await self.hass.async_add_executor_job(
                    partial(mic.get_properties_for_mapping, self.miot_did, mapping)
                )
                if self.custom_config_bool('check_lan'):
                    if self.miot_device:
                        await self.hass.async_add_executor_job(self.miot_device.info)
                    else:
                        self._available = False
                        return
            elif self.miot_device:
                updater = 'lan'
                if self._vars.get('has_local_mapping'):
                    mapping = self._device.mapping
                max_properties = self.custom_config_integer('chunk_properties') or max_properties
                results = await self.hass.async_add_executor_job(
                    partial(
                        self._device.get_properties_for_mapping,
                        max_properties=max_properties,
                        did=self.miot_did,
                        mapping=mapping,
                    )
                )
            else:
                self.logger.error('%s: Local device and miot cloud not ready.', self.name)
        except DeviceException as exc:
            self._available = False
            self.logger.error(
                '%s: Got MiioException while fetching the state: %s, mapping: %s, max_properties: %s',
                self.name, exc, mapping, max_properties,
            )
        except MiCloudException as exc:
            self._available = False
            self.logger.error(
                '%s: Got MiCloudException while fetching the state: %s, mapping: %s',
                self.name, exc, mapping,
            )
        result = MiotResults(results, mapping)
        if not result.is_valid:
            self._available = False
            if self._vars.get('track_miot_error') and updater == 'lan':
                await async_analytics_track_event(
                    self.hass, 'miot', 'error', self._model,
                    firmware=self.device_info.get('sw_version'),
                    results=results,
                )
                self._vars.pop('track_miot_error', None)
            if result.is_empty and results:
                self.logger.warning(
                    '%s: Got invalid miot result while fetching the state: %s, mapping: %s',
                    self.name, results, mapping,
                )
            return False
        attrs = result.to_attributes(self._state_attrs)
        attrs['state_updater'] = updater
        self._available = True
        self._state = True if self._state_attrs.get('power') else False

        if self._miot_service:
            for d in ['sensor', 'binary_sensor', 'switch', 'number', 'select', 'fan', 'cover']:
                pls = self.custom_config_list(f'{d}_properties') or []
                if pls:
                    self._update_sub_entities(pls, '*', domain=d)
            self._update_sub_entities(
                [
                    'temperature', 'indoor_temperature', 'relative_humidity', 'humidity',
                    'pm2_5_density', 'pm10_density', 'co2_density', 'tvoc_density', 'air_quality', 'air_quality_index',
                    'illumination', 'motion_state', 'motion_detection',
                ],
                ['environment', 'illumination_sensor', 'motion_detection'],
                domain='sensor',
            )
            self._update_sub_entities(
                [
                    'filter_life', 'filter_life_level', 'filter_left_time', 'filter_used_time',
                    'filter_left_flow', 'filter_used_flow',
                ],
                ['filter', 'filter_life'],
                domain='sensor',
            )
            self._update_sub_entities(
                [
                    'battery_level', 'ble_battery_level', 'charging_state', 'voltage', 'power_consumption',
                    'electric_current', 'leakage_current', 'surge_power', 'electric_power', 'elec_count',
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
            self._update_sub_entities(
                None,
                ['indicator_light', 'night_light', 'ambient_light', 'plant_light'],
                domain='light',
            )
        if self._subs:
            attrs['sub_entities'] = list(self._subs.keys())
        self.update_attrs(attrs)
        self.logger.debug('%s: Got new state: %s', self.name, attrs)

        # update miio prop/event in cloud
        if cls := self.custom_config_list('miio_cloud_records'):
            await self.hass.async_add_executor_job(partial(self.update_miio_cloud_records, cls))

        if pls := self.custom_config_list('miio_cloud_props'):
            await self.hass.async_add_executor_job(partial(self.update_miio_cloud_props, pls))

        # update micloud statistics in cloud
        if cls := self.custom_config_list('micloud_statistics'):
            await self.hass.async_add_executor_job(partial(self.update_micloud_statistics, cls))

        # update miio properties in lan
        if pls := self.custom_config_list('miio_properties'):
            await self.hass.async_add_executor_job(partial(self.update_miio_props, pls))

        # update miio commands in lan
        if cls := self.custom_config_json('sensor_miio_commands'):
            await self.hass.async_add_executor_job(partial(self.update_miio_command_sensors, cls))

    def update_miio_props(self, props):
        if not self.miot_device:
            return
        try:
            attrs = self._device.get_properties(props)
        except DeviceException as exc:
            self.logger.warning('%s: Got miio properties %s failed: %s', self.name, props, exc)
            return
        if len(props) != len(attrs):
            self.update_attrs({
                'miio.props': attrs,
            })
            return
        attrs = dict(zip(map(lambda x: f'miio.{x}', props), attrs))
        self.logger.debug('%s: Got miio properties: %s', self.name, attrs)
        self.update_attrs(attrs)

    def update_miio_command_sensors(self, commands):
        if not self.miot_device or not isinstance(commands, dict):
            return
        for cmd, cfg in commands.items():
            if isinstance(cfg, list):
                cfg = {'values': cfg}
            props = cfg.get('values') or []
            try:
                attrs = self._device.send(cmd, cfg.get('params') or [])
            except DeviceException as exc:
                self.logger.warning('%s: Send miio command %s(%s) failed: %s', self.name, cmd, cfg, exc)
                return
            if len(props) != len(attrs):
                attrs = {
                    f'miio.{cmd}': attrs,
                }
            else:
                attrs = dict(zip(props, attrs))
            self.logger.debug('%s: Got miio properties: %s', self.name, attrs)
            self.update_attrs(attrs)

    def update_miio_cloud_props(self, keys):
        did = str(self.miot_did)
        mic = self.xiaomi_cloud
        if not did or not mic:
            return
        kls = []
        for k in keys:
            if '.' not in k:
                k = f'prop.{k}'
            kls.append(k)
        pms = {
            'did': did,
            'props': kls,
        }
        rdt = mic.request_miot_api('device/batchdevicedatas', [pms]) or {}
        self.logger.debug('%s: Got miio cloud props: %s', self.name, rdt)
        props = (rdt.get('result') or {}).get(did, {})

        tpl = self.custom_config('miio_cloud_props_template')
        if tpl and props:
            tpl = CUSTOM_TEMPLATES.get(tpl, tpl)
            tpl = cv.template(tpl)
            tpl.hass = self.hass
            attrs = tpl.render({'props': props})
        else:
            attrs = props
        self.update_attrs(attrs)

    def update_miio_cloud_records(self, keys):
        did = self.miot_did
        mic = self.xiaomi_cloud
        if not did or not mic:
            return
        attrs = {}
        for c in keys:
            mat = re.match(r'^\s*(?:(\w+)\.?)(\w+)(?::(\d+))?(?::(\w+))?\s*$', c)
            if not mat:
                continue
            typ, key, lmt, gby = mat.groups()
            stm = int(time.time()) - 86400 * 32
            kws = {
                'time_start': stm,
                'limit': int(lmt or 1),
            }
            if gby:
                kws['group'] = gby
            rdt = mic.get_user_device_data(did, key, typ, **kws) or []
            tpl = self.custom_config(f'miio_{typ}_{key}_template')
            if tpl:
                tpl = CUSTOM_TEMPLATES.get(tpl, tpl)
                tpl = cv.template(tpl)
                tpl.hass = self.hass
                rls = tpl.render({'result': rdt})
            else:
                rls = [
                    v.get('value')
                    for v in rdt
                    if 'value' in v
                ]
            if isinstance(rls, dict) and rls.pop('_entity_attrs', False):
                attrs.update(rls)
            else:
                attrs[f'{typ}.{key}'] = rls
        if attrs:
            self.update_attrs(attrs)

    def update_micloud_statistics(self, lst):
        did = self.miot_did
        mic = self.xiaomi_cloud
        if not did or not mic:
            return
        now = int(time.time())
        attrs = {}
        for c in lst:
            if not c.get('key'):
                continue
            day = c.get('day') or 7
            pms = {
                'did': did,
                'key': c.get('key'),
                'data_type': c.get('type', 'stat_day_v3'),
                'time_start': now - 86400 * day,
                'time_end': now + 60,
                'limit': int(c.get('limit') or 1),
            }
            rdt = mic.request_miot_api('v2/user/statistics', pms) or {}
            self.logger.debug('%s: Got micloud statistics: %s', self.name, rdt)
            tpl = c.get('template')
            if tpl:
                tpl = CUSTOM_TEMPLATES.get(tpl, tpl)
                tpl = cv.template(tpl)
                tpl.hass = self.hass
                rls = tpl.render(rdt)
            else:
                rls = [
                    v.get('value')
                    for v in rdt
                    if 'value' in v
                ]
            if anm := c.get('attribute'):
                attrs[anm] = rls
            elif isinstance(rls, dict):
                attrs.update(rls)
        if attrs:
            self.update_attrs(attrs)

    def get_properties(self, mapping: dict, throw=True, **kwargs):
        results = []
        try:
            if self.miot_cloud:
                results = self.miot_cloud.get_properties_for_mapping(self.miot_did, mapping)
            elif self.miot_device:
                results = self.miot_device.get_properties_for_mapping(mapping=mapping)
        except (ValueError, DeviceException) as exc:
            self.logger.error(
                '%s: Got exception while get properties: %s, mapping: %s, miio: %s',
                self.name, exc, mapping, self._miio_info.data,
            )
            if throw:
                raise exc
            return
        attrs = {
            prop['did']: prop['value'] if prop['code'] == 0 else None
            for prop in results
        }
        self.logger.info('%s: Get miot properties: %s', self.name, results)
        if throw:
            persistent_notification.create(
                self.hass,
                f'{results}',
                'Miot properties',
                f'{DOMAIN}-debug',
            )
        return attrs

    async def async_get_properties(self, mapping, **kwargs):
        return await self.hass.async_add_executor_job(
            partial(self.get_properties, mapping, **kwargs)
        )

    def set_property(self, field, value):
        if isinstance(field, MiotProperty):
            siid = field.siid
            piid = field.iid
            field = field.full_name
        else:
            ext = self.miot_mapping.get(field) or {}
            if not ext:
                self.logger.warning('%s: Set miot property %s(%s) failed: property not found', self.name, field, value)
                return False
            siid = ext['siid']
            piid = ext['piid']
        try:
            result = self.set_miot_property(siid, piid, value)
        except (DeviceException, MiCloudException) as exc:
            self.logger.error('%s: Set miot property %s(%s) failed: %s', self.name, field, value, exc)
            return False
        ret = result.is_success if result else False
        if ret:
            if field in self._state_attrs:
                self.update_attrs({
                    field: value,
                }, update_parent=False)
            self.logger.debug('%s: Set miot property %s(%s), result: %s', self.name, field, value, result)
        else:
            self.logger.info('%s: Set miot property %s(%s) failed, result: %s', self.name, field, value, result)
        return ret

    async def async_set_property(self, *args, **kwargs):
        if not self.hass:
            self.logger.info('%s: Set miot property %s failed: hass not ready.', self.name, args)
            return False
        return await self.hass.async_add_executor_job(partial(self.set_property, *args, **kwargs))

    def set_miot_property(self, siid, piid, value, did=None, **kwargs):
        if did is None:
            did = self.miot_did or f'prop.{siid}.{piid}'
        pms = {
            'did':  str(did),
            'siid': siid,
            'piid': piid,
            'value': value,
        }
        ret = None
        dly = 1
        try:
            mcw = self.miot_cloud_write
            if isinstance(mcw, MiotCloud):
                results = mcw.set_props([pms])
                dly = self.custom_config_integer('cloud_delay_update', 5)
            else:
                results = self.miot_device.send('set_properties', [pms])
            ret = MiotResults(results).first
        except (DeviceException, MiCloudException) as exc:
            self.logger.warning('%s: Set miot property %s failed: %s', self.name, pms, exc)
        if ret:
            self._vars['delay_update'] = dly
            if not ret.is_success:
                self.logger.warning('%s: Set miot property %s failed, result: %s', self.name, pms, ret)
            else:
                self.logger.debug('%s: Set miot property %s, result: %s', self.name, pms, ret)
                if not self._miot_service:
                    pass
                elif not (srv := self._miot_service.spec.services.get(siid)):
                    pass
                elif prop := srv.properties.get(piid):
                    self._state_attrs[prop.full_name] = value
                    self.async_write_ha_state()
        if kwargs.get('throw'):
            persistent_notification.create(
                self.hass,
                f'{ret.result}',
                'Set miot property result',
                f'{DOMAIN}-debug',
            )
        return ret

    async def async_set_miot_property(self, siid, piid, value, did=None, **kwargs):
        return await self.hass.async_add_executor_job(
            partial(self.set_miot_property, siid, piid, value, did, **kwargs)
        )

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
        result = None
        dly = 1
        eno = 1
        try:
            mca = self.miot_cloud_action
            if isinstance(mca, MiotCloud):
                result = mca.do_action(pms)
                dly = self.custom_config_integer('cloud_delay_update', 5)
            else:
                result = self.miot_device.send('action', pms)
            eno = dict(result or {}).get('code', eno)
        except (DeviceException, MiCloudException) as exc:
            self.logger.warning('%s: Call miot action %s failed: %s', self.name, pms, exc)
        except (TypeError, ValueError) as exc:
            self.logger.warning('%s: Call miot action %s failed: %s, result: %s', self.name, pms, exc, result)
        ret = eno == self._success_code
        if ret:
            self._vars['delay_update'] = dly
            self.logger.debug('%s: Call miot action %s, result: %s', self.name, pms, result)
        else:
            self._state_attrs['miot_action_error'] = MiotSpec.spec_error(eno)
            self.logger.info('%s: Call miot action %s failed: %s', self.name, pms, result)
        self._state_attrs['miot_action_result'] = result
        if kwargs.get('throw'):
            persistent_notification.create(
                self.hass,
                f'{result}',
                'Miot action result',
                f'{DOMAIN}-debug',
            )
        return result if ret else ret

    async def async_miot_action(self, siid, aiid, params=None, did=None, **kwargs):
        return await self.hass.async_add_executor_job(
            partial(self.miot_action, siid, aiid, params, did, **kwargs)
        )

    def turn_on(self, **kwargs):
        ret = False
        if hasattr(self, '_prop_power'):
            ret = self.set_property(self._prop_power, True)
            if ret:
                self._state = True
        return ret

    def turn_off(self, **kwargs):
        ret = False
        if hasattr(self, '_prop_power'):
            ret = self.set_property(self._prop_power, False)
            if ret:
                self._state = False
        return ret

    def _update_sub_entities(self, properties, services=None, domain=None, option=None):
        from .sensor import MiotSensorSubEntity
        from .binary_sensor import MiotBinarySensorSubEntity
        from .switch import MiotSwitchSubEntity
        from .switch import MiotSwitchActionSubEntity
        from .light import MiotLightSubEntity
        from .fan import MiotModesSubEntity
        from .cover import MiotCoverSubEntity
        from .number import MiotNumberSubEntity
        if isinstance(services, MiotService):
            sls = [services]
        elif services == '*':
            sls = list(self._miot_service.spec.services.values())
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
        add_selects = self._add_entities.get('select')
        exclude_services = self._vars.get('exclude_services') or []
        for s in sls:
            if s.name in exclude_services:
                continue
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
                        self.logger.info('%s: Device sub entity %s: %s already exists.', self.name, domain, fnm)
                elif add_lights and domain == 'light':
                    pon = s.get_property('on')
                    if pon and pon.full_name in self._state_attrs:
                        self._subs[fnm] = MiotLightSubEntity(self, s)
                        add_lights([self._subs[fnm]])
                if new and fnm in self._subs:
                    self._check_same_sub_entity(fnm, domain, add=1)
                    self.logger.debug('%s: Added sub entity %s: %s', self.name, domain, fnm)
                continue
            pls = s.get_properties(*cv.ensure_list(properties))
            for p in pls:
                fnm = p.unique_name
                opt = {
                    'unique_id': f'{self.unique_did}-{fnm}',
                    **(option or {}),
                }
                tms = self._check_same_sub_entity(fnm, domain)
                new = True
                if fnm in self._subs:
                    new = False
                    self._subs[fnm].update()
                    self._check_same_sub_entity(fnm, domain, add=1)
                elif tms > 0:
                    if tms <= 1:
                        self.logger.info('%s: Device sub entity %s: %s already exists.', self.name, domain, fnm)
                elif p.full_name not in self._state_attrs:
                    if add_switches and p.name in ['feeding_measure']:
                        act = s.get_action('pet_food_out')
                        if not act:
                            continue
                        self._subs[fnm] = MiotSwitchActionSubEntity(self, p, act, option=opt)
                        add_switches([self._subs[fnm]])
                    continue
                elif add_switches and domain == 'switch' and p.format == 'bool' and p.writeable:
                    self._subs[fnm] = MiotSwitchSubEntity(self, p, option=opt)
                    add_switches([self._subs[fnm]])
                elif add_binary_sensors and domain == 'binary_sensor' and p.format == 'bool':
                    self._subs[fnm] = MiotBinarySensorSubEntity(self, p, option=opt)
                    add_binary_sensors([self._subs[fnm]])
                elif add_sensors and domain == 'sensor':
                    if p.full_name == self._state_attrs.get('state_property'):
                        continue
                    self._subs[fnm] = MiotSensorSubEntity(self, p, option=opt)
                    add_sensors([self._subs[fnm]])
                elif add_fans and domain == 'fan':
                    self._subs[fnm] = MiotModesSubEntity(self, p, option=opt)
                    add_fans([self._subs[fnm]])
                elif add_covers and domain == 'cover':
                    self._subs[fnm] = MiotCoverSubEntity(self, p, option=opt)
                    add_covers([self._subs[fnm]])
                elif add_numbers and domain == 'number':
                    self._subs[fnm] = MiotNumberSubEntity(self, p, option=opt)
                    add_numbers([self._subs[fnm]])
                elif add_selects and domain == 'select' and (p.value_list or p.value_range):
                    from .select import MiotSelectSubEntity
                    self._subs[fnm] = MiotSelectSubEntity(self, p, option=opt)
                    add_selects([self._subs[fnm]])
                if new and fnm in self._subs:
                    self._check_same_sub_entity(fnm, domain, add=1)
                    self.logger.debug('%s: Added sub entity %s: %s', self.name, domain, fnm)

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
            f'Xiaomi device data: {self.name}',
            f'{DOMAIN}-debug',
        )
        if throw:
            raise Warning(f'Xiaomi device data for {self.name}: {result}')
        else:
            _LOGGER.debug('%s: Xiaomi device data: %s', self.name, result)
        return result

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
            f'Xiaomi device bindkey: {self.name}',
            f'{DOMAIN}-debug',
        )
        if throw:
            raise Warning(f'Xiaomi device bindkey for {self.name}: {result}')
        else:
            _LOGGER.warning('%s: Xiaomi device bindkey/beaconkey: %s', self.name, result)
        return (result or {}).get('beaconkey')

    async def async_request_xiaomi_api(self, api, data=None, method='POST', crypt=False, **kwargs):
        mic = self.miot_cloud
        if not isinstance(mic, MiotCloud):
            return None
        dat = data or kwargs.get('params')
        fun = partial(mic.request_miot_api, api, data=dat, method=method, crypt=crypt)
        result = await self.hass.async_add_executor_job(fun)
        persistent_notification.async_create(
            self.hass,
            f'{result}',
            f'Xiaomi Api: {api}',
            f'{DOMAIN}-debug',
        )
        if kwargs.get('throw'):
            raise Warning(f'Xiaomi Api {api}: {result}')
        else:
            _LOGGER.debug('Xiaomi Api %s: %s', api, result)
        return result


class MiotToggleEntity(MiotEntity, ToggleEntity):
    def __init__(self, miot_service=None, device=None, **kwargs):
        super().__init__(miot_service, device, **kwargs)
        self._prop_power = None
        if miot_service:
            self._prop_power = miot_service.bool_property('on', 'power', 'switch')

    @property
    def is_on(self):
        if self._prop_power:
            return not not self._state_attrs.get(self._prop_power.full_name)
        return None

    def turn_on(self, **kwargs):
        if self._prop_power:
            return self.set_property(self._prop_power, True)
        return False

    def turn_off(self, **kwargs):
        if self._prop_power:
            return self.set_property(self._prop_power, False)
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
        self._model = parent.device_info.get('model', '')
        self._option = dict(option or {})
        self._dict_key = self._option.get('dict_key')
        if self._dict_key:
            self._unique_id = f'{self._unique_id}-{self._dict_key}'
            self._name = f'{self._name} {self._dict_key}'
        if self._option.get('unique_id'):
            self._unique_id = self._option.get('unique_id')
        if self._option.get('name'):
            self._name = self._option.get('name')
        if self._option.get('entity_id'):
            self.entity_id = self._option.get('entity_id')
            if '.' not in self.entity_id:
                self.entity_id = f'{DOMAIN}.{self.entity_id}'
        elif hasattr(parent, 'entity_id_prefix'):
            eip = getattr(parent, 'entity_id_prefix')
            if eip:
                suf = attr
                if self._dict_key:
                    suf = f'{suf}_{self._dict_key}'
                self.entity_id = f'{eip}_{suf}'
        self._supported_features = int(self._option.get('supported_features', 0))
        self._extra_attrs = {
            'entity_class': self.__class__.__name__,
            'parent_entity_id': parent.entity_id,
        }
        self._state_attrs = {}
        self._parent_attrs = {}

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def unique_mac(self):
        return self._parent.unique_mac

    @property
    def name(self):
        return self._name

    def format_name_by_property(self, prop: MiotProperty):
        dnm = self._parent.device_name
        return f'{dnm} {prop.friendly_desc}'.strip()

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
    def parent_attributes(self):
        return self._parent.extra_state_attributes or {}

    @property
    def extra_state_attributes(self):
        return {
            **self._extra_attrs,
            **self._state_attrs,
        }

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
        
    @property
    def state_class(self):
        return self._option.get('state_class')
        
    @property
    def miot_cloud(self):
        mic = self._parent.miot_cloud
        if not isinstance(mic, MiotCloud):
            raise RuntimeError('The parent entity of %s does not have Mi Cloud.', self.name)
        return mic

    def custom_config(self, key=None, default=None):
        ret = super().custom_config(key)
        if key is not None:
            if ret is not None:
                return ret
            cfg = {}
        else:
            cfg = ret or {}
        if self._model:
            mar = []
            for mod in self.wildcard_models:
                if self._dict_key:
                    mar.append(f'{mod}:{self._attr}:{self._dict_key}')
                else:
                    mar.append(f'{mod}:{self._attr}')
                if hasattr(self, '_miot_property'):
                    prop = getattr(self, '_miot_property')
                    if prop:
                        mar.append(f'{mod}:{prop.name}')
            gcs = GLOBAL_CUSTOMIZES['models']
            ucs = self.global_config('device_customizes') or {}
            if ucs and isinstance(ucs, dict):
                gcs.update(ucs)
            for m in mar:
                cus = gcs.get(m) or {}
                if key is not None and key not in cus:
                    continue
                if cus:
                    cfg = {**cus, **cfg}
        return cfg if key is None else cfg.get(key, default)

    async def async_added_to_hass(self):
        if self.platform:
            self.update_custom_scan_interval(only_custom=True)
        self._option['icon'] = self.custom_config('icon', self.icon)
        self._option['unit'] = self.custom_config('unit_of_measurement', self.unit_of_measurement)
        if not self.device_class:
            self._option['device_class'] = self.custom_config('device_class')

    def update(self, data=None):
        attrs = self.parent_attributes
        self._parent_attrs = attrs
        if self._attr in attrs:
            self._available = True
            self._state = attrs.get(self._attr)
            if self._dict_key and isinstance(self._state, dict):
                self._state = self._state.get(self._dict_key)
            svd = self.custom_config_number('value_ratio') or 0
            if svd:
                self._state = round(float(self._state) * svd, 3)
            keys = self._option.get('keys', [])
            if isinstance(keys, list):
                keys.append(self._attr)
            self._state_attrs = {}.update(attrs) if keys is True else {
                k: v
                for k, v in attrs.items()
                if k in keys
            }
        if data:
            self.update_attrs(data, update_parent=False)

    async def async_update(self):
        await self.hass.async_add_executor_job(self.update)

    def update_attrs(self, attrs: dict, update_parent=True):
        self._state_attrs.update(attrs or {})
        if update_parent:
            if self._parent and hasattr(self._parent, 'update_attrs'):
                getattr(self._parent, 'update_attrs')(attrs or {}, update_parent=False)
        if self.hass:
            self.async_write_ha_state()
        return self._state_attrs

    def call_parent(self, method, *args, **kwargs):
        ret = None
        for f in cv.ensure_list(method):
            if hasattr(self._parent, f):
                ret = getattr(self._parent, f)(*args, **kwargs)
                break
            _LOGGER.info('%s: Parent entity has no method: %s', self.name, f)
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


class MiotPropertySubEntity(BaseSubEntity):
    def __init__(self, parent, miot_property: MiotProperty, option=None):
        self._miot_service = miot_property.service
        self._miot_property = miot_property
        super().__init__(parent, miot_property.full_name, option)

        if not self._option.get('name'):
            self._name = self.format_name_by_property(miot_property)
        if not self._option.get('unique_id'):
            self._unique_id = f'{parent.unique_did}-{miot_property.unique_name}'
        self.entity_id = miot_property.generate_entity_id(self)
        if 'state_class' not in self._option:
            self._option['state_class'] = miot_property.state_class
        if 'icon' not in self._option:
            self._option['icon'] = miot_property.entity_icon
        if 'unit' not in self._option:
            self._option['unit'] = miot_property.unit_of_measurement
        if 'device_class' not in self._option:
            self._option['device_class'] = miot_property.device_class
        self._extra_attrs.update({
            'service_description': miot_property.service.description,
            'property_description': miot_property.description,
        })

    def set_parent_property(self, val, prop=None):
        if prop is None:
            prop = self._miot_property
        ret = self.call_parent('set_miot_property', prop.service.iid, prop.iid, val)
        if ret and prop.readable:
            self.update_attrs({
                prop.full_name: val,
            })
        return ret


class ToggleSubEntity(BaseSubEntity, ToggleEntity):
    def __init__(self, parent, attr='power', option=None):
        self._prop_power = None
        super().__init__(parent, attr, option)

    def update(self, data=None):
        super().update(data)
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
