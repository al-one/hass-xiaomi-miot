"""Tests for async_login_attempt / async_login split."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.xiaomi_miot import init_integration_data
from custom_components.xiaomi_miot.core.xiaomi_cloud import MiotCloud


class _FakeCookies(dict):
    def get_dict(self):
        return dict(self)


class _FakeResponse:
    def __init__(self, text="", cookies=None, status_code=200, reason="OK", url=""):
        self.text = text
        self.cookies = _FakeCookies(cookies or {})
        self.status_code = status_code
        self.reason = reason
        self.url = url


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


async def test_login_verify_fe_skip_url_returns_success(hass):
    init_integration_data(hass)
    c = MiotCloud(hass, "u", "p", "cn", "xiaomiio")
    c.verify_ticket = lambda ticket: {"code": 0, "location": "/identity/result/check?id=1"}
    c._login_step1 = lambda: (_ for _ in ()).throw(AssertionError("_login_step1 should not run"))
    c.session = SimpleNamespace(headers={})

    fe_response = _FakeResponse(
        text="<html><body>skip via query only</body></html>",
        url=(
            "https://account.xiaomi.com/fe/service/verifyEmail?foo=1"
            "&skipUrl=https%3A%2F%2Faccount.xiaomi.com%2Fpass2%2FconfirmPhone"
            "%3Fselected%3D0%26phoneRecycleStatus%3D1%26scene%3D1%26userId%3D1"
        ),
    )
    skipped_response = _FakeResponse(
        cookies={"serviceToken": "TOKEN", "userId": "1"},
        url="https://sts.api.io.mi.com/sts",
    )
    calls = []

    def _account_get(url, method="GET", **kwargs):
        calls.append((url, kwargs))
        if url == "/identity/result/check?id=1":
            assert kwargs.get("allow_redirects") is True
            assert kwargs.get("response") is True
            return fe_response
        if url == (
            "https://account.xiaomi.com/pass2/confirmPhone"
            "?selected=0&phoneRecycleStatus=1&scene=1&userId=1"
        ):
            assert kwargs.get("allow_redirects") is True
            assert kwargs.get("response") is True
            return skipped_response
        raise AssertionError(f"unexpected url: {url}")

    c.account_get = _account_get

    ret = await hass.async_add_executor_job(
        c._login_request,
        {"verify_ticket": "TICKET"},
    )

    assert ret is True
    assert c.service_token == "TOKEN"
    assert c.user_id == "1"
    assert [u for u, _ in calls] == [
        "/identity/result/check?id=1",
        "https://account.xiaomi.com/pass2/confirmPhone?selected=0&phoneRecycleStatus=1&scene=1&userId=1",
    ]


async def test_extract_fe_skip_url_ignores_html_only_value(hass):
    init_integration_data(hass)
    c = MiotCloud(hass, "u", "p", "cn", "xiaomiio")
    response = _FakeResponse(
        text=(
            '<script>var skipUrl = '
            '"https://account.xiaomi.com/pass2/confirmPhone?selected=0&amp;phoneRecycleStatus=1&amp;scene=1&amp;phone=17621167621&amp;userId=143050915";'
            '</script>'
        ),
        url="https://account.xiaomi.com/fe/service/verifyPhone?bizType=ConfirmPhone",
    )

    skip_url = c._extract_confirm_phone_skip_url(response)

    assert skip_url is None


async def test_extract_fe_skip_url_from_body_text_returns_none(hass):
    init_integration_data(hass)
    c = MiotCloud(hass, "u", "p", "cn", "xiaomiio")
    response = _FakeResponse(
        text=(
            'skipUrl=https://account.xiaomi.com/pass2/confirmPhone?selected=0&'
            'phoneRecycleStatus=1&scene=1&phone=17621167621&userId=143050915'
        ),
        url="https://account.xiaomi.com/fe/service/verifyPhone?foo=1",
    )

    skip_url = c._extract_confirm_phone_skip_url(response)

    assert skip_url is None


async def test_extract_fe_skip_url_requires_fe_path(hass):
    init_integration_data(hass)
    c = MiotCloud(hass, "u", "p", "cn", "xiaomiio")
    response = _FakeResponse(
        url=(
            "https://account.xiaomi.com/pass/serviceLogin?skipUrl="
            "https%3A%2F%2Faccount.xiaomi.com%2Fpass2%2FconfirmPhone%3Fselected%3D0%26userId%3D1"
        ),
    )

    skip_url = c._extract_confirm_phone_skip_url(response)

    assert skip_url is None


async def test_extract_fe_skip_url_keeps_full_query(hass):
    init_integration_data(hass)
    c = MiotCloud(hass, "u", "p", "cn", "xiaomiio")
    response = _FakeResponse(
        url=(
            "https://account.xiaomi.com/fe/service/verifyPhone?foo=1"
            "&skipUrl=https%3A%2F%2Faccount.xiaomi.com%2Fpass2%2FconfirmPhone"
            "%3Fselected%3D0%26phoneRecycleStatus%3D1%26scene%3D1%26phone%3D17621167621%26userId%3D143050915"
        ),
    )

    skip_url = c._extract_confirm_phone_skip_url(response)

    assert skip_url == (
        "https://account.xiaomi.com/pass2/confirmPhone"
        "?selected=0&phoneRecycleStatus=1&scene=1&phone=17621167621&userId=143050915"
    )