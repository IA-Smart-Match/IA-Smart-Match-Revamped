"""What the §13 channel surface actually writes, asserted against the tables.

``tests/contract/test_contact_lifecycle_api.py`` owns the status codes.
``tests/authz/test_policy_matrix.py`` owns the authorization rectangle. This
file owns the only question neither can answer: **did anything reach the
database.**

That distinction is not pedantry here. ``get_session`` rolls back
unconditionally, so a write route that forgets ``session.commit()`` returns a
clean ``201`` carrying a fully populated response body and stores nothing at
all. Three tracks have shipped exactly that defect. Every assertion below that
matters reads a ``SELECT``, in a *separate* connection from the request that
was supposed to have written it — a response body is a claim about a write, and
this file is where the claim is checked.

Four things are proved here and nowhere else:

* **The cross-card guarantee.** A contact added through §13's create form leaves
  ``contact_channel`` empty. Asserted with ``SELECT count(*)``, because
  OQ-CBA-011's promise is about the table and only a query about the table can
  keep it.
* **The audit trail.** Every state a person reaches has a row naming who moved
  them there, the trail is append-only at the database level, and a *refused*
  move appends nothing — an audit log that recorded attempts as though they were
  decisions would be worse than none.
* **Suppression.** It outranks the lifecycle and not merely the send, and the
  refusal leaves the stored row exactly as it was.
* **The database's own opinion.** ``ck_contact_channel_sendable_consent``
  refuses a send-eligible row with research provenance even when the INSERT
  comes from a psql session that never touched this application's code. That is
  the threat the duplicated rule exists for, so it is exercised by writing SQL
  rather than by calling the repository.

Requires a live migrated PostgreSQL, and is skipped when none is reachable.
Every address literal is on the RFC 2606 reserved ``.invalid`` TLD.
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
from sqlalchemy.exc import IntegrityError, InternalError, ProgrammingError

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

UNIT_PATH = "iawest.lifecycle"
SIBLING_UNIT_PATH = "iawest.lifecyclesibling"

#: RFC 2606 reserved. Nothing this suite stores can address a real mailbox.
ADDRESS = "dana.reyes@synthetic.invalid"
SUPPRESSED_ADDRESS = "stop.writing@synthetic.invalid"

#: The address a Connector types into §13's form. It must never appear in
#: ``contact_channel``, which is what the first class below asserts by querying
#: for the literal rather than by counting rows.
TYPED_CONTACT_EMAIL = "dana.reyes@example.invalid"

EVIDENCE = "signed consent form, filed 2026-09-05"

#: The full lifecycle, as a sequence of requests. There is no shortcut, and a
#: helper that inserted one would be exercising a path the API does not offer.
WALK: tuple[tuple[str, dict[str, Any]], ...] = (
    ("corroborated", {}),
    ("reviewed", {}),
    ("relationship_recorded", {}),
    ("consented", {"consent_source": "in_person", "consent_evidence": EVIDENCE}),
    ("active_candidate", {}),
)


class _Context:
    """One tenant, one Connector, two units, and direct access to the tables."""

    def __init__(
        self,
        client: TestClient,
        engine: Engine,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        sibling_unit_id: uuid.UUID,
        user_id: uuid.UUID,
        token: str,
    ) -> None:
        self.client = client
        self.engine = engine
        self.tenant_id = tenant_id
        self.unit_id = unit_id
        self.sibling_unit_id = sibling_unit_id
        self.user_id = user_id
        self.token = token

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def add_roster_contact(
        self, *, unit_id: uuid.UUID | None = None, full_name: str = "Dana Reyes", **overrides: Any
    ) -> str:
        body: dict[str, Any] = {
            "full_name": full_name,
            "topic_text": "Financial modelling for early-career analysts.",
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

    def create_channel(self, professional_id: str, **overrides: Any):
        body: dict[str, Any] = {"address": ADDRESS, "contact_state": "discovered"}
        body.update(overrides)
        return self.client.post(
            f"/v1/units/{self.unit_id}/speaker-contacts/{professional_id}/channels",
            json=body,
            headers=self._headers,
        )

    def transition(self, professional_id: str, channel_id: str, **body: Any):
        return self.client.post(
            f"/v1/units/{self.unit_id}/speaker-contacts/{professional_id}"
            f"/channels/{channel_id}/transitions",
            json=body,
            headers=self._headers,
        )

    def walk_to(self, professional_id: str, channel_id: str, final: str) -> None:
        for to_state, extra in WALK:
            response = self.transition(professional_id, channel_id, to_state=to_state, **extra)
            assert response.status_code == 201, response.text
            if to_state == final:
                return
        raise AssertionError(f"{final!r} is not on the lifecycle path")

    # -- reading the tables, which is what this file is for ------------------

    def channel_rows(self) -> list[Any]:
        """Every ``contact_channel`` row this tenant holds, read fresh."""
        with self.engine.connect() as conn:
            return list(
                conn.execute(
                    text(
                        "SELECT id, owning_unit_id, professional_id, address, contact_state, "
                        "consent_source, consent_recorded_at, consent_evidence "
                        "FROM contact_channel WHERE tenant_id = :tid ORDER BY address"
                    ),
                    {"tid": self.tenant_id},
                ).all()
            )

    def trail_rows(self, channel_id: str | uuid.UUID) -> list[Any]:
        """One channel's transitions, in the order a reader would see them."""
        with self.engine.connect() as conn:
            return list(
                conn.execute(
                    text(
                        "SELECT from_state, to_state, consent_source, consent_evidence, "
                        "reason, actor_user_id FROM contact_channel_transition "
                        "WHERE tenant_id = :tid AND contact_channel_id = :cid "
                        "ORDER BY occurred_at, recorded_at, id"
                    ),
                    {"tid": self.tenant_id, "cid": channel_id},
                ).all()
            )

    def suppress(self, address: str) -> None:
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
    """A live migrated PostgreSQL engine, or skip."""
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
    subject = f"sub-lifecycle-{uuid.uuid4().hex}"
    token = f"tok-lifecycle-{uuid.uuid4().hex}"

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-lifecycle-{tenant_id.hex[:12]}"},
        )
        for new_unit_id, path, name in (
            (unit_id, UNIT_PATH, "Lifecycle"),
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

    yield _Context(client, engine, tenant_id, unit_id, sibling_unit_id, user_id, token)

    with engine.begin() as conn:
        # Child-first: every foreign key in 0021, 0022 and 0023 is RESTRICT, and
        # `speaker_profile` restricts against both `user_account` and `org_unit`.
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
# The cross-card guarantee, asserted against the table it is about
# ---------------------------------------------------------------------------


class TestTheRosterCreateWritesNoChannel:
    """OQ-CBA-011 is a promise about `contact_channel`, so this queries it."""

    def test_adding_a_contact_leaves_the_channel_table_empty(self, ctx: _Context) -> None:
        ctx.add_roster_contact(contact_email=TYPED_CONTACT_EMAIL)

        assert ctx.channel_rows() == []

    def test_the_typed_address_is_nowhere_in_the_channel_table(self, ctx: _Context) -> None:
        """Not merely absent from the response — absent from storage.

        A defect that persisted the typed address but hid it from the read model
        would pass every assertion in the contract suite and fail this one,
        which is why this queries by the literal address rather than by count.
        """
        ctx.add_roster_contact(contact_email=TYPED_CONTACT_EMAIL)

        with ctx.engine.connect() as conn:
            found = conn.execute(
                text("SELECT count(*) FROM contact_channel WHERE address = :address"),
                {"address": TYPED_CONTACT_EMAIL},
            ).scalar_one()

        assert found == 0


# ---------------------------------------------------------------------------
# The write actually lands
# ---------------------------------------------------------------------------


class TestTheWriteIsCommitted:
    """`get_session` rolls back unconditionally. A 201 proves nothing on its own."""

    def test_a_created_channel_is_readable_from_a_separate_connection(self, ctx: _Context) -> None:
        professional_id = ctx.add_roster_contact()

        response = ctx.create_channel(professional_id)
        assert response.status_code == 201, response.text

        rows = ctx.channel_rows()
        assert len(rows) == 1
        assert rows[0].address == ADDRESS
        assert rows[0].contact_state == "discovered"
        assert str(rows[0].professional_id) == professional_id
        assert rows[0].owning_unit_id == ctx.unit_id

    def test_a_consented_create_stores_the_source_and_dates_it(self, ctx: _Context) -> None:
        """`ck_contact_channel_consent_dated` pairs them; this proves both landed."""
        professional_id = ctx.add_roster_contact()

        assert (
            ctx.create_channel(
                professional_id,
                contact_state="consented",
                consent_source="in_person",
                consent_evidence=EVIDENCE,
            ).status_code
            == 201
        )

        row = ctx.channel_rows()[0]
        assert row.contact_state == "consented"
        assert row.consent_source == "in_person"
        assert row.consent_recorded_at is not None
        assert row.consent_evidence == EVIDENCE

    def test_a_transition_is_committed_not_merely_returned(self, ctx: _Context) -> None:
        professional_id = ctx.add_roster_contact()
        channel_id = ctx.create_channel(professional_id).json()["channel"]["contact_channel_id"]

        assert (
            ctx.transition(professional_id, channel_id, to_state="corroborated").status_code == 201
        )

        assert ctx.channel_rows()[0].contact_state == "corroborated"

    def test_a_refused_create_stores_nothing(self, ctx: _Context) -> None:
        """The 403 path must not leave a half-written row behind."""
        professional_id = ctx.add_roster_contact()

        assert (
            ctx.create_channel(
                professional_id,
                contact_state="active_candidate",
                consent_source="in_person",
                consent_evidence=EVIDENCE,
            ).status_code
            == 403
        )

        assert ctx.channel_rows() == []


# ---------------------------------------------------------------------------
# The audit trail
# ---------------------------------------------------------------------------


class TestTheAuditTrail:
    """Every state a person reaches, a stored row says who moved them there."""

    def test_the_create_writes_one_entry_naming_the_caller(self, ctx: _Context) -> None:
        professional_id = ctx.add_roster_contact()
        channel_id = ctx.create_channel(professional_id, reason="met at the spring mixer").json()[
            "channel"
        ]["contact_channel_id"]

        trail = ctx.trail_rows(channel_id)

        assert len(trail) == 1
        assert trail[0].from_state is None
        assert trail[0].to_state == "discovered"
        assert trail[0].reason == "met at the spring mixer"
        # The actor is the authenticated principal, never a body field: letting
        # a request name who recorded a consent would be MM-A01 in the one place
        # it would matter most.
        assert trail[0].actor_user_id == ctx.user_id

    def test_the_whole_walk_is_recorded_in_order_with_its_actor(self, ctx: _Context) -> None:
        professional_id = ctx.add_roster_contact()
        channel_id = ctx.create_channel(professional_id).json()["channel"]["contact_channel_id"]

        ctx.walk_to(professional_id, channel_id, "active_candidate")

        trail = ctx.trail_rows(channel_id)
        assert [(row.from_state, row.to_state) for row in trail] == [
            (None, "discovered"),
            ("discovered", "corroborated"),
            ("corroborated", "reviewed"),
            ("reviewed", "relationship_recorded"),
            ("relationship_recorded", "consented"),
            ("consented", "active_candidate"),
        ]
        assert {row.actor_user_id for row in trail} == {ctx.user_id}

    def test_the_consent_entry_carries_the_source_and_its_evidence(self, ctx: _Context) -> None:
        """An auditor asking to see the evidence finds it on the move itself."""
        professional_id = ctx.add_roster_contact()
        channel_id = ctx.create_channel(professional_id).json()["channel"]["contact_channel_id"]
        ctx.walk_to(professional_id, channel_id, "consented")

        consent_entry = ctx.trail_rows(channel_id)[-1]

        assert consent_entry.to_state == "consented"
        assert consent_entry.consent_source == "in_person"
        assert consent_entry.consent_evidence == EVIDENCE

    def test_a_refused_transition_appends_nothing(self, ctx: _Context) -> None:
        """An audit log that recorded attempts as decisions is worse than none."""
        professional_id = ctx.add_roster_contact()
        channel_id = ctx.create_channel(professional_id).json()["channel"]["contact_channel_id"]
        before = len(ctx.trail_rows(channel_id))

        assert (
            ctx.transition(
                professional_id,
                channel_id,
                to_state="active_candidate",
                consent_source="in_person",
                consent_evidence=EVIDENCE,
            ).status_code
            == 409
        )

        assert len(ctx.trail_rows(channel_id)) == before
        assert ctx.channel_rows()[0].contact_state == "discovered"

    def test_the_trail_cannot_be_edited_even_from_a_psql_session(self, ctx: _Context) -> None:
        """Migration 0023's trigger, exercised where application discipline cannot reach.

        A correction to a lifecycle is a *new* transition. There is no update
        method on the repository, and this proves the absence is enforced rather
        than merely observed.
        """
        professional_id = ctx.add_roster_contact()
        channel_id = ctx.create_channel(professional_id).json()["channel"]["contact_channel_id"]

        with (
            pytest.raises((IntegrityError, InternalError, ProgrammingError)),
            ctx.engine.begin() as conn,
        ):
            conn.execute(
                text(
                    "UPDATE contact_channel_transition SET to_state = 'active_candidate' "
                    "WHERE contact_channel_id = :cid"
                ),
                {"cid": channel_id},
            )


# ---------------------------------------------------------------------------
# Suppression, proved against the stored row
# ---------------------------------------------------------------------------


class TestSuppressionWinsInStorage:
    """A refusal that left the row changed anyway would be no refusal at all."""

    def test_a_suppressed_address_never_becomes_a_row(self, ctx: _Context) -> None:
        professional_id = ctx.add_roster_contact()
        ctx.suppress(SUPPRESSED_ADDRESS)

        response = ctx.create_channel(
            professional_id,
            address=SUPPRESSED_ADDRESS,
            contact_state="consented",
            consent_source="in_person",
            consent_evidence=EVIDENCE,
        )

        assert response.status_code == 409, response.text
        assert ctx.channel_rows() == []

    def test_a_blocked_activation_leaves_the_stored_state_untouched(self, ctx: _Context) -> None:
        """The channel stays `consented`, which is what it honestly is."""
        professional_id = ctx.add_roster_contact()
        channel_id = ctx.create_channel(professional_id).json()["channel"]["contact_channel_id"]
        ctx.walk_to(professional_id, channel_id, "consented")
        ctx.suppress(ADDRESS)
        trail_before = len(ctx.trail_rows(channel_id))

        response = ctx.transition(professional_id, channel_id, to_state="active_candidate")

        assert response.status_code == 409, response.text
        row = ctx.channel_rows()[0]
        assert row.contact_state == "consented"
        assert row.consent_source == "in_person"
        assert len(ctx.trail_rows(channel_id)) == trail_before

    def test_no_active_candidate_row_exists_for_a_suppressed_address(self, ctx: _Context) -> None:
        """The property stated as a query, so any future path that broke it fails here."""
        professional_id = ctx.add_roster_contact()
        channel_id = ctx.create_channel(professional_id).json()["channel"]["contact_channel_id"]
        ctx.walk_to(professional_id, channel_id, "consented")
        ctx.suppress(ADDRESS)

        assert (
            ctx.transition(professional_id, channel_id, to_state="active_candidate").status_code
            == 409
        )

        with ctx.engine.connect() as conn:
            sendable = conn.execute(
                text(
                    "SELECT count(*) FROM contact_channel c "
                    "JOIN suppression_record s "
                    "  ON s.tenant_id = c.tenant_id AND s.address = c.address "
                    "WHERE c.tenant_id = :tid AND c.contact_state = 'active_candidate'"
                ),
                {"tid": ctx.tenant_id},
            ).scalar_one()

        assert sendable == 0

    def test_a_de_escalating_move_is_still_written(self, ctx: _Context) -> None:
        """Suppression forbids moves toward a send, and only those."""
        professional_id = ctx.add_roster_contact()
        channel_id = ctx.create_channel(professional_id).json()["channel"]["contact_channel_id"]
        ctx.walk_to(professional_id, channel_id, "active_candidate")
        ctx.suppress(ADDRESS)

        assert ctx.transition(professional_id, channel_id, to_state="stale").status_code == 201

        assert ctx.channel_rows()[0].contact_state == "stale"
        assert ctx.trail_rows(channel_id)[-1].to_state == "stale"


# ---------------------------------------------------------------------------
# The database's own opinion, which no application discipline substitutes for
# ---------------------------------------------------------------------------


class TestTheConstraintHoldsWithoutTheApplication:
    """`ck_contact_channel_sendable_consent`, exercised by raw SQL on purpose.

    The domain check stops application code; this one stops a hand-written
    INSERT in a psql session, which is a different threat and the reason
    migration 0021 duplicates the rule deliberately.
    """

    def _insert(self, ctx: _Context, **values: Any) -> None:
        row: dict[str, Any] = {
            "id": uuid.uuid4(),
            "tid": ctx.tenant_id,
            "unit": ctx.unit_id,
            "pro": uuid.uuid4(),
            "address": f"raw-{uuid.uuid4().hex[:8]}@synthetic.invalid",
            "state": "active_candidate",
            "source": None,
            "recorded": None,
        }
        row.update(values)
        with ctx.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO contact_channel (id, tenant_id, owning_unit_id, "
                    "professional_id, channel_kind, address, contact_state, "
                    "consent_source, consent_recorded_at) VALUES (:id, :tid, :unit, "
                    ":pro, 'email', :address, :state, :source, :recorded)"
                ),
                row,
            )

    def test_an_active_candidate_with_no_source_is_refused(self, ctx: _Context) -> None:
        """SQL's three-valued logic makes this the easy one to get wrong.

        ``NULL IN (...)`` evaluates to NULL, ``FALSE OR NULL`` to NULL, and a
        CHECK treats NULL as satisfied — so the ``IS NOT NULL`` clause is not
        redundant with the IN list, and leaving it out was a real defect.
        """
        with pytest.raises(IntegrityError, match="ck_contact_channel_sendable_consent"):
            self._insert(ctx, source=None, recorded=None)

    @pytest.mark.parametrize("source", ["scraped", "purchased", "inferred"])
    def test_an_active_candidate_with_research_provenance_is_refused(
        self, ctx: _Context, source: str
    ) -> None:
        with pytest.raises(IntegrityError, match="ck_contact_channel_sendable_consent"):
            self._insert(ctx, source=source, recorded="2026-09-05T00:00:00+00:00")

    def test_a_source_without_a_date_is_refused(self, ctx: _Context) -> None:
        """A permission nobody can date is a permission nobody can audit."""
        with pytest.raises(IntegrityError, match="ck_contact_channel_consent_dated"):
            self._insert(ctx, state="consented", source="in_person", recorded=None)

    def test_an_approved_source_with_a_date_is_accepted(self, ctx: _Context) -> None:
        """The constraint refuses the wrong rows, not every row."""
        self._insert(ctx, source="in_person", recorded="2026-09-05T00:00:00+00:00")

        assert ctx.channel_rows()[0].contact_state == "active_candidate"


# ---------------------------------------------------------------------------
# Scoping
# ---------------------------------------------------------------------------


class TestScoping:
    """A person known to two units is two accountabilities, not one."""

    def test_a_channel_is_not_visible_through_a_sibling_unit(self, ctx: _Context) -> None:
        professional_id = ctx.add_roster_contact()
        assert ctx.create_channel(professional_id).status_code == 201

        response = ctx.client.get(
            f"/v1/units/{ctx.sibling_unit_id}/speaker-contacts/{professional_id}/channels",
            headers={"Authorization": f"Bearer {ctx.token}"},
        )

        assert response.status_code == 404, response.text

    def test_the_stored_row_carries_the_owning_unit_that_authorized_it(self, ctx: _Context) -> None:
        """`owning_unit_id` is the authorization input, so it is checked stored."""
        professional_id = ctx.add_roster_contact()
        assert ctx.create_channel(professional_id).status_code == 201

        assert ctx.channel_rows()[0].owning_unit_id == ctx.unit_id

    def test_listing_one_person_does_not_return_another_persons_channels(
        self, ctx: _Context
    ) -> None:
        first = ctx.add_roster_contact(full_name="Dana Reyes")
        second = ctx.add_roster_contact(full_name="Sam Okafor")
        assert ctx.create_channel(first).status_code == 201
        assert ctx.create_channel(second, address="sam.okafor@synthetic.invalid").status_code == 201

        body = ctx.client.get(
            f"/v1/units/{ctx.unit_id}/speaker-contacts/{first}/channels",
            headers={"Authorization": f"Bearer {ctx.token}"},
        ).json()

        assert [entry["channel"]["address"] for entry in body["channels"]] == [ADDRESS]
