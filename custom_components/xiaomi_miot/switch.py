"""Support for Xiaomi switches."""
import logging
import time

from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_TOKEN,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.components.switch import (
    DOMAIN as ENTITY_DOMAIN,
    SwitchEntity,
    SwitchDeviceClass,
)

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    MiioDevice,
    MiioEntity,
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
    MiotAction,
)

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'

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
    if model in ['pwzn.relay.banana']:
        entities.append(PwznRelaySwitchEntity(config))
    elif isinstance(spec, MiotSpec):
        if model in ['pwzn.switch.apple']:
            srv = spec.get_service('relays')
            if srv:
                entities.append(MiotPwznRelaySwitchEntity(config, srv))
        else:
            for srv in spec.get_services(
                ENTITY_DOMAIN, 'outlet', 'massager', 'towel_rack', 'diffuser', 'fish_tank',
                'pet_drinking_fountain', 'mosquito_dispeller', 'electric_blanket', 'foot_bath',
            ):
                if not srv.get_property('on'):
                    continue
                entities.append(MiotSwitchEntity(config, srv))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotSwitchEntity(MiotToggleEntity, SwitchEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(miot_service, config=config, logger=_LOGGER)
        self._attr_icon = self._miot_service.entity_icon

    @property
    def device_class(self):
        if cls := self.get_device_class(SwitchDeviceClass):
            return cls
        typ = f'{self._model} {self._miot_service.spec.type}'
        if 'outlet' in typ or '.plug.' in typ:
            return SwitchDeviceClass.OUTLET
        return SwitchDeviceClass.SWITCH

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if act := self._miot_service.get_action('pet_food_out'):
            prop = self._miot_service.get_property('feeding_measure')
            add_switches = self._add_entities.get('switch')
            if prop and add_switches:
                fnm = prop.unique_name
                self._subs[fnm] = MiotSwitchActionSubEntity(self, prop, act)
                add_switches([self._subs[fnm]], update_before_add=True)

    async def async_update(self):
        await super().async_update()
        if not self._available:
            return
        self._update_sub_entities(
            ['heat_level'],
            ['massager'],
            domain='fan',
            option={
                'power_property': self._miot_service.get_property('heating'),
            },
        )
        self._update_sub_entities(
            ['mode', 'massage_strength', 'massage_part', 'massage_manipulation'],
            ['massager'],
            domain='number_select' if self.entry_config_version >= 0.3 else 'fan',
        )


class SwitchSubEntity(ToggleSubEntity, SwitchEntity):
    def __init__(self, parent, attr='switch', option=None, **kwargs):
        kwargs.setdefault('domain', ENTITY_DOMAIN)
        super().__init__(parent, attr, option, **kwargs)

    def update(self, data=None):
        super().update(data)


class MiotSwitchSubEntity(MiotPropertySubEntity, SwitchSubEntity):
    def __init__(self, parent, miot_property: MiotProperty, option=None):
        super().__init__(parent, miot_property, option, domain=ENTITY_DOMAIN)
        self._name = self.format_name_by_property(miot_property)
        self._prop_power = self._miot_service.get_property('on', 'power')
        if self._prop_power:
            self._option['keys'] = [*(self._option.get('keys') or []), self._prop_power.full_name]
            self._option['icon'] = self._prop_power.entity_icon or self._option.get('icon')
        self._on_descriptions = ['On', 'Open', 'Enable', 'Enabled', 'Yes', '开', '打开']
        if des := self.custom_config_list('descriptions_for_on'):
            self._on_descriptions = des

    @property
    def is_on(self):
        val = self._miot_property.from_dict(self._state_attrs)
        if self._miot_property.value_list:
            if val is not None:
                self._state = val in self._miot_property.list_search(*self._on_descriptions)
        elif self._miot_property.value_range:
            if self._miot_property.range_min() == 0 and self._miot_property.range_max() == 1:
                self._state = val == self._miot_property.range_max()
        elif self._miot_property.format in ['bool']:
            self._state = val

        if self._miot_service.name in ['air_conditioner']:
            if self._prop_power:
                self._state = self._state and self._prop_power.from_dict(self._state_attrs)

        if self._reverse_state and self._state is not None:
            return not self._state
        return self._state

    def turn_on(self, **kwargs):
        val = True
        if self._miot_property.value_range:
            val = self._miot_property.range_max()
        if self._miot_property.value_list:
            ret = self._miot_property.list_first(*self._on_descriptions)
            val = 1 if ret is None else ret
        elif self._miot_property.value_range:
            val = self._miot_property.range_max()
        if self._reverse_state:
            val = not val
        return self.set_parent_property(val)

    def turn_off(self, **kwargs):
        val = False
        if self._miot_property.value_range:
            val = self._miot_property.range_min()
        if self._miot_property.value_list:
            if not (des := self.custom_config_list('descriptions_for_off')):
                des = ['Off', 'Close', 'Closed', '关', '关闭']
            ret = self._miot_property.list_first(*des)
            val = 0 if ret is None else ret
        elif self._miot_property.value_range:
            val = self._miot_property.range_min()
        if self._reverse_state:
            val = not val
        return self.set_parent_property(val)


class MiotSwitchActionSubEntity(MiotPropertySubEntity, SwitchSubEntity):
    def __init__(self, parent, miot_property: MiotProperty, miot_action: MiotAction, option=None):
        SwitchSubEntity.__init__(self, parent, miot_action.full_name, option)
        super().__init__(parent, miot_property, option, domain=ENTITY_DOMAIN)
        self._miot_action = miot_action
        self._state = False
        self._available = True
        if miot_action.name in ['pet_food_out']:
            self._option['icon'] = 'mdi:shaker'
        self._state_attrs.update({
            'miot_action': miot_action.full_name,
        })

    def update(self, data=None):
        self._state = False

    @property
    def is_on(self):
        """Return True if entity is on."""
        return self._state

    def turn_on(self, **kwargs):
        """Turn the entity on."""
        val = self.custom_config_integer(self._miot_property.name)
        if val is not None:
            # feeding_measure
            pass
        elif self._miot_property.value_range:
            val = int(self._miot_property.range_min() or 0)
        elif self._miot_property.value_list:
            val = self._miot_property.value_list[0].get('value')
        ret = self.call_parent('call_action', self._miot_action, None if val is None else [val])
        if ret:
            self._state = True
            self.schedule_update_ha_state()
            time.sleep(0.5)
            self._state = False
        return ret

    def turn_off(self, **kwargs):
        """Turn the entity off."""
        self._state = False
        return True


class MiotWasherActionSubEntity(SwitchSubEntity):
    def __init__(self, parent, miot_property: MiotProperty, option=None):
        super().__init__(parent, miot_property.full_name, option)
        self._name = self.format_name_by_property(miot_property)
        self._miot_property = miot_property
        self._miot_service = miot_property.service
        self._values_on = miot_property.list_search('Busy', 'Delay')
        self._values_off = miot_property.list_search('Off', 'Idle', 'Pause', 'Paused', 'Completed', 'Fault')

    def update(self, data=None):
        super().update(data)
        if self._available:
            self._miot_property.description_to_dict(self._state_attrs)
            sta = self._state_attrs.get(self._attr)
            self._state = sta not in self._values_off

    def turn_on(self, **kwargs):
        val = self._values_on[0] if self._values_on else None
        return self.miot_action('start_wash', val)

    def turn_off(self, **kwargs):
        val = self._values_off[0] if self._values_off else None
        return self.miot_action(['pause', 'stop_washing'], val)

    def miot_action(self, act, sta=None):
        ret = False
        if not isinstance(act, list):
            act = [act]
        act = self._miot_service.get_action(*act)
        if act:
            pms = []
            if act.ins:
                pms = act.in_params_from_attrs(self._parent_attrs, with_piid=False)
            ret = self.call_parent('miot_action', self._miot_service.iid, act.iid, pms)
            if ret and sta is not None:
                self.update_attrs({
                    self._attr: sta,
                })
        return ret

    @property
    def icon(self):
        return 'mdi:play-box'


class MiotCookerSwitchSubEntity(SwitchSubEntity):
    def __init__(self, parent, miot_property: MiotProperty, option=None):
        super().__init__(parent, miot_property.full_name, option)
        self._name = self.format_name_by_property(miot_property)

    @property
    def is_on(self):
        return self._parent.is_on


class MiotPwznRelaySwitchEntity(MiotToggleEntity, SwitchEntity):
    def __init__(self, config: dict, miot_service: MiotService):
        super().__init__(miot_service, config=config, logger=_LOGGER)
        self._prop_status = miot_service.get_property('all_status')
        self._prop_power = self._prop_status

    @property
    def device_class(self):
        return SwitchDeviceClass.SWITCH

    @property
    def all_status(self):
        return (1 << 16) - 1

    async def async_update(self):
        await super().async_update()
        await self.hass.async_add_executor_job(self.update_all)

    def update_all(self):
        if not self._available:
            return
        sta = int(self._prop_status.from_dict(self._state_attrs) or 0)
        self._state = (sta & self.all_status) and True
        add_switches = self._add_entities.get(ENTITY_DOMAIN)
        for idx in range(0, 32):
            s = idx + 1
            b = 1 << idx
            k = 'switch_%02d' % s
            self._state_attrs[k] = STATE_ON if sta & b else STATE_OFF
            if k in self._subs:
                self._subs[k].update_from_parent()
            elif add_switches:
                self._subs[k] = PwznRelaySwitchSubEntity(self, 0, s, {
                    'attr': k,
                    'index': idx,
                })
                add_switches([self._subs[k]], update_before_add=True)

    def relay_ctrl(self, select, ctrl):
        act = self._miot_service.get_action('relay_ctrl')
        if act:
            return self.call_action(act, [select, ctrl])
        return False

    def turn_channel(self, channel, on):
        act = self._miot_service.get_action('relay_chnl_on' if on else 'relay_chnl_off')
        if act:
            return self.call_action(act, [channel])
        return False

    @property
    def is_on(self):
        return self._state

    def turn_on(self, **kwargs):
        act = self._miot_service.get_action('relay_all_on')
        ret = self.call_action(act) if act else False
        if ret:
            self._vars['delay_update'] = 5
            self.update_attrs({
                self._prop_status.full_name: self.all_status,
            }, update_parent=False)
            self.update_all()
            self._state = True
        return ret

    def turn_off(self, **kwargs):
        act = self._miot_service.get_action('relay_all_off')
        ret = self.call_action(act) if act else False
        if ret:
            self._vars['delay_update'] = 5
            sta = int(self._prop_status.from_dict(self._state_attrs) or 0)
            self.update_attrs({
                self._prop_status.full_name: sta & ~ self.all_status,
            }, update_parent=False)
            self.update_all()
            self._state = False
        return ret


class PwznRelaySwitchEntity(MiioEntity, SwitchEntity):
    def __init__(self, config: dict):
        name = config[CONF_NAME]
        host = config[CONF_HOST]
        token = config[CONF_TOKEN]
        _LOGGER.info('Initializing %s with host %s (token %s...)', name, host, token[:5])

        self._config = config
        self._device = MiioDevice(host, token)
        super().__init__(name, self._device, config=config, logger=_LOGGER)
        self._success_result = [0]

        self._props = [
            'relay_names_g1', 'relay_status_g1',
            'relay_names_g2', 'relay_status_g2',
            'g2Enable', 'codeEnable',
        ]
        self._subs = {}

    @property
    def device_class(self):
        return SwitchDeviceClass.SWITCH

    async def async_update(self):
        await super().async_update()
        await self.hass.async_add_executor_job(self.update_all)

    def update_all(self):
        if self._available:
            attrs = self._state_attrs
            self._state = False
            add_switches = self._add_entities.get(ENTITY_DOMAIN)
            idx = 0
            for g in [1, 2]:
                if f'relay_status_g{g}' not in attrs:
                    continue
                sta = int(attrs.get(f'relay_status_g{g}') or 0)
                if sta:
                    self._state = True
                nms = str(attrs.get(f'relay_names_g{g}') or '').split('-')
                s = 0
                b = 1
                for n in nms:
                    s += 1
                    k = f'g{g}s{s}'
                    self._state_attrs[k] = STATE_ON if sta & b else STATE_OFF
                    if k in self._subs:
                        self._subs[k].update_from_parent()
                    elif add_switches:
                        self._subs[k] = PwznRelaySwitchSubEntity(self, g, s, {
                            'attr': k,
                            'index': idx,
                        })
                        add_switches([self._subs[k]], update_before_add=True)
                    b <<= 1
                    idx += 1

            if self.custom_config('enable_advanced'):
                for k in ['g2Enable', 'codeEnable']:
                    if k not in attrs:
                        continue
                    self._state_attrs[k] = STATE_ON if attrs[k] else STATE_OFF
                    if k in self._subs:
                        self._subs[k].update_from_parent()
                    elif add_switches:
                        self._subs[k] = PwznRelaySwitchSubEntity(self, 0, 0, {
                            'attr': k,
                        })
                        add_switches([self._subs[k]], update_before_add=True)

    def turn_on(self, **kwargs):
        ret = self.send_miio_command('power_all', [1])
        if ret:
            full = (1 << 16) - 1
            self.update_attrs({
                'relay_status_g1': full,
                'relay_status_g2': full,
            }, update_parent=False)
            self.update_all()
            self._state = True
        return ret

    def turn_off(self, **kwargs):
        ret = self.send_miio_command('power_all', [0])
        if ret:
            self.update_attrs({
                'relay_status_g1': 0,
                'relay_status_g2': 0,
            }, update_parent=False)
            self.update_all()
            self._state = False
        return ret


class PwznRelaySwitchSubEntity(SwitchSubEntity):
    def __init__(self, parent, group, switch, option=None):
        self._group = group
        self._switch = switch
        self._switch_index = 0
        key = f'g{group}s{switch}'
        if isinstance(option, dict):
            if option.get('attr'):
                key = option.get('attr')
            self._switch_index = int(option.get('index') or 0)
        super().__init__(parent, key, option)

    def turn_parent(self, on):
        if self._attr == 'g2Enable':
            ret = self.call_parent('send_miio_command', 'set_g2enable', [1 if on else 0])
        elif self._attr == 'codeEnable':
            ret = self.call_parent('send_miio_command', 'set_codeEnable', [1 if on else 0])
        elif isinstance(self._parent, MiotPwznRelaySwitchEntity):
            ret = self.call_parent('turn_channel', self._switch_index, on)
        else:
            ret = self.call_parent('send_miio_command', 'power_on' if on else 'power_off', [self._switch_index])
        if ret:
            self.update_attrs({
                self._attr: STATE_ON if on else STATE_OFF
            }, update_parent=True)
            self._state = on and True
        return ret

    def turn_on(self, **kwargs):
        return self.turn_parent(True)

    def turn_off(self, **kwargs):
        return self.turn_parent(False)
