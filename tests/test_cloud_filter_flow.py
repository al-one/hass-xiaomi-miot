"""Tests for saving the cloud filter step."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from custom_components.xiaomi_miot.config_flow import (
    OptionsFlowHandler,
    XiaomiMiotFlowHandler,
)


def _fake_create_entry(*args, **kwargs):
    return {"type": "create_entry", **kwargs}


async def test_config_cloud_filter_empty_submit_creates_entry():
    # A filter form without fields (no devices on the account) submits {}.
    flow = XiaomiMiotFlowHandler.__new__(XiaomiMiotFlowHandler)
    flow.config_data = {"username": "u", "password": "p"}
    flow.filter_models = False
    flow.context = {}
    flow.cloud = SimpleNamespace(to_config=lambda: {"user_id": "123"})
    with patch.object(
        XiaomiMiotFlowHandler,
        "async_create_entry",
        MagicMock(side_effect=_fake_create_entry),
    ):
        result = await flow.async_step_cloud_filter({})

    assert result["type"] == "create_entry"
    assert result["title"] == "Xiaomi: 123"
    assert result["data"]["username"] == "u"


async def test_options_cloud_filter_empty_submit_updates_entry():
    flow = OptionsFlowHandler.__new__(OptionsFlowHandler)
    entry = SimpleNamespace(
        data={"username": "u", "password": "p", "did_list": ["1"]},
        options={},
    )
    update_entry = MagicMock()
    flow.hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_get_known_entry=lambda entry_id: entry,
            async_update_entry=update_entry,
        ),
    )
    flow.handler = "eid"
    flow.context = {}
    flow.config_data = dict(entry.data)
    flow.cloud = SimpleNamespace(to_config=lambda: {"user_id": "123"})
    with patch.object(
        OptionsFlowHandler,
        "async_create_entry",
        MagicMock(side_effect=_fake_create_entry),
    ):
        result = await flow.async_step_cloud_filter({})

    assert result["type"] == "create_entry"
    update_entry.assert_called_once()
    assert update_entry.call_args.kwargs["data"]["user_id"] == "123"
