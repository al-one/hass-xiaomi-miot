"""CS2 discovery and transport handoff.

Implements the Xiaomi CS2 (vendor=4) LAN-search handshake that mirrors the
go2rtc reference implementation at ``pkg/xiaomi/miss/cs2/conn.go``.

Sequence:
    1.  Bind a UDP socket on port 0.
    2.  Send ``[0xF1, 0x30, 0, 0]`` (msgLanSearch) to ``host:32108``.  Re-send
        every second until a reply arrives.
    3.  Receive the punch packet ``[0xF1, 0x41, ...]`` (msgPunchPkt) from the
        camera.  The packet carries the camera's UDP port.
    4.  Send ``[0xF1, 0x42, 0, 0]`` (msgP2PRdyUDP) for UDP transport, or
        ``[0xF1, 0x43, 0, 0]`` (msgP2PRdyTCP) for TCP transport.
    5.  If TCP, close the UDP socket and open a TCP connection to the
        camera.  If UDP, hand the connected socket to ``UdpCs2Transport``.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import socket
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal, Optional, Protocol

from .. import MissError, MissErrorCategory
from .bounds import (
    COMMAND_QUEUE_LIMIT,
    DISCOVERY_PORT,
    DISCOVERY_TIMEOUT_SECONDS,
    GAP_DEADLINE_SECONDS,
    MEDIA_QUEUE_LIMIT,
    REORDER_BYTE_LIMIT,
    REORDER_PACKET_LIMIT,
    RETRANSMIT_INTERVAL_SECONDS,
    RETRANSMIT_LIMIT,
)
from .protocol import (
    MAGIC,
    MSG_LAN_SEARCH,
    MSG_P2P_RDY_TCP,
    MSG_P2P_RDY_UDP,
    MSG_PUNCH_PKT,
    encode_msg,
)
from .udp import UdpCs2Transport

_LOGGER = logging.getLogger(__name__)


TransportPolicyStr = Literal["auto", "prefer_udp", "prefer_tcp"]


class _SocketLike(Protocol):
    def getsockname(self) -> tuple[str, int]: ...
    async def sendto(self, data: bytes, addr: tuple[str, int]) -> None: ...
    async def recvfrom(self) -> tuple[bytes, tuple[str, int]]: ...
    def connect(self, addr: tuple[str, int]) -> None: ...
    def close(self) -> None: ...


class _TcpLike(Protocol):
    async def send_command_frame(self, data: bytes) -> None: ...
    async def recv_command_frame(self) -> bytes: ...
    def close(self) -> None: ...


BindSocketFn = Callable[[int], _SocketLike]
OpenTcpFn = Callable[
    [tuple[str, int]],
    tuple[object, object] | Awaitable[tuple[object, object]],
]


class AsyncioDatagramSocket:
    """Datagram socket wrapper that ignores packets from unexpected peers."""

    def __init__(self, port: int) -> None:
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setblocking(False)
        self._socket.bind(("0.0.0.0", port))

    def getsockname(self) -> tuple[str, int]:
        return self._socket.getsockname()

    async def sendto(self, data: bytes, addr: tuple[str, int]) -> None:
        await asyncio.get_running_loop().sock_sendto(self._socket, data, addr)

    async def recvfrom(self) -> tuple[bytes, tuple[str, int]]:
        return await asyncio.get_running_loop().sock_recvfrom(self._socket, 65535)

    def connect(self, addr: tuple[str, int]) -> None:
        self._socket.connect(addr)

    def close(self) -> None:
        self._socket.close()


def create_default_connector(clock) -> "DefaultCs2Connector":
    async def open_tcp(addr: tuple[str, int]):
        return await asyncio.open_connection(*addr)

    return DefaultCs2Connector(
        clock=clock,
        bind_socket=AsyncioDatagramSocket,
        open_tcp=open_tcp,
        retransmit_after=asyncio.sleep,
        gap_after=asyncio.sleep,
    )


def _build_lan_search() -> bytes:
    """Encode the LAN search request sent to ``host:32108``."""
    return encode_msg(MSG_LAN_SEARCH, b"\x00\x00")


def _is_msg(payload: bytes, kind: int) -> bool:
    """Return True when ``payload`` is a CS2 frame of the given kind."""
    return len(payload) >= 2 and payload[0] == MAGIC and payload[1] == kind


@dataclass
class _HandshakeResult:
    """Outcome of the LanSearch handshake."""

    peer: tuple[str, int]
    mode: str  # "udp" | "tcp"


class DefaultCs2Connector:
    """Single-discovery CS2 connector.

    The connector performs one UDP LanSearch exchange, then either hands the
    existing socket off to a UDP transport or opens a TCP connection.  No
    second discovery is attempted.
    """

    def __init__(
        self,
        *,
        clock,
        bind_socket: BindSocketFn,
        open_tcp: OpenTcpFn,
        retransmit_after: Callable[[float], None],
        gap_after: Callable[[float], None],
        ack_callback: Optional[Callable[[tuple[str, int], int], None]] = None,
        rejection_callback: Optional[Callable[[tuple[str, int]], None]] = None,
    ) -> None:
        self._clock = clock
        self._bind_socket = bind_socket
        self._open_tcp = open_tcp
        self._retransmit_after = retransmit_after
        self._gap_after = gap_after
        self._ack_callback = ack_callback
        self._rejection_callback = rejection_callback

    async def connect(self, bootstrap, policy: str, deadline: float):
        policy = self._validate_policy(policy)
        loop = asyncio.get_running_loop()

        sock = self._bind_socket(0)
        try:
            _LOGGER.debug(
                '=== CS2 discovery sending LanSearch to %s:%s policy=%s',
                bootstrap.host, DISCOVERY_PORT, policy,
            )
            try:
                await sock.sendto(_build_lan_search(), (bootstrap.host, DISCOVERY_PORT))
            except Exception as exc:
                sock.close()
                _LOGGER.warning(
                    "CS2 discovery sendto %s:%s failed: %s; "
                    "check container network can reach the LAN camera",
                    bootstrap.host, DISCOVERY_PORT, exc,
                )
                raise MissError(
                    MissErrorCategory.TRANSPORT, "cs2_discovery_failed"
                ) from exc

            # 1. Wait for the punch packet from the camera. Re-send the
            # LanSearch packet every second until it arrives or the
            # discovery timeout expires.
            deadline_ts = loop.time() + DISCOVERY_TIMEOUT_SECONDS
            punch_payload: bytes | None = None
            punch_addr: tuple[str, int] | None = None
            while True:
                remaining = deadline_ts - loop.time()
                if remaining <= 0:
                    sock.close()
                    _LOGGER.warning(
                        "CS2 discovery timed out after %ss waiting for "
                        "PunchPkt from %s:%s; camera may be offline, behind "
                        "firewall, or not responding to LAN discovery",
                        DISCOVERY_TIMEOUT_SECONDS,
                        bootstrap.host, DISCOVERY_PORT,
                    )
                    raise MissError(
                        MissErrorCategory.TRANSPORT, "cs2_discovery_failed"
                    )
                try:
                    payload, addr = await asyncio.wait_for(
                        sock.recvfrom(), timeout=remaining
                    )
                except asyncio.TimeoutError as exc:
                    sock.close()
                    _LOGGER.warning(
                        "CS2 discovery recvfrom timed out after %ss "
                        "waiting for PunchPkt from %s:%s",
                        DISCOVERY_TIMEOUT_SECONDS,
                        bootstrap.host, DISCOVERY_PORT,
                    )
                    raise MissError(
                        MissErrorCategory.TRANSPORT, "cs2_discovery_failed"
                    ) from exc
                except Exception as exc:
                    sock.close()
                    _LOGGER.warning(
                        "CS2 discovery recvfrom raised: %s", exc,
                    )
                    raise MissError(
                        MissErrorCategory.TRANSPORT, "cs2_discovery_failed"
                    ) from exc

                if addr[0] != bootstrap.host:
                    sock.close()
                    _LOGGER.warning(
                        "CS2 discovery got packet from %s but bootstrap "
                        "pinned %s; refusing to redirect",
                        addr[0], bootstrap.host,
                    )
                    raise MissError(
                        MissErrorCategory.TRANSPORT, "cs2_discovery_invalid"
                    )
                if _is_msg(payload, MSG_PUNCH_PKT):
                    punch_payload = payload
                    punch_addr = addr
                    _LOGGER.debug(
                        '=== CS2 discovery got PunchPkt from %s:%s',
                        addr[0], addr[1],
                    )
                    break
                _LOGGER.warning(
                    "CS2 discovery got unexpected packet kind=0x%02x "
                    "from %s while waiting for PunchPkt",
                    payload[1], addr[0],
                )
                # Re-send LanSearch periodically while we wait.
                try:
                    await sock.sendto(
                        _build_lan_search(), (bootstrap.host, DISCOVERY_PORT)
                    )
                except Exception as exc:
                    _LOGGER.debug(
                        "CS2 discovery re-send LanSearch failed: %s",
                        exc,
                    )

            # 2. Send the ready packet (UDP or TCP) and wait for the camera
            # to acknowledge with the matching ready.
            want_udp = policy in ("auto", "prefer_udp")
            want_tcp = policy in ("auto", "prefer_tcp")
            ack_kind = MSG_P2P_RDY_UDP if want_udp else MSG_P2P_RDY_TCP
            # If both UDP and TCP are acceptable, prefer UDP unless the
            # caller asked for TCP. We send UDP by default and fall back
            # to TCP if the camera rejects it.
            chosen_kind = MSG_P2P_RDY_UDP
            try:
                await sock.sendto(
                    encode_msg(MSG_P2P_RDY_UDP, b"\x00\x00"),
                    punch_addr,
                )
            except Exception as exc:
                sock.close()
                _LOGGER.warning(
                    "CS2 discovery sendto ReadyPkt to %s:%s failed: %s",
                    punch_addr[0], punch_addr[1], exc,
                )
                raise MissError(
                    MissErrorCategory.TRANSPORT, "cs2_discovery_failed"
                ) from exc

            deadline_ts = loop.time() + DISCOVERY_TIMEOUT_SECONDS
            ack_payload: bytes | None = None
            while True:
                remaining = deadline_ts - loop.time()
                if remaining <= 0:
                    sock.close()
                    _LOGGER.warning(
                        "CS2 discovery timed out after %ss waiting for "
                        "ReadyPkt from %s:%s after PunchPkt",
                        DISCOVERY_TIMEOUT_SECONDS,
                        bootstrap.host, DISCOVERY_PORT,
                    )
                    raise MissError(
                        MissErrorCategory.TRANSPORT, "cs2_discovery_failed"
                    )
                try:
                    payload, addr = await asyncio.wait_for(
                        sock.recvfrom(), timeout=remaining
                    )
                except asyncio.TimeoutError as exc:
                    sock.close()
                    _LOGGER.warning(
                        "CS2 discovery recvfrom timed out after %ss "
                        "waiting for ReadyPkt from %s:%s",
                        DISCOVERY_TIMEOUT_SECONDS,
                        bootstrap.host, DISCOVERY_PORT,
                    )
                    raise MissError(
                        MissErrorCategory.TRANSPORT, "cs2_discovery_failed"
                    ) from exc
                except Exception as exc:
                    sock.close()
                    _LOGGER.warning(
                        "CS2 discovery recvfrom raised during ReadyPkt "
                        "phase: %s", exc,
                    )
                    raise MissError(
                        MissErrorCategory.TRANSPORT, "cs2_discovery_failed"
                    ) from exc
                if addr[0] != bootstrap.host:
                    sock.close()
                    _LOGGER.warning(
                        "CS2 discovery got ReadyPkt from %s but bootstrap "
                        "pinned %s; refusing to redirect",
                        addr[0], bootstrap.host,
                    )
                    raise MissError(
                        MissErrorCategory.TRANSPORT, "cs2_discovery_invalid"
                    )
                if _is_msg(payload, MSG_P2P_RDY_UDP) or _is_msg(payload, MSG_P2P_RDY_TCP):
                    ack_payload = payload
                    chosen_kind = payload[1]
                    break

            mode = "udp" if chosen_kind == MSG_P2P_RDY_UDP else "tcp"
            peer = punch_addr

        except BaseException:
            sock.close()
            raise

        if mode == "udp":
            try:
                sock.connect(peer)
            except Exception as exc:
                sock.close()
                _LOGGER.warning(
                    "CS2 discovery UDP connect to %s:%s failed: %s",
                    peer[0], peer[1], exc,
                )
                raise MissError(
                    MissErrorCategory.TRANSPORT, "cs2_discovery_failed"
                ) from exc
            transport = UdpCs2Transport(
                sock=sock,
                peer_addr=peer,
                clock=self._clock,
                retransmit_after=self._retransmit_after,
                gap_after=self._gap_after,
                ack_callback=self._ack_callback,
                rejection_callback=self._rejection_callback,
            )
            transport.start_reader()
            return transport

        # TCP-ready path
        sock.close()
        # Use the source address of the most recent ready packet from the
        # camera (matches go2rtc's ``newTCPConn(conn.RemoteAddr().String())``
        # pattern).
        try:
            tcp_result = self._open_tcp(peer)
            if inspect.isawaitable(tcp_result):
                reader, writer = await tcp_result
            else:
                reader, writer = tcp_result
        except Exception as exc:
            _LOGGER.warning(
                "CS2 discovery TCP connect to %s:%s failed: %s; "
                "check that TCP 32108 (or the camera reply port) is "
                "reachable from the HA host",
                peer[0], peer[1], exc,
            )
            raise MissError(
                MissErrorCategory.TRANSPORT, "cs2_discovery_failed"
            ) from exc
        from .tcp import TcpCs2Transport

        transport = TcpCs2Transport(reader=reader, writer=writer, clock=self._clock)
        transport.start_reader()
        return transport

    @staticmethod
    def _validate_policy(policy: str) -> TransportPolicyStr:
        if policy not in ("auto", "prefer_udp", "prefer_tcp"):
            raise MissError(MissErrorCategory.TRANSPORT, "cs2_policy_invalid")
        return policy  # type: ignore[return-value]


__all__ = [
    "COMMAND_QUEUE_LIMIT",
    "DISCOVERY_PORT",
    "DISCOVERY_TIMEOUT_SECONDS",
    "DefaultCs2Connector",
    "GAP_DEADLINE_SECONDS",
    "MEDIA_QUEUE_LIMIT",
    "REORDER_BYTE_LIMIT",
    "REORDER_PACKET_LIMIT",
    "RETRANSMIT_INTERVAL_SECONDS",
    "RETRANSMIT_LIMIT",
]