"""Tests for async_login_attempt / async_login split."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.xiaomi_miot import init_integration_data
from custom_components.xiaomi_miot.core.xiaomi_cloud import MiotCloud


def _cloud(hass):
    c = MiotCloud(hass, "u", "p", "cn", "xiaomiio")
    c._login_request = lambda login_data=None: True
    return c


async def test_async_login_attempt_does_not_register_session(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    with patch.object(c, "async_stored_auth", AsyncMock(return_value={})):
        ret = await c.async_login_attempt()
    assert ret is True
    assert c.unique_id not in hass.data["xiaomi_miot"]["sessions"]


async def test_async_login_ownerless_registers_session(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    with patch.object(c, "async_stored_auth", AsyncMock(return_value={})):
        ret = await c.async_login()
    assert ret is True
    assert hass.data["xiaomi_miot"]["sessions"][c.unique_id] is c


async def test_async_login_owner_bound_skips_session(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.hass_entry = SimpleNamespace()
    with patch.object(c, "async_stored_auth", AsyncMock(return_value={})):
        ret = await c.async_login()
    assert ret is True
    assert c.unique_id not in hass.data["xiaomi_miot"]["sessions"]


async def test_async_login_failure_returns_false(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c._login_request = lambda login_data=None: False
    with patch.object(c, "async_stored_auth", AsyncMock(return_value={})):
        ret = await c.async_login()
    assert ret is False
    assert c.unique_id not in hass.data["xiaomi_miot"]["sessions"]


async def test_too_many_logins_raises_micloud_exception(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.login_times = 11
    from custom_components.xiaomi_miot.core.xiaomi_cloud import MiCloudException
    with patch.object(c, "async_stored_auth", AsyncMock(return_value={})), \
         pytest.raises(MiCloudException):
        await c.async_login_attempt()