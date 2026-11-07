"""Code delivery, CAPTCHA and verification must share one Xiaomi identity session."""
import base64
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from urllib.parse import urlsplit

import pytest
import requests

from custom_components.xiaomi_miot import config_flow
from custom_components.xiaomi_miot.config_flow import OptionsFlowHandler, XiaomiMiotFlowHandler
from custom_components.xiaomi_miot.core.xiaomi_cloud import (
    CloudSid, MiCloudException, MiCloudNeedVerify, MiCloudVerificationError, MiotCloud,
)

VERIFY_URL = "https://account.xiaomi.com/fe/service/identity/authStart?context=example"


def _cloud(hass):
    return MiotCloud(hass, "test-user", "test-password", "cn")


def _response(data=None, cookies=None, content=None):
    return SimpleNamespace(
        text="&&&START&&&" + json.dumps(data or {}),
        cookies=requests.cookies.cookiejar_from_dict(cookies or {}),
        content=content or b"test-image", status_code=200, reason="OK", url="",
    )


def _identity(c, flag=4):
    c.attrs["verify_url"] = VERIFY_URL
    c.account_get = Mock(return_value=_response(
        {"code": 2, "flag": flag, "options": [4, 8]},
        {"identity_session": "test-identity"},
    ))


@pytest.mark.parametrize("flag,method", [(4, "Phone"), (8, "Email")])
async def test_delivery_and_code_retries_keep_the_issued_session(hass, flag, method):
    c = _cloud(hass)
    _identity(c, flag)
    c.account_post = Mock(side_effect=[
        {"code": 0}, {"code": 70014}, {"code": 0, "location": "/identity/result/check"},
    ])
    await hass.async_add_executor_job(c.send_verify_ticket)
    await hass.async_add_executor_job(c.send_verify_ticket)
    with pytest.raises(MiCloudVerificationError):
        await hass.async_add_executor_job(c.verify_ticket, "wrong-code")
    assert c.attrs["identity_session"] == "test-identity"
    await hass.async_add_executor_job(c.verify_ticket, "valid-code")
    c.account_get.assert_called_once_with(
        "https://account.xiaomi.com/identity/list?context=example", response=True,
    )
    calls = c.account_post.call_args_list
    assert [call.args[0] for call in calls] == [
        f"/identity/auth/send{method}Ticket", f"/identity/auth/verify{method}",
        f"/identity/auth/verify{method}",
    ]
    assert {call.kwargs["cookies"]["identity_session"] for call in calls} == {"test-identity"}
    assert not c.attrs


@pytest.mark.parametrize("path", ["/identity/authStart", "/fe/service/identity/authStart"])
async def test_identity_list_accepts_both_official_callback_paths(hass, path):
    c = _cloud(hass)
    _identity(c)
    assert await hass.async_add_executor_job(
        c.check_identity_list, f"https://account.xiaomi.com{path}?context=example",
    ) == [4, 8]
    assert c.attrs["identity_session"] == "test-identity"
    assert c.account_get.call_args.args[0] == "https://account.xiaomi.com/identity/list?context=example"


@pytest.mark.parametrize("url", [
    "http://account.xiaomi.com/identity/authStart", "https://other.example/identity/authStart",
    "https://account.xiaomi.com/unrelated",
])
async def test_identity_list_rejects_unexpected_destinations(hass, url):
    c = _cloud(hass)
    c.account_get = Mock()
    with pytest.raises(MiCloudException):
        await hass.async_add_executor_job(c.check_identity_list, url)
    c.account_get.assert_not_called()


@pytest.mark.parametrize("payload", [{"code": 70022}, {"code": False}, {"code": "0"}, {}, []])
async def test_unsuccessful_delivery_does_not_claim_a_code_was_sent(hass, payload):
    c = _cloud(hass)
    _identity(c)
    c.account_post = Mock(return_value=payload)
    with pytest.raises(MiCloudException):
        await hass.async_add_executor_job(c.send_verify_ticket)
    assert not c.attrs.get("identity_ticket_sent")


@pytest.mark.parametrize("error", [requests.ConnectionError("offline"), None])
async def test_incomplete_send_captcha_can_be_requested_again(hass, error):
    c = _cloud(hass)
    _identity(c)
    c.account_post = Mock(return_value={"code": 87001, "captchaUrl": "/captcha/image"})
    c._get_captcha = Mock(side_effect=error)
    with pytest.raises(MiCloudException, match="captcha"):
        await hass.async_add_executor_job(c.send_verify_ticket)
    assert not c.attrs.get("identity_send_captcha")
    assert not c.attrs.get("identity_ticket_sent")
    assert "captcha_url" not in c.attrs


class _Wire:
    """Synthetic responses; no real account, outbound requests or device controls."""

    def __init__(self, flag, captcha, redirect):
        self.flag, self.captcha, self.redirect = flag, captcha, redirect
        self.calls = []

    def request(self, method, url, **kwargs):
        path = urlsplit(url).path
        data, cookies = kwargs.get("data") or {}, kwargs.get("cookies") or {}
        self.calls.append((path, data.copy(), cookies.copy()))
        channel = "Phone" if self.flag == 4 else "Email"
        if path == "/pass/serviceLoginAuth2":
            return _response({"code": 0, "notificationUrl": VERIFY_URL})
        if path == "/identity/list":
            return _response({"code": 2, "flag": self.flag, "options": [self.flag]},
                             {"identity_session": "test-identity"})
        if path == f"/identity/auth/send{channel}Ticket":
            assert cookies["identity_session"] == "test-identity"
            if self.captcha and data.get("icode") != "captcha-answer":
                return _response({"code": 87001, "captchaUrl": "/captcha/image"})
            if self.captcha:
                assert cookies["ick"] == "test-ick"
            return _response({"code": 0})
        if path == "/captcha/image":
            return _response(cookies={"ick": "test-ick"})
        if path == f"/identity/auth/verify{channel}":
            assert cookies["identity_session"] == "test-identity"
            if data["ticket"] != "valid-code":
                return _response({"code": 70014})
            return _response({"code": 0, "location": "https://account.xiaomi.com/identity/result/check"})
        if path in ("/identity/result/check", "/sts"):
            return _response(cookies={"serviceToken": "test-service", "userId": "test-user"})
        if path == "/pass/serviceLogin":
            data = {"code": 0, "ssecurity": base64.b64encode(b"test-signing-secret").decode()}
            if self.redirect:
                data["location"] = "https://sts.api.io.mi.com/sts"
            return _response(data)
        raise AssertionError(f"Unexpected test request: {path}")


class _Session:
    def __init__(self, wire):
        self.wire, self.headers = wire, {}
        self.cookies = requests.cookies.RequestsCookieJar()

    def request(self, method, url, **kwargs):
        response = self.wire.request(method, url, **kwargs)
        self.cookies.update(response.cookies)
        return response

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)


@pytest.mark.parametrize("flow_cls", [XiaomiMiotFlowHandler, OptionsFlowHandler])
@pytest.mark.parametrize("flag,captcha,redirect", [(4, False, False), (8, False, True),
                                                  (4, True, True), (8, True, False)])
async def test_cloud_flow_completes_after_wrong_code_without_rotating_session(
    hass, monkeypatch, flow_cls, flag, captcha, redirect,
):
    wire = _Wire(flag, captcha, redirect)
    monkeypatch.setattr(requests, "Session", lambda: _Session(wire))
    c = _cloud(hass)
    c.async_stored_auth = AsyncMock(return_value={})
    c.async_get_devices = AsyncMock(return_value=[{"did": "test-plug"}])
    async def check_auth(notify=False):
        return await c.async_login()
    c.async_check_auth = check_auth
    flow = flow_cls.__new__(flow_cls)
    flow.hass, flow.context, flow.cloud = hass, {}, c
    monkeypatch.setattr(config_flow.persistent_notification, "dismiss", Mock())
    def inputs(**extra):
        return {"username": "test-user", "password": "test-password", **extra}
    errors = {}
    await flow.check_xiaomi_account(inputs(), errors)
    assert errors == {"base": "need_identity_captcha" if captcha else "need_verify"}
    if captcha:
        errors = {}
        await flow.check_xiaomi_account(inputs(captcha="captcha-answer"), errors)
        assert errors == {"base": "need_verify"}
        assert "captchaIck" not in flow.context
    assert c.attrs["identity_ticket_sent"]
    errors = {}
    await flow.check_xiaomi_account(inputs(verify_ticket="wrong-code"), errors)
    assert errors == {"base": "verify_invalid"}
    errors = {}
    submitted = inputs(verify_ticket="valid-code")
    await flow.check_xiaomi_account(submitted, errors)
    assert not errors
    assert "verify_ticket" not in submitted
    assert flow.devices == [{"did": "test-plug"}]
    assert c.service_token and c.ssecurity
    assert 'need_verify' not in flow.context
    assert 'verify_url' not in flow.context
    assert sum(path == "/identity/list" for path, _, _ in wire.calls) == 1
    assert sum(path.endswith("Ticket") for path, _, _ in wire.calls) == (2 if captcha else 1)


@pytest.mark.parametrize("changed,missing_url", [(True, False), (False, True)])
async def test_changed_credentials_or_lost_challenge_discard_old_code(hass, changed, missing_url):
    c = _cloud(hass)
    if not missing_url:
        c.attrs["verify_url"] = VERIFY_URL
    c.async_login, c.async_check_auth = AsyncMock(), AsyncMock(return_value=True)
    flow = config_flow.BaseFlowHandler()
    flow.hass, flow.context, flow.cloud = hass, {"need_verify": True}, c
    await flow.get_cloud({"username": "test-user", "password": "new-password" if changed else "test-password",
                          "verify_ticket": "stale-code"})
    c.async_login.assert_not_awaited()
    c.async_check_auth.assert_awaited_once()
    assert "need_verify" not in flow.context


async def test_empty_code_does_not_reset_the_pending_challenge(hass):
    c = _cloud(hass)
    c.attrs["verify_url"] = VERIFY_URL
    c.async_check_auth = AsyncMock()
    flow = config_flow.BaseFlowHandler()
    flow.hass, flow.context, flow.cloud = hass, {"need_verify": True}, c
    with pytest.raises(MiCloudNeedVerify):
        await flow.get_cloud({"username": "test-user", "password": "test-password"})
    c.async_check_auth.assert_not_awaited()


@pytest.mark.parametrize("sid", [CloudSid.XIAOMIIO, CloudSid.MICOAPI])
@pytest.mark.parametrize("captcha", [False, True])
async def test_reauth_delivers_code_once_and_uses_the_same_session(hass, monkeypatch, sid, captcha):
    wire = _Wire(4, captcha, False)
    monkeypatch.setattr(requests, "Session", lambda: _Session(wire))
    c = _cloud(hass)
    c.sid = sid
    c._init_session()
    c.attrs["verify_url"] = VERIFY_URL
    c.user_id = "test-user"
    flow = XiaomiMiotFlowHandler()
    flow.hass, flow.context, flow._candidate = hass, {}, c
    flow._reauth = SimpleNamespace(sid=sid, entry=SimpleNamespace(data={"user_id": "test-user"}))
    flow.async_show_form = Mock(side_effect=lambda **kw: {"type": "form", **kw})
    flow._persist_and_reload = AsyncMock(return_value={"type": "abort", "reason": "reauth_successful"})
    out = await flow.async_step_reauth_verify()
    if captcha:
        assert out["step_id"] == "reauth_captcha"
        out = await flow.async_step_reauth_captcha({"captcha": "captcha-answer"})
    assert out["step_id"] == "reauth_verify"
    assert set(out["description_placeholders"]) == {"tip"}
    await flow.async_step_reauth_verify()
    c.async_stored_auth = AsyncMock(return_value={})
    out = await flow.async_step_reauth_verify({"verify_ticket": "wrong-code"})
    assert out["errors"]["base"] == "verify_invalid"
    out = await flow.async_step_reauth_verify({"verify_ticket": "valid-code"})
    assert out["reason"] == "reauth_successful"
    assert sum(path == "/identity/list" for path, _, _ in wire.calls) == 1
    assert sum(path.endswith("Ticket") for path, _, _ in wire.calls) == (2 if captcha else 1)
    flow._persist_and_reload.assert_awaited_once_with(c)


async def test_new_identity_context_discards_the_previous_issued_code(hass):
    c = _cloud(hass)
    c.attrs.update(verify_url=VERIFY_URL, identity_session="old", identity_options=[4], identity_ticket_sent=True)
    c.account_post = Mock(return_value=_response({"notificationUrl": "/identity/authStart?context=new"}))
    with pytest.raises(MiCloudNeedVerify):
        await hass.async_add_executor_job(c._login_step2)
    assert c.attrs == {"verify_url": "https://account.xiaomi.com/identity/authStart?context=new"}


async def test_auth_request_timeout_and_logs_do_not_expose_payloads(hass, caplog):
    c = _cloud(hass)
    c._init_session()
    c.session.request = Mock(return_value=_response(
        {"code": 0, "ssecurity": "PRIVATE_SIGNING"}, {"serviceToken": "PRIVATE_TOKEN"},
    ))
    caplog.set_level(logging.DEBUG, logger="custom_components.xiaomi_miot.core.xiaomi_cloud")
    await hass.async_add_executor_job(lambda: c.account_post(
        "/identity/auth/verifyPhone?context=PRIVATE_CONTEXT",
        data={"ticket": "PRIVATE_CODE"}, cookies={"identity_session": "PRIVATE_COOKIE"},
    ))
    assert c.session.request.call_args.kwargs["timeout"] == (5, 10)
    assert "PRIVATE_" not in caplog.text


async def test_cached_client_challenges_and_cookies_are_isolated(hass):
    cached = _cloud(hass)
    cached.user_id, cached.service_token = "test-user", "test-service"
    cached.attrs.update(verify_url=VERIFY_URL, identity_session="cached-identity",
                        identity_options=[4], identity_ticket_sent=True)
    cached.cookies['identity_session'] = 'cached-identity'
    hass.data['xiaomi_miot']['sessions'][cached.unique_id] = cached
    clone = await MiotCloud.from_token(
        hass, {'username': 'test-user', 'password': 'test-password', 'server_country': 'cn',
               'user_id': 'test-user', 'service_token': 'test-service'}, login=False,
    )
    clone._clear_identity_challenge()
    clone.cookies['identity_session'] = 'another-identity'
    assert cached.attrs['identity_session'] == 'cached-identity'
    assert cached.attrs['identity_ticket_sent']
    assert cached.cookies['identity_session'] == 'cached-identity'


async def test_delivery_failure_does_not_show_the_code_sent_prompt(hass):
    c = _cloud(hass)
    _identity(c)
    c.account_post = Mock(return_value={'code': 70022})
    c.async_check_auth = AsyncMock(side_effect=MiCloudNeedVerify('need_verify').with_url(VERIFY_URL))
    flow = config_flow.BaseFlowHandler()
    flow.hass, flow.context, flow.cloud = hass, {}, c
    errors = {}
    await flow.check_xiaomi_account({'username': 'test-user', 'password': 'test-password'}, errors)
    assert errors == {'base': 'cannot_send_verify'}
    assert not c.attrs.get('identity_ticket_sent')


@pytest.mark.parametrize("location", [None, "", False])
async def test_incomplete_verification_preserves_challenge_for_retry(hass, location):
    c = _cloud(hass)
    _identity(c, 8)
    c.account_post = Mock(side_effect=[
        {"code": 0}, {"code": 0, "location": location},
        {"code": 0, "location": "/identity/result/check"},
    ])
    await hass.async_add_executor_job(c.send_verify_ticket)
    before = dict(c.attrs)
    with pytest.raises(MiCloudException, match="location"):
        await hass.async_add_executor_job(c.verify_ticket, "valid-code")
    assert c.attrs == before
    await hass.async_add_executor_job(c.send_verify_ticket)
    await hass.async_add_executor_job(c.verify_ticket, "valid-code")
    assert c.account_post.call_count == 3
    c.account_get.assert_called_once()
    assert not c.attrs


async def test_identity_json_error_is_fixed_and_does_not_publish_session(hass):
    c = _cloud(hass)
    c.attrs["verify_url"] = VERIFY_URL
    c.account_get = Mock(return_value=SimpleNamespace(
        text="PRIVATE_RESPONSE not json",
        cookies=requests.cookies.cookiejar_from_dict({"identity_session": "new-session"}),
    ))
    with pytest.raises(MiCloudException, match="identity response unparseable") as caught:
        await hass.async_add_executor_job(c.send_verify_ticket)
    assert "PRIVATE_RESPONSE" not in str(caught.value)
    assert not c.attrs.get("identity_session")
    assert not c.attrs.get("identity_ticket_sent")


@pytest.mark.parametrize("sid", [CloudSid.XIAOMIIO, CloudSid.MICOAPI])
async def test_reauth_incomplete_verification_keeps_candidate_and_sid(hass, sid):
    c = _cloud(hass)
    c.sid = sid
    _identity(c, 8)
    c.account_post = Mock(side_effect=[{"code": 0}, {"code": 0}])
    await hass.async_add_executor_job(c.send_verify_ticket)
    flow = XiaomiMiotFlowHandler()
    flow.hass, flow.context, flow._candidate = hass, {}, c
    flow._reauth = SimpleNamespace(sid=sid)
    flow.async_show_form = Mock(side_effect=lambda **kw: {"type": "form", **kw})
    flow._persist_and_reload = AsyncMock()
    out = await flow.async_step_reauth_verify({"verify_ticket": "valid-code"})
    assert out["step_id"] == "reauth_verify"
    assert out["errors"] == {"base": "unknown"}
    assert flow._candidate is c
    assert c.sid == sid
    assert c.attrs["identity_session"] == "test-identity"
    assert c.attrs["identity_ticket_sent"]
    flow._persist_and_reload.assert_not_awaited()


@pytest.mark.parametrize("sid", [CloudSid.XIAOMIIO, CloudSid.MICOAPI])
async def test_reauth_malformed_identity_list_uses_delivery_error(hass, sid):
    c = _cloud(hass)
    c.sid = sid
    c.attrs["verify_url"] = VERIFY_URL
    c.account_get = Mock(return_value=SimpleNamespace(
        text="not json", cookies=requests.cookies.cookiejar_from_dict({"identity_session": "new-session"}),
    ))
    flow = XiaomiMiotFlowHandler()
    flow.hass, flow.context, flow._candidate = hass, {}, c
    flow._reauth = SimpleNamespace(sid=sid)
    flow.async_show_form = Mock(side_effect=lambda **kw: {"type": "form", **kw})
    out = await flow.async_step_reauth_verify()
    assert out["step_id"] == "reauth_verify"
    assert out["errors"] == {"base": "cannot_send_verify"}
    assert flow._candidate is c
    assert c.sid == sid
    assert not c.attrs.get("identity_ticket_sent")


@pytest.mark.parametrize("flow_cls", [XiaomiMiotFlowHandler, OptionsFlowHandler])
async def test_cloud_form_malformed_identity_list_uses_delivery_error(hass, flow_cls):
    c = _cloud(hass)
    c.attrs["verify_url"] = VERIFY_URL
    c.account_get = Mock(return_value=SimpleNamespace(
        text="not json", cookies=requests.cookies.cookiejar_from_dict({"identity_session": "new-session"}),
    ))
    c.async_check_auth = AsyncMock(side_effect=MiCloudNeedVerify("need_verify").with_url(VERIFY_URL))
    flow = flow_cls.__new__(flow_cls)
    flow.hass, flow.context, flow.cloud = hass, {}, c
    errors = {}
    await flow.check_xiaomi_account({"username": "test-user", "password": "test-password"}, errors)
    assert errors == {"base": "cannot_send_verify"}
    assert not c.attrs.get("identity_ticket_sent")


@pytest.mark.parametrize("flow_cls", [XiaomiMiotFlowHandler, OptionsFlowHandler])
async def test_cloud_form_incomplete_verification_retains_challenge(hass, flow_cls):
    c = _cloud(hass)
    _identity(c, 8)
    c.account_post = Mock(side_effect=[{"code": 0}, {"code": 0}])
    await hass.async_add_executor_job(c.send_verify_ticket)
    flow = flow_cls.__new__(flow_cls)
    flow.hass, flow.context, flow.cloud = hass, {"need_verify": True}, c
    errors = {}
    await flow.check_xiaomi_account({"username": "test-user", "password": "test-password",
                                     "verify_ticket": "valid-code"}, errors)
    assert errors == {"base": "cannot_login"}
    assert c.attrs["identity_session"] == "test-identity"
    assert c.attrs["identity_ticket_sent"]
    assert flow.context["need_verify"]


@pytest.mark.parametrize("payload", [[], {"options": "invalid"}])
async def test_invalid_identity_structure_does_not_publish_session(hass, payload):
    c = _cloud(hass)
    c.attrs["verify_url"] = VERIFY_URL
    c.account_get = Mock(return_value=SimpleNamespace(
        text=json.dumps(payload),
        cookies=requests.cookies.cookiejar_from_dict({"identity_session": "new-session"}),
    ))
    c.account_post = Mock()
    with pytest.raises(MiCloudException):
        await hass.async_add_executor_job(c.send_verify_ticket)
    assert not c.attrs.get("identity_session")
    c.account_post.assert_not_called()
