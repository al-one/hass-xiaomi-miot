"""Support button entity for Xiaomi Miot."""
from collections import Counter
import logging

from homeassistant.components.button import (
    DOMAIN as ENTITY_DOMAIN,
    ButtonEntity as BaseEntity,
)
from homeassistant.const import CONF_USERNAME
from homeassistant.exceptions import HomeAssistantError

from . import (
    DOMAIN,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    HassEntry,
    XEntity,
    BaseSubEntity,
    async_setup_config_entry,
)
from .core.templates import template
from .core.xiaomi_cloud import MiCloudException

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    entry = HassEntry.init(hass, config_entry)
    entry.new_adder(ENTITY_DOMAIN, async_add_entities)
    await async_setup_config_entry(hass, config_entry, async_setup_platform, async_add_entities, ENTITY_DOMAIN)
    if not entry.get_config(CONF_USERNAME) or not entry.cloud:
        return
    try:
        scenes = await entry.cloud.async_get_manual_scenes()
    except MiCloudException as exc:
        _LOGGER.warning('Unable to get Xiaomi Home manual scenes: %s', exc)
        return
    names = Counter(scene['scene_name'] for scene in scenes)
    async_add_entities([
        ManualSceneButton(
            entry.cloud,
            scene,
            (
                f'{scene["home_name"]} {scene["scene_name"]}'
                if names[scene['scene_name']] > 1 and scene['home_name']
                else scene['scene_name']
            ),
        )
        for scene in scenes
    ])


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hass.data.setdefault(DATA_KEY, {})


class ButtonEntity(XEntity, BaseEntity):
    def on_init(self):
        self._attr_available = True
        if des := getattr(self.conv, 'description', None):
            self._attr_name = f'{self._attr_name} {des}'

    def set_state(self, data: dict):
        pass

    async def async_press(self):
        pms = getattr(self.conv, 'value', None)
        if self._miot_action and self._miot_action.ins:
            pms = self.custom_config_list('action_params', pms)
            if pms:
                vars = {
                    'attrs': self.device.props,
                }
                pms = [
                    v if not isinstance(v, str) else template(v, self.hass).async_render(vars)
                    for v in pms
                ]
        await self.device.async_write({self.attr: pms})


XEntity.CLS[ENTITY_DOMAIN] = ButtonEntity


class ManualSceneButton(BaseEntity):
    _attr_has_entity_name = True
    _attr_icon = 'mdi:play'

    def __init__(self, cloud, scene, name):
        self.cloud = cloud
        self.scene = scene
        self._attr_name = name
        self._attr_unique_id = (
            f'{cloud.unique_id}-manual-scene-'
            f'{scene["home_id"]}-{scene["scene_id"]}'
        )
        self._attr_device_info = {
            'identifiers': {(DOMAIN, f'{cloud.unique_id}-manual-scenes')},
            'name': 'Xiaomi Home Scenes',
            'manufacturer': 'Xiaomi',
            'model': 'Manual scenes',
        }
        self._attr_extra_state_attributes = {
            'home_name': scene.get('home_name') or None,
        }

    async def async_press(self):
        try:
            success = await self.cloud.async_run_manual_scene(self.scene)
        except MiCloudException as exc:
            raise HomeAssistantError(
                f'Unable to run Xiaomi Home scene: {self.name}'
            ) from exc
        if not success:
            raise HomeAssistantError(
                f'Unable to run Xiaomi Home scene: {self.name}'
            )


class ButtonSubEntity(BaseEntity, BaseSubEntity):
    def __init__(self, parent, attr, option=None):
        BaseSubEntity.__init__(self, parent, attr, option, domain=ENTITY_DOMAIN)
        self._available = True
        self._async_action = self._option.get('async_press_action')
        self._press_action = self._option.get('press_action')
        self._press_kwargs = {
            'attr': self._attr,
            **(self._option.get('press_kwargs') or {}),
        }
        self._state_attrs = self._option.get('state_attrs') or {}

    def update(self, data=None):
        return

    def press(self):
        """Press the button."""
        if not self._press_action:
            raise NotImplementedError()
        if ret := self._press_action(**self._press_kwargs):
            self.schedule_update_ha_state()
        return ret

    async def async_press(self):
        if self._async_action:
            if ret := await self._async_action(**self._press_kwargs):
                self.schedule_update_ha_state()
            return ret
        await super().async_press()
