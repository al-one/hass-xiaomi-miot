"""Support for Xiaomi binary sensors."""
import logging
import time
import json
from datetime import datetime

from homeassistant.const import (
        STATE_OFF,
        STATE_ON,
        STATE_UNKNOWN,
)
from homeassistant.components.binary_sensor import (
    DOMAIN as ENTITY_DOMAIN,
    BinarySensorEntity,
    BinarySensorDeviceClass,
)

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    MiotToggleEntity,
    MiotPropertySubEntity,
    ToggleSubEntity,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
    MiotProperty,
)
from .core.xiaomi_cloud import MiotCloud
from .core.utils import local_zone

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    await async_setup_config_entry(hass, config_entry, async_setup_platform, async_add_entities, ENTITY_DOMAIN)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data.setdefault(DATA_KEY, {})
    hass.data[DOMAIN]['add_entities'][ENTITY_DOMAIN] = async_add_entities
    config['hass'] = hass
    did = str(config.get('miot_did') or '')
    model = str(config.get(CONF_MODEL) or '')
    spec = hass.data[DOMAIN]['miot_specs'].get(model)
    entities = []
    if isinstance(spec, MiotSpec):
        for srv in spec.get_services(
            'toilet', 'seat', 'motion_sensor', 'magnet_sensor', 'submersion_sensor', 'alertor',
        ):
            if spec.get_service('nobody_time'):
                # lumi.motion.agl02
                # lumi.motion.agl04
                pass
            elif model in ['lumi.sensor_wleak.aq1', 'htcx.alarm.dt210']:
                pass
            elif not srv.mapping():
                continue
            if srv.name in ['toilet']:
                entities.append(MiotToiletEntity(config, srv))
            elif srv.name in ['seat'] and spec.name in ['toilet']:
                if spec.get_service('toilet'):
                    continue
                # tinymu.toiletlid.v1
                entities.append(MiotToiletEntity(config, srv))
            elif 'blt.' in did:
                entities.append(BleBinarySensorEntity(config, srv))
            elif 'lumi.' in model:
                entities.append(LumiBinarySensorEntity(config, srv))
            else:
                entities.append(MiotBinarySensorEntity(config, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotBinarySensorEntity(MiotToggleEntity, BinarySensorEntity):
    def __init__(self, config, miot_service: MiotService, **kwargs):
        kwargs.setdefault('logger', _LOGGER)
        super().__init__(miot_service, config=config, **kwargs)

        pls = []
        if len(miot_service.properties) > 0:
            first_property = list(miot_service.properties.values() or [])[0].name
            if first_property:
                pls.append(first_property)
        self._prop_state = miot_service.get_property(*pls)

        if miot_service.name in ['motion_sensor']:
            self._prop_state = miot_service.get_property('motion_state', 'no_motion_duration') or self._prop_state
            if self._prop_state.name in ['illumination']:
                # cgllc.motion.cgpr1
                self._prop_state = None
            self._attr_device_class = BinarySensorDeviceClass.MOTION
            if self._prop_state is None:
                srv = miot_service.spec.get_service('nobody_time')
                if srv:
                    self._prop_state = srv.get_property('nobody_time')

        if miot_service.name in ['magnet_sensor']:
            self._prop_state = miot_service.get_property('contact_state') or self._prop_state
            if self._prop_state and self._prop_state.name in ['contact_state']:
                # https://github.com/al-one/hass-xiaomi-miot/issues/270
                self._vars['reverse_state'] = True
            self._attr_device_class = BinarySensorDeviceClass.DOOR

        if miot_service.name in ['submersion_sensor']:
            self._prop_state = miot_service.get_property('submersion_state') or self._prop_state
            self._attr_device_class = BinarySensorDeviceClass.MOISTURE

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if prop := self.custom_config('state_property'):
            self._prop_state = self._miot_service.get_property_by_full_name(prop) or self._prop_state
        self._state_attrs.update({
            'state_property': self._prop_state.full_name if self._prop_state else None,
        })
        rev = self.custom_config_bool('reverse_state', None)
        if rev is not None:
            self._vars['reverse_state'] = rev

    async def async_update_for_main_entity(self):
        await super().async_update_for_main_entity()
        self._update_sub_entities(['illumination', 'no_motion_duration'], domain='sensor')

    @property
    def is_on(self):
        ret = self._state
        if self._prop_state:
            val = self._prop_state.from_dict(self._state_attrs)
            if val is None:
                pass
            elif self._prop_state.name in ['no_motion_duration', 'nobody_time']:
                if self._prop_state.unit in ['minutes']:
                    val *= 60
                dur = self.custom_config_integer('motion_timeout')
                if dur is None and self._prop_state.value_range:
                    stp = self._prop_state.range_step()
                    if stp >= 10:
                        dur = self._prop_state.range_min() + stp
                if dur is None:
                    dur = 60
                ret = val <= dur
            elif self._prop_state.value_list:
                # linp.magnet.m1
                if des := self._prop_state.list_description(val):
                    des = f'{des}'.lower()
                return des in ['open', 'opened']
            else:
                ret = val
        if self._vars.get('reverse_state'):
            ret = not ret
        return ret

    @property
    def state(self):
        iso = self.is_on
        if iso is None:
            return STATE_UNKNOWN
        return STATE_ON if iso else STATE_OFF

    @property
    def device_class(self):
        return self.get_device_class(BinarySensorDeviceClass)


class BleBinarySensorEntity(MiotBinarySensorEntity):
    def __init__(self, config, miot_service: MiotService):
        super().__init__(config, miot_service)
        self._prop_illumination = miot_service.get_property('illumination')
        if not self._prop_illumination:
            if srv := miot_service.spec.get_service('illumination_sensor'):
                self._prop_illumination = srv.get_property('illumination')

        # https://iot.mi.com/new/doc/embedded-development/ble/object-definition
        self._props = [
            'event.15',   # 0x000F motion&illumination
            'prop.4103',  # 0x1007 lux
            'prop.4106',  # 0x100A battery
            'prop.4117',  # 0x1015 smoke
            'prop.4119',  # 0x1017 no_motion_duration
            'prop.4123',  # 0x101B no_motion_timeout
            'prop.4120',  # 0x1018 illumination_level
            'prop.4121',  # 0x1019 magnet
        ]

    async def async_update_for_main_entity(self):
        if self.custom_config_bool('use_ble_object', True):
            await self.async_update_ble_data()
        await super().async_update_for_main_entity()
        self._update_sub_entities(['illumination', 'no_motion_duration'], domain='sensor')

    async def async_update_ble_data(self):
        did = self.miot_did
        mic = self.miot_cloud
        if not did or not isinstance(mic, MiotCloud):
            return
        pms = {
            'did': did,
            'props': self._props,
        }
        rdt = await mic.async_request_api('device/batchdevicedatas', [pms]) or {}
        self.logger.debug('%s: Got miio cloud props: %s', self.name_model, rdt)
        props = (rdt.get('result') or {}).get(did, {})
        sta = None
        adt = {}
        for k, v in props.items():
            if v is None:
                continue
            ise = 'event.' in k
            evt = json.loads(v) if ise else {'value': [v]}
            tim = float(evt.get('timestamp') or 0)
            val = vlk = None
            if vls := evt.get('value'):
                val = vls[0]
            if val:
                try:
                    val = int.from_bytes(bytes.fromhex(val), 'little')
                except (TypeError, ValueError):
                    val = None
                    self.logger.warning('%s: BLE object data invalid: %s (%s)', self.name_model, k, vls)
            if ise and not tim:
                continue

            # https://iot.mi.com/new/doc/embedded-development/ble/object-definition#%E6%9C%89%E4%BA%BA%E7%A7%BB%E5%8A%A8%E4%BA%8B%E4%BB%B6%EF%BC%88%E5%B8%A6%E5%85%89%E7%85%A7%EF%BC%89
            if k == 'event.15':
                adt.update({
                    'trigger_time': tim,
                    'trigger_at': datetime.fromtimestamp(tim, local_zone()),
                })
                dif = time.time() - adt['trigger_time']
                sta = dif <= (self.custom_config_integer('motion_timeout') or 60)
                vlk = 'illumination'
                if self._prop_illumination and self._prop_illumination.value_range:
                    vlk = self._prop_illumination.full_name

            # https://iot.mi.com/new/doc/embedded-development/ble/object-definition#%E5%85%89%E7%85%A7%E5%BA%A6%E5%B1%9E%E6%80%A7
            elif k == 'prop.4103':
                vlk = 'illumination'
                if self._prop_illumination and self._prop_illumination.value_range:
                    vlk = self._prop_illumination.full_name

            # https://iot.mi.com/new/doc/embedded-development/ble/object-definition#%E6%97%A0%E4%BA%BA%E7%A7%BB%E5%8A%A8%E5%B1%9E%E6%80%A7
            elif k == 'prop.4119':
                vlk = 'no_motion_seconds'

            # https://iot.mi.com/new/doc/embedded-development/ble/object-definition#%E5%85%89%E7%85%A7%E5%BC%BA%E5%BC%B1%E5%B1%9E%E6%80%A7
            elif k == 'prop.4120':
                adt['light_strong'] = not not val
                vlk = 'illumination_level'
                val = 'strong' if val else 'weak'
                if self._prop_illumination and self._prop_illumination.value_list:
                    vid = self._prop_illumination.list_value(val)
                    if vid is not None:
                        adt[self._prop_illumination.full_name] = vid

            # https://iot.mi.com/new/doc/embedded-development/ble/object-definition#%E9%97%A8%E7%A3%81%E5%B1%9E%E6%80%A7
            elif k == 'prop.4121':
                sta = val != 2

            if vlk is not None and val is not None:
                adt[vlk] = val
        if sta is not None:
            self._state = sta
        if adt:
            await self.async_update_attrs(adt)


class MiotToiletEntity(MiotBinarySensorEntity):
    def __init__(self, config, miot_service: MiotService):
        super().__init__(config, miot_service)
        self._prop_state = None
        for s in miot_service.spec.get_services('toilet', 'seat'):
            if p := s.get_property('seating_state'):
                self._prop_state = p
                break
        if not self._prop_state:
            self._prop_state = miot_service.get_property(
                self._prop_state.name if self._prop_state else 'status',
            )

    async def async_update(self):
        await super().async_update()
        if not self._available:
            return
        from .fan import MiotModesSubEntity
        add_fans = self._add_entities.get('fan')
        pls = self._miot_service.get_properties(
            'mode', 'washing_strength', 'nozzle_position', 'heat_level',
        )
        seat = self._miot_service.spec.get_service('seat')
        if seat:
            prop = seat.get_property('heat_level')
            if prop:
                pls.append(prop)
            else:
                self._update_sub_entities(
                    ['heating', 'deodorization'],
                    [seat],
                    domain='switch',
                )
        for p in pls:
            if not p.value_list and not p.value_range:
                continue
            if p.name in self._subs:
                self._subs[p.name].update()
            elif add_fans:
                opt = None
                if p.name in ['heat_level']:
                    opt = {
                        'power_property': p.service.bool_property('heating'),
                    }
                self._subs[p.name] = MiotModesSubEntity(self, p, opt)
                add_fans([self._subs[p.name]], update_before_add=True)

        if self._prop_power:
            self._update_sub_entities(self._prop_power, None, 'switch')

    @property
    def icon(self):
        return 'mdi:toilet'


class LumiBinarySensorEntity(MiotBinarySensorEntity):
    def __init__(self, config, miot_service: MiotService):
        super().__init__(config, miot_service)

    async def async_update(self):
        await super().async_update()
        if not self._available:
            return
        mic = self.miot_cloud
        pes = dlg = None
        if isinstance(mic, MiotCloud):
            now = int(time.time())
            ofs = self.custom_config_integer('time_start_offset') or -86400 * 3
            dlg = await mic.async_get_last_device_data(self.miot_did, 'device_log', time_start=now + ofs)
            pes = json.loads(dlg or '[]')
        adt = {}
        typ = None
        dif = time.time()
        if pes and len(pes) >= 2:
            typ = pes[1][0]
            adt['trigger_type'] = typ
            adt['trigger_time'] = int(pes[0] or 0)
            adt['trigger_at'] = f'{datetime.fromtimestamp(adt["trigger_time"])}'
            dif = time.time() - adt['trigger_time']
        if typ == 'prop.illumination':
            prop = self._miot_service.get_property('illumination')
            if prop:
                adt[prop.full_name] = pes[1][1][0]
        self._state = None
        if typ == 'event.motion' or self._miot_service.name in ['motion_sensor']:
            self._state = dif <= (self.custom_config_integer('motion_timeout') or 60)
        elif typ in ['event.open', 'event.close']:
            self._state = typ == 'event.open'
        elif typ in ['event.leak', 'event.no_leak']:
            self._state = typ == 'event.leak'
        elif self._prop_state and self._prop_state.full_name in self._state_attrs:
            _LOGGER.info('%s: Get miio data failed: %s', self.name_model, dlg)
        else:
            _LOGGER.warning('%s: Get miio data failed: %s', self.name_model, dlg)
        if self._prop_state and self._state is not None:
            adt[self._prop_state.full_name] = self._state
        if adt:
            await self.async_update_attrs(adt)


class MiotBinarySensorSubEntity(MiotPropertySubEntity, ToggleSubEntity, BinarySensorEntity):
    def __init__(self, parent, miot_property: MiotProperty, option=None):
        ToggleSubEntity.__init__(self, parent, miot_property.full_name, option)
        super().__init__(parent, miot_property, option, domain=ENTITY_DOMAIN)
