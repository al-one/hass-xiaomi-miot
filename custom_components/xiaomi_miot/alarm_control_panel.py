"""Support alarm_control_panel entity for Xiaomi Miot."""
import logging

from homeassistant.components.alarm_control_panel import (
    DOMAIN as ENTITY_DOMAIN,
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,  # v2022.5
)

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    HassEntry,
    MiotEntity,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.miot_spec import (
    MiotSpec,
    MiotService,
)
from .core.const import AlarmControlPanelState

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'

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
        for srv in spec.get_services('arming'):
            if not srv.get_property('arming_mode'):
                continue
            entities.append(MiotAlarmEntity(config, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotAlarmEntity(MiotEntity, AlarmControlPanelEntity):
    def __init__(self, config, miot_service: MiotService):
        super().__init__(miot_service, config=config, logger=_LOGGER)
        self._attr_code_arm_required = False
        self._is_mgl03 = self.model == 'lumi.gateway.mgl03'
        self._prop_mode = miot_service.get_property('arming_mode')
        if self._prop_mode:
            if self._prop_mode.list_value('home_arming') is not None:
                self._supported_features |= AlarmControlPanelEntityFeature.ARM_HOME
            if self._prop_mode.list_value('away_arming') is not None:
                self._supported_features |= AlarmControlPanelEntityFeature.ARM_AWAY
            if self._prop_mode.list_value('sleep_arming') is not None:
                self._supported_features |= AlarmControlPanelEntityFeature.ARM_NIGHT
            if self._is_mgl03:
                self._supported_features |= AlarmControlPanelEntityFeature.TRIGGER

    async def async_update(self):
        await super().async_update()
        if not self._available:
            return
        self.update_state()

    def update_state(self):
        sta = None
        if self._prop_mode:
            val = self._prop_mode.from_dict(self._state_attrs)
            des = self._prop_mode.list_description(val) if val is not None else None
            if des is not None:
                des = f'{des}'.lower()
                if 'basic' in des:
                    sta = AlarmControlPanelState.DISARMED
                elif 'home' in des:
                    sta = AlarmControlPanelState.ARMED_HOME
                elif 'away' in des:
                    sta = AlarmControlPanelState.ARMED_AWAY
                elif 'sleep' in des:
                    sta = AlarmControlPanelState.ARMED_NIGHT
        if self._is_mgl03:
            if val := self._state_attrs.get('arming.alarm'):
                sta = AlarmControlPanelState.TRIGGERED
        if hasattr(self, '_attr_alarm_state'):
            self._attr_alarm_state = sta
        else:
            self._attr_state = sta

    def set_arm_mode(self, mode):
        ret = False
        val = self._prop_mode.list_value(mode)
        if val is not None:
            ret = self.set_property(self._prop_mode, val)
        if ret:
            self.update_state()
        return ret

    def alarm_disarm(self, code=None):
        """Send disarm command."""
        return self.set_arm_mode('basic_arming')

    def alarm_arm_home(self, code=None):
        """Send arm home command."""
        return self.set_arm_mode('home_arming')

    def alarm_arm_away(self, code=None):
        """Send arm away command."""
        return self.set_arm_mode('away_arming')

    def alarm_arm_night(self, code=None):
        """Send arm night command."""
        return self.set_arm_mode('sleep_arming')

    def alarm_arm_vacation(self, code=None):
        """Send arm vacation command."""
        raise NotImplementedError()

    def alarm_trigger(self, code=None):
        """Send alarm trigger command."""
        if self._is_mgl03:
            return self.set_miot_property(3, 22, 1)
        raise NotImplementedError()

    def alarm_arm_custom_bypass(self, code=None):
        """Send arm custom bypass command."""
        raise NotImplementedError()
