"""Support for Xiaomi WiFi speakers."""
import logging
import requests
import hashlib
import hmac
import time
import json
import voluptuous as vol
from datetime import timedelta
from functools import partial
from urllib.parse import urlencode, urlparse, parse_qsl

from homeassistant.const import *  # noqa: F401
from homeassistant.components.media_player import (
    DOMAIN as ENTITY_DOMAIN,
    MediaPlayerEntity,
    DEVICE_CLASS_TV,
    DEVICE_CLASS_SPEAKER,
    DEVICE_CLASS_RECEIVER,
)
from homeassistant.components.media_player.const import *
import homeassistant.helpers.config_validation as cv

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    XIAOMI_MIIO_SERVICE_SCHEMA,
    MiotEntityInterface,
    MiotEntity,
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
                vol.Optional('text', default=None): cv.string,
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
    model = str(config.get(CONF_MODEL) or '')
    entities = []
    miot = config.get('miot_type')
    if miot:
        spec = await MiotSpec.async_from_type(hass, miot)
        for srv in spec.get_services('play_control', 'doorbell'):
            if not srv.mapping() and not srv.get_action('play'):
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


class BaseMediaPlayerEntity(MediaPlayerEntity, MiotEntityInterface):
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
            self._supported_features |= SUPPORT_PLAY
        if miot_service.get_action('pause'):
            self._supported_features |= SUPPORT_PAUSE
        if miot_service.get_action('previous'):
            self._supported_features |= SUPPORT_PREVIOUS_TRACK
        if miot_service.get_action('next'):
            self._supported_features |= SUPPORT_NEXT_TRACK
        if miot_service.get_action('stop'):
            self._supported_features |= SUPPORT_STOP
        if self._prop_input:
            self._supported_features |= SUPPORT_SELECT_SOURCE
            self._attr_source_list = self._prop_input.list_descriptions()
        if self._prop_volume:
            self._supported_features |= SUPPORT_VOLUME_SET
        if self._prop_mute:
            self._supported_features |= SUPPORT_VOLUME_MUTE
        if self._act_turn_on:
            self._supported_features |= SUPPORT_TURN_ON
        if self._act_turn_off:
            self._supported_features |= SUPPORT_TURN_OFF

    @property
    def supported_features(self):
        return self._supported_features

    @property
    def device_class(self):
        typ = f'{self._model} {self._miot_service.spec.type}'
        if typ.find('speaker') >= 0:
            return DEVICE_CLASS_SPEAKER
        if typ.find('receiver') >= 0:
            return DEVICE_CLASS_RECEIVER
        if typ.find('tv') >= 0 or typ.find('television') >= 0:
            return DEVICE_CLASS_TV
        return None

    @property
    def state(self):
        if self._prop_state:
            sta = self._prop_state.from_dict(self._state_attrs)
            if sta is not None:
                if sta in self._prop_state.list_search('Playing', 'Play'):
                    return STATE_PLAYING
                if sta == self._prop_state.list_value('Pause'):
                    return STATE_PAUSED
                if sta == self._prop_state.list_value('Idle'):
                    return STATE_IDLE
                des = self._prop_state.list_description(sta)
                if des is not None:
                    return des
        if self.available:
            return STATE_IDLE
        return STATE_UNAVAILABLE

    @property
    def is_volume_muted(self):
        if self._prop_mute:
            return self._prop_mute.from_dict(self._state_attrs) and True
        return None

    def mute_volume(self, mute):
        if self._prop_mute:
            return self.set_property(self._prop_mute.full_name, True if mute else False)
        return False

    @property
    def volume_level(self):
        if self._prop_volume:
            return round(self._prop_volume.from_dict(self._state_attrs) or 0) / 100
        return None

    def set_volume_level(self, volume):
        if self._prop_volume:
            val = round(volume * (self._prop_volume.range_max() or 1))
            stp = self._prop_volume.range_step()
            if stp and stp > 1:
                val = round(val / stp) * stp
            return self.set_property(self._prop_volume.full_name, val)
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
        if self._intelligent_speaker:
            self._state_attrs[ATTR_ATTRIBUTION] = 'Support TTS through service'

    async def async_update(self):
        await super().async_update()
        if not self._available:
            return
        self._update_sub_entities('on', domain='switch')
        # deprecated
        self._update_sub_entities(
            ['input_control'],
            ['television', 'projector'],
            domain='fan',
        )

    def turn_on(self):
        if self._act_turn_on:
            return self.call_action(self._act_turn_on)
        return False

    def turn_off(self):
        if self._act_turn_off:
            return self.call_action(self._act_turn_off)
        return False

    def intelligent_speaker(self, text, execute=False, silent=False, **kwargs):
        srv = self._intelligent_speaker
        if srv:
            anm = 'execute_text_directive' if execute else 'play_text'
            act = srv.get_action(anm)
            if act:
                pms = [text]
                pse = srv.get_property('silent_execution')
                if execute and pse:
                    sil = silent and True
                    if pse.value_list:
                        sil = pse.list_value('On' if silent else 'Off')
                        if sil is None:
                            sil = 0 if silent else 1
                    pms.append(sil)
                return self.miot_action(srv.iid, act.iid, pms, **kwargs)
            else:
                _LOGGER.warning('%s does not have action: %s', self.name, anm)
        elif self._message_router:
            act = self._message_router.get_action('post')
            if act and execute:
                return self.call_action(act, [text], **kwargs)
        else:
            _LOGGER.error('%s does not have service: %s', self.name, 'intelligent_speaker/message_router')
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
                _LOGGER.warning('%s does not have action: %s', self.name, 'wake_up')
        else:
            _LOGGER.error('%s does not have service: %s', self.name, 'intelligent_speaker')
        return False

    async def async_xiaoai_wakeup(self, text=None, **kwargs):
        return await self.hass.async_add_executor_job(
            partial(self.xiaoai_wakeup, text, **kwargs)
        )



class MitvMediaPlayerEntity(MiotMediaPlayerEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(config, miot_service)
        self._host = self._config.get(CONF_HOST) or ''
        self._mitv_api = f'http://{self._host}:6095/'
        self._api_key = '881fd5a8c94b4945b46527b07eca2431'
        self._hmac_key = '2840d5f0d078472dbc5fb78e39da123e'
        self._state_attrs['6095_state'] = True
        self._keycodes = [
            'power',
            'home',
            'menu',
            'enter',
            'back',
            'up',
            'down',
            'left',
            'right',
            'volumeup',
            'volumedown',
        ]
        self._supported_features |= SUPPORT_PLAY_MEDIA

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if add_selects := self._add_entities.get('select'):
            from .select import SelectSubEntity
            sub = 'keycodes'
            self._subs[sub] = SelectSubEntity(self, sub, option={
                'options': self._keycodes,
                'select_option': self.press_key,
            })
            add_selects([self._subs[sub]])

    async def async_update(self):
        await super().async_update()
        if not self._available:
            return
        adt = {}

        pms = self.with_opaque({
            'action': 'capturescreen',
            'compressrate': 100,
        })
        rdt = await self.async_request_mitv_api('controller', params=pms)
        if 'url' in rdt:
            url = rdt.get('url', '')
            pms = urlparse(url).query
            url = f'{url}'.replace(pms, '').replace('//null:', f'//{self._host}:')
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

        if self._state_attrs.get('6095_state'):
            pms = {
                'action': 'getinstalledapp',
                'count': 999,
                'changeIcon': 1,
            }
            rdt = await self.async_request_mitv_api('controller', params=pms)
            if lst := rdt.get('AppInfo', []):
                ias = {
                    a.get('PackageName'): a.get('AppName')
                    for a in lst
                }
                als = [
                    f'{v} - {k}'
                    for k, v in ias.items()
                ]
                add_selects = self._add_entities.get('select')
                sub = 'apps'
                if sub in self._subs:
                    self._subs[sub].update_options(als)
                    self._subs[sub].update()
                elif add_selects:
                    from .select import SelectSubEntity
                    self._subs[sub] = SelectSubEntity(self, 'app_current', option={
                        'options': als,
                        'select_option': self.start_app,
                    })
                    add_selects([self._subs[sub]])

        self._state_attrs.update(adt)

    @property
    def state(self):
        sta = super().state
        if not self._state_attrs.get('6095_state') and self.conn_mode != 'cloud':
            sta = STATE_OFF
        return sta

    def turn_on(self):
        if eid := self.custom_config('bind_xiaoai'):
            nam = self.device_info.get('name')
            nam = self.custom_config('television_name', nam)
            if not nam:
                sta = self.hass.states.get(self.entity_id)
                nam = sta.attributes.get(ATTR_FRIENDLY_NAME)
            if nam and self.hass.states.get(eid):
                self.hass.services.call(DOMAIN, 'intelligent_speaker', {
                    'entity_id': eid,
                    'text': f'打开{nam}',
                    'execute': True,
                    'silent': self.custom_config_bool('xiaoai_silent', True),
                })
        return super().turn_on()

    @property
    def device_class(self):
        return DEVICE_CLASS_TV

    def play_media(self, media_type, media_id, **kwargs):
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
        rdt = self.request_mitv_api('controller', params=pms)
        self.logger.debug('%s: Play media: %s', self.name, [pms, rdt])
        return not not rdt

    def start_app(self, app, **kwargs):
        pkg = f'{app}'.split(' - ').pop(-1).strip()
        pms = {
            'action': 'startapp',
            'type': 'packagename',
            'packagename': pkg,
        }
        return self.request_mitv_api('controller', params=pms)

    def press_key(self, key, **kwargs):
        pms = {
            'action': 'keyevent',
            'keycode': key,
        }
        return self.request_mitv_api('controller', params=pms)

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

    def request_mitv_api(self, path, **kwargs):
        try:
            req = requests.get(f'{self._mitv_api}{path}', **kwargs)
            rdt = json.loads(req.content or '{}') or {}
            self._state_attrs['6095_state'] = True
            if 'success' not in rdt.get('msg', ''):
                self.logger.warning('%s: Request mitv api error: %s', self.name, req.text)
        except requests.exceptions.RequestException as exc:
            rdt = {}
            if self._state_attrs.get('6095_state'):
                self.logger.warning('%s: Request mitv api error: %s', self.name, exc)
            self._state_attrs['6095_state'] = False
        return rdt.get('data') or {}

    async def async_request_mitv_api(self, path, **kwargs):
        return await self.hass.async_add_executor_job(
            partial(self.request_mitv_api, path, **kwargs)
        )


class MiotDoorbellEntity(MiotMediaPlayerEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(config, miot_service)
