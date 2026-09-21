from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.xiaomi_miot.core.xiaomi_cloud import MiotCloud


async def test_get_interim_file_falls_back_and_downloads():
    cloud = object.__new__(MiotCloud)
    cloud.hass = object()
    cloud.http_timeout = 15
    cloud.async_request_api = AsyncMock(side_effect=[
        {'code': -8},
        {'result': {'url': 'https://example.test/signed-map'}},
    ])

    response = SimpleNamespace(status=200, read=AsyncMock(return_value=b'map'))
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.get.return_value = context

    with patch(
        'custom_components.xiaomi_miot.core.xiaomi_cloud.async_create_clientsession',
        return_value=session,
    ):
        result = await cloud.async_get_interim_file('user/device/0')

    assert result == b'map'
    assert [call.args[0] for call in cloud.async_request_api.await_args_list] == [
        'v2/home/get_interim_file_url_pro',
        'v2/home/get_interim_file_url',
    ]
    session.get.assert_called_once()
    assert session.get.call_args.args == ('https://example.test/signed-map',)
    response.read.assert_awaited_once_with()
