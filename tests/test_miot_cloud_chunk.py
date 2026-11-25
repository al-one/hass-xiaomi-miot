"""``chunk_coordinators`` entries with ``cloud: True``: an auxiliary chunk polled through the cloud.

Some devices report a property wrongly over LAN (e.g. zhimi.humidifier.ca6 always
reports ``self_clean_percent`` as 0), while the cloud has the right value. Such a
chunk must not take over the main polling nor flip the device availability.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from custom_components.xiaomi_miot.core.xiaomi_cloud import MiCloudException

MODEL = "ykcn.switch.cbcsmj"
CHUNKS = {
    "chunk_coordinators": [
        {"interval": 20, "props": "on"},
        {"interval": 30, "props": "electric_power", "cloud": True},
    ],
}
OUTAGE = MiCloudException("Cloud API returned None response, possible timeout or empty data")


def _device(make_device, load_miot_spec, *cloud_responses):
    device = make_device(load_miot_spec(f"{MODEL}.json"), model=MODEL, customizes=CHUNKS)
    config = {"username": "test-user", "conn_mode": "auto"}
    device.entry.get_config = lambda key=None, default=None: config.get(key, default)
    device.cloud = SimpleNamespace(
        async_get_properties_for_mapping=AsyncMock(side_effect=list(cloud_responses)),
    )
    return device


def _power_mapping(device):
    return {
        k: v for k, v in device.miot_mapping().items()
        if k.startswith("electric_power")
    }


async def test_cloud_chunk_is_auxiliary(make_device, load_miot_spec):
    device = _device(make_device, load_miot_spec)
    coordinators = await device.init_miot_coordinators()
    names = [c.name.rsplit("-", 1)[-1] for c in coordinators]
    main = [c.name.rsplit("-", 1)[-1] for c in device.main_coordinators]

    assert names == ["chunk_1", "chunk_2_cloud", "miot_status"]
    assert main == ["chunk_1"]
    # the cloud chunk's property is not polled again by the local miot_status
    device.update_miot_status = AsyncMock()
    await coordinators[-1].update_method()
    polled = device.update_miot_status.call_args.args[0]
    assert polled and not any(k.startswith("electric_power") for k in polled)


async def test_cloud_chunk_in_local_mode_stays_local(make_device, load_miot_spec):
    device = make_device(load_miot_spec(f"{MODEL}.json"), model=MODEL, customizes=CHUNKS)
    names = [c.name.rsplit("-", 1)[-1] for c in await device.init_miot_coordinators()]
    assert names == ["chunk_1", "chunk_2", "miot_status"]


async def test_cloud_chunk_failures_keep_device_available(make_device, load_miot_spec):
    device = _device(make_device, load_miot_spec, *[OUTAGE] * 5)
    device.dispatch = Mock()
    mapping = _power_mapping(device)

    for _ in range(5):
        result = await device.update_miot_cloud_chunk(mapping)
        assert result.errors is OUTAGE

    assert device.available is True
    assert device._cloud_fails == 0 and device._cloud_state is None
    assert device._cloud_chunk_fails == 5
    device.dispatch.assert_not_called()


async def test_cloud_chunk_success_dispatches_without_changing_updater(make_device, load_miot_spec):
    device = _device(make_device, load_miot_spec)
    mapping = _power_mapping(device)
    (name, prop), = mapping.items()
    device.cloud.async_get_properties_for_mapping.side_effect = [
        [{"did": "test-device", "siid": prop["siid"], "piid": prop["piid"], "code": 0, "value": 12}],
    ]
    device._cloud_chunk_fails = 4
    device.dispatch = Mock()

    result = await device.update_miot_cloud_chunk(mapping)

    assert result.updater == "cloud"
    assert device._cloud_chunk_fails == 0
    assert device.props[name] == 12
    device.dispatch.assert_called_once()
    assert "updater" not in device.data
