"""Support remote entity for Xiaomi Miot."""
import logging
import asyncio
import time
from functools import partial

from homeassistant.const import (
    CONF_HOST,
    CONF_TOKEN,
)
from homeassistant.components import remote, persistent_notification
from homeassistant.components.remote import (
    DOMAIN as ENTITY_DOMAIN,
    RemoteEntity,
    RemoteEntityFeature,
)

from . import (
    DOMAIN,
    CONF_MODEL,
    XIAOMI_CONFIG_SCHEMA as PLATFORM_SCHEMA,  # noqa: F401
    MiotEntity,
    DeviceException,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.utils import get_translations
from .core.miot_spec import (
    MiotSpec,
)
from .core.xiaomi_cloud import (
    MiotCloud,
    MiCloudException,
)

try:
    from miio import ChuangmiIr
except (ModuleNotFoundError, ImportError):
    from miio.integrations.chuangmi.remote import ChuangmiIr

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
    if isinstance(spec, MiotSpec):
        if spec.name in ['remote_control', 'ir_remote_control']:
            if 'chuangmi.remote.' in model or 'chuangmi.ir.' in model:
                entities.append(MiotRemoteEntity(config, spec))
        elif model in [
            'xiaomi.wifispeaker.l05c',
            'xiaomi.wifispeaker.lx5a',
            'xiaomi.wifispeaker.lx06',
            'lumi.acpartner.mcn04',
        ]:
            entities.append(MiotRemoteEntity(config, spec))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)
    bind_services_to_entries(hass, SERVICE_TO_METHOD)


class MiotRemoteEntity(MiotEntity, RemoteEntity):
    def __init__(self, config, miot_spec: MiotSpec):
        self._miot_spec = miot_spec
        super().__init__(miot_service=None, config=config, logger=_LOGGER)
        host = config.get(CONF_HOST)
        token = config.get(CONF_TOKEN)
        self._device = ChuangmiIr(host, token)
        self._attr_should_poll = False
        self._supported_features = RemoteEntityFeature.LEARN_COMMAND
        self._translations = get_translations('ir_devices')

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        did = self.miot_did
        mic = self.miot_cloud
        irs = []
        if did and isinstance(mic, MiotCloud):
            rdt = await mic.async_request_api('v2/irdevice/controllers', {'parent_id': did}) or {}
            rds = (rdt.get('result') or {}).get('controllers') or []
            if not rdt:
                dls = await mic.async_get_devices() or []
                for d in dls:
                    if did == d.get('parent_id'):
                        rds.append(d)
            for d in rds:
                ird = d.get('did')
                rdt = await mic.async_request_api('v2/irdevice/controller/keys', {'did': ird}) or {}
                kys = (rdt.get('result') or {}).get('keys', {})
                irs.append({
                    'did': ird,
                    'name': d.get('name'),
                    'keys': kys,
                })
                add_selects = self._add_entities.get('select')
                if not kys:
                    self.logger.info('%s: IR device %s(%s) have no keys: %s', self.name_model, ird, d.get('name'), rdt)
                elif add_selects and ird not in self._subs:
                    from .select import SelectSubEntity
                    ols = []
                    for k in kys:
                        nam = k.get('display_name') or k.get('name')
                        if not nam:
                            continue
                        nam = self._translations.get(nam, nam)
                        ols.append(nam)
                    self._subs[ird] = SelectSubEntity(self, ird, option={
                        'name': d.get('name'),
                        'entity_id': f'remote_{ird}'.replace('.', '_'),
                        'options': ols,
                        'select_option': self.press_ir_key,
                    })
                    add_selects([self._subs[ird]], update_before_add=False)
        if irs:
            self._state_attrs['ir_devices'] = irs

    def is_on(self):
        return True

    def send_remote_command(self, command, **kwargs):
        """Send commands to a device."""
        repeat = kwargs.get(remote.ATTR_NUM_REPEATS, remote.DEFAULT_NUM_REPEATS)
        delays = kwargs.get(remote.ATTR_DELAY_SECS, remote.DEFAULT_DELAY_SECS)
        did = kwargs.get(remote.ATTR_DEVICE)
        for _ in range(repeat):
            for cmd in command:
                try:
                    if f'{cmd}'[:4] == 'key:':
                        ret = self.send_cloud_command(did, cmd)
                    else:
                        ret = self._device.play(cmd)
                    self.logger.info('%s: Send IR command %s(%s) result: %s', self.name_model, cmd, kwargs, ret)
                except (DeviceException, MiCloudException) as exc:
                    self.logger.error('%s: Send IR command %s(%s) failed: %s', self.name_model, cmd, kwargs, exc)
                time.sleep(delays)

    def send_cloud_command(self, did, command):
        key = f'{command}'
        if key[:4] == 'key:':
            key = key[4:]
        try:
            key = int(key)
        except (TypeError, ValueError):
            key = None
        if not did or not key:
            self.logger.warning('%s: IR command %s to %s invalid for cloud.', self.name_model, command, did)
            return False
        mic = self.miot_cloud
        if not mic:
            return False
        res = mic.request_miot_api('v2/irdevice/controller/key/click', {
            'did': did,
            'key_id': key,
        }) or {}
        if res.get('code'):
            self.logger.warning('%s: Send IR command %s(%s) failed: %s', self.name_model, command, did, res)
        return res

    async def async_send_command(self, command, **kwargs):
        """Send commands to a device."""
        await self.hass.async_add_executor_job(
            partial(self.send_remote_command, command, **kwargs)
        )

    async def async_learn_command(self, **kwargs):
        """Learn a command from a device."""
        timeout = int(kwargs.get(remote.ATTR_TIMEOUT) or 30)
        res = {}
        try:
            key = int(kwargs.get(remote.ATTR_DEVICE, 999999))
            for idx in range(timeout):
                if idx == 0:
                    await self.hass.async_add_executor_job(self._device.learn, key)
                await asyncio.sleep(1)
                res = await self.hass.async_add_executor_job(self._device.read, key)
                if isinstance(res, dict) and res.get('code'):
                    break
        except (TypeError, ValueError, DeviceException) as exc:
            res = {'error': f'{exc}'}
            self.logger.warning(
                '%s: Learn command failed, the device ID must between 1 and 1000000. %s',
                self.name_model, exc,
            )
        persistent_notification.async_create(
            self.hass,
            f'{res}',
            'Remote learn result',
            f'{DOMAIN}-remote-learn',
        )
        return res

    def delete_command(self, **kwargs):
        """Delete commands from the database."""
        raise NotImplementedError()

    def press_ir_key(self, select, **kwargs):
        key = None
        did = kwargs.get('attr')
        for d in self._state_attrs.get('ir_devices', []):
            if did and did != d.get('did'):
                continue
            for k in d.get('keys', []):
                if select not in [
                    k.get('display_name'),
                    k.get('name'),
                    self._translations.get(k.get('display_name') or k.get('name')),
                ]:
                    continue
                key = k.get('id')
        if key:
            return self.send_cloud_command(did, key)
        return False
