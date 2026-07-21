"""Support for Xiaomi cameras."""
import logging
import asyncio
import json
import time
import locale
import base64
import requests
import re
import collections
from os import urandom
from functools import partial
from urllib.parse import urlencode
from datetime import datetime, timedelta

from homeassistant.const import STATE_IDLE
from homeassistant.core import HomeAssistant
from homeassistant.components.camera import (
    DOMAIN as ENTITY_DOMAIN,
    Camera,
    CameraEntityFeature,  # v2022.5
)
from homeassistant.components.ffmpeg import async_get_image, DATA_FFMPEG
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.aiohttp_client import async_aiohttp_proxy_stream
from haffmpeg.camera import CameraMjpeg

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    Device,
    HassEntry,
    XEntity,
    MiotToggleEntity,
    BaseSubEntity,
    MiotCloud,
    MiCloudException,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.const import CameraState
from .core.miot_spec import (
    MiotSpec,
    MiotService,
)

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'
SCAN_INTERVAL = timedelta(seconds=60)

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    HassEntry.init(hass, config_entry).new_adder(ENTITY_DOMAIN, async_add_entities)
    await async_setup_config_entry(hass, config_entry, async_setup_platform, async_add_entities, ENTITY_DOMAIN)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data.setdefault(DATA_KEY, {})
    hass.data[DOMAIN]['add_entities'][ENTITY_DOMAIN] = async_add_entities
    config['hass'] = hass
    model = str(config.get(CONF_MODEL) or '')
    spec = hass.data[DOMAIN]['miot_specs'].get(model)
    entities = []
    if isinstance(spec, MiotSpec):
        svs = spec.get_services(ENTITY_DOMAIN, 'camera_control', 'video_doorbell')
        if svs:
            svs = []  # migrate to converter
        elif spec.services:
            srv = None
            if spec.name in ['video_doorbell']:
                # loock.cateye.v02
                srv = spec.get_service('p2p_stream') or spec.first_service()
            elif model in [
                'lumi.lock.bmcn05',
                'lumi.lock.mcn002',
                'lumi.lock.wbmcn1',
                'loock.lock.t1pro',
            ]:
                srv = spec.first_service()
            if isinstance(srv, MiotService):
                svs = [srv]
        for srv in svs:
            entities.append(MiotCameraEntity(hass, config, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class BaseCameraEntity(Camera):
    _state_attrs: dict
    _last_image = None
    _last_url = None
    _url_expiration = 0
    _extra_arguments = None
    device: Device = None

    def __init__(self, hass: HomeAssistant):
        super().__init__()
        self._supported_features = CameraEntityFeature(0)
        self.access_tokens = collections.deque(self.access_tokens, 12 * 2)
        self._manager = hass.data.get(DATA_FFMPEG)
        # http://ffmpeg.org/ffmpeg-all.html
        self._ffmpeg_options = ''
        self._segment_iv_hex = urandom(16).hex()
        self._segment_iv_b64 = base64.b64encode(bytes.fromhex(self._segment_iv_hex)).decode()
        if not hasattr(self, '_attr_extra_state_attributes'):
            self._attr_extra_state_attributes = {}

    @property
    def brand(self):
        return self.device_info.get('manufacturer')

    @property
    def is_doorbell(self):
        if '.lock.' in self.model:
            return True
        service = getattr(self, '_miot_service', None)
        if service and service.name in ['video_doorbell']:
            return True
        return False

    async def image_source(self, **kwargs):
        raise NotImplementedError()

    async def async_camera_image(self, width=None, height=None):
        url = await self.image_source()
        if url:
            if '-i ' not in str(url):
                url = f'-i "{url}"'
            self._last_image = await async_get_image(
                self.hass,
                f'{self._ffmpeg_options or ""} {url}'.strip(),
                extra_cmd=self._extra_arguments,
                width=width,
                height=height,
            )
        return self._last_image

    async def handle_async_mjpeg_stream(self, request):
        if not self.is_on:
            _LOGGER.debug('%s: camera is off. %s', self.name, self._state_attrs)
            return
        url = await self.stream_source()
        if not url:
            _LOGGER.debug('%s: stream source is empty. %s', self.name, self._state_attrs)
            return
        if '-i ' not in str(url):
            url = f'-i "{url}"'
        stream = CameraMjpeg(self._manager.binary)
        await stream.open_camera(
            f'{self._ffmpeg_options or ""} {url}'.strip(),
            extra_cmd=self._extra_arguments,
        )
        try:
            stream_reader = await stream.get_reader()
            return await async_aiohttp_proxy_stream(
                self.hass,
                request,
                stream_reader,
                self._manager.ffmpeg_stream_content_type,
                timeout=60,
            )
        finally:
            try:
                await stream.close()
            except BrokenPipeError:
                _LOGGER.error('%s: Got BrokenPipeError when close stream: %s', self.name, url)

    async def _async_log_stderr_stream(self, stderr_reader):
        """Log output from ffmpeg."""
        while True:
            line = await stderr_reader.readline()
            if line == b'':
                return
            _LOGGER.info('%s: ffmpeg stderr: %s', self.name, line.rstrip())

    async def get_alarm_playlist(self, begin, ended=None, limit=2):
        cloud = self.device.cloud
        if not cloud:
            return None
        api = cloud.get_api_by_host('business.smartcamera.api.io.mi.com', 'miot/camera/app/v1/alarm/playlist/limit')
        rqd = {
            'did': self.device.did,
            'region': str(cloud.default_server).upper(),
            'language': locale.getlocale()[0],
            'beginTime': begin,
            'endTime': ended or int(time.time() * 1000 + 999),
            'limit': limit,
        }
        rdt = await cloud.async_request_api(api, rqd, method='GET', crypt=True) or {}
        rls = rdt.get('data', {}).get('playUnits') or []
        adt = {}
        if rls:
            fst = rls[0] or {}
            tim = fst.pop('createTime', 0) / 1000
            adt = {
                'motion_video_time': f'{datetime.fromtimestamp(tim)}',
                'motion_video_type': ','.join(fst.get('tags') or []),
                'motion_video_latest': fst,
            }
        else:
            self.log.warning('Camera alarm playlist is empty. %s', rdt)
        return adt

    async def get_alarm_eventlist(self, begin, ended=None, doorbell=False, limit=2):
        cloud = self.device.cloud
        if not cloud:
            return None
        api = cloud.get_api_by_host('business.smartcamera.api.io.mi.com', 'common/app/get/eventlist')
        rqd = {
            'did': self.device.did,
            'model': self.model,
            'doorBell': doorbell,
            'eventType': 'Default',
            'needMerge': True,
            'sortType': 'DESC',
            'region': str(cloud.default_server).upper(),
            'language': locale.getlocale()[0],
            'beginTime': begin,
            'endTime': ended or int(time.time() * 1000 + 999),
            'limit': limit,
        }
        rdt = await cloud.async_request_api(api, rqd, method='GET', crypt=True) or {}
        rls = rdt.get('data', {}).get('thirdPartPlayUnits') or []
        adt = {}
        if rls:
            fst = rls[0] or {}
            tim = fst.pop('createTime', 0) / 1000
            adt = {
                'motion_video_time': f'{datetime.fromtimestamp(tim)}',
                'motion_video_type': fst.get('eventType'),
                'motion_video_latest': fst,
            }
        else:
            self.log.info('Camera events is empty. %s', rdt)
        return adt

    def get_alarm_m3u8_url(self, fileId, isAlarm=False, videoCodec='H265'):
        cloud = self.device.cloud
        if not cloud or not fileId:
            return None
        pms = {
            'did': str(self.device.did),
            'model': self.device_info.get('model'),
            'fileId': fileId,
            'isAlarm': not not isAlarm,
            'videoCodec': videoCodec,
        }
        api = cloud.get_api_by_host('business.smartcamera.api.io.mi.com', 'common/app/m3u8')
        pms = cloud.rc4_params('GET', api, {'data': cloud.json_encode(pms)})
        pms['yetAnotherServiceToken'] = cloud.service_token
        return f'{api}?{urlencode(pms)}'

    def get_alarm_image_address(self, fileId, storeId, crypto=False):
        cloud = self.device.cloud
        if not (cloud and fileId and storeId):
            return None
        dat = {
            'did': str(self.device.did),
            'fileId': fileId,
            'stoId': storeId,
            'segmentIv': self._segment_iv_b64,
        }
        api = cloud.get_api_by_host('processor.smartcamera.api.io.mi.com', 'miot/camera/app/v1/img')
        pms = cloud.rc4_params('GET', api, {'data': cloud.json_encode(dat)})
        pms['yetAnotherServiceToken'] = cloud.service_token
        url = f'{api}?{urlencode(pms)}'
        if crypto:
            key = base64.b64decode(cloud.ssecurity).hex()
            url = f'-decryption_key {key} -decryption_iv {self._segment_iv_hex} -i "crypto+{url}"'
        return url


class CameraEntity(XEntity, BaseCameraEntity):
    _attr_should_poll = True
    _attr_camera_image = None
    _attr_stream_source = None
    _last_motion_time = None
    _p2p_eligible = False
    _p2p_route: object = None

    def on_init(self):
        BaseCameraEntity.__init__(self, self.hass)
        self._attr_brand = self.device_info.get('manufacturer')
        self._attr_model = self.device_info.get('model')
        self._init_native_p2p()

    def _init_native_p2p(self) -> None:
        """Activate the native MISS+CS2 path for eligible devices.

        A converter-backed camera entity is eligible when its ``Device``
        resolved ``p2p_enabled`` during async init. The branch is
        deliberately narrow: it sets the STREAM feature, registers a
        stable loopback route on the entry-owned media server, and
        records the URL for the entity-lifetime ``stream_source()``
        contract. It does not call any cloud, session, or socket APIs.
        """
        device = getattr(self, "device", None)
        if device is None or not getattr(device, "p2p_enabled", False):
            self._p2p_eligible = False
            return
        self._p2p_eligible = True
        try:
            features = self._attr_supported_features | CameraEntityFeature.STREAM
        except AttributeError:
            features = CameraEntityFeature.STREAM
        self._attr_supported_features = features
        self._supported_features = features
        entry = getattr(device, "entry", None)
        server = getattr(entry, "p2p_server", None)
        if server is None:
            return
        try:
            route = server.add_route(self._handle_p2p_request)
        except Exception:  # noqa: BLE001 - server not started yet
            return
        self._p2p_route = route
        self._attr_available = True

    async def _handle_p2p_request(self, request):
        """Acquire a manager lease and return a bridge for the route.

        Validation of the route token and 503 throttling happens inside
        the loopback server's ``_handle_get``; by the time we get here
        the request is authorized. The handler must return a bridge
        object (``MediaBridge``) that exposes ``run(request)`` and
        ``close_future`` so the server can drive FFmpeg and clean up
        the session lease on close.
        """
        device = self.device
        entry = getattr(device, "entry", None)
        manager = await entry.async_ensure_p2p() if entry is not None else None
        if manager is None:
            raise RuntimeError("p2p_manager_unavailable")
        deadline = asyncio.get_event_loop().time() + 24.0
        key = self._p2p_lease_key()
        lease = await manager.acquire(key, deadline)
        return self._build_p2p_bridge(lease, entry)

    def _build_p2p_bridge(self, lease, entry):
        from .core.xiaomi_p2p.bridge import MediaBridge
        from .core.xiaomi_p2p.rtp import build_sdp

        contract = lease.contract
        audio_codec = getattr(contract, "audio_codec", None)
        sample_rate = getattr(contract, "sample_rate", 0) or 0
        track_count = 1
        if audio_codec is not None and sample_rate:
            track_count = 2

        def sdp_for(pairs):
            ports = {"video": pairs[0]}
            if track_count > 1:
                ports["audio"] = pairs[1]
            return build_sdp(
                contract,
                ports,
                {
                    "vps": getattr(contract, "vps", None),
                    "sps": getattr(contract, "video_sps", None),
                    "pps": getattr(contract, "video_pps", None),
                },
            )

        manager = getattr(self._manager, "binary", None)
        if not manager:
            manager = "ffmpeg"
        return MediaBridge(
            ffmpeg_binary=manager,
            sdp=sdp_for,
            port_allocator=entry.p2p_port_allocator,
            session_lease=lease,
            track_count=track_count,
        )

    def _p2p_lease_key(self):
        from .core.xiaomi_p2p.manager import LeaseKey

        device = self.device
        entry = device.entry
        cloud = getattr(entry, "cloud", None)
        region = (
            str(getattr(cloud, "default_server", "")).lower()
            if cloud is not None
            else ""
        )
        profile = getattr(device, "p2p_profile", None)
        return LeaseKey(
            entry_id=entry.id,
            region=region,
            did=device.info.did,
            lens=getattr(device, "p2p_lens", "primary"),
            raw_quality=getattr(profile, "raw_quality", 0),
            transport=getattr(profile, "transport", "auto"),
            request_audio=getattr(profile, "request_audio", True),
        )

    async def async_will_remove_from_hass(self) -> None:
        # Remove the route mapping without touching sibling routes or
        # active sessions; the entry's unload path owns the manager.
        route = getattr(self, "_p2p_route", None)
        if route is not None:
            server = getattr(self.device.entry, "p2p_server", None)
            if server is not None:
                try:
                    server.remove_route(route.route_id)
                except Exception:  # noqa: BLE001
                    pass
            self._p2p_route = None
        await super().async_will_remove_from_hass()

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if self._p2p_eligible and self._p2p_route is None:
            entry = getattr(self.device, "entry", None)
            ensure_server = getattr(entry, "async_ensure_p2p_server", None)
            server = None
            if ensure_server is not None:
                server = await ensure_server()
            else:
                server = getattr(entry, "p2p_server", None)
                if server is not None and hasattr(server, "acquire_entry"):
                    await server.acquire_entry()
            if server is not None:
                try:
                    self._p2p_route = server.add_route(self._handle_p2p_request)
                    self._attr_available = True
                except Exception:  # noqa: BLE001
                    pass
        if self._attr_should_poll:
            await self.async_update_ha_state(True)

    def get_state(self) -> dict:
        return {}

    def set_state(self, data: dict):
        if self._p2p_eligible:
            # Eligible cameras ignore cloud event attributes; the
            # route-only stream is the only source of media.
            return
        if 'motion_video_latest' in self.device.props:
            self._attr_available = True
            self._attr_should_poll = False
            self.update_motion_video(self.device.props)

    async def image_source(self):
        return self._attr_camera_image

    async def stream_source(self):
        if self._p2p_eligible:
            route = getattr(self, "_p2p_route", None)
            if route is not None:
                return route.url
            return self._attr_stream_source
        return self._attr_stream_source

    async def async_refresh_providers(self, *, write_state: bool = True) -> None:
        """Suppress provider selection for eligible P2P cameras.

        MISS streams are served over the loopback MPEG-TS route, not
        through any registered WebRTC provider. The base implementation
        would otherwise call ``_async_get_supported_webrtc_provider``,
        which leaks non-P2P assumptions about provider selection.
        """
        if self._p2p_eligible:
            return
        await super().async_refresh_providers(write_state=write_state)

    async def async_update(self):
        if self._p2p_eligible:
            # The route is the only media source; no cloud alarm
            # refresh is required.
            return
        adt = None
        stm = int(time.time() - 86400 * 7) * 1000
        if not self.device.cloud:
            pass
        elif self.custom_config_bool('miio_event_human_visit_details_template'):
            await self.device.update_miio_cloud_records()
        elif self.custom_config_bool('use_alarm_playlist'):
            adt = await self.get_alarm_playlist(stm)
        else:
            adt = await self.get_alarm_eventlist(stm, None, self.is_doorbell)
        if adt:
            self.log.debug('Camera alarm data: %s', adt)
            self._attr_available = True
            self.update_motion_video(adt)


XEntity.CLS[ENTITY_DOMAIN] = CameraEntity


class MiotCameraEntity(MiotToggleEntity, BaseCameraEntity):
    _srv_stream = None
    _act_start_stream = None
    _act_stop_stream = None
    _prop_stream_address = None
    _prop_expiration_time = None
    _prop_motion_tracking = None
    _stream_refresh_unsub = None
    _motion_entity = None
    _motion_enable = None
    _use_motion_stream = False
    _sub_motion_stream = False

    def __init__(self, hass: HomeAssistant, config: dict, miot_service: MiotService):
        super().__init__(miot_service, config=config, logger=_LOGGER)
        BaseCameraEntity.__init__(self, hass)
        if self._prop_power:
            self._supported_features |= CameraEntityFeature.ON_OFF
        if miot_service:
            self._prop_motion_tracking = miot_service.bool_property('motion_detection', 'motion_tracking')

    async def async_added_to_hass(self):
        await super().async_added_to_hass()

        sls = ['camera_stream_for_google_home', 'camera_stream_for_amazon_alexa']
        if self.custom_config_bool('use_rtsp_stream'):
            sls.reverse()
        for s in sls:
            if not self._miot_service:
                break
            srv = self._miot_service.spec.get_service(s)
            if not srv:
                continue
            act = srv.get_action('start_hls_stream', 'start_rtsp_stream')
            if act:
                self._srv_stream = srv
                self._act_start_stream = act
                self._act_stop_stream = srv.get_action('stop_stream')
                self._prop_stream_address = srv.get_property('stream_address')
                self._prop_expiration_time = srv.get_property('expiration_time')
                break
        if self._prop_stream_address:
            self._supported_features |= CameraEntityFeature.STREAM
            self._sub_motion_stream = True
        elif self._miot_service.name in ['camera_control'] or self.is_doorbell:
            if self.custom_config_bool('use_motion_stream'):
                pass
            elif self.custom_config_bool('sub_motion_stream'):
                pass
            else:
                self._use_motion_stream = True

    @property
    def should_poll(self):
        return True

    @property
    def state(self):  # noqa
        if self.is_recording:
            return CameraState.RECORDING
        if self.is_streaming:
            return CameraState.STREAMING
        return STATE_IDLE

    async def async_update(self):
        self._state_attrs.pop('motion_video_latest', None)  # remove
        await super().async_update()
        if not self._available:
            return

        self._motion_enable = self.custom_config_bool('use_motion_stream', self._use_motion_stream)
        add_cameras = self._add_entities.get(ENTITY_DOMAIN)
        if not self._motion_entity \
                and add_cameras \
                and self.custom_config_bool('sub_motion_stream', self._sub_motion_stream):
            self._motion_entity = MotionCameraEntity(self, self.hass)
            self._subs['motion_event'] = self._motion_entity
            add_cameras([self._motion_entity], update_before_add=True)

        adt = None
        stm = int(time.time() - 86400 * 7) * 1000
        if not self._motion_enable and not self._motion_entity:
            pass
        elif 'motion_video_latest' in self._state_attrs:
            adt = {
                'motion_video_updated': 1,
            }
        elif not self.xiaomi_cloud:
            pass
        elif self.custom_config_bool('use_alarm_playlist'):
            adt = await self.get_alarm_playlist(stm)
        else:
            adt = await self.get_alarm_eventlist(stm, None, self.is_doorbell)
        if adt:
            self._supported_features |= CameraEntityFeature.STREAM
            await self.async_update_attrs(adt)
            if self._motion_enable:
                await self.async_update_attrs(self.motion_event_attributes)
            if self._motion_entity:
                await self.hass.async_add_executor_job(self._motion_entity.update)

    @property
    def is_on(self):
        if self._prop_power:
            return self._prop_power.from_device(self.device) and True
        return True

    async def stream_source(self, **kwargs):
        fun = self.async_get_stream_address()
        if self._motion_enable:
            kwargs['crypto'] = True
            fun = self.hass.async_add_executor_job(partial(self.get_motion_stream_address, **kwargs))
            idx = self.custom_config_integer('motion_stream_slice')
            if idx is not None:
                kwargs['index'] = idx
                fun = self.hass.async_add_executor_job(partial(self.get_motion_stream_slice_video), **kwargs)
        return await fun

    async def image_source(self, **kwargs):
        if self._motion_enable:
            kwargs['crypto'] = True
            return self.get_motion_image_address(**kwargs)
        return await self.stream_source()

    async def async_get_stream_address(self, **kwargs):
        now = time.time()
        if now >= self._url_expiration:
            self._last_url = None
            _LOGGER.debug('%s: camera stream: %s expired: %s', self.name_model, self._last_url, self._url_expiration)
        result = {}
        if not self._act_start_stream:
            self.update_attrs({
                'miot_error': 'Nonsupport start hls/rstp stream via miot-spec',
            })
        elif not self._last_url:
            updater = 'lan'
            try:
                vav = self.custom_config_integer('video_attribute')
                vap = self._srv_stream.get_property('video_attribute')
                if vav is None and vap and vap.value_list:
                    vav = (vap.value_list.pop(0) or {}).get('value')
                if self.xiaomi_cloud:
                    if self._act_stop_stream:
                        await self.async_call_action(self._act_stop_stream)
                    result = await self.async_call_action(self._act_start_stream, [] if vav is None else [vav]) or {}
                    updater = 'cloud'
                if isinstance(result, dict):
                    _LOGGER.debug('%s: Get miot camera stream from %s: %s', self.name_model, updater, result)
                else:
                    _LOGGER.warning('%s: Get miot camera stream error from %s: %s', self.name_model, updater, result)
                    result = {}
            except MiCloudException as exc:
                _LOGGER.error('%s: Get miot camera stream from %s failed: %s', self.name_model, updater, exc)
            odt = self._act_start_stream.out_results(result.get('out')) or {
                'stream_address': '',
            }
            self._url_expiration = 0
            if self._prop_expiration_time:
                self._url_expiration = int(self._prop_expiration_time.from_dict(odt) or 0) / 1000
            if self._url_expiration:
                self._url_expiration -= 10
            else:
                self._url_expiration = now + 60 * 4.5
            if self._prop_stream_address:
                self._last_url = self._prop_stream_address.from_dict(odt)
                self.schedule_update_ha_state()
                self.async_check_stream_address(self._last_url)
                if not kwargs.get('scheduled') or self.custom_config('keep_streaming'):
                    self._schedule_stream_refresh()
            odt['expire_at'] = f'{datetime.fromtimestamp(self._url_expiration)}'
            self.update_attrs(odt)
        self._attr_is_streaming = self._last_url and True
        if self._attr_is_streaming:
            self.update_attrs({
                'miot_error': None,
            })
        return self._last_url

    def async_check_stream_address(self, url):
        if not url or self.custom_config_bool('disable_check_stream'):
            return False
        res = requests.head(url)
        if res.status_code > 200:
            self.update_attrs({
                'stream_http_status':  res.status_code,
                'stream_http_reason':  res.reason,
            })
            _LOGGER.warning(
                '%s: stream address status invalid: %s (%s)',
                self.name,
                res.status_code,
                res.reason,
            )
            return False
        return True

    async def _handle_stream_refresh(self, now, *_):
        self._stream_refresh_unsub = None
        await self.stream_source(scheduled=True)

    def _schedule_stream_refresh(self):
        if self._stream_refresh_unsub is not None:
            self._stream_refresh_unsub()
        self._stream_refresh_unsub = async_track_point_in_utc_time(
            self.hass,
            self._handle_stream_refresh,  # noqa
            datetime.fromtimestamp(self._url_expiration),
        )

    @property
    def motion_event_attributes(self):
        return {
            'motion_video_time': self._state_attrs.get('motion_video_time'),
            'motion_video_type': self._state_attrs.get('motion_video_type'),
            'stream_address': self.get_motion_stream_address(),
            'image_address': self.get_motion_image_address(),
        }

    def get_motion_stream_address(self, **kwargs):
        mic = self.xiaomi_cloud
        if not mic:
            _LOGGER.info('%s: camera does not have cloud.', self.name)
            return None
        mvd = self._state_attrs.get('motion_video_latest') or {}
        fid = mvd.get('fileId')
        if not fid:
            _LOGGER.info('%s: camera does not have motion file in cloud.', self.name)
            return None
        url = self.get_alarm_m3u8_url(fid, mvd.get('isAlarm'))
        _LOGGER.debug('%s: Got stream url: %s', self.name_model, url)
        return url

    def get_motion_video_address(self, **kwargs):
        mic = self.xiaomi_cloud
        if not mic:
            _LOGGER.info('%s: camera does not have cloud.', self.name)
            return None
        mvd = self._state_attrs.get('motion_video_latest') or {}
        fid = mvd.get('fileId')
        vid = mvd.get('videoStoreId')
        if not fid or not vid:
            _LOGGER.info('%s: camera does not have motion video in cloud.', self.name)
            return None
        dat = {
            'did': str(self.miot_did),
            'fileId': fid,
            'stoId': vid,
            'segmentIv': self._segment_iv_b64,
        }
        api = mic.get_api_by_host('processor.smartcamera.api.io.mi.com', 'miot/camera/app/v1/mp4')
        pms = mic.rc4_params('GET', api, {'data': mic.json_encode(dat)})
        pms['yetAnotherServiceToken'] = mic.service_token
        url = f'{api}?{urlencode(pms)}'
        _LOGGER.debug('%s: Got video url: %s', self.name_model, url)

        if kwargs.get('debug'):
            req = requests.get(url)
            if float(req.headers.get('x-xiaomi-status-code', 200)) >= 400:
                try:
                    signed_nonce = mic.signed_nonce(pms['_nonce'])
                    rdt = json.loads(MiotCloud.decrypt_data(signed_nonce, req.text).decode())
                    _LOGGER.info('%s: video stream content: %s', self.name_model, rdt)
                except (TypeError, ValueError):
                    pass
        if kwargs.get('crypto'):
            key = base64.b64decode(mic.ssecurity).hex()
            url = f'-decryption_key {key} -decryption_iv {self._segment_iv_hex} -i "crypto+{url}"'
        return url

    def get_motion_stream_slice_video(self, **kwargs):
        url = self.get_motion_stream_address()
        if not url:
            _LOGGER.info('%s: camera does not have motion stream in cloud.', self.name)
            return None
        req = requests.get(url)
        if float(req.headers.get('x-xiaomi-status-code', 200)) >= 400:
            _LOGGER.warning('%s: camera motion stream with a failed http code: %s', self.name_model, req)
            return url
        aes_key = None
        aes__iv = None
        mat = re.search(r'AES-128,\s*URI="?(https?://[^",]+)"?,\s*IV=(?:0x)?(\w+)', req.text)
        if mat:
            aes_key, aes__iv = mat.groups()
        mat = re.findall(r'[\r\n](https?://[^\r\n]+)', req.text)
        idx = kwargs.get('index', -1)
        mp4 = mat.pop(idx) if mat else None
        if mp4 and aes_key:
            req = requests.get(aes_key)
            key = req.content.hex()
            mp4 = f'-decryption_key {key} -decryption_iv {aes__iv} -i "crypto+{mp4}"'
            _LOGGER.debug('%s: Got video url: %s', self.name_model, mp4)
        return mp4

    def get_motion_image_address(self, **kwargs):
        mic = self.xiaomi_cloud
        if not mic:
            _LOGGER.info('%s: camera does not have cloud.', self.name)
            return None
        mvd = self._state_attrs.get('motion_video_latest') or {}
        fid = mvd.get('fileId')
        iid = mvd.get('imgStoreId')
        if not fid or not iid:
            _LOGGER.info('%s: camera does not have motion image in cloud.', self.name)
            return None
        dat = {
            'did': str(self.miot_did),
            'fileId': fid,
            'stoId': iid,
            'segmentIv': self._segment_iv_b64,
        }
        api = mic.get_api_by_host('processor.smartcamera.api.io.mi.com', 'miot/camera/app/v1/img')
        pms = mic.rc4_params('GET', api, {'data': mic.json_encode(dat)})
        pms['yetAnotherServiceToken'] = mic.service_token
        url = f'{api}?{urlencode(pms)}'
        _LOGGER.debug('%s: Got image url: %s', self.name_model, url)

        if kwargs.get('crypto'):
            key = base64.b64decode(mic.ssecurity).hex()
            url = f'-decryption_key {key} -decryption_iv {self._segment_iv_hex} -i "crypto+{url}"'
        return url

    @property
    def motion_detection_enabled(self):
        if self._prop_motion_tracking:
            return self._prop_motion_tracking.from_device(self.device)
        return None

    async def async_enable_motion_detection(self):
        if self._prop_motion_tracking:
            return await self.async_set_property(self._prop_motion_tracking, True)
        return False

    async def async_disable_motion_detection(self):
        if self._prop_motion_tracking:
            return await self.async_set_property(self._prop_motion_tracking, False)
        return False


class MotionCameraEntity(BaseSubEntity, BaseCameraEntity):
    def __init__(self, parent, hass: HomeAssistant, option=None):
        super().__init__(parent, 'motion_event', option, domain=ENTITY_DOMAIN)
        BaseCameraEntity.__init__(self, hass)
        self._available = True
        self._supported_features |= CameraEntityFeature.STREAM

    def update(self, data=None):
        super().update(data)
        self._available = not not self.parent_attributes.get('motion_video_latest')
        if not self._available:
            return
        self.update_attrs(self._parent.motion_event_attributes, update_parent=False)

    async def stream_source(self, **kwargs):
        kwargs['crypto'] = True
        return await self.hass.async_add_executor_job(
            partial(self._parent.get_motion_stream_address, **kwargs)
        )

    async def image_source(self, **kwargs):
        kwargs['crypto'] = True
        return self._parent.get_motion_image_address(**kwargs)
