import logging
import copy
from typing import TYPE_CHECKING, Optional, Callable
from datetime import timedelta
from functools import partial, cached_property
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_HOST, CONF_TOKEN, CONF_MODEL
from homeassistant.helpers.event import async_call_later
import homeassistant.helpers.device_registry as dr

from .const import DOMAIN, DEVICE_CUSTOMIZES, MIOT_LOCAL_MODELS, DEFAULT_NAME, CONF_CONN_MODE, DEFAULT_CONN_MODE
from .hass_entry import HassEntry
from .hass_entity import XEntity, convert_unique_id
from .converters import BaseConv, InfoConv, MiotPropConv, MiotPropValueConv, MiotActionConv
from .coordinator import DataCoordinator
from .miot_spec import MiotSpec, MiotService, MiotResults
from .miio2miot import Miio2MiotHelper
from .xiaomi_cloud import MiotCloud, MiCloudException
from .utils import get_customize_via_model, CustomConfigHelper


from miio import (  # noqa: F401
    Device as MiioDevice,
    DeviceException,
)
from miio.device import DeviceInfo as MiioInfoBase
from miio.miot_device import MiotDevice as MiotDeviceBase

if TYPE_CHECKING:
    from . import BasicEntity

_LOGGER = logging.getLogger(__name__)
InfoConverter = InfoConv(option={'icon': 'mdi:information'})


class DeviceInfo:
    def __init__(self, data: dict):
        self.data = data

    def get(self, key, default=None):
        return self.data.get(key, default)

    @property
    def did(self):
        return self.data.get('did', '')

    @cached_property
    def unique_id(self):
        if mac := self.mac:
            return dr.format_mac(mac).lower()
        return self.did

    @property
    def name(self):
        return self.data.get('name') or DEFAULT_NAME

    @cached_property
    def model(self):
        return self.miio_info.model or ''

    @cached_property
    def mac(self):
        return self.data.get('mac') or ''

    @property
    def host(self):
        return self.data.get('localip') or self.data.get(CONF_HOST) or ''

    @property
    def token(self):
        return self.data.get(CONF_TOKEN) or self.miio_info.token or ''

    @cached_property
    def pid(self):
        pid = self.data.get('pid')
        if pid is not None:
            try:
                pid = int(pid)
            except Exception:
                pid = None
        return pid

    @property
    def urn(self):
        return self.data.get('urn') or ''

    @property
    def extra(self):
        return self.data.get('extra') or {}

    @cached_property
    def firmware_version(self):
        return self.miio_info.firmware_version

    @cached_property
    def hardware_version(self):
        return self.miio_info.hardware_version

    @cached_property
    def home_name(self):
        return self.data.get('home_name', '')

    @cached_property
    def room_name(self):
        return self.data.get('room_name', '')

    @cached_property
    def home_room(self):
        return f'{self.home_name} {self.room_name}'.strip()

    @cached_property
    def miio_info(self):
        info = self.data
        data = info.get('miio_info') or {
            'ap':     {'ssid': info.get('ssid'), 'bssid': info.get('bssid'), 'rssi': info.get('rssi')},
            'netif':  {'localIp': self.host, 'gw': '', 'mask': ''},
            'fw_ver': self.extra.get('fw_version', ''),
            'hw_ver': info.get('hw_ver', ''),
            'mac':    info.get('mac', ''),
            'model':  info.get(CONF_MODEL, ''),
            'token':  info.get(CONF_TOKEN, ''),
        }
        return MiioInfo(data)


class Device(CustomConfigHelper):
    spec: Optional['MiotSpec'] = None
    cloud: Optional['MiotCloud'] = None
    local: Optional['MiotDevice'] = None
    miio2miot: Optional['Miio2MiotHelper'] = None
    miot_entity = None
    miot_results = None
    _local_state = None
    _miot_mapping = None
    _exclude_miot_services = None
    _exclude_miot_properties = None
    _unreadable_properties = None

    def __init__(self, info: DeviceInfo, entry: HassEntry):
        self.data = {}
        self.info = info
        self.hass = entry.hass
        self.entry = entry
        self.cloud = entry.cloud
        self.entities: dict[str, 'BasicEntity'] = {}
        self.listeners: list[Callable] = []
        self.converters: list[BaseConv] = []
        self.coordinators: list[DataCoordinator] = []

    async def async_init(self):
        if not self.cloud_only:
            self.local = MiotDevice.from_device(self)
        spec = await self.get_spec()
        if spec and self.local and not self.cloud_only:
            self.miio2miot = Miio2MiotHelper.from_model(self.hass, self.model, spec)

        self._exclude_miot_services = self.custom_config_list('exclude_miot_services', [])
        self._exclude_miot_properties = self.custom_config_list('exclude_miot_properties', [])
        self._unreadable_properties = self.custom_config_bool('unreadable_properties')

    @cached_property
    def did(self):
        return self.info.did

    @property
    def name(self):
        return self.info.name

    @cached_property
    def model(self):
        return self.info.model

    @cached_property
    def name_model(self):
        return f'{self.name}({self.model})'

    @cached_property
    def unique_id(self):
        return f'{self.info.unique_id}-{self.entry.entry_id}'

    @property
    def conn_mode(self):
        return self.entry.get_config(CONF_CONN_MODE) or DEFAULT_CONN_MODE

    @property
    def local_only(self):
        return self.conn_mode == 'local'

    @property
    def cloud_only(self):
        return self.conn_mode == 'cloud'

    @property
    def sw_version(self):
        swv = self.info.firmware_version
        if self.info.hardware_version:
            swv = f'{swv}@{self.info.hardware_version}'
        updater = self.data.get('updater')
        emoji = {
            'local': '🛜',
            'cloud': '☁️',
        }.get(updater)
        if emoji:
            swv = f'{swv} {emoji}'
        elif updater:
            swv = f'{swv} ({updater})'
        return swv

    @property
    def identifiers(self):
        return {(DOMAIN, self.unique_id)}

    @property
    def hass_device_info(self):
        return {
            'identifiers': self.identifiers,
            'name': self.name,
            'model': self.model,
            'manufacturer': (self.model or 'Xiaomi').split('.', 1)[0],
            'sw_version': self.sw_version,
            'suggested_area': self.info.room_name,
            'configuration_url': f'https://home.miot-spec.com/s/{self.model}',
        }

    @property
    def customizes(self):
        return get_customize_via_model(self.model)

    def custom_config(self, key=None, default=None):
        cfg = self.customizes
        return cfg if key is None else cfg.get(key, default)

    @cached_property
    def extend_miot_specs(self):
        if self.cloud_only:
            # only for local mode
            return None
        ext = self.custom_config('extend_miot_specs')
        if ext and isinstance(ext, str):
            ext = DEVICE_CUSTOMIZES.get(ext, {}).get('extend_miot_specs')
        else:
            ext = self.custom_config_list('extend_miot_specs')
        if ext and isinstance(ext, list):
            return ext
        return None

    async def get_spec(self) -> Optional[MiotSpec]:
        if self.spec:
            return self.spec

        dat = self.hass.data[DOMAIN].setdefault('miot_specs', {})
        obj = dat.get(self.model)
        if not obj:
            urn = await self.get_urn()
            obj = await MiotSpec.async_from_type(self.hass, urn)
            dat[self.model] = obj
        if obj:
            self.spec = copy.copy(obj)
            if not self.cloud_only:
                if ext := self.extend_miot_specs:
                    self.spec.extend_specs(services=ext)
            self.init_converters()
        return self.spec

    async def get_urn(self):
        urn = self.custom_config('miot_type')
        if not urn:
            urn = self.info.urn
        if not urn:
            urn = await MiotSpec.async_get_model_type(self.hass, self.model)
            self.info.data['urn'] = urn
        return urn

    def init_converters(self):
        if not self.spec:
            return

        self.converters.append(InfoConverter)
        self.dispatch_info()

        for d in [
            'sensor', 'binary_sensor', 'switch', 'number', 'select', 'button', 'number_select',
            # 'fan', 'cover', 'scanner',
        ]:
            pls = self.custom_config_list(f'{d}_properties') or []
            if not pls:
                continue
            for prop in self.spec.get_properties(*pls):
                if d == 'number_select':
                    if prop.value_range:
                        d = 'number'
                    elif prop.value_list:
                        d = 'select'
                    else:
                        _LOGGER.warning(f'Unsupported customize entity: %s for %s', d, prop.full_name)
                        continue
                if d == 'button':
                    if prop.value_list:
                        for pv in prop.value_list:
                            val = pv.get('value')
                            des = pv.get('description') or val
                            attr = f'{prop.full_name}-{val}'
                            conv = MiotPropValueConv(attr, d, prop=prop, value=val, description=des)
                            self.converters.append(conv)
                    elif prop.is_bool:
                        conv = MiotPropValueConv(prop.full_name, d, prop=prop, value=True)
                        self.converters.append(conv)
                elif d == 'number' and not prop.value_range:
                    _LOGGER.warning(f'Unsupported customize entity: %s for %s', d, prop.full_name)
                    continue
                else:
                    desc = bool(prop.value_list and d in ['sensor', 'select'])
                    self.converters.append(MiotPropConv(prop.full_name, d, prop=prop, desc=desc))

        for d in ['button', 'text', 'select']:
            als = self.custom_config_list(f'{d}_actions') or []
            if not als:
                continue
            for srv in self.spec.services.values():
                for action in srv.get_actions(*als):
                    self.converters.append(MiotActionConv(action.full_name, d, action=action))

    async def init_coordinators(self, _):
        if self.miot_entity:
            return

        interval = self.custom_config_integer('interval_seconds') or 30
        lst = [
            DataCoordinator(self, name='update_miot_status', update_interval=timedelta(seconds=interval)),
        ]
        for coo in lst:
            await coo.async_config_entry_first_refresh()
        self.coordinators.extend(lst)

    def add_entities(self, domain):
        for conv in self.converters:
            if conv.domain != domain:
                continue
            key = convert_unique_id(conv)
            entity = self.entities.get(key)
            if entity:
                continue
            cls = XEntity.CLS.get(domain)
            adder = self.entry.adders.get(domain)
            if not (cls and adder):
                continue
            entity = cls(self, conv)
            self.add_entity(entity)
            adder([entity], update_before_add=False)
            _LOGGER.info('New entity: %s', entity)

        self.dispatch_info()
        async_call_later(self.hass, 0.1, self.init_coordinators)

    def add_entity(self, entity: 'BasicEntity'):
        if entity not in self.entities:
            self.entities[entity.unique_id] = entity

    def add_listener(self, handler: Callable):
        if handler not in self.listeners:
            self.listeners.append(handler)

    def remove_listener(self, handler: Callable):
        if handler in self.listeners:
            self.listeners.remove(handler)

    def dispatch(self, data: dict, log=True):
        if log:
            _LOGGER.info('%s: Device updated: %s', self.name_model, data)
        for handler in self.listeners:
            handler(data)

    def dispatch_info(self):
        info = {}
        InfoConverter.decode(self, info, self.info.host)
        self.dispatch(info, log=False)

    def decode(self, data: dict | list) -> dict:
        """Decode data from device."""
        payload = {}
        if not isinstance(data, list):
            data = [data]
        for value in data:
            self.decode_one(payload, value)
        return payload

    def decode_one(self, payload: dict, value: dict):
        if not isinstance(value, dict):
            _LOGGER.warning('%s: Value is not dict: %s', self.name_model, value)
            return
        if value.get('code', 0):
            return
        siid = value.get('siid')
        piid = value.get('piid')
        if siid and piid:
            mi = MiotSpec.unique_prop(siid, piid=piid)
            for conv in self.converters:
                if conv.mi == mi:
                    conv.decode(self, payload, value.get('value'))

    def encode(self, value: dict) -> dict:
        """Encode data from hass to device."""
        payload = {}
        for k, v in value.items():
            for conv in self.converters:
                if conv.attr == k:
                    conv.encode(self, payload, v)
        return payload

    async def async_write(self, payload: dict):
        """Send command to device."""
        data = self.encode(payload)
        result = None
        method = data.get('method')
        if method == 'set_properties':
            params = data.get('params', [])
            if self.miio2miot and self._local_state:
                result = []
                for param in params:
                    siid = param['siid']
                    piid = param.get('piid')
                    if not self.miio2miot.has_setter(siid, piid=piid):
                        continue
                    cmd = partial(self.miio2miot.set_property, self.local, siid, piid, param['value'])
                    result.append(await self.hass.async_add_executor_job(cmd))
            elif self.local and self._local_state:
                result = await self.local.async_send(method, params)
            elif self.cloud:
                result = await self.cloud.async_set_props(params)

        if method == 'action':
            param = data.get('param', {})
            siid = param['siid']
            aiid = param.get('aiid')
            if self.miio2miot and self._local_state and self.miio2miot.has_setter(siid, aiid=aiid):
                cmd = partial(self.miio2miot.call_action, self.local, siid, aiid, param.get('in', []))
                result = await self.hass.async_add_executor_job(cmd)
            elif self.local and self._local_state:
                result = await self.local.async_send(method, param)
            elif self.cloud:
                result = await self.cloud.async_do_action(param)

        _LOGGER.info('%s: Device write: %s', self.name_model, [payload, data, result])
        if result:
            self.dispatch(payload)
        return result

    @property
    def use_local(self):
        if self.cloud_only:
            return False
        if not self.local:
            return False
        if self.miio2miot:
            return True
        if self.model in MIOT_LOCAL_MODELS:
            return True
        if self.custom_config_bool('miot_local'):
            return True
        return False

    @property
    def use_cloud(self):
        if self.local_only:
            return False
        if self.use_local:
            return False
        if not self.cloud:
            return False
        if self.custom_config_bool('miot_cloud'):
            return True
        return True

    def miot_mapping(self):
        if self._miot_mapping:
            return self._miot_mapping

        if not self.spec:
            return None

        if dic := self.custom_config_json('miot_mapping'):
            self.spec.set_custom_mapping(dic)
            self._miot_mapping = dic
            return dic

        mapping = self.spec.services_mapping(
            excludes=self._exclude_miot_services,
            exclude_properties=self._exclude_miot_properties,
            unreadable_properties=self._unreadable_properties,
        ) or {}
        self._miot_mapping = mapping
        return mapping

    async def update_miot_status(
        self,
        mapping=None,
        use_local=None,
        use_cloud=None,
        auto_cloud=None,
        check_lan=None,
        max_properties=None,
    ) -> MiotResults:
        results = []
        self.miot_results = MiotResults()

        if use_local is None:
            use_local = False if use_cloud else self.use_local
        if use_cloud is None:
            use_cloud = False if use_local else self.use_cloud

        if mapping is None:
            mapping = self.miot_mapping()
        if not mapping:
            use_local = False
            use_cloud = False

        if use_local:
            try:
                if self.miio2miot:
                    results = await self.miio2miot.async_get_miot_props(self.local, mapping)
                else:
                    if not max_properties:
                        max_properties = self.custom_config_integer('chunk_properties')
                    if not max_properties:
                        max_properties = self.local.get_max_properties(mapping)
                    maps = []
                    if self.custom_config_integer('chunk_services'):
                        for service in self.spec.get_services(excludes=self._exclude_miot_services):
                            mapp = service.mapping(
                                excludes=self._exclude_miot_properties,
                                unreadable_properties=self._unreadable_properties,
                            ) or {}
                            if mapp:
                                maps.append(mapp)
                    else:
                        maps.append(mapping)
                    for mapp in maps:
                        res = await self.local.async_get_properties_for_mapping(
                            max_properties=max_properties,
                            did=self.did,
                            mapping=mapp,
                        )
                        results.extend(res)
                self._local_state = True
                self.miot_results.updater = 'local'
                self.miot_results.set_results(results, mapping)
            except (DeviceException, OSError) as exc:
                log = _LOGGER.error
                if auto_cloud:
                    use_cloud = self.cloud
                    log = _LOGGER.warning if self._local_state else _LOGGER.info
                else:
                    self.miot_results.errors = exc
                self._local_state = False
                log(
                    '%s: Got MiioException while fetching the state: %s, mapping: %s, max_properties: %s/%s',
                    self.name_model, exc, mapping, max_properties, len(mapping)
                )

        if use_cloud:
            try:
                results = await self.cloud.async_get_properties_for_mapping(self.did, mapping)
                if check_lan and self.local:
                    await self.hass.async_add_executor_job(partial(self.local.info, skip_cache=True))
                self.miot_results.updater = 'cloud'
                self.miot_results.set_results(results, mapping)
            except MiCloudException as exc:
                self.miot_results.errors = exc
                _LOGGER.error(
                    '%s: Got MiCloudException while fetching the state: %s, mapping: %s',
                    self.name_model, exc, mapping,
                )

        if self.miot_results.updater != self.data.get('updater'):
            dev_reg = dr.async_get(self.hass)
            if dev := dev_reg.async_get_device(self.identifiers):
                self.data['updater'] = self.miot_results.updater
                dev_reg.async_update_device(dev.id, sw_version=self.sw_version)
                _LOGGER.info('%s: State updater: %s', self.name_model, self.sw_version)
        if results:
            self.data['miot_results'] = results
            self.dispatch(self.decode(results))
        self.dispatch_info()
        return self.miot_results


class MiotDevice(MiotDeviceBase):
    hass: HomeAssistant = None

    @staticmethod
    def from_device(device: Device):
        host = device.info.host
        token = device.info.token
        if not host or host in ['0.0.0.0']:
            return None
        elif not token:
            return None
        elif device.info.pid in [6, 15, 16, 17]:
            return None
        mapping = {}
        miot_device = None
        try:
            miot_device = MiotDevice(ip=host, token=token, model=device.model, mapping=mapping or {})
        except TypeError as exc:
            err = f'{exc}'
            if 'mapping' in err:
                if 'unexpected keyword argument' in err:
                    # for python-miio <= v0.5.5.1
                    miot_device = MiotDevice(host, token)
                    miot_device.mapping = mapping
                elif 'required positional argument' in err:
                    # for python-miio <= v0.5.4
                    # https://github.com/al-one/hass-xiaomi-miot/issues/44#issuecomment-815474650
                    miot_device = MiotDevice(mapping, host, token)  # noqa
        except ValueError as exc:
            _LOGGER.warning('%s: Initializing with host %s failed: %s', host, device.name_model, exc)
        if miot_device:
            miot_device.hass = device.hass
        return miot_device

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

    async def async_get_properties_for_mapping(self, *, max_properties=None, did=None, mapping=None) -> list:
        return await self.hass.async_add_executor_job(
            partial(
                self.get_properties_for_mapping,
                max_properties=max_properties,
                did=did,
                mapping=mapping,
            )
        )

    def get_max_properties(self, mapping):
        idx = len(mapping)
        if idx < 10:
            return idx
        idx -= 10
        chunks = [
            # 10,11,12,13,14,15,16,17,18,19
            10, 6, 6, 7, 7, 8, 8, 9, 9, 10,
            # 20,21,22,23,24,25,26,27,28,29
            10, 7, 8, 8, 8, 9, 9, 9, 10, 10,
            # 30,31,32,33,34,35,36,37,38,39
            10, 8, 8, 7, 7, 7, 9, 9, 10, 10,
            # 40,41,42,43,44,45,46,47,48,49
            10, 9, 9, 9, 9, 9, 10, 10, 10, 10,
        ]
        return 10 if idx >= len(chunks) else chunks[idx]

    async def async_send(self, *args, **kwargs):
        return await self.hass.async_add_executor_job(partial(self.send,*args, **kwargs))


class MiioInfo(MiioInfoBase):
    @property
    def firmware_version(self):
        return self.data.get('fw_ver')

    @property
    def hardware_version(self):
        return self.data.get('hw_ver')
