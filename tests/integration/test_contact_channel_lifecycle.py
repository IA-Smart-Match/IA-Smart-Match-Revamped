"""The consent lifecycle against a real database (migration ``0022``, OQ-004).

``tests/unit/test_consent.py`` owns the state machine as pure logic: which edges
exist, and what ``assert_transition`` refuses. What that file cannot show is the
half this slice adds — that a move **writes a record of itself**, that the record
cannot be edited afterwards, and that the database refuses the same things the
domain refuses even when the domain is bypassed entirely.

Those three are what make the audit trail worth having, and none of them is
provable without PostgreSQL:

* A ``CHECK`` constraint only exists in a migrated database. The tests below that
  insert rows by hand are testing the guard that stops a ``psql`` session, which
  is precisely the caller no amount of application discipline reaches.
* An append-only trigger is invisible to any in-memory double.
* The guarded ``UPDATE ... WHERE contact_state = :expected`` behaves like an
  ordinary update until two writers race, and "returns None instead of
  clobbering" is a statement about SQL semantics.

Requires a live migrated PostgreSQL, and is skipped when none is reachable.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from smartmatch_domain.consent import ContactState
from smartmatch_persistence.contacts import ContactChannelRepository
from smartmatch_persistence.outreach import OutreachRepository
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration

#: RFC 2606 reserved. Nothing this suite stores can address a real mailbox.
ADDRESS = "lifecycle-0000@synthetic.invalid"

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)

_contacts = ContactChannelRepository()
_outreach = OutreachRepository()


@pytest.fixture
def actor_id(engine: Engine, tenant_id: uuid.UUID) -> uuid.UUID:
    """A user_account row, because ``actor_user_id`` is NOT NULL and a real key.

    Migration ``0022`` refuses a transition whose actor does not exist, which is
    the structural half of "there is no lifecycle move nobody made".
    """
    user_id = uuid.uuid4()
    subject = f"sub-lifecycle-{uuid.uuid4().hex}"
    with engine.begin() as conn:
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
    return user_id


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as db:
        yield db


def _register(
    session: Session,
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    actor_id: uuid.UUID,
    *,
    state: ContactState = ContactState.DISCOVERED,
    address: str = ADDRESS,
    consent_source: str | None = None,
) -> uuid.UUID:
    contact_id = _contacts.register(
        session,
        tenant_id=tenant_id,
        owning_unit_id=owning_unit_id,
        professional_id=uuid.uuid4(),
        address=address,
        contact_state=state.value,
        consent_source=consent_source,
        consent_recorded_at=NOW if consent_source is not None else None,
        consent_evidence="signed consent form" if consent_source is not None else None,
        actor_user_id=actor_id,
        occurred_at=NOW,
    )
    assert contact_id is not None
    session.commit()
    return contact_id


class TestRegistration:
    """A contact arrives with the first entry of its own history."""

    def test_registering_opens_the_trail_with_a_null_from_state(
        self,
        session: Session,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        """The registration is a real entry, not an implied one.

        A trail whose first row is the first *edit* cannot say where a contact
        started, or who put it there — which is the question OQ-004 says a
        migration is not in a position to answer and a coordinator is.
        """
        contact_id = _register(session, tenant_id, owning_unit_id, actor_id)

        trail = _contacts.list_transitions(
            session, tenant_id=tenant_id, contact_channel_id=contact_id
        )
        assert len(trail) == 1
        assert trail[0].from_state is None
        assert trail[0].to_state == ContactState.DISCOVERED.value
        assert trail[0].actor_user_id == actor_id

    def test_a_second_registration_of_one_address_is_reported_not_raised(
        self,
        session: Session,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        """``None``, and the transaction survives.

        The point of ``ON CONFLICT DO NOTHING`` here rather than catching an
        ``IntegrityError``: a raised constraint aborts the whole transaction, so
        a route would lose any other work in it in order to report a conflict a
        caller can act on.
        """
        _register(session, tenant_id, owning_unit_id, actor_id)

        again = _contacts.register(
            session,
            tenant_id=tenant_id,
            owning_unit_id=owning_unit_id,
            professional_id=uuid.uuid4(),
            address=ADDRESS,
            contact_state=ContactState.DISCOVERED.value,
            actor_user_id=actor_id,
            occurred_at=NOW,
        )
        assert again is None
        # The session is still usable, which is the half an exception would cost.
        assert (
            _contacts.list_for_unit(session, tenant_id=tenant_id, owning_unit_id=owning_unit_id)
            != []
        )


class TestTransitions:
    """Moves are recorded, and moves from the wrong state do not happen."""

    def test_a_legal_move_updates_the_contact_and_appends_to_the_trail(
        self,
        session: Session,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        contact_id = _register(session, tenant_id, owning_unit_id, actor_id)

        moved = _contacts.apply_transition(
            session,
            tenant_id=tenant_id,
            contact_channel_id=contact_id,
            expected_state=ContactState.DISCOVERED.value,
            to_state=ContactState.CORROBORATED.value,
            actor_user_id=actor_id,
            occurred_at=NOW,
            reason="a second source names the same address",
        )
        session.commit()

        assert moved is not None
        assert moved.contact_state == ContactState.CORROBORATED.value

        trail = _contacts.list_transitions(
            session, tenant_id=tenant_id, contact_channel_id=contact_id
        )
        assert [(entry.from_state, entry.to_state) for entry in trail] == [
            (None, "discovered"),
            ("discovered", "corroborated"),
        ]
        assert trail[-1].reason == "a second source names the same address"

    def test_a_move_from_a_state_the_contact_has_left_writes_nothing(
        self,
        session: Session,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        """The lost-update guard, which is why ``apply_transition`` returns None.

        Two coordinators working one lifecycle is the ordinary case. Without the
        ``WHERE contact_state = :expected`` clause the second write would
        overwrite a decision it never saw *and* append an audit row claiming a
        move out of a state the contact had already left — a trail that lies.
        """
        contact_id = _register(session, tenant_id, owning_unit_id, actor_id)
        _contacts.apply_transition(
            session,
            tenant_id=tenant_id,
            contact_channel_id=contact_id,
            expected_state=ContactState.DISCOVERED.value,
            to_state=ContactState.CORROBORATED.value,
            actor_user_id=actor_id,
            occurred_at=NOW,
        )
        session.commit()

        stale = _contacts.apply_transition(
            session,
            tenant_id=tenant_id,
            contact_channel_id=contact_id,
            expected_state=ContactState.DISCOVERED.value,
            to_state=ContactState.CORROBORATED.value,
            actor_user_id=actor_id,
            occurred_at=NOW,
        )
        session.commit()

        assert stale is None
        trail = _contacts.list_transitions(
            session, tenant_id=tenant_id, contact_channel_id=contact_id
        )
        assert len(trail) == 2

    def test_the_full_path_to_send_eligibility_is_recorded_end_to_end(
        self,
        session: Session,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        """Registered as consented, activated, and now readable by the send path.

        The assertion that ties this slice to the one before it: what the send
        path reads through ``load_recipient`` is what these transitions wrote.
        """
        contact_id = _register(
            session,
            tenant_id,
            owning_unit_id,
            actor_id,
            state=ContactState.CONSENTED,
            consent_source="in_person",
        )

        _contacts.apply_transition(
            session,
            tenant_id=tenant_id,
            contact_channel_id=contact_id,
            expected_state=ContactState.CONSENTED.value,
            to_state=ContactState.ACTIVE_CANDIDATE.value,
            actor_user_id=actor_id,
            occurred_at=NOW,
        )
        session.commit()

        facts = _outreach.load_recipient(
            session, tenant_id=tenant_id, contact_channel_id=contact_id
        )
        assert facts is not None
        assert facts.contact_state == ContactState.ACTIVE_CANDIDATE.value
        assert facts.consent_source == "in_person"
        assert facts.suppressed is False


class TestTheDatabaseRefusesWhatTheDomainRefuses:
    """Constraints tested by writing SQL, because that is the caller they stop."""

    def test_a_consent_transition_cannot_rest_on_a_scraped_source(
        self,
        engine: Engine,
        session: Session,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        """``ck_contact_channel_transition_consented_source``.

        Research evidence is never permission, and this is the copy of that rule
        that survives an operator with a psql prompt.
        """
        contact_id = _register(session, tenant_id, owning_unit_id, actor_id)

        with pytest.raises(IntegrityError) as caught, engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO contact_channel_transition (id, tenant_id, "
                    "contact_channel_id, from_state, to_state, consent_source, "
                    "actor_user_id, occurred_at) VALUES (:i, :t, :c, "
                    "'relationship_recorded', 'consented', 'scraped', :a, now())"
                ),
                {"i": uuid.uuid4(), "t": tenant_id, "c": contact_id, "a": actor_id},
            )
        assert "ck_contact_channel_transition_consented_source" in str(caught.value)

    def test_a_consent_transition_cannot_carry_no_source_at_all(
        self,
        engine: Engine,
        session: Session,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        """The three-valued-logic half, which an ``IN`` list alone would miss.

        ``NULL IN (...)`` evaluates to NULL and a CHECK treats NULL as satisfied,
        so without the explicit ``IS NOT NULL`` clause a consent transition
        naming no source whatsoever would pass — the exact defect migration
        ``0021`` records having found in the contact table's own version of this
        constraint.
        """
        contact_id = _register(session, tenant_id, owning_unit_id, actor_id)

        with pytest.raises(IntegrityError) as caught, engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO contact_channel_transition (id, tenant_id, "
                    "contact_channel_id, from_state, to_state, actor_user_id, "
                    "occurred_at) VALUES (:i, :t, :c, 'relationship_recorded', "
                    "'consented', :a, now())"
                ),
                {"i": uuid.uuid4(), "t": tenant_id, "c": contact_id, "a": actor_id},
            )
        assert "ck_contact_channel_transition_consented_source" in str(caught.value)

    def test_a_transition_to_the_state_it_came_from_is_not_a_transition(
        self,
        engine: Engine,
        session: Session,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        contact_id = _register(session, tenant_id, owning_unit_id, actor_id)

        with pytest.raises(IntegrityError) as caught, engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO contact_channel_transition (id, tenant_id, "
                    "contact_channel_id, from_state, to_state, actor_user_id, "
                    "occurred_at) VALUES (:i, :t, :c, 'discovered', 'discovered', "
                    ":a, now())"
                ),
                {"i": uuid.uuid4(), "t": tenant_id, "c": contact_id, "a": actor_id},
            )
        assert "ck_contact_channel_transition_moves" in str(caught.value)

    def test_the_trail_cannot_be_edited(
        self,
        engine: Engine,
        session: Session,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        """The append-only trigger. An editable audit trail is not one.

        The refusal arrives as an ``IntegrityError`` because the trigger raises
        with ``ERRCODE = 'restrict_violation'`` — a real integrity class rather
        than an internal error, which is what makes it indistinguishable to a
        caller from the constraints beside it. That is the point: "you may not
        write this" should not depend on which mechanism refused.
        """
        contact_id = _register(session, tenant_id, owning_unit_id, actor_id)

        with pytest.raises(IntegrityError) as caught, engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE contact_channel_transition SET to_state = 'consented' "
                    "WHERE contact_channel_id = :c"
                ),
                {"c": contact_id},
            )
        assert "append-only" in str(caught.value)

    def test_a_transition_needs_an_actor_that_exists(
        self,
        engine: Engine,
        session: Session,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        """There is no lifecycle move nobody made, and the key enforces it."""
        contact_id = _register(session, tenant_id, owning_unit_id, actor_id)

        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO contact_channel_transition (id, tenant_id, "
                    "contact_channel_id, from_state, to_state, actor_user_id, "
                    "occurred_at) VALUES (:i, :t, :c, 'discovered', 'corroborated', "
                    ":a, now())"
                ),
                {
                    "i": uuid.uuid4(),
                    "t": tenant_id,
                    "c": contact_id,
                    "a": uuid.uuid4(),
                },
            )


class TestVocabularyAndShapeConstraints:
    """The trail's own vocabularies, refused at the database.

    Parametrised rather than written out one by one: what is being asserted is
    that each column's ``CHECK`` is *live*, and a table of (column, bad value,
    constraint) says that more legibly than five near-identical functions —
    ``test_outreach_persistence.py``'s ``TestVocabularyConstraints`` makes the
    same call for migration ``0021``'s tables.
    """

    @pytest.mark.parametrize(
        ("column", "value", "constraint"),
        [
            ("from_state", "invented", "ck_contact_channel_transition_from_state"),
            ("to_state", "invented", "ck_contact_channel_transition_to_state"),
            ("consent_source", "telepathy", "ck_contact_channel_transition_consent_source"),
            # Blank is not absent (ADR-0011): an empty reason is
            # indistinguishable from a writer that forgot to supply one.
            ("reason", "   ", "ck_contact_channel_transition_text_present"),
            ("consent_evidence", "", "ck_contact_channel_transition_text_present"),
        ],
    )
    def test_a_transition_refuses_a_value_outside_its_vocabulary(
        self,
        engine: Engine,
        session: Session,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        actor_id: uuid.UUID,
        column: str,
        value: str,
        constraint: str,
    ) -> None:
        contact_id = _register(session, tenant_id, owning_unit_id, actor_id)

        columns = {
            "from_state": "'discovered'",
            "to_state": "'corroborated'",
            "consent_source": "NULL",
            "consent_evidence": "NULL",
            "reason": "NULL",
        }
        columns[column] = ":bad"

        statement = (
            "INSERT INTO contact_channel_transition (id, tenant_id, contact_channel_id, "
            "from_state, to_state, consent_source, consent_evidence, reason, "
            "actor_user_id, occurred_at) VALUES (:i, :t, :c, "
            f"{columns['from_state']}, {columns['to_state']}, {columns['consent_source']}, "
            f"{columns['consent_evidence']}, {columns['reason']}, :a, now())"
        )

        with pytest.raises(IntegrityError) as caught, engine.begin() as conn:
            conn.execute(
                text(statement),
                {
                    "i": uuid.uuid4(),
                    "t": tenant_id,
                    "c": contact_id,
                    "a": actor_id,
                    "bad": value,
                },
            )
        assert constraint in str(caught.value)


class TestSuppressionIsComputed:
    """The contact read reports suppression from the record, never from a flag."""

    def test_suppressing_the_address_shows_up_on_the_contact_read(
        self,
        session: Session,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        contact_id = _register(
            session,
            tenant_id,
            owning_unit_id,
            actor_id,
            state=ContactState.CONSENTED,
            consent_source="in_person",
        )

        before = _contacts.get(session, tenant_id=tenant_id, contact_channel_id=contact_id)
        assert before is not None and before.suppressed is False

        _outreach.suppress(
            session,
            tenant_id=tenant_id,
            address=ADDRESS,
            source="coordinator",
            suppressed_at=NOW,
        )
        session.commit()

        after = _contacts.get(session, tenant_id=tenant_id, contact_channel_id=contact_id)
        assert after is not None and after.suppressed is True

    def test_a_contact_in_another_tenant_is_not_readable_by_id(
        self,
        session: Session,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        """Tenant scoping is part of the lookup, not a filter applied after it."""
        contact_id = _register(session, tenant_id, owning_unit_id, actor_id)

        assert _contacts.get(session, tenant_id=uuid.uuid4(), contact_channel_id=contact_id) is None


def test_the_new_table_is_in_the_metadata_mirror() -> None:
    """A table in a migration and not in ``schema.py`` is a table nothing writes.

    ``test_schema_matches_migration.py`` compares the two whole-schema; this is
    the cheap, database-free half that fails first when the mirror is forgotten.
    """
    from smartmatch_persistence import schema

    assert "contact_channel_transition" in schema.METADATA.tables
    assert isinstance(schema.contact_channel_transition, sa.Table)
