"""Tests for async_check_auth — owner-aware callback + secret-free logging."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.xiaomi_miot import init_integration_data
from custom_components.xiaomi_miot.core.xiaomi_cloud import (
    CloudSid,
    MiotCloud,
)


def _cloud(hass, sid="xiaomiio", hass_entry=None):
    return MiotCloud(hass, "u", "p", "cn", sid, hass_entry=hass_entry)


async def test_async_check_auth_no_service_token_invokes_relogin(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.service_token = None
    c.user_id = "u"
    c.async_relogin = AsyncMock(return_value=True)
    with patch("homeassistant.components.persistent_notification.dismiss") as nd:
        assert await c.async_check_auth(notify=True) is True
    nd.assert_called_once()


async def test_async_check_auth_ownerless_uses_persistent_notification(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.service_token = "TKN"
    c.user_id = "u"
    c.async_request_api = AsyncMock(return_value={"code": 1, "message": "auth err"})
    c.async_relogin = AsyncMock(return_value=False)
    with patch("homeassistant.components.persistent_notification.create") as nc, \
         patch("homeassistant.components.persistent_notification.dismiss") as nd:
        assert await c.async_check_auth(notify=True) is False
    nc.assert_called_once()
    nd.assert_not_called()


async def test_async_check_auth_owner_bound_invokes_callback(hass):
    init_integration_data(hass)
    c = _cloud(hass, hass_entry=SimpleNamespace())
    c.hass_entry.async_auth_failed = AsyncMock()
    c.service_token = "TKN"
    c.user_id = "u"
    c.async_request_api = AsyncMock(return_value={"code": 1, "message": "auth err"})
    c.async_relogin = AsyncMock(return_value=False)
    with patch("homeassistant.components.persistent_notification.create") as nc:
        assert await c.async_check_auth(notify=True) is False
    nc.assert_not_called()
    c.hass_entry.async_auth_failed.assert_awaited_once_with(CloudSid.XIAOMIIO)


async def test_async_check_auth_relogin_success_ownerless_dismisses_notification(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.service_token = "TKN"
    c.user_id = "u"
    c.async_request_api = AsyncMock(return_value={"code": 1, "message": "auth err"})
    c.async_relogin = AsyncMock(return_value=True)
    with patch("homeassistant.components.persistent_notification.create") as nc, \
         patch("homeassistant.components.persistent_notification.dismiss") as nd:
        assert await c.async_check_auth(notify=True) is True
    nd.assert_called()
    nc.assert_not_called()


async def test_async_check_auth_relogin_success_owner_bound_no_callback(hass):
    init_integration_data(hass)
    c = _cloud(hass, hass_entry=SimpleNamespace())
    c.hass_entry.async_auth_failed = AsyncMock()
    c.service_token = "TKN"
    c.user_id = "u"
    c.async_request_api = AsyncMock(return_value={"code": 1, "message": "auth err"})
    c.async_relogin = AsyncMock(return_value=True)
    with patch("homeassistant.components.persistent_notification.create") as nc, \
         patch("homeassistant.components.persistent_notification.dismiss") as nd:
        assert await c.async_check_auth(notify=True) is True
    nc.assert_not_called()
    c.hass_entry.async_auth_failed.assert_not_awaited()


async def test_async_check_auth_token_ok_returns_true(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.service_token = "TKN"
    c.user_id = "u"
    c.async_request_api = AsyncMock(return_value={"code": 0, "message": "ok"})
    assert await c.async_check_auth(notify=True) is True


async def test_async_check_auth_request_network_error_returns_none(hass):
    import requests
    init_integration_data(hass)
    c = _cloud(hass)
    c.service_token = "TKN"
    c.user_id = "u"
    c.async_request_api = AsyncMock(side_effect=requests.exceptions.ConnectionError("nope"))
    assert await c.async_check_auth(notify=True) is None


async def test_async_check_auth_timeout_returns_none(hass):
    import requests
    init_integration_data(hass)
    c = _cloud(hass)
    c.service_token = "TKN"
    c.user_id = "u"
    c.async_request_api = AsyncMock(side_effect=requests.exceptions.Timeout("slow"))
    assert await c.async_check_auth(notify=True) is None


async def test_async_check_auth_need_verify_owner_bound_invokes_callback(hass):
    from custom_components.xiaomi_miot.core.xiaomi_cloud import MiCloudNeedVerify
    init_integration_data(hass)
    c = _cloud(hass, hass_entry=SimpleNamespace())
    c.hass_entry.async_auth_failed = AsyncMock()
    c.service_token = "TKN"
    c.user_id = "u"
    c.async_request_api = AsyncMock(return_value={"code": 1, "message": "auth err"})

    async def _relogin():
        raise MiCloudNeedVerify("need_verify").with_url("https://account.xiaomi.com/x")

    c.async_relogin = _relogin
    with patch("homeassistant.components.persistent_notification.create") as nc:
        assert await c.async_check_auth(notify=True) is False
    nc.assert_not_called()
    c.hass_entry.async_auth_failed.assert_awaited_once_with(CloudSid.XIAOMIIO)


async def test_async_check_auth_need_verify_ownerless_reraises_when_notify_false(hass):
    from custom_components.xiaomi_miot.core.xiaomi_cloud import MiCloudNeedVerify
    init_integration_data(hass)
    c = _cloud(hass)
    c.service_token = "TKN"
    c.user_id = "u"
    c.async_request_api = AsyncMock(return_value={"code": 1, "message": "auth err"})

    async def _relogin():
        raise MiCloudNeedVerify("need_verify").with_url("https://account.xiaomi.com/x")

    c.async_relogin = _relogin
    with pytest.raises(MiCloudNeedVerify):
        await c.async_check_auth(notify=False)