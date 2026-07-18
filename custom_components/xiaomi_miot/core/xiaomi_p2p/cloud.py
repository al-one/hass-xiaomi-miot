"""MISS cloud bootstrap and process-local capability cache.

This module is a thin, typed adapter over the existing
`MiotCloud.async_request_api()` method. It never logs or stores the
DID, host, keys, signature, request body, or raw response, and it never
swallows cancellation that the existing cloud abstraction propagates.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from time import monotonic
from typing import Awaitable, Callable, Protocol

from . import MissBootstrap, MissError, MissErrorCategory


INVALID_HOST_DETAIL = "lan_host_unavailable"

_RFC1918_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)


class _CloudLike(Protocol):
    """Subset of `MiotCloud` the MISS bootstrap layer depends on."""

    hass: object
    async_request_api: Callable[..., Awaitable[dict | None]]
    is_token_expired: Callable[[dict], bool]
    async_check_auth: Callable[..., Awaitable[bool]]


def _validate_pinned_address(value: str) -> str:
    """Validate a single resolved address and return it on success."""

    try:
        ip = ipaddress.ip_address(value)
    except ValueError as exc:
        raise MissError(MissErrorCategory.CLOUD, INVALID_HOST_DETAIL) from exc
    if ip.version != 4:
        raise MissError(MissErrorCategory.CLOUD, INVALID_HOST_DETAIL)
    if (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_global
    ):
        raise MissError(MissErrorCategory.CLOUD, INVALID_HOST_DETAIL)
    if not any(ip in network for network in _RFC1918_NETWORKS):
        raise MissError(MissErrorCategory.CLOUD, INVALID_HOST_DETAIL)
    return str(ip)


async def async_resolve_lan_host(host: str) -> str:
    """Resolve a host literal to a single pinned RFC1918 IPv4 address."""

    if not host or not isinstance(host, str):
        raise MissError(MissErrorCategory.CLOUD, INVALID_HOST_DETAIL)

    stripped = host.strip()
    if not stripped:
        raise MissError(MissErrorCategory.CLOUD, INVALID_HOST_DETAIL)

    if any(ch.isspace() for ch in stripped):
        raise MissError(MissErrorCategory.CLOUD, INVALID_HOST_DETAIL)

    if all(part.isdigit() for part in stripped.split(".")):
        return _validate_pinned_address(stripped)

    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(
            stripped,
            None,
            type=socket.SOCK_STREAM,
        )
    except (socket.gaierror, UnicodeError, ValueError) as exc:
        raise MissError(MissErrorCategory.CLOUD, INVALID_HOST_DETAIL) from exc
    distinct: set[str] = set()
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        candidate = _validate_pinned_address(sockaddr[0])
        distinct.add(candidate)

    if len(distinct) != 1:
        raise MissError(MissErrorCategory.CLOUD, INVALID_HOST_DETAIL)
    return next(iter(distinct))


async def async_miss_get_vendor_impl(
    cloud: _CloudLike,
    did: str,
    host: str,
    deadline: float,
) -> MissBootstrap:
    """Implement the MISS vendor bootstrap against a `MiotCloud`-like client."""

    pinned = await async_resolve_lan_host(host)

    # Ephemeral client Curve25519 key pair generated once per call.
    from nacl.public import PrivateKey

    client_private = PrivateKey.generate()
    client_public = client_private.public_key
    app_pubkey = client_public.encode().hex()

    request_body = {
        "did": did,
        "app_pubkey": app_pubkey,
        "support_vendors": "TUTK_CS2_MTP",
    }

    async def _attempt(remaining_deadline: float):
        remaining = remaining_deadline - monotonic()
        if remaining <= 0:
            raise MissError(MissErrorCategory.TIMEOUT, "deadline")
        timeout = min(10.0, max(1.0, remaining))
        try:
            response = await cloud.async_request_api(
                "/v2/device/miss_get_vendor",
                request_body,
                method="POST",
                debug=False,
                raise_timeout=True,
                timeout=timeout,
            )
        except asyncio.TimeoutError as exc:
            raise MissError(MissErrorCategory.TIMEOUT, "request timeout") from exc
        return response

    response = await _attempt(deadline)

    if response and cloud.is_token_expired(response):
        refreshed = await cloud.async_check_auth(notify=True)
        if not refreshed:
            raise MissError(MissErrorCategory.AUTH, "auth refresh failed")
        response = await _attempt(deadline)
        if response and cloud.is_token_expired(response):
            raise MissError(MissErrorCategory.AUTH, "auth refresh failed")

    if not response:
        raise MissError(MissErrorCategory.CLOUD, "vendor unavailable")

    result = response.get("result") or {}
    vendor_obj = result.get("vendor") or {}
    if not isinstance(vendor_obj, dict):
        raise MissError(MissErrorCategory.CLOUD, "vendor unavailable")
    try:
        vendor = int(vendor_obj.get("vendor"))
    except (TypeError, ValueError) as exc:
        raise MissError(MissErrorCategory.CLOUD, "vendor unavailable") from exc
    if vendor != 4:
        raise MissError(MissErrorCategory.CLOUD, "vendor unavailable")

    public_key_hex = result.get("public_key") or ""
    if not isinstance(public_key_hex, str):
        raise MissError(MissErrorCategory.CLOUD, "vendor unavailable")
    try:
        device_public = bytes.fromhex(public_key_hex)
    except ValueError as exc:
        raise MissError(MissErrorCategory.CLOUD, "vendor unavailable") from exc
    if len(device_public) != 32:
        raise MissError(MissErrorCategory.CLOUD, "vendor unavailable")

    signature = result.get("sign") or ""
    if not isinstance(signature, str) or not signature:
        raise MissError(MissErrorCategory.CLOUD, "vendor unavailable")

    vendor_params = vendor_obj.get("vendor_params") or {}
    p2p_id = vendor_params.get("p2p_id") if isinstance(vendor_params, dict) else None
    if p2p_id is not None and not isinstance(p2p_id, str):
        p2p_id = None

    return MissBootstrap(
        host=pinned,
        p2p_id=p2p_id,
        client_private_key=client_private.encode(),
        client_public_key=client_public.encode(),
        device_public_key=device_public,
        signature=signature,
        vendor=vendor,
    )


class P2PCapabilityCache:
    """Process-local `(entry_id, region, did) -> vendor` capability cache.

    Stores ONLY the vendor integer. Stores NOTHING ELSE: no host, no
    token, no key, no signature, no bootstrap material. A failed probe
    is not cached; the next call probes again.
    """

    TTL_SECONDS = 86400

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str, str], tuple[float, int]] = {}
        self._time = monotonic

    async def get_or_probe(
        self,
        entry_id: str,
        region: str,
        did: str,
        probe: Callable[[], Awaitable[int]],
    ) -> int:
        key = (entry_id, region, did)
        now = self._time()
        cached = self._entries.get(key)
        if cached is not None:
            ts, vendor = cached
            if now - ts < self.TTL_SECONDS:
                return vendor
            self._entries.pop(key, None)
        vendor = await probe()
        if isinstance(vendor, int):
            self._entries[key] = (now, vendor)
        return vendor

    def invalidate_entry(self, entry_id: str) -> None:
        self._entries = {
            key: value for key, value in self._entries.items() if key[0] != entry_id
        }


def get_capability_cache(hass) -> P2PCapabilityCache:
    """Return the integration-wide `P2PCapabilityCache`.

    Lazily installs one under `hass.data[DOMAIN]` so it survives across
    the lifetime of the integration.
    """

    from ..const import DOMAIN

    data = hass.data.setdefault(DOMAIN, {})
    cache = data.get("p2p_capability_cache")
    if cache is None:
        cache = P2PCapabilityCache()
        data["p2p_capability_cache"] = cache
    return cache


__all__ = [
    "INVALID_HOST_DETAIL",
    "P2PCapabilityCache",
    "async_miss_get_vendor_impl",
    "async_resolve_lan_host",
    "get_capability_cache",
]