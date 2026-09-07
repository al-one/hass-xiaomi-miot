from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.xiaomi_miot import sensor as sensor_module
from custom_components.xiaomi_miot.sensor import XiaoaiConversationSensor


@pytest.mark.parametrize('response_data', [None, []])
async def test_invalid_response_data_keeps_last_conversation(monkeypatch, response_data):
    class FakeMiotCloud:
        async_request_api = AsyncMock(return_value={'data': response_data})

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
    sensor._state_attrs = previous.copy()
    sensor.conversation = {'query': previous['content']}

    result = await sensor.fetch_latest_message()

    assert result == {}
    assert sensor._attr_native_value == previous['content']
    assert sensor._state_attrs == previous
    assert sensor.conversation == {'query': previous['content']}
