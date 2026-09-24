"""The Speaker portal read/write path (migration ``0039``, B26 T6b-1).

Rules every method here keeps (plan §3.2, §4.6, §5):

* **Never commits.** The route, or the command it submits, owns the transaction.
* **Every timestamp is a parameter** (R6). No statement here calls ``now()``.
* **Lock order is profile → invitation → address**, in invite and activation
  alike. :meth:`SpeakerPortalRepository.lock_profile` is the first lock in
  both; :meth:`~SpeakerPortalRepository.find_invitation_by_token_hash` takes
  none, so activation can find the profile before locking anything.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = [
    "BoundSpeakerProfile",
    "CurrentInvitation",
    "InvitationForActivation",
    "InvitationForSend",
    "LockedProfile",
    "SpeakerPortalRepository",
    "TokenMatch",
]

_INV = schema.speaker_portal_invitation

#: What Python's ``str.strip()`` removes from an email address, for the SQL
#: side of the comparison: ``btrim`` with no second argument trims spaces only,
#: so a stored address ending in a tab or newline would otherwise not fold.
_WHITESPACE = " \t\n\r\f\v"
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

    def lock_bound_profile_share(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        professional_id: uuid.UUID,
        account_user_id: uuid.UUID,
    ) -> bool:
        """``FOR SHARE`` on the profile, re-checking it is still bound to this login.

        B26 T6b-3: the Speaker's opt-in and opt-out take it right after
        :meth:`find_bound_profile` (which stays lock-free). ``False`` means an
        unbind committed in between; the caller answers ``404``. Holding the
        share lock makes a later unbind wait until the write commits, and a
        T6b-1 invite's ``FOR UPDATE`` serializes with it.
        """
        return (
            session.execute(
                sa.select(sa.literal(1))
                .select_from(_PROFILE)
                .where(
                    _PROFILE.c.tenant_id == tenant_id,
                    _PROFILE.c.professional_id == professional_id,
                    _PROFILE.c.account_user_id == account_user_id,
                )
                .with_for_update(read=True)
            ).first()
            is not None
        )

    def login_address(
        self, session: Session, *, tenant_id: uuid.UUID, account_user_id: uuid.UUID
    ) -> str | None:
        """The signed-in login's ``user_account.email`` (B26 T6b-3, OQ-3).

        The address the invitation proved: an unsubscribe there may be lifted by
        the Speaker; at any other address it may not.
        """
        account = schema.user_account
        found = session.execute(
            sa.select(account.c.email).where(
                account.c.tenant_id == tenant_id, account.c.id == account_user_id
            )
        ).scalar_one_or_none()
        return None if found is None else str(found)

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
        self, session: Session, *, tenant_id: uuid.UUID, invitation_id: uuid.UUID
    ) -> InvitationForActivation | None:
        """The invitation, ``FOR UPDATE OF speaker_portal_invitation``, with its joins."""
        channel = schema.contact_channel
        unit = schema.org_unit
        account = schema.user_account
        row = session.execute(
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
            .with_for_update(of=_INV)
        ).one_or_none()
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

    def account_has_credential(
        self, session: Session, *, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        credential = schema.pilot_credential
        return (
            session.execute(
                sa.select(sa.literal(1)).where(
                    credential.c.tenant_id == tenant_id, credential.c.user_id == user_id
                )
            ).first()
            is not None
        )

    def lock_address(self, session: Session, *, folded_address: str) -> None:
        """Transaction-scoped advisory lock on the address (plan §5 step 8).

        ``folded_address`` is already ``address.strip().lower()``: the caller
        normalises once and passes the same value here, to the duplicate check
        and to the stored email.
        """
        session.execute(
            sa.text(
                "SELECT pg_advisory_xact_lock("
                "hashtextextended('speaker-portal-email:' || :address, 0))"
            ),
            {"address": folded_address},
        )

    def other_credentialed_account_exists(
        self, session: Session, *, folded_address: str, excluding_user_id: uuid.UUID
    ) -> bool:
        """Any credentialed account but ``excluding_user_id`` holds the address, in any tenant.

        ``folded_address`` is ``address.strip().lower()``; stored emails are
        folded the same way in SQL, trimming all ASCII whitespace (R5).
        """
        account = schema.user_account
        credential = schema.pilot_credential
        return (
            session.execute(
                sa.select(sa.literal(1))
                .select_from(
                    account.join(
                        credential,
                        sa.and_(
                            credential.c.tenant_id == account.c.tenant_id,
                            credential.c.user_id == account.c.id,
                        ),
                    )
                )
                .where(
                    sa.func.lower(sa.func.btrim(account.c.email, _WHITESPACE)) == folded_address,
                    account.c.id != excluding_user_id,
                )
                .limit(1)
            ).first()
            is not None
        )

    def set_account_email(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        folded_address: str,
    ) -> None:
        """Store the normalised address, so ``load_by_email``'s folded match finds it."""
        account = schema.user_account
        session.execute(
            sa.update(account)
            .where(account.c.tenant_id == tenant_id, account.c.id == user_id)
            .values(email=folded_address, version=account.c.version + 1)
        )

    def grant_speaker_membership(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        granted_path: str,
        now: datetime,
    ) -> None:
        membership = schema.membership
        session.execute(
            sa.insert(membership).values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                user_id=user_id,
                granted_path=sa.cast(granted_path, schema.LTree()),
                role="speaker",
                valid_from=now,
                created_at=now,
            )
        )

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
        now: datetime,
    ) -> bool:
        result = session.execute(
            sa.update(_INV)
            .where(_INV.c.tenant_id == tenant_id, _INV.c.id == invitation_id, _live())
            .values(
                accepted_at=now,
                bound_account_user_id=bound_account_user_id,
                binding_mode="new_login",
            )
            .returning(_INV.c.id)
        ).all()
        return bool(result)
