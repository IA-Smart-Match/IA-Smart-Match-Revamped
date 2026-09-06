"""Pilot login: stored credentials, server-side sessions, and a pre-auth attempt counter.

Revision ID: 0020_pilot_login_credentials
Revises: 0019_redemption_durability
Create Date: 2026-09-04

The owner authorized, on 2026-09-04, a **pilot-scoped** login backed by
credentials they supply, as a substitute for institutional sign-in while A1b
stays blocked (``docs/decisions/pilot-login-decision-2026-09-04.md``). This
revision is the storage half of it: somewhere to keep a salted password
digest, somewhere to keep a session the browser cannot forge, and somewhere
to count login attempts made by a caller who has not authenticated yet.

Nothing here stores, implies, or can be made to carry a **role**. That is the
one property this whole change is fenced by: a role lives in ``membership``
and is written by an administrator, and the login below resolves an
``external_subject`` and stops. There is deliberately no ``role`` column on
any of the three tables, and no path by which one could be added without the
policy matrix noticing (``tests/authz/test_policy_matrix.py``).

``pilot_credential``
--------------------
One row per account that has a pilot password. Composite
``(tenant_id, user_id)`` to ``user_account``, as every identity reference in
this schema is — a credential belonging to an account in another tenant is
not a credential.

The digest is stored beside **the parameters it was produced with**:
``algorithm``, ``iterations``, and a per-user ``salt``. That is what lets the
iteration count be raised later without invalidating existing rows, and it is
what lets :func:`smartmatch_domain.pilot_credentials.verify_password` refuse a
row written under a scheme it does not recognise instead of re-deriving it
under today's defaults and comparing anyway. ``ck_pilot_credential_algorithm``
pins the vocabulary to the single identifier that module writes, so a row
carrying an unknown scheme cannot be inserted in the first place; the runtime
check and the constraint are the same rule stated at both ends.

``ck_pilot_credential_material`` is the shape rule: 16 bytes of salt and a
32-byte SHA-256 output, and an iteration count at or above the floor
:data:`~smartmatch_domain.pilot_credentials.MINIMUM_ITERATIONS`. A ``NOT
NULL`` alone would accept an empty ``bytea`` and a count of 1 — a credential
that verifies nothing, written by a bug rather than by a person.

``uq_pilot_credential_account`` makes the account the key. One account, at
most one pilot password; there is no history table and no second credential,
because rotating a pilot password is re-running the seed, not accumulating
versions of a secret.

**No plaintext column, and no reversible one.** There is nowhere on this table
to put a recoverable password, which is the point: a pilot database that is
dumped or shared hands over digests, not the owner's chosen strings.

``pilot_session``
-----------------
An opaque server-side session. The browser holds a random token; this table
holds ``token_hash``, a SHA-256 of it, and **never the token**. A session is
therefore not something a client can mint, and a database dump does not
contain live credentials.

``uq_pilot_session_token_hash`` is what the authenticated request path looks
a session up by, so it is named here and named in
:mod:`smartmatch_persistence.pilot_auth`'s query rather than left to
PostgreSQL's generator.

``revoked_at`` exists so that log-out **invalidates** rather than merely
forgetting: the row stays, carrying when it was withdrawn, and the resolver
refuses it from that moment on. Deleting the row would answer the same
request the same way and lose the fact that a session was deliberately ended.
``ck_pilot_session_window`` holds the two orderings that have to be true of a
row for it to be readable at all — an expiry after its issue, and a
revocation not before it.

``pilot_login_attempt``
-----------------------
A counter for requests that arrive **before** there is a principal.

It is not ``rate_limit_counter``, and that is a deliberate, stated deviation
rather than a duplication. That table's primary key opens with a ``tenant_id``
carrying a foreign key to ``tenant``, because every operation it was built for
happens *after* :func:`~smartmatch_api.dependencies.get_current_principal`
has resolved one. A login has no tenant yet — that is what it is trying to
find out — so charging it against ``rate_limit_counter`` would need either a
tenant invented for the purpose (a fabricated row, which ADR-0011 exists to
refuse) or the shared counter's key relaxed to admit a null tenant, which is
a change to the limiter every other route depends on, made on the side of a
change about something else.

So the pre-authentication counter gets its own table with the shape its own
population actually has: a caller key (the client address), a window, and a
count. The mechanism is otherwise identical to
:class:`~smartmatch_persistence.rate_limit.RateLimiter` — a single
``INSERT ... ON CONFLICT DO UPDATE`` with a guard on the ``SET``, so an
exhausted window matches no row and denies without a read-then-write race —
and it is charged as the *first* statement of the login route and committed
immediately, which is ADR-0015's ordering applied to a route that precedes
authentication instead of following it.

``ck_pilot_login_attempt_count`` mirrors
``ck_rate_limit_count_non_negative``: a negative count is not a lenient
counter, it is a broken one.

Expand only, one transaction
----------------------------
Three new tables. Nothing existing is dropped, renamed, or narrowed, so every
reader written before this revision is unaffected by it (v1.1 §4.2,
ADR-0009). ``transaction_per_migration=True`` (``db/migrations/env.py``) holds
the whole thing in one transaction.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0020_pilot_login_credentials"
down_revision = "0019_redemption_durability"
branch_labels = None
depends_on = None

#: The one algorithm identifier a credential row may carry, matching
#: :data:`smartmatch_domain.pilot_credentials.PBKDF2_SHA256`. Held as a
#: constant so the CHECK below and the schema mirror cannot render it
#: differently by accident.
_CREDENTIAL_ALGORITHM = "pbkdf2_hmac_sha256"

#: Salt width, digest width, and the iteration floor, as one expression.
#: Mirrors :data:`~smartmatch_domain.pilot_credentials.SALT_BYTES` (16),
#: SHA-256's 32-byte output, and
#: :data:`~smartmatch_domain.pilot_credentials.MINIMUM_ITERATIONS`.
_CREDENTIAL_MATERIAL_CHECK = (
    "octet_length(salt) >= 16 AND octet_length(password_hash) = 32 AND iterations >= 100000"
)


def upgrade() -> None:
    """Create the credential store, the session store, and the pre-auth counter."""
    op.create_table(
        "pilot_credential",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("algorithm", sa.Text(), nullable=False),
        sa.Column("iterations", sa.Integer(), nullable=False),
        sa.Column("salt", sa.LargeBinary(), nullable=False),
        sa.Column("password_hash", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pilot_credential_pkey"),
        # CASCADE: a credential is not evidence of anything once the account it
        # authenticates is gone, and leaving an orphaned digest behind would be
        # a secret nobody owns.
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_pilot_credential_account"),
        sa.CheckConstraint(
            f"algorithm = '{_CREDENTIAL_ALGORITHM}'", name="ck_pilot_credential_algorithm"
        ),
        sa.CheckConstraint(_CREDENTIAL_MATERIAL_CHECK, name="ck_pilot_credential_material"),
    )

    op.create_table(
        "pilot_session",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The SHA-256 of the token the browser holds. The token itself is never
        # stored, so this column is not a credential — it is a lookup key for
        # one the server has already forgotten.
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        # Set by log-out. The row stays: "this session was ended" is a fact
        # worth keeping, and a deleted row cannot state it.
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pilot_session_pkey"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="CASCADE",
        ),
        # Named because pilot_auth.py resolves a request by this column and a
        # unique index is what makes ``.one_or_none()`` sound there.
        sa.UniqueConstraint("token_hash", name="uq_pilot_session_token_hash"),
        sa.CheckConstraint(
            "expires_at > issued_at AND (revoked_at IS NULL OR revoked_at >= issued_at)",
            name="ck_pilot_session_window",
        ),
        sa.CheckConstraint("octet_length(token_hash) = 32", name="ck_pilot_session_token_hash"),
    )

    # The access path a sweep of dead sessions would read, and the one an
    # operator uses to see whether an account has a live session at all.
    op.create_index(
        "ix_pilot_session_account",
        "pilot_session",
        ["tenant_id", "user_id", sa.text("issued_at DESC")],
    )

    op.create_table(
        "pilot_login_attempt",
        # The client address, as text. Not a UUID and not a tenant: a caller
        # who has not authenticated has neither, and encoding an address as a
        # fake identifier to satisfy a column is the fabrication ADR-0011
        # refuses. Text for the same reason rate_limit_counter.subject is text.
        sa.Column("caller_key", sa.Text(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        # Named because pilot_auth.py passes this name to ON CONFLICT DO UPDATE.
        sa.PrimaryKeyConstraint("caller_key", "window_start", name="pk_pilot_login_attempt"),
        sa.CheckConstraint("count >= 0", name="ck_pilot_login_attempt_count"),
    )


def downgrade() -> None:
    """Drop the three tables, in reverse creation order.

    A development tool, not a production rollback path (v1.1 §4.2). Dropping
    ``pilot_credential`` destroys every stored digest, which is recoverable
    only by re-running the seed with the owner's environment variables — the
    plaintext exists nowhere in this system to be read back.
    """
    op.drop_table("pilot_login_attempt")
    op.drop_index("ix_pilot_session_account", table_name="pilot_session")
    op.drop_table("pilot_session")
    op.drop_table("pilot_credential")
