"""Hard bounds shared by the CS2 UDP transport and connector.

These constants are intentionally module-level integers/floats with no
behavior. Splitting them out of `discovery` lets both `discovery` and
`udp` import them without a cycle.
"""

from __future__ import annotations


REORDER_PACKET_LIMIT: int = 250
REORDER_BYTE_LIMIT: int = 4 * 1024 * 1024
COMMAND_QUEUE_LIMIT: int = 10
MEDIA_QUEUE_LIMIT: int = 100
GAP_DEADLINE_SECONDS: float = 2.0
RETRANSMIT_LIMIT: int = 5
RETRANSMIT_INTERVAL_SECONDS: float = 1.0

DISCOVERY_PORT: int = 32108
DISCOVERY_TIMEOUT_SECONDS: float = 4.0


__all__ = [
    "COMMAND_QUEUE_LIMIT",
    "DISCOVERY_PORT",
    "DISCOVERY_TIMEOUT_SECONDS",
    "GAP_DEADLINE_SECONDS",
    "MEDIA_QUEUE_LIMIT",
    "REORDER_BYTE_LIMIT",
    "REORDER_PACKET_LIMIT",
    "RETRANSMIT_INTERVAL_SECONDS",
    "RETRANSMIT_LIMIT",
]
