"""Provide info to system health."""
import os
import json

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .core.const import *
from .core.xiaomi_cloud import MiotCloud


@callback
def async_register(hass: HomeAssistant, register: system_health.SystemHealthRegistration) -> None:
    """Register system health callbacks."""
    register.async_register_info(system_health_info, '/config/integrations')


async def system_health_info(hass):
    """Get info for the info page."""
    mic = None
    uds = {}
    all_devices = {}
    for v in hass.data[DOMAIN].values():
        if isinstance(v, dict):
            v = v.get(CONF_XIAOMI_CLOUD)
        if isinstance(v, MiotCloud):
            mic = v
            if mic.user_id not in uds:
                uds[mic.user_id] = await mic.async_get_devices_by_key('did') or {}
                all_devices.update(uds[mic.user_id])

    api = mic.get_api_url('') if mic else 'https://api.io.mi.com'
    api_spec = 'https://miot-spec.org/miot-spec-v2/spec/services'

    manifest = {}
    with open(f'{os.path.dirname(__file__)}/manifest.json') as fil:
        manifest = json.load(fil) or {}

    data = {
        'component_version': manifest.get('version', 'unknown'),
        'can_reach_server': system_health.async_check_can_reach_url(hass, api),
        'can_reach_spec': system_health.async_check_can_reach_url(
            hass, api_spec, 'https://home.miot-spec.com/?cant-reach',
        ),
        'logged_accounts': len(uds),
        'total_devices': len(all_devices),
    }

    return data
