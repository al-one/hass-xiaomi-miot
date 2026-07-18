"""Tests for the MISS cloud bootstrap adapter and capability cache.

The adapter MUST validate host reachability and address class before
calling `MiotCloud.async_request_api()`. It MUST pass `debug=False`,
`raise_timeout=True`, and a bounded timeout to the existing request
method, and MUST NOT log or cache the DID, host, keys, signature, or
raw response.
"""

from __future__ import annotations

import asyncio
import socket
from time import monotonic
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.xiaomi_miot.core.xiaomi_p2p import MissBootstrap, MissError
from custom_components.xiaomi_miot.core.xiaomi_p2p.cloud import (
    INVALID_HOST_DETAIL,
    P2PCapabilityCache,
    async_miss_get_vendor_impl,
    async_resolve_lan_host,
)


class _StubCloud:
    """Bare `MiotCloud`-like surface with the real `async_miss_get_vendor` bound."""

    def __init__(self) -> None:
        self.user_id = "user-redacted"
        self.default_server = "cn"
        self.sid = "xiaomiio"
        self.async_request_api = AsyncMock(return_value=None)
        self.is_token_expired = lambda data: False
        self.async_check_auth = AsyncMock(return_value=True)

    async def async_miss_get_vendor(self, did: str, host: str, deadline: float):
        return await async_miss_get_vendor_impl(self, did, host, deadline)


@pytest.fixture
def cloud():
    """Return a `_StubCloud` with sane defaults."""

    return _StubCloud()


@pytest.mark.parametrize(
    "host",
    ["", "not a host", "8.8.8.8", "127.0.0.1", "169.254.1.2", "::1", "224.0.0.1"],
)
async def test_invalid_host_stops_before_cloud_or_socket(host, cloud):
    cloud.async_request_api = AsyncMock()
    with pytest.raises(MissError, match=INVALID_HOST_DETAIL):
        await cloud.async_miss_get_vendor("did-redacted", host, monotonic() + 24)
    cloud.async_request_api.assert_not_awaited()


async def test_resolve_numeric_rfc1918_ipv4_skips_dns(monkeypatch):
    def _explode(*args, **kwargs):
        raise AssertionError("DNS must not be used for a numeric IPv4 literal")

    monkeypatch.setattr(
        "custom_components.xiaomi_miot.core.xiaomi_p2p.cloud.socket.getaddrinfo",
        _explode,
    )
    resolved = await async_resolve_lan_host("192.168.1.20")
    assert resolved == "192.168.1.20"


async def test_resolve_dns_picks_single_rfc1918_result(monkeypatch):
    def _fake_getaddrinfo(host, port, *args, **kwargs):
        if host == "single.local":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", port))]
        if host == "ambiguous.local":
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", port)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.5", port)),
            ]
        if host == "public.local":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port))]
        raise AssertionError(host)

    monkeypatch.setattr(
        "custom_components.xiaomi_miot.core.xiaomi_p2p.cloud.socket.getaddrinfo",
        _fake_getaddrinfo,
    )

    assert await async_resolve_lan_host("single.local") == "10.0.0.5"

    for host in ("ambiguous.local", "public.local"):
        with pytest.raises(MissError, match=INVALID_HOST_DETAIL):
            await async_resolve_lan_host(host)


async def test_vendor_adapter_uses_existing_request_path(cloud, monkeypatch):
    cloud.async_request_api = AsyncMock(
        return_value={
            "code": 0,
            "result": {
                "vendor": {"vendor": 4, "vendor_params": {"p2p_id": "peer"}},
                "public_key": "11" * 32,
                "sign": "signature",
            },
        }
    )
    bootstrap = await cloud.async_miss_get_vendor(
        "did-redacted", "192.168.1.20", monotonic() + 24
    )
    assert isinstance(bootstrap, MissBootstrap)
    assert bootstrap.vendor == 4
    assert bootstrap.p2p_id == "peer"
    assert bootstrap.host == "192.168.1.20"
    cloud.async_request_api.assert_awaited_once()
    _, kwargs = cloud.async_request_api.await_args
    assert kwargs["debug"] is False
    assert kwargs["raise_timeout"] is True
    assert 0 < kwargs["timeout"] <= 10
    sent_data = cloud.async_request_api.await_args.args[1]
    assert sent_data["did"] == "did-redacted"
    assert sent_data["support_vendors"] == "TUTK_CS2_MTP"
    assert set(sent_data["app_pubkey"]) <= set("0123456789abcdef")
    assert len(bytes.fromhex(sent_data["app_pubkey"])) == 32


async def test_non_cs2_vendor_does_not_produce_bootstrap(cloud):
    cloud.async_request_api = AsyncMock(
        return_value={
            "code": 0,
            "result": {
                "vendor": {"vendor": 7, "vendor_params": {"p2p_id": "peer"}},
                "public_key": "11" * 32,
                "sign": "signature",
            },
        }
    )
    with pytest.raises(MissError):
        await cloud.async_miss_get_vendor("did-redacted", "10.0.0.5", monotonic() + 24)


async def test_malformed_key_length_rejected(cloud):
    cloud.async_request_api = AsyncMock(
        return_value={
            "code": 0,
            "result": {
                "vendor": {"vendor": 4, "vendor_params": {"p2p_id": "peer"}},
                "public_key": "abcd",
                "sign": "signature",
            },
        }
    )
    with pytest.raises(MissError):
        await cloud.async_miss_get_vendor("did-redacted", "10.0.0.5", monotonic() + 24)


async def test_auth_refresh_retries_once_with_same_keys(cloud):
    expired_payload = {
        "code": 0,
        "result": {
            "vendor": {"vendor": 4, "vendor_params": {"p2p_id": "peer"}},
            "public_key": "11" * 32,
            "sign": "signature",
        },
    }
    cloud.is_token_expired = MagicMock(side_effect=[True, False])
    cloud.async_check_auth = AsyncMock(return_value=True)

    responses = iter(
        [
            {"code": 2, "message": "auth err"},
            expired_payload,
        ]
    )
    cloud.async_request_api = AsyncMock(side_effect=lambda *a, **k: next(responses))

    await cloud.async_miss_get_vendor("did-redacted", "10.0.0.5", monotonic() + 24)

    cloud.async_check_auth.assert_awaited_once()
    assert cloud.async_request_api.await_count == 2
    first_data = cloud.async_request_api.await_args_list[0].args[1]
    second_data = cloud.async_request_api.await_args_list[1].args[1]
    assert first_data["app_pubkey"] == second_data["app_pubkey"]
    assert first_data["did"] == second_data["did"]


async def test_second_auth_failure_terminates_bootstrap(cloud):
    cloud.is_token_expired = MagicMock(return_value=True)
    cloud.async_check_auth = AsyncMock(return_value=True)
    cloud.async_request_api = AsyncMock(
        return_value={"code": 2, "message": "auth err"}
    )
    with pytest.raises(MissError):
        await cloud.async_miss_get_vendor("did-redacted", "10.0.0.5", monotonic() + 24)
    cloud.async_check_auth.assert_awaited_once()
    assert cloud.async_request_api.await_count == 2


async def test_timeout_does_not_retry(cloud):
    cloud.async_request_api = AsyncMock(side_effect=asyncio.TimeoutError())
    with pytest.raises(MissError):
        await cloud.async_miss_get_vendor("did-redacted", "10.0.0.5", monotonic() + 24)
    cloud.async_check_auth.assert_not_awaited()
    assert cloud.async_request_api.await_count == 1


async def test_cancelled_error_propagates_without_adapter_catch(cloud):
    cloud.async_request_api = AsyncMock(side_effect=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await cloud.async_miss_get_vendor("did-redacted", "10.0.0.5", monotonic() + 24)
    cloud.async_check_auth.assert_not_awaited()


async def test_cache_records_only_vendor_integer():
    cache = P2PCapabilityCache()
    probe = AsyncMock(return_value=4)
    assert await cache.get_or_probe("entry", "cn", "did", probe) == 4
    probe.assert_awaited_once()

    assert await cache.get_or_probe("entry", "cn", "did", probe) == 4
    probe.assert_awaited_once()

    cache.invalidate_entry("entry")
    assert await cache.get_or_probe("entry", "cn", "did", probe) == 4
    assert probe.await_count == 2


async def test_cache_does_not_record_failed_probe():
    cache = P2PCapabilityCache()

    async def failing_probe():
        raise MissError("lan_host_unavailable", "host invalid")

    with pytest.raises(MissError):
        await cache.get_or_probe("entry", "cn", "did", failing_probe)
    probe = AsyncMock(return_value=4)
    assert await cache.get_or_probe("entry", "cn", "did", probe) == 4


async def test_cache_separates_entries():
    cache = P2PCapabilityCache()
    probe_a = AsyncMock(return_value=4)
    probe_b = AsyncMock(return_value=4)
    await cache.get_or_probe("entry-a", "cn", "did", probe_a)
    await cache.get_or_probe("entry-b", "cn", "did", probe_b)
    assert probe_a.await_count == 1
    assert probe_b.await_count == 1

    cache.invalidate_entry("entry-a")
    probe_a2 = AsyncMock(return_value=4)
    assert await cache.get_or_probe("entry-a", "cn", "did", probe_a2) == 4
    assert probe_b.await_count == 1
    assert probe_a2.await_count == 1