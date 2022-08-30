"""Support for humidifier and dehumidifier."""
import logging

from homeassistant.const import *  # noqa: F401
from homeassistant.components.humidifier import (
    DOMAIN as ENTITY_DOMAIN,
    HumidifierEntity,
)
from homeassistant.components.humidifier.const import *

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    MiotToggleEntity,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
)
from .fan import MiotModesSubEntity

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'
MODE_OFF = 'Off'

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    await async_setup_config_entry(hass, config_entry, async_setup_platform, async_add_entities, ENTITY_DOMAIN)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data.setdefault(DATA_KEY, {})
    hass.data[DOMAIN]['add_entities'][ENTITY_DOMAIN] = async_add_entities
    config['hass'] = hass
    model = str(config.get(CONF_MODEL) or '')
    spec = hass.data[DOMAIN]['miot_specs'].get(model)
    entities = []
    if isinstance(spec, MiotSpec):
        for srv in spec.get_services(ENTITY_DOMAIN, 'dehumidifier'):
            if not srv.get_property('on'):
                continue
            entities.append(MiotHumidifierEntity(config, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotHumidifierEntity(MiotToggleEntity, HumidifierEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(miot_service, config=config, logger=_LOGGER)

        self._prop_power = miot_service.get_property('on')
        self._prop_mode = miot_service.get_property('mode')
        self._prop_fan_level = miot_service.get_property('fan_level')
        self._prop_water_level = miot_service.get_property('water_level')
        self._prop_temperature = miot_service.get_property('temperature')
        self._prop_target_humi = miot_service.get_property('target_humidity')
        self._prop_humidity = miot_service.get_property('relative_humidity', 'humidity')
        self._environment = miot_service.spec.get_service('environment')
        if self._environment:
            self._prop_temperature = self._environment.get_property('temperature') or self._prop_temperature
            self._prop_target_humi = self._environment.get_property('target_humidity') or self._prop_target_humi
            self._prop_humidity = self._environment.get_property('relative_humidity', 'humidity') or self._prop_humidity

        self._humidifier_mode = None
        self._mode_props = [self._prop_mode, self._prop_fan_level]
        self._mode_props = list(filter(lambda x: x, self._mode_props))
        if self._mode_props:
            self._humidifier_mode = self._mode_props.pop(0)
            self._supported_features = SUPPORT_MODES

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._vars['target_humidity_ratio'] = self.custom_config_number('target_humidity_ratio')

    async def async_update(self):
        await super().async_update()
        if not self._available:
            return
        if self._prop_water_level and self._prop_water_level.writeable:
            self._update_sub_entities(
                [self._prop_water_level.name],
                domain='number_select',
            )
        add_fans = self._add_entities.get('fan')
        for p in self._mode_props:
            pnm = p.full_name
            if self._humidifier_mode and pnm == self._humidifier_mode.full_name:
                continue
            if pnm in self._subs:
                self._subs[pnm].update_from_parent()
            elif add_fans:
                self._subs[pnm] = MiotModesSubEntity(self, p)
                add_fans([self._subs[pnm]], update_before_add=True)

    @property
    def device_class(self):
        typ = f'{self._model} {self._miot_service.spec.type}'
        if typ.find(DEVICE_CLASS_DEHUMIDIFIER) >= 0:
            return DEVICE_CLASS_DEHUMIDIFIER
        return DEVICE_CLASS_HUMIDIFIER

    @property
    def target_humidity(self):
        if not self._prop_target_humi:
            return None
        num = int(self._prop_target_humi.from_dict(self._state_attrs) or 0)
        if fac := self._vars.get('target_humidity_ratio'):
            num = round(num * fac)
        return num

    def set_humidity(self, humidity: int):
        if not self._prop_target_humi:
            return False
        num = humidity
        if self._prop_target_humi.value_range:
            stp = self._prop_target_humi.range_step()
            num = round(humidity / stp) * stp
            if fac := self._vars.get('target_humidity_ratio'):
                num = round(num / fac)
        elif self._prop_target_humi.value_list:
            num = None
            vls = self._prop_target_humi.list_value(None)
            vls.sort()
            for n in vls:
                if humidity >= n or num is None:
                    num = n
        if num is None:
            return False
        return self.set_property(self._prop_target_humi, num)

    @property
    def min_humidity(self):
        if not self._prop_target_humi:
            return DEFAULT_MIN_HUMIDITY
        if self._prop_target_humi.value_list:
            vls = self._prop_target_humi.list_value(None)
            vls.sort()
            return vls[0]
        num = self._prop_target_humi.range_min()
        if fac := self._vars.get('target_humidity_ratio'):
            num = round(num * fac)
        return num

    @property
    def max_humidity(self):
        if not self._prop_target_humi:
            return DEFAULT_MAX_HUMIDITY
        if self._prop_target_humi.value_list:
            vls = self._prop_target_humi.list_value(None)
            vls.sort()
            return vls[-1]
        num = self._prop_target_humi.range_max()
        if fac := self._vars.get('target_humidity_ratio'):
            num = round(num * fac)
        return num

    @property
    def mode(self):
        if not self.is_on:
            return MODE_OFF
        if not self._humidifier_mode:
            return None
        val = self._humidifier_mode.from_dict(self._state_attrs)
        if val is None:
            return None
        return self._humidifier_mode.list_description(val)

    @property
    def available_modes(self):
        mds = [MODE_OFF]
        if self._humidifier_mode:
            mds.extend(self._humidifier_mode.list_descriptions() or [])
        return mds

    def set_mode(self, mode: str):
        if mode == MODE_OFF:
            return self.turn_off()
        if not self._humidifier_mode:
            return False
        val = self._humidifier_mode.list_value(mode)
        if val is None:
            return False
        return self.set_property(self._humidifier_mode, val)
