"""Assert the hand-written table definitions match the migrated database.

``smartmatch_persistence.schema`` is written by hand rather than reflected,
because the composite tenant-safe keys in v1.1 §2.2 are the point of the schema
and reflection would not reliably preserve them. The cost of writing them by
hand is that they can drift from the migrations that actually shape the
database.

This module is the guard. It compares the code's definitions against a live,
migrated database, so drift fails the build rather than surfacing later as a
confusing runtime error — a missing column shows up here, not as a
``ProgrammingError`` in a request handler.

The comparisons are deliberately whole-schema and symmetric. An earlier version
checked a hard-coded list of five tables for composite foreign keys and asserted
three constraint names existed; anything added to a migration and never mirrored
passed, because there was no list to fail. Every check below iterates the schema
and reports both directions, so a new table or constraint is covered the day it
lands rather than the day someone remembers to extend a list.

What is *not* compared is as deliberate. Server default expressions come back
from PostgreSQL rendered (``'0'::numeric``, ``'pending'::text``) against a code
side that writes ``"0"`` and ``"pending"``, so only their presence is compared —
normalizing the rest would be string munging that breaks on a version bump.
Index sets are not compared because ``schema.py`` declares no indexes on
purpose, and CHECK expressions are not compared because PostgreSQL rewrites them
on the way in (``effect IN (...)`` returns as ``effect = ANY (ARRAY[...])``);
their names are compared here and their behaviour belongs in a test that
attempts the forbidden write.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from smartmatch_persistence import schema
from sqlalchemy import Engine, inspect, text
from sqlalchemy.dialects import postgresql

pytestmark = pytest.mark.integration

_TABLES = sorted(schema.METADATA.tables)

#: ``ltree`` is a PostgreSQL extension type that SQLAlchemy does not ship, so
#: reflection reports ``NullType`` for these two columns and emits the two
#: ``SAWarning`` lines ADR-0004 argues for leaving visible. ``NullType.compile()``
#: raises rather than returning a string, so the type comparison below cannot
#: include them and they get their own assertion against the system catalog.
#: They are listed rather than detected so that a third ``ltree`` column has to
#: be added here consciously.
_LTREE_COLUMNS = (("org_unit", "path"), ("membership", "granted_path"))

#: Constraints something outside this module depends on, asserted absolutely
#: rather than only symmetrically. Each entry is (table, name, columns).
#:
#: The comparisons below are mirror-against-database, which catches drift but by
#: construction cannot catch a constraint removed from *both* sides — the two
#: definitions then agree about a guarantee that no longer exists. These four are
#: listed because each backs a claim made elsewhere in the system, which is the
#: same argument ``test_ltree_paths_have_gist_indexes`` makes for two indexes out
#: of eleven, and not because they are the important ones. The rest of the
#: constraint surface is covered symmetrically on purpose; asserting all of it
#: here would be a third copy of the schema to maintain.
#:
#: Two of the four are *also* guarded behaviourally, and were before this module
#: was widened: ``test_tenant_isolation.py::test_job_event_sequence_is_unique_per_job``
#: and ``::test_outbox_task_name_is_globally_unique`` insert the
#: duplicate row and require ``IntegrityError``. That is a stronger guard than
#: existence, because it proves the constraint does its job rather than that it
#: is present. What is added here is a structural failure that names the
#: constraint, rather than the same drift surfacing as a duplicate-insert error
#: in another module — and, for ``uq_idempotency_scope`` and
#: ``pk_rate_limit_counter``, a check on the columns and the exact name.
_LOAD_BEARING_UNIQUE_CONSTRAINTS = (
    # SSE Last-Event-ID reconnect resumes from a sequence number, which
    # identifies one event only if the pair is unique (v1.1 §1.6).
    ("job_event", "uq_job_event_sequence", ("job_id", "sequence")),
    # ADR-0007's deterministic task names deduplicate a retried dispatch only if
    # the name is unique; without this the crash-window retry doubles the work.
    ("outbox_record", "uq_outbox_task_name", ("task_name",)),
    # v1.1 §1.11's idempotency scope, and the name idempotency.py passes to
    # ON CONFLICT DO NOTHING.
    (
        "idempotency_record",
        "uq_idempotency_scope",
        ("tenant_id", "command_type", "idempotency_key"),
    ),
    # Migration 0024. Customer §§7-8 give the Speaker Request side *many*
    # industries and *many* roles, and this constraint is the whole of what
    # keeps "many" from meaning "the same one twice" — a repeated target is a
    # weight counted twice by a matcher with nothing on screen to explain it.
    # Pinned absolutely because the symmetric comparison above passes happily
    # when a constraint is dropped from the migration and the mirror together,
    # which is exactly how a set silently becomes a bag.
    (
        "speaker_request_classification",
        "uq_speaker_request_classification",
        ("tenant_id", "event_id", "kind", "code"),
    ),
)

#: Same rule, for the one primary key a query names. ``rate_limit.py`` passes
#: ``pk_rate_limit_counter`` to ``ON CONFLICT DO UPDATE``, and the atomic
#: increment that makes the limiter correct under autoscaling is that statement.
_LOAD_BEARING_PRIMARY_KEYS = (
    (
        "rate_limit_counter",
        "pk_rate_limit_counter",
        ("tenant_id", "subject", "operation", "window_start"),
    ),
    # Migration 0024, and the reason it is here is the same one that put
    # `pk_rate_limit_counter` here: the constraint carries a guarantee stated
    # somewhere other than the mirror. Customer §7's "each speaker should have
    # **one primary industry sector**" is enforced by this key and by nothing
    # else — the cardinality is not a CHECK, it is the absence of a second row
    # to put a second primary value in. Widen these columns and the rule is
    # gone with no column missing and no CHECK renamed for the symmetric
    # comparisons above to notice.
    (
        "speaker_profile",
        "speaker_profile_pkey",
        ("tenant_id", "professional_id"),
    ),
)

#: The tenancy root. A foreign key pointing here is a table's own tenant pointer
#: and is single-column by construction; a foreign key pointing anywhere else is
#: a reference between two tenant-owned rows and must carry ``tenant_id``.
_TENANCY_ROOT = "tenant"


@pytest.fixture(scope="module")
def inspector(engine: Engine):
    return inspect(engine)


def test_every_defined_table_exists(inspector):
    """A table in code but not in the database means a migration is missing."""
    defined = set(schema.METADATA.tables)
    actual = set(inspector.get_table_names())

    missing = defined - actual
    assert not missing, f"defined in code but absent from the database: {sorted(missing)}"


def test_no_migrated_table_is_missing_from_code(inspector):
    """The reverse drift: a migration landed but the code never learned about it.

    ``alembic_version`` is Alembic's own bookkeeping and is deliberately not
    modelled.
    """
    defined = set(schema.METADATA.tables) | {"alembic_version"}
    actual = set(inspector.get_table_names())

    unmodelled = actual - defined
    assert not unmodelled, f"in the database but not defined in code: {sorted(unmodelled)}"


@pytest.mark.parametrize("table_name", _TABLES)
def test_columns_match(inspector, table_name: str):
    """Every column defined in code exists in the database, and vice versa."""
    defined = {column.name for column in schema.METADATA.tables[table_name].columns}
    actual = {column["name"] for column in inspector.get_columns(table_name)}

    assert defined == actual, (
        f"{table_name}: only in code {sorted(defined - actual)}, "
        f"only in database {sorted(actual - defined)}"
    )


@pytest.mark.parametrize("table_name", _TABLES)
def test_foreign_keys_match(inspector, table_name: str):
    """Foreign keys agree on columns, target, and delete action.

    The delete action is the half that has been wrong. ``METADATA`` never
    creates a database, so a missing ``ondelete`` breaks nothing at runtime and
    stayed invisible on seven constraints — while ``schema.py`` is what people
    read to learn whether deleting a tenant is refused (``RESTRICT``) or takes
    its children with it (``CASCADE``).

    Comparing the referred table and columns in the same assertion is what
    generalizes the old five-table composite-key check to the whole schema: a
    composite key simplified in *either* definition fails here, whether or not
    anyone remembered to add the table to a list.
    """
    defined = {
        (
            tuple(element.parent.name for element in constraint.elements),
            constraint.referred_table.name,
            tuple(element.column.name for element in constraint.elements),
            _normalize_ondelete(constraint.ondelete),
        )
        for constraint in schema.METADATA.tables[table_name].foreign_key_constraints
    }
    actual = {
        (
            tuple(fk["constrained_columns"]),
            fk["referred_table"],
            tuple(fk["referred_columns"]),
            _normalize_ondelete(fk["options"].get("ondelete")),
        )
        for fk in inspector.get_foreign_keys(table_name)
    }

    assert defined == actual, (
        f"{table_name}: only in code {sorted(defined - actual)}, "
        f"only in database {sorted(actual - defined)}"
    )


def _normalize_ondelete(action: str | None) -> str:
    """``None`` and ``NO ACTION`` are the same thing; case is not significant."""
    return (action or "NO ACTION").upper()


def test_every_tenant_scoped_table_is_anchored_by_a_composite_key(inspector):
    """The isolation guarantee, asserted against the database on its own terms.

    Every tenant-owned row must be tied to its tenant by the database rather than
    by a ``WHERE tenant_id = ?`` clause someone can forget: either directly, by a
    single-column key to ``tenant.id``, or through a parent row, by a composite
    key that carries ``tenant_id`` alongside the parent id. A single-column key
    to a tenant-owned parent would let a row reference a parent in another
    tenant, which is the class of bug v1.1 §2.2 makes impossible at the database
    layer.

    **The correspondence is asserted, not just the membership.** A composite key
    containing ``tenant_id`` proves nothing on its own: ``(tenant_id, user_id)``
    referencing ``user_account (id, tenant_id)`` is composite, does contain
    ``tenant_id``, and maps this table's tenant onto the parent's *id* — it
    constrains a pair of unrelated values and enforces no isolation whatsoever.
    So the position of ``tenant_id`` among the constrained columns must line up
    with a referred column also named ``tenant_id``, and the tenant pointer must
    refer to ``tenant.id`` rather than merely to some column of ``tenant``.

    The tables checked are enumerated from the **database**, not from
    ``schema.py``. That distinction is the whole point of this test: an earlier
    version derived the list from the mirror, so simplifying a composite key in
    the mirror deleted the very case that would have caught it — the
    parametrization shrank and the suite went green one test lighter.
    ``test_foreign_keys_match`` proves the two definitions agree; this proves the
    database is the shape the architecture claims, and it still fails when both
    definitions are simplified together.

    A table with no ``tenant_id`` column is not tenant-owned and is skipped;
    ``tenant`` itself and ``alembic_version`` are the only ones today, and both
    fall out of that rule rather than being named.
    """
    violations: list[str] = []

    for table_name in sorted(inspector.get_table_names()):
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "tenant_id" not in columns:
            continue

        anchored = False
        for fk in inspector.get_foreign_keys(table_name):
            constrained = list(fk["constrained_columns"])
            referred = list(fk["referred_columns"])
            target = f"{fk['referred_table']}({', '.join(referred)})"

            if fk["referred_table"] == _TENANCY_ROOT:
                if constrained == ["tenant_id"] and referred == ["id"]:
                    anchored = True
                else:
                    violations.append(
                        f"{table_name}: key {tuple(constrained)} -> {target} references the "
                        "tenancy root but is not this table's tenant pointer"
                    )
            elif "tenant_id" not in constrained or len(constrained) < 2:
                violations.append(
                    f"{table_name}: foreign key {tuple(constrained)} -> {target} does not "
                    "carry tenant_id, so it would accept a parent row belonging to another "
                    "tenant"
                )
            elif referred[constrained.index("tenant_id")] != "tenant_id":
                # Composite and containing tenant_id, but pointing it somewhere
                # else. This is the shape that looks right and enforces nothing.
                violations.append(
                    f"{table_name}: foreign key {tuple(constrained)} -> {target} is composite "
                    "but its tenant_id does not correspond to the parent's tenant_id, so it "
                    "constrains something other than tenancy"
                )
            else:
                anchored = True

        if not anchored:
            violations.append(
                f"{table_name} carries tenant_id but no foreign key ties it to a tenant, "
                "so its rows are isolated by application code alone"
            )

    assert not violations, "\n".join(violations)


@pytest.mark.parametrize("table_name", _TABLES)
def test_nullability_matches(inspector, table_name: str):
    """A mirror that thinks a column is optional produces inserts that fail late.

    Nothing rejects a query built from a wrong ``nullable`` until a row is
    written, and then the error names the database rather than the mirror.
    """
    defined = {
        column.name: column.nullable for column in schema.METADATA.tables[table_name].columns
    }
    actual = {column["name"]: column["nullable"] for column in inspector.get_columns(table_name)}

    differences = _differences(defined, actual)
    assert not differences, f"{table_name}: nullability differs — {'; '.join(differences)}"


def _differences(defined: dict[str, object], actual: dict[str, object]) -> list[str]:
    """The columns the two definitions disagree about, rendered for the message.

    Only columns both sides declare. A column missing from one side entirely is
    ``test_columns_match``'s failure to report, and repeating it here would turn
    one piece of drift into a wall of failures that all say the same thing.
    """
    return [
        f"{name}: code {defined[name]!r}, database {actual[name]!r}"
        for name in sorted(defined.keys() & actual.keys())
        if defined[name] != actual[name]
    ]


@pytest.mark.parametrize("table_name", _TABLES)
def test_primary_key_matches(inspector, table_name: str):
    """Primary keys agree on name and on columns.

    Names are compared and not skipped because the mirror is what people read,
    and a primary key it names wrongly is a lie about the database. Note what
    this does *not* establish: the comparison is mirror-against-database, so a
    rename applied to the migration and the mirror together passes here while
    breaking ``rate_limit.py``, which hardcodes ``pk_rate_limit_counter`` for
    ``ON CONFLICT DO UPDATE`` independently of both.
    ``test_load_bearing_primary_keys_exist`` pins the name and columns
    absolutely; that the query and the constraint still refer to the same thing
    is proved by ``tests/integration/test_rate_limit.py`` running the statement.
    """
    defined = schema.METADATA.tables[table_name].primary_key
    actual = inspector.get_pk_constraint(table_name)

    assert defined.name == actual["name"], (
        f"{table_name}: primary key named {defined.name!r} in code, "
        f"{actual['name']!r} in the database"
    )
    assert tuple(defined.columns.keys()) == tuple(actual["constrained_columns"]), (
        f"{table_name}: primary key covers {tuple(defined.columns.keys())} in code, "
        f"{tuple(actual['constrained_columns'])} in the database"
    )


@pytest.mark.parametrize("table_name", _TABLES)
def test_unique_constraints_match(inspector, table_name: str):
    """Name *and* columns, both directions.

    A unique constraint added to a migration and never mirrored adds no column,
    so nothing else in this module notices it — and a uniqueness rule the mirror
    does not know about is one queries are written against blind.

    The columns are part of the comparison because a name-only check is exactly
    the one that misses a constraint keeping its name while the columns beneath
    it change, which is the shape of the change Wave C makes to
    ``user_account``'s subject uniqueness.
    """
    defined = {
        (constraint.name, tuple(constraint.columns.keys()))
        for constraint in schema.METADATA.tables[table_name].constraints
        if isinstance(constraint, sa.UniqueConstraint)
    }
    actual = {
        (constraint["name"], tuple(constraint["column_names"]))
        for constraint in inspector.get_unique_constraints(table_name)
    }

    assert defined == actual, (
        f"{table_name}: unique constraints only in code {sorted(defined - actual)}, "
        f"only in database {sorted(actual - defined)}"
    )


@pytest.mark.parametrize(
    ("table_name", "constraint_name", "columns"),
    _LOAD_BEARING_UNIQUE_CONSTRAINTS,
    ids=[name for _, name, _ in _LOAD_BEARING_UNIQUE_CONSTRAINTS],
)
def test_load_bearing_unique_constraints_exist(
    inspector, table_name: str, constraint_name: str, columns: tuple[str, ...]
):
    """Existence, asserted against the database and not against the mirror.

    The comparison above is symmetric, so a constraint dropped from a migration
    *and* deleted from ``schema.py`` in the same change agrees perfectly and
    fails nothing here. These are the constraints something else in the system
    claims to rely on, so they are pinned in the only direction that cannot be
    edited away from the code side. See ``_LOAD_BEARING_UNIQUE_CONSTRAINTS`` for
    what each backs, and for which of them ``test_tenant_isolation.py`` already
    proves behaviourally — this is a second, structural line on two of the three,
    not the only thing standing between the schema and a lost guarantee.

    The columns are asserted too: a constraint carrying the right name over the
    wrong columns satisfies a name comparison and none of the claims.
    """
    constraints = {
        constraint["name"]: tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints(table_name)
    }
    assert constraint_name in constraints, (
        f"{constraint_name} is missing from {table_name}; the guarantee it backs is gone "
        f"whether or not schema.py still mentions it"
    )
    assert constraints[constraint_name] == columns, (
        f"{constraint_name} covers {constraints[constraint_name]}, not {columns}"
    )


@pytest.mark.parametrize(
    ("table_name", "constraint_name", "columns"),
    _LOAD_BEARING_PRIMARY_KEYS,
    ids=[name for _, name, _ in _LOAD_BEARING_PRIMARY_KEYS],
)
def test_load_bearing_primary_keys_exist(
    inspector, table_name: str, constraint_name: str, columns: tuple[str, ...]
):
    """The same absolute check for a primary key a query names by string."""
    primary_key = inspector.get_pk_constraint(table_name)
    assert primary_key["name"] == constraint_name, (
        f"{table_name}'s primary key is {primary_key['name']!r}; rate_limit.py names "
        f"{constraint_name!r} in ON CONFLICT and the increment would fail against this schema"
    )
    assert tuple(primary_key["constrained_columns"]) == columns, (
        f"{constraint_name} covers {tuple(primary_key['constrained_columns'])}, not {columns}"
    )


@pytest.mark.parametrize("table_name", _TABLES)
def test_check_constraint_names_match(inspector, table_name: str):
    """CHECK constraints are compared by name only, and that is a weak check.

    Expressions are not comparable: PostgreSQL rewrites them on the way in, so
    ``effect IN ('allow','deny')`` returns as ``effect = ANY (ARRAY[...])`` and
    comparing text would fail on constraints that are in fact identical. Columns
    are not available to compare either, the way they are for unique
    constraints. So this catches a CHECK added, dropped, or renamed on one side
    only, and nothing else.

    **What it does not catch, stated because the gap is easy to assume away:** a
    constraint re-added under the same name with an inverted expression, or as
    ``NOT VALID``, passes here.

    **That gap is now closed elsewhere, and this paragraph used to say it was
    not.** ``test_check_constraints.py`` (F10) covers all eight by attempting
    both the forbidden write and the permitted one — the second being what
    catches inversion — and reads ``pg_constraint.convalidated`` for the
    ``NOT VALID`` half.

    The ``NOT VALID`` half deserves the correction spelled out, because this
    docstring implied a write test would catch it and a write test cannot.
    Verified against PostgreSQL 16: a CHECK added ``NOT VALID`` rejects new
    inserts exactly as a validated one does. ``NOT VALID`` skips only the scan
    of rows already present, so no attempted write distinguishes the two.
    Reading the catalogue is the only thing that does.
    """
    defined = _named_constraints(table_name, sa.CheckConstraint)
    actual = {constraint["name"] for constraint in inspector.get_check_constraints(table_name)}

    assert defined == actual, (
        f"{table_name}: check constraints only in code {sorted(defined - actual)}, "
        f"only in database {sorted(actual - defined)}"
    )


def _named_constraints(table_name: str, kind: type[sa.Constraint]) -> set[str | None]:
    """Names of one kind of constraint as the mirror declares them.

    Used for CHECK constraints, whose columns reflection does not report and
    whose expressions are not comparable, so the name is all there is.

    ``None`` for an unnamed constraint is returned rather than dropped: the
    database always has a name, so an unnamed mirror is drift and should fail
    the comparison rather than quietly shrink one side of it.
    """
    table = schema.METADATA.tables[table_name]
    return {constraint.name for constraint in table.constraints if isinstance(constraint, kind)}


@pytest.mark.parametrize("table_name", _TABLES)
def test_column_types_match(inspector, table_name: str):
    """Types are compared as the PostgreSQL dialect compiles them, on both sides.

    ``str(column.type)`` renders the generic type and would report a false
    difference between ``sa.Text`` and a reflected ``TEXT``. Compiling both
    against the dialect that actually holds the data makes ``UUID``,
    ``TIMESTAMP WITH TIME ZONE``, ``NUMERIC(12, 4)``, ``JSONB``, ``BIGINT`` and
    the rest normalize identically, so a real difference — a widened ``INTEGER``,
    a ``NUMERIC`` that lost its scale — is the only thing left to fail.

    The two ``ltree`` columns are excluded here and checked by
    ``test_ltree_columns_are_ltree_on_both_sides``; see ``_LTREE_COLUMNS``.
    """
    dialect = postgresql.dialect()
    defined = {
        column.name: column.type.compile(dialect=dialect)
        for column in schema.METADATA.tables[table_name].columns
        if (table_name, column.name) not in _LTREE_COLUMNS
    }
    actual = {
        column["name"]: column["type"].compile(dialect=dialect)
        for column in inspector.get_columns(table_name)
        if (table_name, column["name"]) not in _LTREE_COLUMNS
    }

    differences = _differences(defined, actual)
    assert not differences, f"{table_name}: types differ — {'; '.join(differences)}"


@pytest.mark.parametrize(("table_name", "column_name"), _LTREE_COLUMNS)
def test_ltree_columns_are_ltree_on_both_sides(engine: Engine, table_name: str, column_name: str):
    """The exception the type comparison cannot cover, asserted the long way.

    SQLAlchemy has no ``ltree`` type, so reflection yields ``NullType`` and
    compiling it raises instead of returning a string. Rather than wrapping the
    comparison in a ``try``/``except`` that would also swallow real failures,
    these two columns are named explicitly: the code side must still be the
    ``LTree`` type ADR-0004 chose over ``TEXT``, and the database side is read
    from the catalog, which knows the type even though the inspector does not.
    """
    column = schema.METADATA.tables[table_name].columns[column_name]
    assert isinstance(column.type, schema.LTree), (
        f"{table_name}.{column_name} is {column.type!r} in code; degrading it to TEXT "
        "would cost the subtree operators the authorization path depends on"
    )

    with engine.connect() as connection:
        udt_name = connection.execute(
            text(
                # Filtered to the schema reflection reads, so a same-named table
                # in another schema cannot turn this assertion into a
                # MultipleResultsFound that says nothing about drift.
                "SELECT udt_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() "
                "AND table_name = :table AND column_name = :column"
            ),
            {"table": table_name, "column": column_name},
        ).scalar_one()

    assert udt_name == "ltree", f"{table_name}.{column_name} is {udt_name} in the database"


@pytest.mark.parametrize("table_name", _TABLES)
def test_server_default_presence_matches(inspector, table_name: str):
    """Presence only, which is the half worth asserting.

    The harmful direction is the mirror believing the database fills a column in
    when it does not, because the insert then omits it and fails on a NOT NULL
    the mirror thought was covered. Comparing the expressions themselves would
    mean stripping casts and quotes off ``'0'::numeric`` to match ``"0"`` — a
    normalizer that breaks on a PostgreSQL upgrade and catches a diverged
    default the insert tests already catch.
    """
    defined = {
        column.name: column.server_default is not None
        for column in schema.METADATA.tables[table_name].columns
    }
    actual = {
        column["name"]: column["default"] is not None
        for column in inspector.get_columns(table_name)
    }

    differences = _differences(defined, actual)
    assert not differences, (
        f"{table_name}: server default present on one side only — {'; '.join(differences)}"
    )


@pytest.mark.parametrize(
    ("table_name", "index_name"),
    [("org_unit", "ix_org_unit_path_gist"), ("membership", "ix_membership_path_gist")],
)
def test_ltree_paths_have_gist_indexes(inspector, table_name: str, index_name: str):
    """The two indexes that back a correctness claim, and only those.

    ADR-0004's case for ``ltree`` over ``TEXT`` is that subtree containment is an
    indexed operator; without a GiST index on the path columns that argument is
    false and every authorization check degrades to a scan of the tenant's tree.
    Performance indexes are deliberately not asserted — mirroring the whole index
    set would be a second copy of information nobody reads.
    """
    indexes = {index["name"]: index for index in inspector.get_indexes(table_name)}
    assert index_name in indexes, f"{index_name} is missing from {table_name}"

    using = indexes[index_name].get("dialect_options", {}).get("postgresql_using", "btree")
    assert using == "gist", f"{index_name} is a {using} index; subtree operators need gist"
