"""``OutreachRepository`` against a real PostgreSQL (migration ``0021``, card L4).

Three kinds of thing are checked here, and only the first could have been
checked without a database:

1. The repository's own logic — that a reservation reports which attempt it is,
   that a conclusion is written once, that a repeated unsubscribe is a no-op.
2. The **constraints**, by attempting the writes they exist to refuse. A CHECK
   nothing has ever violated is a CHECK nobody knows still works, and every one
   exercised below encodes a rule about a real person that the application layer
   also enforces — so this is the half that survives someone bypassing the
   application entirely.
3. The append-only trigger, by attempting the UPDATE it refuses.

The recurring theme is the second execution. Almost every test writes something
twice, because at-least-once command delivery means the second write is the
normal case rather than the exceptional one, and every duplicate here would be a
duplicate email.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from smartmatch_persistence.outreach import OutreachRepository
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from tests.integration.conftest import ensure_owning_unit, unique_subject

pytestmark = pytest.mark.integration

_REPO = OutreachRepository()

_NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)

#: RFC 2606 reserved. Nothing this suite writes can address a real mailbox.
_ADDRESS = "professional-0000@synthetic.invalid"
_FROM = "noreply@example.invalid"


@pytest.fixture
def session(session_factory: sessionmaker[Session], tenant_id: uuid.UUID) -> Session:
    """An uncommitted session, rolled back at the end of each test.

    It declares a dependency on ``tenant_id`` that its body never uses, and that
    is the point: pytest finalizes fixtures in reverse setup order, so the
    dependency puts this rollback *before* the ``tenant_id`` fixture's ``DELETE``
    sweep. Without it, teardown deletes rows this session still holds
    uncommitted locks on, and the suite hangs on a lock rather than failing —
    which is a far more expensive way to find out.

    Nothing here commits, so no test can leave a row behind for the next one.
    """
    with session_factory() as s:
        yield s
        s.rollback()


@pytest.fixture
def unit_id(engine: Engine, tenant_id: uuid.UUID) -> uuid.UUID:
    with engine.begin() as conn:
        return ensure_owning_unit(conn, tenant_id)


@pytest.fixture
def actor_id(engine: Engine, tenant_id: uuid.UUID) -> uuid.UUID:
    """A ``user_account`` to hang ``created_by`` and ``approved_by`` off."""
    account_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                "VALUES (:id, :tid, :sub, :email)"
            ),
            {
                "id": account_id,
                "tid": tenant_id,
                "sub": unique_subject("sub-outreach-coordinator"),
                "email": "coordinator@example.invalid",
            },
        )
    return account_id


def _contact(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    address: str = _ADDRESS,
    contact_state: str = "active_candidate",
    consent_source: str | None = "self_service",
) -> uuid.UUID:
    """Insert one contact channel and return its id."""
    contact_id = uuid.uuid4()
    session.execute(
        text(
            "INSERT INTO contact_channel (id, tenant_id, owning_unit_id, professional_id, "
            "channel_kind, address, contact_state, consent_source, consent_recorded_at) "
            "VALUES (:id, :tid, :uid, :pid, 'email', :addr, :state, :src, :at)"
        ),
        {
            "id": contact_id,
            "tid": tenant_id,
            "uid": unit_id,
            "pid": uuid.uuid4(),
            "addr": address,
            "state": contact_state,
            "src": consent_source,
            "at": _NOW if consent_source else None,
        },
    )
    return contact_id


def _job(session: Session, *, tenant_id: uuid.UUID, unit_id: uuid.UUID) -> uuid.UUID:
    """A durable command row for a send to hang off. See `outreach_send.job_id`."""
    job_id = uuid.uuid4()
    session.execute(
        text(
            "INSERT INTO job (id, tenant_id, owning_unit_id, command_type, status, payload) "
            "VALUES (:id, :tid, :uid, 'outreach.send', 'queued', '{}'::jsonb)"
        ),
        {"id": job_id, "tid": tenant_id, "uid": unit_id},
    )
    return job_id


def _draft(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    contact_id: uuid.UUID,
    actor_id: uuid.UUID,
    status: str = "approved",
) -> uuid.UUID:
    return _REPO.create_draft(
        session,
        tenant_id=tenant_id,
        owning_unit_id=unit_id,
        contact_channel_id=contact_id,
        template_id="pilot.event_invitation.v1",
        content_status="synthetic",
        subject="Spring Showcase on Friday, 12 June",
        body="Hello Sam Rivera,\n\nNorthside Robotics is hosting...\n",
        created_by=actor_id,
        status=status,
        approved_by=actor_id if status == "approved" else None,
        approved_at=_NOW if status == "approved" else None,
    )


# ---------------------------------------------------------------------------
# Contacts and the live suppression join
# ---------------------------------------------------------------------------


class TestLoadRecipient:
    """Suppression is computed on every read, never cached."""

    def test_an_eligible_contact_reports_its_consent_facts(
        self, session: Session, tenant_id: uuid.UUID, unit_id: uuid.UUID
    ):
        contact_id = _contact(session, tenant_id=tenant_id, unit_id=unit_id)

        facts = _REPO.load_recipient(session, tenant_id=tenant_id, contact_channel_id=contact_id)

        assert facts is not None
        assert facts.address == _ADDRESS
        assert facts.contact_state == "active_candidate"
        assert facts.consent_source == "self_service"
        assert facts.suppressed is False

    def test_a_suppression_written_afterwards_is_visible_on_the_next_read(
        self, session: Session, tenant_id: uuid.UUID, unit_id: uuid.UUID
    ):
        """The behaviour a cached `suppressed` column would have got wrong.

        Nothing updates `contact_channel` here. The suppression is a row in a
        different table, and the contact becomes ineligible the moment it lands.
        """
        contact_id = _contact(session, tenant_id=tenant_id, unit_id=unit_id)
        before = _REPO.load_recipient(session, tenant_id=tenant_id, contact_channel_id=contact_id)
        assert before is not None and before.suppressed is False

        _REPO.suppress(
            session,
            tenant_id=tenant_id,
            address=_ADDRESS,
            source="unsubscribe_link",
            suppressed_at=_NOW,
        )

        after = _REPO.load_recipient(session, tenant_id=tenant_id, contact_channel_id=contact_id)
        assert after is not None and after.suppressed is True

    def test_another_tenants_contact_is_not_readable(
        self, session: Session, tenant_id: uuid.UUID, unit_id: uuid.UUID
    ):
        contact_id = _contact(session, tenant_id=tenant_id, unit_id=unit_id)

        assert (
            _REPO.load_recipient(session, tenant_id=uuid.uuid4(), contact_channel_id=contact_id)
            is None
        )

    def test_a_suppression_in_another_tenant_does_not_leak_across(
        self, session: Session, tenant_id: uuid.UUID, unit_id: uuid.UUID
    ):
        """Suppression is per tenant, as the unique constraint scopes it.

        Written because the join is on *address*, which is the one column in
        this schema that is not an opaque id — so "the same person in two
        tenants" is representable, and each tenant's instruction is its own.
        """
        contact_id = _contact(session, tenant_id=tenant_id, unit_id=unit_id)
        session.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": (other := uuid.uuid4()), "slug": f"other-{other.hex[:10]}"},
        )
        _REPO.suppress(
            session,
            tenant_id=other,
            address=_ADDRESS,
            source="coordinator",
            suppressed_at=_NOW,
        )

        facts = _REPO.load_recipient(session, tenant_id=tenant_id, contact_channel_id=contact_id)
        assert facts is not None and facts.suppressed is False


class TestContactConstraints:
    """The database refuses what the consent lifecycle forbids."""

    @pytest.mark.parametrize("source", ["scraped", "purchased", "inferred"])
    def test_research_evidence_cannot_be_stored_as_send_eligible(
        self, session: Session, tenant_id: uuid.UUID, unit_id: uuid.UUID, source: str
    ):
        """`ck_contact_channel_sendable_consent`, the rule this table exists for.

        Not reachable through the application — nothing offers a way to write
        this — which is exactly why it is worth a test: this is the guard that
        holds when someone types an INSERT by hand.
        """
        with pytest.raises(IntegrityError, match="ck_contact_channel_sendable_consent"):
            _contact(
                session,
                tenant_id=tenant_id,
                unit_id=unit_id,
                consent_source=source,
            )
        session.rollback()

    def test_research_evidence_can_still_be_recorded_in_a_review_state(
        self, session: Session, tenant_id: uuid.UUID, unit_id: uuid.UUID
    ):
        """Provenance is a fact worth keeping; it just never authorizes a send."""
        contact_id = _contact(
            session,
            tenant_id=tenant_id,
            unit_id=unit_id,
            contact_state="discovered",
            consent_source="scraped",
        )

        facts = _REPO.load_recipient(session, tenant_id=tenant_id, contact_channel_id=contact_id)
        assert facts is not None and facts.consent_source == "scraped"

    def test_a_send_eligible_contact_cannot_omit_its_consent_source(
        self, session: Session, tenant_id: uuid.UUID, unit_id: uuid.UUID
    ):
        with pytest.raises(IntegrityError, match="ck_contact_channel_sendable_consent"):
            _contact(session, tenant_id=tenant_id, unit_id=unit_id, consent_source=None)
        session.rollback()

    def test_one_address_has_one_contact_per_tenant(
        self, session: Session, tenant_id: uuid.UUID, unit_id: uuid.UUID
    ):
        """Two rows would be two consent states for one person."""
        _contact(session, tenant_id=tenant_id, unit_id=unit_id)
        session.flush()

        with pytest.raises(IntegrityError, match="uq_contact_channel_address"):
            _contact(session, tenant_id=tenant_id, unit_id=unit_id)
            session.flush()
        session.rollback()


# ---------------------------------------------------------------------------
# Sends — the re-drive guarantee
# ---------------------------------------------------------------------------


class TestReserveSend:
    """One command sends at most once, however many times it executes."""

    def test_a_first_reservation_is_reported_as_this_calls_own(
        self,
        session: Session,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        actor_id: uuid.UUID,
    ):
        contact_id = _contact(session, tenant_id=tenant_id, unit_id=unit_id)
        draft_id = _draft(
            session,
            tenant_id=tenant_id,
            unit_id=unit_id,
            contact_id=contact_id,
            actor_id=actor_id,
        )
        job_id = _job(session, tenant_id=tenant_id, unit_id=unit_id)

        reservation = _REPO.reserve_send(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            draft_id=draft_id,
            job_id=job_id,
            idempotency_key="key-1",
            recipient_address=_ADDRESS,
            from_address=_FROM,
            unsubscribe_token_hash="a" * 64,
        )

        assert reservation.was_already_reserved is False
        assert reservation.disposition is None

    def test_a_second_execution_of_the_same_job_finds_the_first_reservation(
        self,
        session: Session,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        actor_id: uuid.UUID,
    ):
        """The test this whole table's `job_id` uniqueness exists for.

        A worker that died after committing its send and before its terminal
        transition gets re-driven with the identical payload. Without this, the
        recipient gets the message twice.
        """
        contact_id = _contact(session, tenant_id=tenant_id, unit_id=unit_id)
        draft_id = _draft(
            session,
            tenant_id=tenant_id,
            unit_id=unit_id,
            contact_id=contact_id,
            actor_id=actor_id,
        )
        job_id = _job(session, tenant_id=tenant_id, unit_id=unit_id)

        first = _REPO.reserve_send(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            draft_id=draft_id,
            job_id=job_id,
            idempotency_key="key-1",
            recipient_address=_ADDRESS,
            from_address=_FROM,
            unsubscribe_token_hash="b" * 64,
        )
        second = _REPO.reserve_send(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            draft_id=draft_id,
            job_id=job_id,
            idempotency_key="key-1",
            recipient_address=_ADDRESS,
            from_address=_FROM,
            # A different token, deliberately: the second attempt mints its own
            # and must still find the first row rather than write a second.
            unsubscribe_token_hash="c" * 64,
        )

        assert second.was_already_reserved is True
        assert second.send_id == first.send_id

        stored = session.execute(
            text("SELECT count(*) FROM outreach_send WHERE job_id = :j"), {"j": job_id}
        ).scalar_one()
        assert stored == 1

    def test_a_send_cannot_exist_without_a_job(
        self,
        session: Session,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        actor_id: uuid.UUID,
    ):
        """No synchronous send is *storable*, not merely forbidden by convention."""
        contact_id = _contact(session, tenant_id=tenant_id, unit_id=unit_id)
        draft_id = _draft(
            session,
            tenant_id=tenant_id,
            unit_id=unit_id,
            contact_id=contact_id,
            actor_id=actor_id,
        )

        with pytest.raises(IntegrityError):
            _REPO.reserve_send(
                session,
                tenant_id=tenant_id,
                owning_unit_id=unit_id,
                draft_id=draft_id,
                job_id=uuid.uuid4(),  # no such job
                idempotency_key="key-1",
                recipient_address=_ADDRESS,
                from_address=_FROM,
                unsubscribe_token_hash="d" * 64,
            )
        session.rollback()


class TestConcludeSend:
    """An outcome is written once, and cannot be a half-described one."""

    @pytest.fixture
    def send_id(
        self,
        session: Session,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> uuid.UUID:
        contact_id = _contact(session, tenant_id=tenant_id, unit_id=unit_id)
        draft_id = _draft(
            session,
            tenant_id=tenant_id,
            unit_id=unit_id,
            contact_id=contact_id,
            actor_id=actor_id,
        )
        job_id = _job(session, tenant_id=tenant_id, unit_id=unit_id)
        return _REPO.reserve_send(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            draft_id=draft_id,
            job_id=job_id,
            idempotency_key="key-conclude",
            recipient_address=_ADDRESS,
            from_address=_FROM,
            unsubscribe_token_hash="e" * 64,
        ).send_id

    def test_an_acceptance_records_its_provider_and_message_id(
        self, session: Session, tenant_id: uuid.UUID, send_id: uuid.UUID
    ):
        assert _REPO.conclude_send(
            session,
            tenant_id=tenant_id,
            send_id=send_id,
            disposition="accepted",
            concluded_at=_NOW,
            provider="fixture-email",
            provider_message_id="fixture-key-conclude",
        )

        row = _REPO.get_send(session, tenant_id=tenant_id, send_id=send_id)
        assert row is not None
        assert row.disposition == "accepted"
        assert row.provider_message_id == "fixture-key-conclude"
        assert row.failure_reason is None

    def test_a_second_conclusion_changes_nothing_and_says_so(
        self, session: Session, tenant_id: uuid.UUID, send_id: uuid.UUID
    ):
        """Overwriting `accepted` with a later `failed` would erase the record
        of a message already in somebody's inbox."""
        assert _REPO.conclude_send(
            session,
            tenant_id=tenant_id,
            send_id=send_id,
            disposition="accepted",
            concluded_at=_NOW,
            provider="fixture-email",
            provider_message_id="fixture-key-conclude",
        )

        assert not _REPO.conclude_send(
            session,
            tenant_id=tenant_id,
            send_id=send_id,
            disposition="failed",
            concluded_at=_NOW + timedelta(minutes=1),
            failure_reason="a later, wrong conclusion",
        )

        row = _REPO.get_send(session, tenant_id=tenant_id, send_id=send_id)
        assert row is not None and row.disposition == "accepted"

    def test_a_blocked_send_cannot_carry_a_provider_message_id(
        self, session: Session, tenant_id: uuid.UUID, send_id: uuid.UUID
    ):
        """`ck_outreach_send_message_id_means_accepted` — no fake receipts."""
        with pytest.raises(IntegrityError, match="ck_outreach_send_message_id_means_accepted"):
            _REPO.conclude_send(
                session,
                tenant_id=tenant_id,
                send_id=send_id,
                disposition="blocked",
                concluded_at=_NOW,
                provider_message_id="fixture-pretending",
                failure_reason="consent withdrawn",
            )
        session.rollback()

    def test_an_acceptance_without_a_provider_is_refused(
        self, session: Session, tenant_id: uuid.UUID, send_id: uuid.UUID
    ):
        """An accepted send with nothing to substantiate it is an unsupported claim."""
        with pytest.raises(IntegrityError, match="ck_outreach_send_accepted_has_provider"):
            _REPO.conclude_send(
                session,
                tenant_id=tenant_id,
                send_id=send_id,
                disposition="accepted",
                concluded_at=_NOW,
            )
        session.rollback()

    def test_a_refusal_must_say_why(
        self, session: Session, tenant_id: uuid.UUID, send_id: uuid.UUID
    ):
        with pytest.raises(IntegrityError, match="ck_outreach_send_failure_reason"):
            _REPO.conclude_send(
                session,
                tenant_id=tenant_id,
                send_id=send_id,
                disposition="blocked",
                concluded_at=_NOW,
            )
        session.rollback()


# ---------------------------------------------------------------------------
# Delivery events
# ---------------------------------------------------------------------------


class TestDeliveryEvents:
    """Append-only, and a replayed webhook is one event."""

    @pytest.fixture
    def send_id(
        self,
        session: Session,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> uuid.UUID:
        contact_id = _contact(session, tenant_id=tenant_id, unit_id=unit_id)
        draft_id = _draft(
            session,
            tenant_id=tenant_id,
            unit_id=unit_id,
            contact_id=contact_id,
            actor_id=actor_id,
        )
        job_id = _job(session, tenant_id=tenant_id, unit_id=unit_id)
        return _REPO.reserve_send(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            draft_id=draft_id,
            job_id=job_id,
            idempotency_key="key-events",
            recipient_address=_ADDRESS,
            from_address=_FROM,
            unsubscribe_token_hash="f" * 64,
        ).send_id

    def test_our_own_events_never_collide_despite_a_shared_null_provider_id(
        self, session: Session, tenant_id: uuid.UUID, send_id: uuid.UUID
    ):
        """PostgreSQL treats NULLs as distinct in a unique index — relied on here."""
        first = _REPO.append_delivery_event(
            session,
            tenant_id=tenant_id,
            send_id=send_id,
            event_type="queued",
            occurred_at=_NOW,
        )
        second = _REPO.append_delivery_event(
            session,
            tenant_id=tenant_id,
            send_id=send_id,
            event_type="accepted",
            occurred_at=_NOW + timedelta(seconds=1),
        )

        assert first is not None and second is not None and first != second

    def test_a_replayed_provider_webhook_becomes_one_event(
        self, session: Session, tenant_id: uuid.UUID, send_id: uuid.UUID
    ):
        common = {
            "tenant_id": tenant_id,
            "send_id": send_id,
            "event_type": "bounced",
            "occurred_at": _NOW,
            "provider_event_id": "evt_provider_123",
        }

        assert _REPO.append_delivery_event(session, **common) is not None
        assert _REPO.append_delivery_event(session, **common) is None

        events = _REPO.list_delivery_events(session, tenant_id=tenant_id, send_id=send_id)
        assert len(events) == 1

    def test_the_stream_is_ordered_by_when_things_happened(
        self, session: Session, tenant_id: uuid.UUID, send_id: uuid.UUID
    ):
        """Not by when we learned: a bounce that arrived late still bounced then."""
        _REPO.append_delivery_event(
            session,
            tenant_id=tenant_id,
            send_id=send_id,
            event_type="bounced",
            occurred_at=_NOW + timedelta(minutes=5),
            provider_event_id="evt_late",
        )
        _REPO.append_delivery_event(
            session,
            tenant_id=tenant_id,
            send_id=send_id,
            event_type="queued",
            occurred_at=_NOW,
        )

        events = _REPO.list_delivery_events(session, tenant_id=tenant_id, send_id=send_id)
        assert [e.event_type for e in events] == ["queued", "bounced"]

    def test_an_event_cannot_be_updated(
        self, session: Session, tenant_id: uuid.UUID, send_id: uuid.UUID
    ):
        """The `delivery_event_is_append_only` trigger, named directly.

        A guarantee nothing exercises is a guarantee nobody knows is still
        there, so this attempts the UPDATE rather than trusting the DDL.
        """
        event_id = _REPO.append_delivery_event(
            session,
            tenant_id=tenant_id,
            send_id=send_id,
            event_type="queued",
            occurred_at=_NOW,
        )
        session.flush()

        with pytest.raises(DBAPIError, match="append-only"):
            session.execute(
                text("UPDATE delivery_event SET event_type = 'delivered' WHERE id = :i"),
                {"i": event_id},
            )
        session.rollback()


# ---------------------------------------------------------------------------
# Suppression
# ---------------------------------------------------------------------------


class TestSuppression:
    """Unsubscribing twice is not an error, and does not move the clock."""

    def test_a_first_unsubscribe_is_recorded(self, session: Session, tenant_id: uuid.UUID):
        outcome = _REPO.suppress(
            session,
            tenant_id=tenant_id,
            address=_ADDRESS,
            source="unsubscribe_link",
            suppressed_at=_NOW,
        )

        assert outcome.was_already_suppressed is False
        assert _REPO.is_suppressed(session, tenant_id=tenant_id, address=_ADDRESS)

    def test_a_repeated_unsubscribe_is_a_no_op_that_says_so(
        self, session: Session, tenant_id: uuid.UUID
    ):
        """A person clicking twice has not made an error; showing them one would
        be alarming for no reason."""
        _REPO.suppress(
            session,
            tenant_id=tenant_id,
            address=_ADDRESS,
            source="unsubscribe_link",
            suppressed_at=_NOW,
        )

        again = _REPO.suppress(
            session,
            tenant_id=tenant_id,
            address=_ADDRESS,
            source="one_click",
            suppressed_at=_NOW + timedelta(days=1),
        )

        assert again.was_already_suppressed is True

    def test_the_first_request_is_the_one_that_stands(self, session: Session, tenant_id: uuid.UUID):
        """ "When did they ask us to stop" is answered by the first time they asked."""
        _REPO.suppress(
            session,
            tenant_id=tenant_id,
            address=_ADDRESS,
            source="unsubscribe_link",
            suppressed_at=_NOW,
        )
        _REPO.suppress(
            session,
            tenant_id=tenant_id,
            address=_ADDRESS,
            source="one_click",
            suppressed_at=_NOW + timedelta(days=1),
        )

        stored = session.execute(
            text(
                "SELECT suppressed_at, source FROM suppression_record "
                "WHERE tenant_id = :t AND address = :a"
            ),
            {"t": tenant_id, "a": _ADDRESS},
        ).one()
        assert stored.suppressed_at == _NOW
        assert stored.source == "unsubscribe_link"

    def test_a_token_resolves_to_its_send_without_a_tenant(
        self,
        session: Session,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        actor_id: uuid.UUID,
    ):
        """The unauthenticated lookup the unsubscribe POST depends on."""
        contact_id = _contact(session, tenant_id=tenant_id, unit_id=unit_id)
        draft_id = _draft(
            session,
            tenant_id=tenant_id,
            unit_id=unit_id,
            contact_id=contact_id,
            actor_id=actor_id,
        )
        job_id = _job(session, tenant_id=tenant_id, unit_id=unit_id)
        token_hash = "9" * 64
        _REPO.reserve_send(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            draft_id=draft_id,
            job_id=job_id,
            idempotency_key="key-token",
            recipient_address=_ADDRESS,
            from_address=_FROM,
            unsubscribe_token_hash=token_hash,
        )
        session.flush()

        row = _REPO.resolve_unsubscribe_token(session, token_hash=token_hash)

        assert row is not None
        assert row.tenant_id == tenant_id
        assert row.recipient_address == _ADDRESS

    def test_an_unknown_token_resolves_to_nothing(self, session: Session):
        assert _REPO.resolve_unsubscribe_token(session, token_hash="0" * 64) is None
