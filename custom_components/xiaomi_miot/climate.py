"""Support for Xiaomi Aircondition."""
import logging
from enum import Enum

from homeassistant.const import *
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import *
from miio.airconditioner_miot import (
    AirConditionerMiot,
    FanSpeed,
)

from . import (
    DOMAIN,
    CONF_MODEL,
    PLATFORM_SCHEMA,
    MiotEntity,
    bind_services_to_entries,
)

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'climate.{DOMAIN}'

DEFAULT_MIN_TEMP = 16.0
DEFAULT_MAX_TEMP = 31.0

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    config = hass.data[DOMAIN]['configs'].get(config_entry.entry_id, dict(config_entry.data))
    await async_setup_platform(hass, config, async_add_entities)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data.setdefault(DATA_KEY, {})
    config.setdefault('add_entities', {})
    config['add_entities']['climate'] = async_add_entities
    model = str(config.get(CONF_MODEL) or '')
    entities = []
    if model.find('aircondition') >= 0:
        entity = MiotClimateEntity(config)
        entities.append(entity)
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


HvacModes = Enum('HvacModes', {
    HVAC_MODE_OFF: 0,
    HVAC_MODE_COOL: 2,
    HVAC_MODE_DRY: 3,
    HVAC_MODE_FAN_ONLY: 4,
    HVAC_MODE_HEAT: 5,
})


class SwingModes(Enum):
    Off = 0
    Vertical = 1
    Horizontal = 2
    Steric = 3


class AirConditionerMiotDevice(AirConditionerMiot):
    def __init__(
            self,
            ip: str = None,
            token: str = None,
            start_id: int = 0,
            debug: int = 0,
            lazy_discover: bool = True,
    ) -> None:
        super().__init__(ip, token, start_id, debug, lazy_discover)
        self.mapping.update({
            'horizontal_swing': {'siid': 3, 'piid': 3},
        })


class MiotClimateEntity(MiotEntity, ClimateEntity):
    def __init__(self, config):
        name = config[CONF_NAME]
        host = config[CONF_HOST]
        token = config[CONF_TOKEN]
        model = config.get(CONF_MODEL)
        _LOGGER.info('Initializing with host %s (token %s...)', host, token[:5])

        self._device = AirConditionerMiotDevice(host, token)
        super().__init__(name, self._device)

        self._supported_features = SUPPORT_FAN_MODE | SUPPORT_SWING_MODE | SUPPORT_TARGET_TEMPERATURE
        self._state_attrs.update({'entity_class': self.__class__.__name__})
        self._hvac_mode = HVAC_MODE_OFF
        self._fan_speed = FanSpeed(0)

    async def async_update(self):
        await super().async_update()
        if self._available:
            self._state_attrs.update({
                'current_temperature': self._state_attrs.get('temperature', 0),
                'temperature': self._state_attrs.get('target_temperature', 0),
            })
            attrs = self._state_attrs
            self._fan_speed = FanSpeed(attrs.get('fan_speed', 0))

    @property
    def state(self) -> str:
        return self.hvac_mode

    @property
    def hvac_mode(self):
        self._hvac_mode = HVAC_MODE_OFF
        if self._state:
            self._hvac_mode = HvacModes(int(self._state_attrs.get('mode', 0))).name
        return self._hvac_mode

    @property
    def hvac_modes(self):
        return [v.name for v in HvacModes]

    @property
    def hvac_action(self):
        return None

    def turn_on(self):
        return self._device.on()

    def set_hvac_mode(self, hvac_mode: str):
        if hvac_mode == HVAC_MODE_OFF:
            ret = self._device.off()
        else:
            if not self._state:
                self._device.on()
            ret = self.set_property('mode', HvacModes[hvac_mode].value)
        if ret:
            self._hvac_mode = hvac_mode
            self._state_attrs.update({
                'mode': HvacModes[hvac_mode].value,
            })
        return ret

    @property
    def temperature_unit(self):
        return TEMP_CELSIUS

    @property
    def current_temperature(self):
        return float(self._state_attrs.get('temperature', 0))

    @property
    def min_temp(self) -> float:
        return DEFAULT_MIN_TEMP

    @property
    def max_temp(self) -> float:
        return DEFAULT_MAX_TEMP

    @property
    def target_temperature(self):
        return float(self._state_attrs.get('target_temperature', 0))

    @property
    def target_temperature_step(self):
        return 0.50

    @property
    def target_temperature_high(self):
        return DEFAULT_MAX_TEMP

    @property
    def target_temperature_low(self):
        return DEFAULT_MIN_TEMP

    def set_temperature(self, **kwargs):
        ret = False
        if ATTR_HVAC_MODE in kwargs:
            ret = self.set_hvac_mode(kwargs[ATTR_HVAC_MODE])
        if ATTR_TEMPERATURE in kwargs:
            val = kwargs[ATTR_TEMPERATURE]
            if val < self.min_temp:
                val = self.min_temp
            if val > self.max_temp:
                val = self.max_temp
            ret = self._device.set_target_temperature(val)
            if ret:
                self._state_attrs.update({
                    'target_temperature': val,
                })
        return ret

    @property
    def fan_mode(self):
        return self._fan_speed.name

    @property
    def fan_modes(self):
        return [v.name for v in FanSpeed]

    def set_fan_mode(self, fan_mode: str):
        spd = FanSpeed[fan_mode]
        ret = self._device.set_fan_speed(spd)
        if ret:
            self._fan_speed = spd
        return ret

    @property
    def swing_mode(self):
        val = 0
        if self._state_attrs.get('vertical_swing', False):
            val |= 1
        if self._state_attrs.get('horizontal_swing', False):
            val |= 2
        return SwingModes(val).name

    @property
    def swing_modes(self):
        lst = [v.name for v in SwingModes]
        if self._model not in ['xiaomi.aircondition.mt5']:
            lst = ['Off', 'Vertical']
        return lst

    def set_swing_mode(self, swing_mode: str) -> None:
        ret = None
        ver = None
        hor = None
        val = SwingModes[swing_mode].value
        if val & 1:
            ver = True
            if val == 1:
                hor = False
        if val & 2:
            hor = True
            if val == 2:
                ver = False
        if val == 0:
            ver = False
            hor = False
        for mk, mv in {'vertical_swing': ver, 'horizontal_swing': hor}.items():
            old = self._state_attrs.get(mk, None)
            if old is None or mv is None:
                continue
            if mv == old:
                continue
            ret = self.set_property(mk, mv)
            if ret:
                self._state_attrs.update({
                    mk: mv,
                })
        return ret
