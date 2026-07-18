"""Tests for CloudSid, REAUTH_SIDS, and the narrow auth exception types."""
import pytest

from custom_components.xiaomi_miot.core.xiaomi_cloud import (
    CloudSid,
    MiCloudAuthenticationError,
    MiCloudAccessDenied,
    MiCloudException,
    MiCloudStsUnauthorized,
    MiCloudVerificationError,
    REAUTH_SIDS,
)


def test_cloud_sid_values_are_strings():
    assert CloudSid.XIAOMIIO == 'xiaomiio'
    assert CloudSid.MICOAPI == 'micoapi'
    assert CloudSid.I_MI_COM == 'i.mi.com'
    # StrEnum members are str subclasses.
    assert isinstance(CloudSid.XIAOMIIO, str)


def test_cloud_sid_construct_from_string():
    assert CloudSid('xiaomiio') is CloudSid.XIAOMIIO
    assert CloudSid('micoapi') is CloudSid.MICOAPI


def test_cloud_sid_rejects_unknown_value():
    with pytest.raises(ValueError):
        CloudSid('not-a-sid')


def test_reauth_sids_excludes_imicom():
    assert REAUTH_SIDS == frozenset({CloudSid.XIAOMIIO, CloudSid.MICOAPI})
    assert CloudSid.I_MI_COM not in REAUTH_SIDS


def test_narrow_exceptions_subclass_micloud_access_denied():
    for cls in (
        MiCloudAuthenticationError,
        MiCloudVerificationError,
        MiCloudStsUnauthorized,
    ):
        assert issubclass(cls, MiCloudAccessDenied)


def test_narrow_exceptions_carry_fixed_message():
    for cls in (
        MiCloudAuthenticationError,
        MiCloudVerificationError,
        MiCloudStsUnauthorized,
    ):
        inst = cls('boom')
        assert 'boom' in str(inst)