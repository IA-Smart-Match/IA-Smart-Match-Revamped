"""HTTP contracts for the match-run command resource and its read (card M8b).

``tests/authz/test_policy_matrix.py`` owns the full authorization rectangle for
both operations and needs no database to run it.
``tests/integration/test_match_run_command_path.py`` owns the worker half — that
executing the command writes exactly one immutable, version-pinned snapshot.
What this file adds is the part that only exists over HTTP, and it drives the
whole path rather than any piece of it in isolation: a coordinator names a filed
Speaker Request and a list of speakers, the real dispatcher and the real
executor run the shipped handler, and the coordinator reads back a shortlist.

Five things are asserted that nothing else can assert:

* **A run reaches storage under registry 2.0.0.** OQ-CBA-031's whole point.
  ``match_run.registry_version`` is read out of the table — not off the response
  — and the durable command payload is read out of ``job.payload`` and required
  to carry ``scoring_mode = "cba-virtual-1"`` with a non-null
  ``scoring_mode_version``. The response is not evidence here: ``get_session``
  rolls back unconditionally, so a route that stored nothing would still return
  a perfectly clean ``202``.
* **The body carries no evidence.** There is no field on the request through
  which a caller could state a speaker's industry, role, topic text or place,
  and the published schema is asserted to have none.
* **A physical Speaker Request is scored, and an unlocatable speaker is not.**
  OQ-CBA-024's ZIP-centroid table removed the 503, so ``cba-physical-1`` runs
  end to end — and a speaker whose ZIP that table cannot resolve is reported
  unscorable rather than entered at zero and ranked last.
* **An unreviewed contact is absent, not last.** Track 16's gate holds over
  HTTP: the contact appears in ``excluded_candidates`` with its reason and in
  none of the three scored groups.
* **Unknown survives the whole round trip.** A speaker whose topic evidence
  cannot be compared is reported unscorable with ``state="unknown"`` and a null
  score — over HTTP, after a database round trip, in the JSON a browser would
  parse. ADR-0011 is only worth anything if it holds at that last boundary.

Requires a live migrated PostgreSQL, and is skipped when none is reachable.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_domain.cba_role_categories import CBA_ROLE_TAXONOMY_VERSION
from smartmatch_domain.explanation import (
    MAX_SHORTLIST_SIZE,
    MIN_SHORTLIST_SIZE,
    SCORE_PROVENANCE_LABEL,
)
from smartmatch_domain.factor_registry import (
    REGISTRY_VERSION,
    SCORING_MODE_VERSION,
    SUPERSEDED_REGISTRY_VERSION,
)
from smartmatch_domain.factors.cba_semantic_topic import CBA_SEMANTIC_TOPIC_FACTOR_KEY
from smartmatch_domain.factors.proximity import (
    CBA_PHYSICAL_SCORING_MODE,
    CBA_PROXIMITY_FACTOR_KEY,
    CBA_VIRTUAL_SCORING_MODE,
)
from smartmatch_domain.match_run import MATCH_RUN_COMMAND_TYPE, registry_fingerprint
from smartmatch_domain.naics_sectors import NAICS_TAXONOMY_VERSION
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import FixtureTokenVerifier
from smartmatch_providers.tasks import FixtureTaskQueue
from smartmatch_worker.dispatcher import OutboxDispatcher
from smartmatch_worker.execution import TaskExecutor
from smartmatch_worker.handlers import default_registry
from sqlalchemy import Engine, create_engine, event, text

from tests.unit.registry_evaluation import DOMAIN_MODULES, evaluate_registry_3

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

#: The Speaker Request's targets. One sector and one role, so a speaker either
#: matches or measurably does not — the two-valued factor customer §§7-8
#: describe, with no partial credit to reason about here.
REQUESTED_SECTOR = "52"
REQUESTED_ROLE = "finance"

REQUEST_DESCRIPTION = "A panel on how finance teams evaluate analytics investments."

#: The CPP campus's own ZIP, and therefore one OQ-CBA-024's Californian table
#: resolves. A speaker filed under it has a measured distance and can be scored
#: under ``cba-physical-1``.
CAMPUS_ZIP = "91768"

#: Well formed, five digits, and not in California, so the table does not name
#: it. The distance is **unknown** — not the Far band, and not a fallback to
#: some nearest neighbour, which is the whole of ADR-0016 Proposal 4.
OUT_OF_STATE_ZIP = "10001"


@pytest.fixture(scope="module")
def engine() -> Engine:
    """A live migrated PostgreSQL engine, or skip this contract."""
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1 FROM match_run LIMIT 1"))
            conn.execute(text("SELECT 1 FROM speaker_profile LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}")
    return eng


class MatchFixture:
    """One tenant's rows, and the ids the tests submit against.

    A small object rather than a five-tuple: this fixture grew from "a unit and
    a token" to "a unit, a token, two Speaker Requests and five speakers", and
    positional unpacking at a dozen call sites is where a test starts asserting
    against the wrong id without failing.
    """

    def __init__(
        self,
        client: TestClient,
        *,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        token: str,
        virtual_request_id: uuid.UUID,
        physical_request_id: uuid.UUID,
        speakers: dict[str, uuid.UUID],
        user_id: uuid.UUID | None = None,
        engine: Engine | None = None,
    ) -> None:
        self.client = client
        self.tenant_id = tenant_id
        self.unit_id = unit_id
        self.token = token
        self.virtual_request_id = virtual_request_id
        self.physical_request_id = physical_request_id
        self.speakers = speakers
        self.user_id = user_id
        self.engine = engine

    def state_availability(
        self,
        name: str,
        *,
        paused_until: date | None = None,
        windows: tuple[tuple[date, date], ...] = (),
    ) -> None:
        """Store (or replace) one speaker's availability statement (B26 T4)."""
        assert self.engine is not None and self.user_id is not None
        professional_id = self.speakers[name]
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "DELETE FROM speaker_availability WHERE tenant_id = :t AND professional_id = :p"
                ),
                {"t": self.tenant_id, "p": professional_id},
            )
            conn.execute(
                text(
                    "INSERT INTO speaker_availability (tenant_id, professional_id, "
                    "invitations_paused_until, updated_source, updated_by_user_id) "
                    "VALUES (:t, :p, :paused, 'connector', :u)"
                ),
                {
                    "t": self.tenant_id,
                    "p": professional_id,
                    "paused": paused_until,
                    "u": self.user_id,
                },
            )
            for starts_on, ends_on in windows:
                conn.execute(
                    text(
                        "INSERT INTO speaker_availability_window (id, tenant_id, professional_id, "
                        "starts_on, ends_on, created_source, created_by_user_id) "
                        "VALUES (:id, :t, :p, :s, :e, 'connector', :u)"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "t": self.tenant_id,
                        "p": professional_id,
                        "s": starts_on,
                        "e": ends_on,
                        "u": self.user_id,
                    },
                )

    def new_login(self) -> uuid.UUID:
        """A ``user_account`` in this tenant: a Host, or a Speaker's bound login."""
        assert self.engine is not None
        user_id = uuid.uuid4()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                    "VALUES (:id, :t, :s, :e)"
                ),
                {
                    "id": user_id,
                    "t": self.tenant_id,
                    "s": f"login-{user_id.hex}",
                    "e": f"login-{user_id.hex[:8]}@example.invalid",
                },
            )
        return user_id

    def bind_login(self, name: str, user_id: uuid.UUID) -> None:
        """Bind a login to a Speaker's profile (``0039``), as T6b-5's merge would."""
        assert self.engine is not None
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE speaker_profile SET account_user_id = :u, account_bound_at = now() "
                    "WHERE tenant_id = :t AND professional_id = :p"
                ),
                {"u": user_id, "t": self.tenant_id, "p": self.speakers[name]},
            )

    def file_request(self, filed_by_user_id: uuid.UUID | None) -> uuid.UUID:
        """A virtual Speaker Request filed by ``filed_by_user_id`` (``None``: unrecorded)."""
        assert self.engine is not None
        with self.engine.begin() as conn:
            return _insert_speaker_request(
                conn,
                tenant_id=self.tenant_id,
                unit_id=self.unit_id,
                is_virtual=True,
                title=f"Filed finance panel {uuid.uuid4().hex[:8]}",
                filed_by_user_id=filed_by_user_id,
            )

    def subject(self, *names: str) -> list[str]:
        """The ids for these speakers, as the request body spells them."""
        return [str(self.speakers[name]) for name in names]


def _insert_speaker_request(
    conn: Any,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    is_virtual: bool,
    title: str,
    filed_by_user_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """File one Speaker Request straight into ``event`` and its targets.

    Written through the database rather than through
    ``POST /v1/units/{unit_id}/speaker-requests`` on purpose: that route is
    another surface with its own contract file, and a failure in it would
    surface here as a match-run failure. The row still goes in through the
    shipped schema, so ``ck_event_provenance_evidence``,
    ``ck_event_temporal_shape`` and ``ck_event_virtual_has_no_location`` are
    enforced on it exactly as they would be on a row the application wrote.
    """
    event_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO event (id, tenant_id, host_org_unit_id, title, normalized_title, "
            "description, time_precision, on_date, time_zone, resolved_date, origin, "
            "is_virtual, filed_by_user_id) VALUES (:id, :tid, :unit, :title, :norm, :desc, "
            "'date_only', DATE '2027-03-04', 'America/Los_Angeles', DATE '2027-03-04', "
            "'coordinator_entry', :virtual, :filed)"
        ),
        {
            "id": event_id,
            "tid": tenant_id,
            "unit": unit_id,
            "title": title,
            "norm": title.lower(),
            "desc": REQUEST_DESCRIPTION,
            "virtual": is_virtual,
            "filed": filed_by_user_id,
        },
    )
    for kind, code, version in (
        ("industry", REQUESTED_SECTOR, NAICS_TAXONOMY_VERSION),
        ("role", REQUESTED_ROLE, CBA_ROLE_TAXONOMY_VERSION),
    ):
        conn.execute(
            text(
                "INSERT INTO speaker_request_classification "
                "(id, tenant_id, event_id, kind, code, taxonomy_version) "
                "VALUES (:id, :tid, :event, :kind, :code, :version)"
            ),
            {
                "id": uuid.uuid4(),
                "tid": tenant_id,
                "event": event_id,
                "kind": kind,
                "code": code,
                "version": version,
            },
        )
    return event_id


def _insert_speaker(
    conn: Any,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    name: str,
    industry_code: str | None,
    role_code: str | None,
    industry_source: str | None,
    role_source: str | None,
    topic_text: str | None,
    postal_code: str | None = None,
) -> uuid.UUID:
    """Create one professional and their ``speaker_profile`` row.

    ``professional_id`` is a fresh UUID, never derived from ``name``: OQ-CBA-017
    is re-keying that column to an opaque generated id, and a test that computed
    one from a display name would be asserting the property that decision
    removes.

    The provenance columns are set explicitly on every row, including the
    ``inferred`` case, because ``ck_speaker_profile_industry_provenance`` admits
    exactly three shapes per axis and a test that guessed at a fourth would fail
    on the insert rather than on the behaviour it means to check.
    """
    professional_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :tid, :subject, :email)"
        ),
        {
            "id": professional_id,
            "tid": tenant_id,
            "subject": f"speaker-{professional_id.hex}",
            "email": f"speaker-{professional_id.hex}@example.invalid",
        },
    )
    conn.execute(
        text(
            "INSERT INTO speaker_profile (tenant_id, professional_id, owning_unit_id, "
            "full_name, primary_industry_code, industry_taxonomy_version, "
            "primary_role_code, role_taxonomy_version, topic_text, "
            "location_postal_code, "
            "industry_classification_source, industry_classified_by_user_id, "
            "industry_classified_at, role_classification_source, "
            "role_classified_by_user_id, role_classified_at) "
            "VALUES (:tid, :pid, :unit, :full_name, :industry, :industry_version, "
            ":role, :role_version, :topic, :postal_code, "
            ":industry_source, :industry_actor, "
            ":industry_at, :role_source, :role_actor, :role_at)"
        ),
        {
            "tid": tenant_id,
            "pid": professional_id,
            "unit": unit_id,
            "full_name": name,
            "industry": industry_code,
            "industry_version": None if industry_code is None else NAICS_TAXONOMY_VERSION,
            "role": role_code,
            "role_version": None if role_code is None else CBA_ROLE_TAXONOMY_VERSION,
            "topic": topic_text,
            "postal_code": postal_code,
            "industry_source": industry_source,
            "industry_actor": reviewer_id if industry_source == "human" else None,
            "industry_at": None if industry_source is None else "2026-09-05T00:00:00Z",
            "role_source": role_source,
            "role_actor": reviewer_id if role_source == "human" else None,
            "role_at": None if role_source is None else "2026-09-05T00:00:00Z",
        },
    )
    return professional_id


@pytest.fixture
def match_context(engine: Engine) -> Iterator[MatchFixture]:
    """One tenant, one authorized coordinator, two Speaker Requests, five speakers.

    The five speakers are the whole point of the fixture, and each exists to make
    one distinction visible over HTTP:

    * ``alpha``   — reviewed, sector and role both match, **no topic text**. §9's
      observed absence, so its topic factor is ``policy_neutral`` rather than
      unknown and the candidate is shortlistable. This is the ordinary CBA
      contact today: imported, classified, reviewed, no topic sheet filled in.
    * ``beta``    — reviewed, sector matches, role does not. A measured zero on
      one factor, which is a real score and not an absence.
    * ``gamma``   — reviewed, role matches, sector does not.
    * ``delta``   — reviewed, both match, **has topic text**. The fixture topic
      provider holds no recording for that pair, so the comparison is an
      *unknown* rather than a guess (OQ-CBA-026), and the candidate is
      unscorable. Uncomfortable and correct: it is what "no approved semantic
      model exists" actually looks like at the surface.
    * ``epsilon`` — sector and role present but ``inferred``. Track 16's gate:
      a proposal awaiting the review customer §19 orders, so absent from the
      pool entirely.
    * ``zeta``    — identical to ``alpha`` in every respect except one: their
      ZIP is not Californian, so OQ-CBA-024's table cannot resolve it. Under
      ``cba-physical-1`` that makes their proximity *unknown* and them
      unscorable, and the single-variable difference from ``alpha`` is what
      makes the cause unambiguous. Under ``cba-virtual-1`` they score normally,
      because §11 removes proximity from that model entirely.

    Every speaker carries a postal code, because the physical model needs one
    to resolve and a fixture where nobody had an address could only ever
    exercise the unknown branch.
    """
    tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()
    sibling_unit_id = uuid.uuid4()
    user_id = uuid.uuid4()
    # Derived at runtime rather than written as literals: a fixture credential
    # spelled out in a source file is a credential in a commit patch.
    subject = f"sub-matching-{uuid.uuid4().hex}"
    token = f"tok-matching-{uuid.uuid4().hex}"

    speakers: dict[str, uuid.UUID] = {}

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

        virtual_request_id = _insert_speaker_request(
            conn,
            tenant_id=tenant_id,
            unit_id=unit_id,
            is_virtual=True,
            title=f"Virtual finance analytics panel {uuid.uuid4().hex[:8]}",
        )
        physical_request_id = _insert_speaker_request(
            conn,
            tenant_id=tenant_id,
            unit_id=unit_id,
            is_virtual=False,
            title=f"On-campus finance analytics panel {uuid.uuid4().hex[:8]}",
        )

        for name, industry, role, industry_source, role_source, topic, zip_code in (
            ("alpha", REQUESTED_SECTOR, REQUESTED_ROLE, "human", "human", None, CAMPUS_ZIP),
            ("beta", REQUESTED_SECTOR, "marketing", "human", "human", None, CAMPUS_ZIP),
            ("gamma", "11", REQUESTED_ROLE, "human", "human", None, CAMPUS_ZIP),
            (
                "delta",
                REQUESTED_SECTOR,
                REQUESTED_ROLE,
                "human",
                "human",
                "Twelve years of treasury analytics and forecasting.",
                CAMPUS_ZIP,
            ),
            ("epsilon", REQUESTED_SECTOR, REQUESTED_ROLE, "inferred", "inferred", None, CAMPUS_ZIP),
            ("zeta", REQUESTED_SECTOR, REQUESTED_ROLE, "human", "human", None, OUT_OF_STATE_ZIP),
        ):
            speakers[name] = _insert_speaker(
                conn,
                tenant_id=tenant_id,
                unit_id=unit_id,
                reviewer_id=user_id,
                name=f"Speaker {name.title()}",
                industry_code=industry,
                role_code=role,
                industry_source=industry_source,
                role_source=role_source,
                topic_text=topic,
                postal_code=zip_code,
            )

    verifier = FixtureTokenVerifier()
    verifier.register(token, subject)
    client = TestClient(app)
    client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    client.app.state.token_verifier = verifier

    yield MatchFixture(
        client,
        tenant_id=tenant_id,
        unit_id=unit_id,
        token=token,
        virtual_request_id=virtual_request_id,
        physical_request_id=physical_request_id,
        speakers=speakers,
        user_id=user_id,
        engine=engine,
    )

    with engine.begin() as conn:
        # `match_run` before `job`: `match_run.job_id` is a NOT NULL foreign key
        # to `job`, so removing the job first is a constraint violation. The
        # same ordering `tests/integration/conftest.py` adopted when migration
        # 0018 landed. `speaker_profile` before `user_account` for the same
        # reason: its composite foreign key is ON DELETE RESTRICT.
        for table in (
            "job_event",
            "outbox_record",
            "redrive_record",
            "match_run",
            "job",
            "speaker_request_classification",
            "event",
            "speaker_availability_window",
            "speaker_availability",
            "speaker_profile",
            "membership",
            "resource_grant",
            "user_account",
            "org_unit",
            "idempotency_record",
            "rate_limit_counter",
        ):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tenant_id})


def _submission(fixture: MatchFixture, **overrides: Any) -> dict[str, Any]:
    """The default virtual submission: four reviewed speakers and one proposal."""
    body: dict[str, Any] = {
        "speaker_request_id": str(fixture.virtual_request_id),
        "portfolio_size": MIN_SHORTLIST_SIZE,
        "random_seed": 0,
        "candidate_subject_ids": fixture.subject("alpha", "beta", "gamma", "delta", "epsilon"),
    }
    body.update(overrides)
    return body


def _post(fixture: MatchFixture, body: dict[str, Any], *, key: str | None = None, token: Any = ...):
    headers = {"Idempotency-Key": key or f"idem-{uuid.uuid4().hex}"}
    bearer = fixture.token if token is ... else token
    if bearer is not None:
        headers["Authorization"] = f"Bearer {bearer}"
    return fixture.client.post(
        f"/v1/units/{fixture.unit_id}/match-runs", json=body, headers=headers
    )


def _get(fixture: MatchFixture, path: str, token: Any = ...):
    bearer = fixture.token if token is ... else token
    headers = {"Authorization": f"Bearer {bearer}"} if bearer is not None else {}
    return fixture.client.get(path, headers=headers)


def _execute_pending(engine: Engine, tenant_id: uuid.UUID, job_id: uuid.UUID):
    """Dispatch and execute the accepted command with the shipped registry."""
    session_factory = create_session_factory(engine.url.render_as_string(hide_password=False))
    OutboxDispatcher(session_factory, FixtureTaskQueue()).run_once()
    return TaskExecutor(session_factory, default_registry()).execute(
        tenant_id=tenant_id, job_id=job_id
    )


def _run_row(engine: Engine, job_id: uuid.UUID) -> Any:
    """The stored snapshot, read out of the table rather than off a response."""
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT id, event_need_id, registry_version, registry_hash, weights, "
                "route_estimate_version FROM match_run WHERE job_id = :job"
            ),
            {"job": job_id},
        ).one()


def _stored_payload(engine: Engine, job_id: uuid.UUID) -> dict[str, Any]:
    """The durable command payload, read out of ``job``.

    Read from the table and never from the ``202`` body, because
    ``get_session`` rolls back unconditionally: a route that computed everything
    correctly and never committed would return an immaculate response and store
    nothing at all.
    """
    with engine.connect() as conn:
        payload = conn.execute(
            text("SELECT payload FROM job WHERE id = :job"), {"job": job_id}
        ).scalar_one()
    assert isinstance(payload, dict), payload
    return payload


def _submit_and_execute(fixture: MatchFixture, engine: Engine, body: dict[str, Any] | None = None):
    """The whole path: submit, run the worker, and return the read response."""
    accepted = _post(fixture, body or _submission(fixture))
    assert accepted.status_code == 202, accepted.text
    job_id = uuid.UUID(accepted.json()["job_id"])

    outcome = _execute_pending(engine, fixture.tenant_id, job_id)
    assert outcome.status == "executed", outcome

    run_id = _run_row(engine, job_id).id
    read = _get(fixture, f"/v1/units/{fixture.unit_id}/match-runs/{run_id}")
    assert read.status_code == 200, read.text
    return accepted.json(), read.json()


# ---------------------------------------------------------------------------
# OQ-CBA-031 — a run reaches storage under 2.0.0, scored from stored evidence
# ---------------------------------------------------------------------------


def test_a_virtual_run_is_stored_under_the_cba_registry_and_names_its_mode(
    match_context, engine
) -> None:
    """The card's acceptance criterion, asserted against the tables.

    Before OQ-CBA-031 this could not pass: the route scored with
    ``rank_candidates``, so every stored run carried
    ``1.1.1-approved-g1-m6j`` and ``scoring_mode: null`` no matter what a client
    sent. The submission below carries **no evidence at all** — a request id,
    two numbers and five subject ids — and the run that lands is a 2.0.0 run in
    the virtual model.

    The mode is asserted on the durable command payload and on every stored
    explanation — both rows in ``job``, read back here with the API out of the
    picture. ``match_run`` grew a ``scoring_mode`` column of its own in
    migration ``0032`` (OQ-CBA-028), and that row is asserted in
    ``tests/integration/test_match_run_command_path.py`` rather than here: this
    file is about what the *route* puts on the command path, and the column is
    deliberately not on the wire. Exposing it on the read response is a separate
    card, with its own contract regeneration.
    """
    accepted = _post(match_context, _submission(match_context))
    assert accepted.status_code == 202, accepted.text
    job_id = uuid.UUID(accepted.json()["job_id"])

    payload = _stored_payload(engine, job_id)
    assert payload["scoring_mode"] == CBA_VIRTUAL_SCORING_MODE
    assert payload["event_need_id"] == str(match_context.virtual_request_id)

    stored_explanations = payload["explanations"]
    assert stored_explanations, "the run stored no explanations"
    for explanation in stored_explanations:
        assert explanation["scoring_mode"] == CBA_VIRTUAL_SCORING_MODE
        assert explanation["scoring_mode_version"] is not None
        assert explanation["scoring_mode_version"] == SCORING_MODE_VERSION
        assert explanation["registry_version"] == REGISTRY_VERSION
        assert explanation["registry_version"] != SUPERSEDED_REGISTRY_VERSION

    outcome = _execute_pending(engine, match_context.tenant_id, job_id)
    assert outcome.status == "executed", outcome

    run = _run_row(engine, job_id)
    assert run.registry_version == REGISTRY_VERSION
    assert run.event_need_id == str(match_context.virtual_request_id)
    # Three weights, not four: customer §11 removes Proximity from the virtual
    # model, and the snapshot's own weights say so.
    assert set(run.weights) == {"industry_match", "role_match", CBA_SEMANTIC_TOPIC_FACTOR_KEY}
    assert CBA_PROXIMITY_FACTOR_KEY not in run.weights
    assert abs(sum(float(weight) for weight in run.weights.values()) - 1.0) < 1e-9


def test_the_request_body_has_no_field_for_a_speakers_evidence(match_context) -> None:
    """The trust half of OQ-CBA-031, checked against the published schema.

    Not "the route ignores evidence it is sent" — there is nowhere to send any.
    A body that could state a speaker's industry or coordinates is a body that
    can choose its own shortlist and have the immutable snapshot agree.
    """
    schema = match_context.client.get("/openapi.json").json()
    body_schema = schema["components"]["schemas"]["MatchRunRequest"]

    assert set(body_schema["properties"]) == {
        "speaker_request_id",
        "portfolio_size",
        "random_seed",
        "candidate_subject_ids",
    }
    assert "MatchCandidateRequest" not in schema["components"]["schemas"]
    assert "GeoPointRequest" not in schema["components"]["schemas"]


def test_the_submission_reports_the_mode_and_the_registry_it_scored_under(match_context) -> None:
    """The two pins a caller cannot infer from a job id, on the acknowledgement."""
    body = _post(match_context, _submission(match_context)).json()

    assert body["registry_version"] == REGISTRY_VERSION
    assert body["registry_version"] != SUPERSEDED_REGISTRY_VERSION
    assert body["scoring_mode"] == CBA_VIRTUAL_SCORING_MODE
    assert body["scoring_mode_version"] == SCORING_MODE_VERSION
    assert body["score_label"] == SCORE_PROVENANCE_LABEL


# ---------------------------------------------------------------------------
# Physical is scored now, and an unmeasured speaker is still absent
# ---------------------------------------------------------------------------


def test_a_physical_speaker_request_is_scored_and_reaches_storage(match_context, engine) -> None:
    """OQ-CBA-024 shipped the ZIP-centroid table, so the 503 is gone.

    This route refused every physical request with
    ``match_run_physical_scoring_unavailable`` for as long as no coordinate
    table existed, because customer §10 gives Proximity the largest single
    weight and an unknown distance would have made every composite unknown. The
    table exists now, these speakers have Californian ZIPs on file, and the run
    goes through under ``cba-physical-1``.

    The run is read out of ``match_run`` rather than off the response, for the
    reason the virtual case gives: ``get_session`` rolls back unconditionally,
    so a route that stored nothing would still return a clean ``202``.
    """
    accepted = _post(
        match_context,
        _submission(
            match_context,
            speaker_request_id=str(match_context.physical_request_id),
            candidate_subject_ids=match_context.subject("alpha", "beta", "gamma"),
        ),
    )

    assert accepted.status_code == 202, accepted.text
    body = accepted.json()
    assert body["scoring_mode"] == CBA_PHYSICAL_SCORING_MODE
    assert body["scoring_mode_version"] == SCORING_MODE_VERSION
    assert body["registry_version"] == REGISTRY_VERSION
    assert body["scored_candidates"] == 3

    job_id = uuid.UUID(body["job_id"])
    payload = _stored_payload(engine, job_id)
    assert payload["scoring_mode"] == CBA_PHYSICAL_SCORING_MODE
    assert payload["event_need_id"] == str(match_context.physical_request_id)

    outcome = _execute_pending(engine, match_context.tenant_id, job_id)
    assert outcome.status == "executed", outcome

    run = _run_row(engine, job_id)
    assert run.registry_version == REGISTRY_VERSION
    assert run.event_need_id == str(match_context.physical_request_id)
    # Four weights, not three: customer §10 puts Proximity in the physical
    # model, and the snapshot's own weights are where that shows up.
    assert CBA_PROXIMITY_FACTOR_KEY in run.weights
    assert abs(sum(float(weight) for weight in run.weights.values()) - 1.0) < 1e-9


def test_a_speaker_whose_zip_is_not_in_the_table_is_unscorable_not_ranked_last(
    match_context,
) -> None:
    """The refusal's reason outlived the refusal.

    ``zeta`` differs from ``alpha`` in exactly one respect — a ZIP the
    Californian table does not name — so the cause is unambiguous. Their
    distance is unknown, which under the physical model makes their composite
    unknown, which makes them unscorable. They are **reported** rather than
    entered at ``0.0``: a speaker nobody has located must not sort below
    speakers who were measured, because that reads as "we looked and they were
    a poor fit" rather than "we do not know where they are".
    """
    body = _post(
        match_context,
        _submission(
            match_context,
            speaker_request_id=str(match_context.physical_request_id),
            candidate_subject_ids=match_context.subject("alpha", "beta", "gamma", "zeta"),
        ),
    ).json()

    assert body["scored_candidates"] == 3
    assert body["unscorable_candidates"] == 1
    assert body["excluded_candidates"] == []


def test_the_same_speaker_scores_under_the_virtual_model(match_context) -> None:
    """The control for the test above, and the ADR-0016 Proposal 5 boundary.

    ``zeta`` is unscorable under ``cba-physical-1`` *because of proximity*, and
    the proof is that the identical record scores under ``cba-virtual-1``, where
    customer §11 removes the factor from the model entirely. Without this, a
    ``zeta`` who was unscorable for some unrelated reason would pass the
    physical assertion just as well.
    """
    body = _post(
        match_context,
        _submission(
            match_context,
            candidate_subject_ids=match_context.subject("alpha", "beta", "gamma", "zeta"),
        ),
    ).json()

    assert body["scoring_mode"] == CBA_VIRTUAL_SCORING_MODE
    assert body["scored_candidates"] == 4
    assert body["unscorable_candidates"] == 0


# ---------------------------------------------------------------------------
# Track 16's gate: an unreviewed contact is absent, not ranked last
# ---------------------------------------------------------------------------


def test_an_unreviewed_contact_is_absent_from_the_pool_rather_than_scored(
    match_context, engine
) -> None:
    """§19 orders review before availability, and this is that ordering over HTTP.

    ``epsilon``'s classifications are a classifier's proposal. The honest
    outcome is that they are **not in the run at all** — not in the shortlist,
    not among the considered, not among the unscorable, and not in the stored
    candidate pool. A low rank would read as "we looked and they fit poorly"
    when in fact nobody has checked their record.
    """
    accepted, run = _submit_and_execute(match_context, engine)
    epsilon = str(match_context.speakers["epsilon"])

    excluded = {entry["subject_id"]: entry["reason"] for entry in accepted["excluded_candidates"]}
    assert epsilon in excluded
    assert excluded[epsilon] == "industry_classification_awaiting_review"

    everyone = {
        entry["subject_id"]
        for group in ("shortlist", "considered", "unscorable")
        for entry in run[group]
    }
    assert epsilon not in everyone

    job_id = uuid.UUID(accepted["job_id"])
    stored = _stored_payload(engine, job_id)
    assert epsilon not in {entry["subject_id"] for entry in stored["candidates"]}
    assert epsilon not in {entry["subject_id"] for entry in stored["explanations"]}


def test_a_subject_with_no_profile_row_is_reported_rather_than_scored(match_context) -> None:
    """A name nobody has a record for is an absence, and it says which absence.

    Distinct from the review case on purpose: "import this person" and "review
    this person's classification" are different actions, and one greyed-out row
    for both sends a Speaker Connector to the wrong screen.
    """
    stranger = str(uuid.uuid4())
    body = _submission(
        match_context,
        candidate_subject_ids=[*match_context.subject("alpha", "beta", "gamma"), stranger],
    )

    accepted = _post(match_context, body)

    assert accepted.status_code == 202, accepted.text
    excluded = {
        entry["subject_id"]: entry["reason"] for entry in accepted.json()["excluded_candidates"]
    }
    assert excluded == {stranger: "speaker_profile_not_found"}


# ---------------------------------------------------------------------------
# The write is a command, not an insert
# ---------------------------------------------------------------------------


def test_a_submission_is_accepted_as_a_command_and_writes_no_run_of_its_own(
    match_context, engine
) -> None:
    """202, a job, an outbox row — and no snapshot until the worker runs.

    A route that inserted a ``match_run`` directly would satisfy every read test
    in this file and still be wrong: the snapshot would exist with no durable
    command behind it, outside the transactional-outbox guarantee that business
    work is atomic with its terminal outcome.
    """
    response = _post(match_context, _submission(match_context))

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
                text("SELECT count(*) FROM match_run WHERE tenant_id = :tid"),
                {"tid": match_context.tenant_id},
            ).scalar_one()
            == 0
        ), "the route wrote a snapshot itself instead of enqueuing the command"


def test_the_submission_reports_which_candidates_could_be_scored(match_context) -> None:
    """Three scored, one unscorable, one never evaluated — and the three counts differ.

    A caller handed a job id and nothing else could not tell a pool of five that
    scored five from one that scored three, and the difference between "their
    topic evidence could not be compared" and "nobody has reviewed them" is the
    difference between two different jobs a Speaker Connector has to do.
    """
    body = _post(match_context, _submission(match_context)).json()

    assert body["scored_candidates"] == 3
    assert body["unscorable_candidates"] == 1
    assert len(body["excluded_candidates"]) == 1


def test_a_repeated_submission_under_one_key_is_a_replay_not_a_second_run(match_context) -> None:
    """Idempotency holds for this command as it does for every other."""
    key = f"idem-{uuid.uuid4().hex}"

    first = _post(match_context, _submission(match_context), key=key).json()
    second = _post(match_context, _submission(match_context), key=key).json()

    assert second["job_id"] == first["job_id"]
    assert second["replayed"] is True


def test_a_submission_that_cannot_fill_an_honest_shortlist_is_refused(match_context) -> None:
    """Absent evidence is never padded out with zeros to reach the size.

    ``delta``'s topic comparison is unknown and ``epsilon`` is unreviewed, so
    only ``alpha`` can be scored and a shortlist of two is unfillable. The
    refusal says so, and its details keep the two absences apart rather than
    reporting a single count that hides which fix is needed.
    """
    response = _post(
        match_context,
        _submission(
            match_context, candidate_subject_ids=match_context.subject("alpha", "delta", "epsilon")
        ),
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "match_run_insufficient_scorable_candidates"
    assert error["details"]["scorable_candidates"] == "1"
    assert error["details"]["unscorable_candidates"] == "1"
    assert error["details"]["excluded_candidates"] == "1"


def test_a_shortlist_outside_the_ratified_bounds_is_refused(match_context) -> None:
    """ "Return 2-3 speakers" is enforced on the request, not at render time."""
    too_many = _post(
        match_context, _submission(match_context, portfolio_size=MAX_SHORTLIST_SIZE + 1)
    )
    too_few = _post(
        match_context, _submission(match_context, portfolio_size=MIN_SHORTLIST_SIZE - 1)
    )

    assert too_many.status_code == 422
    assert too_few.status_code == 422


def test_a_duplicate_subject_is_refused_in_this_apis_own_envelope(match_context) -> None:
    """Refused here rather than met as a domain ``ValueError`` turned 500."""
    response = _post(
        match_context,
        _submission(match_context, candidate_subject_ids=match_context.subject("alpha", "alpha")),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "match_run_duplicate_candidate"


# ---------------------------------------------------------------------------
# Authorization is reached before anything is read or written
# ---------------------------------------------------------------------------


def test_an_unauthenticated_submission_is_refused(match_context) -> None:
    assert _post(match_context, _submission(match_context), token=None).status_code == 401


def test_a_unit_in_another_tenant_is_a_404_rather_than_a_403(match_context) -> None:
    """A 403 would confirm that the id names something real."""
    response = match_context.client.post(
        f"/v1/units/{uuid.uuid4()}/match-runs",
        json=_submission(match_context),
        headers={
            "Idempotency-Key": f"idem-{uuid.uuid4().hex}",
            "Authorization": f"Bearer {match_context.token}",
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unit_not_found"


def test_a_speaker_request_this_unit_does_not_host_is_a_404(match_context) -> None:
    """Scoped by unit in the query, so an unknown id and another unit's id agree."""
    response = _post(
        match_context, _submission(match_context, speaker_request_id=str(uuid.uuid4()))
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "speaker_request_not_found"


def test_reading_a_run_that_does_not_exist_is_a_404(match_context) -> None:
    response = _get(match_context, f"/v1/units/{match_context.unit_id}/match-runs/{uuid.uuid4()}")

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
    # `alpha` matches both the requested sector and the requested role; `beta`
    # and `gamma` each match one. The best-evidenced candidate is selected.
    assert str(match_context.speakers["alpha"]) in {
        entry["subject_id"] for entry in run["shortlist"]
    }


def test_every_score_on_the_read_carries_its_label_its_registry_and_its_mode(
    match_context, engine
) -> None:
    """The facts the G1 worksheet and ADR-0016 require beside every stored score."""
    _, run = _submit_and_execute(match_context, engine)

    assert run["score_label"] == SCORE_PROVENANCE_LABEL == "heuristic score"
    assert run["registry_version"] == REGISTRY_VERSION

    scored = run["shortlist"] + run["considered"] + run["unscorable"]
    assert scored, "the read returned no candidates at all"
    for entry in scored:
        assert entry["score_label"] == SCORE_PROVENANCE_LABEL
        # Every score says which rulebook produced it, and after the 2.0.0 bump
        # that is the sharpest form of the rule: the stored pin is the one the
        # score was produced under, never today's.
        assert entry["registry_version"] == REGISTRY_VERSION
        assert entry["scoring_mode"] == CBA_VIRTUAL_SCORING_MODE
        assert entry["scoring_mode_version"] == SCORING_MODE_VERSION


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
    assert set(run["weights"]) == {"industry_match", "role_match", CBA_SEMANTIC_TOPIC_FACTOR_KEY}
    assert abs(sum(run["weights"].values()) - 1.0) < 1e-9


def test_a_speaker_with_no_topic_information_scores_under_the_stated_policy(
    match_context, engine
) -> None:
    """ADR-0016's third state, over HTTP: policy is not measurement and not zero.

    ``alpha`` has an observed absence of topic information, which customer §9
    gives a neutral value rather than a zero. The response says so three ways —
    the factor's state, the composite's state, and the approved caption — so a
    surface can show the number *and* say what part of it was policy.
    """
    _, run = _submit_and_execute(match_context, engine)

    everyone = {
        entry["subject_id"]: entry
        for group in ("shortlist", "considered", "unscorable")
        for entry in run[group]
    }
    alpha = everyone[str(match_context.speakers["alpha"])]

    assert alpha["state"] == "policy_neutral"
    assert alpha["heuristic_score"] is not None
    assert alpha["policy_neutral_factor_keys"] == [CBA_SEMANTIC_TOPIC_FACTOR_KEY]
    assert alpha["caption"]

    topic = next(
        factor
        for factor in alpha["factors"]
        if factor["factor_key"] == CBA_SEMANTIC_TOPIC_FACTOR_KEY
    )
    assert topic["state"] == "policy_neutral"
    assert topic["value"] is not None
    assert topic["zero_classification"] is None
    assert topic["policy_id"]
    assert topic["policy_version"]


def test_a_candidate_with_absent_evidence_is_reported_unscored_and_never_at_zero(
    match_context, engine
) -> None:
    """ADR-0011 at the last boundary: the JSON a browser would parse.

    ``delta`` has topic text on file and the fixture provider holds no recording
    for that pair, so the comparison could not be made. The honest report is a
    null score with ``state="unknown"`` and the unknown factor named — not a
    zero that would place them below every measured candidate as though they had
    been measured and found wanting. That the *best-classified* speaker is the
    one excluded is uncomfortable and correct: it is what an open OQ-CBA-026
    actually costs.
    """
    _, run = _submit_and_execute(match_context, engine)
    delta_id = str(match_context.speakers["delta"])

    unscorable = {entry["subject_id"]: entry for entry in run["unscorable"]}
    assert set(unscorable) == {delta_id}

    delta = unscorable[delta_id]
    assert delta["state"] == "unknown"
    assert delta["heuristic_score"] is None
    assert delta["unknown_factor_keys"] == [CBA_SEMANTIC_TOPIC_FACTOR_KEY]

    factors = {factor["factor_key"]: factor for factor in delta["factors"]}
    topic = factors[CBA_SEMANTIC_TOPIC_FACTOR_KEY]
    assert topic["state"] == "unknown"
    assert topic["value"] is None
    assert topic["zero_classification"] == "unknown"
    assert topic["basis"]

    # The measured factors are still reported with their values: an unknown
    # composite does not erase the evidence that *was* present.
    assert factors["industry_match"]["state"] == "measured"
    assert factors["industry_match"]["value"] == 1.0
    assert factors["role_match"]["value"] == 1.0

    # Proximity is not in the list at all under the virtual model. Absent, not
    # unknown: customer §11 removes it, so there is no absence to explain.
    assert CBA_PROXIMITY_FACTOR_KEY not in factors

    assert delta_id not in {entry["subject_id"] for entry in run["shortlist"]}
    assert delta_id not in {entry["subject_id"] for entry in run["considered"]}


def test_a_measured_zero_is_reported_as_a_measured_zero(match_context, engine) -> None:
    """The other half of ADR-0011, over HTTP.

    ``gamma``'s sector is genuinely not one the request named: the value is
    present, the state says it was measured, and ``zero_classification`` says
    which kind of zero it is. This is the case the worksheet marks "Show 0% with
    source" — the source being ``basis``.
    """
    _, run = _submit_and_execute(match_context, engine)

    everyone = {
        entry["subject_id"]: entry
        for group in ("shortlist", "considered", "unscorable")
        for entry in run[group]
    }
    gamma = everyone[str(match_context.speakers["gamma"])]

    assert gamma["heuristic_score"] is not None
    industry = next(f for f in gamma["factors"] if f["factor_key"] == "industry_match")
    assert industry["state"] == "measured"
    assert industry["value"] == 0.0
    assert industry["zero_classification"] == "measured_zero"
    assert industry["basis"], "a measured zero must carry the source that measured it"


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


# ---------------------------------------------------------------------------
# B26 T4 — stored availability verdicts and "changed since this run"
# ---------------------------------------------------------------------------

#: The Speaker Requests' local date (``_insert_speaker_request``).
REQUEST_DAY = date(2027, 3, 4)
#: A pause that is still in force on any run date these tests produce.
PAUSED_UNTIL = date(2027, 6, 1)


@contextmanager
def _statements() -> Iterator[list[str]]:
    """Every SQL statement any engine executes inside the block."""
    seen: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    event.listen(Engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(Engine, "before_cursor_execute", record)


def _candidates(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        entry["subject_id"]: entry
        for entry in run["shortlist"] + run["considered"] + run["unscorable"]
    }


def _rewrite_payload(engine: Engine, job_id: uuid.UUID, expression: str) -> None:
    """Rewrite the stored command payload, as an older release (or an incident) left it."""
    with engine.begin() as conn:
        conn.execute(
            text(f"UPDATE job SET payload = {expression} WHERE id = :job"), {"job": job_id}
        )


def _read_run(fixture: MatchFixture, engine: Engine, job_id: uuid.UUID) -> dict[str, Any]:
    run_id = _run_row(engine, job_id).id
    read = _get(fixture, f"/v1/units/{fixture.unit_id}/match-runs/{run_id}")
    assert read.status_code == 200, read.text
    return read.json()


def test_availability_costs_one_query_on_create_and_two_on_read(match_context, engine) -> None:
    """17: one ``get_many`` on create; the event row plus one ``get_many`` on read."""
    with _statements() as created:
        accepted = _post(match_context, _submission(match_context))
    assert accepted.status_code == 202, accepted.text
    job_id = uuid.UUID(accepted.json()["job_id"])
    assert _execute_pending(engine, match_context.tenant_id, job_id).status == "executed"
    run_id = _run_row(engine, job_id).id

    with _statements() as read:
        response = _get(match_context, f"/v1/units/{match_context.unit_id}/match-runs/{run_id}")
    assert response.status_code == 200, response.text

    def availability(statements: list[str]) -> int:
        return sum("speaker_availability" in sql for sql in statements)

    def event_reads(statements: list[str]) -> int:
        return sum("FROM event" in sql for sql in statements)

    assert availability(created) == 1
    assert availability(read) == 1
    assert event_reads(read) == 1


def test_the_payload_records_a_verdict_for_every_evaluated_candidate(match_context, engine) -> None:
    """18: scorable and unscorable alike; the never-evaluated get none."""
    match_context.state_availability("alpha", windows=((REQUEST_DAY, REQUEST_DAY),))
    match_context.state_availability("beta", paused_until=PAUSED_UNTIL)
    match_context.state_availability("gamma")

    accepted, _ = _submit_and_execute(match_context, engine)
    payload = _stored_payload(engine, uuid.UUID(accepted["job_id"]))

    evaluated = [entry["subject_id"] for entry in payload["explanations"]]
    stored = payload["availability"]
    assert [entry["subject_id"] for entry in stored] == evaluated
    by_subject = {entry["subject_id"]: entry for entry in stored}
    speakers = {name: str(pid) for name, pid in match_context.speakers.items()}

    assert by_subject[speakers["alpha"]]["verdict"] == "excluded"
    assert by_subject[speakers["alpha"]]["reason"] == "window"
    assert by_subject[speakers["beta"]]["reason"] == "paused"
    assert by_subject[speakers["beta"]]["paused_until"] == PAUSED_UNTIL.isoformat()
    assert by_subject[speakers["gamma"]]["verdict"] == "eligible"
    assert by_subject[speakers["delta"]]["reason"] == "not_stated"
    # epsilon never entered the pool: no verdict, but a stored exclusion (C3).
    assert speakers["epsilon"] not in by_subject
    assert {
        "subject_id": speakers["epsilon"],
        "reason": "industry_classification_awaiting_review",
    } in (payload["excluded"])


def test_a_run_without_availability_reads_not_recorded(match_context, engine) -> None:
    """19: a run stored before T4 is "not recorded", never "available"."""
    accepted, _ = _submit_and_execute(match_context, engine)
    job_id = uuid.UUID(accepted["job_id"])
    _rewrite_payload(engine, job_id, "payload - 'availability' - 'excluded'")

    run = _read_run(match_context, engine, job_id)

    assert run["availability_recorded"] is False
    assert run["availability_unreadable_reason"] is None
    assert run["excluded"] == []
    assert run["excluded_unreadable_reason"] is None
    assert all(entry["availability"] is None for entry in _candidates(run).values())
    assert run["shortlist_available"] is True


def test_a_window_added_after_the_run_reads_changed_since(match_context, engine) -> None:
    """20: stored "available", now inside a window -> changed since this run."""
    match_context.state_availability("alpha")
    accepted, before = _submit_and_execute(match_context, engine)
    alpha = str(match_context.speakers["alpha"])
    assert _candidates(before)[alpha]["availability"]["changed_since_run"] is False

    match_context.state_availability("alpha", windows=((REQUEST_DAY, REQUEST_DAY),))
    run = _read_run(match_context, engine, uuid.UUID(accepted["job_id"]))

    view = _candidates(run)[alpha]["availability"]
    assert run["availability_recorded"] is True
    assert view["verdict"] == "eligible"
    assert view["reason"] == "clear"
    assert view["changed_since_run"] is True
    others = [entry for subject, entry in _candidates(run).items() if subject != alpha]
    assert all(entry["availability"]["changed_since_run"] is False for entry in others)


def test_availability_moves_neither_inputs_hash_nor_registry_hash(match_context, engine) -> None:
    """21a: G-CBA-13 over HTTP — a blacked-out Speaker changes no digest."""
    _, clear = _submit_and_execute(match_context, engine)
    match_context.state_availability("alpha", windows=((REQUEST_DAY, REQUEST_DAY),))
    match_context.state_availability("beta", paused_until=PAUSED_UNTIL)
    _, blocked = _submit_and_execute(match_context, engine)

    assert blocked["inputs_hash"] == clear["inputs_hash"]
    assert blocked["registry_hash"] == clear["registry_hash"]
    assert blocked["registry_version"] == clear["registry_version"] == REGISTRY_VERSION


def test_an_excluded_speaker_stays_on_the_shortlist_in_place(match_context, engine) -> None:
    """21b: the verdict annotates; it removes and reorders no one."""
    _, clear = _submit_and_execute(match_context, engine)
    match_context.state_availability("alpha", windows=((REQUEST_DAY, REQUEST_DAY),))
    _, blocked = _submit_and_execute(match_context, engine)

    for group in ("shortlist", "considered", "unscorable"):
        assert [e["subject_id"] for e in blocked[group]] == [e["subject_id"] for e in clear[group]]
    alpha = _candidates(blocked)[str(match_context.speakers["alpha"])]
    assert alpha["availability"]["verdict"] == "excluded"
    assert alpha["availability"]["reason"] == "window"


def test_a_malformed_availability_block_is_reported_not_repaired(match_context, engine) -> None:
    """23: strict reader — the run still reads, availability says why it cannot."""
    accepted, _ = _submit_and_execute(match_context, engine)
    job_id = uuid.UUID(accepted["job_id"])
    _rewrite_payload(
        engine,
        job_id,
        "jsonb_set(payload, '{availability,0,verdict}', '\"maybe\"'::jsonb)",
    )

    run = _read_run(match_context, engine, job_id)

    assert run["availability_recorded"] is False
    assert "verdict" in run["availability_unreadable_reason"]
    assert all(entry["availability"] is None for entry in _candidates(run).values())
    assert run["shortlist_available"] is True


# ---------------------------------------------------------------------------
# B26 T4 Q8 — the requester is left out of their own request's pool
# ---------------------------------------------------------------------------


def _excluded(accepted: dict[str, Any]) -> dict[str, str]:
    return {entry["subject_id"]: entry["reason"] for entry in accepted["excluded_candidates"]}


def test_the_requester_is_excluded_as_filed_this_request(match_context, engine) -> None:
    """22a."""
    host = match_context.new_login()
    match_context.bind_login("alpha", host)
    request_id = match_context.file_request(host)

    accepted, _ = _submit_and_execute(
        match_context, engine, _submission(match_context, speaker_request_id=str(request_id))
    )

    alpha = str(match_context.speakers["alpha"])
    assert _excluded(accepted)[alpha] == "filed_this_request"
    payload = _stored_payload(engine, uuid.UUID(accepted["job_id"]))
    assert alpha not in {entry["subject_id"] for entry in payload["explanations"]}
    assert alpha not in {entry["subject_id"] for entry in payload["candidates"]}


def test_another_hosts_request_excludes_nobody(match_context, engine) -> None:
    """22b."""
    match_context.bind_login("alpha", match_context.new_login())
    request_id = match_context.file_request(match_context.new_login())

    accepted, _ = _submit_and_execute(
        match_context, engine, _submission(match_context, speaker_request_id=str(request_id))
    )

    assert "filed_this_request" not in _excluded(accepted).values()


def test_a_speaker_with_no_bound_login_is_never_excluded(match_context, engine) -> None:
    """22c."""
    request_id = match_context.file_request(match_context.new_login())

    accepted, _ = _submit_and_execute(
        match_context, engine, _submission(match_context, speaker_request_id=str(request_id))
    )

    assert "filed_this_request" not in _excluded(accepted).values()


def test_a_request_with_no_recorded_filer_excludes_nobody(match_context, engine) -> None:
    """22d: NULL never equals NULL, and an unknown filer is nobody."""
    match_context.bind_login("alpha", match_context.new_login())
    request_id = match_context.file_request(None)

    accepted, _ = _submit_and_execute(
        match_context, engine, _submission(match_context, speaker_request_id=str(request_id))
    )

    assert "filed_this_request" not in _excluded(accepted).values()


def test_excluding_the_requester_fingerprints_like_not_naming_them(match_context, engine) -> None:
    """22e: Q8 changes ``candidates`` only as naming fewer people would."""
    host = match_context.new_login()
    match_context.bind_login("alpha", host)
    request_id = match_context.file_request(host)

    _, with_requester = _submit_and_execute(
        match_context,
        engine,
        _submission(
            match_context,
            speaker_request_id=str(request_id),
            candidate_subject_ids=match_context.subject("alpha", "beta", "gamma", "delta"),
        ),
    )
    _, without = _submit_and_execute(
        match_context,
        engine,
        _submission(
            match_context,
            speaker_request_id=str(request_id),
            candidate_subject_ids=match_context.subject("beta", "gamma", "delta"),
        ),
    )

    assert with_requester["inputs_hash"] == without["inputs_hash"]
    assert with_requester["registry_hash"] == without["registry_hash"]


def test_the_read_lists_the_excluded_requester(match_context, engine) -> None:
    """22f (C3): the stored exclusion is on the read, not only on the 202."""
    host = match_context.new_login()
    match_context.bind_login("alpha", host)
    request_id = match_context.file_request(host)

    _, run = _submit_and_execute(
        match_context, engine, _submission(match_context, speaker_request_id=str(request_id))
    )

    alpha = str(match_context.speakers["alpha"])
    assert {"subject_id": alpha, "reason": "filed_this_request"} in run["excluded"]
    assert alpha not in _candidates(run)


def test_a_malformed_excluded_block_is_reported_not_dropped(match_context, engine) -> None:
    """C3's stored list is read strictly: one bad entry is reported, never skipped."""
    accepted, _ = _submit_and_execute(match_context, engine)
    job_id = uuid.UUID(accepted["job_id"])
    _rewrite_payload(
        engine,
        job_id,
        "jsonb_set(payload, '{excluded}', (payload->'excluded') || '[{\"subject_id\": 7}]'::jsonb)",
    )

    run = _read_run(match_context, engine, job_id)

    assert run["excluded"] == []
    assert "subject_id" in run["excluded_unreadable_reason"]
    assert run["shortlist_available"] is True


def test_a_malformed_load_block_on_an_exclusion_is_reported_not_dropped(
    match_context, engine
) -> None:
    """B26 T8c: a present ``load`` that does not render is unreadable, never "no block"."""
    accepted, _ = _submit_and_execute(match_context, engine)
    job_id = uuid.UUID(accepted["job_id"])
    bad = '[{"subject_id": "x", "reason": "load_full", "load": {"band": 7}}]'
    _rewrite_payload(
        engine,
        job_id,
        f"jsonb_set(payload, '{{excluded}}', (payload->'excluded') || '{bad}'::jsonb)",
    )

    run = _read_run(match_context, engine, job_id)

    assert run["excluded"] == []
    assert ".load" in run["excluded_unreadable_reason"]


# ---------------------------------------------------------------------------
# B26 T8c: registry 3.0.0 (proposed, NOT current) on the create and read routes
# ---------------------------------------------------------------------------
#
# 2.0.0 stays current. The 3.0.0 tests switch the current registry for one test
# only (monkeypatch) and, where the test needs 3.0.0 to score, evaluate its
# approval gate through tests/unit/registry_evaluation.py. C3 and C8 do the
# switch WITHOUT the helper and prove the create route fails closed while
# stored runs stay readable.

#: One fixed run instant, so the load window is exact: as_of = 2026-10-06 (UTC).
T8C_NOW = datetime(2026, 10, 6, 18, 0, tzinfo=UTC)
T8C_AS_OF = date(2026, 10, 6)
_LA = ZoneInfo("America/Los_Angeles")


def _make_3_0_0_current(monkeypatch, *, evaluate: bool) -> None:
    from smartmatch_domain import factor_registry
    from smartmatch_domain.factor_registry import CBA_REGISTRY_3

    monkeypatch.setattr(factor_registry, "CURRENT_CBA_REGISTRY", CBA_REGISTRY_3)
    if evaluate:
        evaluate_registry_3(
            monkeypatch,
            modules=(
                *DOMAIN_MODULES,
                "smartmatch_api.routers.match_runs",
                "smartmatch_worker.handlers",
            ),
        )


@pytest.fixture
def load_context(match_context, engine, monkeypatch) -> Iterator[MatchFixture]:
    """``match_context`` at a fixed run date, with its bookings swept afterwards."""
    from smartmatch_api.routers import match_runs as match_runs_router

    monkeypatch.setattr(match_runs_router, "utc_now", lambda: T8C_NOW)
    yield match_context
    with engine.begin() as conn:
        for table in ("pipeline_record", "attendance_record"):
            conn.execute(
                text(f"DELETE FROM {table} WHERE tenant_id = :tid"),
                {"tid": match_context.tenant_id},
            )


def _state_capacity(fixture: MatchFixture, name: str, hours: str) -> None:
    fixture.state_availability(name)
    assert fixture.engine is not None
    with fixture.engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE speaker_availability SET declared_capacity_hours_per_90_days = "
                "CAST(:hours AS numeric) WHERE tenant_id = :t AND professional_id = :p"
            ),
            {"hours": hours, "t": fixture.tenant_id, "p": fixture.speakers[name]},
        )


def _booking(
    fixture: MatchFixture, name: str, *, offset_days: int, hours: float | None
) -> uuid.UUID:
    """One confirmed booking of ``name`` at noon local, ``offset_days`` from the run.

    ``hours=None`` files a date-only event, whose hours are unknown (never 0).
    """
    from smartmatch_domain.events import DateOnlyTime, ExactTime
    from smartmatch_persistence.events import ORIGIN_COORDINATOR_ENTRY, EventRepository

    day = T8C_AS_OF + timedelta(days=offset_days)
    if hours is None:
        event_time: Any = DateOnlyTime(on_date=day, time_zone="America/Los_Angeles")
    else:
        starts = datetime(day.year, day.month, day.day, 12, 0, tzinfo=_LA)
        event_time = ExactTime(
            starts_at=starts,
            time_zone="America/Los_Angeles",
            ends_at=starts + timedelta(hours=hours),
        )
    assert fixture.engine is not None
    session_factory = create_session_factory(
        fixture.engine.url.render_as_string(hide_password=False)
    )
    with session_factory() as session:
        event_id = EventRepository().upsert(
            session,
            tenant_id=fixture.tenant_id,
            host_org_unit_id=fixture.unit_id,
            title=f"T8c booking {uuid.uuid4().hex[:10]}",
            event_time=event_time,
            origin=ORIGIN_COORDINATOR_ENTRY,
        )
        session.commit()
    record_id = uuid.uuid4()
    base = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
    with fixture.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO pipeline_record (id, tenant_id, owning_unit_id, subject_id, "
                "opportunity_event_id, matched_provenance, matched_at, contacted_at, "
                "confirmed_at) VALUES (:id, :t, :unit, :subject, :event, "
                "'synthetic / coordinator-accepted', :m, :c, :k)"
            ),
            {
                "id": record_id,
                "t": fixture.tenant_id,
                "unit": fixture.unit_id,
                "subject": fixture.speakers[name],
                "event": event_id,
                "m": base,
                "c": base + timedelta(hours=1),
                "k": base + timedelta(hours=2),
            },
        )
    return record_id


def _seed_loads(fixture: MatchFixture) -> dict[str, Any]:
    """alpha Moderate, zeta Unknown (hours unknown), beta Full, gamma Full lower bound."""
    _state_capacity(fixture, "alpha", "10.0")
    _booking(fixture, "alpha", offset_days=5, hours=5)
    _state_capacity(fixture, "zeta", "100.0")
    zeta_ref = _booking(fixture, "zeta", offset_days=4, hours=None)
    _state_capacity(fixture, "beta", "10.0")
    _booking(fixture, "beta", offset_days=5, hours=12)
    _state_capacity(fixture, "gamma", "10.0")
    _booking(fixture, "gamma", offset_days=3, hours=10.5)
    gamma_ref = _booking(fixture, "gamma", offset_days=2, hours=None)
    return {"zeta_ref": str(zeta_ref), "gamma_ref": str(gamma_ref)}


def _load_submission(fixture: MatchFixture) -> dict[str, Any]:
    return _submission(
        fixture, candidate_subject_ids=fixture.subject("alpha", "zeta", "beta", "gamma")
    )


def _explanations_by_subject(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["subject_id"]: entry for entry in payload["explanations"]}


def _keys_anywhere(value: Any) -> set[str]:
    if isinstance(value, dict):
        found = set(value)
        for child in value.values():
            found |= _keys_anywhere(child)
        return found
    if isinstance(value, list):
        found = set()
        for child in value:
            found |= _keys_anywhere(child)
        return found
    return set()


# C1
def test_create_scores_under_2_0_0_and_reads_no_engagements(load_context, engine) -> None:
    _seed_loads(load_context)
    with _statements() as created:
        accepted = _post(load_context, _load_submission(load_context))
    assert accepted.status_code == 202, accepted.text
    payload = _stored_payload(engine, uuid.UUID(accepted.json()["job_id"]))

    assert payload["registry_version"] == REGISTRY_VERSION
    assert accepted.json()["registry_version"] == REGISTRY_VERSION
    assert all("load" not in entry for entry in payload["explanations"])
    assert all("load" not in entry for entry in payload["excluded"])
    # Beta and gamma are Full, but 2.0.0 has no load band table: nobody is removed.
    assert {entry["reason"] for entry in payload["excluded"]} <= {
        "industry_classification_awaiting_review"
    }
    # T4's cost: one availability read, and no engagement read at all.
    assert sum("speaker_availability" in sql for sql in created) == 1
    assert not any("pipeline_record" in sql for sql in created)


# C2
def test_under_evaluation_create_removes_full_and_stores_load_blocks(
    load_context, engine, monkeypatch
) -> None:
    refs = _seed_loads(load_context)
    _make_3_0_0_current(monkeypatch, evaluate=True)
    from smartmatch_domain.factor_registry import (
        CBA_3_VIRTUAL_MODEL,
        CBA_REGISTRY_3,
        REGISTRY_3_VERSION,
        normalize_weights,
    )

    accepted, run = _submit_and_execute(load_context, engine, _load_submission(load_context))
    job_id = uuid.UUID(accepted["job_id"])
    payload = _stored_payload(engine, job_id)
    beta, gamma = (str(load_context.speakers[n]) for n in ("beta", "gamma"))

    # Full removed before the solve, reported with its load.
    assert payload["registry_version"] == REGISTRY_3_VERSION
    excluded = {entry["subject_id"]: entry for entry in payload["excluded"]}
    assert excluded[beta]["reason"] == "load_full"
    assert excluded[beta]["load"]["band"] == "full"
    assert excluded[gamma]["reason"] == "load_full"
    assert excluded[gamma]["load"]["reason"] == "full_by_known_hours"
    # The stored payload keeps the refs: the run's own evidence.
    assert excluded[gamma]["load"]["unknown_hours_refs"] == [refs["gamma_ref"]]
    assert {c["subject_id"] for c in payload["candidates"]}.isdisjoint({beta, gamma})

    # Moderate multiplies the unrounded composite by 0.9, then rounds once.
    alpha = _explanations_by_subject(payload)[str(load_context.speakers["alpha"])]
    assert alpha["load"]["band"] == "moderate"
    assert alpha["heuristic_score"] == round(alpha["load"]["composite_before_load"] * 0.9, 6)

    # The worker pinned 3.0.0 and fingerprinted the band table.
    row = _run_row(engine, job_id)
    weights = normalize_weights(model=CBA_3_VIRTUAL_MODEL, registry=CBA_REGISTRY_3)
    assert row.registry_version == REGISTRY_3_VERSION
    assert row.registry_hash == registry_fingerprint(weights, load_bands=CBA_REGISTRY_3.load_bands)

    # The read renders the Full Speakers with their load, and never the refs.
    read_excluded = {entry["subject_id"]: entry for entry in run["excluded"]}
    assert read_excluded[gamma]["reason"] == "load_full"
    assert read_excluded[gamma]["load"]["band"] == "full"
    assert read_excluded[gamma]["load"]["reason"] == "full_by_known_hours"
    assert "unknown_hours_refs" not in read_excluded[gamma]["load"]
    accepted_excluded = {entry["subject_id"]: entry for entry in accepted["excluded_candidates"]}
    assert accepted_excluded[beta]["load"]["band"] == "full"
    assert "unknown_hours_refs" not in accepted_excluded[gamma]["load"]


# C3
def test_a_proposed_current_registry_fails_closed(load_context, engine, monkeypatch) -> None:
    _make_3_0_0_current(monkeypatch, evaluate=False)
    with engine.connect() as conn:
        before = conn.execute(
            text("SELECT count(*) FROM job WHERE tenant_id = :t"),
            {"t": load_context.tenant_id},
        ).scalar_one()
    response = _post(load_context, _submission(load_context))
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "registry_not_ready"
    with engine.connect() as conn:
        after = conn.execute(
            text("SELECT count(*) FROM job WHERE tenant_id = :t"),
            {"t": load_context.tenant_id},
        ).scalar_one()
    assert after == before


# C4
def test_3_0_0_create_costs_one_more_query_than_2_0_0(load_context, monkeypatch) -> None:
    _seed_loads(load_context)
    with _statements() as two:
        assert _post(load_context, _load_submission(load_context)).status_code == 202
    _make_3_0_0_current(monkeypatch, evaluate=True)
    with _statements() as three:
        assert _post(load_context, _load_submission(load_context)).status_code == 202
    assert len(three) == len(two) + 1
    assert sum("pipeline_record" in sql for sql in three) == 1
    assert sum("speaker_availability" in sql for sql in three) == 1


# C5
def test_cancelling_a_booking_lowers_the_band_on_the_next_run(
    load_context, engine, monkeypatch
) -> None:
    from smartmatch_persistence.pipeline import PipelineRepository

    _make_3_0_0_current(monkeypatch, evaluate=True)
    _state_capacity(load_context, "alpha", "10.0")
    _booking(load_context, "alpha", offset_days=5, hours=4)
    second = _booking(load_context, "alpha", offset_days=6, hours=6)
    body = _submission(load_context, candidate_subject_ids=load_context.subject("alpha", "zeta"))
    alpha = str(load_context.speakers["alpha"])

    first = _post(load_context, body)
    assert first.status_code == 202, first.text
    before = _explanations_by_subject(_stored_payload(engine, uuid.UUID(first.json()["job_id"])))[
        alpha
    ]
    assert before["load"]["band"] == "heavy"

    assert load_context.engine is not None and load_context.user_id is not None
    session_factory = create_session_factory(engine.url.render_as_string(hide_password=False))
    with session_factory() as session:
        PipelineRepository().cancel_booking(
            session,
            tenant_id=load_context.tenant_id,
            record_id=second,
            actor_user_id=load_context.user_id,
            at=datetime.now(UTC),
        )
        session.commit()

    again = _post(load_context, body)
    assert again.status_code == 202, again.text
    after = _explanations_by_subject(_stored_payload(engine, uuid.UUID(again.json()["job_id"])))[
        alpha
    ]
    assert after["load"]["band"] == "light"
    assert after["load"]["utilization"] == "0.4"


# C6
def test_a_stored_2_0_0_run_reads_unchanged_after_current_is_switched(
    load_context, engine, monkeypatch
) -> None:
    accepted, before = _submit_and_execute(load_context, engine)
    _make_3_0_0_current(monkeypatch, evaluate=True)
    after = _read_run(load_context, engine, uuid.UUID(accepted["job_id"]))
    assert after["registry_version"] == before["registry_version"] == REGISTRY_VERSION
    assert after["registry_hash"] == before["registry_hash"]
    assert after["shortlist"] == before["shortlist"]
    assert after["considered"] == before["considered"]
    assert "load" not in _keys_anywhere(after["shortlist"] + after["considered"])


# C7
def test_the_availability_and_load_as_of_are_the_same_date(
    load_context, engine, monkeypatch
) -> None:
    _seed_loads(load_context)
    _make_3_0_0_current(monkeypatch, evaluate=True)
    accepted = _post(load_context, _load_submission(load_context))
    assert accepted.status_code == 202, accepted.text
    payload = _stored_payload(engine, uuid.UUID(accepted.json()["job_id"]))
    availability_dates = {entry["as_of"] for entry in payload["availability"]}
    load_dates = {entry["load"]["as_of"] for entry in payload["explanations"]}
    load_dates |= {entry["load"]["as_of"] for entry in payload["excluded"] if "load" in entry}
    assert availability_dates == load_dates == {T8C_AS_OF.isoformat()}


# C9
def test_the_run_read_never_carries_unknown_hours_refs(load_context, engine, monkeypatch) -> None:
    refs = _seed_loads(load_context)
    _make_3_0_0_current(monkeypatch, evaluate=True)
    accepted, run = _submit_and_execute(load_context, engine, _load_submission(load_context))
    payload = _stored_payload(engine, uuid.UUID(accepted["job_id"]))

    # Stored: non-empty refs on an explanation and on an excluded entry.
    zeta = _explanations_by_subject(payload)[str(load_context.speakers["zeta"])]
    assert zeta["load"]["unknown_hours_refs"] == [refs["zeta_ref"]]
    gamma = next(
        e
        for e in payload["excluded"]
        if e["reason"] == "load_full" and e["load"]["unknown_hours_refs"]
    )
    assert gamma["load"]["unknown_hours_refs"] == [refs["gamma_ref"]]

    # On the wire: nowhere, in the 202 or the read.
    assert "unknown_hours_refs" not in _keys_anywhere(accepted)
    assert "unknown_hours_refs" not in _keys_anywhere(run)
    assert refs["zeta_ref"] not in json.dumps(run)
    assert refs["gamma_ref"] not in json.dumps(run)


# C8
def test_a_flipped_unapproved_current_registry_does_not_block_stored_run_reads(
    load_context, engine, monkeypatch
) -> None:
    accepted, before = _submit_and_execute(load_context, engine)
    _make_3_0_0_current(monkeypatch, evaluate=False)

    after = _read_run(load_context, engine, uuid.UUID(accepted["job_id"]))
    assert after["registry_hash"] == before["registry_hash"]
    assert after["shortlist_available"] is True
    assert after["shortlist"] == before["shortlist"]

    refused = _post(load_context, _submission(load_context))
    assert refused.status_code == 503, refused.text
    assert refused.json()["error"]["code"] == "registry_not_ready"


# ---------------------------------------------------------------------------
# Owner ruling R-A (2026-09-24): load numbers never reach the API wire
# ---------------------------------------------------------------------------
#
# The wire's load block names the band and why; the hours, the declared
# capacity and the utilization it was computed from stay in the stored run
# payload only, for audit.

LOAD_NUMBER_KEYS = frozenset(
    {"completed_hours", "confirmed_hours", "capacity_hours", "utilization"}
)
WIRE_LOAD_BLOCK_KEYS = frozenset({"band", "reason", "measurable", "as_of", "eli_formula_version"})


# C10
def test_no_load_number_reaches_the_wire_and_the_stored_payload_keeps_them(
    load_context, engine, monkeypatch
) -> None:
    _seed_loads(load_context)
    _make_3_0_0_current(monkeypatch, evaluate=True)
    accepted, run = _submit_and_execute(load_context, engine, _load_submission(load_context))
    payload = _stored_payload(engine, uuid.UUID(accepted["job_id"]))
    beta, gamma = (str(load_context.speakers[n]) for n in ("beta", "gamma"))

    # Stored: every load_full exclusion keeps its hours, capacity and utilization.
    stored = {e["subject_id"]: e["load"] for e in payload["excluded"] if "load" in e}
    assert set(stored) == {beta, gamma}
    for block in stored.values():
        assert set(block) >= LOAD_NUMBER_KEYS
    assert stored[beta]["capacity_hours"] == "10.0"

    # On the wire: band and reason only, in the 202 and on the read.
    for wire in (accepted["excluded_candidates"], run["excluded"]):
        loads = {e["subject_id"]: e["load"] for e in wire if "load" in e}
        assert set(loads) == {beta, gamma}
        for block in loads.values():
            assert set(block) == WIRE_LOAD_BLOCK_KEYS
        assert loads[gamma]["band"] == "full"
        assert loads[gamma]["reason"] == "full_by_known_hours"
    assert LOAD_NUMBER_KEYS.isdisjoint(_keys_anywhere(accepted))
    assert LOAD_NUMBER_KEYS.isdisjoint(_keys_anywhere(run))
