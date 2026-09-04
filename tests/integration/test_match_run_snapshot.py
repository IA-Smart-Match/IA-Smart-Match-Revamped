"""What migration ``0018``'s ``match_run`` refuses, against a real PostgreSQL instance.

Card M8a's word is "immutable", and immutability is not a thing a code review
can establish: the guarantee has to hold against a hand-written ``UPDATE`` in a
psql session, not only against a repository that declines to offer one. So the
tests here attempt the forbidden write and require the database to refuse it.

The constraint tests deliberately do **not** go through
:class:`~smartmatch_persistence.match_runs.MatchRunRepository`. That module and
:class:`~smartmatch_domain.match_run.MatchRunPins` guard the same rules in
application code, and a test that went through them would prove the guard
rather than the constraint. The repository's own behaviour — idempotency under
re-drive, and what it actually stores — is tested at the bottom of this file,
where going through it is the point.

Requires a live database, and is skipped when none is reachable.
"""

from __future__ import annotations

import uuid

import pytest

pytest.importorskip("sqlalchemy")

from conftest import ensure_owning_unit
from smartmatch_domain.match_run import MatchRunPins, inputs_fingerprint, weights_fingerprint
from smartmatch_persistence.match_runs import MatchRunRepository
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

NEED = "need-synthetic-1"
POOL_SUBJECTS = ("prof-synthetic-a", "prof-synthetic-b")
POOL_UTILITIES = (0.82, 0.4)
WEIGHTS = {"topic_relevance": 0.6, "travel_burden": 0.4}


def _inputs_hash() -> str:
    """Derived at runtime, never a committed literal."""
    return inputs_fingerprint(
        event_need_id=NEED,
        candidate_subject_ids=POOL_SUBJECTS,
        candidate_utilities=POOL_UTILITIES,
        portfolio_size=1,
        random_seed=0,
        weights=WEIGHTS,
    )


def _pins() -> MatchRunPins:
    return MatchRunPins(
        registry_version="1.1.1-approved-g1-m6j",
        registry_hash=weights_fingerprint(WEIGHTS),
        optimizer_model_version="1.0.0-cpsat",
        solver_name="ortools-cpsat",
        solver_version="9.99.0",
        route_estimate_source="straight_line",
        route_estimate_version="1.0.0-straight-line",
    )


def _insert_job(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    """Insert one queued ``match-run.create`` job in the tenant's job-owning unit."""
    identifier = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO job (id, tenant_id, command_type, status, owning_unit_id) "
            "VALUES (:id, :tid, 'match-run.create', 'queued', :unit)"
        ),
        {"id": identifier, "tid": tenant_id, "unit": ensure_owning_unit(conn, tenant_id)},
    )
    return identifier


@pytest.fixture
def job_id(engine: Engine, tenant_id) -> uuid.UUID:
    """A job for the run to hang off.

    ``match_run.job_id`` is ``NOT NULL`` with a foreign key, so a run cannot be
    written without one. That is the schema half of "no route-side insert": a
    row cannot exist unless a durable command exists first.
    """
    with engine.begin() as conn:
        return _insert_job(conn, tenant_id)


def _insert_run(
    conn,
    tenant_id: uuid.UUID,
    job_id: uuid.UUID,
    *,
    run_id: uuid.UUID | None = None,
    event_need_id: str = NEED,
    inputs_hash: str | None = None,
    portfolio_size: int = 1,
    random_seed: int = 0,
    registry_version: str = "1.1.1-approved-g1-m6j",
    registry_hash: str | None = None,
    weights: str = '{"topic_relevance": 0.6, "travel_burden": 0.4}',
    optimizer_model_version: str = "1.0.0-cpsat",
    solver_name: str = "ortools-cpsat",
    solver_version: str = "9.99.0",
    route_estimate_source: str = "straight_line",
    route_estimate_version: str = "1.0.0-straight-line",
    portfolio_status: str = "optimal",
    supersedes_run_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert one run, defaulting everything the test under way is not about.

    Every value the constraints accept is a keyword with a valid default, so a
    test body contains only the value in question — the shape
    ``test_event_schema_constraints.py`` uses, for the same reason.
    """
    identifier = run_id or uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO match_run (id, tenant_id, owning_unit_id, job_id, event_need_id, "
            "inputs_hash, portfolio_size, random_seed, registry_version, registry_hash, "
            "weights, optimizer_model_version, solver_name, solver_version, "
            "route_estimate_source, route_estimate_version, portfolio_status, "
            "supersedes_run_id) "
            "VALUES (:id, :tid, :unit, :job, :need, :inputs_hash, :size, :seed, "
            ":registry_version, :registry_hash, CAST(:weights AS jsonb), :model, :solver, "
            ":solver_version, :route_source, :route_version, :status, :supersedes)"
        ),
        {
            "id": identifier,
            "tid": tenant_id,
            "unit": ensure_owning_unit(conn, tenant_id),
            "job": job_id,
            "need": event_need_id,
            "inputs_hash": inputs_hash if inputs_hash is not None else _inputs_hash(),
            "size": portfolio_size,
            "seed": random_seed,
            "registry_version": registry_version,
            "registry_hash": (
                registry_hash if registry_hash is not None else weights_fingerprint(WEIGHTS)
            ),
            "weights": weights,
            "model": optimizer_model_version,
            "solver": solver_name,
            "solver_version": solver_version,
            "route_source": route_estimate_source,
            "route_version": route_estimate_version,
            "status": portfolio_status,
            "supersedes": supersedes_run_id,
        },
    )
    return identifier


# ---------------------------------------------------------------------------
# A valid row, so the rest of this file is testing constraints and not typos
# ---------------------------------------------------------------------------


def test_a_well_formed_run_is_accepted(engine, tenant_id, job_id):
    with engine.begin() as conn:
        run_id = _insert_run(conn, tenant_id, job_id)
        stored = conn.execute(
            text("SELECT created_at, supersedes_run_id FROM match_run WHERE id = :id"),
            {"id": run_id},
        ).one()
    # created_at is defaulted by the database, not supplied by the writer, so a
    # row cannot claim a time no clock produced.
    assert stored.created_at is not None
    assert stored.supersedes_run_id is None


def test_the_table_carries_no_updated_at_column(engine):
    """Deliberate absence: carrying one would say mutation is expected here."""
    with engine.connect() as conn:
        columns = {
            row.column_name
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'match_run'"
                )
            )
        }
    assert "updated_at" not in columns
    assert "created_at" in columns


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


def test_updating_a_stored_run_is_refused(engine, tenant_id, job_id):
    """The card's word is "immutable", and this is what makes it true in the database.

    A CHECK constraint cannot express this: it sees the new row and has no way
    to know one existed before. The trigger is why a hand-written UPDATE in a
    psql session fails rather than quietly rewriting history.
    """
    with engine.begin() as conn:
        run_id = _insert_run(conn, tenant_id, job_id)

    with pytest.raises(IntegrityError, match="immutable"), engine.begin() as conn:
        conn.execute(
            text("UPDATE match_run SET registry_version = '9.9.9' WHERE id = :id"),
            {"id": run_id},
        )


def test_the_refusal_is_loud_and_the_row_is_unchanged(engine, tenant_id, job_id):
    """A rule that discarded the UPDATE silently would be worse than none.

    ``CREATE RULE ... DO INSTEAD NOTHING`` was the alternative, and it would
    leave a writer believing it had corrected a run. The row is read back here
    to prove the refusal was not merely raised but also effective.
    """
    with engine.begin() as conn:
        run_id = _insert_run(conn, tenant_id, job_id, portfolio_status="optimal")

    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            text("UPDATE match_run SET portfolio_status = 'infeasible' WHERE id = :id"),
            {"id": run_id},
        )

    with engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT portfolio_status FROM match_run WHERE id = :id"), {"id": run_id}
            ).scalar_one()
            == "optimal"
        )


def test_even_a_no_op_update_is_refused(engine, tenant_id, job_id):
    """Immutable means the statement is forbidden, not that the values must differ.

    An UPDATE that happened to write the same value is still an UPDATE, and
    admitting it would make the guarantee depend on what a writer chose to set
    rather than on what the table allows.
    """
    with engine.begin() as conn:
        run_id = _insert_run(conn, tenant_id, job_id, portfolio_status="optimal")

    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            text("UPDATE match_run SET portfolio_status = 'optimal' WHERE id = :id"),
            {"id": run_id},
        )


def test_a_correction_is_a_new_run_that_names_the_one_it_replaces(engine, tenant_id, job_id):
    """The shape immutability leaves available, and both rows survive it.

    The point is not only that the correction exists but that the superseded run
    is still readable: a coordinator who acted on the first result can find out
    what they were shown.
    """
    with engine.begin() as conn:
        original = _insert_run(conn, tenant_id, job_id)
        correction = _insert_run(
            conn, tenant_id, _insert_job(conn, tenant_id), supersedes_run_id=original
        )

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, supersedes_run_id FROM match_run WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        ).all()

    assert {row.id for row in rows} == {original, correction}
    assert {row.supersedes_run_id for row in rows} == {None, original}


def test_a_run_cannot_supersede_itself(engine, tenant_id, job_id):
    """The foreign key accepts a self-reference; this refuses the cycle of length one."""
    run_id = uuid.uuid4()
    with (
        pytest.raises(IntegrityError, match="ck_match_run_supersedes_is_not_self"),
        engine.begin() as conn,
    ):
        _insert_run(conn, tenant_id, job_id, run_id=run_id, supersedes_run_id=run_id)


# ---------------------------------------------------------------------------
# Pins, and what a blank one would mean
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "blank_field",
    [
        "event_need_id",
        "inputs_hash",
        "registry_version",
        "registry_hash",
        "optimizer_model_version",
        "solver_name",
        "solver_version",
        "route_estimate_version",
    ],
)
def test_a_blank_pin_is_refused(engine, tenant_id, job_id, blank_field):
    """NOT NULL accepts the empty string; ADR-0011 does not.

    A run pinned to ``''`` is a run nobody can reproduce, and it is
    indistinguishable from a writer that forgot the field. Whitespace is used
    rather than ``''`` because a writer that trimmed nothing would otherwise
    store a value that merely looks present.
    """
    with pytest.raises(IntegrityError, match="ck_match_run_pins_present"), engine.begin() as conn:
        _insert_run(conn, tenant_id, job_id, **{blank_field: "   "})


@pytest.mark.parametrize("weights", ["{}", "[]", "null", '"topic_relevance"', "3"])
def test_weights_must_be_a_non_empty_object(engine, tenant_id, job_id, weights):
    """A jsonb column accepts every JSON value; only one of them is a weight set.

    Storing ``{}`` or ``null`` would satisfy ``NOT NULL`` while recording
    nothing — a field that looks answered and is not, which is the shape Fix #15
    closed one table over.
    """
    with pytest.raises(IntegrityError, match="ck_match_run_weights_object"), engine.begin() as conn:
        _insert_run(conn, tenant_id, job_id, weights=weights)


def test_an_unrecognised_route_estimate_source_is_refused(engine, tenant_id, job_id):
    """The vocabulary is closed, so the day D3 lands the older rows still read honestly."""
    with (
        pytest.raises(IntegrityError, match="ck_match_run_route_estimate_source"),
        engine.begin() as conn,
    ):
        _insert_run(conn, tenant_id, job_id, route_estimate_source="a-provider-not-declared")


def test_an_unrecognised_portfolio_status_is_refused(engine, tenant_id, job_id):
    """'infeasible' and 'unknown' are different claims, and neither is a free-text field."""
    with (
        pytest.raises(IntegrityError, match="ck_match_run_portfolio_status"),
        engine.begin() as conn,
    ):
        _insert_run(conn, tenant_id, job_id, portfolio_status="no_result")


@pytest.mark.parametrize(
    ("field", "value", "constraint"),
    [
        ("portfolio_size", 0, "ck_match_run_portfolio_size"),
        ("portfolio_size", -1, "ck_match_run_portfolio_size"),
        ("random_seed", -1, "ck_match_run_random_seed"),
    ],
)
def test_out_of_range_numbers_are_refused(engine, tenant_id, job_id, field, value, constraint):
    with pytest.raises(IntegrityError, match=constraint), engine.begin() as conn:
        _insert_run(conn, tenant_id, job_id, **{field: value})


# ---------------------------------------------------------------------------
# Scoping
# ---------------------------------------------------------------------------


def test_one_snapshot_per_command(engine, tenant_id, job_id):
    """A re-drive must not be able to write a second row for the same run.

    Enforced by the database rather than by the writer noticing, because the
    writer cannot tell a first attempt from a second one — that is the whole
    difficulty a re-drive presents.
    """
    with engine.begin() as conn:
        _insert_run(conn, tenant_id, job_id)

    with pytest.raises(IntegrityError, match="uq_match_run_job"), engine.begin() as conn:
        _insert_run(conn, tenant_id, job_id)


def test_a_run_cannot_cite_another_tenants_job(engine, tenant_id, job_id):
    """The composite foreign key is the v1.1 §2.2 isolation guarantee, not belt and braces.

    A single-column key to ``job.id`` would accept this row, and the run would
    then be authorized against a unit in a tree its tenant has no relationship
    to.
    """
    other_tenant = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": other_tenant, "slug": f"test-{other_tenant.hex[:12]}"},
        )
    try:
        with pytest.raises(IntegrityError), engine.begin() as conn:
            # `job_id` belongs to `tenant_id`, and this row claims it for a
            # different tenant.
            _insert_run(conn, other_tenant, job_id)
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM org_unit WHERE tenant_id = :tid"), {"tid": other_tenant})
            conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": other_tenant})


def test_a_run_cannot_exist_without_a_job(engine, tenant_id):
    """The schema half of "written on the command path, never by a route".

    A route that inserted here directly would have no job to cite, and there is
    no way to invent one: ``job`` rows are written by ``submit_command``.
    """
    with pytest.raises(IntegrityError), engine.begin() as conn:
        _insert_run(conn, tenant_id, uuid.uuid4())


# ---------------------------------------------------------------------------
# The repository, where going through it is the point
# ---------------------------------------------------------------------------


def test_a_replayed_write_returns_the_first_runs_row(session_factory, tenant_id, job_id, engine):
    """A re-driven execution records nothing new and says so.

    The second call proposes a fresh id and gets the first one back. Returning a
    new id would make a re-drive look like a correction, and corrections are
    meant to be deliberate.
    """
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)

    repository = MatchRunRepository()
    arguments = {
        "tenant_id": tenant_id,
        "owning_unit_id": unit_id,
        "job_id": job_id,
        "event_need_id": NEED,
        "inputs_hash": _inputs_hash(),
        "portfolio_size": 1,
        "random_seed": 0,
        "weights": WEIGHTS,
        "pins": _pins(),
        "portfolio_status": "optimal",
    }

    with session_factory() as session:
        first = repository.record(session, **arguments)
        session.commit()

    with session_factory() as session:
        second = repository.record(session, **arguments)
        session.commit()

    assert first.was_already_recorded is False
    assert second.was_already_recorded is True
    assert second.id == first.id
    # The stored timestamp, not the retry's: a re-drive reports when the run
    # actually happened.
    assert second.created_at == first.created_at

    with engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM match_run WHERE tenant_id = :tid"), {"tid": tenant_id}
            ).scalar_one()
            == 1
        )


def test_the_repository_stores_every_pin_it_was_given(session_factory, tenant_id, job_id, engine):
    """The columns are only worth having if the writer actually fills them."""
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)

    pins = _pins()
    with session_factory() as session:
        record = MatchRunRepository().record(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            job_id=job_id,
            event_need_id=NEED,
            inputs_hash=_inputs_hash(),
            portfolio_size=1,
            random_seed=3,
            weights=WEIGHTS,
            pins=pins,
            portfolio_status="feasible",
        )
        session.commit()

    with engine.connect() as conn:
        stored = conn.execute(
            text("SELECT * FROM match_run WHERE id = :id"), {"id": record.id}
        ).one()

    assert stored.registry_version == pins.registry_version
    assert stored.registry_hash == pins.registry_hash
    assert stored.optimizer_model_version == pins.optimizer_model_version
    assert stored.solver_name == pins.solver_name
    assert stored.solver_version == pins.solver_version
    assert stored.route_estimate_source == pins.route_estimate_source
    assert stored.route_estimate_version == pins.route_estimate_version
    assert stored.portfolio_status == "feasible"
    assert stored.random_seed == 3
    assert stored.owning_unit_id == unit_id
    # Readable as well as hashed: a digest cannot answer "which weights were in
    # force", and that is a question a coordinator will ask.
    assert stored.weights == WEIGHTS


def test_the_repository_offers_no_way_to_update_a_run():
    """Code that does not exist cannot be called by accident.

    The database refuses an UPDATE regardless; this asserts the cheaper half of
    the same guarantee, so that adding an update method is a visible decision
    rather than something a future reader discovers from a trigger error.
    """
    methods = {name for name in dir(MatchRunRepository) if not name.startswith("_")}
    assert methods == {"record", "get"}


def test_a_run_is_only_readable_within_its_own_tenant(session_factory, tenant_id, job_id, engine):
    """`tenant_id` is part of the lookup, not a filter applied afterwards."""
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)

    repository = MatchRunRepository()
    with session_factory() as session:
        record = repository.record(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            job_id=job_id,
            event_need_id=NEED,
            inputs_hash=_inputs_hash(),
            portfolio_size=1,
            random_seed=0,
            weights=WEIGHTS,
            pins=_pins(),
            portfolio_status="optimal",
        )
        session.commit()

    with session_factory() as session:
        assert repository.get(session, tenant_id=tenant_id, run_id=record.id) is not None
        assert repository.get(session, tenant_id=uuid.uuid4(), run_id=record.id) is None
