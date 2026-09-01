"""Behavioural coverage for ``ck_review_item_status`` (migration ``0008``).

`tests/integration/test_check_constraints.py` is the home for this codebase's
CHECK-constraint behavioural tests, and its own meta-test —
`test_this_file_covers_every_check_constraint_in_the_schema` — requires every
CHECK constraint in the database to be declared in that file's
`CHECK_CONSTRAINT_DEFINITIONS`, which ``ck_review_item_status`` now is (see
`BEHAVIOURAL_COVERAGE` there, which points here). The forbidden-write and
permitted-write tests live in this separate file, in the same style, so that
adding the quarantine-and-review tables does not require editing a file three
other tracks are touching concurrently.

Same two questions as every entry in that file's `BEHAVIOURAL_COVERAGE`:
does the database refuse the value outside the vocabulary, and does it accept
every value inside it? A name-only comparison (``test_schema_matches_migration.py``)
cannot tell an inverted constraint from a correct one; only an attempted write
can.

Requires a live database, and is skipped when none is reachable (`engine`
fixture, `tests/integration/conftest.py`).
"""

from __future__ import annotations

import uuid

import pytest

pytest.importorskip("sqlalchemy")

from conftest import ensure_owning_unit
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration


def _make_job(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    """Insert a minimal ``job`` row and return its id.

    ``import_batch`` requires a real job (``ON DELETE CASCADE`` from ``job``,
    migration ``0008``), which is also why this file does not need its own
    teardown: deleting ``job`` in `conftest.py`'s `tenant_id` fixture cascades
    to every ``import_batch`` and ``review_item`` row this file writes.
    """
    job_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO job (id, tenant_id, command_type, status, owning_unit_id) "
            "VALUES (:id, :tenant_id, 'import.create', 'queued', :unit_id)"
        ),
        {
            "id": job_id,
            "tenant_id": tenant_id,
            "unit_id": ensure_owning_unit(conn, tenant_id),
        },
    )
    return job_id


def _make_import_batch(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    """Insert a minimal ``import_batch`` row and return its id."""
    batch_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO import_batch "
            "(id, tenant_id, owning_unit_id, job_id, dataset, row_count, dry_run) "
            "VALUES (:id, :tenant_id, :unit_id, :job_id, 'professionals', 1, false)"
        ),
        {
            "id": batch_id,
            "tenant_id": tenant_id,
            "unit_id": ensure_owning_unit(conn, tenant_id),
            "job_id": _make_job(conn, tenant_id),
        },
    )
    return batch_id


def _insert_review_item(conn, tenant_id: uuid.UUID, batch_id: uuid.UUID, status: str) -> None:
    conn.execute(
        text(
            "INSERT INTO review_item "
            "(id, tenant_id, import_batch_id, row_index, row_data, status) "
            "VALUES (:id, :tenant_id, :batch_id, :row_index, :row_data, :status)"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "batch_id": batch_id,
            "row_index": 0,
            "row_data": '{"name": "example"}',
            "status": status,
        },
    )


# ---------------------------------------------------------------------------
# ck_review_item_status — status IN ('pending', 'accepted', 'rejected')
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["approved", "PENDING", "", "accepted "])
def test_review_item_rejects_a_status_outside_the_vocabulary(
    engine: Engine, tenant_id, status: str
) -> None:
    """``approved`` is the interesting one — it is the word a reviewer says,
    not the word the vocabulary uses. A constraint relaxed to accept a
    caller's near-miss would let a review workflow write a status no query
    filtering on the pinned three values would ever find again.
    """
    with pytest.raises(IntegrityError, match="ck_review_item_status"), engine.begin() as conn:
        batch = _make_import_batch(conn, tenant_id)
        _insert_review_item(conn, tenant_id, batch, status)


@pytest.mark.parametrize("status", ["pending", "accepted", "rejected"])
def test_review_item_accepts_every_vocabulary_value(engine: Engine, tenant_id, status: str) -> None:
    """All three, because a review item is written ``pending`` and a human
    resolves it to one of the other two (v1.1 §1.5). A constraint narrowed to
    admit only one of the three outcomes passes every rejection test above and
    fails here — in particular a constraint reduced to ``status = 'pending'``,
    which would make every review decision impossible to record.
    """
    with engine.begin() as conn:
        batch = _make_import_batch(conn, tenant_id)
        _insert_review_item(conn, tenant_id, batch, status)


def test_review_item_defaults_to_pending(engine: Engine, tenant_id) -> None:
    """Every row starts quarantined until a human decides otherwise.

    An insert that omits ``status`` entirely exercises the column's
    ``server_default`` rather than the CHECK, but it is the shape the worker's
    own write will take (``smartmatch_domain.ingest`` produces review items,
    not verified records, and nothing in that path decides ``accepted`` or
    ``rejected`` on a coordinator's behalf) — so an inverted or missing default
    would surface as every freshly imported row being unreviewable rather than
    merely unreviewed.
    """
    with engine.begin() as conn:
        batch = _make_import_batch(conn, tenant_id)
        item_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO review_item (id, tenant_id, import_batch_id, row_index, row_data) "
                "VALUES (:id, :tenant_id, :batch_id, 0, :row_data)"
            ),
            {
                "id": item_id,
                "tenant_id": tenant_id,
                "batch_id": batch,
                "row_data": '{"name": "example"}',
            },
        )
        status = conn.execute(
            text("SELECT status FROM review_item WHERE id = :id"), {"id": item_id}
        ).scalar_one()

    assert status == "pending"


def test_review_item_status_rejects_going_outside_the_vocabulary_on_update(
    engine: Engine, tenant_id
) -> None:
    """The realistic way this happens: a review decision is an UPDATE, not a
    fresh INSERT. A CHECK declared on a column is enforced on both, and every
    other test in this file only inserts.
    """
    with engine.begin() as conn:
        batch = _make_import_batch(conn, tenant_id)
        _insert_review_item(conn, tenant_id, batch, "pending")

    with pytest.raises(IntegrityError, match="ck_review_item_status"), engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE review_item SET status = 'archived' "
                "WHERE tenant_id = :tenant_id AND import_batch_id = :batch_id"
            ),
            {"tenant_id": tenant_id, "batch_id": batch},
        )


def test_review_item_status_accepts_the_review_decision_transition_on_update(
    engine: Engine, tenant_id
) -> None:
    """``pending -> accepted``, the transition a human review actually makes.

    Zero and positive amounts aside, an inverted constraint on this table
    would refuse exactly this write and would be caught by the parametrized
    insert test above; this pins the same guarantee against the UPDATE path a
    reviewer's decision actually takes.
    """
    with engine.begin() as conn:
        batch = _make_import_batch(conn, tenant_id)
        _insert_review_item(conn, tenant_id, batch, "pending")

    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE review_item SET status = 'accepted' "
                "WHERE tenant_id = :tenant_id AND import_batch_id = :batch_id"
            ),
            {"tenant_id": tenant_id, "batch_id": batch},
        )


# ---------------------------------------------------------------------------
# uq_review_item_batch_row — one review item per (import_batch_id, row_index)
# ---------------------------------------------------------------------------
#
# Not a CHECK constraint, and so out of `test_check_constraints.py`'s scope,
# but it is the other guarantee `review_item` carries and it is exercised here
# for the same reason: `test_unique_constraints_match` (name and columns) and
# `test_schema_matches_migration.py` prove the constraint exists; only an
# attempted duplicate write proves it does its job — the same distinction
# `test_tenant_isolation.py` draws for `uq_job_event_sequence`, the constraint
# this one mirrors.


def test_review_item_batch_row_index_is_unique_within_a_batch(engine: Engine, tenant_id) -> None:
    """Two review items claiming the same source-file row is a coordinate a
    coordinator can no longer trust: ``uq_review_item_batch_row`` is what
    makes "row 0 of this batch" name at most one item.
    """
    with pytest.raises(IntegrityError, match="uq_review_item_batch_row"), engine.begin() as conn:
        batch = _make_import_batch(conn, tenant_id)
        _insert_review_item(conn, tenant_id, batch, "pending")
        _insert_review_item(conn, tenant_id, batch, "pending")


def test_review_item_batch_row_index_repeats_across_different_batches(
    engine: Engine, tenant_id
) -> None:
    """The same row index in two different batches is not a collision — each
    batch is its own source file, so this is the permitted-write half that
    proves the constraint scopes to one batch rather than to the whole table.
    """
    with engine.begin() as conn:
        first_batch = _make_import_batch(conn, tenant_id)
        second_batch = _make_import_batch(conn, tenant_id)
        _insert_review_item(conn, tenant_id, first_batch, "pending")
        _insert_review_item(conn, tenant_id, second_batch, "pending")
