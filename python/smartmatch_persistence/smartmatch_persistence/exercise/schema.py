"""The class-exercise tables, mirroring ``db/migrations/versions/0037``.

Design spec §2, ADR-0025 D2. Hand-written on the shared ``METADATA`` for the
same reason every other table in this repository is: ``schema.py``'s mirror is
what ``tests/integration/test_schema_matches_migration.py`` compares against a
freshly migrated database, and a table defined on a private ``MetaData`` would
be invisible to that comparison while still existing in the database — which
the guard's reverse direction would report as an unmodelled table.

Sharing the ``MetaData`` is not sharing tenancy. Nothing here has a
``tenant_id``, nothing here references a table outside this family, and
``tests/unit/test_exercise_schema.py`` walks both directions of that claim.

PLACEHOLDER (OQ-CE-01)
======================
The columns describing a profile and an event are built to the *shape* design
spec §2 names and to no vocabulary at all. Ann's 20-row sample decides the
column mapping, the ``class_year`` values, whether past events are named by
key or by title, and whether a career goal is a G3 term or a small fixed list.
Until it arrives:

* ``class_year`` and ``career_goal`` are ``TEXT`` with **no CHECK**. Writing
  today's guess as a constraint would answer the open question in DDL, where
  changing the answer costs a migration instead of an ingest edit.
* the list columns are ``TEXT[]`` rather than a normalized side table, so a
  vocabulary decision changes what is written, not what exists.

Marked here and in the migration docstring, and asserted literally by
``test_the_placeholder_marker_is_literally_present``.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from smartmatch_persistence.schema import METADATA

__all__ = [
    "EXERCISE_TABLES",
    "EXERCISE_WITHHELD_FIELDS",
    "exercise_dataset",
    "exercise_event",
    "exercise_profile",
    "exercise_profile_overlay",
    "exercise_result_run",
    "exercise_result_unlock",
    "exercise_saved_setting",
    "exercise_team_workspace",
]

_UUID = postgresql.UUID(as_uuid=True)
_TS = sa.DateTime(timezone=True)
_TEXTS = postgresql.ARRAY(sa.Text)
_INTS = postgresql.ARRAY(sa.Integer)

#: An empty PostgreSQL array, as a server default. Written out rather than
#: left to the application because "no topics recorded" and "the column was
#: never written" are the same fact for these columns, and a NULL array would
#: make every reader choose between ``COALESCE`` and a crash.
_EMPTY_ARRAY = sa.text("'{}'")

#: ADR-0025 D6. The data file's hidden "true interests" column is stored on
#: the profile row, is read by the simulated-results rule alone, appears on no
#: response model, and is named here so that removing it from the withheld set
#: is a failing test rather than a silent widening.
#:
#: A frozenset of *column names*, not of paths: the rule is about the field
#: wherever it appears, and the response models that must not carry it are
#: written in later tracks against this name.
EXERCISE_WITHHELD_FIELDS: frozenset[str] = frozenset({"hidden_true_interests"})


exercise_dataset = sa.Table(
    "exercise_dataset",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("label", sa.Text, nullable=False),
    sa.Column("source_filename", sa.Text, nullable=False),
    sa.Column("uploaded_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.Column("row_count", sa.Integer, nullable=False),
    sa.Column("checksum", sa.Text, nullable=False),
    # §5. Thirty is Ann's stated number and carries no open question; the
    # instructor route changes it per dataset, which is why it is a column
    # rather than a constant.
    sa.Column("invite_limit", sa.Integer, nullable=False, server_default=sa.text("30")),
    # Nullable: a data file that names no licence has not named one, and an
    # empty string would be a statement nobody made (ADR-0011 rule 1).
    sa.Column("license_line", sa.Text, nullable=True),
    sa.PrimaryKeyConstraint("id", name="exercise_dataset_pkey"),
    sa.CheckConstraint(
        "length(btrim(label)) > 0 AND length(label) <= 200",
        name="ck_exercise_dataset_label_shape",
    ),
    sa.CheckConstraint("row_count >= 0", name="ck_exercise_dataset_row_count"),
    sa.CheckConstraint("invite_limit >= 1", name="ck_exercise_dataset_invite_limit"),
)


exercise_profile = sa.Table(
    "exercise_profile",
    METADATA,
    sa.Column(
        "dataset_id",
        _UUID,
        sa.ForeignKey("exercise_dataset.id", ondelete="CASCADE"),
        nullable=False,
    ),
    # The profile's number inside its dataset — "the 300". Not an id: the
    # screens and the stored result runs name a person by this number, and a
    # replaced data file produces a new dataset rather than renumbering this
    # one.
    sa.Column("profile_no", sa.Integer, nullable=False),
    # PLACEHOLDER (OQ-CE-01) — the seven columns below are built to design
    # spec §2's names and to no vocabulary. See the module docstring.
    sa.Column("display_name", sa.Text, nullable=False),
    sa.Column("major", sa.Text, nullable=True),
    sa.Column("class_year", sa.Text, nullable=True),
    sa.Column("past_event_keys", _TEXTS, nullable=False, server_default=_EMPTY_ARRAY),
    # Nullable, and that is the three-state rule of §7 rather than an
    # oversight: NULL is "no card on file", ``{}`` is "a card with nothing on
    # it". ``smartmatch_domain/match_depth.py`` draws the same distinction,
    # and collapsing the two would report an empty card as an absent one.
    sa.Column("stated_interests", _TEXTS, nullable=True),
    sa.Column("career_goal", sa.Text, nullable=True),
    # ADR-0025 D6: withheld. Read by the simulated-results rule and by nothing
    # else; on no response model; in `EXERCISE_WITHHELD_FIELDS` above.
    sa.Column("hidden_true_interests", _TEXTS, nullable=False, server_default=_EMPTY_ARRAY),
    sa.PrimaryKeyConstraint("dataset_id", "profile_no", name="exercise_profile_pkey"),
    sa.CheckConstraint("profile_no >= 1", name="ck_exercise_profile_profile_no"),
    sa.CheckConstraint(
        "length(btrim(display_name)) > 0", name="ck_exercise_profile_display_name_shape"
    ),
)


exercise_event = sa.Table(
    "exercise_event",
    METADATA,
    sa.Column(
        "dataset_id",
        _UUID,
        sa.ForeignKey("exercise_dataset.id", ondelete="CASCADE"),
        nullable=False,
    ),
    # PLACEHOLDER (OQ-CE-01) — the six columns below are built to design spec
    # §2's names. Whether a past event is named by key or by title is part of
    # what the 20-row sample settles; ``event_key`` is the identifier either
    # way, which is why it is the key and ``name`` is the label.
    sa.Column("event_key", sa.Text, nullable=False),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("topic_tags", _TEXTS, nullable=False, server_default=_EMPTY_ARRAY),
    sa.Column("target_majors", _TEXTS, nullable=False, server_default=_EMPTY_ARRAY),
    # True for the two events the teams run — Northline (round 1) and Harbor
    # (round 2) — and false for the ten past events a profile may have
    # attended. The distinction is what keeps a past event out of the picker.
    sa.Column("is_exercise_event", sa.Boolean, nullable=False, server_default=sa.text("false")),
    sa.Column("sequence", sa.Integer, nullable=False),
    sa.PrimaryKeyConstraint("dataset_id", "event_key", name="exercise_event_pkey"),
    # One event per position. The ten past events and the two rounds are an
    # ordered list in the case; two events claiming position 11 would make
    # "round one" ambiguous.
    sa.UniqueConstraint("dataset_id", "sequence", name="uq_exercise_event_sequence"),
    sa.CheckConstraint("sequence >= 1", name="ck_exercise_event_sequence"),
    sa.CheckConstraint("length(btrim(event_key)) > 0", name="ck_exercise_event_key_shape"),
    sa.CheckConstraint("length(btrim(name)) > 0", name="ck_exercise_event_name_shape"),
)


exercise_team_workspace = sa.Table(
    "exercise_team_workspace",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column(
        "dataset_id",
        _UUID,
        sa.ForeignKey("exercise_dataset.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("team_number", sa.Integer, nullable=False),
    # §15: the server row is the truth and the cookie is a pointer. A *hash*
    # of the opaque token, never the token — the column name is the whole of
    # what stops a repository written over this table from storing a
    # credential at rest, so it is asserted by name in the unit test.
    sa.Column("workspace_token_hash", sa.Text, nullable=False),
    # §11's chance element, fixed per team so running the same list twice
    # gives the same answer. The coefficients it is drawn against are
    # OQ-CE-03 and are named constants in the domain module, not values here:
    # a seed is per-team state, a coefficient is a rule.
    sa.Column("seed", sa.BigInteger, nullable=False),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    # §12. NULL means the team has not chosen yet, which is a different thing
    # from any of the three choices. The vocabulary is fixed by the design
    # spec and by the case rather than by an open question, so unlike
    # ``class_year`` it is constrained here.
    sa.Column("asking_choice", sa.Text, nullable=True),
    # §13: the refresh is allowed once, and only after the asking choice.
    # NULL means not yet refreshed.
    sa.Column("refreshed_at", _TS, nullable=True),
    sa.PrimaryKeyConstraint("id", name="exercise_team_workspace_pkey"),
    # §15: the entry screen asks for a team number and the server creates or
    # returns *the* workspace for (active dataset, team number). Two rows
    # would make "this team's saved runs" two answers to one question —
    # OQ-CE-08's shared-per-team reading, as a constraint.
    sa.UniqueConstraint(
        "dataset_id", "team_number", name="uq_exercise_team_workspace_dataset_team"
    ),
    # What the overlay, the saved settings and the result runs reference, so
    # that a child row cannot disagree with its workspace about which dataset
    # it belongs to. Same convention as ``uq_host_organization_tenant_id``.
    sa.UniqueConstraint("dataset_id", "id", name="uq_exercise_team_workspace_dataset_id"),
    sa.UniqueConstraint("workspace_token_hash", name="uq_exercise_team_workspace_token_hash"),
    sa.CheckConstraint(
        "team_number BETWEEN 1 AND 6", name="ck_exercise_team_workspace_team_number"
    ),
    sa.CheckConstraint(
        "length(btrim(workspace_token_hash)) > 0",
        name="ck_exercise_team_workspace_token_hash_shape",
    ),
    sa.CheckConstraint(
        "asking_choice IS NULL OR asking_choice IN "
        "('better_recommendations', 'small_reward', 'required')",
        name="ck_exercise_team_workspace_asking_choice",
    ),
    # §13 in one line: a refresh that happened before a choice was made would
    # be a refresh with no share to apply, and the share is what the choice
    # decides.
    sa.CheckConstraint(
        "refreshed_at IS NULL OR asking_choice IS NOT NULL",
        name="ck_exercise_team_workspace_refresh_after_choice",
    ),
)


exercise_profile_overlay = sa.Table(
    "exercise_profile_overlay",
    METADATA,
    sa.Column("workspace_id", _UUID, nullable=False),
    # Carried alongside ``workspace_id`` and ``profile_no``, which looks
    # redundant — the workspace already names a dataset. It is not redundant:
    # it is what lets both foreign keys below be composite, so an overlay row
    # pointing at one dataset's profile from another dataset's workspace is
    # unrepresentable rather than something a repository has to remember to
    # check. The same argument ``0036`` makes for ``unit_id``.
    sa.Column("dataset_id", _UUID, nullable=False),
    sa.Column("profile_no", sa.Integer, nullable=False),
    # §13: Northline's topics, gained by everyone in the round-one attended
    # set. Additive over the base row rather than a rewrite of it, because
    # "base ⟕ overlay" is what makes a team's view isolated by a key instead
    # of by six copies of 300 rows.
    sa.Column("added_event_topics", _TEXTS, nullable=False, server_default=_EMPTY_ARRAY),
    # NULL means this team has not been given a card for this profile, which
    # is not the same as a card with nothing on it. §7's three states again.
    sa.Column("card_interests", _TEXTS, nullable=True),
    sa.Column("card_career_goal", sa.Text, nullable=True),
    # §13 under the ``required`` choice: asked, and did not answer. Excluded
    # from sign-up in round two.
    sa.Column("non_responding", sa.Boolean, nullable=False, server_default=sa.text("false")),
    sa.PrimaryKeyConstraint("workspace_id", "profile_no", name="exercise_profile_overlay_pkey"),
    # CASCADE: an overlay row is part of a team's workspace rather than a
    # thing that outlives it. "Reset team" deletes the workspace's overlay,
    # runs and settings, and the database is what makes that complete.
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


exercise_saved_setting = sa.Table(
    "exercise_saved_setting",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("workspace_id", _UUID, nullable=False),
    # Carried for the same reason it is carried on the overlay: it is what
    # makes both keys below composite, so a setting cannot name one dataset's
    # event from another dataset's workspace.
    sa.Column("dataset_id", _UUID, nullable=False),
    sa.Column("event_key", sa.Text, nullable=False),
    sa.Column("name", sa.Text, nullable=False),
    # §6's four weights, validated against
    # ``smartmatch_domain.weight_settings.validate_weight_overrides`` before
    # they are written. JSONB rather than four columns because the factor set
    # is a registry (ADR-0024 D2) and a fifth factor would otherwise be a
    # migration.
    sa.Column("weights", postgresql.JSONB, nullable=False),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.PrimaryKeyConstraint("id", name="exercise_saved_setting_pkey"),
    # §6: a saved setting is named, and the name identifies it within the
    # team's work on one event. The *at most three per (workspace, event)*
    # rule is not here: a count is not a uniqueness, and expressing it in DDL
    # would take a trigger. It is repository work in a later track.
    sa.UniqueConstraint("workspace_id", "event_key", "name", name="uq_exercise_saved_setting_name"),
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


exercise_result_run = sa.Table(
    "exercise_result_run",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("workspace_id", _UUID, nullable=False),
    sa.Column("dataset_id", _UUID, nullable=False),
    sa.Column("event_key", sa.Text, nullable=False),
    # Northline is round 1, Harbor is round 2. Two rounds is the case, not an
    # open question, so it is a constraint.
    sa.Column("round", sa.Integer, nullable=False),
    # Which saved setting the list came from. NULL when the team ran results
    # on weights they had not saved — a fact about the run, not a missing
    # foreign key: a setting renamed or deleted afterwards must not rewrite
    # what was run (ADR-0011 rule 1).
    sa.Column("setting_name", sa.Text, nullable=True),
    sa.Column("invited_profile_nos", _INTS, nullable=False, server_default=_EMPTY_ARRAY),
    sa.Column("signed_up_profile_nos", _INTS, nullable=False, server_default=_EMPTY_ARRAY),
    sa.Column("attended_profile_nos", _INTS, nullable=False, server_default=_EMPTY_ARRAY),
    # §10's second panel: all 300 run through the simulated-results rule with
    # the same seed. Stored as written rather than recomputed on read, so the
    # comparison a team saw is the comparison it keeps.
    sa.Column("email_everyone", postgresql.JSONB, nullable=False),
    # §10: ``60 - 8 - attended``. Stored rather than derived because the two
    # constants are the case's and a later change to them must not silently
    # restate what a team was shown.
    sa.Column("seats_empty", sa.Integer, nullable=False),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.PrimaryKeyConstraint("id", name="exercise_result_run_pkey"),
    # §9, the one-run rule, as a constraint rather than a check in code: a
    # second run for the same team and event hits this and is refused with
    # "This team has already run results for this event."
    sa.UniqueConstraint("workspace_id", "event_key", name="uq_exercise_result_run_workspace_event"),
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


exercise_result_unlock = sa.Table(
    "exercise_result_unlock",
    METADATA,
    sa.Column("dataset_id", _UUID, nullable=False),
    sa.Column("event_key", sa.Text, nullable=False),
    sa.Column("unlocked_at", _TS, nullable=False, server_default=sa.text("now()")),
    # §9: the absence of a row is "locked". A boolean column would need a row
    # per event written at ingest to mean anything, and a missing row would
    # then be a third state nobody defined.
    sa.PrimaryKeyConstraint("dataset_id", "event_key", name="exercise_result_unlock_pkey"),
    sa.ForeignKeyConstraint(
        ["dataset_id", "event_key"],
        ["exercise_event.dataset_id", "exercise_event.event_key"],
        ondelete="CASCADE",
        name="fk_exercise_result_unlock_event",
    ),
)


#: The family, by name. Used by the tests that walk it as a family rather than
#: filtering the shared ``METADATA`` on a string prefix — the prefix is the
#: rule being tested, so a test that selected by it could not fail.
EXERCISE_TABLES: dict[str, sa.Table] = {
    table.name: table
    for table in (
        exercise_dataset,
        exercise_profile,
        exercise_event,
        exercise_team_workspace,
        exercise_profile_overlay,
        exercise_saved_setting,
        exercise_result_run,
        exercise_result_unlock,
    )
}
