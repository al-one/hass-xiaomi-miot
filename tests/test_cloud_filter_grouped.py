"""Tests for the grouped-by-home device filter schema.

The cloud device filter flow used to present all devices in one flat
multi-select plus a two-step "home_ids" filter. These tests lock in the
new behavior: one multi-select per home (keyed ``home__<home name>``),
no flat ``did_list`` field, no two-step ``home_ids`` field, and the
submit handler merging every ``home__*`` group back into ``did_list``.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, PropertyMock, patch

import voluptuous as vol

from custom_components.xiaomi_miot.config_flow import (
    BaseFlowHandler,
    OptionsFlowHandler,
)


def _mk_devices():
    return [
        {
            "did": "d1",
            "name": "客厅灯",
            "home_id": "100",
            "home_name": "我的家",
            "localip": "192.168.1.2",
            "pid": "0",
        },
        {
            "did": "d2",
            "name": "卧室灯",
            "home_id": "100",
            "home_name": "我的家",
            "localip": "192.168.1.3",
            "pid": "0",
        },
        {
            "did": "d3",
            "name": "餐厅灯",
            "home_id": "200",
            "home_name": "别人的家",
            "localip": "192.168.1.4",
            "pid": "0",
        },
        {
            "did": "d4",
            "name": "附近的设备",
            "home_id": "0",
            "home_name": "",
            "localip": "",
            "pid": "8",
        },
    ]


def _schema_keys(schema):
    return {key.schema for key in schema.schema}


async def test_cloud_filter_schema_groups_devices_by_home():
    flow = BaseFlowHandler.__new__(BaseFlowHandler)
    flow.devices = _mk_devices()
    flow.context = {}

    schema = await flow.get_cloud_filter_schema({}, {}, vol.Schema({}), via_did=True)
    keys = _schema_keys(schema)

    assert "home__我的家" in keys
    assert "home__别人的家" in keys
    assert "home__unassigned" in keys

    # The flat device list and the two-step home_ids filter are gone.
    assert "did_list" not in keys
    assert "home_ids" not in keys


async def test_cloud_filter_schema_keeps_existing_selection():
    flow = BaseFlowHandler.__new__(BaseFlowHandler)
    flow.devices = _mk_devices()
    flow.context = {}

    schema = await flow.get_cloud_filter_schema(
        {"did_list": ["d1"]},
        {},
        vol.Schema({}),
        via_did=True,
    )
    home_key = None
    for key, validator in schema.schema.items():
        if key.schema == "home__我的家":
            home_key = key
    assert home_key is not None
    assert list(home_key.default()) == ["d1"]


async def test_options_cloud_filter_merges_home_groups_into_did_list():
    oflow = OptionsFlowHandler.__new__(OptionsFlowHandler)
    entry = SimpleNamespace(
        data={"username": "u", "password": "p"},
        options={},
    )
    oflow.hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_update_entry=lambda *a, **k: None),
    )
    oflow.config_data = {}
    oflow.context = {}

    class _Cloud:
        def to_config(self):
            return {"username": "u", "password": "p"}

    oflow.cloud = _Cloud()

    with patch.object(
        OptionsFlowHandler,
        "config_entry",
        new_callable=PropertyMock,
        return_value=entry,
    ), patch.object(
        OptionsFlowHandler,
        "async_create_entry",
        AsyncMock(return_value=None),
    ):
        await oflow.async_step_cloud_filter(
            {
                "filter_did": "include",
                "home__我的家": ["d1", "d2"],
                "home__别人的家": ["d3"],
            },
        )

    assert oflow.config_data["did_list"] == ["d1", "d2", "d3"]
    assert oflow.config_data["filter_did"] == "include"
    assert "home__我的家" not in oflow.config_data
    assert "home__别人的家" not in oflow.config_data
