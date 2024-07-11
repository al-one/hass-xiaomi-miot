"""Support for Xiaomi sensors."""
import logging
import time
import json
from typing import cast
from datetime import datetime, timedelta
from functools import partial, cmp_to_key

from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    CONF_HOST,
    CONF_NAME,
    CONF_TOKEN,
    PERCENTAGE,
    STATE_UNKNOWN,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.helpers.entity import (
    Entity,
)
from homeassistant.components.sensor import (
    DOMAIN as ENTITY_DOMAIN,
    SensorDeviceClass,
)
from homeassistant.helpers.restore_state import RestoreEntity, RestoredExtraData
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import (
    DOMAIN,
    CONF_MODEL,
    CONF_XIAOMI_CLOUD,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    MiioEntity,
    MiotEntity,
    BaseSubEntity,
    MiCoordinatorEntity,
    MiotPropertySubEntity,
    MiotCloud,
    DeviceException,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
    MiotProperty,
)
from .core.utils import local_zone, get_translation

try:
    # hass 2021.4.0b0+
    from homeassistant.components.sensor import SensorEntity
except ImportError:
    class SensorEntity(Entity):
        """Base class for sensor entities."""

try:
    # hass 2021.6.0b0+
    from homeassistant.components.sensor import STATE_CLASSES
except ImportError:
    STATE_CLASSES = []

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    cfg = hass.data[DOMAIN].get(config_entry.entry_id) or {}
    mic = cfg.get(CONF_XIAOMI_CLOUD)
    config_data = config_entry.data or {}

    if isinstance(mic, MiotCloud) and mic.user_id:
        if not config_data.get('disable_message'):
            hass.data[DOMAIN]['accounts'].setdefault(mic.user_id, {})

            if not hass.data[DOMAIN]['accounts'][mic.user_id].get('messenger'):
                entity = MihomeMessageSensor(hass, mic)
                hass.data[DOMAIN]['accounts'][mic.user_id]['messenger'] = entity
                async_add_entities([entity], update_before_add=False)

        if not config_data.get('disable_scene_history'):
            homes = await mic.async_get_homerooms()
            for home in homes:
                home_id = home.get('id')
                if hass.data[DOMAIN]['accounts'][mic.user_id].get(f'scene_history_{home_id}'):
                    continue

                entity = MihomeSceneHistorySensor(hass, mic, home_id, home.get('uid'))
                hass.data[DOMAIN]['accounts'][mic.user_id][f'scene_history_{home_id}'] = entity
                async_add_entities([entity], update_before_add=False)

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
            'battery', 'environment', 'tds_sensor', 'switch_sensor', 'vibration_sensor', 'occupancy_sensor',
            'temperature_humidity_sensor', 'illumination_sensor', 'gas_sensor', 'smoke_sensor', 'pressure_sensor',
            'router', 'lock', 'door', 'washer', 'printer', 'sleep_monitor', 'bed', 'walking_pad', 'treadmill',
            'oven', 'microwave_oven', 'health_pot', 'coffee_machine', 'multifunction_cooking_pot',
            'cooker', 'induction_cooker', 'pressure_cooker', 'air_fryer', 'juicer', 'electric_steamer',
            'water_purifier', 'dishwasher', 'fruit_vegetable_purifier',
            'pet_feeder', 'cat_toilet', 'fridge_chamber', 'plant_monitor', 'germicidal_lamp', 'vital_signs',
            'sterilizer', 'steriliser', 'table', 'chair', 'dryer', 'clothes_dryer',
        ):
            if srv.name in ['lock']:
                if not srv.get_property('operation_method', 'operation_id'):
                    continue
            elif srv.name in ['door']:
                if spec.get_service('lock'):
                    continue
            elif srv.name in ['battery']:
                if spec.name not in ['switch_sensor', 'toothbrush']:
                    continue
            elif srv.name in ['environment']:
                if spec.name not in ['air_monitor']:
                    continue
            elif srv.name in ['tds_sensor']:
                if spec.get_service('water_purifier', 'fish_tank'):
                    continue
            elif srv.name in ['temperature_humidity_sensor']:
                if spec.name not in ['temperature_humidity_sensor']:
                    continue
            elif srv.name in ['illumination_sensor']:
                if spec.name not in ['illumination_sensor']:
                    continue
            elif srv.name in ['pet_feeder', 'table']:
                # no readable properties in mmgg.feeder.petfeeder
                # nineam.desk.hoo01
                pass
            elif not srv.mapping():
                continue
            if srv.get_property('cook_mode') or srv.get_action('start_cook', 'cancel_cooking'):
                entities.append(MiotCookerEntity(config, srv))
            elif srv.name in ['oven', 'microwave_oven']:
                entities.append(MiotCookerEntity(config, srv))
            else:
                entities.append(MiotSensorEntity(config, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=False)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


def datetime_with_tzinfo(value):
    if isinstance(value, datetime):
        pass
    elif isinstance(value, str):
        value = datetime.fromisoformat(value)
    elif isinstance(value, (int, float)):
        value = datetime.fromtimestamp(value)
    else:
        value = cast(datetime, value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=local_zone())
    return value


class MiotSensorEntity(MiotEntity, SensorEntity):

    def __init__(self, config, miot_service: MiotService):
        super().__init__(miot_service, config=config, logger=_LOGGER)

        first_property = None
        if len(miot_service.properties) > 0:
            first_property = list(miot_service.properties.values() or [])[0].name
        self._prop_state = miot_service.get_property(
            'status', 'fault', first_property or 'status',
        )
        if miot_service.name in ['lock']:
            self._prop_state = miot_service.get_property('operation_method') or self._prop_state
        elif miot_service.name in ['tds_sensor']:
            self._prop_state = miot_service.get_property('tds_out') or self._prop_state
        elif miot_service.name in ['temperature_humidity_sensor']:
            self._prop_state = miot_service.get_property(
                'temperature', 'indoor_temperature', 'relative_humidity',
            ) or self._prop_state
        elif miot_service.name in ['sleep_monitor']:
            self._prop_state = miot_service.get_property('sleep_state') or self._prop_state
        elif miot_service.name in ['gas_sensor']:
            self._prop_state = miot_service.get_property('gas_concentration') or self._prop_state
        elif miot_service.name in ['smoke_sensor']:
            self._prop_state = miot_service.get_property('smoke_concentration') or self._prop_state
        elif miot_service.name in ['occupancy_sensor']:
            self._prop_state = miot_service.get_property('occupancy_status') or self._prop_state
        elif miot_service.name in ['pressure_sensor']:
            self._prop_state = miot_service.get_property('pressure_present_duration') or self._prop_state

        self._attr_icon = self._miot_service.entity_icon
        self._attr_state_class = None
        self._attr_native_unit_of_measurement = None
        if self._prop_state:
            self._name = f'{self.device_name} {self._prop_state.friendly_desc}'
            self._attr_icon = self._prop_state.entity_icon or self._attr_icon
            self._attr_state_class = self._prop_state.state_class

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if prop := self.custom_config('state_property'):
            self._prop_state = self._miot_service.get_property_by_full_name(prop) or self._prop_state
        if self._prop_state:
            self._attr_icon = self._prop_state.entity_icon
            self._attr_device_class = self._prop_state.device_class
            self._attr_native_unit_of_measurement = self._prop_state.unit_of_measurement
            self._state_attrs.update({
                'state_property': self._prop_state.full_name,
            })

        cls = self.custom_config('state_class')
        if cls in STATE_CLASSES:
            self._attr_state_class = cls
        elif cls in ['', False]:
            self._attr_state_class = None

        if uom := self.custom_config('unit_of_measurement'):
            self._attr_native_unit_of_measurement = uom

        if act := self._miot_service.get_action('pet_food_out'):
            prop = self._miot_service.get_property('feeding_measure')
            add_switches = self._add_entities.get('switch')
            if prop and add_switches:
                from .switch import MiotSwitchActionSubEntity
                fnm = prop.unique_name
                self._subs[fnm] = MiotSwitchActionSubEntity(self, prop, act)
                add_switches([self._subs[fnm]], update_before_add=True)

    async def async_update(self):
        await super().async_update()
        if not self._available or not self._prop_state:
            return
        if self._miot_service.name in ['lock'] and self._prop_state.full_name not in self._state_attrs:
            if how := self._state_attrs.get('lock_method'):
                await self.async_update_attrs({
                    self._prop_state.full_name: get_translation(how, ['lock_method']),
                })
            elif edt := self._state_attrs.get('event.11', {}):
                if isinstance(edt, dict):
                    await self.async_update_attrs({
                        self._prop_state.full_name: edt.get('method'),
                    })
        self._prop_state.description_to_dict(self._state_attrs)

    async def async_update_for_main_entity(self):
        await super().async_update_for_main_entity()

        if self._miot_service.name in ['washer']:
            pls = self._miot_service.get_properties(
                'mode', 'spin_speed', 'rinsh_times',
                'target_temperature', 'target_water_level',
                'drying_level', 'drying_time',
            )
            for p in pls:
                if not p.value_list and not p.value_range:
                    continue
                if self.entry_config_version >= 0.3:
                    opt = {
                        'before_select': self.before_select_modes,
                    }
                    self._update_sub_entities(p, None, 'select', option=opt)
                else:
                    self._update_sub_entities(p, None, 'fan')
            add_switches = self._add_entities.get('switch')
            if self._miot_service.get_action('start_wash', 'pause'):
                pnm = 'action'
                prop = self._miot_service.get_property('status')
                if pnm in self._subs:
                    self._subs[pnm].update_from_parent()
                elif add_switches and prop:
                    from .switch import MiotWasherActionSubEntity
                    self._subs[pnm] = MiotWasherActionSubEntity(self, prop)
                    add_switches([self._subs[pnm]], update_before_add=True)

        self._update_sub_entities(
            [
                'download_speed', 'upload_speed', 'connected_device_number', 'network_connection_type',
                'ip_address', 'online_time', 'wifi_ssid', 'wifi_bandwidth',
            ],
            ['router', 'wifi', 'guest_wifi'],
            domain='sensor',
        )
        self._update_sub_entities(
            ['on'],
            [self._miot_service.name, 'router', 'wifi', 'guest_wifi'],
            domain='switch',
        )
        self._update_sub_entities(
            [
                'temperature', 'relative_humidity', 'humidity', 'pm2_5_density',
                'battery_level', 'soil_ec', 'illumination', 'atmospheric_pressure',
            ],
            ['temperature_humidity_sensor', 'illumination_sensor', 'plant_monitor'],
            domain='sensor',
        )
        self._update_sub_entities(
            [
                'mode_time', 'start_pause', 'leg_pillow', 'rl_control',
                'heat_level', 'heat_time', 'heat_zone', 'intensity_mode', 'massage_strength',
            ],
            [
                'bed', 'backrest_control', 'leg_rest_control', 'massage_mattress', 'fridge',
            ],
            domain='fan',
        )
        self._update_sub_entities(
            ['motor_control', 'backrest_angle', 'leg_rest_angle'],
            ['bed', 'backrest_control', 'leg_rest_control'],
            domain='cover',
        )

    @property
    def device_class(self):
        """Return the class of this entity."""
        return self.get_device_class(SensorDeviceClass)

    @property
    def native_value(self):
        if not self._prop_state:
            return None
        key = f'{self._prop_state.full_name}_desc'
        if key in self._state_attrs:
            return f'{self._state_attrs[key]}'.lower()
        return self._prop_state.from_dict(self._state_attrs)

    def before_select_modes(self, prop, option, **kwargs):
        if prop := self._miot_service.get_property('on'):
            ion = prop.from_dict(self._state_attrs)
            if not ion:
                return self.set_property(prop, True)
        return False


class MiotCookerEntity(MiotSensorEntity):
    def __init__(self, config, miot_service: MiotService):
        super().__init__(config, miot_service)
        self._prop_state = miot_service.get_property('status')
        self._action_start = miot_service.get_action('start_cook')
        self._action_cancel = miot_service.get_action('cancel_cooking', 'pause')

        self._values_on = []
        self._values_off = []
        if self._prop_state:
            self._attr_icon = self._prop_state.entity_icon or 'mdi:chef-hat'
            self._values_on = self._prop_state.list_search('Busy', 'Running', 'Cooking', 'Delay')
            self._values_off = self._prop_state.list_search(
                'Idle', 'Completed', 'Shutdown', 'CookFinish', 'Pause', 'Paused', 'Fault', 'Error', 'Stop', 'Off',
            )

    async def async_update(self):
        await super().async_update()
        if not self._available:
            return
        if self._prop_state:
            self._update_sub_entities(
                ['target_temperature'],
                domain='number',
            )
            add_fans = self._add_entities.get('fan')
            add_selects = self._add_entities.get('select')
            add_switches = self._add_entities.get('switch')
            pls = self._miot_service.get_properties(
                'mode', 'cook_mode', 'heat_level', 'target_time', 'target_temperature',
            )
            for p in pls:
                opt = None
                if p.name in self._subs:
                    self._subs[p.name].update_from_parent()
                elif not (p.value_list or p.value_range):
                    continue
                elif add_selects:
                    from .select import (
                        MiotSelectSubEntity,
                        MiotActionSelectSubEntity,
                    )
                    if p.writeable:
                        self._subs[p.name] = MiotSelectSubEntity(self, p)
                    elif not self._action_start:
                        continue
                    elif p.iid in self._action_start.ins:
                        if self._action_cancel:
                            opt = {
                                'extra_actions': {
                                    p.get_translation('Off'): self._action_cancel,
                                },
                            }
                        self._subs[p.name] = MiotActionSelectSubEntity(self, self._action_start, p, opt)
                    if p.name in self._subs:
                        add_selects([self._subs[p.name]], update_before_add=True)
                elif add_fans:
                    if p.value_list:
                        opt = {
                            'values_on':  self._values_on,
                            'values_off': self._values_off,
                        }
                    from .fan import MiotCookerSubEntity
                    self._subs[p.name] = MiotCookerSubEntity(self, p, self._prop_state, opt)
                    add_fans([self._subs[p.name]], update_before_add=True)
            if self._action_start or self._action_cancel:
                pnm = 'cook_switch'
                if pnm in self._subs:
                    self._subs[pnm].update_from_parent()
                elif add_switches:
                    from .switch import MiotCookerSwitchSubEntity
                    self._subs[pnm] = MiotCookerSwitchSubEntity(self, self._prop_state)
                    add_switches([self._subs[pnm]], update_before_add=True)

    @property
    def is_on(self):
        val = self._prop_state.from_dict(self._state_attrs)
        return val not in [*self._values_off, None]

    def turn_on(self, **kwargs):
        return self.turn_action(True)

    def turn_off(self, **kwargs):
        return self.turn_action(False)

    def turn_action(self, on):
        ret = False
        act = self._action_start if on else self._action_cancel
        vls = self._values_on if on else self._values_off
        if act:
            pms = []
            if on:
                pms = self.custom_config_list('start_cook_params') or []
            ret = self.call_action(act, pms)
            sta = vls[0] if vls else None
            if ret and sta is not None:
                self.update_attrs({
                    self._prop_state.full_name: sta,
                })
        else:
            _LOGGER.warning('%s: Miot device has no turn_action: %s', self.name_model, on)
        return ret


class BaseSensorSubEntity(BaseSubEntity, SensorEntity):
    def __init__(self, parent, attr, option=None, **kwargs):
        kwargs.setdefault('domain', ENTITY_DOMAIN)
        self._attr_state_class = None
        super().__init__(parent, attr, option, **kwargs)

    @property
    def native_value(self):
        value = self._attr_state
        if hasattr(self, '_attr_native_value') and self._attr_native_value is not None:
            value = self._attr_native_value
        value = get_translation(value, [self._attr])
        if self.device_class == SensorDeviceClass.TIMESTAMP:
            value = datetime_with_tzinfo(value)
        return value

    @property
    def state_class(self):
        return self._attr_state_class

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        cls = self.custom_config('state_class')
        if cls in STATE_CLASSES:
            self._attr_state_class = cls
        elif cls in ['', False]:
            self._attr_state_class = None

        if uom := self.custom_config('unit_of_measurement'):
            self._attr_native_unit_of_measurement = uom

    def update(self, data=None):
        old_state = self._attr_state
        super().update(data)

        now = datetime.now(tz=local_zone(self.hass))
        if self.state_class in ['total_increasing'] and old_state not in [None, '', STATE_UNKNOWN]:
            ptm = self._extra_attrs.get('updated_time') or now
            if now.strftime('%Y-%m-%d') == ptm.strftime('%Y-%m-%d'):
                try:
                    if (self._attr_state or 0) < old_state:
                        self._attr_state = old_state
                except (TypeError, ValueError) as exc:
                    _LOGGER.warning(
                        '%s: Total increasing sensor state error: %s',
                        self.name_model, [exc, self._attr_state, old_state],
                    )
        if self._attr_state != old_state:
            self._extra_attrs['updated_time'] = now


class MiotSensorSubEntity(MiotPropertySubEntity, BaseSensorSubEntity):
    def __init__(self, parent, miot_property: MiotProperty, option=None):
        super().__init__(parent, miot_property, option, domain=ENTITY_DOMAIN)
        self._attr_state_class = miot_property.state_class

        self._prop_battery = None
        for s in self._miot_service.spec.get_services('battery', self._miot_service.name):
            p = s.get_property('battery_level')
            if p:
                self._prop_battery = p
        if self._prop_battery:
            self._option['keys'] = [*(self._option.get('keys') or []), self._prop_battery.full_name]

    async def async_added_to_hass(self):
        await BaseSensorSubEntity.async_added_to_hass(self)

    def update(self, data=None):
        super().update(data)
        if not self._available:
            return
        self.update_with_properties()
        self._miot_property.description_to_dict(self._state_attrs)

    @property
    def native_value(self):
        if not self._attr_native_unit_of_measurement:
            key = f'{self._miot_property.full_name}_desc'
            if key in self._state_attrs:
                return f'{self._state_attrs[key]}'.lower()
        val = self._miot_property.from_dict(self._state_attrs)
        if val is not None:
            svd = self.custom_config_number('value_ratio') or 0
            if svd:
                val = round(float(val) * svd, 3)
            elif self.device_class in [SensorDeviceClass.HUMIDITY, SensorDeviceClass.TEMPERATURE]:
                val = round(float(val), 3)
        return val


class MihomeMessageSensor(MiCoordinatorEntity, SensorEntity, RestoreEntity):
    _filter_homes = None
    _exclude_types = None
    _has_none_message = False

    def __init__(self, hass, cloud: MiotCloud):
        self.hass = hass
        self.cloud = cloud
        self.message = {}
        self.entity_id = f'{ENTITY_DOMAIN}.mi_{cloud.user_id}_message'
        self._attr_unique_id = f'{DOMAIN}-mihome-message-{cloud.user_id}'
        self._attr_name = f'Xiaomi {cloud.user_id} message'
        self._attr_icon = 'mdi:message'
        self._attr_should_poll = False
        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            'entity_class': self.__class__.__name__,
        }
        self.coordinator = DataUpdateCoordinator(
            hass,
            _LOGGER,
            name=self._attr_unique_id,
            update_method=self.fetch_latest_message,
            update_interval=timedelta(seconds=15),
        )
        super().__init__(self.coordinator)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.hass.data[DOMAIN]['entities'][self.entity_id] = self
        self._filter_homes = self.custom_config_list('filter_home') or []
        self._exclude_types = list(map(lambda x: int(x), self.custom_config_list('exclude_type', [13]) or []))
        if sec := self.custom_config_integer('interval_seconds'):
            self.coordinator.update_interval = timedelta(seconds=sec)

        if restored := await self.async_get_last_extra_data():
            self._attr_native_value = restored.as_dict().get('state')
            self._attr_extra_state_attributes.update(restored.as_dict().get('attrs', {}))

        self._attr_extra_state_attributes['filter_homes'] = self._filter_homes
        self._attr_extra_state_attributes['exclude_types'] = self._exclude_types
        await self.coordinator.async_config_entry_first_refresh()

    async def async_will_remove_from_hass(self):
        """Run when entity will be removed from hass.
        To be extended by integrations.
        """
        await super().async_will_remove_from_hass()
        self.hass.data[DOMAIN]['accounts'].get(self.cloud.user_id, {}).pop('messenger', None)

    @property
    def extra_restore_state_data(self):
        """Return entity specific state data to be restored."""
        return RestoredExtraData({
            'state': self.native_value,
            'attrs': self._attr_extra_state_attributes,
        })

    async def async_set_message(self, msg):
        if msg == self.message:
            return
        if old := self._attr_native_value:
            self._attr_extra_state_attributes['prev_message'] = old
        con = msg.get('content')
        if tit := msg.get('title'):
            if con:
                self._attr_native_value = f'{con}: {tit}'
            else:
                self._attr_native_value = tit
            logger = _LOGGER.info if old != self._attr_native_value else _LOGGER.debug
            logger('New xiaomi message for %s: %s', self.cloud.user_id, self._attr_native_value)
        tim = msg.get('ctime')
        params = msg.get('params', {})
        body = params.get('body', {})
        self._attr_entity_picture = msg.get('img_url') or None
        self._attr_extra_state_attributes.update({
            'msg_id': msg.get('msg_id'),
            'is_new': msg.get('is_new'),
            'type': msg.get('type'),
            'title': tit,
            'content': con,
            'user_id': msg.get('uid'),
            'ctime': tim,
            'timestamp': datetime.fromtimestamp(tim, local_zone()) if tim else None,
            'model': params.get('model', body.get('model')),
            'device_id': msg.get('did', body.get('did')),
            'home_name': msg.get('homeName'),
            'room_name': msg.get('roomName'),
            'event': body.get('event'),
            'event_data': body.get('extra', body.get('value')),
        })

    async def fetch_latest_message(self):
        res = await self.cloud.async_request_api('v2/message/v2/typelist', data={}) or {}
        mls = (res.get('result') or {}).get('messages') or []
        mls.sort(key=lambda x: x.get('ctime', 0), reverse=False)
        prev_time = self._attr_extra_state_attributes.get('ctime')
        prev_mid = self._attr_extra_state_attributes.get('msg_id')
        msg = {}
        for m in mls:
            hre = m.get('params', {}).get('body', {}).get('homeRoomExtra', {})
            home = hre.get('homeName')
            if self._filter_homes and home and home not in self._filter_homes:
                continue
            typ = m.get('type', 0)
            if self._exclude_types and typ in self._exclude_types:
                continue
            tim = m.get('ctime', 0)
            mid = m.get('msg_id', 0)
            if prev_time and tim < prev_time:
                continue
            if prev_mid and mid <= prev_mid:
                continue
            m['homeName'] = home
            m['roomName'] = hre.get('roomName')
            msg = m
            break
        if not mls:
            if not self._has_none_message:
                # Only raise a warning if there was a failure obtaining the xiaomi message
                # Otherwise, a warning will show anytime that there are simply no messages waiting
                if res['code'] == 0 and res['message'] == 'ok':
                    _LOGGER.debug('Get xiaomi message for %s failed: %s', self.cloud.user_id, res)
                else:
                    _LOGGER.warning('Get xiaomi message for %s failed: %s', self.cloud.user_id, res)
            self._has_none_message = True
        if msg:
            await self.async_set_message(msg)
            self.message = msg
            self._has_none_message = False
        return msg


class MihomeSceneHistorySensor(MiCoordinatorEntity, SensorEntity, RestoreEntity):
    MESSAGE_TIMEOUT = 60
    UPDATE_INTERVAL = 15

    _has_none_message = False

    def __init__(self, hass, cloud: MiotCloud, home_id, owner_user_id):
        self.hass = hass
        self.cloud = cloud
        self.home_id = int(home_id)
        self.owner_user_id = int(owner_user_id)
        self.entity_id = f'{ENTITY_DOMAIN}.mi_{cloud.user_id}_{home_id}_scene_history'
        self._attr_unique_id = f'{DOMAIN}-mihome-scene-history-{cloud.user_id}_{home_id}'
        self._attr_name = f'Xiaomi {cloud.user_id}_{home_id} Scene History'
        self._attr_icon = 'mdi:message'
        self._attr_should_poll = False
        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            'entity_class': self.__class__.__name__,
        }
        self.coordinator = DataUpdateCoordinator(
            hass,
            _LOGGER,
            name=self._attr_unique_id,
            update_method=self.fetch_latest_message,
            update_interval=timedelta(seconds=self.UPDATE_INTERVAL),
        )
        super().__init__(self.coordinator)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.hass.data[DOMAIN]['entities'][self.entity_id] = self
        if sec := self.custom_config_integer('interval_seconds'):
            self.coordinator.update_interval = timedelta(seconds=sec)

        if restored := await self.async_get_last_extra_data():
            restored_dict = restored.as_dict()

            attrs = restored_dict.get('attrs', {})
            if ts := attrs.get('ts'):
                attrs['timestamp'] = datetime.fromtimestamp(ts, local_zone()) if ts else None

            _LOGGER.debug(
                'xiaomi scene history %s %d, async_added_to_hass restore state: state= %s attrs= %s',
                self.cloud.user_id, self.home_id, restored_dict.get('state'), attrs,
            )
            self._attr_native_value = restored_dict.get('state')
            self._attr_extra_state_attributes.update(attrs)

        await self.coordinator.async_config_entry_first_refresh()

    async def async_will_remove_from_hass(self):
        """Run when entity will be removed from hass.
        To be extended by integrations.
        """
        await super().async_will_remove_from_hass()
        self.hass.data[DOMAIN]['accounts'].get(self.cloud.user_id, {}).pop(f'scene_history_{self.home_id}', None)

    @property
    def extra_restore_state_data(self):
        """Return entity specific state data to be restored."""
        return RestoredExtraData({
            'state': self.native_value,
            'attrs': self._attr_extra_state_attributes,
        })

    def trim_message(self, msg):
        ts = msg.get('time') or int(time.time())
        return {
            "from": msg.get('from'),
            "name": msg.get('name'),
            "ts": ts,
            'timestamp': datetime.fromtimestamp(ts, local_zone()),
            "scene_id": str(msg.get('userSceneId')),
            "targets": msg.get('msg', []),
        }

    @staticmethod
    def _cmp_message(a, b):
        a_ts, b_ts = a.get('ts', 0), b.get('ts', 0)
        if a_ts != b_ts:
            return a_ts - b_ts
        
        a_scene_id, b_scene_id = a.get('scene_id', 0), b.get('scene_id', 0)
        if a_scene_id < b_scene_id:
            return -1
        if a_scene_id > b_scene_id:
            return 1
        return 0

    async def async_set_message(self, msg):
        self._attr_native_value = msg.get('name')
        _LOGGER.debug('New xiaomi scene history for %s %d: %s', self.cloud.user_id, self.home_id, self._attr_native_value)

        old = self._attr_extra_state_attributes or {}
        self._attr_extra_state_attributes.update({**msg, 'prev_value': old.get('name'), 'prev_scene_id': old.get('scene_id')})

    async def fetch_latest_message(self):
        res = await self.cloud.async_request_api('scene/history', data={
            "home_id": self.home_id,
            "uid": int(self.cloud.user_id),
            "owner_uid": self.owner_user_id,
            "command": "history",
            "limit": 15,
        }) or {}

        messages = [self.trim_message(msg) for msg in (res.get('result') or {}).get('history') or []]
        if not messages:
            if not self._has_none_message:
                _LOGGER.warning('Get xiaomi scene history for %s %d failed: %s', self.cloud.user_id, self.home_id, res)

            self._has_none_message = True
            return {}

        messages.sort(key=cmp_to_key(self._cmp_message), reverse=False)
        _LOGGER.debug(
            'Get xiaomi scene history for %s %d success: prev_timestamp= %d prev_scene_id= %s messages= %s,',
            self.cloud.user_id, self.home_id,
            self._attr_extra_state_attributes.get('ts') or 0,
            self._attr_extra_state_attributes.get('scene_id') or '',
            messages,
        )

        must_after = int(time.time()) - self.MESSAGE_TIMEOUT
        for msg in messages:
            if msg.get('ts') < must_after:
                continue

            if self._cmp_message(msg, self._attr_extra_state_attributes) <= 0:
                continue

            await self.async_set_message(msg)
            self._has_none_message = False
            return msg

        return {}


class XiaoaiConversationSensor(MiCoordinatorEntity, BaseSensorSubEntity):
    def __init__(self, parent, hass, option=None):
        BaseSensorSubEntity.__init__(self, parent, 'conversation', option)
        self.hass = hass
        self.conversation = {}
        self._available = True
        self._attr_native_value = None
        self._option.setdefault('icon', 'mdi:account-voice')
        self.coordinator = DataUpdateCoordinator(
            hass,
            _LOGGER,
            name=self.unique_id,
            update_method=self.fetch_latest_message,
            update_interval=timedelta(seconds=5),
        )
        super().__init__(self.coordinator)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.hass.data[DOMAIN]['entities'][self.entity_id] = self
        await self.coordinator.async_config_entry_first_refresh()
        if sec := self.custom_config_integer('interval_seconds'):
            self.coordinator.update_interval = timedelta(seconds=sec)

    async def fetch_latest_message(self):
        mic = self._parent.xiaoai_cloud
        dvc = self._parent.xiaoai_device or {}
        aid = dvc.get('deviceID')
        if not isinstance(mic, MiotCloud) or not aid:
            self._available = False
            return
        api = 'https://userprofile.mina.mi.com/device_profile/v2/conversation'
        dat = {
            'hardware': dvc.get('hardware', ''),
            'timestamp': int(time.time() * 1000),
            'limit': 3,
        }
        cks = {
            'deviceId': aid,
        }
        try:
            res = await mic.async_request_api(api, data=dat, method='GET', cookies=cks) or {}
            rdt = res.get('data', {})
            if not isinstance(rdt, dict):
                rdt = json.loads(rdt) or {}
        except (TypeError, ValueError, Exception) as exc:
            rdt = {}
            _LOGGER.warning(
                '%s: Got exception while fetch xiaoai conversation: %s',
                self.name_model, [aid, exc],
            )
        mls = rdt.get('records') or []
        msg = mls.pop(0) if mls else {}
        self.conversation = msg
        old = self._attr_native_value
        if con := msg.get('query'):
            self._state = con
            self._attr_native_value = con
            logger = _LOGGER.info if old != self._attr_native_value else _LOGGER.debug
            logger('%s: New xiaoai conversation: %s', self.name_model, self._attr_native_value)
        tim = msg.get('time')
        ans = []
        for v in msg.get('answers', []):
            if not isinstance(v, dict):
                continue
            typ = v.get('type', '').lower()
            v.pop('bitSet', None)
            v.get(typ, {}).pop('bitSet', None)
            ans.append(v)
        self._state_attrs.update({
            'content': con,
            'answers': ans,
            'history': [
                v.get('query')
                for v in mls
            ],
            'timestamp': datetime.fromtimestamp(tim / 1000, local_zone()) if tim else None,
        })
        return msg
