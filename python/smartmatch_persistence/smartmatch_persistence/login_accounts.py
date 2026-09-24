"""The one writer of ``pilot_credential`` (B26 T6b-5 plan §3; parent §4.5 item 6).

Every path that creates, rotates or removes a pilot password comes through here:
Speaker portal activation (new login and existing login), the Connector's unbind,
and the ``seed-pilot-logins`` operator tool. ``tests/unit/test_login_account_writers.py``
fails if any other module in ``python/``, ``services/``, ``tools/``, ``scripts/`` or
``db/`` inserts, updates or deletes a ``pilot_credential`` row.

Why one writer: ``PilotCredentialRepository.load_by_email`` answers ``None``
unless **exactly one** credentialed account holds an address, in any tenant. A
second credential at an address therefore breaks sign-in for both logins. The
rule that prevents it — never add a credential where the address already has
one — only holds if every inserter checks it under the same lock, and the only
way to make that true for code not yet written is to have one inserter.

Locking (plan §4.5). Global order: seed advisory lock < ``speaker_profile`` row <
``speaker_portal_invitation`` row < **address advisory lock** < ``pilot_credential``
rows, by id. :func:`lock_address` is the address lock; :func:`holders_for_address`
with ``lock=True`` takes the row locks. Both are needed: the advisory lock stops a
second *insert* at the address (there is no row yet to lock), and ``FOR UPDATE``
stops a concurrent *update or delete* of an existing holder's credential between
a caller's password check and its write.

Rules every function keeps: **never commits**; every timestamp is a parameter;
addresses are normalised once in Python (``strip().lower()``, :func:`normalise_address`)
and that value is what the lock, the match and the stored email all see; stored
emails are folded in SQL as ``lower(btrim(…))`` over all ASCII whitespace
(T6b-1 review LOW 1).
Takes a ``Session`` or a ``Connection`` (the seed tool holds a ``Connection``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from smartmatch_domain.pilot_credentials import StoredPassword
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = [
    "AccountAlreadyCredentialed",
    "AddressAmbiguous",
    "AddressHolders",
    "AddressInOtherTenant",
    "AddressState",
    "LoginAccountError",
    "LoginHolder",
    "NewLogin",
    "NoLoginForAddress",
    "RoleGrant",
    "active_roles",
    "find_or_add_role",
    "holders_for_address",
    "lock_address",
    "normalise_address",
    "retire_login",
    "rotate_own_password",
]

_ACCOUNT = schema.user_account
_CREDENTIAL = schema.pilot_credential
_MEMBERSHIP = schema.membership
_SESSION = schema.pilot_session

#: Prefix of the advisory-lock key. Distinct from every other advisory key in
#: the codebase (those are integer constants), and shared by every caller. The
#: bound value is already :func:`normalise_address`'s.
_ADDRESS_LOCK_SQL = sa.text(
    "SELECT pg_advisory_xact_lock(hashtextextended('login-address:' || :address, 0))"
)

#: What Python's ``str.strip()`` removes from an address, for the SQL side:
#: ``btrim`` with no second argument trims spaces only, so a stored address
#: ending in a tab or newline would otherwise not fold.
_WHITESPACE = " \t\n\r\f\v"

Executor = Session | Connection


class AddressState(StrEnum):
    NONE = "none"  # no credentialed account holds the address, in any tenant
    ONE_IN_TENANT = "one_in_tenant"
    OTHER_TENANT = "other_tenant"  # exactly one holder, in another tenant
    AMBIGUOUS = "ambiguous"  # two or more holders, in any tenants


@dataclass(frozen=True, slots=True)
class LoginHolder:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    external_subject: str
    suspended: bool
    password: StoredPassword


@dataclass(frozen=True, slots=True)
class AddressHolders:
    """Who holds an address.

    Attributes:
        state: The classification, counting address holders only.
        holder: Set only for ``ONE_IN_TENANT``.
        also_locked_credentialed: Whether ``also_lock_user_id``'s account holds a
            credential (its row was read, and locked when ``lock=True``). It is
            never counted as an address holder unless it holds the address.
    """

    state: AddressState
    holder: LoginHolder | None
    also_locked_credentialed: bool = False


@dataclass(frozen=True, slots=True)
class NewLogin:
    """The existing, credential-less account to credential when no login holds the address."""

    user_id: uuid.UUID
    password: StoredPassword


@dataclass(frozen=True, slots=True)
class RoleGrant:
    user_id: uuid.UUID
    external_subject: str
    login_created: bool
    role_added: bool


class LoginAccountError(Exception):
    """Base of every refusal here. Carries no account id or address."""


class AddressAmbiguous(LoginAccountError):
    """Two or more credentialed accounts hold the address."""


class AddressInOtherTenant(LoginAccountError):
    """Exactly one credentialed account holds the address, in another tenant."""


class NoLoginForAddress(LoginAccountError):
    """No credentialed account holds the address, and none was to be created."""


class AccountAlreadyCredentialed(LoginAccountError):
    """A caller asked to create a login where one exists, or for an unusable account."""


def normalise_address(address: str) -> str:
    """The one spelling of an address: ``address.strip().lower()``."""
    return address.strip().lower()


def _folded(column: sa.ColumnElement[str]) -> sa.ColumnElement[str]:
    return sa.func.lower(sa.func.btrim(column, _WHITESPACE))


def lock_address(session: Executor, *, address: str) -> None:
    """Transaction-scoped advisory lock on the normalised address.

    Re-entrant within one transaction (PostgreSQL stacks advisory locks), so a
    caller that already holds it may call :func:`find_or_add_role`.
    """
    session.execute(_ADDRESS_LOCK_SQL, {"address": normalise_address(address)})


def holders_for_address(
    session: Executor,
    *,
    tenant_id: uuid.UUID,
    address: str,
    lock: bool,
    also_lock_user_id: uuid.UUID | None = None,
) -> AddressHolders:
    """Classify the credentialed accounts holding ``address``, across **all** tenants.

    With ``lock=True`` every matching ``pilot_credential`` row — plus
    ``also_lock_user_id``'s own row in ``tenant_id``, if it has one — is locked
    ``FOR UPDATE`` in one statement, ordered by id, so every caller locks in the
    same order.
    """
    holds_address = _folded(_ACCOUNT.c.email) == sa.literal(normalise_address(address), sa.Text)
    condition: sa.ColumnElement[bool] = holds_address
    if also_lock_user_id is not None:
        condition = sa.or_(
            holds_address,
            sa.and_(
                _CREDENTIAL.c.tenant_id == tenant_id, _CREDENTIAL.c.user_id == also_lock_user_id
            ),
        )
    statement = (
        sa.select(
            _CREDENTIAL.c.tenant_id,
            _CREDENTIAL.c.user_id,
            _ACCOUNT.c.external_subject,
            _ACCOUNT.c.suspended,
            holds_address.label("holds_address"),
            _CREDENTIAL.c.algorithm,
            _CREDENTIAL.c.iterations,
            _CREDENTIAL.c.salt,
            _CREDENTIAL.c.password_hash,
        )
        .select_from(
            _CREDENTIAL.join(
                _ACCOUNT,
                sa.and_(
                    _ACCOUNT.c.tenant_id == _CREDENTIAL.c.tenant_id,
                    _ACCOUNT.c.id == _CREDENTIAL.c.user_id,
                ),
            )
        )
        .where(condition)
        .order_by(_CREDENTIAL.c.id)
    )
    if lock:
        statement = statement.with_for_update(of=_CREDENTIAL)
    rows = session.execute(statement).all()

    also_locked = also_lock_user_id is not None and any(
        row.tenant_id == tenant_id and row.user_id == also_lock_user_id for row in rows
    )
    holders = [row for row in rows if row.holds_address]
    if not holders:
        return AddressHolders(AddressState.NONE, None, also_locked)
    if len(holders) > 1:
        return AddressHolders(AddressState.AMBIGUOUS, None, also_locked)
    [row] = holders
    if row.tenant_id != tenant_id:
        return AddressHolders(AddressState.OTHER_TENANT, None, also_locked)
    holder = LoginHolder(
        user_id=row.user_id,
        tenant_id=row.tenant_id,
        external_subject=row.external_subject,
        suspended=row.suspended,
        password=StoredPassword(
            algorithm=row.algorithm,
            iterations=row.iterations,
            salt=bytes(row.salt),
            digest=bytes(row.password_hash),
        ),
    )
    return AddressHolders(AddressState.ONE_IN_TENANT, holder, also_locked)


def active_roles(
    session: Executor, *, tenant_id: uuid.UUID, user_id: uuid.UUID, now: datetime
) -> frozenset[str]:
    """The roles ``user_id`` holds at ``now`` in ``tenant_id``, at any path. Reads only.

    "Active" as ``SpeakerPortalRepository.active_roles`` decides it: ``valid_from``
    null or reached, ``valid_until`` null or later than ``now`` (exclusive). The
    seed reads it under the address and credential-row locks (R-B).
    """
    rows = session.execute(
        sa.select(_MEMBERSHIP.c.role)
        .where(
            _MEMBERSHIP.c.tenant_id == tenant_id,
            _MEMBERSHIP.c.user_id == user_id,
            sa.or_(_MEMBERSHIP.c.valid_from.is_(None), _MEMBERSHIP.c.valid_from <= now),
            sa.or_(_MEMBERSHIP.c.valid_until.is_(None), _MEMBERSHIP.c.valid_until > now),
        )
        .distinct()
    ).all()
    return frozenset(row.role for row in rows)


def find_or_add_role(
    session: Executor,
    *,
    tenant_id: uuid.UUID,
    email: str,
    role: str,
    path: str,
    now: datetime,
    create: NewLogin | None = None,
) -> RoleGrant:
    """Find the one login at ``email`` (or credential ``create``) and grant ``role`` at ``path``.

    Plan §3.2, in order: lock the address and its credential rows; refuse an
    ambiguous or other-tenant address; target the holder, or — only when no
    login holds the address — credential ``create``'s existing, credential-less,
    unsuspended account; then add an active membership unless one exists.

    Raises:
        AddressAmbiguous, AddressInOtherTenant: as named.
        AccountAlreadyCredentialed: ``create`` names an account other than the
            holder, or an account that is missing, suspended or credentialed.
        NoLoginForAddress: no holder and no ``create``.
    """
    lock_address(session, address=email)
    holders = holders_for_address(session, tenant_id=tenant_id, address=email, lock=True)

    if holders.state is AddressState.AMBIGUOUS:
        raise AddressAmbiguous
    if holders.state is AddressState.OTHER_TENANT:
        raise AddressInOtherTenant

    login_created = False
    if holders.holder is not None:
        if create is not None and create.user_id != holders.holder.user_id:
            raise AccountAlreadyCredentialed
        target_id = holders.holder.user_id
        subject = holders.holder.external_subject
    else:
        if create is None:
            raise NoLoginForAddress
        subject = _credential_new_login(
            session, tenant_id=tenant_id, email=email, create=create, now=now
        )
        target_id = create.user_id
        login_created = True

    role_added = _ensure_active_role(
        session, tenant_id=tenant_id, user_id=target_id, role=role, path=path, now=now
    )
    return RoleGrant(
        user_id=target_id,
        external_subject=subject,
        login_created=login_created,
        role_added=role_added,
    )


def _credential_new_login(
    session: Executor,
    *,
    tenant_id: uuid.UUID,
    email: str,
    create: NewLogin,
    now: datetime,
) -> str:
    """Store the normalised address on ``create``'s account and insert its first credential."""
    account = session.execute(
        sa.select(
            _ACCOUNT.c.external_subject,
            _ACCOUNT.c.suspended,
            sa.exists()
            .where(_CREDENTIAL.c.tenant_id == _ACCOUNT.c.tenant_id)
            .where(_CREDENTIAL.c.user_id == _ACCOUNT.c.id)
            .label("credentialed"),
        )
        .where(_ACCOUNT.c.tenant_id == tenant_id, _ACCOUNT.c.id == create.user_id)
        .with_for_update(of=_ACCOUNT)
    ).one_or_none()
    if account is None or account.suspended or account.credentialed:
        # T6b-1's round-2 rule: a credentialed account is never re-passworded.
        raise AccountAlreadyCredentialed

    session.execute(
        sa.update(_ACCOUNT)
        .where(_ACCOUNT.c.tenant_id == tenant_id, _ACCOUNT.c.id == create.user_id)
        .values(email=normalise_address(email), version=_ACCOUNT.c.version + 1)
    )
    # A plain insert: a conflict on uq_pilot_credential_account here is a bug.
    session.execute(
        sa.insert(_CREDENTIAL).values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=create.user_id,
            algorithm=create.password.algorithm,
            iterations=create.password.iterations,
            salt=create.password.salt,
            password_hash=create.password.digest,
            created_at=now,
            updated_at=now,
        )
    )
    return str(account.external_subject)


def _ensure_active_role(
    session: Executor,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str,
    path: str,
    now: datetime,
) -> bool:
    """Insert ``(role, path)`` unless an active row exists. ``True`` when inserted.

    ``valid_from`` is ``NULL`` (plan §3.2, C4): ``created_at`` records the grant
    time, the seed treats a non-null ``valid_from`` as a foreign grant, and an
    unbind's ``valid_until = now`` then always satisfies ``ck_membership_valid_window``.
    """
    ltree_path = sa.cast(path, schema.LTree())
    active = session.execute(
        sa.select(sa.literal(1))
        .where(
            _MEMBERSHIP.c.tenant_id == tenant_id,
            _MEMBERSHIP.c.user_id == user_id,
            _MEMBERSHIP.c.role == role,
            _MEMBERSHIP.c.granted_path == ltree_path,
            sa.or_(_MEMBERSHIP.c.valid_from.is_(None), _MEMBERSHIP.c.valid_from <= now),
            sa.or_(_MEMBERSHIP.c.valid_until.is_(None), _MEMBERSHIP.c.valid_until > now),
        )
        .limit(1)
    ).first()
    if active is not None:
        return False
    session.execute(
        sa.insert(_MEMBERSHIP).values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            granted_path=ltree_path,
            role=role,
            valid_from=None,
            valid_until=None,
            created_at=now,
        )
    )
    return True


def rotate_own_password(
    session: Executor,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    password: StoredPassword,
    now: datetime,
) -> None:
    """Replace one account's credential. Only the seed tool calls it, for its own subject.

    Raises:
        NoLoginForAddress: the account holds no credential.
    """
    updated = session.execute(
        sa.update(_CREDENTIAL)
        .where(_CREDENTIAL.c.tenant_id == tenant_id, _CREDENTIAL.c.user_id == user_id)
        .values(
            algorithm=password.algorithm,
            iterations=password.iterations,
            salt=password.salt,
            password_hash=password.digest,
            updated_at=now,
        )
        .returning(_CREDENTIAL.c.id)
    ).first()
    if updated is None:
        raise NoLoginForAddress


def retire_login(
    session: Executor, *, tenant_id: uuid.UUID, user_id: uuid.UUID, now: datetime
) -> None:
    """End every live session of the account, then delete its credential.

    Used by unbind for a new-login binding (plan §4.4, Q3): the contact account
    goes back to credential-less, so a later re-invite runs new-login cleanly.
    """
    session.execute(
        sa.update(_SESSION)
        .where(
            _SESSION.c.tenant_id == tenant_id,
            _SESSION.c.user_id == user_id,
            _SESSION.c.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    session.execute(
        sa.delete(_CREDENTIAL).where(
            _CREDENTIAL.c.tenant_id == tenant_id, _CREDENTIAL.c.user_id == user_id
        )
    )
