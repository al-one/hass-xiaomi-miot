"""Tests for verify_ticket — preserves challenge and raises typed outcomes."""
import pytest

from custom_components.xiaomi_miot import init_integration_data
from custom_components.xiaomi_miot.core.xiaomi_cloud import (
    MiCloudException,
    MiCloudVerificationError,
    MiotCloud,
)


def _cloud(hass):
    return MiotCloud(hass, "u", "p", "cn", "xiaomiio")


def _issued_challenge(c, flag=4):
    c.attrs.update(
        verify_url="https://account.xiaomi.com/identity/authStart",
        identity_session="IS", identity_options=[flag],
        identity_verify_flag=flag, identity_ticket_sent=True,
    )


async def test_verify_ticket_missing_url_raises_micloud(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    with pytest.raises(MiCloudException):
        await hass.async_add_executor_job(c.verify_ticket, "TICKET")


async def test_verify_ticket_missing_identity_session_raises_micloud(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.attrs["verify_url"] = "https://account.xiaomi.com/identity/authStart"
    # Verification must not open a new identity session for an existing code.
    with pytest.raises(MiCloudException, match="session expired"):
        await hass.async_add_executor_job(c.verify_ticket, "TICKET")


async def test_verify_ticket_non_zero_each_method_raises_verification(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    _issued_challenge(c)
    c.account_post = lambda *a, **k: {"code": 87001}
    with pytest.raises(MiCloudVerificationError):
        await hass.async_add_executor_job(c.verify_ticket, "TICKET")
    # verify_url preserved so reauth form can retry
    assert c.attrs.get("verify_url") == "https://account.xiaomi.com/identity/authStart"


async def test_verify_ticket_success_returns_data(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    _issued_challenge(c)
    c.account_post = lambda *a, **k: {"code": 0, "location": "/x?userId=1"}
    ret = await hass.async_add_executor_job(c.verify_ticket, "TICKET")
    assert ret.get("code") == 0
    # identity_session cleared on success
    assert "identity_session" not in c.attrs


async def test_verify_ticket_no_supported_method_raises_micloud(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    _issued_challenge(c, flag=99)
    with pytest.raises(MiCloudException):
        await hass.async_add_executor_job(c.verify_ticket, "TICKET")


async def test_verify_ticket_pins_trust_false_and_payload(hass):
    """Pin trust=false (browser-confirmed) and the surrounding payload fields.

    Flipping any of these silently breaks the embedded-callback path that
    7f454747 locked down."""
    init_integration_data(hass)
    c = _cloud(hass)
    _issued_challenge(c)
    captured = {}

    def _capture(*args, **kwargs):
        captured["args"] = args
        captured.update(kwargs)
        return {"code": 0, "location": "/identity/result/check"}

    c.account_post = _capture
    await hass.async_add_executor_job(c.verify_ticket, "TICKET")

    assert captured["args"][0] == "/identity/auth/verifyPhone"
    assert captured["data"]["trust"] == "false"
    assert captured["data"]["ticket"] == "TICKET"
    assert captured["data"]["_flag"] == 4
    assert captured["data"]["_json"] == "true"
    assert captured["cookies"]["identity_session"] == "IS"
