"""A ``match_run`` is written by executing a command, never by a route (card M8a).

Card M8a: "Executed through the existing durable-command path (transactional
outbox per ADR-0005)." That sentence is a claim about *where* the write happens,
and the only way to check it is to drive the real path: accept a job and its
outbox row in one transaction, dispatch with the real dispatcher, execute with
the real executor and the registry that ships, and then look for the row.

No HTTP anywhere in this file, and that is still not an omission — though the
reason has changed. Card M8b has since landed
``POST /v1/units/{unit_id}/match-runs``, and
``tests/contract/test_match_runs_api.py`` drives the whole path over HTTP,
including the assertion that a ``202`` writes a job and *no* snapshot. What this
file proves is the half that does not depend on a route existing: that the
handler, the outbox and the executor together produce one immutable,
version-pinned row. Accepting the job directly — the same idiom
``test_worker_execution.py::accept_command`` uses for every other command type —
keeps that proof independent of whatever the API happens to accept today, so a
change to the request contract cannot quietly change what this file checks.

Requires a live database, and is skipped when none is reachable.
"""

from __future__ import annotations

import uuid

import pytest

pytest.importorskip("sqlalchemy")

from conftest import ensure_owning_unit
from smartmatch_domain.factor_registry import (
    CBA_PHYSICAL_MODEL,
    REGISTRY_VERSION,
    SUPERSEDED_G1_MODEL,
    SUPERSEDED_REGISTRY_VERSION,
    normalize_weights,
)
from smartmatch_domain.jobs import JobState
from smartmatch_domain.match_run import (
    MATCH_RUN_COMMAND_TYPE,
    inputs_fingerprint,
    weights_fingerprint,
)
from smartmatch_persistence.jobs import JobRepository
from smartmatch_persistence.outbox import OutboxRepository
from smartmatch_providers.tasks import FixtureTaskQueue
from smartmatch_worker.dispatcher import OutboxDispatcher
from smartmatch_worker.execution import TaskExecutor
from smartmatch_worker.handlers import default_registry
from sqlalchemy import text

pytestmark = pytest.mark.integration

NEED = "need-synthetic-1"
#: A synthetic pool. The utilities are invented for this file and stand for
#: "already scored by whoever assembled the pool"; they are not a claim about
#: any real professional, and nothing here computes them.
POOL = (
    {"subject_id": "prof-synthetic-a", "utility": 0.82},
    {"subject_id": "prof-synthetic-b", "utility": 0.4},
    {"subject_id": "prof-synthetic-c", "utility": 0.61},
)
PORTFOLIO_SIZE = 2


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_need_id": NEED,
        "portfolio_size": PORTFOLIO_SIZE,
        "random_seed": 0,
        "candidates": [dict(candidate) for candidate in POOL],
    }
    payload.update(overrides)
    return payload


def _accept(session_factory, tenant_id, payload) -> uuid.UUID:
    """Accept the command the way ``submit_command`` does: job and outbox together.

    One transaction, so a crash can never leave a job with no outbox row to
    dispatch it (v1.1 §1.6). The same idiom as
    ``test_worker_execution.py::accept_command``; written out again rather than
    imported because that helper lives in a test module, not a fixture module.
    """
    with session_factory() as session:
        job = JobRepository().create(
            session,
            tenant_id=tenant_id,
            command_type=MATCH_RUN_COMMAND_TYPE,
            owning_unit_id=ensure_owning_unit(session, tenant_id),
            payload=payload,
        )
        OutboxRepository().enqueue(
            session, tenant_id=tenant_id, job_id=job.id, command_type=MATCH_RUN_COMMAND_TYPE
        )
        session.commit()
    return job.id


def _run(session_factory, tenant_id, job_id):
    """Dispatch and execute one accepted command, with the shipped registry."""
    OutboxDispatcher(session_factory, FixtureTaskQueue()).run_once()
    return TaskExecutor(session_factory, default_registry()).execute(
        tenant_id=tenant_id, job_id=job_id
    )


def _terminal_event(session_factory, tenant_id, job_id):
    with session_factory() as session:
        events = [
            event.payload
            for event in JobRepository().events_since(session, tenant_id=tenant_id, job_id=job_id)
        ]
    return events[-1]


# ---------------------------------------------------------------------------
# The command path, end to end
# ---------------------------------------------------------------------------


def test_executing_the_command_records_one_immutable_snapshot(session_factory, tenant_id, engine):
    """The card, proved: accept, dispatch, execute, and the row exists.

    Asserted as ``succeeded`` **with the snapshot present**, not merely as "the
    job reached a terminal state". A job that failed is terminal too, and a
    handler reporting success while writing nothing is the exact failure mode
    v1.1 §5.5 exists to close.
    """
    job_id = _accept(session_factory, tenant_id, _payload())
    outcome = _run(session_factory, tenant_id, job_id)

    assert outcome.status == "executed"
    assert outcome.state is JobState.SUCCEEDED

    with engine.connect() as conn:
        stored = conn.execute(
            text("SELECT * FROM match_run WHERE tenant_id = :tid"), {"tid": tenant_id}
        ).one()

    assert stored.job_id == job_id
    assert stored.event_need_id == NEED
    assert stored.portfolio_size == PORTFOLIO_SIZE
    assert stored.portfolio_status in {"optimal", "feasible"}


def test_the_snapshot_pins_the_registry_the_run_actually_used(session_factory, tenant_id, engine):
    """The worksheet's "every run records registry version hash", checked.

    Both halves: the version string, and a digest of the weights that were
    actually in force. A version alone is a label somebody types; a digest alone
    cannot be traced back to the decision that approved it.

    ``_payload()`` names no ``scoring_mode``, which under ADR-0016 Proposal 7
    makes it a **pre-ADR-0016 run** — so the pin here is the superseded
    rulebook's, not today's ``REGISTRY_VERSION``. That is the point of the
    title: *the registry the run actually used*. Pinning 2.0.0 over utilities
    that no CBA factor produced would be a reproducible-looking record of
    something that did not happen.
    """
    job_id = _accept(session_factory, tenant_id, _payload())
    _run(session_factory, tenant_id, job_id)

    weights = normalize_weights(model=SUPERSEDED_G1_MODEL)
    with engine.connect() as conn:
        stored = conn.execute(
            text(
                "SELECT registry_version, registry_hash, weights FROM match_run WHERE job_id = :job"
            ),
            {"job": job_id},
        ).one()

    assert stored.registry_version == SUPERSEDED_REGISTRY_VERSION
    assert stored.registry_version != REGISTRY_VERSION
    assert stored.registry_hash == weights_fingerprint(weights)
    # Readable as well as hashed, and it is the *normalized* set: the weights
    # that applied, not the proposed ones that include unimplemented factors.
    assert stored.weights == dict(weights)
    assert set(stored.weights) == {"topic_relevance", "travel_burden"}


def test_a_run_naming_a_cba_mode_pins_the_cba_registry(session_factory, tenant_id, engine):
    """The other arm: a payload that names a mode pins the rulebook that has one.

    The worker chooses no mode of its own — it does not score — so this is the
    only way a run reaches ``2.0.0-approved-oq-cba-004``, and it is worth an
    integration test rather than a unit one because the pin has to survive the
    whole durable path: payload written, job dispatched, handler executed, row
    read back out of PostgreSQL.
    """
    job_id = _accept(
        session_factory, tenant_id, _payload(scoring_mode=CBA_PHYSICAL_MODEL.scoring_mode)
    )
    _run(session_factory, tenant_id, job_id)

    weights = normalize_weights(model=CBA_PHYSICAL_MODEL)
    with engine.connect() as conn:
        stored = conn.execute(
            text(
                "SELECT registry_version, registry_hash, weights FROM match_run WHERE job_id = :job"
            ),
            {"job": job_id},
        ).one()

    assert stored.registry_version == REGISTRY_VERSION
    assert stored.registry_hash == weights_fingerprint(weights)
    assert stored.weights == dict(weights)
    assert set(stored.weights) == {
        "industry_match",
        "role_match",
        "cba_semantic_topic",
        "proximity",
    }


def test_two_modes_of_one_registry_share_a_version_and_differ_in_hash(
    session_factory, tenant_id, engine
):
    """ADR-0016 Proposal 9, end to end: same rulebook, different model.

    The property golden case G-CBA-09 asserts in the domain, asserted again
    here against two rows that actually reached the database — because a
    fingerprint that collided would make two runs scoring different factor sets
    indistinguishable in storage, and that is a storage claim.
    """
    physical_job = _accept(session_factory, tenant_id, _payload(scoring_mode="cba-physical-1"))
    _run(session_factory, tenant_id, physical_job)
    virtual_job = _accept(session_factory, tenant_id, _payload(scoring_mode="cba-virtual-1"))
    _run(session_factory, tenant_id, virtual_job)

    with engine.connect() as conn:
        rows = {
            str(job): conn.execute(
                text("SELECT registry_version, registry_hash FROM match_run WHERE job_id = :job"),
                {"job": job},
            ).one()
            for job in (physical_job, virtual_job)
        }

    physical = rows[str(physical_job)]
    virtual = rows[str(virtual_job)]

    assert physical.registry_version == virtual.registry_version == REGISTRY_VERSION
    assert physical.registry_hash != virtual.registry_hash


def test_the_snapshot_pins_the_optimizer_and_the_route_estimate(session_factory, tenant_id, engine):
    """The other two pins the card names, and what they are allowed to say.

    ``route_estimate_source`` is ``straight_line`` because the D3 route matrix
    is deferred and ``factors/travel_burden.py`` computes a haversine estimate.
    Recording it now is what keeps these rows honest the day D3 lands.
    """
    job_id = _accept(session_factory, tenant_id, _payload())
    _run(session_factory, tenant_id, job_id)

    with engine.connect() as conn:
        stored = conn.execute(
            text(
                "SELECT optimizer_model_version, solver_name, solver_version, "
                "route_estimate_source, route_estimate_version FROM match_run WHERE job_id = :job"
            ),
            {"job": job_id},
        ).one()

    assert stored.solver_name == "ortools-cpsat"
    # Not asserted as a literal: the pinned ortools build is a lock-file fact,
    # and a test naming it would fail on an unrelated dependency bump while
    # proving nothing about whether the version was recorded.
    assert stored.solver_version.strip()
    assert stored.optimizer_model_version.strip()
    assert stored.route_estimate_source == "straight_line"
    assert stored.route_estimate_version.strip()


def test_the_inputs_hash_is_the_one_the_domain_derives(session_factory, tenant_id, engine):
    """A stored digest nobody can recompute answers no question.

    Recomputed here from the same public function the handler used, over the
    payload as submitted, so the column is checkable rather than merely
    populated.
    """
    job_id = _accept(session_factory, tenant_id, _payload())
    _run(session_factory, tenant_id, job_id)

    expected = inputs_fingerprint(
        event_need_id=NEED,
        candidate_subject_ids=[candidate["subject_id"] for candidate in POOL],
        candidate_utilities=[candidate["utility"] for candidate in POOL],
        portfolio_size=PORTFOLIO_SIZE,
        random_seed=0,
        # The weights the run actually applied. ``_payload()`` names no mode, so
        # that is the superseded model's set — folding today's default in here
        # instead would compare the stored digest against weights the run never
        # saw, and the mismatch would look like a fingerprinting bug.
        weights=normalize_weights(model=SUPERSEDED_G1_MODEL),
    )
    with engine.connect() as conn:
        stored_hash = conn.execute(
            text("SELECT inputs_hash FROM match_run WHERE job_id = :job"), {"job": job_id}
        ).scalar_one()

    assert stored_hash == expected


def test_two_runs_of_the_same_problem_share_an_inputs_hash(session_factory, tenant_id, engine):
    """What the column is for: two runs are comparable, or they are not.

    Two separate commands, two separate rows, one digest — because the problem
    posed was the same. This is the property a scenario comparison rests on.
    """
    first = _accept(session_factory, tenant_id, _payload())
    _run(session_factory, tenant_id, first)
    second = _accept(session_factory, tenant_id, _payload())
    _run(session_factory, tenant_id, second)

    with engine.connect() as conn:
        digests = {
            row.inputs_hash
            for row in conn.execute(
                text("SELECT inputs_hash FROM match_run WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            )
        }
    assert len(digests) == 1


def test_a_different_seed_is_a_different_inputs_hash(session_factory, tenant_id, engine):
    """Determinism is "identical inputs *and seed*", so the seed is an input."""
    first = _accept(session_factory, tenant_id, _payload())
    _run(session_factory, tenant_id, first)
    second = _accept(session_factory, tenant_id, _payload(random_seed=11))
    _run(session_factory, tenant_id, second)

    with engine.connect() as conn:
        digests = {
            row.inputs_hash
            for row in conn.execute(
                text("SELECT inputs_hash FROM match_run WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            )
        }
    assert len(digests) == 2


def test_the_run_is_scoped_to_the_unit_that_owns_the_job(session_factory, tenant_id, engine):
    """The authorization input comes from the job row, never from the payload.

    A caller who could name the unit in the body would be naming the subtree
    their own run is filed under, and therefore who may later read it. The
    payload here carries a ``unit_id`` that is nobody's real unit, and the
    stored row must ignore it.
    """
    with engine.begin() as conn:
        expected_unit = ensure_owning_unit(conn, tenant_id)

    job_id = _accept(session_factory, tenant_id, _payload(unit_id=str(uuid.uuid4())))
    _run(session_factory, tenant_id, job_id)

    with engine.connect() as conn:
        stored_unit = conn.execute(
            text("SELECT owning_unit_id FROM match_run WHERE job_id = :job"), {"job": job_id}
        ).scalar_one()

    assert stored_unit == expected_unit


def test_the_terminal_event_names_the_run_and_its_pins(session_factory, tenant_id, engine):
    """What a client following the job actually sees.

    The summary carries the run id and every pin, and a *count* of selected
    candidates rather than their ids: the shortlist is card M10's surface, and a
    job event is not a channel any policy row authorizes it to travel through.
    """
    job_id = _accept(session_factory, tenant_id, _payload())
    _run(session_factory, tenant_id, job_id)

    completed = _terminal_event(session_factory, tenant_id, job_id)
    assert completed["type"] == "job.completed"
    assert completed["state"] == JobState.SUCCEEDED.value

    summary = completed["summary"]
    # No mode on the payload, so the run is pre-ADR-0016 and says so. The
    # summary is also where a client following the job reads the mode, since
    # `match_run` has no column for it (OQ-CBA-028).
    assert summary["registry_version"] == SUPERSEDED_REGISTRY_VERSION
    assert summary["scoring_mode"] is None
    assert summary["scoring_mode_version"] is None
    assert summary["route_estimate_source"] == "straight_line"
    assert summary["candidates_considered"] == len(POOL)
    assert summary["selected_count"] == PORTFOLIO_SIZE
    assert summary["already_recorded"] is False
    assert "selected_subject_ids" not in summary

    with engine.connect() as conn:
        stored_id = conn.execute(
            text("SELECT id FROM match_run WHERE job_id = :job"), {"job": job_id}
        ).scalar_one()
    assert summary["match_run_id"] == str(stored_id)


# ---------------------------------------------------------------------------
# Re-execution
# ---------------------------------------------------------------------------


def test_a_second_execution_records_nothing_new_and_says_so(session_factory, tenant_id, engine):
    """At-least-once delivery is the normal case, not the anomaly.

    A worker can die after this handler's write commits and before the
    executor's terminal transition does; the operator's fix is a re-drive of the
    identical payload. One run means one row, and the summary distinguishes the
    replay so a coordinator is not told a second run happened.
    """
    job_id = _accept(session_factory, tenant_id, _payload())
    _run(session_factory, tenant_id, job_id)

    with engine.connect() as conn:
        first_id = conn.execute(
            text("SELECT id FROM match_run WHERE job_id = :job"), {"job": job_id}
        ).scalar_one()

    # Put the job back in a state the executor will claim, the way a re-drive
    # does, and execute the identical payload again.
    with engine.begin() as conn:
        conn.execute(text("UPDATE job SET status = 'dispatched' WHERE id = :id"), {"id": job_id})
    outcome = TaskExecutor(session_factory, default_registry()).execute(
        tenant_id=tenant_id, job_id=job_id
    )

    assert outcome.state is JobState.SUCCEEDED
    summary = _terminal_event(session_factory, tenant_id, job_id)["summary"]
    assert summary["already_recorded"] is True
    assert summary["match_run_id"] == str(first_id)

    with engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM match_run WHERE job_id = :job"), {"job": job_id}
            ).scalar_one()
            == 1
        )


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_a_job_with_no_payload_fails_rather_than_recording_an_invented_run(
    session_factory, tenant_id, engine
):
    """NULL is not an empty command.

    A job accepted before ``0005`` carries no payload, and its parameters are
    gone — the idempotency fingerprint is a one-way hash. Recording a run
    against invented inputs would be a reproducible-looking record of nothing.
    """
    job_id = _accept(session_factory, tenant_id, None)
    outcome = _run(session_factory, tenant_id, job_id)

    assert outcome.state is JobState.FAILED_POLICY
    with engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM match_run WHERE job_id = :job"), {"job": job_id}
            ).scalar_one()
            == 0
        )


def test_an_unreadable_payload_fails_terminally_and_writes_nothing(
    session_factory, tenant_id, engine
):
    """``failed_policy``, not ``failed_provider``: a re-drive re-reads the same bytes.

    Labelling this re-drivable would invite an operator to press a button that
    cannot work.
    """
    job_id = _accept(session_factory, tenant_id, _payload(candidates=[]))
    outcome = _run(session_factory, tenant_id, job_id)

    assert outcome.state is JobState.FAILED_POLICY
    with engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM match_run WHERE job_id = :job"), {"job": job_id}
            ).scalar_one()
            == 0
        )
