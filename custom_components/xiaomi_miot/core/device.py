import logging
import copy
import re
from typing import TYPE_CHECKING, Optional, Callable
from datetime import timedelta
from functools import partial, cached_property
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_HOST, CONF_TOKEN, CONF_MODEL, CONF_USERNAME, EntityCategory
from homeassistant.util import dt
from homeassistant.components import persistent_notification
from homeassistant.helpers.event import async_call_later
import homeassistant.helpers.device_registry as dr

from .const import (
    DOMAIN,
    DEVICE_CUSTOMIZES,
    GLOBAL_CONVERTERS,
    MIOT_LOCAL_MODELS,
    DEFAULT_NAME,
    CONF_CONN_MODE,
    DEFAULT_CONN_MODE,
)
from .hass_entry import HassEntry
from .hass_entity import XEntity, convert_unique_id
from .converters import BaseConv, InfoConv, MiotPropConv, MiotPropValueConv, MiotActionConv, AttrConv
from .coordinator import DataCoordinator
from .miot_spec import MiotSpec, MiotProperty, MiotResults, MiotResult
from .miio2miot import Miio2MiotHelper
from .xiaomi_cloud import MiotCloud, MiCloudException
from .utils import (
    CustomConfigHelper,
    get_customize_via_model,
    get_value,
    is_offline_exception,
    update_attrs_with_suffix,
)
from .templates import template


from miio import (  # noqa: F401
    Device as MiioDevice,
    DeviceException,
)
from miio.device import DeviceInfo as MiioInfoBase
from miio.miot_device import MiotDevice as MiotDeviceBase

if TYPE_CHECKING:
    from . import BasicEntity

InfoConverter = InfoConv().with_option(
    icon='mdi:information',
    device_class='update',
    entity_category=EntityCategory.DIAGNOSTIC,
)


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
        return self.data.get('mac') or self.miio_info.mac_address or ''

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
        return self.data.get('urn') or self.data.get('spec_type') or ''

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
    available = True
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
        self.props: dict = {}
        self.entities: dict[str, 'BasicEntity'] = {}
        self.listeners: list[Callable] = []
        self.converters: list[BaseConv] = []
        self.coordinators: list[DataCoordinator] = []
        self.log = logging.getLogger(f'{__name__}.{self.model}')

    async def async_init(self):
        if not self.cloud_only:
            self.local = MiotDevice.from_device(self)
        spec = await self.get_spec()
        if spec and self.local and not self.cloud_only:
            self.miio2miot = Miio2MiotHelper.from_model(self.hass, self.model, spec)
            mps = self.custom_config_list('miio_properties')
            if mps and self.miio2miot:
                self.miio2miot.extend_miio_props(mps)

        self._exclude_miot_services = self.custom_config_list('exclude_miot_services', [])
        self._exclude_miot_properties = self.custom_config_list('exclude_miot_properties', [])
        self._unreadable_properties = self.custom_config_bool('unreadable_properties')

    async def async_unload(self):
        for coo in self.coordinators:
            await coo.async_shutdown()

        self.spec = None
        self.hass.data[DOMAIN].setdefault('miot_specs', {}).pop(self.model, None)

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
        if self.entry.get_config(CONF_TOKEN):
            return self.info.unique_id
        return f'{self.info.unique_id}-{self.entry.id}'

    @cached_property
    def app_link(self):
        uid = self.cloud.user_id if self.cloud else ''
        if not self.did:
            return ''
        return f'mihome://device?uid={uid}&did={self.did}'

    @property
    def conn_mode(self):
        if not self.entry.get_config(CONF_USERNAME):
            return 'local'
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
            trans_options = self.custom_config_bool('trans_options', self.entry.get_config('trans_options'))
            urn = await self.get_urn()
            obj = await MiotSpec.async_from_type(self.hass, urn, trans_options=trans_options)
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

    def add_converter(self, conv: BaseConv):
        if conv in self.converters:
            return
        for c in self.converters:
            if c.attr == conv.attr:
                self.log.info('Converter for %s already exists. Ignored.', c.attr)
                return
        self.converters.append(conv)

    def init_converters(self):
        self.add_converter(InfoConverter)
        self.dispatch_info()

        if not self.spec:
            return

        for cfg in GLOBAL_CONVERTERS:
            cls = cfg.get('class')
            kwargs = cfg.get('kwargs', {})
            if services := cfg.get('services'):
                for service in self.spec.get_services(*services, excludes=self._exclude_miot_services):
                    conv = None
                    if cls and hasattr(cls, 'service'):
                        conv = cls(service=service, **kwargs)
                        if getattr(conv, 'prop', None):
                            self.add_converter(conv)
                        else:
                            self.log.info('Converter has no main props: %s', conv)
                            conv = None

                    for p in cfg.get('converters') or []:
                        if not (props := p.get('props')):
                            continue
                        for prop in service.get_properties(*props, excludes=self._exclude_miot_properties):
                            attr = p.get('attr', prop.full_name)
                            c = p.get('class', MiotPropConv)
                            d = p.get('domain', None)
                            ac = c(attr, domain=d, prop=prop, desc=p.get('desc'))
                            self.add_converter(ac)
                            if conv and not d:
                                conv.attrs.add(attr)

        for d in [
            'button', 'sensor', 'binary_sensor', 'switch', 'number', 'select', 'text',
            'number_select', 'scanner',
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
                        self.log.warning(f'Unsupported customize entity: %s for %s', d, prop.full_name)
                        continue
                platform = {
                    'scanner': 'device_tracker',
                    'tracker': 'device_tracker',
                }.get(d) or d
                if platform == 'button':
                    if prop.value_list:
                        for pv in prop.value_list:
                            val = pv.get('value')
                            des = pv.get('description') or val
                            attr = f'{prop.full_name}-{val}'
                            conv = MiotPropValueConv(attr, platform, prop=prop, value=val, description=des)
                            self.add_converter(conv)
                    elif prop.is_bool:
                        conv = MiotPropValueConv(prop.full_name, platform, prop=prop, value=True)
                        self.add_converter(conv)
                elif platform == 'number' and not prop.value_range:
                    self.log.warning(f'Unsupported customize entity: %s for %s', platform, prop.full_name)
                    continue
                else:
                    conv = MiotPropConv(prop.full_name, platform, prop=prop)
                    conv.with_option(
                        entity_type=None if platform == d else d,
                    )
                    self.add_converter(conv)

        for d in ['button', 'text', 'select']:
            als = self.custom_config_list(f'{d}_actions') or []
            if not als:
                continue
            for srv in self.spec.services.values():
                for action in srv.get_actions(*als):
                    self.add_converter(MiotActionConv(action.full_name, d, action=action))

        for d in ['sensor', 'binary_sensor']:
            for attr in self.custom_config_list(f'{d}_attributes') or []:
                self.add_converter(AttrConv(attr, d))

    async def init_coordinators(self, _):
        interval = 30
        interval = self.entry.get_config('scan_interval') or interval
        interval = self.custom_config_integer('interval_seconds') or interval
        lst = []
        if not self.miot_entity:
            lst.append(
                DataCoordinator(self, self.update_miot_status, update_interval=timedelta(seconds=interval)),
            )
        if self.cloud_statistics_commands:
            lst.append(
                DataCoordinator(self, self.update_cloud_statistics, update_interval=timedelta(seconds=interval*20)),
            )
        if self.miio_cloud_records:
            lst.append(
                DataCoordinator(self, self.update_miio_cloud_records, update_interval=timedelta(seconds=interval*20)),
            )
        if self.miio_cloud_props:
            lst.append(
                DataCoordinator(self, self.update_miio_cloud_props, update_interval=timedelta(seconds=interval*2)),
            )
        if self.custom_miio_properties:
            lst.append(
                DataCoordinator(self, self.update_miio_props, update_interval=timedelta(seconds=interval)),
            )
        if self.custom_miio_commands:
            lst.append(
                DataCoordinator(self, self.update_miio_commands, update_interval=timedelta(seconds=interval)),
            )
        self.coordinators.extend(lst)
        for coo in lst:
            await coo.async_config_entry_first_refresh()

    async def update_status(self):
        for coo in self.coordinators:
            await coo.async_refresh()

    def add_entities(self, domain):
        for conv in self.converters:
            if conv.domain != domain:
                continue
            unique = convert_unique_id(conv)
            entity = self.entities.get(unique)
            if entity:
                continue
            cls = XEntity.CLS.get(domain)
            if entity_type := conv.option.get('entity_type'):
                cls = XEntity.CLS.get(entity_type) or cls
            adder = self.entry.adders.get(domain)
            if not (cls and adder):
                self.log.warning('Entity class/adder not found: %s', [domain, conv.attr, cls, adder])
                continue
            entity = cls(self, conv)
            self.add_entity(entity, unique)
            adder([entity], update_before_add=False)
            self.log.info('New entity: %s', entity)

        if domain == 'button':
            self.dispatch_info()
            if not self.coordinators:
                async_call_later(self.hass, 0.1, self.init_coordinators)

    def add_entity(self, entity: 'BasicEntity', unique=None):
        if unique == None:
            unique = entity.unique_id
        if unique in self.entities:
            return None
        self.entities[unique] = entity
        return entity

    def add_listener(self, handler: Callable):
        if handler not in self.listeners:
            self.listeners.append(handler)

    def remove_listener(self, handler: Callable):
        if handler in self.listeners:
            self.listeners.remove(handler)

    def dispatch(self, data: dict, only_info=False, log=True):
        if log:
            self.log.info('Device updated: %s', data)
        for handler in self.listeners:
            handler(data, only_info=only_info)

    def dispatch_info(self):
        info = {}
        InfoConverter.decode(self, info, None)
        self.dispatch(info, only_info=True, log=False)

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
            self.log.warning('Value is not dict: %s', value)
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

    def decode_attrs(self, value: dict):
        if not isinstance(value, dict):
            self.log.warning('Value is not dict: %s', value)
            return
        payload = {}
        for conv in self.converters:
            val = get_value(value, conv.attr, None, ':')
            if val is not None:
                conv.decode(self, payload, val)
        return payload

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

        if method == 'update_status':
            result = await self.update_miot_status()

        if method == 'set_properties':
            params = data.get('params', [])
            cloud_params = []
            if not self._local_state or self.cloud_only:
                cloud_params = params
            elif self.miio2miot:
                result = []
                for param in params:
                    siid = param['siid']
                    piid = param['piid']
                    if not self.miio2miot.has_setter(siid, piid=piid):
                        cloud_params.append(param)
                        continue
                    cmd = partial(self.miio2miot.set_property, self.local, siid, piid, param['value'])
                    result.append(await self.hass.async_add_executor_job(cmd))
            elif self.local:
                result = await self.local.async_send(method, params)
            if self.cloud and cloud_params:
                result = await self.cloud.async_set_props(cloud_params)

        if method == 'action':
            param = data.get('param', {})
            cloud_param = None
            siid = param['siid']
            aiid = param['aiid']
            if not self._local_state or self.cloud_only:
                cloud_param = param
            elif self.miio2miot:
                if self.miio2miot.has_setter(siid, aiid=aiid):
                    cmd = partial(self.miio2miot.call_action, self.local, siid, aiid, param.get('in', []))
                    result = await self.hass.async_add_executor_job(cmd)
                else:
                    cloud_param = param
            elif self.local:
                result = await self.local.async_send(method, param)
            if self.cloud and cloud_param:
                result = await self.cloud.async_do_action(cloud_param)

        self.log.info('Device write: %s', [payload, data, result])
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

    @property
    def auto_cloud(self):
        if not self.cloud:
            return False
        return self.custom_config_bool('auto_cloud')

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
        if auto_cloud is None:
            auto_cloud = self.auto_cloud

        if mapping is None:
            mapping = self.miot_mapping()
        if not mapping:
            use_local = False
            use_cloud = False

        if use_local:
            try:
                if self.miio2miot:
                    results = await self.miio2miot.async_get_miot_props(self.local, mapping)
                    if attrs := self.miio2miot.entity_attrs():
                        self.props.update(attrs)
                        self.dispatch(self.decode_attrs(attrs))
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
                self.available = True
                self._local_state = True
                self.miot_results.updater = 'local'
                self.miot_results.set_results(results, mapping)
            except (DeviceException, OSError) as exc:
                log = self.log.error
                if auto_cloud:
                    use_cloud = self.cloud
                    log = self.log.warning if self._local_state else self.log.info
                else:
                    self.miot_results.errors = exc
                    self.available = False
                self._local_state = False
                props_count = len(mapping)
                log(
                    'Got MiioException while fetching the state: %s, mapping: %s, max_properties: %s/%s',
                    exc, mapping, max_properties or props_count, props_count
                )

        if use_cloud:
            try:
                self.miot_results.updater = 'cloud'
                results = await self.cloud.async_get_properties_for_mapping(self.did, mapping)
                if check_lan and self.local:
                    await self.hass.async_add_executor_job(partial(self.local.info, skip_cache=True))
                self.available = True
                self.miot_results.set_results(results, mapping)
            except MiCloudException as exc:
                self.available = False
                self.miot_results.errors = exc
                self.log.error(
                    'Got MiCloudException while fetching the state: %s, mapping: %s',
                    exc, mapping,
                )

        if self.miot_results.updater != self.data.get('updater'):
            dev_reg = dr.async_get(self.hass)
            if dev := dev_reg.async_get_device(self.identifiers):
                self.data['updater'] = self.miot_results.updater
                dev_reg.async_update_device(dev.id, sw_version=self.sw_version)
                self.log.info('State updater: %s', self.sw_version)
        if results:
            self.miot_results.to_attributes(self.props)
            self.data['updated'] = dt.now()
            self.dispatch(self.decode(results))
        self.dispatch_info()
        await self.offline_notify()
        return self.miot_results

    async def offline_notify(self):
        result = self.miot_results
        is_offline = not result.is_valid and result.errors and is_offline_exception(result.errors)
        offline_devices = self.hass.data[DOMAIN].setdefault('offline_devices', {})
        notification_id = f'{DOMAIN}-devices-offline'
        if not is_offline:
            self.data.pop('offline_times', None)
            if offline_devices.pop(self.info.unique_id, None) and not offline_devices:
                persistent_notification.async_dismiss(self.hass, notification_id)
            return
        offline_times = self.data.setdefault('offline_times', 0)
        if not self.custom_config_bool('ignore_offline'):
            offline_times += 1
        odd = offline_devices.get(self.info.unique_id) or {}
        if odd:
            odd.update({
                'occurrences': offline_times,
            })
        elif offline_times >= 5:
            odd = {
                'device': self,
                'occurrences': offline_times,
            }
            offline_devices[self.info.unique_id] = odd
            tip = f'Some devices cannot be connected in the LAN, please check their IP ' \
                  f'and make sure they are in the same subnet as the HA.\n\n' \
                  f'一些设备无法通过局域网连接，请检查它们的IP，并确保它们和HA在同一子网。\n'
            for d in offline_devices.values():
                device = d.get('device')
                if not device:
                    continue
                tip += f'\n - {device.name_model}: {device.info.host}'
            tip += '\n\n'
            url = 'https://github.com/al-one/hass-xiaomi-miot/search' \
                  '?type=issues&q=%22Unable+to+discover+the+device%22'
            tip += f'[Known issues]({url})'
            url = 'https://github.com/al-one/hass-xiaomi-miot/issues/500#offline'
            tip += f' | [了解更多]({url})'
            persistent_notification.async_create(
                self.hass,
                tip,
                'Devices offline',
                notification_id,
            )
        self.data['offline_times'] = offline_times

    async def async_get_properties(self, mapping, update_entity=True, throw=False, **kwargs):
        if not self.spec:
            return {'error': 'No spec'}
        if isinstance(mapping, list):
            new_mapping = {}
            for p in mapping:
                siid = p['siid']
                piid = p['piid']
                pkey = self.spec.unique_prop(siid, piid=piid)
                prop = self.spec.specs.get(pkey)
                if not isinstance(prop, MiotProperty):
                    continue
                new_mapping[prop.full_name] = p
            mapping = new_mapping
        if not mapping or not isinstance(mapping, dict):
            return {'error': 'Mapping error'}
        try:
            results = []
            if self.use_local and self._local_state:
                results = await self.local.async_get_properties_for_mapping(did=self.did, mapping=mapping)
            elif self.cloud:
                results = await self.cloud.async_get_properties_for_mapping(self.did, mapping)
        except (DeviceException, MiCloudException) as exc:
            self.log.error(
                'Got exception while get properties: %s, mapping: %s, miio: %s',
                exc, mapping, self.info.miio_info,
            )
            if throw:
                raise exc
            return {'error': str(exc)}
        self.log.info('Get miot properties: %s', results)
        if results and update_entity:
            self.dispatch(self.decode(results))
        result = MiotResults(results, mapping)
        return result.to_attributes()

    def set_property(self, field, value):
        if isinstance(field, MiotProperty):
            siid = field.siid
            piid = field.iid
            field = field.full_name
        else:
            ext = (self.miot_mapping() or {}).get(field) or {}
            if not ext:
                return MiotResult({}, code=-1, error='Field not found')
            siid = ext['siid']
            piid = ext['piid']
        try:
            result = self.set_miot_property(siid, piid, value)
        except (DeviceException, MiCloudException) as exc:
            self.log.error('Set miot property %s(%s) failed: %s', field, value, exc)
            return MiotResult({}, code=-1, error=str(exc))
        ret = result.is_success if result else False
        if ret:
            self.log.debug('Set miot property %s(%s), result: %s', field, value, result)
        else:
            self.log.info('Set miot property %s(%s) failed, result: %s', field, value, result)
        return ret

    def set_miot_property(self, siid, piid, value, **kwargs):
        iid = MiotSpec.unique_prop(siid, piid)
        did = self.did or iid
        pms = {
            'did':  str(did),
            'siid': siid,
            'piid': piid,
            'value': value,
        }
        cloud_pms = None
        m2m = None if self.custom_config_bool('miot_cloud_write') else self.miio2miot
        try:
            results = []
            if not self._local_state or self.cloud_only:
                cloud_pms = pms
            elif m2m:
                if m2m.has_setter(siid, piid=piid):
                    results = [m2m.set_property(self.local, siid, piid, value)]
                else:
                    cloud_pms = pms
            elif self.local:
                results = self.local.send('set_properties', [pms])
            if self.cloud and cloud_pms:
                results = self.cloud.set_props([pms])
            result = MiotResults(results).first
        except (DeviceException, MiCloudException) as exc:
            self.log.warning('Set miot property %s failed: %s', pms, exc)
            return MiotResult({}, code=-1, error=str(exc))
        if not result.is_success:
            self.log.warning('Set miot property %s failed, result: %s', pms, result)
        else:
            self.log.info('Set miot property %s, result: %s', pms, result)
            result.value = value
            self.dispatch(self.decode(result.to_json()))
        return result

    def call_action(self, siid, aiid, params=None, **kwargs):
        did = self.did or MiotSpec.unique_prop(siid, aiid=aiid)
        pms = {
            'did':  str(did),
            'siid': siid,
            'aiid': aiid,
            'in':   params or [],
        }
        action = kwargs.get('action')
        if not action and self.spec:
            action = self.spec.services.get(siid, {}).actions.get(aiid)
        m2m = None if self.custom_config_bool('miot_cloud_action') else self.miio2miot
        mca = self.cloud if not self.use_local else None
        if self.auto_cloud and not self._local_state:
            mca = self.cloud
        try:
            if m2m and m2m.has_setter(siid, aiid=aiid):
                result = m2m.call_action(self.local, siid, aiid, params)
            elif isinstance(mca, MiotCloud):
                result = mca.do_action(pms)
            else:
                if not kwargs.get('force_params'):
                    pms['in'] = action.in_params(params or [])
                result = self.local.send('action', pms)
            result = MiotResult(result)
        except (DeviceException, MiCloudException) as exc:
            self.log.warning('Call miot action %s failed: %s', pms, exc)
            return MiotResult({}, code=-1, error=str(exc))
        except (TypeError, ValueError) as exc:
            self.log.warning('Call miot action %s failed: %s, result: %s', pms, exc, result)
            return MiotResult({}, code=-1, error=str(exc))
        if result.is_success:
            self.log.debug('Call miot action %s, result: %s', pms, result)
        else:
            self.log.info('Call miot action %s failed: %s', pms, result)
        return result

    @cached_property
    def cloud_statistics_commands(self):
        commands = self.custom_config_list('micloud_statistics') or []
        if keys := self.custom_config_list('stat_power_cost_key'):
            for k in keys:
                commands.append({
                    'type': self.custom_config('stat_power_cost_type', 'stat_day_v3'),
                    'key': k,
                    'day': 32,
                    'limit': 31,
                    'attribute': None,
                    'template': 'micloud_statistics_power_cost',
                })
        return commands


    async def update_cloud_statistics(self, commands=None):
        if not self.did or not self.cloud:
            return
        if commands is None:
            commands = self.cloud_statistics_commands

        now = int(dt.now().timestamp())
        attrs = {}
        for c in commands:
            if not c.get('key'):
                continue
            pms = {
                'did': self.did,
                'key': c.get('key'),
                'data_type': c.get('type', 'stat_day_v3'),
                'time_start': now - 86400 * (c.get('day') or 7),
                'time_end': now + 60,
                'limit': int(c.get('limit') or 1),
            }
            rdt = await self.cloud.async_request_api('v2/user/statistics', pms) or {}
            self.log.info('Got micloud statistics: %s', rdt)
            if tpl := c.get('template'):
                tpl = template(tpl, self.hass)
                rls = tpl.async_render(rdt)
            else:
                rls = [
                    v.get('value')
                    for v in rdt
                    if 'value' in v
                ]
            if anm := c.get('attribute'):
                attrs[anm] = rls
            elif isinstance(rls, dict):
                update_attrs_with_suffix(attrs, rls)
        if attrs:
            self.available = True
            self.props.update(attrs)
            self.data['updated'] = dt.now()
            self.dispatch(self.decode_attrs(attrs))
        return attrs

    @cached_property
    def miio_cloud_records(self):
        return self.custom_config_list('miio_cloud_records') or []

    async def update_miio_cloud_records(self, keys=None):
        if not self.did or not self.cloud:
            return
        if keys is None:
            keys = self.miio_cloud_records
        if not keys:
            return

        attrs = {}
        for c in keys:
            mat = re.match(r'^\s*(?:(\w+)\.?)([\w.]+)(?::(\d+))?(?::(\w+))?\s*$', c)
            if not mat:
                continue
            typ, key, lmt, gby = mat.groups()
            kws = {
                'time_start': int(dt.now().timestamp()) - 86400 * 32,
                'limit': int(lmt or 1),
            }
            if gby:
                kws['group'] = gby
            rdt = await self.cloud.async_get_user_device_data(self.did, key, typ, **kws) or []
            tpl = self.custom_config(f'miio_{typ}_{key}_template')
            if tpl:
                tpl = template(tpl, self.hass)
                rls = tpl.async_render({'result': rdt})
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
            self.available = True
            self.props.update(attrs)
            self.data['updated'] = dt.now()
            self.dispatch(self.decode_attrs(attrs))
        return attrs

    @cached_property
    def miio_cloud_props(self):
        return self.custom_config_list('miio_cloud_props') or []

    async def update_miio_cloud_props(self, keys=None):
        did = str(self.did)
        if not did or not self.cloud:
            return
        if keys is None:
            keys = self.miio_cloud_props
        if not keys:
            return

        pms = {
            'did': did,
            'props': [
                k if '.' in k else f'prop.{k}'
                for k in keys
            ],
        }
        rdt = await self.cloud.async_request_api('device/batchdevicedatas', [pms]) or {}
        self.log.debug('Got miio cloud props: %s', rdt)
        props = (rdt.get('result') or {}).get(did, {})

        tpl = self.custom_config('miio_cloud_props_template')
        if tpl and props:
            tpl = template(tpl, self.hass)
            attrs = tpl.async_render({'props': props})
        else:
            attrs = props
        if attrs:
            self.available = True
            self.props.update(attrs)
            self.data['updated'] = dt.now()
            self.dispatch(self.decode_attrs(attrs))
        return attrs

    @cached_property
    def custom_miio_properties(self):
        return self.custom_config_list('miio_properties') or []

    async def update_miio_props(self, props=None):
        if not self.local:
            return
        if props == None:
            props = self.custom_miio_properties
        if self.miio2miot:
            attrs = self.miio2miot.only_miio_props(props)
        else:
            try:
                num = self.custom_config_integer('chunk_properties') or 15
                attrs = await self.hass.async_add_executor_job(
                    partial(self.local.get_properties, props, max_properties=num)
                )
            except DeviceException as exc:
                self.log.warning('%s: Got miio properties %s failed: %s', self.name_model, props, exc)
                return
            if len(props) != len(attrs):
                self.props.update({
                    'miio.props': attrs,
                })
                return
        attrs = dict(zip(map(lambda x: f'miio.{x}', props), attrs))
        self.props.update(attrs)
        self.log.info('%s: Got miio properties: %s', self.name_model, attrs)

    @cached_property
    def custom_miio_commands(self):
        return self.custom_config_json('miio_commands') or {}

    async def update_miio_commands(self, commands=None):
        if not self.local:
            return
        if commands == None:
            commands = self.custom_miio_commands
        if isinstance(commands, dict):
            commands = [
                {'method': cmd, **(cfg if isinstance(cfg, dict) else {'values': cfg})}
                for cmd, cfg in commands.items()
            ]
        elif not isinstance(commands, list):
            commands = []
        for cfg in commands:
            cmd = cfg.get('method')
            pms = cfg.get('params') or []
            try:
                attrs = await self.local.async_send(cmd, pms)
            except DeviceException as exc:
                self.log.warning('%s: Send miio command %s(%s) failed: %s', self.name_model, cmd, cfg, exc)
                continue
            props = cfg.get('values', pms) or []
            if len(props) != len(attrs):
                attrs = {
                    f'miio.{cmd}': attrs,
                }
            else:
                attrs = dict(zip(props, attrs))
            self.props.update(attrs)
            self.log.info('%s: Got miio properties: %s', self.name_model, attrs)


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
            device.log.warning('Initializing with host %s failed: %s', host, exc)
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
