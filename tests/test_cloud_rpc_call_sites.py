"""The cloud RPC option must reach every cloud read in Device.async_get_properties."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from custom_components.xiaomi_miot.core.device import Device, DeviceException

MAPPING = {'vacuum.status': {'siid': 2, 'piid': 1}}
RESULT = [{'code': 0, 'siid': 2, 'piid': 1, 'value': 4, 'prop': 'vacuum.status'}]


def _device(rpc, local_error=None, use_local=False):
    cloud = SimpleNamespace(async_get_properties_for_mapping=AsyncMock(return_value=RESULT))
    local = SimpleNamespace(async_get_properties_for_mapping=AsyncMock(
        side_effect=local_error, return_value=RESULT,
    ))
    return SimpleNamespace(
        spec=object(), use_local=use_local, local_only=False, auto_cloud=True, _local_state=True,
        _local_fails=0, name='vac', did='1', cloud=cloud, local=local, log=MagicMock(),
        info=SimpleNamespace(miio_info=None),
        custom_config_bool=lambda key, default=False: rpc if key == 'miot_cloud_rpc' else default,
        normalize_miot_results=lambda results: results,
        dispatch=lambda *args, **kwargs: None,
        decode=lambda results: results,
    )


async def test_cloud_read_passes_the_rpc_option():
    device = _device(rpc=True)
    await Device.async_get_properties(device, MAPPING)

    device.cloud.async_get_properties_for_mapping.assert_awaited_once_with('1', MAPPING, use_rpc=True)


async def test_cloud_read_keeps_the_default_without_the_option():
    device = _device(rpc=False)
    await Device.async_get_properties(device, MAPPING)

    device.cloud.async_get_properties_for_mapping.assert_awaited_once_with('1', MAPPING, use_rpc=False)


async def test_local_failure_fallback_passes_the_rpc_option():
    device = _device(rpc=True, local_error=DeviceException('lan down'), use_local=True)
    await Device.async_get_properties(device, MAPPING)

    device.cloud.async_get_properties_for_mapping.assert_awaited_once_with('1', MAPPING, use_rpc=True)
