"""HTTP contracts for the §13 roster's contact-channel surface.

``tests/authz/test_policy_matrix.py`` owns the authorization rectangle for all
three operations and needs no database to run it.
``tests/integration/test_contact_lifecycle.py`` owns what actually reaches the
tables. What this file adds is the part that exists only over HTTP, and it is
mostly about **which refusal a caller gets**, because on this surface the status
code carries the meaning:

* Creating an ``active_candidate``, or naming a research source as consent, is a
  ``403``. No sequence of legal inputs fixes either, and reporting them as
  validation would invite the caller to try other values until one worked.
* An illegal edge is a ``409``. The caller may work with this channel; the
  channel is not in a state where the move means anything.
* A suppressed address is a ``409`` on both surfaces that could otherwise get
  past it — the create and the escalating transition.
* A person who is not on this unit's roster is a ``404``, identical to one who
  does not exist, so the refusal confirms nothing about ids the caller may not
  read.

The other thing only HTTP can show, and the reason this file leads with it: a
contact added through §13's own form arrives here with **no channels at all**.
That is OQ-CBA-011's posture made visible — the address a Connector typed into
the create form is not here, because it was never stored — and it is the fact
that makes the rest of this surface a deliberate second act rather than a
formality.

Requires a live migrated PostgreSQL, and is skipped when none is reachable.
Every address literal is on the RFC 2606 reserved ``.invalid`` TLD, so a defect
that persisted and later sent one could not reach a real mailbox.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Engine, create_engine, text

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

UNIT_PATH = "iawest.channels"
#: A second department holding none of :data:`UNIT_PATH`. A roster contact
#: registered there must not be reachable through the unit under test, and its
#: channels must not be either.
SIBLING_UNIT_PATH = "iawest.channelssibling"

FULL_NAME = "Dana Reyes"

#: RFC 2606 reserved. Nothing this suite records can address a real mailbox.
ADDRESS = "dana.reyes@synthetic.invalid"
SECOND_ADDRESS = "dana.reyes.alt@synthetic.invalid"
SUPPRESSED_ADDRESS = "stop.writing@synthetic.invalid"

#: What a Connector would type into §13's create form. Recognised, never
#: persisted, reported in ``withheld_fields`` — and therefore absent from this
#: surface until somebody records it here on purpose.
TYPED_CONTACT_EMAIL = "dana.reyes@example.invalid"

EVIDENCE = "signed consent form, filed 2026-09-05"


class _Context:
    """One tenant, one Speaker Connector, two units, and one roster contact."""

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

    # -- the §13 roster, which is this surface's precondition ---------------

    def add_roster_contact(
        self, *, unit_id: uuid.UUID | None = None, full_name: str = FULL_NAME, **overrides: Any
    ) -> str:
        """Add one §13 contact through its own route and return its id.

        Created over HTTP rather than inserted, deliberately: the guarantee this
        file opens with — that the roster create writes no channel — is only
        worth asserting if the contact really came through that route.
        """
        body: dict[str, Any] = {
            "full_name": full_name,
            "topic_text": "Financial modelling for early-career analysts.",
            "location_city": "Pomona",
        }
        body.update(overrides)
        response = self.client.post(
            f"/v1/units/{unit_id or self.unit_id}/speaker-contacts",
            json=body,
            headers=self._headers,
        )
        assert response.status_code == 201, response.text
        professional_id: str = response.json()["professional_id"]
        return professional_id

    # -- the surface under test --------------------------------------------

    def create_channel(
        self,
        professional_id: str,
        *,
        unit_id: uuid.UUID | None = None,
        **overrides: Any,
    ):
        body: dict[str, Any] = {"address": ADDRESS, "contact_state": "discovered"}
        body.update(overrides)
        return self.client.post(
            f"/v1/units/{unit_id or self.unit_id}/speaker-contacts/{professional_id}/channels",
            json=body,
            headers=self._headers,
        )

    def create_consented_channel(self, professional_id: str, **overrides: Any):
        return self.create_channel(
            professional_id,
            contact_state="consented",
            consent_source="in_person",
            consent_evidence=EVIDENCE,
            **overrides,
        )

    def list_channels(self, professional_id: str, *, unit_id: uuid.UUID | None = None):
        return self.client.get(
            f"/v1/units/{unit_id or self.unit_id}/speaker-contacts/{professional_id}/channels",
            headers=self._headers,
        )

    def transition(
        self,
        professional_id: str,
        channel_id: str,
        *,
        unit_id: uuid.UUID | None = None,
        **body: Any,
    ):
        return self.client.post(
            f"/v1/units/{unit_id or self.unit_id}/speaker-contacts/{professional_id}"
            f"/channels/{channel_id}/transitions",
            json=body,
            headers=self._headers,
        )

    def walk_to(self, professional_id: str, channel_id: str, final: str) -> None:
        """Drive a ``discovered`` channel up the lifecycle to ``final``.

        Every step is a real request, because that is the point: there is no
        shortcut to ``active_candidate``, and a helper that inserted one would
        be testing a path the API does not offer.
        """
        steps = [
            ("corroborated", {}),
            ("reviewed", {}),
            ("relationship_recorded", {}),
            ("consented", {"consent_source": "in_person", "consent_evidence": EVIDENCE}),
            ("active_candidate", {}),
        ]
        for to_state, extra in steps:
            response = self.transition(professional_id, channel_id, to_state=to_state, **extra)
            assert response.status_code == 201, response.text
            if to_state == final:
                return
        raise AssertionError(f"{final!r} is not on the lifecycle path")

    def suppress(self, address: str) -> None:
        """Record that somebody at ``address`` has told us to stop."""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO suppression_record "
                    "(id, tenant_id, address, suppressed_at, source) "
                    "VALUES (:id, :tid, :address, now(), 'coordinator')"
                ),
                {"id": uuid.uuid4(), "tid": self.tenant_id, "address": address},
            )


@pytest.fixture(scope="module")
def engine() -> Engine:
    """A live migrated PostgreSQL engine, or skip this contract.

    The probe touches both tables this surface joins across —
    ``speaker_profile`` for the roster precondition and
    ``contact_channel_transition`` for the trail — so a database migrated to
    only one of them skips rather than failing every test with an error naming
    the symptom instead of the cause.
    """
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT full_name FROM speaker_profile LIMIT 1"))
            conn.execute(text("SELECT 1 FROM contact_channel_transition LIMIT 1"))
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
    subject = f"sub-channels-{uuid.uuid4().hex}"
    token = f"tok-channels-{uuid.uuid4().hex}"

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-channels-{tenant_id.hex[:12]}"},
        )
        for new_unit_id, path, name in (
            (unit_id, UNIT_PATH, "Channels"),
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
        # Rooted at `iawest`, so one Connector covers both departments. The
        # sibling unit proves *unit* scoping of the rows, not authorization,
        # which `tests/authz` owns.
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
        # Child-first. Every foreign key in 0021, 0022 and 0023 is RESTRICT, and
        # `speaker_profile` restricts against both `user_account` and `org_unit`
        # — so the trail goes before the channel, the channel before the
        # profile, and the profile before either of the rows it points at.
        for table in (
            "contact_channel_transition",
            "contact_channel",
            "suppression_record",
            "speaker_profile",
            "professional_unit_relationship",
            "membership",
            "resource_grant",
            "user_account",
            "org_unit",
            "rate_limit_counter",
        ):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tenant_id})


# ---------------------------------------------------------------------------
# The posture this surface completes
# ---------------------------------------------------------------------------


class TestARosterContactStartsWithNothing:
    """OQ-CBA-011, visible from the outside."""

    def test_a_contact_added_through_the_form_holds_no_channels(self, ctx: _Context) -> None:
        """The typed address is not here, because it was never stored.

        An empty list rather than a 404: the contact exists and holds nothing,
        which is a different fact from not existing, and a Connector reading
        this screen needs to be able to tell them apart.
        """
        professional_id = ctx.add_roster_contact(contact_email=TYPED_CONTACT_EMAIL)

        response = ctx.list_channels(professional_id)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["channels"] == []
        assert body["professional_id"] == professional_id

    def test_the_form_reports_the_address_it_discarded(self, ctx: _Context) -> None:
        """Restated here because it is the premise of the test above.

        ``tests/contract/test_cba_contacts_api.py`` owns this contract. What it
        does for this file is establish that the empty list is a *refusal* the
        caller was told about, not an address that quietly went missing.
        """
        response = ctx.client.post(
            f"/v1/units/{ctx.unit_id}/speaker-contacts",
            json={
                "full_name": "Priya Raman",
                "topic_text": "Supply chain analytics.",
                "contact_email": TYPED_CONTACT_EMAIL,
            },
            headers={"Authorization": f"Bearer {ctx.token}"},
        )

        assert response.status_code == 201, response.text
        assert "contact_email" in response.json()["withheld_fields"]


# ---------------------------------------------------------------------------
# Creating a channel
# ---------------------------------------------------------------------------


class TestCreateChannel:
    """Recording an address is a claim, and it arrives with a name."""

    def test_a_discovered_channel_asserts_nothing_about_consent(self, ctx: _Context) -> None:
        professional_id = ctx.add_roster_contact()

        response = ctx.create_channel(professional_id)

        assert response.status_code == 201, response.text
        channel = response.json()["channel"]
        assert channel["contact_state"] == "discovered"
        assert channel["consent_source"] is None
        assert channel["consent_recorded_at"] is None
        assert channel["suppressed"] is False
        assert channel["send_eligible"] is False
        assert channel["professional_id"] == professional_id

    def test_the_create_opens_a_trail_naming_the_caller(self, ctx: _Context) -> None:
        """Who says so is the question the whole feature rests on."""
        professional_id = ctx.add_roster_contact()

        response = ctx.create_channel(professional_id, reason="met at the spring mixer")

        assert response.status_code == 201, response.text
        transitions = response.json()["transitions"]
        assert len(transitions) == 1
        entry = transitions[0]
        assert entry["from_state"] is None
        assert entry["to_state"] == "discovered"
        assert entry["reason"] == "met at the spring mixer"
        assert uuid.UUID(entry["actor_user_id"])

    def test_a_consented_channel_is_still_not_send_eligible(self, ctx: _Context) -> None:
        """The pairing this card turns on.

        The strictest legal create — a named person, an approved source, dated
        evidence — still produces something no send may address. Consent is a
        permission on file; being a live recipient is a separate act.
        """
        professional_id = ctx.add_roster_contact()

        response = ctx.create_consented_channel(professional_id)

        assert response.status_code == 201, response.text
        channel = response.json()["channel"]
        assert channel["contact_state"] == "consented"
        assert channel["consent_source"] == "in_person"
        assert channel["consent_recorded_at"] is not None
        assert channel["send_eligible"] is False

    def test_creating_an_active_candidate_is_refused(self, ctx: _Context) -> None:
        """The invite-to-consent loophole at its cheapest entry point.

        403 rather than 400: no consent source, evidence or wording admits this
        request, so the caller should stop rather than try other values.
        """
        professional_id = ctx.add_roster_contact()

        response = ctx.create_channel(
            professional_id,
            contact_state="active_candidate",
            consent_source="in_person",
            consent_evidence=EVIDENCE,
        )

        assert response.status_code == 403, response.text
        assert response.json()["error"]["code"] == "speaker_contact_channel_not_registrable"

    @pytest.mark.parametrize("source", ["scraped", "purchased", "inferred"])
    def test_research_provenance_cannot_be_recorded_as_consent(
        self, ctx: _Context, source: str
    ) -> None:
        """Evidence about a person is never permission to write to them."""
        professional_id = ctx.add_roster_contact()

        response = ctx.create_channel(
            professional_id,
            contact_state="consented",
            consent_source=source,
            consent_evidence=EVIDENCE,
        )

        assert response.status_code == 403, response.text
        assert response.json()["error"]["code"] == "speaker_contact_channel_not_registrable"

    def test_research_provenance_is_storable_on_a_discovered_channel(self, ctx: _Context) -> None:
        """How a row came to exist is what a reviewer needs.

        Recording *that* an address was scraped is fine and useful; what is
        refused is calling it consent. The row that results is not send-eligible
        and cannot become so without passing through `consented`, which this
        source can never reach.
        """
        professional_id = ctx.add_roster_contact()

        response = ctx.create_channel(
            professional_id, contact_state="discovered", consent_source="scraped"
        )

        assert response.status_code == 201, response.text
        channel = response.json()["channel"]
        assert channel["consent_source"] == "scraped"
        assert channel["send_eligible"] is False

    def test_a_consent_claim_without_evidence_is_refused(self, ctx: _Context) -> None:
        """400, not 403: this one *is* fixable by sending something more."""
        professional_id = ctx.add_roster_contact()

        response = ctx.create_channel(
            professional_id, contact_state="consented", consent_source="in_person"
        )

        assert response.status_code == 400, response.text
        assert (
            response.json()["error"]["code"] == "speaker_contact_channel_consent_evidence_required"
        )

    def test_a_second_channel_for_the_same_address_is_refused(self, ctx: _Context) -> None:
        """Two rows for one address would be two consent states for one person."""
        professional_id = ctx.add_roster_contact()
        assert ctx.create_channel(professional_id).status_code == 201

        response = ctx.create_channel(professional_id)

        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "speaker_contact_channel_exists"

    def test_one_person_may_hold_two_addresses(self, ctx: _Context) -> None:
        """The uniqueness is per address, not per person."""
        professional_id = ctx.add_roster_contact()
        assert ctx.create_channel(professional_id).status_code == 201
        assert ctx.create_channel(professional_id, address=SECOND_ADDRESS).status_code == 201

        body = ctx.list_channels(professional_id).json()

        assert sorted(entry["channel"]["address"] for entry in body["channels"]) == sorted(
            [ADDRESS, SECOND_ADDRESS]
        )


# ---------------------------------------------------------------------------
# The roster precondition, which is what makes this surface CBA-specific
# ---------------------------------------------------------------------------


class TestTheRosterPrecondition:
    """An address has to belong to somebody a Connector actually put on a list."""

    def test_a_professional_who_is_not_on_the_roster_is_a_404(self, ctx: _Context) -> None:
        response = ctx.create_channel(str(uuid.uuid4()))

        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "speaker_contact_not_found"

    def test_a_contact_on_another_unit_roster_is_reported_identically(self, ctx: _Context) -> None:
        """Not a 403, which would confirm the id names somebody real."""
        elsewhere = ctx.add_roster_contact(unit_id=ctx.sibling_unit_id)

        response = ctx.create_channel(elsewhere)

        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "speaker_contact_not_found"

    def test_a_channel_cannot_be_moved_through_a_different_persons_path(
        self, ctx: _Context
    ) -> None:
        """The person in the path has to be the person the channel belongs to.

        Without this the route would be a way to move *any* channel in a unit
        the caller may reach, by naming any roster contact they may reach.
        """
        owner = ctx.add_roster_contact(full_name="Dana Reyes")
        bystander = ctx.add_roster_contact(full_name="Sam Okafor")
        channel_id = ctx.create_channel(owner).json()["channel"]["contact_channel_id"]

        response = ctx.transition(bystander, channel_id, to_state="corroborated")

        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "speaker_contact_channel_not_found"

    def test_listing_is_scoped_to_the_unit_that_owns_the_roster_entry(self, ctx: _Context) -> None:
        professional_id = ctx.add_roster_contact()
        assert ctx.create_channel(professional_id).status_code == 201

        response = ctx.list_channels(professional_id, unit_id=ctx.sibling_unit_id)

        assert response.status_code == 404, response.text


# ---------------------------------------------------------------------------
# Driving the lifecycle
# ---------------------------------------------------------------------------


class TestTransitions:
    """Every state a person reaches, somebody moved them to."""

    def test_the_full_walk_reaches_send_eligible_and_only_there(self, ctx: _Context) -> None:
        professional_id = ctx.add_roster_contact()
        channel_id = ctx.create_channel(professional_id).json()["channel"]["contact_channel_id"]

        ctx.walk_to(professional_id, channel_id, "active_candidate")

        channel = ctx.list_channels(professional_id).json()["channels"][0]["channel"]
        assert channel["contact_state"] == "active_candidate"
        assert channel["consent_source"] == "in_person"
        assert channel["send_eligible"] is True

    def test_the_whole_walk_is_on_the_trail_with_its_actor(self, ctx: _Context) -> None:
        """Five moves plus the registration, each naming who made it."""
        professional_id = ctx.add_roster_contact()
        channel_id = ctx.create_channel(professional_id).json()["channel"]["contact_channel_id"]
        ctx.walk_to(professional_id, channel_id, "active_candidate")

        transitions = ctx.list_channels(professional_id).json()["channels"][0]["transitions"]

        assert [entry["to_state"] for entry in transitions] == [
            "discovered",
            "corroborated",
            "reviewed",
            "relationship_recorded",
            "consented",
            "active_candidate",
        ]
        assert len({entry["actor_user_id"] for entry in transitions}) == 1
        assert transitions[0]["from_state"] is None
        assert transitions[4]["consent_source"] == "in_person"
        assert transitions[4]["consent_evidence"] == EVIDENCE

    def test_a_shortcut_to_active_candidate_is_refused(self, ctx: _Context) -> None:
        """409: the caller may work with this channel; it is not there yet."""
        professional_id = ctx.add_roster_contact()
        channel_id = ctx.create_channel(professional_id).json()["channel"]["contact_channel_id"]

        response = ctx.transition(
            professional_id,
            channel_id,
            to_state="active_candidate",
            consent_source="in_person",
            consent_evidence=EVIDENCE,
        )

        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "speaker_contact_channel_transition_refused"

    def test_reaching_consented_with_a_research_source_is_refused(self, ctx: _Context) -> None:
        """403 rather than 409: no legal sequence of moves admits this source."""
        professional_id = ctx.add_roster_contact()
        channel_id = ctx.create_channel(professional_id).json()["channel"]["contact_channel_id"]
        for to_state in ("corroborated", "reviewed", "relationship_recorded"):
            assert ctx.transition(professional_id, channel_id, to_state=to_state).status_code == 201

        response = ctx.transition(
            professional_id,
            channel_id,
            to_state="consented",
            consent_source="scraped",
            consent_evidence=EVIDENCE,
        )

        assert response.status_code == 403, response.text
        assert (
            response.json()["error"]["code"]
            == "speaker_contact_channel_consent_source_not_approved"
        )

    def test_reaching_consented_without_evidence_is_refused(self, ctx: _Context) -> None:
        professional_id = ctx.add_roster_contact()
        channel_id = ctx.create_channel(professional_id).json()["channel"]["contact_channel_id"]
        for to_state in ("corroborated", "reviewed", "relationship_recorded"):
            assert ctx.transition(professional_id, channel_id, to_state=to_state).status_code == 201

        response = ctx.transition(
            professional_id, channel_id, to_state="consented", consent_source="in_person"
        )

        assert response.status_code == 400, response.text
        assert (
            response.json()["error"]["code"] == "speaker_contact_channel_consent_evidence_required"
        )

    def test_a_rejected_contact_cannot_be_revived(self, ctx: _Context) -> None:
        professional_id = ctx.add_roster_contact()
        channel_id = ctx.create_channel(professional_id).json()["channel"]["contact_channel_id"]
        for to_state in ("corroborated", "reviewed", "rejected"):
            assert ctx.transition(professional_id, channel_id, to_state=to_state).status_code == 201

        response = ctx.transition(professional_id, channel_id, to_state="relationship_recorded")

        assert response.status_code == 409, response.text


# ---------------------------------------------------------------------------
# Suppression outranks the lifecycle, not merely the send
# ---------------------------------------------------------------------------


class TestSuppressionWins:
    """A person saying stop beats every approval that might permit a send."""

    def test_a_suppressed_address_cannot_be_recorded_at_all(self, ctx: _Context) -> None:
        """Refused before the row exists, not after somebody notices it."""
        professional_id = ctx.add_roster_contact()
        ctx.suppress(SUPPRESSED_ADDRESS)

        response = ctx.create_consented_channel(professional_id, address=SUPPRESSED_ADDRESS)

        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "speaker_contact_channel_suppressed"

    def test_suppression_blocks_activation_of_a_properly_consented_channel(
        self, ctx: _Context
    ) -> None:
        """The one move that would make a suppressed person writable-to."""
        professional_id = ctx.add_roster_contact()
        channel_id = ctx.create_channel(professional_id).json()["channel"]["contact_channel_id"]
        for to_state, extra in (
            ("corroborated", {}),
            ("reviewed", {}),
            ("relationship_recorded", {}),
            ("consented", {"consent_source": "in_person", "consent_evidence": EVIDENCE}),
        ):
            assert (
                ctx.transition(professional_id, channel_id, to_state=to_state, **extra).status_code
                == 201
            )
        ctx.suppress(ADDRESS)

        response = ctx.transition(professional_id, channel_id, to_state="active_candidate")

        assert response.status_code == 409, response.text
        body = response.json()["error"]
        assert body["code"] == "speaker_contact_channel_transition_refused"
        assert "suppressed" in body["message"]

    def test_suppression_after_activation_removes_send_eligibility(self, ctx: _Context) -> None:
        """Nothing is rewritten; the read simply stops saying yes.

        ``send_eligible`` is computed rather than stored, so a suppression
        recorded after activation takes effect on the next read without anybody
        having to remember to update a flag.
        """
        professional_id = ctx.add_roster_contact()
        channel_id = ctx.create_channel(professional_id).json()["channel"]["contact_channel_id"]
        ctx.walk_to(professional_id, channel_id, "active_candidate")
        assert (
            ctx.list_channels(professional_id).json()["channels"][0]["channel"]["send_eligible"]
            is True
        )

        ctx.suppress(ADDRESS)

        channel = ctx.list_channels(professional_id).json()["channels"][0]["channel"]
        assert channel["contact_state"] == "active_candidate"
        assert channel["suppressed"] is True
        assert channel["send_eligible"] is False

    def test_a_suppressed_contact_can_still_be_recorded_as_stale(self, ctx: _Context) -> None:
        """Suppression forbids moves *toward* a send, not every move.

        Freezing a suppressed contact in whatever state it happened to be in
        records the person's wishes less accurately, not more.
        """
        professional_id = ctx.add_roster_contact()
        channel_id = ctx.create_channel(professional_id).json()["channel"]["contact_channel_id"]
        ctx.walk_to(professional_id, channel_id, "active_candidate")
        ctx.suppress(ADDRESS)

        response = ctx.transition(professional_id, channel_id, to_state="stale")

        assert response.status_code == 201, response.text
        assert response.json()["channel"]["contact_state"] == "stale"

    def test_a_suppressed_contact_cannot_be_re_consented(self, ctx: _Context) -> None:
        """A new form does not overrule an old refusal."""
        professional_id = ctx.add_roster_contact()
        channel_id = ctx.create_channel(professional_id).json()["channel"]["contact_channel_id"]
        for to_state in ("corroborated", "reviewed", "relationship_recorded"):
            assert ctx.transition(professional_id, channel_id, to_state=to_state).status_code == 201
        ctx.suppress(ADDRESS)

        response = ctx.transition(
            professional_id,
            channel_id,
            to_state="consented",
            consent_source="self_service",
            consent_evidence="they filled the form in again",
        )

        assert response.status_code == 409, response.text
        assert "suppressed" in response.json()["error"]["message"]
