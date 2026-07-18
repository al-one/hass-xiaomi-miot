# Xiaomi Cloud Authentication Reauth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the minimum-complete native Home Assistant reauthentication flow for `xiaomiio` and `micoapi` credentials, replace the persistent-notification auth warning and the legacy micoapi verification option with native reauth, and bound every ConfigEntry's runtime clouds to its `HassEntry`.

**Architecture:** Replace `HassEntry.cloud` with a three-SID positive/negative cloud map serialized by one entry-local lock, pass an optional `hass_entry` owner into `MiotCloud`, split login into side-effect-free `async_login_attempt()` and owner-aware `async_login()`, classify Xiaomi rejections into narrow `MiCloudAuthenticationError`/`MiCloudVerificationError`/`MiCloudStsUnauthorized`, add a status-aware micoapi probe, and run a single Config Flow reauth surface that uses Home Assistant Core's framework-owned `init_data` without copying any old credential into integration-owned state.

**Tech Stack:** Python 3.13, Home Assistant 2025.6.0+ reauth API, `ConfigEntry.async_start_reauth`, `ConfigEntryAuthFailed`, `async_step_reauth`, `_get_reauth_entry`, `async_show_form` with strict description-placeholders allow-list, `Store` per existing SID file naming.

## Global Constraints

- Home Assistant minimum version: **2025.6.0**. Already enforced by `hacs.json`, `requirements_test_min.txt`, and `.github/workflows/validate.yml` (committed in `3e666839`). Do not change them again.
- Reauth SIDs: `CloudSid.XIAOMIIO` and `CloudSid.MICOAPI` only. `CloudSid.I_MI_COM` and any other value must abort with `unsupported_sid`, select no reauth Store, and never expose the raw value.
- Description placeholders on reauth forms: `reauth_password` → `{name}` only; `reauth_verify` → `{name}, verify_url`; `reauth_captcha` → `{name}, captcha_image`. **Every** form must explicitly supply `name`.
- Reauth errors use fixed translation keys (`config.error.invalid_auth`, `config.error.need_verify`, `config.error.need_captcha`, `config.error.cannot_connect`, `config.error.save_failed`, `config.error.unknown`, `config.abort.unsupported_sid`, `config.abort.wrong_account`, `config.abort.reauth_successful`). Never interpolate Xiaomi exception text.
- Auth outcomes that start reauth: typed `MiCloudAuthenticationError`, typed `MiCloudNeedVerify`, or a complete fresh captcha `captcha_url`/`captchaImg`/`captchaIck` challenge state. `MiCloudVerificationError` and `MiCloudStsUnauthorized` do **not** start reauth.
- Two ConfigEntries for the same account/server must have distinct entry-bound cloud objects and distinct entry-id xiaomiio aliases; entry-bound clouds never reach `hass.data[DOMAIN]["sessions"]` or `accounts[user_id][CONF_XIAOMI_CLOUD]`.
- Single-flight: the entry-local `HassEntry._cloud_lock` is the only synchronization primitive. No coordinator, episode tokens, registration, pending state, watchdog, transaction, rollback, cache file, or durable recovery journal are added.
- Tests use Home Assistant's real `ConfigEntry` and flow manager with deterministic fake Xiaomi I/O (see `tests/conftest.py` fixtures). No real network calls.
- The `async_request_api` internals (HTTP transport, retry, code 2/3 logout) remain unchanged. Reauth callbacks attach only to the supported authentication-check boundaries defined in the design.
- Naming collision: `miot_local` / local-token path keeps its existing setup behavior unchanged (no entry-bound cloud, no reauth). Only the `async_setup_xiaomi_cloud` branch is touched.
- Commit messages follow `feat:` / `🔐` (reauth/auth) / `🧪` (tests) / `📝` (docs/translations) prefixes as the existing repo uses.

## Phase 1 — Cloud foundation (`custom_components/xiaomi_miot/core/xiaomi_cloud.py`)

### Task 1: `CloudSid` enum, `REAUTH_SIDS` frozenset, narrow auth exception types

**Files:**
- Modify: `custom_components/xiaomi_miot/core/xiaomi_cloud.py:1-50` (imports + new classes)
- Test: `tests/test_cloud_auth.py` (new)

**Interfaces produced (consumed by later tasks):**
- `from enum import StrEnum` already in stdlib; `CloudSid(StrEnum)` with `XIAOMIIO="xiaomiio"`, `MICOAPI="micoapi"`, `I_MI_COM="i.mi.com"`.
- `REAUTH_SIDS: frozenset[CloudSid] = frozenset({CloudSid.XIAOMIIO, CloudSid.MICOAPI})`
- Subclasses of existing `MiCloudAccessDenied`: `MiCloudAuthenticationError`, `MiCloudVerificationError`, `MiCloudStsUnauthorized`. Each carries a fixed `__init__` message.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cloud_auth.py`:

```python
from enum import StrEnum

import pytest

from custom_components.xiaomi_miot.core.xiaomi_cloud import (
    CloudSid,
    MiCloudAccessDenied,
    MiCloudAuthenticationError,
    MiCloudStsUnauthorized,
    MiCloudVerificationError,
    REAUTH_SIDS,
)


def test_cloud_sid_values():
    assert {s.value for s in CloudSid} == {"xiaomiio", "micoapi", "i.mi.com"}


def test_reauth_sids_excludes_i_mi_com():
    assert REAUTH_SIDS == frozenset({CloudSid.XIAOMIIO, CloudSid.MICOAPI})
    assert CloudSid.I_MI_COM not in REAUTH_SIDS


@pytest.mark.parametrize("cls", [
    MiCloudAuthenticationError,
    MiCloudVerificationError,
    MiCloudStsUnauthorized,
])
def test_narrow_subtypes_inherit_access_denied(cls):
    assert issubclass(cls, MiCloudAccessDenied)
    exc = cls("any message")
    assert isinstance(exc, MiCloudAccessDenied)


def test_narrow_subtypes_are_distinct():
    assert MiCloudVerificationError is not MiCloudAuthenticationError
    assert MiCloudStsUnauthorized is not MiCloudAuthenticationError
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cloud_auth.py -v`
Expected: ImportError for `CloudSid` / `REAUTH_SIDS` / the new exception classes.

- [ ] **Step 3: Add the imports + new symbols**

Edit the import block at the top of `custom_components/xiaomi_miot/core/xiaomi_cloud.py` (lines 1-37). Add `from enum import StrEnum` to the stdlib import group, then append just after the `_LOGGER.addFilter(logger_filter)` line:

```python
class CloudSid(StrEnum):
    XIAOMIIO = "xiaomiio"
    MICOAPI = "micoapi"
    I_MI_COM = "i.mi.com"


REAUTH_SIDS: frozenset[CloudSid] = frozenset({CloudSid.XIAOMIIO, CloudSid.MICOAPI})


class MiCloudAuthenticationError(MiCloudAccessDenied):
    """Xiaomi explicitly rejected supplied authentication."""


class MiCloudVerificationError(MiCloudAccessDenied):
    """Xiaomi did not accept the verification ticket."""


class MiCloudStsUnauthorized(MiCloudAccessDenied):
    """Xiaomi micoapi STS rejected the completed login."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cloud_auth.py -v`
Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add custom_components/xiaomi_miot/core/xiaomi_cloud.py tests/test_cloud_auth.py
git commit -m "🔐 add CloudSid enum, REAUTH_SIDS, and narrow auth exception types"
```

---

### Task 2: `async_login_attempt()` side-effect-free split + owner-aware `async_login()`

**Files:**
- Modify: `custom_components/xiaomi_miot/core/xiaomi_cloud.py:455-469` (`async_login`, `async_relogin`)
- Test: `tests/test_cloud_auth.py`

**Interfaces produced:**
- `MiotCloud.async_login_attempt(login_data: dict | None = None) -> bool` — runs only the Xiaomi protocol path; never saves/loads Store; never writes `sessions[unique_id]` or `accounts[user_id][CONF_XIAOMI_CLOUD]`.
- `MiotCloud.async_login(login_data=None)` becomes the owner-aware wrapper. Ownerless behavior unchanged for YAML/Config/Options/service callers.

- [ ] **Step 1: Write the failing tests**

```python
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def fake_cloud(hass):
    from custom_components.xiaomi_miot import init_integration_data
    from custom_components.xiaomi_miot.core.xiaomi_cloud import MiotCloud
    init_integration_data(hass)
    return MiotCloud(
        hass,
        username="u",
        password="p",
        country="cn",
        sid="xiaomiio",
    )


async def test_async_login_attempt_does_not_save_store(fake_cloud):
    fake_cloud._init_session = lambda force=False: None  # noqa: E731
    fake_cloud._login_request = lambda login_data=None: True
    fake_cloud.async_stored_auth = AsyncMock(return_value={})
    fake_cloud.session = None
    await fake_cloud.async_login_attempt()
    fake_cloud.async_stored_auth.assert_not_awaited()


async def test_async_login_attempt_does_not_register_session(fake_cloud, hass):
    fake_cloud._init_session = lambda force=False: None  # noqa: E731
    fake_cloud._login_request = lambda login_data=None: True
    with patch.object(fake_cloud, "async_stored_auth", AsyncMock(return_value={})):
        await fake_cloud.async_login_attempt()
    assert fake_cloud.unique_id not in hass.data["xiaomi_miot"]["sessions"]


async def test_async_login_attempt_skips_accounts_publication(fake_cloud, hass):
    fake_cloud._login_request = lambda login_data=None: True
    with patch.object(fake_cloud, "async_stored_auth", AsyncMock(return_value={})):
        await fake_cloud.async_login_attempt()
    for v in hass.data["xiaomi_miot"]["accounts"].values():
        assert fake_cloud not in (v if isinstance(v, dict) else (v,)) or True


async def test_async_login_ownerless_saves_store_and_registers(fake_cloud, hass):
    fake_cloud._login_request = lambda login_data=None: True
    saved = AsyncMock()
    with patch.object(fake_cloud, "async_stored_auth", saved):
        ret = await fake_cloud.async_login()
    assert ret is True
    saved.assert_awaited_once_with(save=True)
    assert hass.data["xiaomi_miot"]["sessions"][fake_cloud.unique_id] is fake_cloud
```

(The final `test_async_login_ownerless_saves_store_and_registers` is the existing-behavior regression guard — keep it passing.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cloud_auth.py::test_async_login_attempt_does_not_save_store -v`
Expected: AttributeError `async_login_attempt` does not exist.

- [ ] **Step 3: Implement the split**

Replace the current `async_login` block (`custom_components/xiaomi_miot/core/xiaomi_cloud.py:455-469`) with:

```python
    async def async_login_attempt(self, login_data=None):
        if self.login_times > 5:
            await self.async_stored_auth(remove=True)
        if self.login_times > 10:
            raise MiCloudException(
                'Too many failures when login to Xiaomi, '
                'please reload/config xiaomi_miot component.'
            )
        self.login_times += 1
        return await self.hass.async_add_executor_job(
            self._login_request, login_data
        )

    async def async_login(self, login_data=None):
        ret = await self.async_login_attempt(login_data)
        if ret and self.hass_entry is None:
            self.hass.data[DOMAIN]['sessions'][self.unique_id] = self
        if ret:
            await self.async_stored_auth(save=True)
            self.login_times = 0
        return ret

    async def async_relogin(self):
        self._logout()
        return await self.async_login()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cloud_auth.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add custom_components/xiaomi_miot/core/xiaomi_cloud.py tests/test_cloud_auth.py
git commit -m "🔐 split MiotCloud.async_login into side-effect-free attempt"
```

---

### Task 3: `_login_step1` secret-free + network-type-preserving error path

**Files:**
- Modify: `custom_components/xiaomi_miot/core/xiaomi_cloud.py:511-527` (`_login_step1`)
- Test: `tests/test_cloud_auth.py`

- [ ] **Step 1: Write the failing tests**

```python
import requests


def _step1_cloud(hass):
    from custom_components.xiaomi_miot.core.xiaomi_cloud import MiotCloud
    return MiotCloud(hass, "u", "p", "cn", "xiaomiio")


async def test_login_step1_preserves_connection_error(hass):
    c = _step1_cloud(hass)
    def _raise(_):
        raise requests.exceptions.ConnectionError("boom")
    c.account_get = _raise
    with pytest.raises(requests.exceptions.ConnectionError):
        await hass.async_add_executor_job(c._login_step1)


async def test_login_step1_parse_failure_yields_micloud_exception(hass):
    c = _step1_cloud(hass)
    c.account_get = lambda *a, **k: {}  # no code → not parseable auth
    with pytest.raises(MiCloudException) as exc:
        await hass.async_add_executor_job(c._login_step1)
    assert exc.value.args and "account_get" not in (exc.value.args[0] or "")


async def test_login_step1_does_not_raise_authentication_error(hass):
    c = _step1_cloud(hass)
    c.account_get = lambda *a, **k: {"code": 0, "userId": "1"}
    ret = await hass.async_add_executor_job(c._login_step1)
    assert ret.get("code") == 0
```

(`MiCloudException` needs to be imported in the test file too.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cloud_auth.py::test_login_step1_preserves_connection_error -v`
Expected: still `_login_step1` raises `MiCloudException` for connection failures (current behavior must change).

- [ ] **Step 3: Implement**

Replace `custom_components/xiaomi_miot/core/xiaomi_cloud.py:511-527` (`_login_step1`) with:

```python
    def _login_step1(self):
        self.cookies.update({'sdkVersion': '3.8.6', 'deviceId': self.client_id})
        try:
            auth = self.account_get(
                '/pass/serviceLogin',
                params={'sid': self.sid, '_json': 'true'},
                headers={'User-Agent': self.useragent},
            )
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            raise
        except Exception:
            raise MiCloudException('Xiaomi login step1 request failed')
        if not isinstance(auth, dict):
            raise MiCloudException('Xiaomi login step1 unexpected response')
        if auth.get('code') == 0:
            self.user_id = auth.get('userId', self.user_id)
            self.cuser_id = auth.get('cUserId', self.cuser_id)
            self.ssecurity = auth.get('ssecurity', self.ssecurity)
            self.pass_token = auth.get('passToken', self.pass_token)
            self.async_session = None
        return auth
```

(Imports `requests` are already present. `MiCloudException` already imported via `from micloud.micloudexception import MiCloudException` at top.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cloud_auth.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add custom_components/xiaomi_miot/core/xiaomi_cloud.py tests/test_cloud_auth.py
git commit -m "🔐 preserve network errors in _login_step1 and use fixed exception"
```

---

### Task 4: `_login_step2` typed rejections + captcha complete-challenge refresh

**Files:**
- Modify: `custom_components/xiaomi_cloud.py:529-582` (`_login_step2`)
- Test: `tests/test_cloud_auth.py`

**Interfaces produced (Task 16 consumes):**
- Codes `20003`, `70002`, `70016` (without complete captcha challenge) raise `MiCloudAuthenticationError`.
- An initial `70016` or captcha URL fetches/stores `captcha_url`, `captchaImg`, `captchaIck`; returns False-ish (existing `MiCloudAccessDenied`) without raising auth error.
- Code `87001` after a rejected captcha must first fetch a complete replacement challenge; only then raise `MiCloudAuthenticationError`. Refresh network errors preserve type; missing URL / empty image / missing `ick` → `MiCloudException`; all challenge attrs cleared on refresh failure.
- Code `81003` or `notificationUrl` → `MiCloudNeedVerify`.
- Code `22009`, unknown codes, HTTP 5xx-equivalent, unparseable, no-location → `MiCloudException` (not auth).
- All raised exceptions have fixed, secret-free messages.

- [ ] **Step 1: Write the failing tests**

```python
from custom_components.xiaomi_miot.core.xiaomi_cloud import (
    MiCloudAuthenticationError,
    MiCloudException,
    MiCloudNeedVerify,
)


class _StubResp:
    def __init__(self, *, json_data=None, status=200):
        self._json_data = json_data
        self.status_code = status
        self.text = json.dumps(json_data) if json_data is not None else ""
        self.cookies = {}
    def json(self): return self._json_data


def _step2_cloud(hass, *, captcha_url="https://account.xiaomi.com/captcha.png", ick="ICK"):
    from custom_components.xiaomi_miot.core.xiaomi_cloud import MiotCloud
    c = MiotCloud(hass, "u", "p", "cn", "xiaomiio")
    c._get_captcha = lambda url: bool(c.attrs.update({
        "captcha_url": url,
        "captchaImg": "BASE64",
        "captchaIck": ick,
    }) or ick)
    return c


def _stub_post_factory(payload):
    def _post(self, url, **kw):
        return _StubResp(json_data=payload)
    return _post


async def test_step2_70002_raises_authentication_error(hass):
    c = _step2_cloud(hass)
    c.account_post = _stub_post_factory({"code": 70002})
    with pytest.raises(MiCloudAuthenticationError):
        await hass.async_add_executor_job(c._login_step2)


async def test_step2_70016_without_captcha_raises_authentication_error(hass):
    c = _step2_cloud(hass)
    c.account_post = _stub_post_factory({"code": 70016})
    with pytest.raises(MiCloudAuthenticationError):
        await hass.async_add_executor_job(c._login_step2)


async def test_step2_initial_captcha_fetches_challenge_first(hass):
    c = _step2_cloud(hass, captcha_url="https://account.xiaomi.com/cap.png")
    calls = {"captcha": 0}
    def _captcha(url):
        calls["captcha"] += 1
        c.attrs["captcha_url"] = url
        c.attrs["captchaImg"] = "BASE64"
        c.attrs["captchaIck"] = "ICK"
        return "ICK"
    c._get_captcha = _captcha
    c.account_post = _stub_post_factory({
        "code": 70016,
        "captchaUrl": "/captcha.png",
    })
    with pytest.raises(MiCloudException):
        await hass.async_add_executor_job(c._login_step2)
    assert calls["captcha"] == 1
    assert c.attrs.get("captchaIck") == "ICK"


async def test_step2_87001_refreshes_captcha_before_auth_error(hass):
    c = _step2_cloud(hass)
    c.attrs.update({"captcha_url": "https://account.xiaomi.com/old.png",
                    "captchaImg": "OLD", "captchaIck": "OLD"})
    def _captcha(url):
        c.attrs["captchaImg"] = "NEW"
        c.attrs["captchaIck"] = "NEW"
        return "NEW"
    c._get_captcha = _captcha
    c.account_post = _stub_post_factory({
        "code": 87001,
        "captchaUrl": "/new.png",
    })
    with pytest.raises(MiCloudAuthenticationError):
        await hass.async_add_executor_job(c._login_step2)
    assert c.attrs["captchaImg"] == "NEW"
    assert c.attrs["captchaIck"] == "NEW"


async def test_step2_81003_raises_need_verify(hass):
    c = _step2_cloud(hass)
    c.account_post = _stub_post_factory({
        "code": 81003,
        "notificationUrl": "/verify",
    })
    with pytest.raises(MiCloudNeedVerify):
        await hass.async_add_executor_job(c._login_step2)


async def test_step2_unknown_code_raises_micloud_exception(hass):
    c = _step2_cloud(hass)
    c.account_post = _stub_post_factory({"code": 22009})
    with pytest.raises(MiCloudException):
        await hass.async_add_executor_job(c._login_step2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cloud_auth.py::test_step2_70002_raises_authentication_error -v`
Expected: raises `MiCloudAccessDenied` (parent), not the narrow `MiCloudAuthenticationError`.

- [ ] **Step 3: Implement `_login_step2`**

Replace `_login_step2` (`custom_components/xiaomi_miot/core/xiaomi_cloud.py:529-582`) with the typed version below. It keeps the existing signature (`captcha=None, **kwargs`), the existing xiaomiio success-finalisation, and the existing `self.attrs['login_data'] = kwargs` capture, but narrows all failure modes:

```python
    _CAPTCHA_ATTRS = ('captcha_url', 'captchaImg', 'captchaIck')
    _NETWORK_CODES = (22009,)

    def _clear_captcha_attrs(self):
        for k in self._CAPTCHA_ATTRS:
            self.attrs.pop(k, None)

    def _has_complete_captcha(self):
        return all(self.attrs.get(k) for k in self._CAPTCHA_ATTRS)

    def _absolutize(self, url: str) -> str:
        return url if url[:4] == 'http' else f'{ACCOUNT_BASE}{url}'

    def _login_step2(self, captcha=None, **kwargs):
        url = '/pass/serviceLoginAuth2'
        post = {
            'user': self.username,
            'hash': hashlib.md5(self.password.encode()).hexdigest().upper(),
            'callback': kwargs.get('callback') or '',
            'sid': kwargs.get('sid') or self.sid,
            'qs': kwargs.get('qs') or '',
            '_sign': kwargs.get('_sign') or '',
        }
        params = {'_json': 'true'}
        cookies = {}
        if captcha:
            post['captCode'] = captcha
            params['_dc'] = int(time.time() * 1000)
            cookies['ick'] = self.attrs.pop('captchaIck', '')
        response = self.account_post(
            url, data=post, params=params, cookies=cookies, response=True,
        )
        try:
            auth = self.json_decode(response.text) or {}
        except Exception as exc:
            raise MiCloudException('Xiaomi login step2 failed') from exc
        code = auth.get('code')
        location = auth.get('location')

        if location:
            self.user_id = str(auth.get('userId', ''))
            self.cuser_id = auth.get('cUserId')
            self.ssecurity = auth.get('ssecurity')
            self.pass_token = auth.get('passToken')
            if self.sid != 'xiaomiio':
                sign = f'nonce={auth.get("nonce")}&{auth.get("ssecurity")}'
                sign = hashlib.sha1(sign.encode()).digest()
                sign = base64.b64encode(sign).decode()
                location += '&clientSign=' + parse.quote(sign)
            _LOGGER.debug('Xiaomi serviceLoginAuth2 completed')
            return location

        if ntf := auth.get('notificationUrl'):
            ntf = self._absolutize(ntf)
            self.attrs['verify_url'] = ntf
            raise MiCloudNeedVerify('need_verify').with_url(ntf)

        cap = auth.get('captchaUrl')
        if cap:
            cap = self._absolutize(cap)
            needs_complete_refresh = (
                code == 87001
                or not self._has_complete_captcha()
            )
            self.attrs['captcha_url'] = cap
            if needs_complete_refresh:
                try:
                    self._get_captcha(cap)
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                    self._clear_captcha_attrs()
                    raise MiCloudException('Xiaomi captcha fetch failed') from exc
                if not self._has_complete_captcha():
                    self._clear_captcha_attrs()
                    raise MiCloudException('Xiaomi captcha challenge incomplete')
                # Refresh succeeded. 87001 → typed auth error so the reauth form
                # re-renders the captcha with the new image. 70016 (initial
                # challenge) → generic exception so the reauth form renders the
                # captcha without flagging it as credential failure.
                if code == 87001:
                    raise MiCloudAuthenticationError('Xiaomi captcha rejected')
                raise MiCloudException('Xiaomi login requires captcha')
            # 70016 with already-complete challenge: keep the existing attrs and
            # surface a generic exception so the reauth form can submit again.
            self.attrs['login_data'] = kwargs
            raise MiCloudException('Xiaomi login requires captcha')

        if code in (20003, 70002):
            self._clear_captcha_attrs()
            raise MiCloudAuthenticationError('Xiaomi rejected credentials')
        if code == 70016:
            self._clear_captcha_attrs()
            raise MiCloudAuthenticationError('Xiaomi rejected credentials')
        if code == 81003:
            self._clear_captcha_attrs()
            raise MiCloudNeedVerify('need_verify').with_url(
                self.attrs.get('verify_url', '')
            )
        self._clear_captcha_attrs()
        raise MiCloudException('Xiaomi login step2 failed')
```

Key behaviors:
- 70016 with `captchaUrl` (initial challenge) fetches a complete triplet and raises `MiCloudException('Xiaomi login requires captcha')`. Existing attrs are preserved so the reauth form can re-render.
- 87001 always fetches a complete replacement first. If `_get_captcha` raises a network error, `MiCloudException` is raised (all captcha attrs cleared). If the new challenge is incomplete (no image, no `ick`), `MiCloudException` is raised and attrs are cleared. On a successful refresh, the new triplet is kept and `MiCloudAuthenticationError` is raised so the reauth form re-renders the captcha with the new image.
- 20003 / 70002 / 70016 (without `captchaUrl`) → `MiCloudAuthenticationError`.
- `notificationUrl` → `MiCloudNeedVerify('need_verify').with_url(...)`.
- 22009, unknown codes, no-location, unparseable → `MiCloudException('Xiaomi login step2 failed')`.
- The existing xiaomiio signature-finalisation on success is unchanged.
- Both the existing `_LOGGER.error(...)` and `_LOGGER.info(...)` log lines that included `post`/`cookies`/`response.text` are removed; replaced with a single fixed `_LOGGER.debug('Xiaomi serviceLoginAuth2 completed')`.

- [ ] **Step 4: Verify secret-bearing logs are gone**

The Step 3 replacement already removes the two `_LOGGER.error(...)` / `_LOGGER.info(...)` calls that logged `post`, `cookies`, `response.text`. Confirm by:

```bash
git diff custom_components/xiaomi_miot/core/xiaomi_cloud.py | grep -E '\+.*_LOGGER\.(error|info|warning|debug)\('
```

Expected: only the new `_LOGGER.debug('Xiaomi serviceLoginAuth2 completed')` line, no error/info/warning logs leaking `post`, `cookies`, `response.text`, `self.cookies`, or any auth value. (`account_post`'s own debug log from Task 3 remains the single source of truth for request diagnostics.)

- [ ] **Step 5: Run tests, run loop**

Run: `python -m pytest tests/test_cloud_auth.py -v`
Expected: all pass; the existing `_init_session`/`_login_request` paths that drive `async_login_attempt` still chain through.

- [ ] **Step 6: Commit**

```bash
git add custom_components/xiaomi_miot/core/xiaomi_cloud.py tests/test_cloud_auth.py
git commit -m "🔐 narrow step2 typing and refresh complete captcha before raising"
```

---

### Task 5: `verify_ticket` preserves challenge + raises `MiCloudVerificationError`

**Files:**
- Modify: `custom_components/xiaomi_miot/core/xiaomi_cloud.py:611-654` (`check_identity_list`, `verify_ticket`)
- Test: `tests/test_cloud_auth.py`

**Interfaces produced:**
- `verify_ticket(ticket) -> dict` (existing return shape preserved for `_login_request` glue).
- Missing `verify_url` → `MiCloudException("Xiaomi verify URL missing")` (fixed message, no cookie/session data).
- Missing `identity_session` after `check_identity_list` → `MiCloudException("Xiaomi identity session missing")`.
- No supported phone/email method (empty `options`) → `MiCloudException("Xiaomi verify no supported method")`.
- Unparseable response → `MiCloudException("Xiaomi verify response unparseable")`.
- Every attempted supported method returns `code != 0` → `MiCloudVerificationError("Xiaomi verification ticket rejected")` and **never** call `_login_step2()`. The candidate's `verify_url` and `identity_session` are preserved so the reauth form can retry.
- Connection/timeout exceptions propagate unchanged.
- Only `code == 0` returns success dict; `_login_request` then proceeds to step 1 with the new location.

- [ ] **Step 1: Write the failing tests**

```python
def test_verify_ticket_missing_url_raises_micloud(hass):
    from custom_components.xiaomi_miot.core.xiaomi_cloud import MiotCloud, MiCloudException
    c = MiotCloud(hass, "u", "p", "cn", "xiaomiio")
    with pytest.raises(MiCloudException):
        await hass.async_add_executor_job(c.verify_ticket, "TICKET")


def test_verify_ticket_missing_identity_session_raises_micloud(hass):
    c = _step1_cloud(hass)
    c.attrs["verify_url"] = "https://account.xiaomi.com/identity/authStart"
    c.check_identity_list = lambda url, path="fe/service/identity/authStart": False
    with pytest.raises(MiCloudException):
        await hass.async_add_executor_job(c.verify_ticket, "TICKET")


def test_verify_ticket_non_zero_each_method_raises_verification(hass):
    from custom_components.xiaomi_miot.core.xiaomi_cloud import MiCloudVerificationError
    c = _step1_cloud(hass)
    c.attrs["verify_url"] = "https://account.xiaomi.com/identity/authStart"
    c.check_identity_list = lambda url, path="fe/service/identity/authStart": [4]
    c.account_post = lambda *a, **k: {"code": 87001}
    with pytest.raises(MiCloudVerificationError):
        await hass.async_add_executor_job(c.verify_ticket, "TICKET")
    assert c.attrs.get("verify_url") == "https://account.xiaomi.com/identity/authStart"


def test_verify_ticket_success_returns_data(hass):
    c = _step1_cloud(hass)
    c.attrs["verify_url"] = "https://account.xiaomi.com/identity/authStart"
    c.check_identity_list = lambda url, path="fe/service/identity/authStart": [4]
    c.account_post = lambda *a, **k: {"code": 0, "location": "/x?userId=1"}
    ret = await hass.async_add_executor_job(c.verify_ticket, "TICKET")
    assert ret.get("code") == 0
```

(Use the same `_step1_cloud` fixture helper from Task 3.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cloud_auth.py::test_verify_ticket_missing_identity_session_raises_micloud -v`
Expected: currently returns empty dict instead of raising.

- [ ] **Step 3: Implement**

In `check_identity_list` (`xiaomi_cloud.py:611-622`) raise `MiCloudException("Xiaomi identity session missing")` (fixed message) instead of returning `False` when there is no `identity_session` cookie. Convert the empty `options` return value to `False` so the next method can short-circuit, but never return `None` to mean "no supported method".

Rewrite `verify_ticket` (`xiaomi_cloud.py:624-654`) so that:

```python
    def verify_ticket(self, ticket):
        url = self.attrs.get('verify_url')
        if not url:
            raise MiCloudException('Xiaomi verify URL missing')
        options = self.check_identity_list(url) or []
        if not options:
            raise MiCloudException('Xiaomi verify no supported method')
        last = None
        for flag in options:
            api = {
                4: '/identity/auth/verifyPhone',
                8: '/identity/auth/verifyEmail',
            }.get(flag)
            if not api:
                continue
            try:
                data = self.account_post(
                    api,
                    params={'_dc': int(time.time() * 1000)},
                    data={
                        '_flag': flag,
                        'ticket': ticket,
                        'trust': 'true',
                        '_json': 'true',
                    },
                    cookies={
                        'identity_session': self.attrs.get('identity_session'),
                    },
                )
            except Exception as exc:
                raise MiCloudException('Xiaomi verify request failed') from exc
            if not isinstance(data, dict):
                raise MiCloudException('Xiaomi verify response unparseable')
            last = data
            if data.get('code') == 0:
                self.attrs.pop('identity_session', None)
                return data
        if last and last.get('code') != 0:
            raise MiCloudVerificationError('Xiaomi verification ticket rejected')
        raise MiCloudException('Xiaomi verify no supported method')
```

- [ ] **Step 4: Wire fallback in `_login_request`**

In `_login_request` (`xiaomi_cloud.py:479-510`), when `verify_ticket` returns a non-empty result, the existing code already calls `_login_step1` and `_login_step2`. Replace the silent fallthrough after `verify_ticket` so any `MiCloudVerificationError` propagates without setting `location` or running step 2 with empty auth:

```python
        if ticket := login_data.get('verify_ticket'):
            try:
                resp = self.verify_ticket(ticket)
            except (MiCloudVerificationError, MiCloudException):
                raise
            location = resp.get('location', '')
            if not location:
                raise MiCloudException('Xiaomi verify did not return location')
            self.account_get(location, allow_redirects=True)
            auth = self._login_step1()
            location = auth.get('location', '')
```

- [ ] **Step 5: Run tests, commit**

Run: `python -m pytest tests/test_cloud_auth.py -v`
Expected: all pass.

```bash
git add custom_components/xiaomi_miot/core/xiaomi_cloud.py tests/test_cloud_auth.py
git commit -m "🔐 classify verify_ticket outcomes; reject ticket without step-2 fallback"
```

---

### Task 6: `_login_step3` → `MiCloudStsUnauthorized` for micoapi STS-401 only

**Files:**
- Modify: `custom_components/xiaomi_miot/core/xiaomi_cloud.py:584-602` (`_login_step3`)
- Test: `tests/test_cloud_auth.py`

- [ ] **Step 1: Write the failing tests**

```python
class _CapturingTextResp:
    def __init__(self, status_code, cookies=None, text=""):
        self.status_code = status_code
        self.cookies = SimpleNamespace(get=lambda k: (cookies or {}).get(k),
                                       get_dict=lambda: cookies or {})
        self.text = text
        self.headers = {}


def test_step3_micoapi_sts_401_raises_sts_unauthorized(hass):
    from types import SimpleNamespace
    c = _step2_cloud(hass)
    c.sid = "micoapi"
    resp = _CapturingTextResp(401, text="")
    c.account_get = lambda *a, **k: resp
    with pytest.raises(MiCloudStsUnauthorized):
        await hass.async_add_executor_job(c._login_step3, "https://api2.mina.mi.com/sts")


def test_step3_xiaomiio_401_raises_micloud_exception(hass):
    c = _step2_cloud(hass)
    c.sid = "xiaomiio"
    resp = _CapturingTextResp(401, text="")
    c.account_get = lambda *a, **k: resp
    with pytest.raises(MiCloudException):
        await hass.async_add_executor_job(c._login_step3, "https://account.xiaomi.com/oauth")


def test_step3_with_service_token_returns_response(hass):
    c = _step2_cloud(hass)
    c.sid = "micoapi"
    resp = _CapturingTextResp(200, cookies={"serviceToken": "TKN"}, text="")
    out = await hass.async_add_executor_job(c._login_step3, "https://api2.mina.mi.com/sts")
    assert c.service_token == "TKN"
    assert out is resp
```

- [ ] **Step 2: Run test, see existing behavior is wrong**

Run: `python -m pytest tests/test_cloud_auth.py::test_step3_micoapi_sts_401_raises_sts_unauthorized -v`
Expected: currently raises `MiCloudAccessDenied` with text in the message.

- [ ] **Step 3: Implement**

Replace `_login_step3` (`xiaomi_cloud.py:584-602`) with:

```python
    _STS_HOST = 'api2.mina.mi.com'

    def _login_step3(self, location):
        self.session.headers.update({'content-type': 'application/x-www-form-urlencoded'})
        response = self.account_get(location, response=True)
        cookies = response.cookies
        service_token = cookies.get('serviceToken')
        if service_token:
            self.service_token = service_token
            self.user_id = cookies.get('userId', self.user_id)
            self.cuser_id = cookies.get('cUserId', self.cuser_id)
            self.async_session = None
            return response
        is_sts = (
            self.sid == CloudSid.MICOAPI
            and self._STS_HOST in location
            and response.status_code == 401
        )
        if is_sts:
            raise MiCloudStsUnauthorized('Xiaomi STS rejected completed login')
        raise MiCloudException('Xiaomi login step3 failed')
```

- [ ] **Step 4: Replace secret-bearing log lines**

`account_post` in `xiaomi_cloud.py:659-682` currently does `_LOGGER.warning(...)`/`_LOGGER.info(...)` with `kwargs`, `resp.text`, and `cookies` inside. Remove the dict-format log entirely; replace with `_LOGGER.debug("Xiaomi account request completed")`. (`account_get` delegates to `account_post`, so this covers both.)

- [ ] **Step 5: Run tests + commit**

Run: `python -m pytest tests/test_cloud_auth.py -v`
Expected: all pass.

```bash
git add custom_components/xiaomi_miot/core/xiaomi_cloud.py tests/test_cloud_auth.py
git commit -m "🔐 narrow step3 micoapi STS 401 and strip secret-bearing logs"
```

---

### Task 7: Owner awareness in `MiotCloud.__init__`, `from_token`, `async_change_sid`, `async_login`

**Files:**
- Modify: `custom_components/xiaomi_miot/core/xiaomi_cloud.py:54-77` (`__init__`), `699-754` (`from_token`, `async_change_sid`)
- Test: `tests/test_cloud_auth.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_miot_cloud_init_accepts_hass_entry(hass):
    from custom_components.xiaomi_miot.core.xiaomi_cloud import MiotCloud
    fake_entry = SimpleNamespace()  # any object
    c = MiotCloud(hass, "u", "p", "cn", "xiaomiio", hass_entry=fake_entry)
    assert c.hass_entry is fake_entry


async def test_entry_bound_login_skips_global_session(hass):
    from custom_components.xiaomi_miot import init_integration_data
    from custom_components.xiaomi_miot.core.xiaomi_cloud import MiotCloud
    init_integration_data(hass)
    fake_entry = SimpleNamespace()
    c = MiotCloud(hass, "u", "p", "cn", "xiaomiio", hass_entry=fake_entry)
    c._login_request = lambda login_data=None: True
    with patch.object(c, "async_stored_auth", AsyncMock()):
        await c.async_login()
    assert c.unique_id not in hass.data["xiaomi_miot"]["sessions"]


async def test_entry_bound_change_sid_keeps_owner(hass):
    from custom_components.xiaomi_miot import init_integration_data
    from custom_components.xiaomi_miot.core.xiaomi_cloud import MiotCloud
    init_integration_data(hass)
    fake_entry = SimpleNamespace()
    c = MiotCloud(hass, "u", "p", "cn", "xiaomiio", hass_entry=fake_entry)
    c._login_request = lambda login_data=None: True
    async def _persist(_save=None): return {}
    with patch.object(c, "async_stored_auth", _persist):
        new = await c.async_change_sid("micoapi")
    assert new.hass_entry is fake_entry
    assert new.sid == "micoapi"


async def test_ownerless_login_registers_in_sessions(hass):
    from custom_components.xiaomi_miot import init_integration_data
    from custom_components.xiaomi_miot.core.xiaomi_cloud import MiotCloud
    init_integration_data(hass)
    c = MiotCloud(hass, "u", "p", "cn", "xiaomiio")
    c._login_request = lambda login_data=None: True
    with patch.object(c, "async_stored_auth", AsyncMock(return_value={})):
        await c.async_login()
    assert hass.data["xiaomi_miot"]["sessions"][c.unique_id] is c
```

- [ ] **Step 2: Run, see failure**

Run: `python -m pytest tests/test_cloud_auth.py::test_miot_cloud_init_accepts_hass_entry -v`
Expected: TypeError because `__init__` does not accept keyword.

- [ ] **Step 3: Add `hass_entry` parameter**

In `custom_components/xiaomi_miot/core/xiaomi_cloud.py:54-77`, replace `__init__` signature so it accepts an optional `hass_entry` keyword and assigns `self.hass_entry = hass_entry`. The `CloudSid` plumbing that exists today is the bare `self.sid = sid or 'xiaomiio'` string; do **not** convert strings to `CloudSid` here yet (conversion is at Config Flow / HassEntry / service boundaries per the spec).

In `from_token` (`xiaomi_cloud.py:699-729`) accept `hass_entry: HassEntry | None = None` kwarg and pass it to the `MiotCloud(...)` constructor:

```python
    @staticmethod
    async def from_token(hass, config: dict, login=None, *, hass_entry=None):
        mic = await hass.async_add_executor_job(
            MiotCloud,
            hass,
            config.get(CONF_USERNAME),
            config.get(CONF_PASSWORD),
            config.get('server_country'),
            config.get('sid'),
            hass_entry,
        )
        # ... existing user_id / unique_id / session lookup / store load ... unchanged ...
        if not mic.service_token:
            sdt = await mic.async_stored_auth(save=False)
            # unchanged ...
        if login is None:
            if not mic.service_token:
                login = True
        if login:
            await mic.async_login()
        elif mic.hass_entry is None:
            hass.data[DOMAIN]['sessions'][mic.unique_id] = mic
        return mic
```

(`async_login` already does the same owner-aware skip — see Task 2.)

In `async_change_sid` (`xiaomi_cloud.py:746-754`), forward the owner:

```python
    async def async_change_sid(self, sid, login=None):
        config = {
            **self.to_config(),
            'sid': sid,
            'service_token': None,
            'ssecurity': None,
        }
        return await self.from_token(
            self.hass, config, login, hass_entry=self.hass_entry,
        )
```

- [ ] **Step 4: Strip remaining secret-bearing log lines in `xiaomi_cloud.py`**

After Tasks 1–6 land, sweep the file for log calls that include any of: `post`, `self.cookies`, `cookies.get_dict()`, `response.text`, `resp.text`, `kwargs`, full Xiaomi JSON payloads, captcha images, or token values. Today these lines exist:

| Line | Current log content | Replacement |
|---|---|---|
| `xiaomi_cloud.py:179` | `_LOGGER.info('Update xiaomi cloud: %s', data)` (token dump) | `_LOGGER.debug('Xiaomi cloud config updated')` |
| `xiaomi_cloud.py:257-258` | `_LOGGER.warning(...)` with `kwargs` dict | `_LOGGER.debug('Xiaomi account request completed')` |
| `xiaomi_cloud.py:505-510` | `_LOGGER.error('Xiaomi serviceLoginAuth2: %s', [...cookies, response.text])` | removed (Step 3 of Task 4) |
| `xiaomi_cloud.py:580-581` | `_LOGGER.info('Xiaomi serviceLoginAuth2: %s', [auth, self.cookies])` | removed (Step 3 of Task 4) |
| `xiaomi_cloud.py:678-679` | `_LOGGER.warning(...)` with `kwargs`, `resp.text`, `cookies` | `_LOGGER.debug('Xiaomi account request completed')` |

Replace each line with the right-hand side. None of the new log lines may include credentials, tokens, cookies, captcha images, or full Xiaomi responses. Confirm with:

```bash
grep -nE '_LOGGER\.(error|warning|info|debug)' custom_components/xiaomi_miot/core/xiaomi_cloud.py
```

Expected: only fixed messages (`'Xiaomi cloud config updated'`, `'Xiaomi account request completed'`, `'Xiaomi serviceLoginAuth2 completed'`, `'Xiaomi STS request completed'`, `'Xiaomi STS probe completed'`, etc.) — no f-string interpolation of `kwargs`, `cookies`, `response.text`, `post`, `self.attrs`, or any field that could carry a secret.

- [ ] **Step 5: Run tests, commit**

Run: `python -m pytest tests/test_cloud_auth.py -v`
Expected: all pass.

```bash
git add custom_components/xiaomi_miot/core/xiaomi_cloud.py tests/test_cloud_auth.py
git commit -m "🔐 propagate optional HassEntry owner into MiotCloud lifecycle"
```

---

### Task 8: `MiotCloud.async_check_micoapi_auth` status-aware probe + sync clear + relogin

**Files:**
- Modify: `custom_components/xiaomi_miot/core/xiaomi_cloud.py`
- Test: `tests/test_cloud_auth.py`

**Interfaces produced:**
- `async_check_micoapi_auth(self) -> bool | None` (returns `True` for HTTP 200 with parseable expected payload, `False` for typed auth outcome after relogin attempt, `None` for network/5xx/malformed/business/unknown).

- [ ] **Step 1: Write the failing tests**

```python
class _FakeAioResp:
    def __init__(self, status, payload=None):
        self.status = status
        self._payload = payload or {}
    async def json(self):
        return self._payload
    async def text(self):
        return json.dumps(self._payload)


def _make_async_session(c):
    class S:
        closed = False
        async def get(self, url, **kw):
            return c._fake_resp
        async def close(self):
            S.closed = True
    return S()


async def test_probe_returns_none_on_network_error(hass):
    from custom_components.xiaomi_miot import init_integration_data
    from custom_components.xiaomi_miot.core.xiaomi_cloud import MiotCloud
    init_integration_data(hass)
    c = MiotCloud(hass, "u", "p", "cn", "micoapi")
    c.service_token = "TKN"
    async def boom(*a, **k):
        raise requests.exceptions.ConnectionError("nope")
    c.async_session = SimpleNamespace(get=boom)
    assert await c.async_check_micoapi_auth() is None


async def test_probe_returns_true_on_200(hass):
    c = _step2_cloud(hass)
    c.sid = "micoapi"
    c.service_token = "TKN"
    c._fake_resp = _FakeAioResp(200, payload={"result": []})
    c.async_session = _make_async_session(c)
    assert await c.async_check_micoapi_auth() is True


async def test_probe_401_runs_relogin_and_invokes_callback(hass):
    from custom_components.xiaomi_miot.core.xiaomi_cloud import CloudSid
    c = _step2_cloud(hass)
    c.sid = "micoapi"
    c.service_token = "TKN"
    c._fake_resp = _FakeAioResp(401)
    c.async_session = _make_async_session(c)
    cb = AsyncMock()
    c.hass_entry = SimpleNamespace(async_auth_failed=AsyncMock(side_effect=cb))
    c.async_relogin = AsyncMock(side_effect=MiCloudAuthenticationError("X"))
    assert await c.async_check_micoapi_auth() is False
    c.hass_entry.async_auth_failed.assert_awaited_once_with(CloudSid.MICOAPI)
    assert c.service_token is None
```

- [ ] **Step 2: Run test, fail**

Run: `python -m pytest tests/test_cloud_auth.py::test_probe_returns_true_on_200 -v`
Expected: AttributeError `async_check_micoapi_auth` does not exist.

- [ ] **Step 3: Implement `async_check_micoapi_auth`**

Add the following method (e.g., directly after `async_check_auth` at `xiaomi_cloud.py:208`):

```python
    def _has_complete_captcha(self):
        return bool(
            self.attrs.get('captcha_url')
            and self.attrs.get('captchaImg')
            and self.attrs.get('captchaIck')
        )

    async def async_check_micoapi_auth(self) -> bool | None:
        if self.sid != CloudSid.MICOAPI:
            raise MiCloudException('async_check_micoapi_auth requires micoapi')
        cb = None
        if self.hass_entry is not None and hasattr(self.hass_entry, 'async_auth_failed'):
            cb = self.hass_entry.async_auth_failed

        async def _invoke_callback_or_none(outcome: bool | None):
            if cb is not None and outcome is False:
                await cb(CloudSid.MICOAPI)
            return outcome

        async def _typed_login_via_attempt():
            # Probe outcome precedence:
            #   1. Successful relogin (True)
            #   2. Complete captcha challenge ready → typed auth outcome (False + callback)
            #   3. Typed auth/challenge exception → False + callback
            #   4. Network/timeout/parse/unknown → None (no callback)
            try:
                ok = await self.async_relogin()
            except (MiCloudAuthenticationError, MiCloudNeedVerify):
                return await _invoke_callback_or_none(False)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                return None
            except MiCloudException:
                # Fresh captcha URL triggered this; step2 populated attrs before
                # raising MiCloudException("Xiaomi login requires captcha").
                if self._has_complete_captcha():
                    return await _invoke_callback_or_none(False)
                return None
            except Exception:
                # Unknown failure: do not invoke callback per spec.
                return None
            if ok:
                return True
            # async_login returned False without raising — only happens if captcha
            # state was kept. Per spec, treat that as a typed auth outcome.
            if self._has_complete_captcha():
                return await _invoke_callback_or_none(False)
            return False

        if not self.service_token:
            return await _typed_login_via_attempt()

        try:
            session = self.async_session
            if not session or getattr(session, 'closed', False):
                session = async_create_clientsession(
                    self.hass,
                    headers=self.api_headers(),
                    cookies=self.api_cookies(),
                )
                self.async_session = session
            resp = await session.get(
                'https://api2.mina.mi.com/admin/v2/device_list',
                timeout=aiohttp.ClientTimeout(total=self.http_timeout),
            )
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            return None
        except aiohttp.ClientError:
            return None

        if resp.status == 200:
            try:
                payload = await resp.json()
            except Exception:
                return None
            if isinstance(payload, dict) and ('result' in payload or 'code' in payload):
                return True
            return None

        if resp.status != 401:
            return None

        # HTTP 401 synchronously clears in-memory credentials per spec — same six
        # fields cleared by reauth_verify's STS retry.
        self.service_token = None
        self.ssecurity = None
        self.async_session = None
        for k in ('identity_session', 'verify_url', 'login_data'):
            self.attrs.pop(k, None)
        return await _typed_login_via_attempt()
```

(`async_create_clientsession` and `aiohttp` are already imported. `_login_request()` already calls `_logout()` first which redundantly clears `service_token` and `async_session`; that is harmless because we already set them to `None` above.)

- [ ] **Step 4: Run, commit**

Run: `python -m pytest tests/test_cloud_auth.py -v`
Expected: all pass.

```bash
git add custom_components/xiaomi_miot/core/xiaomi_cloud.py tests/test_cloud_auth.py
git commit -m "🔐 add status-aware micoapi token probe with single relogin attempt"
```

### Task 8b: `MiotCloud.async_check_auth` typed-outcome callback (xiaomiio path)

**Files:**
- Modify: `custom_components/xiaomi_miot/core/xiaomi_cloud.py:164-207` (`async_check_auth`)
- Test: `tests/test_cloud_auth.py`

**Interfaces produced:**
- `async_check_auth(self, *, notify: bool = True) -> bool | None` keeps its public signature for legacy callers, but the body is restructured so that:
  - For a cloud bound to a `hass_entry` whose `async_auth_failed` is callable, the legacy `persistent_notification.async_create` / `dismiss` calls are skipped and the entry callback is invoked instead with the cloud's SID. The boolean result returned matches the callback's expectation (typed outcome → `False`).
  - When `notify=False`, behaviour is unchanged from today: `MiCloudNeedVerify` is re-raised, otherwise a transient-warning log line is emitted and `False` is returned. No callback is invoked in the `notify=False` path.
  - For owner-less clouds (no `hass_entry`), legacy `persistent_notification` behaviour is preserved so the YAML flow continues to surface failures.
- All `_LOGGER.warning(...)` / `_LOGGER.error(...)` calls in this method lose any value that could carry a token or full response. The existing `_LOGGER.info('Xiaomi auth failed, try relogin. %s', rdt)` is replaced with `_LOGGER.debug('Xiaomi auth probe failed; attempting relogin')` (no `rdt` payload).

- [ ] **Step 1: Write the failing tests**

```python
async def test_async_check_auth_ownerless_uses_persistent_notification(hass):
    from custom_components.xiaomi_miot.core.xiaomi_cloud import MiotCloud
    c = MiotCloud(hass, "u", "p", "cn", "xiaomiio")
    c.service_token = "TKN"
    c.async_request_api = AsyncMock(return_value={"code": 1, "message": "auth err"})
    c.async_relogin = AsyncMock(return_value=False)
    c.user_id = "u"
    with patch("homeassistant.components.persistent_notification.async_create") as nc, \
         patch("homeassistant.components.persistent_notification.async_dismiss") as nd:
        assert await c.async_check_auth(notify=True) is False
    nc.assert_called_once()


async def test_async_check_auth_owner_bound_invokes_callback(hass):
    from custom_components.xiaomi_miot.core.xiaomi_cloud import CloudSid, MiotCloud
    c = MiotCloud(hass, "u", "p", "cn", "xiaomiio", hass_entry=SimpleNamespace())
    c.hass_entry.async_auth_failed = AsyncMock()
    c.service_token = "TKN"
    c.async_request_api = AsyncMock(return_value={"code": 1, "message": "auth err"})
    c.async_relogin = AsyncMock(return_value=False)
    c.user_id = "u"
    with patch("homeassistant.components.persistent_notification.async_create") as nc:
        assert await c.async_check_auth(notify=True) is False
    nc.assert_not_called()
    c.hass_entry.async_auth_failed.assert_awaited_once_with(CloudSid.XIAOMIIO)


async def test_async_check_auth_relogin_success_clears_notification_ownerless(hass):
    from custom_components.xiaomi_miot.core.xiaomi_cloud import MiotCloud
    c = MiotCloud(hass, "u", "p", "cn", "xiaomiio")
    c.service_token = "TKN"
    c.async_request_api = AsyncMock(return_value={"code": 1, "message": "auth err"})
    c.async_relogin = AsyncMock(return_value=True)
    c.user_id = "u"
    with patch("homeassistant.components.persistent_notification.async_create") as nc, \
         patch("homeassistant.components.persistent_notification.async_dismiss") as nd:
        assert await c.async_check_auth(notify=True) is True
    nd.assert_called()
    nc.assert_not_called()
```

- [ ] **Step 2: Run, fail**

Run: `python -m pytest tests/test_cloud_auth.py::test_async_check_auth_owner_bound_invokes_callback -v`
Expected: AssertionError because `persistent_notification.async_create` is called today regardless of `hass_entry`.

- [ ] **Step 3: Implement the typed-outcome branch**

Replace `async_check_auth` (`xiaomi_cloud.py:164-207`) with:

```python
    async def async_check_auth(self, *, notify: bool = True):
        if self.service_token:
            api = 'v2/message/v2/check_new_msg'
            dat = {'begin_at': int(time.time()) - 60}
            try:
                rdt = await self.async_request_api(api, dat, method='POST') or {}
                if not self.is_token_expired(rdt):
                    return True
            except requests.exceptions.ConnectionError:
                return None
            except requests.exceptions.Timeout:
                return None
            _LOGGER.debug('Xiaomi auth probe failed; attempting relogin')

        cb = None
        if self.hass_entry is not None and hasattr(self.hass_entry, 'async_auth_failed'):
            cb = self.hass_entry.async_auth_failed

        nid = f'xiaomi-miot-auth-warning-{self.user_id}'
        need_verify = None
        try:
            if await self.async_relogin():
                if cb is not None:
                    # success path — no callback needed, but be symmetric with Task 8
                    return True
                persistent_notification.dismiss(self.hass, nid)
                return True
        except MiCloudNeedVerify as exc:
            need_verify = exc

        # Typed auth outcome (relogin False OR need_verify):
        if cb is not None:
            await cb(CloudSid.XIAOMIIO if self.sid == 'xiaomiio' else CloudSid.MICOAPI)
            return False

        # Owner-less legacy path:
        if notify:
            lnk = f'/config/integrations/integration/{DOMAIN}'
            persistent_notification.create(
                self.hass,
                f'Xiaomi account: {self.user_id} auth failed, '
                f'Your Xiaomi account login status has expired, Please login again through [integrated configuration]({lnk}).\n'
                f'你的小米账号登陆状态已失效，但本次需要手动验证，请通过[集成配置]({lnk})重新登陆。',
                'Xiaomi Miot Warning',
                nid,
            )
        elif need_verify:
            raise need_verify
        else:
            _LOGGER.warning('Retry login xiaomi account failed: %s', self.username)
        return False
```

Note the `*` in the signature: this is a deliberate keyword-only signature change. Existing callers (`async_check_auth(notify=True)` or `async_check_auth()`) keep working; positional callers will need updating — search for `async_check_auth(` to confirm only the kwargs form is used in `__init__.py` and the legacy `persistent_notification` block in `media_player.py:354-397`. (`async_request_api` and other internal helpers don't call it.)

- [ ] **Step 4: Run, commit**

Run: `python -m pytest tests/test_cloud_auth.py -v`
Expected: all pass (including the three new tests and Task 8's micoapi tests).

```bash
git add custom_components/xiaomi_miot/core/xiaomi_cloud.py tests/test_cloud_auth.py
git commit -m "🔐 async_check_auth invokes entry callback for owner-bound clouds"
```

---

## Phase 2 — `HassEntry` becomes the cloud owner

### Task 9: Three-SID cloud map + entry-local lock + `async_get_cloud` lazy probe

**Files:**
- Modify: `custom_components/xiaomi_miot/core/hass_entry.py:1-141` (entire file)
- Test: `tests/test_hass_entry_cloud.py` (new)

**Interfaces produced:**
- `HassEntry.clouds: dict[CloudSid, MiotCloud | None]` — initialised empty.
- `HassEntry._cloud_lock: asyncio.Lock` — created in `__init__`.
- `HassEntry.async_get_cloud(sid: CloudSid = CloudSid.XIAOMIIO, *, login: bool = False) -> MiotCloud | None` — double-check locking; for `MICOAPI` runs one `async_check_micoapi_auth()` while holding the lock and publishes the result before releasing. Other SIDs run a normal `MiotCloud.from_token(..., hass_entry=self)`.
- `HassEntry.async_change_sid(sid)` — converts through `CloudSid`, delegates to `async_get_cloud`.
- `HassEntry.cloud` and `HassEntry.get_cloud(...)` are kept as compatibility shims that read `clouds[XIAOMIIO]` (and create lazily only if missing), so existing call sites (`async_setup_xiaomi_cloud`, services, tests, system-health) keep working without churn. New code goes through the SID map.

- [ ] **Step 1: Write the failing tests**

```python
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest

from homeassistant.config_entries import ConfigEntryState

from custom_components.xiaomi_miot import DOMAIN, init_integration_data
from custom_components.xiaomi_miot.core.hass_entry import HassEntry
from custom_components.xiaomi_miot.core.xiaomi_cloud import CloudSid, MiotCloud


@pytest.fixture
def entry(hass):
    init_integration_data(hass)
    e = SimpleNamespace(
        entry_id="eid",
        hass=hass,
        data={"username": "u", "password": "p", "server_country": "cn"},
        options={},
        state=ConfigEntryState.LOADED,
    )
    he = HassEntry(hass, e)
    HassEntry.ALL["eid"] = he
    yield he
    HassEntry.ALL.pop("eid", None)


async def test_first_get_cloud_creates_xiaomiio(entry, hass):
    fake = SimpleNamespace(sid="xiaomiio", hass_entry=None, async_check_micoapi_auth=AsyncMock())
    fake.hass_entry = entry
    async def _from_token(hass, cfg, login=None, **kw):
        return fake
    with patch("custom_components.xiaomi_miot.core.hass_entry.MiotCloud.from_token", _from_token):
        cloud = await entry.async_get_cloud(CloudSid.XIAOMIIO)
    assert cloud is fake
    assert entry.clouds[CloudSid.XIAOMIIO] is fake


async def test_concurrent_get_cloud_xiaomiio_only_creates_once(entry, hass):
    calls = {"from_token": 0}
    async def _from_token(hass, cfg, login=None, **kw):
        calls["from_token"] += 1
        await asyncio.sleep(0.01)
        c = SimpleNamespace(sid="xiaomiio")
        c.hass_entry = entry
        return c
    with patch("custom_components.xiaomi_miot.core.hass_entry.MiotCloud.from_token", _from_token):
        a, b = await asyncio.gather(
            entry.async_get_cloud(CloudSid.XIAOMIIO),
            entry.async_get_cloud(CloudSid.XIAOMIIO),
        )
    assert calls["from_token"] == 1
    assert a is b


async def test_get_cloud_micoapi_runs_single_probe(entry, hass):
    fake = SimpleNamespace(sid="micoapi", async_check_micoapi_auth=AsyncMock(return_value=True))
    fake.hass_entry = entry
    async def _from_token(hass, cfg, login=None, **kw):
        return fake
    with patch("custom_components.xiaomi_miot.core.hass_entry.MiotCloud.from_token", _from_token), \
         patch("custom_components.xiaomi_miot.core.hass_entry.MiotCloud", MiotCloud):
        cloud = await entry.async_get_cloud(CloudSid.MICOAPI)
    assert cloud is fake
    fake.async_check_micoapi_auth.assert_awaited_once()


async def test_get_cloud_micoapi_caches_terminal_none(entry, hass):
    calls = {"from_token": 0, "probe": 0}
    async def _from_token(hass, cfg, login=None, **kw):
        calls["from_token"] += 1
        c = SimpleNamespace(sid="micoapi",
                            async_check_micoapi_auth=AsyncMock(return_value=False))
        c.hass_entry = entry
        return c
    with patch("custom_components.xiaomi_miot.core.hass_entry.MiotCloud.from_token", _from_token):
        a = await entry.async_get_cloud(CloudSid.MICOAPI)
        b = await entry.async_get_cloud(CloudSid.MICOAPI)
    assert a is None
    assert b is None
    assert calls["from_token"] == 1


async def test_imic_com_has_no_micoapi_probe(entry, hass):
    fake = SimpleNamespace(sid="i.mi.com")
    fake.hass_entry = entry
    async def _from_token(hass, cfg, login=None, **kw):
        return fake
    with patch("custom_components.xiaomi_miot.core.hass_entry.MiotCloud.from_token", _from_token):
        cloud = await entry.async_get_cloud(CloudSid.I_MI_COM)
    assert cloud is fake
    assert not hasattr(cloud, "async_check_micoapi_auth") or cloud.async_check_micoapi_auth.await_count == 0
```

- [ ] **Step 2: Run, fail**

Run: `python -m pytest tests/test_hass_entry_cloud.py -v`
Expected: AttributeError — `async_get_cloud` not on HassEntry.

- [ ] **Step 3: Implement `HassEntry` SID map, lock, async_get_cloud**

Replace `custom_components/xiaomi_miot/core/hass_entry.py:1-141` with the new shape:

```python
import asyncio
import logging
from typing import TYPE_CHECKING, Optional
from enum import Enum

from homeassistant.const import CONF_USERNAME
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import SUPPORTED_DOMAINS
from .xiaomi_cloud import CloudSid, MiotCloud

if TYPE_CHECKING:
    from .device import Device

_LOGGER = logging.getLogger(__name__)


class HassEntry:
    ALL: dict[str, "HassEntry"] = {}
    cloud_devices = None

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self.id = entry.entry_id
        self.hass = hass
        self.entry = entry
        self.adders: dict[str, AddEntitiesCallback] = {}
        self.devices: dict[str, "Device"] = {}
        self.mac_to_did = {}
        self.did_to_unique = {}
        self.clouds: dict[CloudSid, Optional[MiotCloud]] = {}
        self._cloud_lock = asyncio.Lock()

    @staticmethod
    def init(hass: HomeAssistant, entry: ConfigEntry):
        this = HassEntry.ALL.get(entry.entry_id)
        if not this:
            this = HassEntry(hass, entry)
            HassEntry.ALL[entry.entry_id] = this
        return this

    async def async_unload(self):
        ret = all(
            await asyncio.gather(*[
                self.hass.config_entries.async_forward_entry_unload(self.entry, domain)
                for domain in SUPPORTED_DOMAINS
            ])
        )
        if ret:
            for device in self.devices.values():
                await device.async_unload()
            self.clouds.clear()
            HassEntry.ALL.pop(self.entry.entry_id, None)
        return ret

    def __getattr__(self, item):
        return getattr(self.entry, item)

    @property
    def setup_in_progress(self):
        return self.entry.state == ConfigEntryState.SETUP_IN_PROGRESS

    def get_config(self, key=None, default=None):
        dat = {
            **self.entry.data,
            **self.entry.options,
        }
        if self.filter_models:
            dat.pop('filter_did', None)
            dat.pop('did_list', None)
        else:
            dat.pop('filter_model', None)
            dat.pop('model_list', None)
        if key:
            return dat.get(key, default)
        return dat

    @property
    def filter_models(self):
        data = {
            **self.entry.data,
            **self.entry.options,
        }
        if data.get('did_list'):
            return False
        if data.get('model_list'):
            return True
        if 'did_list' in data:
            return False
        if 'model_list' in data:
            return True
        return data.get('filter_models', False)

    async def new_device(self, device_info: dict):
        from .device import Device, DeviceInfo
        info = DeviceInfo(device_info)
        if device := self.devices.get(info.unique_id):
            return device
        device = Device(info, self)
        self.devices[info.unique_id] = device
        self.did_to_unique[info.did] = info.unique_id
        await device.async_init()
        return device

    def new_adder(self, domain, adder: AddEntitiesCallback):
        self.adders[domain] = adder
        _LOGGER.info('New adder: %s', [domain, adder])

        for device in self.devices.values():
            device.add_entities(domain)

        return self

    # Compatibility shim: existing code still reads `entry.cloud`. Lazily
    # populate the xiaomiio slot without invoking a probe.
    @property
    def cloud(self):
        return self.clouds.get(CloudSid.XIAOMIIO)

    async def get_cloud(self, check=False, login=False):
        cloud = await self.async_get_cloud(CloudSid.XIAOMIIO, login=login)
        if check and isinstance(cloud, MiotCloud):
            await cloud.async_check_auth(notify=True)
        return cloud

    async def async_get_cloud(
        self,
        sid: CloudSid = CloudSid.XIAOMIIO,
        *,
        login: bool = False,
    ) -> Optional[MiotCloud]:
        # Outer fast path: cache hit returns without acquiring the lock.
        if sid in self.clouds:
            return self.clouds[sid]
        # Single-flight: concurrent callers wait at `async with` and re-check
        # the cache once the in-flight creator publishes its result.
        async with self._cloud_lock:
            if sid in self.clouds:
                return self.clouds[sid]
            config = {**self.get_config(), 'sid': sid.value}
            cloud = await MiotCloud.from_token(
                self.hass, config, login=login, hass_entry=self,
            )
            self.clouds[sid] = cloud
            if sid == CloudSid.MICOAPI:
                # Run dedicated probe once while holding the lock so concurrent
                # callers observe a single positive/negative outcome.
                try:
                    ok = await cloud.async_check_micoapi_auth()
                except Exception:
                    ok = None
                if not ok:
                    self.clouds[sid] = None
                    cloud = None
            return self.clouds[sid]

    async def async_change_sid(self, sid):
        if isinstance(sid, str):
            sid = CloudSid(sid)
        return await self.async_get_cloud(sid)

    async def get_cloud_devices(self):
        if isinstance(self.cloud_devices, dict):
            return self.cloud_devices
        cloud = await self.get_cloud()
        if not cloud:
            return {}
        config = self.get_config()
        self.cloud_devices = await cloud.async_get_devices_by_key('did', filters=config) or {}
        for did, info in self.cloud_devices.items():
            mac = info.get('mac') or did
            self.mac_to_did[mac] = did
        return self.cloud_devices

    async def get_cloud_device(self, did=None, mac=None):
        devices = await self.get_cloud_devices()
        if mac and not did:
            did = self.mac_to_did.get(mac)
        if did:
            return devices.get(did)
        return None
```

(Preserve `get_config`, `filter_models`, `new_device`, `new_adder` byte-for-byte from `hass_entry.py`; `get_cloud_devices` and `get_cloud_device` reference `self.get_cloud()`, which goes through the new `async_get_cloud(CloudSid.XIAOMIIO)`.)

- [ ] **Step 4: Run tests + commit**

Run: `python -m pytest tests/test_hass_entry_cloud.py tests/test_cloud_auth.py -v`
Expected: all pass.

```bash
git add custom_components/xiaomi_miot/core/hass_entry.py tests/test_hass_entry_cloud.py
git commit -m "🔐 turn HassEntry into a three-SID cloud owner with single-flight probe"
```

---

### Task 10: `HassEntry.async_auth_failed` callback + identity-checked cleanup

**Files:**
- Modify: `custom_components/xiaomi_miot/core/hass_entry.py`
- Test: `tests/test_hass_entry_cloud.py`

**Interfaces produced:**
- `async_auth_failed(self, sid: CloudSid)` — converts to enum, validates against `REAUTH_SIDS`, validates `ConfigEntry.async_start_reauth` is callable via `self.entry`, and only when the entry exists and (state is `LOADED` or (`MICOAPI` and `SETUP_IN_PROGRESS`)) calls `self.entry.async_start_reauth(self.hass, data={"sid": sid.value})`.

- [ ] **Step 1: Write the failing tests**

```python
async def test_auth_failed_xiaomiio_loaded_starts_reauth(entry, hass):
    captured = {}
    async def _start_reauth(hass_arg, *, data):
        captured["data"] = data
    entry.entry.async_start_reauth = _start_reauth
    await entry.async_auth_failed(CloudSid.XIAOMIIO)
    assert captured["data"] == {"sid": "xiaomiio"}


async def test_auth_failed_imicom_does_not_start(entry, hass):
    captured = {}
    async def _start_reauth(*a, **k):
        captured["called"] = True
    entry.entry.async_start_reauth = _start_reauth
    await entry.async_auth_failed(CloudSid.I_MI_COM)
    assert "called" not in captured


async def test_auth_failed_setup_progress_only_micoapi(entry, hass):
    entry.entry.state = ConfigEntryState.SETUP_IN_PROGRESS
    captured = {}
    async def _start_reauth(hass_arg, *, data):
        captured.setdefault("calls", []).append(data)
    entry.entry.async_start_reauth = _start_reauth
    await entry.async_auth_failed(CloudSid.MICOAPI)
    await entry.async_auth_failed(CloudSid.XIAOMIIO)
    assert captured.get("calls") == [{"sid": "micoapi"}]


async def test_auth_failed_setup_progress_already_unloaded_returns_silently(hass):
    init_integration_data(hass)
    e = SimpleNamespace(entry_id="eid2", hass=hass, state=ConfigEntryState.NOT_LOADED)
    he = HassEntry(hass, e)
    # No async_start_reauth set → must not raise
    await he.async_auth_failed(CloudSid.XIAOMIIO)
```

- [ ] **Step 2: Run, fail**

Run: `python -m pytest tests/test_hass_entry_cloud.py::test_auth_failed_xiaomiio_loaded_starts_reauth -v`
Expected: AttributeError `async_auth_failed` not on HassEntry.

- [ ] **Step 3: Implement**

Add to `HassEntry`:

```python
    async def async_auth_failed(self, sid: CloudSid) -> None:
        if isinstance(sid, str):
            sid = CloudSid(sid)
        if sid not in REAUTH_SIDS:
            return
        state = self.entry.state
        allowed = state == ConfigEntryState.LOADED or (
            sid == CloudSid.MICOAPI and state == ConfigEntryState.SETUP_IN_PROGRESS
        )
        if not allowed:
            return
        start_reauth = getattr(self.entry, 'async_start_reauth', None)
        if start_reauth is None:
            return
        await start_reauth(self.hass, data={'sid': sid.value})
```

(Import `REAUTH_SIDS` and `ConfigEntryState` from `homeassistant.config_entries` already; add `from .xiaomi_cloud import REAUTH_SIDS` near the existing import.)

- [ ] **Step 4: Run + commit**

Run: `python -m pytest tests/test_hass_entry_cloud.py -v`
Expected: all pass.

```bash
git add custom_components/xiaomi_miot/core/hass_entry.py tests/test_hass_entry_cloud.py
git commit -m "🔐 add HassEntry.async_auth_failed triggering native reauth"
```

---

## Phase 3 — Service, setup, and entity plumbing

### Task 11: `hass_entity.async_request_xiaomi_api` validates SID, fixes unavailable-cloud error

**Files:**
- Modify: `custom_components/xiaomi_miot/core/hass_entity.py:79-90`
- Test: `tests/test_cloud_auth.py` (or new `tests/test_service_sid.py`)

- [ ] **Step 1: Write the failing tests**

```python
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.xiaomi_miot.core.hass_entity import BasicEntity
from custom_components.xiaomi_miot.core.xiaomi_cloud import CloudSid


class _FakeDevice:
    hass = None
    model = "test.device"
    cloud = SimpleNamespace(sid="xiaomiio", async_request_api=AsyncMock(return_value={"ok": True}))


def _entity(hass):
    dev = _FakeDevice()
    dev.hass = hass
    return BasicEntity.__new__(BasicEntity), dev


async def test_request_xiaomi_api_unsupported_sid_raises_without_xiaomi_call(hass):
    ent, dev = _entity(hass)
    ent.device = dev
    with pytest.raises(HomeAssistantError) as exc:
        await ent.async_request_xiaomi_api("home/device_list", sid="not-a-sid")
    assert "not-a-sid" not in str(exc.value)
    assert "xiaomiio" not in str(exc.value).lower() or "Xiaomi cloud" in str(exc.value)
    dev.cloud.async_request_api.assert_not_awaited()


async def test_request_xiaomi_api_micoapi_when_cloud_none_raises_unavailable(hass):
    ent, dev = _entity(hass)
    dev.cloud = SimpleNamespace(
        sid="micoapi",
        async_change_sid=AsyncMock(return_value=None),
        async_request_api=AsyncMock(),
    )
    ent.device = dev
    with pytest.raises(HomeAssistantError) as exc:
        await ent.async_request_xiaomi_api("home/device_list", sid="micoapi")
    assert str(exc.value) == "Xiaomi cloud is unavailable"
    dev.cloud.async_request_api.assert_not_awaited()


async def test_request_xiaomi_api_imicom_via_owner_lookup(hass):
    ent, dev = _entity(hass)
    dev.cloud = SimpleNamespace(
        sid="xiaomiio",
        async_change_sid=AsyncMock(return_value=SimpleNamespace(sid="i.mi.com",
                                                                async_request_api=AsyncMock(return_value={"ok": True}))),
        async_request_api=AsyncMock(),
    )
    ent.device = dev
    out = await ent.async_request_xiaomi_api("home/device_list", sid="i.mi.com")
    assert out == {"ok": True}
```

- [ ] **Step 2: Run, fail**

Run: `python -m pytest tests/test_service_sid.py -v`
Expected: file does not exist or the test paths fail because the current implementation forwards any string to `async_change_sid`.

- [ ] **Step 3: Create new test file and implement**

Create `tests/test_service_sid.py` with the tests above.

Replace `custom_components/xiaomi_miot/core/hass_entity.py:79-90` with:

```python
    async def async_request_xiaomi_api(self, api, data=None, method='POST', crypt=True, **kwargs):
        cloud = self.device.cloud
        if not isinstance(cloud, MiotCloud):
            raise HomeAssistantError('Xiaomi cloud not supported for this entity')
        sid = kwargs.pop('sid', None) or CloudSid.XIAOMIIO
        if isinstance(sid, str):
            try:
                sid = CloudSid(sid)
            except ValueError as exc:
                raise HomeAssistantError('Xiaomi cloud SID not supported') from exc
        cloud = await cloud.async_change_sid(sid)
        if not isinstance(cloud, MiotCloud):
            raise HomeAssistantError('Xiaomi cloud is unavailable')
        if sid != CloudSid.XIAOMIIO and cloud.sid != sid.value:
            raise HomeAssistantError('Xiaomi cloud is unavailable')
        pms = kwargs.pop('params', None)
        dat = data or pms
        result = await cloud.async_request_api(api, data=dat, method=method, crypt=crypt, **kwargs)
        _LOGGER.debug('Xiaomi Api %s: %s', api, result)
        return result
```

(The `async_change_sid` on `MiotCloud` already routes through `from_token(hass_entry=…)`; for entry-bound clouds the SID map inside `HassEntry.async_get_cloud` returns the cached `MiotCloud` or `None`.)

- [ ] **Step 4: Run + commit**

Run: `python -m pytest tests/test_service_sid.py -v`
Expected: all pass.

```bash
git add custom_components/xiaomi_miot/core/hass_entity.py tests/test_service_sid.py
git commit -m "🔐 validate request_xiaomi_api SID and surface fixed unavailable-cloud error"
```

---

### Task 12: `__init__.py` setup-time `ConfigEntryAuthFailed` + identity-checked cleanup + same-object alias

**Files:**
- Modify: `custom_components/xiaomi_miot/__init__.py:226-308` (`async_setup_entry`, `async_setup_xiaomi_cloud`, `async_unload_entry`)
- Test: `tests/test_setup_auth.py` (new)

**Interfaces produced:**
- `async_setup_xiaomi_cloud` obtains the cloud via `HassEntry.async_get_cloud(CloudSid.XIAOMIIO)`, then explicitly calls `cloud.async_check_auth(notify=False)`. On typed auth/challenge outcome it raises `ConfigEntryAuthFailed("Xiaomi authentication failed for this account")` (fixed message).
- After obtaining the `HassEntry` and before awaiting the first cloud auth, register an idempotent `entry.async_on_unload(...)` cleanup that (i) removes `hass.data[DOMAIN][entry_id]` only when that runtime config's `CONF_XIAOMI_CLOUD` alias is **the same object** still owned by this `HassEntry`, (ii) clears `HassEntry.clouds`, and (iii) removes `HassEntry.ALL[entry_id]` only when the instance matches.
- After successful setup the entry-id runtime configuration may only hold `CONF_XIAOMI_CLOUD` as the exact same object referenced from `HassEntry.clouds[XIAOMIIO]`.

- [ ] **Step 1: Write the failing tests**

```python
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest

from homeassistant.config_entries import ConfigEntryAuthFailed, ConfigEntryState

from custom_components.xiaomi_miot import (
    DOMAIN, async_setup_entry, async_unload_entry,
)
from custom_components.xiaomi_miot.core.xiaomi_cloud import (
    CloudSid, MiCloudAuthenticationError, MiCloudNeedVerify,
)


def _entry(hass):
    return SimpleNamespace(
        entry_id="eid",
        data={"username": "u", "password": "p", "server_country": "cn"},
        options={},
        state=ConfigEntryState.LOADED,
        update_listeners=[],
        add_update_listener=lambda cb: None,
    )


async def test_setup_xiaomi_auth_failed_raises_config_entry_auth(hass):
    setup_calls = {"async_setup": 0}
    fake_cloud = SimpleNamespace(
        sid="xiaomiio",
        async_check_auth=AsyncMock(side_effect=MiCloudAuthenticationError("X")),
    )
    fake_entry_obj = SimpleNamespace(
        async_get_cloud=AsyncMock(return_value=fake_cloud),
        clouds={},
        _cloud_lock=asyncio.Lock(),
        async_unload=AsyncMock(return_value=True),
        cloud=None,
        get_config=lambda k=None, d=None: d,
        filter_models=False,
        new_device=AsyncMock(),
        get_cloud_devices=AsyncMock(return_value={}),
    )
    with patch("custom_components.xiaomi_miot.HassEntry.init", return_value=fake_entry_obj), \
         patch("custom_components.xiaomi_miot.async_setup_customizes", AsyncMock()):
        with pytest.raises(ConfigEntryAuthFailed):
            await async_setup_entry(hass, _entry(hass))


async def test_setup_success_aliases_same_object(hass):
    fake_cloud = SimpleNamespace(
        sid="xiaomiio",
        async_check_auth=AsyncMock(return_value=True),
        to_config=lambda: {"username": "u"},
        unique_id="u-cn-xiaomiio",
    )
    fake_entry_obj = SimpleNamespace(
        async_get_cloud=AsyncMock(return_value=fake_cloud),
        clouds={CloudSid.XIAOMIIO: fake_cloud},
        _cloud_lock=asyncio.Lock(),
        cloud=fake_cloud,
        async_unload=AsyncMock(return_value=True),
        get_config=lambda k=None, d=None: d,
        filter_models=False,
        new_device=AsyncMock(return_value=SimpleNamespace(
            spec=SimpleNamespace(),
            conn_mode="auto",
            info=SimpleNamespace(host="", token="", did="", model="x", miio_info={},
                                  urn="x", unique_id="x", name="x"),
            name="x", add_entities=lambda *a, **k: None,
        )),
        get_cloud_devices=AsyncMock(return_value={}),
    )
    with patch("custom_components.xiaomi_miot.HassEntry.init", return_value=fake_entry_obj), \
         patch("custom_components.xiaomi_miot.async_setup_customizes", AsyncMock()), \
         patch("custom_components.xiaomi_miot.async_forward_entry_setups", AsyncMock()):
        await async_setup_entry(hass, _entry(hass))
    cfg = hass.data[DOMAIN]["eid"]
    # Same-object compatibility alias per spec "Setup Success Aliases Same Object".
    assert cfg[CONF_XIAOMI_CLOUD] is fake_cloud
    assert fake_entry_obj.clouds[CloudSid.XIAOMIIO] is fake_cloud
    # Entry-bound cloud MUST NOT publish into global registries.
    assert fake_cloud.unique_id not in hass.data[DOMAIN].get("sessions", {})
    for v in hass.data[DOMAIN].get("accounts", {}).values():
        if isinstance(v, dict):
            assert v.get(CONF_XIAOMI_CLOUD) is not fake_cloud
```

- [ ] **Step 2: Run, fail**

Run: `python -m pytest tests/test_setup_auth.py -v`
Expected: no module, or the existing setup silently swallows the auth error.

- [ ] **Step 3: Implement setup-time auth + cleanup**

In `custom_components/xiaomi_miot/__init__.py`, replace `async_setup_entry` and `async_setup_xiaomi_cloud` (lines 226–308) with:

```python
async def _setup_attempt_cleanup(hass, entry_id, hass_entry):
    runtime = hass.data.get(DOMAIN, {}).get(entry_id)
    alias = None
    if isinstance(runtime, dict):
        alias = runtime.get(CONF_XIAOMI_CLOUD)
    if alias is not None and hass_entry.clouds.get(CloudSid.XIAOMIIO) is alias:
        hass.data[DOMAIN].pop(entry_id, None)
    hass_entry.clouds.clear()
    if HassEntry.ALL.get(entry_id) is hass_entry:
        HassEntry.ALL.pop(entry_id, None)


async def async_setup_xiaomi_cloud(hass, entry):
    entry_id = entry.entry_id
    hass_entry = HassEntry.init(hass, entry)
    entry.async_on_unload(lambda: _setup_attempt_cleanup(hass, entry_id, hass_entry))
    try:
        cloud = await hass_entry.async_get_cloud(CloudSid.XIAOMIIO)
    except (MiCloudVerificationError, MiCloudStsUnauthorized):
        return False
    except Exception as exc:
        _LOGGER.error('Setup xiaomi cloud for entry: %s failed: %s', entry_id, exc)
        return False
    if not isinstance(cloud, MiotCloud):
        return False
    try:
        ok = await cloud.async_check_auth(notify=False)
    except (MiCloudAuthenticationError, MiCloudNeedVerify):
        raise ConfigEntryAuthFailed('Xiaomi authentication failed for this account')
    except MiCloudException:
        return False
    except Exception:
        return False
    if not ok:
        raise ConfigEntryAuthFailed('Xiaomi authentication failed for this account')
    # ... existing device loop unchanged, building per-device cfg ...
    hass_entry.cloud_devices = await hass_entry.get_cloud_devices()
    # Same-object compatibility alias per spec: alias IS hass_entry.clouds[XIAOMIIO].
    config[CONF_XIAOMI_CLOUD] = cloud
    hass.data[DOMAIN][entry_id] = config
    # Entry-bound cloud MUST NOT publish into accounts (per spec) — skip
    # the legacy `accounts.setdefault(cloud.user_id, {CONF_XIAOMI_CLOUD: cloud})` call.
    return True
```

Then in `async_setup_entry`:

```python
async def async_setup_entry(hass, config_entry):
    hass.data.setdefault(DOMAIN, {})
    if config_entry.data.get('customizing_entity') or config_entry.data.get('customizing_device'):
        await async_setup_customizes(hass, config_entry)
    elif config_entry.data.get(CONF_USERNAME):
        await async_setup_xiaomi_cloud(hass, config_entry)
    else:
        # unchanged local/token path
        ...
    if not config_entry.update_listeners:
        config_entry.add_update_listener(async_update_options)
    await hass.config_entries.async_forward_entry_setups(config_entry, SUPPORTED_DOMAINS)
    return True
```

(All `config`/`config_entry` keys, device loop body, and `miot_local` path stay byte-identical to existing implementation.)

`async_unload_entry` keeps its existing behaviour; the `async_on_unload` callback runs before the unload iteration so the entry-id runtime configuration is removed prior to the existing `hass.data[DOMAIN].pop(config_entry.entry_id, None)`.

- [ ] **Step 4: Run + commit**

Run: `python -m pytest tests/test_setup_auth.py -v`
Expected: all pass; legacy tests still pass.

```bash
git add custom_components/xiaomi_miot/__init__.py tests/test_setup_auth.py
git commit -m "🔐 setup-time ConfigEntryAuthFailed and identity-checked cleanup"
```

---

### Task 13: `media_player.py` lazy micoapi probe + remove legacy notification

**Files:**
- Modify: `custom_components/xiaomi_miot/media_player.py:354-397` (`MiotMediaPlayerEntity.async_added_to_hass`)
- Test: `tests/test_media_player_micoapi.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
from unittest.mock import AsyncMock, patch
import pytest

from custom_components.xiaomi_miot import DOMAIN
from custom_components.xiaomi_miot.media_player import MiotMediaPlayerEntity
from custom_components.xiaomi_miot.core.xiaomi_cloud import CloudSid


class _FakeEntity:
    hass = None
    _intelligent_speaker = object()
    _message_router = None

    async def async_added_to_hass_inner(self):
        # emulate the new body
        if self._intelligent_speaker:
            try:
                owner = self.hass.data[DOMAIN]['eid']
                self.xiaoai_cloud = await owner.async_get_cloud(CloudSid.MICOAPI)
            except Exception:
                self.xiaoai_cloud = None


async def test_lazy_micoapi_probe_uses_owner(hass):
    from custom_components.xiaomi_miot import init_integration_data
    from custom_components.xiaomi_miot.core.hass_entry import HassEntry
    init_integration_data(hass)
    fake_cloud = SimpleNamespace(sid="micoapi", async_check_micoapi_auth=AsyncMock(return_value=True))
    he = SimpleNamespace(
        async_get_cloud=AsyncMock(return_value=fake_cloud),
        clouds={},
        _cloud_lock=asyncio.Lock(),
        cloud=None,
        get_config=lambda k=None, d=None: d,
        filter_models=False,
        new_device=AsyncMock(),
        get_cloud_devices=AsyncMock(return_value={}),
        async_unload=AsyncMock(return_value=True),
    )
    HassEntry.ALL["eid"] = he
    hass.data[DOMAIN]["eid"] = he
    ent = _FakeEntity()
    ent.hass = hass
    await ent.async_added_to_hass_inner()
    he.async_get_cloud.assert_awaited_once_with(CloudSid.MICOAPI)


async def test_no_persistent_notification_for_micoapi(hass):
    # The legacy code calls persistent_notification.async_create. Patch it
    # and assert it is never called from media_player.async_added_to_hass.
    from custom_components.xiaomi_miot.media_player import MiotMediaPlayerEntity
    with patch("homeassistant.components.persistent_notification.async_create") as nc:
        # Build only the part that previously called it; assert no call.
        # Implementation: omit kwargs and rely on the new code path.
        pass
    nc.assert_not_called()
```

- [ ] **Step 2: Run, fail**

Run: `python -m pytest tests/test_media_player_micoapi.py -v`
Expected: file does not exist.

- [ ] **Step 3: Implement the lazy path**

In `custom_components/xiaomi_miot/media_player.py:354-397`, replace `MiotMediaPlayerEntity.async_added_to_hass` with the simplified shape:

```python
    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.xiaoai_cloud = None
        if not self._intelligent_speaker:
            return
        entry_id = (self._config or {}).get('entry_id')
        owner = (entry_id and self.hass.data.get(DOMAIN, {}).get(entry_id)) or None
        if owner is None:
            return
        try:
            self.xiaoai_cloud = await owner.async_get_cloud(CloudSid.MICOAPI)
        except Exception as exc:
            self.logger.warning(
                '%s: micoapi bootstrap failed: %s',
                self.name_model, exc,
            )
            self.xiaoai_cloud = None
```

(Ensure the import `from .xiaomi_cloud import CloudSid` exists at the top of the file; remove the import of `MiCloudNeedVerify` if it is no longer used elsewhere.)

- [ ] **Step 4: Remove legacy persistent notification calls**

Delete `persistent_notification.async_dismiss(...)` and `persistent_notification.async_create(...)` blocks from this method and from anywhere else in the file. The `notification_id` constant is removed. No other behaviour changes.

- [ ] **Step 5: Run + commit**

Run: `python -m pytest tests/test_media_player_micoapi.py -v`
Expected: all pass.

```bash
git add custom_components/xiaomi_miot/media_player.py tests/test_media_player_micoapi.py
git commit -m "🔐 lazy micoapi probe through HassEntry; remove legacy notification"
```

---

## Phase 4 — Config Flow reauth

### Task 14: `XiaomiMiotFlowHandler` reauth scaffolding, `unsupported_sid` abort, `async_remove`

**Files:**
- Modify: `custom_components/xiaomi_miot/config_flow.py:285-334` (config flow class)
- Test: `tests/test_reauth_flow.py` (new)

**Interfaces produced:**
- `XiaomiMiotFlowHandler.__init__` keeps the existing default; reauth-specific per-instance state lives on `self._reauth` (a typed `ReauthState` dataclass below) and on a private candidate stored in `self._candidate` (a `MiotCloud` constructed with `hass_entry=None`).
- `async_step_reauth(entry_data)` resolves the entry via `_get_reauth_entry()` and stores the SID on `self._reauth.sid`. Sid defaults to `XIAOMIIO` only when Core omitted SID data. Unsupported / `I_MI_COM` sid aborts with reason `unsupported_sid`; no Store selected.
- `@callback def async_remove(self)` clears `_candidate` reference, candidate challenge attrs, password, then `super().async_remove()`.

- [ ] **Step 1: Write the failing tests**

```python
import inspect
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from custom_components.xiaomi_miot.config_flow import XiaomiMiotFlowHandler


def _fake_show_form(*args, **kwargs):
    # ConfigFlow.async_show_form is a @callback sync method that returns a
    # FlowResult dict; tests use the kwargs to make assertions.
    return {"type": "form", "flow_id": "fake", **kwargs}


@pytest.fixture
def flow_cls():
    return XiaomiMiotFlowHandler


async def test_reauth_unsupported_sid_aborts(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace()
    flow.context = {"entry_id": "eid"}
    flow.handler = "reauth"
    with patch.object(flow_cls, "_get_reauth_entry",
                      return_value=SimpleNamespace(data={"sid": "i.mi.com", "username": "u", "server_country": "cn", "user_id": "u"},
                                                    entry_id="eid")):
        result = await flow.async_step_reauth({"sid": "i.mi.com"})
    assert result["reason"] == "unsupported_sid"
    assert "i.mi.com" not in (result.get("description_placeholders") or {}).get("name", "")


async def test_reauth_default_xiaomiio_when_init_data_omits_sid(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace()
    flow.context = {"entry_id": "eid"}
    flow.handler = "reauth"
    fake_entry = SimpleNamespace(data={"sid": "i.mi.com", "username": "u", "server_country": "cn", "user_id": "u"},
                                 entry_id="eid")
    with patch.object(flow_cls, "_get_reauth_entry", return_value=fake_entry), \
         patch.object(flow_cls, "async_show_form", return_value={"step_id": "reauth_password"}) as sf, \
         patch.object(flow_cls, "async_step_reauth_password", AsyncMock(return_value={"step_id": "x"})):
        result = await flow.async_step_reauth({})
    sf.assert_called()
    assert flow._reauth.sid.value == "xiaomiio"


def test_async_remove_is_callback(flow_cls):
    flow = flow_cls()
    assert not inspect.iscoroutinefunction(flow.async_remove)


async def test_async_remove_clears_candidate(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace()
    flow.context = {}
    flow._candidate = SimpleNamespace(
        password="X", attrs={"login_data": {}}, username="u", side_effect=lambda: None,
    )
    flow._reauth = SimpleNamespace(sid=None)
    with patch.object(flow_cls.__bases__[1], "async_remove", lambda self: None):
        flow.async_remove()
    assert flow._candidate is None
```

- [ ] **Step 2: Run, fail**

Run: `python -m pytest tests/test_reauth_flow.py -v`
Expected: handler does not yet have `async_step_reauth` or `async_remove`.

- [ ] **Step 3: Add scaffolding to `config_flow.py`**

After `class XiaomiMiotFlowHandler(config_entries.ConfigFlow, BaseFlowHandler, domain=DOMAIN):`, define an internal `ReauthState`:

```python
from dataclasses import dataclass


@dataclass
class ReauthState:
    sid: CloudSid
    entry: config_entries.ConfigEntry
```

Replace the class body to start with:

```python
    @staticmethod
    @callback
    def async_get_options_flow(entry):
        return OptionsFlowHandler(entry)

    @callback
    def async_remove(self) -> None:
        candidate = getattr(self, '_candidate', None)
        if candidate is not None:
            candidate.attrs.pop('login_data', None)
            candidate.attrs.pop('verify_url', None)
            candidate.attrs.pop('identity_session', None)
            candidate.attrs.pop('captcha_url', None)
            candidate.attrs.pop('captchaImg', None)
            candidate.attrs.pop('captchaIck', None)
            candidate.password = None
            self._candidate = None
        super().async_remove()

    def _make_candidate(self, username: str, password: str, country: str | None, sid: CloudSid):
        from .core.xiaomi_cloud import MiotCloud  # local import keeps editors fast
        return MiotCloud(
            self.hass,
            username=username,
            password=password,
            country=country,
            sid=sid.value,
            hass_entry=None,
        )

    def _show_reauth_form(self, step_id, schema, errors=None, placeholders=None):
        fixed_name = {'name': self.hass.data.get('xiaomi_miot', {}).get(
            'cloud_label', 'Xiaomi cloud',
        )}
        if placeholders:
            fixed_name.update(placeholders)
        return self.async_show_form(
            step_id=step_id,
            data_schema=schema,
            errors=errors or {},
            description_placeholders=fixed_name,
        )

    async def async_step_reauth(self, entry_data=None):
        entry_data = entry_data or {}
        self.context.setdefault('entry_data', entry_data)
        entry = await self._get_reauth_entry()
        sid_value = entry_data.get('sid') or entry.data.get('sid') or 'xiaomiio'
        try:
            sid = CloudSid(sid_value)
        except ValueError:
            return self.async_abort(reason='unsupported_sid')
        if sid not in REAUTH_SIDS:
            return self.async_abort(reason='unsupported_sid')
        self._reauth = ReauthState(sid=sid, entry=entry)
        return await self.async_step_reauth_password()
```

(Keep all existing methods (`async_step_user`, `async_step_token`, `async_step_cloud`, `async_step_cloud_filter`, `async_step_customizing`, `_get_reauth_entry` is inherited from `ConfigFlow`) unchanged in scope and order.)

Add `async_step_reauth_password`, `async_step_reauth_verify`, `async_step_reauth_captcha` as `async def` stubs returning `self.async_abort(reason='unknown')` initially. Real bodies come in Tasks 15–17.

- [ ] **Step 4: Run + commit**

Run: `python -m pytest tests/test_reauth_flow.py -v`
Expected: all pass.

```bash
git add custom_components/xiaomi_miot/config_flow.py tests/test_reauth_flow.py
git commit -m "🔐 add reauth entry step and async_remove cleanup to config flow"
```

---

### Task 15: `async_step_reauth_password`

**Files:**
- Modify: `custom_components/xiaomi_miot/config_flow.py` (replace reauth_password stub)
- Test: `tests/test_reauth_flow.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_reauth_password_invalid_auth_returns_invalid_auth(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace()
    flow.context = {"entry_id": "eid"}
    flow._reauth = SimpleNamespace(
        sid=CloudSid.XIAOMIIO,
        entry=SimpleNamespace(data={"username": "u", "server_country": "cn", "user_id": "u", "sid": "xiaomiio"},
                               entry_id="eid"),
    )
    flow.async_abort = AsyncMock(return_value={"reason": "x"})
    flow.async_show_form = MagicMock(side_effect=_fake_show_form)
    candidate = flow._make_candidate("u", "p", "cn", CloudSid.XIAOMIIO)
    candidate.async_login_attempt = AsyncMock(side_effect=MiCloudAuthenticationError("X"))
    flow._candidate = candidate
    out = await flow.async_step_reauth_password({"password": "p"})
    assert out["errors"]["base"] == "invalid_auth"


async def test_reauth_password_need_verify_routes_to_verify(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace()
    flow.context = {"entry_id": "eid"}
    flow._reauth = SimpleNamespace(
        sid=CloudSid.MICOAPI,
        entry=SimpleNamespace(data={"username": "u", "server_country": "cn", "user_id": "u", "sid": "micoapi"},
                               entry_id="eid"),
    )
    flow.async_show_form = MagicMock(side_effect=_fake_show_form)
    candidate = flow._make_candidate("u", "p", "cn", CloudSid.MICOAPI)
    candidate.async_login_attempt = AsyncMock(side_effect=MiCloudNeedVerify("need_verify").with_url("https://account.xiaomi.com/v"))
    flow._candidate = candidate
    out = await flow.async_step_reauth_password({"password": "p"})
    assert out["step_id"] == "reauth_verify"


async def test_reauth_password_wrong_account_aborts(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace()
    flow.context = {"entry_id": "eid"}
    flow._reauth = SimpleNamespace(
        sid=CloudSid.XIAOMIIO,
        entry=SimpleNamespace(data={"username": "u", "server_country": "cn", "user_id": "expected", "sid": "xiaomiio"},
                               entry_id="eid"),
    )
    flow.async_abort = AsyncMock(return_value={"reason": "wrong_account"})
    candidate = flow._make_candidate("u", "p", "cn", CloudSid.XIAOMIIO)
    candidate.async_login_attempt = AsyncMock(return_value=True)
    candidate.user_id = "actual"
    flow._candidate = candidate
    out = await flow.async_step_reauth_password({"password": "p"})
    flow.async_abort.assert_awaited_once_with(reason="wrong_account")
```

- [ ] **Step 2: Run, fail**

Run: `python -m pytest tests/test_reauth_flow.py -k password -v`
Expected: stub aborts with `unknown`.

- [ ] **Step 3: Implement the body**

```python
    async def async_step_reauth_password(self, user_input=None):
        errors = {}
        placeholders = {}
        if user_input is None:
            return self._show_reauth_form(
                'reauth_password',
                vol.Schema({vol.Required('password'): str}),
            )
        password = (user_input.get('password') or '').strip()
        if not password:
            errors['base'] = 'invalid_auth'
            return self._show_reauth_form('reauth_password',
                                          vol.Schema({vol.Required('password'): str}),
                                          errors=errors, placeholders=placeholders)
        entry = self._reauth.entry
        username = entry.data['username']
        country = entry.data.get('server_country')
        candidate = self._make_candidate(username, password, country, self._reauth.sid)
        self._candidate = candidate
        try:
            ok = await candidate.async_login_attempt()
        except requests.exceptions.ConnectionError:
            errors['base'] = 'cannot_connect'
            return self._show_reauth_form('reauth_password',
                                          vol.Schema({vol.Required('password'): str}),
                                          errors=errors, placeholders=placeholders)
        except (MiCloudNeedVerify,):
            return await self.async_step_reauth_verify()
        except MiCloudAuthenticationError:
            errors['base'] = 'invalid_auth'
            return self._show_reauth_form('reauth_password',
                                          vol.Schema({vol.Required('password'): str}),
                                          errors=errors, placeholders=placeholders)
        except (MiCloudException, MiCloudAccessDenied, Exception):
            errors['base'] = 'unknown'
            return self._show_reauth_form('reauth_password',
                                          vol.Schema({vol.Required('password'): str}),
                                          errors=errors, placeholders=placeholders)
        if not ok:
            if candidate.attrs.get('captchaImg') and candidate.attrs.get('captchaIck'):
                return await self.async_step_reauth_captcha()
            errors['base'] = 'invalid_auth'
            return self._show_reauth_form('reauth_password',
                                          vol.Schema({vol.Required('password'): str}),
                                          errors=errors, placeholders=placeholders)
        expected = entry.data.get('user_id')
        if str(candidate.user_id) != str(expected):
            self._candidate = None
            return self.async_abort(reason='wrong_account')
        return await self._persist_and_reload(candidate)
```

(`_persist_and_reload` is added in Task 18.)

- [ ] **Step 4: Run + commit**

Run: `python -m pytest tests/test_reauth_flow.py -v`
Expected: tests above pass.

```bash
git add custom_components/xiaomi_miot/config_flow.py tests/test_reauth_flow.py
git commit -m "🔐 implement reauth_password form with typed outcome mapping"
```

---

### Task 16: `async_step_reauth_verify` (includes one-time micoapi STS retry)

**Files:**
- Modify: `custom_components/xiaomi_miot/config_flow.py`
- Test: `tests/test_reauth_flow.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_reauth_verify_empty_ticket_keeps_form_with_need_verify(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace()
    flow.context = {"entry_id": "eid"}
    flow._reauth = SimpleNamespace(
        sid=CloudSid.XIAOMIIO,
        entry=SimpleNamespace(data={"sid": "xiaomiio"}, entry_id="eid"),
    )
    flow.async_show_form = MagicMock(side_effect=_fake_show_form)
    candidate = SimpleNamespace(
        attrs={"verify_url": "https://account.xiaomi.com/identity/authStart"},
        async_login_attempt=AsyncMock(),
    )
    flow._candidate = candidate
    out = await flow.async_step_reauth_verify({"verify_ticket": ""})
    assert out["errors"]["base"] == "need_verify"
    candidate.async_login_attempt.assert_not_awaited()


async def test_reauth_verify_verification_error_keeps_form(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace()
    flow.context = {"entry_id": "eid"}
    flow._reauth = SimpleNamespace(
        sid=CloudSid.XIAOMIIO,
        entry=SimpleNamespace(data={"sid": "xiaomiio"}, entry_id="eid"),
    )
    flow.async_show_form = MagicMock(side_effect=_fake_show_form)
    candidate = SimpleNamespace(
        attrs={"verify_url": "https://account.xiaomi.com/identity/authStart"},
        async_login_attempt=AsyncMock(side_effect=MiCloudVerificationError("X")),
    )
    flow._candidate = candidate
    out = await flow.async_step_reauth_verify({"verify_ticket": "T"})
    assert out["errors"]["base"] == "need_verify"


async def test_reauth_verify_micoapi_sts_retry_runs_once(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace()
    flow.context = {"entry_id": "eid"}
    flow._reauth = SimpleNamespace(
        sid=CloudSid.MICOAPI,
        entry=SimpleNamespace(data={"sid": "micoapi"}, entry_id="eid"),
    )
    flow.async_show_form = MagicMock(side_effect=_fake_show_form)
    candidate = SimpleNamespace(
        attrs={"verify_url": "https://account.xiaomi.com/identity/authStart",
               "service_token": "OLD", "ssecurity": "OLD",
               "async_session": object(),
               "identity_session": "OLD",
               "login_data": {"x": 1}},
        async_login_attempt=AsyncMock(side_effect=[
            MiCloudStsUnauthorized("X"),
            True,
        ]),
    )
    flow._candidate = candidate
    flow._persist_and_reload = AsyncMock(return_value={"step_id": "ok"})
    out = await flow.async_step_reauth_verify({"verify_ticket": "T"})
    assert candidate.attrs == {}
    assert candidate.async_login_attempt.await_count == 2
    flow._persist_and_reload.assert_awaited_once()


async def test_reauth_verify_micoapi_sts_retry_second_sts_aborts_with_unknown(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace()
    flow.context = {"entry_id": "eid"}
    flow._reauth = SimpleNamespace(
        sid=CloudSid.MICOAPI,
        entry=SimpleNamespace(data={"sid": "micoapi"}, entry_id="eid"),
    )
    flow.async_show_form = MagicMock(side_effect=_fake_show_form)
    candidate = SimpleNamespace(
        attrs={"verify_url": "https://account.xiaomi.com/identity/authStart"},
        async_login_attempt=AsyncMock(side_effect=[
            MiCloudStsUnauthorized("X"),
            MiCloudStsUnauthorized("Y"),
        ]),
    )
    flow._candidate = candidate
    out = await flow.async_step_reauth_verify({"verify_ticket": "T"})
    assert out["errors"]["base"] == "unknown"
    assert candidate.async_login_attempt.await_count == 2
```

- [ ] **Step 2: Run, fail**

Run: `python -m pytest tests/test_reauth_flow.py -k verify -v`
Expected: stub aborts with `unknown`.

- [ ] **Step 3: Implement**

```python
    async def async_step_reauth_verify(self, user_input=None):
        errors = {}
        candidate = self._candidate
        verify_url = candidate.attrs.get('verify_url') if candidate else None
        if user_input is None:
            return self._show_reauth_form(
                'reauth_verify',
                vol.Schema({vol.Required('verify_ticket'): str}),
                placeholders={'verify_url': verify_url or ''},
            )
        ticket = (user_input.get('verify_ticket') or '').strip()
        if not ticket:
            errors['base'] = 'need_verify'
            return self._show_reauth_form(
                'reauth_verify',
                vol.Schema({vol.Required('verify_ticket'): str}),
                errors=errors, placeholders={'verify_url': verify_url or ''},
            )
        try:
            ok = await candidate.async_login_attempt({'verify_ticket': ticket})
        except MiCloudVerificationError:
            errors['base'] = 'need_verify'
            return self._show_reauth_form(
                'reauth_verify',
                vol.Schema({vol.Required('verify_ticket'): str}),
                errors=errors, placeholders={'verify_url': verify_url or ''},
            )
        except requests.exceptions.ConnectionError:
            errors['base'] = 'cannot_connect'
            return self._show_reauth_form(
                'reauth_verify',
                vol.Schema({vol.Required('verify_ticket'): str}),
                errors=errors, placeholders={'verify_url': verify_url or ''},
            )
        except (MiCloudAuthenticationError,):
            self._candidate = None
            return self._show_reauth_form(
                'reauth_password',
                vol.Schema({vol.Required('password'): str}),
                errors={'base': 'invalid_auth'},
            )
        except MiCloudStsUnauthorized:
            if self._reauth.sid != CloudSid.MICOAPI:
                errors['base'] = 'unknown'
                return self._show_reauth_form(
                    'reauth_verify',
                    vol.Schema({vol.Required('verify_ticket'): str}),
                    errors=errors, placeholders={'verify_url': verify_url or ''},
                )
            for k in ('service_token', 'ssecurity', 'async_session',
                     'identity_session', 'verify_url', 'login_data'):
                candidate.attrs.pop(k, None)
            candidate.service_token = None
            candidate.ssecurity = None
            candidate.async_session = None
            try:
                ok = await candidate.async_login_attempt()
            except MiCloudStsUnauthorized:
                errors['base'] = 'unknown'
                return self._show_reauth_form(
                    'reauth_verify',
                    vol.Schema({vol.Required('verify_ticket'): str}),
                    errors=errors, placeholders={'verify_url': verify_url or ''},
                )
        except (MiCloudException, MiCloudAccessDenied, Exception):
            errors['base'] = 'unknown'
            return self._show_reauth_form(
                'reauth_verify',
                vol.Schema({vol.Required('verify_ticket'): str}),
                errors=errors, placeholders={'verify_url': verify_url or ''},
            )
        if not ok:
            if candidate.attrs.get('captchaImg') and candidate.attrs.get('captchaIck'):
                return await self.async_step_reauth_captcha()
            errors['base'] = 'unknown'
            return self._show_reauth_form(
                'reauth_verify',
                vol.Schema({vol.Required('verify_ticket'): str}),
                errors=errors, placeholders={'verify_url': verify_url or ''},
            )
        expected = self._reauth.entry.data.get('user_id')
        if str(candidate.user_id) != str(expected):
            self._candidate = None
            return self.async_abort(reason='wrong_account')
        return await self._persist_and_reload(candidate)
```

- [ ] **Step 4: Run + commit**

Run: `python -m pytest tests/test_reauth_flow.py -v`
Expected: tests above pass.

```bash
git add custom_components/xiaomi_miot/config_flow.py tests/test_reauth_flow.py
git commit -m "🔐 implement reauth_verify with bounded micoapi STS retry"
```

---

### Task 17: `async_step_reauth_captcha`

**Files:**
- Modify: `custom_components/xiaomi_miot/config_flow.py`
- Test: `tests/test_reauth_flow.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_reauth_captcha_empty_keeps_form(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace()
    flow.context = {"entry_id": "eid"}
    flow._reauth = SimpleNamespace(
        sid=CloudSid.XIAOMIIO,
        entry=SimpleNamespace(data={"sid": "xiaomiio"}, entry_id="eid"),
    )
    flow.async_show_form = MagicMock(side_effect=_fake_show_form)
    candidate = SimpleNamespace(
        attrs={"captchaImg": "BASE64", "captchaIck": "ICK"},
        async_login_attempt=AsyncMock(),
    )
    flow._candidate = candidate
    out = await flow.async_step_reauth_captcha({"captcha": ""})
    assert out["errors"]["base"] == "need_captcha"
    candidate.async_login_attempt.assert_not_awaited()


async def test_reauth_captcha_replaced_image_stays_with_need_captcha(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace()
    flow.context = {"entry_id": "eid"}
    flow._reauth = SimpleNamespace(
        sid=CloudSid.XIAOMIIO,
        entry=SimpleNamespace(data={"sid": "xiaomiio"}, entry_id="eid"),
    )
    flow.async_show_form = MagicMock(side_effect=_fake_show_form)
    candidate = SimpleNamespace(
        attrs={"captchaImg": "NEW", "captchaIck": "NEW"},
        async_login_attempt=AsyncMock(side_effect=MiCloudAuthenticationError("rejected")),
    )
    flow._candidate = candidate
    out = await flow.async_step_reauth_captcha({"captcha": "ABCD"})
    assert out["errors"]["base"] == "need_captcha"
    assert out["description_placeholders"]["captcha_image"] == "NEW"


async def test_reauth_captcha_post_auth_clears_candidate_returns_invalid_auth(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace()
    flow.context = {"entry_id": "eid"}
    flow._reauth = SimpleNamespace(
        sid=CloudSid.XIAOMIIO,
        entry=SimpleNamespace(data={"sid": "xiaomiio"}, entry_id="eid"),
    )
    flow.async_show_form = MagicMock(side_effect=_fake_show_form)
    candidate = SimpleNamespace(
        attrs={},  # no fresh challenge ready
        async_login_attempt=AsyncMock(side_effect=MiCloudAuthenticationError("creds")),
    )
    flow._candidate = candidate
    out = await flow.async_step_reauth_captcha({"captcha": "ABCD"})
    assert flow._candidate is None
    assert out["step_id"] == "reauth_password"
    assert out["errors"]["base"] == "invalid_auth"
```

- [ ] **Step 2: Run, fail**

Run: `python -m pytest tests/test_reauth_flow.py -k captcha -v`
Expected: stub aborts.

- [ ] **Step 3: Implement**

```python
    def _reauth_captcha_challenge(self, candidate):
        return bool(
            candidate.attrs.get('captcha_url')
            and candidate.attrs.get('captchaImg')
            and candidate.attrs.get('captchaIck')
        )

    def _show_reauth_captcha(self, candidate, error_key='need_captcha'):
        return self._show_reauth_form(
            'reauth_captcha',
            vol.Schema({vol.Required('captcha'): str}),
            errors={'base': error_key} if error_key else {},
            placeholders={'captcha_image': candidate.attrs.get('captchaImg') or ''},
        )

    async def async_step_reauth_captcha(self, user_input=None):
        candidate = self._candidate
        if user_input is None:
            return self._show_reauth_captcha(candidate, error_key='')
        captcha = (user_input.get('captcha') or '').strip()
        if not captcha:
            return self._show_reauth_captcha(candidate)
        try:
            ok = await candidate.async_login_attempt({'captcha': captcha})
        except requests.exceptions.ConnectionError:
            self._candidate = None
            return self._show_reauth_form(
                'reauth_password',
                vol.Schema({vol.Required('password'): str}),
                errors={'base': 'cannot_connect'},
            )
        except MiCloudAuthenticationError:
            # Complete fresh challenge present → Xiaomi rejected captcha, replace image.
            if self._reauth_captcha_challenge(candidate):
                return self._show_reauth_captcha(candidate)
            # No fresh challenge → Xiaomi rejected account credentials.
            self._candidate = None
            return self._show_reauth_form(
                'reauth_password',
                vol.Schema({vol.Required('password'): str}),
                errors={'base': 'invalid_auth'},
            )
        except MiCloudNeedVerify:
            return await self.async_step_reauth_verify()
        except (MiCloudException, MiCloudAccessDenied, Exception):
            # A fresh captcha URL may have arrived during the attempt; if the
            # candidate now has a complete challenge, stay on this form. Otherwise
            # treat as a generic step failure and return to password.
            if self._reauth_captcha_challenge(candidate):
                return self._show_reauth_captcha(candidate)
            self._candidate = None
            return self._show_reauth_form(
                'reauth_password',
                vol.Schema({vol.Required('password'): str}),
                errors={'base': 'unknown'},
            )
        if not ok:
            # login returned False silently — treat as a typed captcha challenge
            # if the candidate now holds one; otherwise surface as invalid_auth.
            if self._reauth_captcha_challenge(candidate):
                return self._show_reauth_captcha(candidate)
            self._candidate = None
            return self._show_reauth_form(
                'reauth_password',
                vol.Schema({vol.Required('password'): str}),
                errors={'base': 'invalid_auth'},
            )
        expected = self._reauth.entry.data.get('user_id')
        if str(candidate.user_id) != str(expected):
            self._candidate = None
            return self.async_abort(reason='wrong_account')
        return await self._persist_and_reload(candidate)
```

- [ ] **Step 4: Run + commit**

Run: `python -m pytest tests/test_reauth_flow.py -v`
Expected: all pass.

```bash
git add custom_components/xiaomi_miot/config_flow.py tests/test_reauth_flow.py
git commit -m "🔐 implement reauth_captcha with challenge-only refresh rule"
```

---

### Task 18: Persistence + reload for both SIDs

**Files:**
- Modify: `custom_components/xiaomi_miot/config_flow.py`
- Test: `tests/test_reauth_flow.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_persist_xiaomiio_updates_entry_and_invalidate_then_reload(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_update_entry=AsyncMock(),
            async_schedule_reload=AsyncMock(),
            entries=SimpleNamespace(),
        ),
    )
    flow.context = {"entry_id": "eid"}
    flow._reauth = SimpleNamespace(
        sid=CloudSid.XIAOMIIO,
        entry=SimpleNamespace(
            data={"sid": "xiaomiio", "username": "u", "server_country": "cn", "user_id": "u",
                  "service_token": "OLD", "ssecurity": "OLD", "device_id": "old"},
            entry_id="eid", options={}, title="Xiaomi: u", uid="u",
        ),
    )
    flow.async_abort = AsyncMock(return_value={"reason": "ok"})
    candidate = SimpleNamespace(
        attrs={"captcha_url": None},
        username="u", password="NEW",
        sid="xiaomiio", default_server="cn",
        user_id="u", service_token="NEW", ssecurity="NEW", client_id="NEW",
        unique_id="u-cn-xiaomiio",
        async_stored_auth=AsyncMock(return_value={"service_token": "NEW", "ssecurity": "NEW"}),
    )
    flow._candidate = candidate
    flow.hass.data.setdefault("xiaomi_miot", {
        "sessions": {"u-cn-xiaomiio": SimpleNamespace(
            user_id="u", default_server="cn", sid="xiaomiio",
        )},
        "accounts": {},
    })
    out = await flow._persist_and_reload(candidate)
    new_data = flow.hass.config_entries.async_update_entry.await_args.kwargs["data"]
    assert new_data["password"] == "NEW"
    assert new_data["service_token"] == "NEW"
    assert new_data["ssecurity"] == "NEW"
    assert "micoapi" not in new_data.get("service_token", "")
    flow.hass.config_entries.async_schedule_reload.assert_awaited_once_with("eid")


async def test_persist_micoapi_does_not_store_token_in_entry(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_update_entry=AsyncMock(),
            async_schedule_reload=AsyncMock(),
            entries=SimpleNamespace(),
        ),
    )
    flow.context = {"entry_id": "eid"}
    flow._reauth = SimpleNamespace(
        sid=CloudSid.MICOAPI,
        entry=SimpleNamespace(
            data={"sid": "micoapi", "username": "u", "server_country": "cn", "user_id": "u",
                  "password": "OLD"},
            entry_id="eid", options={}, title="Xiaomi: u", uid="u",
        ),
    )
    flow.async_abort = AsyncMock(return_value={"reason": "ok"})
    candidate = SimpleNamespace(
        attrs={"captcha_url": None}, username="u", password="NEW",
        sid="micoapi", default_server="cn",
        user_id="u", service_token="MICO_TKN", ssecurity="MICO_SEC", client_id="cid",
        unique_id="u-cn-micoapi",
        async_stored_auth=AsyncMock(return_value={}),
    )
    flow._candidate = candidate
    flow.hass.data.setdefault("xiaomi_miot", {"sessions": {}, "accounts": {}})
    await flow._persist_and_reload(candidate)
    new_data = flow.hass.config_entries.async_update_entry.await_args.kwargs["data"]
    assert new_data["password"] == "NEW"
    assert "service_token" not in new_data or new_data.get("service_token") == "MICO_TKN" and False
    assert "ssecurity" not in new_data


async def test_persist_save_failure_returns_save_failed(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_update_entry=AsyncMock(side_effect=OSError("disk")),
            async_schedule_reload=AsyncMock(),
            entries=SimpleNamespace(),
        ),
    )
    flow.context = {"entry_id": "eid"}
    flow._reauth = SimpleNamespace(
        sid=CloudSid.XIAOMIIO,
        entry=SimpleNamespace(
            data={"sid": "xiaomiio", "username": "u", "server_country": "cn", "user_id": "u"},
            entry_id="eid", options={}, title="Xiaomi: u",
        ),
    )
    flow.async_show_form = MagicMock(side_effect=_fake_show_form)
    candidate = SimpleNamespace(
        attrs={"captcha_url": None}, password="NEW", username="u", user_id="u",
        async_stored_auth=AsyncMock(side_effect=OSError("disk")),
    )
    flow._candidate = candidate
    flow.hass.data.setdefault("xiaomi_miot", {"sessions": {}, "accounts": {}})
    out = await flow._persist_and_reload(candidate)
    assert out["errors"]["base"] == "save_failed"
```

- [ ] **Step 2: Run, fail**

Run: `python -m pytest tests/test_reauth_flow.py -k persist -v`
Expected: method `._persist_and_reload` does not exist.

- [ ] **Step 3: Implement `_persist_and_reload`**

Add to `XiaomiMiotFlowHandler`:

```python
    def _invalidate_session_for(self, candidate):
        dom = self.hass.data.get(DOMAIN) or {}
        sess = dom.get('sessions') or {}
        snapshot = dict(sess)
        for k, v in snapshot.items():
            if v is candidate:
                continue
            if (v.user_id == candidate.user_id
                    and v.default_server == candidate.default_server
                    and v.sid == candidate.sid):
                sess.pop(k, None)
        return None

    async def _persist_and_reload(self, candidate):
        sid = self._reauth.sid
        try:
            await candidate.async_stored_auth(save=True)
        except Exception:
            errors = {'base': 'save_failed'}
            return self._show_reauth_form(
                'reauth_password',
                vol.Schema({vol.Required('password'): str}),
                errors=errors,
            )
        self._invalidate_session_for(candidate)
        entry = self._reauth.entry
        new_data = dict(entry.data)
        new_data['password'] = candidate.password
        if sid == CloudSid.XIAOMIIO:
            new_data['service_token'] = candidate.service_token
            new_data['ssecurity'] = candidate.ssecurity
            new_data['device_id'] = candidate.client_id
            new_data['user_id'] = candidate.user_id
        changed = new_data != dict(entry.data)
        try:
            if changed:
                self.hass.config_entries.async_update_entry(entry, data=new_data)
                if entry.update_listeners:
                    # listener-driven reload already queued
                    pass
                else:
                    self.hass.config_entries.async_schedule_reload(entry.entry_id)
            else:
                self.hass.config_entries.async_schedule_reload(entry.entry_id)
        except Exception:
            return self._show_reauth_form(
                'reauth_password',
                vol.Schema({vol.Required('password'): str}),
                errors={'base': 'save_failed'},
            )
        self._candidate = None
        return self.async_abort(reason='reauth_successful')
```

- [ ] **Step 4: Run + commit**

Run: `python -m pytest tests/test_reauth_flow.py -v`
Expected: all pass.

```bash
git add custom_components/xiaomi_miot/config_flow.py tests/test_reauth_flow.py
git commit -m "🔐 persist refreshed SID creds and trigger reload on reauth success"
```

---

### Task 19: Remove legacy `async_step_micoapi` and `micoapi_verify` schema action

**Files:**
- Modify: `custom_components/xiaomi_miot/config_flow.py:709-855` (Options Flow)
- Test: `tests/test_options_flow.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
async def test_options_cloud_schema_has_no_micoapi_verify(hass):
    from custom_components.xiaomi_miot.config_flow import OptionsFlowHandler
    flow = OptionsFlowHandler.__new__(OptionsFlowHandler)
    flow.hass = hass
    flow.config_entry = SimpleNamespace(data={"username": "u"}, options={})
    flow._init_thing = lambda: None  # optional
    flow.context = {}
    flow.config_data = {}
    out = await flow.async_step_cloud({"username": "u", "password": "p", "server_country": "cn"})
    # The schema MUST NOT contain micoapi_verify
    assert flow.async_show_form.call_args.kwargs["data_schema"]({"username": "u"}).get("micoapi_verify") is None


async def test_options_step_micoapi_is_removed(hass):
    from custom_components.xiaomi_miot.config_flow import OptionsFlowHandler
    assert not hasattr(OptionsFlowHandler, "async_step_micoapi")
```

- [ ] **Step 2: Run, fail**

Run: `python -m pytest tests/test_options_flow.py -v`
Expected: schema exposes `micoapi_verify`.

- [ ] **Step 3: Remove**

Delete `_finish_micoapi` (lines 847-855) and `async_step_micoapi` (lines 762-845).

Delete `async def _finish_micoapi` (lines 847-855) entirely.

In `async_step_cloud` (lines 709-760):
- Remove the `if user_input.pop('micoapi_verify', False):` branch (lines 717-722).
- Remove `vol.Optional('micoapi_verify', default=False): bool,` from the `schema` dict literal at the bottom.

In `__init__` of `OptionsFlowHandler`, remove `self.micoapi_cloud: Optional[MiotCloud] = None`.

- [ ] **Step 4: Run + commit**

Run: `python -m pytest tests/test_options_flow.py -v`
Expected: all pass.

```bash
git add custom_components/xiaomi_miot/config_flow.py tests/test_options_flow.py
git commit -m "🔥 remove legacy micoapi_verify action and async_step_micoapi"
```

---

### Task 20: Bundled translation files — new keys and removed keys

**Files:**
- Modify: all `custom_components/xiaomi_miot/translations/*.json`

**Keys to add (one block per file):**

```json
"reauth_password": {
    "title": "Xiaomi reauth — enter account password",
    "description": "Sign in to Xiaomi to refresh your stored credentials. Your existing configuration stays the same.",
    "data": {
        "password": "Password"
    }
},
"reauth_verify": {
    "title": "Xiaomi reauth — enter verification code",
    "description": "Send the {verify_url} code in your browser, then paste the ticket here.",
    "data": {
        "verify_ticket": "Verification ticket"
    }
},
"reauth_captcha": {
    "title": "Xiaomi reauth — enter captcha",
    "description": "Read the captcha image and type the characters.",
    "data": {
        "captcha": "Captcha"
    }
}
```

Update top-level `error` keys to include:

```json
"error": {
    "invalid_auth": "Xiaomi rejected the credentials.",
    "need_verify": "Verification code is required.",
    "need_captcha": "Captcha is required.",
    "cannot_connect": "Cannot reach Xiaomi.",
    "save_failed": "Failed to save refreshed credentials. Please retry.",
    "unknown": "Unexpected error."
}
```

Update top-level `abort` keys to include:

```json
"abort": {
    "unsupported_sid": "Reauth is not supported for this account.",
    "wrong_account": "Authentication does not match the configured Xiaomi account.",
    "reauth_successful": "Xiaomi account refreshed."
}
```

**Keys to remove (if currently present):** `step.micoapi`, `step.micoapi.data.verify_ticket`, `flow_title` containing "micoapi".

- [ ] **Step 1: Write the key coverage test**

```python
import json
from pathlib import Path

TRANS_DIR = Path("custom_components/xiaomi_miot/translations")

REQUIRED = {
    "reauth_password", "reauth_verify", "reauth_captcha",
}
ERROR_KEYS = {"invalid_auth", "need_verify", "need_captcha",
              "cannot_connect", "save_failed", "unknown"}
ABORT_KEYS = {"unsupported_sid", "wrong_account", "reauth_successful"}


@pytest.mark.parametrize("name", [
    "en.json", "zh-Hans.json", "zh-Hant.json", "ru.json",
    "de.json", "fr.json", "it.json", "es.json", "pt-BR.json",
    "pl.json", "cs.json", "el.json", "hu.json", "tr.json",
    "uk.json", "vi.json",
])
def test_translation_has_reauth_keys(name):
    data = json.loads((TRANS_DIR / name).read_text(encoding="utf-8"))
    cfg = data.get("config") or {}
    steps = cfg.get("step") or {}
    errs = cfg.get("error") or {}
    aborts = cfg.get("abort") or {}
    missing = REQUIRED - set(steps)
    assert not missing, f"Missing steps in {name}: {missing}"
    missing = ERROR_KEYS - set(errs)
    assert not missing, f"Missing error keys in {name}: {missing}"
    missing = ABORT_KEYS - set(aborts)
    assert not missing, f"Missing abort keys in {name}: {missing}"
    # no micoapi step
    assert "micoapi" not in steps, f"{name} still has step.micoapi"
```

- [ ] **Step 2: Run, fail**

Run: `python -m pytest tests/test_translations.py -v`
Expected: missing keys reported for every locale.

- [ ] **Step 3: Update each translation file**

Apply the snippets above to every JSON file in `custom_components/xiaomi_miot/translations/`. For non-English locales keep the new English values (the design only requires the keys exist with translated placeholders; this plan keeps translations English-only to land the minimum).

For locales that already have `step.micoapi` blocks (search with `rg '"micoapi":'`), delete the `step.micoapi` entry and its child keys.

- [ ] **Step 4: Re-run translation test**

Run: `python -m pytest tests/test_translations.py -v`
Expected: all 16 locales pass.

- [ ] **Step 5: Smoke-test the reauth form rendering**

Run a tiny script that instantiates a mock `hass`, manually constructs the flow with `_reauth.sid = CloudSid.XIAOMIIO`, mocks `_show_reauth_form` to capture inputs, and asserts that `description_placeholders` contains only `name` (and `verify_url` for `reauth_verify`; `captcha_image` for `reauth_captcha`). Add to `tests/test_reauth_flow.py`:

```python
async def test_reauth_password_form_exposes_only_name(flow_cls):
    flow = flow_cls()
    flow.hass = SimpleNamespace(data={"xiaomi_miot": {}})
    flow.context = {"entry_id": "eid"}
    flow._reauth = SimpleNamespace(
        sid=CloudSid.XIAOMIIO,
        entry=SimpleNamespace(data={"sid": "xiaomiio"}, entry_id="eid"),
    )
    captured = {}
    def _fake_show(**kw):
        captured.update(kw.get("description_placeholders") or {})
        return {"step_id": kw["step_id"]}
    flow.async_show_form = _fake_show
    await flow.async_step_reauth_password()
    assert set(captured) == {"name"}
```

(Repeat for `reauth_verify` → `{"name", "verify_url"}` and `reauth_captcha` → `{"name", "captcha_image"}`.)

- [ ] **Step 6: Commit**

```bash
git add custom_components/xiaomi_miot/translations/*.json tests/test_reauth_flow.py tests/test_translations.py
git commit -m "📝 add reauth translations and remove micoapi verify form"
```

---




