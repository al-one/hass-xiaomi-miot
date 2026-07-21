"""Tests for bundled Xiaomi Miot translations."""
import json
from pathlib import Path

import pytest


TRANS_DIR = Path("custom_components/xiaomi_miot/translations")
TRANSLATIONS = sorted(path.name for path in TRANS_DIR.glob("*.json"))
REAUTH_STEPS = {"reauth_password", "reauth_verify", "reauth_captcha"}
ERROR_KEYS = {
    "invalid_auth",
    "need_verify",
    "need_captcha",
    "cannot_connect",
    "save_failed",
    "unknown",
}
ABORT_KEYS = {"unsupported_sid", "wrong_account", "reauth_successful"}


@pytest.mark.parametrize("name", TRANSLATIONS)
def test_translation_has_reauth_keys_without_legacy_micoapi(name):
    data = json.loads((TRANS_DIR / name).read_text(encoding="utf-8"))
    config = data.get("config") or {}
    steps = config.get("step") or {}

    assert not REAUTH_STEPS - set(steps)
    assert not ERROR_KEYS - set(config.get("error") or {})
    assert not ABORT_KEYS - set(config.get("abort") or {})
    assert "{verify_url}" in steps["reauth_verify"]["description"]
    assert "{captcha_image}" in steps["reauth_captcha"]["description"]

    option_steps = (data.get("options") or {}).get("step") or {}
    assert "micoapi" not in option_steps
    cloud = option_steps.get("cloud") or {}
    assert "micoapi_verify" not in (cloud.get("data") or {})
    assert "micoapi_verify" not in (cloud.get("data_description") or {})
