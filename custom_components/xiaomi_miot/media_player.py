"""Support for Xiaomi WiFi speakers."""
import logging
import voluptuous as vol
from datetime import timedelta
from functools import partial

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
    MiotToggleEntity,
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
        for srv in spec.get_services('play_control'):
            if not srv.mapping():
                continue
            cfg = {
                **config,
                'name': f"{config.get('name')} {srv.description}"
            }
            entities.append(MiotMediaPlayerEntity(cfg, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotMediaPlayerEntity(MiotToggleEntity, MediaPlayerEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(miot_service, config=config)

        self._prop_state = miot_service.get_property('playing_state')
        self._speaker = miot_service.spec.get_service('speaker')
        self._prop_volume = self._speaker.get_property('volume')
        self._prop_mute = self._speaker.get_property('mute')
        self._act_turn_on = None
        self._act_turn_off = None
        for srv in miot_service.spec.services:
            act = srv.get_action('turn_on')
            if act:
                self._act_turn_on = act
            act = srv.get_action('turn_off')
            if act:
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
        if self._prop_volume:
            self._supported_features |= SUPPORT_VOLUME_SET
        if self._prop_mute:
            self._supported_features |= SUPPORT_VOLUME_MUTE
        if self._act_turn_on:
            self._supported_features |= SUPPORT_TURN_ON
        if self._act_turn_off:
            self._supported_features |= SUPPORT_TURN_OFF

        self._state_attrs.update({'entity_class': self.__class__.__name__})

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
                if sta == self._prop_state.list_value('Playing'):
                    return STATE_PLAYING
                if sta == self._prop_state.list_value('Pause'):
                    return STATE_PAUSED
                if sta == self._prop_state.list_value('Idle'):
                    return STATE_IDLE
        if self.available:
            return STATE_UNKNOWN
        return STATE_UNAVAILABLE

    def turn_on(self):
        if self._act_turn_on:
            return self.miot_action(self._act_turn_on.service.iid, self._act_turn_on.iid)
        return False

    def turn_off(self):
        if self._act_turn_off:
            return self.miot_action(self._act_turn_off.service.iid, self._act_turn_off.iid)
        return False

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
            vol = round(volume * (self._prop_volume.range_max() or 1))
            stp = self._prop_volume.range_step()
            if stp and stp > 1:
                vol = round(vol / stp) * stp
            return self.set_property(self._prop_volume.full_name, vol)
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

    def select_source(self, source):
        return False

    def select_sound_mode(self, sound_mode):
        return False

    def clear_playlist(self):
        return False

    def set_shuffle(self, shuffle):
        return False

    def set_repeat(self, repeat):
        return False

    def intelligent_speaker(self, text, execute=False, silent=False, **kwargs):
        srv = self._miot_service.spec.get_service('intelligent_speaker')
        if srv:
            anm = 'execute_text_directive' if execute else 'play_text'
            act = srv.get_action(anm)
            if act:
                pms = [text]
                if execute:
                    pms.append(0 if silent else 1)
                return self.miot_action(srv.iid, act.iid, pms, **kwargs)
            else:
                _LOGGER.warning('%s have no action: %s', self.name, anm)
        else:
            _LOGGER.warning('%s have no service: %s', self.name, 'intelligent_speaker')
        return False

    async def async_intelligent_speaker(self, text, execute=False, silent=False, **kwargs):
        return await self.hass.async_add_executor_job(
            partial(self.intelligent_speaker, text, execute, silent, **kwargs)
        )
