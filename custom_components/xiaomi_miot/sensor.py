"""Support for Xiaomi sensors."""
import logging
from functools import partial

from homeassistant.const import *  # noqa: F401
from homeassistant.helpers.entity import (
    Entity,
)
from homeassistant.components.sensor import (
    DOMAIN as ENTITY_DOMAIN,
)
from miio.waterpurifier_yunmi import WaterPurifierYunmi

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    MiioEntity,
    MiotEntity,
    BaseSubEntity,
    DeviceException,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
)
from .switch import MiotCookerSwitchSubEntity
from .fan import MiotCookerSubEntity

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    await async_setup_config_entry(hass, config_entry, async_setup_platform, async_add_entities)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data.setdefault(DATA_KEY, {})
    hass.data[DOMAIN]['add_entities'][ENTITY_DOMAIN] = async_add_entities
    model = str(config.get(CONF_MODEL) or '')
    entities = []
    if model in ['yunmi.waterpuri.lx9', 'yunmi.waterpuri.lx11']:
        entity = WaterPurifierYunmiEntity(config)
        entities.append(entity)
    else:
        miot = config.get('miot_type')
        if miot:
            spec = await MiotSpec.async_from_type(hass, miot)
            for srv in spec.get_services(
                'water_purifier', 'oven', 'microwave_oven',
                'cooker', 'induction_cooker', 'pressure_cooker',
                'health_pot', 'coffee_machine', 'router', 'video_doorbell',
                'temperature_humidity_sensor',
            ):
                if srv.name in ['video_doorbell']:
                    if not (srv.mapping() or spec.get_service('battery')):
                        continue
                elif srv.name in ['temperature_humidity_sensor']:
                    if spec.name not in ['temperature_humidity_sensor']:
                        continue
                elif not srv.mapping():
                    continue
                cfg = {
                    **config,
                    'name': f"{config.get('name')} {srv.description}"
                }
                if srv.get_property('cook_mode') or srv.get_action('start_cook', 'cancel_cooking'):
                    entities.append(MiotCookerEntity(cfg, srv))
                elif srv.name in ['oven', 'microwave_oven']:
                    entities.append(MiotCookerEntity(cfg, srv))
                else:
                    entities.append(MiotSensorEntity(cfg, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotSensorEntity(MiotEntity):
    def __init__(self, config, miot_service: MiotService):
        super().__init__(miot_service, config=config)
        self._state_attrs.update({'entity_class': self.__class__.__name__})

        first_property = None
        if len(miot_service.properties) > 0:
            first_property = list(miot_service.properties.values() or [])[0].name
        self._prop_state = miot_service.get_property(
            'status', 'fault', first_property or 'status',
        )
        if miot_service.name in ['tds_sensor']:
            self._prop_state = miot_service.get_property('tds_out') or self._prop_state
        elif miot_service.name in ['temperature_humidity_sensor']:
            self._prop_state = miot_service.get_property('temperature', 'indoor_temperature') or self._prop_state

    async def async_update(self):
        await super().async_update()
        if self._available:
            ext = {}
            sta = self._prop_state.from_dict(self._state_attrs)
            if self._prop_state.value_list and sta is not None:
                des = self._prop_state.list_description(sta)
                if des:
                    ext[f'{self._prop_state.full_name}_desc'] = des
            if ext:
                self.update_attrs(ext)
            self._update_sub_entities('on', domain='switch')
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
                ['router', 'wifi', 'guest_wifi'],
                domain='switch',
            )
            self._update_sub_entities(
                ['relative_humidity', 'humidity', 'pm2_5_density', 'battery_level'],
                ['temperature_humidity_sensor'],
                domain='sensor',
            )

    @property
    def state(self):
        key = f'{self._prop_state.full_name}_desc'
        if key in self._state_attrs:
            return f'{self._state_attrs[key]}'.lower()
        return self._prop_state.from_dict(self._state_attrs, STATE_UNKNOWN)

    @property
    def device_class(self):
        if self._prop_state.name in ['temperature']:
            return DEVICE_CLASS_TEMPERATURE
        if self._prop_state.name in ['relative_humidity', 'humidity']:
            return DEVICE_CLASS_HUMIDITY
        if self._prop_state.name in ['illumination']:
            return DEVICE_CLASS_ILLUMINANCE
        if self._miot_service.name in ['illumination_sensor']:
            return DEVICE_CLASS_ILLUMINANCE
        if self._prop_state.name in ['battery', 'battery_level']:
            return DEVICE_CLASS_BATTERY
        return None

    @property
    def unit_of_measurement(self):
        prop = self._prop_state
        if prop:
            if prop.unit in ['celsius', TEMP_CELSIUS]:
                return TEMP_CELSIUS
            if prop.unit in ['fahrenheit', TEMP_FAHRENHEIT]:
                return TEMP_FAHRENHEIT
            if prop.unit in ['kelvin', TEMP_KELVIN]:
                return TEMP_KELVIN
            if prop.unit in ['percentage', PERCENTAGE]:
                return PERCENTAGE
        return None


class MiotCookerEntity(MiotSensorEntity):
    def __init__(self, config, miot_service: MiotService):
        super().__init__(config, miot_service)
        self._prop_state = miot_service.get_property('status')
        self._action_cancel = miot_service.get_action('cancel_cooking', 'pause')

        self._values_on = []
        self._values_off = []
        if self._prop_state:
            self._values_on = self._prop_state.list_search('Busy', 'Running', 'Delay')
            self._values_off = self._prop_state.list_search(
                'Idle', 'Completed', 'CookFinish', 'Paused', 'Fault', 'Error', 'Stop', 'Off',
            )

    @property
    def icon(self):
        if self._miot_service.name in ['oven', 'microwave_oven']:
            return 'mdi:microwave'
        if self._miot_service.name in ['health_pot']:
            return 'mdi:coffee'
        return 'mdi:chef-hat'

    async def async_update(self):
        await super().async_update()
        if self._available:
            if self._prop_state:
                add_fans = self._add_entities.get('fan')
                add_switches = self._add_entities.get('switch')
                pls = self._miot_service.get_properties('cook_mode')
                for p in pls:
                    if not p.value_list:
                        continue
                    if p.name in self._subs:
                        self._subs[p.name].update()
                    elif add_fans:
                        self._subs[p.name] = MiotCookerSubEntity(self, p, self._prop_state, {
                            'values_on':  self._values_on,
                            'values_off': self._values_off,
                        })
                        add_fans([self._subs[p.name]])
                if not pls and self._action_cancel:
                    pnm = 'cook_switch'
                    if pnm in self._subs:
                        self._subs[pnm].update()
                    elif add_switches:
                        self._subs[pnm] = MiotCookerSwitchSubEntity(self, self._prop_state)
                        add_switches([self._subs[pnm]])

    @property
    def is_on(self):
        val = self._prop_state.from_dict(self._state_attrs)
        return val not in [*self._values_off, None]

    def turn_on(self, **kwargs):
        return False

    def turn_off(self, **kwargs):
        ret = False
        if self._action_cancel:
            ret = self.miot_action(self._miot_service.iid, self._action_cancel.iid)
            sta = self._values_off[0] if self._values_off else None
            if ret and sta is not None:
                self.update_attrs({
                    self._prop_state.full_name: sta,
                })
        return ret


class WaterPurifierYunmiEntity(MiioEntity, Entity):
    def __init__(self, config):
        name = config[CONF_NAME]
        host = config[CONF_HOST]
        token = config[CONF_TOKEN]
        _LOGGER.info('Initializing with host %s (token %s...)', host, token[:5])

        self._device = WaterPurifierYunmi(host, token)
        super().__init__(name, self._device)
        self._state_attrs.update({'entity_class': self.__class__.__name__})
        self._subs = {
            'tds_in':  {'keys': ['tds_warn_thd'], 'unit': CONCENTRATION_PARTS_PER_MILLION, 'icon': 'mdi:water'},
            'tds_out': {'keys': ['tds_warn_thd'], 'unit': CONCENTRATION_PARTS_PER_MILLION, 'icon': 'mdi:water-check'},
            'temperature': {'class': DEVICE_CLASS_TEMPERATURE, 'unit': TEMP_CELSIUS},
        }
        for i in [1, 2, 3]:
            self._subs.update({
                f'f{i}_remaining': {
                    'keys': [f'f{i}_totalflow', f'f{i}_usedflow'],
                    'unit': PERCENTAGE,
                    'icon': 'mdi:water-percent',
                },
                f'f{i}_remain_days': {
                    'keys': [f'f{i}_totaltime', f'f{i}_usedtime'],
                    'unit': TIME_DAYS,
                    'icon': 'mdi:clock',
                },
            })

    @property
    def state(self):
        return self._state

    @property
    def icon(self):
        return 'mdi:water-pump'

    @property
    def unit_of_measurement(self):
        return CONCENTRATION_PARTS_PER_MILLION

    async def async_update(self):
        try:
            status = await self.hass.async_add_executor_job(partial(self._device.status))
        except DeviceException as ex:
            if self._available:
                self._available = False
                _LOGGER.error('Got exception while fetching the state for %s: %s', self.entity_id, ex)
            return
        attrs = status.data or {}
        _LOGGER.debug('Got new state from %s: %s', self.entity_id, attrs)
        self._available = True
        self._state = int(attrs.get('tds_out', 0))
        self._state_attrs.update(attrs)
        for i in [1, 2, 3]:
            self._state_attrs.update({
                f'f{i}_remaining':   round(100 - 100 * attrs[f'f{i}_usedtime'] / attrs[f'f{i}_totaltime']),
                f'f{i}_remain_days': round((attrs[f'f{i}_totaltime'] - attrs[f'f{i}_usedtime']) / 24),
            })
        self._state_attrs.update({
            'errors': '|'.join(status.operation_status.errors),
        })
        add_entities = self._add_entities.get('sensor')
        for k, v in self._subs.items():
            if 'entity' in v:
                v['entity'].update()
            elif add_entities:
                v['entity'] = WaterPurifierYunmiSubEntity(self, k, v)
                add_entities([v['entity']])


class WaterPurifierYunmiSubEntity(BaseSubEntity):
    def __init__(self, parent: WaterPurifierYunmiEntity, attr, option=None):
        super().__init__(parent, attr, option)
