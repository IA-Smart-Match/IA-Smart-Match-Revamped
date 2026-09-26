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

Registration is an import side effect
=====================================
The eight tables join the shared ``METADATA`` when **this module is imported**
and not before. A consumer that needs them on the mirror — anything that walks
``METADATA`` for structure rather than looking up one table by name — must
import ``smartmatch_persistence.exercise.schema`` itself; importing
``smartmatch_persistence`` is not enough.

That is deliberate, and the alternative was measured rather than assumed.
Eager registration (a side-effect import in the persistence package
``__init__``) would make every consumer of the package load the exercise family
to fix a problem no consumer currently has: ``db/migrations/env.py`` sets
``target_metadata = None``, so Alembic never autogenerates against the mirror;
nothing in the repository calls ``create_all`` or ``drop_all``; and the only
code that iterates ``METADATA`` for structure is
``tests/integration/test_schema_matches_migration.py``, which imports this
module by name and explains why in a comment beside the import.
``tests/unit/test_exercise_schema_registration.py`` pins the behaviour in fresh
subprocesses and shows both import orders are cycle-free and agree — it is the
place to revisit this if a consumer that does walk ``METADATA`` ever lands.

Arrays where the rest of the repository uses JSONB
==================================================
The columns design spec §2 writes as ``[]`` are PostgreSQL ``TEXT[]`` and
``INTEGER[]``, not JSONB. Everywhere else in ``schema.py`` a list is JSONB, so
this is a deliberate exception rather than an oversight: these lists are
compared and filtered as sets of scalars (a team's invited numbers, a profile's
topic keys), which is what array containment operators are for, and the
placeholder note above turns on being able to change *values* without a
migration — ``TEXT[]`` keeps that true where a normalized side table would not.
JSONB is kept for the two columns that hold a *structure* rather than a list:
``exercise_saved_setting.weights`` and ``exercise_result_run.email_everyone``.

No GIN index exists on any of them, and none is added here. An index for a
containment query belongs with the query that needs it; nothing reads these
tables yet, so an index today would be migration ``0038`` written on a guess —
and the first repository track can measure instead.

Vocabularies live in code, not in DDL
======================================
Ann's data file (2026-09-24) closed OQ-CE-01, and the owner ruled the same day
that its vocabularies — six majors, four years, thirteen topics, sixteen
career goals — are closed **in code**
(``smartmatch_domain.exercise.vocabulary``) and enforced at ingest. So:

* ``major``, ``class_year`` and ``career_goal`` are ``TEXT`` with **no CHECK**.
  A vocabulary written as a constraint costs a migration to change; the ingest
  edit is the cheaper place, and it is the one place a value enters.
* the list columns are ``TEXT[]`` rather than a normalized side table, for the
  same reason.

Revision ``0042_exercise_ann_dataset`` added Ann's two columns this table did
not have: ``hidden_true_career_goal`` (withheld) and ``tiebreak_order``.
Revision ``0043_exercise_event_exploratory`` added ``exercise_event.is_exploratory``
(OQ-CE-14): a boolean derived from Ann's ``event_type`` at ingest, so no
vocabulary of event types is written as DDL either.
"""

from __future__ import annotations

import sqlalchemy as sa
from smartmatch_domain.exercise import EXERCISE_WITHHELD_FIELDS
from sqlalchemy.dialects import postgresql

from smartmatch_persistence.schema import METADATA

__all__ = [
    "EXERCISE_TABLES",
    "EXERCISE_WITHHELD_FIELDS",
    "exercise_dataset",
    "exercise_event",
    "exercise_profile",
    "exercise_profile_overlay",
    "exercise_profile_public_columns",
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

# ADR-0025 D6. The data file's hidden "true interests" column is stored on the
# profile row, is read by the simulated-results rule alone, and appears on no
# response model.
#
# Re-exported from ``smartmatch_domain.exercise`` rather than restated here.
# The name was defined in both places; the domain copy is the canonical one and
# its docstring asks for this dedupe by name, because two answers to "what is
# withheld" is one more than the question has — and the failure mode of editing
# one copy is a field leaving the server because a response model was written
# against the other. It stays importable from this module so that persistence
# code and its tests can read it beside the table it guards.


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
    # Ann's columns, stored in her spelling. Vocabularies are closed in code,
    # not here. See the module docstring.
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
    # Revision 0042. Ann's "fixed random order" for the last tie-break step.
    # NULL on a dataset stored before 0042, which keeps the checksum order.
    sa.Column("tiebreak_order", sa.Integer, nullable=True),
    # Revision 0042. ADR-0025 D6: withheld, like the column above — in
    # `EXERCISE_WITHHELD_FIELDS`, so no public read selects it.
    sa.Column("hidden_true_career_goal", sa.Text, nullable=True),
    sa.PrimaryKeyConstraint("dataset_id", "profile_no", name="exercise_profile_pkey"),
    sa.CheckConstraint("profile_no >= 1", name="ck_exercise_profile_profile_no"),
    sa.CheckConstraint(
        "length(btrim(display_name)) > 0", name="ck_exercise_profile_display_name_shape"
    ),
    sa.CheckConstraint("tiebreak_order >= 1", name="ck_exercise_profile_tiebreak_order"),
    sa.UniqueConstraint("dataset_id", "tiebreak_order", name="uq_exercise_profile_tiebreak_order"),
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
    # Ann's ``event_id`` (E01–E12) is ``event_key`` — profiles name the past
    # events they attended by it — and ``event_name`` is ``name``, the label.
    # ``sequence`` is the event's row position on her Events sheet.
    sa.Column("event_key", sa.Text, nullable=False),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("topic_tags", _TEXTS, nullable=False, server_default=_EMPTY_ARRAY),
    sa.Column("target_majors", _TEXTS, nullable=False, server_default=_EMPTY_ARRAY),
    # True for the two events the teams run — Northline (round 1) and Harbor
    # (round 2) — and false for the ten past events a profile may have
    # attended. The distinction is what keeps a past event out of the picker.
    sa.Column("is_exercise_event", sa.Boolean, nullable=False, server_default=sa.text("false")),
    sa.Column("sequence", sa.Integer, nullable=False),
    # Revision 0043 (OQ-CE-14, Ann 2026-09-25): a broad exploratory event — a
    # company talk, an industry panel, a career fair — which an undecided
    # career goal half-fits. Derived at ingest from Ann's ``event_type``; the
    # type itself is not stored. False for a dataset stored before 0043.
    sa.Column("is_exploratory", sa.Boolean, nullable=False, server_default=sa.text("false")),
    sa.PrimaryKeyConstraint("dataset_id", "event_key", name="exercise_event_pkey"),
    # One event per position. The ten past events and the two rounds are an
    # ordered list in the case; two events claiming position 11 would make
    # "round one" ambiguous.
    sa.UniqueConstraint("dataset_id", "sequence", name="uq_exercise_event_sequence"),
    sa.CheckConstraint("sequence >= 1", name="ck_exercise_event_sequence"),
    sa.CheckConstraint("length(btrim(event_key)) > 0", name="ck_exercise_event_key_shape"),
    sa.CheckConstraint("length(btrim(name)) > 0", name="ck_exercise_event_name_shape"),
)


# Re-pointing a workspace at a new dataset is a DELETE-then-UPDATE, and the
# order is not optional (design spec §3: "Existing workspaces keep pointing at
# their old dataset until the instructor re-points them; a re-point resets
# every team").
#
# The re-point is an UPDATE of ``dataset_id`` on the row below. The composite
# foreign keys from ``exercise_profile_overlay``, ``exercise_saved_setting`` and
# ``exercise_result_run`` all reference ``(dataset_id, id)`` here, and they are
# ``ON DELETE CASCADE`` only — not ``ON UPDATE CASCADE`` and not
# ``DEFERRABLE``. So the child rows do not follow the update and the constraint
# is checked immediately: the UPDATE is refused while any of them exist, and
# were it to succeed it would leave a team's overlay, saved settings and result
# runs pointing at profiles and events from the dataset it no longer uses.
#
# A repository implementing the re-point must therefore delete this workspace's
# overlay rows, saved settings and result runs *before* updating
# ``dataset_id``, in one transaction. That is not a workaround for the keys —
# it is the spec's own semantics, since a re-point resets every team. Changing
# the keys to ``ON UPDATE CASCADE`` would carry the stale rows across instead,
# which is the outcome the spec rules out.
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
    # gives the same answer. The coefficients it is drawn against (approved,
    # closing OQ-CE-03) are named constants in the domain module, not values here:
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


def exercise_profile_public_columns() -> tuple[sa.Column[object], ...]:
    """Every ``exercise_profile`` column except the withheld ones (ADR-0025 D6).

    ``sa.select(exercise_profile)`` carries ``hidden_true_interests``, and a
    repository that then builds a response out of the row it got back has
    served the withheld field without anyone writing a line that names it. The
    table cannot refuse the projection, so this is the projection to use
    instead: **any repository serving a response selects through this helper**,
    and only the simulation loader — the simulated-results rule of design spec
    §11, which is what the field exists for — selects the withheld column, by
    naming it explicitly so the exception is visible at the call site.

    Returns the ``sa.Column`` objects themselves, in table order, so the caller
    writes ``sa.select(*exercise_profile_public_columns())``.

    :raises ValueError: if a withheld name matches no ``exercise_profile``
        column. Every withheld field is on the profile row today; a name that
        matches nothing would subtract nothing and read as a passing
        projection, which is the one way this guard could quietly stop
        guarding.
    """
    columns = {column.name for column in exercise_profile.columns}
    unknown = sorted(EXERCISE_WITHHELD_FIELDS - columns)
    if unknown:
        raise ValueError(f"withheld fields name no exercise_profile column: {unknown}")
    return tuple(
        column for column in exercise_profile.columns if column.name not in EXERCISE_WITHHELD_FIELDS
    )
