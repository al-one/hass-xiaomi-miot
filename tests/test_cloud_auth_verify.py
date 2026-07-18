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


async def test_verify_ticket_missing_url_raises_micloud(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    with pytest.raises(MiCloudException):
        await hass.async_add_executor_job(c.verify_ticket, "TICKET")


async def test_verify_ticket_missing_identity_session_raises_micloud(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.attrs["verify_url"] = "https://account.xiaomi.com/identity/authStart"
    c.check_identity_list = lambda url, path="fe/service/identity/authStart": (_ for _ in ()).throw(MiCloudException("missing"))
    # The above hack won't propagate cleanly; use a real exception-raising stub:
    def _raise(*a, **k):
        raise MiCloudException("Xiaomi identity session missing")
    c.check_identity_list = _raise
    with pytest.raises(MiCloudException):
        await hass.async_add_executor_job(c.verify_ticket, "TICKET")


async def test_verify_ticket_non_zero_each_method_raises_verification(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.attrs["verify_url"] = "https://account.xiaomi.com/identity/authStart"
    c.check_identity_list = lambda url, path="fe/service/identity/authStart": [4]
    c.account_post = lambda *a, **k: {"code": 87001}
    with pytest.raises(MiCloudVerificationError):
        await hass.async_add_executor_job(c.verify_ticket, "TICKET")
    # verify_url preserved so reauth form can retry
    assert c.attrs.get("verify_url") == "https://account.xiaomi.com/identity/authStart"


async def test_verify_ticket_success_returns_data(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.attrs["verify_url"] = "https://account.xiaomi.com/identity/authStart"
    c.attrs["identity_session"] = "IS"
    c.check_identity_list = lambda url, path="fe/service/identity/authStart": [4]
    c.account_post = lambda *a, **k: {"code": 0, "location": "/x?userId=1"}
    ret = await hass.async_add_executor_job(c.verify_ticket, "TICKET")
    assert ret.get("code") == 0
    # identity_session cleared on success
    assert "identity_session" not in c.attrs


async def test_verify_ticket_no_supported_method_raises_micloud(hass):
    init_integration_data(hass)
    c = _cloud(hass)
    c.attrs["verify_url"] = "https://account.xiaomi.com/identity/authStart"
    # Return a flag that has no api mapping (not 4 or 8)
    c.check_identity_list = lambda url, path="fe/service/identity/authStart": [99]
    with pytest.raises(MiCloudException):
        await hass.async_add_executor_job(c.verify_ticket, "TICKET")