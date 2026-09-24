"""Activate a Speaker portal login from an invitation token (B26 T6b-1 §5, T6b-5 §4.2).

One function, :func:`activate`, called by the JSON route (``POST
/v1/speaker-portal/activate``, which issues a session) and the no-JS form route
(``POST /s/{token}``, which does not, C4). The route charges the rate limit and
checks the new password's policy first (steps 1–3); this module is the rest.

**Two modes, chosen under the locks** (T6b-5 §4.2 step 10), never by the caller:

``new_login``
    No credentialed account holds the invited address. The contact account
    becomes the login: its email is set, it gets its first credential and the
    ``speaker`` role.
``existing_login``
    Exactly one credentialed account in this tenant holds the address — an
    Event Host's login (Q1: an active ``volunteer`` role and no active staff
    or student role; :func:`existing_login_may_bind`). The Speaker proves
    it with that login's password; the login gains ``speaker``. No email, no
    credential and no account is written. The contact account keeps its
    ``.invalid`` email and no credential (R-B).

The caller sends exactly one of ``new_password`` / ``existing_password``. The
other is :class:`ActivationModeMismatch` (409), reached only after the token is
verified, so only the invitee learns the mode (Q5).

Lock order is **profile → invitation → address advisory lock → credential
rows** (T6b-5 §4.5), the same as invite's profile → invitation. The address
lock, the credential row locks and every credential write belong to
:mod:`smartmatch_persistence.login_accounts`, the one ``pilot_credential``
writer (R-G). Every other refusal raises the one :class:`ActivationRefused`,
which the routes answer with one status, code and body. Nothing here commits:
the route commits once, and on any exception the request session rolls back.
"""

from __future__ import annotations

import hmac
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

from smartmatch_domain.pilot_credentials import (
    SESSION_TTL,
    derive_password_hash,
    hash_session_token,
    new_salt,
    new_session_token,
    verify_password,
)
from smartmatch_domain.speaker_portal import (
    ACTIVATABLE_CHANNEL_STATES,
    derive_token,
    is_well_formed_token,
    token_hash,
)
from smartmatch_persistence import login_accounts
from smartmatch_persistence.login_accounts import (
    AddressHolders,
    AddressState,
    LoginAccountError,
    LoginHolder,
    NewLogin,
)
from smartmatch_persistence.pilot_auth import PilotSessionRepository
from smartmatch_persistence.speaker_portal import (
    InvitationForActivation,
    SpeakerPortalRepository,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

__all__ = [
    "EXISTING_LOGIN_ALLOWED_ROLES",
    "ActivationCredentialsInvalid",
    "ActivationMode",
    "ActivationModeMismatch",
    "ActivationRefused",
    "ActivationResult",
    "IssuedSession",
    "activate",
    "existing_login_may_bind",
    "page_mode",
]

_portal: Final[SpeakerPortalRepository] = SpeakerPortalRepository()
_ACTIVATABLE_STATES: Final[frozenset[str]] = frozenset(
    state.value for state in ACTIVATABLE_CHANNEL_STATES
)

#: Q1 (owner ruling, amended 2026-09-24 from a deny-list; tightened
#: 2026-09-24 on #224 LOW row 10): existing-login mode binds Event Host logins
#: only, as a **true allow-list**. Apart from ``speaker``, a holder's active
#: roles must be exactly these — any other role, including one this code does
#: not know yet, refuses. This also keeps T6b-1 §11's self-invite mitigation: a
#: Connector's own address is a staff login, so inviting it never binds the
#: Connector as a Speaker.
EXISTING_LOGIN_ALLOWED_ROLES: Final[frozenset[str]] = frozenset({"volunteer"})

#: The one role activation grants (never a seed: INVITATION_ONLY_ROLES).
_SPEAKER_ROLE: Final[str] = "speaker"

#: ``speaker`` neither qualifies nor disqualifies a login (``speaker`` and
#: ``volunteer`` never widen each other), so the rule ignores it.
_ROLE_THE_RULE_IGNORES: Final[frozenset[str]] = frozenset({_SPEAKER_ROLE})


def existing_login_may_bind(held: frozenset[str]) -> bool:
    """Q1, the one rule: may a login holding ``held`` (its *active* roles) gain ``speaker``?

    ``True`` only when ``volunteer`` is held and, ``speaker`` aside, nothing
    else is: ``held - {"speaker"} == {"volunteer"}``. A login with no active
    role, only expired roles, only ``speaker``, or ``volunteer`` plus any other
    role (staff, student, or one this code does not know) is refused: at
    activation with the generic 400, at invite with ``409
    speaker_portal_address_not_host_login`` — one body for every reason.
    """
    return held - _ROLE_THE_RULE_IGNORES == EXISTING_LOGIN_ALLOWED_ROLES


class ActivationMode(StrEnum):
    NEW_LOGIN = "new_login"
    EXISTING_LOGIN = "existing_login"


class ActivationRefused(Exception):
    """Every refusal but the two below. Carries nothing, so no caller can tell two apart."""


class ActivationCredentialsInvalid(Exception):
    """Existing-login mode, wrong password (401). The token stays live."""


class ActivationModeMismatch(Exception):
    """The body carried the other password field (409). Nothing written."""

    def __init__(self, expected: ActivationMode) -> None:
        super().__init__(expected.value)
        self.expected = expected


@dataclass(frozen=True, slots=True)
class IssuedSession:
    token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ActivationResult:
    mode: ActivationMode
    user_id: uuid.UUID
    session: IssuedSession | None


def activate(
    session: Session,
    *,
    token: str,
    new_password: str | None,
    existing_password: str | None,
    secret: str,
    now: datetime,
    issue_session: bool,
) -> ActivationResult:
    """Bind the invitation's profile to a login and grant ``speaker``.

    Exactly one of ``new_password`` / ``existing_password`` is given (the route
    validates the body shape).

    Raises:
        ActivationRefused: every refusal in T6b-1 §5 and T6b-5 §4.2, identically.
        ActivationModeMismatch: the other password field was expected.
        ActivationCredentialsInvalid: existing-login mode, wrong password.
    """
    if (new_password is None) == (existing_password is None):
        raise ValueError("exactly one of new_password and existing_password is required")
    supplied = (
        ActivationMode.NEW_LOGIN if new_password is not None else ActivationMode.EXISTING_LOGIN
    )

    invitation = _verified_invitation(session, token=token, secret=secret, now=now, lock=True)
    professional_id = invitation.professional_id
    # Step 9: the address lock, then every credential row at the address plus
    # the contact account's own, FOR UPDATE, in one statement ordered by id.
    login_accounts.lock_address(session, address=invitation.address)
    holders = login_accounts.holders_for_address(
        session,
        tenant_id=invitation.tenant_id,
        address=invitation.address,
        lock=True,
        also_lock_user_id=professional_id,
    )
    mode, holder = _choose_mode(session, invitation=invitation, holders=holders, now=now)
    # Step 11: only a verified invitee gets this far, so only they learn the mode.
    if mode is not supplied:
        raise ActivationModeMismatch(expected=mode)

    create: NewLogin | None = None
    if mode is ActivationMode.EXISTING_LOGIN:
        assert holder is not None and existing_password is not None
        # Step 12: the password first, then suspension — a suspended login is
        # named only to someone who proved they hold it.
        if not verify_password(existing_password, holder.password):
            raise ActivationCredentialsInvalid
        if holder.suspended:
            raise ActivationRefused
        expected_user = holder.user_id
    else:
        assert new_password is not None
        create = NewLogin(
            user_id=professional_id,
            password=derive_password_hash(new_password, salt=new_salt()),
        )
        expected_user = professional_id

    bound_user = _bind(
        session,
        invitation=invitation,
        mode=mode,
        create=create,
        expected_user=expected_user,
        now=now,
    )

    if not issue_session:
        return ActivationResult(mode=mode, user_id=bound_user, session=None)
    session_token = new_session_token()
    expires_at = now + SESSION_TTL
    PilotSessionRepository().issue(
        session,
        tenant_id=invitation.tenant_id,
        user_id=bound_user,
        token_hash=hash_session_token(session_token),
        issued_at=now,
        expires_at=expires_at,
    )
    return ActivationResult(
        mode=mode,
        user_id=bound_user,
        session=IssuedSession(token=session_token, expires_at=expires_at),
    )


def page_mode(session: Session, *, token: str, secret: str, now: datetime) -> ActivationMode | None:
    """The mode a live, verified token would activate in, or ``None``.

    ``GET /s/{token}``'s read (T6b-5 §4.2 "/s pages"). **Reads only**: no lock,
    no write, no rate-limit charge. ``None`` for every token that would be
    refused, so the page for those is T6b-1's bytes.
    """
    try:
        invitation = _verified_invitation(session, token=token, secret=secret, now=now, lock=False)
        holders = login_accounts.holders_for_address(
            session,
            tenant_id=invitation.tenant_id,
            address=invitation.address,
            lock=False,
            also_lock_user_id=invitation.professional_id,
        )
        mode, _holder = _choose_mode(session, invitation=invitation, holders=holders, now=now)
    except ActivationRefused:
        return None
    return mode


def _verified_invitation(
    session: Session, *, token: str, secret: str, now: datetime, lock: bool
) -> InvitationForActivation:
    """Steps 4–8: shape, lookup, profile lock, invitation lock and re-checks, HMAC."""
    if not is_well_formed_token(token):
        raise ActivationRefused
    match = _portal.find_invitation_by_token_hash(session, token_hash=token_hash(token))
    if match is None:
        raise ActivationRefused
    # The profile lock first — as in invite and unbind.
    profile = _portal.lock_profile(
        session, tenant_id=match.tenant_id, professional_id=match.professional_id, lock=lock
    )
    if profile is None:
        raise ActivationRefused
    invitation = _portal.lock_invitation(
        session, tenant_id=match.tenant_id, invitation_id=match.invitation_id, lock=lock
    )
    if invitation is None or _is_unusable(invitation, now=now):
        raise ActivationRefused
    # R1: verified against the secret, not only the hash.
    if not hmac.compare_digest(token, derive_token(secret, invitation.id)):
        raise ActivationRefused
    return invitation


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


def _choose_mode(
    session: Session,
    *,
    invitation: InvitationForActivation,
    holders: AddressHolders,
    now: datetime,
) -> tuple[ActivationMode, LoginHolder | None]:
    """Step 10 (T6b-5 §4.2 table). Every refusal is :class:`ActivationRefused`."""
    professional_id = invitation.professional_id
    if holders.state is AddressState.NONE:
        if holders.also_locked_credentialed:
            # T6b-1 round-2 rule: a credentialed contact account is never re-passworded.
            raise ActivationRefused
        return ActivationMode.NEW_LOGIN, None
    if holders.state is not AddressState.ONE_IN_TENANT or holders.holder is None:
        # R-E (ambiguous), R-F (other tenant).
        raise ActivationRefused
    holder = holders.holder
    if holder.user_id != professional_id and holders.also_locked_credentialed:
        # R-B: a merged contact account must stay credential-less.
        raise ActivationRefused
    if _portal.login_bound_elsewhere(
        session,
        tenant_id=invitation.tenant_id,
        account_user_id=holder.user_id,
        excluding_professional_id=professional_id,
    ):
        # One login speaks for one Speaker (uq_speaker_profile_account).
        raise ActivationRefused
    held = _portal.active_roles(
        session, tenant_id=invitation.tenant_id, user_id=holder.user_id, now=now
    )
    if not existing_login_may_bind(held):
        # Q1: Event Host logins only (an allow-list).
        raise ActivationRefused
    return ActivationMode.EXISTING_LOGIN, holder


def _bind(
    session: Session,
    *,
    invitation: InvitationForActivation,
    mode: ActivationMode,
    create: NewLogin | None,
    expected_user: uuid.UUID,
    now: datetime,
) -> uuid.UUID:
    """Steps 13–15. Any failure propagates and the route's session rolls back."""
    tenant_id: uuid.UUID = invitation.tenant_id
    professional_id: uuid.UUID = invitation.professional_id
    try:
        # Re-takes the address lock and re-reads the same locked rows
        # (re-entrant, same answer).
        grant = login_accounts.find_or_add_role(
            session,
            tenant_id=tenant_id,
            email=invitation.address,
            role=_SPEAKER_ROLE,
            path=invitation.owning_unit_path,
            now=now,
            create=create,
        )
    except LoginAccountError as exc:
        raise ActivationRefused from exc
    if grant.user_id != expected_user or grant.login_created != (create is not None):
        raise ActivationRefused
    try:
        bound = _portal.bind_profile(
            session,
            tenant_id=tenant_id,
            professional_id=professional_id,
            account_user_id=grant.user_id,
            now=now,
        )
    except IntegrityError as exc:
        # uq_speaker_profile_account: defence in depth behind _choose_mode.
        raise ActivationRefused from exc
    if not bound:
        raise ActivationRefused
    if not _portal.accept_invitation(
        session,
        tenant_id=tenant_id,
        invitation_id=invitation.id,
        bound_account_user_id=grant.user_id,
        binding_mode=mode.value,
        now=now,
    ):
        raise ActivationRefused
    return grant.user_id
