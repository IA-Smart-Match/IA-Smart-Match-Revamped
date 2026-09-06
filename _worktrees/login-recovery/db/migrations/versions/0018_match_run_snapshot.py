"""``match_run`` — the immutable G1 match-run snapshot (card M8a).

Revision ID: 0018_match_run_snapshot
Revises: 0017_event_persistence
Create Date: 2026-09-04

Plan `docs/plans/2026-08-28-g1-matching-m1-m10-plan.md` card M8a: "Immutable
``match_run`` snapshot rows: inputs hash, registry version, weights, optimizer
+ route-estimate version pins, tenant/unit scoping, created-at. Executed
through the existing durable-command path (transactional outbox per ADR-0005)."
The weight-governance half comes from the signed G1 worksheet
`docs/plans/workshops/g1-workshop-output-worksheet.md` agenda item 4: weights
change only through the MM-005 shadow gate, and "every run records registry
version hash".

**Storage only.** No route reads or writes this table. Card M8b adds the
``/match-runs`` operations, their policy-matrix rows, and the OpenAPI
regeneration; `tests/unit/test_matching_fail_closed.py`'s scan still asserts
that no match, score, or rank operation exists in the committed contract, and
this revision deliberately leaves that assertion true. The one writer is
``smartmatch_worker.handlers.handle_match_run_create``, reached only by
executing a durable ``match-run.create`` job.

What the row is, and what it is not
------------------------------------
It is the **snapshot of the configuration a run was produced under**, plus the
solver's verdict about the search. It is not the shortlist: the selected
professionals are card M10's surface and belong to a table that does not exist
yet, and inventing one here would be storing an assignment nothing can display
and no policy row authorizes. What is stored is everything needed to answer
"under what rules did this run happen, and would running it again give the same
answer" — which is the question a coordinator comparing two scenarios is
actually asking, and the question the legacy engine could not answer at all.

Immutability is a trigger, and that is a deliberate exception
--------------------------------------------------------------
``0017``'s docstring argues against triggers — "a trigger is a second place
where the publish rule lives with no test naming it" — and that argument is
about a trigger that *maintains* data a CHECK constraint could not see. This
one does the opposite: it forbids a statement outright, which no CHECK
constraint can express, because a CHECK is evaluated against the new row alone
and has no way to know whether a row existed before it. The alternatives were
each worse:

* ``CREATE RULE ... ON UPDATE DO INSTEAD NOTHING`` discards the UPDATE
  *silently*. A writer would believe it had corrected a run, and nothing would
  say otherwise — a fake success, which is the class of defect v1.1 §5.5 exists
  to end.
* ``REVOKE UPDATE`` binds to a role name this migration does not know, does not
  show up in a table description, and is undone by any future ``GRANT ALL``.
* Application-side discipline is what "immutable" means in most schemas, and it
  holds exactly as long as every writer remembers. ``match_runs.py`` offers no
  update method, which is the code half; this is the half that survives a psql
  session.

So ``match_run_reject_mutation()`` raises ``restrict_violation`` on UPDATE, and
`tests/integration/test_match_run_snapshot.py` names it. **DELETE is not
blocked**, and that is a separate judgement rather than an oversight: deletion
is a retention question this card does not decide, the tenant-teardown path in
`tests/integration/conftest.py` needs it, and blocking it would make a tenant
undeletable by way of a table nobody can authorize deleting from. Immutability
here means the recorded facts never change, not that the row is eternal.

A correction is a new run
--------------------------
``supersedes_run_id`` is how a correction is expressed: the corrected run is a
new row that names the one it replaces, and the replaced row is untouched. Both
remain readable, which is the point — a coordinator who saw the first result
can still find out what they were shown and why it changed. The self-reference
is composite (``tenant_id, supersedes_run_id``) against
``uq_match_run_tenant_id``, for the reason every other foreign key in this
schema is composite (v1.1 §2.2): a single-column key would let one tenant's run
cite another tenant's. ``ON DELETE RESTRICT``, because a superseded run that
vanished would leave the correction pointing at nothing while still claiming to
be a correction. ``ck_match_run_supersedes_is_not_self`` refuses the one
self-reference a foreign key cannot: a row naming itself.

One snapshot per command
-------------------------
``uq_match_run_job`` spans ``(tenant_id, job_id)``. A handler can execute twice
for the same job — a worker can die after its business write commits and before
the executor's terminal transition does, and the operator's fix is a re-drive
of the identical persisted payload (``review.py`` makes the same argument at
length). Without this constraint a re-drive would write a second snapshot of
the same run, and a scenario comparison would show a coordinator two rows that
are one run. With it the second insert conflicts and
``MatchRunRepository.record`` reads the first row back instead — idempotent
without the writer having to know which attempt it is.

Why the weights are stored as well as hashed
---------------------------------------------
``registry_hash`` proves two runs used the same weights. It cannot say what
they were: a digest is one-way, and a coordinator asking "why was travel
weighted that heavily in March" cannot be answered with a hash. ``weights`` is
the readable copy, and ``ck_match_run_weights_object`` keeps it an object with
something in it — a run recording ``{}`` or ``[]`` or ``null`` as its weights
would satisfy a ``jsonb NOT NULL`` column while recording nothing, and that is
the fabricated-field shape (Fix #15) arriving through a permissive type.

Unknown is not zero (ADR-0011), so nothing here defaults
---------------------------------------------------------
Every pin is ``NOT NULL`` with no server default. A default would let a writer
omit a version and have the database supply a plausible-looking one, and a run
pinned to a version nobody chose is worse than a run that failed to record.
``route_estimate_source`` is a two-value vocabulary rather than a boolean for
the same reason: today every run is ``straight_line`` (the D3 route matrix is
deferred, and ``factors/travel_burden.py`` says so in its own header), and when
D3 lands the older rows must keep saying what they actually used.

Expand only
------------
One new table, one index, one trigger function and its trigger. Nothing is
dropped, renamed, or backfilled, so this revision is safe to run ahead of the
code that reads it (v1.1 §4.2, ADR-0009). On an empty database there is nothing
to migrate; on a populated one there is no existing row to violate a constraint
that applies only to a table this revision creates.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018_match_run_snapshot"
down_revision = "0017_event_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create ``match_run`` and the trigger that refuses to let a row change."""
    op.create_table(
        "match_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        # A5-shaped, as job.owning_unit_id (0006) and event.host_org_unit_id
        # (0017) are: the unit every authorization decision about this run is
        # scoped against. Card M8b's routes authorize against this column, and
        # it is NOT NULL from the moment it exists because a nullable
        # authorization input is a fail-open shape waiting to be written.
        sa.Column("owning_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The durable command that produced this run. NOT NULL and constrained,
        # which is what makes "no route-side insert" a property of the schema
        # rather than a convention: a row cannot exist without a job, and a job
        # is only created by the submission path in `commands.py`.
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The event need the portfolio was selected for, as
        # PortfolioRequest.event_need_id. Text rather than a foreign key: the
        # need is card S12's opportunity surface, and constraining it here
        # would be a change to what that surface's writer must produce —
        # exactly as 0017 declined to constrain
        # pipeline_record.opportunity_event_id.
        sa.Column("event_need_id", sa.Text, nullable=False),
        # --- what was asked -----------------------------------------------
        # smartmatch_domain.match_run.inputs_fingerprint over the candidate
        # pool, the requested size, the seed, and the weights. See that
        # module's docstring for why a digest rather than the pool itself.
        sa.Column("inputs_hash", sa.Text, nullable=False),
        sa.Column("portfolio_size", sa.Integer, nullable=False),
        sa.Column("random_seed", sa.BigInteger, nullable=False),
        # --- the rulebook in force ----------------------------------------
        sa.Column("registry_version", sa.Text, nullable=False),
        sa.Column("registry_hash", sa.Text, nullable=False),
        # The readable copy of what registry_hash fingerprints; see the module
        # docstring for why both are stored.
        sa.Column("weights", postgresql.JSONB, nullable=False),
        # --- the machinery in force ---------------------------------------
        sa.Column("optimizer_model_version", sa.Text, nullable=False),
        sa.Column("solver_name", sa.Text, nullable=False),
        sa.Column("solver_version", sa.Text, nullable=False),
        sa.Column("route_estimate_source", sa.Text, nullable=False),
        sa.Column("route_estimate_version", sa.Text, nullable=False),
        # --- what the search concluded ------------------------------------
        # Mirrors smartmatch_domain.optimizer.PortfolioStatus, whose own
        # docstring asks for exactly this: 'infeasible' is a claim about the
        # model and 'unknown' a claim about the search stopping early, "never
        # conflated ... a stored match_run (M8) reads this status back as
        # reproducible evidence, and reporting a stalled search as 'no valid
        # portfolio exists' would be false, and unrecoverable after the fact".
        sa.Column("portfolio_status", sa.Text, nullable=False),
        # The correction chain. See the module docstring.
        sa.Column("supersedes_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # **No updated_at, deliberately.** 0011's reasoning inverted: carrying
        # one is a statement that mutation is expected here, and here it is
        # forbidden. A column that could only ever equal created_at would be an
        # invitation to write to it.
        sa.PrimaryKeyConstraint("id", name="match_run_pkey"),
        # What supersedes_run_id references, and what card M8b's routes will
        # scope a lookup by.
        sa.UniqueConstraint("tenant_id", "id", name="uq_match_run_tenant_id"),
        # One snapshot per command; see the module docstring.
        sa.UniqueConstraint("tenant_id", "job_id", name="uq_match_run_job"),
        # RESTRICT: reorganizing a unit must not silently delete the record of
        # what was recommended under it.
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id"],
            ["org_unit.tenant_id", "org_unit.id"],
            ondelete="RESTRICT",
        ),
        # RESTRICT: the job is this run's provenance, and a run whose job had
        # been deleted could not be traced back to the command that asked for
        # it.
        sa.ForeignKeyConstraint(
            ["tenant_id", "job_id"],
            ["job.tenant_id", "job.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "supersedes_run_id"],
            ["match_run.tenant_id", "match_run.id"],
            ondelete="RESTRICT",
        ),
        # A row may not supersede itself: the foreign key above is satisfied by
        # a self-reference, and a run claiming to correct itself is a cycle of
        # length one that no reader can unwind.
        sa.CheckConstraint(
            "supersedes_run_id IS NULL OR supersedes_run_id <> id",
            name="ck_match_run_supersedes_is_not_self",
        ),
        # Every pin carries a value, not whitespace. NOT NULL alone accepts the
        # empty string, and an empty version pin is indistinguishable from a
        # writer that forgot — precisely the state ADR-0011 says must not be
        # storable as though it were a measurement.
        sa.CheckConstraint(
            "length(btrim(event_need_id)) > 0 "
            "AND length(btrim(inputs_hash)) > 0 "
            "AND length(btrim(registry_version)) > 0 "
            "AND length(btrim(registry_hash)) > 0 "
            "AND length(btrim(optimizer_model_version)) > 0 "
            "AND length(btrim(solver_name)) > 0 "
            "AND length(btrim(solver_version)) > 0 "
            "AND length(btrim(route_estimate_version)) > 0",
            name="ck_match_run_pins_present",
        ),
        # An object with at least one entry. See the module docstring.
        sa.CheckConstraint(
            "jsonb_typeof(weights) = 'object' AND weights <> '{}'::jsonb",
            name="ck_match_run_weights_object",
        ),
        # PortfolioRequest refuses portfolio_size < 1 in the domain; this is
        # the same rule where a hand-written INSERT can reach it.
        sa.CheckConstraint("portfolio_size >= 1", name="ck_match_run_portfolio_size"),
        # CP-SAT takes a non-negative seed, and a negative one stored here
        # would name a run nobody can reproduce.
        sa.CheckConstraint("random_seed >= 0", name="ck_match_run_random_seed"),
        sa.CheckConstraint(
            "route_estimate_source IN ('straight_line','route_matrix')",
            name="ck_match_run_route_estimate_source",
        ),
        sa.CheckConstraint(
            "portfolio_status IN ('optimal','feasible','infeasible','unknown')",
            name="ck_match_run_portfolio_status",
        ),
    )

    # The access path cards M8b and M10 both read: one unit's runs within one
    # tenant, newest first. Declared with the table rather than left for the
    # card that adds the route — an index is cheap and a sequential scan
    # discovered later is not (0017 makes the same call for
    # `ix_event_host_unit`).
    op.create_index(
        "ix_match_run_unit_created",
        "match_run",
        ["tenant_id", "owning_unit_id", sa.text("created_at DESC")],
    )

    # Immutability, structurally. See the module docstring for why this is a
    # trigger, and why UPDATE only.
    op.execute(
        """
        CREATE FUNCTION match_run_reject_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'match_run rows are immutable: a correction is a new run that '
                'sets supersedes_run_id, never an UPDATE of an existing one '
                '(migration 0018, plan card M8a)'
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER match_run_is_immutable
        BEFORE UPDATE ON match_run
        FOR EACH ROW EXECUTE FUNCTION match_run_reject_mutation();
        """
    )


def downgrade() -> None:
    """Drop the trigger, its function, the index, and the table.

    In reverse creation order. Dropping the table first would take the trigger
    with it and leave the function behind, holding a name a later revision
    could not reuse without noticing.
    """
    op.execute("DROP TRIGGER IF EXISTS match_run_is_immutable ON match_run")
    op.execute("DROP FUNCTION IF EXISTS match_run_reject_mutation()")
    op.drop_index("ix_match_run_unit_created", table_name="match_run")
    op.drop_table("match_run")
