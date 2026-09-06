"""Storage for the pilot login: credentials, sessions, and pre-auth attempts.

The companion to :mod:`smartmatch_domain.pilot_credentials`, which does the
arithmetic. This module does the rows, and it is written to preserve one
property above every other:

    **Authentication resolves an ``external_subject``. It never resolves a
    role, a tenant the caller named, or a unit.**

That is why :meth:`PilotSessionRepository.resolve_subject` returns a *string*
and nothing else. The caller hands it to
:meth:`~smartmatch_persistence.principals.PrincipalRepository.load_by_subject`,
which is the one place a tenant and a set of memberships come from — exactly
as a verified identity-provider token would be handled. A session that
carried its own roles would be caller-selected identity wearing a different
hat (MM-A01), so there is deliberately no method here that returns one.

## Why a login is looked up by email and can still refuse an ambiguous one

``user_account.email`` is not unique — nothing in this schema says a person
holds one account. :meth:`PilotCredentialRepository.load_by_email` therefore
selects *every* credentialed account for the address and returns ``None``
unless there is exactly one. That is fail-closed rather than convenient: two
matching accounts means "which of these is signing in" has no answer, and
picking the first would be the API deciding an identity question on the
caller's behalf. The route treats the ``None`` exactly as it treats a wrong
password, so an ambiguous address is not distinguishable from an unknown one.

## Sessions are refused, not merely absent

:meth:`PilotSessionRepository.resolve_subject` filters on ``revoked_at IS
NULL`` and ``expires_at > now`` in the query, so an expired or logged-out
session resolves to nothing on every instance at once — there is no in-process
cache of live sessions to go stale. :meth:`PilotSessionRepository.revoke` sets
``revoked_at`` rather than deleting: both make the next request fail, and only
one of them can still say a session was deliberately ended.

## The pre-authentication counter

:class:`LoginAttemptLimiter` is :class:`~smartmatch_persistence.rate_limit.RateLimiter`'s
guarded ``INSERT ... ON CONFLICT DO UPDATE``, keyed on a caller address
instead of on ``(tenant, subject)``, because a caller who has not
authenticated has no tenant to key on. Migration ``0020``'s docstring records
why that is a separate table rather than a relaxation of the shared one.
It reuses :class:`~smartmatch_persistence.rate_limit.RateLimit` and
:class:`~smartmatch_persistence.rate_limit.RateLimitDecision` rather than
restating them, so the window arithmetic has one implementation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import sqlalchemy as sa
from smartmatch_domain.pilot_credentials import StoredPassword
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from smartmatch_persistence import schema
from smartmatch_persistence.rate_limit import RateLimit, RateLimitDecision

__all__ = [
    "CredentialedAccount",
    "LoginAttemptLimiter",
    "PilotCredentialRepository",
    "PilotSessionRepository",
]


@dataclass(frozen=True, slots=True)
class CredentialedAccount:
    """An account that holds a pilot password, and the stored password itself.

    Carries no role and no membership, deliberately. What this type is *for*
    is deciding whether a presented password matches; who the account may act
    as is a separate question answered by
    :class:`~smartmatch_persistence.principals.PrincipalRepository` from
    ``membership`` rows.

    Attributes:
        user_id: The local account id.
        tenant_id: The tenant the account belongs to. Resolved here, never
            supplied by the request.
        external_subject: The globally unique subject a session resolves to.
        suspended: Whether an administrator has suspended the account. Carried
            rather than filtered, so the login route can refuse a suspended
            account explicitly instead of confusing it with a bad password.
        password: The stored digest and the parameters it was derived under.
    """

    user_id: uuid.UUID
    tenant_id: uuid.UUID
    external_subject: str
    suspended: bool
    password: StoredPassword


class PilotCredentialRepository:
    """Reads and writes ``pilot_credential`` rows."""

    def load_by_email(self, session: Session, *, email: str) -> CredentialedAccount | None:
        """Load the single credentialed account for ``email``, or ``None``.

        ``None`` covers three genuinely different situations — no account with
        that address, an account with no pilot credential, and two or more
        accounts sharing the address — and that conflation is intentional. The
        login route answers all three with the same denial, so distinguishing
        them here would only create a value someone could later be tempted to
        report.

        The address is matched case-insensitively on both sides. An email that
        differs only in case is the same mailbox to every mail system a pilot
        participant will use, and a login that refused ``Coordinator@…`` while
        accepting ``coordinator@…`` would be a support ticket, not a control.
        """
        rows = session.execute(
            sa.select(
                schema.user_account.c.id,
                schema.user_account.c.tenant_id,
                schema.user_account.c.external_subject,
                schema.user_account.c.suspended,
                schema.pilot_credential.c.algorithm,
                schema.pilot_credential.c.iterations,
                schema.pilot_credential.c.salt,
                schema.pilot_credential.c.password_hash,
            )
            .select_from(
                schema.user_account.join(
                    schema.pilot_credential,
                    sa.and_(
                        schema.pilot_credential.c.tenant_id == schema.user_account.c.tenant_id,
                        schema.pilot_credential.c.user_id == schema.user_account.c.id,
                    ),
                )
            )
            .where(sa.func.lower(schema.user_account.c.email) == email.strip().lower())
            # Two is already too many; there is no reason to read a thousand to
            # find that out.
            .limit(2)
        ).all()

        if len(rows) != 1:
            return None

        row = rows[0]
        return CredentialedAccount(
            user_id=row.id,
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

    def upsert(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        password: StoredPassword,
        now: datetime | None = None,
    ) -> None:
        """Write or replace one account's pilot credential. **Does not commit.**

        Called by the seed tool, never by a route: there is no endpoint in this
        API that sets a password, because the owner supplies pilot credentials
        out of band and a self-service password surface is part of real
        authentication rather than of a stand-in for it.

        Replacing rather than appending is deliberate — see migration ``0020``:
        rotating a pilot password is re-running the seed, not accumulating
        versions of a secret in a table.
        """
        moment = now or datetime.now(UTC)
        statement = (
            pg_insert(schema.pilot_credential)
            .values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                user_id=user_id,
                algorithm=password.algorithm,
                iterations=password.iterations,
                salt=password.salt,
                password_hash=password.digest,
                created_at=moment,
                updated_at=moment,
            )
            .on_conflict_do_update(
                constraint="uq_pilot_credential_account",
                set_={
                    "algorithm": password.algorithm,
                    "iterations": password.iterations,
                    "salt": password.salt,
                    "password_hash": password.digest,
                    "updated_at": moment,
                },
            )
        )
        session.execute(statement)


class PilotSessionRepository:
    """Issues, resolves, and revokes ``pilot_session`` rows."""

    def issue(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        token_hash: bytes,
        issued_at: datetime,
        expires_at: datetime,
    ) -> uuid.UUID:
        """Record a new session. **Does not commit.**

        Takes the *hash* of the token, never the token: this layer has no way
        to reconstruct what the browser was handed, which is what makes a
        database dump useless as a set of live credentials.
        """
        session_id = uuid.uuid4()
        session.execute(
            sa.insert(schema.pilot_session).values(
                id=session_id,
                tenant_id=tenant_id,
                user_id=user_id,
                token_hash=token_hash,
                issued_at=issued_at,
                expires_at=expires_at,
            )
        )
        return session_id

    def resolve_subject(
        self, session: Session, *, token_hash: bytes, now: datetime | None = None
    ) -> str | None:
        """The ``external_subject`` a live session belongs to, or ``None``.

        A **subject**, and nothing else. The caller resolves the principal from
        it exactly as it would from a verified token's subject, so the tenant
        and every role still come from ``user_account`` and ``membership``.

        Liveness is expressed in the query — not revoked, not expired — so
        every instance agrees the moment a row changes, and there is no cache
        of live sessions to invalidate.
        """
        moment = now or datetime.now(UTC)
        row = session.execute(
            sa.select(schema.user_account.c.external_subject)
            .select_from(
                schema.pilot_session.join(
                    schema.user_account,
                    sa.and_(
                        schema.pilot_session.c.tenant_id == schema.user_account.c.tenant_id,
                        schema.pilot_session.c.user_id == schema.user_account.c.id,
                    ),
                )
            )
            .where(
                schema.pilot_session.c.token_hash == token_hash,
                schema.pilot_session.c.revoked_at.is_(None),
                schema.pilot_session.c.expires_at > moment,
            )
        ).one_or_none()

        return None if row is None else str(row.external_subject)

    def revoke(self, session: Session, *, token_hash: bytes, now: datetime | None = None) -> bool:
        """Withdraw a session. **Does not commit.**

        Returns whether a live session was actually withdrawn. ``False`` means
        the token named nothing live — already revoked, already expired, or
        never a session at all — and a log-out route reports success either
        way, because the caller's requested end state has been reached in every
        one of those cases.

        The ``revoked_at IS NULL`` guard makes this idempotent without
        rewriting the original revocation time, so "when was this session
        ended" keeps its first, true answer.
        """
        moment = now or datetime.now(UTC)
        # ``RETURNING`` rather than ``rowcount``: the update's own report of how
        # many rows it touched is typed as unavailable on the generic result,
        # and asking the statement to hand back what it changed is both
        # narrower and checkable.
        revoked = session.execute(
            sa.update(schema.pilot_session)
            .where(
                schema.pilot_session.c.token_hash == token_hash,
                schema.pilot_session.c.revoked_at.is_(None),
            )
            .values(revoked_at=moment)
            .returning(schema.pilot_session.c.id)
        ).one_or_none()
        return revoked is not None


class LoginAttemptLimiter:
    """A fixed-window counter for callers who have not authenticated yet.

    :class:`~smartmatch_persistence.rate_limit.RateLimiter` keyed by tenant and
    user cannot be used before either exists, so this is the same mechanism
    keyed by the client address. Migration ``0020`` records why that is a
    separate table rather than a nullable tenant on the shared one.

    Fails closed in the same sense as the shared limiter: a database error
    propagates rather than being swallowed into an allow (v1.1 §3.6, N4).
    """

    def check(
        self,
        session: Session,
        *,
        limit: RateLimit,
        caller_key: str,
        now: datetime | None = None,
    ) -> RateLimitDecision:
        """Consume one unit of the caller's login quota, or deny. **Does not commit.**

        One statement with a guard on the ``SET``: once the window is spent the
        update matches nothing, no row comes back, and the attempt is denied.
        There is no read-then-write window in which two instances both see
        room.
        """
        moment = now or datetime.now(UTC)
        window_start = limit.window_start(moment)
        retry_after = (window_start + limit.window) - moment

        statement = (
            pg_insert(schema.pilot_login_attempt)
            .values(caller_key=caller_key, window_start=window_start, count=1)
            .on_conflict_do_update(
                constraint="pk_pilot_login_attempt",
                set_={"count": schema.pilot_login_attempt.c.count + 1},
                where=schema.pilot_login_attempt.c.count < limit.max_requests,
            )
            # Labelled for the reason rate_limit.py labels its own: ``Row.count``
            # otherwise resolves to the inherited tuple method.
            .returning(schema.pilot_login_attempt.c.count.label("current_count"))
        )

        row = session.execute(statement).one_or_none()

        if row is None:
            return RateLimitDecision(
                allowed=False, remaining=0, retry_after=retry_after, limit=limit
            )

        return RateLimitDecision(
            allowed=True,
            remaining=max(0, limit.max_requests - row.current_count),
            retry_after=retry_after,
            limit=limit,
        )
