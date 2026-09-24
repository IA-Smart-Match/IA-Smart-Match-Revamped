"""``smartmatch_domain.speaker_portal``: token, TTL, password policy and status (B26 T6b-1).

Token-shaped values are built at runtime, never written as literals, so the
forbidden-behaviour scanner has nothing to flag.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import string
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from smartmatch_domain.consent import ContactState
from smartmatch_domain.pilot_credentials import MINIMUM_PASSWORD_LENGTH
from smartmatch_domain.speaker_portal import (
    ACTIVATABLE_CHANNEL_STATES,
    INVITATION_TTL,
    MAXIMUM_PASSWORD_LENGTH,
    TOKEN_DERIVATION_LABEL,
    PasswordPolicyError,
    PortalAccessStatus,
    check_new_password,
    derive_status,
    derive_token,
    is_well_formed_token,
    token_hash,
)

_SECRET_A = "a" * 40
_SECRET_B = "b" * 40
_NOW = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
_URLSAFE = set(string.ascii_letters + string.digits + "-_")


def test_token_is_256_bits_urlsafe() -> None:
    token = derive_token(_SECRET_A, uuid.uuid4())
    assert len(token) == 43
    assert set(token) <= _URLSAFE
    padded = token + "="
    assert len(base64.urlsafe_b64decode(padded)) == 32


def test_token_is_stable_per_invitation_and_secret() -> None:
    invitation_id = uuid.uuid4()
    assert derive_token(_SECRET_A, invitation_id) == derive_token(_SECRET_A, invitation_id)
    assert derive_token(_SECRET_A, invitation_id) != derive_token(_SECRET_A, uuid.uuid4())


def test_token_changes_with_the_secret() -> None:
    invitation_id = uuid.uuid4()
    assert derive_token(_SECRET_A, invitation_id) != derive_token(_SECRET_B, invitation_id)


def test_derivation_label_is_versioned() -> None:
    assert TOKEN_DERIVATION_LABEL == "speaker-portal:v1:"
    invitation_id = uuid.uuid4()
    digest = hmac.new(
        _SECRET_A.encode(), f"{TOKEN_DERIVATION_LABEL}{invitation_id}".encode(), hashlib.sha256
    ).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    assert derive_token(_SECRET_A, invitation_id) == expected


def test_token_hash_is_32_byte_sha256() -> None:
    token = derive_token(_SECRET_A, uuid.uuid4())
    assert token_hash(token) == hashlib.sha256(token.encode()).digest()
    assert len(token_hash(token)) == 32


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        ("x" * 43, True),
        ("A-_9" * 10 + "abc", True),
        ("x" * 42, False),
        ("x" * 44, False),
        ("x" * 42 + "=", False),
        ("x" * 42 + "/", False),
        ("", False),
    ],
)
def test_well_formed_token_is_43_urlsafe_chars(candidate: str, expected: bool) -> None:
    assert is_well_formed_token(candidate) is expected


def test_a_derived_token_is_well_formed() -> None:
    assert is_well_formed_token(derive_token(_SECRET_A, uuid.uuid4()))


def test_invitation_ttl_is_seven_days() -> None:
    assert timedelta(days=7) == INVITATION_TTL


@pytest.mark.parametrize(
    "candidate",
    [
        "x" * (MINIMUM_PASSWORD_LENGTH - 1),
        " " * 20,
        "\t\n " * 5,
        "x" * (MAXIMUM_PASSWORD_LENGTH + 1),
        "",
    ],
    ids=["short", "blank", "whitespace", "over-256", "empty"],
)
def test_password_policy_rejects_short_blank_and_over_256(candidate: str) -> None:
    with pytest.raises(PasswordPolicyError):
        check_new_password(candidate)


@pytest.mark.parametrize("length", [MINIMUM_PASSWORD_LENGTH, MAXIMUM_PASSWORD_LENGTH])
def test_password_policy_accepts_12_and_256(length: int) -> None:
    assert MINIMUM_PASSWORD_LENGTH == 12
    assert MAXIMUM_PASSWORD_LENGTH == 256
    check_new_password("y" * length)


def test_status_none_invited_expired_active() -> None:
    later = _NOW + timedelta(days=1)
    earlier = _NOW - timedelta(seconds=1)
    assert derive_status(account_bound=False, live_expires_at=None, now=_NOW) == (
        PortalAccessStatus.NONE
    )
    assert derive_status(account_bound=False, live_expires_at=later, now=_NOW) == (
        PortalAccessStatus.INVITED
    )
    assert derive_status(account_bound=False, live_expires_at=earlier, now=_NOW) == (
        PortalAccessStatus.EXPIRED
    )
    # Expiry is strict: a link at exactly its expiry is dead.
    assert derive_status(account_bound=False, live_expires_at=_NOW, now=_NOW) == (
        PortalAccessStatus.EXPIRED
    )
    assert derive_status(account_bound=True, live_expires_at=later, now=_NOW) == (
        PortalAccessStatus.ACTIVE
    )
    assert {status.value for status in PortalAccessStatus} == {
        "none",
        "invited",
        "expired",
        "active",
    }


def test_activatable_states_are_consented_and_active_candidate() -> None:
    assert frozenset({ContactState.CONSENTED, ContactState.ACTIVE_CANDIDATE}) == (
        ACTIVATABLE_CHANNEL_STATES
    )
