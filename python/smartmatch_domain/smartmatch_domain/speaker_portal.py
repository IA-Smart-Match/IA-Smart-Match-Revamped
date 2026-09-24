"""Speaker portal accounts: the invitation token, its TTL, and the activation rules.

B26 T6b-1 (``docs/plans/b26-tracks/T6b-1-plan.md`` §4, §5). The API (invite,
activation) and the worker (late-bound link) both import this module, so there
is exactly one derivation label and one token shape.

The token (owner ruling C1 = b)
===============================

``token = base64url_nopad(HMAC-SHA256(secret, TOKEN_DERIVATION_LABEL + str(invitation_id)))``

* 256 bits, 43 URL-safe characters. Derived, never stored: the database keeps
  only :func:`token_hash`, and the draft body carries
  :data:`ACTIVATION_URL_SENTINEL` until the worker renders the link at send.
* Both sides verify against the secret, not only the hash (R1). Rotating the
  secret therefore kills every live link on both sides.
* A later ``v2`` label is a new derivation, not an edit of this one.

Nothing here reads a clock. Callers pass ``now`` (R6).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import uuid
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

from smartmatch_domain.consent import ContactState
from smartmatch_domain.pilot_credentials import MINIMUM_PASSWORD_LENGTH

__all__ = [
    "ACTIVATABLE_CHANNEL_STATES",
    "ACTIVATION_URL_SENTINEL",
    "INVITATION_TTL",
    "INVITE_TEMPLATE_ID",
    "MAXIMUM_PASSWORD_LENGTH",
    "MINIMUM_PASSWORD_LENGTH",
    "TOKEN_DERIVATION_LABEL",
    "TOKEN_LENGTH",
    "PasswordPolicyError",
    "PortalAccessStatus",
    "check_new_password",
    "derive_status",
    "derive_token",
    "is_well_formed_token",
    "token_hash",
]

#: How long an invitation link lives. The schema caps it too
#: (``ck_speaker_portal_invitation_window``).
INVITATION_TTL: Final[timedelta] = timedelta(days=7)

#: The one versioned derivation label. The worker imports it; it never copies it.
TOKEN_DERIVATION_LABEL: Final[str] = "speaker-portal:v1:"

#: ``base64url_nopad`` of a 32-byte digest.
TOKEN_LENGTH: Final[int] = 43

_WELL_FORMED: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9_-]{43}")

#: The longest password activation accepts. The request model's 1024 bound only
#: limits parsing; this is the policy.
MAXIMUM_PASSWORD_LENGTH: Final[int] = 256

#: The invite template. Only the invite route composes it
#: (``smartmatch_domain.outreach.SYSTEM_ONLY_TEMPLATES``).
INVITE_TEMPLATE_ID: Final[str] = "cba.speaker_portal_invite.v1"

#: What the invite route passes as ``activation_url``. The stored draft carries
#: this, never a link; the worker replaces it with ``{base}/s/{token}`` in the
#: message it sends and leaves the stored body untouched.
ACTIVATION_URL_SENTINEL: Final[str] = "[[speaker-portal-activation-link]]"

#: Channel states from which an invitation may still be activated (R11). The
#: invite itself requires send-eligibility; by activation time the channel may
#: have moved, and only these two states still stand for the Speaker's consent.
ACTIVATABLE_CHANNEL_STATES: Final[frozenset[ContactState]] = frozenset(
    {ContactState.CONSENTED, ContactState.ACTIVE_CANDIDATE}
)


class PasswordPolicyError(ValueError):
    """A new password is outside the activation policy."""


class PortalAccessStatus(StrEnum):
    """What a Speaker Connector sees for one contact (plan L4)."""

    NONE = "none"
    INVITED = "invited"
    EXPIRED = "expired"
    ACTIVE = "active"


def derive_token(secret: str, invitation_id: uuid.UUID) -> str:
    """The activation token for ``invitation_id`` under ``secret``."""
    digest = hmac.new(
        secret.encode("utf-8"),
        f"{TOKEN_DERIVATION_LABEL}{invitation_id}".encode(),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def token_hash(token: str) -> bytes:
    """What the database stores: SHA-256 of the token, 32 bytes."""
    return hashlib.sha256(token.encode("utf-8")).digest()


def is_well_formed_token(token: str) -> bool:
    """43 URL-safe characters, checked before any database read."""
    return _WELL_FORMED.fullmatch(token) is not None


def check_new_password(password: str) -> None:
    """Refuse a password outside 12..256 characters, or one that is all whitespace.

    Raises:
        PasswordPolicyError: with a message that never quotes the password.
    """
    if not MINIMUM_PASSWORD_LENGTH <= len(password) <= MAXIMUM_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            f"a password must be {MINIMUM_PASSWORD_LENGTH} to {MAXIMUM_PASSWORD_LENGTH} characters"
        )
    if not password.strip():
        raise PasswordPolicyError("a password cannot be only whitespace")


def derive_status(
    *, account_bound: bool, live_expires_at: datetime | None, now: datetime
) -> PortalAccessStatus:
    """The Connector-facing status.

    Args:
        account_bound: ``speaker_profile.account_user_id IS NOT NULL``.
        live_expires_at: The ``expires_at`` of the profile's invitation that is
            neither accepted nor revoked, or ``None`` when there is none.
        now: The request's one clock reading.
    """
    if account_bound:
        return PortalAccessStatus.ACTIVE
    if live_expires_at is None:
        return PortalAccessStatus.NONE
    if live_expires_at > now:
        return PortalAccessStatus.INVITED
    return PortalAccessStatus.EXPIRED
