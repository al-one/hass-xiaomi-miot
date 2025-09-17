"""Support for Xiaomi Miot."""
import logging
import asyncio
import json
import os
import re
from datetime import timedelta
import voluptuous as vol

from homeassistant import (
    core as hass_core,
    config_entries,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_HOST,
    CONF_NAME,
    CONF_DEVICE,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    CONF_USERNAME,
    STATE_UNKNOWN,
    SERVICE_RELOAD,
)
from homeassistant.helpers.entity import ToggleEntity, EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.reload import async_integration_yaml_config
from homeassistant.helpers.service import async_register_admin_service
import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.config_validation as cv

from .core.const import *
from .core.utils import DeviceException, wildcard_models
from .core import HassEntry, BasicEntity, XEntity # noqa
from .core.device import Device, AsyncMiIO
from .core.miot_spec import (
    MiotService,
    MiotProperty,
    MiotResult,
    MiotResults,
)
from .core.xiaomi_cloud import (
    MiotCloud,
    MiCloudException,
    MiCloudAccessDenied,
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
        'method': 'async_miio_command',
        'schema': XIAOMI_MIIO_SERVICE_SCHEMA.extend(
            {
                vol.Required('method'): cv.string,
                vol.Optional('params', default=[]): cv.ensure_list,
                vol.Optional('throw', default=False): cv.boolean,  # Deprecated
                vol.Optional('return_result', default=True): cv.boolean,
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
                vol.Required('mapping'): vol.Any(dict, list),
                vol.Optional('update_entity', default=False): cv.boolean,
                vol.Optional('throw', default=False): cv.boolean,
            },
        ),
    },
    'call_action': {
        'method': 'async_call_action',
        'schema': XIAOMI_MIIO_SERVICE_SCHEMA.extend(
            {
                vol.Required('siid'): int,
                vol.Required('aiid'): int,
                vol.Optional('did'): cv.string,
                vol.Optional('params', default=[]): cv.ensure_list,
                vol.Optional('force_params', default=False): cv.boolean,
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
                vol.Optional('method', default='POST'): cv.string,
                vol.Optional('crypt', default=True): cv.boolean,
                vol.Optional('sid', default=None): vol.Any(cv.string, None),
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
    init_integration_data(hass)
    config = hass_config.get(DOMAIN) or {}
    await async_reload_integration_config(hass, config)

    def extend_miot_specs():
        with open(os.path.dirname(__file__) + '/core/miot_specs_extend.json') as file:
            try:
                models = json.load(file) or {}
            except ValueError as exc:
                models = {}
                _LOGGER.exception('Error parsing miot_specs_extend.json: %s', exc)
            for m, specs in models.items():
                DEVICE_CUSTOMIZES.setdefault(m, {})
                DEVICE_CUSTOMIZES[m]['extend_miot_specs'] = specs

    await hass.async_add_executor_job(extend_miot_specs)

    component = EntityComponent(_LOGGER, DOMAIN, hass, SCAN_INTERVAL)
    hass.data[DOMAIN]['component'] = component
    await component.async_setup(config)
    await async_setup_component_services(hass)
    bind_services_to_entries(hass, SERVICE_TO_METHOD_BASE)

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
            hass.data[DOMAIN]['accounts'].setdefault(mic.user_id, {CONF_XIAOMI_CLOUD: mic})
            cnt = len(hass.data[DOMAIN]['devices_by_mac'])
            _LOGGER.debug('Setup xiaomi cloud for user: %s, %s devices', config.get(CONF_USERNAME), cnt)
        except (MiCloudException, MiCloudAccessDenied) as exc:
            _LOGGER.warning('Setup xiaomi cloud for user: %s failed: %s', config.get(CONF_USERNAME), exc)

    await _handle_device_registry_event(hass)
    return True


async def async_setup_entry(hass: hass_core.HomeAssistant, config_entry: config_entries.ConfigEntry):
    hass.data.setdefault(DOMAIN, {})
    entry_id = config_entry.entry_id

    if config_entry.data.get('customizing_entity') or config_entry.data.get('customizing_device'):
        await async_setup_customizes(hass, config_entry)
    elif config_entry.data.get(CONF_USERNAME):
        await async_setup_xiaomi_cloud(hass, config_entry)
    else:
        entry = HassEntry.init(hass, config_entry)
        config = {**entry.get_config()}
        device = await entry.new_device(config)
        config[CONF_DEVICE] = device
        config[CONF_MODEL] = device.model
        config['miot_type'] = await device.get_urn()
        config['config_entry'] = config_entry
        config['miot_local'] = True
        config[CONF_CONN_MODE] = 'local'
        hass.data[DOMAIN][entry_id] = config
        _LOGGER.debug('Xiaomi Miot setup config entry: %s', {
            'entry_id': entry_id,
            'config': config,
        })

    if not config_entry.update_listeners:
        config_entry.add_update_listener(async_update_options)

    await hass.config_entries.async_forward_entry_setups(config_entry, SUPPORTED_DOMAINS)
    return True


async def async_setup_xiaomi_cloud(hass: hass_core.HomeAssistant, config_entry: config_entries.ConfigEntry):
    entry_id = config_entry.entry_id
    entry = HassEntry.init(hass, config_entry)
    entry_config = entry.get_config()
    username = entry_config.get(CONF_USERNAME)
    config = {
        'entry_id': entry_id,
        'config_entry': config_entry,
        'configs': [],
    }
    try:
        cloud = await entry.get_cloud(check=True)
        config[CONF_XIAOMI_CLOUD] = cloud
        devices = await entry.get_cloud_devices()
    except (MiCloudException, MiCloudAccessDenied) as exc:
        _LOGGER.error('Setup xiaomi cloud for user: %s failed: %s', username, exc)
        return False
    if not devices:
        _LOGGER.warning('None device in xiaomi cloud: %s', username)
    else:
        _LOGGER.debug('Setup xiaomi cloud for user: %s, %s devices', username, len(devices))
    for d in devices.values():
        device = await entry.new_device(d)
        if not device.spec:
            _LOGGER.warning('%s: Device has no spec %s', device.name_model, device.info.urn)
            continue
        conn = device.conn_mode
        cfg = {
            CONF_DEVICE: device,
            CONF_NAME: device.name,
            CONF_HOST: device.info.host,
            CONF_TOKEN: device.info.token,
            CONF_MODEL: device.info.model,
            'miot_did': device.info.did,
            'miot_type': await device.get_urn(),
            'miio_info': device.info.miio_info,
            CONF_CONN_MODE: conn,
            'miot_local': conn == 'local',
            'miot_cloud': conn != 'local',
            'home_name': device.info.home_name,
            'room_name': device.info.room_name,
            'entry_id': entry_id,
            CONF_CONFIG_VERSION: entry_config.get(CONF_CONFIG_VERSION) or 0,
        }
        if conn == 'auto' and device.info.model in MIOT_LOCAL_MODELS:
            cfg['miot_local'] = True
            cfg['miot_cloud'] = False
        config['configs'].append(cfg)
        _LOGGER.debug('Xiaomi cloud device: %s', {**cfg, CONF_TOKEN: '****'})
    hass.data[DOMAIN][entry_id] = config
    hass.data[DOMAIN]['accounts'].setdefault(cloud.user_id, {CONF_XIAOMI_CLOUD: cloud})
    return True


async def async_setup_customizes(hass: hass_core.HomeAssistant, config_entry: config_entries.ConfigEntry):
    entry_data = {**config_entry.data, **config_entry.options}
    if cus := entry_data.get('customizing_entity'):
        hass.data[DOMAIN][DATA_CUSTOMIZE] = cus
    if cus := entry_data.get('customizing_device'):
        for m, cfg in cus.items():
            if not isinstance(cfg, dict):
                continue
            DEVICE_CUSTOMIZES.setdefault(m, {})
            DEVICE_CUSTOMIZES[m].update(cfg)
    if entry_data:
        _LOGGER.info('Customizing via config flow: %s', entry_data)


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
    unload_ok = await HassEntry.init(hass, config_entry).async_unload()
    if unload_ok:
        hass.data[DOMAIN].pop(config_entry.entry_id, None)
        hass.data[DOMAIN]['sub_entities'] = {}
    return unload_ok


def init_integration_data(hass):
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault('entries', {})
    hass.data[DOMAIN].setdefault('configs', {})
    hass.data[DOMAIN].setdefault('entities', {})
    hass.data[DOMAIN].setdefault('accounts', {})
    hass.data[DOMAIN].setdefault('sessions', {})
    hass.data[DOMAIN].setdefault('miot_specs', {})
    hass.data[DOMAIN].setdefault('add_entities', {})
    hass.data[DOMAIN].setdefault('sub_entities', {})


def bind_services_to_entries(hass, services):
    async def async_service_handler(service) -> ServiceResponse:
        result = None
        method = services.get(service.service)
        fun = method['method']
        params = {
            key: value
            for key, value in service.data.items()
            if key != ATTR_ENTITY_ID
        }
        target_entities = []
        entity_ids = service.data.get(ATTR_ENTITY_ID)
        if entity_ids:
            target_entities = [
                hass.data[DOMAIN]['entities'][eid]
                for eid in entity_ids
                if eid in hass.data[DOMAIN].get('entities', {})
            ]
        if not target_entities:
            _LOGGER.warning('Call service failed: Entities not found for %s', entity_ids)
        else:
            _LOGGER.debug('Xiaomi Miot service handler: %s', {
                'targets': [ent.entity_id for ent in target_entities],
                'method': fun,
                'params': params,
            })
        update_tasks = []
        for ent in target_entities:
            if hasattr(ent, 'parent_entity'):
                ent = getattr(ent, 'parent_entity') or ent
            if not hasattr(ent, fun):
                _LOGGER.warning('Call service failed: Entity %s have no method: %s', ent.entity_id, fun)
                continue
            try:
                result = await getattr(ent, fun)(**params)
                update_tasks.append(ent.async_update_ha_state(True))
            except Exception as exc:
                result = {'error': str(exc)}
        if update_tasks:
            await asyncio.gather(*update_tasks)
        if isinstance(result, (MiotResult, MiotResults)):
            result = result.to_json()
        if not isinstance(result, dict):
            result = {'result': result}
        return result

    for srv, obj in services.items():
        kws = {
            'schema': obj.get('schema', XIAOMI_MIIO_SERVICE_SCHEMA),
        }
        if SupportsResponse:
            kws['supports_response'] = SupportsResponse.OPTIONAL
        hass.services.async_register(DOMAIN, srv, async_service_handler, **kws)


async def async_reload_integration_config(hass, config):
    hass.data[DOMAIN]['config'] = config

    if lang := config.get('language'):
        dic = TRANSLATION_LANGUAGES.get(lang)
        if isinstance(dic, dict):
            TRANSLATION_LANGUAGES.update(dic)
    dic = config.get('translations') or {}
    if dic and isinstance(dic, dict):
        TRANSLATION_LANGUAGES.update(dic)

    dcs = config.get('device_customizes')
    if dcs and isinstance(dcs, dict):
        for m, cus in dcs.items():
            if not isinstance(cus, dict):
                continue
            DEVICE_CUSTOMIZES.setdefault(m, {})
            DEVICE_CUSTOMIZES[m].update(cus)
    return config


async def async_setup_component_services(hass):

    async def async_get_token(call) -> ServiceResponse:
        nam = call.data.get('name')
        kwd = f'{nam}'.strip().lower()
        cnt = 0
        lst = []
        dls = {}
        beaconkey = miio_info = None
        for cld in MiotCloud.all_clouds(hass):
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
                tok = d.get('token') or ''
                if kwd in [did, dip] or kwd in dnm.lower() or kwd in dmd:
                    row = {
                        'did': did,
                        CONF_NAME: dnm,
                        CONF_HOST: dip,
                        CONF_MODEL: dmd,
                        CONF_TOKEN: tok,
                    }
                    if not beaconkey and 'blt.' in did:
                        beaconkey = await cld.async_get_beaconkey(did)
                        row['beaconkey'] = (beaconkey or {}).get('beaconkey', beaconkey)
                        row.pop(CONF_TOKEN, None)
                    elif dip and tok:
                        row['miio_cmd'] = f'miiocli device --ip {dip} --token {tok} info'
                        if not miio_info:
                            try:
                                miio = AsyncMiIO(dip, tok)
                                miio_info = await miio.info()
                            except Exception as exc:
                                miio_info = {'error': str(exc)}
                            row['miio_info'] = miio_info
                    lst.append(row)
                dls[did] = 1
                cnt += 1
        if not lst:
            lst = [f'Not Found "{nam}" in {cnt} devices.']
        return {
            'list': lst,
        }

    kws = {
        'schema': XIAOMI_MIIO_SERVICE_SCHEMA.extend({
            vol.Required('name', default=''): cv.string,
        }),
    }
    if SupportsResponse:
        kws['supports_response'] = SupportsResponse.OPTIONAL,
    hass.services.async_register(
        DOMAIN, 'get_token', async_get_token, **kws,
    )

    async def async_renew_devices(call):
        nam = call.data.get('username')
        for cld in MiotCloud.all_clouds(hass):
            if nam and str(nam) not in [cld.user_id, cld.username]:
                continue
            dvs = await cld.async_renew_devices()
            cnt = len(dvs)
            _LOGGER.info('Renew xiaomi devices for %s. Got %s devices.', cld.username, cnt)
        return True

    hass.services.async_register(
        DOMAIN, 'renew_devices', async_renew_devices,
        schema=vol.Schema({
            vol.Optional('username', default=''): cv.string,
        }),
    )

    async def _handle_reload_config(service):
        config = await async_integration_yaml_config(hass, DOMAIN)
        if not config or DOMAIN not in config:
            return
        await async_reload_integration_config(hass, config.get(DOMAIN) or {})
        current_entries = hass.config_entries.async_entries(DOMAIN)
        reload_tasks = [
            hass.config_entries.async_reload(entry.entry_id)
            for entry in current_entries
        ]
        await asyncio.gather(*reload_tasks)

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_RELOAD,
        _handle_reload_config,
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
        action = event.data['action']
        registry = dr.async_get(hass)
        device_id = event.data.get('device_id')
        if device_id not in registry.devices:
            return
        device = registry.async_get(device_id)
        if not device or not device.identifiers:
            return
        identifier = next(iter(device.identifiers))
        if identifier[0] != DOMAIN:
            return
        miot_device = None
        for entry_id in device.config_entries:
            entry = HassEntry.ALL.get(entry_id)
            if not entry:
                continue
            for d in entry.devices.values():
                if d.identifiers == device.identifiers:
                    miot_device = d
                    break
        if action == 'update' and device.name_by_user in ['delete', 'remove', '删除']:
            # remove from Hass
            if miot_device:
                await miot_device.async_unload()
            registry.async_remove_device(device.id)
            return
        if not miot_device:
            return
        miot_device.log.info('Device registry updated: %s', [action, identifier, device.disabled])
        if device.disabled and miot_device.coordinators:
            await miot_device.async_unload()
        if not device.disabled and not miot_device.coordinators:
            await miot_device.init_coordinators()
    hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, updated)


async def async_remove_config_entry_device(hass: hass_core.HomeAssistant, config_entry: ConfigEntry, device: dr.DeviceEntry):
    """Supported from Hass v2022.3"""
    entry = HassEntry.init(hass, config_entry)
    cloud_device = None
    identifier = next(iter(device.identifiers))
    if len(identifier) >= 2 and identifier[0] == DOMAIN:
        mac = identifier[1].split('-')[0]
        if mac:
            cloud_device = await entry.get_cloud_device(mac=mac.upper())
    data = {**entry.entry.data}
    for typ in (['did'] if cloud_device else []):
        filter_typ = data.get(f'filter_{typ}')
        filter_val = cloud_device.get(typ)
        if not filter_val or not filter_typ:
            continue
        lst = data.get(f'{typ}_list') or []
        if filter_typ == 'exclude':
            lst = list({*lst, filter_val})
        else:
            lst = list({*lst}.difference({filter_val}))
        data[f'{typ}_list'] = lst
        hass.config_entries.async_update_entry(config_entry, data=data)
        _LOGGER.info('Remove miot device: %s', cloud_device)

    dr.async_get(hass).async_remove_device(device.id)
    return True


class BaseEntity(BasicEntity):
    device: Device = None
    _config = None
    _model = None
    _unique_did = None
    _attr_device_class = None
    _attr_entity_category = None
    _attr_translation_key = None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if self.hass:
            self.hass.data[DOMAIN]['entities'][self.entity_id] = self

    @property
    def entity_category(self):
        cat = super().entity_category
        if isinstance(cat, EntityCategory):
            return cat
        if isinstance(cat, str) and cat in EntityCategory:
            return EntityCategory(cat)
        return None

    def get_device_class(self, enum):
        cls = self._attr_device_class
        if isinstance(cls, enum):
            return cls
        if isinstance(cls, str) and cls in enum:
            return enum(cls)
        return None

    @property
    def model(self):
        if self.device:
            return self.device.info.model
        return self._model

    @property
    def name_model(self):
        return f'{self.name}({self.model})'

    def global_config(self, key=None, default=None):
        if not self.hass:
            return default
        cfg = self.hass.data[DOMAIN]['config'] or {}
        return cfg if key is None else cfg.get(key, default)

    @property
    def conn_mode(self):
        return self._config.get(CONF_CONN_MODE)

    @property
    def local_only(self):
        return self.conn_mode == 'local'

    @property
    def cloud_only(self):
        return self.conn_mode == 'cloud'

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
            if hasattr(self.platform, 'scan_interval_seconds'):
                self.platform.scan_interval_seconds = tim.total_seconds()            
            _LOGGER.debug('%s: Update custom scan interval: %s', self.name_model, tim)

    def update_custom_parallel_updates(self):
        if not self.hass:
            return False
        if not hasattr(self, '_unique_did'):
            return False
        num = self.custom_config_integer('parallel_updates', 0)
        if not num:
            return False
        did = self._unique_did
        self.hass.data[DOMAIN].setdefault(did, {})
        dcs = self.hass.data[DOMAIN].get(did, {})
        pus = dcs.get('parallel_updates')
        if not pus:
            pus = asyncio.Semaphore(num)
            self.hass.data[DOMAIN][did]['parallel_updates'] = pus
            _LOGGER.debug('%s: Update custom parallel updates: %s', self.name_model, num)
        self.parallel_updates = pus
        return pus

    def filter_state_attributes(self, dat: dict):
        if exl := self.global_config('exclude_state_attributes'):
            exl = cv.ensure_list(exl)
            dat = {
                k: v
                for k, v in dat.items()
                if k not in exl
            }
        return dat


class MiCoordinatorEntity(CoordinatorEntity, BaseEntity):
    async def async_added_to_hass(self):
        await super().async_added_to_hass()


class MiioEntity(BaseEntity):
    def __init__(self, name, device, **kwargs):
        self._device = device
        self._config = dict(kwargs.get('config') or {})
        self.device = self._config.get(CONF_DEVICE)
        self.hass = self.device.hass
        self.log = self.device.log
        self.logger = self.device.log
        self._miio_info = self.device.info.miio_info
        self._unique_did = self.unique_did
        self._unique_id = self._unique_did
        self._name = name
        self._model = self.device.info.model
        self._state = None
        self._available = False
        self._state_attrs = {}
        self._attr_device_info = self.device.hass_device_info
        self._supported_features = 0
        self._props = []
        self._success_result = ['ok']
        self._add_entities = {}
        self._vars = {}
        self._subs = {}

        self._vars['is_main_entity'] = not self.device.miot_entity
        self.device.miot_entity = self

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def unique_mac(self):
        mac = self.device.info.mac
        if not mac:
            mac = self.device.info.did
        return mac

    @property
    def unique_did(self):
        return self.device.unique_id

    @property
    def name(self):
        return self._name

    @property
    def name_model(self):
        return self.device.name_model

    @property
    def device_name(self):
        return self.device.name

    @property
    def device_host(self):
        return self.device.info.host

    @property
    def available(self):
        return self._available

    @property
    def is_on(self):
        return self._state

    @property
    def state_attrs(self):
        return self._state_attrs

    @property
    def extra_state_attributes(self):
        ext = self.state_attributes or {}
        esa = {**self._state_attrs, **ext}
        return self.filter_state_attributes(esa)

    @property
    def supported_features(self):
        return self._supported_features

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if self.platform:
            self.update_custom_scan_interval()
            self.update_custom_parallel_updates()
            if self.platform.config_entry:
                eid = self.platform.config_entry.entry_id
                self._add_entities = self.hass.data[DOMAIN][eid].get('add_entities') or {}

    async def async_miio_command(self, method, params=None, **kwargs):
        return await self.device.local.async_send(method, params, **kwargs)

    async def async_update(self):
        if not self._props:
            return
        try:
            attrs = await self.device.local.async_get_prop(self._props)
        except DeviceException as ex:
            self._available = False
            self.logger.error('%s: Got exception while fetching the state %s: %s', self.name_model, self._props, ex)
            return
        attrs = dict(zip(self._props, attrs))
        self.logger.debug('%s: Got new state: %s', self.name_model, attrs)
        self._available = True
        self._state = attrs.get('power') == 'on'
        await self.async_update_attrs(attrs)

    def update_attrs(self, attrs: dict, update_parent=False):
        self._state_attrs.update(attrs or {})
        if update_parent and hasattr(self, '_parent'):
            if self._parent and hasattr(self._parent, 'update_attrs'):
                getattr(self._parent, 'update_attrs')(attrs or {}, update_parent=False)
        return self._state_attrs

    async def async_update_attrs(self, attrs: dict, update_subs=True):
        self._state_attrs.update(attrs or {})
        if update_subs:
            if self.hass and self.platform:
                tps = cv.ensure_list(self.custom_config('attributes_template'))
                for tpl in tps:
                    if not tpl:
                        continue
                    tpl = CUSTOM_TEMPLATES.get(tpl, tpl)
                    tpl = cv.template(tpl)
                    tpl.hass = self.hass
                    adt = tpl.async_render({'data': self._state_attrs}) or {}
                    if isinstance(adt, dict):
                        if adt.pop('_override', False):
                            self._state_attrs = adt
                        else:
                            self._state_attrs.update(adt)
        return self._state_attrs


class MiotEntityInterface:
    _miot_service = None
    _model = ''
    _state_attrs: dict
    _supported_features = 0

    def update_attrs(self, *args, **kwargs):
        raise NotImplementedError()


class MiotEntity(MiioEntity):
    def __init__(self, miot_service=None, device=None, **kwargs):
        self._config = dict(kwargs.get('config') or {})
        name = kwargs.get(CONF_NAME) or self._config.get(CONF_NAME) or ''
        self._miot_service = miot_service if isinstance(miot_service, MiotService) else None
        if self._miot_service:
            name = f'{name} {self._miot_service.friendly_desc}'.strip()
            kwargs['miot_service'] = self._miot_service
        super().__init__(name, device, **kwargs)

        self._local_state = None
        self._miio2miot = self.device.miio2miot
        self._miot_mapping = dict(kwargs.get('mapping') or {})
        if self._miot_service:
            if not self._miot_mapping:
                self._miot_mapping = miot_service.mapping(
                    excludes=self.device._exclude_miot_properties,
                    unreadable_properties=self.device._unreadable_properties,
                ) or {}
            self._unique_id = f'{self._unique_id}-{self._miot_service.iid}'
            self.entity_id = self._miot_service.generate_entity_id(self)
            self._attr_translation_key = self._miot_service.name
        if not self.entity_id and self.model:
            mls = f'{self.model}..'.split('.')
            mac = re.sub(r'[\W_]+', '', self.unique_mac)
            self.entity_id = f'{DOMAIN}.{mls[0]}_{mls[2]}_{mac[-4:]}_{mls[1]}'
        self._success_code = 0
        self.logger.info('%s: Initializing miot device with mapping: %s', self.name_model, self._miot_mapping)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if not self._miot_service:
            return
        self._vars['ignore_offline'] = self.custom_config_bool('ignore_offline')
        self.logger.debug('%s: Added to hass: %s', self.name_model, [self.custom_config()])

    @property
    def miot_device(self):
        if not self._device:
            device = self.device.local
            if device:
                self._device = device
        return self._device

    @property
    def miot_did(self):
        did = self.custom_config('miot_did') or self._config.get('miot_did')
        if did:
            return did
        return self.device.did

    @property
    def xiaomi_cloud(self):
        return self.device.cloud

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
        if self.custom_config_bool('miot_local') or self._config.get('miot_local'):
            return self.miot_device
        return None

    @property
    def is_main_entity(self):
        return self._vars.get('is_main_entity')

    @property
    def miot_config(self):
        return self._config or {}

    @property
    def entity_id_prefix(self):
        if not self._miot_service:
            return None
        return self._miot_service.spec.generate_entity_id(self)

    async def async_update_from_device(self):
        self._available = self.device.available
        if self.is_main_entity:
            attrs = self.device.props
            attrs['state_updater'] = self.device.data.get('updater')
            await self.async_update_for_main_entity()
        else:
            attrs = {
                k: v
                for k, v in self.device.props.items()
                if k in self._miot_mapping
            }
        self._state_attrs = attrs
        await self.async_update_attrs(attrs, update_subs=True)
        return attrs

    async def async_update(self):
        if self._vars.get('delay_update'):
            await asyncio.sleep(self._vars.get('delay_update'))
            self._vars.pop('delay_update', 0)
        await self.device.update_main_status()
        attrs = await self.async_update_from_device()
        self.logger.debug('%s: Got new state: %s', self.name, attrs)

    async def async_update_for_main_entity(self):
        pass

    async def async_get_device_data(self, key, did=None, **kwargs):
        if did is None:
            did = self.miot_did
        mic = self.xiaomi_cloud
        if not isinstance(mic, MiotCloud):
            return None
        result = await mic.async_get_user_device_data(did, key, raw=True, **kwargs)
        _LOGGER.info('%s: Xiaomi device data: %s', self.name_model, result)
        return result

    async def async_get_bindkey(self, did=None):
        mic = self.xiaomi_cloud
        if not isinstance(mic, MiotCloud):
            return None
        result = await mic.async_get_beaconkey(did or self.miot_did)
        _LOGGER.info('%s: Xiaomi device bindkey/beaconkey: %s', self.name_model, result)
        return result

    async def async_request_xiaomi_api(self, api, data=None, method='POST', crypt=True, **kwargs):
        mic = self.xiaomi_cloud
        if not isinstance(mic, MiotCloud):
            return None
        sid = kwargs.pop('sid', None) or 'xiaomiio'
        if sid != mic.sid:
            mic = await mic.async_change_sid(sid)
        pms = kwargs.pop('params', None)
        dat = data or pms
        result = await mic.async_request_api(api, data=dat, method=method, crypt=crypt, **kwargs)
        _LOGGER.debug('Xiaomi Api %s: %s', api, result)
        return result


class MiotToggleEntity(MiotEntity, ToggleEntity):
    _reverse_state = None

    def __init__(self, miot_service=None, device=None, **kwargs):
        super().__init__(miot_service, device, **kwargs)
        self._prop_power = None
        if miot_service:
            self._prop_power = miot_service.get_property('on', 'power', 'switch')

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._reverse_state = self.custom_config_bool('reverse_state', None)

    @property
    def is_on(self):
        val = None
        if self._prop_power:
            val = not not self._state_attrs.get(self._prop_power.full_name)
            if self._reverse_state:
                val = not val
        return val

    async def async_turn_on(self, **kwargs):
        if self._prop_power:
            val = True
            if self._prop_power.value_range:
                val = self._prop_power.range_max() or 1
            elif self._reverse_state:
                val = not val
            return await self.async_set_property(self._prop_power, val)
        return False

    async def async_turn_off(self, **kwargs):
        if self._prop_power:
            val = False
            if self._prop_power.value_range:
                val = self._prop_power.range_min() or 0
            elif self._reverse_state:
                val = not val
            return await self.async_set_property(self._prop_power, val)
        act = self._miot_service.get_action('stop_working', 'power_off')
        if act:
            return await self.async_call_action(self._miot_service.iid, act.iid)
        return False


class MiirToggleEntity(MiotEntity, ToggleEntity):
    def __init__(self, miot_service=None, device=None, **kwargs):
        super().__init__(miot_service, device, **kwargs)
        self._available = True
        self._miot_actions = []
        for a in miot_service.actions.values():
            if a.ins:
                continue
            self._miot_actions.append(a.friendly_desc)
        self._attr_is_on = None
        self._act_turn_on = miot_service.get_action('turn_on')
        self._act_turn_off = miot_service.get_action('turn_off')
        self._attr_should_poll = False

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if self.is_main_entity:
            await self.async_update_for_main_entity()

    @property
    def is_on(self):
        """Return True if entity is on."""
        return self._attr_is_on

    async def async_turn_on(self, **kwargs):
        """Turn the entity on."""
        if not self._act_turn_on:
            raise NotImplementedError()
        return await self.async_call_action(self._act_turn_on)

    async def async_turn_off(self, **kwargs):
        """Turn the entity off."""
        if not self._act_turn_off:
            raise NotImplementedError()
        return await self.async_call_action(self._act_turn_off)


class BaseSubEntity(BaseEntity):
    def __init__(self, parent, attr, option=None, **kwargs):
        self.hass = parent.hass
        self.device = parent.device
        self._unique_id = f'{parent.unique_id}-{attr}'
        self._name = f'{parent.name} {attr}'
        self._state = STATE_UNKNOWN
        self._attr_state = None
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
        self._option['domain'] = kwargs.get('domain')
        self.generate_entity_id()
        self._supported_features = int(self._option.get('supported_features', 0))
        self._attr_entity_category = self.custom_config('entity_category', self._option.get('entity_category'))
        self._attr_native_unit_of_measurement = self._option.get('unit')
        self._attr_translation_key = self.custom_config('translation_key') or attr
        self._extra_attrs = {
            'entity_class': self.__class__.__name__,
            'parent_entity_id': parent.entity_id,
        }
        self._state_attrs = {}
        self._parent_attrs = {}

    def generate_entity_id(self, domain=None):
        entity_id = None
        if self._option.get('entity_id'):
            entity_id = self._option.get('entity_id')
        elif not hasattr(self._parent, 'entity_id_prefix'):
            pass
        elif eip := self._parent.entity_id_prefix:
            suf = self._attr
            if self._dict_key:
                suf = f'{suf}_{self._dict_key}'
            entity_id = f'{eip}_{suf}'
        if not domain:
            domain = self._option.get('domain') or DOMAIN
        if entity_id is None:
            pass
        elif f'{domain}.' in entity_id:
            self.entity_id = entity_id
        else:
            if '.' in entity_id:
                entity_id = hass_core.split_entity_id(entity_id)[1]
            self.entity_id = f'{domain}.{entity_id}'

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def unique_mac(self):
        return self._parent.unique_mac

    @property
    def name(self):
        return self._name

    @property
    def device_name(self):
        return self._parent.device_name

    @property
    def name_model(self):
        return f'{self.device_name}({self.model})'

    def format_name_by_property(self, prop: MiotProperty):
        return f'{self.device_name} {prop.friendly_desc}'.strip()

    @property
    def available(self):
        return self._available and self._parent.available

    @property
    def supported_features(self):
        return self._supported_features

    @property
    def parent_entity(self):
        return self._parent

    @property
    def parent_attributes(self):
        return self.device.props or {}

    @property
    def extra_state_attributes(self):
        esa = {
            **self._extra_attrs,
            **self._state_attrs,
        }
        return self.filter_state_attributes(esa)

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
    def miot_cloud(self):
        mic = self._parent.miot_cloud
        if not isinstance(mic, MiotCloud):
            raise RuntimeError('The parent entity of %s does not have Mi Cloud.', self.name)
        return mic

    @property
    def customize_keys(self):
        mar = []
        for mod in wildcard_models(self.model):
            if self._dict_key:
                mar.append(f'{mod}:{self._attr}:{self._dict_key}')
            elif self._attr:
                mar.append(f'{mod}:{self._attr}')
            if hasattr(self, '_miot_property'):
                prop = getattr(self, '_miot_property')
                if prop:
                    mar.append(f'{mod}:{prop.full_name}')
                    mar.append(f'{mod}:{prop.name}')
        return mar

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if self.platform:
            self.update_custom_scan_interval(only_custom=True)
        self._option['icon'] = self.custom_config('icon', self.icon)
        self._option['device_class'] = self.custom_config('device_class', self.device_class)
        if uom := self.custom_config('unit_of_measurement'):
            self._attr_native_unit_of_measurement = uom

    def update_from_parent(self):
        self.update()
        if self.platform:
            self.schedule_update_ha_state()

    def update(self, data=None):
        attrs = self.parent_attributes
        self._parent_attrs = attrs
        if self._attr in attrs:
            self._available = True
            self._attr_state = attrs.get(self._attr)
            if self._dict_key and isinstance(self._attr_state, dict):
                self._attr_state = self._attr_state.get(self._dict_key)
            svd = self.custom_config_number('value_ratio') or 0
            if svd:
                try:
                    self._attr_state = round(float(self._attr_state) * svd, 3)
                except (TypeError, ValueError):
                    pass
        keys = self._option.get('keys', [])
        if isinstance(keys, list) and self._attr not in keys:
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
        if self.hass and self.platform:
            # don't set state before added to hass
            self.schedule_update_ha_state()
        return self._state_attrs

    async def async_call_parent(self, method, *args, **kwargs):
        ret = None
        if fun := getattr(self, method, None):
            ret = await fun(*args, **kwargs)
        if ret:
            await self.async_update()
        return ret

    def call_parent(self, method, *args, **kwargs):
        ret = None
        if fun := getattr(self, method, None):
            ret = fun(*args, **kwargs)
        if ret:
            self.update()
        return ret


class ToggleSubEntity(BaseSubEntity, ToggleEntity):
    def __init__(self, parent, attr='power', option=None, **kwargs):
        self._prop_power = None
        self._reverse_state = None
        super().__init__(parent, attr, option, **kwargs)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._reverse_state = self.custom_config_bool('reverse_state', None)

    def update(self, data=None):
        super().update(data)
        if not self._available:
            return
        try:
            self._state = cv.boolean(self._state_attrs.get(self._attr))
        except vol.Invalid:
            self._state = None

    @property
    def is_on(self):
        if self._reverse_state and self._state is not None:
            return not self._state
        return self._state

    async def async_turn_on(self, **kwargs):
        if self._prop_power:
            ret = await self.async_call_parent('async_set_property', self._prop_power, True)
            if ret:
                self._state = True
            return ret
        return await self.async_call_parent('async_turn_on', **kwargs)

    async def async_turn_off(self, **kwargs):
        if self._prop_power:
            ret = await self.async_call_parent('async_set_property', self._prop_power, False)
            if ret:
                self._state = False
            return ret
        return await self.async_call_parent('async_turn_off', **kwargs)
