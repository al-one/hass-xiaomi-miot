"""Provide info to system health."""
import os
import json

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .core.const import *
from .core.utils import get_manifest
from .core.xiaomi_cloud import MiotCloud


@callback
def async_register(hass: HomeAssistant, register: system_health.SystemHealthRegistration) -> None:
    """Register system health callbacks."""
    register.async_register_info(system_health_info, '/config/integrations')


async def system_health_info(hass):
    """Get info for the info page."""
    mic = None
    uas = {}
    uds = {}
    all_devices = {}
    for mic in MiotCloud.all_clouds(hass):
        uas[mic.user_id] = mic
        uds[mic.unique_id] = await mic.async_get_devices_by_key('did') or {}
        all_devices.update(uds[mic.unique_id])

    api = mic.get_api_url('') if mic else 'https://api.io.mi.com'
    api_spec = 'https://miot-spec.org/miot-spec-v2/spec/services'

    version = await hass.async_add_executor_job(get_manifest, 'version', 'unknown')
    data = {
        'component_version': version,
        'can_reach_server': system_health.async_check_can_reach_url(hass, api),
        'can_reach_spec': system_health.async_check_can_reach_url(
            hass, api_spec, 'https://home.miot-spec.com/?cant-reach',
        ),
        'logged_accounts': len(uas),
        'total_devices': len(all_devices),
    }

    return data
