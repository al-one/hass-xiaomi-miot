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