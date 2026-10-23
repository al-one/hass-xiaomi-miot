"""Account-scoped scene metadata, refresh ownership and single dispatch.

Use the existing Miot cloud session. Cached metadata is not execution evidence
for a gateway, and an unsuccessful read is not an authoritative empty home.
"""

import asyncio
from collections import Counter
import logging
from aiohttp import ClientError

from homeassistant.exceptions import HomeAssistantError
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .xiaomi_cloud import MiCloudException, manual_scene_id, normalize_manual_scene

_LOGGER = logging.getLogger(__name__)
REFRESH_INTERVAL = 600


def scene_key(scene):
    return scene['home_id'], scene['scene_id']


def manual_scene_button_names(scenes):
    names = [f'{s.get("home_name") or s["home_id"]} {s["scene_name"]}' for s in scenes]
    counts = Counter(names)
    return [f'{name} {s["home_id"]}-{s["scene_id"]}' if counts[name] > 1 else name
            for s, name in zip(scenes, names)]


def scene_error(key):
    return HomeAssistantError(translation_domain=DOMAIN, translation_key=key)


class ManualScenes:
    """One entry owns its metadata task, snapshots, listeners and executions."""

    def __init__(self, entry):
        self.entry = entry
        self.hass = entry.hass
        self.cloud = entry.cloud
        self._account = self.cloud.unique_id
        self.signal = f'{DOMAIN}.manual_scenes.{entry.id}'
        self._store = Store(self.hass, 1, f'{DOMAIN}.manual_scenes.{entry.id}', private=True)
        self._homes = {}
        self._scenes = {}
        self._names = {}
        self._task = None
        self._timer = None
        self._pending = False
        self._loaded = False
        self._closed = False
        self._cloud_available = True  # No separate network probe is introduced.
        self._executions = {}
        self._unsub_stop = None

    @property
    def enabled(self):
        return (not self._closed and not self.hass.is_stopping
                and self.cloud.unique_id == self._account
                and not self.entry.get_config('disable_manual_scenes', False))

    @property
    def scenes(self):
        return {key: dict(value) for key, value in self._scenes.items()}

    def get_scene(self, key):
        scene = self._scenes.get(key)
        return dict(scene) if scene else None

    def name(self, key):
        return self._names.get(key)

    def route(self, key):
        """A channel to attempt, not proof of cloud or physical completion."""
        return 'cloud' if self.enabled and key in self._scenes and self._cloud_available else None

    def notify(self):
        if not self._closed:
            values = list(self._scenes.values())
            self._names = dict(zip(self._scenes, manual_scene_button_names(values)))
            async_dispatcher_send(self.hass, self.signal)

    def cloud_status(self, available):
        """Passive feedback from the existing cloud traffic; no extra ping."""
        if not self.enabled or available == self._cloud_available:
            return
        self._cloud_available = available
        self.notify()
        if available:
            self.request_refresh()

    def _selected(self, home_id):
        mode = self.entry.get_config('filter_home_id')
        if not mode:
            return True
        values = self.entry.get_config('home_id_list', []) or []
        matches = home_id in {str(value) for value in values}
        return matches if mode == 'include' else not matches

    def _parse_scenes(self, home, records):
        if not isinstance(records, list):
            raise MiCloudException('Xiaomi manual scene list is invalid')
        scenes = {}
        for record in records:
            scene = normalize_manual_scene(
                record, home['home_id'], home['owner_uid'], home['home_name'],
            )
            key = scene_key(scene)
            if key in scenes and scenes[key] != scene:
                raise MiCloudException('Xiaomi manual scene list has conflicting records')
            scenes[key] = scene
        return scenes

    async def async_start(self):
        """Only the cache is awaited during platform setup."""
        if self._loaded or not self.enabled:
            return
        self._unsub_stop = self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, self.async_close,
        )
        try:
            cached = await self._store.async_load()
        except (OSError, ValueError):
            cached = None
            _LOGGER.debug('Manual scene cache unavailable')
        if self._closed:
            return
        if isinstance(cached, dict) and cached.get('account') == self._account:
            homes = cached.get('homes')
            if isinstance(homes, list):
                conflicts = set()
                for home in homes:
                    try:
                        home_id = manual_scene_id(home['home_id'])
                        owner = manual_scene_id(home['owner_uid'])
                        scoped = {'home_id': home_id, 'owner_uid': owner,
                                  'home_name': (home.get('home_name')
                                                if isinstance(home.get('home_name'), str) else '')}
                        records = self._parse_scenes(scoped, home['scenes'])
                    except (KeyError, TypeError, MiCloudException):
                        continue
                    if home_id in self._homes:
                        old = {key: scene for key, scene in self._scenes.items() if key[0] == home_id}
                        if self._homes[home_id] != scoped or old != records:
                            conflicts.add(home_id)
                    elif self._selected(home_id):
                        self._homes[home_id] = scoped
                        self._scenes.update(records)
                for home_id in conflicts:
                    self._homes.pop(home_id, None)
                    self._scenes = {key: scene for key, scene in self._scenes.items() if key[0] != home_id}
        self._loaded = True
        self.notify()
        self.request_refresh()

    def request_refresh(self):
        if not self.enabled or not self._loaded:
            return
        if self._timer:
            self._timer.cancel()
            self._timer = None
        if self._task is not None:
            self._pending = True
            return
        self._task = self.hass.async_create_background_task(
            self._refresh(), 'xiaomi_miot manual scenes', eager_start=False,
        )

    async def _refresh(self):
        try:
            await self._refresh_homes()
        except (MiCloudException, ClientError, OSError, TimeoutError, ValueError):
            _LOGGER.debug('Manual scene metadata refresh unavailable')
        finally:
            self._task = None
            pending, self._pending = self._pending, False
            if self.enabled:
                if pending:
                    self.request_refresh()
                else:
                    self._timer = self.hass.loop.call_later(REFRESH_INTERVAL, self.request_refresh)

    async def _refresh_homes(self):
        homes = await self.cloud.async_get_manual_scene_homes()
        if not self.enabled:
            return
        # Validate the complete home snapshot before removing any old home.
        selected = {}
        for home in homes:
            home_id = manual_scene_id(home.get('id'))
            item = {'home_id': home_id,
                    'owner_uid': manual_scene_id(home.get('uid', self.cloud.user_id)),
                    'home_name': home.get('name') if isinstance(home.get('name'), str) else ''}
            if home_id in selected and selected[home_id] != item:
                raise MiCloudException('Conflicting Xiaomi scene home identities')
            if self._selected(home_id):
                selected[home_id] = item
        # A new authoritative scope revokes the old owner before any list I/O.
        retained = {key: dict(scene, home_name=selected[key[0]]['home_name'])
                    for key, scene in self._scenes.items()
                    if key[0] in selected
                    and scene['owner_uid'] == selected[key[0]]['owner_uid']}
        if retained != self._scenes or selected != self._homes:
            self._homes, self._scenes = selected, retained
            self.notify()
        updated = {}
        for home_id, home in selected.items():
            try:
                records = await self.cloud.async_get_manual_scene_home(home)
                scenes = self._parse_scenes(home, records)
            except (MiCloudException, ClientError, OSError, TimeoutError, ValueError):
                old = self._homes.get(home_id)
                scenes = {key: dict(scene, home_name=home['home_name'])
                          for key, scene in self._scenes.items()
                          if old and old['owner_uid'] == home['owner_uid']
                          and key[0] == home_id}
                _LOGGER.debug('Manual scene home refresh unavailable; retaining scoped metadata')
            if not self.enabled:
                return
            updated.update(scenes)
        self._homes, self._scenes = selected, updated
        self.notify()
        payload = {'account': self._account, 'homes': [
            {**home, 'scenes': [scene for key, scene in updated.items() if key[0] == home_id]}
            for home_id, home in selected.items()
        ]}
        try:
            await self._store.async_save(payload)
        except (OSError, ValueError):
            # In-memory empty homes remain authoritative even if saving fails.
            _LOGGER.debug('Manual scene cache save unavailable')

    async def async_execute(self, scene):
        return await self.cloud.async_run_manual_scene(scene)

    async def async_run(self, key):
        if self.route(key) is None:
            raise scene_error('scene_unavailable')
        if key in self._executions:
            raise scene_error('scene_busy')
        scene = self.get_scene(key)
        self._executions[key] = asyncio.current_task()
        try:
            if await self.async_execute(scene) is not True:
                raise scene_error('scene_failed')
        except (MiCloudException, ClientError, OSError, TimeoutError, ValueError) as exc:
            raise scene_error('scene_result_unknown') from exc
        finally:
            self._executions.pop(key, None)

    async def async_close(self, event=None):
        if self._closed:
            return
        self._closed = True
        if self._unsub_stop:
            if event is None:
                self._unsub_stop()
            self._unsub_stop = None
        self._pending = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
        tasks = set(self._executions.values())
        if self._task:
            tasks.add(self._task)
        tasks.discard(asyncio.current_task())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._executions.clear()


async def async_remove_scene_cache(hass, entry_id):
    await Store(hass, 1, f'{DOMAIN}.manual_scenes.{entry_id}').async_remove()
