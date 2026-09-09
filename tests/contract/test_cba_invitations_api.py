"""HTTP contracts for speaker invitations (customer §6 steps 7-8, §13, §14).

``tests/integration/test_cba_invitation_batch.py`` owns the constraints and the
repository. What this file adds is the part that exists only over HTTP, and it is
mostly about **what a Connector is told**, because on this surface the response
body is the product:

* A batch reports every name it was given, invited or skipped, with a reason.
  Silently returning nine outcomes for twelve names is the failure this whole
  card is arranged against, so it is asserted directly.
* ``delivery`` and ``speaker_response`` arrive as two nested objects with
  disjoint vocabularies. A client cannot reach a provider's ``accepted`` through
  a field that also carries a Speaker's answer, because there is no such field.
* A replayed batch invites nobody a second time, and says so.

Every write is also asserted **against the table**, not only against the status
code. ``get_session`` rolls back unconditionally, so a route that forgot to
commit would return a clean ``201`` having stored nothing — a defect three tracks
in this repository have shipped, and one a response-only assertion cannot see.

Requires a live migrated PostgreSQL, and is skipped when none is reachable.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_domain.cba_invitations import DELIVERY_VOCABULARY, SPEAKER_RESPONSE_VALUES
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Engine, create_engine, text

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

UNIT_PATH = "iawest.invites"

#: A second department containing none of :data:`UNIT_PATH`, so a batch composed
#: there must not be reachable from the unit under test.
SIBLING_UNIT_PATH = "iawest.invitessibling"

#: The date as a Connector types it, and the reason the column is Text: this
#: string is rendered into the message verbatim and never parsed.
EVENT_DATE = "Friday, 12 June"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class _Context:
    """One tenant, one Connector, two units, and a roster to invite from."""

    def __init__(
        self,
        client: TestClient,
        engine: Engine,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        sibling_unit_id: uuid.UUID,
        token: str,
    ) -> None:
        self.client = client
        self.engine = engine
        self.tenant_id = tenant_id
        self.unit_id = unit_id
        self.sibling_unit_id = sibling_unit_id
        self.token = token

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    # -- set-up helpers ----------------------------------------------------

    def roster_contact(
        self,
        *,
        name: str,
        contact_state: str | None = "active_candidate",
        unit_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Put somebody on a unit's §13 roster, optionally with a channel.

        ``contact_state=None`` means a roster entry with **no channel at all** —
        the ordinary state of a contact added through the §13 form, which writes
        none (OQ-CBA-011). It is the case a batch has to skip with a reason
        rather than fail on.
        """
        professional_id = uuid.uuid4()
        owning = unit_id or self.unit_id
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                    "VALUES (:id, :t, :s, :e)"
                ),
                {
                    "id": professional_id,
                    "t": self.tenant_id,
                    "s": f"sub-speaker-{professional_id.hex}",
                    "e": f"{professional_id.hex[:8]}@example.invalid",
                },
            )
            conn.execute(
                text(
                    "INSERT INTO speaker_profile (tenant_id, professional_id, "
                    "owning_unit_id, full_name) VALUES (:t, :p, :u, :n)"
                ),
                {"t": self.tenant_id, "p": professional_id, "u": owning, "n": name},
            )
            if contact_state is not None:
                conn.execute(
                    text(
                        "INSERT INTO contact_channel (id, tenant_id, owning_unit_id, "
                        "professional_id, channel_kind, address, contact_state, "
                        "consent_source, consent_recorded_at) VALUES (:id, :t, :u, :p, "
                        "'email', :a, :s, 'self_service', now())"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "t": self.tenant_id,
                        "u": owning,
                        "p": professional_id,
                        "a": self.address_of(professional_id),
                        "s": contact_state,
                    },
                )
        return professional_id

    def address_of(self, professional_id: uuid.UUID) -> str:
        return f"speaker-{professional_id.hex[:8]}@synthetic.invalid"

    def suppress(self, address: str) -> None:
        """Record an unsubscribe, as if it arrived between two steps."""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO suppression_record (id, tenant_id, address, "
                    "suppressed_at, source) VALUES (:i, :t, :a, now(), 'unsubscribe_link')"
                ),
                {"i": uuid.uuid4(), "t": self.tenant_id, "a": address},
            )

    def stored(self, invitation_id: str) -> Any:
        """One invitation row, read straight from the table."""
        with self.engine.begin() as conn:
            return conn.execute(
                text(
                    "SELECT status, skip_reason, response_status, response_channel, "
                    "response_recorded_at, outreach_send_job_id, recipient_address "
                    "FROM cba_invitation WHERE id = :i"
                ),
                {"i": invitation_id},
            ).one()

    def count_invitations(self) -> int:
        with self.engine.begin() as conn:
            return int(
                conn.execute(
                    text("SELECT count(*) FROM cba_invitation WHERE tenant_id = :t"),
                    {"t": self.tenant_id},
                ).scalar_one()
            )

    def set_response_token(self, invitation_id: str, token: str) -> None:
        """Plant a known token on a stored invitation.

        The route mints the token and puts it only in the message, which is
        correct and makes the Speaker's own path untestable over HTTP without
        this. Writing the *hash* directly is the honest way in: the test learns
        nothing the database would tell it, and the route still has to do the
        matching.
        """
        with self.engine.begin() as conn:
            conn.execute(
                text("UPDATE cba_invitation SET response_token_hash = :h WHERE id = :i"),
                {"h": _token_hash(token), "i": invitation_id},
            )

    # -- request helpers ---------------------------------------------------

    def create_batch(
        self,
        professional_ids: list[uuid.UUID],
        *,
        key: str | None = "batch-key-1",
        unit_id: uuid.UUID | None = None,
        **overrides: Any,
    ):
        body: dict[str, Any] = {
            "professional_ids": [str(pid) for pid in professional_ids],
            "event_name": "Spring Showcase",
            "event_date": EVENT_DATE,
            "coordinator_name": "Dana Okafor",
        }
        body.update(overrides)
        headers = dict(self._headers)
        if key is not None:
            headers["Idempotency-Key"] = key
        return self.client.post(
            f"/v1/units/{unit_id or self.unit_id}/speaker-invitations/batches",
            json=body,
            headers=headers,
        )

    def dispatch(self, batch_id: str, *, unit_id: uuid.UUID | None = None):
        return self.client.post(
            f"/v1/units/{unit_id or self.unit_id}/speaker-invitations/batches/{batch_id}/dispatch",
            headers=self._headers,
        )

    def read_batch(self, batch_id: str, *, unit_id: uuid.UUID | None = None):
        return self.client.get(
            f"/v1/units/{unit_id or self.unit_id}/speaker-invitations/batches/{batch_id}",
            headers=self._headers,
        )

    def list_batches(self):
        return self.client.get(
            f"/v1/units/{self.unit_id}/speaker-invitations/batches", headers=self._headers
        )

    def record(self, invitation_id: str, response: str):
        return self.client.post(
            f"/v1/units/{self.unit_id}/speaker-invitations/{invitation_id}/response",
            json={"response": response},
            headers=self._headers,
        )

    def respond(self, token: str, response: str):
        """The Speaker's own answer. No Authorization header, deliberately."""
        return self.client.post(
            "/v1/speaker-invitations/respond", json={"token": token, "response": response}
        )


@pytest.fixture(scope="module")
def engine() -> Engine:
    """A live migrated PostgreSQL engine, or skip this contract."""
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1 FROM cba_invitation LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}")
    return eng


@pytest.fixture
def ctx(engine: Engine) -> Iterator[_Context]:
    tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()
    sibling_unit_id = uuid.uuid4()
    user_id = uuid.uuid4()
    # Derived at runtime rather than written as literals: a fixture credential
    # spelled out in a source file is a credential in a commit patch.
    subject = f"sub-invites-{uuid.uuid4().hex}"
    token = f"tok-invites-{uuid.uuid4().hex}"

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-invites-{tenant_id.hex[:12]}"},
        )
        for new_unit_id, path, name in (
            (unit_id, UNIT_PATH, "Northside Robotics"),
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
        # Rooted at `iawest`, so the same Connector covers both departments. The
        # sibling unit is here to prove *unit* scoping of the batch rows, not to
        # test authorization, which `tests/authz` owns.
        conn.execute(
            text(
                "INSERT INTO membership (id, tenant_id, user_id, granted_path, role) "
                "VALUES (:id, :tid, :uid, CAST('iawest' AS ltree), 'coordinator')"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "uid": user_id},
        )

    verifier = FixtureTokenVerifier()
    verifier.register(token, subject)
    client = TestClient(app)
    client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    client.app.state.token_verifier = verifier

    yield _Context(client, engine, tenant_id, unit_id, sibling_unit_id, token)

    with engine.begin() as conn:
        # Child-first: every foreign key in 0021 and 0029 is RESTRICT.
        for table in (
            "cba_invitation",
            "cba_invitation_batch",
            "delivery_event",
            "outreach_send",
            "outreach_draft",
            "contact_channel_transition",
            "contact_channel",
            "suppression_record",
            "job_event",
            "job",
            "idempotency_record",
            "speaker_profile",
            "membership",
            "user_account",
            "org_unit",
            "rate_limit_counter",
        ):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tenant_id})


# ---------------------------------------------------------------------------
# Composing a batch
# ---------------------------------------------------------------------------


class TestComposeBatch:
    """Every name comes back, and the ones nobody wrote to say why."""

    def test_an_eligible_recipient_is_invited_and_stored(self, ctx: _Context):
        professional_id = ctx.roster_contact(name="Sam Rivera")

        response = ctx.create_batch([professional_id])

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["replayed"] is False
        assert body["invited_count"] == 1
        assert body["skipped_count"] == 0
        assert body["template_id"] == "cba.speaker_invitation.v1"
        # The date is echoed exactly as typed, not normalised into an ISO string
        # nobody asked for.
        assert body["event_date"] == EVENT_DATE

        outcome = body["invitations"][0]
        assert outcome["status"] == "pending"
        assert outcome["recipient_address"] == ctx.address_of(professional_id)

        # Against the table, not the status code: a route that forgot to commit
        # would have answered 201 with all of the above and stored nothing.
        stored = ctx.stored(outcome["invitation_id"])
        assert stored.status == "pending"
        assert stored.recipient_address == ctx.address_of(professional_id)

    def test_every_named_recipient_produces_an_outcome(self, ctx: _Context):
        """The assertion this card exists to make. A batch never shrinks.

        Four names, one of which can be invited. A response carrying one entry
        would tell a Connector that one person was invited and nothing about the
        three who were not — and those three are the ones needing a decision.
        """
        invitable = ctx.roster_contact(name="Sam Rivera")
        no_channel = ctx.roster_contact(name="Ada Chen", contact_state=None)
        not_activated = ctx.roster_contact(name="Lee Park", contact_state="consented")
        stranger = uuid.uuid4()

        body = ctx.create_batch([invitable, no_channel, not_activated, stranger]).json()

        assert len(body["invitations"]) == 4
        assert body["invited_count"] == 1
        assert body["skipped_count"] == 3

        by_professional = {entry["professional_id"]: entry for entry in body["invitations"]}
        assert by_professional[str(invitable)]["skip_reason"] is None
        assert by_professional[str(no_channel)]["skip_reason"] == "no_contact_channel"
        assert by_professional[str(not_activated)]["skip_reason"] == "channel_not_active_candidate"
        assert by_professional[str(stranger)]["skip_reason"] == "not_on_roster"

    def test_a_suppressed_address_is_skipped_and_says_so(self, ctx: _Context):
        """Suppression outranks everything, and the reason names it.

        Reported as ``channel_suppressed`` rather than as a generic ineligibility
        because the two need different actions from a Connector: one is a person
        who has told us to stop, and nothing they do to the roster changes that.
        """
        professional_id = ctx.roster_contact(name="Sam Rivera")
        ctx.suppress(ctx.address_of(professional_id))

        body = ctx.create_batch([professional_id]).json()

        assert body["invitations"][0]["skip_reason"] == "channel_suppressed"
        assert body["invited_count"] == 0

    def test_composing_a_batch_does_not_advance_anybodys_consent(self, ctx: _Context):
        """Track 19's loophole stays closed.

        The tempting bug is to "activate" a consented contact so the invitation
        can go out. This asserts the contact is exactly where it was: an
        invitation is not a consent event, and being invited must never be what
        makes somebody invitable.
        """
        professional_id = ctx.roster_contact(name="Lee Park", contact_state="consented")

        ctx.create_batch([professional_id])

        with ctx.engine.begin() as conn:
            state = conn.execute(
                text("SELECT contact_state FROM contact_channel WHERE professional_id = :p"),
                {"p": professional_id},
            ).scalar_one()
        assert state == "consented"

    def test_a_duplicate_name_is_refused_rather_than_folded(self, ctx: _Context):
        """Refused, and the repeated id is named.

        A batch holds one outcome per person, so a repeat has no second outcome
        to report. Quietly dropping it would hand back a shorter list than the
        one submitted — which is the silent shrink this surface is arranged
        against — so the request is refused and nothing is composed.
        """
        professional_id = ctx.roster_contact(name="Sam Rivera")

        response = ctx.create_batch([professional_id, professional_id])

        assert response.status_code == 400, response.text
        error = response.json()["error"]
        assert error["code"] == "speaker_invitation_duplicate_recipient"
        # Named, so a Connector does not have to re-read twelve UUIDs to find it.
        assert str(professional_id) in error["message"]
        assert ctx.count_invitations() == 0

    def test_a_missing_idempotency_key_is_refused(self, ctx: _Context):
        professional_id = ctx.roster_contact(name="Sam Rivera")

        response = ctx.create_batch([professional_id], key=None)

        assert response.status_code == 400, response.text
        assert response.json()["error"]["code"] == "idempotency_key_required"
        assert ctx.count_invitations() == 0


class TestBatchIsIdempotent:
    """A Connector who double-clicks has not written to anybody twice."""

    def test_a_replay_invites_nobody_and_says_so(self, ctx: _Context):
        professional_id = ctx.roster_contact(name="Sam Rivera")
        first = ctx.create_batch([professional_id], key="the-same-key").json()

        second = ctx.create_batch([professional_id], key="the-same-key")

        assert second.status_code == 201, second.text
        body = second.json()
        assert body["replayed"] is True
        assert body["batch_id"] == first["batch_id"]
        # The same invitation, not a second one with the same recipient.
        assert [entry["invitation_id"] for entry in body["invitations"]] == [
            entry["invitation_id"] for entry in first["invitations"]
        ]
        assert ctx.count_invitations() == 1

    def test_a_replay_reports_the_first_submissions_outcomes(self, ctx: _Context):
        """Not a recomputation, which would answer a different question.

        The second request names a different person and a different event. What
        comes back is the first submission's, because the key is the promise that
        the retry is the same act — and because eligibility may have moved since,
        so recomputing would silently answer about a different world.
        """
        first_person = ctx.roster_contact(name="Sam Rivera")
        second_person = ctx.roster_contact(name="Ada Chen")
        first = ctx.create_batch([first_person], key="k").json()

        body = ctx.create_batch(
            [second_person], key="k", event_name="Some other event entirely"
        ).json()

        assert body["event_name"] == "Spring Showcase"
        assert [entry["professional_id"] for entry in body["invitations"]] == [
            entry["professional_id"] for entry in first["invitations"]
        ]

    def test_a_different_key_composes_a_second_batch(self, ctx: _Context):
        """Inviting the same person to a second event is a real thing to do."""
        professional_id = ctx.roster_contact(name="Sam Rivera")
        ctx.create_batch([professional_id], key="k1")

        second = ctx.create_batch([professional_id], key="k2").json()

        assert second["replayed"] is False
        assert ctx.count_invitations() == 2


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


class TestDispatch:
    """Submitting sends, rechecking consent, and never sending twice."""

    def _one_pending(self, ctx: _Context) -> tuple[str, str, uuid.UUID]:
        professional_id = ctx.roster_contact(name="Sam Rivera")
        batch = ctx.create_batch([professional_id]).json()
        return batch["batch_id"], batch["invitations"][0]["invitation_id"], professional_id

    def test_a_dispatch_submits_a_command_and_sends_nothing(self, ctx: _Context):
        """202, a job id, and no field a client could render as "sent"."""
        batch_id, invitation_id, _ = self._one_pending(ctx)

        response = ctx.dispatch(batch_id)

        assert response.status_code == 202, response.text
        body = response.json()
        assert len(body["dispatched"]) == 1
        assert body["not_dispatched"] == []
        entry = body["dispatched"][0]
        assert entry["invitation_id"] == invitation_id
        assert entry["events_url"] == f"/v1/jobs/{entry['job_id']}/events"
        # Nothing in this response says a message went anywhere.
        assert "disposition" not in entry
        assert "sent" not in body

        stored = ctx.stored(invitation_id)
        assert stored.status == "dispatched"
        assert str(stored.outreach_send_job_id) == entry["job_id"]
        # And the Speaker has still said nothing.
        assert stored.response_status == "awaiting_response"

    def test_a_second_dispatch_submits_nothing(self, ctx: _Context):
        batch_id, invitation_id, _ = self._one_pending(ctx)
        first = ctx.dispatch(batch_id).json()

        second = ctx.dispatch(batch_id)

        assert second.status_code == 202
        assert second.json()["dispatched"] == []
        assert second.json()["not_dispatched"] == []
        # The original job stands; no second command was queued for this person.
        stored = ctx.stored(invitation_id)
        assert str(stored.outreach_send_job_id) == first["dispatched"][0]["job_id"]

    def test_consent_withdrawn_after_composing_stops_the_dispatch(self, ctx: _Context):
        """The recheck the card requires, and the window it closes.

        The batch was composed while the contact was invitable. The person
        unsubscribed afterwards. Nothing may be submitted for them now, and the
        Connector is told which invitation and why rather than discovering it in
        a job log.
        """
        batch_id, invitation_id, professional_id = self._one_pending(ctx)
        ctx.suppress(ctx.address_of(professional_id))

        body = ctx.dispatch(batch_id).json()

        assert body["dispatched"] == []
        assert body["not_dispatched"] == [
            {"invitation_id": invitation_id, "reason": "channel_suppressed"}
        ]
        # Still pending, not skipped: nothing was sent, and resolving the reason
        # and dispatching again must work rather than requiring a new batch.
        stored = ctx.stored(invitation_id)
        assert stored.status == "pending"
        assert stored.outreach_send_job_id is None

    def test_a_batch_from_another_unit_is_not_dispatchable_here(self, ctx: _Context):
        professional_id = ctx.roster_contact(name="Sam Rivera")
        batch = ctx.create_batch([professional_id]).json()

        response = ctx.dispatch(batch["batch_id"], unit_id=ctx.sibling_unit_id)

        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "speaker_invitation_batch_not_found"


# ---------------------------------------------------------------------------
# Tracking: the two facts, kept apart
# ---------------------------------------------------------------------------


class TestTrackingKeepsTheTwoFactsApart:
    """§13's tracking view. The reason this card exists."""

    def test_delivery_and_response_are_separate_objects(self, ctx: _Context):
        professional_id = ctx.roster_contact(name="Sam Rivera")
        batch = ctx.create_batch([professional_id]).json()
        ctx.dispatch(batch["batch_id"])

        outcome = ctx.read_batch(batch["batch_id"]).json()["invitations"][0]

        # Two objects, and no third field that could carry either fact.
        assert set(outcome) == {
            "invitation_id",
            "professional_id",
            "status",
            "skip_reason",
            "recipient_address",
            "delivery",
            "speaker_response",
        }
        # The command is queued and no worker has run, so there is no send row
        # yet. That is an absence, not a failure, and it is reported as null.
        assert outcome["delivery"] is None
        assert outcome["speaker_response"]["response"] == "awaiting_response"
        assert outcome["speaker_response"]["recorded_at"] is None

    def test_the_response_value_is_never_a_delivery_word(self, ctx: _Context):
        """Held over the live enums, so a value added to either is caught here."""
        professional_id = ctx.roster_contact(name="Sam Rivera")
        batch = ctx.create_batch([professional_id]).json()
        ctx.dispatch(batch["batch_id"])
        invitation_id = batch["invitations"][0]["invitation_id"]
        ctx.record(invitation_id, "accept")

        outcome = ctx.read_batch(batch["batch_id"]).json()["invitations"][0]

        response = outcome["speaker_response"]["response"]
        assert response == "accepted_invitation"
        assert response in SPEAKER_RESPONSE_VALUES
        assert response not in DELIVERY_VOCABULARY
        # The word a provider would use is not what a Speaker's acceptance says.
        assert response != "accepted"

    def test_a_batch_from_another_unit_is_not_readable_here(self, ctx: _Context):
        professional_id = ctx.roster_contact(name="Sam Rivera")
        batch = ctx.create_batch([professional_id]).json()

        response = ctx.read_batch(batch["batch_id"], unit_id=ctx.sibling_unit_id)

        assert response.status_code == 404, response.text

    def test_the_listing_carries_no_outcomes(self, ctx: _Context):
        """A batch summary does not fold twelve outcomes into one word."""
        professional_id = ctx.roster_contact(name="Sam Rivera")
        ctx.create_batch([professional_id])

        body = ctx.list_batches().json()

        assert len(body["batches"]) == 1
        assert "invitations" not in body["batches"][0]
        assert body["batches"][0]["event_date"] == EVENT_DATE


# ---------------------------------------------------------------------------
# Answers
# ---------------------------------------------------------------------------


class TestConnectorRecordedResponse:
    """What a Speaker said on the phone, entered by the person they told."""

    def _dispatched(self, ctx: _Context) -> str:
        professional_id = ctx.roster_contact(name="Sam Rivera")
        batch = ctx.create_batch([professional_id]).json()
        ctx.dispatch(batch["batch_id"])
        return str(batch["invitations"][0]["invitation_id"])

    def test_an_answer_is_recorded_with_its_channel_and_its_witness(self, ctx: _Context):
        invitation_id = self._dispatched(ctx)

        response = ctx.record(invitation_id, "accept")

        assert response.status_code == 200, response.text
        assert response.json()["recorded"] is True
        assert response.json()["response"] == "accepted_invitation"

        stored = ctx.stored(invitation_id)
        assert stored.response_status == "accepted_invitation"
        # A coordinator's entry is a weaker evidentiary claim than a Speaker's
        # own click, and the row says which it was rather than showing them alike.
        assert stored.response_channel == "connector_recorded"
        assert stored.response_recorded_at is not None

    def test_repeating_the_same_answer_succeeds_and_writes_nothing(self, ctx: _Context):
        invitation_id = self._dispatched(ctx)
        ctx.record(invitation_id, "accept")
        first_time = ctx.stored(invitation_id).response_recorded_at

        response = ctx.record(invitation_id, "accept")

        assert response.status_code == 200
        assert response.json()["recorded"] is False
        # The time of the *first* answer stands rather than being redated.
        assert ctx.stored(invitation_id).response_recorded_at == first_time

    def test_a_different_second_answer_is_refused(self, ctx: _Context):
        """An acceptance an Event Host may already have booked a room on."""
        invitation_id = self._dispatched(ctx)
        ctx.record(invitation_id, "accept")

        response = ctx.record(invitation_id, "decline")

        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "speaker_invitation_already_answered"
        assert ctx.stored(invitation_id).response_status == "accepted_invitation"

    def test_an_undispatched_invitation_cannot_be_answered(self, ctx: _Context):
        """Nothing was sent, so there is no invitation to have answered."""
        professional_id = ctx.roster_contact(name="Sam Rivera")
        batch = ctx.create_batch([professional_id]).json()
        invitation_id = batch["invitations"][0]["invitation_id"]

        response = ctx.record(invitation_id, "accept")

        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "speaker_invitation_not_dispatched"
        assert ctx.stored(invitation_id).response_status == "awaiting_response"

    def test_an_invitation_in_another_unit_is_not_answerable_here(self, ctx: _Context):
        professional_id = ctx.roster_contact(name="Elsewhere", unit_id=ctx.sibling_unit_id)
        batch = ctx.create_batch([professional_id], unit_id=ctx.sibling_unit_id).json()
        ctx.dispatch(batch["batch_id"], unit_id=ctx.sibling_unit_id)

        response = ctx.record(batch["invitations"][0]["invitation_id"], "accept")

        assert response.status_code == 404, response.text


class TestSpeakerRespondsThemselves:
    """§14, over the link in the message. Unauthenticated by design."""

    def _dispatched_with_token(self, ctx: _Context) -> tuple[str, str]:
        professional_id = ctx.roster_contact(name="Sam Rivera")
        batch = ctx.create_batch([professional_id]).json()
        ctx.dispatch(batch["batch_id"])
        invitation_id = str(batch["invitations"][0]["invitation_id"])
        token = secrets.token_urlsafe(32)
        ctx.set_response_token(invitation_id, token)
        return invitation_id, token

    def test_a_speakers_answer_needs_no_credential(self, ctx: _Context):
        """A roster contact is not an account, so requiring a session would make
        this route unreachable by the only person it exists for."""
        invitation_id, token = self._dispatched_with_token(ctx)

        response = ctx.respond(token, "accept")

        assert response.status_code == 200, response.text
        assert response.json()["recorded"] is True

        stored = ctx.stored(invitation_id)
        assert stored.response_status == "accepted_invitation"
        # Their own click, and no coordinator is named as having witnessed it.
        assert stored.response_channel == "speaker_link"

    def test_an_invented_token_is_answered_identically_and_writes_nothing(self, ctx: _Context):
        """The anti-oracle rule. A 404 here would confirm who was invited."""
        invitation_id, _ = self._dispatched_with_token(ctx)

        response = ctx.respond(secrets.token_urlsafe(32), "accept")

        assert response.status_code == 200
        assert response.json() == {"recorded": True}
        assert ctx.stored(invitation_id).response_status == "awaiting_response"

    def test_a_second_different_answer_is_refused_without_saying_so(self, ctx: _Context):
        """Telling a stranger a token has been used is telling them it is real."""
        invitation_id, token = self._dispatched_with_token(ctx)
        ctx.respond(token, "accept")

        response = ctx.respond(token, "decline")

        assert response.status_code == 200
        assert response.json() == {"recorded": True}
        assert ctx.stored(invitation_id).response_status == "accepted_invitation"

    def test_declining_is_not_an_unsubscribe(self, ctx: _Context):
        """Two separate lifecycles, and this is where they would get merged.

        Somebody who cannot make one date is still a consented contact who may be
        invited to a different event. Suppressing them here would silently turn
        one decline into a permanent removal from every future shortlist — and
        the person never asked for that. The unsubscribe link is in the same
        message for those who did.
        """
        professional_id = ctx.roster_contact(name="Sam Rivera")
        batch = ctx.create_batch([professional_id]).json()
        ctx.dispatch(batch["batch_id"])
        invitation_id = str(batch["invitations"][0]["invitation_id"])
        token = secrets.token_urlsafe(32)
        ctx.set_response_token(invitation_id, token)

        ctx.respond(token, "decline")

        with ctx.engine.begin() as conn:
            suppressions = conn.execute(
                text("SELECT count(*) FROM suppression_record WHERE tenant_id = :t"),
                {"t": ctx.tenant_id},
            ).scalar_one()
            state = conn.execute(
                text("SELECT contact_state FROM contact_channel WHERE professional_id = :p"),
                {"p": professional_id},
            ).scalar_one()

        assert suppressions == 0
        assert state == "active_candidate"
        assert ctx.stored(invitation_id).response_status == "declined_invitation"
