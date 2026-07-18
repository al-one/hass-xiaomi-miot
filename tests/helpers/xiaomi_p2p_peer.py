"""Fake CS2 peer for transport tests.

`FakeCs2Peer` simulates a CS2 camera just enough to drive the
connector and UDP transport through discovery, peer lock, ACK, and
reorder scenarios. It is NOT a complete CS2 stack; it only models
the surfaces tests need to assert against.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from custom_components.xiaomi_miot.core.xiaomi_p2p import MissBootstrap
from custom_components.xiaomi_miot.core.xiaomi_p2p.cs2.protocol import (
    DRW_MAGIC_MEDIA,
    encode_outbound_cs2_command,
)


DISCOVERY_PORT = 32108


@dataclass
class _QueuedResponse:
    addr: tuple[str, int]
    kind: str  # "udp" | "tcp" | "intermediate"


@dataclass
class _Datagram:
    addr: tuple[str, int]
    payload: bytes


class FakeSocket:
    def __init__(
        self,
        peer: "FakeCs2Peer",
        *,
        kind: str = "udp",
        local_port: int = 0,
        discovery_response=None,
    ) -> None:
        self._peer = peer
        self._kind = kind
        self._local_port = local_port
        self._closed = False
        self._connected: tuple[str, int] | None = None
        self._discovery_response = discovery_response

    @property
    def kind(self) -> str:
        return self._kind

    def getsockname(self):
        return ("0.0.0.0", self._local_port)

    def connect(self, addr):
        if self._kind != "udp":
            raise RuntimeError("connect() on TCP socket")
        self._connected = tuple(addr)

    async def sendto(self, data: bytes, addr):
        if self._kind != "udp":
            raise RuntimeError("sendto on TCP socket")
        if self._closed:
            raise RuntimeError("send on closed socket")
        self._peer.udp_sends.append((bytes(data), tuple(addr)))
        # Track the host the connector targeted so the fake can route the
        # scripted response back to the same address.
        self._peer._last_target_host = addr[0]

    async def recvfrom(self) -> tuple[bytes, tuple[str, int]]:
        if self._closed:
            raise asyncio.IncompleteReadError(b"", 0)
        # First, drain anything the test injected directly.
        if self._peer._inbound:
            return await self._peer.await_next_datagram(self)
        # Otherwise, ask the discovery_response callback for a ready
        # response (this is how the fake models the network reply).
        if self._discovery_response is not None:
            payload = self._discovery_response()
            # The fake doesn't know the local source addr; default to
            # the host the connector targeted.
            host = self._peer._last_target_host or "0.0.0.0"
            self._peer._inbound.append(
                _Datagram(addr=(host, 32108), payload=bytes(payload))
            )
        return await self._peer.await_next_datagram(self)

    def close(self) -> None:
        self._closed = True


class FakeCs2Peer:
    """Fake CS2 camera. Drives connector + transport through scripted scenarios."""

    def __init__(self, clock) -> None:
        self.clock = clock
        self.discovery_socket: FakeSocket | None = None
        self.session_socket: FakeSocket | None = None
        self.udp_sends: list[tuple[bytes, tuple[str, int]]] = []
        self.tcp_connects: list[tuple[str, int]] = []
        self.discovery_count = 0
        self.ack_count = 0
        self.rejected_peer_datagrams = 0
        self._udp_responses: list[_QueuedResponse] = []
        self._tcp_responses: list[_QueuedResponse] = []
        self._intermediate_responses: list[_QueuedResponse] = []
        self._inbound: list[_Datagram] = []
        self._waiters: list[asyncio.Future] = []
        self._discovery_response = None
        self._last_target_host: str | None = None

    # ---- Response / payload scripting ----------------------------------

    def queue_udp_ready(self, addr: tuple[str, int]) -> None:
        self._udp_responses.append(_QueuedResponse(addr=tuple(addr), kind="udp"))

    def queue_tcp_ready(self, addr: tuple[str, int]) -> None:
        self._tcp_responses.append(_QueuedResponse(addr=tuple(addr), kind="tcp"))

    def queue_intermediate_port(self, addr: tuple[str, int]) -> None:
        self._intermediate_responses.append(
            _QueuedResponse(addr=tuple(addr), kind="intermediate")
        )

    def inject_datagram(self, addr: tuple[str, int], payload: bytes) -> None:
        self._inbound.append(_Datagram(addr=tuple(addr), payload=bytes(payload)))
        self._wake_waiters()

    def valid_command_datagram(self, sequence: int = 0, payload: bytes = b"ok") -> bytes:
        return encode_outbound_cs2_command(0x101, payload, sequence=sequence)

    def valid_media_datagram(self, sequence: int = 0) -> bytes:
        # Channel-2 DRW framing with a small payload.
        header = DRW_MAGIC_MEDIA + sequence.to_bytes(2, "big")
        return header + b"\x00" * 8

    # ---- Transport-facing primitives -----------------------------------

    def bind_discovery_socket(self, local_port: int = 0, *, discovery_response=None) -> FakeSocket:
        sock = FakeSocket(
            self,
            kind="udp",
            local_port=local_port,
            discovery_response=discovery_response,
        )
        self.discovery_socket = sock
        return sock

    def open_session_socket(self, local_port: int = 0) -> FakeSocket:
        sock = FakeSocket(self, kind="udp", local_port=local_port)
        self.session_socket = sock
        return sock

    def open_tcp_connection(self, addr: tuple[str, int]):
        self.tcp_connects.append(tuple(addr))
        return (None, None)

    # ---- Connector-facing ----------------------------------------------

    def next_discovery_response(self) -> bytes:
        self.discovery_count += 1
        if self._intermediate_responses:
            ready = self._intermediate_responses.pop(0)
            kind_byte = 0x00
            port = ready.addr[1]
        elif self._udp_responses:
            ready = self._udp_responses.pop(0)
            kind_byte = 0x01
            port = ready.addr[1]
        elif self._tcp_responses:
            ready = self._tcp_responses.pop(0)
            kind_byte = 0x02
            port = ready.addr[1]
        else:
            raise AssertionError("no ready response queued")

        return b"\x21\x00" + bytes([kind_byte]) + port.to_bytes(2, "big") + b"\x00" * 7

    # ---- Transport ack and reject tracking -----------------------------

    def record_ack(self, addr: tuple[str, int], sequence: int) -> None:
        if addr and sequence >= 0:
            self.ack_count += 1

    def record_rejection(self, addr: tuple[str, int] | None = None) -> None:
        self.rejected_peer_datagrams += 1

    # ---- Datagram queue ------------------------------------------------

    async def await_next_datagram(self, sock: FakeSocket):
        while True:
            if self._inbound:
                dg = self._inbound.pop(0)
                return dg.payload, dg.addr
            fut: asyncio.Future = asyncio.get_event_loop().create_future()
            self._waiters.append(fut)
            await fut

    def _wake_waiters(self) -> None:
        for fut in self._waiters:
            if not fut.done():
                fut.set_result(None)
        self._waiters.clear()


def make_bootstrap(host: str = "192.168.1.20") -> MissBootstrap:
    return MissBootstrap(
        host=host,
        p2p_id="peer",
        client_private_key=b"\x11" * 32,
        client_public_key=b"\x22" * 32,
        device_public_key=b"\x33" * 32,
        signature="sig-redacted",
        vendor=4,
    )