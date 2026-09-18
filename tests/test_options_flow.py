"""Tests for Xiaomi Miot options flow."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from custom_components.xiaomi_miot.config_flow import OptionsFlowHandler


def _fake_show_form(*args, **kwargs):
    return {"type": "form", **kwargs}


async def test_options_cloud_schema_has_no_micoapi_verify():
    flow = OptionsFlowHandler.__new__(OptionsFlowHandler)
    entry = SimpleNamespace(
        data={
            "username": "u",
            "password": "p",
            "server_country": "cn",
        },
        options={},
    )
    flow.hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_get_known_entry=lambda entry_id: entry,
        ),
    )
    flow.handler = "eid"
    flow.context = {}
    with patch.object(
        OptionsFlowHandler,
        "async_show_form",
        MagicMock(side_effect=_fake_show_form),
    ):
        result = await flow.async_step_cloud()

    schema_keys = {key.schema for key in result["data_schema"].schema}
    assert "micoapi_verify" not in schema_keys


def test_options_step_micoapi_is_removed():
    assert not hasattr(OptionsFlowHandler, "async_step_micoapi")
