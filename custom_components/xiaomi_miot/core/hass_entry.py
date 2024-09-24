import logging
from typing import TYPE_CHECKING, Optional
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_USERNAME
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .miio2miot import Miio2MiotHelper
from .xiaomi_cloud import MiotCloud
from .hass_entity import XEntity, convert_unique_id

if TYPE_CHECKING:
    from .device import Device

_LOGGER = logging.getLogger(__package__)

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

    async def new_device(self, device_info: dict, cloud: Optional[MiotCloud] = None):
        from .device import Device, DeviceInfo
        info = DeviceInfo(device_info)
        device = Device(info, self)
        device.cloud = cloud
        spec = await device.get_spec()
        if spec and not device.cloud_only:
            device.miio2miot = Miio2MiotHelper.from_model(self.hass, device.model, spec)
            await device.update_miot_status() # TODO
        self.devices[info.unique_id] = device
        return device

    def new_adder(self, domain, adder: AddEntitiesCallback):
        self.adders[domain] = adder
        _LOGGER.info('New adder: %s', [domain, adder])

        for device in self.devices.values():
            for conv in device.converters:
                if conv.domain != domain:
                    continue
                key = convert_unique_id(conv)
                entity = device.entities.get(key)
                if not entity:
                    cls = XEntity.CLS.get(domain)
                    if not cls:
                        continue
                    entity = cls(device, conv)
                    device.add_entity(entity)
                    adder([entity], update_before_add=False)
                    _LOGGER.info('New entity: %s', entity)

        return self

    async def get_cloud(self, check=False, login=False):
        if not self.cloud:
            if not self.get_config(CONF_USERNAME):
                return None
            self.cloud = await MiotCloud.from_token(self.hass, self.get_config(), login=login)
        if check:
            await self.cloud.async_check_auth(notify=True)
        return self.cloud
