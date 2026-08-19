"""A globally unique identity-provider subject.

Revision ID: 0003_global_subject
Revises: 0002_rate_limit
Create Date: 2026-08-19

``PrincipalRepository.load_by_subject`` (v1.1 §1.2) is the seam where a verified
token becomes a set of permissions. It looks an account up by ``external_subject``
and by nothing else, then calls ``.one_or_none()``. The lookup cannot filter by
tenant, because the tenant is what the lookup is *for*: the token proves who you
are, and the database decides which tenant you belong to and what you may do.

Until this migration the only uniqueness on that column was
``uq_user_account_tenant_subject`` — ``(tenant_id, external_subject)`` — which
promises one account per subject *per tenant* and says nothing about two. One
identity-provider subject with accounts in two tenants therefore returned two
rows, ``.one_or_none()`` raised ``MultipleResultsFound``, and every authenticated
request by that person became a 500. Not a denial, not a wrong-tenant answer: an
unhandled error on every request, for exactly the people a multi-tenant
deployment is most likely to create.

**The decision is that ``external_subject`` is globally unique**, and this
migration makes the database say so. The alternative — teaching the query to
pick a row, by tenant hint or by ``LIMIT 1`` — would leave the ambiguity in the
data and resolve it differently depending on which caller asked. Making the
column unique means the query's shape is *correct* rather than defended: at most
one row can match, so at most one row is returned.

Duplicates are refused, not repaired
------------------------------------
``upgrade()`` looks for duplicate subjects before it adds the constraint, and
raises with the offending subjects named if it finds any. It deliberately does
not deduplicate, merge, or pick a winner.

Two accounts sharing a subject is a question about the world, not about the
schema. Either the identity provider issued one subject to one person who was
enrolled twice — in which case the accounts merge, and someone must decide which
memberships and grants survive — or a subject was reused for two different
people, which is an incident at the identity provider and not something a
migration should paper over. A migration that silently deleted one of the rows
would destroy authorization state to make a constraint apply, and would do it at
deploy time with nobody watching.

Letting PostgreSQL raise the ``IntegrityError`` on its own was rejected for a
smaller reason: it reports a single conflicting key. An operator who reads
``Key (external_subject)=(sub-91f2) is duplicated`` cannot tell whether that is
the only collision or the first of nine hundred, and so cannot tell whether the
fix is a phone call or a project. The check below reports the total and names as
many subjects as fit.

The check needs a live connection, so it cannot run in Alembic's offline
(``--sql``) mode; the generated script carries the constraint but not the guard,
and applying reviewed SQL by hand means running the duplicate query first. The
constraint still refuses the bad state — the loss is the readable message, not
the protection.

What this does to a live ``user_account``
----------------------------------------
``op.create_unique_constraint`` compiles to ``ALTER TABLE ... ADD CONSTRAINT ...
UNIQUE``, and PostgreSQL builds the backing index while holding ``ACCESS
EXCLUSIVE`` on the table. That lock blocks **reads**, not merely writes, and
``smartmatch_api.dependencies`` resolves a principal out of ``user_account`` on
every authenticated request — so for as long as the index build takes, every
authenticated request waits on it. At pilot table size that is milliseconds, and
this simple form is the right trade for it.

It would not be the right trade against a large ``user_account``, and the form
that fixes it is deliberately *not* used here. That form is::

    CREATE UNIQUE INDEX CONCURRENTLY uq_user_account_external_subject
        ON user_account (external_subject);
    ALTER TABLE user_account
        ADD CONSTRAINT uq_user_account_external_subject
        UNIQUE USING INDEX uq_user_account_external_subject;

``CONCURRENTLY`` builds without blocking readers or writers, but it cannot run
inside a transaction — so Alembic's per-migration transaction has to be
disabled for it, the duplicate check below can no longer share a transaction
with the ``ALTER``, and a build that fails partway leaves an ``INVALID`` index
behind that a later attempt must find and drop by hand. Those are real
operational obligations, and they would be accepted here in exchange for an
availability benefit that nothing can currently collect: nothing is deployed,
and no instance is serving requests against this database. Whoever first runs
this against a live system with a large ``user_account`` should switch to the
form above, and take on the obligations with it.

The lock is taken before the check, not left to the ``ALTER``
------------------------------------------------------------
``upgrade()`` issues ``LOCK TABLE user_account IN ACCESS EXCLUSIVE MODE`` as its
first statement, ahead of the duplicate query. This is not superstition and
should not be removed as redundant.

Without it, the ``SELECT`` and the ``ALTER`` are two statements with a gap
between them. An insert landing in that gap — a person signing in for the first
time during a deploy is enough — is not seen by the check and is caught by the
``ALTER``, which means the failure an operator gets is the bare one-key
``IntegrityError`` this whole guard exists to replace, occurring rarely and
therefore at the worst possible moment for understanding it. Taking the lock
first closes the window. It costs no availability that the ``ALTER`` was not
about to cost anyway, a few statements later; it only moves the instant the
table stops changing to *before* the question is asked rather than after.

**How long the lock is actually held — read this before writing ``0004``.** A
lock lives until its transaction ends, and the transaction here is not this
migration's. ``db/migrations/env.py`` wraps ``context.run_migrations()`` in a
single ``context.begin_transaction()`` and does not set
``transaction_per_migration=True``, so one transaction spans *every pending
revision in the run*. ``ACCESS EXCLUSIVE`` on ``user_account`` is therefore held
from the ``LOCK`` above until the whole ``alembic upgrade`` commits — not until
this migration finishes.

That is acceptable only for as long as ``0003`` is head, which is the situation
at the time it was written: the lock and the run end together, and the window is
the index build the section above budgets for. It stops being true the moment a
``0004`` exists. Upgrading a live database from ``0002`` would then hold the
table locked across ``0003``, ``0004``, and everything after it in the same run,
blocking every authenticated request for the whole upgrade rather than for an
index build — and nothing in this file would be wrong, which is why it is
written down here rather than assumed.

Whoever writes ``0004`` inherits that. The available fixes are
``transaction_per_migration=True`` in ``env.py`` — which is arguably the better
default but changes rollback semantics for **every** migration in the
repository, since a failed multi-step upgrade would then leave earlier revisions
committed instead of rolling the run back as a unit — or running this revision
on its own. Both are decisions about the migration system rather than about
identity, so neither is made here.

``uq_user_account_tenant_subject`` is kept
------------------------------------------
It is now strictly implied: if a subject appears at most once in the whole
table, it appears at most once per tenant. The old constraint and its index are
redundant, and they cost a write on every ``user_account`` insert.

They are kept anyway, because dropping them is a **contract-phase** action and
every migration in this repository is expand-phase only (v1.1 §4.2, and
ADR-0004's "expand / migrate / contract" section). The claim is about *schema
compatibility* and nothing else — this migration is not available to serve
traffic while it runs, per the lock discussion above. Both releases read the
same table across a rollout, and a release rolled back after this migration ran
must still find the schema it was built against. Nothing in the old release
breaks because a redundant constraint is still present, and something could
break because it is suddenly absent. Removing ``uq_user_account_tenant_subject``
belongs in a later, deliberately destructive change that runs after this release
is fully promoted — the same rule under which ``0001`` drops nothing.

What phase this actually is
---------------------------
``0001`` and ``0002`` are expand-phase in the strict sense v1.1 §4.2 means:
they create, and they constrain nothing that already holds rows. **This one is
not that.** Adding a ``UNIQUE`` constraint *tightens* what ``user_account`` will
accept, and a tightening is only safe while nothing is producing the rows it
would reject.

It is safe here for a specific and temporary reason: **nothing writes
``user_account`` yet.** No production code path inserts an account — account
provisioning does not exist — so no in-flight writer can emit a duplicate
subject while this runs, and the check above inspects a table that is standing
still rather than one that is moving underneath it.

So do not read the §4.2 citation as a promise that this shape is generally safe
under a rolling deploy. Once a provisioning path exists, a constraint like this
one has to come *second*: the write path stops producing duplicates first —
deployed, promoted, and verified — and only then is the constraint added.
Otherwise the old release goes on writing rows the new constraint rejects, and
the migration either fails outright or takes the table down in the middle of a
deploy. What stays true in either order is the narrower rollback claim above,
which is only about **reads**: keeping ``uq_user_account_tenant_subject`` means
an old release still finds the schema it was built to query.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

revision = "0003_global_subject"
down_revision = "0002_rate_limit"
branch_labels = None
depends_on = None

#: How many duplicated subjects the error message names before it stops. A
#: deployment that has been running for a while with a misconfigured identity
#: provider could have thousands, and an error that prints all of them is one an
#: operator scrolls past rather than reads. The total is always reported, so the
#: cap hides detail and never hides scale.
_MAX_REPORTED_SUBJECTS = 20

#: Subjects held by more than one account, worst first so the cap keeps the
#: examples most likely to explain what happened.
_DUPLICATE_SUBJECTS = sa.text(
    """
    SELECT external_subject, count(*) AS accounts
    FROM user_account
    GROUP BY external_subject
    HAVING count(*) > 1
    ORDER BY count(*) DESC, external_subject
    """
)


def _refuse_duplicate_external_subjects(bind: sa.Connection) -> None:
    """Raise if any ``external_subject`` is held by more than one account.

    Separated from :func:`upgrade` so it reads as what it is — a precondition
    with an explanation attached — and so a test can run the real check against
    a database holding real duplicates instead of asserting against a copy of
    the query.

    Raises:
        RuntimeError: naming the duplicated subjects and how many there are.
            ``RuntimeError`` rather than a database exception because nothing
            here should be caught and retried: the migration is stopping to ask
            a question that only a human with access to the identity provider
            can answer.
    """
    duplicates = bind.execute(_DUPLICATE_SUBJECTS).all()
    if not duplicates:
        return

    accounts = sum(row.accounts for row in duplicates)
    shown = duplicates[:_MAX_REPORTED_SUBJECTS]
    listing = "\n".join(
        f"  {row.external_subject!r}: {row.accounts} accounts" for row in shown
    )
    elided = len(duplicates) - len(shown)
    if elided:
        listing += f"\n  ... and {elided} more subject(s) not listed"

    raise RuntimeError(
        f"Cannot make user_account.external_subject unique: "
        f"{len(duplicates)} subject(s), across {accounts} accounts, are held by "
        f"more than one account.\n"
        f"{listing}\n"
        f"These rows are why load_by_subject raises MultipleResultsFound today, "
        f"and they are not something this migration will resolve on your behalf. "
        f"Each duplicate is one of two different situations: one person enrolled "
        f"twice under a single identity-provider subject, whose accounts must be "
        f"merged by hand so the surviving memberships and grants are chosen "
        f"deliberately; or one subject issued to two different people, which is "
        f"an identity-provider incident and must be fixed there first. Resolve "
        f"every subject listed above, then run this migration again."
    )


def upgrade() -> None:
    """Make ``external_subject`` unique across the whole table."""
    # First statement, and deliberately so: it closes the window between the
    # duplicate check and the ALTER in which a concurrent insert would slip past
    # the readable error and hit the bare IntegrityError instead. The ALTER takes
    # this lock anyway; see the docstring.
    op.execute("LOCK TABLE user_account IN ACCESS EXCLUSIVE MODE")

    if context.is_offline_mode():
        # The duplicate check reads the table, which offline mode has no
        # connection to. Say so in the emitted script rather than silently
        # generating SQL that looks like it carries the same guard.
        op.execute(
            "-- 0003: the duplicate-subject check requires a live connection and "
            "was not run.\n"
            "-- Before applying this script, run:\n"
            "--   SELECT external_subject, count(*) FROM user_account\n"
            "--   GROUP BY external_subject HAVING count(*) > 1;\n"
            "-- and resolve every row it returns."
        )
    else:
        _refuse_duplicate_external_subjects(op.get_bind())

    op.create_unique_constraint(
        "uq_user_account_external_subject", "user_account", ["external_subject"]
    )


def downgrade() -> None:
    """Drop the global uniqueness constraint.

    Usable on a development database. Production rollback never depends on it:
    migrations follow expand → migrate → contract, and the destructive step runs
    only after a release is fully promoted (v1.1 §4.2).

    Note what reversing this does *not* restore. Dropping the constraint permits
    duplicate subjects again, and with them the ``MultipleResultsFound`` that
    500s every request for anyone holding one. ``uq_user_account_tenant_subject``
    survives — this migration never touched it — so a downgraded database is
    exactly the schema that existed before, defect included.
    """
    op.drop_constraint(
        "uq_user_account_external_subject", "user_account", type_="unique"
    )
