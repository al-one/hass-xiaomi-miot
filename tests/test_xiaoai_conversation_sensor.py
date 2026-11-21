from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.xiaomi_miot import sensor as sensor_module
from custom_components.xiaomi_miot.sensor import XiaoaiConversationSensor


@pytest.mark.parametrize(
    ('response_data', 'request_error'),
    [
        (None, None),
        ([], None),
        ('null', None),
        ('[]', None),
        ('{', None),
        (None, OSError('request failed')),
    ],
    ids=['null', 'list', 'json-null', 'json-list', 'invalid-json', 'request-error'],
)
async def test_failed_poll_keeps_last_conversation_and_recovers(
    monkeypatch, response_data, request_error,
):
    class FakeMiotCloud:
        async_request_api = AsyncMock(
            side_effect=[
                request_error if request_error is not None else {'data': response_data},
                {'data': '{"records": [{"query": "turn on the light"}]}'},
            ],
        )

    monkeypatch.setattr(sensor_module, 'MiotCloud', FakeMiotCloud)
    previous = {
        'content': 'turn off the computer',
        'answers': [],
        'history': [],
        'timestamp': None,
    }
    sensor = XiaoaiConversationSensor.__new__(XiaoaiConversationSensor)
    sensor._parent = SimpleNamespace(
        xiaoai_cloud=FakeMiotCloud(),
        xiaoai_device={'deviceID': 'test-device', 'hardware': 'test-hardware'},
        device_name='Test Speaker',
    )
    sensor._model = 'test.speaker'
    sensor._available = True
    sensor._attr_native_value = previous['content']
    sensor._state = previous['content']
    sensor._state_attrs = previous.copy()
    sensor.conversation = {'query': previous['content']}

    result = await sensor.fetch_latest_message()

    assert result == {}
    assert sensor._attr_native_value == previous['content']
    assert sensor._state == previous['content']
    assert sensor._state_attrs == previous
    assert sensor.conversation == {'query': previous['content']}

    result = await sensor.fetch_latest_message()

    assert result == sensor.conversation == {'query': 'turn on the light'}
    assert sensor._attr_native_value == sensor._state == 'turn on the light'
    assert sensor._state_attrs['content'] == 'turn on the light'
