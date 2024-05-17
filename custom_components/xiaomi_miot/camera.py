"""Support for Xiaomi cameras."""
import logging
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
    STATE_RECORDING,
    STATE_STREAMING,
)
from homeassistant.components.ffmpeg import async_get_image, DATA_FFMPEG
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.aiohttp_client import async_aiohttp_proxy_stream
from haffmpeg.camera import CameraMjpeg

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    MiotToggleEntity,
    BaseSubEntity,
    MiotCloud,
    MiCloudException,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
)

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'
SCAN_INTERVAL = timedelta(seconds=60)

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
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
        if not svs and spec.services:
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

    def __init__(self, hass: HomeAssistant):
        super().__init__()
        self.access_tokens = collections.deque(self.access_tokens, 12 * 2)
        self._manager = hass.data.get(DATA_FFMPEG)
        # http://ffmpeg.org/ffmpeg-all.html
        self._ffmpeg_options = ''
        self._segment_iv_hex = urandom(16).hex()
        self._segment_iv_b64 = base64.b64encode(bytes.fromhex(self._segment_iv_hex)).decode()

    @property
    def brand(self):
        return self.device_info.get('manufacturer')

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
    _is_doorbell = None
    _use_motion_stream = False
    _sub_motion_stream = False

    def __init__(self, hass: HomeAssistant, config: dict, miot_service: MiotService):
        super().__init__(miot_service, config=config, logger=_LOGGER)
        BaseCameraEntity.__init__(self, hass)
        if self._prop_power:
            self._supported_features |= CameraEntityFeature.ON_OFF
        if miot_service:
            self._prop_motion_tracking = miot_service.bool_property('motion_detection', 'motion_tracking')
            self._is_doorbell = miot_service.name in ['video_doorbell'] or '.lock.' in self._model

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
        elif self._miot_service.name in ['camera_control'] or self._is_doorbell:
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
            return STATE_RECORDING
        if self.is_streaming:
            return STATE_STREAMING
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
        lag = locale.getlocale()[0]
        stm = int(time.time() - 86400 * 7) * 1000
        etm = int(time.time() * 1000 + 999)
        if not self._motion_enable and not self._motion_entity:
            pass
        elif 'motion_video_latest' in self._state_attrs:
            adt = {
                'motion_video_updated': 1,
            }
        elif not (mic := self.xiaomi_cloud):
            pass
        elif self.custom_config_bool('use_alarm_playlist'):
            api = mic.get_api_by_host('business.smartcamera.api.io.mi.com', 'miot/camera/app/v1/alarm/playlist/limit')
            rqd = {
                'did': self.miot_did,
                'region': str(mic.default_server).upper(),
                'language': lag,
                'beginTime': stm,
                'endTime': etm,
                'limit': 2,
            }
            rdt = await mic.async_request_api(api, rqd, method='GET', crypt=True) or {}
            rls = rdt.get('data', {}).get('playUnits') or []
            if rls:
                fst = rls[0] or {}
                tim = fst.pop('createTime', 0) / 1000
                adt = {
                    'motion_video_time': f'{datetime.fromtimestamp(tim)}',
                    'motion_video_type': ','.join(fst.get('tags') or []),
                    'motion_video_latest': fst,
                }
            else:
                _LOGGER.warning('%s: camera alarm playlist is empty. %s', self.name_model, rdt)
        else:
            api = mic.get_api_by_host('business.smartcamera.api.io.mi.com', 'common/app/get/eventlist')
            rqd = {
                'did': self.miot_did,
                'model': self._model,
                'doorBell': self._is_doorbell,
                'eventType': 'Default',
                'needMerge': True,
                'sortType': 'DESC',
                'region': str(mic.default_server).upper(),
                'language': lag,
                'beginTime': stm,
                'endTime': etm,
                'limit': 2,
            }
            rdt = await mic.async_request_api(api, rqd, method='GET', crypt=True) or {}
            rls = rdt.get('data', {}).get('thirdPartPlayUnits') or []
            if rls:
                fst = rls[0] or {}
                tim = fst.pop('createTime', 0) / 1000
                adt = {
                    'motion_video_time': f'{datetime.fromtimestamp(tim)}',
                    'motion_video_type': fst.get('eventType'),
                    'motion_video_latest': fst,
                }
            else:
                _LOGGER.warning('%s: camera events is empty. %s', self.name_model, rdt)
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
            return self._state_attrs.get(self._prop_power.full_name) and True
        return True

    async def stream_source(self, **kwargs):
        fun = self.get_stream_address
        if self._motion_enable:
            fun = self.get_motion_stream_address
            idx = self.custom_config_integer('motion_stream_slice')
            if idx is not None:
                kwargs['index'] = idx
                fun = self.get_motion_stream_slice_video
            kwargs['crypto'] = True
        return await self.hass.async_add_executor_job(partial(fun, **kwargs))

    async def image_source(self, **kwargs):
        if self._motion_enable:
            kwargs['crypto'] = True
            return await self.hass.async_add_executor_job(
                partial(self.get_motion_image_address, **kwargs)
            )
        return await self.stream_source()

    def get_stream_address(self, **kwargs):
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
                        self.miot_action(
                            self._srv_stream.iid,
                            self._act_stop_stream.iid,
                        )
                    result = self.miot_action(
                        self._srv_stream.iid,
                        self._act_start_stream.iid,
                        [] if vav is None else [vav],
                    ) or {}
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
            'stream_address': self.get_motion_stream_address(),
            # 'video_address': self.get_motion_video_address(),
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
        pms = {
            'did': str(self.miot_did),
            'model': self.device_info.get('model'),
            'fileId': fid,
            'isAlarm': not not mvd.get('isAlarm'),
            'videoCodec': 'H265',
        }
        api = mic.get_api_by_host('business.smartcamera.api.io.mi.com', 'common/app/m3u8')
        pms = mic.rc4_params('GET', api, {'data': mic.json_encode(pms)})
        pms['yetAnotherServiceToken'] = mic.service_token
        url = f'{api}?{urlencode(pms)}'
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
            return self._prop_motion_tracking.from_dict(self._state_attrs)
        return None

    def enable_motion_detection(self):
        if self._prop_motion_tracking:
            return self.set_property(self._prop_motion_tracking, True)
        return False

    def disable_motion_detection(self):
        if self._prop_motion_tracking:
            return self.set_property(self._prop_motion_tracking, False)
        return False


class MotionCameraEntity(BaseSubEntity, BaseCameraEntity):
    def __init__(self, parent, hass: HomeAssistant, option=None):
        super().__init__(parent, 'motion_event', option, domain=ENTITY_DOMAIN)
        BaseCameraEntity.__init__(self, hass)
        self._available = True
        self._supported_features |= CameraEntityFeature.STREAM

    @property
    def state(self):
        if self.is_recording:
            return STATE_RECORDING
        if self.is_streaming:
            return STATE_STREAMING
        return STATE_IDLE

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
        return await self.hass.async_add_executor_job(
            partial(self._parent.get_motion_image_address, **kwargs)
        )
