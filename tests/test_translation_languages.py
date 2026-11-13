from copy import deepcopy

import pytest

from custom_components.xiaomi_miot.core.translation_languages import TRANSLATION_LANGUAGES

_ORIGINAL_TRANSLATIONS: dict | None = None


@pytest.fixture(autouse=True)
def _protect_translations():
    global _ORIGINAL_TRANSLATIONS
    if _ORIGINAL_TRANSLATIONS is None:
        _ORIGINAL_TRANSLATIONS = deepcopy(dict(TRANSLATION_LANGUAGES))
    yield
    TRANSLATION_LANGUAGES.clear()
    TRANSLATION_LANGUAGES.update(deepcopy(_ORIGINAL_TRANSLATIONS))


def test_all_languages_are_dicts():
    for lang, value in TRANSLATION_LANGUAGES.items():
        assert isinstance(value, dict), f"{lang} is not a dict"


def test_all_translation_dicts_are_nonempty():
    empty = [
        f"{lang}.{k}"
        for lang, entries in TRANSLATION_LANGUAGES.items()
        for k, v in entries.items()
        if isinstance(v, dict) and not v
    ]
    assert not empty, f"empty sub-dicts: {empty}"


async def test_auto_detect_pt_PT_promotes_pt(hass):
    from custom_components.xiaomi_miot import async_reload_integration_config

    hass.data.setdefault("xiaomi_miot", {})["config"] = {}
    hass.config.language = "pt-PT"
    await async_reload_integration_config(hass, {})

    assert TRANSLATION_LANGUAGES.get("idle") == "Parado"


async def test_auto_detect_pt_BR_fallsback_to_pt(hass):
    from custom_components.xiaomi_miot import async_reload_integration_config

    hass.data.setdefault("xiaomi_miot", {})["config"] = {}
    hass.config.language = "pt-BR"
    await async_reload_integration_config(hass, {})

    assert TRANSLATION_LANGUAGES.get("idle") == "Parado"


async def test_auto_detect_de_promotes_de(hass):
    from custom_components.xiaomi_miot import async_reload_integration_config

    hass.data.setdefault("xiaomi_miot", {})["config"] = {}
    hass.config.language = "de"
    await async_reload_integration_config(hass, {})

    assert TRANSLATION_LANGUAGES.get("idle") == "Inaktiv"


async def test_yaml_language_takes_precedence(hass):
    from custom_components.xiaomi_miot import async_reload_integration_config

    hass.data.setdefault("xiaomi_miot", {})["config"] = {}
    hass.config.language = "pt-PT"
    await async_reload_integration_config(hass, {"language": "de"})

    assert TRANSLATION_LANGUAGES.get("idle") == "Inaktiv"


async def test_no_language_auto_promotes_nothing(hass):
    from custom_components.xiaomi_miot import async_reload_integration_config

    hass.data.setdefault("xiaomi_miot", {})["config"] = {}
    hass.config.language = ""
    await async_reload_integration_config(hass, {})

    assert TRANSLATION_LANGUAGES.get("idle") is None
