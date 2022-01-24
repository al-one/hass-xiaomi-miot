"""Support for Xiaomi vacuums."""
import logging
from datetime import timedelta
from functools import partial

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
    MIOT_LOCAL_MODELS,
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
    entities = []
    if miot := config.get('miot_type'):
        spec = await MiotSpec.async_from_type(hass, miot)
        for srv in spec.get_services(ENTITY_DOMAIN, 'mopping_machine'):
            if not srv.get_property('status'):
                continue
            if model in MIOT_LOCAL_MODELS:
                entities.append(MiotVacuumEntity(config, srv))
            elif 'roborock.' in model or 'rockrobo.' in model:
                entities.append(MiotRoborockVacuumEntity(config, srv))
            elif 'viomi.' in model:
                entities.append(MiotViomiVacuumEntity(config, srv))
            else:
                entities.append(MiotVacuumEntity(config, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotVacuumEntity(MiotEntity, StateVacuumEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(miot_service, config=config, logger=_LOGGER)

        self._prop_power = miot_service.get_property('on', 'power')
        self._prop_status = miot_service.get_property('status')
        self._prop_mode = miot_service.get_property('fan_level', 'speed_level', 'mode')
        self._act_start = miot_service.get_action('start_sweep')
        self._act_pause = miot_service.get_action('pause_sweeping', 'pause')
        self._act_stop = miot_service.get_action('stop_sweeping')
        self._act_locate = miot_service.get_action('find_device', 'position')
        self._prop_battery = miot_service.get_property('battery_level')
        self._srv_battery = miot_service.spec.get_service('battery')
        if self._srv_battery:
            self._prop_battery = self._srv_battery.get_property('battery_level')
        self._srv_audio = miot_service.spec.get_service('audio', 'voice')
        if self._srv_audio and not self._act_locate:
            self._act_locate = self._srv_audio.get_action('find_device', 'position')
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
            elif val in self._prop_status.list_search('Idle', 'Sleep', 'Charging', 'Fullcharge'):
                return STATE_DOCKED
            elif val in self._prop_status.list_search('Go Charging'):
                return STATE_RETURNING
            elif val in self._prop_status.list_search('Paused'):
                return STATE_PAUSED
            elif val in self._prop_status.list_search('Error'):
                return STATE_ERROR
            else:
                return self._prop_status.list_description(val)
        return None

    @property
    def battery_level(self):
        if self._prop_battery:
            return self._prop_battery.from_dict(self._state_attrs)
        return None

    def turn_on(self, **kwargs):
        if self._prop_power:
            self.set_property(self._prop_power, True)
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
            try:
                val = int(val)
            except (TypeError, ValueError):
                val = None
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
            return self.set_property(self._prop_mode, val)
        return False

    def send_vacuum_command(self, command, params=None, **kwargs):
        """Send a command to a vacuum cleaner."""
        raise NotImplementedError()

    async def async_send_command(self, command, params=None, **kwargs):
        """Send a command to a vacuum cleaner.
        This method must be run in the event loop.
        """
        await self.hass.async_add_executor_job(
            partial(self.send_vacuum_command, command, params=params, **kwargs)
        )


class MiotRoborockVacuumEntity(MiotVacuumEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(config, miot_service)
        self._supported_features |= SUPPORT_LOCATE
        self._miio_commands = {
            'get_status': ['props'],
            'get_consumable': ['consumables'],
        }

    async def async_update(self):
        await super().async_update()
        if not self._available:
            return
        await self.hass.async_add_executor_job(partial(self.update_miio_commands, self._miio_commands))
        props = self.miio_props
        adt = {}
        if 'clean_area' in props:
            adt['clean_area'] = round(props['clean_area'] / 1000000, 1)
        if 'clean_time' in props:
            adt['clean_time'] = round(props['clean_time'] / 60, 1)
        if adt:
            await self.async_update_attrs(adt)

    @property
    def miio_props(self):
        return self._state_attrs.get('props') or {}

    @property
    def state(self):
        sta = super().state
        if sta is not None:
            return sta
        states = {
            1: STATE_CLEANING,  # Starting
            2: 'Charger disconnected',
            3: STATE_DOCKED,    # Idle
            4: STATE_CLEANING,  # Remote control active
            5: STATE_CLEANING,
            6: STATE_RETURNING,
            7: 'Manual mode',
            8: STATE_DOCKED,  # Charging
            9: STATE_ERROR,   # Charging problem
            10: STATE_PAUSED,
            11: STATE_CLEANING,  # Spot cleaning
            12: STATE_ERROR,
            13: 'Shutting down',
            14: STATE_DOCKED,     # Updating
            15: STATE_RETURNING,  # Docking
            16: STATE_CLEANING,   # Going to target
            17: STATE_CLEANING,   # Zoned cleaning
            18: STATE_CLEANING,   # Segment cleaning
            100: STATE_DOCKED,    # Charging complete
            101: 'Device offline',
        }
        sta = self.miio_props.get('state')
        sta = states.get(sta, sta)
        return sta

    @property
    def battery_level(self):
        val = super().battery_level
        if val is not None:
            return val
        return self.miio_props.get('battery')

    def clean_spot(self, **kwargs):
        """Perform a spot clean-up."""
        return self.send_miio_command('app_spot')

    def locate(self, **kwargs):
        """Locate the vacuum cleaner."""
        if not self._act_locate:
            return self.send_miio_command('find_me', [''])
        return super().locate()

    def send_vacuum_command(self, command, params=None, **kwargs):
        """Send a command to a vacuum cleaner."""
        dvc = self.miot_device
        if not dvc:
            raise NotImplementedError()
        return self.send_miio_command(command, params)


class MiotViomiVacuumEntity(MiotVacuumEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(config, miot_service)
        self._supported_features |= SUPPORT_LOCATE
        self._miio_props = [
            'run_state', 'mode', 'err_state', 'battary_life', 'box_type', 'mop_type', 's_time', 's_area',
            'suction_grade', 'water_grade', 'remember_map', 'has_map', 'is_mop', 'has_newmap',
        ]

    async def async_update(self):
        await super().async_update()
        if not self._available:
            return
        await self.hass.async_add_executor_job(partial(self.update_miio_props, self._miio_props))
        props = self._state_attrs or {}
        adt = {}
        if 'miio.s_area' in props:
            adt['clean_area'] = props['miio.s_area']
        if 'miio.s_time' in props:
            adt['clean_time'] = props['miio.s_time']
        if adt:
            await self.async_update_attrs(adt)

    def locate(self, **kwargs):
        """Locate the vacuum cleaner."""
        if not self._act_locate:
            return self.send_miio_command('set_resetpos', [1])
        return super().locate()

    def send_vacuum_command(self, command, params=None, **kwargs):
        """Send a command to a vacuum cleaner."""
        dvc = self.miot_device
        if not dvc:
            raise NotImplementedError()
        _LOGGER.debug('Send command to %s: %s %s', self.name, command, params)
        if command == 'app_zoned_clean':
            rpt = 1
            lst = []
            for z in params or []:
                rpt = z.pop(-1)
                lst.append(z)
            return self.clean_zones(lst, rpt)
        elif command == 'app_goto_target':
            return self.clean_point(params)
        return self.send_miio_command(command, params)

    def clean_zones(self, zones, repeats=1):
        result = []
        i = 0
        for z in zones:
            x1, y2, x2, y1 = z
            res = '_'.join(str(x) for x in [i, 0, x1, y1, x1, y2, x2, y2, x2, y1])
            for _ in range(repeats):
                result.append(res)
                i += 1
        result = [i, *result]
        self.send_miio_command('set_uploadmap', [1])
        self.send_miio_command('set_zone', result)
        return self.send_miio_command('set_mode', [3, 1])

    def clean_point(self, point):
        self.send_miio_command('set_uploadmap', [0])
        return self.send_miio_command('set_pointclean', [1, *point])
