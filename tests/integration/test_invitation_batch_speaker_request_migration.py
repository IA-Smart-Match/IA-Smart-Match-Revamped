"""Migration ``0041_invitation_batch_speaker_request``: column, backfill, key (B26 T4).

``0041`` gives ``cba_invitation_batch`` the Speaker Request it invites for:

* ``speaker_request_id`` — nullable ``uuid``, no default.
* A one-statement backfill from the batch's run: the run's ``event_need_id``
  names a ``coordinator_entry`` event hosted by the batch's own unit, and the run
  is in that unit too. Text comparison, never ``::uuid``, so a pre-OQ-CBA-031
  free-text need leaves the row NULL instead of aborting the revision.
* ``fk_cba_invitation_batch_speaker_request`` — composite ``(tenant_id,
  speaker_request_id)`` → ``event (tenant_id, id)``, ``ON DELETE RESTRICT``.

Plan: ``docs/plans/b26-tracks/T4-plan.md`` §4.1, tests M1–M7. The upgrade and
downgrade run for real against a scratch database seeded at ``0040``.

Requires a live database and the privilege to create one; skipped otherwise.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest

pytest.importorskip("sqlalchemy")

from migration_harness import alembic, applied_revision, connected, scratch_database
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

#: Read off the ``revision =`` line of ``0040_speaker_booking_cancellation.py``.
REVISION_BEFORE = "0040_booking_cancellation"

#: The revision under test. Read off the ``revision =`` line of
#: ``0041_invitation_batch_speaker_request.py``: ``alembic_version`` is
#: ``varchar(32)``, so the id is shorter than the file name.
REVISION = "0041_batch_speaker_request"

_FK = "fk_cba_invitation_batch_speaker_request"

#: The pins on every seeded run. Plausible literals: these rows are never scored.
_PINS = (
    "'sha256:0000', 1, 0, '2.0.0', 'sha256:1111', "
    "CAST('{\"topic_relevance\": 1.0}' AS jsonb), '1.0.0-cpsat', 'ortools-cpsat', "
    "'9.99.0', 'straight_line', '1.0.0-straight-line', 'optimal'"
)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Tenant:
    tenant_id: uuid.UUID
    unit_a: uuid.UUID
    unit_b: uuid.UUID
    user_id: uuid.UUID


def _tenant(conn) -> _Tenant:
    tenant_id = uuid.uuid4()
    conn.execute(
        text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
        {"id": tenant_id, "slug": f"scratch-{tenant_id.hex[:12]}"},
    )
    units = []
    for label in ("a", "b"):
        unit_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                "VALUES (:id, :tid, CAST(:path AS ltree), 'department', :name)"
            ),
            {
                "id": unit_id,
                "tid": tenant_id,
                "path": f"scratch{label}{unit_id.hex[:8]}",
                "name": f"Unit {label}",
            },
        )
        units.append(unit_id)
    user_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :tid, :sub, :email)"
        ),
        {
            "id": user_id,
            "tid": tenant_id,
            "sub": f"scratch-{user_id.hex}",
            "email": f"{user_id.hex[:8]}@example.edu",
        },
    )
    return _Tenant(tenant_id, units[0], units[1], user_id)


def _request(conn, tenant_id: uuid.UUID, unit_id: uuid.UUID) -> uuid.UUID:
    """A Speaker Request: a ``coordinator_entry`` event hosted by ``unit_id``."""
    event_id = uuid.uuid4()
    title = f"Career Panel {event_id.hex[:8]}"
    conn.execute(
        text(
            "INSERT INTO event (id, tenant_id, host_org_unit_id, title, normalized_title, "
            "on_date, time_zone, time_precision, resolved_date, origin) "
            "VALUES (:id, :tid, :unit, :title, :normalized, DATE '2026-10-05', "
            "'America/Los_Angeles', 'date_only', DATE '2026-10-05', 'coordinator_entry')"
        ),
        {
            "id": event_id,
            "tid": tenant_id,
            "unit": unit_id,
            "title": title,
            "normalized": title.lower(),
        },
    )
    return event_id


def _run(conn, tenant_id: uuid.UUID, unit_id: uuid.UUID, need: str) -> uuid.UUID:
    job_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO job (id, tenant_id, command_type, status, owning_unit_id, payload) "
            "VALUES (:id, :tid, 'match-run.create', 'succeeded', :unit, CAST('{}' AS jsonb))"
        ),
        {"id": job_id, "tid": tenant_id, "unit": unit_id},
    )
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


def _batch(
    conn,
    tenant: _Tenant,
    unit_id: uuid.UUID,
    run_id: uuid.UUID | None,
    *,
    speaker_request_id: uuid.UUID | None = None,
) -> uuid.UUID:
    batch_id = uuid.uuid4()
    columns = "id, tenant_id, owning_unit_id, match_run_id, idempotency_key, template_id, "
    columns += "event_name, event_date, created_by_user_id"
    values = ":id, :tid, :unit, :run, :key, 'speaker_invite_v1', 'Career Panel', "
    values += "'5 October 2026', :actor"
    params = {
        "id": batch_id,
        "tid": tenant.tenant_id,
        "unit": unit_id,
        "run": run_id,
        "key": f"key-{batch_id.hex}",
        "actor": tenant.user_id,
    }
    if speaker_request_id is not None:
        columns += ", speaker_request_id"
        values += ", :request"
        params["request"] = speaker_request_id
    conn.execute(
        text(f"INSERT INTO cba_invitation_batch ({columns}) VALUES ({values})"),
        params,
    )
    return batch_id


def _stamped(conn, batch_id: uuid.UUID) -> uuid.UUID | None:
    value = conn.execute(
        text("SELECT speaker_request_id FROM cba_invitation_batch WHERE id = :id"),
        {"id": batch_id},
    ).scalar_one()
    return None if value is None else uuid.UUID(str(value))


def _has_column(conn) -> bool:
    return bool(
        conn.execute(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'cba_invitation_batch' "
                "AND column_name = 'speaker_request_id'"
            )
        ).scalar_one()
    )


def _has_fk(conn) -> bool:
    return bool(
        conn.execute(
            text("SELECT count(*) FROM pg_constraint WHERE conname = :n"), {"n": _FK}
        ).scalar_one()
    )


# ---------------------------------------------------------------------------
# M1-M4: the backfill
# ---------------------------------------------------------------------------


def test_upgrade_backfills_the_request_from_a_same_unit_run(engine: Engine) -> None:
    """M1."""
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)
        with connected(url) as scratch:
            with scratch.begin() as conn:
                tenant = _tenant(conn)
                request_id = _request(conn, tenant.tenant_id, tenant.unit_a)
                run_id = _run(conn, tenant.tenant_id, tenant.unit_a, str(request_id))
                batch_id = _batch(conn, tenant, tenant.unit_a, run_id)

            alembic(url, REVISION, expect_success=True)
            assert applied_revision(url) == REVISION

            with scratch.connect() as conn:
                assert _stamped(conn, batch_id) == request_id


def test_upgrade_leaves_null_for_a_batch_without_a_run(engine: Engine) -> None:
    """M2."""
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)
        with connected(url) as scratch:
            with scratch.begin() as conn:
                tenant = _tenant(conn)
                _request(conn, tenant.tenant_id, tenant.unit_a)
                batch_id = _batch(conn, tenant, tenant.unit_a, None)

            alembic(url, REVISION, expect_success=True)

            with scratch.connect() as conn:
                assert _stamped(conn, batch_id) is None


def test_upgrade_leaves_null_for_a_run_whose_need_is_not_a_uuid(engine: Engine) -> None:
    """M3: a pre-OQ-CBA-031 free-text need; a ``::uuid`` cast would abort the revision."""
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)
        with connected(url) as scratch:
            with scratch.begin() as conn:
                tenant = _tenant(conn)
                _request(conn, tenant.tenant_id, tenant.unit_a)
                run_id = _run(conn, tenant.tenant_id, tenant.unit_a, "need-career-panel")
                batch_id = _batch(conn, tenant, tenant.unit_a, run_id)

            alembic(url, REVISION, expect_success=True)
            assert applied_revision(url) == REVISION

            with scratch.connect() as conn:
                assert _stamped(conn, batch_id) is None


def test_upgrade_leaves_null_when_the_run_or_request_is_in_another_unit(engine: Engine) -> None:
    """M4: a run in unit B, and a run in unit A naming a request hosted by unit B."""
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)
        with connected(url) as scratch:
            with scratch.begin() as conn:
                tenant = _tenant(conn)
                request_a = _request(conn, tenant.tenant_id, tenant.unit_a)
                request_b = _request(conn, tenant.tenant_id, tenant.unit_b)
                run_in_b = _run(conn, tenant.tenant_id, tenant.unit_b, str(request_a))
                foreign_run = _batch(conn, tenant, tenant.unit_a, run_in_b)
                run_naming_b = _run(conn, tenant.tenant_id, tenant.unit_a, str(request_b))
                foreign_request = _batch(conn, tenant, tenant.unit_a, run_naming_b)

            alembic(url, REVISION, expect_success=True)

            with scratch.connect() as conn:
                assert _stamped(conn, foreign_run) is None
                assert _stamped(conn, foreign_request) is None


# ---------------------------------------------------------------------------
# M5-M6: the key
# ---------------------------------------------------------------------------


def test_the_fk_refuses_a_request_from_another_tenant(engine: Engine) -> None:
    """M5: composite, so a batch can never name another tenant's request."""
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)
        with connected(url) as scratch:
            with scratch.begin() as conn:
                ours = _tenant(conn)
                theirs = _tenant(conn)
                their_request = _request(conn, theirs.tenant_id, theirs.unit_a)

            with pytest.raises(IntegrityError) as refused, scratch.begin() as conn:
                _batch(conn, ours, ours.unit_a, None, speaker_request_id=their_request)
            assert _FK in str(refused.value)


def test_the_fk_restricts_deleting_a_request_a_batch_names(engine: Engine) -> None:
    """M6: ``ON DELETE RESTRICT`` — a batch's record of what it invited for stays."""
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)
        with connected(url) as scratch:
            with scratch.begin() as conn:
                tenant = _tenant(conn)
                request_id = _request(conn, tenant.tenant_id, tenant.unit_a)
                _batch(conn, tenant, tenant.unit_a, None, speaker_request_id=request_id)

            with pytest.raises(IntegrityError) as refused, scratch.begin() as conn:
                conn.execute(text("DELETE FROM event WHERE id = :id"), {"id": request_id})
            assert _FK in str(refused.value)


# ---------------------------------------------------------------------------
# M7: the downgrade
# ---------------------------------------------------------------------------


def test_downgrade_drops_column_and_fk_and_upgrade_reapplies(engine: Engine) -> None:
    """M7: the backfilled value is derivable again on re-upgrade."""
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)
        with connected(url) as scratch:
            with scratch.begin() as conn:
                tenant = _tenant(conn)
                request_id = _request(conn, tenant.tenant_id, tenant.unit_a)
                run_id = _run(conn, tenant.tenant_id, tenant.unit_a, str(request_id))
                batch_id = _batch(conn, tenant, tenant.unit_a, run_id)

            alembic(url, REVISION, expect_success=True)
            with scratch.connect() as conn:
                assert _has_column(conn)
                assert _has_fk(conn)

            alembic(url, REVISION_BEFORE, expect_success=True, command="downgrade")
            assert applied_revision(url) == REVISION_BEFORE
            with scratch.connect() as conn:
                assert not _has_column(conn)
                assert not _has_fk(conn)

            alembic(url, REVISION, expect_success=True)
            assert applied_revision(url) == REVISION
            with scratch.connect() as conn:
                assert _stamped(conn, batch_id) == request_id
