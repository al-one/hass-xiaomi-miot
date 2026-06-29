"""Support for Xiaomi vacuums."""
import logging
import asyncio
import json
from datetime import timedelta

from homeassistant.components.vacuum import (  # noqa: F401
    DOMAIN as ENTITY_DOMAIN,
    StateVacuumEntity,
    VacuumEntityFeature,  # v2022.5
)
from .core.const import VacuumActivity

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
            if model in ['xiaomi.vacuum.d106gl']:
                entities.append(MiotXiaomiD106GLVacuumEntity(config, srv))
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
                'Cleaning', 'Sweeping', 'Mopping', 'Sweeping And Mopping', 'Washing', 'Go Washing',
                'Part Sweeping', 'Zone Sweeping', 'Select Sweeping', 'Spot Sweeping', 'Goto Target',
                'Starting', 'Working', 'Busy', 'DustCollecting'
            ):
                self._attr_activity = VacuumActivity.CLEANING
            elif val in self._prop_status.list_search('Idle', 'Sleep'):
                self._attr_activity = VacuumActivity.IDLE
            elif val in self._prop_status.list_search('Charging', 'Charging Completed', 'Fullcharge', 'Charge Done', 'Drying'):
                self._attr_activity = VacuumActivity.DOCKED
            elif val in self._prop_status.list_search('Go Charging'):
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
            return self.async_set_property(self._prop_fan, val)
        return False

    async def async_send_command(self, command, params=None, **kwargs):
        """Send a command to a vacuum cleaner.
        This method must be run in the event loop.
        """
        return await self.async_miio_command(command, params)


class MiotXiaomiD106GLVacuumEntity(MiotVacuumEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(config, miot_service)
        self._srv_map = miot_service.spec.get_service('map')
        self._prop_map_id = None
        self._act_get_rooms = None
        self._act_room_sweep = miot_service.get_action('start_room_sweep')
        self._act_vacuum_room_sweep = miot_service.get_action('start_vacuum_room_sweep')
        self._d106gl_room_buttons_added = False
        if self._srv_map:
            self._prop_map_id = self._srv_map.get_property('cur_map_id')
            self._act_get_rooms = self._srv_map.get_action('get_map_room_list')

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        await self.async_refresh_d106gl_rooms()

    async def async_update(self):
        await super().async_update()
        if not self._available:
            return
        if not self._state_attrs.get('d106gl_rooms'):
            await self.async_refresh_d106gl_rooms()

    def d106gl_current_map_id(self):
        if self._prop_map_id:
            val = self._prop_map_id.from_device(self.device)
            if val is not None:
                return val
            for key in [self._prop_map_id.full_name, self._prop_map_id.unique_name, 'map.cur_map_id']:
                if key in self._state_attrs:
                    return self._state_attrs[key]
        return self._state_attrs.get('map.cur_map_id') or self._state_attrs.get('cur_map_id')

    async def async_refresh_d106gl_rooms(self):
        if not (self._act_get_rooms and self._prop_map_id):
            return []
        map_id = self.d106gl_current_map_id()
        if map_id in [None, '']:
            return []
        try:
            result = await self.async_call_action(self._act_get_rooms, [map_id])
        except (DeviceException, Exception) as exc:
            self.logger.info('%s: D106GL room discovery failed: %s', self.name_model, exc)
            return []
        payload = self.d106gl_extract_action_payload(result)
        rooms = self.d106gl_parse_rooms(payload)
        self._state_attrs['d106gl_room_payload'] = payload
        self._state_attrs['d106gl_rooms'] = rooms
        self._state_attrs['d106gl_map_id'] = map_id
        await self.async_update_attrs({
            'd106gl_room_payload': payload,
            'd106gl_rooms': rooms,
            'd106gl_map_id': map_id,
        })
        if rooms:
            self.async_add_d106gl_room_buttons(rooms)
        return rooms

    def d106gl_extract_action_payload(self, result):
        if hasattr(result, 'to_json'):
            result = result.to_json()
        if isinstance(result, dict):
            for key in ['value', 'out', 'result', 'results']:
                val = result.get(key)
                if val not in [None, []]:
                    if isinstance(val, list) and len(val) == 1:
                        return val[0]
                    return val
        return result

    def d106gl_parse_rooms(self, payload):
        data = payload
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (TypeError, ValueError):
                data = [p for p in data.replace(';', ',').split(',') if p]
        if isinstance(data, dict):
            for key in ['rooms', 'room_info', 'room_list', 'roomIdNameList']:
                if isinstance(data.get(key), list):
                    data = data[key]
                    break
        rooms = []
        if isinstance(data, list):
            for idx, item in enumerate(data, 1):
                rid = None
                name = None
                if isinstance(item, dict):
                    rid = item.get('room_id') or item.get('roomId') or item.get('id')
                    name = item.get('name') or item.get('room_name') or item.get('roomName')
                elif isinstance(item, (list, tuple)) and item:
                    rid = item[0]
                    name = item[1] if len(item) > 1 else None
                elif isinstance(item, str):
                    parts = item.split(':', 1)
                    rid = parts[0]
                    name = parts[1] if len(parts) > 1 else None
                if rid in [None, '']:
                    continue
                rooms.append({
                    'id': str(rid),
                    'name': str(name or f'Room {idx}'),
                })
        return rooms

    def async_add_d106gl_room_buttons(self, rooms):
        if self._d106gl_room_buttons_added:
            return
        if not (add_buttons := self.device.entry.adders.get('button')):
            return
        from .button import ButtonSubEntity
        for room in rooms:
            rid = room.get('id')
            name = room.get('name') or rid
            if rid in [None, '']:
                continue
            sub = f'd106gl_room_{rid}'
            if sub in self._subs:
                continue
            self._subs[sub] = ButtonSubEntity(self, sub, option={
                'name': f'{self.device_name} {name}',
                'async_press_action': self.async_start_d106gl_room_sweep,
                'press_kwargs': {'room_id': rid},
                'state_attrs': {'room_id': rid, 'room_name': name},
            })
            add_buttons([self._subs[sub]], update_before_add=False)
        self._d106gl_room_buttons_added = True

    async def async_start_d106gl_room_sweep(self, room_id, **kwargs):
        params = [str(room_id)]
        for act in [self._act_room_sweep, self._act_vacuum_room_sweep]:
            if not act:
                continue
            result = await self.async_call_action(act, params)
            if getattr(result, 'is_success', False):
                return result
        return False


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
