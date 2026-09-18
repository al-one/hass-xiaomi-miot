# Xiaomi Cloud Authentication Reauth Design

## Summary

When a Xiaomi main-cloud (`xiaomiio`) or XiaoAI-cloud (`micoapi`) credential is explicitly rejected at a supported authentication-check boundary and the existing relogin attempt cannot recover it, Xiaomi Miot starts Home Assistant's native reauthentication flow. The user enters the account password and, when required by Xiaomi, completes verification-ticket or captcha steps. Successful reauth updates only the affected SID's existing credential destinations and reloads the ConfigEntry.

This design intentionally implements only the minimum complete reauth path. It reuses the integration's current login protocol, challenge attributes, auth Stores, update listener, and Home Assistant's own flow deduplication. It does not introduce an authentication coordinator, episode tokens, automatic-login suppression, transaction compensation, cache-based setup recovery, or a new persistence architecture.

The implementation requires Home Assistant 2025.6.0 or newer.

## Goals

- Start native Home Assistant reauth from the supported setup and authentication-check boundaries for `xiaomiio` and `micoapi`.
- Do not add request-level reauth triggering to every background API call.
- Support password, Xiaomi verification-ticket, and captcha login steps.
- Verify that the authenticated Xiaomi account matches the existing ConfigEntry.
- Persist refreshed credentials using the integration's existing ConfigEntry and SID Store conventions.
- Reload the existing ConfigEntry after successful reauth.
- Avoid exposing passwords, tokens, cookies, challenge sessions, or complete Xiaomi responses through the flow, logs, or notifications.
- Keep already-running local entities loaded while reauth is being requested or is awaiting user input; only the normal successful ConfigEntry reload may recreate them.
- Isolate each ConfigEntry's runtime clouds from global session and account registries while preserving existing ownerless YAML and Config/Options Flow behavior and all three documented service SIDs.

## Non-goals

- No request-level auth recovery or reauth trigger in ordinary background `async_request_api()` calls. API code `2`/`3` and HTTP 401 responses outside the supported check boundaries retain their current logout/return behavior.
- No manual micoapi verification option. If micoapi authentication expires only in a later background request, the user must reload the ConfigEntry so the entry-bound micoapi cloud can re-probe and start reauth after a typed authentication or challenge outcome.
- No redesign of the existing automatic relogin algorithm.
- No single-flight login task, waiter tracking, cancellation shielding, retry suppression, or cooldown.
- No `AuthEpisodeToken`, runtime generation, stale-callback protocol, or recovery-succeeded callback.
- No `EntryReauthCoordinator`, SID queue, pending state, flow watchdog, or custom flow-removal tracking.
- No guarantee that a second SID failure is automatically resumed after another entry-bound flow wins the race. A later explicit rejection may request reauth again.
- No cache-only setup or stale device-inventory fallback.
- No new entry-scoped Store format, legacy Store migration, or change to current Store naming.
- No cross-file transaction, snapshot rollback framework, commit barrier, save-retry transaction state, `persistence_inconsistent`, or cancellation compensation.
- No durable reauth or transaction state across Home Assistant restart.
- No Home Assistant `reconfigure` flow.
- Reauth cannot change the Xiaomi username, region, connection mode, device filters, or failed SID.

## Existing Behavior Reused

The implementation keeps these existing mechanisms:

- `MiotCloud.async_check_auth()` checks the current token and performs one existing relogin path when authentication has expired.
- `MiotCloud` already distinguishes `xiaomiio` and `micoapi` through `sid`.
- Xiaomi verification uses `MiCloudNeedVerify`, `verify_url`, `identity_session`, and `verify_ticket`. The `verify_ticket()` HTTP request pins `trust='false'` and the documented Xiaomi payload fields (`_flag`, `ticket`, `_json`), so the integration does not request persistent browser-trust cookies from Xiaomi and matches the request shape observed in production HAR captures.
- Captcha login uses `captchaImg`, `captchaIck`, pending login data, and `captcha`.
- `MiotCloud.async_stored_auth()` already stores xiaomiio and non-xiaomiio SID credentials in separate existing Store files.
- The ConfigEntry update listener reloads the entry when ConfigEntry data changes.
- Home Assistant Core owns ConfigEntry flow locking and duplicate reauth handling.

Existing Config Flow and Options Flow behavior remains unchanged except for small shared login utilities or security fixes directly required by reauth and removal of the transient `micoapi_verify` action with its ownerless `async_step_micoapi`. The lazy entry-bound micoapi probe may start native reauth after a 401 or absent token and a failed typed login/relogin outcome. The implementation does not otherwise migrate those flows to a new authentication state machine.

## Minimal Architecture

### SID identification

The integration recognizes the three existing cloud service identifiers, while only two participate in reauth:

```python
class CloudSid(StrEnum):
    XIAOMIIO = "xiaomiio"
    MICOAPI = "micoapi"
    I_MI_COM = "i.mi.com"


REAUTH_SIDS = frozenset({CloudSid.XIAOMIIO, CloudSid.MICOAPI})
```

External SID values are converted to `CloudSid` at the Config Flow, `HassEntry`, SID-change, and `request_xiaomi_api` service boundaries. Values outside the enum are rejected before cloud or Store selection with a fixed error that does not interpolate the raw SID. The service recognizes all three enum values; a recognized SID whose entry-bound lookup returns no usable cloud follows the separate fixed unavailable-cloud behavior below. Reauth accepts only `REAUTH_SIDS`; `CloudSid.I_MI_COM` and invalid values abort with the fixed `unsupported_sid` reason, expose no raw SID placeholder, and never select a reauth Store.

### Entry-bound runtime clouds

A runtime cloud that may be used by a ConfigEntry is associated with exactly one `HassEntry`. `HassEntry` keeps the three possible runtime cloud results in a small SID map and serializes cache misses with one entry-local creation lock:

```python
clouds: dict[CloudSid, MiotCloud | None]
_cloud_lock: asyncio.Lock

async def async_get_cloud(
    self,
    sid: CloudSid = CloudSid.XIAOMIIO,
    *,
    login: bool = False,
) -> MiotCloud | None:
    ...
```

An absent SID key means that cloud creation has not been attempted in this `HassEntry` lifecycle. A `MiotCloud` value is a completed usable result. `None` is stored only as the terminal negative result of the lazy micoapi bootstrap, meaning that creation and the dedicated probe finished without making micoapi available. `async_get_cloud()` checks membership before taking `_cloud_lock`, checks it again after acquiring the lock, and keeps a newly constructed micoapi candidate local until its probe completes. It publishes either the usable cloud or `None` before releasing the lock, so concurrent entity additions never observe an unprobed cloud and never start a second construction, probe, or login. The negative result is process-local and lasts only until the current `HassEntry` is cleaned up or reloaded.

The existing `entry.cloud` compatibility property returns the xiaomiio cloud or `None`. Local/token ConfigEntries do not create a cloud merely by reading this property.

`MiotCloud` accepts an optional owner, and `from_token()` propagates it explicitly:

```python
class MiotCloud:
    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        password: str,
        country: str | None = None,
        sid: CloudSid | str | None = None,
        *,
        hass_entry: HassEntry | None = None,
    ) -> None:
        ...

    @staticmethod
    async def from_token(
        hass: HomeAssistant,
        config: dict,
        login: bool | None = None,
        *,
        hass_entry: HassEntry | None = None,
    ) -> MiotCloud:
        ...
```

When `hass_entry` is supplied, the cloud is entry-bound: that owner's `hass_entry.clouds` is its authoritative owner and construction cache. The cloud does not query, reuse, insert, or replace `hass.data[DOMAIN]["sessions"]`, and it is never published through `hass.data[DOMAIN]["accounts"]`. Its `async_login()` may retain the existing Store persistence and login-attempt behavior, but skips global-session registration; `async_relogin()` delegates to that owner-aware wrapper and therefore has the same rule. ConfigEntry setup passes its `HassEntry` to `MiotCloud.from_token()` and does not write the resulting cloud to `accounts[user_id][CONF_XIAOMI_CLOUD]`.

When `from_token()` finds a cached `MiotCloud` in `hass.data[DOMAIN]["sessions"][mic.unique_id]` (this lookup is ownerless-path only — an entry-bound cloud never enters the sessions registry, so the cache hit only happens for ownerless constructions before entry binding) it does **not** mutate the cached object. It shallow-copies the cached cloud, rebinds the new `hass_entry` onto the clone, and runs `merger_config(config)` on the clone so each caller receives an independent cloud with its own `hass_entry`, `service_token`, `ssecurity`, session, and pending login data. The cached object remains intact for any other caller that still holds a reference to it. This prevents concurrent ConfigEntries that share a Xiaomi account from clobbering each other's session and token material when `merger_config` would otherwise overwrite them in place.

After successful xiaomiio setup, the existing per-entry runtime configuration at `hass.data[DOMAIN][entry_id]` retains `CONF_XIAOMI_CLOUD` as a compatibility alias to the exact same object as `hass_entry.clouds[CloudSid.XIAOMIIO]`. This entry-id-scoped alias is not an owner, cache, or session registry: cloud construction, SID changes, authentication callbacks, login, and reauth never read it to select or reuse a cloud. It exists only so the current `entry_config(CONF_XIAOMI_CLOUD)`, `MiotCloud.all_clouds()`, component services, and system-health paths continue to discover the entry's xiaomiio cloud. micoapi, `i.mi.com`, and negative `None` results receive no such alias.

When `hass_entry` is `None`, the cloud is ownerless. Existing YAML, Config Flow, Options Flow, and service calls originating from an ownerless cloud keep their current global-session lookup, reuse, and insertion behavior; legacy YAML keeps its current `accounts` publication. This design does not convert those callers to entry ownership.

For an entry-bound cloud, `async_change_sid()` converts the requested value to `CloudSid` and delegates to `hass_entry.async_get_cloud()`, so every supported SID retains the same ConfigEntry owner. `CloudSid.I_MI_COM` is created lazily only when explicitly requested by `request_xiaomi_api`; it is stored in the owner's SID map and uses the existing SID-specific login and Store behavior, but receives no authentication-failure callback, performs no setup probe, and cannot start reauth. Values outside `CloudSid` fail before constructing a cloud or selecting a Store. The single entry-local `_cloud_lock` protects only SID-map cache misses and the initial micoapi probe; it is not a login-task cache, waiter protocol, coordinator, or cross-entry lock. No generation counters, cancellation shielding, unload handoff, or authentication coordinator are added. Ordinary entry unload removes the per-entry runtime configuration and its xiaomiio compatibility alias through the existing unload path, then discards the `HassEntry`, its positive and negative SID results, and all cloud references.

The `request_xiaomi_api` service backend validates its optional `sid` against the three `CloudSid` values rather than accepting an arbitrary string; its existing selector already exposes those same values. `HassEntity.async_request_xiaomi_api()` defaults to `CloudSid.XIAOMIIO`, converts the service value before calling `async_change_sid()`, and raises a fixed `HomeAssistantError` for an unsupported value without including that value in the message. After a supported SID change, it verifies that the returned object is a `MiotCloud`. If entry-bound lookup returns `None`, including a cached unavailable micoapi result, it raises the fixed `HomeAssistantError("Xiaomi cloud is unavailable")` without including the SID, exception text, or challenge state. This unavailable path retains the negative cache and performs no cloud reconstruction, probe, login, Xiaomi API request, Store access, authentication callback, or reauth request. This intentionally removes undocumented arbitrary-SID Store selection while preserving the documented `i.mi.com` service path and making optional micoapi failure explicit.

`async_setup_entry()` registers an idempotent ConfigEntry `async_on_unload()` cleanup immediately after obtaining the `HassEntry` and before the first cloud authentication await. Before clearing the SID map, the cleanup removes `hass.data[DOMAIN][entry_id]` only when that runtime configuration's `CONF_XIAOMI_CLOUD` alias is the exact xiaomiio object still owned by this `HassEntry`; a setup failure before alias publication has nothing to remove. It then clears that setup attempt's SID results and cloud-device cache, and removes `HassEntry.ALL[entry_id]` only when it still refers to the same `HassEntry` instance. These identity checks prevent an old setup callback from removing a newer instance or its compatibility alias. On normal unload the existing unload path performs the full platform, device, and per-entry runtime-configuration teardown first; the lifecycle cleanup is a harmless final fallback.

### Authentication-failure callback

Only an entry-bound cloud whose SID belongs to `REAUTH_SIDS` receives the optional callback:

```python
async def async_auth_failed(sid: CloudSid) -> None:
    ...
```

The callback carries only the SID. It does not carry a cloud object, exception, response, password, token, cookie, challenge data, or Store payload.

`MiotCloud.async_check_auth()` invokes this callback only when all of the following are true:

1. Its token check produced an explicit authentication rejection recognized by the existing token-expiry rules.
2. The existing relogin attempt did not succeed.
3. Relogin ended with `MiCloudAuthenticationError`, `MiCloudNeedVerify`, or candidate-local captcha challenge state.

The lazy entry-bound micoapi probe uses the same callback only when its one login/relogin attempt ends with one of those typed authentication or challenge outcomes. A probe HTTP 401 alone does not start reauth. Ordinary API calls do not use this callback.

Connection errors, timeouts, HTTP 5xx responses, malformed responses, package or other business errors, unknown Xiaomi error codes, and ordinary API errors do not invoke the callback. The existing relogin attempt and request retry limit are not redesigned.

### Typed authentication outcomes

Reauth classification uses exception types and explicit candidate challenge state; it never classifies an exception by matching its message. Add narrow exceptions that remain compatible with existing broad `MiCloudAccessDenied` callers:

```python
class MiCloudAuthenticationError(MiCloudAccessDenied):
    """Xiaomi explicitly rejected supplied authentication."""


class MiCloudVerificationError(MiCloudAccessDenied):
    """Xiaomi did not accept the verification ticket."""


class MiCloudStsUnauthorized(MiCloudAccessDenied):
    """Xiaomi micoapi STS rejected the completed login."""
```

`MiCloudVerificationError` and `MiCloudStsUnauthorized` are intentionally not `MiCloudAuthenticationError`. The former is an interactive ticket rejection within an existing verification challenge; the latter is a narrow, retryable micoapi login-transport outcome. Neither is evidence that the account password is invalid, and neither may trigger setup or runtime reauth. All three types use fixed, secret-free messages. `MiCloudAccessDenied` by itself, including either narrow non-authentication subtype after its permitted handling, is not sufficient evidence to start reauth.

The existing login protocol is classified at its source:

- `verify_ticket()` preserves connection and timeout exceptions and never uses an empty dictionary as a generic failure. Missing `verify_url`, a missing identity session, no supported phone/email verification method, an unparseable response, or `code == 0` without a non-empty login location raises a fixed `MiCloudException`. A parseable explicit non-zero result from every attempted supported verification method raises `MiCloudVerificationError` and preserves the candidate's verification challenge so the user can retry. Only `code == 0` with a non-empty location returns success. `_login_request()` either receives that successful location or propagates the typed exception; it never falls through to `_login_step2()` with empty auth after ticket failure.
- `_login_step1()` preserves `requests.ConnectionError` and timeout exceptions. Response parsing failures and other unexpected protocol failures become a fixed, secret-free `MiCloudException`; step 1 does not produce `MiCloudAuthenticationError` without an explicit structured rejection.
- `_login_step2()` maps only known credential rejection codes to `MiCloudAuthenticationError`: `20003` invalid username, `70002` invalid credentials, `70016` invalid credentials when no complete captcha challenge is returned, and `87001` rejected captcha only after a replacement challenge has been fetched successfully. A captcha challenge is complete only when candidate-local `captcha_url`, `captchaImg`, and `captchaIck` are all non-empty. An initial `70016` or other response with a captcha URL fetches and stores all three values and returns an unsuccessful attempt rather than an authentication error. Before submitting a non-empty captcha, the candidate removes the old image and `ick` but retains the private normalized URL for one refresh. On `87001`, it prefers a new response URL, otherwise reuses that retained URL, and fetches a replacement image and `ick`; only then does it raise `MiCloudAuthenticationError`. A connection or timeout during refresh preserves its network type; a missing URL, malformed image response, empty image, or missing `ick` becomes fixed `MiCloudException`. Every failed refresh leaves all captcha challenge attributes cleared. `81003` or a verification URL produces `MiCloudNeedVerify`. `22009` package denial, unknown codes, HTTP 5xx, an unparseable response, and an unexpected response without a login location are ordinary `MiCloudException` outcomes.
- `_login_step3()` preserves connection and timeout exceptions. If `sid == CloudSid.MICOAPI`, the login location has the exact existing Mina STS host/path, the response status is 401, and no `serviceToken` is present, it raises `MiCloudStsUnauthorized`. That exception has a fixed message and contains no location, cookies, status payload, or response body. HTTP 5xx, parsing failures, an unexpected redirect, or a response without `serviceToken` outside the narrow exception below is an ordinary `MiCloudException`, not an authentication rejection. Step 3 produces `MiCloudAuthenticationError` only if Xiaomi supplies a recognized structured credential-rejection code, with one narrow exception: when `_login_request()` reached `_login_step3` after a `verify_ticket()` that returned a non-empty `location`, the final redirect landed on Xiaomi's public `/fe/service/login` HTML page with no `serviceToken` cookie, step 3 raises `MiCloudAuthenticationError` with the fixed message `"Xiaomi login step3 missing service token"`. This protects the user from seeing the generic `unknown` mapping for what is in practice a credential rejection (Xiaomi declined to issue a service token after verification). The exception contains no location, cookies, response body, or challenge state; the candidate is cleared before step 3 raises.

Every exception created by these paths has a fixed, secret-free message. It contains no response body, cookies, login data, location query parameters, verification ticket, captcha cookie, identity session, service token, or `ssecurity`.

### micoapi token probe

Stored micoapi credentials are checked without forcing a full login on every reload:

```python
async def async_check_micoapi_auth(self) -> bool | None:
    ...
```

The check performs one status-aware `GET` to the existing Mina `https://api2.mina.mi.com/admin/v2/device_list` endpoint with the current micoapi token. The probe consumes only the HTTP status and enough parsed structure to establish success; it never logs or returns the complete response or device list.

- HTTP 200 with the expected parseable response proves the current token is accepted and returns `True` without logging in.
- HTTP 401 synchronously clears the rejected candidate's in-memory `service_token`, `ssecurity`, `async_session`, `identity_session`, `verify_url`, and `login_data` — the same six fields the `reauth_verify` STS retry clears — and then runs the existing relogin path once. Successful relogin persists through the existing SID Store behavior and returns `True`. `MiCloudAuthenticationError`, `MiCloudNeedVerify`, or captcha challenge state invokes the SID-only callback and returns `False`.
- Absence of a stored token also runs the existing login path once, with the same typed outcome handling.
- Connection errors, timeouts, HTTP 5xx, malformed responses, unexpected HTTP statuses, and business errors return `None` and invoke no reauth callback.

HTTP 401 is passed to this checker as a structured status, not detected from exception text or response content. The existing ordinary background `async_request_api()` behavior remains unchanged; only this dedicated lazy probe opts into status-aware handling.

The entry-bound micoapi cloud is created lazily by the first `MiotMediaPlayerEntity` whose device spec exposes an `intelligent_speaker` service, through `HassEntry.async_get_cloud(CloudSid.MICOAPI)` during `async_added_to_hass()`. Because Home Assistant may add those entities concurrently, the first cache miss performs construction and the dedicated probe while holding the entry-local cloud lock; concurrent and later entities receive the same completed positive or negative result. The lazy probe is therefore the only micoapi authentication check performed in this `HassEntry` lifecycle. A typed authentication/challenge failure requests reauth, clears the rejected candidate's in-memory credentials and challenge data, drops the candidate reference, stores `None` for `CloudSid.MICOAPI`, leaves micoapi unavailable, and does not fail xiaomiio setup or local entities. A transient probe failure invokes no reauth callback but stores the same terminal negative result, so it also remains optional and is not retried until ConfigEntry reload creates a fresh `HassEntry`.

### Private reauth candidate

The private reauth candidate is constructed directly with `hass_entry=None`, does not call `from_token()`, and calls only `async_login_attempt()`. It is ownerless only in the type-level sense that it has no `HassEntry`; unlike ordinary ownerless runtime clouds, it never enters `hass.data[DOMAIN]["sessions"]` or `hass.data[DOMAIN]["accounts"]`, never loads a different account from either registry, and is never shared with another flow. It remains private Config Flow instance state until the flow ends.

The cloud login operation is split into a side-effect-free attempt and the existing persistent wrapper:

```python
async def async_login_attempt(
    self,
    login_data: dict | None = None,
) -> bool:
    ...


async def async_login(
    self,
    login_data: dict | None = None,
) -> bool:
    ...
```

`async_login_attempt()` performs only the Xiaomi account, verification-ticket, and captcha protocol. It retains the existing login-attempt limit and mutates only the candidate's in-memory token, cookies, session, challenge attributes, and `login_times`. It never calls `async_stored_auth(save=True)`, never calls `async_stored_auth(remove=True)`, and never writes either global registry.

`async_login()` becomes an owner-aware wrapper around `async_login_attempt()`. For every caller it may remove stale stored auth after the existing failure threshold, saves successful auth through `async_stored_auth(save=True)`, and resets `login_times` only after persistence succeeds. It registers the successful cloud in `hass.data[DOMAIN]["sessions"]` only when `hass_entry is None`; an entry-bound cloud remains private to `hass_entry.clouds`. `async_relogin()` continues to call `async_login()` and therefore inherits the same ownership rule without a separate registration path.

Reauth always calls `async_login_attempt()` until account identity has been validated. No boolean persistence flag is added to `async_login()`.

The candidate password, token, cookies, identity session, captcha cookie, normalized captcha URL, and pending login data remain on the flow or candidate only. They never enter flow context, flow results, description placeholders, callbacks, or logs.

## Reauth Trigger

### Supported authentication-check failures

The first implementation requests reauth only from these existing authentication-check boundaries:

1. An existing higher-level `async_request_miot_spec()` token-expiry path calls the entry-bound cloud's `async_check_auth()`. When its token check rejects authentication and the existing relogin ends with `MiCloudAuthenticationError`, `MiCloudNeedVerify`, or captcha challenge state, `HassEntry.async_auth_failed()` requests reauth.
2. The lazy entry-bound micoapi probe receives HTTP 401 or finds no stored token, performs one existing login/relogin attempt, and that attempt ends with one of those typed authentication or challenge outcomes. It invokes the SID-only callback rather than the old persistent notification.

After an accepted callback, `HassEntry.async_auth_failed()` performs only these actions:

1. Verify that the SID is supported.
2. Verify that the ConfigEntry still exists.
3. Accept either a `LOADED` ConfigEntry at a supported runtime boundary or `CloudSid.MICOAPI` while the ConfigEntry is `SETUP_IN_PROGRESS` for the lazy entry-bound micoapi probe. Reject every other state/SID combination.
4. Call `config_entry.async_start_reauth(hass, data={"sid": sid.value})`.

Home Assistant Core provides entry-level duplicate-flow handling. The integration does not keep a `starting`, `active`, `pending`, or `cooldown` state and does not run a watchdog.

If the entry is neither `LOADED` nor the allowed `SETUP_IN_PROGRESS` micoapi case, or another reauth/reconfigure flow prevents creation, the callback returns without maintaining pending work. The next supported authentication-check failure may request reauth again.

Ordinary background `async_request_api()` calls are explicitly outside this trigger boundary. Their API code `2`/`3` and HTTP 401 behavior remains the existing logout/return behavior; this phase does not add request-level relogin, retry, or reauth scheduling. A later supported auth check can still discover the invalid credential.

Starting or displaying reauth does not unload the ConfigEntry and does not remove already-running local entities. After successful reauth, the required normal ConfigEntry reload may unload and recreate those entities.

### Setup failure

xiaomiio setup (e.g., the `async_setup_xiaomi_cloud` ConfigEntry setup path) obtains the entry-bound xiaomiio cloud through `HassEntry.async_get_cloud(CloudSid.XIAOMIIO)` and then explicitly calls the cloud's `async_check_auth()` to validate the stored token. Setup raises `ConfigEntryAuthFailed` with a fixed, secret-free message in two cases: (a) the explicit `async_check_auth()` rejection path where the existing relogin ends with `MiCloudAuthenticationError`, `MiCloudNeedVerify`, or captcha challenge state, or (b) `async_get_cloud()` itself surfaces a typed authentication or verification exception — `MiCloudAuthenticationError`, `MiCloudVerificationError`, or `MiCloudStsUnauthorized` — when cloud construction triggered the relogin (e.g., absent stored credentials). Home Assistant Core first processes the registered `async_on_unload()` cleanup, removing the failed setup attempt's `HassEntry` and cloud references, and then creates the reauth flow. Absence of explicit SID data defaults to `CloudSid.XIAOMIIO`.

Setup never raises `ConfigEntryAuthFailed` for another `MiCloudAccessDenied` outside the narrow authentication subtype, `MiCloudException`, network errors, timeouts, HTTP 5xx, malformed responses, unknown Xiaomi error codes, package or other business errors, or ordinary Xiaomi API errors. Those continue to use the existing setup failure path. The SID-only authentication callback is not used for xiaomiio setup: reauth is started exclusively by Core's handling of `ConfigEntryAuthFailed`, so the entry remains in `SETUP_IN_PROGRESS` without first requesting a runtime reauth.

After successful reauth, the next setup attempt creates a new `HassEntry` and entry-bound xiaomiio cloud from the updated ConfigEntry data; it must not reuse the cloud rejected by the failed setup attempt.

Network errors and other non-authentication setup failures retain their existing handling. This design does not load cached device inventory to complete setup.

### micoapi failure

Entry-bound micoapi bootstrap uses the dedicated token probe above. The first `MiotMediaPlayerEntity` whose device spec exposes an `intelligent_speaker` service requests the entry-bound micoapi result through `HassEntry.async_get_cloud(CloudSid.MICOAPI)` during `async_added_to_hass()`. The entry-local cloud lock makes creation plus probe atomic with respect to other SID-map cache misses: concurrent entities wait, recheck the map after acquiring the lock, and reuse either the completed cloud or the terminal `None` result. The probe therefore runs exactly once per `HassEntry`, even when Home Assistant adds multiple qualifying entities concurrently. It does not force login when the stored token is accepted. Only a probe 401 or absent token runs one login/relogin attempt; only a typed authentication or challenge outcome from that attempt may request reauth. Authentication/challenge and transient probe failures both leave the per-entry negative result, so micoapi remains optional and unavailable without failing or unloading the ConfigEntry. If reauth completes before setup does, Home Assistant's ConfigEntry setup lock serializes the scheduled reload after the current setup attempt.

The old entry-bound micoapi verification notification, transient `micoapi_verify` Options Flow action, and ownerless `async_step_micoapi` verification form are removed. The action was never persisted, so no ConfigEntry migration is required. Later micoapi background requests do not directly start reauth in this phase; after such a failure, manually reloading the ConfigEntry discards the old `HassEntry` and its positive or negative SID cache, recreates the entry-bound media-player entities, and lets the fresh `HassEntry` run one new lazy micoapi probe, which may start native reauth after its login/relogin attempt fails with a typed authentication or challenge outcome.

## Reauth Config Flow

### Entry step

`async_step_reauth(entry_data)` obtains the existing ConfigEntry with `_get_reauth_entry()`. It reads `sid` from `entry_data` and defaults to xiaomiio only for a Core-created setup reauth that omitted SID data. Every other authoritative value, including username, region, and expected `user_id`, is read from that ConfigEntry rather than copied from `entry_data` into integration-owned flow state.

Home Assistant 2025.6 constructs reauth initialization data as `config_entry.data | (data or {})` and retains that new dictionary as the active flow's framework-owned `init_data` until the flow is removed. This design accepts that Core behavior and does not clear or mutate `entry_data`/`self.init_data`. The integration reads only the SID from `init_data`; fixed username, region, and expected `user_id` come directly from `_get_reauth_entry()`. It never copies the old password, token material, or any other value from `init_data` into integration-owned flow context, form results, description placeholders, callbacks, logs, or the private candidate. The candidate receives only the fixed username and region from the ConfigEntry plus the replacement password and challenge input submitted in later steps; those later inputs are not added to `init_data`. The dictionary is Core's temporary copy, not a new Store or mutation of the ConfigEntry.

The flow stores the validated SID in private instance state and always starts at `reauth_password`. It does not attempt to transfer a runtime cloud's existing challenge state. If Xiaomi requires verification or captcha, the private candidate creates the required challenge again after password submission.

Every reauth `async_show_form()` call supplies a localized `tip` placeholder through `description_placeholders`. `tip` carries the contextual user guidance for the current step (e.g., "Please enter your password" on empty `reauth_password` submission, or the rendered `MiCloudAuthenticationError` message when invalid credentials are rejected); its value is fixed, secret-free, and never contains the ConfigEntry title, username, Xiaomi user ID, or region. The integration does not inject a `name` placeholder: each form's translation references only `tip`, `verify_url`, or `captcha_image` as needed, and the Home Assistant frontend renders no entry-title placeholder against an unreferenced key. The reauth forms do not expose the ConfigEntry title and do not define separate `entry_title` or `cloud_name` placeholders.

The region remains fixed private input from the ConfigEntry: it is neither displayed through a description placeholder nor included in the form schema. The flow does not allow changes to username, region, connection mode, device filters, or SID. The saved password is never displayed as a form default.

### Password step

`async_step_reauth_password` declares `password` as `vol.Optional`. When the form is first shown, the placeholder includes a localized "Please enter your password" hint but never pre-fills the existing password. On submission, an empty or whitespace-only `password` falls back to `entry.data[CONF_PASSWORD]` (read from `_get_reauth_entry()`, not from `init_data`); only when neither the submitted nor the stored password is non-empty does the flow remain on `reauth_password` with `invalid_auth` and a `tip` placeholder carrying the localized "Please enter your password" message. The submitted or fallback password is used to create or replace the private candidate, which then calls `async_login_attempt()`.

Outcomes are mapped by type and explicit candidate challenge state:

- successful login: validate the candidate Xiaomi `user_id`;
- `MiCloudNeedVerify`: show `reauth_verify` with only the verification URL and `verify_ticket` field;
- captcha challenge state after an unsuccessful attempt: show `reauth_captcha` with only the captcha image and `captcha` field;
- `MiCloudAuthenticationError` without a challenge: remain on `reauth_password` with `invalid_auth` and a `tip` placeholder carrying the typed auth error's fixed, secret-free message;
- connection or timeout failure: remain on the current form with `cannot_connect`;
- `MiCloudAccessDenied` without the narrow authentication subtype and every other failure: remain on the current form with `unknown`.

A successful login whose `user_id` differs from the ConfigEntry's stored `user_id` clears the candidate and aborts with `wrong_account`. It performs no Store or ConfigEntry write.

### Verification step

`async_step_reauth_verify` submits the required `verify_ticket` to the same private candidate through `async_login_attempt(login_data={"verify_ticket": ticket})`. Empty input or `MiCloudVerificationError` remains on `reauth_verify` with `need_verify` and keeps the candidate's current verification challenge. A `MiCloudAuthenticationError` raised only after Xiaomi accepted the ticket and later rejected the account credentials clears the candidate and returns to `reauth_password` with `invalid_auth`. Connection or timeout failures remain on the verification form with `cannot_connect`; protocol, broad `MiCloudAccessDenied`, and unknown failures remain with `unknown`. No mapping exposes exception text.

After `verify_ticket()` returns a non-empty `location`, the login attempt follows that redirect chain with `response=True` before deciding whether another password-login round is needed. If the redirect chain already completes login and sets `serviceToken`, the attempt succeeds immediately. Otherwise the integration inspects only the outer redirect response URL: if that URL's path is under `/fe/` and its own query contains a non-empty `skipUrl`, the integration follows that `skipUrl` once with redirects enabled and accepts the resulting `serviceToken` if present. It does not parse HTML or script bodies for `skipUrl`, and it does not infer behavior from nested business-specific parameters such as `bizType`. Only when neither response yields a completed login does the flow continue with the existing `_login_step1()` plus `_login_step3()` path.

For micoapi only, reauth retains the legacy Options Flow's STS-401-after-verification workaround as a strict one-time retry inside `reauth_verify`:

1. Only `MiCloudStsUnauthorized` raised by the same candidate triggers the retry. No exception message parsing, status code string match, or response text inspection is used.
2. The retry synchronously clears that candidate's in-memory `service_token`, `ssecurity`, `async_session`, `identity_session`, `verify_url`, and `login_data`. It does not touch the persisted SID Store or the global session map.
3. The retry calls `async_login_attempt()` once with no `verify_ticket`. The retry adds no artificial delay, fixed wait, or back-off.
4. The retry is bounded to the current verification submission: a second `MiCloudStsUnauthorized` returned from that retry maps to `unknown` and does not schedule another attempt. A retry that yields any other typed outcome follows that outcome's mapping, including `MiCloudNeedVerify`, captcha challenge, `MiCloudAuthenticationError`, network error, or success. A retry that succeeds without identity validation does not start another reauth flow.

The retry does not recurse, mutate the verification form, store additional flow state, or persist before identity validation.

A returned captcha challenge routes to `reauth_captcha`. Success routes to persistence after the same `user_id` check.

### Captcha step

`async_step_reauth_captcha` accepts one required captcha. Empty input remains on the existing form with `need_captcha` and does not call `async_login_attempt()`, consume `captchaIck`, or replace the displayed challenge. A non-empty value is submitted to the same private candidate through `async_login_attempt(login_data={"captcha": captcha})`.

Outcome mapping inspects candidate challenge state before exception type:

- `MiCloudAuthenticationError` with a complete freshly fetched `captcha_url`/`captchaImg`/`captchaIck` challenge means Xiaomi rejected the submitted captcha; remain on `reauth_captcha`, replace the displayed image, and show `need_captcha`;
- `MiCloudAuthenticationError` without a complete challenge means account credentials were rejected; clear the candidate and return to `reauth_password` with `invalid_auth`;
- a connection or timeout raised while refreshing the challenge clears the candidate and returns to `reauth_password` with `cannot_connect`;
- `MiCloudException`, broad `MiCloudAccessDenied`, malformed challenge data, and unknown failures clear the candidate and return to `reauth_password` with `unknown`;
- `MiCloudNeedVerify` routes to `reauth_verify`, and success routes to persistence after the same `user_id` check.

The captcha form is never rendered after a non-empty submission unless the candidate holds a complete replacement challenge. The old image and `ick` are never reused. The captcha step does not perform an STS retry.

### Flow cleanup

The Config Flow overrides Home Assistant 2025.6's synchronous lifecycle hook with `@callback def async_remove(self) -> None:`. It clears all flow-owned reauth candidate references, candidate credentials, and challenge data, then explicitly calls `super().async_remove()`. It must not be declared `async def`, because Home Assistant invokes this hook without awaiting it. It does not report lifecycle state to `HassEntry` and does not track flow outcomes outside the flow instance.

Successful completion, wrong-account abort, ordinary abort, frontend cancellation, and manager removal therefore clear the private candidate reference and candidate password. Cleanup removes the candidate's challenge attributes and cookies from memory. Repeated cleanup is harmless. There is no coordinator notification or cross-flow save state.

## Persistence and Reload

Persistence begins only after successful candidate login and matching `user_id` validation.

### xiaomiio

For xiaomiio:

1. Persist the candidate through the existing xiaomiio `async_stored_auth(save=True)` path.
2. Invalidate matching entries in `hass.data[DOMAIN]["sessions"]` after the awaited Store save returns, using the validated `user_id`, server, and `xiaomiio` SID. The shared SID-parameterized invalidation synchronously iterates a snapshot of the session map, compares cloud-object fields rather than parsing session keys, and contains no `await`. This prevents a later ownerless `MiotCloud.from_token()` call from reusing stale token material.
3. Update the existing ConfigEntry data with only:
   - the submitted replacement password;
   - `service_token`;
   - `ssecurity`;
   - `device_id`;
   - the validated `user_id` value, which must equal the existing value.

Username, region, connection mode, filters, and ConfigEntry options remain unchanged. The current entry's normal reload recreates its entry-bound cloud directly from updated ConfigEntry data and the refreshed Store; it does not consult the global session map. Matching ownerless sessions are still invalidated so later YAML, Config/Options Flow, or service creation cannot reuse stale token material. Already-held entry-bound cloud objects belonging to other ConfigEntries are not broadcast-updated or reloaded by this phase. Reauth does not introduce, rename, migrate, or remove a Store.

### micoapi

For micoapi:

1. Persist the candidate through the existing SID-specific `async_stored_auth(save=True)` path.
2. After the awaited Store save returns, use the same synchronous SID-parameterized operation to invalidate global sessions whose cloud-object fields match the validated `user_id`, server, and `micoapi` SID.
3. Update only the common ConfigEntry password when the submitted password differs.
4. Do not copy micoapi token material into ConfigEntry data.

Invalidation occurs before the ConfigEntry update and reload. It preserves xiaomiio sessions and every session for another account or server. The private reauth candidate is not registered as a replacement global session and is still cleared by flow cleanup. Already-held cloud objects belonging to other ConfigEntries are not modified or reloaded.

This design deliberately retains the current micoapi Store naming and sharing behavior. It does not introduce `auth-<entry_id>-micoapi.json` or migrate legacy Stores.

### Failure behavior

An exception raised directly by an awaited persistence operation leaves the user on the current reauth form with the fixed `save_failed` error and does not report `reauth_successful` or request reload. There is no separate save-retry step or cross-step retry state. A subsequent submission follows that form's normal login path and may contact Xiaomi again.

Home Assistant 2025.6 does not expose delayed ConfigEntry or `Store.async_save()` disk-write failures to this flow: `async_update_entry()` and `Store.async_save()` schedule or perform writes whose storage layer logs supported write errors without re-raising them. This design therefore does not claim to detect or retry those failures.

There is no transactional rollback or persistence inconsistency marker. A matching global-session invalidation is not rolled back if a later ConfigEntry update raises; the refreshed SID Store remains the source for subsequent ownerless session creation. After restart or cancellation, currently persisted ConfigEntry data and existing SID Stores are authoritative.

### Successful reload

After required persistence succeeds:

1. Update ConfigEntry data only when its data actually changed.
2. If changed data invokes the integration's registered update listener, let that listener perform the reload.
3. Only when `entry.update_listeners` is empty (e.g., setup failed before the integration's update listener was registered, or the entry has no listener attached at all) call `hass.config_entries.async_schedule_reload(entry.entry_id)` once. If a listener is present, the listener handles reload on data change and an unchanged-data case schedules no reload.
4. Clear candidate secrets.
5. Return `self.async_abort(reason="reauth_successful")`.

The flow never creates a new ConfigEntry and never changes ConfigEntry options.

## User-facing Copy

The implementation adds fixed translations for:

- `config.step.reauth_password` and its `password` field;
- `config.step.reauth_verify` and its `verify_ticket` field;
- `config.step.reauth_captcha` and its `captcha` field;
- `config.error.invalid_auth`;
- `config.error.need_verify`;
- `config.error.need_captcha`;
- `config.error.cannot_connect`;
- `config.error.save_failed`;
- `config.error.unknown`;
- `config.abort.unsupported_sid`;
- `config.abort.wrong_account`;
- `config.abort.reauth_successful`.

Allowed description placeholders are exactly:

- `tip` on every reauth form, carrying a fixed localized user-facing message;
- `verify_url` only on `reauth_verify`;
- `captcha_image` only on `reauth_captcha`.

`reauth_password` therefore exposes only `tip`; `reauth_verify` exposes only `tip` and `verify_url`; `reauth_captcha` exposes only `tip` and `captcha_image`. The `invalid_auth` translation renders the `tip` value (the fixed localized exception message from the typed auth error) so the user sees the actual rejection reason rather than a generic "credentials rejected" line; the `unknown` translation renders `tip` only when it has been explicitly set. No reauth form references `name`, so Home Assistant cannot fall back to the ConfigEntry title.

No exception text, response body, ConfigEntry title, username, Xiaomi user ID, token, cookie, password, or internal challenge state is used as a translation key or placeholder.

No new persistent-notification system is added. Native Home Assistant reauth is the user-facing recovery mechanism. Existing entry-bound auth warning and micoapi verification notifications are replaced by reauth requests; ownerless flow behavior outside removal of the legacy micoapi verification action remains unchanged.

## Security Requirements

- Reauth candidate login is non-persisting until Xiaomi account identity matches the ConfigEntry.
- Home Assistant Core's temporary reauth `init_data` copy may contain the existing ConfigEntry data for the lifetime of the active flow. The integration does not clear it or mutate the ConfigEntry through it, reads only SID from it, and copies none of its old password or token material into integration-owned flow state, context, results, placeholders, callbacks, logs, or the candidate. The candidate's fixed username and region are read directly from the ConfigEntry; later replacement passwords and challenge data are never added to `init_data`.
- Passwords, service tokens, `ssecurity`, cookies, captcha cookies, normalized captcha URLs, identity sessions, Store payloads, and complete Xiaomi responses are never logged by new or modified reauth paths.
- Existing login log statements reached by reauth must be changed to fixed, secret-free messages when they currently include request data, cookies, account responses, or exception text containing those values.
- The auth-failure callback contains only a SID from `REAUTH_SIDS`.
- `request_xiaomi_api` unsupported-SID and unavailable-cloud errors are fixed and contain no raw SID, cloud exception, credential, or challenge data.
- The verification URL may appear only on the verification form.
- The captcha image may appear only on the captcha form.
- Reauth errors use fixed translation keys and never expose Xiaomi exception text.
- Every reauth form explicitly provides a fixed translated `tip`; no reauth form exposes the ConfigEntry title, username, Xiaomi user ID, or region.
- Every ConfigEntry runtime cloud remains owned by its `HassEntry`; it never enters the global session or account registries. The xiaomiio per-entry runtime configuration may hold only the same-object compatibility alias described above, which never participates in cloud selection or reuse.
- Tests use fake credentials and transports and never contact Xiaomi.

This minimal design does not otherwise refactor HTTP transports or Xiaomi's login protocol.

## Home Assistant Compatibility

The minimum supported Home Assistant version becomes 2025.6.0:

- `hacs.json`: `"homeassistant": "2025.6.0"`;
- the oldest Home Assistant validation matrix entry in `.github/workflows/validate.yml` becomes `2025.6.0`;
- the minimum-version pytest lane uses `pytest-homeassistant-custom-component==0.13.251`, which exact-pins `homeassistant==2025.6.0` and declares `requires_python=">=3.13"`; that lane installs the test dependencies from `requirements_test_min.txt` so the latest-stable and minimum-version tests remain independently auditable.

The CI `pytest` job and the `validate-homeassistant` matrix already use Python 3.13; no Python-bump is required for this raise. No pre-2025.6 compatibility fallback is added.

The implementation uses:

- `ConfigEntry.async_start_reauth()`;
- `async_step_reauth(entry_data)`;
- `_get_reauth_entry()`;
- `ConfigEntryAuthFailed`;
- `hass.config_entries.async_update_entry()`;
- `hass.config_entries.async_schedule_reload()`;
- `self.async_abort(reason="wrong_account")`;
- `self.async_abort(reason="reauth_successful")`.

## Implementation Scope

Expected production changes are limited to:

- `custom_components/xiaomi_miot/core/xiaomi_cloud.py`: define the three-value `CloudSid` and two-value `REAUTH_SIDS`, split side-effect-free login attempt, add the narrow `MiCloudAuthenticationError`, `MiCloudVerificationError`, and `MiCloudStsUnauthorized` classifications, make verification-ticket failure terminal before password-login fallback, make captcha rejection refresh a complete replacement challenge before raising `MiCloudAuthenticationError`, preserve network failures, add the status-aware micoapi token probe and optional `HassEntry` owner, make `from_token()`, `async_login()`, `async_relogin()`, and SID changes owner-aware, pin `verify_ticket()` to `trust='false'`, narrow the step-3 missing-`serviceToken` case to a fixed `MiCloudAuthenticationError`, and make login exceptions and logging secret-free;
- `custom_components/xiaomi_miot/core/hass_entry.py`: three-SID positive/negative cloud map, one entry-local lock that serializes SID-map cache misses and the initial micoapi probe, owner-aware cloud construction and SID retrieval, no auth callback for `i.mi.com`, idempotent per-attempt cleanup, and minimal reauth trigger;
- `custom_components/xiaomi_miot/core/hass_entity.py`: validate `request_xiaomi_api` SID values, preserve the documented `i.mi.com` path through the owner-aware SID map, reject unsupported values before cloud or Store creation, and map a supported SID's `None` lookup result to a fixed unavailable-cloud `HomeAssistantError` without retrying or calling Xiaomi;
- `custom_components/xiaomi_miot/config_flow.py`: restrict reauth to `REAUTH_SIDS`, implement native shared reauth steps and persistence, accept Core's framework-owned ConfigEntry-data copy in `init_data` while reading only SID from it and copying no old password or token material from it into integration-owned state, private candidates that use `hass_entry=None` without entering global registries, the one-time micoapi STS retry inside `reauth_verify`, plus removal of the transient `micoapi_verify` action and legacy ownerless `async_step_micoapi`;
- `custom_components/xiaomi_miot/__init__.py`: validate the `request_xiaomi_api` service SID against `CloudSid`, register early setup cleanup, construct entry-bound clouds without publishing to `accounts[user_id][CONF_XIAOMI_CLOUD]`, preserve the same-object xiaomiio compatibility alias in the existing entry-id runtime configuration, identity-check that alias during cleanup, raise setup-time `ConfigEntryAuthFailed`, defer micoapi bootstrap to the lazy entity-level probe, and preserve listener-aware reload behavior;
- `custom_components/xiaomi_miot/media_player.py`: lazily obtain the entry-bound micoapi result through `HassEntry.async_get_cloud(CloudSid.MICOAPI)` in `async_added_to_hass()`, trigger the dedicated micoapi probe exactly once per `HassEntry` lifecycle, reuse the cached positive or negative result across all media-player entities, and remove the old verification notification;
- bundled translation JSON files required for the new forms, errors, and abort reasons, with legacy micoapi Options Flow action/step keys removed;
- `hacs.json`, `requirements_test_min.txt`, and `.github/workflows/validate.yml` for the minimum version;
- focused authentication tests and minimum-version test constraints.

No coordinator module, transaction module, cache loader, migration layer, or durable state file is created.

## Testing Strategy

Tests use Home Assistant's real ConfigEntry and flow manager while replacing Xiaomi I/O with deterministic fakes.

### Cloud tests

- entry-bound xiaomiio, micoapi, and lazily requested `i.mi.com` clouds retain the correct `HassEntry` owner and use that owner's SID map as the authoritative positive-result cache; successful xiaomiio setup may expose only a same-object entry-id compatibility alias, while micoapi, `i.mi.com`, and a terminal micoapi `None` result receive no alias;
- `i.mi.com` receives no authentication-failure callback, runs no micoapi probe, and cannot request reauth;
- entry-bound construction and SID changes never query, reuse, insert, or replace `hass.data[DOMAIN]["sessions"]`;
- entry-bound `async_login()` and `async_relogin()` preserve Store persistence but never register globally;
- ownerless YAML, Config Flow, Options Flow, and service calls originating from an ownerless cloud retain their session lookup, reuse, and registration behavior;
- a private reauth candidate has `hass_entry=None`, uses only `async_login_attempt()`, and never reads or writes either `sessions` or `accounts`;
- `async_login_attempt()` writes no Store, removes no Store, and registers no global session;
- ownerless `async_login()` delegates to the attempt and preserves its Store removal, successful Store save, global-session registration, and post-persistence `login_times` reset behavior; entry-bound `async_login()` differs only by skipping global registration;
- more than five failed candidate `async_login_attempt()` calls leave a pre-existing SID Store byte-for-byte unchanged;
- known step-2 credential rejection codes `20003`, `70002`, and `70016` without a complete captcha challenge raise `MiCloudAuthenticationError`; `87001` raises `MiCloudAuthenticationError` only after a fresh replacement captcha image and `ick` have been fetched, while `81003`/verification URL and an initial captcha URL produce their respective challenge outcomes;
- a parseable explicit non-zero verification result raises `MiCloudVerificationError`, preserves the verification challenge, and never calls `_login_step2()`; missing verification URL or identity session, no supported method, malformed response, and success without a location raise fixed `MiCloudException`, while connection and timeout types are preserved;
- `MiCloudVerificationError` and verification protocol exception messages contain no ticket, identity session, verification response, cookies, or login location;
- successful verification with a non-empty location continues through steps 1–3, and only a later explicit credential rejection may raise `MiCloudAuthenticationError`;
- step-1 connection and timeout failures retain their network types, and step-1 parse failures use a fixed `MiCloudException`;
- package denial `22009`, unknown step-2 codes, HTTP 5xx, malformed responses, and unexpected no-location or no-`serviceToken` responses use `MiCloudException`, not `MiCloudAuthenticationError`;
- micoapi step-3 with the exact STS host/path, HTTP 401, and no `serviceToken` raises `MiCloudStsUnauthorized`; the same shape under xiaomiio, the same SID with any other status, or the same SID with a `serviceToken` does not raise that type;
- a rejected captcha clears the submitted challenge's old `captchaIck` and image, fetches a fresh image and `ick` using the new or retained private URL, and never raises `MiCloudAuthenticationError` or re-shows the captcha form until that replacement is complete;
- a captcha refresh network, malformed, empty-image, or missing-`ick` failure clears all captcha challenge attributes and uses `MiCloudException` or the original network type without exposing the old image;
- exception classification never depends on exception-message text;
- a supported `async_check_auth()` `MiCloudAuthenticationError`, `MiCloudNeedVerify`, or captcha challenge invokes the SID-only callback after the existing relogin fails;
- a valid stored micoapi token receives one successful status-aware device-list probe and performs no login;
- a micoapi probe HTTP 401 synchronously clears the candidate's in-memory `service_token`, `ssecurity`, `async_session`, `identity_session`, `verify_url`, and `login_data` (the same six fields the `reauth_verify` STS retry clears), performs one relogin, and invokes the SID-only callback only when that relogin ends with `MiCloudAuthenticationError`, `MiCloudNeedVerify`, or captcha challenge state;
- an absent micoapi token performs one login through the same typed outcome path;
- micoapi probe connection, timeout, HTTP 5xx, malformed, unexpected-status, and business failures invoke no callback and expose no response body;
- ordinary background `async_request_api()` code `2`/`3` and HTTP 401 responses retain existing logout/return behavior and invoke no reauth callback;
- connection, timeout, HTTP 5xx, malformed, unknown-code, and business failures invoke no callback;
- modified login logs and exception messages contain no password, token, cookie, challenge session, Store payload, location query data, or complete response canary.

### Config Flow tests

For both reauth SIDs:

- Core-started and runtime-started reauth resolve the correct existing ConfigEntry and SID;
- the active flow retains Core's temporary `init_data` copy of existing ConfigEntry data unchanged until removal, but the integration reads only SID from it; fixed username, region, and expected `user_id` are read from `_get_reauth_entry()`, no old password or token material is copied from `init_data` into integration-owned flow context, form results, placeholders, callbacks, logs, or the private candidate, and later replacement-password or challenge submissions do not modify `init_data`;
- `CloudSid.I_MI_COM` or a value outside `CloudSid` aborts reauth with `unsupported_sid`, selects no reauth Store, and exposes no raw SID placeholder;
- `reauth_password` exposes only an explicitly supplied fixed translated `name`; region is absent from both the schema and description placeholders;
- `reauth_verify` exposes exactly `name` and `verify_url`, and `reauth_captcha` exposes exactly `name` and `captcha_image`;
- ConfigEntry title and `user_id` secret canaries never appear in any form result, proving that Home Assistant does not inject the entry title over the explicit safe `name`;
- no `entry_title` or `cloud_name` placeholder is emitted;
- password success reaches persistence;
- `MiCloudAuthenticationError` maps to `invalid_auth`, while a broad `MiCloudAccessDenied`, protocol failure, or unknown error maps to `unknown` and cannot start another reauth;
- `MiCloudVerificationError` on `reauth_verify` remains on that form with `need_verify` and preserves the challenge; a post-verification `MiCloudAuthenticationError` clears the candidate and returns to `reauth_password` with `invalid_auth`; verification protocol failures map to `unknown` and network failures map to `cannot_connect`;
- `reauth_captcha` keeps an empty submission on the current form without consuming the challenge; a non-empty rejected captcha shows `need_captcha` only with a complete replacement image and `ick`; refresh network/protocol failures clear the candidate and return to `reauth_password` with `cannot_connect`/`unknown`; a rejected captcha never re-displays the old image;
- connection and timeout exceptions map to `cannot_connect` without exposing exception text;
- password to verification to success;
- password to captcha to success;
- verification and captcha can transition to each other;
- micoapi `reauth_verify` recognizes only `MiCloudStsUnauthorized` as the retry trigger; a single retry that follows the typed outcome mapping; a second `MiCloudStsUnauthorized` from that retry maps to `unknown` and never triggers another retry; the retry clears the candidate's in-memory token, ssecurity, HTTP session, identity session, verification URL, and login data without touching the persisted SID Store or global session map; the captcha step never retries;
- wrong account writes nothing and aborts with `wrong_account`;
- fixed errors and exact placeholder allowlists expose no secret canary;
- successful completion, wrong-account abort, ordinary abort, frontend cancellation, and manager removal through the real flow manager each invoke the synchronous `async_remove()` hook and clear all flow-owned candidate credentials and challenge data;
- an exception raised directly by an awaited persistence operation leaves the current form with `save_failed` and does not reload or report success;
- no `reauth_save` step exists, and a subsequent submission follows the current form's normal login path;

Persistence assertions cover:

- xiaomiio and micoapi each update their existing SID Store and then invalidate matching global sessions by validated `user_id`, server, and SID before ConfigEntry update or reload;
- session invalidation synchronously iterates a session-map snapshot without `await` and compares cloud-object fields rather than parsing session keys;
- xiaomiio updates only allowed ConfigEntry data fields and never changes options; micoapi updates only the common password when changed and does not place its token in ConfigEntry data;
- xiaomiio invalidation preserves unrelated account, server, and micoapi sessions; micoapi invalidation preserves unrelated account, server, and xiaomiio sessions;
- neither SID registers the private candidate as a replacement global session or modifies already-held cloud objects belonging to other ConfigEntries;
- entering the same password still prevents the current entry reload and later ownerless flow creation from reusing stale token material for the refreshed SID;
- if a ConfigEntry update raises after Store save and session invalidation, the invalidation remains and no rollback is attempted;
- changed ConfigEntry data reloads through the existing listener;
- unchanged Store-only success schedules one reload;
- successful flow aborts with `reauth_successful` and never creates an entry.

### Trigger, service, and setup tests

- `request_xiaomi_api` recognizes xiaomiio, micoapi, and `i.mi.com`; when the selected cloud is available, an entry-bound `i.mi.com` request creates or reuses the current owner's lazy SID-map cloud and completes through the existing API request path;
- an unsupported service SID raises a fixed `HomeAssistantError` before constructing a cloud, loading or saving a Store, or changing either global registry, and the error contains no raw SID;
- a supported micoapi SID whose entry-bound lookup returns cached `None` raises only the fixed unavailable-cloud `HomeAssistantError`; it preserves the negative result and performs no reconstruction, probe, login, Xiaomi API request, Store access, callback, or reauth request, and neither its error nor service response contains the SID or challenge data;
- an `i.mi.com` authentication failure invokes no auth-failure callback and cannot start reauth;
- a loaded entry's supported `async_check_auth()` failure requests native reauth with the correct SID;
- the lazy entry-bound micoapi probe runs only when the first `MiotMediaPlayerEntity` whose device spec exposes an `intelligent_speaker` service is added; when multiple qualifying media-player entities are added concurrently, the entry-local lock permits exactly one construction and probe while every other caller receives the same completed cloud or terminal `None` result;
- a successful probe positively caches and reuses the entry-bound cloud; a typed authentication/challenge failure clears and releases the rejected candidate after requesting reauth, while a transient failure invokes no callback; both failure classes negatively cache `None`, perform no additional probe or login during the same `HassEntry` lifecycle, and become retryable only after reload creates a fresh `HassEntry`;
- a probe 401 or absent token followed by a typed micoapi authentication or verification failure while the ConfigEntry is `SETUP_IN_PROGRESS` requests micoapi reauth without failing setup or creating the old notification;
- a `SETUP_IN_PROGRESS` xiaomiio callback does not request runtime reauth because xiaomiio setup uses `ConfigEntryAuthFailed`;
- an ordinary background API code `2`/`3` or HTTP 401 does not directly request reauth, and a later manual ConfigEntry reload recreates the entry-bound media-player entities so the lazy micoapi probe can rerun;
- every state other than `LOADED` and the explicit `SETUP_IN_PROGRESS` micoapi case rejects the callback;
- Home Assistant Core prevents duplicate entry-bound reauth flows;
- setup-time explicit xiaomiio authentication failure raises `ConfigEntryAuthFailed` with a fixed secret-free message, defaults to xiaomiio reauth, and lets Core invoke the registered cleanup before starting the flow;
- setup does not raise `ConfigEntryAuthFailed` for `MiCloudVerificationError`, `MiCloudStsUnauthorized`, another broad `MiCloudAccessDenied`, `MiCloudException`, connection errors, timeouts, HTTP 5xx, malformed responses, unknown Xiaomi error codes, package or business errors, or ordinary API errors; those use the existing setup failure path;
- setup xiaomiio does not invoke the SID-only authentication callback, so reauth is started only by Core's `ConfigEntryAuthFailed` handling and no runtime reauth is requested while the entry is `SETUP_IN_PROGRESS`;
- setup-failure cleanup removes a per-entry runtime configuration only when its xiaomiio alias is the same object owned by that setup attempt, clears the attempt's SID results, and removes only the matching `HassEntry.ALL` instance; normal unload plus lifecycle cleanup removes the alias and SID results idempotently, and an old cleanup callback cannot remove a newer `HassEntry` instance or alias;
- setup after successful reauth creates a new `HassEntry` and owner-aware cloud from updated ConfigEntry data rather than reusing the rejected instance or a global session;
- successful xiaomiio setup publishes `hass.data[DOMAIN][entry_id][CONF_XIAOMI_CLOUD]` as the exact same object as `HassEntry.clouds[CloudSid.XIAOMIIO]`, so `entry_config()`, `MiotCloud.all_clouds()`, the existing component services, and system health continue to discover it;
- the entry-id compatibility alias is never consulted by `MiotCloud.from_token()`, `HassEntry.async_get_cloud()`, SID changes, authentication callbacks, login, or reauth; micoapi, `i.mi.com`, and negative SID results create no compatibility alias;
- ConfigEntry-owned xiaomiio, micoapi, and lazy `i.mi.com` clouds are never published through `hass.data[DOMAIN]["accounts"]`, including when another ConfigEntry uses the same Xiaomi account;
- two ConfigEntries for the same account and server receive distinct entry-bound cloud objects and distinct entry-id xiaomiio aliases, and authentication or SID changes on one do not replace or mutate the other's cloud or alias;
- legacy YAML setup continues to publish its ownerless xiaomiio cloud through `accounts[user_id][CONF_XIAOMI_CLOUD]` and otherwise retains its existing behavior;
- network setup failures do not become authentication reauth;
- the Options Flow schema has no `micoapi_verify` action, the legacy ownerless `async_step_micoapi` is absent, and their bundled translation keys are removed;
- starting reauth does not unload already-running local entities; if it completes during setup, the scheduled reload waits for the ConfigEntry setup lock.

No concurrency stress matrix, fake monotonic clock, watchdog test, device-inventory cache test, rollback test, compensation test, or restart-journal test is required.

## Acceptance Criteria

1. Setup-time xiaomiio authentication failure, a lazy micoapi probe 401 or absent token followed by a typed authentication or verification failure during `SETUP_IN_PROGRESS`, and supported runtime authentication failure for a loaded ConfigEntry can each start one native reauth flow after the existing login or relogin attempt fails.
2. Setup-time explicit xiaomiio authentication failure raises `ConfigEntryAuthFailed` with a fixed secret-free message; Core runs the registered per-attempt cleanup before starting reauth, and successful reauth setup creates a new `HassEntry` and cloud from updated ConfigEntry data. Setup-time non-authentication failures do not raise `ConfigEntryAuthFailed`, and setup does not invoke the SID-only authentication callback.
3. Both reauth SIDs complete password, verification-ticket, and captcha paths through the same reauth step implementations. `CloudSid.I_MI_COM` and values outside `CloudSid` abort with `unsupported_sid` without selecting a reauth Store or exposing the raw value.
4. Candidate `async_login_attempt()` performs no Store save, Store removal, global-session registration, or `accounts` publication before the authenticated Xiaomi `user_id` matches the existing ConfigEntry.
5. Wrong-account authentication writes nothing and aborts with `wrong_account`.
6. Each reauth SID refreshes its existing auth Store and then invalidates only matching global sessions by validated account, server, and SID before ConfigEntry update or reload. xiaomiio refreshes its allowed ConfigEntry credentials; micoapi copies no token material into ConfigEntry data. Neither changes unrelated configuration, ConfigEntry options, unrelated sessions, or other ConfigEntries' already-held clouds, and neither registers the private candidate globally.
7. An exception raised directly by an awaited persistence operation leaves the current form with `save_failed`, does not request reload or report success, and creates no separate save-retry step or state.
8. Successful reauth aborts the existing flow with `reauth_successful` and reloads the ConfigEntry once through the existing listener or the unchanged-data fallback schedule.
9. Only `MiCloudAuthenticationError`, `MiCloudNeedVerify`, and explicit captcha challenge state qualify as login-side authentication outcomes, both for setup `ConfigEntryAuthFailed` and runtime reauth. `MiCloudVerificationError` is confined to an existing verification form and never starts reauth; failed verification never falls through to `_login_step2()` with empty auth. `MiCloudStsUnauthorized` is not an authentication outcome and never starts reauth; it permits one STS-specific retry inside `reauth_verify`. A micoapi probe 401 only permits one relogin attempt and does not itself start reauth. Network, server, malformed-response, package/business, unknown-code, broad `MiCloudAccessDenied`, ordinary API failures, and ordinary background `async_request_api()` code `2`/`3` or HTTP 401 responses do not directly start reauth in this phase. No manual micoapi verification option remains; a manual ConfigEntry reload recreates the entry-bound media-player entities so the lazy micoapi probe reruns.
10. Home Assistant Core may retain its temporary `init_data` copy of the existing ConfigEntry data until the active flow is removed; the integration reads only SID from that copy, does not mutate it, and does not add later password or challenge submissions to it. Subject to that explicit framework-owned copy, new and modified login and reauth paths expose no password, token, cookie, internal challenge state, Store payload, location query data, exception text, complete Xiaomi response, ConfigEntry title, username, or Xiaomi user ID in integration-owned flow context, results, placeholders, callbacks, logs, exception messages, or user-visible flow data. Every reauth form explicitly supplies a fixed translated `name`; region is absent from reauth schemas and description placeholders.
11. Requesting and displaying reauth does not unload already-running local entities; optional micoapi failure does not fail setup. The entry-local cloud lock makes concurrent qualifying media-player additions share exactly one completed micoapi construction and probe result per `HassEntry`: success caches the usable cloud, authentication/challenge or transient failure caches `None`, and only a fresh `HassEntry` after reload may probe again. A successful reauth reload is serialized by the ConfigEntry setup lock before it may recreate entities.
12. Home Assistant 2025.6.0 is the enforced minimum in metadata, validation CI, the minimum-version pytest lane, and the assertion in focused tests.
13. The implementation contains no coordinator, episode state, cooldown, watchdog, cache-only setup, Store migration, transaction compensation, or durable recovery journal.
14. Every ConfigEntry runtime cloud is owner-aware: its `HassEntry` SID map is the authoritative owner and construction cache, it never reads or writes the global session registry, and it is not published through `accounts[user_id][CONF_XIAOMI_CLOUD]`. Successful xiaomiio setup preserves only a same-object compatibility alias in the existing entry-id runtime configuration so `entry_config()`, `MiotCloud.all_clouds()`, component services, and system health retain their current discovery path; no other SID or negative result receives an alias, and no construction, login, SID-change, authentication, or reauth path consults it for reuse. Two same-account ConfigEntries retain distinct clouds and entry-id aliases. Ownerless YAML and Config/Options Flow session behavior remains unchanged; service calls originating from ownerless clouds retain that behavior, while private reauth candidates use `hass_entry=None` without entering either global registry.
15. `CloudSid` contains exactly xiaomiio, micoapi, and `i.mi.com`, while `REAUTH_SIDS` contains only xiaomiio and micoapi. `request_xiaomi_api` recognizes all three values, lazily owns an available `i.mi.com` cloud through the current `HassEntry`, and rejects every other SID before cloud or Store selection. A supported SID whose lookup returns `None` produces only the fixed unavailable-cloud `HomeAssistantError` and preserves the negative cache without reconstruction, probe, login, API, Store, callback, or reauth side effects. `i.mi.com` has no auth-failure callback or micoapi probe and cannot start reauth.
16. A non-empty captcha submission consumes the old challenge and may keep the user on `reauth_captcha` only after a complete replacement image and `ick` have been fetched. Refresh failures clear the candidate and return to `reauth_password`; no stale captcha image or cookie is reused or exposed.
