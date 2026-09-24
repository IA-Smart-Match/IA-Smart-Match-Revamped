"""The Speaker portal read/write path (migration ``0039``, B26 T6b-1).

Rules every method here keeps (plan §3.2, §4.6, §5):

* **Never commits.** The route, or the command it submits, owns the transaction.
* **Every timestamp is a parameter** (R6). No statement here calls ``now()``.
* **Lock order is profile → invitation → address → credential rows**, in
  invite, activation and unbind alike (B26 T6b-5 plan §4.5).
  :meth:`SpeakerPortalRepository.lock_profile` is the first lock in all three;
  :meth:`~SpeakerPortalRepository.find_invitation_by_token_hash` takes none, so
  activation can find the profile before locking anything. The address and
  credential locks are :mod:`smartmatch_persistence.login_accounts`'s, which is
  also the only writer of ``pilot_credential``, of a login's email, and of the
  ``speaker`` membership.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = [
    "BoundInvitation",
    "BoundSpeakerProfile",
    "CurrentInvitation",
    "InvitationForActivation",
    "InvitationForSend",
    "LockedProfile",
    "SpeakerPortalRepository",
    "TokenMatch",
]

_INV = schema.speaker_portal_invitation
_PROFILE = schema.speaker_profile


@dataclass(frozen=True, slots=True)
class LockedProfile:
    tenant_id: uuid.UUID
    professional_id: uuid.UUID
    owning_unit_id: uuid.UUID
    full_name: str
    account_user_id: uuid.UUID | None
    account_bound_at: datetime | None


@dataclass(frozen=True, slots=True)
class BoundSpeakerProfile:
    """The profile a signed-in Speaker's login is bound to (B26 T6b-2).

    ``professional_id`` keys every row the Speaker reads or writes; it is never
    the login id (after T6b-5's merged login the two differ).
    ``owning_unit_path`` is what the ``speaker`` role is checked against.
    """

    professional_id: uuid.UUID
    owning_unit_id: uuid.UUID
    owning_unit_path: str


@dataclass(frozen=True, slots=True)
class TokenMatch:
    tenant_id: uuid.UUID
    professional_id: uuid.UUID
    invitation_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class InvitationForActivation:
    """An invitation row joined with what activation must re-check under lock."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    professional_id: uuid.UUID
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    profile_bound: bool
    channel_kind: str
    contact_state: str
    address: str
    owning_unit_path: str
    account_suspended: bool


@dataclass(frozen=True, slots=True)
class InvitationForSend:
    id: uuid.UUID
    owning_unit_id: uuid.UUID
    contact_channel_id: uuid.UUID
    token_hash: bytes
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None


@dataclass(frozen=True, slots=True)
class CurrentInvitation:
    id: uuid.UUID
    contact_channel_id: uuid.UUID
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class BoundInvitation:
    """The accepted invitation that made a profile's current binding (T6b-5 §4.4)."""

    id: uuid.UUID
    binding_mode: str


def _live() -> sa.ColumnElement[bool]:
    return sa.and_(_INV.c.accepted_at.is_(None), _INV.c.revoked_at.is_(None))


class SpeakerPortalRepository:
    """Reads and writes ``speaker_portal_invitation`` and the profile binding."""

    # -- profile -----------------------------------------------------------

    def lock_profile(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        professional_id: uuid.UUID,
        owning_unit_id: uuid.UUID | None = None,
        lock: bool = True,
    ) -> LockedProfile | None:
        """``SELECT … FROM speaker_profile … FOR UPDATE``: the first lock everywhere."""
        statement = sa.select(
            _PROFILE.c.tenant_id,
            _PROFILE.c.professional_id,
            _PROFILE.c.owning_unit_id,
            _PROFILE.c.full_name,
            _PROFILE.c.account_user_id,
            _PROFILE.c.account_bound_at,
        ).where(_PROFILE.c.tenant_id == tenant_id, _PROFILE.c.professional_id == professional_id)
        if owning_unit_id is not None:
            statement = statement.where(_PROFILE.c.owning_unit_id == owning_unit_id)
        if lock:
            statement = statement.with_for_update()
        row = session.execute(statement).one_or_none()
        return None if row is None else LockedProfile(**row._mapping)

    def find_bound_profile(
        self, session: Session, *, tenant_id: uuid.UUID, account_user_id: uuid.UUID
    ) -> BoundSpeakerProfile | None:
        """The profile bound to ``account_user_id`` in ``tenant_id``, or ``None``.

        At most one row (``uq_speaker_profile_account``). Takes no lock: the
        Speaker's own routes read, or write rows keyed by the profile.
        """
        unit = schema.org_unit
        row = session.execute(
            sa.select(
                _PROFILE.c.professional_id,
                _PROFILE.c.owning_unit_id,
                sa.cast(unit.c.path, sa.Text).label("owning_unit_path"),
            )
            .select_from(
                _PROFILE.join(
                    unit,
                    sa.and_(
                        unit.c.tenant_id == _PROFILE.c.tenant_id,
                        unit.c.id == _PROFILE.c.owning_unit_id,
                    ),
                )
            )
            .where(
                _PROFILE.c.tenant_id == tenant_id,
                _PROFILE.c.account_user_id == account_user_id,
            )
        ).one_or_none()
        return None if row is None else BoundSpeakerProfile(**row._mapping)

    # -- invitations -------------------------------------------------------

    def revoke_live(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        professional_id: uuid.UUID,
        revoked_at: datetime,
    ) -> bool:
        """Revoke the profile's live invitation, if any. ``True`` when one was revoked."""
        result = session.execute(
            sa.update(_INV)
            .where(
                _INV.c.tenant_id == tenant_id,
                _INV.c.professional_id == professional_id,
                _live(),
            )
            .values(revoked_at=revoked_at)
            .returning(_INV.c.id)
        ).all()
        return bool(result)

    def insert_invitation(
        self,
        session: Session,
        *,
        invitation_id: uuid.UUID,
        tenant_id: uuid.UUID,
        professional_id: uuid.UUID,
        contact_channel_id: uuid.UUID,
        issued_by_user_id: uuid.UUID,
        token_hash: bytes,
        issued_at: datetime,
        expires_at: datetime,
    ) -> None:
        session.execute(
            sa.insert(_INV).values(
                id=invitation_id,
                tenant_id=tenant_id,
                professional_id=professional_id,
                contact_channel_id=contact_channel_id,
                issued_by_user_id=issued_by_user_id,
                token_hash=token_hash,
                issued_at=issued_at,
                expires_at=expires_at,
            )
        )

    def current_for_profile(
        self, session: Session, *, tenant_id: uuid.UUID, professional_id: uuid.UUID
    ) -> CurrentInvitation | None:
        """The live (neither accepted nor revoked) invitation, expired or not."""
        row = session.execute(
            sa.select(_INV.c.id, _INV.c.contact_channel_id, _INV.c.issued_at, _INV.c.expires_at)
            .where(
                _INV.c.tenant_id == tenant_id,
                _INV.c.professional_id == professional_id,
                _live(),
            )
            .limit(1)
        ).one_or_none()
        return None if row is None else CurrentInvitation(**row._mapping)

    def find_invitation_by_token_hash(
        self, session: Session, *, token_hash: bytes
    ) -> TokenMatch | None:
        """Look the invitation up by hash, across tenants. **Takes no lock.**"""
        row = session.execute(
            sa.select(_INV.c.tenant_id, _INV.c.professional_id, _INV.c.id).where(
                _INV.c.token_hash == token_hash
            )
        ).one_or_none()
        if row is None:
            return None
        return TokenMatch(
            tenant_id=row.tenant_id, professional_id=row.professional_id, invitation_id=row.id
        )

    def lock_invitation(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        invitation_id: uuid.UUID,
        lock: bool = True,
    ) -> InvitationForActivation | None:
        """The invitation, ``FOR UPDATE OF speaker_portal_invitation``, with its joins.

        ``lock=False`` is the read-only ``GET /s/{token}`` page's read (T6b-5 §4.2).
        """
        channel = schema.contact_channel
        unit = schema.org_unit
        account = schema.user_account
        statement = (
            sa.select(
                _INV.c.id,
                _INV.c.tenant_id,
                _INV.c.professional_id,
                _INV.c.expires_at,
                _INV.c.accepted_at,
                _INV.c.revoked_at,
                _PROFILE.c.account_user_id.is_not(None).label("profile_bound"),
                channel.c.channel_kind,
                channel.c.contact_state,
                channel.c.address,
                sa.cast(unit.c.path, sa.Text).label("owning_unit_path"),
                account.c.suspended.label("account_suspended"),
            )
            .select_from(
                _INV.join(
                    _PROFILE,
                    sa.and_(
                        _PROFILE.c.tenant_id == _INV.c.tenant_id,
                        _PROFILE.c.professional_id == _INV.c.professional_id,
                    ),
                )
                .join(
                    channel,
                    sa.and_(
                        channel.c.tenant_id == _INV.c.tenant_id,
                        channel.c.id == _INV.c.contact_channel_id,
                    ),
                )
                .join(
                    unit,
                    sa.and_(
                        unit.c.tenant_id == _PROFILE.c.tenant_id,
                        unit.c.id == _PROFILE.c.owning_unit_id,
                    ),
                )
                .join(
                    account,
                    sa.and_(
                        account.c.tenant_id == _INV.c.tenant_id,
                        account.c.id == _INV.c.professional_id,
                    ),
                )
            )
            .where(_INV.c.tenant_id == tenant_id, _INV.c.id == invitation_id)
        )
        if lock:
            statement = statement.with_for_update(of=_INV)
        row = session.execute(statement).one_or_none()
        return None if row is None else InvitationForActivation(**row._mapping)

    def get_for_send(
        self, session: Session, *, tenant_id: uuid.UUID, invitation_id: uuid.UUID
    ) -> InvitationForSend | None:
        """The worker's read. Tenant-scoped: another tenant's id finds nothing."""
        row = session.execute(
            sa.select(
                _INV.c.id,
                _PROFILE.c.owning_unit_id,
                _INV.c.contact_channel_id,
                _INV.c.token_hash,
                _INV.c.expires_at,
                _INV.c.accepted_at,
                _INV.c.revoked_at,
            )
            .select_from(
                _INV.join(
                    _PROFILE,
                    sa.and_(
                        _PROFILE.c.tenant_id == _INV.c.tenant_id,
                        _PROFILE.c.professional_id == _INV.c.professional_id,
                    ),
                )
            )
            .where(_INV.c.tenant_id == tenant_id, _INV.c.id == invitation_id)
        ).one_or_none()
        if row is None:
            return None
        values = dict(row._mapping)
        values["token_hash"] = bytes(values["token_hash"])
        return InvitationForSend(**values)

    # -- activation --------------------------------------------------------

    def bind_profile(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        professional_id: uuid.UUID,
        account_user_id: uuid.UUID,
        now: datetime,
    ) -> bool:
        result = session.execute(
            sa.update(_PROFILE)
            .where(
                _PROFILE.c.tenant_id == tenant_id,
                _PROFILE.c.professional_id == professional_id,
                _PROFILE.c.account_user_id.is_(None),
            )
            .values(account_user_id=account_user_id, account_bound_at=now)
            .returning(_PROFILE.c.professional_id)
        ).all()
        return bool(result)

    def accept_invitation(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        invitation_id: uuid.UUID,
        bound_account_user_id: uuid.UUID,
        binding_mode: str,
        now: datetime,
    ) -> bool:
        """Mark the live invitation accepted by ``bound_account_user_id``.

        ``binding_mode`` is ``new_login`` (the contact account became the login)
        or ``existing_login`` (an Event Host's login gained ``speaker``, T6b-5).
        """
        result = session.execute(
            sa.update(_INV)
            .where(_INV.c.tenant_id == tenant_id, _INV.c.id == invitation_id, _live())
            .values(
                accepted_at=now,
                bound_account_user_id=bound_account_user_id,
                binding_mode=binding_mode,
            )
            .returning(_INV.c.id)
        ).all()
        return bool(result)

    # -- one login, two roles (B26 T6b-5) ------------------------------------

    def login_bound_elsewhere(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        account_user_id: uuid.UUID,
        excluding_professional_id: uuid.UUID,
    ) -> bool:
        """Whether ``account_user_id`` already speaks for another profile.

        One login speaks for at most one Speaker (``uq_speaker_profile_account``);
        activation refuses before the bind rather than relying on the violation.
        """
        return (
            session.execute(
                sa.select(sa.literal(1))
                .where(
                    _PROFILE.c.tenant_id == tenant_id,
                    _PROFILE.c.account_user_id == account_user_id,
                    _PROFILE.c.professional_id != excluding_professional_id,
                )
                .limit(1)
            ).first()
            is not None
        )

    def active_roles(
        self, session: Session, *, tenant_id: uuid.UUID, user_id: uuid.UUID, now: datetime
    ) -> frozenset[str]:
        """The roles ``user_id`` holds at ``now``, at any path (``valid_until`` exclusive)."""
        membership = schema.membership
        rows = session.execute(
            sa.select(membership.c.role)
            .where(
                membership.c.tenant_id == tenant_id,
                membership.c.user_id == user_id,
                sa.or_(membership.c.valid_from.is_(None), membership.c.valid_from <= now),
                sa.or_(membership.c.valid_until.is_(None), membership.c.valid_until > now),
            )
            .distinct()
        ).all()
        return frozenset(row.role for row in rows)

    def lock_bound_profile_invitation(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        professional_id: uuid.UUID,
        account_user_id: uuid.UUID,
        lock: bool = True,
    ) -> BoundInvitation | None:
        """The accepted, not-unbound invitation that bound ``account_user_id``.

        ``FOR UPDATE`` by default: unbind's second lock, after the profile's.
        ``lock=False`` is ``GET …/portal-access``'s read of ``binding_mode``.
        """
        statement = (
            sa.select(_INV.c.id, _INV.c.binding_mode)
            .where(
                _INV.c.tenant_id == tenant_id,
                _INV.c.professional_id == professional_id,
                _INV.c.accepted_at.is_not(None),
                _INV.c.bound_account_user_id == account_user_id,
                _INV.c.unbound_at.is_(None),
            )
            .order_by(_INV.c.accepted_at.desc())
            .limit(1)
        )
        if lock:
            statement = statement.with_for_update(of=_INV)
        row = session.execute(statement).one_or_none()
        return None if row is None else BoundInvitation(id=row.id, binding_mode=row.binding_mode)

    def account_email(
        self, session: Session, *, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> str | None:
        account = schema.user_account
        return session.execute(
            sa.select(account.c.email).where(
                account.c.tenant_id == tenant_id, account.c.id == user_id
            )
        ).scalar_one_or_none()

    def unbind(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        professional_id: uuid.UUID,
        login_user_id: uuid.UUID,
        invitation_id: uuid.UUID | None,
        unbound_by_user_id: uuid.UUID,
        now: datetime,
    ) -> None:
        """Unbind steps 5–7 (T6b-5 §4.4). The caller holds the profile and invitation locks.

        * Every active ``speaker`` row on the login ends at ``now``
          (``valid_until`` is exclusive). Only activation grants ``speaker`` and
          one login speaks for at most one profile, so these are this profile's.
          **No other role is touched** (R-I): the Event Host keeps hosting.
        * The profile's binding is cleared.
        * The invitation records who unbound it and when.
        """
        membership = schema.membership
        session.execute(
            sa.update(membership)
            .where(
                membership.c.tenant_id == tenant_id,
                membership.c.user_id == login_user_id,
                membership.c.role == "speaker",
                sa.or_(membership.c.valid_until.is_(None), membership.c.valid_until > now),
            )
            .values(valid_until=now)
        )
        session.execute(
            sa.update(_PROFILE)
            .where(
                _PROFILE.c.tenant_id == tenant_id,
                _PROFILE.c.professional_id == professional_id,
                _PROFILE.c.account_user_id == login_user_id,
            )
            .values(account_user_id=None, account_bound_at=None)
        )
        if invitation_id is not None:
            session.execute(
                sa.update(_INV)
                .where(_INV.c.tenant_id == tenant_id, _INV.c.id == invitation_id)
                .values(unbound_at=now, unbound_by_user_id=unbound_by_user_id)
            )
