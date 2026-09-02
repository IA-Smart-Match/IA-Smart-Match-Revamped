"""Behavioural coverage for P9 Gate A's ``professional_unit_relationship`` (migration 0012).

Same pattern ``tests/integration/test_engagement_schema_constraints.py`` set
for the ADR-0013 tables: ``tests/unit/test_professional_unit_relationship_schema.py``
proves the code-side definition says the right thing without a database; this
file proves PostgreSQL actually enforces it.

``docs/decisions/p9-gate-a-board-role-decision-draft.md`` (CLOSED 2026-09-02)
is what every test below is checking against:

* §1 — ``board_role`` is relationship-scoped, not intrinsic to a professional.
* §2 — multiple concurrent ``board_role`` values per person across different
  units must be representable at the same instant; no effective-date columns
  for the pilot; a correction updates the current relationship record.

Requires a live database, and is skipped when none is reachable (``engine``
fixture, ``tests/integration/conftest.py``).

**Unrun in the authoring environment.** This file was written as source, the
same as the migration and schema definitions it exercises — it has not been
executed against PostgreSQL. See this slice's report for the blocker.

No shared teardown to lean on. ``_clean_relationship_table`` below is this
file's own teardown, run before ``tenant_id``'s by fixture dependency order —
the same reasoning ``test_engagement_schema_constraints.py``'s
``_clean_engagement_tables`` documents — so a row left behind here does not
make ``org_unit``'s ``RESTRICT`` foreign key block ``tenant_id``'s own
teardown.
"""

from __future__ import annotations

import uuid

import pytest

pytest.importorskip("sqlalchemy")

from conftest import ensure_owning_unit
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clean_relationship_table(engine: Engine, tenant_id):
    """Delete this file's rows before ``tenant_id`` tears down its own."""
    yield
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM professional_unit_relationship WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )


# ---------------------------------------------------------------------------
# Row builder.
# ---------------------------------------------------------------------------


def _insert_relationship(
    conn,
    tenant_id: uuid.UUID,
    *,
    professional_id: uuid.UUID | None = None,
    unit_id: uuid.UUID | None = None,
    board_role: object = "Director",
) -> tuple[uuid.UUID, uuid.UUID]:
    """Insert a ``professional_unit_relationship`` row.

    Returns the ``(professional_id, unit_id)`` pair actually used, so a
    caller that did not supply one of them can still address the row it
    wrote. ``unit_id`` defaults to the test tenant's shared job-owning unit
    (``ensure_owning_unit``) unless the caller wants a specific one — needed
    by the multi-unit and duplicate-key tests below, which must reuse or vary
    it deliberately.
    """
    prof_id = professional_id or uuid.uuid4()
    resolved_unit_id = unit_id or ensure_owning_unit(conn, tenant_id)
    conn.execute(
        text(
            "INSERT INTO professional_unit_relationship "
            "(tenant_id, professional_id, unit_id, board_role) "
            "VALUES (:tenant_id, :professional_id, :unit_id, :board_role)"
        ),
        {
            "tenant_id": tenant_id,
            "professional_id": prof_id,
            "unit_id": resolved_unit_id,
            "board_role": board_role,
        },
    )
    return prof_id, resolved_unit_id


def _insert_unit(conn, tenant_id: uuid.UUID, path: str) -> uuid.UUID:
    """A second org_unit at a distinct path, for the multi-unit tests below."""
    unit_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
            "VALUES (:id, :tid, CAST(:path AS ltree), 'department', 'Second Unit')"
        ),
        {"id": unit_id, "tid": tenant_id, "path": path},
    )
    return unit_id


# ---------------------------------------------------------------------------
# The happy path, and Gate A §2's multiplicity requirement
# ---------------------------------------------------------------------------


def test_a_relationship_row_can_be_written_and_read_back(engine: Engine, tenant_id) -> None:
    with engine.begin() as conn:
        prof_id, unit_id = _insert_relationship(conn, tenant_id, board_role="Treasurer")
        row = conn.execute(
            text(
                "SELECT board_role, created_at, updated_at FROM professional_unit_relationship "
                "WHERE tenant_id = :tid AND professional_id = :pid AND unit_id = :uid"
            ),
            {"tid": tenant_id, "pid": prof_id, "uid": unit_id},
        ).one()
    assert row.board_role == "Treasurer"
    assert row.created_at is not None
    assert row.updated_at is not None


def test_the_same_professional_can_hold_concurrent_roles_at_two_different_units(
    engine: Engine, tenant_id
) -> None:
    """Gate A §2: multiple concurrent board_role values per person, across units, at once."""
    with engine.begin() as conn:
        prof_id = uuid.uuid4()
        unit_a = ensure_owning_unit(conn, tenant_id)
        unit_b = _insert_unit(conn, tenant_id, "iawest.relationships.second")
        _insert_relationship(
            conn, tenant_id, professional_id=prof_id, unit_id=unit_a, board_role="Director"
        )
        _insert_relationship(
            conn, tenant_id, professional_id=prof_id, unit_id=unit_b, board_role="Treasurer"
        )

        rows = conn.execute(
            text(
                "SELECT unit_id, board_role FROM professional_unit_relationship "
                "WHERE tenant_id = :tid AND professional_id = :pid ORDER BY board_role"
            ),
            {"tid": tenant_id, "pid": prof_id},
        ).all()
    assert {(row.unit_id, row.board_role) for row in rows} == {
        (unit_a, "Director"),
        (unit_b, "Treasurer"),
    }


# ---------------------------------------------------------------------------
# professional_unit_relationship_pkey — the composite natural key
# ---------------------------------------------------------------------------


def test_a_duplicate_professional_unit_pair_is_rejected(engine: Engine, tenant_id) -> None:
    """The same (tenant, professional, unit) triple cannot be written twice."""
    with engine.begin() as conn:
        prof_id, unit_id = _insert_relationship(conn, tenant_id, board_role="Director")

    with (
        pytest.raises(IntegrityError, match="professional_unit_relationship_pkey"),
        engine.begin() as conn,
    ):
        _insert_relationship(
            conn,
            tenant_id,
            professional_id=prof_id,
            unit_id=unit_id,
            board_role="Secretary",
        )


def test_the_primary_key_has_no_surrogate_id_column(engine: Engine) -> None:
    """The natural key is the only identity this table has."""
    with engine.connect() as conn:
        columns = {
            row.column_name
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'professional_unit_relationship'"
                )
            )
        }
    assert "id" not in columns
    assert {"tenant_id", "professional_id", "unit_id", "board_role"} <= columns


# ---------------------------------------------------------------------------
# board_role NOT NULL
# ---------------------------------------------------------------------------


def test_a_null_board_role_is_rejected(engine: Engine, tenant_id) -> None:
    with (
        pytest.raises(IntegrityError, match=r"(?i)null value|not-null|board_role"),
        engine.begin() as conn,
    ):
        _insert_relationship(conn, tenant_id, board_role=None)


# ---------------------------------------------------------------------------
# unit_id -- composite, tenant-scoped foreign key to org_unit, ON DELETE RESTRICT
# ---------------------------------------------------------------------------


def test_unit_id_must_reference_a_real_unit(engine: Engine, tenant_id) -> None:
    with pytest.raises(IntegrityError), engine.begin() as conn:
        _insert_relationship(conn, tenant_id, unit_id=uuid.uuid4())


def test_unit_id_cannot_reference_a_unit_in_another_tenant(
    engine: Engine, tenant_id, session_factory
) -> None:
    """A single-column key would have accepted this; the composite key must not."""
    other_tenant_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :name)"),
            {
                "id": other_tenant_id,
                "slug": f"other-{other_tenant_id.hex[:12]}",
                "name": "Other tenant",
            },
        )
        other_unit_id = ensure_owning_unit(conn, other_tenant_id)

    try:
        with pytest.raises(IntegrityError), engine.begin() as conn:
            _insert_relationship(conn, tenant_id, unit_id=other_unit_id)
    finally:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM org_unit WHERE tenant_id = :tid"), {"tid": other_tenant_id}
            )
            conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": other_tenant_id})


def test_a_unit_cannot_be_deleted_out_from_under_its_relationships(
    engine: Engine, tenant_id
) -> None:
    """RESTRICT: reorganizing a unit must not silently delete the roles recorded against it."""
    with engine.begin() as conn:
        _, unit_id = _insert_relationship(conn, tenant_id)

    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("DELETE FROM org_unit WHERE id = :id"), {"id": unit_id})


# ---------------------------------------------------------------------------
# professional_id -- no foreign key (no professional table exists yet)
# ---------------------------------------------------------------------------


def test_professional_id_accepts_any_uuid_with_no_referential_check(
    engine: Engine, tenant_id
) -> None:
    """No professional table exists yet, so nothing constrains this column but its type.

    This is the same situation ``attendance_record.event_id`` is already in
    for its own not-yet-built parent table — see the migration's docstring.
    """
    with engine.begin() as conn:
        _insert_relationship(conn, tenant_id, professional_id=uuid.uuid4())


# ---------------------------------------------------------------------------
# No effective-date columns -- Gate A §2, current-state only for the pilot
# ---------------------------------------------------------------------------


def test_no_effective_date_columns_exist_in_the_live_table(engine: Engine) -> None:
    with engine.connect() as conn:
        columns = {
            row.column_name.lower()
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'professional_unit_relationship'"
                )
            )
        }
    forbidden_fragments = ("effective_from", "effective_to", "valid_from", "valid_until")
    offenders = [c for c in columns for frag in forbidden_fragments if frag in c]
    assert not offenders, (
        f"found date-ranging column(s) {offenders} in the live table -- the pilot "
        "is current-state only per Gate A §2"
    )
