# Native Xiaomi MISS+CS2 Camera Streaming Design

**Date:** 2026-07-15
**Status:** Draft for review

## Problem

The integration can control Xiaomi camera properties and retrieve recent cloud event recordings, but its primary camera path does not establish a native real-time media session with the device. The legacy camera path can request temporary HLS or RTSP URLs through MIoT actions, but support depends on model-specific cloud behavior and does not provide the Xiaomi P2P protocol stack.

The go2rtc Xiaomi source demonstrates a different architecture: Xiaomi Cloud supplies temporary authentication material, while real-time media travels directly between the client and the camera over the local network using Xiaomi MISS over CS2. This design ports the modern MISS+CS2 subset into Python and integrates it with Home Assistant without depending on a go2rtc process.

## Goals

- Automatically provide native real-time streaming for explicitly allowlisted Xiaomi camera model profiles.
- Leave camera models without a P2P profile on their existing stream path.
- Reuse the integration's existing Xiaomi Cloud account and region handling.
- Support the modern Xiaomi MISS protocol over negotiated CS2 UDP or TCP.
- Receive H.264 or H.265 video and PCMA or Opus audio.
- Feed video and one-way camera audio into Home Assistant Camera and Stream/HLS.
- Select transport, lens, stream quality, and audio behavior from model profiles without new user configuration.
- Expose both lenses of `mxiang.camera.c500ch` as independent Camera entities.
- Bound buffers, retries, tasks, sockets, HTTP consumers, and subprocess lifetimes.
- Keep credentials, ephemeral keys, signed connection material, and media endpoint tokens out of entity state, diagnostics, and logs.

## Non-Goals

- Xiaomi Legacy camera protocols.
- TUTK, MTP, Agora, cloud relay, or remote P2P access.
- Cloud event recording, SD-card playback, or recording timelines.
- Two-way audio or microphone backchannel.
- PTZ controls as part of the media protocol work.
- Sharing one CS2 connection between both `mxiang.camera.c500ch` lenses.
- Supporting camera models that do not have an explicit P2P model profile.
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

## Supported Device Profiles

Native streaming is enabled automatically only when a model has a `p2p_profile` customization. The first release contains these profiles:

| Model | Lenses | Transport policy | Raw quality | Video acceptance | Audio policy |
| --- | --- | --- | --- | --- | --- |
| `isa.camera.hlc7` | `primary` | forced UDP | `2` | H.265 required | request audio; PCMA required for hardware acceptance |
| `chuangmi.camera.039c01` | `primary` | forced TCP | `2` | H.265 required | request audio; Opus required for hardware acceptance |
| `mxiang.camera.c500ch` | `primary`, `secondary` | auto negotiation | `3` for both lenses | H.264 or H.265 accepted and recorded per lens | request audio; PCMA or Opus accepted when present and recorded per lens |

Each profile contains the one raw quality value used at runtime; there is no user or runtime `sd`/`hd` selection path. All profiles request audio. Audio absence does not prevent video startup, but the first two profiles must negotiate their listed audio codec during hardware acceptance. The `mxiang.camera.c500ch` profile treats audio as optional and records the detected codec or absence independently for each lens.

Every model shipped in the automatic allowlist must pass its own hardware acceptance. An equivalent model may assist protocol development but cannot satisfy another model's release gate. A model unavailable for acceptance is removed from the shipped allowlist rather than covered by substitution.

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

The bootstrap layer reuses the existing `MiotCloud` login state and selected region through a dedicated `async_miss_get_vendor()` method. It does not use the generic cloud request logging path for sensitive request or response values.

Its input is an account/region binding, device DID, `device.info.host`, and the caller's absolute startup deadline. The host must be a numeric RFC 1918 IPv4 address or resolve once to exactly one distinct RFC 1918 IPv4 address. Bootstrap rejects public, loopback, link-local, multicast, unspecified, IPv6, and ambiguously resolved addresses. It pins the validated numeric address for the full connection attempt so later DNS changes cannot redirect discovery.

If the host is empty, malformed, unresolvable, or outside the accepted address scope, bootstrap raises the sanitized `lan_host_unavailable` error. It does not refresh the cloud device record, infer another host, call `miss_get_vendor`, create a socket, or enter a reconnect loop.

For each full connection or reconnect, bootstrap:

1. Generates an ephemeral client Curve25519 key pair.
2. Calls `/v2/device/miss_get_vendor` with hex `app_pubkey`, `did`, and `support_vendors: TUTK_CS2_MTP`.
3. Parses `vendor.vendor`, `vendor.vendor_params.p2p_id`, top-level `public_key`, and top-level `sign`.
4. Accepts only vendor value `4`, which maps to CS2.
5. Hex-decodes and validates the 32-byte device public key.
6. Returns an immutable `MissBootstrap` containing the LAN host, optional P2P ID, client key pair, device public key, signature, and non-sensitive transport metadata.

A cloud network attempt is capped at 10 seconds and must also honor the caller's shorter remaining deadline. Cancellation is always re-raised. A token-expired result may call the existing authentication refresh once and retry the request once with the same key pair. A second authentication failure is surfaced without another login loop. A failed CS2 connection discards this bootstrap; a full reconnect obtains new key material.

The dedicated method never logs the DID, key pair, device public key, signature, request body, or raw response.

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

#### Discovery and Transport Negotiation

All transport modes begin with UDP LAN discovery against the pinned RFC 1918 camera address on port `32108`:

- `auto` accepts either UDP-ready or TCP-ready.
- `udp` accepts only UDP-ready.
- `tcp` accepts only TCP-ready.
- Discovery accepts packets only when their source IP equals the pinned camera address.
- A TCP-ready response closes the discovery socket and opens TCP only to the same pinned camera IP and the validated source port from that response.

A ready message cannot redirect TCP to another IP. `auto` is one discovery exchange and one ready selection, not sequential UDP and TCP attempts. A discovery, connect, or login failure closes the current transport. Only a subsequent full reconnect repeats cloud bootstrap and discovery.

#### Reliability and Bounds

The CS2 implementation defines these hard bounds:

- UDP outbound commands retransmit once per second, at most five times.
- The media reorder window holds at most 250 packets and 4 MiB.
- The command queue holds at most 10 items.
- The media queue holds at most 100 items.
- Incomplete media access-unit assembly holds at most 8 MiB per track.
- Sixteen-bit CS2 sequence numbers use wraparound-aware ordering.

Packets older than the active reorder window are discarded. An unrecoverable video gap discards the partial access unit and waits for the next complete keyframe. Queue or byte-limit overflow terminates the affected session with a bounded-resource error rather than retaining arbitrary data.

TCP framing follows the CS2 length wrapper and DRW framing. TCP ping follows the reference behavior: while processing DRW traffic it is emitted at most once per second. The first release does not add an independently scheduled TCP keepalive without separate hardware evidence.

### MISS Session and Media

A MISS session owns one `(did, lens)` connection. It performs:

- Plaintext CS2 login using the cloud signature and ephemeral client public key.
- Encrypted MISS command encoding and decoding after login.
- Start-media and stop-media commands.
- Model-profile lens, quality, and audio selection.
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

All profiles request audio, and that fixed request behavior participates in the session key. Audio remains optional for runtime video startup. After mandatory video configuration and a complete keyframe are available, the session waits up to two seconds or the caller's remaining startup deadline for audio. If audio is absent, it starts video-only and records the condition in diagnostics. Hardware acceptance still requires PCMA for `isa.camera.hlc7` and Opus for `chuangmi.camera.039c01`; each `mxiang.camera.c500ch` lens records PCMA, Opus, or no audio without failing acceptance solely because audio is absent.

## Automatic Entity and Profile Design

There are no new P2P config-flow or options-flow fields. Runtime behavior is selected entirely by static model profiles in `device_customizes.py`:

- Models with `p2p_profile` automatically use the native P2P live-stream path.
- Models without `p2p_profile` retain their current live-stream behavior.
- Transport, lens list, one raw quality value per lens, accepted video codec, audio request behavior, and expected acceptance codec come from the profile.
- Removing or changing a profile requires a normal integration update or existing customization reload; there is no live mutation.

During converter initialization, a profiled camera expands into one Camera entity per profile lens:

- `primary` preserves the existing converter and entity unique ID.
- `secondary` receives a distinct converter attribute, explicit unique-ID suffix, distinct `full_name`, and `use_unique_attr=True` so current converter deduplication cannot merge it.
- Both entities remain attached to the same Home Assistant device registry device.

A profiled Camera entity advertises `CameraEntityFeature.STREAM` during initialization and returns only its native P2P loopback source for live streaming. A P2P failure is surfaced explicitly; it does not silently substitute a cloud event video or legacy MIoT HLS action. Existing event snapshots, event metadata, and non-live camera attributes may continue updating.

The two `mxiang.camera.c500ch` entities own independent sessions, reconnect independently, and can consume two camera connection slots. There is no UI switch to disable native P2P for a profiled model. Restoring the previous live-stream path requires removing that model's profile.

The existing `keep_streaming` customization retains lazy semantics. It creates a persistent P2P lease only after the entity's first successful HTTP source GET; it does not connect at entity creation.

## Session Management and Data Flow

Each `HassEntry` owns a `ChannelSessionManager`. A session key contains account entry, region, DID, lens, resolved raw quality, transport policy, and audio policy. Sessions are never shared across accounts, regions, lenses, or profile settings.

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
  -> start media for profile lens and quality
  -> codec and complete-keyframe probe
  -> per-GET RTP/FFmpeg bridge
  -> first MPEG-TS bytes
  -> Home Assistant Stream/HLS
```

`stream_source()` returns the same entity-lifetime URL in under one second and never waits for bootstrap or codec probing. This is below Home Assistant's ten-second camera source timeout.

The HTTP GET uses one 25-second monotonic startup deadline covering handler entry through receipt of the first MPEG-TS chunk:

- A cloud network attempt is capped at 10 seconds.
- Discovery and transport connect are capped at 5 seconds.
- MISS login is capped at 5 seconds.
- Codec and complete-keyframe probing must finish with at least 5 seconds still reserved for RTP/FFmpeg startup and the first MPEG-TS chunk.

The per-stage caps are ceilings relative to the remaining budget, not additive allowances. Each stage must complete in `min(stage_cap, remaining_budget)`. Setup fails immediately if the remaining budget before a stage is less than that stage's reserved minimum. The bridge must read one bounded MPEG-TS chunk by the absolute deadline before preparing the HTTP success response, then immediately write that chunk.

A setup timeout prepares and completes HTTP 504 with `write_eof()` by the 25-second deadline. After the response is complete, the same handler awaits subprocess termination, kill, and drain in its `finally` block; this may delay handler return by the separate five-second terminate and two-second kill limits but cannot delay delivery of the error response. A non-timeout bootstrap, protocol, or codec failure similarly completes HTTP 502 before cleanup. Entry unload tracks and awaits handlers that are still cleaning up.

Multiple HTTP consumers of one entity acquire leases on the same healthy MISS session. The fourth concurrent bridge is the per-lens limit; a fifth GET returns HTTP 503 with `Retry-After: 5`. Consumers never receive HTTP 409 for ordinary concurrency.

When the final consumer releases its lease, the manager starts a 30-second idle timer. A new GET cancels the timer and reuses a healthy session. An activated `keep_streaming` lease remains until entity removal or config-entry unload.

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

The URL remains stable for the entity lifetime. The server is reference-counted by entries that contain profiled devices. The final such entry unload stops both `TCPSite` and `AppRunner`.

The endpoint supports Home Assistant Core, Home Assistant Stream/HLS, and FFmpeg processes running in the Home Assistant host network namespace. A go2rtc or FFmpeg process in another container or host cannot resolve the loopback endpoint and is unsupported in the first release.

### Per-GET FFmpeg Bridge

Each accepted GET creates an independent FFmpeg bridge while sharing the underlying MISS session. Every bridge has its own random RTP SSRCs, sequence numbers, timestamp bases, RTP/RTCP port pairs, FFmpeg process, stdout/stderr tasks, and HTTP response.

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

The bridge uses Home Assistant's configured FFmpeg binary. One integration-wide allocator leases non-overlapping even RTP and following RTCP ports under an asynchronous lock. It initially binds reservation sockets to both ports, records the lease, and closes the reservation sockets immediately before a newly spawned FFmpeg consumes the SDP. The allocator retains logical ownership of the pair until bridge cleanup. If FFmpeg exits during startup with a bind error, the bridge releases the pair and retries with a new pair at most three times within the shared startup deadline.

FFmpeg receives the equivalent arguments:

```text
-hide_banner -loglevel warning
-protocol_whitelist pipe,udp,rtp
-f sdp -i pipe:0
-map 0:v:0 -c:v copy
-map 0:a:0? -c:a aac -b:a 64k
-f mpegts -mpegts_flags +resend_headers pipe:1
```

The bridge writes the complete SDP once and closes stdin. While FFmpeg remains alive, it polls both leased receive ports for `EADDRINUSE` every 20 ms for at most two seconds; both ports must be bound before the bridge subscribes to session frames. Failure releases the pair and enters the bounded port-pair retry path. Cached parameter sets and a complete keyframe are sent only after this readiness check, so datagrams emitted before FFmpeg input initialization are not required for startup.

FFmpeg copies H.264 or H.265 video and transcodes detected PCMA or Opus audio to AAC. It writes MPEG-TS to stdout. The GET handler reads one bounded first chunk before preparing `Content-Type: video/mp2t`, then streams stdout directly to the HTTP response.

There is no unbounded application media queue. RTP uses non-blocking loopback UDP sends; datagrams that encounter socket backpressure are dropped and counted. HTTP backpressure can block only that bridge's FFmpeg stdout. One slow or disconnected consumer cannot block another bridge or the shared MISS session.

H.265 remains stream-copied because unconditional video transcoding is too expensive for typical Home Assistant hosts. Playback is client-dependent and covered by the frontend acceptance matrix.

## Reconnection Strategy

Recovery runs only while a session has an HTTP consumer lease or an activated `keep_streaming` lease.

1. Ten seconds without valid media first sends stop-media and start-media on the current connection.
2. Failure closes the transport and discards bootstrap and key references.
3. A full reconnect obtains new MISS bootstrap material and repeats discovery negotiation.
4. Retries use jittered delays of 1, 2, 5, 15, and then at most 30 seconds while a lease remains active.
5. Successful codec probing followed by a complete keyframe resets backoff.

A missing or invalid host stops recovery with `lan_host_unavailable`; it does not refresh cloud device records or loop indefinitely. A failure in one `mxiang.camera.c500ch` lens does not cancel or restart the other lens.

P2P connection-slot exhaustion leaves live streaming unavailable with a sanitized diagnostic. Event snapshots and non-live attributes may continue updating, but they are not substituted as the live source.

## Error Handling and Diagnostics

Errors are categorized before crossing the protocol boundary:

- LAN host unavailable.
- Cloud authentication.
- Cloud bootstrap timeout or response invalid.
- Unsupported vendor.
- Key negotiation or crypto input invalid.
- CS2 discovery or connect timeout.
- CS2 framing or bounded-queue violation.
- CS2 login rejection.
- MISS command timeout or malformed command.
- Media probe timeout.
- Codec unsupported or media malformed.
- HTTP consumer limit.
- RTP, bridge, or FFmpeg failure.
- Stream stalled.

Unknown MISS message types are counted and ignored only when framing and lengths remain valid. Invalid lengths, impossible state transitions, malformed decoded commands, transport desynchronization, or bounded-resource violations terminate the session safely.

A new `diagnostics.py` implements `async_get_config_entry_diagnostics()` and reads sanitized snapshots from entry-owned managers. Diagnostics may expose:

- Model profile and lens.
- Selected transport policy and negotiated transport.
- Resolved raw quality.
- Detected video and audio codecs.
- Detected resolution and sample rate.
- Reconnect count.
- Dropped, reordered, duplicate, and malformed packet counters.
- Active lease and bridge counts.
- Age of the last successful media frame.
- Sanitized error category.

Diagnostics and Camera state must not expose:

- DID, account ID, or LAN host.
- passToken, serviceToken, or cloud request/response data.
- Client private key, shared key, device public key, or cloud signature.
- Route token, full route URL, or FFmpeg command containing the URL.
- Raw MISS, CS2, RTP, or media payloads.

## Resource Lifecycle

Every session is owned by one `HassEntry`; every HTTP bridge is owned by one active GET; the loopback server and RTP port allocator are integration-wide and reference-counted.

Config-entry unload is ordered as follows:

1. Invalidate the entry's route mappings so new GETs return 404.
2. Close and await all active HTTP/FFmpeg bridges.
3. Release activated `keep_streaming` leases.
4. Send stop-media on usable sessions.
5. Cancel session reader, writer, reconnect, and transport maintenance tasks.
6. Close CS2 sockets and unblock waiters.
7. Remove cached codec data, bootstrap/key references, and session references.
8. Decrement the loopback server reference count and stop the site and runner after the final entry.

A single GET bridge closes as follows:

1. Remove its frame subscription.
2. Close its RTP/RTCP sockets.
3. Terminate FFmpeg and wait up to five seconds.
4. Kill FFmpeg if necessary and wait up to two additional seconds.
5. Await bounded stdout and stderr drain tasks.
6. Close the HTTP response.
7. Release the session lease in `finally`.

Client disconnect, response write failure, cancellation, FFmpeg failure, Home Assistant stop, and partial initialization all use these idempotent cleanup paths. One bridge failure does not close sibling bridges or a healthy shared session.

## Security

- Camera media remains on the local camera network and Home Assistant loopback interface; cloud relay is not implemented.
- Camera discovery accepts only a pinned RFC 1918 IPv4 target, and TCP-ready negotiation cannot redirect the connection to another IP.
- Internet access is required for each full MISS bootstrap.
- Ephemeral private keys, shared keys, signatures, and endpoint tokens remain in memory only.
- Python cannot guarantee physical memory zeroization; cleanup removes references and does not claim secure erasure.
- The media server binds only to `127.0.0.1` and uses independent entity-lifetime authentication tokens.
- Logging performs structured redaction before values are passed as logger arguments; it does not rely on the current `record.msg` filter.
- Sanitized fixtures replace all account, device, key, signature, and address material.
- The implementation documents that MISS uses unauthenticated ChaCha20 because protocol compatibility prevents substituting an authenticated cipher.
- The lack of a user-facing disable switch and the inability of external go2rtc containers to open the loopback source are documented release limitations.

## Proposed Code Boundaries

Exact names may be adjusted to existing package conventions, but responsibilities remain separated:

```text
custom_components/xiaomi_miot/core/xiaomi_p2p/
  __init__.py          public types and factories
  cloud.py             dedicated sanitized MISS bootstrap adapter
  crypto.py            NaCl-compatible key derivation and ChaCha20
  miss.py              login, encrypted commands, and session state
  cs2/
    protocol.py        typed frames, wire constants, and framing
    transport.py       typed transport protocol/interface
    udp.py             discovery, ACK, reorder, and retransmission
    tcp.py             TCP framing and reference-compatible ping
  media.py             media headers, codecs, access units, and frames
  rtp.py               codec-specific RTP packetization
  bridge.py            per-GET RTP, FFmpeg, and MPEG-TS response
  server.py            loopback wildcard route and RTP port allocator
  manager.py           entry sessions, leases, idle timeout, and shutdown
```

Existing integration points remain in:

- `core/xiaomi_cloud.py`: dedicated `async_miss_get_vendor()` entry point.
- `core/device.py`: profile lookup and converter expansion.
- `core/hass_entry.py`: manager ownership and unload ordering.
- `camera.py`: Camera feature flag and stable loopback `stream_source()`.
- `core/device_customizes.py`: allowlisted model profiles.
- `diagnostics.py`: sanitized config-entry diagnostics.

Protocol modules do not import Home Assistant entity classes.

## Testing Strategy

### Cloud and Security Tests

- Missing, malformed, unresolvable, public, loopback, link-local, multicast, unspecified, IPv6, and ambiguously resolved hosts return `lan_host_unavailable` without refreshing cloud device records, calling `miss_get_vendor`, or creating sockets.
- DNS is resolved once per connection attempt, the numeric RFC 1918 address is pinned, and discovery packets or TCP-ready endpoints from another IP are rejected.
- Cloud request timeout honors both its ten-second cap and the caller deadline.
- Cancellation propagates without being converted to a normal response.
- Token expiration permits exactly one authentication refresh and one retry.
- A second authentication failure does not loop.
- Captured integration, aiohttp access, and aiohttp exception logs contain no DID, host, token, key, signature, request body, raw response, request object, raw request target, `path_qs`, `rel_url`, or query string. Real authenticated GETs and forced handler exceptions exercise every logging path.
- Token generation is patched with deterministic 32-byte input to assert 256 bits of source entropy, and route mapping representations omit the token.
- Diagnostics and entity state contain no prohibited values.
- Unknown, invalid, and unloaded loopback routes return 404.

### Protocol Unit Tests

- Curve25519 plus HSalsa20 shared-key vectors.
- ChaCha20 nonce layout, encode/decode vectors, short nonce, and malformed input.
- Plaintext login and encrypted `0x1001` command fixtures.
- CS2 channel `0` command and channel `2` media separation.
- CS2 fragmentation, concatenation, lengths, and 16-bit sequence wraparound.
- UDP discovery with UDP-ready and TCP-ready in auto mode, proving one discovery exchange and no sequential transport fallback.
- Forced UDP/TCP rejection of the opposite ready type.
- Primary start-media emits `videoquality`; secondary emits `videoquality: -1` plus `videoquality2`, using each profile's exact raw quality.
- UDP ACK, duplicate, reorder, loss, one-second retransmission, and retry exhaustion.
- The 250-packet, 4 MiB, 10-command, 100-media, and 8 MiB bounds.
- TCP partial frames, reference-compatible DRW ping, and disconnects.
- MISS media header offsets, endianness, and supported codec IDs.
- H.264/H.265 parameter-set and complete-access-unit detection.
- PCMA/Opus codec and timestamp normalization.

### Simulated Peer Tests

A fake CS2 peer covers UDP and TCP without real Xiaomi credentials. It injects:

- Delayed and missing acknowledgements.
- Reordered and duplicated packets.
- Partial TCP frames and framing desynchronization.
- Disconnects during discovery, login, probe, and steady media.
- Structurally invalid encrypted commands and media bodies.
- Keyframe loss and later recovery.
- Independent failures for the two `mxiang.camera.c500ch` lenses.

Tests assert negotiation, reconnect behavior, fresh bootstrap usage, bounds, task cleanup, and error categorization.

### RTP and FFmpeg Bridge Tests

- H.264 RFC 6184 and H.265 RFC 7798 single-NAL and fragmented packetization with a 1200-byte maximum RTP datagram.
- PCMA 8 kHz static payload `8`, PCMA 16 kHz dynamic payload `97`, and Opus RFC 7587 payload `111`.
- Video 90 kHz, exact PCMA sample-rate, and Opus `48000/2` clocks.
- Marker bits, timestamp normalization from one shared media origin, sequence wrap, and independent bridge SSRCs.
- Immediate and five-second compound RTCP sender reports use one common NTP origin and correct packet/octet counters.
- Exact H.264/H.265 parameter-set SDP, `a=rtpmap`, `a=rtcp`, Opus stereo, and PCMA sample-rate attributes.
- Non-overlapping RTP/RTCP reservation, 20 ms receive-port readiness polling, logical lease ownership, bind-failure retry, and final release.
- SDP stdin is closed, the protocol whitelist includes `pipe,udp,rtp`, and the complete FFmpeg input/map/codec/MPEG-TS command matches the design.
- Home Assistant's configured FFmpeg binary is used.
- Video is stream-copied and PCMA/Opus is transcoded to AAC.
- The first MPEG-TS chunk is read before HTTP 200 preparation.
- Four concurrent GETs share one MISS session and use independent FFmpeg processes.
- Disconnecting or slowing one bridge does not affect another.
- A fifth GET returns 503 with `Retry-After: 5`.
- FFmpeg graceful exit, five-second terminate timeout, two-second kill timeout, and stderr cleanup.
- The server binds only to `127.0.0.1` and the route is inaccessible through LAN-bound addresses.

### Home Assistant Tests

- Profiled models automatically use P2P; unprofiled models retain existing behavior, and no new config-flow or options-flow fields are registered.
- Each shipped profile resolves to its exact transport, lens list, raw quality, accepted video codec, and audio request policy.
- `mxiang.camera.c500ch` creates stable, distinct primary and secondary unique IDs.
- Converter deduplication does not remove the secondary lens.
- One session is shared by consumers of the same lens.
- The two `mxiang.camera.c500ch` lenses use independent sessions.
- `stream_source()` is stable and completes in under one second without cloud or socket I/O.
- Exactly one wildcard route is registered before server startup; entity setup and unload mutate only the in-memory route map.
- GET startup uses one 25-second absolute deadline covering bootstrap through first MPEG-TS bytes, reserves five seconds for FFmpeg, and delivers either HTTP 200 with media or HTTP 504 within that wall-clock bound.
- P2P failure does not substitute legacy live video.
- Cloud event snapshots and non-live camera attributes continue updating.
- `keep_streaming` acquires a persistent lease only after the first successful GET; failed, rejected, and timed-out GETs never activate it.
- Each lens enforces its own four-GET limit, so simultaneous consumers on the other lens do not consume that limit.
- Config-entry unload covers active GETs, idle sessions, reconnect, and partial initialization.
- Unload leaves no P2P tasks, sockets, route mappings, RTP ports, or FFmpeg processes.

H.264 release support is established through sanitized protocol fixtures, fake-peer tests, and FFmpeg bridge tests. An H.264 hardware profile is not a first-release gate.

### Hardware Acceptance

Under a normal local network:

- `stream_source()` returns in under one second.
- First playable media appears within 12 seconds.
- A forced disconnect recovers within 30 seconds.
- Audio and video do not sustain more than 250 ms of drift.
- A ten-minute deterministic network test with 2% independent packet loss plus one five-packet burst every 30 seconds stays within all bounds and resumes playback no later than five seconds after the next complete keyframe.
- `isa.camera.hlc7` runs continuously for 24 hours over its forced UDP profile with H.265 and PCMA.
- `chuangmi.camera.039c01` runs continuously for 24 hours over its forced TCP profile with H.265 and Opus.
- Both `mxiang.camera.c500ch` lenses run concurrently for eight hours using auto transport negotiation without cross-lens data or coupled restart. The acceptance record captures the transport and codecs negotiated for each lens.
- Four simultaneous consumers of one lens run for one hour without cross-consumer blocking or an additional MISS session.
- Connection-slot interference with Mi Home while both `mxiang.camera.c500ch` lenses are active is recorded as an accepted limitation.

A hardware run that negotiates H.265 is incomplete until at least one frontend path in the matrix below plays that exact profile/lens during the run. A transport-only 24-hour result cannot satisfy the H.265 release gate.

The H.265 frontend acceptance record is part of this spec rather than a separate informal note. Each executed cell must record the Home Assistant version, client OS/version, browser or Companion App version, negotiated codec, HLS playback path, result, and limitation.

| Profile/lens | Desktop Chromium | Desktop Safari | iOS Companion App | Android Companion App |
| --- | --- | --- | --- | --- |
| `isa.camera.hlc7` primary | Not run — release blocking | Not run — release blocking | Not run — release blocking | Not run — release blocking |
| `chuangmi.camera.039c01` primary | Not run — release blocking | Not run — release blocking | Not run — release blocking | Not run — release blocking |
| `mxiang.camera.c500ch` primary, if H.265 | Not run — conditional release gate | Not run — conditional release gate | Not run — conditional release gate | Not run — conditional release gate |
| `mxiang.camera.c500ch` secondary, if H.265 | Not run — conditional release gate | Not run — conditional release gate | Not run — conditional release gate | Not run — conditional release gate |

The current Draft status means these hardware results have not been executed. The document cannot move to release-ready status while a release-blocking cell remains `Not run`. Universal H.265 playback is not required, but at least one recorded Home Assistant frontend path must play each H.265 profile/lens, and every failed path must retain its recorded limitation.

## Primary Risks

1. Xiaomi firmware differences in CS2 commands, quality identifiers, and packet formats.
2. UDP reorder and retransmission behavior under real Wi-Fi loss.
3. H.265 frontend compatibility without video transcoding.
4. FFmpeg subprocess, RTP port, and HTTP response cleanup during rapid reloads.
5. Xiaomi Cloud token expiration or API changes preventing new bootstrap.
6. `mxiang.camera.c500ch` quality behavior causing CS2 buffer errors or incorrect dimensions.
7. Two independent `mxiang.camera.c500ch` sessions exhausting connection slots and blocking Mi Home playback.
8. Automatic enablement without a UI disable switch affecting a validated model with divergent firmware.
9. Loopback-only media preventing use by go2rtc or FFmpeg in another container.

## Completion Criteria

The feature is ready for release only when:

- All cloud, protocol, fake-peer, bridge, and Home Assistant tests pass.
- The three hardware profiles meet their duration, startup, recovery, drift, and bounded-loss targets.
- The H.265 frontend compatibility matrix contains no release-blocking `Not run` cells, records required client versions and outcomes, and has at least one working HA frontend path for each H.265 profile/lens.
- No credential, key, signature, host, DID, route token, or raw connection material appears in entity state, diagnostics, or logs.
- Config-entry unload leaves no P2P tasks, sockets, route mappings, RTP ports, HTTP responses, or FFmpeg processes.
- Unprofiled cameras, existing cloud-event behavior, and non-camera tests remain unchanged.
- Limitations for Internet bootstrap, LAN camera access, loopback-only consumers, H.265 playback, unsupported protocols, automatic enablement, and dual-lens connection slots are documented.
