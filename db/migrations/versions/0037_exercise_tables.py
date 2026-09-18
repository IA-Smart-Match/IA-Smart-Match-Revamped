"""The class-exercise tables: eight of them, prefixed, and tenancy-free.

Design spec §2 (``docs/superpowers/specs/2026-09-16-class-exercise-design.md``)
and ADR-0025 D2, which is the whole reason this revision looks unlike every
other one in this directory:

    The exercise stores its data in tables prefixed ``exercise_`` keyed by
    ``(exercise_dataset_id, team_number)``. They carry no ``tenant_id``, no
    ``owning_unit_id``, and no foreign key to ``user_account``.

Modelling the class as an ``org_unit`` under the CBA tenant was rejected: it
would mint about 1,800 fake principals and put synthetic rows one join from
real ones. So the absence of ``tenant_id`` here is not an omission to be fixed
later — it is the decision. Every foreign key below stays inside the
``exercise_`` family, in both directions, and
``tests/unit/test_exercise_schema.py`` walks the mirror to say so without a
database.

What this revision is not
=========================
Tables only. No repository, no router, no ingest, no row. Nothing reads a CBA
table and no CBA table is altered, so this revision is invisible to every
existing query. The ingest that fills these tables (§3), the repositories
(§§5-13) and the routers (§1) are later tracks.

PLACEHOLDER (OQ-CE-01)
======================
``exercise_profile``'s ``display_name``, ``major``, ``class_year``,
``past_event_keys``, ``stated_interests``, ``career_goal`` and
``hidden_true_interests``, and ``exercise_event``'s ``event_key``, ``name``,
``topic_tags``, ``target_majors``, ``is_exercise_event`` and ``sequence``, are
built to design spec §2's *shape* and to no vocabulary. Ann's 20-row sample
(due Fri Sept 18) decides the mapping from her column names, the ``class_year``
values, whether past events are named by key or by title, and whether a career
goal is a G3 term or a small fixed list.

Consequently **no CHECK constrains ``class_year`` or ``career_goal``**, and
that is deliberate rather than forgotten. A vocabulary written here would
answer the open question in DDL, where changing the answer costs a migration
instead of an ingest edit. The register row stays OPEN; this revision does not
close it.

Two other placeholders touch this schema without living in it.
``exercise_team_workspace.seed`` is the per-team chance element of §11, whose
four coefficients are OQ-CE-03 — the seed is per-team state and belongs in a
row; a coefficient is a rule and belongs in a named constant in
``smartmatch_domain``, so no coefficient value appears here. And
``uq_exercise_team_workspace_dataset_team`` is OQ-CE-08's "shared per team
number" reading expressed as a constraint: a second browser tab entering team
3 finds the same workspace because there can only be one.

Constraints that carry a rule
=============================
* ``invite_limit`` defaults to **30** (§5). Ann's stated number, adjustable
  per dataset by the instructor route, and not an open question.
* ``ck_exercise_team_workspace_team_number``: teams 1-6, the six in the class.
* ``uq_exercise_saved_setting_name``: a saved setting is named, and the name
  identifies it within a team's work on one event (§6). The *at most three per
  (workspace, event)* half of §6 is **not** here. A count is not a uniqueness;
  expressing it in DDL would take a trigger, and a trigger that silently
  refuses the fourth save is a worse error message than the sentence the
  repository will write. It is repository work in a later track.
* ``uq_exercise_result_run_workspace_event``: §9's one-run rule as a
  constraint rather than a check in code, so a second run is refused by the
  database whichever path reaches it.
* ``exercise_result_unlock`` is keyed ``(dataset_id, event_key)`` and the
  *absence* of a row means locked (§9). A boolean column would need a row per
  event written at ingest to mean anything, and a missing row would then be a
  third state nobody defined.
* ``workspace_token_hash`` stores a hash. The raw workspace token of §15 lives
  in an httpOnly cookie and is never written down; the column is named for
  what it holds so that a repository written over this table cannot drift into
  storing a credential at rest without renaming it first.

The three ``dataset_id`` columns that look redundant
====================================================
``exercise_profile_overlay``, ``exercise_saved_setting`` and
``exercise_result_run`` each carry ``dataset_id`` alongside ``workspace_id``,
although the workspace already names a dataset. This is ``0036``'s argument
about ``host_organization_member.unit_id``, applied to a dataset instead of an
org unit: it is what lets the foreign keys be composite, so a row pointing at
one dataset's profile or event from another dataset's workspace is
unrepresentable rather than something a repository has to remember to check.

Expand-only
===========
Eight CREATE TABLEs. No existing table is altered, dropped, renamed or
backfilled, and no existing row is read — safe under a rolling deploy per
v1.1 §4.2.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0037_exercise_tables"
down_revision = "0036_host_organization"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)
_TS = sa.DateTime(timezone=True)
_TEXTS = postgresql.ARRAY(sa.Text)
_INTS = postgresql.ARRAY(sa.Integer)

#: An empty array, as a server default. "No topics recorded" and "the column
#: was never written" are the same fact for these columns, so a NULL array
#: would only make every reader choose between ``COALESCE`` and a crash.
_EMPTY_ARRAY = sa.text("'{}'")


def upgrade() -> None:
    """Create the eight ``exercise_`` tables of design spec §2."""
    op.create_table(
        "exercise_dataset",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("source_filename", sa.Text, nullable=False),
        sa.Column("uploaded_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("row_count", sa.Integer, nullable=False),
        sa.Column("checksum", sa.Text, nullable=False),
        # §5. Ann's number; the instructor route adjusts it per dataset.
        sa.Column("invite_limit", sa.Integer, nullable=False, server_default=sa.text("30")),
        sa.Column("license_line", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("id", name="exercise_dataset_pkey"),
        sa.CheckConstraint(
            "length(btrim(label)) > 0 AND length(label) <= 200",
            name="ck_exercise_dataset_label_shape",
        ),
        sa.CheckConstraint("row_count >= 0", name="ck_exercise_dataset_row_count"),
        sa.CheckConstraint("invite_limit >= 1", name="ck_exercise_dataset_invite_limit"),
    )

    # PLACEHOLDER (OQ-CE-01): the descriptive columns below are built to
    # design spec §2's names and to no vocabulary. See the module docstring.
    op.create_table(
        "exercise_profile",
        sa.Column("dataset_id", _UUID, nullable=False),
        sa.Column("profile_no", sa.Integer, nullable=False),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("major", sa.Text, nullable=True),
        # No CHECK. OQ-CE-01 decides this vocabulary, not this revision.
        sa.Column("class_year", sa.Text, nullable=True),
        sa.Column("past_event_keys", _TEXTS, nullable=False, server_default=_EMPTY_ARRAY),
        # NULL is "no card on file"; ``{}`` is "a card with nothing on it".
        # §7's three states, and the distinction the markers are built on.
        sa.Column("stated_interests", _TEXTS, nullable=True),
        # No CHECK, for the same reason ``class_year`` has none.
        sa.Column("career_goal", sa.Text, nullable=True),
        # ADR-0025 D6: withheld. Read by the simulated-results rule alone and
        # named in ``EXERCISE_WITHHELD_FIELDS``.
        sa.Column("hidden_true_interests", _TEXTS, nullable=False, server_default=_EMPTY_ARRAY),
        sa.PrimaryKeyConstraint("dataset_id", "profile_no", name="exercise_profile_pkey"),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["exercise_dataset.id"],
            ondelete="CASCADE",
            name="fk_exercise_profile_dataset",
        ),
        sa.CheckConstraint("profile_no >= 1", name="ck_exercise_profile_profile_no"),
        sa.CheckConstraint(
            "length(btrim(display_name)) > 0", name="ck_exercise_profile_display_name_shape"
        ),
    )

    # PLACEHOLDER (OQ-CE-01) again: whether a past event is named by key or by
    # title is part of what the sample settles. ``event_key`` is the
    # identifier either way.
    op.create_table(
        "exercise_event",
        sa.Column("dataset_id", _UUID, nullable=False),
        sa.Column("event_key", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("topic_tags", _TEXTS, nullable=False, server_default=_EMPTY_ARRAY),
        sa.Column("target_majors", _TEXTS, nullable=False, server_default=_EMPTY_ARRAY),
        sa.Column("is_exercise_event", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.PrimaryKeyConstraint("dataset_id", "event_key", name="exercise_event_pkey"),
        sa.UniqueConstraint("dataset_id", "sequence", name="uq_exercise_event_sequence"),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["exercise_dataset.id"],
            ondelete="CASCADE",
            name="fk_exercise_event_dataset",
        ),
        sa.CheckConstraint("sequence >= 1", name="ck_exercise_event_sequence"),
        sa.CheckConstraint("length(btrim(event_key)) > 0", name="ck_exercise_event_key_shape"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_exercise_event_name_shape"),
    )

    op.create_table(
        "exercise_team_workspace",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("dataset_id", _UUID, nullable=False),
        sa.Column("team_number", sa.Integer, nullable=False),
        # §15. A hash, never the token.
        sa.Column("workspace_token_hash", sa.Text, nullable=False),
        # §11's chance element, fixed per team. The coefficients it is drawn
        # against are OQ-CE-03 and are not values in this schema.
        sa.Column("seed", sa.BigInteger, nullable=False),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        # §12. NULL is "has not chosen", which is none of the three choices.
        sa.Column("asking_choice", sa.Text, nullable=True),
        sa.Column("refreshed_at", _TS, nullable=True),
        sa.PrimaryKeyConstraint("id", name="exercise_team_workspace_pkey"),
        # OQ-CE-08's shared-per-team reading, as a constraint.
        sa.UniqueConstraint(
            "dataset_id", "team_number", name="uq_exercise_team_workspace_dataset_team"
        ),
        # What the three child tables' composite keys reference.
        sa.UniqueConstraint("dataset_id", "id", name="uq_exercise_team_workspace_dataset_id"),
        sa.UniqueConstraint("workspace_token_hash", name="uq_exercise_team_workspace_token_hash"),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["exercise_dataset.id"],
            ondelete="CASCADE",
            name="fk_exercise_team_workspace_dataset",
        ),
        sa.CheckConstraint(
            "team_number BETWEEN 1 AND 6", name="ck_exercise_team_workspace_team_number"
        ),
        sa.CheckConstraint(
            "length(btrim(workspace_token_hash)) > 0",
            name="ck_exercise_team_workspace_token_hash_shape",
        ),
        # Fixed by the design spec and the case rather than by an open
        # question, so unlike ``class_year`` it is constrained.
        sa.CheckConstraint(
            "asking_choice IS NULL OR asking_choice IN "
            "('better_recommendations', 'small_reward', 'required')",
            name="ck_exercise_team_workspace_asking_choice",
        ),
        # §13: the refresh follows the choice, and the choice decides the
        # share the refresh applies.
        sa.CheckConstraint(
            "refreshed_at IS NULL OR asking_choice IS NOT NULL",
            name="ck_exercise_team_workspace_refresh_after_choice",
        ),
    )

    op.create_table(
        "exercise_profile_overlay",
        sa.Column("workspace_id", _UUID, nullable=False),
        sa.Column("dataset_id", _UUID, nullable=False),
        sa.Column("profile_no", sa.Integer, nullable=False),
        sa.Column("added_event_topics", _TEXTS, nullable=False, server_default=_EMPTY_ARRAY),
        # NULL is "this team has no card for this profile"; ``{}`` is a card
        # with nothing on it.
        sa.Column("card_interests", _TEXTS, nullable=True),
        sa.Column("card_career_goal", sa.Text, nullable=True),
        sa.Column("non_responding", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint("workspace_id", "profile_no", name="exercise_profile_overlay_pkey"),
        # CASCADE, both of them: an overlay row is part of a team's workspace
        # and of a dataset's profile rather than a thing that outlives either.
        # "Reset team" is a delete the database completes.
        sa.ForeignKeyConstraint(
            ["dataset_id", "workspace_id"],
            ["exercise_team_workspace.dataset_id", "exercise_team_workspace.id"],
            ondelete="CASCADE",
            name="fk_exercise_profile_overlay_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "profile_no"],
            ["exercise_profile.dataset_id", "exercise_profile.profile_no"],
            ondelete="CASCADE",
            name="fk_exercise_profile_overlay_profile",
        ),
    )

    op.create_table(
        "exercise_saved_setting",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("workspace_id", _UUID, nullable=False),
        sa.Column("dataset_id", _UUID, nullable=False),
        sa.Column("event_key", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        # §6's four weights, validated by the domain's
        # ``validate_weight_overrides`` before anything writes them.
        sa.Column("weights", postgresql.JSONB, nullable=False),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="exercise_saved_setting_pkey"),
        # The "at most three" half of §6 is repository work — see the module
        # docstring for why it is not a trigger here.
        sa.UniqueConstraint(
            "workspace_id", "event_key", "name", name="uq_exercise_saved_setting_name"
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "workspace_id"],
            ["exercise_team_workspace.dataset_id", "exercise_team_workspace.id"],
            ondelete="CASCADE",
            name="fk_exercise_saved_setting_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "event_key"],
            ["exercise_event.dataset_id", "exercise_event.event_key"],
            ondelete="CASCADE",
            name="fk_exercise_saved_setting_event",
        ),
        sa.CheckConstraint(
            "length(btrim(name)) > 0 AND length(name) <= 100",
            name="ck_exercise_saved_setting_name_shape",
        ),
    )

    op.create_table(
        "exercise_result_run",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("workspace_id", _UUID, nullable=False),
        sa.Column("dataset_id", _UUID, nullable=False),
        sa.Column("event_key", sa.Text, nullable=False),
        sa.Column("round", sa.Integer, nullable=False),
        # NULL when the team ran on weights they had not saved. Not a foreign
        # key: a setting renamed afterwards must not rewrite what was run.
        sa.Column("setting_name", sa.Text, nullable=True),
        sa.Column("invited_profile_nos", _INTS, nullable=False, server_default=_EMPTY_ARRAY),
        sa.Column("signed_up_profile_nos", _INTS, nullable=False, server_default=_EMPTY_ARRAY),
        sa.Column("attended_profile_nos", _INTS, nullable=False, server_default=_EMPTY_ARRAY),
        # §10's second panel, stored as written rather than recomputed on
        # read, so the comparison a team saw is the comparison it keeps.
        sa.Column("email_everyone", postgresql.JSONB, nullable=False),
        sa.Column("seats_empty", sa.Integer, nullable=False),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="exercise_result_run_pkey"),
        # §9's one-run rule. The second run hits this.
        sa.UniqueConstraint(
            "workspace_id", "event_key", name="uq_exercise_result_run_workspace_event"
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "workspace_id"],
            ["exercise_team_workspace.dataset_id", "exercise_team_workspace.id"],
            ondelete="CASCADE",
            name="fk_exercise_result_run_workspace",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "event_key"],
            ["exercise_event.dataset_id", "exercise_event.event_key"],
            ondelete="CASCADE",
            name="fk_exercise_result_run_event",
        ),
        sa.CheckConstraint("round IN (1, 2)", name="ck_exercise_result_run_round"),
        sa.CheckConstraint("seats_empty >= 0", name="ck_exercise_result_run_seats_empty"),
    )

    op.create_table(
        "exercise_result_unlock",
        sa.Column("dataset_id", _UUID, nullable=False),
        sa.Column("event_key", sa.Text, nullable=False),
        sa.Column("unlocked_at", _TS, nullable=False, server_default=sa.text("now()")),
        # Absence of a row is "locked" (§9).
        sa.PrimaryKeyConstraint("dataset_id", "event_key", name="exercise_result_unlock_pkey"),
        sa.ForeignKeyConstraint(
            ["dataset_id", "event_key"],
            ["exercise_event.dataset_id", "exercise_event.event_key"],
            ondelete="CASCADE",
            name="fk_exercise_result_unlock_event",
        ),
    )


def downgrade() -> None:
    """Drop the eight tables, children first.

    A development tool, not a production rollback path (v1.1 §4.2). Unlike
    every other downgrade in this directory, this one destroys nothing a
    person outside the class ever sees: the rows are a teaching exercise's
    synthetic profiles and the six teams' work on them. That is the same
    property D2 was chosen for, read from the other end.
    """
    op.drop_table("exercise_result_unlock")
    op.drop_table("exercise_result_run")
    op.drop_table("exercise_saved_setting")
    op.drop_table("exercise_profile_overlay")
    op.drop_table("exercise_team_workspace")
    op.drop_table("exercise_event")
    op.drop_table("exercise_profile")
    op.drop_table("exercise_dataset")
