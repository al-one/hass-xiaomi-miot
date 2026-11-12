"""Coverage for reading cloud properties through the RPC relay instead of the cached `prop/get`."""
from unittest.mock import AsyncMock, patch

from custom_components.xiaomi_miot import init_integration_data
from custom_components.xiaomi_miot.core.device_customizes import DEVICE_CUSTOMIZES
from custom_components.xiaomi_miot.core.xiaomi_cloud import MiotCloud

MAPPING = {
    'vacuum.status': {'siid': 2, 'piid': 1},
    'battery_level': {'siid': 3, 'piid': 1},
}
CACHED = [
    {'code': 0, 'did': '1', 'siid': 2, 'piid': 1, 'value': 3},
    {'code': 0, 'did': '1', 'siid': 3, 'piid': 1, 'value': 99},
]
LIVE = [
    {'code': 0, 'did': '1', 'siid': 2, 'piid': 1, 'value': 4},
    {'code': 0, 'did': '1', 'siid': 3, 'piid': 1, 'value': 100},
]


def _cloud(hass):
    init_integration_data(hass)
    return MiotCloud(hass, 'u', 'p', 'cn', 'xiaomiio')


def test_ijai_vacuum_v3_reads_properties_through_rpc():
    assert DEVICE_CUSTOMIZES['ijai.vacuum.v3']['miot_cloud_rpc'] is True


async def test_default_read_uses_cached_prop_get(hass):
    c = _cloud(hass)
    with patch.object(c, 'async_get_props', AsyncMock(return_value=CACHED)) as cached, \
            patch.object(c, 'async_get_props_rpc', AsyncMock(return_value=LIVE)) as rpc:
        result = await c.async_get_properties_for_mapping('1', MAPPING)

    cached.assert_awaited_once()
    rpc.assert_not_awaited()
    assert [r['value'] for r in result] == [3, 99]


async def test_rpc_read_returns_live_values(hass):
    c = _cloud(hass)
    with patch.object(c, 'async_get_props', AsyncMock(return_value=CACHED)) as cached, \
            patch.object(c, 'async_get_props_rpc', AsyncMock(return_value=LIVE)):
        result = await c.async_get_properties_for_mapping('1', MAPPING, use_rpc=True)

    cached.assert_not_awaited()
    assert {r['prop']: r['value'] for r in result} == {'vacuum.status': 4, 'battery_level': 100}


async def test_rpc_read_falls_back_to_cached_values(hass):
    c = _cloud(hass)
    with patch.object(c, 'async_get_props', AsyncMock(return_value=CACHED)) as cached, \
            patch.object(c, 'async_get_props_rpc', AsyncMock(return_value=None)):
        result = await c.async_get_properties_for_mapping('1', MAPPING, use_rpc=True)

    cached.assert_awaited_once()
    assert [r['value'] for r in result] == [3, 99]


async def test_get_props_rpc_calls_the_device_relay(hass):
    c = _cloud(hass)
    response = {'code': 0, 'result': LIVE}
    with patch.object(c, 'async_request_api', AsyncMock(return_value=response)) as request:
        result = await c.async_get_props_rpc('1', [{'did': '1', 'siid': 2, 'piid': 1}])

    assert result == LIVE
    api, data = request.await_args.args
    assert api == 'v2/home/rpc/1'
    assert data['method'] == 'get_properties'


async def test_get_props_rpc_returns_none_on_error_response(hass):
    c = _cloud(hass)
    for response in (None, {}, {'code': -1, 'message': 'offline'}, {'code': 0, 'result': []}):
        with patch.object(c, 'async_request_api', AsyncMock(return_value=response)):
            assert await c.async_get_props_rpc('1', [{'did': '1', 'siid': 2, 'piid': 1}]) is None


async def test_rpc_property_errors_are_filled_from_cached_values(hass):
    c = _cloud(hass)
    partial = [
        {'code': 0, 'did': '1', 'siid': 2, 'piid': 1, 'value': 4},
        {'code': -4001, 'did': '1', 'siid': 3, 'piid': 1},
    ]
    cached = [CACHED[1]]
    with patch.object(c, 'async_get_props', AsyncMock(return_value=cached)) as cached_read, \
            patch.object(c, 'async_get_props_rpc', AsyncMock(return_value=partial)):
        result = await c.async_get_properties_for_mapping('1', MAPPING, use_rpc=True)

    assert cached_read.await_args.args[0] == [{'did': '1', 'siid': 3, 'piid': 1}]
    assert {r['prop']: r['value'] for r in result} == {'vacuum.status': 4, 'battery_level': 99}


async def test_rpc_items_without_a_known_property_use_cached_values(hass):
    c = _cloud(hass)
    odd = [{'did': '1', 'foo': 'bar'}]
    with patch.object(c, 'async_get_props', AsyncMock(return_value=CACHED)), \
            patch.object(c, 'async_get_props_rpc', AsyncMock(return_value=odd)):
        result = await c.async_get_properties_for_mapping('1', MAPPING, use_rpc=True)

    assert {r['prop']: r['value'] for r in result} == {'vacuum.status': 3, 'battery_level': 99}


async def test_complete_rpc_result_does_not_read_the_cache(hass):
    c = _cloud(hass)
    with patch.object(c, 'async_get_props', AsyncMock(return_value=CACHED)) as cached, \
            patch.object(c, 'async_get_props_rpc', AsyncMock(return_value=LIVE)):
        await c.async_get_properties_for_mapping('1', MAPPING, use_rpc=True)

    cached.assert_not_awaited()
