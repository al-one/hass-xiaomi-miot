"""Tests for XiaomiMiotFlowHandler reauth scaffolding."""
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.xiaomi_miot.config_flow import XiaomiMiotFlowHandler
from custom_components.xiaomi_miot.core.xiaomi_cloud import (
    CloudSid,
    MiCloudAuthenticationError,
    MiCloudNeedVerify,
    MiCloudStsUnauthorized,
    MiCloudVerificationError,
)


def _fake_show_form(*args, **kwargs):
    return {"type": "form", "flow_id": "fake", **kwargs}


@pytest.fixture
def flow_cls():
    return XiaomiMiotFlowHandler


async def test_reauth_unsupported_sid_aborts(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace()
    flow.context = {"entry_id": "eid"}
    flow.handler = "reauth"
    with patch.object(
        flow_cls,
        "_get_reauth_entry",
        return_value=SimpleNamespace(
            data={"sid": "i.mi.com", "username": "u", "server_country": "cn", "user_id": "u"},
            entry_id="eid",
        ),
    ):
        result = await flow.async_step_reauth({"sid": "i.mi.com"})
    assert result["reason"] == "unsupported_sid"
    placeholders = result.get("description_placeholders") or {}
    assert "i.mi.com" not in placeholders.get("name", "")


async def test_reauth_default_xiaomiio_when_init_data_omits_sid(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace(data={"xiaomi_miot": {}})
    flow.context = {"entry_id": "eid"}
    flow.handler = "reauth"
    fake_entry = SimpleNamespace(
        data={"sid": "i.mi.com", "username": "u", "server_country": "cn", "user_id": "u"},
        entry_id="eid",
    )
    with patch.object(flow_cls, "_get_reauth_entry", return_value=fake_entry), \
         patch.object(
             flow_cls,
             "async_step_reauth_password",
             AsyncMock(return_value={"step_id": "x"}),
         ) as password_step:
        result = await flow.async_step_reauth({})
    password_step.assert_awaited_once_with()
    assert result["step_id"] == "x"
    assert flow._reauth.sid.value == "xiaomiio"


def test_async_remove_is_callback(flow_cls):
    flow = flow_cls()
    assert not inspect.iscoroutinefunction(flow.async_remove)


async def test_async_remove_clears_candidate(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace()
    flow.context = {}
    flow._candidate = SimpleNamespace(
        password="X",
        attrs={"login_data": {}, "verify_url": "x"},
        username="u",
    )
    flow._reauth = SimpleNamespace(sid=None)
    with patch.object(flow_cls.__mro__[1], "async_remove", lambda self: None):
        flow.async_remove()
    assert flow._candidate is None


async def test_reauth_password_invalid_auth_returns_invalid_auth(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace(data={"xiaomi_miot": {}})
    flow.context = {"entry_id": "eid"}
    flow._reauth = SimpleNamespace(
        sid=CloudSid.XIAOMIIO,
        entry=SimpleNamespace(
            data={
                "username": "u",
                "server_country": "cn",
                "user_id": "u",
                "sid": "xiaomiio",
            },
            entry_id="eid",
        ),
    )
    flow.async_show_form = MagicMock(side_effect=_fake_show_form)
    candidate = flow._make_candidate("u", "p", "cn", CloudSid.XIAOMIIO)
    candidate.async_login_attempt = AsyncMock(
        side_effect=MiCloudAuthenticationError("X"),
    )
    flow._make_candidate = MagicMock(return_value=candidate)

    out = await flow.async_step_reauth_password({"password": "p"})

    assert out["errors"]["base"] == "invalid_auth"


async def test_reauth_password_need_verify_routes_to_verify(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace(data={"xiaomi_miot": {}})
    flow.context = {"entry_id": "eid"}
    flow._reauth = SimpleNamespace(
        sid=CloudSid.MICOAPI,
        entry=SimpleNamespace(
            data={
                "username": "u",
                "server_country": "cn",
                "user_id": "u",
                "sid": "micoapi",
            },
            entry_id="eid",
        ),
    )
    candidate = flow._make_candidate("u", "p", "cn", CloudSid.MICOAPI)
    candidate.async_login_attempt = AsyncMock(
        side_effect=MiCloudNeedVerify("need_verify").with_url(
            "https://account.xiaomi.com/v",
        ),
    )
    flow._make_candidate = MagicMock(return_value=candidate)
    flow.async_step_reauth_verify = AsyncMock(
        return_value={"step_id": "reauth_verify"},
    )

    out = await flow.async_step_reauth_password({"password": "p"})

    assert out["step_id"] == "reauth_verify"
    flow.async_step_reauth_verify.assert_awaited_once_with()


async def test_reauth_password_wrong_account_aborts(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace(data={"xiaomi_miot": {}})
    flow.context = {"entry_id": "eid"}
    flow._reauth = SimpleNamespace(
        sid=CloudSid.XIAOMIIO,
        entry=SimpleNamespace(
            data={
                "username": "u",
                "server_country": "cn",
                "user_id": "expected",
                "sid": "xiaomiio",
            },
            entry_id="eid",
        ),
    )
    flow.async_abort = MagicMock(return_value={"reason": "wrong_account"})
    candidate = flow._make_candidate("u", "p", "cn", CloudSid.XIAOMIIO)
    candidate.async_login_attempt = AsyncMock(return_value=True)
    candidate.user_id = "actual"
    flow._make_candidate = MagicMock(return_value=candidate)

    out = await flow.async_step_reauth_password({"password": "p"})

    assert out["reason"] == "wrong_account"
    flow.async_abort.assert_called_once_with(reason="wrong_account")
    assert flow._candidate is None


async def test_reauth_verify_empty_ticket_keeps_form_with_need_verify(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace(data={"xiaomi_miot": {}})
    flow.context = {"entry_id": "eid"}
    flow._reauth = SimpleNamespace(
        sid=CloudSid.XIAOMIIO,
        entry=SimpleNamespace(data={"sid": "xiaomiio"}, entry_id="eid"),
    )
    flow.async_show_form = MagicMock(side_effect=_fake_show_form)
    candidate = SimpleNamespace(
        attrs={"verify_url": "https://account.xiaomi.com/identity/authStart"},
        async_login_attempt=AsyncMock(),
    )
    flow._candidate = candidate

    out = await flow.async_step_reauth_verify({"verify_ticket": ""})

    assert out["errors"]["base"] == "need_verify"
    candidate.async_login_attempt.assert_not_awaited()


async def test_reauth_verify_verification_error_keeps_form(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace(data={"xiaomi_miot": {}})
    flow.context = {"entry_id": "eid"}
    flow._reauth = SimpleNamespace(
        sid=CloudSid.XIAOMIIO,
        entry=SimpleNamespace(data={"sid": "xiaomiio"}, entry_id="eid"),
    )
    flow.async_show_form = MagicMock(side_effect=_fake_show_form)
    candidate = SimpleNamespace(
        attrs={"verify_url": "https://account.xiaomi.com/identity/authStart"},
        async_login_attempt=AsyncMock(side_effect=MiCloudVerificationError("X")),
    )
    flow._candidate = candidate

    out = await flow.async_step_reauth_verify({"verify_ticket": "T"})

    assert out["errors"]["base"] == "need_verify"


async def test_reauth_verify_micoapi_sts_retry_runs_once(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace(data={"xiaomi_miot": {}})
    flow.context = {"entry_id": "eid"}
    flow._reauth = SimpleNamespace(
        sid=CloudSid.MICOAPI,
        entry=SimpleNamespace(data={"sid": "micoapi"}, entry_id="eid"),
    )
    flow.async_show_form = MagicMock(side_effect=_fake_show_form)
    candidate = SimpleNamespace(
        attrs={
            "verify_url": "https://account.xiaomi.com/identity/authStart",
            "service_token": "OLD",
            "ssecurity": "OLD",
            "async_session": object(),
            "identity_session": "OLD",
            "login_data": {"x": 1},
        },
        service_token="OLD",
        ssecurity="OLD",
        async_session=object(),
        user_id=None,
        async_login_attempt=AsyncMock(
            side_effect=[MiCloudStsUnauthorized("X"), True],
        ),
    )
    flow._candidate = candidate
    flow._persist_and_reload = AsyncMock(return_value={"step_id": "ok"})

    out = await flow.async_step_reauth_verify({"verify_ticket": "T"})

    assert out["step_id"] == "ok"
    assert candidate.attrs == {}
    assert candidate.service_token is None
    assert candidate.ssecurity is None
    assert candidate.async_session is None
    assert candidate.async_login_attempt.await_count == 2
    flow._persist_and_reload.assert_awaited_once_with(candidate)


async def test_reauth_verify_micoapi_second_sts_returns_unknown(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace(data={"xiaomi_miot": {}})
    flow.context = {"entry_id": "eid"}
    flow._reauth = SimpleNamespace(
        sid=CloudSid.MICOAPI,
        entry=SimpleNamespace(data={"sid": "micoapi"}, entry_id="eid"),
    )
    flow.async_show_form = MagicMock(side_effect=_fake_show_form)
    candidate = SimpleNamespace(
        attrs={"verify_url": "https://account.xiaomi.com/identity/authStart"},
        service_token="OLD",
        ssecurity="OLD",
        async_session=object(),
        async_login_attempt=AsyncMock(
            side_effect=[
                MiCloudStsUnauthorized("X"),
                MiCloudStsUnauthorized("Y"),
            ],
        ),
    )
    flow._candidate = candidate

    out = await flow.async_step_reauth_verify({"verify_ticket": "T"})

    assert out["errors"]["base"] == "unknown"
    assert candidate.async_login_attempt.await_count == 2


async def test_reauth_captcha_empty_keeps_form(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace(data={"xiaomi_miot": {}})
    flow.context = {"entry_id": "eid"}
    flow._reauth = SimpleNamespace(
        sid=CloudSid.XIAOMIIO,
        entry=SimpleNamespace(data={"sid": "xiaomiio"}, entry_id="eid"),
    )
    flow.async_show_form = MagicMock(side_effect=_fake_show_form)
    candidate = SimpleNamespace(
        attrs={
            "captcha_url": "https://account.xiaomi.com/pass/getCode",
            "captchaImg": "BASE64",
            "captchaIck": "ICK",
        },
        async_login_attempt=AsyncMock(),
    )
    flow._candidate = candidate

    out = await flow.async_step_reauth_captcha({"captcha": ""})

    assert out["errors"]["base"] == "need_captcha"
    candidate.async_login_attempt.assert_not_awaited()


async def test_reauth_captcha_replaced_image_stays_with_need_captcha(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace(data={"xiaomi_miot": {}})
    flow.context = {"entry_id": "eid"}
    flow._reauth = SimpleNamespace(
        sid=CloudSid.XIAOMIIO,
        entry=SimpleNamespace(data={"sid": "xiaomiio"}, entry_id="eid"),
    )
    flow.async_show_form = MagicMock(side_effect=_fake_show_form)
    candidate = SimpleNamespace(
        attrs={
            "captcha_url": "https://account.xiaomi.com/pass/getCode",
            "captchaImg": "NEW",
            "captchaIck": "NEW",
        },
        async_login_attempt=AsyncMock(
            side_effect=MiCloudAuthenticationError("rejected"),
        ),
    )
    flow._candidate = candidate

    out = await flow.async_step_reauth_captcha({"captcha": "ABCD"})

    assert out["errors"]["base"] == "need_captcha"
    assert out["description_placeholders"]["captcha_image"] == "NEW"


async def test_reauth_captcha_auth_error_without_challenge_returns_password(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace(data={"xiaomi_miot": {}})
    flow.context = {"entry_id": "eid"}
    flow._reauth = SimpleNamespace(
        sid=CloudSid.XIAOMIIO,
        entry=SimpleNamespace(data={"sid": "xiaomiio"}, entry_id="eid"),
    )
    flow.async_show_form = MagicMock(side_effect=_fake_show_form)
    candidate = SimpleNamespace(
        attrs={},
        async_login_attempt=AsyncMock(
            side_effect=MiCloudAuthenticationError("creds"),
        ),
    )
    flow._candidate = candidate

    out = await flow.async_step_reauth_captcha({"captcha": "ABCD"})

    assert flow._candidate is None
    assert out["step_id"] == "reauth_password"
    assert out["errors"]["base"] == "invalid_auth"


async def test_persist_xiaomiio_updates_entry_invalidates_and_reloads(flow_cls):
    config_entries = SimpleNamespace(
        async_update_entry=MagicMock(),
        async_schedule_reload=MagicMock(),
    )
    flow = flow_cls()
    flow.hass = SimpleNamespace(
        config_entries=config_entries,
        data={
            "xiaomi_miot": {
                "sessions": {
                    "old": SimpleNamespace(
                        user_id="u",
                        default_server="cn",
                        sid="xiaomiio",
                    ),
                },
                "accounts": {},
            },
        },
    )
    flow.context = {"entry_id": "eid"}
    entry = SimpleNamespace(
        data={
            "sid": "xiaomiio",
            "username": "u",
            "password": "OLD",
            "server_country": "cn",
            "user_id": "u",
            "service_token": "OLD",
            "ssecurity": "OLD",
            "device_id": "old",
        },
        entry_id="eid",
        update_listeners=(),
    )
    flow._reauth = SimpleNamespace(sid=CloudSid.XIAOMIIO, entry=entry)
    flow.async_abort = MagicMock(return_value={"reason": "reauth_successful"})
    candidate = SimpleNamespace(
        attrs={},
        username="u",
        password="NEW",
        sid="xiaomiio",
        default_server="cn",
        user_id="u",
        service_token="NEW",
        ssecurity="NEW",
        client_id="NEW",
        async_stored_auth=AsyncMock(return_value={}),
    )
    flow._candidate = candidate

    out = await flow._persist_and_reload(candidate)

    new_data = config_entries.async_update_entry.call_args.kwargs["data"]
    assert new_data["password"] == "NEW"
    assert new_data["service_token"] == "NEW"
    assert new_data["ssecurity"] == "NEW"
    assert new_data["device_id"] == "NEW"
    assert flow.hass.data["xiaomi_miot"]["sessions"] == {}
    candidate.async_stored_auth.assert_awaited_once_with(save=True)
    config_entries.async_schedule_reload.assert_called_once_with("eid")
    flow.async_abort.assert_called_once_with(reason="reauth_successful")
    assert out["reason"] == "reauth_successful"
    assert flow._candidate is None


async def test_persist_unchanged_with_listeners_skips_reload(flow_cls):
    """When new credentials equal stored credentials and listeners exist,
    async_update_entry must not be called and async_schedule_reload must be skipped
    (listeners are already wired up)."""
    config_entries = SimpleNamespace(
        async_update_entry=MagicMock(),
        async_schedule_reload=MagicMock(),
    )
    flow = flow_cls()
    flow.hass = SimpleNamespace(
        config_entries=config_entries,
        data={"xiaomi_miot": {"sessions": {}, "accounts": {}}},
    )
    flow.context = {"entry_id": "eid"}
    stored = {
        "sid": "xiaomiio",
        "username": "u",
        "password": "SAME",
        "server_country": "cn",
        "user_id": "u",
        "service_token": "SAME",
        "ssecurity": "SAME",
        "device_id": "same",
    }
    entry = SimpleNamespace(
        data=stored,
        entry_id="eid",
        update_listeners=[lambda hass, ent: None],
    )
    flow._reauth = SimpleNamespace(sid=CloudSid.XIAOMIIO, entry=entry)
    flow.async_abort = MagicMock(return_value={"reason": "reauth_successful"})
    candidate = SimpleNamespace(
        attrs={},
        username="u",
        password="SAME",
        sid="xiaomiio",
        default_server="cn",
        user_id="u",
        service_token="SAME",
        ssecurity="SAME",
        client_id="same",
        async_stored_auth=AsyncMock(return_value={}),
    )
    flow._candidate = candidate

    out = await flow._persist_and_reload(candidate)

    config_entries.async_update_entry.assert_not_called()
    config_entries.async_schedule_reload.assert_not_called()
    candidate.async_stored_auth.assert_awaited_once_with(save=True)
    flow.async_abort.assert_called_once_with(reason="reauth_successful")
    assert out["reason"] == "reauth_successful"


async def test_persist_micoapi_does_not_store_micoapi_tokens_in_entry(flow_cls):
    config_entries = SimpleNamespace(
        async_update_entry=MagicMock(),
        async_schedule_reload=MagicMock(),
    )
    flow = flow_cls()
    flow.hass = SimpleNamespace(
        config_entries=config_entries,
        data={"xiaomi_miot": {"sessions": {}, "accounts": {}}},
    )
    flow.context = {"entry_id": "eid"}
    entry = SimpleNamespace(
        data={
            "username": "u",
            "password": "OLD",
            "server_country": "cn",
            "user_id": "u",
            "service_token": "XIAOMIIO_TKN",
            "ssecurity": "XIAOMIIO_SEC",
        },
        entry_id="eid",
        update_listeners=(),
    )
    flow._reauth = SimpleNamespace(sid=CloudSid.MICOAPI, entry=entry)
    flow.async_abort = MagicMock(return_value={"reason": "reauth_successful"})
    candidate = SimpleNamespace(
        attrs={},
        username="u",
        password="NEW",
        sid="micoapi",
        default_server="cn",
        user_id="u",
        service_token="MICO_TKN",
        ssecurity="MICO_SEC",
        client_id="MICO_DEVICE",
        async_stored_auth=AsyncMock(return_value={}),
    )
    flow._candidate = candidate

    await flow._persist_and_reload(candidate)

    new_data = config_entries.async_update_entry.call_args.kwargs["data"]
    assert new_data["password"] == "NEW"
    assert new_data["service_token"] == "XIAOMIIO_TKN"
    assert new_data["ssecurity"] == "XIAOMIIO_SEC"
    assert "MICO_TKN" not in new_data.values()
    assert "MICO_SEC" not in new_data.values()
    candidate.async_stored_auth.assert_awaited_once_with(save=True)


async def test_persist_store_failure_returns_save_failed(flow_cls):
    config_entries = SimpleNamespace(
        async_update_entry=MagicMock(),
        async_schedule_reload=MagicMock(),
    )
    flow = flow_cls()
    flow.hass = SimpleNamespace(
        config_entries=config_entries,
        data={"xiaomi_miot": {"sessions": {}, "accounts": {}}},
    )
    flow.context = {"entry_id": "eid"}
    flow._reauth = SimpleNamespace(
        sid=CloudSid.XIAOMIIO,
        entry=SimpleNamespace(
            data={
                "username": "u",
                "server_country": "cn",
                "user_id": "u",
            },
            entry_id="eid",
            update_listeners=(),
        ),
    )
    flow.async_show_form = MagicMock(side_effect=_fake_show_form)
    candidate = SimpleNamespace(
        attrs={},
        password="NEW",
        username="u",
        user_id="u",
        async_stored_auth=AsyncMock(side_effect=OSError("disk")),
    )
    flow._candidate = candidate

    out = await flow._persist_and_reload(candidate)

    assert out["errors"]["base"] == "save_failed"
    config_entries.async_update_entry.assert_not_called()
    config_entries.async_schedule_reload.assert_not_called()


async def test_reauth_password_form_exposes_only_tip(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace(data={"xiaomi_miot": {}})
    flow.context = {"entry_id": "eid"}
    flow.async_show_form = MagicMock(side_effect=_fake_show_form)

    out = await flow.async_step_reauth_password()

    assert set(out["description_placeholders"]) == {"tip"}


async def test_reauth_verify_form_exposes_only_tip_and_url(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace(data={"xiaomi_miot": {}})
    flow.context = {"entry_id": "eid"}
    flow.async_show_form = MagicMock(side_effect=_fake_show_form)
    flow._candidate = SimpleNamespace(
        attrs={"verify_url": "https://account.xiaomi.com/identity/authStart"},
    )

    out = await flow.async_step_reauth_verify()

    assert set(out["description_placeholders"]) == {"tip", "verify_url"}


async def test_reauth_captcha_form_exposes_only_tip_and_image(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace(data={"xiaomi_miot": {}})
    flow.context = {"entry_id": "eid"}
    flow.async_show_form = MagicMock(side_effect=_fake_show_form)
    flow._candidate = SimpleNamespace(attrs={"captchaImg": "BASE64"})

    out = await flow.async_step_reauth_captcha()

    assert set(out["description_placeholders"]) == {"tip", "captcha_image"}