"""HTTP contracts for the contact-channel surface (OQ-004's operational half).

``tests/integration/test_contact_channel_lifecycle.py`` owns the repository and
the constraints. What this file adds is the part that exists only over HTTP, and
it is mostly about **which refusal a caller gets**, because on this surface the
status code carries the meaning:

* An illegal edge is a ``409``. The caller may work with this contact; the
  contact is not in a state where the move means anything.
* An unapproved consent source is a ``403``. No sequence of legal moves fixes it,
  and reporting it as validation would invite the caller to try other inputs.
* Un-suppressing is a ``400`` that names OQ-009 rather than a silent no-op,
  because a fake success on this particular field reaches a real person.

The other thing only HTTP can show: a contact registered here becomes
``send_eligible`` only after somebody activates it, and the activation is a row
in the trail with that person's id on it.

Requires a live migrated PostgreSQL, and is skipped when none is reachable.
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

UNIT_PATH = "iawest.contacts"
#: A second department containing none of :data:`UNIT_PATH`, so a contact
#: registered there must not be reachable from the unit under test.
SIBLING_UNIT_PATH = "iawest.contactssibling"

#: RFC 2606 reserved. Nothing this suite registers can address a real mailbox.
ADDRESS = "contact-0000@synthetic.invalid"


class _Context:
    """One tenant, one coordinator, and two units."""

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

    def register(self, *, unit_id: uuid.UUID | None = None, **overrides: Any):
        body: dict[str, Any] = {
            "professional_id": str(uuid.uuid4()),
            "address": ADDRESS,
            "contact_state": "discovered",
        }
        body.update(overrides)
        return self.client.post(
            f"/v1/units/{unit_id or self.unit_id}/outreach/contacts",
            json=body,
            headers=self._headers,
        )

    def register_consented(self, **overrides: Any):
        return self.register(
            contact_state="consented",
            consent_source="in_person",
            consent_evidence="signed consent form, filed 2026-09-04",
            **overrides,
        )

    def read(self, contact_id: str):
        return self.client.get(
            f"/v1/units/{self.unit_id}/outreach/contacts/{contact_id}", headers=self._headers
        )

    def list_contacts(self):
        return self.client.get(f"/v1/units/{self.unit_id}/outreach/contacts", headers=self._headers)

    def patch(self, contact_id: str, **body: Any):
        return self.client.patch(
            f"/v1/units/{self.unit_id}/outreach/contacts/{contact_id}",
            json=body,
            headers=self._headers,
        )

    def transition(self, contact_id: str, **body: Any):
        return self.client.post(
            f"/v1/units/{self.unit_id}/outreach/contacts/{contact_id}/transitions",
            json=body,
            headers=self._headers,
        )


@pytest.fixture(scope="module")
def engine() -> Engine:
    """A live migrated PostgreSQL engine, or skip this contract."""
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
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
    subject = f"sub-contacts-{uuid.uuid4().hex}"
    token = f"tok-contacts-{uuid.uuid4().hex}"

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-contacts-{tenant_id.hex[:12]}"},
        )
        for new_unit_id, path, name in (
            (unit_id, UNIT_PATH, "Contacts"),
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
        # Rooted at `iawest`, so the same coordinator covers both departments.
        # The sibling unit is here to prove *unit* scoping of the contact rows,
        # not to test authorization, which `tests/authz` owns.
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
        # Child-first: every foreign key in 0021 and 0022 is RESTRICT.
        for table in (
            "contact_channel_speaker_choice",
            "contact_channel_transition",
            "contact_channel",
            "suppression_record",
            "speaker_profile",
            "membership",
            "user_account",
            "org_unit",
            "rate_limit_counter",
        ):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tenant_id})


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegisterContact:
    """Who this platform may write to is a claim, and it arrives with a name."""

    def test_registering_a_discovered_contact_asserts_nothing_about_consent(
        self, ctx: _Context
    ) -> None:
        response = ctx.register()

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["contact_state"] == "discovered"
        assert body["consent_source"] is None
        assert body["send_eligible"] is False

    def test_a_consented_registration_records_source_and_evidence(self, ctx: _Context) -> None:
        response = ctx.register_consented()

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["contact_state"] == "consented"
        assert body["consent_source"] == "in_person"
        assert body["consent_recorded_at"] is not None
        # Consent is not yet permission to send: activation is a separate act.
        assert body["send_eligible"] is False

    def test_the_registration_is_the_first_entry_of_the_trail(self, ctx: _Context) -> None:
        """Who recorded this contact is stored, not inferred later."""
        contact_id = ctx.register().json()["contact_channel_id"]

        history = ctx.read(contact_id).json()["transitions"]
        assert len(history) == 1
        assert history[0]["from_state"] is None
        assert history[0]["to_state"] == "discovered"
        assert history[0]["actor_user_id"] is not None

    def test_a_scraped_address_cannot_be_registered_as_consented(self, ctx: _Context) -> None:
        """403, and no sequence of inputs makes it work.

        Research evidence is never permission — an email asking a scraped
        address to opt in is itself prohibited outreach (v1.1 §1.8).
        """
        response = ctx.register(
            contact_state="consented",
            consent_source="scraped",
            consent_evidence="found on a public directory",
        )

        assert response.status_code == 403, response.text
        assert response.json()["error"]["code"] == "outreach_consent_source_not_approved"

    def test_a_consent_claim_without_evidence_is_refused(self, ctx: _Context) -> None:
        """An auditor asking to see the evidence needs somewhere for it to live."""
        response = ctx.register(contact_state="consented", consent_source="in_person")

        assert response.status_code == 400, response.text
        assert response.json()["error"]["code"] == "outreach_consent_evidence_required"

    def test_a_contact_cannot_be_registered_directly_as_send_eligible(self, ctx: _Context) -> None:
        """The database would take the row; this route will not write it.

        Activation is an act with an actor. Allowing it in the registration call
        would let a send-eligible contact exist with no recorded moment at which
        anybody activated it.
        """
        response = ctx.register(
            contact_state="active_candidate",
            consent_source="in_person",
            consent_evidence="signed consent form",
        )

        assert response.status_code == 400, response.text
        assert response.json()["error"]["code"] == "outreach_contact_state_not_registrable"

    def test_a_second_registration_of_one_address_is_a_conflict(self, ctx: _Context) -> None:
        ctx.register()

        response = ctx.register()

        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "contact_channel_exists"

    def test_a_contact_in_another_unit_is_not_readable_here(self, ctx: _Context) -> None:
        """404 rather than 403: a 403 would confirm the id names something real."""
        other = ctx.register(unit_id=ctx.sibling_unit_id, address="sibling@synthetic.invalid")
        assert other.status_code == 201, other.text

        response = ctx.read(other.json()["contact_channel_id"])

        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "contact_channel_not_found"


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------


class TestTransitions:
    """The state machine over HTTP, including the moves that must not happen."""

    def test_an_illegal_edge_is_refused_with_the_state_the_contact_is_in(
        self, ctx: _Context
    ) -> None:
        """409, naming the present state, which is what a stale screen needs.

        ``discovered -> active_candidate`` is the move the whole lifecycle exists
        to make impossible: there is no path from a research state to a
        send-eligible one except through ``consented``.
        """
        contact_id = ctx.register().json()["contact_channel_id"]

        response = ctx.transition(contact_id, to_state="active_candidate")

        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "outreach_contact_transition_illegal"
        assert "discovered" in response.json()["error"]["message"]

    def test_a_legal_edge_moves_the_contact_and_extends_the_trail(self, ctx: _Context) -> None:
        contact_id = ctx.register().json()["contact_channel_id"]

        response = ctx.transition(
            contact_id, to_state="corroborated", reason="a second source agrees"
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["contact"]["contact_state"] == "corroborated"
        assert [entry["to_state"] for entry in body["transitions"]] == [
            "discovered",
            "corroborated",
        ]
        assert body["transitions"][-1]["reason"] == "a second source agrees"

    def test_activation_is_what_makes_a_contact_send_eligible(self, ctx: _Context) -> None:
        """The two-step the send path depends on, driven over HTTP."""
        contact_id = ctx.register_consented().json()["contact_channel_id"]

        response = ctx.transition(contact_id, to_state="active_candidate")

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["contact"]["contact_state"] == "active_candidate"
        assert body["contact"]["send_eligible"] is True
        assert [entry["to_state"] for entry in body["transitions"]] == [
            "consented",
            "active_candidate",
        ]

    def test_reaching_consented_through_a_transition_needs_an_approved_source(
        self, ctx: _Context
    ) -> None:
        contact_id = ctx.register().json()["contact_channel_id"]
        ctx.transition(contact_id, to_state="corroborated")
        ctx.transition(contact_id, to_state="reviewed")
        ctx.transition(contact_id, to_state="relationship_recorded")

        refused = ctx.transition(
            contact_id,
            to_state="consented",
            consent_source="purchased",
            consent_evidence="bought from a list vendor",
        )
        assert refused.status_code == 403, refused.text
        assert refused.json()["error"]["code"] == "outreach_consent_source_not_approved"

        missing = ctx.transition(contact_id, to_state="consented")
        assert missing.status_code == 403, missing.text
        assert missing.json()["error"]["code"] == "outreach_consent_source_required"

    def test_the_whole_lifecycle_can_be_walked_and_every_step_is_recorded(
        self, ctx: _Context
    ) -> None:
        """The path OQ-004 says a coordinator must be able to drive, end to end."""
        contact_id = ctx.register().json()["contact_channel_id"]

        for step in ("corroborated", "reviewed", "relationship_recorded"):
            assert ctx.transition(contact_id, to_state=step).status_code == 201

        consented = ctx.transition(
            contact_id,
            to_state="consented",
            consent_source="institutional_relationship",
            consent_evidence="MOU 2026-14, section 3",
        )
        assert consented.status_code == 201, consented.text

        activated = ctx.transition(contact_id, to_state="active_candidate")
        assert activated.status_code == 201, activated.text

        body = activated.json()
        assert body["contact"]["send_eligible"] is True
        assert [entry["to_state"] for entry in body["transitions"]] == [
            "discovered",
            "corroborated",
            "reviewed",
            "relationship_recorded",
            "consented",
            "active_candidate",
        ]
        # Every entry names somebody. There is no lifecycle move nobody made.
        assert all(entry["actor_user_id"] for entry in body["transitions"])

    def test_a_rejected_contact_is_terminal(self, ctx: _Context) -> None:
        """``rejected`` has no outgoing edges, and the route says so rather than
        finding out at the database."""
        contact_id = ctx.register().json()["contact_channel_id"]
        ctx.transition(contact_id, to_state="corroborated")
        ctx.transition(contact_id, to_state="reviewed")
        assert ctx.transition(contact_id, to_state="rejected").status_code == 201

        response = ctx.transition(contact_id, to_state="reviewed")

        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "outreach_contact_transition_illegal"


# ---------------------------------------------------------------------------
# Correction and suppression
# ---------------------------------------------------------------------------


class TestUpdateContact:
    """The two edits that are not lifecycle moves, and the one that is refused."""

    def test_the_evidence_can_be_corrected(self, ctx: _Context) -> None:
        contact_id = ctx.register_consented().json()["contact_channel_id"]

        response = ctx.patch(contact_id, consent_evidence="form 118-B, filed 2026-09-04")

        assert response.status_code == 200, response.text
        assert response.json()["consent_evidence"] == "form 118-B, filed 2026-09-04"

    def test_suppressing_stops_the_contact_being_send_eligible(self, ctx: _Context) -> None:
        """The flag is a ``suppression_record``, and it is read back by a join."""
        contact_id = ctx.register_consented().json()["contact_channel_id"]
        assert ctx.transition(contact_id, to_state="active_candidate").status_code == 201

        response = ctx.patch(contact_id, suppressed=True)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["suppressed"] is True
        assert body["send_eligible"] is False
        # The lifecycle state is untouched: suppression is a statement about the
        # person, not a move of the contact.
        assert body["contact_state"] == "active_candidate"

    def test_suppressing_twice_is_the_same_instruction_repeated(self, ctx: _Context) -> None:
        contact_id = ctx.register_consented().json()["contact_channel_id"]
        ctx.patch(contact_id, suppressed=True)

        again = ctx.patch(contact_id, suppressed=True)

        assert again.status_code == 200, again.text
        assert again.json()["suppressed"] is True

    def test_un_suppressing_is_refused_rather_than_silently_ignored(self, ctx: _Context) -> None:
        """The fake success this slice exists to remove, on the field where it
        would reach a real person."""
        contact_id = ctx.register_consented().json()["contact_channel_id"]
        ctx.patch(contact_id, suppressed=True)

        response = ctx.patch(contact_id, suppressed=False)

        assert response.status_code == 400, response.text
        assert response.json()["error"]["code"] == "outreach_unsuppress_not_supported"
        assert ctx.read(contact_id).json()["contact"]["suppressed"] is True

    def test_a_patch_that_changes_nothing_says_so(self, ctx: _Context) -> None:
        contact_id = ctx.register().json()["contact_channel_id"]

        response = ctx.patch(contact_id)

        assert response.status_code == 400, response.text
        assert response.json()["error"]["code"] == "outreach_contact_update_empty"

    def test_a_patch_cannot_move_the_lifecycle_state(self, ctx: _Context) -> None:
        """Not by refusing the field — by not having it.

        A state change through PATCH would be a state change with no audit row,
        which is the failure migration 0022 exists to prevent.
        """
        contact_id = ctx.register().json()["contact_channel_id"]

        ctx.patch(contact_id, contact_state="active_candidate")

        assert ctx.read(contact_id).json()["contact"]["contact_state"] == "discovered"


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


class TestListContacts:
    """A unit's contacts, and only that unit's."""

    def test_the_list_is_scoped_to_the_unit_and_reports_eligibility(self, ctx: _Context) -> None:
        mine = ctx.register().json()["contact_channel_id"]
        ctx.register(unit_id=ctx.sibling_unit_id, address="sibling@synthetic.invalid")

        response = ctx.list_contacts()

        assert response.status_code == 200, response.text
        body = response.json()
        assert [row["contact_channel_id"] for row in body["contacts"]] == [mine]
        assert body["contacts"][0]["send_eligible"] is False
        assert body["limit"] > 0


# ---------------------------------------------------------------------------
# B26 T6b-3: the Speaker wins (G2, G3) and suppression wins on this route (OQ-4)
# ---------------------------------------------------------------------------

_EVIDENCE = "signed consent form, filed 2026-09-04"


def _suppress(ctx: _Context, source: str = "unsubscribe_link") -> None:
    with ctx.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO suppression_record (id, tenant_id, address, suppressed_at, source) "
                "VALUES (:id, :t, :a, now(), :s)"
            ),
            {"id": uuid.uuid4(), "t": ctx.tenant_id, "a": ADDRESS, "s": source},
        )


def _choose(ctx: _Context, contact_id: str, choice: str) -> None:
    """Append a Speaker choice as the Speaker portal would (the route ships later)."""
    with ctx.engine.begin() as conn:
        row = conn.execute(
            text("SELECT professional_id, owning_unit_id FROM contact_channel WHERE id = :c"),
            {"c": contact_id},
        ).one()
        # A professional id is a user_account id (speaker_profile's key).
        conn.execute(
            text(
                "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                "VALUES (:p, :t, :sub, :email) ON CONFLICT DO NOTHING"
            ),
            {
                "p": row.professional_id,
                "t": ctx.tenant_id,
                "sub": f"sub-professional-{row.professional_id.hex}",
                "email": f"{row.professional_id.hex[:8]}@example.edu",
            },
        )
        conn.execute(
            text(
                "INSERT INTO speaker_profile (tenant_id, professional_id, owning_unit_id, "
                "full_name) VALUES (:t, :p, :u, 'Sam Rivera') ON CONFLICT DO NOTHING"
            ),
            {"t": ctx.tenant_id, "p": row.professional_id, "u": row.owning_unit_id},
        )
        actor = conn.execute(
            text(
                "SELECT user_id FROM membership WHERE tenant_id = :t AND role = 'coordinator' "
                "LIMIT 1"
            ),
            {"t": ctx.tenant_id},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO contact_channel_speaker_choice (id, tenant_id, professional_id, "
                "contact_channel_id, sequence, choice, decided_at, actor_user_id) "
                "SELECT :i, :t, :p, :c, coalesce(max(sequence), 0) + 1, :ch, now(), :u "
                "FROM contact_channel_speaker_choice WHERE tenant_id = :t "
                "AND contact_channel_id = :c"
            ),
            {
                "i": uuid.uuid4(),
                "t": ctx.tenant_id,
                "p": row.professional_id,
                "c": contact_id,
                "ch": choice,
                "u": actor,
            },
        )


def _walk(ctx: _Context, contact_id: str, *states: str) -> None:
    for to_state in states:
        extra: dict[str, Any] = {}
        if to_state == "consented":
            extra = {"consent_source": "in_person", "consent_evidence": _EVIDENCE}
        response = ctx.transition(contact_id, to_state=to_state, **extra)
        assert response.status_code == 201, response.text


_TO_RELATIONSHIP = ("corroborated", "reviewed", "relationship_recorded")


def _trail_length(ctx: _Context, contact_id: str) -> int:
    with ctx.engine.connect() as conn:
        return int(
            conn.execute(
                text(
                    "SELECT count(*) FROM contact_channel_transition WHERE contact_channel_id = :c"
                ),
                {"c": contact_id},
            ).scalar_one()
        )


class TestTheSpeakerWinsOnTheGenericRoute:
    """G2: the Speaker's latest choice beats a coordinator's move."""

    def test_opted_out_contact_refuses_consented_and_active_candidate(self, ctx: _Context) -> None:
        contact_id = ctx.register().json()["contact_channel_id"]
        _walk(ctx, contact_id, *_TO_RELATIONSHIP)
        _choose(ctx, contact_id, "opt_out")

        response = ctx.transition(contact_id, to_state="consented")  # no evidence either

        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "speaker_contact_channel_speaker_opted_out"

        other = ctx.register_consented(address="other-0001@synthetic.invalid").json()
        _choose(ctx, other["contact_channel_id"], "opt_out")
        response = ctx.transition(other["contact_channel_id"], to_state="active_candidate")
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "speaker_contact_channel_speaker_opted_out"

    def test_opted_in_contact_refuses_stale(self, ctx: _Context) -> None:
        contact_id = ctx.register_consented().json()["contact_channel_id"]
        _walk(ctx, contact_id, "active_candidate")
        _choose(ctx, contact_id, "opt_in")

        response = ctx.transition(contact_id, to_state="stale")

        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "speaker_contact_channel_speaker_opted_in"

    def test_speaker_wins_code_wins_over_suppressed_code(self, ctx: _Context) -> None:
        contact_id = ctx.register_consented().json()["contact_channel_id"]
        _choose(ctx, contact_id, "opt_out")
        _suppress(ctx, "speaker_portal")

        response = ctx.transition(contact_id, to_state="active_candidate")

        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "speaker_contact_channel_speaker_opted_out"

    def test_view_carries_speaker_choice(self, ctx: _Context) -> None:
        contact_id = ctx.register().json()["contact_channel_id"]
        before = ctx.read(contact_id).json()["contact"]
        assert before["speaker_choice"] is None and before["speaker_choice_at"] is None

        _choose(ctx, contact_id, "opt_out")

        after = ctx.read(contact_id).json()["contact"]
        assert after["speaker_choice"] == "opt_out"
        assert after["speaker_choice_at"] is not None
        listed = ctx.list_contacts().json()["contacts"]
        assert [c["speaker_choice"] for c in listed] == ["opt_out"]


class TestSuppressionWinsOnTheGenericRoute:
    """OQ-4: this route used to ignore suppression. Shipped-behaviour change."""

    def test_generic_transition_refuses_escalating_a_suppressed_contact(
        self, ctx: _Context
    ) -> None:
        to_consented = ctx.register().json()["contact_channel_id"]
        _walk(ctx, to_consented, *_TO_RELATIONSHIP)
        to_active = ctx.register_consented(address="other-0002@synthetic.invalid").json()[
            "contact_channel_id"
        ]
        with ctx.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO suppression_record (id, tenant_id, address, suppressed_at, "
                    "source) VALUES (:i, :t, :a, now(), 'unsubscribe_link'), "
                    "(:j, :t, 'other-0002@synthetic.invalid', now(), 'unsubscribe_link')"
                ),
                {"i": uuid.uuid4(), "j": uuid.uuid4(), "t": ctx.tenant_id, "a": ADDRESS},
            )
        cases = (
            (
                to_consented,
                "relationship_recorded",
                {
                    "to_state": "consented",
                    "consent_source": "in_person",
                    "consent_evidence": _EVIDENCE,
                },
            ),
            (to_active, "consented", {"to_state": "active_candidate"}),
        )
        for contact_id, state, body in cases:
            trail = _trail_length(ctx, contact_id)
            response = ctx.transition(contact_id, **body)
            assert response.status_code == 409, response.text
            assert response.json()["error"]["code"] == "outreach_contact_suppressed"
            assert _trail_length(ctx, contact_id) == trail
            assert ctx.read(contact_id).json()["contact"]["contact_state"] == state

    def test_suppressed_code_wins_over_missing_evidence(self, ctx: _Context) -> None:
        contact_id = ctx.register().json()["contact_channel_id"]
        _walk(ctx, contact_id, *_TO_RELATIONSHIP)
        _suppress(ctx)

        response = ctx.transition(contact_id, to_state="consented")

        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "outreach_contact_suppressed"

    def test_generic_transition_still_allows_stale_and_rejected_when_suppressed(
        self, ctx: _Context
    ) -> None:
        active = ctx.register_consented().json()["contact_channel_id"]
        _walk(ctx, active, "active_candidate")
        reviewed = ctx.register(address="other-0003@synthetic.invalid").json()["contact_channel_id"]
        _walk(ctx, reviewed, "corroborated", "reviewed")
        _suppress(ctx)
        with ctx.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO suppression_record (id, tenant_id, address, suppressed_at, "
                    "source) VALUES (:i, :t, 'other-0003@synthetic.invalid', now(), 'bounce')"
                ),
                {"i": uuid.uuid4(), "t": ctx.tenant_id},
            )

        assert ctx.transition(active, to_state="stale").status_code == 201
        assert ctx.transition(reviewed, to_state="rejected").status_code == 201

    def test_unsuppressed_illegal_edge_is_still_409_illegal(self, ctx: _Context) -> None:
        contact_id = ctx.register().json()["contact_channel_id"]

        response = ctx.transition(contact_id, to_state="consented")

        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "outreach_contact_transition_illegal"

    def test_a_lifted_suppression_no_longer_blocks(self, ctx: _Context) -> None:
        contact_id = ctx.register_consented().json()["contact_channel_id"]
        _suppress(ctx)
        with ctx.engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE suppression_record SET lifted_at = now(), lifted_by_user_id = "
                    "(SELECT id FROM user_account WHERE tenant_id = :t LIMIT 1) "
                    "WHERE tenant_id = :t"
                ),
                {"t": ctx.tenant_id},
            )

        assert ctx.transition(contact_id, to_state="active_candidate").status_code == 201


class TestTheSpeakerWinsOnPatch:
    """G3: a coordinator may not suppress or re-evidence a Speaker's own opt-in (OQ-2, S4)."""

    def _opted_in(self, ctx: _Context) -> str:
        contact_id: str = ctx.register_consented().json()["contact_channel_id"]
        _walk(ctx, contact_id, "active_candidate")
        _choose(ctx, contact_id, "opt_in")
        return contact_id

    def test_coordinator_suppress_on_an_opted_in_channel_is_409(self, ctx: _Context) -> None:
        contact_id = self._opted_in(ctx)

        response = ctx.patch(contact_id, suppressed=True)

        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "speaker_contact_channel_speaker_opted_in"

    def test_coordinator_suppress_on_an_opted_in_channel_writes_nothing(
        self, ctx: _Context
    ) -> None:
        contact_id = self._opted_in(ctx)

        ctx.patch(contact_id, suppressed=True, consent_evidence="corrected")

        with ctx.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT count(*) FROM suppression_record WHERE tenant_id = :t"),
                {"t": ctx.tenant_id},
            ).scalar_one()
        assert rows == 0
        read = ctx.read(contact_id).json()["contact"]
        assert read["suppressed"] is False
        assert read["consent_evidence"] == _EVIDENCE

    def test_evidence_patch_on_an_opted_in_channel_is_409(self, ctx: _Context) -> None:
        contact_id = self._opted_in(ctx)

        response = ctx.patch(contact_id, consent_evidence="a coordinator's correction")

        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "speaker_contact_channel_speaker_opted_in"
        assert ctx.read(contact_id).json()["contact"]["consent_evidence"] == _EVIDENCE

    def test_evidence_patch_after_opt_out_or_with_no_choice_succeeds(self, ctx: _Context) -> None:
        plain = ctx.register_consented().json()["contact_channel_id"]
        opted_out = ctx.register_consented(address="other-0004@synthetic.invalid").json()[
            "contact_channel_id"
        ]
        _choose(ctx, opted_out, "opt_in")
        _choose(ctx, opted_out, "opt_out")

        for contact_id in (plain, opted_out):
            response = ctx.patch(contact_id, consent_evidence="a coordinator's correction")
            assert response.status_code == 200, response.text
        assert ctx.patch(opted_out, suppressed=True).status_code == 200
