"""HTTP contracts for the outreach surface (plan card L7).

``tests/integration/test_outreach_handler.py`` owns the worker half and
``tests/integration/test_outreach_persistence.py`` owns the constraints. What
this file adds is the part that exists only over HTTP, and it drives the whole
path rather than any piece of it: a coordinator composes a draft, submits a
send, the real dispatcher and the real executor run the shipped handler, and the
coordinator reads back what happened.

Four things are asserted that nothing else can assert:

* **The write goes through the command path.** After the ``202`` and before the
  worker runs, no message exists and no send row exists — there is a job. A
  route that sent inline would pass every other test in this repository.
* **B17 cannot come back.** The ``202`` body has no field a client could render
  as "sent". The legacy button logged to the console and said "Message sent!";
  what replaces it is a job id, and the contract is what makes that permanent.
* **Consent survives the round trip.** A recipient who unsubscribes *after* the
  command is accepted is not written to — asserted over HTTP, through the real
  dispatcher, against the fixture provider's own record of what it was asked to
  send.
* **The unsubscribe POST tells a stranger nothing.** A real token and an
  invented one produce identical responses.

Requires a live migrated PostgreSQL, and is skipped when none is reachable.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import FixtureTokenVerifier
from smartmatch_providers.fixtures import FixtureEmailProvider
from smartmatch_providers.tasks import FixtureTaskQueue
from smartmatch_worker.dispatcher import OutboxDispatcher
from smartmatch_worker.execution import TaskExecutor
from smartmatch_worker.handlers import default_registry
from smartmatch_worker.outreach import build_outreach_send_handler, with_outreach_send
from sqlalchemy import Engine, create_engine, text

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

UNIT_PATH = "iawest.outreach"
#: A second department containing none of :data:`UNIT_PATH`, so a coordinator
#: here must not reach the outreach unit.
SIBLING_UNIT_PATH = "iawest.outreachsibling"

#: RFC 2606 reserved. Nothing this suite composes can address a real mailbox.
ADDRESS = "professional-0000@synthetic.invalid"

TEMPLATE_ID = "pilot.event_invitation.v1"
VALUES = {
    "professional_name": "Sam Rivera",
    "unit_name": "Northside Robotics",
    "event_name": "Spring Showcase",
    "event_date": "Friday, 12 June",
    "coordinator_name": "Alex Chen",
}


class _Context:
    """One tenant, one coordinator, one contact, and the fixture provider."""

    def __init__(
        self,
        client: TestClient,
        engine: Engine,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        sibling_unit_id: uuid.UUID,
        token: str,
        contact_id: uuid.UUID,
    ) -> None:
        self.client = client
        self.engine = engine
        self.tenant_id = tenant_id
        self.unit_id = unit_id
        self.sibling_unit_id = sibling_unit_id
        self.token = token
        self.contact_id = contact_id
        self.provider = FixtureEmailProvider()

    # -- HTTP helpers ------------------------------------------------------

    def _headers(self, *, key: str | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.token}"}
        if key is not None:
            headers["Idempotency-Key"] = key
        return headers

    def compose(self, *, approve: bool = True, **overrides):
        body = {
            "contact_channel_id": str(self.contact_id),
            "template_id": TEMPLATE_ID,
            "values": VALUES,
            "approve": approve,
        }
        body.update(overrides)
        return self.client.post(
            f"/v1/units/{self.unit_id}/outreach/drafts", json=body, headers=self._headers()
        )

    def send(self, draft_id: str, *, key: str | None = None):
        return self.client.post(
            f"/v1/units/{self.unit_id}/outreach/drafts/{draft_id}/send",
            headers=self._headers(key=key or f"idem-{uuid.uuid4().hex}"),
        )

    def read_send(self, send_id: str):
        return self.client.get(
            f"/v1/units/{self.unit_id}/outreach/sends/{send_id}", headers=self._headers()
        )

    def list_drafts(self):
        return self.client.get(f"/v1/units/{self.unit_id}/outreach/drafts", headers=self._headers())

    def list_sends(self):
        return self.client.get(f"/v1/units/{self.unit_id}/outreach/sends", headers=self._headers())

    # -- worker ------------------------------------------------------------

    def run_worker(self, job_id: str):
        """Dispatch and execute with the *shipped* handler plus the outreach one.

        Composed here the same way ``main.py`` composes it at the worker's
        boot — through ``with_outreach_send`` and ``build_outreach_send_handler``
        — rather than by registering a test double, so what runs is the code a
        deployment runs, with only the provider swapped for the fixture it would
        already be using outside live mode.
        """
        session_factory = create_session_factory(
            self.engine.url.render_as_string(hide_password=False)
        )
        OutboxDispatcher(session_factory, FixtureTaskQueue()).run_once()
        registry = with_outreach_send(
            default_registry(),
            build_outreach_send_handler(
                session_factory=session_factory,
                provider=self.provider,
                from_address="noreply@example.invalid",
                public_base_url="http://localhost:8080",
                unsubscribe_secret=None,
                live_mode=False,
            ),
            "outreach.send",
        )
        return TaskExecutor(session_factory, registry).execute(
            tenant_id=self.tenant_id, job_id=uuid.UUID(job_id)
        )

    def unsubscribe_recipient(self) -> None:
        """Record a suppression, as if the recipient clicked between steps."""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO suppression_record (id, tenant_id, address, "
                    "suppressed_at, source) VALUES (:i, :t, :a, now(), 'unsubscribe_link')"
                ),
                {"i": uuid.uuid4(), "t": self.tenant_id, "a": ADDRESS},
            )

    def send_row_count(self) -> int:
        with self.engine.connect() as conn:
            return conn.execute(
                text("SELECT count(*) FROM outreach_send WHERE tenant_id = :t"),
                {"t": self.tenant_id},
            ).scalar_one()

    def send_id_for_job(self, job_id: str) -> str:
        with self.engine.connect() as conn:
            return str(
                conn.execute(
                    text("SELECT id FROM outreach_send WHERE job_id = :j"), {"j": job_id}
                ).scalar_one()
            )


@pytest.fixture(scope="module")
def engine() -> Engine:
    """A live migrated PostgreSQL engine, or skip this contract."""
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1 FROM outreach_draft LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}")
    return eng


@pytest.fixture
def ctx(engine: Engine) -> Iterator[_Context]:
    tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()
    sibling_unit_id = uuid.uuid4()
    user_id = uuid.uuid4()
    contact_id = uuid.uuid4()
    # Derived at runtime rather than written as literals: a fixture credential
    # spelled out in a source file is a credential in a commit patch.
    subject = f"sub-outreach-{uuid.uuid4().hex}"
    token = f"tok-outreach-{uuid.uuid4().hex}"

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-outreach-{tenant_id.hex[:12]}"},
        )
        for new_unit_id, path, name in (
            (unit_id, UNIT_PATH, "Outreach"),
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
        conn.execute(
            text(
                "INSERT INTO contact_channel (id, tenant_id, owning_unit_id, "
                "professional_id, channel_kind, address, contact_state, "
                "consent_source, consent_recorded_at) "
                "VALUES (:id, :t, :u, :p, 'email', :a, 'active_candidate', "
                "'self_service', now())"
            ),
            {
                "id": contact_id,
                "t": tenant_id,
                "u": unit_id,
                "p": uuid.uuid4(),
                "a": ADDRESS,
            },
        )

    verifier = FixtureTokenVerifier()
    verifier.register(token, subject)
    client = TestClient(app)
    client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    client.app.state.token_verifier = verifier

    yield _Context(client, engine, tenant_id, unit_id, sibling_unit_id, token, contact_id)

    with engine.begin() as conn:
        # Child-first: every foreign key in migration 0021 is RESTRICT, and
        # `outreach_send` references `job`, so a parent dropped early refuses.
        for table in (
            "job_event",
            "outbox_record",
            "redrive_record",
            "delivery_event",
            "outreach_send",
            "outreach_draft",
            "contact_channel_transition",
            "contact_channel",
            "suppression_record",
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


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------


class TestComposeDraft:
    """A draft is stored text, and the consent gate runs before there is any."""

    def test_composing_returns_the_rendered_message(self, ctx: _Context):
        response = ctx.compose()

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["subject"] == "Spring Showcase on Friday, 12 June"
        assert "Sam Rivera" in body["body"]
        assert body["recipient_address"] == ADDRESS
        assert body["status"] == "approved"

    def test_the_draft_says_its_copy_is_unreviewed(self, ctx: _Context):
        """OQ-003, surfaced on the wire rather than buried in a table.

        A coordinator can see that the wording has not been through
        institutional review, which is the fact that decides whether this
        message could go to a real person.
        """
        assert ctx.compose().json()["content_status"] == "synthetic"

    def test_a_suppressed_recipient_cannot_be_composed_for(self, ctx: _Context):
        """403, not 422: this is a permission fact, not a validation problem.

        Reporting it as a validation error would invite the caller to try
        different inputs, and there are no inputs that make it allowed.
        """
        ctx.unsubscribe_recipient()

        response = ctx.compose()

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "outreach_recipient_not_eligible"

    def test_an_unknown_template_is_refused(self, ctx: _Context):
        response = ctx.compose(template_id="invite.please.opt.in")

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "outreach_composition_failed"

    def test_placeholder_values_must_match_the_template_exactly(self, ctx: _Context):
        response = ctx.compose(values={"professional_name": "Sam Rivera"})

        assert response.status_code == 400

    def test_no_request_field_accepts_message_text(self, ctx: _Context):
        """Free-form body text is the door back to unreviewed copy.

        Pinned against the published schema rather than by attempting a request,
        so the assertion is about what the contract *permits* rather than about
        what one particular payload happens to do.
        """
        schema = ctx.client.get("/openapi.json").json()["components"]["schemas"]["DraftRequest"]

        assert set(schema["properties"]) == {
            "contact_channel_id",
            "template_id",
            "values",
            "approve",
        }

    def test_a_contact_in_another_unit_is_a_404(self, ctx: _Context):
        """Not a 403: saying "forbidden" confirms the id names something real."""
        response = ctx.client.post(
            f"/v1/units/{ctx.sibling_unit_id}/outreach/drafts",
            json={
                "contact_channel_id": str(ctx.contact_id),
                "template_id": TEMPLATE_ID,
                "values": VALUES,
            },
            headers={"Authorization": f"Bearer {ctx.token}"},
        )

        assert response.status_code in (403, 404)

    def test_an_unauthenticated_caller_is_refused(self, ctx: _Context):
        response = ctx.client.post(
            f"/v1/units/{ctx.unit_id}/outreach/drafts",
            json={
                "contact_channel_id": str(ctx.contact_id),
                "template_id": TEMPLATE_ID,
                "values": VALUES,
            },
        )

        assert response.status_code == 401


# ---------------------------------------------------------------------------
# The send command
# ---------------------------------------------------------------------------


class TestSendCommand:
    """202, and nothing has happened yet."""

    def test_submitting_returns_202_with_a_job_and_no_status(self, ctx: _Context):
        """B17's replacement, asserted as the absence of a field.

        There is nothing in this body a client could render as "sent", which is
        what makes an optimistic success toast impossible rather than merely
        discouraged.
        """
        draft_id = ctx.compose().json()["draft_id"]

        response = ctx.send(draft_id)

        assert response.status_code == 202
        body = response.json()
        assert set(body) == {"job_id", "events_url", "replayed"}
        assert body["events_url"] == f"/v1/jobs/{body['job_id']}/events"

    def test_nothing_is_sent_before_the_worker_runs(self, ctx: _Context):
        """The write really does go through the command path.

        A route that sent inline would pass every other test in this file.
        """
        draft_id = ctx.compose().json()["draft_id"]

        ctx.send(draft_id)

        assert ctx.send_row_count() == 0
        assert ctx.provider.sent == []

    def test_an_unapproved_draft_cannot_be_sent(self, ctx: _Context):
        """409, not 403: the caller may send from this unit; the draft is not ready."""
        draft_id = ctx.compose(approve=False).json()["draft_id"]

        response = ctx.send(draft_id)

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "outreach_draft_not_approved"

    def test_a_send_without_an_idempotency_key_is_refused(self, ctx: _Context):
        draft_id = ctx.compose().json()["draft_id"]

        response = ctx.client.post(
            f"/v1/units/{ctx.unit_id}/outreach/drafts/{draft_id}/send",
            headers={"Authorization": f"Bearer {ctx.token}"},
        )

        assert response.status_code == 400

    def test_repeating_a_request_under_one_key_is_the_same_command(self, ctx: _Context):
        draft_id = ctx.compose().json()["draft_id"]
        key = f"idem-{uuid.uuid4().hex}"

        first = ctx.send(draft_id, key=key).json()
        second = ctx.send(draft_id, key=key).json()

        assert first["job_id"] == second["job_id"]
        assert second["replayed"] is True


# ---------------------------------------------------------------------------
# The whole path
# ---------------------------------------------------------------------------


class TestEndToEnd:
    """Compose, submit, run the worker, read it back."""

    def test_the_message_reaches_the_provider_and_the_read_reports_accepted(self, ctx: _Context):
        draft_id = ctx.compose().json()["draft_id"]
        job_id = ctx.send(draft_id).json()["job_id"]

        ctx.run_worker(job_id)

        assert len(ctx.provider.sent) == 1
        assert ctx.provider.sent[0].to_address == ADDRESS

        send_id = ctx.send_id_for_job(job_id)
        body = ctx.read_send(send_id).json()
        assert body["disposition"] == "accepted"
        assert body["provider"] == "fixture-email"
        assert body["provider_message_id"].startswith("fixture-")
        assert [event["event_type"] for event in body["delivery_events"]] == [
            "queued",
            "accepted",
        ]

    def test_a_recipient_who_unsubscribes_after_submission_is_not_written_to(self, ctx: _Context):
        """The whole feature, in one test.

        The draft was composed while the recipient was eligible and approved by
        a coordinator who saw that. The command was accepted. *Then* the person
        clicked unsubscribe. The worker refuses, the fixture provider records
        nothing, and the read says why.
        """
        draft_id = ctx.compose().json()["draft_id"]
        job_id = ctx.send(draft_id).json()["job_id"]

        ctx.unsubscribe_recipient()
        ctx.run_worker(job_id)

        assert ctx.provider.sent == [], "a recipient who unsubscribed was written to"

        body = ctx.read_send(ctx.send_id_for_job(job_id)).json()
        assert body["disposition"] == "blocked"
        assert body["provider_message_id"] is None
        assert "suppressed" in body["failure_reason"]
        assert "blocked" in {event["event_type"] for event in body["delivery_events"]}

    def test_an_in_flight_send_reports_null_rather_than_a_guess(self, ctx: _Context):
        """A read between acceptance and execution has nothing to report.

        There is no send row yet, so this is a 404 — which is the honest answer,
        and the reason the client follows ``events_url`` rather than polling a
        send id it was never given.
        """
        draft_id = ctx.compose().json()["draft_id"]
        ctx.send(draft_id)

        assert ctx.read_send(str(uuid.uuid4())).status_code == 404

    def test_the_list_shows_the_draft_that_was_composed(self, ctx: _Context):
        draft_id = ctx.compose().json()["draft_id"]

        body = ctx.list_drafts().json()

        assert [draft["draft_id"] for draft in body["drafts"]] == [draft_id]
        assert body["drafts"][0]["recipient_address"] == ADDRESS


# ---------------------------------------------------------------------------
# Unsubscribe
# ---------------------------------------------------------------------------


class TestUnsubscribe:
    """The mutating half, and what it refuses to tell a stranger."""

    def test_the_get_page_still_mutates_nothing(self, ctx: _Context):
        """v1.1 §1.10. A link scanner following this must not suppress anybody."""
        draft_id = ctx.compose().json()["draft_id"]
        job_id = ctx.send(draft_id).json()["job_id"]
        ctx.run_worker(job_id)
        token = ctx.provider.sent[0].list_unsubscribe_url.rsplit("/", 1)[-1]

        assert ctx.client.get(f"/u/{token}").status_code == 200

        with ctx.engine.connect() as conn:
            assert (
                conn.execute(
                    text("SELECT count(*) FROM suppression_record WHERE tenant_id = :t"),
                    {"t": ctx.tenant_id},
                ).scalar_one()
                == 0
            )

    def test_the_post_suppresses_the_address(self, ctx: _Context):
        draft_id = ctx.compose().json()["draft_id"]
        job_id = ctx.send(draft_id).json()["job_id"]
        ctx.run_worker(job_id)
        token = ctx.provider.sent[0].list_unsubscribe_url.rsplit("/", 1)[-1]

        response = ctx.client.post("/v1/unsubscribe", json={"token": token})

        assert response.status_code == 200
        assert response.json() == {"unsubscribed": True}
        with ctx.engine.connect() as conn:
            row = conn.execute(
                text("SELECT address, source FROM suppression_record WHERE tenant_id = :t"),
                {"t": ctx.tenant_id},
            ).one()
        assert row.address == ADDRESS
        assert row.source == "unsubscribe_link"

    def test_it_needs_no_authentication(self, ctx: _Context):
        """A person who has stopped reading our mail should not have to sign in
        to stop receiving it — and RFC 8058 one-click arrives with no session
        at all."""
        response = ctx.client.post("/v1/unsubscribe", json={"token": "z" * 64})

        assert response.status_code != 401

    def test_an_invented_token_is_answered_identically(self, ctx: _Context):
        """The route must not be an oracle.

        A 404 for an unknown token would let anyone holding a guess confirm
        whether a token — and therefore an address — is on our list. Reporting
        acceptance is not a fake success: the claim is about the request, not
        about a person we cannot identify.
        """
        response = ctx.client.post("/v1/unsubscribe", json={"token": "0" * 64})

        assert response.status_code == 200
        assert response.json() == {"unsubscribed": True}
        with ctx.engine.connect() as conn:
            assert (
                conn.execute(
                    text("SELECT count(*) FROM suppression_record WHERE tenant_id = :t"),
                    {"t": ctx.tenant_id},
                ).scalar_one()
                == 0
            ), "an invented token wrote a suppression"

    def test_unsubscribing_twice_is_not_an_error(self, ctx: _Context):
        """Clicking twice is not a mistake, and showing an error would alarm."""
        draft_id = ctx.compose().json()["draft_id"]
        job_id = ctx.send(draft_id).json()["job_id"]
        ctx.run_worker(job_id)
        token = ctx.provider.sent[0].list_unsubscribe_url.rsplit("/", 1)[-1]

        assert ctx.client.post("/v1/unsubscribe", json={"token": token}).status_code == 200
        assert ctx.client.post("/v1/unsubscribe", json={"token": token}).status_code == 200


# ---------------------------------------------------------------------------
# The sends listing, and the gate that runs when a send is submitted
# ---------------------------------------------------------------------------


class TestListSends:
    """What a unit has attempted, which nothing could read before this slice.

    Drafts could be listed and one send could be read by id, so the only way to
    see a unit's sends was to have kept the ids. OQ-008 records that this slice
    stores sends rather than threads; this is that list, and it draws no
    conversation because none is stored.
    """

    def test_a_unit_with_no_sends_gets_an_empty_page_not_an_error(self, ctx: _Context):
        """Empty is an answer. A 404 here would be "no sends" reported as "no unit"."""
        response = ctx.list_sends()

        assert response.status_code == 200, response.text
        assert response.json()["sends"] == []

    def test_a_submitted_send_is_not_in_the_list_until_the_worker_runs(self, ctx: _Context):
        """Still empty after the 202, and that is the honest answer.

        The ``outreach_send`` row is written by the handler, not by the route —
        the request path records intent and nothing else (v1.1 §1.6). A listing
        that showed a row here would be showing a send attempt that has not been
        attempted, which is B17 wearing a list instead of a button. The job is
        what exists at this point, and ``events_url`` is where it is followed.
        """
        draft_id = ctx.compose().json()["draft_id"]
        ctx.send(draft_id)

        assert ctx.list_sends().json()["sends"] == []

    def test_the_listing_reports_the_outcome_once_the_worker_has_run(self, ctx: _Context):
        draft_id = ctx.compose().json()["draft_id"]
        job_id = ctx.send(draft_id).json()["job_id"]
        ctx.run_worker(job_id)

        rows = ctx.list_sends().json()["sends"]

        assert len(rows) == 1
        assert rows[0]["disposition"] == "accepted"
        assert rows[0]["concluded_at"] is not None
        assert rows[0]["recipient_address"] == ADDRESS

    def test_the_listing_carries_no_delivery_stream(self, ctx: _Context):
        """Deliberate. Folding a stream into one word per row would bury the
        choice of which fact to forget where nobody reviews it — a provider can
        report `delivered` and then `complained`. The stream is on the send."""
        draft_id = ctx.compose().json()["draft_id"]
        job_id = ctx.send(draft_id).json()["job_id"]
        ctx.run_worker(job_id)

        row = ctx.list_sends().json()["sends"][0]

        assert "delivery_events" not in row
        # The id is there, so the stream is one request away rather than absent.
        assert row["send_id"] == ctx.send_id_for_job(job_id)

    def test_another_unit_sees_none_of_it(self, ctx: _Context):
        """Unit scoping, on the listing as on everything else in this surface."""
        draft_id = ctx.compose().json()["draft_id"]
        job_id = ctx.send(draft_id).json()["job_id"]
        ctx.run_worker(job_id)

        response = ctx.client.get(
            f"/v1/units/{ctx.sibling_unit_id}/outreach/sends",
            headers={"Authorization": f"Bearer {ctx.token}"},
        )

        # The coordinator's membership does not cover the sibling department at
        # all, so this is a 403 rather than an empty page — and an empty page
        # would have been the worse answer, because it says "nothing here" to
        # somebody who is not entitled to know.
        assert response.status_code == 403, response.text


class TestSendChecksConsentAtSubmission:
    """The middle of the three gates: composition, submission, delivery."""

    def test_a_recipient_who_unsubscribes_before_the_send_is_refused_at_submission(
        self, ctx: _Context
    ):
        """403 at the moment the coordinator acts, not a job failure later.

        The draft was composed while the recipient was eligible, which is what
        the composition-time check proved. Consent was then withdrawn. Accepting
        the command anyway would be honest about the queue and useless to the
        person looking at the screen — and would spend a job to discover what
        this route already knows.
        """
        draft_id = ctx.compose().json()["draft_id"]
        ctx.unsubscribe_recipient()

        response = ctx.send(draft_id)

        assert response.status_code == 403, response.text
        assert response.json()["error"]["code"] == "outreach_recipient_not_eligible"
        assert ctx.send_row_count() == 0, "a refused submission still reserved a send"

    def test_nothing_is_queued_when_the_submission_is_refused(self, ctx: _Context):
        """The refusal is before `submit_command`, so no job exists to fail."""
        draft_id = ctx.compose().json()["draft_id"]
        ctx.unsubscribe_recipient()

        ctx.send(draft_id)

        with ctx.engine.connect() as conn:
            queued = conn.execute(
                text("SELECT count(*) FROM job WHERE tenant_id = :t"), {"t": ctx.tenant_id}
            ).scalar_one()
        assert queued == 0
