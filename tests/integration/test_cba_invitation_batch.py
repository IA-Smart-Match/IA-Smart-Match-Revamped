"""Invitation batches against PostgreSQL: the constraints, and what they refuse.

``tests/contract/test_cba_invitations_api.py`` owns the HTTP surface. This file
owns the half only a real database can state — the ``0029`` ``CHECK``s and unique
constraints, and the two guarded updates that make a repeated dispatch and a
repeated answer safe.

The assertions here are deliberately of the form "the database refused this", not
"the repository declined to try it". A rule enforced only in Python is a rule
that stops applying the moment a second writer appears — a fixture, a migration
backfill, somebody in psql — and the rules in question are the ones that would
let a delivery receipt read as a person agreeing to speak.

## What is worth reading first

:class:`TestTheTwoVocabulariesCannotCollide`. Everything else in this file is
ordinary integrity checking; that class is the card's whole point expressed as
DDL, and it fails if anybody ever teaches ``cba_invitation.response_status`` to
say ``accepted``.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from smartmatch_domain.cba_invitations import (
    DELIVERY_VOCABULARY,
    SPEAKER_RESPONSE_VALUES,
    InvitationStatus,
    SkipReason,
    SpeakerResponse,
)
from smartmatch_domain.outreach import OUTREACH_SEND_COMMAND_TYPE
from smartmatch_persistence.cba_invitations import InvitationRepository
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from tests.integration.conftest import ensure_owning_unit, unique_subject

pytestmark = pytest.mark.integration

_REPO = InvitationRepository()
_NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)

#: RFC 2606 reserved. Nothing this suite stores can address a real mailbox.
_ADDRESS = "speaker-0000@synthetic.invalid"

#: The date as a Connector would type it. Stored and rendered verbatim, never
#: parsed — which is the point of the column being Text, and is why this value is
#: deliberately not an ISO date.
_EVENT_DATE = "Friday, 12 June"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class _Rows:
    """One tenant's worth of set-up rows, built per test that needs them."""

    def __init__(self, engine: Engine, tenant_id: uuid.UUID, unit_id: uuid.UUID) -> None:
        self.engine = engine
        self.tenant_id = tenant_id
        self.unit_id = unit_id
        self.actor_id = uuid.uuid4()
        self.professional_id = uuid.uuid4()
        self.channel_id = uuid.uuid4()
        self.draft_id = uuid.uuid4()

        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                    "VALUES (:id, :t, :s, :e)"
                ),
                {
                    "id": self.actor_id,
                    "t": tenant_id,
                    "s": unique_subject("sub-invitation-connector"),
                    "e": "connector@example.invalid",
                },
            )
            conn.execute(
                text(
                    "INSERT INTO contact_channel (id, tenant_id, owning_unit_id, "
                    "professional_id, channel_kind, address, contact_state, "
                    "consent_source, consent_recorded_at) "
                    "VALUES (:id, :t, :u, :p, 'email', :a, 'active_candidate', "
                    "'self_service', :at)"
                ),
                {
                    "id": self.channel_id,
                    "t": tenant_id,
                    "u": unit_id,
                    "p": self.professional_id,
                    "a": _ADDRESS,
                    "at": _NOW,
                },
            )
            conn.execute(
                text(
                    "INSERT INTO outreach_draft (id, tenant_id, owning_unit_id, "
                    "contact_channel_id, template_id, content_status, subject, body, "
                    "status, version, created_by, approved_by, approved_at) "
                    "VALUES (:id, :t, :u, :c, 'cba.speaker_invitation.v1', 'synthetic', "
                    "'Invitation to speak', 'Hello...', 'approved', 1, :by, :by, :at)"
                ),
                {
                    "id": self.draft_id,
                    "t": tenant_id,
                    "u": unit_id,
                    "c": self.channel_id,
                    "by": self.actor_id,
                    "at": _NOW,
                },
            )

    def job(self) -> uuid.UUID:
        """A job row, so an invitation has something real to be dispatched as."""
        job_id = uuid.uuid4()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO job (id, tenant_id, owning_unit_id, command_type, "
                    "status, payload) VALUES (:id, :t, :u, :ct, 'queued', :p)"
                ),
                {
                    "id": job_id,
                    "t": self.tenant_id,
                    "u": self.unit_id,
                    "ct": OUTREACH_SEND_COMMAND_TYPE,
                    "p": f'{{"draft_id": "{self.draft_id}"}}',
                },
            )
        return job_id

    def reserve(self, session: Session, key: str = "batch-1") -> uuid.UUID:
        reservation = _REPO.reserve_batch(
            session,
            tenant_id=self.tenant_id,
            owning_unit_id=self.unit_id,
            idempotency_key=key,
            template_id="cba.speaker_invitation.v1",
            event_name="Spring Showcase",
            event_date=_EVENT_DATE,
            created_by_user_id=self.actor_id,
        )
        session.commit()
        return reservation.batch.id

    def invite(self, session: Session, batch_id: uuid.UUID, **overrides: object) -> uuid.UUID:
        """A pending invitation, addressed and composed, awaiting an answer."""
        fields: dict[str, object] = {
            "status": InvitationStatus.PENDING.value,
            "response_status": SpeakerResponse.AWAITING_RESPONSE.value,
            "contact_channel_id": self.channel_id,
            "recipient_address": _ADDRESS,
            "outreach_draft_id": self.draft_id,
        }
        fields.update(overrides)
        invitation_id = _REPO.add_invitation(
            session,
            tenant_id=self.tenant_id,
            owning_unit_id=self.unit_id,
            batch_id=batch_id,
            professional_id=uuid.uuid4(),
            **fields,  # type: ignore[arg-type]
        )
        session.commit()
        return invitation_id

    def raw_answered_insert(
        self, session: Session, batch_id: uuid.UUID, **overrides: object
    ) -> None:
        """Insert an *answered* invitation directly, bypassing the repository.

        Needed because :meth:`invite` cannot express an answer: ``add_invitation``
        deliberately takes no ``response_recorded_at``, since a freshly composed
        invitation has not been answered and a parameter for it would be a
        parameter somebody could pass.

        The point of the raw insert is isolation, not convenience. A row that
        names a response word *and* omits the timestamp violates two constraints
        at once, and PostgreSQL reports whichever it evaluates first — which
        would make a test asserting one constraint name pass or fail on
        evaluation order. Supplying a well-formed answer leaves exactly one rule
        that can refuse the row, so the test names the rule it is actually about.
        """
        columns: dict[str, object] = {
            "id": uuid.uuid4(),
            "tenant_id": self.tenant_id,
            "owning_unit_id": self.unit_id,
            "batch_id": batch_id,
            "professional_id": uuid.uuid4(),
            "status": InvitationStatus.DISPATCHED.value,
            "skip_reason": None,
            "contact_channel_id": self.channel_id,
            "recipient_address": _ADDRESS,
            "outreach_draft_id": self.draft_id,
            "outreach_send_job_id": self.job(),
            "dispatched_at": _NOW,
            "response_status": SpeakerResponse.ACCEPTED_INVITATION.value,
            "response_recorded_at": _NOW,
            "response_channel": "speaker_link",
            "response_recorded_by_user_id": None,
            "response_token_hash": None,
        }
        columns.update(overrides)
        names = ", ".join(columns)
        binds = ", ".join(f":{name}" for name in columns)
        session.execute(text(f"INSERT INTO cba_invitation ({names}) VALUES ({binds})"), columns)
        session.commit()


@pytest.fixture
def unit_id(engine: Engine, tenant_id: uuid.UUID) -> uuid.UUID:
    with engine.begin() as conn:
        return ensure_owning_unit(conn, tenant_id)


@pytest.fixture
def session(session_factory: sessionmaker[Session], tenant_id: uuid.UUID) -> Iterator[Session]:
    """Depends on ``tenant_id`` so it finalizes before the tenant sweep."""
    with session_factory() as s:
        yield s
        s.rollback()


@pytest.fixture
def rows(engine: Engine, tenant_id: uuid.UUID, unit_id: uuid.UUID) -> _Rows:
    return _Rows(engine, tenant_id, unit_id)


# ---------------------------------------------------------------------------
# The card's point, as DDL
# ---------------------------------------------------------------------------


class TestTheTwoVocabulariesCannotCollide:
    """A provider taking custody of bytes is not a person agreeing to speak."""

    def test_the_response_column_refuses_a_provider_disposition(
        self, session: Session, rows: _Rows
    ):
        """The single most important assertion in this file.

        ``'accepted'`` is what ``outreach_send.disposition`` says when a mail
        system took the message. If ``cba_invitation.response_status`` could also
        say it, then a tracking screen showing "accepted" would be ambiguous
        between "a server received some bytes" and "a professional has agreed to
        come and talk to students" — and an Event Host would book a room on the
        first.
        """
        batch_id = rows.reserve(session)

        with pytest.raises(IntegrityError, match="ck_cba_invitation_response_status"):
            rows.raw_answered_insert(session, batch_id, response_status="accepted")
        session.rollback()

    @pytest.mark.parametrize("disposition", sorted(DELIVERY_VOCABULARY))
    def test_no_delivery_word_at_all_is_storable_as_an_answer(
        self, session: Session, rows: _Rows, disposition: str
    ):
        """Every word the delivery side uses, not only the tempting one.

        Parametrized over the live enums rather than a transcribed list, so a
        disposition or delivery event added later is covered without this file
        being edited to learn about it.
        """
        batch_id = rows.reserve(session)

        with pytest.raises(IntegrityError, match="ck_cba_invitation_response_status"):
            rows.raw_answered_insert(session, batch_id, response_status=disposition)
        session.rollback()

    def test_the_two_sets_are_disjoint_in_the_code_as_well(self):
        """The DDL and the enums have to agree, so both are asserted."""
        assert not (SPEAKER_RESPONSE_VALUES & DELIVERY_VOCABULARY)


# ---------------------------------------------------------------------------
# Batch idempotency
# ---------------------------------------------------------------------------


class TestBatchIdempotency:
    """A Connector who double-clicks has not invited anybody twice."""

    def test_a_second_reservation_under_one_key_finds_the_first_batch(
        self, session: Session, rows: _Rows
    ):
        first = rows.reserve(session, key="batch-repeat")
        second = _REPO.reserve_batch(
            session,
            tenant_id=rows.tenant_id,
            owning_unit_id=rows.unit_id,
            idempotency_key="batch-repeat",
            template_id="cba.speaker_invitation.v1",
            event_name="A different event entirely",
            event_date="Tuesday, 1 July",
            created_by_user_id=rows.actor_id,
        )
        session.commit()

        assert second.was_replayed is True
        assert second.batch.id == first
        # And the *first* submission's text is what stands. A replay that rewrote
        # the event name would let a retry silently change what was already sent
        # to people.
        assert second.batch.event_name == "Spring Showcase"
        assert second.batch.event_date == _EVENT_DATE

    def test_two_units_may_use_the_same_key(
        self, session: Session, rows: _Rows, engine: Engine, tenant_id: uuid.UUID
    ):
        """The key is unique per unit, not per tenant.

        Two departments composing batches on the same afternoon must not collide
        on a key either of them might reasonably choose.
        """
        other_unit = uuid.uuid4()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                    "VALUES (:id, :t, CAST('iawest.otherinvites' AS ltree), "
                    "'department', 'Other')"
                ),
                {"id": other_unit, "t": tenant_id},
            )

        rows.reserve(session, key="shared-key")
        elsewhere = _REPO.reserve_batch(
            session,
            tenant_id=tenant_id,
            owning_unit_id=other_unit,
            idempotency_key="shared-key",
            template_id="cba.speaker_invitation.v1",
            event_name="Their event",
            event_date=_EVENT_DATE,
            created_by_user_id=rows.actor_id,
        )
        session.commit()

        assert elsewhere.was_replayed is False

    def test_one_person_cannot_hold_two_invitations_in_one_batch(
        self, session: Session, rows: _Rows
    ):
        """The replay guarantee at the row level, below any route's own check."""
        batch_id = rows.reserve(session)
        professional_id = uuid.uuid4()

        _REPO.add_invitation(
            session,
            tenant_id=rows.tenant_id,
            owning_unit_id=rows.unit_id,
            batch_id=batch_id,
            professional_id=professional_id,
            status=InvitationStatus.SKIPPED.value,
            response_status=SpeakerResponse.AWAITING_RESPONSE.value,
            skip_reason=SkipReason.NOT_ON_ROSTER.value,
        )
        session.commit()

        with pytest.raises(IntegrityError, match="uq_cba_invitation_batch_recipient"):
            _REPO.add_invitation(
                session,
                tenant_id=rows.tenant_id,
                owning_unit_id=rows.unit_id,
                batch_id=batch_id,
                professional_id=professional_id,
                status=InvitationStatus.SKIPPED.value,
                response_status=SpeakerResponse.AWAITING_RESPONSE.value,
                skip_reason=SkipReason.NOT_ON_ROSTER.value,
            )
            session.commit()
        session.rollback()


# ---------------------------------------------------------------------------
# A skip is a real outcome, and it is inert
# ---------------------------------------------------------------------------


class TestSkipsAreStoredAndInert:
    """The people a batch did not write to are rows, not an omission."""

    def test_a_skip_must_say_why(self, session: Session, rows: _Rows):
        batch_id = rows.reserve(session)

        with pytest.raises(IntegrityError, match="ck_cba_invitation_skip_reason"):
            _REPO.add_invitation(
                session,
                tenant_id=rows.tenant_id,
                owning_unit_id=rows.unit_id,
                batch_id=batch_id,
                professional_id=uuid.uuid4(),
                status=InvitationStatus.SKIPPED.value,
                response_status=SpeakerResponse.AWAITING_RESPONSE.value,
            )
            session.commit()
        session.rollback()

    def test_a_skip_cannot_carry_an_address(self, session: Session, rows: _Rows):
        """Nobody was written to, so there is no address this row can name."""
        batch_id = rows.reserve(session)

        with pytest.raises(IntegrityError, match="ck_cba_invitation_addressed"):
            rows.invite(
                session,
                batch_id,
                status=InvitationStatus.SKIPPED.value,
                skip_reason=SkipReason.CHANNEL_SUPPRESSED.value,
            )
        session.rollback()

    def test_a_skip_cannot_carry_an_answer(self, session: Session, rows: _Rows):
        """The constraint that stops a skip becoming a fabricated acceptance.

        Nobody sent this person anything. A row saying they accepted would be an
        answer to a message that does not exist, and it is exactly the row a
        careless "mark the whole batch as invited" would write.
        """
        batch_id = rows.reserve(session)

        with pytest.raises(IntegrityError, match="ck_cba_invitation_skipped_unanswered"):
            rows.raw_answered_insert(
                session,
                batch_id,
                status=InvitationStatus.SKIPPED.value,
                skip_reason=SkipReason.NO_CONTACT_CHANNEL.value,
                # A skip holds no channel, address, draft or job — the
                # `ck_cba_invitation_addressed` and `ck_cba_invitation_dispatched`
                # rules — so the row is well-formed in every respect except the
                # one under test.
                contact_channel_id=None,
                recipient_address=None,
                outreach_draft_id=None,
                outreach_send_job_id=None,
                dispatched_at=None,
            )
        session.rollback()

    def test_record_response_refuses_a_skipped_invitation(self, session: Session, rows: _Rows):
        """And the repository agrees with the constraint rather than relying on it."""
        batch_id = rows.reserve(session)
        invitation_id = _REPO.add_invitation(
            session,
            tenant_id=rows.tenant_id,
            owning_unit_id=rows.unit_id,
            batch_id=batch_id,
            professional_id=uuid.uuid4(),
            status=InvitationStatus.SKIPPED.value,
            response_status=SpeakerResponse.AWAITING_RESPONSE.value,
            skip_reason=SkipReason.CHANNEL_SUPPRESSED.value,
        )
        session.commit()

        wrote = _REPO.record_response(
            session,
            tenant_id=rows.tenant_id,
            invitation_id=invitation_id,
            response_status=SpeakerResponse.ACCEPTED_INVITATION.value,
            response_channel="speaker_link",
            recorded_at=_NOW,
        )
        session.commit()

        assert wrote is False
        stored = _REPO.get_invitation(
            session, tenant_id=rows.tenant_id, invitation_id=invitation_id
        )
        assert stored is not None
        assert stored.response_status == SpeakerResponse.AWAITING_RESPONSE.value


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


class TestDispatch:
    """A second dispatch must not put a second invitation in an inbox."""

    def test_marking_dispatched_records_the_job_and_the_time(self, session: Session, rows: _Rows):
        batch_id = rows.reserve(session)
        invitation_id = rows.invite(session, batch_id)
        job_id = rows.job()

        wrote = _REPO.mark_dispatched(
            session,
            tenant_id=rows.tenant_id,
            invitation_id=invitation_id,
            outreach_send_job_id=job_id,
            dispatched_at=_NOW,
        )
        session.commit()

        assert wrote is True
        stored = _REPO.get_invitation(
            session, tenant_id=rows.tenant_id, invitation_id=invitation_id
        )
        assert stored is not None
        assert stored.status == InvitationStatus.DISPATCHED.value
        assert stored.outreach_send_job_id == job_id
        assert stored.dispatched_at is not None
        # And nothing about the Speaker moved. Submitting a command is not an
        # answer, and this is the assertion that says so at the row level.
        assert stored.response_status == SpeakerResponse.AWAITING_RESPONSE.value

    def test_a_second_dispatch_of_the_same_invitation_writes_nothing(
        self, session: Session, rows: _Rows
    ):
        batch_id = rows.reserve(session)
        invitation_id = rows.invite(session, batch_id)
        first_job = rows.job()
        second_job = rows.job()

        _REPO.mark_dispatched(
            session,
            tenant_id=rows.tenant_id,
            invitation_id=invitation_id,
            outreach_send_job_id=first_job,
            dispatched_at=_NOW,
        )
        session.commit()

        wrote = _REPO.mark_dispatched(
            session,
            tenant_id=rows.tenant_id,
            invitation_id=invitation_id,
            outreach_send_job_id=second_job,
            dispatched_at=_NOW,
        )
        session.commit()

        assert wrote is False
        stored = _REPO.get_invitation(
            session, tenant_id=rows.tenant_id, invitation_id=invitation_id
        )
        assert stored is not None
        # The *first* job stands. Overwriting it would orphan the send already in
        # flight and leave two commands pointing at one person.
        assert stored.outreach_send_job_id == first_job

    def test_a_dispatched_invitation_leaves_the_pending_list(self, session: Session, rows: _Rows):
        """What makes a re-dispatch a no-op before any guard is reached."""
        batch_id = rows.reserve(session)
        invitation_id = rows.invite(session, batch_id)

        pending = _REPO.list_pending(session, tenant_id=rows.tenant_id, batch_id=batch_id)
        assert [row.id for row in pending] == [invitation_id]

        _REPO.mark_dispatched(
            session,
            tenant_id=rows.tenant_id,
            invitation_id=invitation_id,
            outreach_send_job_id=rows.job(),
            dispatched_at=_NOW,
        )
        session.commit()

        assert _REPO.list_pending(session, tenant_id=rows.tenant_id, batch_id=batch_id) == []


# ---------------------------------------------------------------------------
# Delivery is read, never copied
# ---------------------------------------------------------------------------


class TestDeliveryIsSeparate:
    """Two facts, two records, and two different kinds of unknown."""

    def test_an_undispatched_invitation_has_no_delivery_at_all(self, session: Session, rows: _Rows):
        batch_id = rows.reserve(session)
        rows.invite(session, batch_id)

        entries = _REPO.list_invitations(session, tenant_id=rows.tenant_id, batch_id=batch_id)

        assert len(entries) == 1
        assert entries[0].delivery is None
        assert entries[0].invitation.response_status == SpeakerResponse.AWAITING_RESPONSE.value

    def test_a_dispatched_invitation_whose_send_has_not_run_still_has_no_delivery(
        self, session: Session, rows: _Rows
    ):
        """A different unknown from the one above, and neither is a failure.

        The command exists; the handler has not written a send yet. Reporting
        this as "not delivered" would be the ADR-0011 collapse — an unknown
        rendered as a measured negative.
        """
        batch_id = rows.reserve(session)
        invitation_id = rows.invite(session, batch_id)
        _REPO.mark_dispatched(
            session,
            tenant_id=rows.tenant_id,
            invitation_id=invitation_id,
            outreach_send_job_id=rows.job(),
            dispatched_at=_NOW,
        )
        session.commit()

        entries = _REPO.list_invitations(session, tenant_id=rows.tenant_id, batch_id=batch_id)

        assert entries[0].invitation.status == InvitationStatus.DISPATCHED.value
        assert entries[0].delivery is None

    def test_a_concluded_send_is_reported_beside_the_answer_not_inside_it(
        self, session: Session, rows: _Rows, engine: Engine
    ):
        """The join that keeps the two facts adjacent and distinct.

        The provider accepted. The Speaker has still said nothing. Both are true
        at once, and this is the read that has to show both without letting
        either be mistaken for the other.
        """
        batch_id = rows.reserve(session)
        invitation_id = rows.invite(session, batch_id)
        job_id = rows.job()
        _REPO.mark_dispatched(
            session,
            tenant_id=rows.tenant_id,
            invitation_id=invitation_id,
            outreach_send_job_id=job_id,
            dispatched_at=_NOW,
        )
        session.commit()

        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO outreach_send (id, tenant_id, owning_unit_id, draft_id, "
                    "job_id, idempotency_key, recipient_address, from_address, "
                    "unsubscribe_token_hash, disposition, provider, provider_message_id, "
                    "concluded_at) VALUES (:id, :t, :u, :d, :j, :k, :a, :f, :h, "
                    "'accepted', 'fixture-email', 'msg-1', :at)"
                ),
                {
                    "id": uuid.uuid4(),
                    "t": rows.tenant_id,
                    "u": rows.unit_id,
                    "d": rows.draft_id,
                    "j": job_id,
                    "k": f"outreach-send:{job_id}",
                    "a": _ADDRESS,
                    "f": "noreply@example.invalid",
                    "h": _token_hash(secrets.token_urlsafe(32)),
                    "at": _NOW,
                },
            )

        entry = _REPO.list_invitations(session, tenant_id=rows.tenant_id, batch_id=batch_id)[0]

        assert entry.delivery is not None
        assert entry.delivery.disposition == "accepted"
        assert entry.delivery.provider == "fixture-email"
        # And the Speaker is still unasked. This pair of assertions is the whole
        # card in four lines.
        assert entry.invitation.response_status == SpeakerResponse.AWAITING_RESPONSE.value
        assert entry.invitation.response_recorded_at is None


# ---------------------------------------------------------------------------
# Answers
# ---------------------------------------------------------------------------


class TestResponses:
    """The first answer stands, and how it arrived is part of the record."""

    def _dispatched(self, session: Session, rows: _Rows) -> tuple[uuid.UUID, uuid.UUID]:
        batch_id = rows.reserve(session)
        invitation_id = rows.invite(session, batch_id)
        _REPO.mark_dispatched(
            session,
            tenant_id=rows.tenant_id,
            invitation_id=invitation_id,
            outreach_send_job_id=rows.job(),
            dispatched_at=_NOW,
        )
        session.commit()
        return batch_id, invitation_id

    def test_a_speakers_own_answer_names_no_coordinator(self, session: Session, rows: _Rows):
        _, invitation_id = self._dispatched(session, rows)

        wrote = _REPO.record_response(
            session,
            tenant_id=rows.tenant_id,
            invitation_id=invitation_id,
            response_status=SpeakerResponse.ACCEPTED_INVITATION.value,
            response_channel="speaker_link",
            recorded_at=_NOW,
        )
        session.commit()

        assert wrote is True
        stored = _REPO.get_invitation(
            session, tenant_id=rows.tenant_id, invitation_id=invitation_id
        )
        assert stored is not None
        assert stored.response_status == SpeakerResponse.ACCEPTED_INVITATION.value
        assert stored.response_channel == "speaker_link"
        # Nobody witnessed it, and the row says so rather than naming whoever
        # happened to be nearby.
        assert stored.response_recorded_by_user_id is None

    def test_a_connector_recorded_answer_must_name_the_coordinator(
        self, session: Session, rows: _Rows
    ):
        """The constraint that keeps the weaker evidentiary claim attributable."""
        _, invitation_id = self._dispatched(session, rows)

        with pytest.raises(IntegrityError, match="ck_cba_invitation_response_actor"):
            _REPO.record_response(
                session,
                tenant_id=rows.tenant_id,
                invitation_id=invitation_id,
                response_status=SpeakerResponse.DECLINED_INVITATION.value,
                response_channel="connector_recorded",
                recorded_at=_NOW,
            )
            session.commit()
        session.rollback()

    def test_a_second_answer_writes_nothing(self, session: Session, rows: _Rows):
        """The guard that stops a decline erasing an acceptance."""
        _, invitation_id = self._dispatched(session, rows)

        _REPO.record_response(
            session,
            tenant_id=rows.tenant_id,
            invitation_id=invitation_id,
            response_status=SpeakerResponse.ACCEPTED_INVITATION.value,
            response_channel="speaker_link",
            recorded_at=_NOW,
        )
        session.commit()

        wrote = _REPO.record_response(
            session,
            tenant_id=rows.tenant_id,
            invitation_id=invitation_id,
            response_status=SpeakerResponse.DECLINED_INVITATION.value,
            response_channel="speaker_link",
            recorded_at=_NOW,
        )
        session.commit()

        assert wrote is False
        stored = _REPO.get_invitation(
            session, tenant_id=rows.tenant_id, invitation_id=invitation_id
        )
        assert stored is not None
        assert stored.response_status == SpeakerResponse.ACCEPTED_INVITATION.value

    def test_a_pending_invitation_cannot_be_answered(self, session: Session, rows: _Rows):
        """Nothing was submitted, so there is nothing to have answered."""
        batch_id = rows.reserve(session)
        invitation_id = rows.invite(session, batch_id)

        wrote = _REPO.record_response(
            session,
            tenant_id=rows.tenant_id,
            invitation_id=invitation_id,
            response_status=SpeakerResponse.ACCEPTED_INVITATION.value,
            response_channel="speaker_link",
            recorded_at=_NOW,
        )
        session.commit()

        assert wrote is False


class TestResponseTokens:
    """The token is the whole authorization, and it is never stored."""

    def test_a_token_resolves_to_its_invitation_without_a_tenant(
        self, session: Session, rows: _Rows
    ):
        """Deliberately un-scoped: the public respond route has no tenant to scope by."""
        batch_id = rows.reserve(session)
        token = secrets.token_urlsafe(32)
        invitation_id = rows.invite(session, batch_id, response_token_hash=_token_hash(token))

        found = _REPO.resolve_response_token(session, token_hash=_token_hash(token))

        assert found is not None
        assert found.id == invitation_id
        assert found.tenant_id == rows.tenant_id

    def test_an_unknown_token_resolves_to_nothing(self, session: Session, rows: _Rows):
        """And the route answers identically either way — see the router."""
        rows.reserve(session)

        assert (
            _REPO.resolve_response_token(session, token_hash=_token_hash(secrets.token_urlsafe(32)))
            is None
        )

    def test_the_token_itself_is_nowhere_in_the_row(self, session: Session, rows: _Rows):
        """Possession of the database must not confer the ability to answer.

        Asserted over the whole row's text rather than over the one column, so a
        later card that adds a convenience copy of the token somewhere else on
        this table fails here.
        """
        batch_id = rows.reserve(session)
        token = secrets.token_urlsafe(32)
        invitation_id = rows.invite(session, batch_id, response_token_hash=_token_hash(token))

        with rows.engine.begin() as conn:
            rendered = conn.execute(
                text("SELECT cba_invitation::text FROM cba_invitation WHERE id = :i"),
                {"i": invitation_id},
            ).scalar_one()

        assert token not in rendered
        assert _token_hash(token) in rendered
