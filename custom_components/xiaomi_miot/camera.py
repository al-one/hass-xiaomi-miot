"""Support for Xiaomi cameras."""
import logging
import asyncio
import time
from datetime import timedelta

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
    await async_setup_config_entry(hass, config_entry, async_setup_platform, async_add_entities)


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
        self._prop_stream_address = None
        self._prop_expiration_time = None
        for s in ['camera_stream_for_google_home', 'camera_stream_for_amazon_alexa']:
            srv = miot_service.spec.get_service(s)
            if not srv:
                continue
            act = srv.get_action('start_hls_stream', 'start_rtsp_stream')
            if act:
                self._srv_stream = srv
                self._act_start_stream = act
                self._prop_stream_address = srv.get_property('stream_address')
                self._prop_expiration_time = srv.get_property('expiration_time')
                break

        if self._prop_power:
            self._supported_features |= SUPPORT_ON_OFF
        if self._prop_stream_address:
            self._supported_features |= SUPPORT_STREAM

        self._state_attrs.update({'entity_class': self.__class__.__name__})
        self._last_image = None
        self._last_url = None
        self._url_expiration = 0
        self._extra_arguments = None
        self._manager = hass.data.get(DATA_FFMPEG)
        self._subs = {}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._manager = self.hass.data.get(DATA_FFMPEG)

    @property
    def should_poll(self):
        return True

    @property
    def brand(self):
        return self.device_info.get('manufacturer')

    async def async_update(self):
        await super().async_update()
        if self._available:
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

    async def stream_source(self):
        now = time.time() * 1000
        if self._url_expiration <= now:
            self._last_url = None
            _LOGGER.debug('Miot camera: %s url: %s expired: %s', self.name, self._last_url, self._url_expiration)
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
            if result.get('out'):
                odt = self._act_start_stream.out_results(result.get('out')) or {}
                self.update_attrs(odt)
                if self._prop_stream_address:
                    self._last_url = self._prop_stream_address.from_dict(odt)
                self._url_expiration = 0
                if self._prop_expiration_time:
                    self._url_expiration = int(self._prop_expiration_time.from_dict(odt) or 0)
                if not self._url_expiration:
                    self._url_expiration = now + 1000 * 60 * 4
        self.is_streaming = self._last_url and True
        if self.is_streaming:
            self.update_attrs({
                'miot_error': None,
            })
        return self._last_url

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
            await stream.close()

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
