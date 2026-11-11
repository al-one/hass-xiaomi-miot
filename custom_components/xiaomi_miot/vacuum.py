"""Support for Xiaomi vacuums."""
import json
import logging
import asyncio
from datetime import timedelta

from homeassistant.components.vacuum import (  # noqa: F401
    DOMAIN as ENTITY_DOMAIN,
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,  # v2022.5
)
from homeassistant.exceptions import HomeAssistantError

try:
    from homeassistant.components.vacuum import Segment
except ImportError:  # Room cleaning is unavailable on older supported HA versions.
    Segment = None

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    HassEntry,
    MiotEntity,
    MIOT_LOCAL_MODELS,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.utils import DeviceException
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
    _entity_domain = ENTITY_DOMAIN
    _attr_activity = None

    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(miot_service, config=config, logger=_LOGGER)

        self._prop_power = miot_service.get_property('on', 'power')
        self._prop_status = miot_service.get_property('status')
        self._act_start = miot_service.get_action('start_sweep', 'start_mop')
        self._act_pause = miot_service.get_action('pause_sweeping', 'pause')
        self._act_stop = miot_service.get_action('stop_sweeping')
        self._act_locate = miot_service.get_action('find_device', 'position')
        self._prop_mode = miot_service.get_property('mode', 'clean_mode')
        self._prop_fan = self._prop_mode
        for srv in [*miot_service.spec.get_services('sweep', 'clean'), miot_service]:
            if prop := srv.get_property('fan_level', 'speed_level', 'suction_state', 'fan_mode', 'mode'):
                self._prop_fan = prop
                break
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

        # Room cleaning.  Newer MIoT vacuums use room_information plus
        # get_room_configs; older ijai vacuums expose the map room list and
        # set-room-clean instead.  Detect both from the MIoT spec.
        self._srv_map = miot_service.spec.get_service('map')
        self._prop_cur_map_id = self._srv_map.get_property('cur_map_id') if self._srv_map else None
        self._act_get_map_room_list = (
            self._srv_map.get_action('get_map_room_list') if self._srv_map else None
        )
        self._srv_sweep = miot_service.spec.get_service('sweep', 'clean')
        self._act_set_room_clean = (
            self._srv_sweep.get_action('set_room_clean') if self._srv_sweep else None
        )
        self._prop_clean_room_ids = (
            self._srv_sweep.get_property('clean_room_ids') if self._srv_sweep else None
        )
        self._prop_clean_room_mode = (
            self._srv_sweep.get_property('clean_room_mode') if self._srv_sweep else None
        )
        self._prop_clean_room_oper = (
            self._srv_sweep.get_property('clean_room_oper') if self._srv_sweep else None
        )
        self._act_start_room_sweep = miot_service.get_action('start_room_sweep')
        self._prop_sweep_mop_type = miot_service.get_property('sweep_mop_type')
        self._prop_room_information = miot_service.get_property('room_information')
        self._act_get_room_configs = miot_service.get_action('get_room_configs')
        self._act_set_room_clean_configs = miot_service.get_action(
            'set_room_clean_configs'
        )

        if self._prop_power:
            self._supported_features |= VacuumEntityFeature.TURN_ON
            self._supported_features |= VacuumEntityFeature.TURN_OFF
        if self._act_start:
            self._supported_features |= VacuumEntityFeature.START
        if self._act_pause:
            self._supported_features |= VacuumEntityFeature.PAUSE
        if self._act_stop:
            self._supported_features |= VacuumEntityFeature.STOP
        if self._act_charge:
            self._supported_features |= VacuumEntityFeature.RETURN_HOME
        if self._prop_fan:
            self._supported_features |= VacuumEntityFeature.FAN_SPEED
        if self._prop_status:
            self._supported_features |= VacuumEntityFeature.STATUS
            self._supported_features |= VacuumEntityFeature.STATE
        if self._act_locate:
            self._supported_features |= VacuumEntityFeature.LOCATE
        if self.supports_room_cleaning:
            self._supported_features |= VacuumEntityFeature.CLEAN_AREA
        self._supported_features |= VacuumEntityFeature.SEND_COMMAND

    @property
    def supports_room_cleaning(self):
        if Segment is None:
            return False
        if self._prop_room_information and self._act_get_room_configs:
            return bool(
                self._act_start_room_sweep or self._act_set_room_clean_configs
            )
        return bool(
            self._act_get_map_room_list
            and self._prop_cur_map_id
            and self._prop_clean_room_ids
            and (self._act_set_room_clean or self._act_start_room_sweep)
        )

    async def async_get_segments(self):
        """Return rooms exposed by the vacuum map."""
        if not self.supports_room_cleaning:
            return []

        if self._prop_room_information and self._act_get_room_configs:
            in_properties = self._act_get_room_configs.in_properties()
            params = self._act_get_room_configs.in_params_from_attrs(
                {in_properties[0].full_name: ''}
            ) if in_properties else []
            result = await self.async_call_action(
                self._act_get_room_configs, params, force_params=True
            )
            if not result.is_success:
                raise HomeAssistantError('Unable to refresh vacuum rooms')
            props = await self.device.async_get_properties(
                [{'siid': self._prop_room_information.service.iid,
                  'piid': self._prop_room_information.iid}],
                update_entity=True,
                throw=True,
            )
            value = props.get(self._prop_room_information.full_name)
            segments = _parse_room_information(value)
        else:
            map_id = self._prop_cur_map_id.from_device(self.device)
            if map_id is None:
                map_id = self._state_attrs.get(self._prop_cur_map_id.full_name)
            if map_id is None:
                raise HomeAssistantError('Unable to read vacuum map id')
            try:
                map_id = int(map_id)
            except (TypeError, ValueError):
                pass
            result = await self.async_call_action(
                self._act_get_map_room_list, [map_id]
            )
            if not result.is_success:
                raise HomeAssistantError('Unable to read vacuum rooms')
            out = result.get('out') or []
            value = out[0].get('value') if out and isinstance(out[0], dict) else None
            segments = _parse_map_room_list(value)

        self._state_attrs['room_mapping'] = [
            [segment.id, segment.id, segment.name] for segment in segments
        ]
        return segments

    async def async_clean_segments(self, segment_ids, **kwargs):
        """Send the vacuum to the selected room ids."""
        if not segment_ids or not self.supports_room_cleaning:
            return False

        ids = ','.join(str(segment_id) for segment_id in segment_ids)
        if self._act_set_room_clean:
            # Older ijai vacuums start room cleaning directly with the room
            # ids, cleaning mode (global/edge) and operation (start).
            mode = 0
            if self._prop_clean_room_mode and self._prop_clean_room_mode.value_list:
                mode = self._prop_clean_room_mode.value_list[0].get('value', 0)
            params = self._act_set_room_clean.in_params([ids, mode, 1])
            result = await self.async_call_action(
                self._act_set_room_clean, params, force_params=True
            )
        else:
            if self._act_set_room_clean_configs:
                prop = self._prop_sweep_mop_type
                if not prop:
                    raise HomeAssistantError(
                        'Vacuum room cleaning requires a cleaning mode'
                    )
                values = await self.device.async_get_properties(
                    [{'siid': prop.service.iid, 'piid': prop.iid}], throw=True,
                )
                mode = values.get(prop.full_name)
                if (isinstance(mode, bool) or not isinstance(mode, int)
                        or (prop.value_list and mode not in [
                            v['value'] for v in prop.value_list
                        ])):
                    raise HomeAssistantError('Unable to read vacuum cleaning mode')
                config = _room_clean_config(segment_ids, mode)
                params = self._act_set_room_clean_configs.in_params([config])
                result = await self.async_call_action(
                    self._act_set_room_clean_configs, params, force_params=True
                )
                if not result.is_success:
                    raise HomeAssistantError(
                        'Unable to configure vacuum room cleaning'
                    )
            params = self._act_start_room_sweep.in_params([ids])
            result = await self.async_call_action(
                self._act_start_room_sweep, params, force_params=True
            )
        if not result.is_success:
            raise HomeAssistantError('Unable to start vacuum room cleaning')
        return True

    async def async_update(self):
        await super().async_update()
        if not self._available:
            return
        if self._prop_status:
            self._prop_status.description_to_dict(self._state_attrs)
            val = self._prop_status.from_device(self.device)
            if val is None:
                pass
            elif val in self._prop_status.list_search(
                'Cleaning', 'Sweeping', 'Mopping', 'Sweeping And Mopping', 'Sweeping and Mopping',
                'Washing', 'Go Washing',
                'Part Sweeping', 'Zone Sweeping', 'Select Sweeping', 'Spot Sweeping', 'Goto Target',
                'Starting', 'Working', 'Busy', 'DustCollecting'
            ):
                self._attr_activity = VacuumActivity.CLEANING
            elif val in self._prop_status.list_search('Idle', 'Sleep'):
                self._attr_activity = VacuumActivity.IDLE
            elif val in self._prop_status.list_search(
                'Charging', 'Charging Completed', 'Fullcharge', 'Charge Done', 'Charged', 'Drying',
                'MultiTaskStationWorking', 'StationWorking', 'MultiTaskRecharge', 'WashBreak',
            ):
                self._attr_activity = VacuumActivity.DOCKED
            elif val in self._prop_status.list_search('Go Charging', 'GoWash', 'Go Wash'):
                self._attr_activity = VacuumActivity.RETURNING
            elif val in self._prop_status.list_search('Paused'):
                self._attr_activity = VacuumActivity.PAUSED
            elif val in self._prop_status.list_search('Error', 'Charging Problem'):
                self._attr_activity = VacuumActivity.ERROR
            else:
                self._attr_activity = VacuumActivity.IDLE

    async def async_turn_on(self, **kwargs):
        if self._prop_power:
            await self.async_set_property(self._prop_power, True)
        return await self.async_start()

    async def async_turn_off(self, **kwargs):
        return await self.async_stop()

    async def async_start(self):
        if self._act_start:
            return await self.async_call_action(self._act_start)
        return False

    async def async_stop(self, **kwargs):
        if self._act_stop:
            return await self.async_call_action(self._act_stop)
        return False

    async def async_pause(self):
        if self._act_pause:
            return await self.async_call_action(self._act_pause)
        return await self.async_stop()

    async def async_return_to_base(self, **kwargs):
        if self._act_charge:
            return await self.async_call_action(self._act_charge)
        return self.stop()

    async def async_locate(self, **kwargs):
        if self._act_locate:
            return await self.async_call_action(self._act_locate)
        return False

    def clean_spot(self, **kwargs):
        raise NotImplementedError()

    @property
    def fan_speed(self):
        if self._prop_fan:
            val = self._prop_fan.from_device(self.device)
            try:
                val = int(val)
            except (TypeError, ValueError):
                val = None
            if val is not None:
                return self._prop_fan.list_description(val)
        return None

    @property
    def fan_speed_list(self):
        if self._prop_fan:
            return self._prop_fan.list_description(None) or []
        return None

    async def async_set_fan_speed(self, fan_speed, **kwargs):
        if self._prop_fan:
            val = self._prop_fan.list_value(fan_speed)
            return await self.async_set_property(self._prop_fan, val)
        return False

    async def async_send_command(self, command, params=None, **kwargs):
        """Send a command to a vacuum cleaner.
        This method must be run in the event loop.
        """
        return await self.async_miio_command(command, params)


def _parse_room_information(value):
    """Convert a MIoT room_information property into HA segments."""
    if Segment is None or not value:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return []
    if not isinstance(value, dict):
        return []
    rooms = value.get('rooms')
    if not isinstance(rooms, list):
        return []
    segments = []
    for room in rooms:
        if not isinstance(room, dict) or room.get('id') is None:
            continue
        name = room.get('name') or str(room['id'])
        segments.append(Segment(id=str(room['id']), name=str(name)))
    return segments


def _parse_map_room_list(value):
    """Convert a MIoT map room list into HA segments."""
    if Segment is None or not value:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return []
    if not isinstance(value, list):
        return []
    segments = []
    for room in value:
        if not isinstance(room, dict) or room.get('id') is None:
            continue
        name = room.get('name') or str(room['id'])
        segments.append(Segment(id=str(room['id']), name=str(name)))
    return segments


def _room_clean_config(segment_ids, clean_mode):
    """Build the room-cleaning configuration used by newer MIoT vacuums."""
    rooms = []
    for segment_id in segment_ids:
        try:
            rooms.append(int(segment_id))
        except (TypeError, ValueError):
            rooms.append(str(segment_id))
    return json.dumps({
        'rooms': rooms,
        'clean_mode': clean_mode,
        'is_ai_cleaning': False,
    }, separators=(',', ':'))


class MiotRoborockVacuumEntity(MiotVacuumEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(config, miot_service)
        self._supported_features |= VacuumEntityFeature.PAUSE
        self._supported_features |= VacuumEntityFeature.LOCATE
        self._supported_features |= VacuumEntityFeature.SEND_COMMAND

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        rooms = await self.get_room_mapping() or []

        if add_buttons := self.device.entry.adders.get('button'):
            from .button import ButtonSubEntity
            for r in rooms:
                if len(r) < 3:
                    continue
                rid = r[0]
                sub = f'segment_{rid}'
                self._subs[sub] = ButtonSubEntity(self, sub, option={
                    'name': f'{self.device_name} {r[2]}',
                    'async_press_action': self.async_start_clean_segment,
                    'press_kwargs': {'segment': rid},
                    'state_attrs': {'room_id': r[1]},
                })
                add_buttons([self._subs[sub]], update_before_add=False)
        self.logger.info('Room buttons: %s', [rooms, add_buttons])

    async def async_update(self):
        await super().async_update()
        if not self._available:
            return
        if self._miio2miot:
            self._state_attrs['props'] = self._miio2miot.miio_props_values
        props = self.miio_props
        adt = {}
        if 'clean_area' in props:
            adt['clean_area'] = round(props['clean_area'] / 1000000, 1)
        if 'clean_time' in props:
            adt['clean_time'] = round(props['clean_time'] / 60, 1)
        if adt:
            await self.async_update_attrs(adt)
            self.device.dispatch(self.device.decode_attrs({'props': props}))

    async def get_room_mapping(self):
        if not self.miot_device:
            return None
        try:
            rooms = await self.miot_device.async_send('get_room_mapping')
            if rooms and rooms != 'unknown_method':
                homes = await self.xiaomi_cloud.async_get_homerooms() if self.xiaomi_cloud else []
                cloud_rooms = {}
                for home in homes:
                    for room in home.get('roomlist', []):
                        cloud_rooms[room['id']] = room
                for r in rooms:
                    room = cloud_rooms.get(r[1])
                    name = room['name'] if room else r[0]
                    if len(r) < 3:
                        r.append(name)
                    else:
                        r[2] = name
                self._state_attrs['room_mapping'] = rooms
                self.logger.info('Vacuum rooms: %s', rooms)
                return rooms
            self.logger.info('Vacuum rooms: %s', rooms)
        except (DeviceException, Exception):
            pass
        return None

    @property
    def miio_props(self):
        return self._state_attrs.get('props') or {}

    async def async_pause(self):
        """Pause the cleaning task."""
        if not self._act_pause:
            return await self.async_miio_command('app_pause')
        return await super().async_pause()

    async def async_return_to_base(self, **kwargs):
        if self.model in ['rockrobo.vacuum.v1']:
            await self.async_stop()
        return await super().async_return_to_base()

    async def async_clean_spot(self, **kwargs):
        """Perform a spot clean-up."""
        if self._miio2miot:
            return await self.async_miio_command('app_spot')
        return await super().async_clean_spot()

    async def async_locate(self, **kwargs):
        """Locate the vacuum cleaner."""
        if not self._act_locate:
            return await self.async_miio_command('find_me', [''])
        return await super().async_locate()

    async def async_send_command(self, command, params=None, **kwargs):
        """Send a command to a vacuum cleaner."""
        dvc = self.miot_device
        if not dvc:
            raise NotImplementedError()
        return await self.async_miio_command(command, params)

    async def async_start_clean_segment(self, segment, repeat=1, **kwargs):
        segments = []
        for r in self._state_attrs.get('room_mapping', []):
            if segment in r:
                segments.append(r[0])
                break
        if not segments:
            await self.async_return_to_base()
            return False
        if self.state == VacuumActivity.CLEANING:
            await self.async_pause()
            await asyncio.sleep(1)
        if self.model in ['roborock.vacuum.m1s']:
            return await self.async_miio_command('app_segment_clean', segments)
        return await self.async_miio_command('app_segment_clean', [{'segments': segments, 'repeat': repeat}])


class MiotViomiVacuumEntity(MiotVacuumEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(config, miot_service)
        self._supported_features |= VacuumEntityFeature.LOCATE
        self._supported_features |= VacuumEntityFeature.SEND_COMMAND
        self._miio_props = [
            'run_state', 'mode', 'err_state', 'battary_life', 'box_type', 'mop_type', 's_time', 's_area',
            'suction_grade', 'water_grade', 'remember_map', 'has_map', 'is_mop', 'has_newmap',
        ]

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if self._miio2miot:
            self._miio2miot.extend_miio_props(self._miio_props)

    async def async_update(self):
        await super().async_update()
        if not self._available:
            return
        props = self.device.props or {}
        adt = {}
        if 'miio.s_area' in props:
            adt['clean_area'] = props['miio.s_area']
        if 'miio.s_time' in props:
            adt['clean_time'] = props['miio.s_time']
        if adt:
            await self.async_update_attrs(adt)
            self.device.dispatch(self.device.decode_attrs(adt))

    async def async_locate(self, **kwargs):
        """Locate the vacuum cleaner."""
        if not self._act_locate:
            return await self.async_miio_command('set_resetpos', [1])
        return await super().async_locate()

    async def async_send_command(self, command, params=None, **kwargs):
        """Send a command to a vacuum cleaner."""
        dvc = self.miot_device
        if not dvc:
            raise NotImplementedError()
        _LOGGER.debug('%s: Send command: %s %s', self.name_model, command, params)
        if command == 'app_zoned_clean':
            # params: [[x1, y2, x2, y1, repeats]]
            rpt = 1
            lst = []
            for z in params or []:
                rpt = z.pop(-1)
                lst.append(z)
            return await self.async_clean_zones(lst, rpt)
        elif command == 'app_goto_target':
            return await self.async_clean_point(params)
        return await self.async_miio_command(command, params)

    async def async_clean_zones(self, zones, repeats=1):
        result = []
        i = 0
        for z in zones:
            x1, y2, x2, y1 = z
            res = '_'.join(str(x) for x in [i, 0, x1, y1, x1, y2, x2, y2, x2, y1])
            for _ in range(repeats):
                result.append(res)
                i += 1
        result = [i, *result]
        await self.async_miio_command('set_uploadmap', [1])
        await self.async_miio_command('set_zone', result)
        return await self.async_miio_command('set_mode', [3, 1])

    async def async_clean_point(self, point):
        await self.async_miio_command('set_uploadmap', [0])
        return await self.async_miio_command('set_pointclean', [1, *point])
