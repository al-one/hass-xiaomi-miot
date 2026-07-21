"""Tests for _login_step3 — narrow micoapi STS-401 to MiCloudStsUnauthorized and missing serviceToken to MiCloudAuthenticationError."""
from types import SimpleNamespace

import pytest

from custom_components.xiaomi_miot import init_integration_data
from custom_components.xiaomi_miot.core.xiaomi_cloud import (
    MiCloudAuthenticationError,
    MiCloudStsUnauthorized,
    MiotCloud,
)


class _CapturingTextResp:
    def __init__(self, status_code, cookies=None, text=""):
        self.status_code = status_code
        self.cookies = SimpleNamespace(
            get=lambda k, default=None: (cookies or {}).get(k, default),
            get_dict=lambda: cookies or {},
        )
        self.text = text
        self.headers = {}
        self.request = SimpleNamespace(headers={}, method="GET", url="", body=None)
        self.reason = ""


def _cloud(hass):
    c = MiotCloud(hass, "u", "p", "cn", "xiaomiio")
    c.session = SimpleNamespace(headers={})
    return c


async def test_step3_micoapi_sts_401_raises_sts_unauthorized(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.sid = "micoapi"
    resp = _CapturingTextResp(401, text="")
    c.account_get = lambda *a, **k: resp
    with pytest.raises(MiCloudStsUnauthorized):
        await hass.async_add_executor_job(
            c._login_step3, "https://api2.mina.mi.com/sts"
        )


async def test_step3_xiaomiio_401_raises_authentication_error(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.sid = "xiaomiio"
    resp = _CapturingTextResp(401, text="")
    c.account_get = lambda *a, **k: resp
    with pytest.raises(MiCloudAuthenticationError):
        await hass.async_add_executor_job(
            c._login_step3, "https://account.xiaomi.com/oauth"
        )


async def test_step3_micoapi_non_sts_401_raises_authentication_error(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.sid = "micoapi"
    resp = _CapturingTextResp(401, text="")
    c.account_get = lambda *a, **k: resp
    with pytest.raises(MiCloudAuthenticationError):
        await hass.async_add_executor_job(
            c._login_step3, "https://account.xiaomi.com/oauth2/token"
        )


async def test_step3_html_login_page_raises_authentication_error(hass):
    """Xiaomi /fe/service/login returns HTML for invalidated sessions; step3 must reject as auth failure, not a bare MiCloudException."""
    init_integration_data(hass)
    c = _cloud(hass)
    c.sid = "xiaomiio"
    resp = _CapturingTextResp(200, text="<!doctype html><html>...</html>")
    c.account_get = lambda *a, **k: resp
    with pytest.raises(MiCloudAuthenticationError):
        await hass.async_add_executor_job(
            c._login_step3, "https://account.xiaomi.com/fe/service/login"
        )


async def test_step3_with_service_token_returns_response(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.sid = "micoapi"
    resp = _CapturingTextResp(200, cookies={"serviceToken": "TKN"}, text="")
    c.account_get = lambda *a, **k: resp
    out = c._login_step3("https://api2.mina.mi.com/sts")
    assert c.service_token == "TKN"
    assert out is resp