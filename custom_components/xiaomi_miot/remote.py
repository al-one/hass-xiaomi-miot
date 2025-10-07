"""Support remote entity for Xiaomi Miot."""
import logging
import asyncio
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
    HassEntry,
    MiotEntity,
    async_setup_config_entry,
    bind_services_to_entries,
)
from .core.utils import get_translations, DeviceException
from .core.miot_spec import (
    MiotSpec,
)
from .core.xiaomi_cloud import (
    MiotCloud,
    MiCloudException,
)

_LOGGER = logging.getLogger(__name__)
DATA_KEY = f'{ENTITY_DOMAIN}.{DOMAIN}'


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
        host = config.get(CONF_HOST)
        token = config.get(CONF_TOKEN)
        if spec.name in ['remote_control', 'ir_remote_control']:
            if 'chuangmi.remote.' in model or 'chuangmi.ir.' in model:
                ChuangmiIr = await hass.async_add_executor_job(import_miio_chuangmi_remote)
                device = ChuangmiIr(host, token)
                entities.append(MiotRemoteEntity(config, spec, device))
        elif model in [
            'xiaomi.wifispeaker.l05c',
            'xiaomi.wifispeaker.lx5a',
            'xiaomi.wifispeaker.lx06',
            'xiaomi.wifispeaker.oh2p',
            'lumi.acpartner.v1',
            'lumi.acpartner.v2',
            'lumi.acpartner.v3',
            'lumi.acpartner.mcn04',
        ]:
            entities.append(MiotRemoteEntity(config, spec))
    for entity in entities:
        hass.data[DOMAIN]['entities'][entity.unique_id] = entity
    async_add_entities(entities, update_before_add=True)


def import_miio_chuangmi_remote():
    try:
        from miio import ChuangmiIr
    except (ModuleNotFoundError, ImportError):
        from miio.integrations.chuangmi.remote import ChuangmiIr
    return ChuangmiIr


class MiotRemoteEntity(MiotEntity, RemoteEntity):
    def __init__(self, config, miot_spec: MiotSpec, device=None):
        self._miot_spec = miot_spec
        super().__init__(miot_service=None, device=device, config=config, logger=_LOGGER)
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
                        'async_select_option': self.async_press_ir_key,
                    })
                    add_selects([self._subs[ird]], update_before_add=False)
        if irs:
            self._state_attrs['ir_devices'] = irs

    def is_on(self):
        return True

    async def async_send_command(self, command, **kwargs):
        """Send commands to a device."""
        repeat = kwargs.get(remote.ATTR_NUM_REPEATS, remote.DEFAULT_NUM_REPEATS)
        delays = kwargs.get(remote.ATTR_DELAY_SECS, remote.DEFAULT_DELAY_SECS)
        did = kwargs.get(remote.ATTR_DEVICE)
        for _ in range(repeat):
            for cmd in command:
                try:
                    if f'{cmd}'[:4] == 'key:':
                        ret = await self.async_send_cloud_command(did, cmd)
                    elif f'{cmd}'.startswith('FE'):
                        ret = await self.miot_device.async_send('send_ir_code', [cmd])
                    else:
                        ret = self.hass.async_add_executor_job(self.miot_device.play, cmd)
                    self.logger.info('%s: Send IR command %s(%s) result: %s', self.name_model, cmd, kwargs, ret)
                except (DeviceException, MiCloudException) as exc:
                    self.logger.error('%s: Send IR command %s(%s) failed: %s', self.name_model, cmd, kwargs, exc)
                await asyncio.sleep(delays)

    async def async_send_cloud_command(self, did, command):
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
        res = await mic.async_request_api('v2/irdevice/controller/key/click', {
            'did': did,
            'key_id': key,
        }) or {}
        if res.get('code'):
            self.logger.warning('%s: Send IR command %s(%s) failed: %s', self.name_model, command, did, res)
        return res

    async def async_learn_command(self, **kwargs):
        """Learn a command from a device."""
        if not self.miot_device:
            return {'error': f'Not support for {self.model}'}
        timeout = int(kwargs.get(remote.ATTR_TIMEOUT) or 30)
        res = {}
        key = int(kwargs.get(remote.ATTR_DEVICE, 999999))
        try:
            for idx in range(timeout):
                if hasattr(self.miot_device, 'read'):
                    learn = self.hass.async_add_executor_job(self.miot_device.learn, key)
                    read = self.hass.async_add_executor_job(self.miot_device.read, key)
                else:
                    learn = self.miot_device.async_send('start_ir_learn', [key])
                    read = self.miot_device.async_send('get_ir_learn_result')
                if idx == 0:
                    await learn
                await asyncio.sleep(1)
                res = await read
                if isinstance(res, dict) and res.get('code'):
                    break
                if isinstance(res, list) and res and str(res[0]).startswith('FE'):
                    # lumi.acpartner.v*
                    res = {'result': res}
                    break
        except Exception as exc:
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

    async def async_press_ir_key(self, select, **kwargs):
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
            return await self.async_send_cloud_command(did, key)
        return False
