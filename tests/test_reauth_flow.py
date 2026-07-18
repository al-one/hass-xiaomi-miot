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