"""Support for Xiaomi vacuums."""
import logging
from datetime import timedelta

from homeassistant.const import *  # noqa: F401
from homeassistant.components.vacuum import (  # noqa: F401
    DOMAIN as ENTITY_DOMAIN,
    StateVacuumEntity,
    SUPPORT_TURN_ON,
    SUPPORT_TURN_OFF,
    SUPPORT_PAUSE,
    SUPPORT_STOP,
    SUPPORT_RETURN_HOME,
    SUPPORT_FAN_SPEED,
    SUPPORT_BATTERY,
    SUPPORT_STATUS,
    SUPPORT_SEND_COMMAND,
    SUPPORT_LOCATE,
    SUPPORT_CLEAN_SPOT,
    SUPPORT_MAP,
    SUPPORT_STATE,
    SUPPORT_START,
    STATE_CLEANING,
    STATE_DOCKED,
    STATE_RETURNING,
    STATE_ERROR,
)

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
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
        for srv in spec.get_services(ENTITY_DOMAIN):
            if not srv.get_property('status'):
                continue
            cfg = {
                **config,
                'name': f"{config.get('name')} {srv.description}"
            }
            entities.append(MiotVacuumEntity(cfg, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotVacuumEntity(MiotEntity, StateVacuumEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(miot_service, config=config)

        self._prop_power = miot_service.get_property('on', 'power')
        self._prop_status = miot_service.get_property('status')
        self._prop_mode = miot_service.get_property('fan_level', 'mode')
        self._act_start = miot_service.get_action('start_sweep')
        self._act_pause = miot_service.get_action('pause_sweeping')
        self._act_stop = miot_service.get_action('stop_sweeping')
        self._act_locate = miot_service.get_action('position')
        self._prop_battery = miot_service.get_property('battery_level')
        self._srv_battery = miot_service.spec.get_service('battery')
        if self._srv_battery:
            self._prop_battery = self._srv_battery.get_property('battery_level')
        self._srv_audio = miot_service.spec.get_service('audio', 'voice')
        if self._srv_audio and not self._act_locate:
            self._act_locate = self._srv_battery.get_property('position', 'find_device')
        self._act_charge = None
        for srv in [*miot_service.spec.get_services('battery', 'go_charging'), miot_service]:
            act = srv.get_action('start_charge', 'start_charging')
            if act:
                self._act_charge = act
                break

        if self._prop_power:
            self._supported_features |= SUPPORT_TURN_ON
            self._supported_features |= SUPPORT_TURN_OFF
        if self._act_start:
            self._supported_features |= SUPPORT_START
        if self._act_pause:
            self._supported_features |= SUPPORT_PAUSE
        if self._act_stop:
            self._supported_features |= SUPPORT_STOP
        if self._act_charge:
            self._supported_features |= SUPPORT_RETURN_HOME
        if self._prop_mode:
            self._supported_features |= SUPPORT_FAN_SPEED
        if self._prop_battery:
            self._supported_features |= SUPPORT_BATTERY
        if self._prop_status:
            self._supported_features |= SUPPORT_STATUS
            self._supported_features |= SUPPORT_STATE
        if self._act_locate:
            self._supported_features |= SUPPORT_LOCATE

        self._state_attrs.update({'entity_class': self.__class__.__name__})

    @property
    def status(self):
        if self._prop_status:
            val = self._prop_status.from_dict(self._state_attrs)
            if val is not None:
                return self._prop_status.list_description(val)
        return None

    @property
    def state(self):
        if self._prop_status:
            val = self._prop_status.from_dict(self._state_attrs)
            if val is None:
                pass
            elif val in self._prop_status.list_search(
                'Cleaning', 'Sweeping', 'Mopping', 'Sweeping and Mopping',
                'Part Sweeping', 'Zone Sweeping', 'Select Sweeping',
                'Working', 'Busy',
            ):
                return STATE_CLEANING
            elif val in self._prop_status.list_search('Idle', 'Sleep', 'Charging'):
                return STATE_DOCKED
            elif val in self._prop_status.list_search('Go Charging'):
                return STATE_RETURNING
            elif val in self._prop_status.list_search('Paused'):
                return STATE_PAUSED
            elif val in self._prop_status.list_search('Error'):
                return STATE_ERROR
        return None

    @property
    def battery_level(self):
        if self._prop_battery:
            return self._prop_battery.from_dict(self._state_attrs)
        return None

    def turn_on(self, **kwargs):
        if self._prop_power:
            self.set_property(self._prop_power.full_name, True)
        return self.start()

    def turn_off(self, **kwargs):
        return self.stop()

    def start(self):
        if self._act_start:
            return self.miot_action(self._act_start.service.iid, self._act_start.iid)
        return False

    def stop(self, **kwargs):
        if self._act_stop:
            return self.miot_action(self._act_stop.service.iid, self._act_stop.iid)
        return False

    def pause(self):
        if self._act_pause:
            return self.miot_action(self._act_pause.service.iid, self._act_pause.iid)
        return self.stop()

    def start_pause(self, **kwargs):
        sta = self.state
        if sta == STATE_CLEANING:
            return self.pause()
        return self.start()

    def return_to_base(self, **kwargs):
        if self._act_charge:
            return self.miot_action(self._act_charge.service.iid, self._act_charge.iid)
        return self.stop()

    def locate(self, **kwargs):
        if self._act_locate:
            return self.miot_action(self._act_locate.service.iid, self._act_locate.iid)
        return False

    def clean_spot(self, **kwargs):
        raise NotImplementedError()

    @property
    def fan_speed(self):
        if self._prop_mode:
            val = self._prop_mode.from_dict(self._state_attrs)
            if val is not None:
                return self._prop_mode.list_description(val)
        return None

    @property
    def fan_speed_list(self):
        if self._prop_mode:
            return self._prop_mode.list_description(None) or []
        return None

    def set_fan_speed(self, fan_speed, **kwargs):
        if self._prop_mode:
            val = self._prop_mode.list_value(fan_speed)
            return self.set_property(self._prop_mode.full_name, val)
        return False
