# Native Xiaomi MISS+CS2 Camera Streaming Design

**Date:** 2026-07-15
**Status:** Draft for review

## Problem

The integration can control Xiaomi camera properties and retrieve recent cloud event recordings, but its primary camera path does not establish a native real-time media session with the device. The legacy camera path can request temporary HLS or RTSP URLs through MIoT actions, but support depends on model-specific cloud behavior and does not provide the Xiaomi P2P protocol stack.

The go2rtc Xiaomi source demonstrates a different architecture: Xiaomi Cloud supplies temporary authentication material, while real-time media travels directly between the client and the camera over the local network using Xiaomi MISS over CS2. This design ports the modern MISS+CS2 subset into Python and integrates it with Home Assistant without depending on a go2rtc process.

## Goals

- Automatically provide native real-time streaming for converter-backed Xiaomi camera entities whose MIoT spec declares `p2p-stream` and whose owning cloud entry's setup-time preflight confirms vendor 4 (CS2).
- Leave camera models without the MIoT `p2p-stream` service, or whose capability preflight does not confirm MISS+CS2, on their existing stream path.
- Reuse the integration's existing Xiaomi Cloud account and region handling.
- Support the modern Xiaomi MISS protocol over negotiated CS2 UDP or TCP.
- Receive H.264 or H.265 video and PCMA or Opus audio.
- Feed video and one-way camera audio into Home Assistant Camera and Stream/HLS.
- Select transport, lens, stream quality, and audio behavior from MIoT capability hints, built-in defaults, and optional model overrides without new user configuration.
- Expose both lenses of an eligible cloud-entry converter-backed `CameraEntity` for `mxiang.camera.c500ch` as independent Camera entities.
- Bound buffers, retries, tasks, sockets, loopback source GETs, and subprocess lifetimes.
- Keep credentials, ephemeral keys, signed connection material, and media endpoint tokens out of MISS-owned entity state, diagnostics, and logs; existing `MiotCloud` request logging remains outside this design's scope.

## Non-Goals

- Xiaomi Legacy camera protocols.
- TUTK, MTP, Agora, cloud relay, or remote P2P access.
- Cloud event recording, SD-card playback, or recording timelines.
- Two-way audio or microphone backchannel.
- PTZ controls as part of the media protocol work.
- Sharing one CS2 connection between both `mxiang.camera.c500ch` lenses.
- Supporting camera models whose MIoT spec does not declare `p2p-stream` or whose cloud capability preflight does not confirm MISS+CS2.
- Retrofitting native MISS P2P into legacy `MiotCameraEntity`, `MotionCameraEntity`, or the shared `BaseCameraEntity`.
- User-facing P2P transport, quality, audio, lens, enable, or disable options.
- Reimplementing Xiaomi account password, captcha, email, or phone verification flows.
- Providing a general-purpose RTSP server.
- Supporting a go2rtc or FFmpeg consumer running outside the Home Assistant host network namespace.
- Exposing the media bridge on a LAN interface.
- Guaranteeing H.265 playback on every Home Assistant frontend client.

## Reference Implementation and Licensing

Protocol behavior is based on the MIT-licensed `AlexxIT/go2rtc` Xiaomi implementation at commit `c245815e75e2a5fd60b4290f12bfc04e55a984d3`, particularly:

- `internal/xiaomi`
- `pkg/xiaomi/crypto`
- `pkg/xiaomi/miss`
- `pkg/xiaomi/miss/cs2`

The Python implementation must preserve MIT attribution for translated code. Protocol tests use independently recorded, sanitized fixtures and fixed cryptographic vectors; they must not commit account tokens, device signatures, private keys, DIDs, account IDs, or routable device addresses.

Intentional differences from the reference implementation, including stricter byte limits and Home Assistant lifecycle integration, are identified in this design and require independent tests.

## Terminology

This design uses the following terms with fixed meaning.

**Entity classes**

- `camera.CameraEntity` — Home Assistant's Camera entity base class; written bare as `CameraEntity` after first mention.
- `BaseCameraEntity` — the integration's shared Camera base class. Does not implement model-based P2P activation.
- `MiotCameraEntity` — the integration's legacy MIoT Camera entity. Never receives native P2P activation.
- `MotionCameraEntity` — the integration's event-derived Camera entity. Never receives native P2P activation.
- Converter-backed `CameraEntity` — a `CameraEntity` instantiated through `XEntity.CLS[ENTITY_DOMAIN]` from a converter. This is the only entity kind eligible for native P2P activation.

**Account and entry**

- `HassEntry` — a Home Assistant config entry. Owns the entry-tracked close task, manager ownership, and one reference on the loopback server.
- `MiotCloud` — the integration's existing Xiaomi Cloud client. Provides login state, region, and `async_request_api()`. P2P bootstrap calls into it through a dedicated `async_miss_get_vendor()` adapter and does not alter the existing client.

**Customizations and profiles**

- MIoT `p2p-stream` service — an integration-owned, model-declared candidate marker for converter-backed cameras. It does not by itself prove MISS+CS2 support; setup must confirm `vendor=4` through the owning cloud entry. This rule does not claim that Mi Home discovers MISS support from the same MIoT service.
- `p2p_overrides` — an optional model-specific customization overriding defaults that MIoT cannot reliably provide, such as transport policy, lens list, raw quality, or mandatory acceptance codecs. Its absence does not prevent native P2P activation after capability preflight.
- `p2p_capability_cache` — a process-local `(entry_id, region, did) -> vendor` cache with a 24-hour TTL. It stores only the vendor enum for setup-time eligibility; it never stores host, token, key, signature, or bootstrap material. Actual viewing always performs a fresh bootstrap and does not use this cache.
- `keep_streaming` — a legacy customization that drives URL refresh on `MiotCameraEntity` and other non-P2P Camera entities. Native P2P entities ignore it.

**Runtime types**

- `MissBootstrap` — immutable value returned by `async_miss_get_vendor()`. Contains the LAN host, optional P2P ID, ephemeral client Curve25519 key pair, device public key, cloud signature, and non-sensitive transport metadata.
- `MediaContract` — immutable value created by the first successful codec probe in a session generation. Contains the video codec ID, decoded dimensions, parameter-set fingerprints, audio-track presence, audio codec, sample rate, channel count, and derived RTP payload types and clock mappings. Excludes bitrate, timestamps, transport, endpoint, bootstrap material, and RTP SSRC or sequence state.
- MediaContract generation — an integer that increments when a session publishes a `MediaContract` whose video codec, dimensions, parameter sets, track presence, audio codec, sample rate, channel count, payload type, or clock mapping differs from the previous one. Bridges attach to the generation they acquired at construction and stop on `codec_contract_changed` for that generation.
- `ChannelSessionManager` — entry-owned object holding one MISS session per `(entry, region, DID, lens, raw quality, transport policy, audio policy)` tuple. Manages leases, idle timer, and the four-active-source-GET limit.

**Bridge lifecycle states**

- `STARTING` — bridge has not yet read the first bounded MPEG-TS chunk and prepared HTTP 200.
- `STREAMING` — bridge is writing MPEG-TS to the response.
- `CLOSING` — bridge has accepted its first terminal trigger and is performing the ordered close state machine.
- `CLOSED` — bridge has released every acquired resource, recorded one immutable close result, and resolved its `close_future`.

**Loopback URL**

- `GET /xiaomi_miot/p2p/{route_id}?auth={token}` URL returned by `stream_source()`. Stable for the entity lifetime. Binds only to `127.0.0.1` on an ephemeral port. Token is a 256-bit URL-safe random string. Unknown, invalid, expired, or unloaded route IDs return HTTP 404.

**Lease**

- Active source-GET lease — count held by `ChannelSessionManager` of loopback source GETs that have passed route and token check on a session. Capped at four per lens; a fifth GET returns HTTP 503 with `Retry-After: 5`. Released exactly once at the end of bridge close cleanup; that release is the only event that may start the 30-second idle timer.

**Sanitized error categories**

- `lan_host_unavailable` — host missing, malformed, unresolvable, or outside accepted RFC 1918 IPv4 scope. Surfaces a sanitized diagnostic; does not refresh cloud device records.
- `codec_contract_changed` — session probe accepted a `MediaContract` whose fields differ from the current generation. Old-generation bridges stop; new bridges attach to the adopted generation.
- `sequence_gap` — UDP reorder-bound failure or two-second gap-deadline expiry. Closes transport and forces a full reconnect without scanning the damaged byte stream.

## Supported Device Defaults and Overrides

Native streaming is enabled automatically for a converter-backed `camera.CameraEntity` whose MIoT spec declares the `p2p-stream` service, whose `Device` was created from the cloud device list of its owning Xiaomi account config entry, and whose setup-time capability preflight confirms vendor `4` (CS2). The preflight uses the process-local `p2p_capability_cache` keyed by `(entry_id, region, did)` with a 24-hour TTL. A cache miss or expiry calls `async_miss_get_vendor()` once, records only the returned vendor enum, and discards all bootstrap material. A failed preflight or a vendor other than `4` leaves the existing Camera stream path unchanged. Actual viewing always obtains fresh MISS bootstrap material.

Devices without `p2p_overrides` use these defaults: `auto` transport, the `primary` lens only, raw quality `0` (the Mi Home MISS auto-video raw value, not a negotiated adaptive-quality semantic), audio requested, and runtime codec/resolution/audio detection from the media probe. Generic candidates send only raw quality `0`; rejection surfaces sanitized `default_quality_rejected` and never triggers automatic enumeration of other quality values. Supporting another raw quality requires a model `p2p_overrides` entry. MIoT `p2p-stream` properties are capability hints and diagnostics inputs; `resolution-types` values are never converted into MISS `videoquality`, and the emitted `MediaContract` remains authoritative. Optional overrides provide model-specific lens expansion, transport, raw quality, and hardware acceptance requirements that cannot be inferred safely from MIoT.

The first release has these known overrides and hardware acceptance profiles:

| Model | Lenses | Transport policy | Raw quality | Video acceptance | Audio policy |
| --- | --- | --- | --- | --- | --- |
| `isa.camera.hlc7` | `primary` | forced UDP | `2` | H.265 required | request audio; PCMA required for hardware acceptance |
| `chuangmi.camera.039c01` | `primary` | forced TCP | `2` | H.265 required | request audio; Opus required for hardware acceptance |
| `mxiang.camera.c500ch` | `primary`, `secondary` | auto negotiation | `0` for both lenses (the Mi Home MISS auto-video raw value, not a negotiated adaptive-quality semantic) | H.264 or H.265 accepted and recorded per lens | request audio; PCMA or Opus accepted when present and recorded per lens |

Transport values in `p2p_overrides` (`forced UDP`, `forced TCP`, `auto`) are integration-side preferences describing what the integration wants the native MISS layer or the camera to choose. The native MISS session or the camera itself decides whether to honor a forced transport; an unaccepted forced transport falls back to negotiated transport without breaking activation. The decompiled Mi Home Java code does not expose a transport field on the public `MissConfig` API, so this behavior is recorded as an observed-app behavior contract rather than as a direct Java field guarantee.

`miss_camera_support_config` exposes additional fields that this integration does not read, parse, or consume as activation or runtime inputs. Specifically, `frame_type`, `audio_type`, `rate`, `turn_head`, `isChild`, `idm_support`, `ijk_audio`, `msg_reply`, `ratio`, and `type` are evaluated and intentionally ignored. `frame_type` and `audio_type` could in theory reduce `codec_contract_changed` frequency or skip the two-second audio wait, but the current spec already accepts `MediaContract` discovery, override-driven codec/audio policies, and audio-absent video-only fallback; importing these fields would require cache, merge, and version-handling logic and would couple runtime behavior to Mi Home's panel configuration. Other fields have no relevance to live streaming under this design.

Audio request is an integration-side policy: every automatically activated candidate sends `enableaudio=1` regardless of the Mi Home app's `isAutoAudio=false` default and independent of the `audio_type` field in `miss_camera_support_config`. Audio absence at runtime is non-fatal; the session starts video-only and records the condition.

All automatically activated candidates request audio. Audio absence does not prevent video startup unless a known override's hardware acceptance requires its listed codec. The `mxiang.camera.c500ch` override treats audio as optional and records the detected codec or absence independently for each lens. The known override profiles require their own hardware acceptance; generic MIoT-detected candidates use defaults and are not treated as hardware-equivalent substitutes for a known profile.

## Architecture

The implementation consists of six layers with one-way dependencies:

1. Cloud bootstrap.
2. MISS cryptography.
3. Typed CS2 transport.
4. MISS session and media parsing.
5. Entry-owned channel session management.
6. Integration-wide loopback media bridge.

Protocol and media modules do not import Home Assistant entity classes.

### Cloud Bootstrap

The bootstrap layer reuses the existing `MiotCloud` login state and selected region through a dedicated `async_miss_get_vendor()` method. That method is a thin typed adapter over `MiotCloud.async_request_api()` and inherits the existing cloud abstraction's authentication, request, logging, timeout, and cancellation behavior. This design does not alter or strengthen the generic cloud request path.

Its input is an account/region binding, device DID, `device.info.host`, and the caller's absolute operation deadline. During an initial source GET this is the 24-second setup deadline; reconnect attempts receive their own bounded deadline. The host must be a numeric RFC 1918 IPv4 address or resolve once to exactly one distinct RFC 1918 IPv4 address. Bootstrap rejects public, loopback, link-local, multicast, unspecified, IPv6, and ambiguously resolved addresses. It pins the validated numeric address for the full connection attempt so later DNS changes cannot redirect discovery.

If the host is empty, malformed, unresolvable, or outside the accepted address scope, bootstrap raises the sanitized `lan_host_unavailable` error. It does not refresh the cloud device record, infer another host, call `miss_get_vendor`, create a socket, or enter a reconnect loop.

For each full connection or reconnect, bootstrap:

1. Generates an ephemeral client Curve25519 key pair.
2. Calls `/v2/device/miss_get_vendor` with hex `app_pubkey`, `did`, and `support_vendors: TUTK_CS2_MTP`.
3. Parses `vendor.vendor`, `vendor.vendor_params.p2p_id`, top-level `public_key`, and top-level `sign`.
4. Accepts only vendor value `4`, which maps to CS2.
5. Hex-decodes and validates the 32-byte device public key.
6. Returns an immutable `MissBootstrap` containing the LAN host, optional P2P ID, client key pair, device public key, signature, and non-sensitive transport metadata.

A cloud network attempt passes `debug=False`, `raise_timeout=True`, and the shorter of 10 seconds or the caller's remaining deadline to `async_request_api()`. MISS-owned code does not catch or convert cancellation raised by that abstraction; cancellation behavior inside `async_request_api()` is outside this design's scope. A token-expired result may call the existing authentication refresh once and retry the request once with the same key pair. A second authentication failure is surfaced without another login loop. A failed CS2 connection discards this bootstrap; a full reconnect obtains new key material.

The dedicated method never logs the DID, key pair, device public key, signature, request body, or raw response. This requirement covers logging added by the MISS adapter; logs produced inside `async_request_api()` or the existing authentication refresh retain the integration's existing behavior and are outside this design's scope.

### MISS Cryptography

The cryptography layer provides pure byte-oriented operations:

- Curve25519 key generation.
- Shared-key derivation compatible with NaCl `box.Precompute`: X25519 scalar multiplication followed by HSalsa20 derivation, not raw X25519 output.
- MISS ChaCha20 encode and decode.

MISS encoding generates a random eight-byte nonce prefix, constructs the twelve-byte nonce `00000000 || nonce8`, starts the counter at zero, and returns `nonce8 || ciphertext`. Input shorter than eight bytes is rejected before decoding.

MISS uses unauthenticated ChaCha20. The implementation does not claim to detect cryptographic authentication failure. Corrupted ciphertext is detected only when resulting command structure, lengths, codec data, or session state violates a validated invariant.

This layer has no Home Assistant, cloud, socket, entity, or logging dependencies. It is verified with fixed vectors and malformed-input tests.

### Typed CS2 Transport

The CS2 abstraction preserves command, media, and multiplexing semantics instead of returning undifferentiated byte frames:

```python
class Cs2Transport(Protocol):
    async def connect(
        self,
        bootstrap: MissBootstrap,
        mode: Literal["auto", "udp", "tcp"],
        deadline: float,
    ) -> Literal["udp", "tcp"]: ...
    async def read_command(self, timeout: float | None = None) -> Cs2Command: ...
    async def write_command(
        self,
        command: Cs2Command,
        timeout: float | None = None,
    ) -> None: ...
    async def read_media_packet(
        self,
        timeout: float | None = None,
    ) -> Cs2MediaPacket: ...
    async def close(self) -> None: ...
```

`Cs2Command` retains the command ID and payload from CS2 multiplex channel `0`. `Cs2MediaPacket` retains the plaintext 32-byte MISS header and encrypted body from inbound channel `2`. The transport parses CS2 framing but does not decrypt MISS payloads or parse codecs.

The initial authentication command `0x100` contains plaintext JSON. After login, MISS commands are encrypted and carried inside command wrapper `0x1001`. Media headers remain plaintext and only media bodies are decrypted.

Timeout, malformed framing, queue overflow, login rejection, transport closure, and cancellation have distinct exception types. Cancellation never reconnects implicitly. `close()` is idempotent and unblocks all readers and writers.

#### Wire Format and Byte Order

CS2 commands and MISS plaintext use direction-dependent byte orders. The asymmetry is part of the protocol; substituting little-endian for big-endian (or vice versa) on either direction desynchronizes the channel.

Outbound CS2 command frame:

| Field | Offset | Encoding |
| --- | --- | --- |
| Magic/type | 0 | bytes |
| Outer length | 2 | uint16 big-endian |
| DRW magic/channel | 4 | bytes |
| DRW sequence | 6 | uint16 big-endian |
| Command payload length | 8 | uint32 big-endian |
| Wrapper command ID | 12 | uint32 big-endian |
| Payload | 16 | bytes |

Inbound CS2 channel-0 command frame:

| Field | Offset | Encoding |
| --- | --- | --- |
| Command ID | 0 | uint32 little-endian |
| Payload | 4 | bytes |

Encrypted outbound MISS plaintext (carried inside wrapper `0x1001`):

| Field | Offset | Encoding |
| --- | --- | --- |
| MISS command ID | 0 | uint32 big-endian |
| JSON body | 4 | bytes |

The 32-byte media header uses little-endian for codec ID, sequence, flags, and timestamp (see the table under MISS Session and Media).

The implementation exposes direction-specific encode and decode helpers:

- `encode_outbound_cs2_command(...)` builds an outbound CS2 command frame.
- `decode_inbound_cs2_command(...)` parses an inbound channel-0 command frame.
- `encode_outbound_miss_plaintext(...)` builds an encrypted MISS plaintext block.
- `decode_miss_media_header(...)` parses a media header.

The decoder and encoder are not interchangeable. The decoder takes channel-0 bytes and returns a command; the encoder takes a command and returns a frame. Tests assert the asymmetry rather than collapsing both directions into one symmetric codec.

#### Discovery and Transport Negotiation

All transport modes begin with an unconnected UDP discovery socket targeting the pinned RFC 1918 camera address on port `32108`:

- `auto` accepts either UDP-ready or TCP-ready.
- `udp` accepts only UDP-ready.
- `tcp` accepts only TCP-ready.
- Every discovery response must come from the pinned camera IP, use a nonzero source port, meet the minimum framing length, and contain the message type expected by the current handshake state.
- A validated intermediate handshake response may update the candidate destination port used for the next handshake message, but it does not establish the session peer.
- The accepted final UDP-ready response locks its exact `(pinned camera IP, source port)` as the sole UDP session peer. The implementation connects the existing discovery socket to that endpoint, preserving its local port; if the socket abstraction cannot provide connected-UDP filtering, every receive performs an equivalent exact tuple comparison.
- After peer lock, a datagram from any other IP or port is discarded before message type, length, channel, ACK, or sequence processing. It receives no ACK, cannot change the peer, cannot update gap or stall deadlines, and cannot enter a command, media, or reorder queue.
- The UDP peer remains immutable for the connection lifetime. A camera source-port change is accepted only through a subsequent full reconnect and discovery exchange.
- A TCP-ready response closes the discovery socket and opens TCP only to the same pinned camera IP and the validated source port from that response.

A ready message cannot redirect either transport to another IP. `auto` is one discovery exchange and one ready selection, not sequential UDP and TCP attempts. A discovery, connect, or login failure closes the current transport. Only a subsequent full reconnect repeats cloud bootstrap and discovery. The strict post-ready UDP tuple lock is an intentional hardening difference from the pinned reference implementation's permissive receive check; it does not claim cryptographic peer authentication.

#### Reliability and Bounds

The CS2 implementation defines these hard bounds:

- UDP outbound commands retransmit once per second, at most five times.
- The media reorder window holds at most 250 packets and 4 MiB.
- The command queue holds at most 10 items.
- The media queue holds at most 100 items.
- Incomplete media access-unit assembly holds at most 8 MiB per track.
- Sixteen-bit CS2 sequence numbers use wraparound-aware ordering.

Packets on UDP channel `2` are reordered before their length-prefixed byte stream is parsed. The reorder state tracks one `next_sequence` and compares sixteen-bit sequence numbers using wraparound-aware signed distance:

- A packet matching `next_sequence` is accepted, `next_sequence` advances, and all now-contiguous buffered packets are drained in order.
- A future packet is copied into the reorder buffer and acknowledged only when retaining it keeps both the 250-packet and 4 MiB bounds. The first future packet for the current missing sequence starts a two-second monotonic gap deadline; later packets do not extend it.
- A packet already delivered or already present in the reorder buffer is counted as duplicate, discarded, and acknowledged so the peer does not continue retransmitting it.
- When the missing packet arrives, the current deadline is cancelled after contiguous draining. If draining exposes a different gap with future packets still buffered, that new gap receives its own two-second deadline.
- If adding a future packet would exceed either reorder bound, the packet is not acknowledged and the gap fails immediately rather than evicting another packet.

CS2 DRW payloads form a fragmented, length-prefixed byte stream; a missing packet may contain framing bytes and cannot be skipped safely. A gap deadline expiry or reorder-limit failure therefore raises `sequence_gap`, closes the transport, and discards all reorder, message-framing, decryption, codec, and partial access-unit state. It never advances `next_sequence`, searches the damaged stream for a media header, or waits for a keyframe on the same connection. Recovery uses the full reconnect path with fresh cloud bootstrap, discovery, login, codec probing, and a new complete keyframe.

Command- or media-queue overflow and byte-limit overflow likewise terminate the affected session with a bounded-resource error rather than silently dropping bytes. TCP does not use the UDP reorder state because its ordered byte stream is passed directly to the same bounded length-framing parser.

TCP framing follows the CS2 length wrapper and DRW framing. TCP ping follows the reference behavior: while processing DRW traffic it is emitted at most once per second. The first release does not add an independently scheduled TCP keepalive without separate hardware evidence.

### MISS Session and Media

A MISS session owns one `(did, lens)` connection. It performs:

- Plaintext CS2 login using the cloud signature and ephemeral client public key.
- Encrypted MISS command encoding and decoding after login.
- Start-media and stop-media commands.
- Resolved lens, quality, and audio selection.
- Media header parsing and body decryption.
- Codec discovery, access-unit assembly, and timestamp normalization.
- Parameter-set and latest-keyframe caching for new bridge consumers.

Lens names are not CS2 multiplex channels. For the primary lens, start-media sends `videoquality`. For the secondary lens, it sends `videoquality: -1` and `videoquality2` with the resolved profile quality. Models cannot request a lens absent from their profile.

The 32-byte media header is parsed as follows:

| Field | Offset | Encoding |
| --- | --- | --- |
| Codec ID | 4 | little-endian uint32 |
| Sequence | 8 | little-endian uint32 |
| Flags | 12 | little-endian uint32 |
| Timestamp | 16 | little-endian uint64 |

Supported codec IDs are H.264 `4`, H.265 `5`, PCMA `1027`, and Opus `1032`. Video arrives as Annex-B data. H.264 requires SPS/PPS and H.265 requires VPS/SPS/PPS before a bridge is ready. PCMA sample rate is derived from MISS flags as 8 or 16 kHz. Opus uses the reference implementation's fixed 48 kHz stereo profile and observed packet duration; the bridge does not claim to detect or upmix mono Opus. A device whose Opus payload is incompatible with `opus/48000/2` fails audio probing and continues video-only unless its hardware acceptance requires Opus.

The session emits immutable normalized video and audio frames. It caches only current parameter sets and at most one complete keyframe, subject to the 8 MiB per-track limit. It does not know about Camera entities, HTTP responses, FFmpeg processes, or Home Assistant Stream.

The first successful codec probe creates an immutable `MediaContract` for the current session generation. It contains the video codec ID, decoded width and height, fingerprints of the required H.264 or H.265 parameter sets, audio-track presence, audio codec, sample rate and channel count, and the derived bridge RTP payload types and clock mappings. Bitrate, camera timestamps, transport, endpoint, bootstrap material, and RTP SSRC or sequence state are not contract fields. Parameter-set bytes and fingerprints remain private runtime data and are not exposed through diagnostics or entity state.

Every recovery operation that can replace the media flow, including an in-place stop-media/start-media restart and a full reconnect, probes a candidate contract before publishing any new frame to existing subscribers. An exact contract match keeps the current generation: incomplete media and access-unit parser state is discarded before probing, the session supplies the matching parameter sets and a new complete keyframe, and timestamp normalization maps recovered media strictly after the last emitted media time so existing bridges retain monotonic RTP timestamps, SSRCs, and sequence spaces.

A contract mismatch raises terminal `codec_contract_changed` for every subscription to the old generation before candidate frames are published. The session itself reports the generation change without importing bridge or HTTP classes. The manager increments the generation, invalidates old subscriptions, and adopts the candidate contract only for new bridge acquisition. Codec, resolution, parameter-set, track-presence, audio-codec, sample-rate, channel-count, payload-type, or clock-mapping changes can never be inserted into an existing FFmpeg process or HTTP MPEG-TS response.

All automatically activated candidates request audio, and that request behavior participates in the session key. Audio remains optional for runtime video startup. After mandatory video configuration and a complete keyframe are available, the session waits up to two seconds or the caller's remaining operation deadline for audio. If audio is absent, it starts video-only and records the condition in diagnostics. Known override acceptance still requires PCMA for `isa.camera.hlc7` and Opus for `chuangmi.camera.039c01`. For `mxiang.camera.c500ch`, audio is requested, each lens independently records detected PCMA or Opus or records audio absence, and audio absence does not fail acceptance on either lens.

## Automatic Entity and Capability Design

There are no new P2P config-flow or options-flow fields. The integration-owned MIoT `p2p-stream` marker identifies candidates, setup-time cloud preflight confirms MISS+CS2, built-in defaults cover discoverable-independent parameters, and optional `p2p_overrides` supply model-specific exceptions.

In this design, an eligible native P2P Camera entity is specifically the converter-backed `camera.CameraEntity` selected through `XEntity.CLS[ENTITY_DOMAIN]`. Eligibility additionally requires its owning cloud entry, `Device`, converter, MIoT `p2p-stream` candidate marker, cached or freshly confirmed vendor `4`, entry-owned session manager, and loopback server dependencies. `BaseCameraEntity` does not implement model-based P2P activation. Legacy `MiotCameraEntity` and event-derived `MotionCameraEntity` are never native P2P entities, even if their MIoT spec has `p2p-stream` or they independently advertise `CameraEntityFeature.STREAM` for an existing MIoT, HLS, RTSP, or event stream.

The activation rules are:

- A converter-backed `CameraEntity` whose MIoT spec declares `p2p-stream` uses the native P2P live-stream path only after setup preflight through its owning Xiaomi account `HassEntry` confirms vendor `4`.
- The eligibility path does not request, parse, cache, or reproduce Mi Home's remotely managed `miss_camera_support_config`. The observed app-side support configuration is not treated as an authoritative protocol capability source for this design; vendor `4` remains the required cloud protocol confirmation.
- The preflight reads the process-local `(entry_id, region, did)` capability cache with a 24-hour TTL. A miss or expiry calls `async_miss_get_vendor()` once; only the vendor enum is retained. A failed call does not cache a result and leaves the existing stream path unchanged for this setup.
- The owning entry's `MiotCloud`, region, and DID form one immutable account binding for the entity lifetime. An account entry remains eligible when its MIoT connection mode is `local`, `auto`, or `cloud`.
- A host/token-only local entry has no account binding and retains its existing Camera entities, feature flags, and live-stream behavior even when its MIoT spec has `p2p-stream`; it does not create P2P secondary-lens entities, routes, or sessions.
- A shared device listed by more than one Xiaomi account entry triggers independent capability preflight in each entry. A `vendor=4` confirmation that activates native P2P in one entry never forces P2P activation in another entry that lists the same device through host/token binding or a different account. MISS sessions, leases, routes, and bridge state are never shared across config entries.
- A candidate instantiated through legacy `MiotCameraEntity` likewise retains that entity's existing MIoT, HLS, RTSP, and event behavior. MIoT `p2p-stream` does not add native P2P feature flags, secondary lenses, routes, sessions, or leases to legacy entities.
- The integration never searches `MiotCloud.all_clouds()` or selects another entry's account by DID, MAC, host, or model. A session never borrows or changes its owning entry's cloud binding.
- Candidates whose spec lacks `p2p-stream`, whose preflight returns a vendor other than `4`, or whose preflight fails retain their current live-stream behavior. This is an ineligible preflight result, not P2P fallback. After vendor `4` has enabled native P2P, any bootstrap, transport, media, or bridge failure is surfaced as a native P2P error and never invokes the legacy stream path.
- Transport defaults to `auto`, the lens list defaults to `primary`, raw quality defaults to `0`, and audio is requested. `p2p_overrides` replaces only the values it declares; a declared transport is an integration-side preference and the native MISS layer or camera may accept or reject it.
- Runtime codec, resolution, audio format, and channel information comes from the media probe and `MediaContract`; MIoT properties do not override observed media.
- Updating an override requires a normal integration update or existing customization reload; there is no live mutation.

During `Device` converter initialization, an eligible converter-backed `CameraEntity` expands into one `CameraEntity` per resolved lens. The default resolution is `primary`; an override may add `secondary` or define another model-specific mapping:

- `primary` preserves the existing converter and entity unique ID.
- `secondary` receives a distinct converter attribute, explicit unique-ID suffix, distinct `full_name`, and `use_unique_attr=True` so current converter deduplication cannot merge it.
- Both entities remain attached to the same Home Assistant device registry device.

An eligible native P2P converter-backed `CameraEntity` advertises native P2P `CameraEntityFeature.STREAM` with HLS as its only Home Assistant frontend stream type during its own initialization and returns only its native P2P loopback source for live streaming. Native P2P entities skip Home Assistant's registered `CameraWebRTCProvider` discovery by overriding `async_refresh_providers()` only for this entity path and leaving `_webrtc_provider` unset; they must not override `async_handle_async_webrtc_offer()`, because Home Assistant interprets that override as a native WebRTC implementation. With no native WebRTC override and no selected provider, Home Assistant's capability check rejects WebRTC offers before dispatch. Non-P2P Camera entities delegate `async_refresh_providers()` to the Home Assistant base implementation unchanged. The flag and route are not added from `BaseCameraEntity` or by a model-only check. A P2P failure is surfaced explicitly; it does not silently substitute a cloud event video or legacy MIoT HLS action.

Eligible native P2P converter-backed `CameraEntity` instances disable cloud event handling entirely. They do not call `get_alarm_playlist()` or `get_alarm_eventlist()`, consume `motion_video_latest`, generate cloud event image or video URLs, update event-derived camera images, publish motion-event attributes, or create motion-event Camera subentities. Non-event MIoT properties may continue updating. Existing cloud event behavior remains unchanged for every non-P2P Camera entity, including legacy `MiotCameraEntity` and `MotionCameraEntity`.

The two eligible `mxiang.camera.c500ch` converter-backed entities own independent sessions, reconnect independently, and can consume two camera connection slots. There is no UI switch to disable native P2P for an eligible converter-backed entity. Restoring the previous live-stream path for that account entry requires removing the MIoT `p2p-stream` capability marker from the device spec or preventing the cloud preflight from confirming vendor `4`.

The `keep_streaming` customization has no P2P effect. Native P2P entities ignore it: they never start at entity creation, never hold a persistent lease, and never suppress the 30-second idle timer. The customization continues to apply to legacy MIoT URL refresh behavior on `MiotCameraEntity` and other non-P2P Camera entities.

## Session Management and Data Flow

Each Xiaomi account `HassEntry` with at least one `Device` that produces an eligible converter-backed `CameraEntity` owns a `ChannelSessionManager`. A session key contains the owning config-entry ID, cloud region, DID, lens, resolved raw quality, transport policy, and audio policy. Sessions are never shared across config entries, accounts, regions, lenses, or resolved capability settings.

The first source request follows this sequence:

```text
Camera entity stream_source()
  -> return stable loopback URL without network I/O
Home Assistant opens URL
  -> validate route and auth token
  -> ChannelSessionManager.acquire(...)
  -> cloud bootstrap
  -> CS2 discovery and UDP/TCP negotiation
  -> MISS login
  -> start media for resolved lens and quality
  -> codec and complete-keyframe probe
  -> per-GET RTP/FFmpeg bridge
  -> first MPEG-TS bytes
  -> Home Assistant Stream/HLS
```

Home Assistant frontend viewers are downstream of the cached Home Assistant `Stream` object and do not each open the integration source URL. The normal cardinality for one active lens is:

| Resource | Normal count | Cardinality rule |
| --- | --- | --- |
| Frontend viewer | `0..N` | Multiple browser or Companion App viewers share Home Assistant's provider output. |
| Home Assistant `Stream` | `1` | `Camera.async_create_stream()` serializes creation and reuses the entity's cached Stream. |
| Active loopback source GET | `1` | The Stream worker normally opens one upstream source connection. |
| Integration FFmpeg bridge | `1` | Exactly one bridge exists per active loopback GET. |
| MISS session | `1` | All overlapping GETs for the same lens share this session. |

A Home Assistant Stream restart, source reconnection, or a direct FFmpeg/PyAV consumer in the Home Assistant host network namespace can create overlapping loopback GETs. These exceptional overlaps, not ordinary frontend viewer count, motivate the per-lens limit of four active source GETs.

`stream_source()` returns the same entity-lifetime URL in under one second. It performs no cloud, socket, session-acquisition, codec-probe, or FFmpeg I/O. This satisfies `Camera.async_create_stream()` callers that impose Home Assistant's ten-second source timeout and prevents direct source callers such as `async_get_stream_source()` from blocking on integration-owned stream setup. Native P2P entities do not offer this URL through a `CameraWebRTCProvider`.

The HTTP GET derives two monotonic deadlines from handler entry:

- The setup deadline is 24 seconds and covers cloud bootstrap through receipt of the first bounded MPEG-TS chunk.
- The response deadline is 25 seconds and reserves the final second for preparing and delivering either HTTP 200 plus the first MPEG-TS chunk or a completed HTTP 502/504 response.
- A cloud network attempt is capped at 10 seconds.
- Discovery and transport connect are capped at 5 seconds.
- MISS login is capped at 5 seconds.
- Codec and complete-keyframe probing must finish with at least 5 seconds still reserved before the setup deadline for RTP/FFmpeg startup and the first MPEG-TS chunk.

The per-stage caps are ceilings relative to the remaining setup budget, not additive allowances. Each stage must complete in `min(stage_cap, setup_deadline - now)`. Setup fails immediately if the remaining budget before a stage is less than that stage's reserved minimum. The bridge must read one bounded MPEG-TS chunk by the setup deadline. It then prepares HTTP 200 and writes that chunk within the one-second response reserve.

If setup has not produced the first chunk by the setup deadline, the handler requests terminal closure with HTTP 504, and the bridge close task prepares and completes `write_eof()` by the response deadline. A non-timeout bootstrap, protocol, or codec failure similarly records HTTP 502. Response preparation and each initial write are bounded by the remaining response budget; a client disconnect, write failure, or exhausted response budget aborts the bridge without claiming that a response was delivered. The handler awaits the shielded shared `close_future`; its cancellation cannot cancel cleanup. The entry-tracked close task performs subprocess termination, kill, drain, and lease release after the response is delivered or aborted. That cleanup may delay handler return by the separate five-second terminate and two-second kill limits but does not extend either deadline and is outside the response-delivery guarantee. Entry unload also tracks and awaits the same future.

Multiple active loopback source GETs for one entity acquire leases on the same healthy MISS session. Four active GETs are allowed per lens; a fifth returns HTTP 503 with `Retry-After: 5`. This limit counts upstream source GETs, not Home Assistant frontend viewers. Accepted GETs never receive HTTP 409 for ordinary overlap.

Each bridge lease captures the session generation and its `MediaContract`. On `codec_contract_changed`, all bridges attached to the old generation stop before receiving candidate frames and run their normal independent cleanup. A bridge still in startup completes HTTP 502; a bridge that already prepared HTTP 200 closes its MPEG-TS response so Home Assistant Stream can open a replacement source GET. The existing HTTP response and FFmpeg process are never rebuilt in place. A later GET acquires the adopted generation and constructs a new SDP and FFmpeg process from its contract. If no active bridge remains, the manager may adopt the candidate generation for a healthy session during its normal 30-second idle period; this does not create or retain any lease.

When the final active source GET releases its lease, the manager starts a 30-second idle timer without sending stop-media. During that idle period the healthy session continues receiving and parsing media, updating its current parameter-set and complete-keyframe caches, and recording the last valid complete video access unit, but it performs no soft restart or full reconnect without an active lease. A new GET cancels the timer and reuses the session without sending another start-media command when valid complete video has arrived within the preceding ten seconds. If that video-stall threshold is already exceeded, the new lease immediately activates the normal one-soft-restart recovery path. Timer expiry sends stop-media on a usable session, closes the transport and session, and removes its cached media state. `keep_streaming` has no P2P effect and cannot alter or suppress this idle behavior.

Config-entry reload invalidates the process-local `(entry_id, region, did)` capability cache for the reloaded entry and triggers fresh setup-time preflight on the next entity setup. In-flight sessions, active leases, idle timers, and bridge close futures from before the reload are not interrupted; they continue under their existing lifecycle. Entities newly created after reload consume the revalidated vendor decision and reapply the activation rules.

## Home Assistant Loopback Media Bridge

Home Assistant Camera `stream_source()` exposes a string source that Stream/PyAV or a local FFmpeg consumer can open. Home Assistant has no public API for injecting an integration-owned raw-frame iterator or subprocess stdout into Stream. The bridge therefore exposes FFmpeg MPEG-TS output through an HTTP URL.

### Loopback Server

One integration-wide `aiohttp.web.AppRunner/TCPSite` binds explicitly to `127.0.0.1` on an ephemeral port. It does not bind `0.0.0.0`, a LAN address, or Home Assistant's externally reachable HTTP server. The standalone runner disables aiohttp access logging. The wildcard handler converts all expected setup and stream exceptions into sanitized responses before they reach aiohttp's default exception logger. Integration logs record only sanitized status and error categories and never include a request object, raw request target, `path_qs`, `rel_url`, or query string.

The server registers one wildcard route before startup:

```text
GET /xiaomi_miot/p2p/{route_id}?auth={token}
```

Runtime entity setup adds and removes in-memory route mappings without modifying the frozen aiohttp router. Each entity receives:

- A random, non-sensitive, opaque route ID generated from 16 random bytes that contains no DID, account, model, or lens.
- An independent authentication token generated with `secrets.token_urlsafe(32)`, providing 256 bits of source entropy.

Route mappings store the authentication token in a field excluded from `repr`; no route mapping object may be logged or formatted wholesale.

Home Assistant's source-URL logging recognizes the query key `auth` for redaction. The standalone aiohttp runner has access logging disabled independently, and integration-owned logs never format the raw URL or query. Tokens are compared with `hmac.compare_digest()`. Unknown route IDs, invalid tokens, expired mappings, and unloaded entries all return HTTP 404.

The URL remains stable for the entity lifetime. The server is reference-counted by Xiaomi account entries whose `Device` set produces at least one eligible converter-backed `CameraEntity`. The final such entry unload stops both `TCPSite` and `AppRunner`.

The endpoint supports Home Assistant Core, Home Assistant Stream/HLS, and direct FFmpeg processes running in the Home Assistant host network namespace. Native P2P entities deliberately suppress all `CameraWebRTCProvider` selection, including an otherwise reachable Home Assistant-managed go2rtc process, because the first release is HLS-only. A go2rtc or FFmpeg process in another container or host cannot resolve the loopback endpoint and is unsupported; the integration does not widen the listener or return a provider-specific non-loopback URL.

### Per-GET FFmpeg Bridge

Each accepted GET creates an independent FFmpeg bridge while sharing the underlying MISS session. Under the standard Home Assistant HLS path, multiple frontend viewers normally produce one active loopback GET and therefore one bridge. Every bridge has its own random RTP SSRCs, sequence numbers, timestamp bases, RTP/RTCP port pairs, FFmpeg process, stdout/stderr tasks, and HTTP response.

A bridge has `STARTING`, `STREAMING`, `CLOSING`, and `CLOSED` states guarded by one asynchronous state lock. The first terminal trigger atomically transitions it to `CLOSING`, records the terminal reason and startup HTTP status if applicable, and creates one entry-tracked close task and `close_future`. Client disconnect, response failure, FFmpeg exit, media-contract change, handler cancellation, Home Assistant stop, and config-entry unload all converge on that operation. Later triggers cannot replace the first reason, start another cleanup, or release a resource; they await the same shielded future. Cancellation of an individual waiter does not cancel the close task. The task reaches `CLOSED` only after all acquired resources have been released, and entry unload always awaits it.

The bridge uses fixed payload types:

| Codec | Payload type | RTP mapping |
| --- | --- | --- |
| H.264 | `96` | `H264/90000` |
| H.265 | `98` | `H265/90000` |
| PCMA 8 kHz mono | `8` | static RFC 3551 mapping |
| PCMA 16 kHz mono | `97` | dynamic `PCMA/16000/1` mapping validated by bridge tests |
| Opus | `111` | `opus/48000/2` |

H.264 packetization follows RFC 6184 and H.265 follows RFC 7798. Opus follows RFC 7587. Eight-kHz PCMA uses the RFC 3551 static mapping; sixteen-kHz PCMA does not claim the RFC 3551 static payload and instead uses the explicit dynamic mapping above.

Every RTP datagram is at most 1200 bytes including its RTP and codec fragmentation headers. Packetization defines single-NAL and fragmented-NAL handling, access-unit marker bits, sequence wraparound, and cached parameter-set injection. A new bridge starts video from a complete keyframe.

Each bridge establishes one normalized media-time origin shared by audio and video, then scales timestamps into each codec clock. It also establishes one wall-clock NTP origin and sends a compound RTCP sender report after each track's first RTP packet and every five seconds thereafter. Sender reports use that common origin and maintain per-track packet and octet counts so FFmpeg can align audio and video without exceeding the default RTCP interval.

The generated SDP contains session-level `c=IN IP4 127.0.0.1` and `t=0 0`, one `m=` section per detected track, explicit `a=rtpmap` and `a=rtcp` lines, and codec configuration:

- H.264 uses `packetization-mode=1` and base64 `sprop-parameter-sets`.
- H.265 uses base64 `sprop-vps`, `sprop-sps`, and `sprop-pps`.
- Opus declares stereo in its format parameters.
- PCMA uses the exact detected mono sample rate.

The bridge uses Home Assistant's configured FFmpeg binary. One integration-wide allocator leases non-overlapping even RTP and following RTCP ports under an asynchronous lock. It initially binds reservation sockets to both ports, records the lease, and closes the reservation sockets immediately before a newly spawned FFmpeg consumes the SDP. This handoff is not atomic: reservation sockets prevent collisions between integration-owned bridges but do not prove that an external local process cannot claim a port. FFmpeg's bind result is authoritative. A startup bind error, unexpected FFmpeg exit, or failure to produce the first MPEG-TS chunk within the setup deadline releases the pair and retries with a new pair at most three times. A failed attempt never leaves its logical lease, process, sockets, or session subscription active.

FFmpeg receives the equivalent arguments:

```text
-hide_banner -loglevel warning
-protocol_whitelist pipe,udp,rtp
-f sdp -i pipe:0
-map 0:v:0 -c:v copy
-map 0:a:0? -c:a aac -b:a 64k
-f mpegts -mpegts_flags +resend_headers pipe:1
```

The bridge writes the complete SDP once and closes stdin. It starts FFmpeg and monitors process exit and startup diagnostics for bind or input failures; it does not use a temporary bind probe or treat an occupied port as proof that FFmpeg owns it. After FFmpeg is alive without an immediate startup failure, the bridge may subscribe the session and send cached parameter sets and a complete keyframe. Reading the first bounded MPEG-TS chunk is the final startup success gate. An early failed attempt is fully terminated and releases its pair before retry only when sufficient setup budget remains. Setup-deadline expiry follows the terminal response-first path above and defers bounded process cleanup until after that response is delivered or aborted. No HTTP 200 is prepared until the gate succeeds.

FFmpeg copies H.264 or H.265 video and transcodes detected PCMA or Opus audio to AAC. It writes MPEG-TS to stdout. One bridge-owned stdout task is the sole reader of that pipe: the GET handler obtains the first bounded chunk from it before preparing `Content-Type: video/mp2t`, and in `STREAMING` the task serializes later writes to the HTTP response. On close it stops HTTP writes, bounds or cancels any blocked response write, and continues as the sole drain-to-discard owner until FFmpeg stdout reaches EOF. The separate stderr drain task likewise remains active through process termination. No cleanup path starts a second reader for either pipe.

There is no unbounded application media queue. RTP uses non-blocking loopback UDP sends; datagrams that encounter socket backpressure are dropped and counted. HTTP backpressure can block only that bridge's FFmpeg stdout. One slow or disconnected source GET cannot block another bridge or the shared MISS session.

H.265 remains stream-copied because unconditional video transcoding is too expensive for typical Home Assistant hosts. Playback is client-dependent and covered by the frontend acceptance matrix.

## Reconnection Strategy

Recovery runs only while a session has an active source-GET lease. During the 30-second no-lease idle period, the session continues receiving and parsing the already-started media flow and updates the video-stall clock, parameter-set cache, and complete-keyframe cache, but a stall cannot trigger soft restart or full reconnect until a new GET acquires a lease. If the ten-second video-stall threshold is already exceeded at acquisition, that new lease immediately begins one stall episode through the normal serialized recovery path. `keep_streaming` has no P2P effect, so it neither activates recovery nor changes the idle timer. After the current generation publishes its first complete keyframe, a monotonic video-stall clock records the last structurally valid complete video access unit accepted from the locked peer. Audio packets, command or transport ACKs, unknown messages, malformed or incomplete video, candidate video not yet accepted for publication, and rejected-peer datagrams cannot update that clock. Initial startup remains governed by the media-probe deadline rather than the steady-state stall clock.

1. A UDP `sequence_gap` deadline or reorder-limit failure marks the current CS2 byte stream unrecoverable, closes the transport, discards bootstrap and all parser state, and proceeds directly to a full reconnect. It does not attempt stop-media/start-media on the damaged connection.
2. Separately, ten seconds without a valid complete video access unit and without an active sequence gap begins one stream-stall episode. Recovery is serialized with the session reconnect state machine so no other stall, command-timeout, transport-failure, or lease transition can start a competing recovery operation.
3. Each stall episode permits exactly one in-place soft restart. Stop-media followed by the resolved start-media command shares one bounded command deadline. Before reprobe, the session discards incomplete media and access-unit assembly state but retains the usable CS2 transport, its sequence state, and its locked peer.
4. Successful command writes or acknowledgements do not prove recovery. After start-media completes, one five-second monotonic reprobe deadline requires a complete candidate `MediaContract`, including its bounded optional-audio probe, and a complete video keyframe. An exact contract match publishes the parameter sets and keyframe into the current generation with monotonic timestamp normalization. A mismatch follows the normal generation-replacement rule and terminates old-generation subscriptions before candidate frames are published.
5. A stop/start command error or timeout, malformed candidate media, transport failure, sequence gap, or expiry of the five-second reprobe deadline closes the transport, discards bootstrap and all parser state, and proceeds to a full reconnect. The same stall episode cannot issue a second soft restart. The episode ends and its one-restart allowance resets only after an accepted candidate contract and complete keyframe are published.
6. A full reconnect obtains new MISS bootstrap material and repeats discovery negotiation. Its candidate probe uses the same contract and complete-keyframe publication gate; an exact match resumes the current generation, while a mismatch replaces the generation.
7. Full-reconnect retries use jittered delays of 1, 2, 5, 15, and then at most 30 seconds while a lease remains active. Backoff resets only after an accepted contract and complete keyframe are published.

A missing or invalid host stops recovery with `lan_host_unavailable`; it does not refresh cloud device records or loop indefinitely. A failure in one `mxiang.camera.c500ch` lens does not cancel or restart the other lens.

P2P connection-slot exhaustion leaves live streaming unavailable with a sanitized diagnostic. The eligible native P2P converter-backed `CameraEntity` does not query or expose cloud events as a fallback; non-event MIoT properties may continue updating.

## Error Handling and Diagnostics

Errors are categorized before crossing the protocol boundary:

- LAN host unavailable.
- Cloud authentication.
- Cloud bootstrap timeout or response invalid.
- Unsupported vendor.
- Key negotiation or crypto input invalid.
- CS2 discovery or connect timeout.
- CS2 framing or bounded-queue violation.
- CS2 sequence-gap timeout or reorder-limit failure.
- CS2 login rejection.
- MISS command timeout or malformed command.
- Generic default quality rejected.
- Media probe timeout.
- Codec unsupported or media malformed.
- Media contract changed after reconnect.
- Active loopback source GET limit.
- RTP, bridge, or FFmpeg failure.
- Stream stalled.

Unknown MISS message types are counted and ignored only when framing and lengths remain valid. Invalid lengths, impossible state transitions, malformed decoded commands, transport desynchronization, or bounded-resource violations terminate the session safely.

A new `diagnostics.py` implements `async_get_config_entry_diagnostics()` and reads sanitized snapshots from entry-owned managers. Diagnostics may expose:

- Model profile and lens.
- Selected transport policy and negotiated transport.
- Resolved raw quality.
- Detected video and audio codecs.
- Detected resolution and sample rate.
- Full-reconnect count, plus soft-restart attempt, success, reprobe-timeout, and stall-triggered-reconnect counts.
- Media-contract generation and contract-change count, without parameter-set bytes or fingerprints.
- Dropped, reordered, duplicate, and malformed packet counters, plus rejected-peer-datagram, sequence-gap-timeout, and reorder-limit-failure counters.
- Active lease and bridge counts.
- Age of the last published complete video access unit.
- `keep_streaming` is reported as inactive for native P2P entities.
- Sanitized error category.

Diagnostics and Camera state must not expose:

- DID, account ID, LAN host, or negotiated peer port.
- passToken, serviceToken, or cloud request/response data.
- Client private key, shared key, device public key, or cloud signature.
- Route token, full route URL, or FFmpeg command containing the URL.
- Raw MISS, CS2, RTP, or media payloads.

## Resource Lifecycle

Every session is owned by one `HassEntry`; every HTTP bridge is owned by one active GET; the loopback server and RTP port allocator are integration-wide and reference-counted.

Config-entry unload is ordered as follows:

1. Invalidate the entry's route mappings so new GETs return 404.
2. Atomically request closure of every active or partially initialized HTTP/FFmpeg bridge without awaiting bridges serially.
3. Concurrently await their shared close futures; each future includes HTTP termination, process exit, pipe drains, logical port release, and active source-GET lease release.
4. Send stop-media on usable sessions.
5. Cancel session reader, writer, reconnect, and transport maintenance tasks.
6. Close CS2 sockets and unblock waiters.
7. Remove cached codec data, bootstrap/key references, and session references.
8. Decrement the loopback server reference count and stop the site and runner after the final entry.

The first caller that transitions a single GET bridge to `CLOSING` owns this sequence:

1. Prevent new media response writes and frame delivery; only the close task may perform the terminal HTTP operation in the next step. Remove the session frame subscription and stop or await the RTP producer before closing RTP/RTCP sockets, so no send can race socket closure.
2. Resolve the HTTP side before any potentially long process wait. In `STARTING`, cancel the first-chunk wait and deliver or abort the recorded HTTP 502/504 under the response deadline. In `STREAMING`, stop the stdout task's response-write phase, bound graceful `write_eof()`, and abort the response transport on timeout, disconnect, or write failure. Once response termination begins, no task may write to it again.
3. Close RTP/RTCP sockets. Their logical port lease remains held.
4. Keep exactly one stdout drain owner and the stderr drain task active, terminate FFmpeg, and wait up to five seconds.
5. Kill FFmpeg if necessary and wait up to two additional seconds while both pipes continue draining.
6. After process exit, boundedly await stdout and stderr EOF, close any remaining process pipes, and only then release the logical RTP/RTCP port lease.
7. Release the active source-GET session lease exactly once in the outermost `finally`. This is the final acquired bridge resource released; only then may the manager start the 30-second session idle timer. `keep_streaming` has no P2P effect, so bridge closure does not interact with the customization.
8. Mark the bridge `CLOSED`, resolve `close_future`, and unregister the close task from its entry.

Every acquisition records ownership immediately, and the close task checks that ownership rather than assuming full initialization. Failure before HTTP preparation, session subscription, socket allocation, process spawn, or task creation therefore runs the same ordered state machine and releases only resources actually acquired. Each bounded cleanup step is nested so its failure is recorded as a sanitized cleanup category but cannot skip later releases; `close_future` completes with one immutable close result only after `CLOSED`. One bridge failure does not close sibling bridges or a healthy shared session.

## Security

- Camera media remains on the local camera network and Home Assistant loopback interface; cloud relay is not implemented.
- Camera discovery accepts only a pinned RFC 1918 IPv4 target; final UDP-ready locks the exact session IP and port, and TCP-ready negotiation cannot redirect the connection to another IP. Endpoint filtering narrows packet injection but is not cryptographic peer authentication.
- Internet access is required for each full MISS bootstrap.
- Ephemeral private keys, shared keys, signatures, and endpoint tokens remain in memory only.
- Python cannot guarantee physical memory zeroization; cleanup removes references and does not claim secure erasure.
- The media server binds only to `127.0.0.1` and uses independent entity-lifetime authentication tokens.
- MISS-owned logging performs structured redaction before values are passed as logger arguments; it does not rely on the current `record.msg` filter. Existing `MiotCloud` request logging is unchanged and outside this design's scope.
- Sanitized fixtures replace all account, device, key, signature, and address material.
- The implementation documents that MISS uses unauthenticated ChaCha20 because protocol compatibility prevents substituting an authenticated cipher.
- Native P2P entities are HLS-only and never offer the route URL to a registered `CameraWebRTCProvider`. A go2rtc or FFmpeg process outside the Home Assistant host network namespace cannot open the loopback source, and the integration does not widen the listener to accommodate it.
- The lack of a user-facing native P2P disable switch is a documented release limitation.

## Proposed Code Boundaries

Exact names may be adjusted to existing package conventions, but responsibilities remain separated:

```text
custom_components/xiaomi_miot/core/xiaomi_p2p/
  __init__.py          public types and factories
  cloud.py             typed MISS bootstrap adapter over async_request_api
  crypto.py            NaCl-compatible key derivation and ChaCha20
  miss.py              login, encrypted commands, and session state
  cs2/
    protocol.py        typed frames, wire constants, and framing
    transport.py       typed transport protocol/interface
    udp.py             discovery, ACK, reorder, and retransmission
    tcp.py             TCP framing and reference-compatible ping
  media.py             media headers, codecs, access units, and frames
  rtp.py               codec-specific RTP packetization
  bridge.py            per-GET RTP, FFmpeg, MPEG-TS response, and close state machine
  server.py            loopback wildcard route and RTP port allocator
  manager.py           entry sessions, leases, idle timeout, and shutdown
```

Existing integration points remain in:

- `core/xiaomi_cloud.py`: dedicated `async_miss_get_vendor()` entry point.
- `core/device.py`: MIoT `p2p-stream` capability lookup, optional override resolution, and converter expansion.
- `core/hass_entry.py`: manager ownership and unload ordering.
- `camera.py`: native P2P feature activation, HLS-only frontend capability, provider-discovery suppression through `async_refresh_providers()` only on converter-backed `CameraEntity`, and stable loopback `stream_source()`; no native WebRTC override, no activation in `BaseCameraEntity`, and no native P2P retrofit in `MiotCameraEntity` or `MotionCameraEntity`.
- `core/device_customizes.py`: optional model `p2p_overrides`, not an activation allowlist.
- `diagnostics.py`: sanitized config-entry diagnostics.

Protocol modules do not import Home Assistant entity classes.

## Testing Strategy

### Cloud and Security Tests

- Missing, malformed, unresolvable, public, loopback, link-local, multicast, unspecified, IPv6, and ambiguously resolved hosts return `lan_host_unavailable` without refreshing cloud device records, calling `miss_get_vendor`, or creating sockets.
- MIoT service lookup treats the canonical `p2p-stream` service marker as an integration-owned candidate signal even when its property set is empty; it does not infer MISS+CS2 support without the cloud vendor preflight or claim that Mi Home uses the same discovery rule.
- Setup eligibility neither calls `/app/service/getappconfig` nor parses or caches `miss_camera_support_config`; app-side support configuration cannot enable or disable native P2P in this design.
- Capability preflight is setup-time, uses `(entry_id, region, did)` isolation, caches only the vendor enum for 24 hours, and performs a fresh `miss_get_vendor` call after expiry or config-entry reload.
- A vendor `4` result enables native P2P with defaults or declared `p2p_overrides`; a different vendor, timeout, cancellation, or other preflight failure leaves the existing Camera path unchanged and does not cache a failed result.
- Capability cache entries contain no host, token, key, signature, or bootstrap material and are absent from diagnostics and entity state.
- DNS is resolved once per connection attempt, the numeric RFC 1918 address is pinned, discovery responses from another IP are rejected, final UDP-ready locks its validated source port, and TCP-ready cannot select another IP.
- The MISS adapter passes `debug=False`, `raise_timeout=True`, and the shorter of its ten-second cap or caller deadline to `async_request_api()`.
- Cancellation raised by `async_request_api()` propagates without being caught or converted by MISS-owned code; the existing cloud abstraction's internal cancellation behavior is not changed or retested here.
- Token expiration permits exactly one existing authentication refresh and one retry.
- A second authentication failure does not loop.
- Captured MISS-owned, aiohttp access, and aiohttp exception logs contain no DID, host, token, key, signature, request body, raw response, request object, raw request target, `path_qs`, `rel_url`, or query string. Real authenticated GETs and forced handler exceptions exercise every new logging path. Logs produced inside the existing `MiotCloud` request and authentication implementations are outside this design's scope.
- Token generation is patched with deterministic 32-byte input to assert 256 bits of source entropy, and route mapping representations omit the token.
- Diagnostics and entity state contain no prohibited values.
- Unknown, invalid, and unloaded loopback routes return 404.

### Protocol Unit Tests

- Curve25519 plus HSalsa20 shared-key vectors.
- ChaCha20 nonce layout, encode/decode vectors, short nonce, and malformed input.
- Plaintext login and encrypted `0x1001` command fixtures.
- Direction-specific byte-order vectors use non-palindromic command IDs: outbound authentication `0x100` encodes its wrapper ID as `00 00 01 00`, inbound authentication response `0x101` decodes from `01 01 00 00`, outbound encrypted wrapper `0x1001` encodes as `00 00 10 01`, and outbound start-media MISS plaintext `0x102` encodes as `00 00 01 02`.
- Outbound CS2 outer length, DRW sequence, command payload length, and wrapper command ID encode big-endian; inbound channel-0 command IDs and every declared media-header field decode little-endian.
- Outbound encoders cannot generate inbound fixtures, and an inbound channel-0 payload shorter than four bytes raises malformed framing rather than producing a command.
- CS2 channel `0` command and channel `2` media separation.
- CS2 fragmentation, concatenation, lengths, and 16-bit sequence wraparound.
- UDP discovery with UDP-ready and TCP-ready in auto mode, proving one discovery exchange and no sequential transport fallback.
- Forced UDP/TCP rejection of the opposite ready type.
- Final UDP-ready locks the response's exact pinned-IP/source-port tuple on the existing socket; valid session commands, media, and ACKs use only that endpoint.
- Datagrams from a different IP or from the pinned IP with a different port are dropped before CS2 parsing, receive no ACK, and cannot mutate the peer, queues, sequence state, gap deadline, or stall deadline.
- A UDP endpoint can change only after transport closure and a full reconnect performs a new discovery exchange.
- Primary start-media emits `videoquality`; secondary emits `videoquality: -1` plus `videoquality2`, using the resolved raw quality from defaults or override.
- The `mxiang.camera.c500ch` primary and secondary start-media commands use raw quality `0` for `videoquality` and `videoquality2`.
- UDP outbound-command ACK, one-second retransmission, and retry exhaustion.
- UDP channel-2 in-order delivery, future-packet buffering, contiguous drain, duplicate handling, and DRW ACK behavior across sixteen-bit sequence wraparound.
- A future packet starts one two-second monotonic gap deadline that later packets cannot extend; closing one gap cancels its deadline, while a newly exposed gap receives a new deadline.
- Gap-deadline expiry and the packet or byte reorder limit close the transport without skipping a sequence or parsing later bytes, discard all transport and media parser state, and require a full reconnect with fresh bootstrap and a new complete keyframe.
- The 250-packet, 4 MiB, 10-command, 100-media, and 8 MiB bounds; a future packet that would exceed a reorder bound is not acknowledged, while duplicate accepted packets are acknowledged.
- TCP partial frames, reference-compatible DRW ping, and disconnects.
- MISS media header offsets, endianness, and supported codec IDs.
- `MediaContract` equality covers video codec, dimensions, parameter-set fingerprints, audio-track presence and format, and derived RTP mappings while excluding timestamps, transport, endpoint, SSRC, and sequence state.
- H.264/H.265 parameter-set and complete-access-unit detection.
- The monotonic steady-state stall clock starts only after the first published complete keyframe and is updated only by structurally valid complete video access units; audio, acknowledgements, malformed or incomplete video, unaccepted candidate media, and rejected-peer traffic cannot postpone it.
- One stall episode can acquire the serialized recovery owner and issue stop-media/start-media at most once. Command failure, concurrent recovery triggers, and five-second reprobe expiry all converge on one full-reconnect transition without a second in-place restart.
- PCMA/Opus codec and timestamp normalization.

### Simulated Peer Tests

A fake CS2 peer covers UDP and TCP without real Xiaomi credentials. It injects:

- Delayed and missing acknowledgements.
- Discovery and steady-state datagrams from wrong IPs and wrong source ports, including valid-looking CS2 frames that must be ignored before parsing.
- Reordered, duplicated, temporarily missing, and permanently missing UDP media packets.
- A permanent sequence gap followed by valid-looking media bytes, proving the implementation reconnects without scanning the damaged byte stream for a media header or keyframe.
- Partial TCP frames and framing desynchronization.
- Disconnects during discovery, login, probe, and steady media.
- A reconnect with the same contract but reset camera timestamps, proving normalized media time remains monotonic for old-generation bridges.
- Reconnects that independently change video codec, dimensions, parameter sets, audio presence, audio codec, sample rate, or channel count, proving candidate frames never reach old-generation subscriptions.
- Structurally invalid encrypted commands and media bodies.
- Keyframe loss and later recovery.
- Audio continuing for more than ten seconds after video access units stop, proving audio cannot suppress the video-stall trigger.
- Stop-media/start-media commands that are acknowledged but produce no video, delta-only video, or no complete keyframe before the five-second reprobe deadline, proving each case performs a full reconnect without a second soft restart.
- A soft restart that supplies a matching contract and complete keyframe within five seconds, followed by a later independent stall, proving successful publication ends the first episode and only the later episode receives a new one-restart allowance.
- A soft restart whose candidate contract changes, proving the normal generation-replacement rule applies before any candidate frame reaches an old subscription.
- Independent failures for the two `mxiang.camera.c500ch` lenses.

Tests assert negotiation, exact UDP peer lock and immutability, rejected-peer isolation, gap deadlines and ACK decisions, full reconnect with fresh bootstrap after an unrecoverable gap, video-only stall timing, one soft restart per stall episode, bounded complete-keyframe reprobe, compatible-contract continuation, incompatible generation replacement, bounds, parser-state cleanup, task cleanup, and error categorization.

### RTP and FFmpeg Bridge Tests

- H.264 RFC 6184 and H.265 RFC 7798 single-NAL and fragmented packetization with a 1200-byte maximum RTP datagram.
- PCMA 8 kHz static payload `8`, PCMA 16 kHz dynamic payload `97`, and Opus RFC 7587 payload `111`.
- Video 90 kHz, exact PCMA sample-rate, and Opus `48000/2` clocks.
- Marker bits, timestamp normalization from one shared media origin, sequence wrap, and independent bridge SSRCs.
- Immediate and five-second compound RTCP sender reports use one common NTP origin and correct packet/octet counters.
- Exact H.264/H.265 parameter-set SDP, `a=rtpmap`, `a=rtcp`, Opus stereo, and PCMA sample-rate attributes.
- A compatible full reconnect or successful in-place soft restart preserves each bridge's SSRC, RTP sequence space, and monotonic timestamp mapping after reinjecting matching parameter sets and a complete keyframe.
- A changed media contract discovered by either recovery path sends no candidate RTP packet to an old-generation bridge; its FFmpeg process and HTTP response close instead of rebuilding SDP in place.
- Non-overlapping RTP/RTCP reservation and logical lease ownership prevent integration-internal collisions while tests preserve the explicitly non-atomic close/spawn handoff; no temporary bind probe is used as an ownership check.
- FFmpeg bind failure, unexpected startup exit, and first-MPEG-TS timeout permit a new port pair only while the setup deadline leaves enough budget; no more than three attempts are started. A failed pre-deadline attempt is fully terminated and drained before its session subscription and logical port lease are released for retry. On terminal setup failure, the HTTP error response is delivered or aborted within the response reserve before bounded process termination and drain are awaited, and the logical lease remains held until that process has stopped.
- SDP stdin is closed, the protocol whitelist includes `pipe,udp,rtp`, and the complete FFmpeg input/map/codec/MPEG-TS command matches the design.
- Home Assistant's configured FFmpeg binary is used.
- Video is stream-copied and PCMA/Opus is transcoded to AAC.
- The first bounded MPEG-TS chunk is read by the 24-second setup deadline before HTTP 200 preparation and is the final bridge startup success gate; a failed gate cannot leave a process, lease, port pair, or session subscription behind.
- Success prepares HTTP 200 and writes the first bounded chunk by the 25-second response deadline; setup-deadline expiry instead completes HTTP 504 within the same one-second response reserve.
- Response preparation, the initial media write, and error `write_eof()` are each bounded by the remaining response budget; disconnect, write failure, or exhausted budget aborts the bridge and exercises full cleanup without recording the response as delivered.
- Four direct authenticated loopback GETs share one MISS session and use independent FFmpeg processes.
- Disconnecting or slowing one source GET does not affect another bridge.
- A fifth active loopback GET returns 503 with `Retry-After: 5`.
- FFmpeg graceful exit, five-second terminate timeout, two-second kill timeout, and stderr cleanup.
- Concurrent client disconnect, FFmpeg exit, media-contract change, handler cancellation, Home Assistant stop, and entry-unload triggers produce one `CLOSING` transition, one close task, one preserved terminal reason, and one exact-once release of every acquired resource; every caller observes the same `close_future`.
- Cancelling one close waiter does not cancel the entry-tracked close task, and unload awaits that task through `CLOSED`.
- Removing the frame subscription and stopping the RTP producer precede socket closure; no packet is sent after detachment begins.
- A blocked stdout-to-response write is bounded or cancelled before response close, after which the same stdout owner drains to EOF without a concurrent pipe reader.
- Full stdout and stderr pipes remain actively drained during terminate and kill, proving process wait cannot deadlock on pipe backpressure.
- The logical RTP/RTCP port lease remains unavailable to another bridge until FFmpeg has exited, pipe ownership is resolved, and the sockets are closed; the active source-GET session lease is released exactly once afterward and is the event that may start the idle timer.
- Failures injected after each individual acquisition and inside each cleanup step prove partial initialization uses the same state machine, releases only acquired resources in the required order, continues later releases after a cleanup error, and resolves one immutable sanitized close result only after `CLOSED`.
- The server binds only to `127.0.0.1` and the route is inaccessible through LAN-bound addresses.

### Home Assistant Tests

- Converter-backed `CameraEntity` instances whose MIoT spec declares `p2p-stream` perform setup-time capability preflight through their owning Xiaomi account entry; a cached or freshly confirmed vendor `4` enables native P2P for `local`, `auto`, and `cloud` connection modes, while a failed or non-CS2 preflight retains the existing stream path and records only a sanitized capability diagnostic. No new config-flow or options-flow fields are registered.
- Capability preflight uses the `(entry_id, region, did)` process-local cache with a 24-hour TTL, stores only the vendor enum, does not retain bootstrap material, and retries after expiry or config-entry reload.
- A candidate without `p2p_overrides` resolves `auto` transport, the `primary` lens, raw quality `0`, audio request enabled, and runtime media probing; an override replaces only declared defaults and cannot change the owning entry binding.
- A generic candidate whose start-media command rejects raw quality `0` surfaces `default_quality_rejected`, sends no alternative quality command, does not convert MIoT `resolution-types` into MISS values, and requires a model override for another quality.
- Native P2P converter-backed `CameraEntity` instances remain HLS-only when a registered `CameraWebRTCProvider` supports their `http` loopback URL, whether the provider exists before entity setup or is registered or refreshed later: provider refresh does not call `stream_source()`, select, or retain a provider; capabilities contain HLS but not WebRTC; and a WebRTC offer is rejected by Home Assistant's capability guard. The entity does not override native WebRTC handling.
- Non-P2P converter-backed Camera entities continue to delegate provider refresh to Home Assistant and retain their existing WebRTC provider behavior.
- A host/token-only local entry retains its existing entities, feature flags, and stream path and creates no P2P secondary lens, route, or session even when its MIoT spec declares `p2p-stream`.
- The same candidate model instantiated through legacy `MiotCameraEntity` retains its existing MIoT, HLS, RTSP, and event-backed STREAM behavior and creates no native P2P secondary lens, route, session, or lease.
- A test-only `BaseCameraEntity` subclass and `MotionCameraEntity` do not consult MIoT P2P capability or acquire native P2P feature flags, routes, sessions, or leases, including when associated with a candidate model.
- Multiple Xiaomi account entries containing the same shared device remain isolated by config-entry ID and region; local entries never borrow an account through DID, MAC, host, or model matching. A second entry that lists an already-activated device through host/token binding does not reuse the first entry's MISS session, route, lease, FFmpeg process, or `ChannelSessionManager`; each entry's eligible entities own their own session lifecycle and idle timer.
- Each known override resolves to its exact transport, lens list, raw quality, accepted video codec, and audio request policy; generic candidates use the defaults and runtime media probe.
- `mxiang.camera.c500ch` creates stable, distinct primary and secondary unique IDs.
- Converter deduplication does not remove the secondary lens.
- Multiple Home Assistant HLS frontend viewers of one Camera reuse one cached Home Assistant `Stream`, one active loopback source GET, one integration FFmpeg bridge, and one MISS session.
- Home Assistant Stream stop and recreation opens a replacement source GET; any temporary overlap shares the healthy MISS session, and the previous bridge releases its response, FFmpeg process, tasks, and RTP ports.
- Overlapping source GETs for the same lens share one MISS session, while the two `mxiang.camera.c500ch` lenses use independent sessions.
- A media-contract change closes every active bridge on the old session generation without affecting the other lens; startup bridges complete 502, streaming responses close, and a replacement GET creates new SDP and FFmpeg from the adopted generation.
- With `keep_streaming` set on a native P2P entity, the customization has no P2P effect: the entity does not connect at creation, holds no persistent lease, never suppresses the 30-second idle timer, and exposes `keep_streaming` as inactive in diagnostics.
- `stream_source()` is stable and completes in under one second without cloud, socket, session-acquisition, codec-probe, or FFmpeg I/O when invoked through both the timed `Camera.async_create_stream()` path and direct source calls such as `async_get_stream_source()`; provider refresh for a native P2P entity never invokes it.
- Exactly one wildcard route is registered before server startup; entity setup and unload mutate only the in-memory route map.
- GET startup derives a 24-second setup deadline and a 25-second response deadline from handler entry, reserves at least the final five setup seconds for FFmpeg, and uses the final one-second response reserve to deliver HTTP 200 plus the first bounded MPEG-TS chunk or a completed HTTP 502/504 response.
- Simulated clocks exercise success and setup timeout at the 24-second boundary, proving response preparation and the initial write complete or abort by 25 seconds rather than beginning only after the outer deadline.
- A delayed initial response writer, client disconnect, write failure, and exhausted response reserve each abort without claiming delivery; bounded FFmpeg cleanup may outlive the response deadline, remains tracked by the handler, and is awaited during entry unload.
- P2P failure does not substitute legacy live video.
- Eligible native P2P converter-backed `CameraEntity` instances never call cloud event APIs, consume `motion_video_latest`, generate event media URLs, update event-derived images or attributes, or create motion-event Camera subentities; event behavior remains unchanged for every non-P2P Camera entity, including legacy `MiotCameraEntity` and `MotionCameraEntity`.
- Native P2P converter-backed `CameraEntity` instances ignore the `keep_streaming` customization: enabling it does not create a persistent lease, change the 30-second media-active idle period, or retain the session after timer expiry. After the final source-GET lease release, media continues without another start-media command; a healthy session is reused by a GET arriving during the idle period, while a session whose ten-second video-stall threshold has already expired immediately enters the normal one-soft-restart recovery path only after that GET acquires its lease. Idle timer expiry sends stop-media on a usable session and closes it. Disabling or removing `keep_streaming` has no effect on P2P behavior. Legacy `MiotCameraEntity` and other non-P2P Camera entities continue to use the existing URL refresh semantics.
- Each lens enforces its own four-active-source-GET limit, so overlapping GETs for the other lens do not consume that limit.
- Config-entry unload covers active GETs, idle sessions, reconnect, and every partial-initialization boundary. It broadcasts closure to all bridges before concurrently awaiting their shared close futures, so per-bridge terminate/kill bounds do not accumulate serially.
- The active source-GET lease is released exactly once after bridge-owned resources, and that release is the only event that may start the 30-second idle timer. `keep_streaming` does not participate in either step for native P2P entities.
- Unload leaves no P2P tasks, sockets, route mappings, RTP ports, HTTP responses, or FFmpeg processes.

H.264 release support is established through sanitized protocol fixtures, fake-peer tests, and FFmpeg bridge tests. An H.264 hardware profile is not a first-release gate.

### Hardware Acceptance

Under a normal local network:

- `stream_source()` returns in under one second.
- First playable media appears within 12 seconds.
- A forced disconnect recovers within 30 seconds.
- A forced audio-only video stall triggers exactly one stop-media/start-media attempt after ten seconds; a matching complete keyframe within the five-second reprobe window resumes the existing bridge.
- When the same commands are acknowledged but no complete keyframe follows, instrumentation confirms that full reconnect begins at reprobe expiry without a second in-place restart.
- Audio and video do not sustain more than 250 ms of drift.
- A ten-minute deterministic network test with 2% independent packet loss plus one five-packet burst every 30 seconds stays within all bounds and resumes playback no later than five seconds after the next complete keyframe.
- `isa.camera.hlc7` runs continuously for 24 hours over its forced UDP profile with H.265 and PCMA.
- `chuangmi.camera.039c01` runs continuously for 24 hours over its forced TCP profile with H.265 and Opus.
- Both `mxiang.camera.c500ch` lenses run concurrently for eight hours using auto transport negotiation and raw quality `0` (the Mi Home MISS auto-video raw value), without cross-lens data or coupled restart. The acceptance record captures the transport, quality, and codecs negotiated for each lens.
- Multiple Home Assistant HLS frontend viewers of one lens run concurrently for one hour while instrumentation confirms one cached Home Assistant `Stream`, one active loopback source GET, one integration FFmpeg bridge, and one MISS session.
- Connection-slot interference with Mi Home while both `mxiang.camera.c500ch` lenses are active is recorded as an accepted limitation.

A hardware run that negotiates H.265 is incomplete until at least one frontend path in the matrix below plays that exact profile/lens during the run. A transport-only 24-hour result cannot satisfy the H.265 release gate. This is a profile/lens-level gate, not a per-client matrix-cell gate.

The H.265 frontend acceptance record is part of this spec rather than a separate informal note. Each executed cell must record the Home Assistant version, client OS/version, browser or Companion App version, negotiated codec, HLS playback path, result, and limitation. An unexecuted or failed client path does not block release when another recorded path satisfies the same profile/lens gate, but its result or limitation remains part of the acceptance record.

| Profile/lens | Gate status | Desktop Chromium | Desktop Safari | iOS Companion App | Android Companion App |
| --- | --- | --- | --- | --- | --- |
| `isa.camera.hlc7` primary | Pending — needs one pass | Not run | Not run | Not run | Not run |
| `chuangmi.camera.039c01` primary | Pending — needs one pass | Not run | Not run | Not run | Not run |
| `mxiang.camera.c500ch` primary, if H.265 | Pending — needs one pass if H.265 | Not run | Not run | Not run | Not run |
| `mxiang.camera.c500ch` secondary, if H.265 | Pending — needs one pass if H.265 | Not run | Not run | Not run | Not run |

Gate status is `Pending — needs one pass` while an applicable profile/lens has no successful H.265 frontend result, `Passed` after any one recorded client path plays that exact H.265 stream, and `Not applicable — H.264 negotiated` for an `mxiang.camera.c500ch` lens whose hardware run negotiates H.264.

For `isa.camera.hlc7` primary and `chuangmi.camera.039c01` primary, H.265 is required by the profile and at least one successful H.265 frontend path is mandatory. For each `mxiang.camera.c500ch` lens, this gate applies only when that lens actually negotiates H.265; an H.264 result does not create an H.265 frontend gate. The matrix records every executed client path, but an unexecuted or failed client path blocks release only when no other recorded path satisfies the same profile/lens gate.

The current Draft status means these hardware results have not been executed. The document cannot move to release-ready status while a profile/lens gate remains pending. Universal H.265 playback is not required, but at least one recorded Home Assistant frontend path must play each H.265 profile/lens, and every failed path must retain its recorded limitation.

## Primary Risks

1. Xiaomi firmware differences in CS2 commands, quality identifiers, and packet formats.
2. UDP reorder and retransmission behavior under real Wi-Fi loss.
3. H.265 frontend compatibility without video transcoding.
4. FFmpeg subprocess, RTP port, and HTTP response cleanup during rapid reloads.
5. Xiaomi Cloud token expiration or API changes preventing new bootstrap.
6. `mxiang.camera.c500ch` quality behavior causing CS2 buffer errors or incorrect dimensions.
7. Two independent `mxiang.camera.c500ch` sessions exhausting connection slots and blocking Mi Home playback.
8. Automatic enablement without a UI disable switch affecting an eligible cloud-entry device with divergent firmware.
9. HLS-only provider suppression and loopback-only media prevent native P2P entities from using go2rtc WebRTC or FFmpeg consumers in another container.
10. Older Dafang and Xiaofang cameras on the MISS path interpret `videoquality=0` as HD rather than as auto, inverting the field semantics used by newer models. This design does not consume those models, and the `raw quality 0` default is documented strictly against newer models' auto-video behavior; future readers must not assume the field has the same meaning across all Xiaomi devices.
11. The Mi Home app's cache and retry behavior for `/v2/device/miss_get_vendor` was not directly verified from the decompiled code. The setup-time preflight and 24-hour process-local vendor cache in this design are an integration-owned policy; they are not claimed to match Mi Home's internal caching, and they do not imply that vendor decisions are durable across server-side changes.

## Completion Criteria

The feature is ready for release only when:

- All cloud, protocol, fake-peer, bridge, and Home Assistant tests pass.
- The three known override hardware profiles meet their duration, startup, recovery, drift, and bounded-loss targets; generic MIoT-detected candidates are not treated as hardware-equivalent substitutes for those profiles.
- The H.265 frontend compatibility matrix records the required client versions and outcomes, every applicable profile/lens gate is `Passed`, each passed gate identifies at least one recorded Home Assistant frontend path that played that exact H.265 stream, and every executed failure retains its limitation. An `mxiang.camera.c500ch` lens that negotiates H.264 records `Not applicable — H.264 negotiated` instead of requiring an H.265 frontend result.
- No credential, key, signature, host, DID, route token, or raw connection material appears in entity state, diagnostics, or MISS-owned logs; existing `MiotCloud` request and authentication logs remain outside this design's scope.
- Config-entry unload leaves no P2P tasks, sockets, route mappings, RTP ports, HTTP responses, or FFmpeg processes.
- Cameras without the MIoT `p2p-stream` service, candidates whose setup preflight does not confirm vendor `4`, and legacy `MiotCameraEntity`, `MotionCameraEntity`, and `BaseCameraEntity` paths retain existing behavior; only eligible converter-backed `CameraEntity` instances activate native P2P, cloud event behavior remains unchanged for every non-P2P Camera entity, and non-camera tests remain unchanged.
- Eligible native P2P entities advertise HLS but not WebRTC, never select a registered `CameraWebRTCProvider`, and do not alter provider behavior for non-P2P Camera entities.
- Limitations for Xiaomi account entry ownership, Internet bootstrap, LAN camera access, loopback-only consumers, H.265 playback, unsupported protocols, automatic enablement, and dual-lens connection slots are documented.
