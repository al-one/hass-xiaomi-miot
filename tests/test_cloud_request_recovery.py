"""Cancellation and timeout contracts for ordinary cloud requests."""
import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.xiaomi_miot.core.xiaomi_cloud import MiotCloud


@pytest.mark.parametrize("route", ["rc4", "raw", "plain"])
async def test_cancelled_request_propagates(hass, route):
    cloud = MiotCloud(hass, "user", "password", "cn", "xiaomiio")
    cloud.service_token = "test-token"
    cloud.attrs["timeouts"] = 2
    cloud.async_login = AsyncMock()
    cloud._logout = Mock()
    entered = asyncio.Event()
    stopped = asyncio.Event()

    async def pending(*args):
        entered.set()
        try:
            await asyncio.Future()
        finally:
            stopped.set()

    transport = AsyncMock(side_effect=pending)
    if route == "rc4":
        cloud.async_request_rc4_api = transport
    else:
        # Exercise cancellation at the executor await boundary, without starting
        # an uninterruptible synchronous HTTP worker in this lifecycle test.
        hass.async_add_executor_job = transport
    task = asyncio.create_task(cloud.async_request_api(
        "test/endpoint", {}, raw=route == "raw", crypt=route != "plain",
    ))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()
    assert stopped.is_set()
    assert transport.await_count == 1
    cloud.async_login.assert_not_awaited()
    cloud._logout.assert_not_called()
    assert cloud.attrs["timeouts"] == 2


@pytest.mark.parametrize("raise_timeout", [False, True])
async def test_real_timeout_and_next_success(hass, raise_timeout):
    cloud = MiotCloud(hass, "user", "password", "cn", "xiaomiio")
    cloud.service_token = "test-token"
    cloud.async_request_rc4_api = AsyncMock(side_effect=[
        asyncio.TimeoutError(), '{"code": 0, "result": []}',
    ])
    if raise_timeout:
        with pytest.raises(asyncio.TimeoutError):
            await cloud.async_request_api("test/endpoint", {}, raise_timeout=True)
    else:
        assert await cloud.async_request_api("test/endpoint", {}) is None
        assert cloud.attrs["timeouts"] == 1
    assert await cloud.async_request_api("test/endpoint", {}) == {"code": 0, "result": []}
    assert cloud.attrs["timeouts"] == 0
