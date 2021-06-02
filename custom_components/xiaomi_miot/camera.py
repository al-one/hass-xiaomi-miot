"""Support for Xiaomi cameras."""
import logging
import asyncio
import time
import requests
from datetime import datetime, timedelta

from homeassistant.const import *  # noqa: F401
from homeassistant.components.camera import (
    DOMAIN as ENTITY_DOMAIN,
    Camera,
    SUPPORT_ON_OFF,
    SUPPORT_STREAM,
    STATE_RECORDING,
    STATE_STREAMING,
)
from homeassistant.components.ffmpeg import DATA_FFMPEG
from homeassistant.components import persistent_notification
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.aiohttp_client import async_aiohttp_proxy_stream
from haffmpeg.camera import CameraMjpeg
from haffmpeg.tools import IMAGE_JPEG, ImageFrame

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    MiotToggleEntity,
    MiCloudException,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
)
from .switch import SwitchSubEntity

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'
SCAN_INTERVAL = timedelta(seconds=60)

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    await async_setup_config_entry(hass, config_entry, async_setup_platform, async_add_entities, ENTITY_DOMAIN)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data.setdefault(DATA_KEY, {})
    hass.data[DOMAIN]['add_entities'][ENTITY_DOMAIN] = async_add_entities
    model = str(config.get(CONF_MODEL) or '')
    entities = []
    miot = config.get('miot_type')
    if miot:
        spec = await MiotSpec.async_from_type(hass, miot)
        for srv in spec.get_services(ENTITY_DOMAIN, 'camera_control', 'video_doorbell'):
            if not spec.get_service('camera_stream_for_google_home', 'camera_stream_for_amazon_alexa'):
                if srv.name in ['camera_control']:
                    persistent_notification.create(
                        hass,
                        f'Your camera [**{model}**](https://miot-spec.org/miot-spec-v2/instance?type={miot}) '
                        'doesn\'t support streaming services.\n'
                        f'你的摄像机不支持流服务。\n'
                        'https://github.com/al-one/hass-xiaomi-miot/issues/60#issuecomment-819435571',
                        'Xiaomi Miot Warning',
                        f'{DATA_KEY}-warning-{model}',
                    )
                continue
            cfg = {
                **config,
                'name': f"{config.get('name')} {srv.description}"
            }
            entities.append(MiotCameraEntity(hass, cfg, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotCameraEntity(MiotToggleEntity, Camera):
    def __init__(self, hass, config: dict, miot_service: MiotService):
        super().__init__(miot_service, config=config)
        Camera.__init__(self)

        self._prop_motion_tracking = miot_service.get_property('motion_tracking')
        self._srv_stream = None
        self._act_start_stream = None
        self._act_stop_stream = None
        self._prop_stream_address = None
        self._prop_expiration_time = None
        if self._prop_power:
            self._supported_features |= SUPPORT_ON_OFF

        self._state_attrs.update({'entity_class': self.__class__.__name__})
        self._last_image = None
        self._last_url = None
        self._url_expiration = 0
        self._extra_arguments = None
        self._manager = hass.data.get(DATA_FFMPEG)
        self._stream_refresh_unsub = None
        self._subs = {}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._manager = self.hass.data.get(DATA_FFMPEG)

        sls = ['camera_stream_for_google_home', 'camera_stream_for_amazon_alexa']
        if self.custom_config('use_rtsp_stream'):
            sls.reverse()
        for s in sls:
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
            self._supported_features |= SUPPORT_STREAM

    @property
    def should_poll(self):
        return True

    @property
    def brand(self):
        return self.device_info.get('manufacturer')

    async def async_update(self):
        await super().async_update()
        if not self._available:
            return
        if self._prop_power:
            add_switches = self._add_entities.get('switch')
            pnm = self._prop_power.full_name
            if pnm in self._subs:
                self._subs[pnm].update()
            elif add_switches:
                self._subs[pnm] = SwitchSubEntity(self, pnm)
                add_switches([self._subs[pnm]])

    @property
    def state(self):
        if self.is_recording:
            return STATE_RECORDING
        if self.is_streaming:
            return STATE_STREAMING
        return STATE_IDLE

    @property
    def is_on(self):
        if self._prop_power:
            return self._state_attrs.get(self._prop_power.full_name) and True
        return True

    async def stream_source(self, **kwargs):
        now = time.time()
        if now >= self._url_expiration:
            self._last_url = None
            _LOGGER.debug('Miot camera: %s stream: %s expired: %s', self.name, self._last_url, self._url_expiration)
        if not self._act_start_stream:
            self.update_attrs({
                'miot_error': 'Nonsupport start hls/rstp stream',
            })
        elif not self._last_url:
            result = {}
            updater = 'lan'
            try:
                vda = int(self.custom_config('video_attribute') or 0)
                if self.miot_cloud:
                    if self._act_stop_stream:
                        await self.async_miot_action(
                            self._srv_stream.iid,
                            self._act_stop_stream.iid,
                        )
                    result = await self.async_miot_action(
                        self._srv_stream.iid,
                        self._act_start_stream.iid,
                        [vda],
                    ) or {}
                    updater = 'cloud'
                else:
                    result = {}
                _LOGGER.debug('Get miot camera stream from %s for %s: %s', updater, self.name, result)
            except MiCloudException as exc:
                _LOGGER.error('Get miot camera stream from %s for %s failed: %s', updater, self.name, exc)
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
                self.async_write_ha_state()
                await self.async_check_stream_address(self._last_url)
                if not kwargs.get('scheduled') or self.custom_config('keep_streaming'):
                    self._schedule_stream_refresh()
            odt['expire_at'] = f'{datetime.fromtimestamp(self._url_expiration)}'
            self.update_attrs(odt)
        self.is_streaming = self._last_url and True
        if self.is_streaming:
            self.update_attrs({
                'miot_error': None,
            })
        return self._last_url

    async def async_check_stream_address(self, url):
        if not url:
            return False
        res = await self.hass.async_add_executor_job(requests.head, url)
        if res.status_code >= 300:
            self.update_attrs({
                'stream_http_status':  res.status_code,
                'stream_http_reason':  res.reason,
            })
            _LOGGER.warning(
                '%s stream address status invalid: %s (%s)',
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

    async def async_camera_image(self):
        url = await self.stream_source()
        if url:
            ffmpeg = ImageFrame(self._manager.binary)
            self._last_image = await asyncio.shield(
                ffmpeg.get_image(
                    url,
                    output_format=IMAGE_JPEG,
                    extra_cmd=self._extra_arguments,
                    timeout=60,
                )
            )
        return self._last_image

    async def handle_async_mjpeg_stream(self, request):
        if not self.is_on:
            _LOGGER.debug('Miot camera: %s is off. %s', self.name, self._state_attrs)
            return
        url = await self.stream_source()
        if not url:
            _LOGGER.debug('Miot camera: %s url is empty. %s', self.name, self._state_attrs)
            return
        stream = CameraMjpeg(self._manager.binary)
        await stream.open_camera(url, extra_cmd=self._extra_arguments)
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
            except BrokenPipeError as exc:
                _LOGGER.error('Got BrokenPipeError when close stream: %s', url)

    @property
    def motion_detection_enabled(self):
        if self._prop_motion_tracking:
            return self._prop_motion_tracking.from_dict(self._state_attrs)
        return None

    def enable_motion_detection(self):
        if self._prop_motion_tracking:
            return self.set_property(self._prop_motion_tracking.full_name, True)
        return False

    def disable_motion_detection(self):
        if self._prop_motion_tracking:
            return self.set_property(self._prop_motion_tracking.full_name, False)
        return False
