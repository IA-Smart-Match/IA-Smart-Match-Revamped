"""What migration ``0032`` does to rows that already exist: nothing.

``0032`` adds ``scoring_mode`` and ``scoring_mode_version`` to ``match_run``
(OQ-CBA-028) and **deliberately does not backfill them**. That is the part of the
revision no assertion against the development database can reach: there, the
migration has already run and the pre-``0032`` rows it would have rewritten are
gone. So this file brings a scratch database to ``0031``, fills it with runs the
way the previous release would have, and then runs Alembic for real.

The row that matters is the first one
=======================================
Two of the three runs below have nothing a backfill could have used. The third —
``backfillable`` — has **everything** it would have needed: a durable job payload
whose ``explanations`` array names one mode, unanimously, in the vocabulary, with
one version beside it. That is precisely the shape the rejected backfill was
written to catch.

It must still be NULL after the upgrade. Without that row this file would pass
against a migration that backfilled enthusiastically and merely had no data to
work on — the difference between "the backfill was removed" and "the backfill
found nothing", and only one of those is the decision that was made.

Why there is no backfill at all
=================================
Recorded here as well as in the migration, because a test is where somebody looks
when they are about to change the behaviour. The backfill was written, reviewed,
and rejected on 6 September 2026 by Danny Tran, program owner of record. Reaching
those rows requires an UPDATE, ``0018``'s ``match_run_is_immutable`` refuses every
UPDATE, and switching that trigger off — by name, by ``session_replication_role``,
or by drop-and-recreate — is a permanent precedent the next revision wanting to
"just fix these rows" would cite correctly. Nothing is lost by declining: the
stored explanation payload remains the system of record for a pre-ADR-0016 run's
mode, and NULL is the true statement about a run that has none.

So this file asserts the trigger too. A later edit reintroducing a backfill would
have to move it, and
:func:`test_the_immutability_trigger_is_untouched_by_the_upgrade` is what notices.

Requires a live database and the privilege to create one; skipped otherwise.
"""

from __future__ import annotations

import uuid

import pytest

pytest.importorskip("sqlalchemy")

from migration_harness import alembic, applied_revision, connected, scratch_database
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.integration

#: The revision immediately before the one under test. A scratch database is
#: brought to here and filled with runs that predate the mode columns.
#:
#: Read off the ``revision =`` line of ``0031_student_speaker_feedback.py``, not
#: off a filename: Alembic revision ids are not filenames, and this repository
#: carries the standing proof — ``0024_cba_classification_schema.py`` declares
#: ``revision = "0024_cba_classification"``.
REVISION_BEFORE = "0031_student_speaker_feedback"

#: The revision under test.
REVISION = "0032_match_run_scoring_mode"

#: A job payload carrying exactly what the rejected backfill would have read: one
#: mode, on every entry, in the vocabulary, with one version beside it. Written
#: as JSON text rather than as a dict so the row lands the way the previous
#: release wrote it, through an explicit ``jsonb`` cast.
UNAMBIGUOUS_PAYLOAD = (
    '{"explanations": ['
    '{"subject_id": "prof-a", "scoring_mode": "cba-virtual-1", '
    '"scoring_mode_version": "1.0.0"}, '
    '{"subject_id": "prof-b", "scoring_mode": "cba-virtual-1", '
    '"scoring_mode_version": "1.0.0"}]}'
)

#: A payload from a release that had no modes. The honest pre-ADR-0016 shape, and
#: the row for which NULL was always going to be the answer.
UNLABELLED_PAYLOAD = (
    '{"explanations": [{"subject_id": "prof-c", "scoring_mode": null, '
    '"scoring_mode_version": null}]}'
)

#: The pins on every seeded run. Plausible literals rather than derived values:
#: these rows are never re-scored, and what this file is about is the two columns
#: they do not have yet.
_PINS = (
    "'sha256:0000', 1, 0, '1.1.1-approved-g1-m6j', 'sha256:1111', "
    "CAST('{\"topic_relevance\": 1.0}' AS jsonb), '1.0.0-cpsat', 'ortools-cpsat', "
    "'9.99.0', 'straight_line', '1.0.0-straight-line', 'optimal'"
)


def _insert_tenant(conn, tenant_id: uuid.UUID) -> None:
    conn.execute(
        text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
        {"id": tenant_id, "slug": f"scratch-{tenant_id.hex[:12]}"},
    )


def _insert_unit(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    unit_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
            "VALUES (:id, :tid, CAST(:path AS ltree), 'department', 'Scratch')"
        ),
        {"id": unit_id, "tid": tenant_id, "path": f"scratch{tenant_id.hex[:8]}"},
    )
    return unit_id


def _insert_job(conn, tenant_id: uuid.UUID, unit_id: uuid.UUID, payload: str | None) -> uuid.UUID:
    job_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO job (id, tenant_id, command_type, status, owning_unit_id, payload) "
            "VALUES (:id, :tid, 'match-run.create', 'succeeded', :unit, CAST(:payload AS jsonb))"
        ),
        {"id": job_id, "tid": tenant_id, "unit": unit_id, "payload": payload},
    )
    return job_id


def _insert_pre_0032_run(
    conn, tenant_id: uuid.UUID, unit_id: uuid.UUID, job_id: uuid.UUID, need: str
) -> uuid.UUID:
    """Insert a run the way ``0031`` would have, naming no mode columns at all."""
    run_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO match_run (id, tenant_id, owning_unit_id, job_id, event_need_id, "
            "inputs_hash, portfolio_size, random_seed, registry_version, registry_hash, "
            "weights, optimizer_model_version, solver_name, solver_version, "
            "route_estimate_source, route_estimate_version, portfolio_status) "
            f"VALUES (:id, :tid, :unit, :job, :need, {_PINS})"
        ),
        {"id": run_id, "tid": tenant_id, "unit": unit_id, "job": job_id, "need": need},
    )
    return run_id


def _seed_three_runs(scratch) -> dict[str, uuid.UUID]:
    """Three pre-``0032`` runs: unambiguous payload, unlabelled payload, no payload."""
    tenant_id = uuid.uuid4()
    with scratch.begin() as conn:
        _insert_tenant(conn, tenant_id)
        unit_id = _insert_unit(conn, tenant_id)
        return {
            "backfillable": _insert_pre_0032_run(
                conn,
                tenant_id,
                unit_id,
                _insert_job(conn, tenant_id, unit_id, UNAMBIGUOUS_PAYLOAD),
                "need-backfillable",
            ),
            "unlabelled": _insert_pre_0032_run(
                conn,
                tenant_id,
                unit_id,
                _insert_job(conn, tenant_id, unit_id, UNLABELLED_PAYLOAD),
                "need-unlabelled",
            ),
            "no_payload": _insert_pre_0032_run(
                conn,
                tenant_id,
                unit_id,
                _insert_job(conn, tenant_id, unit_id, None),
                "need-no-payload",
            ),
        }


def test_a_pre_0032_run_keeps_a_null_mode_even_when_its_payload_names_one(engine: Engine):
    """The decision, asserted on the one row that could have gone either way.

    ``backfillable``'s job payload names ``cba-virtual-1`` unanimously — the
    rejected backfill's exact target. It stays NULL, which is what says the
    backfill was *removed* rather than merely starved of data.

    The other two rows are the control: they were always going to be NULL, and a
    test made only of them would pass against either migration.

    Upgraded to :data:`REVISION` rather than ``head``: this test is about what
    ``0032`` itself does to a pre-existing row, not about the state of the chain
    after whatever runs after it. ``0033_event_filed_by`` moved head past ``0032``
    without touching ``match_run`` at all, and pinning here (as
    :data:`REVISION_BEFORE` already does for the starting point) keeps this test
    from re-breaking every time head moves again.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)

        with connected(url) as scratch:
            runs = _seed_three_runs(scratch)

            alembic(url, REVISION, expect_success=True)

            with scratch.connect() as conn:
                stored = {
                    row.id: (row.scoring_mode, row.scoring_mode_version)
                    for row in conn.execute(
                        text("SELECT id, scoring_mode, scoring_mode_version FROM match_run")
                    )
                }

        assert applied_revision(url) == REVISION

    assert stored[runs["backfillable"]] == (None, None), (
        "a run whose stored payload names one unambiguous mode was backfilled. "
        "0032 declines to backfill on purpose: reaching this row needs an UPDATE, "
        "and match_run_is_immutable refuses every UPDATE (OQ-CBA-028)."
    )
    assert stored[runs["unlabelled"]] == (None, None)
    assert stored[runs["no_payload"]] == (None, None)


def test_the_upgrade_writes_no_row_at_all(engine: Engine):
    """Whole-table, so a backfill reaching rows this file did not name still fails.

    The mirror of ``test_job_owning_unit.py``'s "no row anywhere escaped the
    backfill", inverted: here the claim is that no row anywhere was *reached* by
    one.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)

        with connected(url) as scratch:
            _seed_three_runs(scratch)

            alembic(url, "head", expect_success=True)

            with scratch.connect() as conn:
                labelled = conn.execute(
                    text(
                        "SELECT count(*) FROM match_run "
                        "WHERE scoring_mode IS NOT NULL OR scoring_mode_version IS NOT NULL"
                    )
                ).scalar_one()

    assert labelled == 0


def test_the_immutability_trigger_is_untouched_by_the_upgrade(engine: Engine):
    """``0018``'s guarantee survives ``0032`` — enabled, and still refusing.

    Both halves, because they fail differently. ``tgenabled`` catches a migration
    that disabled the trigger and forgot to switch it back on; the attempted
    UPDATE catches one that re-enabled it in a state where it no longer fires. A
    revision reintroducing the rejected backfill would have to move this trigger,
    and this is what notices.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)

        with connected(url) as scratch:
            runs = _seed_three_runs(scratch)

            alembic(url, "head", expect_success=True)

            with scratch.connect() as conn:
                enabled = conn.execute(
                    text("SELECT tgenabled FROM pg_trigger WHERE tgname = 'match_run_is_immutable'")
                ).scalar_one()

            with pytest.raises(DBAPIError) as raised, scratch.begin() as conn:
                conn.execute(
                    text("UPDATE match_run SET scoring_mode = 'cba-virtual-1' WHERE id = :id"),
                    {"id": runs["backfillable"]},
                )

    # 'O' is "enabled, origin" — the state CREATE TRIGGER leaves it in. 'D' would
    # be a trigger this migration switched off and never switched back on.
    assert enabled == "O", f"match_run_is_immutable is not enabled at origin: {enabled!r}"
    assert "immutable" in str(raised.value).lower(), (
        f"the UPDATE was refused by something other than the trigger: {raised.value}"
    )


def test_a_run_written_after_the_upgrade_can_carry_a_mode(engine: Engine):
    """Not backfilling the old rows does not mean the columns are inert.

    The complement of every assertion above: what ``0032`` buys is that runs from
    now on are queryable, and a file proving only that the old rows were untouched
    would pass against a migration that added two columns nothing can ever use.

    Written as an INSERT rather than an UPDATE of a seeded row, because the
    trigger forbids the update — which is the whole reason this migration does not
    backfill.
    """
    with scratch_database(engine) as url:
        alembic(url, "head", expect_success=True)

        with connected(url) as scratch:
            tenant_id = uuid.uuid4()
            with scratch.begin() as conn:
                _insert_tenant(conn, tenant_id)
                unit_id = _insert_unit(conn, tenant_id)
                job_id = _insert_job(conn, tenant_id, unit_id, UNAMBIGUOUS_PAYLOAD)
                conn.execute(
                    text(
                        "INSERT INTO match_run (id, tenant_id, owning_unit_id, job_id, "
                        "event_need_id, inputs_hash, portfolio_size, random_seed, "
                        "registry_version, registry_hash, weights, optimizer_model_version, "
                        "solver_name, solver_version, route_estimate_source, "
                        "route_estimate_version, portfolio_status, scoring_mode, "
                        f"scoring_mode_version) VALUES (:id, :tid, :unit, :job, "
                        f"'need-labelled', {_PINS}, 'cba-virtual-1', '1.0.0')"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "tid": tenant_id,
                        "unit": unit_id,
                        "job": job_id,
                    },
                )

            with scratch.connect() as conn:
                virtual = conn.execute(
                    text("SELECT count(*) FROM match_run WHERE scoring_mode = 'cba-virtual-1'")
                ).scalar_one()

    assert virtual == 1
