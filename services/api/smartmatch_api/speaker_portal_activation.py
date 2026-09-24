"""Activate a Speaker's new login from a portal invitation token (B26 T6b-1 plan §5).

One function, called by the JSON route (``POST /v1/speaker-portal/activate``,
which issues a session) and the no-JS form route (``POST /s/{token}``, which
does not, C4). The route charges the rate limit and checks the password policy
first (steps 1–2); this module is steps 3–15.

Lock order is **profile → invitation → address advisory lock → credential
rows**, the same as invite's profile → invitation (R5; T6b-5 plan §4.5). The
address lock, the credential row locks and every credential write belong to
:mod:`smartmatch_persistence.login_accounts`, the one ``pilot_credential``
writer (T6b-5 R-G). Every refusal raises the one
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
from smartmatch_persistence import login_accounts
from smartmatch_persistence.login_accounts import AddressState, LoginAccountError, NewLogin
from smartmatch_persistence.pilot_auth import PilotSessionRepository
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
    # Step 7 (R1): verified against the secret, not only the hash.
    if not hmac.compare_digest(token, derive_token(secret, invitation.id)):
        raise ActivationRefused
    # Steps 8–9: the address lock, then every credential row at the address plus
    # the contact account's own, FOR UPDATE (login_accounts, T6b-5 §4.2 step 9).
    login_accounts.lock_address(session, address=invitation.address)
    holders = login_accounts.holders_for_address(
        session,
        tenant_id=invitation.tenant_id,
        address=invitation.address,
        lock=True,
        also_lock_user_id=professional_id,
    )
    if holders.state is not AddressState.NONE or holders.also_locked_credentialed:
        # A second credential for the address, or a contact account that is
        # already a login (round-2 gate): new-login mode never replaces one.
        raise ActivationRefused

    _bind(session, invitation=invitation, new_password=new_password, now=now)

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
    session: Session, *, invitation: InvitationForActivation, new_password: str, now: datetime
) -> None:
    """Steps 10–14. Any failure propagates and the route's session rolls back."""
    tenant_id: uuid.UUID = invitation.tenant_id
    professional_id: uuid.UUID = invitation.professional_id
    try:
        grant = login_accounts.find_or_add_role(
            session,
            tenant_id=tenant_id,
            email=invitation.address,
            role="speaker",
            path=invitation.owning_unit_path,
            now=now,
            create=NewLogin(
                user_id=professional_id,
                password=derive_password_hash(new_password, salt=new_salt()),
            ),
        )
    except LoginAccountError as exc:
        raise ActivationRefused from exc
    if grant.user_id != professional_id or not grant.login_created:
        raise ActivationRefused
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
        binding_mode="new_login",
        now=now,
    ):
        raise ActivationRefused
