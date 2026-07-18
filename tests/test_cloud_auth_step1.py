"""Tests for _login_step1 — secret-free logging + network-type preservation."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import requests

from custom_components.xiaomi_miot import init_integration_data
from custom_components.xiaomi_miot.core.xiaomi_cloud import (
    MiCloudException,
    MiotCloud,
)


def _cloud(hass):
    return MiotCloud(hass, "u", "p", "cn", "xiaomiio")


async def test_login_step1_network_error_preserves_type(hass):
    init_integration_data(hass)
    c = _cloud(hass)

    def _boom(*a, **k):
        raise requests.exceptions.ConnectionError("nope")

    c.account_get = _boom
    with pytest.raises(requests.exceptions.ConnectionError):
        await hass.async_add_executor_job(c._login_step1)


async def test_login_step1_timeout_preserves_type(hass):
    init_integration_data(hass)
    c = _cloud(hass)

    def _boom(*a, **k):
        raise requests.exceptions.Timeout("slow")

    c.account_get = _boom
    with pytest.raises(requests.exceptions.Timeout):
        await hass.async_add_executor_job(c._login_step1)


async def test_login_step1_other_exception_becomes_micloud_exception(hass):
    init_integration_data(hass)
    c = _cloud(hass)

    def _boom(*a, **k):
        raise ValueError("bad json")

    c.account_get = _boom
    with pytest.raises(MiCloudException) as exc_info:
        await hass.async_add_executor_job(c._login_step1)
    assert "Xiaomi login sign request failed" in str(exc_info.value)


async def test_login_step1_success_populates_fields(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    auth = {
        "code": 0,
        "userId": "u",
        "cUserId": "cu",
        "ssecurity": "s",
        "passToken": "p",
    }
    c.account_get = lambda *a, **k: auth
    out = await hass.async_add_executor_job(c._login_step1)
    assert out == auth
    assert c.user_id == "u"
    assert c.ssecurity == "s"
    assert c.pass_token == "p"