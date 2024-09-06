import logging
from typing import Optional
from functools import partial
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import format_mac

from .const import DOMAIN, DEVICE_CUSTOMIZES, DEFAULT_NAME, CONF_CONN_MODE, DEFAULT_CONN_MODE
from .miot_spec import MiotSpec
from .xiaomi_cloud import MiotCloud


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
    cloud: Optional['MiotCloud'] = None
    local: Optional['MiotDevice'] = None

    def __init__(self, info: DeviceInfo, hass: HomeAssistant, entry: ConfigEntry):
        self.info = info
        self.hass = hass
        self.entry = entry
        self.entities = []

        self.local = MiotDevice.from_device(self)

    @property
    def name(self):
        return self.info.name

    @property
    def name_model(self):
        return f'{self.info.name}({self.info.model})'

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

    async def get_spec(self) -> Optional[MiotSpec]:
        self.hass.data[DOMAIN].setdefault('miot_specs', {})
        dat = self.hass.data[DOMAIN]['miot_specs']
        obj = dat.get(self.info.model)
        if not obj:
            urn = await self.get_urn()
            obj = await MiotSpec.async_from_type(self.hass, urn)
            dat[self.info.model] = obj
        return obj

    async def get_urn(self):
        urn = self.customizes.get('miot_type')
        if not urn:
            urn = self.info.urn
        if not urn:
            urn = await MiotSpec.async_get_model_type(self.hass, self.info.model)
            self.info.data['urn'] = urn
        return urn


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

    async def async_get_properties_for_mapping(self, *args, **kwargs) -> list:
        if not self.hass:
            return self.get_properties_for_mapping(*args, **kwargs)

        return await self.hass.async_add_executor_job(
            partial(
                self.get_properties_for_mapping,
                *args, **kwargs,
            )
        )

    async def async_send(self, *args, **kwargs):
        return await self.hass.async_add_executor_job(partial(self.send,*args, **kwargs))


class MiioInfo(MiioInfoBase):
    @property
    def firmware_version(self):
        return self.data.get('fw_ver')

    @property
    def hardware_version(self):
        return self.data.get('hw_ver')
