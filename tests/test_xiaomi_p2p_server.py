from __future__ import annotations

import asyncio
import base64
import socket
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import aiohttp
import pytest
from aiohttp import web

from custom_components.xiaomi_miot.core.xiaomi_p2p import (
    MissError,
    MissErrorCategory,
)
from custom_components.xiaomi_miot.core.xiaomi_p2p.server import (
    LoopbackMediaServer,
    PortLease,
    RtpPortAllocator,
)


pytestmark = pytest.mark.enable_socket


@pytest.fixture(autouse=True)
def enable_test_sockets(socket_enabled):
    yield


@pytest.fixture
async def server():
    instance = LoopbackMediaServer()
    await instance.acquire_entry()
    yield instance
    await instance.release_entry()


async def test_route_auth_binding_and_redaction(server, monkeypatch):
    monkeypatch.setattr(
        "custom_components.xiaomi_miot.core.xiaomi_p2p.server.secrets.token_bytes",
        lambda size: b"r" * size,
    )
    monkeypatch.setattr(
        "custom_components.xiaomi_miot.core.xiaomi_p2p.server.secrets.token_urlsafe",
        lambda size: "token-value",
    )
    route = server.add_route(
        lambda _request: asyncio.sleep(0, result=web.Response(text="ok"))
    )

    route_bytes = base64.urlsafe_b64decode(route.route_id + "==")
    parsed = urlsplit(route.url)
    assert route_bytes == b"r" * 16
    assert parsed.hostname == "127.0.0.1"
    assert server._runner.addresses == [("127.0.0.1", parsed.port)]
    assert len(list(server._runner.app.router.resources())) == 1
    assert server._runner._kwargs["access_log"] is None
    assert parse_qs(parsed.query) == {"auth": ["token-value"]}
    assert "token-value" not in repr(route)

    async with aiohttp.ClientSession() as client:
        unauthenticated_url = parsed._replace(query="").geturl()
        assert (await client.get(unauthenticated_url)).status == 404
        response = await client.get(route.url)
        assert response.status == 200
        assert await response.text() == "ok"


async def test_route_ids_are_opaque_unique_and_url_safe(server, monkeypatch):
    entropy = iter([b"a" * 16, b"b" * 16])
    monkeypatch.setattr(
        "custom_components.xiaomi_miot.core.xiaomi_p2p.server.secrets.token_bytes",
        lambda size: next(entropy),
    )
    monkeypatch.setattr(
        "custom_components.xiaomi_miot.core.xiaomi_p2p.server.secrets.token_urlsafe",
        lambda size: "route-token",
    )
    first = server.add_route(lambda _request: asyncio.sleep(0))
    second = server.add_route(lambda _request: asyncio.sleep(0))

    assert first.route_id != second.route_id
    assert len(base64.urlsafe_b64decode(first.route_id + "==")) == 16
    assert all(value not in first.route_id for value in ("did", "model", "lens"))


async def test_unknown_invalid_and_removed_routes_return_404(server):
    route = server.add_route(
        lambda _request: asyncio.sleep(0, result=web.Response(text="ok"))
    )
    parsed = urlsplit(route.url)
    invalid_url = parsed._replace(query="auth=invalid").geturl()
    unknown_url = parsed._replace(path="/xiaomi_miot/p2p/unknown").geturl()

    async with aiohttp.ClientSession() as client:
        assert (await client.get(invalid_url)).status == 404
        unicode_url = parsed._replace(query="auth=%C3%A9").geturl()
        assert (await client.get(unicode_url)).status == 404
        assert (await client.get(unknown_url)).status == 404
        server.remove_route(route.route_id)
        assert (await client.get(route.url)).status == 404


async def test_active_source_limit_maps_to_503(server):
    async def reject(_request):
        raise MissError(MissErrorCategory.MEDIA, "active_source_limit")

    route = server.add_route(reject)

    async with aiohttp.ClientSession() as client:
        response = await client.get(route.url)

    assert response.status == 503
    assert response.headers["Retry-After"] == "5"


async def test_forced_handler_exception_is_sanitized(server, caplog):
    async def fail(_request):
        raise RuntimeError("secret-token route payload")

    route = server.add_route(fail)

    async with aiohttp.ClientSession() as client:
        response = await client.get(route.url)
        body = await response.text()

    assert response.status == 502
    assert "secret-token" not in body
    assert "payload" not in body
    assert "secret-token" not in caplog.text
    assert route.route_id not in caplog.text


async def test_bridge_failure_waits_for_close_and_preserves_exception(server):
    started = asyncio.Event()
    close_future = asyncio.get_running_loop().create_future()

    class FailingBridge:
        async def run(self, _request):
            started.set()
            raise RuntimeError("bridge failed")

    bridge = FailingBridge()
    bridge.close_future = close_future
    task = asyncio.create_task(server._run_bridge(bridge, None))
    await started.wait()
    await asyncio.sleep(0)
    assert not task.done()

    close_future.set_result(SimpleNamespace(reason="failed"))
    with pytest.raises(RuntimeError, match="bridge failed"):
        await task


async def test_bridge_cancellation_waits_for_close_future(server):
    close_future = asyncio.get_running_loop().create_future()
    running = asyncio.Event()

    class BlockingBridge:
        async def run(self, _request):
            running.set()
            await asyncio.Future()

    bridge = BlockingBridge()
    bridge.close_future = close_future
    task = asyncio.create_task(server._run_bridge(bridge, None))
    await running.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    assert not close_future.cancelled()

    close_future.set_exception(RuntimeError("cleanup failed"))
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_bridge_handoff_awaits_shielded_close_future(server):
    started = asyncio.Event()
    close_future = asyncio.get_running_loop().create_future()

    class FakeBridge:
        async def run(self, _request):
            started.set()
            return web.Response(text="stream")

    bridge = FakeBridge()
    bridge.close_future = close_future
    route = server.add_route(lambda _request: asyncio.sleep(0, result=bridge))

    async with aiohttp.ClientSession() as client:
        request_task = asyncio.create_task(client.get(route.url))
        await started.wait()
        await asyncio.sleep(0)
        assert not request_task.done()
        close_future.set_result(SimpleNamespace(reason="complete"))
        response = await request_task
        assert response.status == 200
        assert await response.text() == "stream"


async def test_final_shutdown_attempts_runner_cleanup_after_site_failure():
    calls = []

    class FailingSite:
        async def stop(self):
            calls.append("site")
            raise RuntimeError("site stop failed")

    class Runner:
        async def cleanup(self):
            calls.append("runner")

    server = LoopbackMediaServer()
    server._entry_references = 1
    server._site = FailingSite()
    server._runner = Runner()
    server._port = 1234

    with pytest.raises(RuntimeError, match="site stop failed"):
        await server.release_entry()

    assert calls == ["site", "runner"]
    assert server._site is None
    assert server._runner is None
    assert server._port is None


async def test_final_shutdown_is_shielded_from_caller_cancellation():
    cleanup_started = asyncio.Event()
    finish_cleanup = asyncio.Event()

    class Site:
        async def stop(self):
            pass

    class Runner:
        async def cleanup(self):
            cleanup_started.set()
            await finish_cleanup.wait()

    server = LoopbackMediaServer()
    server._entry_references = 1
    server._site = Site()
    server._runner = Runner()
    server._port = 1234
    release_task = asyncio.create_task(server.release_entry())
    await cleanup_started.wait()

    release_task.cancel()
    await asyncio.sleep(0)
    assert not release_task.done()
    finish_cleanup.set()

    with pytest.raises(asyncio.CancelledError):
        await release_task
    assert server._site is None
    assert server._runner is None
    assert server._port is None


async def test_final_shutdown_re_raises_cancellation_over_cleanup_failure():
    cleanup_started = asyncio.Event()
    finish_cleanup = asyncio.Event()

    class Site:
        async def stop(self):
            pass

    class Runner:
        async def cleanup(self):
            cleanup_started.set()
            await finish_cleanup.wait()
            raise RuntimeError("cleanup failed")

    server = LoopbackMediaServer()
    server._entry_references = 1
    server._site = Site()
    server._runner = Runner()
    server._port = 1234
    release_task = asyncio.create_task(server.release_entry())
    await cleanup_started.wait()

    release_task.cancel()
    await asyncio.sleep(0)
    finish_cleanup.set()

    with pytest.raises(asyncio.CancelledError):
        await release_task
    assert server._site is None
    assert server._runner is None


async def test_server_reuses_runner_until_final_entry_release():
    server = LoopbackMediaServer()
    await server.acquire_entry()
    first_runner = server._runner
    first_site = server._site
    await server.acquire_entry()

    assert server._runner is first_runner
    assert server._site is first_site

    await server.release_entry()
    assert server._runner is first_runner
    await server.release_entry()
    assert server._runner is None
    assert server._site is None


async def test_allocator_reserves_even_non_overlapping_port_pairs():
    allocator = RtpPortAllocator()
    first, second = await asyncio.gather(
        allocator.acquire(2),
        allocator.acquire(1),
    )
    first_ports = {port for pair in first.pairs for port in pair}
    second_ports = {port for pair in second.pairs for port in pair}

    assert all(rtp % 2 == 0 and rtcp == rtp + 1 for rtp, rtcp in first.pairs)
    assert first_ports.isdisjoint(second_ports)

    probes = []
    try:
        for port in first_ports:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probes.append(probe)
            with pytest.raises(OSError):
                probe.bind(("127.0.0.1", port))
    finally:
        for probe in probes:
            probe.close()

    await first.release()
    await second.release()


async def test_allocator_retains_logical_lease_after_reservations_close():
    offered_ports = iter(
        [4000, None, 4000, 4002, None, 4000, None]
    )

    class FakeSocket:
        def __init__(self, port):
            self.port = port

        def setblocking(self, _enabled):
            pass

        def bind(self, address):
            if self.port is None:
                self.port = address[1]

        def getsockname(self):
            return "127.0.0.1", self.port

        def close(self):
            pass

    allocator = RtpPortAllocator(
        socket_factory=lambda *_args: FakeSocket(next(offered_ports))
    )
    first = await allocator.acquire(1)
    first.release_reservations()
    second = await allocator.acquire(1)

    assert first.pairs == ((4000, 4001),)
    assert second.pairs == ((4002, 4003),)
    assert first.released is False

    await first.release()
    third = await allocator.acquire(1)
    assert third.pairs == ((4000, 4001),)

    await second.release()
    await third.release()
    assert first.released is True
    assert second.released is True
    assert third.released is True


async def test_allocator_rolls_back_partial_multi_track_acquisition():
    created = []
    ports = iter([4000, None, 4002, None])

    class FakeSocket:
        def __init__(self, port):
            self.port = port
            self.closed = False
            created.append(self)

        def setblocking(self, _enabled):
            pass

        def bind(self, address):
            if self.port is None:
                self.port = address[1]
            if self.port == 4003:
                raise OSError("occupied")

        def getsockname(self):
            return "127.0.0.1", self.port

        def close(self):
            self.closed = True
            if self.port == 4000:
                raise OSError("close failed")

    def socket_factory(*_args):
        try:
            return FakeSocket(next(ports))
        except StopIteration:
            raise RuntimeError("allocation stopped") from None

    allocator = RtpPortAllocator(socket_factory=socket_factory)

    with pytest.raises(RuntimeError, match="allocation stopped"):
        await allocator.acquire(2)

    assert allocator._leased_ports == set()
    assert all(sock.closed for sock in created)


async def test_allocator_release_closes_every_socket_after_close_failure():
    allocator = RtpPortAllocator()
    closed = []

    class FailingSocket:
        def __init__(self, name, *, fail=False):
            self.name = name
            self.fail = fail

        def close(self):
            closed.append(self.name)
            if self.fail:
                raise OSError("close failed")

    lease = PortLease(
        allocator,
        ((4000, 4001),),
        [FailingSocket("rtp", fail=True), FailingSocket("rtcp")],
    )
    allocator._leased_ports.update((4000, 4001))

    with pytest.raises(OSError, match="close failed"):
        await lease.release()

    assert closed == ["rtp", "rtcp"]
    assert lease.released is True
    assert allocator._leased_ports == set()


async def test_allocator_rejects_invalid_track_count():
    allocator = RtpPortAllocator()

    with pytest.raises(ValueError, match="track_count"):
        await allocator.acquire(0)
