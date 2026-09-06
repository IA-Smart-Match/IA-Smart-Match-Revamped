"""Behavioural coverage for ``review_item``'s CHECK and FK constraints.

`tests/integration/test_check_constraints.py` is the home for this codebase's
CHECK-constraint behavioural tests, and its own meta-test —
`test_this_file_covers_every_check_constraint_in_the_schema` — requires every
CHECK constraint in the database to be declared in that file's
`CHECK_CONSTRAINT_DEFINITIONS`, which both ``ck_review_item_status``
(migration ``0008``) and ``ck_review_item_decision_evidence`` (migration
``0013``) now are (see `BEHAVIOURAL_COVERAGE` there, which points to both back
here). The forbidden-write and permitted-write tests live in this separate
file, in the same style, so that adding the quarantine-and-review tables — and
later, the decision columns — does not require editing a file other tracks
are touching concurrently.

Same two questions as every entry in that file's `BEHAVIOURAL_COVERAGE`:
does the database refuse the value outside the vocabulary, and does it accept
every value inside it? A name-only comparison (``test_schema_matches_migration.py``)
cannot tell an inverted constraint from a correct one; only an attempted write
can.

``fk_review_item_decided_by`` (migration ``0013``) is covered here too, for
the same reason ``uq_review_item_batch_row`` already is despite not being a
CHECK: it is the other guarantee this table carries, and only an attempted
write proves it holds.

Requires a live database, and is skipped when none is reachable (`engine`
fixture, `tests/integration/conftest.py`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

pytest.importorskip("sqlalchemy")

from conftest import ensure_owning_unit, unique_subject
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


def _make_user(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    """Insert a minimal ``user_account`` row and return its id.

    What ``decided_by`` cites: a decision that names nobody is exactly the
    fabricated-field state ``ck_review_item_decision_evidence`` (migration
    ``0013``) exists to make unstorable, so every test below that writes an
    ``accepted``/``rejected`` row needs a real user to cite, the same way
    ``_make_job``/``_make_import_batch`` need a real job/batch to hang off.
    """
    user_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :tenant_id, :sub, :email)"
        ),
        {
            "id": user_id,
            "tenant_id": tenant_id,
            "sub": unique_subject(f"review-decision-{user_id.hex[:8]}"),
            "email": f"{user_id.hex[:8]}@example.edu",
        },
    )
    return user_id


def _insert_review_item(
    conn,
    tenant_id: uuid.UUID,
    batch_id: uuid.UUID,
    status: str,
    *,
    decided_by: uuid.UUID | None = None,
) -> None:
    """Insert a ``review_item`` row.

    ``decided_by`` is ``None`` by default — a fresh, ``pending`` row, which is
    the shape every pre-existing caller in this file wants. A caller writing a
    non-``pending`` status and wanting to isolate ``ck_review_item_status``
    from ``ck_review_item_decision_evidence`` (migration ``0013``, which
    refuses any non-``pending`` status with no ``decided_by``/``decided_at``)
    passes a real user id; this helper then writes ``decided_at = now()``
    alongside it, since the two are never meaningfully set independently
    outside the two negative tests written specifically to prove that pairing
    is enforced.
    """
    conn.execute(
        text(
            "INSERT INTO review_item "
            "(id, tenant_id, import_batch_id, row_index, row_data, status, "
            "decided_at, decided_by) "
            "VALUES (:id, :tenant_id, :batch_id, :row_index, :row_data, :status, "
            ":decided_at, :decided_by)"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "batch_id": batch_id,
            "row_index": 0,
            "row_data": '{"name": "example"}',
            "status": status,
            "decided_at": datetime.now(UTC) if decided_by is not None else None,
            "decided_by": decided_by,
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

    ``decided_by`` is supplied (a real user, via ``_make_user``) for every one
    of these, none of which is ``'pending'``: without it,
    ``ck_review_item_decision_evidence`` (migration ``0013``) would refuse the
    row first, for a different reason than the one this test is naming, and
    the assertion below would be checking the wrong constraint's message.
    """
    with pytest.raises(IntegrityError, match="ck_review_item_status"), engine.begin() as conn:
        batch = _make_import_batch(conn, tenant_id)
        _insert_review_item(conn, tenant_id, batch, status, decided_by=_make_user(conn, tenant_id))


@pytest.mark.parametrize("status", ["pending", "accepted", "rejected"])
def test_review_item_accepts_every_vocabulary_value(engine: Engine, tenant_id, status: str) -> None:
    """All three, because a review item is written ``pending`` and a human
    resolves it to one of the other two (v1.1 §1.5). A constraint narrowed to
    admit only one of the three outcomes passes every rejection test above and
    fails here — in particular a constraint reduced to ``status = 'pending'``,
    which would make every review decision impossible to record.

    ``pending`` is written with no decider — a fresh row, the shape an import
    actually produces. ``accepted``/``rejected`` are written with one, which
    ``ck_review_item_decision_evidence`` now requires of any non-``pending``
    row; leaving it off either of those two would fail *that* constraint
    rather than exercise this one.
    """
    with engine.begin() as conn:
        batch = _make_import_batch(conn, tenant_id)
        decided_by = _make_user(conn, tenant_id) if status != "pending" else None
        _insert_review_item(conn, tenant_id, batch, status, decided_by=decided_by)


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

    ``decided_at``/``decided_by`` are set in the same ``UPDATE`` — the shape
    ``ReviewRepository.decide`` actually writes — so what is refused here is
    ``'archived'`` itself, not the absence of decision evidence that
    ``ck_review_item_decision_evidence`` would refuse regardless of the status
    value.
    """
    with engine.begin() as conn:
        batch = _make_import_batch(conn, tenant_id)
        _insert_review_item(conn, tenant_id, batch, "pending")
        decider = _make_user(conn, tenant_id)

    with pytest.raises(IntegrityError, match="ck_review_item_status"), engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE review_item SET status = 'archived', decided_at = now(), "
                "decided_by = :decided_by "
                "WHERE tenant_id = :tenant_id AND import_batch_id = :batch_id"
            ),
            {"tenant_id": tenant_id, "batch_id": batch, "decided_by": decider},
        )


def test_review_item_status_accepts_the_review_decision_transition_on_update(
    engine: Engine, tenant_id
) -> None:
    """``pending -> accepted``, the transition a human review actually makes.

    Zero and positive amounts aside, an inverted constraint on this table
    would refuse exactly this write and would be caught by the parametrized
    insert test above; this pins the same guarantee against the UPDATE path a
    reviewer's decision actually takes — now carrying the citation
    ``ck_review_item_decision_evidence`` (migration ``0013``) requires
    alongside the status change, the shape ``ReviewRepository.decide``'s own
    single ``UPDATE`` writes.
    """
    with engine.begin() as conn:
        batch = _make_import_batch(conn, tenant_id)
        _insert_review_item(conn, tenant_id, batch, "pending")
        decider = _make_user(conn, tenant_id)

    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE review_item SET status = 'accepted', decided_at = now(), "
                "decided_by = :decided_by "
                "WHERE tenant_id = :tenant_id AND import_batch_id = :batch_id"
            ),
            {"tenant_id": tenant_id, "batch_id": batch, "decided_by": decider},
        )


# ---------------------------------------------------------------------------
# ck_review_item_decision_evidence — a decision cites who made it and when
# ---------------------------------------------------------------------------
#
# Migration 0013. Two biconditionals, ANDed: (status = 'pending') = (decided_at
# IS NULL), and (decided_at IS NULL) = (decided_by IS NULL). The forbidden
# writes below hit each biconditional from the direction a real bug would
# actually take — a status change that forgot to name a decider, and a
# still-pending row that somehow acquired a timestamp — rather than the
# direction the CHECK's own text reads most naturally in.


def test_review_item_decision_evidence_refuses_a_decided_row_with_no_decided_by(
    engine: Engine, tenant_id
) -> None:
    """``accepted`` with a timestamp but no author is a decision no one made.

    This is the write a bug in ``ReviewRepository.decide`` would produce if it
    ever set ``decided_at`` without also setting ``decided_by`` in the same
    statement — exactly the half-written-fact shape
    ``ck_redrive_authorship_complete`` already refuses for
    ``redriven_at``/``redriven_by`` one table over.
    """
    with (
        pytest.raises(IntegrityError, match="ck_review_item_decision_evidence"),
        engine.begin() as conn,
    ):
        batch = _make_import_batch(conn, tenant_id)
        conn.execute(
            text(
                "INSERT INTO review_item "
                "(id, tenant_id, import_batch_id, row_index, row_data, status, decided_at) "
                "VALUES (:id, :tenant_id, :batch_id, 0, :row_data, 'accepted', now())"
            ),
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "batch_id": batch,
                "row_data": '{"name": "example"}',
            },
        )


def test_review_item_decision_evidence_refuses_a_pending_row_carrying_a_decided_at(
    engine: Engine, tenant_id
) -> None:
    """A row that is still ``pending`` must not also claim a decision time.

    The mirror image of the test above, and the half of the CHECK a decider
    with no timestamp cannot exercise: this is what refuses a stray
    ``UPDATE ... SET decided_at = now()`` that never also moved ``status`` off
    ``pending`` — a bug that would otherwise leave the queue a coordinator
    reads (``pending_review_items``) reporting a row as undecided while its
    own ``decided_at`` says otherwise.
    """
    with (
        pytest.raises(IntegrityError, match="ck_review_item_decision_evidence"),
        engine.begin() as conn,
    ):
        batch = _make_import_batch(conn, tenant_id)
        conn.execute(
            text(
                "INSERT INTO review_item "
                "(id, tenant_id, import_batch_id, row_index, row_data, status, decided_at) "
                "VALUES (:id, :tenant_id, :batch_id, 0, :row_data, 'pending', now())"
            ),
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "batch_id": batch,
                "row_data": '{"name": "example"}',
            },
        )


def test_review_item_decision_evidence_accepts_a_fully_evidenced_decision(
    engine: Engine, tenant_id
) -> None:
    """The legitimate write: a non-``pending`` status, a timestamp, and a decider.

    The permitted-write half of this CHECK, proven independently of the
    UPDATE-path test above (which pins the same guarantee against
    ``ck_review_item_status`` and reaches this shape as a side effect, not as
    its own point).
    """
    with engine.begin() as conn:
        batch = _make_import_batch(conn, tenant_id)
        decider = _make_user(conn, tenant_id)
        _insert_review_item(conn, tenant_id, batch, "rejected", decided_by=decider)


# ---------------------------------------------------------------------------
# fk_review_item_decided_by — the deciding user, cited and protected
# ---------------------------------------------------------------------------
#
# Migration 0013. ON DELETE RESTRICT: deleting the user_account behind a
# recorded decision must not silently turn a cited decision back into an
# uncited one — the same fabricated-field state the CHECK above exists to
# make unstorable in the first place. Not a CHECK constraint, and so out of
# `test_check_constraints.py`'s scope, exercised here for the reason
# `uq_review_item_batch_row` already is: only an attempted write proves it.


def test_review_item_decided_by_user_cannot_be_deleted(engine: Engine, tenant_id) -> None:
    """The deciding user cannot be deleted out from under the decision.

    Verified against a *live* decision, not an orphaned reference someone
    typed in: the row is written first through the ordinary accepted path,
    and only then is the same user's own deletion attempted and refused.
    """
    with engine.begin() as conn:
        batch = _make_import_batch(conn, tenant_id)
        decider = _make_user(conn, tenant_id)
        _insert_review_item(conn, tenant_id, batch, "accepted", decided_by=decider)

    with pytest.raises(IntegrityError, match="fk_review_item_decided_by"), engine.begin() as conn:
        conn.execute(
            text("DELETE FROM user_account WHERE tenant_id = :tenant_id AND id = :id"),
            {"tenant_id": tenant_id, "id": decider},
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
