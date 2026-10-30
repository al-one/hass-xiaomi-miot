"""Support for Xiaomi vacuums."""
import logging
import asyncio
import json
import time
from datetime import timedelta

from homeassistant.components.vacuum import (  # noqa: F401
    DOMAIN as ENTITY_DOMAIN,
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,  # v2022.5
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

try:
    from homeassistant.components.vacuum import Segment  # v2026.3
except ImportError:
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
            if model.startswith('xtl.vacuum.') and spec.get_service('robotic_vacuum'):
                entities.append(MiotXtlVacuumEntity(config, srv))
            elif model in MIOT_LOCAL_MODELS:
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
        self._supported_features |= VacuumEntityFeature.SEND_COMMAND

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


class MiotXtlVacuumEntity(MiotVacuumEntity):
    """XTL (Jonr P20 etc.): rooms, zones and spot via robotic-vacuum:start-clean.

    start-clean takes [clean-type, clean-values] where clean-values is a JSON string:
    3 = rooms "[3,4]" (room_id from the cloud map), 4 = zones, 8 ints per rectangle
    "[x1,y1,x2,y1,x2,y2,x1,y2]" in the map position frame, 6 = spot "".
    The robot ignores start-clean while a task is open, so stop-clean goes first.
    See https://github.com/al-one/hass-xiaomi-miot/issues/2961
    """
    ROOMS_TTL = 3600

    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(config, miot_service)
        self._srv_robot = miot_service.spec.get_service('robotic_vacuum')
        self._act_start_clean = self._srv_robot.get_action('start_clean')
        self._act_stop_clean = self._srv_robot.get_action('stop_clean')
        self._act_clean_count = self._srv_robot.get_action('set_clean_count')
        self._act_map_data = self._srv_robot.get_action('get_map_data')
        self._prop_task = self._srv_robot.get_property('clean_type_status')
        self._prop_return = self._srv_robot.get_property('return_status')
        self._rooms = {}
        self._rooms_time = 0
        if self._act_start_clean:
            self._supported_features |= VacuumEntityFeature.CLEAN_SPOT
            if Segment and hasattr(VacuumEntityFeature, 'CLEAN_AREA'):
                self._supported_features |= VacuumEntityFeature.CLEAN_AREA

    @property
    def supported_features(self):
        return VacuumEntityFeature(self._supported_features)

    async def async_update(self):
        await super().async_update()
        if not self._available or time.time() - self._rooms_time < self.ROOMS_TTL:
            return
        await self.async_refresh_rooms()

    async def async_refresh_rooms(self):
        """Read the room list from the map file the robot uploads to the cloud."""
        self._rooms_time = time.time()
        try:
            rooms = await self.async_get_cloud_rooms()
        except Exception as exc:
            self.logger.warning('%s: Failed to load rooms from the cloud map: %s', self.name_model, exc)
            return self._rooms
        if rooms is None:
            return self._rooms
        self._rooms = rooms
        self._state_attrs['rooms'] = {rid: r['name'] for rid, r in rooms.items()}
        self._check_segments_changed()
        return rooms

    async def async_get_cloud_rooms(self):
        cloud = self.xiaomi_cloud
        if not cloud:
            return None
        obj_name = None
        if self._act_map_data:
            # out: map-data == "<uid>/<did>/0", the live map file
            res = await self.async_call_action(self._act_map_data)
            for out in res.get('out') or []:
                obj_name = out.get('value') if isinstance(out, dict) else out
        if not obj_name:
            obj_name = f'{cloud.user_id}/{self.miot_did}/0'
        url = None
        for api in ['v2/home/get_interim_file_url_pro', 'v2/home/get_interim_file_url']:
            rdt = await cloud.async_request_api(api, {'obj_name': obj_name}) or {}
            if url := (rdt.get('result') or {}).get('url'):
                break
        if not url:
            return None
        session = async_get_clientsession(self.hass)
        async with session.get(url, timeout=30) as rsp:
            rsp.raise_for_status()
            outer = json.loads(await rsp.read())
        fields = outer.get('fields') or []
        infos = json.loads(fields[3]) if len(fields) > 3 and fields[3] else []
        outlines = {r['id']: r.get('data') or [] for r in (fields[9] if len(fields) > 9 else None) or []}
        rooms = {}
        for info in infos:
            rid = info.get('room_id')
            if rid is None:
                continue
            name = str(info.get('name') or '').strip()
            if not name:
                name = f'Room {rid}'
                if area := _polygon_area(outlines.get(rid)):
                    # unnamed in the app: the size helps to tell rooms apart (5 cm per map unit)
                    name = f'{name} ({area * 0.0025:.1f} m²)'
            rooms[rid] = {'name': name, 'id': info.get('id')}
        self.logger.debug('%s: Rooms from %s: %s', self.name_model, obj_name, rooms)
        return rooms

    def _check_segments_changed(self):
        if self.registry_entry is None or not (self._supported_features & VacuumEntityFeature.CLEAN_AREA):
            return
        last_seen = self.last_seen_segments
        if last_seen is None:
            return
        if {s.id for s in last_seen} != {str(rid) for rid in self._rooms}:
            self.async_create_segments_issue()

    async def async_get_segments(self):
        if not self._rooms or time.time() - self._rooms_time > 60:
            await self.async_refresh_rooms()
        return [Segment(id=str(rid), name=r['name']) for rid, r in self._rooms.items()]

    async def async_clean_segments(self, segment_ids, **kwargs):
        return await self.async_clean_rooms([int(s) for s in segment_ids])

    async def async_clean_rooms(self, rooms, repeats=None):
        return await self.async_start_clean(3, json.dumps([int(r) for r in rooms], separators=(',', ':')), repeats)

    async def async_clean_zones(self, zones, repeats=None):
        """zones: [[x1, y1, x2, y2], ...] in the map position frame (same as the vacuum position)."""
        values = []
        for z in zones:
            x1, y1, x2, y2 = (int(round(v)) for v in z[:4])
            x1, x2 = sorted([x1, x2])
            y1, y2 = sorted([y1, y2])
            values.extend([x1, y1, x2, y1, x2, y2, x1, y2])
        if not values:
            return False
        return await self.async_start_clean(4, json.dumps(values, separators=(',', ':')), repeats)

    async def async_clean_spot(self, **kwargs):
        return await self.async_start_clean(6, '')

    async def async_start_clean(self, clean_type, values, repeats=None):
        if not self._act_start_clean:
            return False
        if self._task_open():
            await self.async_call_action(self._act_stop_clean)
            await asyncio.sleep(2)
        if repeats and self._act_clean_count:
            await self.async_call_action(self._act_clean_count, [min(max(int(repeats), 1), 2)])
        result = await self.async_call_action(self._act_start_clean, [clean_type, values])
        self.logger.info('%s: Start clean %s %s: %s', self.name_model, clean_type, values, result)
        return result

    def _task_open(self):
        if not self._act_stop_clean:
            return False
        task = self._prop_task.from_device(self.device) if self._prop_task else None
        ret = self._prop_return.from_device(self.device) if self._prop_return else None
        # clean-type-status 0 None / 1 Idle, return-status 0 None / 1 Idle
        return task not in (0, 1) or ret not in (0, 1, None)

    async def async_stop(self, **kwargs):
        # stop-sweeping is acknowledged but leaves the task open, stop-clean ends it
        if self._act_stop_clean:
            return await self.async_call_action(self._act_stop_clean)
        return await super().async_stop(**kwargs)

    async def async_send_command(self, command, params=None, **kwargs):
        """Roborock-style commands, e.g. from the Xiaomi Vacuum Map Card.

        app_segment_clean: [3, 4] or [{"segments": [3, 4], "repeat": 1}]
        app_zoned_clean:   [[x1, y1, x2, y2, repeats], ...]
        """
        if command == 'app_segment_clean':
            repeats = None
            if params and isinstance(params[0], dict):
                repeats = params[0].get('repeat')
                params = params[0].get('segments') or []
            return await self.async_clean_rooms(params or [], repeats)
        if command == 'app_zoned_clean':
            zones = [z for z in params or [] if len(z) >= 4]
            repeats = zones[0][4] if zones and len(zones[0]) > 4 else None
            return await self.async_clean_zones(zones, repeats)
        return await super().async_send_command(command, params, **kwargs)


def _polygon_area(data):
    """Shoelace area of a flat [x0, y0, x1, y1, ...] outline, in map units²."""
    if not data or len(data) < 6:
        return 0
    pts = list(zip(data[::2], data[1::2]))
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]))) / 2
