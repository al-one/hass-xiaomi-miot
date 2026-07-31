from unittest.mock import patch

import pytest
from homeassistant.components.alarm_control_panel.const import AlarmControlPanelState
from homeassistant.components.vacuum.const import VacuumActivity
from homeassistant.core import ServiceResponse, SupportsResponse
from homeassistant.core_config import DATA_CUSTOMIZE

from custom_components.xiaomi_miot import (
    async_setup_component_services,
    bind_services_to_entries,
)
from custom_components.xiaomi_miot.core import const


def test_const_uses_minimum_home_assistant_apis():
    assert const.AlarmControlPanelState is AlarmControlPanelState
    assert const.VacuumActivity is VacuumActivity
    assert const.ServiceResponse is ServiceResponse
    assert const.SupportsResponse is SupportsResponse
    assert const.DATA_CUSTOMIZE is DATA_CUSTOMIZE


def test_platform_services_support_responses(hass):
    services = {
        "test_service": {
            "method": "async_test_method",
        },
    }

    with patch.object(
        type(hass.services), "async_register", autospec=True
    ) as async_register:
        bind_services_to_entries(hass, services)

    assert (
        async_register.call_args.kwargs["supports_response"]
        is SupportsResponse.OPTIONAL
    )


@pytest.mark.asyncio
async def test_get_token_service_supports_responses(hass):
    with patch.object(
        type(hass.services), "async_register", autospec=True
    ) as async_register:
        await async_setup_component_services(hass)

    get_token_call = next(
        call for call in async_register.call_args_list
        if call.args[2] == "get_token"
    )
    assert (
        get_token_call.kwargs["supports_response"]
        is SupportsResponse.OPTIONAL
    )
