"""Activate a Speaker's new login from a portal invitation token (B26 T6b-1 plan §5).

One function, called by the JSON route (``POST /v1/speaker-portal/activate``,
which issues a session) and the no-JS form route (``POST /s/{token}``, which
does not, C4). The route charges the rate limit and checks the password policy
first (steps 1–2); this module is steps 3–15.

Lock order is **profile → invitation → address advisory lock**, the same as
invite's profile → invitation (R5). Every refusal raises the one
:class:`ActivationRefused`, which the routes answer with one status, code and
body. Nothing here commits: the route commits once (step 16), and on any
exception ``get_session`` rolls back, so nothing from steps 10–15 persists.
"""

from __future__ import annotations

import hmac
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from smartmatch_domain.pilot_credentials import (
    SESSION_TTL,
    derive_password_hash,
    hash_session_token,
    new_salt,
    new_session_token,
)
from smartmatch_domain.speaker_portal import (
    ACTIVATABLE_CHANNEL_STATES,
    derive_token,
    is_well_formed_token,
    token_hash,
)
from smartmatch_persistence.pilot_auth import PilotCredentialRepository, PilotSessionRepository
from smartmatch_persistence.speaker_portal import (
    InvitationForActivation,
    SpeakerPortalRepository,
)
from sqlalchemy.orm import Session

__all__ = ["ActivationRefused", "IssuedSession", "activate_new_login"]

_portal: Final[SpeakerPortalRepository] = SpeakerPortalRepository()
_ACTIVATABLE_STATES: Final[frozenset[str]] = frozenset(
    state.value for state in ACTIVATABLE_CHANNEL_STATES
)


class ActivationRefused(Exception):
    """Every §5 refusal. Carries nothing, so no caller can tell two apart."""


@dataclass(frozen=True, slots=True)
class IssuedSession:
    token: str
    expires_at: datetime


def activate_new_login(
    session: Session,
    *,
    token: str,
    new_password: str,
    secret: str,
    now: datetime,
    issue_session: bool,
) -> IssuedSession | None:
    """Bind the invitation's contact account as a new ``speaker`` login.

    Returns:
        The issued session when ``issue_session`` is true, else ``None``.

    Raises:
        ActivationRefused: for every refusal in plan §5, identically.
    """
    # Step 3: shape first, with no database read.
    if not is_well_formed_token(token):
        raise ActivationRefused
    # Step 4: find, without a lock.
    match = _portal.find_invitation_by_token_hash(session, token_hash=token_hash(token))
    if match is None:
        raise ActivationRefused
    # Step 5: the profile lock, first — as in invite.
    profile = _portal.lock_profile(
        session, tenant_id=match.tenant_id, professional_id=match.professional_id
    )
    if profile is None:
        raise ActivationRefused
    # Step 6: the invitation lock, and every re-check under it.
    invitation = _portal.lock_invitation(
        session, tenant_id=match.tenant_id, invitation_id=match.invitation_id
    )
    if invitation is None or _is_unusable(invitation, now=now):
        raise ActivationRefused
    professional_id = invitation.professional_id
    if _portal.account_has_credential(
        session, tenant_id=invitation.tenant_id, user_id=professional_id
    ):
        # The contact account is already a login (round-2 gate). New-login mode
        # never replaces an existing password; existing-login mode is T6b-5.
        raise ActivationRefused
    # Step 7 (R1): verified against the secret, not only the hash.
    if not hmac.compare_digest(token, derive_token(secret, invitation.id)):
        raise ActivationRefused
    # Steps 8–9: serialize new logins for this address; refuse a second one.
    # Normalised once, here, and that one value is what the lock, the check and
    # the stored email all see.
    folded_address = invitation.address.strip().lower()
    _portal.lock_address(session, folded_address=folded_address)
    if _portal.other_credentialed_account_exists(
        session, folded_address=folded_address, excluding_user_id=professional_id
    ):
        raise ActivationRefused

    _bind(
        session,
        invitation=invitation,
        folded_address=folded_address,
        new_password=new_password,
        now=now,
    )

    if not issue_session:
        return None
    # Step 15.
    session_token = new_session_token()
    expires_at = now + SESSION_TTL
    PilotSessionRepository().issue(
        session,
        tenant_id=invitation.tenant_id,
        user_id=professional_id,
        token_hash=hash_session_token(session_token),
        issued_at=now,
        expires_at=expires_at,
    )
    return IssuedSession(token=session_token, expires_at=expires_at)


def _is_unusable(invitation: InvitationForActivation, *, now: datetime) -> bool:
    return (
        invitation.accepted_at is not None
        or invitation.revoked_at is not None
        or invitation.expires_at <= now
        or invitation.profile_bound
        or invitation.channel_kind != "email"
        or invitation.contact_state not in _ACTIVATABLE_STATES
        or invitation.account_suspended
    )


def _bind(
    session: Session,
    *,
    invitation: InvitationForActivation,
    folded_address: str,
    new_password: str,
    now: datetime,
) -> None:
    """Steps 10–14. Any failure propagates and the route's session rolls back."""
    tenant_id: uuid.UUID = invitation.tenant_id
    professional_id: uuid.UUID = invitation.professional_id
    _portal.set_account_email(
        session, tenant_id=tenant_id, user_id=professional_id, folded_address=folded_address
    )
    PilotCredentialRepository().upsert(
        session,
        tenant_id=tenant_id,
        user_id=professional_id,
        password=derive_password_hash(new_password, salt=new_salt()),
        now=now,
    )
    _portal.grant_speaker_membership(
        session,
        tenant_id=tenant_id,
        user_id=professional_id,
        granted_path=invitation.owning_unit_path,
        now=now,
    )
    if not _portal.bind_profile(
        session,
        tenant_id=tenant_id,
        professional_id=professional_id,
        account_user_id=professional_id,
        now=now,
    ):
        raise ActivationRefused
    if not _portal.accept_invitation(
        session,
        tenant_id=tenant_id,
        invitation_id=invitation.id,
        bound_account_user_id=professional_id,
        now=now,
    ):
        raise ActivationRefused
