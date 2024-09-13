from typing import TYPE_CHECKING, Optional
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_USERNAME
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .xiaomi_cloud import MiotCloud

if TYPE_CHECKING:
    from .device import Device

class HassEntry:
    ALL: dict[str, 'HassEntry'] = {}
    cloud: MiotCloud = None

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self.hass = hass
        self.entry = entry
        self.adders: dict[str, AddEntitiesCallback] = {}
        self.devices: dict[str, 'Device'] = {}

    @staticmethod
    def init(hass: HomeAssistant, entry: ConfigEntry):
        this = HassEntry.ALL.get(entry.entry_id)
        if not this:
            this = HassEntry(hass, entry)
            HassEntry.ALL[entry.entry_id] = this
        return this

    def __getattr__(self, item):
        return getattr(self.entry, item)

    def get_config(self, key=None, default=None):
        dat = {
            **self.entry.data,
            **self.entry.options,
        }
        if key:
            return dat.get(key, default)
        return dat

    def new_device(self, device_info: dict):
        from .device import Device, DeviceInfo
        info = DeviceInfo(device_info)
        device = Device(info, self)
        self.devices[info.unique_id] = device
        return device

    def new_adder(self, domain, adder: AddEntitiesCallback):
        self.adders[domain] = adder
        return self

    async def get_cloud(self, check=False, login=False):
        if not self.cloud:
            if not self.get_config(CONF_USERNAME):
                return None
            self.cloud = await MiotCloud.from_token(self.hass, self.get_config(), login=login)
        if check:
            await self.cloud.async_check_auth(notify=True)
        return self.cloud
