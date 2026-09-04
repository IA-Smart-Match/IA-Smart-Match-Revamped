"""HTTP contracts for the match-run command resource and its read (card M8b).

``tests/authz/test_policy_matrix.py`` owns the full authorization rectangle for
both operations and needs no database to run it.
``tests/integration/test_match_run_command_path.py`` owns the worker half — that
executing the command writes exactly one immutable, version-pinned snapshot.
What this file adds is the part that only exists over HTTP, and it drives the
whole path rather than any piece of it in isolation: a coordinator submits
evidence, the real dispatcher and the real executor run the shipped handler,
and the coordinator reads back a shortlist.

Three things are asserted that nothing else can assert:

* **The write goes through the command path.** After a ``202`` and before the
  worker runs, there is no ``match_run`` row — only a job. A route that inserted
  one directly would pass every other test in this repository.
* **The shortlist obeys the ratified presentation rules.** 2-3 speakers, the
  label "heuristic score", the registry version on every score, and no
  percentage anywhere in the response body.
* **Unknown survives the whole round trip.** A candidate with no coordinates is
  reported as unscorable with ``state="unknown"`` and a null score — over HTTP,
  after a database round trip, in the JSON a browser would parse. ADR-0011 is
  only worth anything if it holds at that last boundary.

Requires a live migrated PostgreSQL, and is skipped when none is reachable.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_domain.explanation import (
    MAX_SHORTLIST_SIZE,
    MIN_SHORTLIST_SIZE,
    SCORE_PROVENANCE_LABEL,
)
from smartmatch_domain.factor_registry import REGISTRY_VERSION
from smartmatch_domain.match_run import MATCH_RUN_COMMAND_TYPE
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import FixtureTokenVerifier
from smartmatch_providers.tasks import FixtureTaskQueue
from smartmatch_worker.dispatcher import OutboxDispatcher
from smartmatch_worker.execution import TaskExecutor
from smartmatch_worker.handlers import default_registry
from sqlalchemy import Engine, create_engine, text

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

UNIT_PATH = "iawest.matching"
#: A second department in the same tenant containing none of :data:`UNIT_PATH`.
#: Neither operation passes ``tenant_wide_roles``, so ordinary subtree
#: containment applies and a coordinator here must not reach the matching unit.
SIBLING_UNIT_PATH = "iawest.matchingsibling"

NEED = "need-synthetic-analytics"
REQUIRED_TOPICS = ["analytics", "ethics"]

#: Synthetic coordinates. Close enough together that travel burden is a
#: measured value rather than a saturated one, so the responses below exercise
#: real arithmetic rather than a clamp.
EVENT_LOCATION = {"latitude": 34.05, "longitude": -118.25}
NEARBY = {"latitude": 34.06, "longitude": -118.26}
FURTHER = {"latitude": 34.30, "longitude": -118.55}


def _candidate(subject: str, topics: list[str] | None, location: dict[str, float] | None) -> dict:
    """One submitted candidate. ``topics=None`` means no expertise record."""
    return {"subject_id": subject, "expertise_topics": topics, "location": location}


#: Three candidates with complete evidence and one with none. The last is the
#: point of the fixture: it must come back reported and unscored, never at zero.
POOL = [
    _candidate("prof-alpha", ["analytics", "ethics"], NEARBY),
    _candidate("prof-beta", ["analytics"], NEARBY),
    _candidate("prof-gamma", ["analytics", "ethics"], FURTHER),
    _candidate("prof-delta", ["analytics", "ethics"], None),
]


def _submission(**overrides) -> dict:
    body = {
        "event_need_id": NEED,
        "required_topics": REQUIRED_TOPICS,
        "preferred_topics": [],
        "event_location": EVENT_LOCATION,
        "portfolio_size": MIN_SHORTLIST_SIZE,
        "random_seed": 0,
        "candidates": POOL,
    }
    body.update(overrides)
    return body


@pytest.fixture(scope="module")
def engine() -> Engine:
    """A live migrated PostgreSQL engine, or skip this contract."""
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1 FROM match_run LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}")
    return eng


@pytest.fixture
def match_context(engine: Engine) -> Iterator[tuple[TestClient, uuid.UUID, str, uuid.UUID]]:
    """One tenant, one authorized coordinator, and one sibling department."""
    tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()
    sibling_unit_id = uuid.uuid4()
    user_id = uuid.uuid4()
    # Derived at runtime rather than written as literals: a fixture credential
    # spelled out in a source file is a credential in a commit patch.
    subject = f"sub-matching-{uuid.uuid4().hex}"
    token = f"tok-matching-{uuid.uuid4().hex}"

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-matching-{tenant_id.hex[:12]}"},
        )
        for new_unit_id, path, name in (
            (unit_id, UNIT_PATH, "Matching"),
            (sibling_unit_id, SIBLING_UNIT_PATH, "Sibling"),
        ):
            conn.execute(
                text(
                    "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                    "VALUES (:id, :tid, CAST(:path AS ltree), 'department', :name)"
                ),
                {"id": new_unit_id, "tid": tenant_id, "path": path, "name": name},
            )
        conn.execute(
            text(
                "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                "VALUES (:id, :tid, :subject, :email)"
            ),
            {
                "id": user_id,
                "tid": tenant_id,
                "subject": subject,
                "email": f"{subject}@example.edu",
            },
        )
        conn.execute(
            text(
                "INSERT INTO membership (id, tenant_id, user_id, granted_path, role) "
                "VALUES (:id, :tid, :uid, CAST(:path AS ltree), 'coordinator')"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "uid": user_id, "path": UNIT_PATH},
        )

    verifier = FixtureTokenVerifier()
    verifier.register(token, subject)
    client = TestClient(app)
    client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    client.app.state.token_verifier = verifier

    yield client, unit_id, token, tenant_id

    with engine.begin() as conn:
        # `match_run` before `job`: `match_run.job_id` is a NOT NULL foreign key
        # to `job`, so removing the job first is a constraint violation. The
        # same ordering `tests/integration/conftest.py` adopted when migration
        # 0018 landed.
        for table in (
            "job_event",
            "outbox_record",
            "redrive_record",
            "match_run",
            "job",
            "membership",
            "resource_grant",
            "user_account",
            "org_unit",
            "idempotency_record",
            "rate_limit_counter",
        ):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tenant_id})


def _post(client: TestClient, unit_id, token, body: dict, *, key: str | None = None):
    headers = {"Idempotency-Key": key or f"idem-{uuid.uuid4().hex}"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return client.post(f"/v1/units/{unit_id}/match-runs", json=body, headers=headers)


def _get(client: TestClient, path: str, token: str | None):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return client.get(path, headers=headers)


def _execute_pending(engine: Engine, tenant_id: uuid.UUID, job_id: uuid.UUID):
    """Dispatch and execute the accepted command with the shipped registry."""
    session_factory = create_session_factory(engine.url.render_as_string(hide_password=False))
    OutboxDispatcher(session_factory, FixtureTaskQueue()).run_once()
    return TaskExecutor(session_factory, default_registry()).execute(
        tenant_id=tenant_id, job_id=job_id
    )


def _run_id(engine: Engine, job_id: uuid.UUID) -> uuid.UUID:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT id FROM match_run WHERE job_id = :job"), {"job": job_id}
        ).scalar_one()


def _submit_and_execute(match_context, engine, body: dict | None = None):
    """The whole path: submit, run the worker, and return the read response."""
    client, unit_id, token, tenant_id = match_context

    accepted = _post(client, unit_id, token, body or _submission())
    assert accepted.status_code == 202, accepted.text
    job_id = uuid.UUID(accepted.json()["job_id"])

    outcome = _execute_pending(engine, tenant_id, job_id)
    assert outcome.status == "executed", outcome

    run_id = _run_id(engine, job_id)
    read = _get(client, f"/v1/units/{unit_id}/match-runs/{run_id}", token)
    assert read.status_code == 200, read.text
    return accepted.json(), read.json()


# ---------------------------------------------------------------------------
# The write is a command, not an insert
# ---------------------------------------------------------------------------


def test_a_submission_is_accepted_as_a_command_and_writes_no_run_of_its_own(
    match_context, engine
) -> None:
    """202, a job, an outbox row — and no snapshot until the worker runs.

    This is the property the module docstring calls the point of the whole
    design. A route that inserted a ``match_run`` directly would satisfy every
    read test in this file and still be wrong: the snapshot would exist with no
    durable command behind it, outside the transactional-outbox guarantee that
    business work is atomic with its terminal outcome.
    """
    client, unit_id, token, tenant_id = match_context

    response = _post(client, unit_id, token, _submission())

    assert response.status_code == 202
    body = response.json()
    job_id = uuid.UUID(body["job_id"])
    assert body["events_url"] == f"/v1/jobs/{job_id}/events"
    assert body["replayed"] is False

    with engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT command_type FROM job WHERE id = :job"), {"job": job_id}
            ).scalar_one()
            == MATCH_RUN_COMMAND_TYPE
        )
        assert (
            conn.execute(
                text("SELECT count(*) FROM outbox_record WHERE job_id = :job"), {"job": job_id}
            ).scalar_one()
            == 1
        )
        assert (
            conn.execute(
                text("SELECT count(*) FROM match_run WHERE tenant_id = :tid"), {"tid": tenant_id}
            ).scalar_one()
            == 0
        ), "the route wrote a snapshot itself instead of enqueuing the command"


def test_the_submission_reports_which_candidates_could_be_scored(match_context) -> None:
    """Three of four had complete evidence. The fourth is counted, not dropped.

    A caller handed a job id and nothing else could not tell a pool of four that
    scored four from one that scored three, and the difference is exactly the
    ADR-0011 case.
    """
    client, unit_id, token, _ = match_context

    body = _post(client, unit_id, token, _submission()).json()

    assert body["scored_candidates"] == 3
    assert body["unscorable_candidates"] == 1
    assert body["registry_version"] == REGISTRY_VERSION
    assert body["score_label"] == SCORE_PROVENANCE_LABEL


def test_a_repeated_submission_under_one_key_is_a_replay_not_a_second_run(match_context) -> None:
    """Idempotency holds for this command as it does for every other."""
    client, unit_id, token, _ = match_context
    key = f"idem-{uuid.uuid4().hex}"

    first = _post(client, unit_id, token, _submission(), key=key).json()
    second = _post(client, unit_id, token, _submission(), key=key).json()

    assert second["job_id"] == first["job_id"]
    assert second["replayed"] is True


def test_a_submission_that_cannot_fill_an_honest_shortlist_is_refused(match_context) -> None:
    """Unknown evidence is never padded out with zeros to reach the size.

    One candidate has no coordinates and one has no expertise record, so only
    one candidate can be scored and a shortlist of two is unfillable. The
    refusal says so rather than shipping a shortlist with a fabricated member.
    """
    client, unit_id, token, _ = match_context

    response = _post(
        client,
        unit_id,
        token,
        _submission(
            candidates=[
                _candidate("prof-alpha", ["analytics", "ethics"], NEARBY),
                _candidate("prof-beta", ["analytics"], None),
                _candidate("prof-gamma", None, NEARBY),
            ]
        ),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "match_run_insufficient_scorable_candidates"


def test_a_shortlist_outside_the_ratified_bounds_is_refused(match_context) -> None:
    """ "Return 2-3 speakers" is enforced on the request, not at render time."""
    client, unit_id, token, _ = match_context

    too_many = _post(client, unit_id, token, _submission(portfolio_size=MAX_SHORTLIST_SIZE + 1))
    too_few = _post(client, unit_id, token, _submission(portfolio_size=MIN_SHORTLIST_SIZE - 1))

    assert too_many.status_code == 422
    assert too_few.status_code == 422


# ---------------------------------------------------------------------------
# Authorization is reached before anything is read or written
# ---------------------------------------------------------------------------


def test_an_unauthenticated_submission_is_refused(match_context) -> None:
    client, unit_id, _, _ = match_context

    assert _post(client, unit_id, None, _submission()).status_code == 401


def test_a_unit_in_another_tenant_is_a_404_rather_than_a_403(match_context) -> None:
    """A 403 would confirm that the id names something real."""
    client, _, token, _ = match_context

    response = _post(client, uuid.uuid4(), token, _submission())

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unit_not_found"


def test_reading_a_run_that_does_not_exist_is_a_404(match_context) -> None:
    client, unit_id, token, _ = match_context

    response = _get(client, f"/v1/units/{unit_id}/match-runs/{uuid.uuid4()}", token)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "match_run_not_found"


# ---------------------------------------------------------------------------
# The read: shortlist, explanations, and the presentation rules
# ---------------------------------------------------------------------------


def test_the_read_returns_the_shortlist_the_worker_actually_solved(match_context, engine) -> None:
    """End to end: submit, execute, read, and get names back.

    The shortlist is reconstructed from the recorded inputs and is reported
    available only when that reconstruction fingerprints to the snapshot's own
    ``inputs_hash`` and re-solves to its recorded status — so a green assertion
    here is a statement that the read agrees with the write, not merely that it
    returned something.
    """
    _, run = _submit_and_execute(match_context, engine)

    assert run["shortlist_available"] is True
    assert run["shortlist_unavailable_reason"] is None
    assert MIN_SHORTLIST_SIZE <= len(run["shortlist"]) <= MAX_SHORTLIST_SIZE
    assert run["portfolio_status"] in {"optimal", "feasible"}
    # The pool was built so the best-evidenced candidate wins: alpha covers
    # every required topic from nearby, beta covers half from nearby, and gamma
    # covers every topic but from further away.
    assert "prof-alpha" in {entry["subject_id"] for entry in run["shortlist"]}


def test_every_score_on_the_read_carries_its_label_and_its_registry_version(
    match_context, engine
) -> None:
    """The two facts the G1 worksheet requires beside every displayed score."""
    _, run = _submit_and_execute(match_context, engine)

    assert run["score_label"] == SCORE_PROVENANCE_LABEL == "heuristic score"
    assert run["registry_version"] == REGISTRY_VERSION

    scored = run["shortlist"] + run["considered"] + run["unscorable"]
    assert scored, "the read returned no candidates at all"
    for entry in scored:
        assert entry["score_label"] == SCORE_PROVENANCE_LABEL
        assert entry["registry_version"] == REGISTRY_VERSION


def test_the_read_reports_the_pins_the_snapshot_recorded(match_context, engine) -> None:
    """Versions come off the stored row, never off today's registry.

    A run recorded under an earlier registry must keep saying so — that is what
    pinning is for — so these are read back rather than recomputed.
    """
    _, run = _submit_and_execute(match_context, engine)

    assert run["registry_hash"].startswith("sha256:")
    assert run["inputs_hash"].startswith("sha256:")
    assert run["route_estimate_source"] == "straight_line"
    assert run["solver_name"]
    assert run["solver_version"]
    assert run["optimizer_model_version"]
    assert set(run["weights"]) == {"topic_relevance", "travel_burden"}
    assert abs(sum(run["weights"].values()) - 1.0) < 1e-9


def test_a_candidate_with_absent_evidence_is_reported_unscored_and_never_at_zero(
    match_context, engine
) -> None:
    """ADR-0011 at the last boundary: the JSON a browser would parse.

    ``prof-delta`` has full expertise and no coordinates. The honest report is a
    null score with ``state="unknown"`` and the unknown factor named — not a
    zero that would place them below every measured candidate as though they had
    been measured and found wanting.
    """
    _, run = _submit_and_execute(match_context, engine)

    unscorable = {entry["subject_id"]: entry for entry in run["unscorable"]}
    assert set(unscorable) == {"prof-delta"}

    delta = unscorable["prof-delta"]
    assert delta["state"] == "unknown"
    assert delta["heuristic_score"] is None
    assert delta["unknown_factor_keys"] == ["travel_burden"]

    factors = {factor["factor_key"]: factor for factor in delta["factors"]}
    travel = factors["travel_burden"]
    assert travel["state"] == "unknown"
    assert travel["value"] is None
    assert travel["zero_classification"] == "unknown"
    assert travel["basis"]

    # The measured factor is still reported with its value: an unknown
    # composite does not erase the evidence that *was* present.
    topic = factors["topic_relevance"]
    assert topic["state"] == "measured"
    assert topic["value"] == 1.0

    # And they are in neither the shortlist nor the scored non-selected.
    assert "prof-delta" not in {entry["subject_id"] for entry in run["shortlist"]}
    assert "prof-delta" not in {entry["subject_id"] for entry in run["considered"]}


def test_a_measured_zero_is_reported_as_a_measured_zero(match_context, engine) -> None:
    """The other half of ADR-0011, over HTTP.

    A recorded but disjoint expertise tuple is a genuine, showable zero: the
    value is present, the state says it was measured, and
    ``zero_classification`` says which kind of zero it is. This is the case the
    worksheet marks "Show 0% with source" — the source being ``basis``.
    """
    body = _submission(
        candidates=[
            _candidate("prof-alpha", ["analytics", "ethics"], NEARBY),
            _candidate("prof-beta", ["analytics"], NEARBY),
            _candidate("prof-zero", ["basket weaving"], NEARBY),
        ]
    )
    _, run = _submit_and_execute(match_context, engine, body)

    everyone = {
        entry["subject_id"]: entry
        for entry in run["shortlist"] + run["considered"] + run["unscorable"]
    }
    zero = everyone["prof-zero"]

    assert zero["state"] == "measured"
    assert zero["heuristic_score"] is not None
    topic = next(f for f in zero["factors"] if f["factor_key"] == "topic_relevance")
    assert topic["state"] == "measured"
    assert topic["value"] == 0.0
    assert topic["zero_classification"] == "measured_zero"
    assert topic["basis"], "a measured zero must carry the source that measured it"


def test_no_percentage_appears_anywhere_in_the_response(match_context, engine) -> None:
    """The ratified rule, checked against the whole serialized body.

    Not "the fields we remembered to look at" — the entire JSON document. Every
    number that reaches a coordinator is in the unit interval and no string
    formats one as a percentage, so there is no percentage for a surface to
    render even by accident.
    """
    _, run = _submit_and_execute(match_context, engine)

    rendered = json.dumps(run)
    assert "%" not in rendered
    assert "percent" not in rendered.lower()

    for entry in run["shortlist"] + run["considered"] + run["unscorable"]:
        if entry["heuristic_score"] is not None:
            assert 0.0 <= entry["heuristic_score"] <= 1.0
        for factor in entry["factors"]:
            assert factor["value"] is None or 0.0 <= factor["value"] <= 1.0
