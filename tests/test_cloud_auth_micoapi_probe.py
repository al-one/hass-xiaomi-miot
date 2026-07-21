"""Tests for async_check_micoapi_auth — status-aware probe + relogin + owner callback."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import pytest
import requests

from custom_components.xiaomi_miot import init_integration_data
from custom_components.xiaomi_miot.core.xiaomi_cloud import (
    CloudSid,
    MiCloudAuthenticationError,
    MiotCloud,
)


class _FakeAioResp:
    def __init__(self, status, payload=None):
        self.status = status
        self._payload = payload or {}

    async def json(self):
        return self._payload

    async def text(self):
        return json.dumps(self._payload)


def _make_async_session(c):
    class S:
        closed = False

        async def get(self, url, **kw):
            return c._fake_resp

        async def close(self):
            S.closed = True

    return S()


def _cloud(hass, sid="micoapi"):
    c = MiotCloud(hass, "u", "p", "cn", sid)
    c.session = SimpleNamespace(headers={})
    return c


async def test_probe_returns_none_on_network_error(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.service_token = "TKN"

    async def boom(*a, **k):
        raise requests.exceptions.ConnectionError("nope")

    c.async_session = SimpleNamespace(get=boom, closed=False)
    assert await c.async_check_micoapi_auth() is None


async def test_probe_returns_none_on_aiohttp_client_error(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.service_token = "TKN"

    async def boom(*a, **k):
        raise aiohttp.ClientError("boom")

    c.async_session = SimpleNamespace(get=boom, closed=False)
    assert await c.async_check_micoapi_auth() is None


async def test_probe_returns_true_on_200(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.sid = "micoapi"
    c.service_token = "TKN"
    c._fake_resp = _FakeAioResp(200, payload={"result": []})
    c.async_session = _make_async_session(c)
    assert await c.async_check_micoapi_auth() is True


async def test_probe_returns_true_on_200_with_code(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.sid = "micoapi"
    c.service_token = "TKN"
    c._fake_resp = _FakeAioResp(200, payload={"code": 0})
    c.async_session = _make_async_session(c)
    assert await c.async_check_micoapi_auth() is True


async def test_probe_returns_none_on_malformed_200(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.sid = "micoapi"
    c.service_token = "TKN"
    c._fake_resp = _FakeAioResp(200, payload=["unexpected", "list"])
    c.async_session = _make_async_session(c)
    assert await c.async_check_micoapi_auth() is None


async def test_probe_returns_none_on_non_401_status(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.sid = "micoapi"
    c.service_token = "TKN"
    c._fake_resp = _FakeAioResp(500)
    c.async_session = _make_async_session(c)
    assert await c.async_check_micoapi_auth() is None


async def test_probe_401_clears_credentials_and_invokes_owner_callback(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.sid = "micoapi"
    c.service_token = "TKN"
    c.ssecurity = "SEC"
    c.attrs["identity_session"] = "IS"
    c.attrs["verify_url"] = "https://example/x"
    c.attrs["login_data"] = {"a": 1}
    c._fake_resp = _FakeAioResp(401)
    c.async_session = _make_async_session(c)

    cb = AsyncMock()
    c.hass_entry = SimpleNamespace(async_auth_failed=cb)
    c.async_relogin = AsyncMock(side_effect=MiCloudAuthenticationError("X"))

    assert await c.async_check_micoapi_auth() is False
    cb.assert_awaited_once_with(CloudSid.MICOAPI)
    assert c.service_token is None
    assert c.ssecurity is None
    assert c.async_session is None
    assert "identity_session" not in c.attrs
    assert "verify_url" not in c.attrs
    assert "login_data" not in c.attrs


async def test_probe_401_relogin_success_returns_true(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.sid = "micoapi"
    c.service_token = "TKN"
    c._fake_resp = _FakeAioResp(401)
    c.async_session = _make_async_session(c)

    cb = AsyncMock()
    c.hass_entry = SimpleNamespace(async_auth_failed=cb)
    c.async_relogin = AsyncMock(return_value=True)

    assert await c.async_check_micoapi_auth() is True
    cb.assert_not_awaited()
    assert c.service_token is None  # cleared before relogin


async def test_probe_401_relogin_false_with_complete_captcha_invokes_callback(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.sid = "micoapi"
    c.service_token = "TKN"
    c._fake_resp = _FakeAioResp(401)
    c.async_session = _make_async_session(c)

    cb = AsyncMock()
    c.hass_entry = SimpleNamespace(async_auth_failed=cb)
    c.async_relogin = AsyncMock(return_value=False)
    c.attrs.update({
        "captcha_url": "https://account.xiaomi.com/c.png",
        "captchaImg": "BASE64",
        "captchaIck": "ICK",
    })

    assert await c.async_check_micoapi_auth() is False
    cb.assert_awaited_once_with(CloudSid.MICOAPI)


async def test_probe_401_relogin_false_without_complete_captcha_returns_false_without_callback(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.sid = "micoapi"
    c.service_token = "TKN"
    c._fake_resp = _FakeAioResp(401)
    c.async_session = _make_async_session(c)

    cb = AsyncMock()
    c.hass_entry = SimpleNamespace(async_auth_failed=cb)
    c.async_relogin = AsyncMock(return_value=False)

    assert await c.async_check_micoapi_auth() is False
    cb.assert_not_awaited()


async def test_probe_without_service_token_runs_relogin(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.sid = "micoapi"
    c.service_token = None
    cb = AsyncMock()
    c.hass_entry = SimpleNamespace(async_auth_failed=cb)
    c.async_relogin = AsyncMock(return_value=True)

    assert await c.async_check_micoapi_auth() is True
    cb.assert_not_awaited()


async def test_probe_without_service_token_relogin_raises_auth_error(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.sid = "micoapi"
    c.service_token = None
    cb = AsyncMock()
    c.hass_entry = SimpleNamespace(async_auth_failed=cb)
    c.async_relogin = AsyncMock(side_effect=MiCloudAuthenticationError("X"))

    assert await c.async_check_micoapi_auth() is False
    cb.assert_awaited_once_with(CloudSid.MICOAPI)


async def test_probe_without_service_token_relogin_network_error_returns_none(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.sid = "micoapi"
    c.service_token = None
    cb = AsyncMock()
    c.hass_entry = SimpleNamespace(async_auth_failed=cb)
    c.async_relogin = AsyncMock(side_effect=requests.exceptions.ConnectionError("nope"))

    assert await c.async_check_micoapi_auth() is None
    cb.assert_not_awaited()


async def test_probe_401_relogin_raises_generic_micloud_with_complete_captcha(hass):
    init_integration_data(hass)
    from custom_components.xiaomi_miot.core.xiaomi_cloud import MiCloudException
    c = _cloud(hass)
    c.sid = "micoapi"
    c.service_token = "TKN"
    c._fake_resp = _FakeAioResp(401)
    c.async_session = _make_async_session(c)

    cb = AsyncMock()
    c.hass_entry = SimpleNamespace(async_auth_failed=cb)
    c.async_relogin = AsyncMock(side_effect=MiCloudException("requires captcha"))
    c.attrs.update({
        "captcha_url": "https://account.xiaomi.com/c.png",
        "captchaImg": "BASE64",
        "captchaIck": "ICK",
    })

    assert await c.async_check_micoapi_auth() is False
    cb.assert_awaited_once_with(CloudSid.MICOAPI)


async def test_probe_401_relogin_raises_generic_micloud_without_complete_captcha_returns_none(hass):
    init_integration_data(hass)
    from custom_components.xiaomi_miot.core.xiaomi_cloud import MiCloudException
    c = _cloud(hass)
    c.sid = "micoapi"
    c.service_token = "TKN"
    c._fake_resp = _FakeAioResp(401)
    c.async_session = _make_async_session(c)

    cb = AsyncMock()
    c.hass_entry = SimpleNamespace(async_auth_failed=cb)
    c.async_relogin = AsyncMock(side_effect=MiCloudException("requires captcha"))

    assert await c.async_check_micoapi_auth() is None
    cb.assert_not_awaited()


async def test_probe_rejects_non_micoapi_sid(hass):
    init_integration_data(hass)
    c = _cloud(hass, sid="xiaomiio")
    from custom_components.xiaomi_miot.core.xiaomi_cloud import MiCloudException
    with pytest.raises(MiCloudException):
        await c.async_check_micoapi_auth()