"""CS2 discovery and transport handoff.

`DefaultCs2Connector` performs one UDP discovery exchange against the
pinned RFC 1918 host on port 32108. The single ready response selects
either the UDP or TCP transport; no second discovery is attempted.
"""

from __future__ import annotations

import asyncio
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
from .protocol import CS2_FRAME_MAGIC, encode_outbound_cs2_command
from .udp import UdpCs2Transport


# Re-export bounds for callers that import them from `discovery`.


TransportPolicyStr = Literal["auto", "prefer_udp", "prefer_tcp"]


class _SocketLike(Protocol):
    def getsockname(self) -> tuple[str, int]: ...
    async def sendto(self, data: bytes, addr: tuple[str, int]) -> None: ...
    async def recvfrom(self) -> tuple[bytes, tuple[str, int]]: ...
    def close(self) -> None: ...


class _TcpLike(Protocol):
    async def send_command_frame(self, data: bytes) -> None: ...
    async def recv_command_frame(self) -> bytes: ...
    def close(self) -> None: ...


BindSocketFn = Callable[[int], _SocketLike]
OpenTcpFn = Callable[[tuple[str, int]], tuple[object, object]]


@dataclass(frozen=True)
class _ReadyResponse:
    addr: tuple[str, int]
    kind: str  # "udp" | "tcp" | "intermediate"


def _parse_ready(payload: bytes, *, expected_host: str) -> _ReadyResponse:
    """Decode a 12-byte ready response.

    Layout:
        2 bytes magic `0x21 0x00`
        1 byte kind (`0x00` intermediate, `0x01` UDP-ready, `0x02` TCP-ready)
        2 bytes port (uint16 BE)
        7 bytes reserved (must be zero in tests; ignored here)
    """

    if len(payload) < 12:
        raise MissError(MissErrorCategory.TRANSPORT, "cs2_discovery_invalid")
    if payload[0:2] != b"\x21\x00":
        raise MissError(MissErrorCategory.TRANSPORT, "cs2_discovery_invalid")
    kind_byte = payload[2]
    port = int.from_bytes(payload[3:5], "big")
    if port == 0:
        raise MissError(MissErrorCategory.TRANSPORT, "cs2_discovery_invalid")
    if kind_byte == 0x01:
        kind = "udp"
    elif kind_byte == 0x02:
        kind = "tcp"
    elif kind_byte == 0x00:
        kind = "intermediate"
    else:
        raise MissError(MissErrorCategory.TRANSPORT, "cs2_discovery_invalid")
    return _ReadyResponse(addr=(expected_host, port), kind=kind)


class DefaultCs2Connector:
    """Single-discovery CS2 connector.

    The connector owns one UDP discovery exchange, then either hands
    the existing socket off to a UDP transport (after `connect()`) or
    closes discovery and opens TCP for a TCP transport.
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

        sock = self._bind_socket(0)
        try:
            await sock.sendto(
                _build_discovery_request(policy),
                (bootstrap.host, DISCOVERY_PORT),
            )
        except Exception as exc:  # pragma: no cover - defensive
            sock.close()
            raise MissError(MissErrorCategory.TRANSPORT, "cs2_discovery_failed") from exc

        try:
            payload, addr = await asyncio.wait_for(
                sock.recvfrom(), timeout=DISCOVERY_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError as exc:
            sock.close()
            raise MissError(MissErrorCategory.TRANSPORT, "cs2_discovery_failed") from exc
        except Exception as exc:
            sock.close()
            raise MissError(MissErrorCategory.TRANSPORT, "cs2_discovery_failed") from exc

        if addr[0] != bootstrap.host:
            sock.close()
            raise MissError(MissErrorCategory.TRANSPORT, "cs2_discovery_invalid")

        try:
            ready = _parse_ready(payload, expected_host=bootstrap.host)
        except MissError:
            sock.close()
            raise

        candidate_port = ready.addr[1]
        if ready.kind == "intermediate":
            # Validate intermediate shape but keep waiting for the final ready.
            try:
                final_payload, _ = await asyncio.wait_for(
                    sock.recvfrom(), timeout=DISCOVERY_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError as exc:
                sock.close()
                raise MissError(MissErrorCategory.TRANSPORT, "cs2_discovery_failed") from exc
            except Exception as exc:
                sock.close()
                raise MissError(MissErrorCategory.TRANSPORT, "cs2_discovery_failed") from exc
            try:
                final = _parse_ready(final_payload, expected_host=bootstrap.host)
            except MissError:
                sock.close()
                raise
            candidate_port = final.addr[1]
            ready = final

        if ready.kind == "udp":
            try:
                sock.connect((bootstrap.host, candidate_port))
            except Exception as exc:
                sock.close()
                raise MissError(MissErrorCategory.TRANSPORT, "cs2_discovery_failed") from exc
            transport = UdpCs2Transport(
                sock=sock,
                peer_addr=(bootstrap.host, candidate_port),
                clock=self._clock,
                retransmit_after=self._retransmit_after,
                gap_after=self._gap_after,
                ack_callback=self._ack_callback or self._record_ack_udp,
                rejection_callback=self._rejection_callback or self._record_rejection_udp,
            )
            transport.start_reader()
            return transport

        # TCP-ready path
        sock.close()
        reader, writer = self._open_tcp((bootstrap.host, candidate_port))
        # The TCP transport lives in `cs2/tcp.py` and is constructed by
        # importing it lazily so this module stays independent of asyncio
        # StreamReader/StreamWriter during unit tests.
        from .tcp import TcpCs2Transport

        return TcpCs2Transport(reader=reader, writer=writer)

    @staticmethod
    def _validate_policy(policy: str) -> TransportPolicyStr:
        if policy not in ("auto", "prefer_udp", "prefer_tcp"):
            raise MissError(MissErrorCategory.TRANSPORT, "cs2_policy_invalid")
        return policy  # type: ignore[return-value]

    def _record_ack_udp(self, addr, sequence):
        # The peer fixture tracks acks for tests; production code records
        # against the session socket's bound peer.
        return None

    def _record_rejection_udp(self, addr):
        # The peer fixture tracks rejections for tests; production code
        # only needs the transport's own counter.
        return None


def _build_discovery_request(policy: str) -> bytes:
    """Encode the single discovery request for the given policy."""

    # Layout: 2 bytes magic, 4 bytes policy preference, 4 bytes reserved.
    pref = {
        "auto": 0x00,
        "prefer_udp": 0x01,
        "prefer_tcp": 0x02,
    }[policy]
    return CS2_FRAME_MAGIC + bytes([pref]) + b"\x00" * 5


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