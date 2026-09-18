"""The class-exercise tables, held to ADR-0025 D2 and D6 without a database.

``tests/integration/test_exercise_schema_migration.py`` proves migration
``0037`` builds these tables in PostgreSQL, and
``tests/integration/test_schema_matches_migration.py`` proves the mirror below
and the migration agree. Neither runs without a live database, and both of the
rules this file exists for are properties of the *definitions* rather than of
any row:

* **D2 — no tenancy.** The exercise tables carry no ``tenant_id``, no
  ``owning_unit_id``, and no foreign key out of the ``exercise_`` family. A
  team is not a tenant and a made-up profile is not an account; the point of
  the rule is that synthetic rows are never one join from real ones. A test
  that needed a database to say so would not run in the gate that matters —
  the one a change to ``schema.py`` passes through.
* **D6 — the withheld field.** ``hidden_true_interests`` is stored and read
  only by the simulated-results rule. ``EXERCISE_WITHHELD_FIELDS`` is the
  frozenset that names it, and this file pins its membership so that removing
  the name is a failing test rather than a silent widening.

It also pins the two things OQ-CE-01 must be able to answer later: the
placeholder columns exist under the spec's names, and **no CHECK constrains
``class_year`` or ``career_goal``**. A vocabulary constraint written before
Ann's sample arrives would close the open question in code, and unpicking it
would be a migration rather than an edit.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")

import sqlalchemy as sa
from smartmatch_persistence.exercise import schema as exercise_schema

#: Design spec §2's table list, in the order the spec gives it.
EXPECTED_TABLES = (
    "exercise_dataset",
    "exercise_profile",
    "exercise_event",
    "exercise_team_workspace",
    "exercise_profile_overlay",
    "exercise_saved_setting",
    "exercise_result_run",
    "exercise_result_unlock",
)

#: Columns design spec §2 marks ``PLACEHOLDER until 9/18`` — the ones OQ-CE-01
#: settles. Built to the spec's names so the shape exists; typed loosely on
#: purpose so the answer does not need a second migration to be recorded.
PLACEHOLDER_PROFILE_COLUMNS = (
    "display_name",
    "major",
    "class_year",
    "past_event_keys",
    "stated_interests",
    "career_goal",
    "hidden_true_interests",
)
PLACEHOLDER_EVENT_COLUMNS = (
    "event_key",
    "name",
    "topic_tags",
    "target_majors",
    "is_exercise_event",
    "sequence",
)


def _table(name: str) -> sa.Table:
    return exercise_schema.EXERCISE_TABLES[name]


def test_the_eight_tables_of_design_spec_section_2_are_defined():
    assert set(exercise_schema.EXERCISE_TABLES) == set(EXPECTED_TABLES)


def test_every_exercise_table_is_registered_on_the_shared_metadata():
    """The drift guard walks ``METADATA``; a table absent from it is uncompared.

    ``test_schema_matches_migration.py`` derives its whole parametrization from
    ``schema.METADATA``, so a table defined on a private ``MetaData`` would be
    invisible to the comparison *and* would make
    ``test_no_migrated_table_is_missing_from_code`` fail the moment ``0037``
    ran. One mirror, one guard.
    """
    from smartmatch_persistence import schema as core_schema

    for name in EXPECTED_TABLES:
        assert name in core_schema.METADATA.tables, f"{name} is not on the shared METADATA"


#: The table names the registry actually holds, read off the ``sa.Table``
#: objects rather than off :data:`EXPECTED_TABLES`.
#:
#: The prefix rule below is parametrized over this on purpose. Parametrized over
#: the literal, it asserted that eight strings this file wrote start with
#: ``exercise_`` — true by inspection and true no matter what ``schema.py``
#: says. A ninth table registered under a name outside the family would not
#: appear in the parametrization at all, so the rule it exists to enforce would
#: be enforced against nothing. Read from the registry, the same test fails on
#: exactly that change. ``test_the_eight_tables_of_design_spec_section_2_are_defined``
#: remains the assertion that the registry is the *expected* eight.
REGISTERED_TABLE_NAMES = tuple(
    sorted(table.name for table in exercise_schema.EXERCISE_TABLES.values())
)


def test_the_registry_is_not_empty():
    """Guards the parametrization below, which an empty registry would vacate.

    ``@parametrize`` over an empty sequence does not fail; it collects zero
    cases and reports green. That is the one way the derived prefix rule could
    stop enforcing anything without anyone noticing.
    """
    assert REGISTERED_TABLE_NAMES


@pytest.mark.parametrize("table_name", REGISTERED_TABLE_NAMES)
def test_every_table_is_prefixed_exercise(table_name: str):
    assert table_name.startswith("exercise_")


@pytest.mark.parametrize("table_name", EXPECTED_TABLES)
def test_no_table_carries_a_tenancy_column(table_name: str):
    """ADR-0025 D2. A team is not a tenant and a profile is not an account."""
    columns = {column.name for column in _table(table_name).columns}
    forbidden = columns & {"tenant_id", "owning_unit_id", "user_id", "unit_id"}
    assert not forbidden, f"{table_name} carries tenancy columns {sorted(forbidden)}"


@pytest.mark.parametrize("table_name", EXPECTED_TABLES)
def test_every_foreign_key_stays_inside_the_exercise_family(table_name: str):
    """The half of D2 that a column check cannot reach.

    A table with no ``tenant_id`` is still one join from real data if it
    references ``user_account`` or ``event``. Walking the constraints is what
    makes "synthetic rows are never one join from real ones" a property of the
    schema rather than a sentence in an ADR.
    """
    strays = [
        f"{tuple(element.parent.name for element in constraint.elements)} -> "
        f"{constraint.referred_table.name}"
        for constraint in _table(table_name).foreign_key_constraints
        if not constraint.referred_table.name.startswith("exercise_")
    ]
    assert not strays, f"{table_name} references outside the exercise family: {strays}"


def test_no_table_outside_the_exercise_family_references_one():
    """And the reverse direction, walked over the whole mirror.

    D2 is a two-way statement. A CBA table given a foreign key *into* an
    exercise table would put real rows one join from synthetic ones, which is
    the same failure read from the other end and is not caught by walking the
    exercise tables alone.
    """
    from smartmatch_persistence import schema as core_schema

    strays = [
        f"{table.name}.{tuple(element.parent.name for element in constraint.elements)}"
        for table in core_schema.METADATA.tables.values()
        if not table.name.startswith("exercise_")
        for constraint in table.foreign_key_constraints
        if constraint.referred_table.name.startswith("exercise_")
    ]
    assert not strays, f"non-exercise tables reference exercise tables: {strays}"


def test_hidden_true_interests_is_the_withheld_field():
    """ADR-0025 D6, pinned as a name rather than as a convention."""
    assert "hidden_true_interests" in exercise_schema.EXERCISE_WITHHELD_FIELDS
    assert isinstance(exercise_schema.EXERCISE_WITHHELD_FIELDS, frozenset)


def test_every_withheld_field_is_a_real_column():
    """A withheld name that matches no column protects nothing."""
    columns = {
        column.name
        for table in exercise_schema.EXERCISE_TABLES.values()
        for column in table.columns
    }
    assert columns >= exercise_schema.EXERCISE_WITHHELD_FIELDS


def test_the_withheld_set_is_the_domain_constant_and_not_a_second_copy():
    """One answer to "what is withheld", held in the domain.

    The set was defined twice — here in persistence and in
    ``smartmatch_domain.exercise``, whose docstring asks for exactly this
    dedupe once the persistence package exists. Two frozensets with the same
    member today are two places to edit tomorrow, and the failure mode of
    editing one is a field that leaves the server because the *other* copy was
    the one a response model was written against. Identity, not equality: equal
    literals are what the situation already was.
    """
    from smartmatch_domain.exercise import EXERCISE_WITHHELD_FIELDS as domain_withheld

    assert exercise_schema.EXERCISE_WITHHELD_FIELDS is domain_withheld


def test_the_public_projection_excludes_exactly_the_withheld_columns():
    """ADR-0025 D6's guard against ``sa.select(exercise_profile)``.

    The withheld column is on the profile row, so any repository that selects
    the table selects it. The helper is the projection a response-serving
    repository is required to go through, and the two assertions below are its
    whole contract: nothing withheld is in it, and nothing else is left out.
    """
    profile = _table("exercise_profile")
    public = exercise_schema.exercise_profile_public_columns()
    names = [column.name for column in public]

    assert set(names).isdisjoint(exercise_schema.EXERCISE_WITHHELD_FIELDS)
    assert (
        set(names)
        == {column.name for column in profile.columns} - exercise_schema.EXERCISE_WITHHELD_FIELDS
    )


def test_the_public_projection_returns_the_profile_table_s_own_columns():
    """Columns, not names — the helper feeds ``sa.select(*...)`` directly."""
    profile = _table("exercise_profile")
    for column in exercise_schema.exercise_profile_public_columns():
        assert column is profile.columns[column.name]


def test_the_public_projection_refuses_a_withheld_name_that_is_not_a_column(
    monkeypatch: pytest.MonkeyPatch,
):
    """A guard that silently ignores a typo guards nothing.

    ``test_every_withheld_field_is_a_real_column`` covers the module-level set.
    This covers the helper: a name added to the withheld set that matches no
    ``exercise_profile`` column would otherwise subtract nothing and read as a
    passing projection.
    """
    monkeypatch.setattr(
        exercise_schema,
        "EXERCISE_WITHHELD_FIELDS",
        frozenset({"hidden_true_interests", "not_a_column"}),
    )
    with pytest.raises(ValueError, match="not_a_column"):
        exercise_schema.exercise_profile_public_columns()


@pytest.mark.parametrize("column_name", PLACEHOLDER_PROFILE_COLUMNS)
def test_profile_carries_the_placeholder_columns(column_name: str):
    assert column_name in _table("exercise_profile").columns


@pytest.mark.parametrize("column_name", PLACEHOLDER_EVENT_COLUMNS)
def test_event_carries_the_placeholder_columns(column_name: str):
    assert column_name in _table("exercise_event").columns


def test_no_check_constrains_the_open_vocabularies():
    """OQ-CE-01 stays open, which means it stays out of the database.

    ``class_year`` and ``career_goal`` are the two columns whose *values* the
    open question decides. A CHECK naming today's guesses would answer it in
    DDL, and the answer would then need a migration to change rather than an
    ingest edit.
    """
    profile = _table("exercise_profile")
    expressions = [
        str(constraint.sqltext)
        for constraint in profile.constraints
        if isinstance(constraint, sa.CheckConstraint)
    ]
    for expression in expressions:
        assert "class_year" not in expression, f"CHECK constrains class_year: {expression}"
        assert "career_goal" not in expression, f"CHECK constrains career_goal: {expression}"


def test_the_placeholder_marker_is_literally_present():
    """The register's ID, in the source, where a reader of the column finds it."""
    source = Path(exercise_schema.__file__).read_text(encoding="utf-8")
    assert "PLACEHOLDER (OQ-CE-01)" in source


#: The constraints design spec §2 and §9 name in words. Each is the whole of
#: some rule stated elsewhere, so each is asserted by name rather than left to
#: the symmetric mirror comparison — which passes happily when a constraint is
#: dropped from the migration and the mirror together.
NAMED_CONSTRAINTS = (
    # §15: one workspace per team per dataset. Two rows would make "the team's
    # saved runs" two answers to one question.
    ("exercise_team_workspace", "uq_exercise_team_workspace_dataset_team"),
    # §2: team numbers 1-6, the six teams in Ann's class.
    ("exercise_team_workspace", "ck_exercise_team_workspace_team_number"),
    # §6: a saved setting is named, and the name identifies it.
    ("exercise_saved_setting", "uq_exercise_saved_setting_name"),
    # §9: the one-run rule, as a constraint rather than a check in code.
    ("exercise_result_run", "uq_exercise_result_run_workspace_event"),
)


@pytest.mark.parametrize(("table_name", "constraint_name"), NAMED_CONSTRAINTS)
def test_the_named_constraints_exist(table_name: str, constraint_name: str):
    names = {constraint.name for constraint in _table(table_name).constraints}
    assert constraint_name in names, f"{constraint_name} is missing from {table_name}"


def test_the_invite_limit_defaults_to_thirty():
    """§5, and Ann's stated number rather than an open question."""
    default = _table("exercise_dataset").columns["invite_limit"].server_default
    assert default is not None
    assert "30" in str(default.arg)


def test_the_workspace_stores_a_hash_and_never_a_raw_token():
    """§15: the cookie is a pointer; the server row is the truth.

    A column named for the token itself would be a credential at rest, and the
    name is the only thing standing between "we store a hash" and "we store
    the token" once a repository is written over this table.
    """
    columns = {column.name for column in _table("exercise_team_workspace").columns}
    assert "workspace_token_hash" in columns
    assert "workspace_token" not in columns


#: The only ``smartmatch_persistence`` modules the exercise package may import.
#: ADR-0025 D2 forbids it ``smartmatch_authz`` and any tenant-scoped
#: repository; the import-linter contract in ``pyproject.toml`` covers authz
#: and the frameworks, and this covers the repositories — as an allow-list, so
#: a repository added next year is refused without anyone remembering to
#: extend a denial list.
ALLOWED_PERSISTENCE_IMPORTS = frozenset({"smartmatch_persistence.schema"})


def test_the_exercise_package_imports_no_tenant_scoped_repository():
    package = Path(exercise_schema.__file__).parent
    offenders: list[str] = []

    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                module = node.module
            elif isinstance(node, ast.Import):
                module = node.names[0].name
            else:
                continue
            if not module.startswith("smartmatch_persistence"):
                continue
            if module.startswith("smartmatch_persistence.exercise"):
                continue
            if module not in ALLOWED_PERSISTENCE_IMPORTS:
                offenders.append(f"{path.name}: {module}")

    assert not offenders, f"exercise package reaches into persistence: {offenders}"
