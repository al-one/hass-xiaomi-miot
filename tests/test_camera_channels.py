import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from custom_components.xiaomi_miot.camera import BaseCameraEntity


def test_alarm_eventlist_groups_latest_event_by_channel():
    events = [
        {'channel': 10, 'createTime': 3000, 'fileId': 'lower-new'},
        {'channel': 0, 'createTime': 2000, 'fileId': 'main-new'},
        {'channel': 10, 'createTime': 1000, 'fileId': 'lower-old'},
    ]
    cloud = SimpleNamespace(
        default_server='cn',
        get_api_by_host=lambda host, path: f'https://{host}/{path}',
        async_request_api=AsyncMock(return_value={
            'data': {'thirdPartPlayUnits': events},
        }),
    )
    entity = object.__new__(BaseCameraEntity)
    entity.device = SimpleNamespace(cloud=cloud, did='test-device')
    entity._attr_model = 'midr.cateye.sd400'

    result = asyncio.run(
        entity.get_alarm_eventlist(
            0,
            doorbell=True,
            limit=10,
            include_channels=True,
        )
    )

    channels = result.pop('_motion_video_channels')
    assert result['motion_video_latest']['fileId'] == 'lower-new'
    assert channels['0']['motion_video_latest']['fileId'] == 'main-new'
    assert channels['10']['motion_video_latest']['fileId'] == 'lower-new'
    assert events[0]['createTime'] == 3000
