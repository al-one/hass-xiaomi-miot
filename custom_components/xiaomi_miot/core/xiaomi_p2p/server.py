"""Authenticated loopback HTTP routing and RTP port reservations."""

from __future__ import annotations

import asyncio
import base64
import hmac
import secrets
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from aiohttp import web

from . import MissError


RouteHandler = Callable[[web.Request], Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class RouteHandle:
    route_id: str
    path: str
    url: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class _RouteMapping:
    handler: RouteHandler = field(repr=False)
    auth_token: str = field(repr=False)


class PortLease:
    __slots__ = (
        "pairs",
        "released",
        "_allocator",
        "_reservation_sockets",
    )

    def __init__(
        self,
        allocator: RtpPortAllocator,
        pairs: tuple[tuple[int, int], ...],
        reservation_sockets: list[socket.socket],
    ) -> None:
        self.pairs = pairs
        self.released = False
        self._allocator = allocator
        self._reservation_sockets = reservation_sockets

    def release_reservations(self) -> None:
        sockets, self._reservation_sockets = self._reservation_sockets, []
        first_error: BaseException | None = None
        for reservation in sockets:
            try:
                reservation.close()
            except BaseException as err:
                if first_error is None:
                    first_error = err
        if first_error is not None:
            raise first_error

    async def release(self) -> None:
        await self._allocator._release(self)


class RtpPortAllocator:
    def __init__(
        self,
        *,
        socket_factory: Callable[..., socket.socket] = socket.socket,
    ) -> None:
        self._socket_factory = socket_factory
        self._lock = asyncio.Lock()
        self._leased_ports: set[int] = set()

    async def acquire(self, track_count: int) -> PortLease:
        if track_count <= 0:
            raise ValueError("track_count must be positive")
        async with self._lock:
            pairs: list[tuple[int, int]] = []
            reservations: list[socket.socket] = []
            try:
                for _ in range(track_count):
                    pair, sockets = self._reserve_pair()
                    pairs.append(pair)
                    reservations.extend(sockets)
                    self._leased_ports.update(pair)
            except BaseException:
                for reservation in reservations:
                    try:
                        reservation.close()
                    except BaseException:
                        pass
                for pair in pairs:
                    self._leased_ports.difference_update(pair)
                raise
            return PortLease(self, tuple(pairs), reservations)

    def _reserve_pair(
        self,
    ) -> tuple[tuple[int, int], tuple[socket.socket, socket.socket]]:
        for _ in range(1000):
            rtp_socket = self._new_socket()
            try:
                rtp_socket.bind(("127.0.0.1", 0))
                rtp_port = rtp_socket.getsockname()[1]
                rtcp_port = rtp_port + 1
                if rtp_port % 2 or rtcp_port in self._leased_ports:
                    rtp_socket.close()
                    continue
                rtcp_socket = self._new_socket()
                try:
                    rtcp_socket.bind(("127.0.0.1", rtcp_port))
                except OSError:
                    rtcp_socket.close()
                    rtp_socket.close()
                    continue
                return (rtp_port, rtcp_port), (rtp_socket, rtcp_socket)
            except BaseException:
                rtp_socket.close()
                raise
        raise OSError("RTP port pair unavailable")

    def _new_socket(self) -> socket.socket:
        reservation = self._socket_factory(socket.AF_INET, socket.SOCK_DGRAM)
        reservation.setblocking(False)
        return reservation

    async def _release(self, lease: PortLease) -> None:
        async with self._lock:
            if lease.released:
                return
            first_error: BaseException | None = None
            try:
                lease.release_reservations()
            except BaseException as err:
                first_error = err
            finally:
                for pair in lease.pairs:
                    self._leased_ports.difference_update(pair)
                lease.released = True
            if first_error is not None:
                raise first_error


class LoopbackMediaServer:
    ROUTE_PATH = "/xiaomi_miot/p2p/{route_id}"

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._entry_references = 0
        self._routes: dict[str, _RouteMapping] = {}
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._port: int | None = None

    async def acquire_entry(self) -> None:
        async with self._lock:
            if self._entry_references:
                self._entry_references += 1
                return
            app = web.Application()
            app.router.add_get(self.ROUTE_PATH, self._handle_get)
            runner = web.AppRunner(app, access_log=None)
            await runner.setup()
            site = web.TCPSite(runner, "127.0.0.1", 0)
            try:
                await site.start()
            except BaseException:
                await runner.cleanup()
                raise
            addresses = runner.addresses
            if not addresses:
                await runner.cleanup()
                raise OSError("loopback media server did not bind")
            self._runner = runner
            self._site = site
            self._port = addresses[0][1]
            self._entry_references = 1

    async def release_entry(self) -> None:
        async with self._lock:
            if self._entry_references == 0:
                return
            self._entry_references -= 1
            if self._entry_references:
                return
            self._routes.clear()
            shutdown_task = asyncio.create_task(
                self._shutdown(self._site, self._runner)
            )
            await self._await_shielded(shutdown_task)

    async def _shutdown(
        self,
        site: web.TCPSite | None,
        runner: web.AppRunner | None,
    ) -> None:
        try:
            if site is not None:
                await site.stop()
        finally:
            try:
                if runner is not None:
                    await runner.cleanup()
            finally:
                self._site = None
                self._runner = None
                self._port = None

    def add_route(self, handler: RouteHandler) -> RouteHandle:
        if self._port is None:
            raise RuntimeError("loopback media server is not running")
        while True:
            route_id = base64.urlsafe_b64encode(
                secrets.token_bytes(16)
            ).rstrip(b"=").decode("ascii")
            if route_id not in self._routes:
                break
        auth_token = secrets.token_urlsafe(32)
        path = self.ROUTE_PATH.format(route_id=route_id)
        url = f"http://127.0.0.1:{self._port}{path}?auth={auth_token}"
        self._routes[route_id] = _RouteMapping(handler, auth_token)
        return RouteHandle(route_id, path, url)

    def remove_route(self, route_id: str) -> None:
        self._routes.pop(route_id, None)

    async def _handle_get(self, request: web.Request) -> web.StreamResponse:
        mapping = self._routes.get(request.match_info["route_id"])
        if mapping is None:
            return web.Response(status=404)
        supplied_token = request.query.get("auth")
        try:
            supplied_token_bytes = (
                supplied_token.encode("ascii")
                if supplied_token is not None
                else b""
            )
        except UnicodeEncodeError:
            return web.Response(status=404)
        if supplied_token is None or not hmac.compare_digest(
            supplied_token_bytes,
            mapping.auth_token.encode("ascii"),
        ):
            return web.Response(status=404)
        try:
            target = await mapping.handler(request)
        except MissError as err:
            if err.detail == "active_source_limit":
                return web.Response(
                    status=503,
                    headers={"Retry-After": "5"},
                )
            return web.Response(status=502)
        except asyncio.CancelledError:
            raise
        except Exception:
            return web.Response(status=502)
        if isinstance(target, web.StreamResponse):
            return target
        return await self._run_bridge(target, request)

    async def _run_bridge(
        self,
        bridge: Any,
        request: web.Request,
    ) -> web.StreamResponse:
        run_error: BaseException | None = None
        response: web.StreamResponse | None = None
        try:
            response = await bridge.run(request)
        except BaseException as err:
            run_error = err
        try:
            await self._await_shielded(bridge.close_future)
        except BaseException:
            if run_error is not None:
                raise run_error
            raise
        if run_error is not None:
            raise run_error
        if response is None:
            raise RuntimeError("bridge returned no response")
        return response

    @staticmethod
    async def _await_shielded(future: asyncio.Future[Any]) -> Any:
        cancellation: asyncio.CancelledError | None = None
        while not future.done():
            try:
                await asyncio.shield(future)
            except asyncio.CancelledError as err:
                cancellation = err
            except BaseException:
                if cancellation is not None:
                    try:
                        future.result()
                    except BaseException:
                        pass
                    raise cancellation
                raise
        if cancellation is not None:
            try:
                future.result()
            except BaseException:
                pass
            raise cancellation
        return future.result()


__all__ = [
    "LoopbackMediaServer",
    "PortLease",
    "RouteHandle",
    "RtpPortAllocator",
]
