# Native Xiaomi MISS+CS2 Camera Streaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add automatically activated, native LAN real-time streaming for eligible converter-backed Xiaomi cameras using MISS over CS2, exposed to Home Assistant as an authenticated loopback MPEG-TS source.

**Architecture:** Build six one-way layers: cloud bootstrap, pure cryptography, typed CS2 transport, MISS/media session, entry-owned session management, and an integration-wide loopback/FFmpeg bridge. Pure protocol modules remain independent of Home Assistant entities; only `Device`, `HassEntry`, and converter-backed `camera.CameraEntity` integrate those layers.

**Tech Stack:** Python 3.13 CI, Home Assistant Camera/Stream APIs, `aiohttp`, Home Assistant FFmpeg, `PyNaCl`, `pycryptodome`, `pytest`, and `pytest-homeassistant-custom-component`.

## Global Constraints

- Activate native P2P only for converter-backed `camera.CameraEntity` instances whose MIoT spec declares `p2p-stream`, whose `Device` belongs to a Xiaomi account entry, and whose setup-time preflight returns vendor `4`.
- Preserve every existing path for cameras without `p2p-stream`, failed/non-CS2 preflight, host/token-only entries, `BaseCameraEntity`, `MiotCameraEntity`, and `MotionCameraEntity`.
- Reuse `MiotCloud.async_request_api()` through `async_miss_get_vendor()`; do not modify the generic request method or its logging, timeout, authentication, or cancellation internals.
- Use process-local `(entry_id, region, did) -> vendor` capability cache entries with a 24-hour TTL; persist no bootstrap material and invalidate an entry's entries on reload.
- Default to transport `auto`, lens `primary`, raw quality `0`, and requested audio; never enumerate alternate quality values automatically.
- Support H.264/H.265 video and optional PCMA/Opus audio; only known profiles may require a specific codec for hardware acceptance.
- Bind the media server only to `127.0.0.1`; use one wildcard route registered before startup, opaque 16-byte route IDs, and independent `secrets.token_urlsafe(32)` tokens compared with `hmac.compare_digest()`.
- `stream_source()` must return its stable entity-lifetime URL in under one second and perform no cloud, socket, session, probe, or FFmpeg I/O.
- Bound setup at 24 seconds and response delivery at 25 seconds; reserve at least five setup seconds for RTP/FFmpeg and the first MPEG-TS chunk.
- Allow at most four active source GET leases per lens; return HTTP 503 and `Retry-After: 5` for the fifth.
- Start a 30-second idle timer only when the final bridge releases its lease; `keep_streaming` has no native P2P effect.
- Keep DIDs, account IDs, hosts, ports, tokens, keys, signatures, parameter sets, request bodies, raw responses, URLs, and payloads out of MISS-owned logs, diagnostics, and entity state.
- Preserve MIT attribution for translated go2rtc code and use only sanitized fixtures and fixed vectors.
- Use repository commit style: emoji followed by a lowercase imperative description.
- Established local validation is `python -m pytest -q`; the repository has no lint or static-type command.
- The Home Assistant `2023.7.0` CI job validates configuration only; it is not evidence that modern Camera provider APIs execute on that runtime. Before Camera implementation, characterize provider APIs in the installed pytest environment and preserve older non-P2P behavior with narrowly scoped feature detection where the base API is absent.
- Tasks 5, 8, and 11 contain multiple state machines; execute and review each named implementation step as an independent red-green-commit slice rather than batching the whole task into one commit.

---

## File Map

**Create production package**

- `custom_components/xiaomi_miot/core/xiaomi_p2p/__init__.py` — public immutable types, enums, errors, profiles, and factories.
- `custom_components/xiaomi_miot/core/xiaomi_p2p/cloud.py` — host validation, DNS pinning, and typed bootstrap orchestration.
- `custom_components/xiaomi_miot/core/xiaomi_p2p/crypto.py` — Curve25519/HSalsa20 shared-key derivation and MISS ChaCha20.
- `custom_components/xiaomi_miot/core/xiaomi_p2p/cs2/protocol.py` — framing constants, typed command/media frames, endian-specific codecs, and bounded stream parser.
- `custom_components/xiaomi_miot/core/xiaomi_p2p/cs2/transport.py` — `Cs2Transport` and `Cs2Connector` protocols plus transport exception taxonomy.
- `custom_components/xiaomi_miot/core/xiaomi_p2p/cs2/discovery.py` — one UDP discovery exchange and established UDP/TCP transport handoff.
- `custom_components/xiaomi_miot/core/xiaomi_p2p/cs2/udp.py` — peer lock, ACK/retransmission, reorder, and gap handling after UDP handoff.
- `custom_components/xiaomi_miot/core/xiaomi_p2p/cs2/tcp.py` — TCP framing, ping, and close behavior after TCP handoff.
- `custom_components/xiaomi_miot/core/xiaomi_p2p/media.py` — media headers, Annex-B parsing, access units, contracts, and normalized frames.
- `custom_components/xiaomi_miot/core/xiaomi_p2p/miss.py` — login, encrypted commands, media start/stop, probing, and recovery state.
- `custom_components/xiaomi_miot/core/xiaomi_p2p/rtp.py` — RTP packetization, SDP, timestamp mapping, and RTCP sender reports.
- `custom_components/xiaomi_miot/core/xiaomi_p2p/server.py` — loopback route map, server reference counting, and RTP/RTCP allocator.
- `custom_components/xiaomi_miot/core/xiaomi_p2p/bridge.py` — per-GET FFmpeg/RTP/HTTP bridge and ordered close state machine.
- `custom_components/xiaomi_miot/core/xiaomi_p2p/manager.py` — entry sessions, generation-bound leases, idle timers, reconnect ownership, snapshots, and shutdown.
- `custom_components/xiaomi_miot/diagnostics.py` — sanitized config-entry diagnostics.

**Modify integration points**

- `custom_components/xiaomi_miot/core/xiaomi_cloud.py:220-273` — add the dedicated MISS adapter without changing `async_request_api()`.
- `custom_components/xiaomi_miot/core/device.py:197-223,337-354,399-511` — preflight after spec load, profile resolution, and lens converter expansion.
- `custom_components/xiaomi_miot/core/hass_entry.py:20-50,90-99` — capability cache, manager/server ownership, task tracking, and unload ordering.
- `custom_components/xiaomi_miot/camera.py:277-340` — native activation, HLS-only provider behavior, stable source URL, and event suppression only for eligible converter-backed entities.
- `custom_components/xiaomi_miot/core/device_customizes.py` — add the three `p2p_overrides` profiles.
- `custom_components/xiaomi_miot/__init__.py:225-352` — initialize integration-wide server/allocator state and preserve account/local setup boundaries.
- `custom_components/xiaomi_miot/manifest.json` — declare direct crypto requirements.
- `requirements_test.txt` — install the same direct crypto requirements in tests.

**Create focused tests and support**

- `tests/helpers/xiaomi_p2p_clock.py`, `tests/helpers/xiaomi_p2p_peer.py`, `tests/helpers/fake_ffmpeg.py` — deterministic time, fake CS2 peers, and subprocess behavior.
- `tests/fixtures/xiaomi_p2p/` — sanitized crypto, framing, login, and media fixtures.
- `tests/test_xiaomi_p2p_cloud.py`
- `tests/test_xiaomi_p2p_crypto.py`
- `tests/test_xiaomi_p2p_cs2_protocol.py`
- `tests/test_xiaomi_p2p_cs2_udp.py`
- `tests/test_xiaomi_p2p_cs2_tcp.py`
- `tests/test_xiaomi_p2p_media.py`
- `tests/test_xiaomi_p2p_miss.py`
- `tests/test_xiaomi_p2p_fake_peer.py`
- `tests/test_xiaomi_p2p_rtp.py`
- `tests/test_xiaomi_p2p_server.py`
- `tests/test_xiaomi_p2p_bridge.py`
- `tests/test_xiaomi_p2p_manager.py`
- `tests/test_xiaomi_p2p_device.py`
- `tests/test_xiaomi_p2p_camera.py`
- `tests/test_xiaomi_p2p_entry.py`
- `tests/test_diagnostics.py`

---

### Task 1: Public Types, Profiles, Errors, and Crypto Dependencies

**Files:**
- Create: `custom_components/xiaomi_miot/core/xiaomi_p2p/__init__.py`
- Modify: `custom_components/xiaomi_miot/manifest.json:15-19`
- Modify: `requirements_test.txt:1-5`
- Test: `tests/test_xiaomi_p2p_types.py`

**Interfaces:**
- Produces: `MissErrorCategory`, `MissError`, `MissBootstrap`, `P2PProfile`, `MediaContract`, `NormalizedVideoFrame`, `NormalizedAudioFrame`, `SessionKey`, `SessionSnapshot`, `P2P_PROFILES`, and `DEFAULT_P2P_PROFILE`.
- `MissBootstrap` contains `host: str`, `p2p_id: str | None`, `client_private_key: bytes`, `client_public_key: bytes`, `device_public_key: bytes`, `signature: str`, and `vendor: int`; mark secret fields `repr=False`.
- `P2PProfile` contains `lenses: tuple[str, ...]`, `transport: Literal["auto", "prefer_udp", "prefer_tcp"]`, `raw_quality: int`, `request_audio: bool`, `required_video_codec: int | None`, and `required_audio_codec: int | None`.

- [ ] **Step 1: Write the failing immutable/redaction/profile tests**

```python
from dataclasses import FrozenInstanceError

from custom_components.xiaomi_miot.core.xiaomi_p2p import (
    DEFAULT_P2P_PROFILE,
    P2P_PROFILES,
    MissBootstrap,
)


def test_bootstrap_is_immutable_and_hides_secrets():
    bootstrap = MissBootstrap(
        host="192.168.1.20",
        p2p_id="peer",
        client_private_key=b"a" * 32,
        client_public_key=b"b" * 32,
        device_public_key=b"c" * 32,
        signature="signed-material",
        vendor=4,
    )
    text = repr(bootstrap)
    assert "signed-material" not in text
    assert "aaaaaaaa" not in text
    try:
        bootstrap.vendor = 3
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("MissBootstrap must be frozen")


def test_profiles_match_release_contract():
    assert DEFAULT_P2P_PROFILE.lenses == ("primary",)
    assert DEFAULT_P2P_PROFILE.transport == "auto"
    assert DEFAULT_P2P_PROFILE.raw_quality == 0
    assert DEFAULT_P2P_PROFILE.request_audio is True
    assert P2P_PROFILES["isa.camera.hlc7"].transport == "prefer_udp"
    assert P2P_PROFILES["isa.camera.hlc7"].raw_quality == 2
    assert P2P_PROFILES["chuangmi.camera.039c01"].transport == "prefer_tcp"
    assert P2P_PROFILES["mxiang.camera.c500ch"].lenses == ("primary", "secondary")
```

- [ ] **Step 2: Run the test to verify imports fail**

Run: `python -m pytest -q tests/test_xiaomi_p2p_types.py`

Expected: FAIL with `ModuleNotFoundError: custom_components.xiaomi_miot.core.xiaomi_p2p`.

- [ ] **Step 3: Add immutable types and exact release profiles**

```python
P2P_PROFILES = {
    "isa.camera.hlc7": P2PProfile(("primary",), "prefer_udp", 2, True, 5, 1027),
    "chuangmi.camera.039c01": P2PProfile(("primary",), "prefer_tcp", 2, True, 5, 1032),
    "mxiang.camera.c500ch": P2PProfile(
        ("primary", "secondary"), "auto", 0, True, None, None
    ),
}
DEFAULT_P2P_PROFILE = P2PProfile(("primary",), "auto", 0, True, None, None)
```

Define all listed dataclasses as `@dataclass(frozen=True, slots=True)` and define `MissError` with a required `category: MissErrorCategory`; exception text must contain only the category value and a non-sensitive detail supplied explicitly by the caller.

- [ ] **Step 4: Declare direct dependencies**

Add `"PyNaCl>=1.5.0"` and `"pycryptodome>=3.20.0"` to `manifest.json` requirements and matching lines to `requirements_test.txt`. PyNaCl supplies NaCl-compatible `crypto_box_beforenm`; PyCryptodome supplies the 12-byte-nonce ChaCha20 variant. Before continuing to Task 2, run this clean import gate with the same Python interpreter used by CI:

```bash
python3 -m venv /tmp/xiaomi-miss-crypto
/tmp/xiaomi-miss-crypto/bin/pip install "PyNaCl>=1.5.0" "pycryptodome>=3.20.0"
/tmp/xiaomi-miss-crypto/bin/python -c "from nacl.bindings import crypto_box_beforenm; from Crypto.Cipher import ChaCha20"
```

Expected: all commands exit 0. Remove `/tmp/xiaomi-miss-crypto` after recording the result; do not add upper bounds unless this gate demonstrates a concrete incompatibility.

- [ ] **Step 5: Run the focused test**

Run: `python -m pytest -q tests/test_xiaomi_p2p_types.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add custom_components/xiaomi_miot/core/xiaomi_p2p/__init__.py custom_components/xiaomi_miot/manifest.json requirements_test.txt tests/test_xiaomi_p2p_types.py
git commit -m "🔐 add MISS public types and crypto dependencies"
```

---

### Task 2: Cloud Bootstrap and Setup-Time Vendor Cache

**Files:**
- Create: `custom_components/xiaomi_miot/core/xiaomi_p2p/cloud.py`
- Modify: `custom_components/xiaomi_miot/core/xiaomi_cloud.py:220-273`
- Modify: `custom_components/xiaomi_miot/core/hass_entry.py:20-35`
- Test: `tests/test_xiaomi_p2p_cloud.py`

**Interfaces:**
- Produces: `async_resolve_lan_host(host: str) -> str`, `MiotCloud.async_miss_get_vendor(did: str, host: str, deadline: float) -> MissBootstrap`, and `P2PCapabilityCache.get_or_probe(entry_id, region, did, probe) -> int`.
- Consumes: `MiotCloud.async_request_api()` with `debug=False`, `raise_timeout=True`, and `timeout=min(10, deadline-loop.time())`.

- [ ] **Step 1: Write host-validation and adapter tests**

```python
@pytest.mark.parametrize(
    "host",
    ["", "not a host", "8.8.8.8", "127.0.0.1", "169.254.1.2", "::1", "224.0.0.1"],
)
async def test_invalid_host_stops_before_cloud_or_socket(host, cloud):
    cloud.async_request_api = AsyncMock()
    with pytest.raises(MissError, match="lan_host_unavailable"):
        await cloud.async_miss_get_vendor("did-redacted", host, monotonic() + 24)
    cloud.async_request_api.assert_not_awaited()


async def test_vendor_adapter_uses_existing_request_path(cloud, monkeypatch):
    cloud.async_request_api = AsyncMock(return_value={
        "code": 0,
        "result": {
            "vendor": {"vendor": 4, "vendor_params": {"p2p_id": "peer"}},
            "public_key": "11" * 32,
            "sign": "signature",
        },
    })
    bootstrap = await cloud.async_miss_get_vendor(
        "did-redacted", "192.168.1.20", monotonic() + 24
    )
    assert bootstrap.vendor == 4
    cloud.async_request_api.assert_awaited_once()
    _, kwargs = cloud.async_request_api.await_args
    assert kwargs["debug"] is False
    assert kwargs["raise_timeout"] is True
    assert 0 < kwargs["timeout"] <= 10
```

Also cover one DNS result, ambiguous/private+public results, malformed key lengths, vendor other than 4, one auth refresh/retry using the same key pair, second auth failure, timeout, and a mocked `async_request_api()` raising `CancelledError` without an adapter catch.

- [ ] **Step 2: Verify failure**

Run: `python -m pytest -q tests/test_xiaomi_p2p_cloud.py`

Expected: FAIL because the adapter and cache do not exist.

- [ ] **Step 3: Implement numeric/DNS host pinning and thin adapter**

Use `ipaddress.ip_address()` and one executor-backed `socket.getaddrinfo()` call. Accept exactly one distinct RFC1918 IPv4 result; reject loopback, link-local, multicast, unspecified, public, IPv6, and ambiguous results. Generate one `nacl.public.PrivateKey` and one immutable request body, send its public key as lowercase hex, and parse only the fields required by `MissBootstrap`. If `cloud.is_token_expired(response)` is true, call `cloud.async_check_auth()` exactly once, recompute the remaining deadline, and retry exactly once with the same key pair and request body; stop on refresh failure, insufficient remaining budget, or a second auth failure. Do not log arguments or returned values in the adapter. If a mocked `async_request_api()` raises `CancelledError`, let it propagate; do not claim propagation when the existing method internally consumes cancellation and returns `None`.

- [ ] **Step 4: Implement process-local cache**

Store `dict[tuple[str, str, str], tuple[float, int]]` in one integration-wide `P2PCapabilityCache` under `hass.data[DOMAIN]`; expose it to each `HassEntry` without copying entries. Use `hass.loop.time()` and TTL `86400`. Cache only successful vendor integers. Add `invalidate_entry(entry_id)` and call it from entry reload/unload integration in Task 15.

- [ ] **Step 5: Run cloud tests**

Run: `python -m pytest -q tests/test_xiaomi_p2p_cloud.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add custom_components/xiaomi_miot/core/xiaomi_p2p/cloud.py custom_components/xiaomi_miot/core/xiaomi_cloud.py custom_components/xiaomi_miot/core/hass_entry.py tests/test_xiaomi_p2p_cloud.py
git commit -m "🔐 add MISS cloud bootstrap and capability cache"
```

---

### Task 3: MISS Cryptography

**Files:**
- Create: `custom_components/xiaomi_miot/core/xiaomi_p2p/crypto.py`
- Create: `tests/fixtures/xiaomi_p2p/crypto_vectors.json`
- Test: `tests/test_xiaomi_p2p_crypto.py`

**Interfaces:**
- Produces: `generate_key_pair() -> tuple[bytes, bytes]`, `derive_shared_key(private_key: bytes, peer_public_key: bytes) -> bytes`, `miss_encode(key: bytes, plaintext: bytes, nonce8: bytes | None = None) -> bytes`, and `miss_decode(key: bytes, payload: bytes) -> bytes`.

- [ ] **Step 1: Add sanitized fixed-vector tests**

```python
def test_miss_nonce_layout_and_round_trip(monkeypatch):
    key = bytes(range(32))
    nonce8 = bytes.fromhex("0102030405060708")
    encoded = miss_encode(key, b"miss command", nonce8=nonce8)
    assert encoded[:8] == nonce8
    assert miss_decode(key, encoded) == b"miss command"


def test_miss_decode_rejects_short_nonce():
    with pytest.raises(MissError, match="crypto_input_invalid"):
        miss_decode(bytes(32), b"1234567")
```

The JSON fixture must contain only fixed synthetic private/public keys, expected 32-byte precomputed key, nonce, plaintext, and ciphertext.

- [ ] **Step 2: Verify failure**

Run: `python -m pytest -q tests/test_xiaomi_p2p_crypto.py`

Expected: FAIL because `crypto.py` does not exist.

- [ ] **Step 3: Implement NaCl-compatible derivation and ChaCha20**

Call `nacl.bindings.crypto_box_beforenm(peer_public_key, private_key)` for X25519 plus HSalsa20. For MISS encryption, prepend a random eight-byte prefix, construct the PyCryptodome nonce as `b"\x00\x00\x00\x00" + nonce8`, call `cipher.seek(0)` so encryption begins at counter zero, and return `nonce8 + cipher.encrypt(plaintext)`. Validate all key and nonce lengths before invoking libraries.

- [ ] **Step 4: Run crypto tests**

Run: `python -m pytest -q tests/test_xiaomi_p2p_crypto.py`

Expected: PASS for derivation, encode/decode, malformed lengths, and fixed vectors.

- [ ] **Step 5: Commit**

```bash
git add custom_components/xiaomi_miot/core/xiaomi_p2p/crypto.py tests/fixtures/xiaomi_p2p/crypto_vectors.json tests/test_xiaomi_p2p_crypto.py
git commit -m "🔐 add MISS cryptographic primitives"
```

---

### Task 4: Typed CS2 Framing and Bounded Stream Parser

**Files:**
- Create: `custom_components/xiaomi_miot/core/xiaomi_p2p/cs2/__init__.py`
- Create: `custom_components/xiaomi_miot/core/xiaomi_p2p/cs2/protocol.py`
- Create: `custom_components/xiaomi_miot/core/xiaomi_p2p/cs2/transport.py`
- Create: `tests/fixtures/xiaomi_p2p/cs2_frames.json`
- Test: `tests/test_xiaomi_p2p_cs2_protocol.py`

**Interfaces:**
- Produces: `Cs2Command(command_id: int, payload: bytes)`, `Cs2MediaPacket(header: bytes, encrypted_body: bytes)`, `encode_outbound_cs2_command()`, `decode_inbound_cs2_command()`, `encode_outbound_miss_plaintext()`, `decode_miss_media_header()`, `sequence_distance()`, `BoundedDrwParser`, the exact `Cs2Transport` protocol from the design, and `Cs2Connector.connect(bootstrap, policy, deadline) -> Cs2Transport`.

- [ ] **Step 1: Write endian-asymmetry and bounds tests**

```python
def test_direction_specific_command_endianness():
    frame = encode_outbound_cs2_command(0x100, b"{}", sequence=0x1234)
    assert frame[6:8] == bytes.fromhex("1234")
    assert frame[12:16] == bytes.fromhex("00000100")
    inbound = decode_inbound_cs2_command(bytes.fromhex("01010000") + b"ok")
    assert inbound == Cs2Command(0x101, b"ok")


def test_start_media_plaintext_is_big_endian():
    assert encode_outbound_miss_plaintext(0x102, b"{}")[:4] == bytes.fromhex(
        "00000102"
    )
```

Also assert big-endian outer/payload lengths, little-endian media fields, input shorter than four bytes, partial/concatenated DRW frames, maximum message sizes, channel 0/2 separation, and 16-bit wraparound ordering.

- [ ] **Step 2: Verify failure**

Run: `python -m pytest -q tests/test_xiaomi_p2p_cs2_protocol.py`

Expected: FAIL because CS2 modules do not exist.

- [ ] **Step 3: Implement exact wire codecs**

Use `struct.Struct` objects with explicit `>` and `<` formats. Keep outbound encoding and inbound decoding as distinct functions. `BoundedDrwParser.feed()` must reject an advertised frame beyond its configured byte limit before allocating or retaining that body.

- [ ] **Step 4: Run protocol tests**

Run: `python -m pytest -q tests/test_xiaomi_p2p_cs2_protocol.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/xiaomi_miot/core/xiaomi_p2p/cs2 tests/fixtures/xiaomi_p2p/cs2_frames.json tests/test_xiaomi_p2p_cs2_protocol.py
git commit -m "🔧 add typed CS2 framing"
```

---

### Task 5: UDP Discovery, Peer Lock, Reliability, and Reordering

**Files:**
- Create: `custom_components/xiaomi_miot/core/xiaomi_p2p/cs2/discovery.py`
- Create: `custom_components/xiaomi_miot/core/xiaomi_p2p/cs2/udp.py`
- Create: `tests/helpers/xiaomi_p2p_clock.py`
- Create: `tests/helpers/xiaomi_p2p_peer.py`
- Test: `tests/test_xiaomi_p2p_cs2_udp.py`

**Interfaces:**
- Produces: `DefaultCs2Connector(Cs2Connector)` that owns one discovery exchange and returns an established `UdpCs2Transport` or `TcpCs2Transport` with `negotiated_mode` set.
- Produces: established `UdpCs2Transport(Cs2Transport)` with `read_command`, `write_command`, `read_media_packet`, and idempotent `close`; it performs no discovery itself.
- Hard bounds: five one-second sends, 250 reorder packets, 4 MiB reorder bytes, 10 commands, 100 media messages, and two-second non-extending gap deadlines.

- [ ] **Step 1: Write deterministic discovery and tuple-lock tests**

```python
async def test_auto_uses_one_discovery_and_locks_final_udp_peer(peer, bootstrap):
    peer.queue_udp_ready((bootstrap.host, 41000))
    connector = DefaultCs2Connector(clock=peer.clock, socket_factory=peer.socket_factory)
    transport = await connector.connect(bootstrap, "auto", peer.clock.now + 5)
    assert transport.negotiated_mode == "udp"
    assert isinstance(transport, UdpCs2Transport)
    assert peer.discovery_count == 1
    peer.inject_datagram((bootstrap.host, 41001), peer.valid_media_datagram())
    assert peer.ack_count == 0
    assert transport.rejected_peer_datagrams == 1
```

Cover auto UDP/TCP ready selection; `prefer_udp` receiving validated TCP-ready and `prefer_tcp` receiving validated UDP-ready as same-exchange negotiated fallback; intermediate port updates; final exact tuple lock; wrong IP/port isolation before parsing; endpoint immutability; ACKs; five retransmissions; queue overflow; in-order and future packets; duplicate ACKs; wraparound; non-extending gap timer; new gap after drain; packet/byte limit failure without ACK; and close unblocking every waiter.

- [ ] **Step 2: Verify failure**

Run: `python -m pytest -q tests/test_xiaomi_p2p_cs2_udp.py`

Expected: FAIL because `UdpCs2Transport` does not exist.

- [ ] **Step 3: Implement UDP state machine**

`DefaultCs2Connector` creates one unconnected discovery socket to port `32108` and pins the validated host from bootstrap. Encode `auto`, `prefer_udp`, or `prefer_tcp` in the discovery request, but accept either validated ready type as the final result of that single exchange. For UDP-ready, connect the existing socket to the final peer so the local port is retained and construct `UdpCs2Transport` around that socket. For TCP-ready, close discovery, open TCP to the pinned IP and validated source port, and construct `TcpCs2Transport` around the established streams. Neither concrete transport repeats discovery. Reject non-peer UDP datagrams before any frame, ACK, sequence, queue, gap, or stall mutation.

Run: `python -m pytest -q tests/test_xiaomi_p2p_cs2_udp.py -k "discovery or ready or peer"`

Expected: PASS for discovery, negotiated fallback, concrete transport handoff, peer lock, and wrong-peer isolation.

```bash
git add custom_components/xiaomi_miot/core/xiaomi_p2p/cs2/discovery.py custom_components/xiaomi_miot/core/xiaomi_p2p/cs2/udp.py tests/helpers/xiaomi_p2p_peer.py tests/test_xiaomi_p2p_cs2_udp.py
git commit -m "🔧 add CS2 discovery and transport handoff"
```

- [ ] **Step 4: Implement wraparound reorder and gap failure**

Keep `next_sequence`, a copied-payload dictionary, total retained bytes, and one deadline task. On deadline or bound failure, raise `MissError(sequence_gap)`, close transport, and clear reorder/parser/queue state without scanning later bytes.

- [ ] **Step 5: Run UDP tests**

Run: `python -m pytest -q tests/test_xiaomi_p2p_cs2_udp.py`

Expected: PASS without real sleeps.

- [ ] **Step 6: Commit**

```bash
git add custom_components/xiaomi_miot/core/xiaomi_p2p/cs2/udp.py tests/helpers/xiaomi_p2p_clock.py tests/helpers/xiaomi_p2p_peer.py tests/test_xiaomi_p2p_cs2_udp.py
git commit -m "🔧 add bounded CS2 UDP transport"
```

---

### Task 6: TCP Transport

**Files:**
- Create: `custom_components/xiaomi_miot/core/xiaomi_p2p/cs2/tcp.py`
- Test: `tests/test_xiaomi_p2p_cs2_tcp.py`

**Interfaces:**
- Produces: established `TcpCs2Transport(Cs2Transport)` using the bounded parser after `DefaultCs2Connector` completes the single discovery exchange and TCP handoff.

- [ ] **Step 1: Write TCP-ready, partial-frame, ping, and close tests**

```python
async def test_tcp_ready_cannot_redirect_ip(peer, bootstrap):
    peer.queue_tcp_ready(("192.168.1.99", 41000))
    connector = DefaultCs2Connector(clock=peer.clock, socket_factory=peer.socket_factory)
    with pytest.raises(MissError, match="cs2_discovery_invalid"):
        await connector.connect(bootstrap, "prefer_tcp", peer.clock.now + 5)
    assert peer.tcp_connects == []
```

Also feed one frame byte-by-byte, concatenate frames in one read, assert command/media separation, emit DRW ping at most once per second while processing traffic, propagate EOF distinctly, and prove idempotent close unblocks readers/writers.

- [ ] **Step 2: Verify failure**

Run: `python -m pytest -q tests/test_xiaomi_p2p_cs2_tcp.py`

Expected: FAIL because `TcpCs2Transport` does not exist.

- [ ] **Step 3: Implement TCP transport**

Construct `TcpCs2Transport` only from reader/writer streams already established by `DefaultCs2Connector`; it performs no discovery and cannot select or redirect an endpoint. Feed ordered bytes directly to `BoundedDrwParser`, and schedule no independent keepalive.

- [ ] **Step 4: Run TCP tests and commit**

Run: `python -m pytest -q tests/test_xiaomi_p2p_cs2_tcp.py`

Expected: PASS.

```bash
git add custom_components/xiaomi_miot/core/xiaomi_p2p/cs2/tcp.py tests/test_xiaomi_p2p_cs2_tcp.py
git commit -m "🔧 add bounded CS2 TCP transport"
```

---

### Task 7: Media Parsing, Contracts, and Timestamp Normalization

**Files:**
- Create: `custom_components/xiaomi_miot/core/xiaomi_p2p/media.py`
- Create: `tests/fixtures/xiaomi_p2p/media_frames.json`
- Test: `tests/test_xiaomi_p2p_media.py`

**Interfaces:**
- Produces: `MediaHeader`, `MediaProbe`, `AccessUnitAssembler`, `TimestampNormalizer`, and immutable normalized frames.
- Supports codec IDs `4`, `5`, `1027`, and `1032`; bounds incomplete assembly at 8 MiB per track.

- [ ] **Step 1: Write codec, access-unit, contract, and clock tests**

```python
def test_media_contract_equality_ignores_transport_and_timestamps():
    first = make_contract(video_codec=4, width=1920, height=1080, audio_codec=1027)
    same = replace(first)
    assert first == same


def test_stall_clock_advances_only_for_complete_video(probe, clock):
    probe.publish_complete_keyframe(clock.now)
    initial = probe.last_complete_video_at
    probe.accept_audio(make_pcma_frame())
    probe.accept_incomplete_video(make_delta_fragment())
    assert probe.last_complete_video_at == initial
```

Cover media-header offsets/endianness, SPS/PPS and VPS/SPS/PPS discovery, complete keyframes, parameter fingerprints, dimensions, PCMA 8/16 kHz flags, Opus `48000/2`, incompatible Opus video-only fallback, optional two-second audio wait, all contract equality fields, monotonic recovery after camera timestamp reset, and overflow.

- [ ] **Step 2: Verify failure**

Run: `python -m pytest -q tests/test_xiaomi_p2p_media.py`

Expected: FAIL because `media.py` does not exist.

- [ ] **Step 3: Implement bounded parsers and immutable contracts**

Parse Annex-B start codes without retaining unbounded input. Cache only current parameter sets and one complete keyframe. Fingerprint parameter sets with SHA-256 and keep bytes private to the session. Normalize recovered media strictly after the last emitted media time.

- [ ] **Step 4: Run media tests and commit**

Run: `python -m pytest -q tests/test_xiaomi_p2p_media.py`

Expected: PASS.

```bash
git add custom_components/xiaomi_miot/core/xiaomi_p2p/media.py tests/fixtures/xiaomi_p2p/media_frames.json tests/test_xiaomi_p2p_media.py
git commit -m "📹 add MISS media parsing and contracts"
```

---

### Task 8: MISS Login, Commands, Session Probe, and Recovery

**Files:**
- Create: `custom_components/xiaomi_miot/core/xiaomi_p2p/miss.py`
- Create: `tests/fixtures/xiaomi_p2p/miss_commands.json`
- Test: `tests/test_xiaomi_p2p_miss.py`
- Test: `tests/test_xiaomi_p2p_fake_peer.py`

**Interfaces:**
- Produces: `MissSession.connect_and_start(deadline) -> MediaContract`, `subscribe(generation)`, `soft_restart(deadline)`, `reconnect(deadline)`, `stop_media()`, and `close()`.
- Consumes: fresh bootstrap factory for every full reconnect and one `Cs2Connector` that returns an already-established concrete transport after the single discovery exchange.

- [ ] **Step 1: Write exact login/start command tests**

```python
@pytest.mark.parametrize(
    ("lens", "quality", "expected"),
    [
        ("primary", 0, {"videoquality": 0, "enableaudio": 1}),
        (
            "secondary",
            0,
            {"videoquality": -1, "videoquality2": 0, "enableaudio": 1},
        ),
    ],
)
async def test_start_media_payload(lens, quality, expected, session):
    await session.start_media(lens=lens, raw_quality=quality, request_audio=True)
    assert session.transport.last_decrypted_json == expected
```

Cover plaintext `0x100` login, encrypted `0x1001` commands, command ID `0x102`, stop-media, generic quality rejection category, mandatory profile codecs, optional audio, unknown valid message counting, malformed state termination, and cancellation without reconnect.

- [ ] **Step 2: Write recovery/fake-peer tests**

Drive UDP and TCP peers through discovery, login, probe, gap failure, disconnect, timestamp reset, matching contracts, each individual contract-field change, audio-only video stall, one soft restart, five-second keyframe reprobe, one full-reconnect owner, and backoffs `1, 2, 5, 15, 30` while a lease remains active.

- [ ] **Step 3: Verify failure**

Run: `python -m pytest -q tests/test_xiaomi_p2p_miss.py tests/test_xiaomi_p2p_fake_peer.py`

Expected: FAIL because `MissSession` does not exist.

- [ ] **Step 4: Implement session state and publication gate**

Login in plaintext, derive the shared key after accepted login, encrypt later commands, decrypt media bodies while retaining plaintext headers, and publish no candidate frame until the complete contract/keyframe gate succeeds. Matching recovery retains generation and timestamp continuity; mismatch emits `codec_contract_changed` to old subscriptions before adopting a new generation.

Run: `python -m pytest -q tests/test_xiaomi_p2p_miss.py -k "login or command or start_media or initial_probe"`

Expected: PASS for login, encrypted commands, lens/quality payloads, and initial contract publication.

```bash
git add custom_components/xiaomi_miot/core/xiaomi_p2p/miss.py tests/fixtures/xiaomi_p2p/miss_commands.json tests/test_xiaomi_p2p_miss.py
git commit -m "📹 add MISS login and initial media probe"
```

- [ ] **Step 5: Implement serialized recovery**

Start stall timing only after the first published complete keyframe. Permit one stop/start attempt per stall episode. Send gap failures directly to full reconnect. Reset backoff and soft-restart allowance only after a contract and complete keyframe publish successfully. Do not recover without an active lease.

- [ ] **Step 6: Run session tests and commit**

Run: `python -m pytest -q tests/test_xiaomi_p2p_miss.py tests/test_xiaomi_p2p_fake_peer.py`

Expected: PASS.

```bash
git add custom_components/xiaomi_miot/core/xiaomi_p2p/miss.py tests/fixtures/xiaomi_p2p/miss_commands.json tests/test_xiaomi_p2p_miss.py tests/test_xiaomi_p2p_fake_peer.py
git commit -m "📹 add MISS session and recovery"
```

---

### Task 9: RTP, RTCP, and SDP

**Files:**
- Create: `custom_components/xiaomi_miot/core/xiaomi_p2p/rtp.py`
- Test: `tests/test_xiaomi_p2p_rtp.py`

**Interfaces:**
- Produces: immutable `RtpPacket(payload: bytes, marker: bool, sequence: int, timestamp: int, ssrc: int)` with `to_bytes() -> bytes`, plus `RtpTrack`, `RtpPacketizer`, `RtcpSender`, and `build_sdp(contract, ports, parameter_sets) -> str`.
- Payloads: H.264 `96`, H.265 `98`, PCMA 8 kHz `8`, PCMA 16 kHz `97`, Opus `111`.

- [ ] **Step 1: Write packet and SDP tests**

```python
@pytest.mark.parametrize("codec", [4, 5])
def test_video_packets_never_exceed_1200_bytes(codec):
    packets = packetize_video(codec, b"\x00\x00\x00\x01" + b"x" * 5000)
    assert packets
    assert max(len(packet.to_bytes()) for packet in packets) <= 1200
    assert packets[-1].marker is True


def test_pcma_payload_mapping():
    assert payload_mapping(audio_codec=1027, sample_rate=8000) == (8, "PCMA/8000/1")
    assert payload_mapping(audio_codec=1027, sample_rate=16000) == (97, "PCMA/16000/1")
```

Cover single/fragmented H.264 RFC 6184 and H.265 RFC 7798 packets, Opus RFC 7587, marker bits, sequence wrap, independent SSRCs, common media/NTP origins, first and five-second compound sender reports, packet/octet counters, and exact codec SDP attributes.

- [ ] **Step 2: Verify failure**

Run: `python -m pytest -q tests/test_xiaomi_p2p_rtp.py`

Expected: FAIL because `rtp.py` does not exist.

- [ ] **Step 3: Implement packetization and SDP**

Subtract RTP and codec fragmentation headers from the 1200-byte datagram ceiling. Use a common normalized media origin but scale video to 90 kHz, PCMA to detected sample rate, and Opus to 48 kHz. Generate session `c=IN IP4 127.0.0.1`, `t=0 0`, per-track `a=rtcp`, and exact parameter-set attributes.

- [ ] **Step 4: Run RTP tests and commit**

Run: `python -m pytest -q tests/test_xiaomi_p2p_rtp.py`

Expected: PASS.

```bash
git add custom_components/xiaomi_miot/core/xiaomi_p2p/rtp.py tests/test_xiaomi_p2p_rtp.py
git commit -m "📹 add RTP packetization and SDP"
```

---

### Task 10: Loopback Server and RTP Port Allocator

**Files:**
- Create: `custom_components/xiaomi_miot/core/xiaomi_p2p/server.py`
- Test: `tests/test_xiaomi_p2p_server.py`

**Interfaces:**
- Produces: `LoopbackMediaServer.acquire_entry()`, `release_entry()`, `add_route(handler) -> RouteHandle`, `remove_route(route_id)`, and `RtpPortAllocator.acquire(track_count) -> PortLease`.
- The wildcard handler owns route/auth and pre-bridge lease-limit outcomes: route/auth failure → 404; `active_source_limit` → 503 plus `Retry-After: 5`. After handing an accepted lease to `MediaBridge.run(request)`, the bridge exclusively owns HTTP preparation, startup 502/504 mapping, post-200 EOF, and response cleanup. The handler always awaits the shielded bridge `close_future`.
- `RouteHandle.url` is stable for the mapping lifetime; token and URL are excluded from `repr` and snapshots.

- [ ] **Step 1: Write real-server auth and binding tests**

```python
async def test_route_auth_and_redaction(server, aiohttp_client, monkeypatch):
    monkeypatch.setattr(secrets, "token_bytes", lambda size: b"r" * size)
    monkeypatch.setattr(secrets, "token_urlsafe", lambda size: "token-value")
    route = server.add_route(AsyncMock(return_value=web.Response(text="ok")))
    assert "token-value" not in repr(route)
    assert (await server.client.get(route.path)).status == 404
    assert (await server.client.get(route.url)).status == 200
```

Assert one wildcard route, `127.0.0.1` binding, 404 for unknown/invalid/unloaded routes, constant-time token comparison, disabled access logging, sanitized forced exceptions, one site/runner across references, final shutdown, non-overlapping even RTP/following RTCP pairs, and logical lease retention until release. Patch the route entropy source and assert each opaque URL-safe route ID decodes to exactly 16 source bytes, differs across calls, and contains no DID/model/lens material. Add end-to-end handler tests for route/auth 404 and lease-limit 503 with `Retry-After: 5`; after accepted handoff, assert the handler delegates the request to one bridge and awaits its shielded `close_future` without preparing or writing the response itself.

- [ ] **Step 2: Verify failure**

Run: `python -m pytest -q tests/test_xiaomi_p2p_server.py`

Expected: FAIL because `server.py` does not exist.

- [ ] **Step 3: Implement server and allocator**

Register `GET /xiaomi_miot/p2p/{route_id}` before `AppRunner.setup()`. Keep mappings in a dictionary; mutate no router after startup. Return 404 for every auth/mapping failure. Reserve port pairs with loopback sockets under one async lock, close reservation sockets immediately before FFmpeg spawn, and retain the logical lease until the process and pipes are finished.

- [ ] **Step 4: Run server tests and commit**

Run: `python -m pytest -q tests/test_xiaomi_p2p_server.py`

Expected: PASS.

```bash
git add custom_components/xiaomi_miot/core/xiaomi_p2p/server.py tests/test_xiaomi_p2p_server.py
git commit -m "🔐 add authenticated loopback media server"
```

---

### Task 11: Per-GET FFmpeg Bridge and Ordered Close State Machine

**Files:**
- Create: `custom_components/xiaomi_miot/core/xiaomi_p2p/bridge.py`
- Create: `tests/helpers/fake_ffmpeg.py`
- Test: `tests/test_xiaomi_p2p_bridge.py`

**Interfaces:**
- Produces: `BridgeState`, `BridgeCloseResult`, and `MediaBridge.run(request)` with one shielded `close_future`; `run()` derives the 24-second setup and 25-second response deadlines from handler entry and does not accept caller-supplied deadlines.
- `MediaBridge` is the exclusive response owner after lease handoff: non-timeout startup failure and startup contract change → 502; setup deadline → 504; first bounded chunk → prepare 200 and write it; terminal condition after 200 → EOF/abort without another status.
- Consumes: generation-bound session lease, `RtpPortAllocator`, configured `hass.data[DATA_FFMPEG].binary`, and `aiohttp.web.Request`.

- [ ] **Step 1: Define pytest fixtures and write exact command and first-chunk gate tests**

Add the following fixtures at the top of `tests/test_xiaomi_p2p_bridge.py` so subsequent steps can reuse them:

```python
import asyncio

import pytest


@pytest.fixture
def fake_ffmpeg():
    process = SimpleNamespace(
        returncode=None,
        started=asyncio.Event(),
        stdout=FakePipe(),
        stderr=FakePipe(),
        configure=lambda *args, **kwargs: process._configured(args, **kwargs),
        _configured=lambda args, kwargs: None,
        wait=AsyncMock(),
        terminate=lambda: None,
        kill=lambda: None,
    )
    yield process


class FakePipe:
    def __init__(self):
        self._chunks = asyncio.Queue()
        self.closed = False

    def feed(self, chunk: bytes) -> None:
        self._chunks.put_nowait(chunk)

    async def read(self, _n: int) -> bytes:
        if self.closed and self._chunks.empty():
            return b""
        return await self._chunks.get()

    def close(self) -> None:
        self.closed = True
        self._chunks.put_nowait(b"")


@pytest.fixture
def bridge(fake_ffmpeg):
    handle = SimpleNamespace(
        request=SimpleNamespace(),
        process=fake_ffmpeg,
        response=SimpleNamespace(prepared=False, status=None, writes=[]),
        close_future=asyncio.get_event_loop().create_future(),
    )
    yield handle
```

Then add the first-chunk gate test:

```python
EXPECTED_FFMPEG_ARGS = (
    "-hide_banner", "-loglevel", "warning",
    "-protocol_whitelist", "pipe,udp,rtp",
    "-f", "sdp", "-i", "pipe:0",
    "-map", "0:v:0", "-c:v", "copy",
    "-map", "0:a:0?", "-c:a", "aac", "-b:a", "64k",
    "-f", "mpegts", "-mpegts_flags", "+resend_headers", "pipe:1",
)

async def test_http_200_waits_for_first_mpegts_chunk(bridge, fake_ffmpeg):
    task = asyncio.create_task(bridge.run(bridge.request))
    await fake_ffmpeg.started.wait()
    assert bridge.response.prepared is False
    fake_ffmpeg.stdout.feed(b"first-ts-chunk")
    await task
    assert bridge.response.status == 200
    assert bridge.response.writes[0] == b"first-ts-chunk"
```

Cover configured binary, SDP stdin closure, stdout/stderr single-reader ownership, 24/25-second boundaries, 502/504, delayed/failing prepare/write/write_eof, client cancellation, non-blocking RTP drops, three bind/start attempts only with budget, no HTTP 200 before first chunk, early exit, five-second terminate, two-second kill, drain-to-EOF, and port/session lease ordering.

- [ ] **Step 2: Write close-race and partial-acquisition tests**

Trigger disconnect, FFmpeg exit, contract change, handler cancellation, Home Assistant stop, and unload concurrently. Assert one transition to `CLOSING`, one close task, first terminal reason retained, every waiter receives the same immutable result, cancelled waiter does not cancel cleanup, and failure after each acquisition releases only owned resources in the specified order.

- [ ] **Step 3: Verify failure**

Run: `python -m pytest -q tests/test_xiaomi_p2p_bridge.py`

Expected: FAIL because bridge support does not exist.

- [ ] **Step 4: Implement startup attempts and streaming**

Derive both monotonic deadlines from handler entry. Before each stage compute `min(stage_cap, setup_deadline-now)` and reject a stage that consumes the final five-second FFmpeg reserve. Start FFmpeg with the exact arguments, write/close SDP stdin, start one stdout and one stderr owner, then attach cached parameter sets/keyframe. Prepare HTTP 200 only after the stdout owner reports its first bounded chunk.

Run: `python -m pytest -q tests/test_xiaomi_p2p_bridge.py -k "startup or first_chunk or deadline or ffmpeg_command or bind"`

Expected: PASS for startup attempts, exact FFmpeg invocation, first-chunk gate, and 24/25-second response behavior.

```bash
git add custom_components/xiaomi_miot/core/xiaomi_p2p/bridge.py tests/helpers/fake_ffmpeg.py tests/test_xiaomi_p2p_bridge.py
git commit -m "📹 add FFmpeg bridge startup and deadlines"
```

- [ ] **Step 5: Implement ordered idempotent close**

Under one state lock, let the first terminal trigger create the entry-tracked close task. Detach frame delivery and RTP producer; terminate/abort HTTP; close RTP sockets; terminate then kill FFmpeg while the original pipe owners drain; release logical ports; release the session lease exactly once in the outermost `finally`; then set `CLOSED` and resolve `close_future`.

- [ ] **Step 6: Run bridge tests and commit**

Run: `python -m pytest -q tests/test_xiaomi_p2p_bridge.py`

Expected: PASS.

```bash
git add custom_components/xiaomi_miot/core/xiaomi_p2p/bridge.py tests/helpers/fake_ffmpeg.py tests/test_xiaomi_p2p_bridge.py
git commit -m "📹 add bounded FFmpeg media bridge"
```

---

### Task 12: Entry-Owned Session Manager, Leases, Generations, and Idle Timer

**Files:**
- Create: `custom_components/xiaomi_miot/core/xiaomi_p2p/manager.py`
- Modify: `custom_components/xiaomi_miot/core/hass_entry.py:20-35`
- Modify: `custom_components/xiaomi_miot/__init__.py:343-352`
- Test: `tests/test_xiaomi_p2p_manager.py`

**Interfaces:**
- Produces: `ChannelSessionManager.acquire(key, deadline) -> SessionLease`, `release(lease)`, `snapshot()`, `close_bridges()`, and `async_close()`.
- Produces: `HassEntry.async_ensure_p2p() -> ChannelSessionManager`, `track_bridge_close_task()`, and `untrack_bridge_close_task()` backed by one integration-wide `LoopbackMediaServer`, `RtpPortAllocator`, and `P2PCapabilityCache`.
- Session key includes entry ID, region, DID, lens, raw quality, transport preference, and audio policy.

- [ ] **Step 1: Write sharing, isolation, and lease-limit tests**

```python
async def test_four_gets_share_session_and_fifth_is_rejected(manager, key):
    leases = [await manager.acquire(key, deadline=100) for _ in range(4)]
    assert len({id(lease.session) for lease in leases}) == 1
    with pytest.raises(MissError, match="active_source_limit"):
        await manager.acquire(key, deadline=100)


async def test_lenses_use_independent_sessions(manager, primary_key):
    primary = await manager.acquire(primary_key, deadline=100)
    secondary = await manager.acquire(replace(primary_key, lens="secondary"), deadline=100)
    assert primary.session is not secondary.session
```

Cover entry/region isolation, generation capture, mismatch invalidation, compatible continuation, exact-once release, idle timer only after final release, no stop-media at release, reuse within 30 seconds with video newer than 10 seconds, immediate recovery when stale, timer expiry stop/close/remove, no recovery without lease, and `keep_streaming` absence from keys/behavior. Also assert that `async_ensure_p2p()` lazily creates one manager and one server reference per eligible entry, repeated calls reuse them, and entries without an eligible device never acquire either resource.

- [ ] **Step 2: Verify failure**

Run: `python -m pytest -q tests/test_xiaomi_p2p_manager.py`

Expected: FAIL because manager support does not exist.

- [ ] **Step 3: Implement manager ownership**

Serialize creation per key, maintain active lease counts and bridge registrations, and make release the sole idle-timer start point. On contract mismatch, invalidate old-generation subscriptions before adopting the candidate for later acquisitions. Build snapshots only from approved non-sensitive fields. Initialize the integration-wide server, allocator, and capability cache in `init_integration_data()`; implement `HassEntry.async_ensure_p2p()` as the sole lazy manager/server-reference constructor so Tasks 13 and 14 consume established production interfaces rather than temporary mocks.

- [ ] **Step 4: Run manager tests and commit**

Run: `python -m pytest -q tests/test_xiaomi_p2p_manager.py`

Expected: PASS.

```bash
git add custom_components/xiaomi_miot/core/xiaomi_p2p/manager.py custom_components/xiaomi_miot/core/hass_entry.py custom_components/xiaomi_miot/__init__.py tests/test_xiaomi_p2p_manager.py
git commit -m "📹 add entry-owned P2P session management"
```

---

### Task 13: Device Eligibility, Overrides, and Dual-Lens Converter Expansion

**Files:**
- Modify: `custom_components/xiaomi_miot/core/device.py:197-223,337-354,399-511`
- Modify: `custom_components/xiaomi_miot/core/device_customizes.py`
- Modify: `tests/conftest.py:36-79`
- Create: `tests/test_xiaomi_p2p_device.py`
- Create: `tests/fixtures/isa.camera.hlc7.json`
- Create: `tests/fixtures/chuangmi.camera.039c01.json`
- Create: `tests/fixtures/mxiang.camera.c500ch.json`
- Create: `tests/fixtures/generic.camera.p2p.json`

**Interfaces:**
- Produces on `Device`: `p2p_profile: P2PProfile | None`, `p2p_vendor: int | None`, `p2p_enabled: bool`, and `p2p_lens: str` converter option.
- Consumes only `self.entry`, `self.cloud`, `self.did`, `self.info.host`, `self.spec.get_service("p2p_stream")`, and the entry capability cache.

- [ ] **Step 1: Write eligibility matrix tests**

```python
@pytest.mark.parametrize("conn_mode", ["local", "auto", "cloud"])
async def test_account_candidate_activates_after_vendor_four(make_p2p_device, conn_mode):
    device = await make_p2p_device(
        "generic.camera.p2p.json", account=True, conn_mode=conn_mode, vendor=4
    )
    assert device.p2p_enabled is True
    assert device.p2p_profile == DEFAULT_P2P_PROFILE


async def test_host_token_candidate_never_preflights(make_p2p_device):
    device = await make_p2p_device(
        "generic.camera.p2p.json", account=False, vendor=4
    )
    assert device.p2p_enabled is False
    device.entry.capability_cache.get_or_probe.assert_not_awaited()
```

Cover an empty `p2p-stream` service, no marker, vendor non-4, failed preflight without caching, no app-config call, no `MiotCloud.all_clouds()`, shared DID isolation, default profile, exact overrides, ignored support-config fields, generic raw-quality rejection behavior, and unchanged `resolution-types` handling.

- [ ] **Step 2: Write dual-lens identity tests**

Assert `mxiang.camera.c500ch` creates two camera converters; primary preserves the existing converter identity, secondary has a distinct `attr`, `full_name`, explicit unique-ID suffix, and `use_unique_attr=True`; converter and entity deduplication keep both, and both entities expose the same device registry identifiers.

- [ ] **Step 3: Verify failure**

Run: `python -m pytest -q tests/test_xiaomi_p2p_device.py`

Expected: FAIL because P2P eligibility and profiles are not integrated.

- [ ] **Step 4: Add exact model customizations**

```python
"isa.camera.hlc7": {
    "p2p_overrides": {
        "lenses": ["primary"], "transport": "prefer_udp", "raw_quality": 2,
        "request_audio": True, "required_video_codec": 5,
        "required_audio_codec": 1027,
    },
},
"chuangmi.camera.039c01": {
    "p2p_overrides": {
        "lenses": ["primary"], "transport": "prefer_tcp", "raw_quality": 2,
        "request_audio": True, "required_video_codec": 5,
        "required_audio_codec": 1032,
    },
},
"mxiang.camera.c500ch": {
    "p2p_overrides": {
        "lenses": ["primary", "secondary"], "transport": "auto",
        "raw_quality": 0, "request_audio": True,
    },
},
```

Merge these keys into existing exact model entries rather than replacing their current customization fields.

- [ ] **Step 5: Integrate preflight at async device initialization**

After `get_spec()` and before platform entity materialization, check account cloud ownership and `spec.get_service("p2p_stream")`; resolve cached/fresh vendor and set immutable per-device P2P state. Keep `init_converters()` synchronous by performing lens expansion only after async preflight and before adders can materialize entities.

- [ ] **Step 6: Run device tests and commit**

Run: `python -m pytest -q tests/test_xiaomi_p2p_device.py tests/test_converter_options.py`

Expected: PASS.

```bash
git add custom_components/xiaomi_miot/core/device.py custom_components/xiaomi_miot/core/device_customizes.py tests/conftest.py tests/test_xiaomi_p2p_device.py tests/fixtures/*.camera.*.json
git commit -m "📹 add P2P camera eligibility and lens profiles"
```

---

### Task 14: Converter-Backed Camera Activation and HLS-Only Behavior

**Files:**
- Modify: `custom_components/xiaomi_miot/camera.py:277-340`
- Create: `tests/test_xiaomi_p2p_camera.py`

**Interfaces:**
- Eligible `CameraEntity` consumes `device.p2p_enabled`, lens/profile options, entry manager, and a server route handle.
- Produces stable async `stream_source() -> str`, `CameraEntityFeature.STREAM`, HLS-only frontend stream type, and eligible-only provider suppression.

- [ ] **Step 1: Characterize Home Assistant Camera APIs and excluded paths**

Add the following compatibility gate at the top of `tests/test_xiaomi_p2p_camera.py` so subsequent steps can rely on the resolved base API surface:

```python
from homeassistant.components import camera as ha_camera


def test_ha_camera_base_apis_resolved():
    capabilities = getattr(ha_camera, "CameraEntityFeature", None)
    assert capabilities is not None
    assert callable(getattr(ha_camera.Camera, "async_refresh_providers", None))
    assert callable(
        getattr(ha_camera.Camera, "async_handle_async_webrtc_offer", None)
    )
    capabilities_module = getattr(ha_camera, "camera_capabilities", None)
    assert capabilities_module is not None
    assert hasattr(capabilities_module, "frontend_stream_types")
    assert hasattr(capabilities_module, "StreamType") or hasattr(
        capabilities_module, "CameraFrontendStreamType"
    )


def test_hass_frontend_stream_type_hls_only(p2p_camera, monkeypatch):
    # Production must advertise HLS but never WebRTC for eligible cameras.
    import homeassistant.components.camera as ha_camera_mod

    stream_types = ha_camera_mod.camera_capabilities.frontend_stream_types(
        p2p_camera
    )
    name = "HLS" if hasattr(ha_camera_mod.camera_capabilities, "StreamType") else "HLS"
    assert name in {getattr(s, "name", s) for s in stream_types}
```

Then in the installed pytest Home Assistant version, assert the base Camera provider refresh/capability behavior, the HLS frontend stream-type representation, entity-removal callback behavior, and FFmpeg manager lookup before changing production code. Then instantiate non-P2P converter-backed `CameraEntity`, `MiotCameraEntity`, `MotionCameraEntity`, and a test-only `BaseCameraEntity` subclass. Assert current stream features, cloud event calls, provider refresh, motion subentities, and `keep_streaming` behavior remain unchanged. Add a base-without-provider-refresh test double and require the non-P2P compatibility branch to no-op only when that base API is absent; do not claim the repository's Home Assistant `2023.7.0` configuration-validation job exercises these runtime APIs.

- [ ] **Step 2: Write eligible-camera behavior tests**

```python
async def test_p2p_stream_source_is_stable_and_side_effect_free(p2p_camera):
    first = await asyncio.wait_for(p2p_camera.stream_source(), timeout=1)
    second = await asyncio.wait_for(p2p_camera.stream_source(), timeout=1)
    assert first == second
    assert first.startswith("http://127.0.0.1:")
    p2p_camera.device.entry.manager.acquire.assert_not_awaited()
    p2p_camera.device.cloud.async_request_api.assert_not_awaited()
```

Assert HLS advertised and WebRTC absent before/after provider registration; `async_refresh_providers()` does not call `stream_source()` or retain a provider; no native WebRTC handler override exists; cloud event methods and `motion_video_latest` are ignored; no event attributes/subentity are created; P2P failure never calls a legacy source; `keep_streaming` creates no lease.

- [ ] **Step 3: Verify failure**

Run: `python -m pytest -q tests/test_xiaomi_p2p_camera.py`

Expected: FAIL because the eligible branch does not exist.

- [ ] **Step 4: Implement eligible-only initialization and route ownership**

In `CameraEntity.on_init()`, branch on `device.p2p_enabled` and converter lens metadata. Register one route handler that acquires a manager lease only after route/token validation. Set stream support and HLS frontend type, and override `async_refresh_providers()` to return without provider selection only for this instance. For non-P2P instances, call the Home Assistant base implementation when the characterization test proves it exists; otherwise no-op to preserve the older base behavior. Do not override `async_handle_async_webrtc_offer()`.

- [ ] **Step 5: Suppress event behavior only for eligible instances**

Return before event consumption in `set_state()` and `async_update()` for eligible instances; retain non-event MIoT updates supplied by the normal device coordinator. Remove the route mapping in entity removal without closing sibling routes or sessions.

- [ ] **Step 6: Run camera tests and commit**

Run: `python -m pytest -q tests/test_xiaomi_p2p_camera.py`

Expected: PASS.

```bash
git add custom_components/xiaomi_miot/camera.py tests/test_xiaomi_p2p_camera.py
git commit -m "📹 activate native P2P camera streaming"
```

---

### Task 15: Config-Entry Reload and Concurrent Unload

**Files:**
- Modify: `custom_components/xiaomi_miot/core/hass_entry.py:20-50,90-99`
- Modify: `custom_components/xiaomi_miot/__init__.py:225-352`
- Create: `tests/test_xiaomi_p2p_entry.py`

**Interfaces:**
- Each eligible account entry already owns the `ChannelSessionManager`, loopback-server reference, and tracked bridge close tasks created in Task 12.
- Reload and permanent unload both consume those interfaces through the same bounded teardown; reload then creates a fresh entry generation and reruns preflight.

- [ ] **Step 1: Write ownership and reload tests**

Assert host/token-only and ineligible entries still own no P2P resources; same DID in two account entries remains isolated; reload invalidates only the reloaded entry's vendor-cache keys, performs full bounded teardown of its routes/bridges/sessions, and fresh setup performs a new vendor preflight before replacement entities become active. Assert no old route, lease, idle timer, session, bridge, or tracked close task survives into the replacement `HassEntry`.

- [ ] **Step 2: Write exact unload-order tests**

Record calls and assert: invalidate routes; request all bridge closes without serial waits; concurrently await shared close futures; stop usable sessions; cancel session tasks; close transports; clear media/bootstrap references; release server reference; then remove entry ownership. Inject partial initialization and cleanup errors and assert later releases still execute.

- [ ] **Step 3: Verify failure**

Run: `python -m pytest -q tests/test_xiaomi_p2p_entry.py`

Expected: FAIL because entry ownership is not integrated.

- [ ] **Step 4: Integrate cache invalidation and lifecycle ownership**

Invalidate only this entry's capability-cache keys before route shutdown. Use the Task 12 task registry and manager interfaces; do not create a second manager, server reference, allocator, or cache in unload/reload code. Keep resources entry-local and never search global clouds by DID/model/host/MAC.

- [ ] **Step 5: Implement concurrent shutdown around existing platform unload**

Invalidate P2P routes before forwarding platform unload so new GETs fail immediately. After entities request bridge closure, await all close futures concurrently. Then close the manager and release the server reference. Preserve the existing return value and do not remove `HassEntry.ALL` if platform unload fails.

- [ ] **Step 6: Run entry and reload tests and commit**

Run: `python -m pytest -q tests/test_xiaomi_p2p_entry.py tests/test_cnhdm_airrtc_wkq01.py`

Expected: PASS.

```bash
git add custom_components/xiaomi_miot/core/hass_entry.py custom_components/xiaomi_miot/__init__.py tests/test_xiaomi_p2p_entry.py
git commit -m "🧹 manage P2P resources by config entry"
```

---

### Task 16: Sanitized Diagnostics and Security Regression Coverage

**Files:**
- Create: `custom_components/xiaomi_miot/diagnostics.py`
- Create: `tests/test_diagnostics.py`
- Modify: `tests/test_xiaomi_p2p_cloud.py`
- Modify: `tests/test_xiaomi_p2p_server.py`
- Modify: `tests/test_xiaomi_p2p_camera.py`

**Interfaces:**
- Produces: `async_get_config_entry_diagnostics(hass, entry) -> dict` using only entry manager snapshots.
- Top-level schema is `{"p2p": {"enabled": bool, "sessions": list[dict], "bridges": list[dict]}}`; sessions sort by `(model_profile, lens, transport_policy)` and bridges sort by opaque non-secret snapshot ID. Ineligible entries return `enabled=False` and empty lists.

- [ ] **Step 1: Write an explicit prohibited-value assertion helper and diagnostics test**

Read the existing `custom_config('keep_streaming')` lookup path used by `MiotCameraEntity._handle_stream_refresh()` (`custom_components/xiaomi_miot/camera.py:512`) and use the same path inside `async_get_config_entry_diagnostics()` so the diagnostics snapshot never diverges from production behavior when the customization key is later surfaced elsewhere.

```python
PROHIBITED = {
    "did-secret", "192.168.1.20", "41000", "service-token",
    "private-key", "device-public-key", "cloud-signature",
    "route-token", "auth=", "raw-media-payload",
    "bootstrap", "signature", "client-private", "public-key",
    "pass-token", "service-token",
}


def assert_sanitized(value):
    text = repr(value)
    for secret in PROHIBITED:
        assert secret not in text


async def test_diagnostics_expose_only_sanitized_session_snapshot(hass, entry):
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["p2p"]["sessions"][0]["lens"] == "primary"
    assert result["p2p"]["sessions"][0]["keep_streaming"] == "inactive"
    assert_sanitized(result)
```

Assert approved profile/lens/transport/quality/codecs/resolution/rates/recovery counters/packet counters/lease counts/generation/last-video age/error category, and explicit absence of every forbidden field and parameter-set fingerprint.

- [ ] **Step 2: Capture every new logging path**

Use `caplog`, real authenticated/unauthenticated loopback GETs, forced handler exceptions, cloud adapter failures, transport errors, and bridge failures. Assert log records contain categories/counts only and never request objects, raw targets, `path_qs`, `rel_url`, query strings, URLs, or bootstrap/media values. Exclude existing `MiotCloud.async_request_api()` internal logs from the assertion scope.

- [ ] **Step 3: Verify failure**

Run: `python -m pytest -q tests/test_diagnostics.py tests/test_xiaomi_p2p_cloud.py tests/test_xiaomi_p2p_server.py tests/test_xiaomi_p2p_camera.py`

Expected: FAIL because diagnostics do not exist.

- [ ] **Step 4: Implement snapshot-only diagnostics**

Look up the exact `HassEntry` by config-entry ID and serialize manager snapshots. Return empty session/bridge lists for entries without P2P ownership. Never inspect private bootstrap, route, media, RTP, or subprocess objects while building output.

- [ ] **Step 5: Run security tests and commit**

Run: `python -m pytest -q tests/test_diagnostics.py tests/test_xiaomi_p2p_cloud.py tests/test_xiaomi_p2p_server.py tests/test_xiaomi_p2p_camera.py`

Expected: PASS.

```bash
git add custom_components/xiaomi_miot/diagnostics.py tests/test_diagnostics.py tests/test_xiaomi_p2p_cloud.py tests/test_xiaomi_p2p_server.py tests/test_xiaomi_p2p_camera.py
git commit -m "🔐 add sanitized P2P diagnostics"
```

---

### Task 17: Full Automated Verification and Resource-Leak Matrix

**Files:**
- Modify: focused P2P tests listed above only when failures reveal missing specified coverage.

**Interfaces:**
- Confirms all production interfaces compose without introducing a second implementation path.

- [ ] **Step 1: Run pure protocol tests**

Run:

```bash
python -m pytest -q \
  tests/test_xiaomi_p2p_types.py \
  tests/test_xiaomi_p2p_crypto.py \
  tests/test_xiaomi_p2p_cs2_protocol.py \
  tests/test_xiaomi_p2p_cs2_udp.py \
  tests/test_xiaomi_p2p_cs2_tcp.py \
  tests/test_xiaomi_p2p_media.py \
  tests/test_xiaomi_p2p_miss.py \
  tests/test_xiaomi_p2p_fake_peer.py \
  tests/test_xiaomi_p2p_rtp.py
```

Expected: PASS with no real network, cloud credentials, or wall-clock waits.

- [ ] **Step 2: Run bridge and Home Assistant integration tests**

Run:

```bash
python -m pytest -q \
  tests/test_xiaomi_p2p_server.py \
  tests/test_xiaomi_p2p_bridge.py \
  tests/test_xiaomi_p2p_manager.py \
  tests/test_xiaomi_p2p_device.py \
  tests/test_xiaomi_p2p_camera.py \
  tests/test_xiaomi_p2p_entry.py \
  tests/test_diagnostics.py
```

Expected: PASS and teardown reports no pending P2P tasks, sockets, routes, port leases, HTTP responses, or subprocesses.

- [ ] **Step 3: Run the complete repository suite**

Run: `python -m pytest -q`

Expected: PASS, including unchanged converter and existing integration tests.

- [ ] **Step 4: Run CI-equivalent repository validation**

Push-free local checks are limited to `python -m pytest -q`. Verify the branch in GitHub CI against hassfest, HACS, and Home Assistant stable/dev/`2023.7.0`; do not claim those jobs passed from local pytest output.

- [ ] **Step 5: Inspect any verification-only changes**

Run: `git status --short && git diff -- tests`

Expected: no changes. If verification exposed a real defect, return to the owning task, add the exact changed production and test paths there, rerun that task's red-green cycle, and create a new focused commit; never stage the entire `tests/` directory.

---

### Task 18: Hardware and Frontend Release Gates

**Files:**
- Modify: `docs/superpowers/specs/2026-07-15-xiaomi-miss-cs2-design.md:769-801` only with measured acceptance results.

**Interfaces:**
- Produces release evidence; does not change protocol behavior.

- [ ] **Step 1: Run shared hardware checks for every known profile/lens**

Record Home Assistant version, camera firmware, negotiated transport/quality/codecs, source URL return time, first playable-media time, forced-disconnect recovery time, audio/video drift, and cleanup state. Required thresholds are: source under one second, playable media under 12 seconds, reconnect under 30 seconds, drift at most 250 ms, one soft restart after a ten-second video-only stall, and full reconnect after a five-second unsuccessful reprobe.

- [ ] **Step 2: Run duration and loss gates**

- `isa.camera.hlc7` primary: 24 hours, UDP-preferred policy with negotiated transport recorded, H.265, PCMA.
- `chuangmi.camera.039c01` primary: 24 hours, TCP-preferred policy with negotiated transport recorded, H.265, Opus.
- `mxiang.camera.c500ch` primary and secondary: concurrent eight-hour run, auto transport, raw quality `0`, independent sessions/recovery.
- Each applicable stream: ten-minute deterministic 2% independent packet-loss test plus one five-packet burst every 30 seconds.
- One lens: one-hour multi-viewer run proving one cached HA Stream, one source GET, one bridge, and one MISS session.

- [ ] **Step 3: Execute the H.265 frontend matrix**

For each H.265 profile/lens, test available Desktop Chromium, Desktop Safari, iOS Companion App, and Android Companion App paths. Record HA version, OS/version, browser/app version, negotiated codec, HLS path, result, and limitation. Mark a profile/lens `Passed` only after one exact H.265 path plays successfully; mark a c500ch lens `Not applicable — H.264 negotiated` only when its measured stream is H.264.

- [ ] **Step 4: Update measured results without inventing evidence**

Edit only the hardware acceptance table and accompanying measured records. Leave unexecuted cells `Not run`, retain failed-path limitations, and keep the design status non-release-ready while any applicable profile/lens gate remains pending.

- [ ] **Step 5: Commit acceptance evidence**

```bash
git add docs/superpowers/specs/2026-07-15-xiaomi-miss-cs2-design.md
git commit -m "📝 record MISS P2P hardware acceptance"
```

---

## Final Completion Check

Before release, confirm all of the following from fresh evidence:

- `python -m pytest -q` passes.
- CI hassfest, HACS, and Home Assistant stable/dev/`2023.7.0` checks pass.
- Every known hardware profile meets duration, startup, recovery, drift, and packet-loss gates.
- Every applicable H.265 profile/lens has at least one recorded successful frontend path.
- No prohibited material appears in entity state, diagnostics, or MISS-owned logs.
- Entry unload leaves no P2P task, socket, route, port, response, lease, cached key/bootstrap, or FFmpeg process.
- Ineligible and legacy camera paths remain behaviorally unchanged.
