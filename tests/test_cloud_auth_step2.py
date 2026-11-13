"""Tests for _login_step2 — typed rejections + captcha complete-challenge refresh."""
import json
from functools import partial
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
        await hass.async_add_executor_job(partial(c._login_step2, _sign="SIGN"))
    assert calls["captcha"] == 1
    assert c.attrs.get("captchaIck") == "ICK"
    assert c.attrs["login_data"] == {"_sign": "SIGN"}


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
        await hass.async_add_executor_job(partial(c._login_step2, _sign="SIGN"))
    assert c.attrs["captchaImg"] == "NEW"
    assert c.attrs["captchaIck"] == "NEW"
    assert c.attrs["login_data"] == {"_sign": "SIGN"}


@pytest.mark.parametrize("error", [requests.exceptions.ConnectionError, requests.exceptions.Timeout])
async def test_step2_87001_captcha_refresh_failure_clears_attrs(hass, error):
    init_integration_data(hass)
    c = _step2_cloud(hass)
    c.attrs["login_data"] = {"_sign": "OLD"}

    def _boom(url):
        raise error("nope")

    c._get_captcha = _boom
    c.account_post = _stub_post_factory({
        "code": 87001,
        "captchaUrl": "/new.png",
    })
    with pytest.raises(MiCloudException):
        await hass.async_add_executor_job(c._login_step2)
    assert "captchaImg" not in c.attrs
    assert "captchaIck" not in c.attrs
    assert "captcha_url" not in c.attrs
    assert "login_data" not in c.attrs


async def test_step2_incomplete_captcha_clears_login_context(hass):
    c = _step2_cloud(hass)
    c.attrs["login_data"] = {"_sign": "OLD"}
    c._get_captcha = lambda url: None
    c.account_post = _stub_post_factory({"code": 87001, "captchaUrl": "/captcha.png"})
    with pytest.raises(MiCloudException, match="challenge incomplete"):
        await hass.async_add_executor_job(partial(c._login_step2, _sign="SIGN"))
    assert c.attrs == {}


@pytest.mark.parametrize("initial_code", [70016, 87001])
async def test_login_captcha_retries_preserve_context_and_replace_cookie(hass, initial_code):
    c = _step2_cloud(hass)
    c._init_session()
    responses = iter([
        {"code": initial_code, "captchaUrl": "/first.png"},
        {"code": 87001, "captchaUrl": "/second.png"},
        {"location": "https://sts.api.io.mi.com/sts", "userId": "u"},
    ])
    posts = []

    def _post(url, **kwargs):
        posts.append(kwargs)
        return _StubResp(json_data=next(responses))

    def _captcha(url):
        c.attrs.update(captchaImg=url, captchaIck=url)

    c.account_post = _post
    c._get_captcha = _captcha
    context = {"_sign": "SIGN", "sid": "xiaomiio", "qs": "QUERY", "callback": "CALLBACK"}
    error = MiCloudAuthenticationError if initial_code == 87001 else MiCloudException
    with pytest.raises(error):
        await hass.async_add_executor_job(partial(c._login_step2, **context))

    session = c.session
    with patch.object(c, "_login_step1") as step1, \
         patch.object(c, "_login_step3", return_value=_StubResp()):
        with pytest.raises(MiCloudAuthenticationError):
            await hass.async_add_executor_job(c._login_request, {"captcha": "wrong"})
        assert await hass.async_add_executor_job(c._login_request, {"captcha": "correct"})
    step1.assert_not_called()
    assert c.session is session
    for post, answer, image in zip(posts[1:], ("wrong", "correct"), ("first", "second")):
        assert post["data"]["captCode"] == answer
        assert post["cookies"]["ick"] == f"https://account.xiaomi.com/{image}.png"
        assert {key: post["data"][key] for key in context} == context


async def test_login_captcha_without_saved_context_forwards_answer(hass):
    c = _step2_cloud(hass)
    c.attrs["captchaIck"] = "ICK"
    with patch.object(c, "_login_step1", return_value={"_sign": "SIGN"}) as step1, \
         patch.object(c, "account_post", return_value=_StubResp(json_data={
             "location": "https://sts.api.io.mi.com/sts", "userId": "u",
         })) as post, \
         patch.object(c, "_login_step3", return_value=_StubResp()):
        assert await hass.async_add_executor_job(c._login_request, {"captcha": "answer"})
    step1.assert_called_once_with()
    assert post.call_args.kwargs["data"]["captCode"] == "answer"
    assert post.call_args.kwargs["data"]["_sign"] == "SIGN"
    assert post.call_args.kwargs["cookies"]["ick"] == "ICK"


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
