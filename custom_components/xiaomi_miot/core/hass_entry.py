import asyncio
import logging
from typing import TYPE_CHECKING, Any, Optional

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import SUPPORTED_DOMAINS
from .xiaomi_cloud import REAUTH_SIDS, CloudSid, MiotCloud
from .xiaomi_p2p.cloud import get_capability_cache

if TYPE_CHECKING:
    from .device import Device

_LOGGER = logging.getLogger(__name__)


class HassEntry:
    ALL: dict[str, 'HassEntry'] = {}
    cloud_devices = None

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self.id = entry.entry_id
        self.hass = hass
        self.entry = entry
        self.adders: dict[str, AddEntitiesCallback] = {}
        self.devices: dict[str, 'Device'] = {}
        self.mac_to_did = {}
        self.did_to_unique = {}
        self.clouds: dict[CloudSid, Optional[MiotCloud]] = {}
        self._cloud_lock = asyncio.Lock()

        self.p2p_cache = get_capability_cache(hass)
        self.p2p_manager = None
        self._p2p_ensure_lock = asyncio.Lock()
        self._p2p_server_acquired = False
        self._p2p_bridge_close_tasks: set[asyncio.Task[Any]] = set()

    async def async_ensure_p2p(self):
        if self.p2p_manager is not None:
            return self.p2p_manager
        if not any(
            getattr(device, "p2p_enabled", False)
            for device in self.devices.values()
        ):
            return None
        async with self._p2p_ensure_lock:
            if self.p2p_manager is not None:
                return self.p2p_manager
            from .const import DOMAIN

            server = self.hass.data[DOMAIN]["p2p_media_server"]
            await server.acquire_entry()
            try:
                self.p2p_manager = self._create_p2p_manager()
            except BaseException:
                await server.release_entry()
                raise
            self._p2p_server_acquired = True
            return self.p2p_manager

    def _create_p2p_manager(self):
        from .xiaomi_p2p.manager import ChannelSessionManager

        return ChannelSessionManager(session_factory=self._create_p2p_session)

    async def _create_p2p_session(self, key, deadline):
        from .xiaomi_p2p import DEFAULT_P2P_PROFILE, P2PProfile
        from .xiaomi_p2p.cloud import async_miss_get_vendor_impl
        from .xiaomi_p2p.cs2.discovery import create_default_connector
        from .xiaomi_p2p.manager import MonotonicClock
        from .xiaomi_p2p.miss import MissSession

        unique = self.did_to_unique.get(key.did)
        device = self.devices.get(unique) if unique is not None else None
        if device is None or not getattr(device, "p2p_enabled", False):
            from .xiaomi_p2p import MissError, MissErrorCategory

            raise MissError(MissErrorCategory.MEDIA, "device_not_eligible")
        cloud = await self.get_cloud()
        if cloud is None:
            from .xiaomi_p2p import MissError, MissErrorCategory

            raise MissError(MissErrorCategory.CLOUD, "cloud_unavailable")
        host = device.info.host
        base_profile = getattr(device, "p2p_profile", None) or DEFAULT_P2P_PROFILE
        profile = P2PProfile(
            lenses=base_profile.lenses,
            transport=key.transport,
            raw_quality=key.raw_quality,
            request_audio=key.request_audio,
            required_video_codec=base_profile.required_video_codec,
            required_audio_codec=base_profile.required_audio_codec,
        )
        clock = MonotonicClock()
        connector = create_default_connector(clock)

        async def connect_fresh(connect_deadline):
            bootstrap = await async_miss_get_vendor_impl(
                cloud, key.did, host, connect_deadline
            )
            transport = await connector.connect(
                bootstrap, key.transport, connect_deadline
            )
            return bootstrap, transport

        bootstrap, transport = await connect_fresh(deadline)
        return MissSession(
            bootstrap=bootstrap,
            transport=transport,
            profile=profile,
            lens=key.lens,
            clock=clock,
            raw_quality=key.raw_quality,
            request_audio=key.request_audio,
            bootstrap_factory=connect_fresh,
        )

    def track_bridge_close_task(self, task: asyncio.Task[Any]) -> None:
        self._p2p_bridge_close_tasks.add(task)

    def untrack_bridge_close_task(self, task: asyncio.Task[Any]) -> None:
        self._p2p_bridge_close_tasks.discard(task)

    async def async_close_p2p(self) -> None:
        async with self._p2p_ensure_lock:
            manager, self.p2p_manager = self.p2p_manager, None
            acquired, self._p2p_server_acquired = (
                self._p2p_server_acquired,
                False,
            )
        try:
            if manager is not None:
                await manager.async_close()
        finally:
            if acquired:
                from .const import DOMAIN

                await self.hass.data[DOMAIN]["p2p_media_server"].release_entry()

    def invalidate_p2p_capability_cache(self):
        self.p2p_cache.invalidate_entry(self.id)

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
            self.clouds.clear()
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
        self.devices[info.unique_id] = device
        self.did_to_unique[info.did] = info.unique_id
        await device.async_init()
        return device

    def new_adder(self, domain, adder: AddEntitiesCallback):
        self.adders[domain] = adder
        _LOGGER.info('New adder: %s', [domain, adder])

        for device in self.devices.values():
            device.add_entities(domain)

        return self

    @property
    def cloud(self):
        return self.clouds.get(CloudSid.XIAOMIIO)

    async def get_cloud(self, check=False, login=False):
        cloud = await self.async_get_cloud(CloudSid.XIAOMIIO, login=login)
        if check and isinstance(cloud, MiotCloud):
            await cloud.async_check_auth(notify=True)
        return cloud

    async def async_get_cloud(
        self,
        sid: CloudSid = CloudSid.XIAOMIIO,
        *,
        login: bool = False,
    ) -> Optional[MiotCloud]:
        if isinstance(sid, str):
            sid = CloudSid(sid)
        if sid in self.clouds:
            return self.clouds[sid]
        async with self._cloud_lock:
            if sid in self.clouds:
                return self.clouds[sid]
            config = {**self.get_config(), 'sid': sid.value}
            cloud = await MiotCloud.from_token(
                self.hass, config, login=login, hass_entry=self,
            )
            self.clouds[sid] = cloud
            if sid == CloudSid.MICOAPI:
                try:
                    ok = await cloud.async_check_micoapi_auth()
                except Exception:
                    ok = None
                if not ok:
                    self.clouds[sid] = None
                    cloud = None
            return self.clouds[sid]

    async def async_change_sid(self, sid):
        if isinstance(sid, str):
            sid = CloudSid(sid)
        return await self.async_get_cloud(sid)

    async def async_auth_failed(self, sid: CloudSid) -> None:
        if isinstance(sid, str):
            sid = CloudSid(sid)
        if sid not in REAUTH_SIDS:
            return
        state = self.entry.state
        allowed = state == ConfigEntryState.LOADED or (
            sid == CloudSid.MICOAPI and state == ConfigEntryState.SETUP_IN_PROGRESS
        )
        if not allowed:
            return
        start_reauth = getattr(self.entry, 'async_start_reauth', None)
        if start_reauth is None:
            return
        await start_reauth(self.hass, data={'sid': sid.value})

    async def get_cloud_devices(self):
        if isinstance(self.cloud_devices, dict):
            return self.cloud_devices
        cloud = await self.get_cloud()
        if not cloud:
            return {}
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