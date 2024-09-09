import logging
import copy
from typing import Optional
from functools import partial, cached_property
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import format_mac

from .const import DOMAIN, DEVICE_CUSTOMIZES, DEFAULT_NAME, CONF_CONN_MODE, DEFAULT_CONN_MODE
from .miot_spec import MiotSpec, MiotResults
from .miio2miot import Miio2MiotHelper
from .xiaomi_cloud import MiotCloud, MiCloudException


from miio import (  # noqa: F401
    Device as MiioDevice,
    DeviceException,
)
from miio.device import DeviceInfo as MiioInfoBase
from miio.miot_device import MiotDevice as MiotDeviceBase

_LOGGER = logging.getLogger(__name__)


class DeviceInfo:
    def __init__(self, data: dict):
        self.data = data

    def get(self, key, default=None):
        return self.data.get(key, default)

    @property
    def did(self):
        return self.data.get('did', '')

    @property
    def unique_id(self):
        if mac := self.mac:
            return format_mac(mac).lower()
        return self.did

    @property
    def name(self):
        return self.data.get('name') or DEFAULT_NAME

    @property
    def model(self):
        return self.data.get('model') or self.miio_info.model or ''

    @property
    def mac(self):
        return self.data.get('mac') or ''

    @property
    def host(self):
        return self.data.get('localip') or ''

    @property
    def token(self):
        return self.data.get('token') or ''

    @property
    def urn(self):
        return self.data.get('urn') or ''

    @property
    def extra(self):
        return self.data.get('extra') or {}

    @property
    def firmware_version(self):
        return self.extra.get('fw_version', '')

    @property
    def hardware_version(self):
        return self.data.get('hw_ver', '')

    @property
    def home_name(self):
        return self.data.get('home_name', '')

    @property
    def room_name(self):
        return self.data.get('room_name', '')

    @property
    def home_room(self):
        return f'{self.home_name} {self.room_name}'.strip()

    @property
    def miio_info(self):
        info = self.data
        data = info.get('miio_info') or {
            'ap':     {'ssid': info.get('ssid'), 'bssid': info.get('bssid'), 'rssi': info.get('rssi')},
            'netif':  {'localIp': self.host, 'gw': '', 'mask': ''},
            'fw_ver': self.firmware_version,
            'hw_ver': self.hardware_version,
            'mac':    self.mac,
            'model':  self.model,
            'token':  self.token,
        }
        return MiioInfo(data)


class Device:
    spec: Optional['MiotSpec'] = None
    cloud: Optional['MiotCloud'] = None
    local: Optional['MiotDevice'] = None
    miio2miot: Optional['Miio2MiotHelper'] = None
    miot_results = None
    _local_state = None

    def __init__(self, info: DeviceInfo, hass: HomeAssistant, entry: ConfigEntry):
        self.info = info
        self.hass = hass
        self.entry = entry
        self.entities = []

        self.local = MiotDevice.from_device(self)
        if self.spec and not self.cloud_only:
            self.miio2miot = Miio2MiotHelper.from_model(hass, self.info.model, self.spec)

    @cached_property
    def did(self):
        return self.info.did

    @property
    def name(self):
        return self.info.name

    @cached_property
    def name_model(self):
        return f'{self.name}({self.info.model})'

    @property
    def conn_mode(self):
        return self.entry.data.get(CONF_CONN_MODE, DEFAULT_CONN_MODE)

    @property
    def local_only(self):
        return self.conn_mode == 'local'

    @property
    def cloud_only(self):
        return self.conn_mode == 'cloud'

    @property
    def customizes(self):
        return DEVICE_CUSTOMIZES.get(self.info.model) or {}

    def custom_config(self, key=None, default=None):
        return self.customizes.get(key, default)

    def custom_config_list(self, key=None, default=None):
        lst = self.custom_config(key)
        if lst is None:
            return default
        if not isinstance(lst, list):
            lst = f'{lst}'.split(',')
            lst = list(map(lambda x: x.strip(), lst))
        return lst

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
        obj = dat.get(self.info.model)
        if not obj:
            urn = await self.get_urn()
            obj = await MiotSpec.async_from_type(self.hass, urn)
            dat[self.info.model] = obj
        if obj:
            self.spec = copy.copy(obj)
            if not self.cloud_only:
                if ext := self.extend_miot_specs:
                    self.spec.extend_specs(services=ext)
        return obj

    async def get_urn(self):
        urn = self.customizes.get('miot_type')
        if not urn:
            urn = self.info.urn
        if not urn:
            urn = await MiotSpec.async_get_model_type(self.hass, self.info.model)
            self.info.data['urn'] = urn
        return urn

    async def update_miot_status(
        self,
        mapping=None,
        local_mapping=None,
        use_local=None,
        use_cloud=None,
        auto_cloud=None,
        check_lan=None,
        max_properties=None,
    ):
        self.miot_results = MiotResults([])
        if use_local is None:
            use_local = self.local or self.miio2miot
            if self.cloud_only or use_cloud:
                use_local = False
        if use_cloud is None:
            use_cloud = not use_local and self.cloud
            if not self.local:
                use_cloud = self.cloud
        if not (mapping or local_mapping):
            use_local = False
            use_cloud = False

        if use_local:
            self.miot_results.updater = 'lan'
            if not local_mapping:
                local_mapping = mapping
            try:
                if self.miio2miot:
                    results = await self.miio2miot.async_get_miot_props(self.local, local_mapping)
                    attrs = self.miio2miot.entity_attrs()
                else:
                    if not max_properties:
                        max_properties = self.local.get_max_properties(local_mapping)
                    results = await self.local.async_get_properties_for_mapping(
                        max_properties=max_properties,
                        did=self.did,
                        mapping=local_mapping,
                    )
                self._local_state = True
                self.miot_results.set_results(results, local_mapping)
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
                    self.name_model, exc, local_mapping, max_properties, len(local_mapping)
                )

        if use_cloud:
            self.miot_results.updater = 'cloud'
            try:
                results = await self.cloud.async_get_properties_for_mapping(self.did, mapping)
                if check_lan and self.local:
                    await self.hass.async_add_executor_job(partial(self.local.info, skip_cache=True))
                self.miot_results.set_results(results, mapping)
            except MiCloudException as exc:
                self.miot_results.errors = exc
                _LOGGER.error(
                    '%s: Got MiCloudException while fetching the state: %s, mapping: %s',
                    self.name_model, exc, mapping,
                )

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
        mapping = {}
        miot_device = None
        try:
            miot_device = MiotDevice(ip=host, token=token, model=device.info.model, mapping=mapping or {})
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
        if idx >= 10:
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
