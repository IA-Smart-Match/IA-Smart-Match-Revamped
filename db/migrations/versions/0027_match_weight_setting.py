"""Unit-scoped matching-weight overrides, and the immutable log of their changes.

Customer §5 requires the matching weights to live in "one configurable location"
that a Speaker Connector can adjust, and in the same breath forbids scattering or
duplicating the weight values. This revision is the storage half of that, and the
shape it stores is the reason both halves can hold at once.

Why this table holds **overrides**, not weights
=================================================
``match_weight_setting.overrides`` is a partial map: the factor keys this unit
has deliberately changed, and nothing else. A factor absent from it has no stored
value anywhere in this database, and its weight comes from
``smartmatch_domain.factor_registry`` at scoring time.

That absence is the whole design. The obvious alternative — a row carrying all
four weights, seeded from the registry — would put a second copy of ADR-0016's
approved figures in the database, and the two copies would disagree the first
time either changed, with nothing able to say which one scored a run. So:

* **There is no server default on ``overrides``** naming any weight, and no
  backfill. A unit with no row is not a unit with default weights *stored*; it is
  a unit whose weights are read from the registry.
* **Clearing an override deletes the entry**, leaving ``{}``. It does not write
  the registry value back, because writing it back is what creates the copy.
* An **empty ``{}`` is meaningful and permitted**: it is a unit that configured
  something and then reset it, which has an author and a timestamp that a unit
  with no row does not. ``ck_match_weight_setting_overrides_object`` requires a
  JSON object and nothing more — the vocabulary of admissible *keys* and the
  refusal of negative, non-finite and zero-total values live in
  ``smartmatch_domain.weight_settings``, because a CHECK constraint cannot see
  the registry and would become one more place a factor key is written down.

Why the revision table exists, and why it is immutable
========================================================
Changing a weight changes every future shortlist a unit produces. §5 says a
Connector may make that change; it does not say the change may be untraceable.
``match_weight_setting`` carries the current value, its ``version`` and the
account that last wrote it, which answers "what is in force and who set it".
``match_weight_setting_revision`` answers "and what was it before" — one
insert-only row per accepted change, unique on ``(tenant, unit, version)``.

The immutability trigger is 0018's, for 0018's reason and with its exception: a
trigger is normally a second place the rules live, and is justified here because
a CHECK cannot express "this row may not change". An audit log that can be
rewritten in a psql session is not an audit log, and the guarantee is worth the
exception exactly as it was for ``match_run``.

Note what this revision does **not** do to ``match_run``. A stored run already
carries the weights it was scored with (``0018``'s ``match_run.weights``) and is
immutable, so a settings change cannot reach one: there is no foreign key from a
run to a setting, and adding one would make a historical run's meaning depend on
a mutable row. The run's copy is a snapshot, not a reference, and that is the
whole of "historical match runs are immutable" at the schema level.

Scoping
=========
``(tenant_id, owning_unit_id)``, A5-shaped like ``import_batch``, ``job`` and
``event_registration``: the unit whose matching this configures. Unique on that
pair, so a unit has one weighting rather than a most-recent one. Both foreign
keys are composite and ``ON DELETE RESTRICT`` — reorganizing a unit must not
silently delete its configuration, and deleting an account must not silently
erase the authorship of a change it made.

Expand-only
=============
Two new tables, one trigger function and its trigger. Nothing is dropped,
renamed, backfilled or widened, and no existing table is touched — safe under a
rolling deploy per v1.1 §4.2: the old release does not know these tables exist,
and a unit with no row scores exactly as it did before, on the registry's own
weights.

Open questions this revision leaves open
==========================================
* **OQ-CBA-032** — whether a weight change should require a shadow evaluation
  before it takes effect. MM-005 says weights may only change through a
  shadow-evaluation gate; this revision gives a Connector a way to change them
  now, with an audit trail and a version, and does not build that gate. Recorded
  rather than assumed: a gate nobody specified would be a policy invented in DDL.
* **OQ-CBA-033** — whether an override should be scoped per scoring mode. It is
  not here: one map covers both modes, and the virtual model simply never reads
  the proximity entry (customer §11). A per-mode setting would be a second row
  shape and a second thing to keep consistent, for a distinction no requirement
  has yet drawn.
* **OQ-CBA-034** — how long the revision log is kept. Nothing prunes it, and
  nothing should until somebody says what the retention is.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0027_match_weight_setting"
down_revision = "0026_event_registration"
branch_labels = None
depends_on = None


#: Required of both tables' JSON column. An object, so ``{}`` is admissible and a
#: bare array or scalar is not. Deliberately says nothing about which keys or
#: which values are acceptable — see the module docstring.
_OVERRIDES_IS_OBJECT = "jsonb_typeof(overrides) = 'object'"

#: Versions start at 1 and only ever increase. A zero or negative version could
#: not have come from an accepted change.
_VERSION_IS_POSITIVE = "version >= 1"


def upgrade() -> None:
    """Create the settings table, its revision log, and the log's immutability."""
    op.create_table(
        "match_weight_setting",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        # A5-shaped: the unit whose matching this configures.
        sa.Column("owning_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The overrides only. No server default naming a weight, and no
        # backfill: a factor absent here reads its weight from the registry.
        sa.Column("overrides", postgresql.JSONB, nullable=False),
        # Monotonic, and what a client echoes back to say which version it meant
        # to modify — so two Connectors editing one unit's weights cannot
        # silently overwrite each other.
        sa.Column("version", sa.Integer, nullable=False),
        # Who last changed it. RESTRICT below, so the authorship of a change
        # cannot be erased by deleting the account that made it.
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="match_weight_setting_pkey"),
        # One weighting per unit, not a most-recent one.
        sa.UniqueConstraint(
            "tenant_id",
            "owning_unit_id",
            name="uq_match_weight_setting_unit",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id"],
            ["org_unit.tenant_id", "org_unit.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "updated_by_user_id"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            _OVERRIDES_IS_OBJECT,
            name="ck_match_weight_setting_overrides_object",
        ),
        sa.CheckConstraint(
            _VERSION_IS_POSITIVE,
            name="ck_match_weight_setting_version",
        ),
    )

    op.create_table(
        "match_weight_setting_revision",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owning_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The state this change put the unit into, at this version. Stored in
        # full rather than as a diff: a diff is only readable next to the row it
        # applies to, and the row it applies to is the one that moved.
        sa.Column("overrides", postgresql.JSONB, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("changed_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="match_weight_setting_revision_pkey"),
        # One row per version per unit. This is also the log's idempotency: a
        # re-driven write of the same version cannot append a second entry
        # claiming a change that happened once.
        sa.UniqueConstraint(
            "tenant_id",
            "owning_unit_id",
            "version",
            name="uq_match_weight_setting_revision_version",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id"],
            ["org_unit.tenant_id", "org_unit.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "changed_by_user_id"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            _OVERRIDES_IS_OBJECT,
            name="ck_match_weight_setting_revision_overrides_object",
        ),
        sa.CheckConstraint(
            _VERSION_IS_POSITIVE,
            name="ck_match_weight_setting_revision_version",
        ),
    )

    # 0018's trigger, for 0018's reason: a CHECK cannot express "this row may not
    # change", and an audit log that survives a hand-written UPDATE is the only
    # kind worth keeping. UPDATE only — nothing in this codebase issues a DELETE
    # against the log, and a DELETE trigger would also make the table undroppable
    # in development.
    op.execute(
        """
        CREATE FUNCTION match_weight_setting_revision_reject_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'match_weight_setting_revision rows are immutable: a change to a '
                'unit''s weights is a new revision at the next version, never an '
                'UPDATE of an existing one (migration 0027)'
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER match_weight_setting_revision_is_immutable
        BEFORE UPDATE ON match_weight_setting_revision
        FOR EACH ROW EXECUTE FUNCTION match_weight_setting_revision_reject_mutation();
        """
    )


def downgrade() -> None:
    """Drop the trigger, its function, and both tables, in reverse order.

    A development tool, not a production rollback path (v1.1 §4.2). Dropping
    these tables discards every unit's configuration and the log of how it got
    there; the units then score on the registry's own weights again, which is the
    one respect in which this rollback is undramatic.
    """
    op.execute(
        "DROP TRIGGER IF EXISTS match_weight_setting_revision_is_immutable "
        "ON match_weight_setting_revision"
    )
    op.execute("DROP FUNCTION IF EXISTS match_weight_setting_revision_reject_mutation()")
    op.drop_table("match_weight_setting_revision")
    op.drop_table("match_weight_setting")
