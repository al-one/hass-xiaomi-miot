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
from homeassistant.components.switch import SwitchEntity
from homeassistant.components.select import SelectEntity
from homeassistant.components.time import TimeEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from .core.const import VacuumActivity

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    HassEntry,
    MiotEntity,
    MIOT_LOCAL_MODELS,
    BaseSubEntity,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.utils import DeviceException
from .core.miot_spec import (
    MiotSpec,
    MiotService,
)
from .core.vacuum_zones import (
    ZONE_SIID,
    RESTRICTED_AREAS_PIID,
    RESTRICTED_WALLS_PIID,
    ZONE_TYPE_NO_SWEEP_AND_MOP,
    ZONE_TYPE_LABELS,
    LABEL_TO_ZONE_TYPE,
    build_zone_lists,
    remove_zone_lists,
    zone_write_payloads,
    describe_zones,
    parse_zone_property_values,
)
from .core.vacuum_maps import (
    MAP_SIID,
    MAP_MANAGEMENT_PIID,
    BACKUP_MAP_LIST_PIID,
    MAX_SAVED_MAPS,
    parse_map_management,
    parse_backup_map_list,
    map_label,
    saved_maps,
    find_current_map,
    find_backup_for_map,
    set_map_name_payload,
)
from .core.vacuum_schedule import (
    decode_schedule,
    schedule_enabled,
    set_schedule_enabled,
    schedule_time,
    set_schedule_time,
    schedule_mode_label,
    set_schedule_mode,
    schedule_day_enabled,
    set_schedule_day,
    unpack_dnd_schedule,
    pack_dnd_schedule,
    SCHEDULE_DAY_BITS,
    SCHEDULE_MODE_LABELS,
)
from .core.vacuum_area_sweep import (
    MAX_AREAS,
    build_area_list,
    describe_areas,
    area_sweep_payload,
)
from .core.converters import FAULT_LABELS, BASE_STATION_MODE_LABELS

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
            elif srv.get_property('room_information') and srv.get_action('start_vacuum_room_sweep'):
                # Detected by capability (this exact room-sweep property/
                # action pair), not a hardcoded model check - covers
                # xiaomi.vacuum.ov42gl (H50 Pro) and any other model sharing
                # the same spec shape.
                entities.append(MiotOv42glVacuumEntity(config, srv))
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
                'Cleaning', 'Sweeping', 'Mopping', 'Sweeping And Mopping', 'Washing', 'Go Washing',
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
            return self.async_set_property(self._prop_fan, val)
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


class _StagingSwitch(BaseSubEntity, SwitchEntity):
    """A pure in-memory toggle sub-entity - not backed by any MIoT property,
    doesn't survive a Home Assistant restart. Follows the same "no-op
    update()" idiom ButtonSubEntity (button.py) already uses for the same
    reason: there's nothing on the device to poll for this attribute, so
    BaseSubEntity's default update() (which reads from `device.props` and
    would otherwise leave `available` stuck False forever) is skipped."""

    def __init__(self, parent, attr, option=None):
        BaseSubEntity.__init__(self, parent, attr, option, domain='switch')
        self._available = True
        self._attr_is_on = bool(self._option.get('is_on', False))
        self._async_turn_on_action = self._option.get('async_turn_on_action')
        self._async_turn_off_action = self._option.get('async_turn_off_action')

    def update(self, data=None):
        return

    @property
    def is_on(self):
        return self._attr_is_on

    async def async_turn_on(self, **kwargs):
        self._attr_is_on = True
        if self._async_turn_on_action:
            await self._async_turn_on_action(self)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        self._attr_is_on = False
        if self._async_turn_off_action:
            await self._async_turn_off_action(self)
        self.async_write_ha_state()


class _StagingSelect(BaseSubEntity, SelectEntity):
    """A pure in-memory select sub-entity - see _StagingSwitch above for why
    update() is a no-op here too. Options can be static (`option['options']`)
    or computed live (`option['options_getter']`, a zero-arg callable) so a
    "which zone to remove" list can follow whatever's actually on the map
    right now instead of going stale."""

    def __init__(self, parent, attr, option=None):
        BaseSubEntity.__init__(self, parent, attr, option, domain='select')
        self._available = True
        self._attr_current_option = self._option.get('current_option')
        self._options_getter = self._option.get('options_getter')
        self._static_options = self._option.get('options') or []
        self._async_select_option_action = self._option.get('async_select_option_action')

    def update(self, data=None):
        return

    @property
    def options(self):
        if self._options_getter:
            return self._options_getter()
        return self._static_options

    @property
    def current_option(self):
        if self._attr_current_option in self.options:
            return self._attr_current_option
        return None

    async def async_select_option(self, option: str):
        self._attr_current_option = option
        if self._async_select_option_action:
            # Immediate-write selects (e.g. schedule mode) - as opposed to
            # the staging-only selects above (zone_type/zone_to_remove/
            # map_to_delete), which just get read later by a separate
            # button press and pass no action here.
            await self._async_select_option_action(self, option)
        self.async_write_ha_state()


class _StagingTime(BaseSubEntity, TimeEntity):
    """A pure in-memory time sub-entity - see _StagingSwitch above for the
    same "no-op update()" rationale. Always backed by `option
    ['async_set_value_action']` (unlike _StagingSwitch/_StagingSelect,
    every use of this class here needs an immediate device write - there's
    no staging-only use case for a bare time value)."""

    def __init__(self, parent, attr, option=None):
        BaseSubEntity.__init__(self, parent, attr, option, domain='time')
        self._available = True
        self._attr_native_value = self._option.get('native_value')
        self._async_set_value_action = self._option.get('async_set_value_action')

    def update(self, data=None):
        return

    @property
    def native_value(self):
        return self._attr_native_value

    async def async_set_value(self, value):
        await self._async_set_value_action(self, value)


class _PolledSensor(BaseSubEntity, SensorEntity):
    """A read-only sensor sub-entity refreshed by the parent's own timer
    (see _async_setup_extra_sensors) instead of through a MiotPropConv -
    these particular properties don't reliably produce entities via the
    generic `sensor_properties` pipeline for this device model (root cause
    not fully pinned down; DND/schedule above hit the same wall via
    append_converters and are wired the same direct way as a result)."""

    def __init__(self, parent, attr, option=None):
        BaseSubEntity.__init__(self, parent, attr, option, domain='sensor')
        self._available = True
        self._attr_native_value = self._option.get('native_value')
        self._attr_device_class = self._option.get('device_class')

    def update(self, data=None):
        return

    @property
    def native_value(self):
        return self._attr_native_value


class MiotOv42glVacuumEntity(MiotVacuumEntity):
    """xiaomi.vacuum.ov42gl (H50 Pro), and any other model exposing the same
    room-sweep property/action pair (see async_setup_platform) - adds what
    xiaomi_miot's generic property/action-to-entity mapping can't represent
    on its own:

      - Per-room and multi-room cleaning: `start_vacuum_room_sweep` takes a
        comma-separated room-id string, not a fixed enum value, so it can't
        become a plain button/select the way a simple action can.
      - Room renaming: writes a `{"room_attrs": [...]}` JSON payload through
        `set_room_clean_configs` (which is also used for per-room fan/mop
        settings) rather than a plain property.
      - Virtual wall / restricted zone editing: `restricted_sweep_areas`/
        `restricted_walls` are always rewritten as a whole replacement list
        (see core/vacuum_zones.py), not a single scalar value.

    All of the above were reverse-engineered from the Xiaomi Home app's own
    write flows, for interoperability - see the README's section for this
    model for the full writeup.
    """

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        await self._async_setup_room_entities()
        await self._async_setup_zone_entities()
        await self._async_setup_map_entities()
        await self._async_setup_dnd_entities()
        await self._async_setup_schedule_entities()
        await self._async_setup_extra_sensors()
        await self._async_setup_area_sweep_entities()

    # -- Per-room / multi-room cleaning --------------------------------

    async def _async_fetch_rooms(self):
        prop = self._miot_service.get_property('room_information')
        # did is not required here - see the comment in _async_read_zones for why.
        if not prop or not self.device.local:
            return []
        try:
            results = await self.device.local.async_get_properties_for_mapping(
                did=self.device.did,
                mapping={'room_information': {'siid': prop.siid, 'piid': prop.iid}},
            )
        except Exception as exc:
            self.logger.debug('%s: failed to read room_information: %s', self.name_model, exc)
            return []
        for item in results or []:
            if item.get('code') == 0 and item.get('value'):
                try:
                    data = json.loads(item['value'])
                except (TypeError, ValueError):
                    return []
                return [(r['id'], r.get('name') or f'Room {r["id"]}') for r in data.get('rooms', [])]
        return []

    async def _async_setup_room_entities(self):
        # Room list is fetched once here, at platform setup, matching this
        # device's actual behavior: it doesn't reflect an app-side rename
        # back into `room_information` in real time either, so periodic
        # re-polling wouldn't gain much - a Home Assistant restart already
        # picks up any change made from the app.
        rooms = await self._async_fetch_rooms()
        if not rooms:
            return
        add_buttons = self.device.entry.adders.get('button')
        add_switches = self.device.entry.adders.get('switch')
        add_texts = self.device.entry.adders.get('text')
        if not (add_buttons and add_switches):
            return

        from .button import ButtonSubEntity
        from .text import TextSubEntity

        rename_action = self._miot_service.get_action('set_room_clean_configs')

        room_switches = {}
        new_buttons, new_switches, new_texts = [], [], []
        for room_id, room_name in rooms:
            # Explicit `entity_id` (slugified from the room name, e.g.
            # "Living room" -> select_room_living_room) rather than letting
            # Home Assistant derive one from the entity's full display name
            # (which would fold in the device's own name too, producing an
            # unpredictable id that differs per installation). This mirrors
            # the naming scheme already used by the older xiaomi_miot_tools
            # add-on this replaces, so a dashboard referencing
            # `switch.select_room_*`/`button.clean_selected_rooms` keeps
            # working after migrating to this integration's own entities.
            sub = f'clean_room_{room_id}'
            self._subs[sub] = ButtonSubEntity(self, sub, option={
                'name': f'{self.device_name} Clean Room: {room_name}',
                'entity_id': f'clean_room_{room_name}',
                'async_press_action': self._async_clean_rooms,
                'press_kwargs': {'room_ids': [room_id]},
            })
            new_buttons.append(self._subs[sub])

            sub = f'select_room_{room_id}'
            self._subs[sub] = _StagingSwitch(self, sub, option={
                'name': f'{self.device_name} Select Room: {room_name}',
                'entity_id': f'select_room_{room_name}',
            })
            room_switches[room_id] = self._subs[sub]
            new_switches.append(self._subs[sub])

            if rename_action and add_texts:
                sub = f'rename_room_{room_id}'
                self._subs[sub] = TextSubEntity(self, sub, option={
                    'name': f'{self.device_name} Rename Room: {room_name}',
                    'entity_id': f'rename_room_{room_name}',
                    'native_value': room_name,
                    'async_set_value_action': self._make_rename_room_action(room_id, rename_action),
                })
                new_texts.append(self._subs[sub])

        sweep_action = self._miot_service.get_action('start_vacuum_room_sweep')
        if sweep_action:
            sub = 'clean_selected_rooms'
            self._subs[sub] = ButtonSubEntity(self, sub, option={
                'name': f'{self.device_name} Clean Selected Rooms',
                'entity_id': 'clean_selected_rooms',
                'async_press_action': self._async_clean_selected_rooms,
                'press_kwargs': {'room_switches': room_switches},
            })
            new_buttons.append(self._subs[sub])

        add_buttons(new_buttons, update_before_add=False)
        add_switches(new_switches, update_before_add=False)
        if new_texts and add_texts:
            add_texts(new_texts, update_before_add=False)

    async def _async_clean_rooms(self, room_ids, **kwargs):
        act = self._miot_service.get_action('start_vacuum_room_sweep')
        if not act:
            return False
        result = await self.async_call_action(act, [','.join(str(r) for r in room_ids)])
        return bool(result and result.is_success)

    async def _async_clean_selected_rooms(self, room_switches, **kwargs):
        selected = [room_id for room_id, sw in room_switches.items() if sw.is_on]
        if not selected:
            self.logger.warning('%s: Clean Selected Rooms pressed with no rooms selected', self.name_model)
            return False
        ok = await self._async_clean_rooms(selected)
        for sw in room_switches.values():
            if sw.is_on:
                sw._attr_is_on = False
                sw.async_write_ha_state()
        return ok

    def _make_rename_room_action(self, room_id, rename_action):
        async def _do_rename(entity, value):
            name = value.strip()
            if not name:
                raise HomeAssistantError('Room name must not be empty')
            payload = json.dumps({'room_attrs': [{'id': room_id, 'room_name': name}]})
            result = await self.async_call_action(rename_action, [payload])
            if not result or not result.is_success:
                raise HomeAssistantError(f'Failed to rename room: {result.error if result else "no response"}')
            # Optimistic update: the device doesn't reflect this write back
            # into room_information synchronously, so re-reading it right
            # after the write can still return the pre-rename value.
            entity._attr_native_value = name
            entity._name = f'{self.device_name} Rename Room: {name}'
            entity.async_write_ha_state()
        return _do_rename

    # -- Virtual wall / restricted zone editor ---------------------------

    async def _async_read_zones(self):
        """Reads the two zone/wall properties directly off the device (both
        are plain read/write MIoT properties, SIID2 PIID13/14) and returns
        them in the internal (regions, walls) list shape - see
        core/vacuum_zones.py. No cloud map involved."""
        prop_regions = self._miot_service.get_property('restricted_sweep_areas')
        prop_walls = self._miot_service.get_property('restricted_walls')
        # did is not required here: async_get_properties_for_mapping only uses
        # it as a per-property request/response matching label (falls back to
        # 'prop.{siid}.{piid}' when absent - see its own body in device.py),
        # not for local addressing/auth. Requiring it blocked reads whenever
        # the device's cloud did hadn't resolved yet, even though local
        # (IP+token) works fine without it.
        if not (prop_regions and prop_walls and self.device.local):
            return [], []
        try:
            results = await self.device.local.async_get_properties_for_mapping(
                did=self.device.did,
                mapping={
                    'restricted_sweep_areas': {'siid': prop_regions.siid, 'piid': prop_regions.iid},
                    'restricted_walls': {'siid': prop_walls.siid, 'piid': prop_walls.iid},
                },
            )
        except Exception as exc:
            self.logger.debug('%s: failed to read zones/walls: %s', self.name_model, exc)
            return [], []
        values = {}
        for item in results or []:
            if item.get('code') == 0:
                values[(item.get('siid'), item.get('piid'))] = item.get('value')
        regions_raw = values.get((prop_regions.siid, prop_regions.iid))
        walls_raw = values.get((prop_walls.siid, prop_walls.iid))
        return parse_zone_property_values(regions_raw, walls_raw)

    async def _async_setup_zone_entities(self):
        if not (self._miot_service.get_property('restricted_sweep_areas') and self._miot_service.get_property('restricted_walls')):
            return
        add_numbers = self.device.entry.adders.get('number')
        add_selects = self.device.entry.adders.get('select')
        add_buttons = self.device.entry.adders.get('button')
        if not (add_numbers and add_selects and add_buttons):
            return

        from .number import NumberSubEntity
        from .button import ButtonSubEntity

        # Read once at setup, then kept in sync locally after every add/remove
        # made from HA (same "fetch once, HA-side edits update the cache
        # immediately, app-side edits need a restart" behavior as rooms
        # above - the device doesn't reflect a write back into these
        # properties synchronously enough to just re-read them right after).
        self._zone_regions, self._zone_walls = await self._async_read_zones()

        coord_option = {'min': -20000, 'max': 20000, 'step': 10, 'native_value': 0}
        new_numbers = []
        for key, label in (
            ('zone_x1', 'Zone X1'), ('zone_y1', 'Zone Y1'),
            ('zone_x2', 'Zone X2'), ('zone_y2', 'Zone Y2'),
        ):
            self._subs[key] = NumberSubEntity(self, key, option={
                **coord_option,
                'name': f'{self.device_name} {label}',
            })
            new_numbers.append(self._subs[key])
        add_numbers(new_numbers, update_before_add=False)

        self._subs['zone_type'] = _StagingSelect(self, 'zone_type', option={
            'name': f'{self.device_name} Zone Type',
            'options': list(ZONE_TYPE_LABELS.values()),
            'current_option': ZONE_TYPE_LABELS[ZONE_TYPE_NO_SWEEP_AND_MOP],
        })
        self._subs['zone_to_remove'] = _StagingSelect(self, 'zone_to_remove', option={
            'name': f'{self.device_name} Zone to Remove',
            'options_getter': self._describe_current_zones,
        })
        add_selects([self._subs['zone_type'], self._subs['zone_to_remove']], update_before_add=False)

        self._subs['add_zone'] = ButtonSubEntity(self, 'add_zone', option={
            'name': f'{self.device_name} Add Zone',
            'async_press_action': self._async_add_zone,
        })
        self._subs['remove_zone'] = ButtonSubEntity(self, 'remove_zone', option={
            'name': f'{self.device_name} Remove Zone',
            'async_press_action': self._async_remove_zone,
        })
        add_buttons([self._subs['add_zone'], self._subs['remove_zone']], update_before_add=False)

    def _zone_numbers(self):
        return (
            self._subs['zone_x1'].native_value,
            self._subs['zone_y1'].native_value,
            self._subs['zone_x2'].native_value,
            self._subs['zone_y2'].native_value,
        )

    def _current_zone_type(self):
        select = self._subs.get('zone_type')
        label = select.current_option if select else None
        return LABEL_TO_ZONE_TYPE.get(label, ZONE_TYPE_NO_SWEEP_AND_MOP)

    def _describe_current_zones(self):
        return [label for label, _kind, _index in describe_zones(self._zone_regions, self._zone_walls)]

    async def _async_add_zone(self, **kwargs):
        x1, y1, x2, y2 = self._zone_numbers()
        if x1 == x2 and y1 == y2:
            raise HomeAssistantError('Set two different points (Zone X1/Y1/X2/Y2) before adding')
        zone_type = self._current_zone_type()
        try:
            regions, walls = build_zone_lists(self._zone_regions, self._zone_walls, zone_type, x1, y1, x2, y2)
        except ValueError as exc:
            raise HomeAssistantError(str(exc)) from exc
        await self._async_write_zones(regions, walls)

        # Reset the staging inputs so the editor is ready for the next zone.
        for key in ('zone_x1', 'zone_y1', 'zone_x2', 'zone_y2'):
            entity = self._subs[key]
            entity._attr_native_value = 0
            entity.async_write_ha_state()
        return True

    async def _async_remove_zone(self, **kwargs):
        select = self._subs.get('zone_to_remove')
        selected = select.current_option if select else None
        if not selected:
            raise HomeAssistantError('No zone selected in "Zone to Remove"')
        match = next(
            ((kind, index) for label, kind, index in describe_zones(self._zone_regions, self._zone_walls) if label == selected),
            None,
        )
        if match is None:
            raise HomeAssistantError('Zone not found - the list may have changed, try refreshing the selection')
        kind, index = match
        try:
            regions, walls = remove_zone_lists(self._zone_regions, self._zone_walls, kind, index)
        except ValueError as exc:
            raise HomeAssistantError(str(exc)) from exc
        await self._async_write_zones(regions, walls)
        return True

    async def _async_write_zones(self, regions, walls):
        regions_payload, walls_payload = zone_write_payloads(regions, walls)
        result = await self.async_set_miot_property(ZONE_SIID, RESTRICTED_AREAS_PIID, regions_payload)
        if not result or not result.is_success:
            raise HomeAssistantError(f'Failed to write zones: {result.error if result else "no response"}')
        result = await self.async_set_miot_property(ZONE_SIID, RESTRICTED_WALLS_PIID, walls_payload)
        if not result or not result.is_success:
            raise HomeAssistantError(f'Failed to write walls: {result.error if result else "no response"}')

        # Optimistic update: the write above already confirmed success, so
        # the local cache is updated straight away instead of re-reading the
        # properties back (same rationale as room renaming above - no
        # guarantee the device reflects the write back synchronously).
        self._zone_regions = [{'fb_point': r['fb_point'], 'fb_attr': r['fb_attr']} for r in regions]
        self._zone_walls = [{'wall_points': w['wall_points']} for w in walls]

    # -- Saved map list / backup restore ----------------------------------

    async def _async_read_maps(self):
        """Reads map-management/backup-map-list directly off the device
        (SIID10 PIID5/13 - a separate MIoT service from the main vacuum one,
        excluded from the generic pipeline; see core/vacuum_maps.py for why).
        No cloud map download involved - both are already plain JSON, unlike
        the rendered map file in core/vacuum_map.py. Returns ([], []) if
        local isn't ready yet or the read fails - callers must not treat
        that as "unsupported" (see _async_setup_map_entities, which gates
        entity creation on the service existing in the spec, not on this
        read succeeding - same contract as _async_read_zones). did is not
        required - see the comment in _async_read_zones for why."""
        if not self.device.local:
            return [], []
        try:
            results = await self.device.local.async_get_properties_for_mapping(
                did=self.device.did,
                mapping={
                    'map_management': {'siid': MAP_SIID, 'piid': MAP_MANAGEMENT_PIID},
                    'backup_map_list': {'siid': MAP_SIID, 'piid': BACKUP_MAP_LIST_PIID},
                },
            )
        except Exception as exc:
            self.logger.debug('%s: failed to read map list: %s', self.name_model, exc)
            return [], []
        values = {}
        for item in results or []:
            if item.get('code') == 0:
                values[(item.get('siid'), item.get('piid'))] = item.get('value')
        maps = parse_map_management(values.get((MAP_SIID, MAP_MANAGEMENT_PIID)))
        backups = parse_backup_map_list(values.get((MAP_SIID, BACKUP_MAP_LIST_PIID)))
        return maps, backups

    async def _async_setup_map_entities(self):
        # Gate on the service existing in the spec, not on the read below
        # succeeding - did/cloud-link can still be resolving at this point
        # in the device's lifecycle, same as restricted_sweep_areas/
        # restricted_walls above; entities must still appear (empty until
        # the data shows up) rather than silently not exist.
        self._map_service = self._miot_service.spec.get_service('vacuum_map')
        if not self._map_service:
            return
        add_buttons = self.device.entry.adders.get('button')
        add_texts = self.device.entry.adders.get('text')
        add_selects = self.device.entry.adders.get('select')
        if not add_buttons:
            return

        from .button import ButtonSubEntity

        # Read once at setup, same "fetch once, HA-side edits update the
        # cache immediately, app-side edits need a restart" behavior as
        # rooms/zones above (see _async_setup_zone_entities).
        self._maps, self._map_backups = await self._async_read_maps()

        new_buttons, new_texts = [], []
        for entry in saved_maps(self._maps):
            new_buttons.append(self._add_use_map_button(entry))
            if add_texts:
                new_texts.append(self._add_rename_map_text(entry))

        sub = 'save_map'
        self._subs[sub] = ButtonSubEntity(self, sub, option={
            'name': f'{self.device_name} Save Current Map',
            'entity_id': 'save_current_map',
            'async_press_action': self._async_save_map,
        })
        new_buttons.append(self._subs[sub])

        current = find_current_map(self._maps)
        backup = find_backup_for_map(current.get('map_id'), self._map_backups) if current else None
        if backup is not None:
            sub = 'restore_map_backup'
            self._subs[sub] = ButtonSubEntity(self, sub, option={
                'name': f'{self.device_name} Restore Map Backup',
                'entity_id': 'restore_map_backup',
                'async_press_action': self._async_restore_map_backup,
            })
            new_buttons.append(self._subs[sub])

        if add_selects and len(saved_maps(self._maps)) > 1:
            self._subs['map_to_delete'] = _StagingSelect(self, 'map_to_delete', option={
                'name': f'{self.device_name} Map to Delete',
                'options_getter': self._describe_deletable_maps,
            })
            add_selects([self._subs['map_to_delete']], update_before_add=False)

            sub = 'delete_map'
            self._subs[sub] = ButtonSubEntity(self, sub, option={
                'name': f'{self.device_name} Delete Selected Map',
                'entity_id': 'delete_selected_map',
                'async_press_action': self._async_delete_map,
            })
            new_buttons.append(self._subs[sub])

        add_buttons(new_buttons, update_before_add=False)
        if new_texts and add_texts:
            add_texts(new_texts, update_before_add=False)

    def _add_use_map_button(self, entry):
        from .button import ButtonSubEntity
        map_id = entry.get('map_id')
        sub = f'use_map_{map_id}'
        self._subs[sub] = ButtonSubEntity(self, sub, option={
            'name': f'{self.device_name} Use Map: {map_label(entry)}',
            'entity_id': f'use_map_{map_id}',
            'async_press_action': self._async_use_map,
            'press_kwargs': {'map_id': map_id},
        })
        return self._subs[sub]

    def _add_rename_map_text(self, entry):
        from .text import TextSubEntity
        map_id = entry.get('map_id')
        sub = f'rename_map_{map_id}'
        self._subs[sub] = TextSubEntity(self, sub, option={
            'name': f'{self.device_name} Rename Map: {map_label(entry)}',
            'entity_id': f'rename_map_{map_id}',
            'native_value': map_label(entry),
            'async_set_value_action': self._make_rename_map_action(map_id),
        })
        return self._subs[sub]

    def _map_action(self, name):
        return self._map_service.get_action(name) if self._map_service else None

    async def _async_call_map_action(self, name, params=None):
        act = self._map_action(name)
        if not act:
            raise HomeAssistantError(f'Action not supported by this device: {name}')
        result = await self.async_call_action(act, params if params is not None else [])
        if not result or not result.is_success:
            label = name.replace('_', ' ')
            raise HomeAssistantError(f'Failed to {label}: {result.error if result else "no response"}')
        return result

    async def _async_use_map(self, map_id, **kwargs):
        await self._async_call_map_action('set_map', [map_id])
        # Optimistic update - same rationale as room/zone writes above: the
        # device doesn't reflect this back into map-management synchronously.
        for m in self._maps:
            m['is_current'] = (m.get('map_id') == map_id)
        return True

    def _make_rename_map_action(self, map_id):
        async def _do_rename(entity, value):
            name = value.strip()
            if not name:
                raise HomeAssistantError('Map name must not be empty')
            await self._async_call_map_action('set_map_name', [set_map_name_payload(map_id, name)])
            for m in self._maps:
                if m.get('map_id') == map_id:
                    m['map_name'] = name
            entity._attr_native_value = name
            entity._name = f'{self.device_name} Rename Map: {name}'
            entity.async_write_ha_state()
        return _do_rename

    async def _async_save_map(self, **kwargs):
        if len(saved_maps(self._maps)) >= MAX_SAVED_MAPS:
            raise HomeAssistantError(f'Limit of {MAX_SAVED_MAPS} saved maps reached (same limit the app enforces)')
        await self._async_call_map_action('save_map')
        await self._async_refresh_maps_after_save()
        return True

    async def _async_refresh_maps_after_save(self):
        """save-map assigns a new map_id server-side that can't be predicted
        client-side (unlike rename/delete/switch, where the affected id is
        already known) - so this specifically re-reads map-management, then
        creates entities for whatever map_id(s) weren't there before."""
        maps, backups = await self._async_read_maps()
        known_ids = {m.get('map_id') for m in self._maps}
        self._map_backups = backups

        add_buttons = self.device.entry.adders.get('button')
        add_texts = self.device.entry.adders.get('text')
        new_buttons, new_texts = [], []
        for entry in saved_maps(maps):
            if entry.get('map_id') in known_ids:
                continue
            new_buttons.append(self._add_use_map_button(entry))
            if add_texts:
                new_texts.append(self._add_rename_map_text(entry))

        self._maps = maps
        if new_buttons and add_buttons:
            add_buttons(new_buttons, update_before_add=False)
        if new_texts and add_texts:
            add_texts(new_texts, update_before_add=False)

    async def _async_restore_map_backup(self, **kwargs):
        current = find_current_map(self._maps)
        backup = find_backup_for_map(current.get('map_id'), self._map_backups) if current else None
        if backup is None:
            raise HomeAssistantError('No backup available for the current map')
        await self._async_call_map_action('restore_map', [backup.get('map_id')])
        return True

    def _describe_deletable_maps(self):
        current = find_current_map(self._maps)
        current_id = current.get('map_id') if current else None
        return [map_label(m) for m in saved_maps(self._maps) if m.get('map_id') != current_id]

    async def _async_delete_map(self, **kwargs):
        select = self._subs.get('map_to_delete')
        selected = select.current_option if select else None
        if not selected:
            raise HomeAssistantError('No map selected in "Map to Delete"')
        match = next((m for m in saved_maps(self._maps) if map_label(m) == selected), None)
        if match is None:
            raise HomeAssistantError('Map not found - the list may have changed, try refreshing the selection')
        if match.get('is_current'):
            # Not confirmed the device blocks this server-side too - guarded
            # client-side to be safe (same caution as MAX_SAVED_MAPS above).
            raise HomeAssistantError('Cannot delete the currently active map - switch to a different map first')
        await self._async_call_map_action('delete_map', [match.get('map_id')])
        self._maps = [m for m in self._maps if m.get('map_id') != match.get('map_id')]
        return True

    # -- Do Not Disturb (packed start+end time) ---------------------------

    async def _async_read_raw_property(self, siid, piid):
        """Single-property local read helper for DND/schedule below - did
        is not required here, see the comment in _async_read_zones for why."""
        if not self.device.local:
            return None
        try:
            results = await self.device.local.async_get_properties_for_mapping(
                did=self.device.did,
                mapping={'value': {'siid': siid, 'piid': piid}},
            )
        except Exception as exc:
            self.logger.debug('%s: failed to read %s/%s: %s', self.name_model, siid, piid, exc)
            return None
        for item in results or []:
            if item.get('code') == 0:
                return item.get('value')
        return None

    async def _async_setup_dnd_entities(self):
        no_disturb = self._miot_service.spec.get_service('no_disturb')
        prop = no_disturb and no_disturb.get_property('enable_time_period')
        if not prop:
            return
        add_times = self.device.entry.adders.get('time')
        if not add_times:
            return

        raw = await self._async_read_raw_property(prop.siid, prop.iid)
        self._dnd = unpack_dnd_schedule(raw)  # (start_h, start_m, end_h, end_m)
        self._dnd_prop = prop

        new_times = []
        for half in ('start', 'end'):
            sub = f'dnd_{half}'
            self._subs[sub] = _StagingTime(self, sub, option={
                'name': f'{self.device_name} DND {half.capitalize()}',
                'entity_id': sub,
                'native_value': self._dnd_time_value(half),
                'async_set_value_action': self._make_dnd_write_action(half),
            })
            new_times.append(self._subs[sub])
        add_times(new_times, update_before_add=False)

    def _dnd_time_value(self, half):
        from datetime import time as dt_time
        sh, sm, eh, em = self._dnd
        return dt_time(sh % 24, sm % 60) if half == 'start' else dt_time(eh % 24, em % 60)

    def _make_dnd_write_action(self, half):
        async def _do_write(entity, value):
            sh, sm, eh, em = self._dnd
            if half == 'start':
                sh, sm = value.hour, value.minute
            else:
                eh, em = value.hour, value.minute
            packed = pack_dnd_schedule(sh, sm, eh, em)
            result = await self.async_set_miot_property(self._dnd_prop.siid, self._dnd_prop.iid, packed)
            if not result or not result.is_success:
                raise HomeAssistantError(f'Failed to set DND {half}: {result.error if result else "no response"}')
            # Optimistic update - same rationale as maps/zones/rooms above.
            self._dnd = (sh, sm, eh, em)
            entity._attr_native_value = value
            entity.async_write_ha_state()
        return _do_write

    # -- Cleaning schedule (order_clean, single slot) ----------------------

    async def _async_setup_schedule_entities(self):
        prop = self._miot_service.get_property('order_clean')
        if not prop:
            return
        add_switches = self.device.entry.adders.get('switch')
        if not add_switches:
            return
        add_times = self.device.entry.adders.get('time')
        add_selects = self.device.entry.adders.get('select')

        raw = await self._async_read_raw_property(prop.siid, prop.iid)
        self._schedule = decode_schedule(raw)
        self._schedule_prop = prop

        new_switches = []
        self._subs['schedule_enabled'] = _StagingSwitch(self, 'schedule_enabled', option={
            'name': f'{self.device_name} Schedule Enabled',
            'entity_id': 'schedule_enabled',
            'is_on': schedule_enabled(self._schedule),
            'async_turn_on_action': self._make_schedule_enabled_action(True),
            'async_turn_off_action': self._make_schedule_enabled_action(False),
        })
        new_switches.append(self._subs['schedule_enabled'])

        for day in SCHEDULE_DAY_BITS:
            sub = f'schedule_day_{day}'
            self._subs[sub] = _StagingSwitch(self, sub, option={
                'name': f'{self.device_name} Schedule Day: {day.capitalize()}',
                'entity_id': sub,
                'is_on': schedule_day_enabled(self._schedule, day),
                'async_turn_on_action': self._make_schedule_day_action(day, True),
                'async_turn_off_action': self._make_schedule_day_action(day, False),
            })
            new_switches.append(self._subs[sub])
        add_switches(new_switches, update_before_add=False)

        if add_times:
            from datetime import time as dt_time
            hour, minute = schedule_time(self._schedule)
            self._subs['schedule_time'] = _StagingTime(self, 'schedule_time', option={
                'name': f'{self.device_name} Schedule Time',
                'entity_id': 'schedule_time',
                'native_value': dt_time(hour % 24, minute % 60),
                'async_set_value_action': self._async_write_schedule_time,
            })
            add_times([self._subs['schedule_time']], update_before_add=False)

        if add_selects:
            self._subs['schedule_mode'] = _StagingSelect(self, 'schedule_mode', option={
                'name': f'{self.device_name} Schedule Mode',
                'entity_id': 'schedule_mode',
                'options': list(SCHEDULE_MODE_LABELS.values()),
                'current_option': schedule_mode_label(self._schedule),
                'async_select_option_action': self._async_write_schedule_mode,
            })
            add_selects([self._subs['schedule_mode']], update_before_add=False)

    async def _async_write_schedule(self, data):
        result = await self.async_set_miot_property(self._schedule_prop.siid, self._schedule_prop.iid, json.dumps(data))
        if not result or not result.is_success:
            raise HomeAssistantError(f'Failed to write schedule: {result.error if result else "no response"}')
        # Optimistic update - same rationale as maps/zones/rooms above.
        self._schedule = data

    def _make_schedule_enabled_action(self, enabled):
        async def _do_write(entity):
            await self._async_write_schedule(set_schedule_enabled(dict(self._schedule), enabled))
        return _do_write

    def _make_schedule_day_action(self, day, enabled):
        async def _do_write(entity):
            await self._async_write_schedule(set_schedule_day(dict(self._schedule), day, enabled))
        return _do_write

    async def _async_write_schedule_time(self, entity, value):
        await self._async_write_schedule(set_schedule_time(dict(self._schedule), value.hour, value.minute))
        entity._attr_native_value = value
        entity.async_write_ha_state()

    async def _async_write_schedule_mode(self, entity, label):
        await self._async_write_schedule(set_schedule_mode(dict(self._schedule), label))

    # -- Extra sensors (not reliably produced by the generic pipeline) ----

    # (label, unit, device_class) - these five are already listed in this
    # model's built-in `sensor_properties` customization but don't reliably
    # end up as entities for this device (same unresolved gap as the
    # append_converters-based ones above), so they're polled directly here
    # instead, same pattern as everything else in this class.
    EXTRA_SENSOR_PROPS = {
        'cleaning_progress': ('Cleaning Progress', '%', None),
        'last_clean_time': ('Last Clean Time', None, 'timestamp'),
        'statistical_clean_area': ('Total Cleaning Area', 'm²', None),
        'water_tank_status': ('Water Tank Status', None, None),
        'sewage_tank_status': ('Sewage Tank Status', None, None),
        # 'fault' also exists as a generic, untranslated sensor via the
        # normal pipeline (spec gives it no value-list of its own, so that
        # one just shows the raw numeric code, e.g. sensor.xiaomi_ov42gl_
        # e1af_device_fault) - this one uses FAULT_LABELS (empirically
        # reverse-engineered, see converters.py) to show real text instead,
        # same as the intended-but-never-activated MiotFaultLabelConv.
        # Ends up as sensor.fault - distinct entity_id, doesn't collide
        # with the existing raw one, doesn't replace it either.
        'fault': ('Fault Status', None, None),
        # Same story as 'fault' above: base_station_working_status is JSON
        # ({"mode":N,"progress":N}) the generic pipeline would just show
        # raw/undecoded (as sensor.xiaomi_ov42gl_e1af_base_station_working_
        # status) - this one decodes it via BASE_STATION_MODE_LABELS, same
        # logic as the never-activated MiotBaseStationModeConv.
        'base_station_working_status': ('Base Station Activity', None, None),
    }

    async def _async_setup_extra_sensors(self):
        add_sensors = self.device.entry.adders.get('sensor')
        if not add_sensors:
            return
        props = {}
        for name in self.EXTRA_SENSOR_PROPS:
            prop = self._miot_service.get_property(name)
            if prop:
                props[name] = prop
        if not props:
            return
        self._extra_sensor_props = props

        new_sensors = []
        for name, prop in props.items():
            label, unit, device_class = self.EXTRA_SENSOR_PROPS[name]
            sub = f'extra_{name}'
            self._subs[sub] = _PolledSensor(self, sub, option={
                'name': f'{self.device_name} {label}',
                'entity_id': name,
                'unit': unit,
                'device_class': device_class,
            })
            new_sensors.append(self._subs[sub])
        add_sensors(new_sensors, update_before_add=False)

        await self._async_refresh_extra_sensors()
        self.async_on_remove(
            async_track_time_interval(self.hass, self._async_refresh_extra_sensors_tick, timedelta(seconds=30))
        )

    async def _async_refresh_extra_sensors_tick(self, now=None):
        await self._async_refresh_extra_sensors()

    async def _async_refresh_extra_sensors(self):
        props = getattr(self, '_extra_sensor_props', None)
        if not props or not self.device.local:
            return
        mapping = {name: {'siid': p.siid, 'piid': p.iid} for name, p in props.items()}
        try:
            results = await self.device.local.async_get_properties_for_mapping(did=self.device.did, mapping=mapping)
        except Exception as exc:
            self.logger.debug('%s: failed to refresh extra sensors: %s', self.name_model, exc)
            return
        by_siid_piid = {(p.siid, p.iid): name for name, p in props.items()}
        for item in results or []:
            if item.get('code') != 0:
                continue
            name = by_siid_piid.get((item.get('siid'), item.get('piid')))
            entity = self._subs.get(f'extra_{name}') if name else None
            if not entity:
                continue
            value = item.get('value')
            if name == 'last_clean_time' and value:
                from datetime import datetime, timezone
                try:
                    value = datetime.fromtimestamp(int(value), tz=timezone.utc)
                except (TypeError, ValueError, OSError):
                    pass
            elif name == 'fault':
                try:
                    code = int(value)
                except (TypeError, ValueError):
                    code = None
                if code is not None:
                    value = FAULT_LABELS.get(code, f'Unknown fault (code {code})')
            elif name == 'base_station_working_status':
                try:
                    parsed = json.loads(value) if isinstance(value, str) else (value or {})
                except (TypeError, ValueError):
                    parsed = {}
                mode = parsed.get('mode')
                if mode is not None:
                    label = BASE_STATION_MODE_LABELS.get(mode, f'Unknown mode ({mode})')
                    progress = parsed.get('progress')
                    value = f'{label} ({progress}%)' if progress is not None else label
            elif props[name].value_list:
                # water_tank_status/sewage_tank_status are enums (e.g. 0
                # "Not Full"/1 "Full") - the spec's own value_list, not
                # guessed, same source as FAULT_LABELS elsewhere.
                for entry in props[name].value_list:
                    if entry.get('value') == value:
                        value = entry.get('description', value)
                        break
            entity._attr_native_value = value
            entity.async_write_ha_state()

    # -- Ad-hoc area cleaning ("clean this area now", not a saved room or
    # a permanent restricted zone) ----------------------------------------

    async def _async_setup_area_sweep_entities(self):
        action = self._miot_service.get_action('start_zone_sweep')
        if not action:
            return
        add_numbers = self.device.entry.adders.get('number')
        add_selects = self.device.entry.adders.get('select')
        add_buttons = self.device.entry.adders.get('button')
        if not (add_numbers and add_buttons):
            return

        from .number import NumberSubEntity
        from .button import ButtonSubEntity

        self._area_sweep_action = action
        self._pending_areas = []

        coord_option = {'min': -20000, 'max': 20000, 'step': 10, 'native_value': 0}
        new_numbers = []
        for key, label in (
            ('area_x1', 'Area X1'), ('area_y1', 'Area Y1'),
            ('area_x2', 'Area X2'), ('area_y2', 'Area Y2'),
        ):
            self._subs[key] = NumberSubEntity(self, key, option={
                **coord_option,
                'name': f'{self.device_name} {label}',
            })
            new_numbers.append(self._subs[key])
        add_numbers(new_numbers, update_before_add=False)

        if add_selects:
            self._subs['areas_queued'] = _StagingSelect(self, 'areas_queued', option={
                'name': f'{self.device_name} Areas Queued',
                'options_getter': lambda: describe_areas(self._pending_areas) or ['(none)'],
            })
            add_selects([self._subs['areas_queued']], update_before_add=False)

        new_buttons = []
        self._subs['add_area'] = ButtonSubEntity(self, 'add_area', option={
            'name': f'{self.device_name} Add Area',
            'async_press_action': self._async_add_area,
        })
        new_buttons.append(self._subs['add_area'])
        self._subs['clear_areas'] = ButtonSubEntity(self, 'clear_areas', option={
            'name': f'{self.device_name} Clear Areas',
            'async_press_action': self._async_clear_areas,
        })
        new_buttons.append(self._subs['clear_areas'])
        self._subs['clean_areas'] = ButtonSubEntity(self, 'clean_areas', option={
            'name': f'{self.device_name} Clean Areas Now',
            'async_press_action': self._async_clean_areas,
        })
        new_buttons.append(self._subs['clean_areas'])
        add_buttons(new_buttons, update_before_add=False)

    def _area_numbers(self):
        return (
            self._subs['area_x1'].native_value,
            self._subs['area_y1'].native_value,
            self._subs['area_x2'].native_value,
            self._subs['area_y2'].native_value,
        )

    async def _async_add_area(self, **kwargs):
        x1, y1, x2, y2 = self._area_numbers()
        if x1 == x2 and y1 == y2:
            raise HomeAssistantError('Set two different points (Area X1/Y1/X2/Y2) before adding')
        try:
            self._pending_areas = build_area_list(self._pending_areas, x1, y1, x2, y2)
        except ValueError as exc:
            raise HomeAssistantError(str(exc)) from exc

        # Reset the staging inputs so the editor is ready for the next area.
        for key in ('area_x1', 'area_y1', 'area_x2', 'area_y2'):
            entity = self._subs[key]
            entity._attr_native_value = 0
            entity.async_write_ha_state()
        return True

    async def _async_clear_areas(self, **kwargs):
        self._pending_areas = []
        return True

    async def _async_clean_areas(self, **kwargs):
        if not self._pending_areas:
            raise HomeAssistantError(f'No areas queued - add up to {MAX_AREAS} with "Add Area" first')
        payload = area_sweep_payload(self._pending_areas)
        result = await self.async_call_action(self._area_sweep_action, [json.dumps(payload)])
        if not result or not result.is_success:
            raise HomeAssistantError(f'Failed to start area sweep: {result.error if result else "no response"}')
        # This is "clean now and forget", not a persistent config like
        # zones - nothing to keep around after a successful send.
        self._pending_areas = []
        return True
