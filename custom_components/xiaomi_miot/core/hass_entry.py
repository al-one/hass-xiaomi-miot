import logging
import asyncio
from typing import TYPE_CHECKING
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_USERNAME
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import SUPPORTED_DOMAINS
from .xiaomi_cloud import MiotCloud

if TYPE_CHECKING:
    from .device import Device

_LOGGER = logging.getLogger(__name__)

class HassEntry:
    ALL: dict[str, 'HassEntry'] = {}
    cloud: MiotCloud = None
    cloud_devices = None

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self.id = entry.entry_id
        self.hass = hass
        self.entry = entry
        self.adders: dict[str, AddEntitiesCallback] = {}
        self.devices: dict[str, 'Device'] = {}
        self.mac_to_did = {}

    @staticmethod
    def init(hass: HomeAssistant, entry: ConfigEntry):
        this = HassEntry.ALL.get(entry.entry_id)
        if not this:
            this = HassEntry(hass, entry)
            HassEntry.ALL[entry.entry_id] = this
        return this

    async def async_unload(self):
        ret = all(
            await asyncio.gather(
                *[
                    self.hass.config_entries.async_forward_entry_unload(self.entry, domain)
                    for domain in SUPPORTED_DOMAINS
                ]
            )
        )
        if ret:
            for device in self.devices.values():
                await device.async_unload()
            HassEntry.ALL.pop(self.entry.entry_id, None)
        return ret

    def __getattr__(self, item):
        return getattr(self.entry, item)

    @property
    def setup_in_progress(self):
        return self.entry.state == ConfigEntryState.SETUP_IN_PROGRESS

    def get_config(self, key=None, default=None):
        dat = {
            **self.entry.data,
            **self.entry.options,
        }
        if self.filter_models:
            dat.pop('filter_did', None)
            dat.pop('did_list', None)
        else:
            dat.pop('filter_model', None)
            dat.pop('model_list', None)
        if key:
            return dat.get(key, default)
        return dat

    @property
    def filter_models(self):
        data = {
            **self.entry.data,
            **self.entry.options,
        }
        if data.get('did_list'):
            return False
        if data.get('model_list'):
            return True
        if 'did_list' in data:
            return False
        if 'model_list' in data:
            return True
        return data.get('filter_models', False)

    async def new_device(self, device_info: dict):
        from .device import Device, DeviceInfo
        info = DeviceInfo(device_info)
        if device := self.devices.get(info.unique_id):
            return device
        device = Device(info, self)
        await device.async_init()
        self.devices[info.unique_id] = device
        return device

    def new_adder(self, domain, adder: AddEntitiesCallback):
        self.adders[domain] = adder
        _LOGGER.info('New adder: %s', [domain, adder])

        for device in self.devices.values():
            device.add_entities(domain)

        return self

    async def get_cloud(self, check=False, login=False):
        if not self.cloud:
            if not self.get_config(CONF_USERNAME):
                return None
            self.cloud = await MiotCloud.from_token(self.hass, self.get_config(), login=login)
        if check:
            await self.cloud.async_check_auth(notify=True)
        return self.cloud

    async def get_cloud_devices(self):
        if isinstance(self.cloud_devices, dict):
            return self.cloud_devices
        cloud = await self.get_cloud()
        config = self.get_config()
        self.cloud_devices = await cloud.async_get_devices_by_key('did', filters=config) or {}
        for did, info in self.cloud_devices.items():
            mac = info.get('mac') or did
            self.mac_to_did[mac] = did
        return self.cloud_devices

    async def get_cloud_device(self, did=None, mac=None):
        devices = await self.get_cloud_devices()
        if mac and not did:
            did = self.mac_to_did.get(mac)
        if did:
            return devices.get(did)
        return None
