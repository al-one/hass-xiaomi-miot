"""Tests for _login_step2 — typed rejections + captcha complete-challenge refresh."""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import requests

from custom_components.xiaomi_miot import init_integration_data
from custom_components.xiaomi_miot.core.xiaomi_cloud import (
    MiCloudAuthenticationError,
    MiCloudException,
    MiCloudNeedVerify,
    MiotCloud,
)


class _StubResp:
    def __init__(self, *, json_data=None, status=200):
        self._json_data = json_data
        self.status_code = status
        self.text = json.dumps(json_data) if json_data is not None else ""
        self.cookies = {}

    def json(self):
        return self._json_data


def _step2_cloud(hass):
    c = MiotCloud(hass, "u", "p", "cn", "xiaomiio")
    c._get_captcha = lambda url: bool(
        c.attrs.update({
            "captcha_url": url,
            "captchaImg": "BASE64",
            "captchaIck": "ICK",
        }) or "ICK"
    )
    return c


def _stub_post_factory(payload):
    def _post(url, **kw):
        return _StubResp(json_data=payload)
    return _post


async def test_step2_70002_raises_authentication_error(hass):
    init_integration_data(hass)
    c = _step2_cloud(hass)
    c.account_post = _stub_post_factory({"code": 70002})
    with pytest.raises(MiCloudAuthenticationError):
        await hass.async_add_executor_job(c._login_step2)


async def test_step2_70016_without_captcha_raises_authentication_error(hass):
    init_integration_data(hass)
    c = _step2_cloud(hass)
    c.account_post = _stub_post_factory({"code": 70016})
    with pytest.raises(MiCloudAuthenticationError):
        await hass.async_add_executor_job(c._login_step2)


async def test_step2_initial_captcha_fetches_challenge_first(hass):
    init_integration_data(hass)
    c = _step2_cloud(hass)
    calls = {"captcha": 0}

    def _captcha(url):
        calls["captcha"] += 1
        c.attrs["captcha_url"] = url
        c.attrs["captchaImg"] = "BASE64"
        c.attrs["captchaIck"] = "ICK"
        return "ICK"

    c._get_captcha = _captcha
    c.account_post = _stub_post_factory({
        "code": 70016,
        "captchaUrl": "/captcha.png",
    })
    with pytest.raises(MiCloudException):
        await hass.async_add_executor_job(c._login_step2)
    assert calls["captcha"] == 1
    assert c.attrs.get("captchaIck") == "ICK"


async def test_step2_87001_refreshes_captcha_before_auth_error(hass):
    init_integration_data(hass)
    c = _step2_cloud(hass)
    c.attrs.update({
        "captcha_url": "https://account.xiaomi.com/old.png",
        "captchaImg": "OLD",
        "captchaIck": "OLD",
    })

    def _captcha(url):
        c.attrs["captchaImg"] = "NEW"
        c.attrs["captchaIck"] = "NEW"
        return "NEW"

    c._get_captcha = _captcha
    c.account_post = _stub_post_factory({
        "code": 87001,
        "captchaUrl": "/new.png",
    })
    with pytest.raises(MiCloudAuthenticationError):
        await hass.async_add_executor_job(c._login_step2)
    assert c.attrs["captchaImg"] == "NEW"
    assert c.attrs["captchaIck"] == "NEW"


async def test_step2_87001_captcha_refresh_failure_clears_attrs(hass):
    init_integration_data(hass)
    c = _step2_cloud(hass)

    def _boom(url):
        raise requests.exceptions.ConnectionError("nope")

    c._get_captcha = _boom
    c.account_post = _stub_post_factory({
        "code": 87001,
        "captchaUrl": "/new.png",
    })
    with pytest.raises(MiCloudException):
        await hass.async_add_executor_job(c._login_step2)
    assert "captchaImg" not in c.attrs
    assert "captchaIck" not in c.attrs


async def test_step2_81003_raises_need_verify(hass):
    init_integration_data(hass)
    c = _step2_cloud(hass)
    c.account_post = _stub_post_factory({
        "code": 81003,
        "notificationUrl": "/verify",
    })
    with pytest.raises(MiCloudNeedVerify):
        await hass.async_add_executor_job(c._login_step2)


async def test_step2_unknown_code_raises_micloud_exception(hass):
    init_integration_data(hass)
    c = _step2_cloud(hass)
    c.account_post = _stub_post_factory({"code": 22009})
    with pytest.raises(MiCloudException):
        await hass.async_add_executor_job(c._login_step2)