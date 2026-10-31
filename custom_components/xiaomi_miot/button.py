"""Support button entity for Xiaomi Miot."""
import asyncio
import hashlib
import logging

from homeassistant.components.button import (
    DOMAIN as ENTITY_DOMAIN,
    ButtonEntity as BaseEntity,
)
from homeassistant.const import CONF_USERNAME
from homeassistant.exceptions import HomeAssistantError
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import async_get_current_platform
from homeassistant.loader import async_get_integration

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
from .core.manual_scenes import manual_scene_button_names as _manual_scene_button_names, scene_key
from .core.utils import slugify_object_id

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'

SERVICE_TO_METHOD = {}


async def async_setup_entry(hass, config_entry, async_add_entities):
    entry = HassEntry.init(hass, config_entry)
    entry.new_adder(ENTITY_DOMAIN, async_add_entities)
    await async_setup_config_entry(hass, config_entry, async_setup_platform, async_add_entities, ENTITY_DOMAIN)
    if (not entry.get_config(CONF_USERNAME) or not entry.cloud
            or entry.get_config('disable_manual_scenes', False)):
        return
    manager = entry.get_manual_scenes()
    platform = async_get_current_platform()
    version = (await async_get_integration(hass, DOMAIN)).version
    entities = {}
    task = None
    unloaded = False

    async def synchronize():
        scenes = manager.scenes
        for key in list(entities):
            if key not in scenes:
                entity = entities.pop(key)
                if entity.entity_id in platform.entities:
                    await platform.async_remove_entity(entity.entity_id)
        registry = er.async_get(hass)
        occupied = set(registry.entities) | set(hass.states.async_entity_ids())
        added = []
        for key, scene in sorted(scenes.items()):
            if key in entities:
                continue
            entity = ManualSceneButton(entry.cloud, scene, manager.name(key), manager, version)
            existing = registry.async_get_entity_id(ENTITY_DOMAIN, DOMAIN, entity.unique_id)
            if existing:
                if registry.async_get(existing).config_entry_id != config_entry.entry_id:
                    raise HomeAssistantError('Manual scene identity belongs to another entry')
                entity.entity_id = existing
            else:
                base = entity.entity_id
                if base in occupied:
                    digest = hashlib.sha256(entity.unique_id.encode()).hexdigest()[:12]
                    base = f'{base}_{digest}'
                entity.entity_id = base
                index = 2
                while entity.entity_id in occupied:
                    entity.entity_id = f'{base}_{index}'
                    index += 1
            entities[key] = entity
            occupied.add(entity.entity_id)
            added.append(entity)
        if added:
            # Await the real platform addition, then reconcile metadata again.
            await platform.async_add_entities(added)

    @callback
    def schedule():
        nonlocal task
        if unloaded or set(entities) == set(manager.scenes):
            return
        if task is None or task.done():
            task = hass.async_create_task(synchronize())
            task.add_done_callback(completed)

    @callback
    def completed(done):
        if not done.cancelled():
            if done.exception():
                _LOGGER.error('Manual scene entity synchronization failed')
            else:
                schedule()

    unsubscribe = async_dispatcher_connect(hass, manager.signal, schedule)

    async def close():
        nonlocal unloaded
        unloaded = True
        unsubscribe()
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    config_entry.async_on_unload(close)
    config_entry.async_on_unload(manager.async_close)
    await manager.async_start()
    schedule()
    if task:
        await task


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

    def __init__(self, cloud, scene, name, manager=None, version=None):
        self.cloud = cloud
        self.scene = scene
        self.manager = manager
        self._scene_key = scene_key(scene)
        self._attr_name = name
        self._attr_unique_id = (
            f'{cloud.unique_id}-manual-scene-'
            f'{scene["home_id"]}-{scene["scene_id"]}'
        )
        self._attr_device_info = {
            'identifiers': {(DOMAIN, f'{cloud.unique_id}-manual-scenes')},
            'name': '米家场景手动控制',
            'translation_key': 'manual_scenes',
            'manufacturer': 'Xiaomi',
            'model': 'xiaomi_miot.scenes.manual_controls',
            'entry_type': DeviceEntryType.SERVICE,
            'configuration_url': 'homeassistant://config/integrations/integration/xiaomi_miot',
            'sw_version': str(version) if version is not None else None,
        }
        self._attr_extra_state_attributes = {
            'home_name': scene.get('home_name') or None,
        }
        if manager:
            self.entity_id = ('button.xiaomi_miot_scenes_manual_controls_'
                              f'{slugify_object_id(scene.get("home_name") or scene["home_id"])}_'
                              f'{slugify_object_id(scene["scene_id"])}')

    @property
    def available(self):
        return self.manager.route(self._scene_key) is not None if self.manager else True

    @property
    def icon(self):
        if not self.manager:
            return self._attr_icon
        return {'cloud': 'mdi:cloud-outline', 'local': 'mdi:hub-outline'}.get(
            self.manager.route(self._scene_key), 'mdi:cloud-off-outline',
        )

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if self.manager:
            self.async_on_remove(async_dispatcher_connect(
                self.hass, self.manager.signal, self._scene_updated,
            ))
            self._scene_updated()

    @callback
    def _scene_updated(self):
        scene = self.manager.get_scene(self._scene_key)
        if scene:
            self.scene = scene
            name = self.manager.name(self._scene_key)
            if self._attr_name != name:
                self._attr_name = name
                er.async_get(self.hass).async_update_entity(self.entity_id, original_name=name)
            self._attr_extra_state_attributes = {'home_name': scene.get('home_name') or None}
        self.async_write_ha_state()

    async def async_press(self):
        if self.manager:
            return await self.manager.async_run(self._scene_key)
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
