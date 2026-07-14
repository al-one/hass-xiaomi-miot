# Xiaomi Cloud Authentication Reauth Design

## Summary

When a Xiaomi main-cloud (`xiaomiio`) or XiaoAI-cloud (`micoapi`) token is explicitly rejected and automatic login cannot recover it, Xiaomi Miot will start Home Assistant's native reauthentication flow. The flow handles password replacement, Xiaomi security verification tickets, and captchas. It also creates a persistent notification, as an additional reminder and fallback.

Authentication detection and automatic-login suppression remain in `MiotCloud`; Home Assistant flow lifecycle, SID coordination, flow cooldown, and ConfigEntry updates belong to `HassEntry`. Each SID is recovered independently. The implementation requires Home Assistant 2024.11.0 or newer.

## Goals

- Detect explicit cloud authentication failures for both `xiaomiio` and `micoapi`.
- Attempt automatic login before involving the user.
- Start a native Home Assistant reauth flow when automatic login fails with a canonical authentication category; transient login failures are suppressed without reauth.
- Handle password, `verify_ticket`, and captcha challenges in reauth.
- Recover only the failed SID without overwriting another SID's valid credentials.
- Prevent repeated login attempts, duplicate flows, and duplicate notifications.
- Preserve local device operation while cloud authentication is unavailable when cached inventory and valid local connection data are available.
- Avoid exposing passwords, tokens, cookies, internal verification sessions, or complete server responses. User-facing verification URLs and captcha images are displayed only where required for recovery.

## Non-goals

- Reauth does not change the Xiaomi username, server region, connection mode, or device filters.
- This work does not implement Home Assistant's `reconfigure` flow. User-initiated changes to account configuration remain in the existing configuration/options path.
- Network timeouts, connection errors, HTTP 5xx responses, malformed responses, and ordinary API business errors do not trigger reauth.
- This work does not redesign Xiaomi's login protocol or replace the existing credential store.
- This work does not combine `xiaomiio` and `micoapi` into one verification session.

## Existing Behavior

`MiotCloud.async_check_auth()` currently checks a token, attempts `async_relogin()`, and creates a persistent notification if recovery fails. Explicit token failures include API codes `2` and `3`, messages containing `auth err`, `invalid signature`, and `SERVICETOKEN_EXPIRED`. Raw requests also clear their session after HTTP 401.

The options flow already accepts Xiaomi verification tickets and captchas. The micoapi options step has additional handling for an STS 401 after verification. No `async_step_reauth()` exists, and cloud clients do not currently report authentication failures to their owning ConfigEntry.

## Architecture

### `MiotCloud`: authentication detection and recovery

`MiotCloud` remains responsible for cloud protocol behavior:

1. Detect an explicit authentication rejection.
2. Clear only the rejected SID's token and HTTP session.
3. Use a per-cloud single-flight recovery task to run one automatic login for concurrent failures.
4. If login succeeds, retry the original request at most once and let the episode finalizer persist the refreshed token after all callers settle without another rejection.
5. If login fails with a canonical authentication category, set that cloud's ten-minute automatic-login suppression deadline and report the category once through the asynchronous callback bound by `HassEntry`. A timeout, connection error, or HTTP 5xx during automatic login sets the same suppression deadline to prevent a login storm but produces no `AuthFailureReport` and never starts reauth.

HTTP transport implementations detect status 401 before consuming or logging the response body and raise a sanitized `MiCloudAuthError` with `AuthFailureCategory.TOKEN_EXPIRED`, the current `CloudSid`, and `LoginStage.API_REQUEST`. API-level token-expired codes and messages are classified after JSON parsing without constructing a transport exception. Both forms enter the same recovery path in `async_request_api()`, but retain distinct terminal contracts: when automatic login is suppressed, fails, or succeeds but the one permitted retry receives another explicit rejection, a transport-level rejection re-raises its sanitized typed exception, while an API-level rejection returns the parsed rejection result from the request attempt that terminates the loop unchanged. The transport exception contains only `AuthFailureCategory`, `CloudSid`, and internal `LoginStage`; it never retains a response object, body, headers, cookies, or request payload.

Every synchronous `requests` path that can classify an authentication HTTP status uses `stream=True` and a response context manager. It inspects only `status_code` before body access; for ordinary API 401, account-login 401/403, and micoapi STS 401 it closes the response and raises the mapped sanitized `MiCloudAuthError` without accessing `.content`, `.text`, `.json()`, response headers, or response cookies. Non-authentication statuses retain the existing body-read, parse, and decrypt behavior inside the context manager.

Every `aiohttp` path uses an async response context manager, inspects `status` before `.read()`, `.text()`, `.json()`, or decryption, and calls `release()` before raising the mapped exception. Context exit remains the final connection-release guarantee. This status-before-body contract applies to ordinary request, raw request, RC4 request, account-login, and micoapi STS transports; no authentication rejection body is buffered merely to discard it later.

`async_request_api()` owns the complete request recovery loop. It performs the original request, joins or creates the cloud instance's single-flight automatic-login task after an explicit authentication rejection, and retries the original request at most once after successful login. A second authentication rejection claims the episode's report-once latch without another login or recursive request call. While automatic-login suppression is active, an explicit authentication rejection short-circuits the recovery loop without invoking the authentication-failure callback and preserves the applicable transport-exception or parsed-result terminal contract. Timeouts, connection failures, HTTP 5xx responses, empty responses, parse failures, and business errors keep their existing behavior and do not invoke the callback.

Each HassEntry-bound runtime cloud has a process-local `auth_rejected` flag. An explicit transport- or API-level authentication rejection sets it before clearing only the service token and HTTP session; successful automatic recovery, successful reauth, or an ordinary authenticated API success clears it. When `auth_rejected` is True and the service token is absent, a later runtime request skips the legacy no-token preflight login and executes its original API operation once with the remaining signing state. An explicit rejection during active suppression terminates immediately without login, episode allocation, or callback. After suppression expires, the next explicit rejection may allocate one new episode. A non-authentication request failure retains its ordinary behavior and neither starts recovery nor clears the flag.

A missing token with `auth_rejected` False retains the existing explicit-login behavior used by initial setup and ownerless Config/Options Flow clouds. Private reauth candidates submit through `CloudLoginFlowHelper`, not this runtime no-token path.

The authentication-failure callback receives a structured `AuthFailureReport` containing:

```python
class CloudSid(StrEnum):
    XIAOMIIO = "xiaomiio"
    MICOAPI = "micoapi"


@dataclass(frozen=True)
class AuthEpisodeToken:
    runtime_generation: int
    episode_id: int


@dataclass(frozen=True)
class AuthFailureReport:
    sid: CloudSid
    category: AuthFailureCategory
    episode: AuthEpisodeToken
```

`runtime_generation` is assigned by `EntryReauthCoordinator` when a new `HassEntry` generation attaches; `episode_id` is monotonically allocated for that generation and SID when an explicit rejection creates a single-flight recovery task. The same immutable token is carried by the failure and recovery-succeeded callbacks. The coordinator accepts a callback only when its token matches the current SID state; a callback from an older runtime generation or replaced episode is an idempotent no-op.

```python
async def async_recovery_succeeded(
    sid: CloudSid,
    episode: AuthEpisodeToken,
) -> None:
    ...
```

```python
class AuthFailureCategory(StrEnum):
    INVALID_CREDENTIALS = "invalid_credentials"
    TOKEN_EXPIRED = "token_expired"
    VERIFY_REQUIRED = "verify_required"
    CAPTCHA_REQUIRED = "captcha_required"
    ACCESS_DENIED = "access_denied"
```

The enum is the single contract shared by cloud exceptions, the authentication-failure callback, Config Flow routing, and tests. Network failures, timeouts, HTTP 5xx responses, and other non-authentication failures are not enum members and never produce an `AuthFailureReport`.

The callbacks do not carry a `MiotCloud`, another secret-bearing object, the original exception, response bodies, request payloads, tokens, cookies, `ssecurity`, captcha cookies, or identity sessions. Cloud exceptions distinguish authentication failure as a typed category rather than a formatted string. Existing `MiCloudAccessDenied` and `MiCloudNeedVerify` are still allowed internally but their message text must never reach logs, notifications, or flow placeholders.

### `HassEntry`: Home Assistant lifecycle coordination

`HassEntry` owns ConfigEntry-specific behavior. It binds authentication-failure and recovery-succeeded callbacks whenever it creates or reuses a ConfigEntry runtime cloud. `MiotCloud` names the optional coordinating reference `hass_entry`; `owner` is not used as the parameter or instance-field name.

The bound authentication-failure callback receives only `AuthFailureReport`. Before accessing runtime cloud state, `HassEntry` requires itself to remain the coordinator's currently attached generation and requires the report token to match the current SID episode, then resolves `self.clouds.get(report.sid)` locally. A missing cloud, detached generation, or replaced token is a stale-callback no-op. The callback may derive only the permitted notification variant and displayable verification URL from that current cloud; neither the report nor coordinator state stores a cloud reference. A later Config Flow resolves the current runtime cloud again through its attached `HassEntry` before transferring challenge ownership.

Cloud instances are tracked by SID and coordinated by exactly one `HassEntry`:

```python
clouds: dict[CloudSid, MiotCloud]
cloud_creation_locks: dict[CloudSid, asyncio.Lock]

async def async_get_cloud(
    self,
    sid: CloudSid = CloudSid.XIAOMIIO,
    *,
    login: bool = False,
) -> MiotCloud | None:
    ...

External configuration strings are normalized to `CloudSid` at this boundary; no arbitrary SID string enters runtime state.
```

`async_get_cloud()` serializes creation per SID, so concurrent requests for the same ConfigEntry and SID produce one instance while different SIDs remain independent. The compatibility property remains nullable for local/token ConfigEntries that have not created a main cloud:

```python
@property
def cloud(self) -> MiotCloud | None:
    return self.clouds.get(CloudSid.XIAOMIIO)
```

A caller that requires cloud behavior uses `async_get_cloud()` and handles its optional result explicitly. Local device construction may retain `cloud=None`; reading the compatibility property never creates a cloud and never raises `KeyError`.

`MiotCloud.from_token()` exposes the construction boundary explicitly:

```python
@classmethod
async def from_token(
    cls,
    hass: HomeAssistant,
    config: dict,
    login: bool | None = None,
    *,
    hass_entry: HassEntry | None = None,
    reuse_global_session: bool = True,
) -> MiotCloud:
    ...
```

It supports exactly three scopes:

1. A ConfigEntry runtime cloud passes `hass_entry=self` and `reuse_global_session=False`. It neither reads nor writes `hass.data[DOMAIN]["sessions"]`; it binds the entry callback and is registered only in `hass_entry.clouds[sid]`.
2. A reauth candidate passes no `hass_entry` and `reuse_global_session=False`. It is private to the Config Flow, has no runtime callback, never enters either registry, and uses non-persisting login until persistence and identity validation succeed.
3. Existing ownerless Config Flow and Options Flow callers omit both keyword arguments. They retain current account/SID global-session reuse behavior outside this feature.

Passing a non-`None` `hass_entry` always disables global-session reuse regardless of the caller-provided flag. Successful login and SID changes must preserve that scope; HassEntry-bound and private clouds must not be inserted into the global session registry as a side effect of login.

Runtime cloud identity is `(entry_id, sid)`. `MiotCloud.unique_id` remains usable for existing Store identity but is not a ConfigEntry runtime-instance key. `MiotCloud.async_change_sid()` delegates to `self.hass_entry.async_get_cloud(sid, login=...)` when `hass_entry` is present. An ownerless instance calls `from_token()` with its existing `reuse_global_session` setting, so a private candidate also remains private when changing SID. This lets reauth reuse the exact runtime cloud that owns `verify_url`, `identity_session`, captcha cookies, and pending login data without crossing ConfigEntry boundaries.

`HassEntry` associates runtime cloud failures with its ConfigEntry and SID, then forwards lifecycle coordination to `EntryReauthCoordinator`. The coordinator is responsible for:

- starting native reauth through `ConfigEntry.async_start_reauth()`;
- tracking which SID is active or pending when one entry has failures for both SIDs;
- enforcing SID-specific flow cooldown after an unsuccessful or cancelled flow;
- creating and dismissing persistent notifications;
- retaining pending state across normal reload;
- clearing runtime failure state after successful authentication.

Home Assistant Core provides entry-level flow locking and deduplication. `EntryReauthCoordinator` does not duplicate the flow manager's lock; it adds only the SID-specific pending, reload handoff, and flow-cooldown behavior that Core does not provide. This flow cooldown is independent of the automatic-login suppression owned by each `MiotCloud`.

## Authentication Failure Data Flow

### Request and automatic recovery

1. A request receives a transport-level HTTP 401 or returns a parsed API-level token rejection.
2. `MiotCloud` logs out only that SID and enters its single-flight login section.
3. The first caller attempts automatic login; concurrent callers await the same result.
4. On success, each caller retries its own original request at most once with the refreshed session.
5. On a canonical authentication-category login failure, `MiotCloud` preserves challenge context, sets suppression, and invokes the authentication-failure callback at most once for the episode. On a timeout, connection error, or HTTP 5xx login failure, it sets suppression but invokes no callback and creates no reauth flow.
6. The request never loops indefinitely and the login failure never replaces its terminal result. A terminal transport-level rejection re-raises the original sanitized `MiCloudAuthError`; a terminal API-level rejection returns that attempt's parsed rejection result unchanged.

#### Single-flight episode callback contract

- An entry-bound episode begins when an explicit authentication rejection synchronously calls `HassEntry.begin_auth_episode()`, registers its first caller, and then creates a cloud-owned login task and finalizer task without an intervening `await`. Concurrent callers join that same episode and register before awaiting it.
- Every caller awaits the shared login task through `asyncio.shield()`, so cancellation of one or every request caller never cancels automatic login or the episode finalizer. After its permitted retry returns, raises, or is cancelled, each caller decrements the episode's waiter count in `finally`; cancellation counts as settled but never as an authentication rejection.
- The finalizer owns completion independently of request callers. It waits for the login task to finish and for every registered caller to settle. If login succeeded and no caller observed a second explicit authentication rejection, it persists the refreshed credentials exactly once and invokes the recovery-succeeded callback once after that attempt. This rule also applies when every request caller was cancelled.
- Normal runtime unload or permanent close is the only owner cancellation path. It explicitly cancels both the generation-owned login and finalizer tasks, waits for them during unload cleanup, and performs neither episode persistence nor either callback after cancellation.
- The episode is tracked by a single report-once latch shared across the recovery task and any concurrent waiter that later hits the same explicit rejection. Whichever caller observes the latch first invokes the authentication-failure callback; every other caller preserves its own terminal transport-exception or parsed-result contract without invoking it.
- Concurrent callers that join an in-progress episode never invoke the authentication-failure callback while awaiting the shared recovery task.
- If automatic-login suppression is active, an explicit authentication rejection preserves its terminal transport-exception or parsed-result contract immediately, does not start a new episode, and does not invoke the authentication-failure callback.
- Suppression expiry does not produce a callback. Only the next post-expiry explicit authentication rejection can begin a new episode and, on failure, invoke the authentication-failure callback again.
- A canonical authentication-category automatic-login failure sets suppression and claims the episode's report-once latch. A timeout, connection error, or HTTP 5xx automatic-login failure sets suppression but does not claim the latch, invoke either callback, or create reauth. A second explicit rejection after an apparently successful login sets suppression and claims the latch. A successful login followed by settled callers and no second rejection clears suppression and `auth_rejected`, invokes no authentication-failure callback, and leaves persistence and the recovery-succeeded callback to the finalizer.
- `xiaomiio` automatic-recovery persistence updates its ConfigEntry token data and lets the existing listener reload once when data changes; `micoapi` saves only its entry-scoped Store and does not reload. Persistence failure is not reclassified as authentication failure: the valid in-memory session remains usable and only a fixed, secret-free persistence error is logged.
- An episode with any second explicit authentication rejection does not persist its candidate token.
- Reauth form submissions never enter `async_request_api()`'s single-flight path and invoke neither runtime callback; their failures are reported through the Config Flow.
- Both callbacks are bound by `HassEntry` and may be unbound on entry unload; an unbound callback skips invocation silently.
- Both callbacks run without holding the original request's critical state; a callback exception is logged and never masks the original request's return value or exception.

#### Automatic-recovery success callback

A HassEntry-bound runtime cloud also binds a single-fired recovery-succeeded callback so the coordinator reconciles state when the cloud quietly regains authentication. The contract is:

- the callback takes `(sid: CloudSid, episode: AuthEpisodeToken)` and is invoked by the episode finalizer at most once after automatic login succeeds, every joined caller has settled, no caller observed a second explicit rejection, and the authoritative persistence attempt has completed;
- private candidates and ownerless globals never invoke it because they have no entry-scoped coordinator;
- the callback fires after the episode's authoritative persistence attempt has completed, whether successful or not; a persistence failure remains a fixed secret-free persistence log and the in-memory session keeps working;
- the callback body runs without holding the original request's critical state; an exception is logged and never masks the request's return value or exception.

On invocation the `EntryReauthCoordinator` first requires the supplied `AuthEpisodeToken` to equal the current state for `(entry_id, sid)`. A missing or mismatched state is an idempotent no-op. A matching callback then performs the following atomic update:

- sets `auth_failed = False` and clears `flow_cooldown_until` and any registration deadline;
- clears a `pending` or `cooldown` phase immediately, but retains a `starting` or `active` phase and its `flow_id` only until the already-created flow or watchdog confirms removal;
- preserves `persistence_inconsistent` and any `pending_compensation`, because restored authentication does not prove that an earlier partial local commit was compensated; when either is present, it retains the active `reauth_save` flow or coordinator-owned compensation state and the notification until restoration or persistence succeeds;
- dismisses that SID's persistent notification only when both `persistence_inconsistent` is False and `pending_compensation` is absent;
- leaves the other SID's state, pending notification, `loaded_hass_entry`, and `watchdog_task` unchanged;
- requests an idempotent pending check so another failed SID remains observable.

When the callback observes a flow that already exists for the SID, it cooperates with that flow rather than racing it:

- when a `starting` SID later self-registers, `async_step_reauth()` first checks `pending_compensation`; if present it registers and routes to compensation-only `reauth_save`. Otherwise, when `auth_failed = False`, it creates no candidate, records terminal success, and returns `self.async_abort(reason="reauth_successful")`; if no flow registers, the watchdog removes the recovered starting state without cooldown;
- an `active` reauth submission step checks `auth_failed` first; when `auth_failed`, `persistence_inconsistent`, and `pending_compensation` are all clear, it clears its private candidate, records terminal success, and returns `self.async_abort(reason="reauth_successful")` without writing credentials. When `pending_compensation` exists, only compensation-only `reauth_save` may run until restoration succeeds; when an active candidate-owning flow has `persistence_inconsistent` without a transferred record, its own `reauth_save` retries snapshot-aware persistence without another Xiaomi login;
- `async_remove()` whose flow ended after recovery-succeeded cleanup and has neither a `persistence_inconsistent` marker nor `pending_compensation` deletes that SID's state, never enters flow cooldown, and never recreates the notification.

A newer explicit rejection installs its `AuthEpisodeToken` before setting `auth_failed = True` and may reclaim any of `pending`, `cooldown`, or `flow_id`. Once replaced, delayed failure or success callbacks from the prior token cannot clear, recreate, or otherwise mutate the new episode's state or notification. The next accepted failure creates a fresh notification with the fixed variant.

### Runtime reauth trigger

The authentication-failure callback accepts `AuthFailureReport`, uses `(entry_id, report.sid)` as the failure key, and ignores it unless `report.episode` is the current token for that SID. An accepted report creates or updates that SID's persistent notification, checks its flow cooldown and current phase, and queries the ConfigEntry's active reauth and reconfigure flows. If another entry-bound flow is active, the failed SID becomes pending and its notification remains visible.

The callback may request a new flow only while the ConfigEntry state is `LOADED`. During initial setup, reload, unload, or any other non-`LOADED` state, it records `auth_failed = True` and `phase = pending`, leaves registration timestamps unset, and returns without calling `async_start_reauth()`. This state gate applies to setup-time authentication failure even when no other flow exists.

When the entry is `LOADED` and no entry-bound flow is active, the callback marks the SID as `starting`, records a 60-second registration deadline, and calls `entry.async_start_reauth(hass, data={"sid": sid})`. Home Assistant 2024.11 returns `None` and creates the flow in a background task, so the caller neither expects a flow result nor records a `flow_id`. A synchronous exception from `async_start_reauth()` starts the flow cooldown immediately; background initialization failure is detected by the watchdog.

Home Assistant Core remains authoritative for ConfigEntry-level locking and duplicate suppression. If a competing reauth or reconfigure flow wins the race after the pre-check, Core may silently skip the requested flow; the watchdog moves the still-failed starting SID to pending behind the active flow rather than treating the race as a creation failure. The two SIDs never share one verification form.

### Setup-time failure

During ConfigEntry setup, main-cloud authentication follows the same automatic recovery rule. If it fails, the integration creates the notification and calls a dedicated non-mutating cache reader:

```python
async def async_load_cached_devices(self) -> list[dict] | None:
    ...
```

The method reads only the existing `xiaomi_miot/devices-<user_id>-<region>.json` Store. It ignores `update_time`, never calls a Xiaomi API, never saves or removes the Store, and returns shallow copies rather than mutating the loaded mapping. A valid empty `devices` list returns `[]`; `None` means the cache is unavailable.

A cache is unavailable when the Store path cannot be derived because `user_id` is absent, the Store is missing or cannot be parsed, the root is not a mapping, `devices` is absent or is not a list, or the list contains no mapping entries. Home Assistant's `.corrupt.<timestamp>` backup is left untouched.

Device filtering and key indexing are extracted into a pure transformation shared by normal cloud loading and cache-only setup:

```python
def devices_by_key(
    devices: list[dict],
    key: str,
    filters: dict,
) -> dict:
    ...
```

It applies the existing hidden-device and `ssid`, `bssid`, `home_id`, `model`, and `did` filters without modifying input items. A missing `mac` uses `did` only as the returned index key; it is not written into the cached device mapping.

Cache-only setup admits a device only when it passes those filters, has nonempty `did` and `model`, uses `local` mode or a supported locally capable `auto` mode, provides nonempty local host and token through `DeviceInfo`, and loads a usable MIOT spec. Cloud-dependent devices are not admitted to the cache-only configuration and remain unavailable until reauth reloads the entry.

If at least one cached device is admitted, the integration completes cache-only setup without calling `async_start_reauth()` directly. Once Home Assistant has transitioned the ConfigEntry to `LOADED`, setup completion requests the coordinator's idempotent pending check, which starts the recorded `xiaomiio` failure through the normal `starting` path. If the cache is unavailable, empty, or yields no admitted local device, setup raises `ConfigEntryAuthFailed` without directly requesting a flow, allowing Home Assistant Core to create the entry-bound reauth flow. A Core-started setup-time reauth without explicit SID data defaults to `xiaomiio`; `async_step_reauth()` self-registers against the existing pending state, or creates it if setup failed before the runtime callback recorded one. Successful reauth reloads the entry and resumes normal cloud-backed setup.

The failure callback, cache decision, setup completion, Core flow initialization, flow self-registration, and watchdog all converge through the same coordinator state and idempotent pending check. Under any ordering there is at most one `(entry_id, sid)` state and one entry-bound flow request path: cache-preserving setup waits for `LOADED`, while cache rejection delegates flow creation exclusively to Core.

micoapi is normally created while XiaoAI-capable entities initialize, so its setup failure uses the runtime callback with `sid=CloudSid.MICOAPI`.

A runtime authentication failure never unloads or blocks locally reachable entities that are already running. The cache-only admission path applies only while setting up or reloading a ConfigEntry.

## Reauth Runtime State

Runtime coordination is kept in integration memory and is not persisted in ConfigEntry data. It is split from a particular loaded `HassEntry` generation so pending work survives a normal reload:

```text
entry_reauth_coordinators[entry_id] = EntryReauthCoordinator {
    states[sid: CloudSid] = {
        episode,                 # current AuthEpisodeToken or None
        phase,                   # starting | active | pending | cooldown
        flow_id,                  # set only after flow self-registration
        triggered_at,
        registration_deadline,   # set only while starting
        flow_cooldown_until,
        auth_failed,
        persistence_inconsistent, # rollback failed; never treated as success
        pending_compensation      # process-local restore record or None
    },
    compensation_task,            # coordinator-owned restore task or None
    watchdog_task,
    loaded_hass_entry,           # current generation or None during reload
    runtime_generation,           # increments on each new HassEntry attach
    next_episode_id,              # monotonic counter per CloudSid
    auth_commit_lock,            # serializes entry-scoped auth persistence
    auth_commit_idle,            # set when no auth commit is finalizing
    reload_listener_registered   # this integration's listener is attached
}
```

A new attached `HassEntry` increments `runtime_generation` before it binds either runtime callback. It exposes the synchronous episode-allocation boundary used only by its bound runtime clouds:

```python
def begin_auth_episode(self, sid: CloudSid) -> AuthEpisodeToken:
    ...
```

`begin_auth_episode()` delegates to the entry's coordinator, atomically obtains the next SID-local `episode_id`, and installs the resulting `AuthEpisodeToken` in the current SID state before returning. It is valid only while that exact `HassEntry` generation remains attached and its callbacks are bound; normal unload first prevents new calls and then explicitly cancels every generation-owned episode. `MiotCloud` calls this boundary before registering the first caller or creating the single-flight task, stores the returned token on the cloud episode, and carries that exact token through failure or success. Private candidates and ownerless clouds have no entry episode token and never invoke either runtime callback.

A newer token replaces the current state's token before it can mutate `auth_failed`; callbacks compare the complete `(runtime_generation, episode_id)` pair and ignore every stale or cross-SID token. Numeric episode IDs may coincide across SIDs because `CloudSid` remains part of the state key.

`auth_commit_lock` serializes every entry-scoped authentication persistence operation, whether initiated by automatic recovery or reauth. The operation clears `auth_commit_idle` before its first Store snapshot and sets it in a `finally` block after coordinator terminal state and reload ownership are recorded. The update listener awaits `auth_commit_idle` before reloading, so Home Assistant 2024.11's task scheduled by `async_update_entry()` cannot unload the old `HassEntry` before authentication state is reconciled. The barrier never spans a network login and is released on every persistence or rollback error.

The integration records `reload_listener_registered` when its ConfigEntry update listener is attached. Reload ownership depends on the source of the auth commit:

- Successful reauth always reloads because its private candidate must become the runtime cloud. Changed ConfigEntry data uses the registered listener exactly once; unchanged data, or changed data without that listener because setup previously failed, uses one `async_schedule_reload()` fallback. Store-only micoapi reauth is therefore an unchanged-data scheduled reload.
- Successful xiaomiio automatic recovery of a loaded entry updates ConfigEntry token data. Changed data lets the registered listener reload exactly once after the barrier; unchanged data keeps using the already-recovered runtime cloud and does not reload.
- Successful micoapi automatic recovery of a loaded entry saves only the refreshed entry-scoped Store under `auth_commit_lock`, records coordinator terminal state, and does not call `async_update_entry()` or reload because that same runtime cloud already owns the refreshed session.
- Automatic recovery during initial setup schedules no reload regardless of listener absence: setup continues with the recovered in-memory cloud and registers the listener at its normal setup point.

A normal ConfigEntry reload detaches the old `HassEntry` but retains its `EntryReauthCoordinator`, SID states, notifications, and watchdog. The newly loaded `HassEntry` attaches to the same coordinator during setup and requests an idempotent pending check after setup completes. Home Assistant restart clears this in-memory state. Permanent ConfigEntry removal, unlike ordinary unload, deletes the coordinator, cancels its watchdog, and clears both SID states and notifications.

This restart boundary is intentional. `AuthStoreSnapshot`, `PendingAuthCompensation`, coordinator-owned `compensation_task`, `reauth_save`, `persistence_inconsistent`, transaction progress, and compensation work are process-local and are not restored after a Home Assistant restart. The feature creates no durable transaction journal or inconsistency marker. After restart, the currently persisted ConfigEntry data and entry-scoped SID Store are the starting authority; if those credentials are rejected, the next explicit authentication failure enters the normal automatic-recovery and reauth path.

Before requesting a flow, `EntryReauthCoordinator` checks its SID state and the ConfigEntry's active flow progress, including uninitialized flows. Core remains authoritative for entry-level locking and duplicate suppression:

- A starting or active SID is not requested again.
- If Core reports an active reauth or reconfigure flow for the entry, another failed SID becomes pending.
- `async_start_reauth()` returning normally leaves the SID in `starting`; it does not prove that a flow was created.
- `async_step_reauth()` synchronously registers its SID and public `self.flow_id`, moving that SID from starting to active before it returns the initial form.
- A setup-time flow started by Core after `ConfigEntryAuthFailed` creates and registers a `xiaomiio` state even when no prior starting state exists.
- A synchronous start exception or a registration timeout with no active entry-bound flow starts the ten-minute flow cooldown.
- A registration timeout while another entry-bound flow is active moves the SID to pending without flow cooldown.
- If `async_remove()` reports removal without a successful recorded outcome, the SID enters a ten-minute flow cooldown beginning at removal.
- During flow cooldown, the notification remains but no new flow starts.
- Successful reauth records the matching SID's terminal outcome immediately, clears its `auth_failed` flag and automatic-login suppression without flow cooldown, and retains the active `flow_id` only until `async_remove()` confirms that the flow ended.
- A second failed SID for the same entry remains pending until the active flow ends.

The state naturally resets on Home Assistant restart. If credentials are still invalid, the next explicit authentication failure can trigger a new flow.

## Login and Persistence

### Non-persisting candidate login

Reauth login attempts are non-persisting and non-destructive. They neither save nor remove a SID auth Store, and a candidate password is passed to the login attempt without replacing the cloud's stored password until identity verification confirms success. After successful Xiaomi login, the flow verifies the Xiaomi `user_id` before beginning local persistence. A wrong account never writes a Store or ConfigEntry.

The authenticated candidate cloud, candidate password, candidate Store payload, and final ConfigEntry data remain private Config Flow instance state. They are not placed in flow context, callbacks, notifications, placeholders, or logs. Account information is canonical in `ConfigEntry.data`; reauth never modifies `ConfigEntry.options`.

### SID credential ownership

Each runtime SID has exactly one persisted token authority:

- `xiaomiio` uses only ConfigEntry data for `username`, `password`, region, `user_id`, `service_token`, `ssecurity`, and `device_id`. A HassEntry-bound main cloud never reads, writes, or removes the legacy account-level main auth Store. Reauth and successful automatic recovery update ConfigEntry data only.
- `micoapi` uses only the entry-scoped `xiaomi_miot/auth-<entry_id>-micoapi.json` Store for `user_id`, `server_country`, fixed `sid="micoapi"`, `service_token`, `ssecurity`, and `device_id`. The Store never contains username or password, and micoapi token material never enters ConfigEntry data.

Different ConfigEntries never share an entry-scoped Store even when they use the same Xiaomi account. Ownerless Config Flow and Options Flow may retain their existing legacy account-level Store behavior outside the HassEntry runtime path.

When an entry-scoped micoapi Store is absent, its first HassEntry-bound construction may migrate the legacy account-level micoapi Store non-destructively. It accepts only a mapping whose `user_id`, region, and `sid="micoapi"` match the ConfigEntry, copies only the approved fields above, and saves them to the entry-scoped Store. It never changes or removes the legacy Store because another entry or ownerless flow may use it. A migration save failure leaves the legacy Store untouched, keeps any validated token only in memory for the current runtime, and emits a fixed secret-free persistence error.

The legacy main Store is not migrated or used as fallback. Missing or rejected main token data follows normal automatic login and reauth.

### Auth Store snapshots

Before the first entry-scoped micoapi Store write, the flow snapshots that Store. `xiaomiio` has no auth Store snapshot because ConfigEntry data is its only persistence boundary:

```text
AuthStoreSnapshot = {
    state,  # present | absent
    data    # exact valid mapping when present, otherwise None
}

PendingAuthCompensation = {
    original_entry_data, # exact pre-commit ConfigEntry data
    store_snapshots,     # affected Store -> AuthStoreSnapshot
    written_stores       # deterministic set/order of boundaries to restore
}
```

A missing Store and a present empty mapping remain distinct. The existing combined `async_stored_auth()` load/save/remove behavior is replaced on the HassEntry path by explicit entry-scoped micoapi load, save, restore, migration, and remove operations. Home Assistant 2024.11 preserves malformed Store content by renaming it to `.corrupt.<timestamp>` and returning no data; the transaction treats that active Store as absent while Core retains the corrupt backup. Snapshot and candidate payloads may contain credentials and must never be logged or exposed.

`PendingAuthCompensation` exists only after a cancelling flow transfers an incomplete local restore to `EntryReauthCoordinator`. It contains only the exact pre-commit local state and affected-boundary metadata required for reverse restoration; it never contains the candidate password, candidate cloud, login challenge, response, or exception. The record is process-local secret-bearing state: it never enters callback data, flow context/results, notifications, placeholders, or logs, and restart intentionally discards it.

### Compensating commit

The flow performs a compensating transaction over the persistence boundaries owned by the recovered SID. For `xiaomiio`, the Store-related steps are empty and only ConfigEntry data changes. For `micoapi`, the entry-scoped Store is written first and ConfigEntry data changes only when the user supplied a replacement common password:

1. Acquire `auth_commit_lock` and clear `auth_commit_idle` before copying the original ConfigEntry data or loading any `AuthStoreSnapshot`.
2. Prepare the complete candidate Store payloads and final ConfigEntry data without mutating persisted state.
3. Save candidate Stores in deterministic order. If a Store write fails, leave the ConfigEntry unchanged and enter the save-retry step.
4. After every required Store write succeeds, call `hass.config_entries.async_update_entry(entry, data=candidate_data)`. ConfigEntry options are never passed or modified.
5. `async_update_entry()` returning `False` is successful and means the ConfigEntry was unchanged; it is not a persistence error.
6. If `async_update_entry()` raises, restore each Store in reverse write order: save the exact snapshot mapping when present, or remove the newly written Store when the snapshot was absent.
7. While `auth_commit_lock` remains held, record terminal success only after Store writes and the synchronous ConfigEntry update call succeed; update coordinator state, clear authentication failure and the matching notification, and retain any active flow phase and `flow_id` until `async_remove()` confirms removal.
8. Set `auth_commit_idle` in a `finally` block after the terminal outcome or persistence failure has been recorded, then release `auth_commit_lock`.
9. After the barrier is idle, apply the source-specific reload policy: reauth uses the registered listener for changed data and the single scheduled fallback otherwise; loaded-entry xiaomiio automatic recovery reloads only through a listener fired by changed data; loaded-entry micoapi and initial-setup automatic recovery do not reload.

If Store rollback succeeds, persisted credentials again match the pre-commit snapshot. If rollback fails, the SID is marked `persistence_inconsistent`; the flow and persistent notification remain active, no reload is requested, and the partial commit is never treated as success. Logs identify only the entry ID, SID, operation, and fixed error category, never snapshot data, candidate credentials, or secret-bearing exception text.

This compensation ends when `async_update_entry()` returns successfully and the auth commit barrier has recorded its terminal state. Home Assistant Core owns its later asynchronous ConfigEntry storage write, which the integration cannot include in a cross-file transaction.

### Save retry lifecycle

A Store write, ConfigEntry update, or Store rollback failure in an active authenticated flow routes to `reauth_save` with a fixed `save_failed` error and no credential fields. That original flow retains the authenticated candidate cloud and prepared payloads privately. A retry repeats only snapshot-aware persistence; it does not log in to Xiaomi again or ask the user to repeat verification or captcha.

While this candidate-owning save retry is pending, the candidate cloud is detached from the owner runtime SID registry and held only by the flow. `HassEntry` rebuilds its owner-bound runtime cloud from the original ConfigEntry and Store snapshot so ordinary runtime work cannot consume a partially committed candidate. A successful retry installs the candidate cloud only after persistence completes.

Cancellation from `reauth_save` first transfers a `PendingAuthCompensation` record to the coordinator whenever any local boundary may require restoration, marks `persistence_inconsistent`, and starts `compensation_task` under `auth_commit_lock`. Only after the coordinator owns that record does the flow clear and discard its candidate password, cloud, challenge, and prepared candidate payloads. The compensation task restores Stores in reverse write order and restores original ConfigEntry data only when that boundary changed; it records its terminal state before setting `auth_commit_idle` and releasing the lock.

If cancellation compensation succeeds, the coordinator clears `pending_compensation` and `persistence_inconsistent`, leaves the current `auth_failed` and flow-cooldown values unchanged, and reconciles the notification from that current state. A still-failed SID retains its notification and cancellation cooldown; a SID already cleared by recovery-succeeded dismisses the notification and needs no credential flow. If compensation fails, the exact record remains process-local and secret-bearing, the marker and notification remain visible, and no automatic retry loop is scheduled. After the task has ended and flow cooldown permits another flow, `async_step_reauth()` registers normally but routes directly to a compensation-only `reauth_save` form before candidate construction. Submitting that form retries only reverse restoration without contacting Xiaomi. Successful restoration clears the record and marker, then rechecks `auth_failed`: a still-failed SID routes to `reauth_password` because the cancelled candidate was destroyed, while an already-recovered SID records terminal success and aborts with `reauth_successful` without credential writes. Another restore failure remains on the fixed `save_failed` form.

Permanent ConfigEntry removal cancels and awaits `compensation_task` and clears the record before deleting the entry-scoped micoapi Store. Home Assistant restart discards the task and record without a durable marker, as defined by the intentional restart boundary.

## Authentication Retry Timers

Two independent monotonic deadlines prevent different retry storms:

- `MiotCloud.auto_login_suppressed_until` prevents only automatic login for that cloud SID. Any failed single-flight automatic login sets it for ten minutes, but only a canonical authentication-category failure reports to `HassEntry`; timeout, connection, and HTTP 5xx failures remain transient. While `auth_rejected` is True, a no-token runtime request still performs its original API operation once, and an explicit rejection during suppression terminates without login or callback. Expiry permits the next explicit rejection to create one new single-flight login attempt, and another failure starts a new ten-minute suppression period. A successful automatic-recovery episode, an ordinary API success, and successful reauth clear both suppression and `auth_rejected`. Reauth form submissions always bypass suppression.
- `ReauthState.flow_cooldown_until` prevents only `EntryReauthCoordinator` from requesting another reauth flow for that ConfigEntry and SID. Unsuccessful or cancelled flow removal, synchronous flow-start failure, background initialization failure, or abnormal disappearance sets it for ten minutes. Authentication-failure reports received during an existing flow cooldown do not extend its current deadline. Successful reauth clears it.

The timers never write or extend each other. Flow cooldown does not suppress automatic login or ordinary cloud requests, and automatic-login suppression does not prevent an active reauth form from attempting login. An unsuccessful or cancelled reauth does not clear automatic-login suppression or `auth_rejected`. A request that succeeds without entering an explicit-rejection recovery episode clears both cloud fields and does not alter flow lifecycle state; a successful automatic-recovery episode additionally invokes the recovery-succeeded callback to reconcile coordinator state. Both in-memory deadlines and `auth_rejected` reset on Home Assistant restart.

## Login Challenge Lifecycle

Password verification and captcha use one structured in-memory challenge instead of independent values in `MiotCloud.attrs`:

```python
@dataclass
class LoginChallenge:
    generation: int
    category: AuthFailureCategory
    verify_url: str | None = None
    identity_session: str | None = None
    captcha_image: str | None = None
    captcha_ick: str | None = None
    login_data: dict | None = None
```

Each cloud holds at most one challenge. Only `verify_url` and `captcha_image` may be presented to the user. `identity_session`, `captcha_ick`, and `login_data` remain inside cloud login methods and never enter Config Flow context, flow results, callbacks, notifications, placeholders, or logs. Candidate replacement passwords remain separate private Config Flow instance state and are never stored in `LoginChallenge`.

A failed runtime automatic login initially leaves the challenge on that SID's runtime cloud. When reauth creates its private candidate cloud, it transfers the exact challenge under the shared login lock:

```python
challenge = runtime_cloud.detach_login_challenge()
candidate_cloud.attach_login_challenge(challenge)
```

The transfer is atomic and leaves only the candidate as owner; it does not copy secret fields. If no current challenge is available, the flow starts from password entry. A normal ConfigEntry reload may clear the old runtime cloud but never touches a challenge owned by an active Config Flow candidate.

Form rendering and challenge submission read the candidate's challenge without destructive `pop()` operations. A failed captcha or verification submission retains the current cookie, identity session, and pending login data. If Xiaomi returns a replacement challenge, the cloud fully constructs and installs the new generation before clearing the old generation. Successful login clears the current challenge. Runtime automatic login, reauth login, transfer, and replacement transitions use the same cloud login lock so they cannot mutate challenge ownership concurrently.

All cleanup uses one generation-aware, idempotent entry point:

```python
def clear_login_challenge(
    self,
    *,
    expected_generation: int | None = None,
) -> None:
    ...
```

No challenge is a no-op. When an expected generation is provided, a mismatch is also a no-op, preventing delayed cleanup from an old flow from clearing a newer challenge. A matching cleanup removes the complete challenge reference at once; code does not separately pop individual secret fields.

Terminal cleanup order is deterministic:

- **Successful reauth:** finish identity validation and persistence, record terminal success, clear the candidate challenge and candidate password, make only the clean candidate eligible for runtime handoff, then abort the flow and let `async_remove()` notify the coordinator.
- **Cancellation or ordinary failure:** when a candidate-owning flow is in `reauth_save`, transfer required restore state to coordinator-owned `PendingAuthCompensation` and start compensation before clearing the candidate; then detach it from any temporary handoff location, clear its challenge and candidate password, record the unsuccessful outcome and cooldown, and notify the coordinator. A compensation-only flow owns no candidate and leaves a failed record with the coordinator.
- **Wrong account:** write nothing, clear the candidate challenge and password, discard the candidate, abort with `wrong_account`, and let removal enter unsuccessful cooldown.
- **Normal `HassEntry` unload:** clear only challenges owned by that runtime generation. It does not touch a Config Flow candidate. Repeated unload and cleanup calls are safe.

Both `xiaomiio` and `micoapi` use this same ownership, password, verification-ticket, captcha, and cleanup state machine.

### Shared cloud login flow helper

Authentication and challenge classification are implemented once rather than in separate xiaomiio and micoapi Config Flow branches:

```python
@dataclass(frozen=True)
class LoginSubmission:
    password: str | None = None
    verify_ticket: str | None = None
    captcha: str | None = None

@dataclass(frozen=True)
class LoginTransition:
    success: bool
    category: AuthFailureCategory | None = None
    error_key: str | None = None
    verify_url: str | None = None
    captcha_image: str | None = None
```

Exactly one `LoginSubmission` field may be nonempty. `LoginTransition` contains only fixed status values and the two displayable challenge fields. It never carries a password, ticket, captcha answer, identity session, captcha cookie, pending login data, exception, or response body.

```python
class CloudLoginFlowHelper:
    async def async_submit(
        self,
        cloud: MiotCloud,
        submission: LoginSubmission,
        *,
        persist: bool,
    ) -> LoginTransition:
        ...
```

The helper calls the structured `LoginChallenge` login API, maps `AuthFailureCategory` to fixed keys (`invalid_auth`, `access_denied`, `need_verify`, `need_captcha`), maps transport failures to fixed ordinary keys such as `cannot_reach`, and extracts only `verify_url` or `captcha_image`. It does not render a Home Assistant form or choose the successful persistence target. Reauth candidates always pass `persist=False`; existing Config Flow and Options Flow may pass `persist=True` and retain their existing completion behavior.

Existing main-cloud and micoapi Config/Options Flow schemas, filters, and finish actions remain separate, but they use this helper for login and challenge classification. They no longer access `captchaIck`, `captchaImg`, `identity_session`, or pending login data directly; construct placeholders from exception text; or maintain separate challenge-category branches.

micoapi's special verification retry uses a typed internal stage rather than exception-string matching:

```python
class LoginStage(StrEnum):
    ACCOUNT = "account"
    MICOAPI_STS = "micoapi_sts"
    API_REQUEST = "api_request"

MiCloudAuthError(
    category=AuthFailureCategory.ACCESS_DENIED,
    sid=CloudSid.MICOAPI,
    stage=LoginStage.MICOAPI_STS,
)
```

The stage/category mapping is exhaustive:

| Rejection source | Category | Stage and terminal representation |
| --- | --- | --- |
| xiaomiio or micoapi ordinary API HTTP 401 | `TOKEN_EXPIRED` | Raise sanitized `MiCloudAuthError(..., stage=API_REQUEST)` |
| Ordinary API code `2` or `3`, or a recognized authentication-error message | `TOKEN_EXPIRED` | No transport exception; return the parsed API rejection result unchanged when terminal |
| Account-login HTTP 401 or 403 | `ACCESS_DENIED` | Raise sanitized `MiCloudAuthError(..., stage=ACCOUNT)` |
| micoapi STS HTTP 401 after verification | `ACCESS_DENIED` | Raise sanitized `MiCloudAuthError(..., stage=MICOAPI_STS)` |

Structured account-login outcomes for invalid credentials, verification, or captcha retain their canonical `INVALID_CREDENTIALS`, `VERIFY_REQUIRED`, or `CAPTCHA_REQUIRED` category and use `LoginStage.ACCOUNT`; they are mapped to `LoginTransition` rather than exposed as transport response data.

`CloudLoginFlowHelper` retries exactly once only when the SID is `micoapi`, the submission is a verification ticket, the typed stage is `MICOAPI_STS`, and that submission has not retried. It clears only the rejected token and HTTP session, preserves the structured challenge state needed by the retry, does not persist, and never invokes the runtime callback. A second STS rejection returns `ACCESS_DENIED`. xiaomiio never enters this branch.

## Flow Lifecycle

Home Assistant creates the reauth flow and assigns `self.flow_id` before invoking `async_step_reauth()`. The step synchronously registers `(entry_id, sid, flow_id)` with the entry's `EntryReauthCoordinator` as its first integration-specific action. If that SID has `pending_compensation`, it constructs no candidate and routes first to compensation-only `reauth_save`; otherwise it routes to the appropriate initial password, verification-ticket, or captcha form. This initial step runs in the `async_start_reauth()` background task before the user opens the flow; the user's later submission continues the already active form step.

The Config Flow records its reauth SID and terminal outcome and overrides the public `FlowHandler.async_remove()` lifecycle callback. Removal schedules an asynchronous notification to `EntryReauthCoordinator`, covering successful completion, explicit abort, frontend cancellation, and manager removal.

A successful outcome clears the matching SID without flow cooldown. Any unsuccessful removal or removal without a recorded outcome retains the notification and starts that SID's ten-minute flow cooldown. Flow removal requests an idempotent pending check but never directly starts the pending SID from the old `HassEntry` generation.

A shared low-frequency coordinator watchdog runs every 30 seconds and survives ordinary entry reload. For a starting SID whose 60-second registration deadline has elapsed, it queries the public entry-bound flow progress: an active reauth or reconfigure flow moves the SID to pending, while no active flow is treated as background initialization failure and starts flow cooldown. For an active SID, the watchdog verifies its registered `flow_id` through `async_get()`; a flow that disappears without `async_remove()` is treated as unsuccessful from the time disappearance is detected. Registration and removal handling are idempotent by `flow_id`.

A pending SID starts only when a current `HassEntry` is attached, the ConfigEntry is `LOADED`, no reauth or reconfigure flow is active, the SID remains `auth_failed`, its flow cooldown is inactive, and no coordinator-owned `compensation_task` is running. Setup completion, flow removal, compensation completion, and the watchdog all call the same idempotent pending check. If reload is in progress, the current flow still exists, or compensation is still running, the check leaves the SID pending for a later trigger. A failed completed compensation record does not block flow creation after cooldown; the newly registered flow detects it and enters compensation-only `reauth_save` before constructing a candidate.

### ConfigEntry unload and permanent removal

`async_unload_entry()` cleans only the current loaded runtime generation. After platform and device unload succeeds, it unbinds every runtime cloud authentication callback, cancels generation-owned device and cloud tasks, clears runtime SID clouds, creation locks, and runtime challenges, detaches that exact `HassEntry` from its coordinator, and removes it from `HassEntry.ALL`. It retains the `EntryReauthCoordinator`, SID states, notifications, active flow registration, flow-owned candidate, coordinator-owned compensation task and record, and auth Stores. If no `HassEntry` and no active flow remain, the coordinator may suspend its watchdog while any compensation task continues independently; attach during a later setup restarts the watchdog and requests a pending check.

Permanent deletion uses a separate integration hook:

```python
async def async_remove_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> None:
    coordinator = EntryReauthCoordinator.pop(config_entry.entry_id)
    if coordinator is not None:
        await coordinator.async_close()
    dismiss_auth_notifications(config_entry.entry_id)
```

`async_close()` first sets irreversible `closed = True`, then rejects late failure or recovery-succeeded callbacks, flow registration, and pending checks; cancels and awaits coordinator-owned tasks including `compensation_task`; detaches any remaining `HassEntry` and both runtime callbacks; clears both SID states and every `pending_compensation` record; dismisses both SID notifications; and removes the coordinator from integration runtime storage. Coordinator lookup or creation verifies that the ConfigEntry still exists, so late callbacks cannot recreate state for a deleted entry.

Home Assistant may call the integration removal hook before Core aborts entry-bound reauth flows. Therefore `async_close()` does not wait for flow removal. The Config Flow still clears its private candidate and secrets in `async_remove()`; its later coordinator notification is a safe no-op when the coordinator is closed or absent. Permanent cleanup also works when ordinary unload failed or no valid `HassEntry` remains.

Ordinary unload never removes an auth Store. Permanent removal deletes only `xiaomi_miot/auth-<entry_id>-micoapi.json`; it does not delete the legacy account-level micoapi Store, the legacy main Store, or shared device inventory cache.

## Reauth Config Flow

### Entry and fixed identity

`async_step_reauth(entry_data)` obtains the target ConfigEntry with `_get_reauth_entry()`. The failed SID comes from the data passed to `ConfigEntry.async_start_reauth()` and defaults to `xiaomiio` only when setup initiated reauth without explicit SID data. Before selecting a form, the step stores the SID on the flow and synchronously registers `(entry_id, sid, self.flow_id)` with `EntryReauthCoordinator`; this also creates the state for a Core-initiated setup-time flow that had no prior starting record. Reauth displays but does not permit changes to:

- Xiaomi username
- server region
- connection mode
- failed cloud type

After login, the flow compares the authenticated Xiaomi `user_id` with the ConfigEntry's stored `user_id`. A mismatch aborts with `wrong_account` and does not update credentials. This feature does not add or migrate ConfigEntry unique IDs.

Account or region changes remain in the existing configuration/options path. Home Assistant `reconfigure` is reserved for a future user-initiated migration of those required settings; it is not used for token expiry or other authentication failures.

The flow obtains the SID's runtime `MiotCloud` from `HassEntry` only long enough to atomically transfer its `LoginChallenge` into a private candidate cloud. The flow then uses only the candidate. If runtime or challenge state was lost, such as after a restart, it creates a private SID-specific candidate and starts from password entry.

### Initial form selection

The first form depends on the recorded `AuthFailureCategory`:

- `TOKEN_EXPIRED`: show the password form without exposing the saved password.
- `INVALID_CREDENTIALS`: return to the password form with fixed `invalid_auth` base error.
- `VERIFY_REQUIRED`: show the verification URL and request `verify_ticket`.
- `CAPTCHA_REQUIRED`: show the captcha image and request `captcha`.
- `ACCESS_DENIED`: return to the password form with fixed `access_denied` base error and allow another password submission.
- Missing or stale challenge context: return to the password form without exposing the saved password.

`ACCESS_DENIED` does not abort reauth because it may represent an incorrect password, an account restriction, or an STS rejection that a later submission can recover. Only a successful login whose Xiaomi `user_id` differs from the ConfigEntry aborts with `wrong_account`.

The password field does not expose the saved password. The stored password remains unchanged unless the user submits a replacement. Replacement candidate passwords are private Config Flow instance state; they never enter flow context, callbacks, notifications, placeholders, or logs.

### Shared challenge transitions

Both SIDs use the same Home Assistant steps:

```text
async_step_reauth_password
async_step_reauth_verify
async_step_reauth_captcha
async_step_reauth_save
```

Each authentication step creates one `LoginSubmission`, calls `CloudLoginFlowHelper.async_submit(..., persist=False)`, and routes the returned `LoginTransition` through the canonical category-to-form mapping. SID affects only candidate construction, the typed micoapi STS retry, and successful persistence. There are no SID-specific duplicate reauth form implementations.

- A password submission updates only the private candidate password and attempts login.
- A verification-ticket submission uses the candidate's stored verification session.
- A captcha submission uses the candidate's stored captcha cookie and pending login data.
- If Xiaomi changes the required challenge, the returned transition selects the corresponding shared step.
- Empty or rejected credentials return to the password form with a fixed error key; exception text and response bodies never enter `errors["base"]` or placeholders.
- Connection, timeout, and server failures use fixed ordinary form errors such as `cannot_reach`; they do not create an `AuthFailureReport` or nested reauth flow.

A micoapi STS 401 after verification is handled only by the helper's typed, at-most-once retry. A second STS rejection returns `ACCESS_DENIED` and routes to the shared password form; it cannot recursively invoke runtime recovery.

### User-facing copy and translation contract

Reauth uses fixed translation keys rather than exception messages, response text, or dynamically assembled Markdown. Implementation adds matching entries to the bundled translation resources for these steps and fields:

- `config.step.reauth_password`, with only the `password` input;
- `config.step.reauth_verify`, with only the `verify_ticket` input;
- `config.step.reauth_captcha`, with only the `captcha` input;
- `config.step.reauth_save`, with no credential input and an empty submit-only schema that retries active-flow persistence or coordinator-owned compensation.

The complete reauth base-error allowlist is `invalid_auth`, `access_denied`, `need_verify`, `need_captcha`, `cannot_reach`, `save_failed`, and Home Assistant's fixed `unknown` error. Empty or rejected password, verification-ticket, and captcha submissions map respectively to `invalid_auth`, `need_verify`, and `need_captcha`; transport failures map to `cannot_reach`; snapshot-aware persistence or compensation failures map to `save_failed`. No exception message or response field may be used as a translation key. The only reauth abort reasons are `wrong_account` and `reauth_successful`, and both have fixed translations.

Form descriptions use a strict placeholder allowlist. Every reauth form may use `entry_title` and `cloud_name`; the verification form may additionally use `verify_url`, and the captcha form may additionally use `captcha_image`. `cloud_name` comes from a fixed SID-to-display-name mapping, not the raw SID. `entry_title` is the existing ConfigEntry title, not a username or Xiaomi user ID read from credentials. No other placeholder is accepted, including `tip`, exception text, response bodies, username, Xiaomi user ID, tokens, cookies, pending login data, or candidate state.

Only fixed translation text wraps `verify_url` or `captcha_image`; the integration never constructs user-visible Markdown from an exception. Existing Config/Options Flow steps migrated to `CloudLoginFlowHelper` use the same error-key and challenge-placeholder rules while retaining their existing step IDs and non-authentication fields.

### Successful completion

On successful `xiaomiio` reauth:

- persist the main cloud's new token, `ssecurity`, and `device_id` only in ConfigEntry data;
- update the ConfigEntry password only if the user submitted a replacement;
- never read or write a main auth Store;
- leave micoapi credentials untouched.

On successful `micoapi` reauth:

- persist its token, `ssecurity`, and `device_id` only in `xiaomi_miot/auth-<entry_id>-micoapi.json`;
- update the ConfigEntry password only if the user submitted a replacement;
- leave main-cloud token fields untouched.

For either SID:

- verify that the authenticated Xiaomi `user_id` still matches the ConfigEntry;
- perform the compensating commit described in *Login and Persistence*: snapshot affected Stores and the original ConfigEntry data, write the candidate Store payloads in deterministic order, call `hass.config_entries.async_update_entry(entry, data=candidate_data)`, and only after both succeed record the terminal outcome;
- after persistence succeeds and while `auth_commit_lock` remains held, record the current SID's terminal success, dismiss only that SID's notification, clear its authentication-failure and persistence state, clear the recovered cloud's automatic-login suppression, and retain an active flow phase and `flow_id` until matching `async_remove()`; retain every other SID's pending state and notification in `EntryReauthCoordinator`;
- after `auth_commit_idle` is set and the lock is released, when `async_update_entry()` returned `True` and the integration listener was registered at update time, let that listener perform exactly one reload; when it returned `False` or no integration listener was registered, call `hass.config_entries.async_schedule_reload()` exactly once;
- return `self.async_abort(reason="reauth_successful")` from the flow step;
- let `async_remove()` record that the current flow ended and request an idempotent pending check; the successful flow never calls `async_start_reauth()` for the pending SID directly;
- after reload, the newly attached `HassEntry` and coordinator start a still-failed pending SID only after the entry is `LOADED` and Core reports no active reauth or reconfigure flow.

The reauth flow never calls `async_create_entry()`. It does not use `async_update_reload_and_abort()`, directly await `async_reload()`, or call the flow manager's removal API. This avoids a duplicate reload when ConfigEntry data changes while still reloading after a Store-only reauth. A persistence failure routes to the save-retry form and never returns `reauth_successful`. Cancelling before persistence or failing identity verification leaves persisted credentials unchanged; cancelling from save retry performs compensation, and a failed compensation remains explicitly `persistence_inconsistent`. Neither path dismisses the notification.

## Persistent Notifications

Native reauth and persistent notifications are both shown. Notification IDs are SID-specific:

```text
xiaomi_miot-auth-<entry_id>-xiaomiio
xiaomi_miot-auth-<entry_id>-micoapi
```

The coordinator selects one of three fixed notification body variants: `auth_failed`, `verify_required`, or `captcha_required`. The notification title is fixed. Title and body are never derived from an exception, response, or caller-supplied summary.

Notification interpolation uses a strict allowlist: the existing ConfigEntry `entry_title`, a `cloud_name` selected from the fixed SID-to-display-name mapping, and the integration configuration link. Only the `verify_required` variant may additionally interpolate `verify_url`. Notifications do not interpolate usernames, Xiaomi user IDs, raw SIDs, exception text, response bodies, or candidate state, and they never include a captcha image. This identifies the affected entry and cloud without copying account credentials into the notification.

Notifications must not contain passwords, service tokens, `ssecurity`, cookies, captcha cookies, identity sessions, or complete API/login responses. A fixed ID updates an existing notification instead of creating a stack.

Successful reauth dismisses only the matching SID notification. A cancelled or unsuccessful flow leaves it visible. Ordinary unload or reload preserves notifications. Permanent ConfigEntry removal dismisses both notifications through `async_remove_entry()` and deletes all of that entry's reauth runtime state.

## Home Assistant Compatibility

This feature raises the integration's minimum supported Home Assistant version to 2024.11.0. During implementation, `hacs.json` changes from `2023.12.0` to `2024.11.0`, and the oldest Home Assistant configuration-validation matrix entry changes from `2023.7.0` to `2024.11.0`. These metadata and CI files remain unchanged during design review.

The implementation directly uses the Home Assistant 2024.11 ConfigEntry flow APIs:

- `ConfigEntry.async_start_reauth()` to request runtime or cache-preserving setup-time reauth; it returns `None` and initializes the flow asynchronously;
- `async_step_reauth(entry_data)`, `_get_reauth_entry()`, and the flow's assigned `self.flow_id` to access the existing entry and self-register the active SID;
- `hass.config_entries.async_update_entry(entry, data=candidate_data)` to update only the existing entry data and fire its update listener when data changes; reauth never passes or modifies entry options;
- `hass.config_entries.async_schedule_reload()` to request the single reload only when successful entry-scoped micoapi Store persistence leaves the ConfigEntry unchanged or no integration update listener is registered;
- `hass.config_entries.async_update_entry()` schedules registered update listeners asynchronously before returning, so authentication persistence uses `EntryReauthCoordinator.auth_commit_lock` and `auth_commit_idle` to finish coordinator reconciliation before the listener reloads;
- `self.async_abort(reason="wrong_account")` when the authenticated Xiaomi `user_id` differs from the stored account;
- `self.async_abort(reason="reauth_successful")` to finish the successful reauth flow;

There is no compatibility fallback that starts `source=reauth` directly through the flow manager, and reauth never creates a new ConfigEntry. Existing entries remain reloadable through their update listener. No compatibility path may silently treat an authentication failure as success.

## Error Handling and Logging

- Explicit authentication failures are logged without credential-bearing response bodies.
- Automatic login success is informational/debug-level and does not notify the user.
- Canonical authentication-category automatic-login failure logs only fixed category, entry identity, and SID; transient login failure retains fixed network/server logging without response bodies or secrets.
- Repeated polling during automatic-login suppression, an active flow, or flow cooldown does not emit repeated warning/error logs.
- Network and server failures retain their existing retry and logging semantics.
- A callback or flow-start exception cannot mask the original request failure.
- The authentication-failure callback is invoked at most once for each completed failed single-flight episode; a successful episode invokes no failure callback and invokes the recovery-succeeded callback at most once after persistence is attempted.
- Reauth submissions do not invoke the runtime failure callback recursively.

## Testing Strategy

Authentication tests use Home Assistant's real `ConfigEntry` and flow machinery with Xiaomi transport, Store failure, notification, and time boundaries controlled by deterministic fixtures. No test contacts Xiaomi or uses real credentials. Tests are split by responsibility, and concurrency uses explicit barriers; automatic-login suppression, flow cooldown, and watchdog deadlines use a controlled monotonic clock; flow cancellation uses the real flow manager.

### `tests/test_cloud_auth.py`

Pure cloud authentication pipeline:

- Parameterized transport-level HTTP 401 and API-level token-expired classification for both SIDs: ordinary API HTTP 401 is exactly `TOKEN_EXPIRED + API_REQUEST`, account HTTP 401/403 is exactly `ACCESS_DENIED + ACCOUNT`, micoapi post-verification STS 401 is exactly `ACCESS_DENIED + MICOAPI_STS`, and API codes `2` and `3` plus every recognized authentication-error message are parsed `TOKEN_EXPIRED` results without a transport exception.
- Parameterized terminal-contract cases cover the first rejection, active-suppression short-circuit, canonical authentication-category login failure, transient timeout/connection/HTTP 5xx login failure, and a second rejection after the one permitted retry: transport-level cases re-raise sanitized `MiCloudAuthError`, API-level cases return the terminal attempt's parsed result unchanged, and both paths have identical request, login, retry, callback, and suppression counts.
- Transport-level `MiCloudAuthError` retains only the exact category, SID, and `LoginStage` from the exhaustive mapping; response body, headers, cookies, response object, and request payload canaries are absent from the exception and its string representation.
- Transport-specific ordinary, raw, RC4, account-login, and micoapi STS tests use synchronous and asynchronous fake responses whose body, headers, cookies, and decoding accessors fail the test. Authentication HTTP statuses reach none of those accessors, synchronous responses are closed, asynchronous responses are released, and non-authentication responses retain their existing read/parse/decrypt behavior.
- Exact enum coverage for invalid credentials, token expiry, verification, captcha, and access denied; transport and server errors remain outside the enum.
- Synchronous `begin_auth_episode()` installs the current `AuthEpisodeToken` before the first caller is registered or either cloud-owned episode task is created.
- Single-flight login and finalizer tasks, exact retry count, one shared report-once latch per episode, and at most one callback across all callers.
- Barrier-controlled cancellation covers one cancelled waiter, every waiter cancelled before and after login completes, and explicit runtime-owner cancellation: request cancellation cannot cancel the shielded login or finalizer, every waiter decrements in `finally`, all-caller cancellation still permits one successful persistence and recovery callback, and owner cancellation permits neither.
- Sequential no-token runtime requests while `auth_rejected` is True skip preflight login and perform the original API operation once; an explicit rejection during suppression preserves its terminal contract without episode allocation or callback.
- A missing token with `auth_rejected` False retains explicit preflight login for initial setup and ownerless Config/Options Flow callers; private reauth candidates remain on the helper path.
- A new post-expiry explicit rejection creates one new episode and may invoke the authentication-failure callback again only for a canonical authentication-category login failure.
- Ten-minute automatic-login suppression blocks additional automatic login but not reauth submissions or ordinary request failure behavior; timeout, connection, and HTTP 5xx login failures set suppression without an `AuthFailureReport` or reauth flow.
- Suppression expiry permits one new single-flight automatic login only after a new explicit rejection, and another login failure starts a new deadline.
- Ordinary API success, successful automatic recovery, and successful reauth clear both automatic-login suppression and `auth_rejected`; non-authentication request failure clears neither.
- `CloudSid`, `AuthEpisodeToken`, and `AuthFailureReport` shapes; one immutable token is shared by the failure or recovery-succeeded result of an episode, and the report contains no `MiotCloud`, original exception, response body, snapshot data, candidate credential, Store payload, or other secret-bearing object.
- Automatic recovery finalization waits for every registered caller to settle before persisting exactly once; cancelled callers require no retry and cannot strand finalization.
- A second explicit authentication rejection prevents candidate-token persistence.
- Successful loaded-entry xiaomiio automatic recovery updates ConfigEntry token data once after all joined callers settle; changed data reloads once through the listener, while unchanged data does not reload.
- Successful loaded-entry micoapi automatic recovery saves only its entry-scoped Store, does not call `async_update_entry()`, and does not reload.
- Automatic-recovery persistence failure keeps the valid in-memory session, invokes no authentication-failure callback, invokes the recovery-succeeded callback once, and logs only a fixed secret-free category.
- Reauth login is non-persisting and non-destructive; identity verification happens before any local persistence.
- Structured `LoginChallenge` state machine for both SIDs, including non-destructive submissions and atomic replacement.
- Runtime-to-candidate challenge transfer leaves exactly one secret owner.
- Generation-aware cleanup is idempotent and cannot clear a newer challenge.
- Repeated form rendering and rejected captcha or verification input retain required challenge state unless Xiaomi replaces it.
- Shared `CloudLoginFlowHelper` parameterized over both SIDs for password-to-verification, password-to-captcha, verification-to-captcha, captcha-to-verification, invalid credentials, access denied, transport failure, challenge replacement, and success.
- `LoginSubmission` accepts exactly one input and `LoginTransition` contains no secret-bearing field.
- micoapi verification-stage STS 401 uses typed `LoginStage.MICOAPI_STS` and retries once; xiaomiio never retries that stage and a second micoapi rejection returns `ACCESS_DENIED`.
- Existing Config Flow, Options Flow, and reauth classify the same cloud outcome identically and expose only the same permitted URL or image.
- Sensitive data log canaries.

### `tests/test_hass_entry_reauth.py`

`HassEntry` coordination:

- `(entry_id, sid)` cloud registry isolation.
- Local/token ConfigEntries with no xiaomiio runtime cloud return `None` from `entry.cloud`; local device initialization and unload complete without creating a cloud or raising `KeyError`.
- Same SID concurrent creation performs one creation; different SIDs use independent per-SID locks.
- Different ConfigEntries using the same Xiaomi account, region, and SID do not share runtime cloud, callback, timers, session, or challenge state.
- ConfigEntry runtime clouds bypass the global session registry before and after login.
- A private reauth candidate bypasses both registries and remains private across `async_change_sid()`.
- Ownerless Config Flow and Options Flow callers retain global account/SID session reuse.
- A HassEntry-bound `async_change_sid()` delegates to `hass_entry.async_get_cloud()` and returns the entry's SID-specific instance.
- HassEntry-bound xiaomiio uses ConfigEntry data as its only token authority and never reads, writes, migrates, or removes the legacy main Store.
- Different ConfigEntries use different entry-scoped micoapi Stores even for the same Xiaomi account.
- Missing entry-scoped micoapi auth accepts a legacy Store only when user ID, region, and SID match, copies only approved fields, and never changes or removes the legacy Store.
- Legacy migration save failure retains validated credentials only in memory and exposes no Store payload or exception text.
- `begin_auth_episode()` accepts only the currently attached runtime generation, installs its token before cloud task creation, and maps later callbacks to the correct entry, `CloudSid`, runtime generation, and episode token; a missing current cloud, detached generation, or replaced token is a no-op that never reads the stale cloud object.
- Barrier-controlled callback reordering covers old success followed by new failure, new failure followed by old success, old failure followed by new success, and callbacks from a detached runtime generation; only the current token may mutate state.
- Equal numeric episode IDs for different SIDs remain isolated by `(entry_id, CloudSid)`.
- Core active flow marks the other SID pending.
- Authentication-failure callbacks received while the ConfigEntry is not `LOADED` record one pending SID and notification without calling `async_start_reauth()` or setting a registration deadline.
- Setup completion, flow self-registration, callback delivery, and watchdog checks remain idempotent when deliberately reordered.
- `async_start_reauth()` returning `None` leaves the requested SID starting until flow self-registration.
- A synchronous start exception and a 60-second unregistered start without an active flow enter flow cooldown.
- A Core deduplication race moves an unregistered starting SID behind the competing active flow without cooldown.
- Ten-minute flow cooldown after failure, cancellation, disappearance, and background creation failure.
- Authentication-failure reports during flow cooldown do not extend its deadline.
- A running coordinator-owned compensation task blocks pending flow creation; completion requests the shared pending check, successful restoration clears compensation state and reconciles notification from the current `auth_failed` value, and failed restoration becomes a compensation-only flow after cooldown.
- Flow cooldown does not suppress cloud automatic login, and an ordinary successful request that did not enter an explicit-rejection recovery episode does not clear flow lifecycle state.
- A successful automatic-recovery episode invokes the recovery-succeeded callback once and clears stale notification and `auth_failed` state independently for `pending` and `cooldown` SIDs.
- Recovery-succeeded races with `starting` registration and `active` flow submission retain only the flow identity needed for cleanup, abort with `reauth_successful` without candidate writes, and create no cooldown or replacement notification when both `persistence_inconsistent` is False and `pending_compensation` is absent.
- Recovery-succeeded while `persistence_inconsistent` or `pending_compensation` is present clears authentication failure but retains the active save-retry flow or coordinator-owned compensation record, marker, and notification until restoration or persistence succeeds.
- Callback ordering tests use explicit barriers for recovery completion versus coordinator mutation, flow self-registration, flow submission, `async_remove()`, watchdog cleanup, and normal reload.
- A recovery-succeeded callback for one SID leaves the other SID's failed, pending, notification, and cooldown state unchanged.
- Successful reauth clears the matching SID state and suppression while retaining another failed SID as pending across reload.
- `async_remove()` outcome drives flow cooldown or requests an idempotent pending check.
- The 30-second coordinator watchdog detects both unregistered starts and vanished active flows and survives ordinary reload.
- A normal unload first blocks new episode allocation, then detaches the old `HassEntry`, unbinds callbacks, explicitly cancels and awaits every generation-owned login and finalizer task, cancels its other device/cloud tasks, and clears every runtime SID cloud, challenge, and creation lock without episode persistence or callbacks and without clearing the coordinator, pending state, notifications, flow candidate, coordinator-owned compensation task/record, auth Stores, or ownerless global sessions.
- With no attached `HassEntry` and no active flow, the coordinator watchdog may suspend; a later attach restarts it and requests a pending check.
- The new `HassEntry` attaches during setup; pending does not start until setup completes, the entry is `LOADED`, and no active reauth/reconfigure flow remains.
- Update-listener reloads and Store-only reauth scheduled reloads both preserve pending state; the old `HassEntry` never starts the pending flow.
- `async_remove_entry()` closes and removes the coordinator, cancels and awaits `compensation_task`, and dismisses both notifications even if unload failed.
- Closing first marks the coordinator irreversible; late flow removal, cloud callbacks, registration, and pending checks cannot recreate it for an absent ConfigEntry.
- Core may abort an active reauth flow after integration cleanup; flow-owned candidate cleanup still runs and its coordinator notification becomes a no-op.
- Home Assistant restart does not restore coordinator, snapshot, save-retry, transaction-progress, `pending_compensation`, `compensation_task`, or `persistence_inconsistent` state and creates no durable transaction marker; post-restart setup starts from the currently persisted ConfigEntry data and SID Store.

### `tests/test_config_flow_reauth.py`

Reauth Config Flow against the real flow manager:

- Both SIDs use the same `async_step_reauth_password`, `async_step_reauth_verify`, `async_step_reauth_captcha`, and `async_step_reauth_save` implementations.
- Parameterized password, verification, captcha, cross-challenge, invalid-auth, access-denied, and network transitions produce identical forms for both SIDs.
- Reauth passes `persist=False`; existing Config/Options Flow helper integration preserves their finish behavior without direct challenge-secret access.
- `async_step_reauth()` registers its SID and assigned `flow_id` before returning the initial form. `pending_compensation` takes priority and routes to compensation-only `reauth_save`; otherwise, if a racing recovery-succeeded callback already cleared `auth_failed`, the step creates no candidate and aborts with `reauth_successful`.
- Every active reauth submission rechecks `auth_failed` before candidate login or persistence; a recovered SID with neither persistence marker nor pending compensation clears its private candidate and aborts with `reauth_successful` without credential writes. An active candidate-owning persistence retry remains in `reauth_save`, while a flow created with `pending_compensation` constructs no candidate and remains in compensation-only `reauth_save` until restoration succeeds.
- A Core-initiated setup-time reauth without explicit SID data registers as `xiaomiio`.
- Password, verify-ticket, and captcha initial forms for every canonical authentication category.
- `INVALID_CREDENTIALS` returns `invalid_auth`, `ACCESS_DENIED` returns `access_denied`, and neither aborts the flow.
- Network, timeout, and server failures use fixed ordinary form errors and do not expose exception text.
- Every reauth step, field, base error, and abort reason resolves through the fixed translation keys; no exception or response value is used as a key or rendered copy.
- Parameterized form tests assert the exact placeholder allowlist: `entry_title` and fixed `cloud_name` everywhere, plus only `verify_url` for verification or `captcha_image` for captcha.
- Notification tests cover the fixed `auth_failed`, `verify_required`, and `captcha_required` variants and reject every interpolation except `entry_title`, fixed `cloud_name`, the configuration link, and `verify_url` for the verification variant.
- Secret and exception canaries are absent from all translated form descriptions, errors, abort results, and notification title/body values.
- Fixed username, region, connection mode, and SID fields.
- `wrong_account` without credential updates.
- Main-cloud ConfigEntry-only persistence without reading or touching either micoapi or legacy main Stores.
- Entry-scoped micoapi persistence without touching main token fields or any legacy Store.
- Optional common-password update in ConfigEntry data; omitted replacement input preserves the existing password.
- ConfigEntry options remain byte-for-byte unchanged and contain no account fields before or after reauth.
- Identity is verified before any Store or ConfigEntry write.
- A missing Store and a present empty Store produce distinct snapshots.
- Deterministic Store-before-ConfigEntry ordering and reverse-order rollback.
- A Store write failure in micoapi reauth leaves the ConfigEntry and runtime state unchanged, requests no reload, and enters `reauth_save`.
- A ConfigEntry update failure after micoapi Store write restores the exact prior entry-scoped Store payload or removes a newly created Store, requests no reload, and never reports `reauth_successful`.
- Rollback failure marks `persistence_inconsistent`, retains the flow and notification, and does not reload.
- Save retry reuses the private authenticated candidate without another Xiaomi login, verification ticket, or captcha.
- Success clears candidate challenge and password before runtime handoff or reload.
- Cancellation from candidate-owning save retry transfers exact local restore inputs to `PendingAuthCompensation` before clearing and discarding candidate challenge, password, cloud, and prepared payloads; the coordinator task runs under the auth commit barrier.
- Successful cancellation compensation clears the process-local record and inconsistency marker while retaining authentication failure, notification, and flow cooldown.
- Failed cancellation compensation retains no candidate but preserves the secret-bearing restore record; after cooldown the next flow enters compensation-only `reauth_save` and retries no Xiaomi operation. Restoration routes a still-failed SID to `reauth_password`, while a SID already cleared by recovery-succeeded aborts with `reauth_successful` without credential writes.
- Restart discards the compensation record intentionally; permanent removal cancels its task, clears it, and still deletes only the entry-scoped micoapi Store.
- Wrong-account abort writes nothing and clears all candidate challenge state.
- Runtime unload clears only runtime-generation challenges and never an active flow candidate.
- Repeated cleanup and delayed old-generation cleanup are harmless.
- Snapshot, candidate, Store, and secret-bearing persistence errors never enter logs, flow results, placeholders, or notifications.
- Auth persistence holds `auth_commit_lock` from snapshot through coordinator terminal-state recording; the update listener waits for `auth_commit_idle` before reloading, including when HA 2024.11 schedules it immediately after `async_update_entry()`.
- Successful reauth with a changed ConfigEntry and registered integration listener reloads exactly once after the barrier; unchanged reauth data and changed reauth data without a registered listener use exactly one `async_schedule_reload()` fallback.
- Initial-setup automatic recovery uses no reload and registers the listener at normal setup completion.
- Loaded-entry xiaomiio automatic recovery with changed ConfigEntry data fires its update listener and reloads exactly once without calling `async_schedule_reload()`; unchanged data causes no reload.
- Store-only micoapi reauth treats `async_update_entry()` returning `False` as success and calls `async_schedule_reload()` exactly once, while loaded-entry micoapi automatic recovery saves only its Store, does not call `async_update_entry()`, and does not reload.
- A reauth after `ConfigEntryAuthFailed` with changed data and no registered listener calls `async_schedule_reload()` exactly once.
- Cancellation calls `async_remove()`, triggers flow cooldown, and does not clear automatic-login suppression.
- Pending SID remains in `EntryReauthCoordinator` across both update-listener reloads and Store-only reauth scheduled reloads.
- The old `HassEntry` never starts pending; the newly attached generation starts it only when the entry is `LOADED` and the successful flow is no longer active.
- Setup completion, flow removal, and watchdog checks are idempotent when they race to resume pending.

### `tests/test_setup_reauth.py`

ConfigEntry setup and cache lifecycle:

- Fresh and stale cache reads return shallow device copies without a cloud request.
- Missing, unparseable, malformed-root, malformed-`devices`, and mapping-free caches return unavailable without refresh, overwrite, or deletion.
- A valid empty cache remains distinguishable from an unavailable cache, but both raise `ConfigEntryAuthFailed` when no local device can be admitted.
- Shared pure filtering preserves hidden-device and configured filter behavior without mutating cached items or injecting `mac`.
- Cache-only setup admits only filtered devices with `did`, `model`, usable MIOT spec, locally capable connection mode, and nonempty local host and token.
- A cache with devices but no admitted local device raises `ConfigEntryAuthFailed`; it does not complete an empty setup.
- At least one admitted local device completes cache-only setup without directly requesting reauth; the coordinator starts the pending `xiaomiio` flow exactly once only after the ConfigEntry reaches `LOADED`.
- With no admitted local device, setup raises `ConfigEntryAuthFailed` and only Core creates the reauth flow; `async_step_reauth()` self-registers against the existing or newly created `xiaomiio` state.
- A failure callback arriving before cache loading, during cache admission, or concurrently with setup completion produces one SID state, one notification, and one flow under both cache outcomes.
- Cloud-only devices are omitted from cache-only configs and remain unavailable until the successful reauth reload.
- Reauth reload resumes normal cloud-backed setup.
- Permanent entry removal closes and removes the coordinator, cancels its tasks, dismisses both notifications, and leaves late callbacks unable to recreate state.
- Permanent cleanup succeeds after unload failure and while Core still has an active flow to abort.
- Ordinary unload preserves all auth Stores.
- Permanent removal deletes only `xiaomi_miot/auth-<entry_id>-micoapi.json`; it preserves legacy main and micoapi Stores and shared inventory cache.
- Removing one of two same-account entries does not affect the other entry's micoapi credentials.

### Common fixtures

- `cloud_config_entry` (mock entry with stored username, password, region, `user_id`, `service_token`, `ssecurity`).
- `clean_xiaomi_state` to clear `HassEntry.ALL`, `EntryReauthCoordinator` instances, `hass.data[DOMAIN]["sessions"]`, pending notifications, and tasks between tests.
- Stateful `auth_store` fake that distinguishes absent, empty, valid, corrupt-backup, save failure, remove failure, and rollback failure states.
- Synchronous and asynchronous transport response fakes with body/header/cookie access canaries and observable close/release state.
- Controllable monotonic clock for automatic-login suppression, flow cooldown, and watchdog tests.

### CI

CI runs the complete pytest suite, including all four authentication suites, in two environments:

- the stable lane retains Python 3.13 and installs the current `requirements_test.txt`, exercising the current stable Home Assistant selected by the unpinned test package;
- the minimum-version lane uses Python 3.12 and installs `requirements_test.txt` under a checked-in `constraints_test_ha_2024_11.txt` containing exactly:

  ```text
  pytest-homeassistant-custom-component==0.13.181
  homeassistant==2024.11.0
  ```

`pytest-homeassistant-custom-component==0.13.181` is the release whose package metadata pins Home Assistant 2024.11.0; later releases must not replace it in the minimum lane. Both lanes run `python -m pytest -q`, not a reduced authentication-only selection. The separate Home Assistant configuration-validation matrix is `[stable, dev, "2024.11.0"]`. Secret canaries are checked across logs, callbacks, notifications, flow results, and placeholders.

The constraint file, CI workflow, and `hacs.json` change only during implementation. The spec records their exact target values now so metadata, runtime API assumptions, pytest, and configuration validation all enforce the same minimum release.

## Acceptance Criteria

1. The integration requires Home Assistant 2024.11.0 or newer and uses its native ConfigEntry reauth APIs without a direct flow-manager compatibility fallback.
2. Reauth starts only after an explicit authentication rejection and a canonical authentication-category automatic-login failure. A transient timeout, connection error, or HTTP 5xx login failure sets automatic-login suppression but produces no report or reauth flow. While `auth_rejected` is True, sequential runtime requests do not preflight-login; suppression short-circuits only after the original API operation produces another explicit rejection. An ordinary API transport-level 401 is exactly `TOKEN_EXPIRED + API_REQUEST` and, when terminal, re-raises a sanitized `MiCloudAuthError` containing only category, SID, and stage; a terminal API-level rejection returns the parsed rejection result unchanged. Account and micoapi STS HTTP rejections use the fixed exhaustive stage/category mapping.
3. Both `xiaomiio` and `micoapi` use the canonical `AuthFailureCategory`, structured `LoginChallenge`, and shared `CloudLoginFlowHelper` contract, entering deterministic password, verification-ticket, captcha, or access-denied transitions through one set of reauth steps; only a successfully authenticated mismatched Xiaomi account aborts as `wrong_account`.
4. Polling cannot create duplicate flows, duplicate notifications, repeated login storms, or unbounded retries; Core owns entry-level flow deduplication while `HassEntry` serializes failed SIDs. Request cancellation cannot cancel or strand a shared recovery episode, while runtime-owner cancellation performs no persistence or callback.
5. Successful recovery updates only the failed SID's single authoritative credential store and any explicitly replaced common password in ConfigEntry data: xiaomiio token material exists only in ConfigEntry data, while micoapi token material exists only in its entry-scoped Store. It leaves ConfigEntry options unchanged and refuses an authenticated Xiaomi `user_id` that does not match the ConfigEntry.
6. Store and ConfigEntry persistence uses snapshot-aware process-local compensation: no partial commit is reported as success, rollback failure remains visible as `persistence_inconsistent` for the lifetime of the current Home Assistant process, and active-flow save retry does not repeat Xiaomi authentication. Cancellation transfers only exact local restore state to coordinator-owned `PendingAuthCompensation`; its retry contacts no Xiaomi service, and after restoration a still-failed SID requires a new password submission because the cancelled candidate was destroyed, while an already-recovered SID completes without credential writes. Restart intentionally discards this state and creates no durable transaction journal.
7. During setup-time main-cloud authentication failure, a dedicated cache-only API reads fresh or stale inventory without cloud I/O or Store mutation. With at least one filtered, locally capable cached device that has complete local connection data and a usable spec, setup completes and the coordinator starts the pending native reauth only after the entry reaches `LOADED`; otherwise setup raises `ConfigEntryAuthFailed` and delegates flow creation exclusively to Core. Runtime authentication failure never unloads already-running local entities, and a local/token ConfigEntry without a main runtime cloud retains `entry.cloud is None` without creating one implicitly.
8. Successful reauth updates and aborts the existing flow, triggers exactly one ConfigEntry reload through either the update listener or the Store-only fallback schedule, dismisses the matching notification, and clears runtime state.
9. Reauth never changes username, region, connection mode, SID, or device filters; user-initiated changes to those settings are outside this feature and are not authentication recovery.
10. No credential or internal challenge secret is exposed through logs, notifications, flow results, or placeholders. Authentication HTTP statuses are classified and their responses closed or released before any body, header, cookie, or decoding accessor is used. The user-facing verification URL may appear only in the verification form and `verify_required` notification; the captcha image may appear only in the captcha form.
11. A successful automatic-recovery episode reconciles the matching SID's stale coordinator and notification state exactly once only when its `AuthEpisodeToken` remains current, including races with pending, cooldown, starting, active, reload, and flow-removal paths. Older episode or runtime-generation callbacks are no-ops; the accepted callback does not change another SID or write a reauth candidate. Within the current Home Assistant process, an unresolved `persistence_inconsistent` marker, active save-retry flow or coordinator-owned `PendingAuthCompensation`, and notification remain visible until restoration or persistence succeeds; restart intentionally discards them.
