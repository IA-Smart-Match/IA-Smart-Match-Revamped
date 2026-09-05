"""HTTP contracts for the coordinator-driven pipeline stage writers (S12).

``docs/plans/2026-09-05-pipeline-stage-writers-plan.md`` §4. What this file
asserts that nothing else can:

* **A coordinator cannot hand-write Contacted or Matched.** The request schema
  admits three stages, and the exclusion is the point rather than an oversight:
  Contacted is the funnel's one machine-witnessed stage (the outreach worker
  writes it after a provider took custody of a message), and a route that let a
  human type it would destroy the distinction the metric depends on. Asserted
  against the *published OpenAPI enum*, not just the Python model, because the
  enum is what a client generator reads.
* **Attended cites evidence or is refused.** Both halves of
  ``ck_pipeline_record_attendance_evidence`` are enforced at the request
  boundary as a ``422``, and evidence naming no row is a ``409`` — the stage
  cites attendance and never creates it.
* **The ordering constraints reach the caller as 409s, not 500s.** Skipping a
  stage and back-dating a stage are two different refusals with two different
  ``code`` values, so a client can tell a coordinator which mistake they made.
* **A repeat is idempotent in the data.** No ``Idempotency-Key`` exists on this
  route; asserting a stage that is already recorded is a ``200`` reporting
  ``transitioned: false, already_reached: true`` and the unchanged timestamp.
* **A record in a sibling unit is a 404, never a 403.** A 403 would confirm that
  an id the caller may not read names a real journey.

:class:`TestStageRequestSchema` needs no database and runs in the default
``make test`` gate. Everything below it drives real rows through the real routes
and is marked ``integration``, skipped when no migrated PostgreSQL is reachable.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from smartmatch_api.main import app
from smartmatch_api.routers.pipeline import StageAdvanceRequest
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Engine, create_engine, text

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

UNIT_PATH = "iawest.pipelinestages"
#: A second department containing none of :data:`UNIT_PATH`, so a coordinator
#: granted there must not reach this one's journeys.
SIBLING_UNIT_PATH = "iawest.pipelinestagessibling"

#: The one provenance string this repository writes for a coordinator-accepted
#: row (``MATCH_PROVENANCE_SYNTHETIC_COORDINATOR``). Spelled here rather than
#: imported so a test row is visibly synthetic in the SQL that creates it.
SYNTHETIC_PROVENANCE = "synthetic / coordinator-accepted"

#: A fixed instant the whole file orders its timestamps against, so an assertion
#: about ordering is about the ordering and not about how long the test took.
BASE = datetime(2026, 6, 12, 15, 0, tzinfo=UTC)
MATCHED_AT = BASE
CONTACTED_AT = BASE + timedelta(hours=1)
CONFIRMED_AT = BASE + timedelta(hours=2)
ATTENDED_AT = BASE + timedelta(hours=3)
INQUIRY_AT = BASE + timedelta(hours=4)


# ---------------------------------------------------------------------------
# The request schema — no database, so this runs in the default gate
# ---------------------------------------------------------------------------


class TestStageRequestSchema:
    """What the wire will and will not accept, before any row is involved."""

    def test_only_three_stages_are_writable_over_http(self) -> None:
        """``matched`` and ``contacted`` are absent from the published enum.

        Read out of the OpenAPI document rather than off the Python ``Literal``:
        a generated client's own enum comes from this document, so this is the
        artifact that has to be right.
        """
        schema = app.openapi()["components"]["schemas"]["StageAdvanceRequest"]
        stage = schema["properties"]["stage"]
        # Pydantic renders a `Literal` of three strings as an inline enum.
        assert stage["enum"] == ["confirmed", "attended", "member_inquiry"]

    @pytest.mark.parametrize("stage", ["matched", "contacted"])
    def test_the_machine_witnessed_stages_are_refused(self, stage: str) -> None:
        with pytest.raises(ValidationError):
            StageAdvanceRequest(stage=stage, reached_at=CONFIRMED_AT)  # type: ignore[arg-type]

    def test_attended_without_evidence_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="attendance_id is required"):
            StageAdvanceRequest(stage="attended", reached_at=ATTENDED_AT)

    def test_evidence_for_a_stage_that_is_not_attended_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="only accepted for the 'attended' stage"):
            StageAdvanceRequest(
                stage="confirmed", reached_at=CONFIRMED_AT, attendance_id=uuid.uuid4()
            )

    def test_a_naive_reached_at_is_refused(self) -> None:
        """A naive datetime can silently violate ``ck_pipeline_record_stage_order``.

        ``AwareDatetime`` moves that from a constraint violation naming a column
        to a ``422`` naming the field.
        """
        with pytest.raises(ValidationError):
            StageAdvanceRequest(stage="confirmed", reached_at=datetime(2026, 6, 12, 17, 0))

    def test_reached_at_has_no_default(self) -> None:
        """It is never ``now()``: this records when something happened."""
        with pytest.raises(ValidationError):
            StageAdvanceRequest(stage="confirmed")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Everything below drives real rows through the real routes
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def engine() -> Engine:
    """A live migrated PostgreSQL engine, or skip this contract."""
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1 FROM pipeline_record LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}")
    return eng


@dataclass(frozen=True, slots=True)
class _Context:
    """One tenant, one coordinator, one journey at Contacted, and its evidence."""

    client: TestClient
    engine: Engine
    tenant_id: uuid.UUID
    unit_id: uuid.UUID
    sibling_unit_id: uuid.UUID
    token: str
    record_id: uuid.UUID
    sibling_record_id: uuid.UUID
    attendance_id: uuid.UUID
    student_id: uuid.UUID
    event_id: uuid.UUID

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def advance(self, stage: str, reached_at: datetime, **extra: object):
        body: dict[str, object] = {"stage": stage, "reached_at": reached_at.isoformat()}
        body.update(extra)
        return self.client.post(
            f"/v1/units/{self.unit_id}/pipeline-records/{self.record_id}/stages",
            json=body,
            headers=self.headers(),
        )

    def read(self, record_id: uuid.UUID | None = None):
        target = self.record_id if record_id is None else record_id
        return self.client.get(
            f"/v1/units/{self.unit_id}/pipeline-records/{target}",
            headers=self.headers(),
        )

    def stage_timestamps(self) -> dict[str, object]:
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT confirmed_at, attended_at, member_inquiry_at, "
                    "attended_attendance_id FROM pipeline_record WHERE id = :id"
                ),
                {"id": self.record_id},
            ).one()
        return {
            "confirmed_at": row.confirmed_at,
            "attended_at": row.attended_at,
            "member_inquiry_at": row.member_inquiry_at,
            "attended_attendance_id": row.attended_attendance_id,
        }


def _insert_journey(
    conn: object,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    subject_id: uuid.UUID,
    event_id: uuid.UUID,
) -> uuid.UUID:
    """One journey already at Contacted — where the outreach worker leaves it.

    Contacted is seeded rather than asserted over HTTP because no route writes
    it: that is this slice's whole premise, and a test that reached it through
    the new route would be testing a rule the module deliberately refuses.
    """
    record_id = uuid.uuid4()
    conn.execute(  # type: ignore[attr-defined]
        text(
            "INSERT INTO pipeline_record (id, tenant_id, owning_unit_id, subject_id, "
            "opportunity_event_id, matched_at, matched_provenance, contacted_at) "
            "VALUES (:id, :tid, :unit, :subject, :event, :matched, :prov, :contacted)"
        ),
        {
            "id": record_id,
            "tid": tenant_id,
            "unit": unit_id,
            "subject": subject_id,
            "event": event_id,
            "matched": MATCHED_AT,
            "prov": SYNTHETIC_PROVENANCE,
            "contacted": CONTACTED_AT,
        },
    )
    return record_id


@pytest.fixture
def ctx(engine: Engine) -> Iterator[_Context]:
    tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()
    sibling_unit_id = uuid.uuid4()
    coordinator_id = uuid.uuid4()
    student_id = uuid.uuid4()
    sibling_student_id = uuid.uuid4()
    event_id = uuid.uuid4()
    attendance_id = uuid.uuid4()
    # Derived at runtime rather than written as literals: a fixture credential
    # spelled out in a source file is a credential in a commit patch.
    subject = f"sub-pipeline-{uuid.uuid4().hex}"
    token = f"tok-pipeline-{uuid.uuid4().hex}"

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-pipeline-{tenant_id.hex[:12]}"},
        )
        for new_unit_id, path, name in (
            (unit_id, UNIT_PATH, "Pipeline"),
            (sibling_unit_id, SIBLING_UNIT_PATH, "Sibling"),
        ):
            conn.execute(
                text(
                    "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                    "VALUES (:id, :tid, CAST(:path AS ltree), 'department', :name)"
                ),
                {"id": new_unit_id, "tid": tenant_id, "path": path, "name": name},
            )
        for account_id, account_subject in (
            (coordinator_id, subject),
            (student_id, f"sub-student-{uuid.uuid4().hex}"),
            (sibling_student_id, f"sub-student-{uuid.uuid4().hex}"),
        ):
            conn.execute(
                text(
                    "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                    "VALUES (:id, :tid, :subject, :email)"
                ),
                {
                    "id": account_id,
                    "tid": tenant_id,
                    "subject": account_subject,
                    "email": f"{account_subject}@example.edu",
                },
            )
        conn.execute(
            text(
                "INSERT INTO membership (id, tenant_id, user_id, granted_path, role) "
                "VALUES (:id, :tid, :uid, CAST(:path AS ltree), 'coordinator')"
            ),
            {
                "id": uuid.uuid4(),
                "tid": tenant_id,
                "uid": coordinator_id,
                "path": UNIT_PATH,
            },
        )
        conn.execute(
            text(
                "INSERT INTO event (id, tenant_id, host_org_unit_id, title, "
                "normalized_title, time_precision, origin) "
                "VALUES (:id, :tid, :unit, :title, :normalized, 'unresolved', "
                "'coordinator_entry')"
            ),
            {
                "id": event_id,
                "tid": tenant_id,
                "unit": unit_id,
                "title": f"Synthetic Showcase {event_id}",
                "normalized": f"synthetic showcase {event_id}",
            },
        )
        # Real evidence, so the Attended stage has something honest to cite.
        # Nothing in this slice writes it — see OQ-102.
        conn.execute(
            text(
                "INSERT INTO attendance_record "
                "(id, tenant_id, owning_unit_id, subject_id, event_id, method) "
                "VALUES (:id, :tid, :unit, :subject, :event, 'qr_scan')"
            ),
            {
                "id": attendance_id,
                "tid": tenant_id,
                "unit": unit_id,
                "subject": student_id,
                "event": event_id,
            },
        )
        record_id = _insert_journey(
            conn,
            tenant_id=tenant_id,
            unit_id=unit_id,
            subject_id=student_id,
            event_id=event_id,
        )
        sibling_record_id = _insert_journey(
            conn,
            tenant_id=tenant_id,
            unit_id=sibling_unit_id,
            subject_id=sibling_student_id,
            event_id=event_id,
        )

    verifier = FixtureTokenVerifier()
    verifier.register(token, subject)
    client = TestClient(app)
    client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    client.app.state.token_verifier = verifier

    yield _Context(
        client=client,
        engine=engine,
        tenant_id=tenant_id,
        unit_id=unit_id,
        sibling_unit_id=sibling_unit_id,
        token=token,
        record_id=record_id,
        sibling_record_id=sibling_record_id,
        attendance_id=attendance_id,
        student_id=student_id,
        event_id=event_id,
    )

    with engine.begin() as conn:
        # Child-first: every foreign key on these tables is RESTRICT, so a
        # parent dropped early refuses. `pipeline_record` cites
        # `attendance_record`, which cites `event`, which cites `org_unit`.
        for table in (
            "pipeline_record",
            "attendance_record",
            "event",
            "membership",
            "resource_grant",
            "user_account",
            "org_unit",
            "idempotency_record",
            "rate_limit_counter",
        ):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tenant_id})


# ---------------------------------------------------------------------------
# Reading one journey
# ---------------------------------------------------------------------------


class TestReadOneJourney:
    pytestmark = pytest.mark.integration

    def test_an_unreached_stage_is_null_and_never_zero(self, ctx: _Context) -> None:
        """ADR-0011: the column holds nothing, so the field reports nothing."""
        body = ctx.read().json()
        assert body["current_stage"] == "contacted"
        assert body["confirmed_at"] is None
        assert body["attended_at"] is None
        assert body["member_inquiry_at"] is None
        assert body["attendance_id"] is None

    def test_the_provenance_of_the_match_is_carried_to_the_client(self, ctx: _Context) -> None:
        assert ctx.read().json()["matched_provenance"] == SYNTHETIC_PROVENANCE

    def test_a_record_in_a_sibling_unit_is_a_404_not_a_403(self, ctx: _Context) -> None:
        """A 403 would confirm that an id the caller may not read names a journey."""
        response = ctx.read(ctx.sibling_record_id)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "pipeline_record_not_found"

    def test_an_unknown_record_is_the_same_404(self, ctx: _Context) -> None:
        response = ctx.read(uuid.uuid4())
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "pipeline_record_not_found"

    def test_an_unauthenticated_caller_is_refused(self, ctx: _Context) -> None:
        response = ctx.client.get(
            f"/v1/units/{ctx.unit_id}/pipeline-records/{ctx.record_id}",
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# The advance
# ---------------------------------------------------------------------------


class TestAdvancingStages:
    pytestmark = pytest.mark.integration

    def test_the_whole_walk_from_contacted_to_member_inquiry(self, ctx: _Context) -> None:
        """The point of the slice: three stages a coordinator can actually reach.

        Matched and Contacted were seeded, because nothing in this router may
        write them. Everything after is driven over HTTP.
        """
        confirmed = ctx.advance("confirmed", CONFIRMED_AT)
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["transitioned"] is True
        assert confirmed.json()["record"]["current_stage"] == "confirmed"

        attended = ctx.advance("attended", ATTENDED_AT, attendance_id=str(ctx.attendance_id))
        assert attended.status_code == 200, attended.text
        assert attended.json()["record"]["attendance_id"] == str(ctx.attendance_id)

        inquiry = ctx.advance("member_inquiry", INQUIRY_AT)
        assert inquiry.status_code == 200, inquiry.text
        assert inquiry.json()["record"]["current_stage"] == "member_inquiry"

        stored = ctx.stage_timestamps()
        assert stored["confirmed_at"] == CONFIRMED_AT
        assert stored["attended_at"] == ATTENDED_AT
        assert stored["member_inquiry_at"] == INQUIRY_AT
        assert stored["attended_attendance_id"] == ctx.attendance_id

    def test_skipping_a_stage_is_a_409_naming_the_prerequisite(self, ctx: _Context) -> None:
        response = ctx.advance("attended", ATTENDED_AT, attendance_id=str(ctx.attendance_id))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "pipeline_stage_prerequisite_unmet"
        assert ctx.stage_timestamps()["attended_at"] is None

    def test_back_dating_a_stage_is_a_different_409(self, ctx: _Context) -> None:
        """Two mistakes, two codes: a client can say which one was made."""
        response = ctx.advance("confirmed", MATCHED_AT - timedelta(hours=1))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "pipeline_stage_out_of_order"
        assert ctx.stage_timestamps()["confirmed_at"] is None

    def test_attended_citing_evidence_that_does_not_exist_is_a_409(self, ctx: _Context) -> None:
        """The stage cites attendance; it never creates it."""
        assert ctx.advance("confirmed", CONFIRMED_AT).status_code == 200
        response = ctx.advance("attended", ATTENDED_AT, attendance_id=str(uuid.uuid4()))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "pipeline_attendance_evidence_not_found"
        assert ctx.stage_timestamps()["attended_at"] is None

    def test_attended_without_evidence_is_a_422_from_the_schema(self, ctx: _Context) -> None:
        assert ctx.advance("confirmed", CONFIRMED_AT).status_code == 200
        assert ctx.advance("attended", ATTENDED_AT).status_code == 422

    @pytest.mark.parametrize("stage", ["matched", "contacted"])
    def test_no_route_writes_the_machine_witnessed_stages(self, ctx: _Context, stage: str) -> None:
        """422 from the enum, not 409 from the repository — refused at the wire."""
        assert ctx.advance(stage, CONFIRMED_AT).status_code == 422

    def test_repeating_an_advance_is_idempotent_in_the_data(self, ctx: _Context) -> None:
        """No ``Idempotency-Key``: the column being already set is the guard.

        The second call reports ``transitioned: false`` — it did not write —
        and ``already_reached: true``, which are two different facts and stay
        two fields. The stored timestamp is the first call's, not the second's.
        """
        first = ctx.advance("confirmed", CONFIRMED_AT)
        assert first.json()["transitioned"] is True
        assert first.json()["already_reached"] is False

        second = ctx.advance("confirmed", CONFIRMED_AT + timedelta(hours=6))
        assert second.status_code == 200
        assert second.json()["transitioned"] is False
        assert second.json()["already_reached"] is True
        assert ctx.stage_timestamps()["confirmed_at"] == CONFIRMED_AT

    def test_a_record_in_a_sibling_unit_cannot_be_advanced(self, ctx: _Context) -> None:
        response = ctx.client.post(
            f"/v1/units/{ctx.unit_id}/pipeline-records/{ctx.sibling_record_id}/stages",
            json={"stage": "confirmed", "reached_at": CONFIRMED_AT.isoformat()},
            headers=ctx.headers(),
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "pipeline_record_not_found"

    def test_a_coordinator_cannot_advance_through_a_unit_they_lack(self, ctx: _Context) -> None:
        """The grant is on ``UNIT_PATH``; the sibling contains none of it."""
        response = ctx.client.post(
            f"/v1/units/{ctx.sibling_unit_id}/pipeline-records/{ctx.sibling_record_id}/stages",
            json={"stage": "confirmed", "reached_at": CONFIRMED_AT.isoformat()},
            headers=ctx.headers(),
        )
        assert response.status_code == 403

    def test_an_unauthenticated_caller_writes_nothing(self, ctx: _Context) -> None:
        response = ctx.client.post(
            f"/v1/units/{ctx.unit_id}/pipeline-records/{ctx.record_id}/stages",
            json={"stage": "confirmed", "reached_at": CONFIRMED_AT.isoformat()},
        )
        assert response.status_code == 401
        assert ctx.stage_timestamps()["confirmed_at"] is None
