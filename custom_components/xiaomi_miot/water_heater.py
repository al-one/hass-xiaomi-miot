"""Support for Xiaomi water heaters."""
import logging
import math

from homeassistant.const import (
    ATTR_TEMPERATURE,
    STATE_OFF,
    STATE_ON,
    UnitOfTemperature,
)
from homeassistant.components.water_heater import (
    DOMAIN as ENTITY_DOMAIN,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,  # v2022.5
)

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    HassEntry,
    MiotToggleEntity,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
)

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'

DEFAULT_MIN_TEMP = 40
DEFAULT_MAX_TEMP = 65

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
        for srv in spec.get_services(ENTITY_DOMAIN, 'kettle', 'water_dispenser'):
            if not srv.get_property('mode', 'target_temperature'):
                continue
            entities.append(MiotWaterHeaterEntity(config, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotWaterHeaterEntity(MiotToggleEntity, WaterHeaterEntity):
    def __init__(self, config, miot_service: MiotService):
        super().__init__(miot_service, config=config, logger=_LOGGER)

        self._prop_status = miot_service.get_property('status')
        self._prop_mode = miot_service.get_property('mode')
        self._prop_modes = []
        if self._prop_mode:
            self._prop_modes.append(self._prop_mode)
        self._prop_modes.extend(miot_service.get_properties('water_level'))
        self._prop_temperature = miot_service.get_property('temperature', 'indoor_temperature')
        self._prop_target_temp = miot_service.get_property('target_temperature')
        self._prop_keep_warm_temp = miot_service.get_property("keep_warm_temperature")
        self._prop_keep_warm_time = miot_service.get_property("keep_warm_time")

        self._prev_target_temp = None

        if self._prop_target_temp:
            self._supported_features |= WaterHeaterEntityFeature.TARGET_TEMPERATURE
        if self._prop_modes:
            self._supported_features |= WaterHeaterEntityFeature.OPERATION_MODE

        # Defer dynamic button creation to async_added_to_hass where the button platform is guaranteed to be ready.
        self._kettle_buttons_added = False


    async def async_update(self):
        await super().async_update()
        if not self._available:
            return
        if self._prop_power:
            if not self._prop_power.readable and self._prop_status:
                # https://github.com/al-one/hass-xiaomi-miot/issues/30
                val = self._prop_status.from_device(self.device)
                if val is not None:
                    off = val in self._prop_status.list_search('Off')
                    await self.async_update_attrs({
                        self._prop_power.full_name: not off,
                    })

    @property
    def state(self):
        """Return the current state."""
        sta = self.current_operation
        mds = []
        if self._prop_mode:
            mds = self._prop_mode.list_descriptions()
        if sta is None or sta not in mds:
            if self._prop_status:
                val = self._prop_status.from_device(self.device)
                if val is not None:
                    sta = self._prop_status.list_description(val)
        if sta is None and self._prop_power and self._prop_power.readable:
            sta = STATE_ON if self._prop_power.from_device(self.device) else STATE_OFF
        if sta:
            sta = str(sta).lower()
        return sta

    @property
    def current_operation(self):
        """Return current operation ie. eco, electric, performance, ..."""
        for p in self._prop_modes:
            val = p.from_device(self.device)
            if val is not None:
                return p.list_description(val)
        return None

    @property
    def operation_list(self):
        """Return the list of available operation modes."""
        for p in self._prop_modes:
            return p.list_descriptions() or []
        return None

    def set_operation_mode(self, mode):
        """Set new target operation mode."""
        for p in self._prop_modes:
            val = p.list_value(mode)
            return self.set_property(p, val)
        raise NotImplementedError()

    @property
    def current_temperature(self):
        """Return the current temperature."""
        if self._prop_temperature:
            return round(self._prop_temperature.from_device(self.device) or 0, 2)
        return None

    @property
    def temperature_unit(self):
        prop = self._prop_temperature or self._prop_target_temp
        if prop:
            if prop.unit in ['celsius', UnitOfTemperature.CELSIUS]:
                return UnitOfTemperature.CELSIUS
            if prop.unit in ['fahrenheit', UnitOfTemperature.FAHRENHEIT]:
                return UnitOfTemperature.FAHRENHEIT
            if prop.unit in ['kelvin', UnitOfTemperature.KELVIN]:
                return UnitOfTemperature.KELVIN
        return UnitOfTemperature.CELSIUS

    def set_temperature(self, **kwargs):
        """Set new target temperature."""
        if self._prop_target_temp:
            val = kwargs.get(ATTR_TEMPERATURE) or 0
            stp = self._prop_target_temp.range_step()
            if stp and stp > 1:
                val = round(val / stp) * stp
            elif self._prev_target_temp is None:
                val = round(val)
            elif val >= self._prev_target_temp:
                val = math.ceil(val)
            else:
                val = int(val)
            ret = self.set_property(self._prop_target_temp, val)
            if ret:
                self._prev_target_temp = val
            return ret
        raise NotImplementedError()

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        if self._prop_target_temp:
            val = round(self._prop_target_temp.from_device(self.device) or 0, 2)
            if val:
                self._prev_target_temp = val
            elif self._prev_target_temp:
                val = self._prev_target_temp
            return val
        return None

    @property
    def target_temperature_high(self):
        """Return the highbound target temperature we try to reach."""
        if self._prop_target_temp:
            return self._prop_target_temp.range_max()
        return None

    @property
    def target_temperature_low(self):
        """Return the lowbound target temperature we try to reach."""
        if self._prop_target_temp:
            return self._prop_target_temp.range_min()
        return None

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return self.target_temperature_low or DEFAULT_MIN_TEMP

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self.target_temperature_high or DEFAULT_MAX_TEMP

    @property
    def is_away_mode_on(self):
        """Return true if away mode is on."""
        return None

    def turn_away_mode_on(self):
        """Turn away mode on."""
        raise NotImplementedError()

    def turn_away_mode_off(self):
        """Turn away mode off."""
        raise NotImplementedError()

    async def async_added_to_hass(self):
        await super().async_added_to_hass()

        # Create control buttons once the button platform adder is present.
        if not self._kettle_buttons_added and self.model in ["xiaomi.kettle.v20", "xiaomi.kettle.v21"]:
            add_buttons = self.device.entry.adders.get("button")
            if not add_buttons:
                return
            from .button import ButtonSubEntity

            btn_defs = [
                ("boil", "start-boil", self.start_boil),
                ("keep_warm", "start-keep-warm", self.start_keep_warm),
                ("extended_mode", "start-extended-mode", self.start_extended_mode),
            ]
            subs = []
            for key, ui_name, act in btn_defs:
                if key in self._subs:
                    continue
                sub = ButtonSubEntity(
                    self,
                    key,
                    option={
                        "name": ui_name,
                        "press_action": act,
                    },
                )
                self._subs[key] = sub
                subs.append(sub)

            if subs:
                add_buttons(subs, update_before_add=False)
                self._kettle_buttons_added = True

    def _send_kettle_props(self, props):
        """Send a batch of set_properties payloads via Mi Cloud."""
        # Prefer local communication when possible; fall back to cloud.
        if self.device.use_local and self.device.local:
            try:
                res = self.device.local.send("set_properties", props)
                if isinstance(res, list) and all(r.get("code", -1) == 0 for r in res):
                    return True
            except Exception:
                pass
        mic = self.miot_cloud_write or self.miot_cloud
        if not mic:
            self.logger.warning(
                "%s: No connection available for kettle RPC commands.", self.name_model
            )
            return False
        try:
            res = mic.set_props(props)
            ok = isinstance(res, list) and all(r.get("code", -1) == 0 for r in res)
            if not ok:
                self.logger.info(
                    "%s: Cloud kettle RPC returned unexpected result: %s",
                    self.name_model,
                    res,
                )
            return ok
        except Exception:
            self.logger.warning(
                "%s: Cloud kettle RPC command failed", self.name_model
            )
            return False

    def _cur_target_temp(self, default):
        val = self.target_temperature
        if val is None and self._prop_target_temp:
            val = self._prop_target_temp.from_device(self.device)
        return val or default

    def _cur_keep_warm_temp(self, default):
        val = None
        if self._prop_keep_warm_temp:
            val = self._prop_keep_warm_temp.from_device(self.device)
        return val or default

    def _cur_keep_warm_time(self, default):
        val = None
        if self._prop_keep_warm_time:
            val = self._prop_keep_warm_time.from_device(self.device)
        return val or default

    def start_boil(self, **kwargs):
        """Trigger boiling mode via cloud RPC using current HA values."""
        did = self.miot_did

        target_temp = self._cur_target_temp(90)
        keep_warm_temp = self._cur_keep_warm_temp(75)
        keep_warm_time = self._cur_keep_warm_time(1440)

        props = [
            {"did": str(did), "siid": 2, "piid": 4, "value": 99},
            {"did": str(did), "siid": 2, "piid": 5, "value": True},
            {"did": str(did), "siid": 2, "piid": 6, "value": keep_warm_temp},
            {"did": str(did), "siid": 3, "piid": 1, "value": keep_warm_time},
            {"did": str(did), "siid": 3, "piid": 11, "value": 1},
            {
                "did": str(did),
                "siid": 3,
                "piid": 13,
                "value": f"{99},1,{keep_warm_temp},{keep_warm_time}",
            },
        ]
        return self._send_kettle_props(props)

    def start_keep_warm(self, **kwargs):
        """Trigger keep-warm mode via cloud RPC using current HA values."""
        did = self.miot_did

        target_temp = self._cur_target_temp(90)
        keep_warm_temp = self._cur_keep_warm_temp(75)
        keep_warm_time = self._cur_keep_warm_time(1440)

        props = [
            {"did": str(did), "siid": 2, "piid": 4, "value": keep_warm_temp},
            {"did": str(did), "siid": 2, "piid": 5, "value": True},
            {"did": str(did), "siid": 2, "piid": 6, "value": keep_warm_temp},
            {"did": str(did), "siid": 3, "piid": 1, "value": keep_warm_time},
            {"did": str(did), "siid": 3, "piid": 11, "value": 0},
            {
                "did": str(did),
                "siid": 3,
                "piid": 12,
                "value": f"{keep_warm_temp},1,{keep_warm_temp},{keep_warm_time}",
            },
        ]
        return self._send_kettle_props(props)

    def start_extended_mode(self, **kwargs):
        """Trigger the first extended mode via cloud RPC using current HA values."""
        did = self.miot_did

        target_temp = self._cur_target_temp(90)
        keep_warm_temp = self._cur_keep_warm_temp(75)
        keep_warm_time = self._cur_keep_warm_time(1440)

        props = [
            {"did": str(did), "siid": 2, "piid": 4, "value": target_temp},
            {"did": str(did), "siid": 2, "piid": 5, "value": True},
            {"did": str(did), "siid": 2, "piid": 6, "value": keep_warm_temp},
            {"did": str(did), "siid": 3, "piid": 1, "value": keep_warm_time},
            {"did": str(did), "siid": 3, "piid": 11, "value": 10},
        ]
        return self._send_kettle_props(props)
