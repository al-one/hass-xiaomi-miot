"""Support for Xiaomi WiFi speakers."""
import logging
import requests
import hashlib
import hmac
import time
import json
import re
import voluptuous as vol
from datetime import timedelta
from functools import partial
from urllib.parse import urlencode, urlparse, parse_qsl

from homeassistant.const import (
    ATTR_ATTRIBUTION,
    ATTR_FRIENDLY_NAME,
    CONF_HOST,
)
from homeassistant.components.media_player.const import ( 
    MEDIA_TYPE_MUSIC,
    MEDIA_TYPE_VIDEO,
    RepeatMode,
)
from homeassistant.components.media_player import (
    DOMAIN as ENTITY_DOMAIN,
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,  # v2022.5
    MediaPlayerState,  # v2022.10
)
from homeassistant.components.homekit.const import EVENT_HOMEKIT_TV_REMOTE_KEY_PRESSED
from homeassistant.core import HassJob
from homeassistant.util.dt import utcnow
from homeassistant.helpers.event import async_track_point_in_utc_time
import homeassistant.helpers.config_validation as cv

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    XIAOMI_MIIO_SERVICE_SCHEMA,
    BaseEntity,
    MiotEntityInterface,
    MiotEntity,
    MiirToggleEntity,
    MiotCloud,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
)

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'
SCAN_INTERVAL = timedelta(seconds=30)

SERVICE_TO_METHOD = {
    'intelligent_speaker': {
        'method': 'async_intelligent_speaker',
        'schema': XIAOMI_MIIO_SERVICE_SCHEMA.extend(
            {
                vol.Required('text'): cv.string,
                vol.Optional('execute', default=False): cv.boolean,
                vol.Optional('silent', default=False): cv.boolean,
                vol.Optional('throw', default=False): cv.boolean,
            },
        ),
    },
    'xiaoai_wakeup': {
        'method': 'async_xiaoai_wakeup',
        'schema': XIAOMI_MIIO_SERVICE_SCHEMA.extend(
            {
                vol.Optional('text', default=''): vol.Any(cv.string, None),
                vol.Optional('throw', default=False): cv.boolean,
            },
        ),
    },
}


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
        for srv in spec.get_services(
            'play_control', 'ir_tv_control', 'ir_projector_control',
            'ir_box_control', 'ir_stb_control', 'doorbell',
        ):
            if 'miir.' in model:
                entities.append(MiirMediaPlayerEntity(config, srv))
                continue
            if model in ['xiaomi.controller.86v1']:
                pass
            elif not srv.mapping() and not srv.get_action('play'):
                continue
            if spec.get_service('television', 'projector', 'tv_box'):
                entities.append(MitvMediaPlayerEntity(config, srv))
            elif srv.name in ['doorbell']:
                entities.append(MiotDoorbellEntity(config, srv))
            else:
                entities.append(MiotMediaPlayerEntity(config, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class BaseMediaPlayerEntity(MediaPlayerEntity, MiotEntityInterface, BaseEntity):
    _attr_state = None

    def __init__(self, miot_service: MiotService):
        self._miot_service = miot_service
        self._prop_state = miot_service.get_property('playing_state')
        self._prop_volume = miot_service.get_property('volume')
        self._prop_mute = miot_service.get_property('mute')
        self._speaker = miot_service.spec.get_service('speaker')
        if self._speaker:
            self._prop_volume = self._speaker.get_property('volume') or self._prop_volume
            self._prop_mute = self._speaker.get_property('mute') or self._prop_mute
        self._prop_input = None
        self._act_turn_on = None
        self._act_turn_off = None
        for srv in miot_service.spec.services.values():
            if p := srv.get_property('input_control'):
                self._prop_input = p
            act = srv.get_action('turn_on')
            if act and not self._act_turn_on:
                self._act_turn_on = act
            act = srv.get_action('turn_off')
            if act and not self._act_turn_off:
                self._act_turn_off = act

        if miot_service.get_action('play'):
            self._supported_features |= MediaPlayerEntityFeature.PLAY
        if miot_service.get_action('pause'):
            self._supported_features |= MediaPlayerEntityFeature.PAUSE
        if miot_service.get_action('previous'):
            self._supported_features |= MediaPlayerEntityFeature.PREVIOUS_TRACK
        if miot_service.get_action('next'):
            self._supported_features |= MediaPlayerEntityFeature.NEXT_TRACK
        if miot_service.get_action('stop'):
            self._supported_features |= MediaPlayerEntityFeature.STOP
        if self._prop_input:
            self._supported_features |= MediaPlayerEntityFeature.SELECT_SOURCE
            self._attr_source_list = self._prop_input.list_descriptions()
        if self._prop_volume:
            self._supported_features |= MediaPlayerEntityFeature.VOLUME_SET
            self._supported_features |= MediaPlayerEntityFeature.VOLUME_STEP
        if self._prop_mute:
            self._supported_features |= MediaPlayerEntityFeature.VOLUME_MUTE
        if self._act_turn_on:
            self._supported_features |= MediaPlayerEntityFeature.TURN_ON
        if self._act_turn_off:
            self._supported_features |= MediaPlayerEntityFeature.TURN_OFF

    @property
    def supported_features(self):
        return self._supported_features

    @property
    def device_class(self):
        if cls := self.get_device_class(MediaPlayerDeviceClass):
            return cls
        typ = f'{self._model} {self._miot_service.spec.type}'
        if 'speaker' in typ:
            return MediaPlayerDeviceClass.SPEAKER
        if 'receiver' in typ:
            return MediaPlayerDeviceClass.RECEIVER
        if 'television' in typ or '.tv.' in typ:
            return MediaPlayerDeviceClass.TV
        return None

    @property
    def state(self):
        if self._prop_state and self._prop_state.readable:
            sta = self._prop_state.from_dict(self._state_attrs)
            if sta is not None:
                if sta in self._prop_state.list_search('Playing', 'Play'):
                    return MediaPlayerState.PLAYING
                if sta == self._prop_state.list_value('Pause'):
                    return MediaPlayerState.PAUSED
                if sta == self._prop_state.list_value('Idle'):
                    return MediaPlayerState.IDLE
                des = self._prop_state.list_description(sta)
                if des is not None:
                    return des
        if self._attr_state is not None:
            return self._attr_state
        if self.available:
            return MediaPlayerState.IDLE
        return None

    @property
    def is_volume_muted(self):
        if self._prop_mute:
            return self._prop_mute.from_dict(self._state_attrs) and True
        return None

    def mute_volume(self, mute):
        if self._prop_mute:
            return self.set_property(self._prop_mute, True if mute else False)
        return False

    @property
    def volume_level(self):
        if self._prop_volume:
            val = self._prop_volume.from_dict(self._state_attrs)
            if val is not None:
                try:
                    return round(val or 0) / 100
                except (TypeError, ValueError):
                    pass
        return self._attr_volume_level

    def set_volume_level(self, volume):
        if self._prop_volume:
            val = round(volume * (self._prop_volume.range_max() or 1))
            stp = self._prop_volume.range_step()
            if stp and stp > 1:
                val = round(val / stp) * stp
            return self.set_property(self._prop_volume, val)
        return False

    def volume_up(self):
        if self._prop_volume:
            stp = self._prop_volume.range_step() or 5
            val = round(self._prop_volume.from_dict(self._state_attrs) or 0) + stp
            return self.set_property(self._prop_volume, val)
        return False

    def volume_down(self):
        if self._prop_volume:
            stp = self._prop_volume.range_step() or 5
            val = round(self._prop_volume.from_dict(self._state_attrs) or 0) - stp
            return self.set_property(self._prop_volume, val)
        return False

    def media_play(self):
        act = self._miot_service.get_action('play')
        if act:
            if self.miot_action(self._miot_service.iid, act.iid):
                if self._prop_state:
                    self.update_attrs({
                        self._prop_state.full_name: self._prop_state.list_value('Playing'),
                    })
                return True
        return False

    def media_pause(self):
        act = self._miot_service.get_action('pause')
        if act:
            if self.miot_action(self._miot_service.iid, act.iid):
                if self._prop_state:
                    self.update_attrs({
                        self._prop_state.full_name: self._prop_state.list_value('Pause'),
                    })
                return True
        return False

    def media_stop(self):
        act = self._miot_service.get_action('stop')
        if act:
            if self.miot_action(self._miot_service.iid, act.iid):
                if self._prop_state:
                    self.update_attrs({
                        self._prop_state.full_name: self._prop_state.list_value('Stopped', 'Stop', 'Idle'),
                    })
                return True
        return self.media_pause()

    def media_previous_track(self):
        act = self._miot_service.get_action('previous')
        if act:
            return self.miot_action(self._miot_service.iid, act.iid)
        return False

    def media_next_track(self):
        act = self._miot_service.get_action('next')
        if act:
            return self.miot_action(self._miot_service.iid, act.iid)
        return False

    def media_seek(self, position):
        return False

    def play_media(self, media_type, media_id, **kwargs):
        return False

    @property
    def source(self):
        """Name of the current input source."""
        if self._prop_input:
            val = self._prop_input.from_dict(self._state_attrs)
            if val is not None:
                return self._prop_input.list_description(val)
        return None

    def select_source(self, source):
        """Select input source."""
        val = self._prop_input.list_value(source)
        if val is not None:
            return self.set_property(self._prop_input, val)
        return False

    def select_sound_mode(self, sound_mode):
        return False

    def clear_playlist(self):
        return False

    def set_shuffle(self, shuffle):
        return False

    def set_repeat(self, repeat):
        return False

    async def async_browse_media(self, media_content_type=None, media_content_id=None):
        """Return a BrowseMedia instance."""
        pass


class MiotMediaPlayerEntity(MiotEntity, BaseMediaPlayerEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(miot_service, config=config, logger=_LOGGER)
        BaseMediaPlayerEntity.__init__(self, miot_service)

        self._intelligent_speaker = miot_service.spec.get_service('intelligent_speaker')
        self._message_router = miot_service.spec.get_service('message_router')
        self.xiaoai_cloud = None
        self.xiaoai_device = None
        if self._intelligent_speaker:
            self._state_attrs[ATTR_ATTRIBUTION] = 'Support TTS through service'
        self._supported_features |= MediaPlayerEntityFeature.PLAY_MEDIA

    @property
    def xiaoai_id(self):
        if not self.xiaoai_device:
            return None
        return self.xiaoai_device.get('deviceID')

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if self._intelligent_speaker:
            mic = self.miot_cloud
            if isinstance(mic, MiotCloud):
                self.xiaoai_cloud = await mic.async_change_sid('micoapi')

    async def async_update(self):
        await super().async_update()
        if not self._available:
            return
        self._update_sub_entities('on', domain='switch')

        if self._prop_state and not self._prop_state.readable:
            if self.is_volume_muted is False:
                self._attr_state = MediaPlayerState.PLAYING
            else:
                self._attr_state = MediaPlayerState.IDLE

        if self.xiaoai_device is None:
            await self.async_update_xiaoai_device()

        if self.xiaoai_device:
            await self.async_update_play_status()

            from .sensor import XiaoaiConversationSensor
            add_sensors = self._add_entities.get('sensor')
            if 'conversation' not in self._subs and add_sensors:
                self._subs['conversation'] = XiaoaiConversationSensor(self, self.hass)
                add_sensors([self._subs['conversation']])

    async def async_update_xiaoai_device(self):
        if not isinstance(self.xiaoai_cloud, MiotCloud):
            return self.xiaoai_device
        api = 'https://api2.mina.mi.com/admin/v2/device_list'
        dat = {
          'presence': False,
          'master': False,
        }
        result = await self.xiaoai_cloud.async_request_api(api, data=dat, method='GET') or {}
        if 'data' in result:
            self.xiaoai_device = {}
        for d in result.get('data', []):
            if not isinstance(d, dict):
                continue
            if d.get('miotDID') == self.miot_did or d.get('mac') == self._miio_info.mac_address:
                self.xiaoai_device = d
                break
        return self.xiaoai_device

    async def async_update_play_status(self, now=None):
        if not (aid := self.xiaoai_id):
            return
        self.update_attrs({'xiaoai_id': aid})
        api = 'https://api2.mina.mi.com/remote/ubus'
        dat = {
            'deviceId': aid,
            'path': 'mediaplayer',
            'method': 'player_get_play_status',
            'message': '{}',
        }
        try:
            result = await self.xiaoai_cloud.async_request_api(api, data=dat, method='POST') or {}
            info = result.get('data', {}).get('info', {})
            if not isinstance(info, dict):
                info = json.loads(info)
            if info:
                song = playing = info.get('play_song_detail') or {}
                mid = song.get('audio_id') or song.get('global_id')
                if mid and not song.get('title'):
                    song = self._vars.get('latest_song') or {}
                    aid = song.get('audioId') or song.get('songID')
                    if not aid or mid != aid or mid != self._attr_media_content_id:
                        song = await self.async_get_media_detail(song) or {}
                        self._vars['latest_song'] = song
                song.update(playing)

                if (sta := info.get('status')) is not None:
                    self._attr_state = {
                        0: MediaPlayerState.IDLE,
                        1: MediaPlayerState.PLAYING,
                        2: MediaPlayerState.PAUSED,
                    }.get(sta)
                if (typ := info.get('media_type')) is not None:
                    self._attr_media_content_type = {3: MEDIA_TYPE_MUSIC, 13: MEDIA_TYPE_VIDEO}.get(typ)
                else:
                    self._attr_media_content_type = song.get('audioType')
                self._attr_volume_level = info.get('volume')
                if self._attr_volume_level is not None:
                    self._attr_volume_level = self._attr_volume_level / 100
                self._attr_repeat = {
                    0: RepeatMode.ONE,
                    1: RepeatMode.ALL,
                    3: RepeatMode.OFF,  # random
                }.get(info.get('loop_type'), RepeatMode.OFF)

                self._attr_media_content_id = mid
                self._attr_media_title = song.get('title') or song.get('name')
                self._attr_media_artist = song.get('artist') or song.get('artistName')
                self._attr_media_album_name = song.get('album') or song.get('albumName')
                self._attr_media_image_url = song.get('cover') or song.get('coverURL')
                self._attr_media_image_remotely_accessible = False
                self._attr_media_duration = int(song['duration'] / 1000) if 'duration' in song else None
                self._attr_media_position = int(song['position'] / 1000) if 'position' in song else None
                if self._attr_state == MediaPlayerState.PLAYING:
                    self._attr_media_position_updated_at = utcnow()
            if not self._attr_state:
                self.logger.info('%s: Got empty media info: %s', self.name_model, result)
        except (TypeError, ValueError, Exception) as exc:
            self.logger.warning(
                '%s: Got exception while fetch xiaoai playing status: %s',
                self.name_model, [aid, exc],
            )

        if unsub := self._vars.pop('unsub_play_status', None):
            unsub()
        if self.state not in [MediaPlayerState.PLAYING]:
            pass
        elif not self._attr_media_duration or self._attr_media_position is None:
            pass
        elif self._attr_media_duration >= self._attr_media_position:
            rem = timedelta(seconds=self._attr_media_duration - self._attr_media_position + 3)
            self._vars['unsub_play_status'] = async_track_point_in_utc_time(
                self.hass,
                HassJob(self.async_update_play_status),
                utcnow().replace(microsecond=0) + rem,
            )

    async def async_get_media_detail(self, media: dict):
        mid = media.get('audio_id') or media.get('global_id')
        if not mid:
            return None
        api = 'https://api2.mina.mi.com/music/song_info'
        if is3 := self.xiaoai_device.get('capabilities', {}).get('ai_protocol_3_0', 0):
            api = 'https://api2.mina.mi.com/aivs3/audio/info'
        dat = {
            'audioIdList' if is3 else 'songIdList': json.dumps([mid]),
        }
        try:
            result = await self.xiaoai_cloud.async_request_api(api, data=dat, method='POST') or {}
            for m in result.get('data') or []:
                if 'duration' in m:
                    m['duration'] = int(m['duration'] * 1000)
                return m
        except (TypeError, ValueError, Exception) as exc:
            self.logger.info(
                '%s: Got exception while fetch xiaoai playing media: %s',
                self.name_model, [mid, exc],
            )
        return None

    def turn_on(self):
        if self._act_turn_on:
            return self.call_action(self._act_turn_on)
        return False

    def turn_off(self):
        if self._act_turn_off:
            return self.call_action(self._act_turn_off)
        return False

    async def async_play_media(self, media_type, media_id, **kwargs):
        if not (aid := self.xiaoai_id):
            return
        typ = {
            'audio': 1,
            'music': 1,
            'voice': 1,
            'mp3': 1,
            'tts': 1,
        }.get(media_type, media_type)
        if typ == 1:
            return await self.async_play_music(media_id)

        api = 'https://api2.mina.mi.com/remote/ubus'
        dat = {
            'deviceId': aid,
            'path': 'mediaplayer',
            'method': 'player_play_url',
            'message': json.dumps({'url': media_id, 'type': typ, 'media': 'app_ios'}),
        }
        rdt = await self.xiaoai_cloud.async_request_api(api, data=dat, method='POST') or {}
        logger = rdt.get('code') and self.logger.warning or self.logger.info
        logger('%s: Play media: %s', self.name_model, [dat, rdt])

    async def async_play_music(self, media_id, audio_id="1582971365183456177", id="355454500", **kwargs):
        if not (aid := self.xiaoai_id):
            return
        music = {
            "payload": {
                "audio_type": "MUSIC",
                "audio_items": [
                    {
                        "item_id": {
                            "audio_id": audio_id,
                            "cp": {
                                "album_id": "-1",
                                "episode_index": 0,
                                "id": id,
                                "name": "xiaowei",
                            },
                        },
                        "stream": {"url": media_id},
                    }
                ],
                "list_params": {
                    "listId": "-1",
                    "loadmore_offset": 0,
                    "origin": "xiaowei",
                    "type": "MUSIC",
                },
            },
            "play_behavior": "REPLACE_ALL",
        }
        api = 'https://api2.mina.mi.com/remote/ubus'
        dat = {
            'deviceId': aid,
            'path': 'mediaplayer',
            'method': 'player_play_music',
            'message': json.dumps({"startaudioid": audio_id, "music": json.dumps(music)}),
        }
        rdt = await self.xiaoai_cloud.async_request_api(api, data=dat, method='POST') or {}
        logger = rdt.get('code') and self.logger.warning or self.logger.info
        logger('%s: Play Music: %s', self.name_model, [dat, rdt])

    def intelligent_speaker(self, text, execute=False, silent=False, **kwargs):
        if srv := self._intelligent_speaker:
            anm = 'execute_text_directive' if execute else 'play_text'
            act = srv.get_action(anm)
            if act:
                pms = [text]
                pse = srv.get_property('silent_execution')
                if execute and pse:
                    sil = silent
                    if pse.value_list:
                        sil = pse.list_value('On' if silent else 'Off')
                        if sil is None:
                            sil = 0 if silent else 1
                    pms.append(sil)
                return self.miot_action(srv.iid, act.iid, pms, **kwargs)
            else:
                self.logger.warning('%s does not have action: %s', self.name_model, anm)
        elif self._message_router:
            act = self._message_router.get_action('post')
            if act:
                if not execute:
                    text = f'跟我说 {text}'
                return self.call_action(act, [text], **kwargs)
        else:
            self.logger.error('%s does not have service: %s', self.name_model, 'intelligent_speaker/message_router')
        return False

    async def async_intelligent_speaker(self, text, execute=False, silent=False, **kwargs):
        return await self.hass.async_add_executor_job(
            partial(self.intelligent_speaker, text, execute, silent, **kwargs)
        )

    def xiaoai_wakeup(self, text=None, **kwargs):
        if srv := self._intelligent_speaker:
            if act := srv.get_action('wake_up'):
                pms = [text or ''] if act.ins else []
                return self.miot_action(srv.iid, act.iid, pms, **kwargs)
            else:
                self.logger.warning('%s does not have action: %s', self.name_model, 'wake_up')
        else:
            self.logger.error('%s does not have service: %s', self.name_model, 'intelligent_speaker')
        return False

    async def async_xiaoai_wakeup(self, text=None, **kwargs):
        return await self.hass.async_add_executor_job(
            partial(self.xiaoai_wakeup, text, **kwargs)
        )


class MitvMediaPlayerEntity(MiotMediaPlayerEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(config, miot_service)
        self._host = self._config.get(CONF_HOST) or ''
        self._api_key = '881fd5a8c94b4945b46527b07eca2431'
        self._hmac_key = '2840d5f0d078472dbc5fb78e39da123e'
        self._state_attrs['6095_state'] = True
        self._keycode_actions = {
            'power': 'turn_off',
            'home': 'press_home',
            'menu': 'press_menu',
            'enter': 'press_ok',
            'back': 'press_back',
            'up': 'press_up',
            'down': 'press_down',
            'left': 'press_left',
            'right': 'press_right',
            'volumeup': 'press_volume_up',
            'volumedown': 'press_volume_down',
        }
        self._speaker_mode = self._miot_service.spec.get_service('speaker_mode')
        self._speaker_mode_switch = self._speaker_mode.bool_property('is_on') if self._speaker_mode else None
        self._remote_ctrl = self._miot_service.spec.get_service('remote_control')
        if self._remote_ctrl:
            self._keycode_actions.update({
                'settings': 'press_settings',
                'play': 'press_play',
                'pause': 'press_pause',
                'play_pause': 'press_play_pause',
            })
        self._keycodes = list(self._keycode_actions.keys())
        self._apps = {}
        self._supported_features |= MediaPlayerEntityFeature.PLAY_MEDIA

    @property
    def device_class(self):
        return MediaPlayerDeviceClass.TV

    @property
    def mitv_name(self):
        nam = self.device_info.get('name', '')
        if not re.match(r'[^x00-xff]', nam):
            nam = None
        nam = self.custom_config('television_name') or nam
        if not nam:
            sta = self.hass.states.get(self.entity_id)
            nam = sta.attributes.get(ATTR_FRIENDLY_NAME) if sta else None
        return nam or self.device_info.get('name', '电视')

    @property
    def bind_xiaoai(self):
        eid = self.custom_config('bind_xiaoai')
        if not eid or not self.hass:
            return None
        return self.hass.states.get(eid)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()

        if lip := self.custom_config('mitv_lan_host'):
            self._host = lip
            self._config = {**self._config, CONF_HOST: lip}
            self._device = None

        await self.async_update_apps()

        sva = self.custom_config_list('sources_via_apps')
        if self.custom_config('sources_via_apps') in [True, 'true', 'all', '*']:
            sva = list(self._apps.values())
        if sva:
            if not self.custom_config_bool('source_list_append', True):
                self._attr_source_list = []
            self._attr_source_list.extend(sva)
            self._vars['sources_via_apps'] = sva

        svk = self.custom_config_list('sources_via_keycodes')
        if self.custom_config('sources_via_keycodes') in [True, 'true', 'all', '*']:
            svk = [*self._keycodes]
        if svk:
            if not sva:
                self._attr_source_list = []
            self._attr_source_list.extend(svk)
            self._vars['sources_via_keycodes'] = svk

        if add_selects := self._add_entities.get('select'):
            from .select import SelectSubEntity
            sub = 'keycodes'
            self._subs[sub] = SelectSubEntity(self, sub, option={
                'options': self._keycodes,
                'select_option': self.press_key,
            })
            add_selects([self._subs[sub]], update_before_add=False)

        self._vars['homekit_remote_unsub'] = self.hass.bus.async_listen(
            EVENT_HOMEKIT_TV_REMOTE_KEY_PRESSED,
            self.async_homekit_remote_event_handler,
        )

    async def async_will_remove_from_hass(self):
        """Run when entity will be removed from hass.
        To be extended by integrations.
        """
        await super().async_will_remove_from_hass()
        if unsub := self._vars.pop('homekit_remote_unsub', None):
            unsub()

    async def async_update(self):
        await super().async_update()
        if not self._available:
            return
        adt = {}
        pms = self.with_opaque({
            'action': 'capturescreen',
            'compressrate': self.custom_config_integer('screenshot_compress') or 50,
        })
        prev_6095 = self._state_attrs.get('6095_state')
        rdt = await self.async_request_mitv_api('controller', params=pms)
        if 'url' in rdt:
            url = rdt.get('url', '')
            pms = urlparse(url).query
            url = f'{url}'.replace(pms, '')
            url = url.replace('//null:', f'//{self._host}:')
            url = url.replace('//0.0.0.0:', f'//{self._host}:')
            pms = dict(parse_qsl(pms))
            pms = self.with_opaque(pms, token=rdt.get('token'))
            self._attr_media_image_url = url + urlencode(pms)
            self._attr_app_id = rdt.get('pkg')
            self._attr_app_name = rdt.get('label')
            adt.update({
                'capture': self._attr_media_image_url,
                'capture_token': rdt.get('token'),
                'app_current': f'{self._attr_app_name} - {self._attr_app_id}',
                'app_page': rdt.get('clz'),
            })
        self._state_attrs.update(adt)

        if prev_6095 != self._state_attrs.get('6095_state'):
            await self.async_update_apps()

    async def async_update_apps(self):
        if not self._state_attrs.get('6095_state', True):
            return
        pms = {
            'action': 'getinstalledapp',
            'count': 999,
            'changeIcon': 1,
        }
        rdt = await self.async_request_mitv_api('controller', params=pms)
        if lst := rdt.get('AppInfo', []):
            self._apps = {
                a.get('PackageName'): a.get('AppName')
                for a in lst
            }
            als = [
                f'{v} - {k}'
                for k, v in self._apps.items()
            ]
            add_selects = self._add_entities.get('select')
            sub = 'apps'
            if sub in self._subs:
                self._subs[sub].update_options(als)
                self._subs[sub].update_from_parent()
            elif add_selects:
                from .select import SelectSubEntity
                self._subs[sub] = SelectSubEntity(self, 'app_current', option={
                    'options': als,
                    'select_option': self.start_app,
                })
                add_selects([self._subs[sub]], update_before_add=False)

    @property
    def state(self):
        sta = super().state
        if not self.cloud_only and not self._local_state:
            sta = None
        if self._speaker_mode_switch and self.custom_config_bool('turn_off_screen'):
            if self._speaker_mode_switch.from_dict(self._state_attrs):
                sta = MediaPlayerState.OFF
        return sta

    def turn_on(self):
        if self._local_state and self._state_attrs.get('6095_state'):
            # tv is on
            pass
        elif self._speaker_mode_switch:
            self.set_property(self._speaker_mode_switch, False)
        elif xai := self.bind_xiaoai:
            nam = self.mitv_name
            txt = f'{nam}亮屏' if self._local_state else f'打开{nam}'
            self.hass.services.call(DOMAIN, 'intelligent_speaker', {
                'entity_id': xai.entity_id,
                'text': txt,
                'execute': True,
                'silent': self.custom_config_bool('xiaoai_silent', True),
            })
        return super().turn_on()

    def turn_off(self):
        if self.custom_config_bool('turn_off_screen'):
            act = self._message_router.get_action('post') if self._message_router else None
            if self._speaker_mode_switch:
                return self.set_property(self._speaker_mode_switch, True)
            elif xai := self.bind_xiaoai:
                return self.hass.services.call(DOMAIN, 'intelligent_speaker', {
                    'entity_id': xai.entity_id,
                    'text': f'{self.mitv_name}熄屏',
                    'execute': True,
                    'silent': self.custom_config_bool('xiaoai_silent', True),
                })
            elif act:
                return self.call_action(act, ['熄屏'])
        return super().turn_off()

    async def async_play_media(self, media_type, media_id, **kwargs):
        """Play a piece of media."""
        tim = str(int(time.time() * 1000))
        pms = {
            'action': 'play',
            'type': media_type,
            'url': media_id,
            'apikey': self._api_key,
            'ts': tim,
            'sign': hashlib.md5(f'mitvsignsalt{media_id}{self._api_key}{tim[-5:]}'.encode()).hexdigest(),
        }
        rdt = await self.async_request_mitv_api('controller', params=pms)
        self.logger.info('%s: Play media: %s', self.name_model, [pms, rdt])

    @property
    def source(self):
        """Name of the current input source."""
        if self.app_name in self._vars.get('sources_via_apps', []):
            return self.app_name
        return super().source

    def select_source(self, source):
        """Select input source."""
        if source in self._apps:
            return self.start_app(self._apps[source])
        if source in self._apps.values():
            return self.start_app(source)
        if source in self._keycodes:
            ret = self.press_key(source)
            self._attr_app_name = source
            self.schedule_update_ha_state()
            return ret
        if source in self.source_list:
            return super().select_source(source)
        return False

    def start_app(self, app, **kwargs):
        pkg = f'{app}'.split(' - ').pop(-1).strip()
        if pkg not in self._apps:
            pkg = None
            for k, v in self._apps.items():
                if v == app:
                    pkg = k
                    break
        if pkg is None:
            return False
        pms = {
            'action': 'startapp',
            'type': 'packagename',
            'packagename': pkg,
        }
        return self.request_mitv_api('controller', params=pms)

    def press_key(self, key, **kwargs):
        if self._remote_ctrl:
            act = self._keycode_actions.get(key) or key
            if act := self._remote_ctrl.get_action(act):
                return self.call_action(act)
        pms = {
            'action': 'keyevent',
            'keycode': key,
        }
        return self.request_mitv_api('controller', params=pms)

    async def async_homekit_remote_event_handler(self, event):
        eid = event.data.get('entity_id')
        if eid != self.entity_id:
            return
        dic = {
            'arrow_up': 'up',
            'arrow_down': 'down',
            'arrow_left': 'left',
            'arrow_right': 'right',
            'back': 'back',
            'select': 'enter',
            'information': 'menu',
        }
        key = dic.get(event.data.get('key_name', ''))
        if not key:
            return
        return self.hass.async_add_executor_job(self.press_key, key)

    def with_opaque(self, pms: dict, token=None):
        if token is None:
            token = self._api_key
        pms.update({
            'timestamp': int(time.time() * 1000),
            'token': token,
        })
        pms['opaque'] = hmac.new(self._hmac_key.encode(), urlencode(pms).encode(), hashlib.sha1).hexdigest()
        pms.pop('token', None)
        return pms

    def mitv_api_path(self, path=''):
        return f'http://{self._host}:6095/{path.lstrip("/")}'

    def request_mitv_api(self, path, **kwargs):
        kwargs.setdefault('timeout', 5)
        req = None
        try:
            req = requests.get(self.mitv_api_path(path), **kwargs)
            rdt = json.loads(req.content or '{}') or {}
            self._state_attrs['6095_state'] = True
            if 'success' not in rdt.get('msg', ''):
                self.logger.warning('%s: Request mitv api error: %s', self.name_model, req.text)
        except requests.exceptions.RequestException as exc:
            rdt = {}
            if self._state_attrs.get('6095_state'):
                log = self.logger.info if 'NewConnectionError' in f'{exc}' else self.logger.warning
                log('%s: Request mitv api error: %s', self.name_model, exc)
            self._state_attrs['6095_state'] = False
        except json.decoder.JSONDecodeError:
            rdt = {}
            if req:
                self.logger.warning('%s: Invalid response data: %s with %s', req.content, kwargs)
        return rdt.get('data') or {}

    async def async_request_mitv_api(self, path, **kwargs):
        return await self.hass.async_add_executor_job(
            partial(self.request_mitv_api, path, **kwargs)
        )


class MiirMediaPlayerEntity(MiirToggleEntity, MediaPlayerEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(miot_service, config=config, logger=_LOGGER)

        if self._act_turn_on:
            self._supported_features |= MediaPlayerEntityFeature.TURN_ON
        if self._act_turn_off:
            self._supported_features |= MediaPlayerEntityFeature.TURN_OFF

        self._attr_is_volume_muted = None
        self._act_mute_on = miot_service.get_action('mute_on')
        self._act_mute_off = miot_service.get_action('mute_off')
        if self._act_mute_on or self._act_mute_off:
            self._supported_features |= MediaPlayerEntityFeature.VOLUME_MUTE

        self._attr_volume_level = 0.5
        self._act_volume_up = miot_service.get_action('volume_up')
        self._act_volume_dn = miot_service.get_action('volume_down')
        if self._act_volume_up or self._act_volume_dn:
            self._supported_features |= MediaPlayerEntityFeature.VOLUME_SET
            self._supported_features |= MediaPlayerEntityFeature.VOLUME_STEP

        if self._miot_actions:
            self._supported_features |= MediaPlayerEntityFeature.SELECT_SOURCE
            self._attr_source_list = self._miot_actions

    async def async_added_to_hass(self):
        await super().async_added_to_hass()

        if act := self._miot_service.get_action('set_channel_number'):
            prop = self._miot_service.get_property('channel_number')
            add_numbers = self._add_entities.get('number')
            if prop and add_numbers:
                from .number import MiotNumberActionSubEntity
                fnm = prop.unique_name
                self._subs[fnm] = MiotNumberActionSubEntity(self, prop, act)
                add_numbers([self._subs[fnm]], update_before_add=True)

    @property
    def state(self):
        """State of the player."""
        return None

    def mute_volume(self, mute):
        """Mute the volume."""
        ret = None
        if not mute and self._act_mute_off:
            ret = self.call_action(self._act_mute_off)
        elif mute and self._act_mute_on:
            ret = self.call_action(self._act_mute_on)
        if ret:
            self._attr_is_volume_muted = mute
        return ret

    def set_volume_level(self, volume):
        """Set volume level, range 0..1."""
        if volume > self._attr_volume_level and self._act_volume_up:
            return self.call_action(self._act_volume_up)
        elif volume < self._attr_volume_level and self._act_volume_dn:
            return self.call_action(self._act_volume_dn)
        raise NotImplementedError()

    def select_source(self, source):
        """Select input source."""
        if act := self._miot_service.get_action(source):
            return self.call_action(act)
        raise NotImplementedError()


class MiotDoorbellEntity(MiotMediaPlayerEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(config, miot_service)
