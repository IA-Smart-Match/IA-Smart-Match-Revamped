"""``outreach.send`` end to end against PostgreSQL and a fixture provider (card L5).

An integration test rather than a unit test, and deliberately so. The handler's
whole design is about which writes survive which failures — the reservation must
outlive the refusal it caused, the refusal record must outlive the exception that
follows it, the pipeline advance must not — and none of that is observable
against a mock session. The interesting assertions here are all of the form
"after the handler raised, what is actually in the database", which requires a
real one.

The provider is the fixture adapter, which records what it was asked to send
instead of sending it. That is not a weaker test than a mocked provider: it is
the same adapter the pilot runs against, so what these tests assert about
``FixtureEmailProvider.sent`` is what a coordinator's message actually looks
like.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from smartmatch_domain.jobs import JobState
from smartmatch_domain.outreach import OUTREACH_SEND_COMMAND_TYPE
from smartmatch_persistence.jobs import JobRecord
from smartmatch_persistence.outreach import OutreachRepository
from smartmatch_providers.fixtures import FixtureEmailProvider
from smartmatch_worker.handlers import CommandContext, PolicyFailure, ProviderFailure
from smartmatch_worker.outreach import (
    SYNTHETIC_UNSUBSCRIBE_SECRET,
    build_outreach_send_handler,
    unsubscribe_token,
)
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from tests.integration.conftest import ensure_owning_unit, unique_subject

pytestmark = pytest.mark.integration

_REPO = OutreachRepository()
_NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
_ADDRESS = "professional-0000@synthetic.invalid"
_FROM = "noreply@example.invalid"
_BASE = "http://localhost:8080"


class _RecordingProvider:
    """An adapter that raises. Used to exercise the ProviderFailure branch."""

    name = "exploding-email"

    def send(self, request: Any) -> Any:
        raise RuntimeError("the provider is down")


@pytest.fixture
def session(session_factory: sessionmaker[Session], tenant_id: uuid.UUID) -> Iterator[Session]:
    """The executor's session, for the writes the executor would own.

    Depends on ``tenant_id`` so it is finalized *before* the tenant sweep — see
    ``test_outreach_persistence.py``'s fixture for why that ordering matters.

    Unlike that module's, this one commits: the handler under test uses a
    *separate* session that commits as it goes, so a test's setup rows have to be
    visible to it. Everything written here is inside the per-test tenant, which
    the ``tenant_id`` fixture deletes.
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
                "sub": unique_subject("sub-outreach-sender"),
                "email": "coordinator@example.invalid",
            },
        )
    return account_id


class _Fixtures:
    """One tenant's worth of set-up rows, built once per test that needs them."""

    def __init__(
        self,
        engine: Engine,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        self.engine = engine
        self.tenant_id = tenant_id
        self.unit_id = unit_id
        self.actor_id = actor_id
        self.contact_id = uuid.uuid4()
        self.draft_id = uuid.uuid4()
        self.job_id = uuid.uuid4()

    def build(
        self,
        *,
        contact_state: str = "active_candidate",
        consent_source: str = "self_service",
        draft_status: str = "approved",
        content_status: str = "synthetic",
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO contact_channel (id, tenant_id, owning_unit_id, "
                    "professional_id, channel_kind, address, contact_state, "
                    "consent_source, consent_recorded_at) "
                    "VALUES (:id, :t, :u, :p, 'email', :a, :s, :c, :at)"
                ),
                {
                    "id": self.contact_id,
                    "t": self.tenant_id,
                    "u": self.unit_id,
                    "p": uuid.uuid4(),
                    "a": _ADDRESS,
                    "s": contact_state,
                    "c": consent_source,
                    "at": _NOW,
                },
            )
            conn.execute(
                text(
                    "INSERT INTO outreach_draft (id, tenant_id, owning_unit_id, "
                    "contact_channel_id, template_id, content_status, subject, body, "
                    "status, version, created_by, approved_by, approved_at) "
                    "VALUES (:id, :t, :u, :c, 'pilot.event_invitation.v1', :cs, "
                    ":subj, :body, :st, 1, :by, :appby, :appat)"
                ),
                {
                    "id": self.draft_id,
                    "t": self.tenant_id,
                    "u": self.unit_id,
                    "c": self.contact_id,
                    "cs": content_status,
                    "subj": "Spring Showcase on Friday, 12 June",
                    "body": "Hello Sam Rivera,\n\nNorthside Robotics is hosting...\n",
                    "st": draft_status,
                    "by": self.actor_id,
                    "appby": self.actor_id if draft_status == "approved" else None,
                    "appat": _NOW if draft_status == "approved" else None,
                },
            )
            conn.execute(
                text(
                    "INSERT INTO job (id, tenant_id, owning_unit_id, command_type, "
                    "status, payload) VALUES (:id, :t, :u, :ct, 'running', :p)"
                ),
                {
                    "id": self.job_id,
                    "t": self.tenant_id,
                    "u": self.unit_id,
                    "ct": OUTREACH_SEND_COMMAND_TYPE,
                    "p": f'{{"draft_id": "{self.draft_id}"}}',
                },
            )

    def suppress(self) -> None:
        """Record an unsubscribe, as if the recipient clicked between steps."""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO suppression_record (id, tenant_id, address, "
                    "suppressed_at, source) VALUES (:i, :t, :a, :at, 'unsubscribe_link')"
                ),
                {"i": uuid.uuid4(), "t": self.tenant_id, "a": _ADDRESS, "at": _NOW},
            )

    def context(self, session: Session, payload: dict[str, Any] | None = None) -> CommandContext:
        return CommandContext(
            job=JobRecord(
                id=self.job_id,
                tenant_id=self.tenant_id,
                command_type=OUTREACH_SEND_COMMAND_TYPE,
                status=JobState.RUNNING,
                owning_unit_id=self.unit_id,
                payload={"draft_id": str(self.draft_id)} if payload is None else payload,
                actor_id=self.actor_id,
                created_at=_NOW,
                updated_at=_NOW,
            ),
            emit=lambda event: 1,
            session=session,
        )


@pytest.fixture
def rows(
    engine: Engine, tenant_id: uuid.UUID, unit_id: uuid.UUID, actor_id: uuid.UUID
) -> _Fixtures:
    return _Fixtures(engine, tenant_id, unit_id, actor_id)


def _handler(
    session_factory: sessionmaker[Session],
    provider: Any,
    *,
    live_mode: bool = False,
    unsubscribe_secret: str | None = None,
) -> Any:
    return build_outreach_send_handler(
        session_factory=session_factory,
        provider=provider,
        from_address=_FROM,
        public_base_url=_BASE,
        unsubscribe_secret=unsubscribe_secret,
        live_mode=live_mode,
        clock=lambda: _NOW,
    )


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


class TestAcceptedSend:
    """What a message actually looks like when the provider takes it."""

    def test_the_provider_receives_the_approved_text_and_both_unsubscribe_headers(
        self,
        session: Session,
        session_factory: sessionmaker[Session],
        rows: _Fixtures,
    ):
        rows.build()
        provider = FixtureEmailProvider()

        result = _handler(session_factory, provider)(rows.context(session))

        assert result.state is JobState.SUCCEEDED
        assert len(provider.sent) == 1
        sent = provider.sent[0]
        assert sent.to_address == _ADDRESS
        assert sent.subject == "Spring Showcase on Friday, 12 June"
        assert sent.approval_id == str(rows.draft_id)
        assert sent.approved_draft_version == 1
        # RFC 8058 requires the POST variant alongside the link, and
        # `SendRequest.__post_init__` refuses a request missing either.
        assert sent.list_unsubscribe_url.startswith(f"{_BASE}/u/")
        assert sent.list_unsubscribe_post_url == f"{_BASE}/v1/unsubscribe"

    def test_the_summary_says_accepted_and_never_sent_or_delivered(
        self,
        session: Session,
        session_factory: sessionmaker[Session],
        rows: _Fixtures,
    ):
        """A provider taking custody is not a person receiving anything."""
        rows.build()

        result = _handler(session_factory, FixtureEmailProvider())(rows.context(session))

        assert result.summary["disposition"] == "accepted"
        assert "sent" not in result.summary.values()
        assert "delivered" not in result.summary.values()

    def test_the_send_row_and_its_delivery_stream_are_recorded(
        self,
        session: Session,
        session_factory: sessionmaker[Session],
        rows: _Fixtures,
        tenant_id: uuid.UUID,
    ):
        rows.build()

        _handler(session_factory, FixtureEmailProvider())(rows.context(session))

        stored = _REPO.get_send_for_job(session, tenant_id=tenant_id, job_id=rows.job_id)
        assert stored is not None
        assert stored.disposition == "accepted"
        assert stored.provider == "fixture-email"
        assert stored.provider_message_id is not None
        assert stored.failure_reason is None

        events = _REPO.list_delivery_events(session, tenant_id=tenant_id, send_id=stored.id)
        assert [e.event_type for e in events] == ["queued", "accepted"]

    def test_the_stored_token_hash_is_not_the_token(
        self,
        session: Session,
        session_factory: sessionmaker[Session],
        rows: _Fixtures,
        tenant_id: uuid.UUID,
    ):
        """The table must not be a set of working unsubscribe links."""
        rows.build()
        provider = FixtureEmailProvider()

        _handler(session_factory, provider)(rows.context(session))

        token = provider.sent[0].list_unsubscribe_url.rsplit("/", 1)[-1]
        stored = _REPO.get_send_for_job(session, tenant_id=tenant_id, job_id=rows.job_id)
        assert stored is not None
        row = session.execute(
            text("SELECT unsubscribe_token_hash FROM outreach_send WHERE id = :i"),
            {"i": stored.id},
        ).one()
        assert row.unsubscribe_token_hash != token
        assert _REPO.resolve_unsubscribe_token(session, token_hash=token) is None


# ---------------------------------------------------------------------------
# The refusals — the reason the gate runs a second time
# ---------------------------------------------------------------------------


class TestDeliveryTimeRefusal:
    """State that changed after approval, and what the handler does about it."""

    def test_consent_withdrawn_after_approval_blocks_the_send(
        self,
        session: Session,
        session_factory: sessionmaker[Session],
        rows: _Fixtures,
    ):
        """The card's central case.

        The draft is approved. The recipient was eligible when it was composed.
        They then clicked unsubscribe, and the queued command is executed
        afterwards. Nothing about the draft changed, and no message may go out.
        """
        rows.build()
        rows.suppress()
        provider = FixtureEmailProvider()

        with pytest.raises(PolicyFailure, match="suppressed"):
            _handler(session_factory, provider)(rows.context(session))

        assert provider.sent == [], "a suppressed recipient was written to"

    def test_the_refusal_survives_the_exception_that_follows_it(
        self,
        session: Session,
        session_factory: sessionmaker[Session],
        rows: _Fixtures,
        tenant_id: uuid.UUID,
    ):
        """The handler-owned session earns its place here.

        The executor rolls its own session back on any handler exception. If the
        refusal had been staged there, "we declined to contact this person, and
        here is why" would have vanished along with the failure it explains.
        """
        rows.build()
        rows.suppress()

        with pytest.raises(PolicyFailure):
            _handler(session_factory, FixtureEmailProvider())(rows.context(session))

        stored = _REPO.get_send_for_job(session, tenant_id=tenant_id, job_id=rows.job_id)
        assert stored is not None
        assert stored.disposition == "blocked"
        assert stored.failure_reason is not None and "suppressed" in stored.failure_reason
        assert stored.provider_message_id is None

        events = _REPO.list_delivery_events(session, tenant_id=tenant_id, send_id=stored.id)
        assert [e.event_type for e in events] == ["queued", "blocked"]

    def test_an_unapproved_draft_is_refused(
        self,
        session: Session,
        session_factory: sessionmaker[Session],
        rows: _Fixtures,
    ):
        rows.build(draft_status="draft")
        provider = FixtureEmailProvider()

        with pytest.raises(PolicyFailure, match="approved"):
            _handler(session_factory, provider)(rows.context(session))

        assert provider.sent == []

    def test_synthetic_copy_is_refused_in_live_mode(
        self,
        session: Session,
        session_factory: sessionmaker[Session],
        rows: _Fixtures,
    ):
        """OQ-003: the pilot runs the whole path; unreviewed copy never goes live."""
        rows.build()
        provider = FixtureEmailProvider()

        with pytest.raises(PolicyFailure, match="synthetic"):
            _handler(session_factory, provider, live_mode=True, unsubscribe_secret="a-real-key")(
                rows.context(session)
            )

        assert provider.sent == []

    def test_a_draft_from_another_unit_is_refused(
        self,
        session: Session,
        session_factory: sessionmaker[Session],
        rows: _Fixtures,
        engine: Engine,
        tenant_id: uuid.UUID,
    ):
        """Not a lookup miss: a command whose authorization does not cover its target."""
        rows.build()
        other_unit = uuid.uuid4()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                    "VALUES (:i, :t, CAST(:p AS ltree), 'school', 'Other')"
                ),
                {"i": other_unit, "t": tenant_id, "p": "iawest.other"},
            )
            conn.execute(
                text("UPDATE job SET owning_unit_id = :u WHERE id = :i"),
                {"u": other_unit, "i": rows.job_id},
            )

        # `JobRecord` is frozen, so the command is rebuilt against the other
        # unit rather than mutated — which is also the honest shape: this is a
        # different command, filed under a unit whose authorization does not
        # reach the draft it names.
        moved = _Fixtures(engine, tenant_id, other_unit, rows.actor_id)
        moved.draft_id, moved.job_id = rows.draft_id, rows.job_id

        with pytest.raises(PolicyFailure, match="different organizational unit"):
            _handler(session_factory, FixtureEmailProvider())(moved.context(session))


class TestProviderFailure:
    """A dependency that failed is not a policy that refused."""

    def test_a_provider_error_is_redrivable_not_terminal(
        self,
        session: Session,
        session_factory: sessionmaker[Session],
        rows: _Fixtures,
    ):
        rows.build()

        with pytest.raises(ProviderFailure, match="provider is down"):
            _handler(session_factory, _RecordingProvider())(rows.context(session))

    def test_the_failure_is_recorded_with_its_reason(
        self,
        session: Session,
        session_factory: sessionmaker[Session],
        rows: _Fixtures,
        tenant_id: uuid.UUID,
    ):
        rows.build()

        with pytest.raises(ProviderFailure):
            _handler(session_factory, _RecordingProvider())(rows.context(session))

        stored = _REPO.get_send_for_job(session, tenant_id=tenant_id, job_id=rows.job_id)
        assert stored is not None
        assert stored.disposition == "failed"
        assert stored.provider_message_id is None


# ---------------------------------------------------------------------------
# Re-drive
# ---------------------------------------------------------------------------


class TestRedrive:
    """At-least-once delivery of a command must not mean two messages."""

    def test_a_second_execution_does_not_call_the_provider_again(
        self,
        session: Session,
        session_factory: sessionmaker[Session],
        rows: _Fixtures,
    ):
        rows.build()
        provider = FixtureEmailProvider()
        handler = _handler(session_factory, provider)

        handler(rows.context(session))
        second = handler(rows.context(session))

        assert len(provider.sent) == 1, "the recipient was written to twice"
        assert second.summary["replayed"] is True
        assert second.summary["disposition"] == "accepted"

    def test_a_second_execution_reports_a_recorded_refusal_rather_than_retrying(
        self,
        session: Session,
        session_factory: sessionmaker[Session],
        rows: _Fixtures,
    ):
        """A re-driven blocked send succeeds *as a job* and still sends nothing.

        "Did this command execute" and "did a message go out" are different
        questions; the second is answered by `disposition`, never flattened into
        the job state.
        """
        rows.build()
        rows.suppress()
        provider = FixtureEmailProvider()
        handler = _handler(session_factory, provider)

        with pytest.raises(PolicyFailure):
            handler(rows.context(session))

        replay = handler(rows.context(session))

        assert replay.state is JobState.SUCCEEDED
        assert replay.summary["disposition"] == "blocked"
        assert provider.sent == []

    def test_the_unsubscribe_token_is_the_same_on_every_execution(self, rows: _Fixtures):
        """Derived, not random — the row stores only a hash, so a re-drive could
        not recover a random token and would mint a link that unsubscribes
        nothing."""
        first = unsubscribe_token(SYNTHETIC_UNSUBSCRIBE_SECRET, rows.job_id)
        second = unsubscribe_token(SYNTHETIC_UNSUBSCRIBE_SECRET, rows.job_id)

        assert first == second
        assert first != unsubscribe_token(SYNTHETIC_UNSUBSCRIBE_SECRET, uuid.uuid4())


# ---------------------------------------------------------------------------
# Payload and configuration
# ---------------------------------------------------------------------------


class TestPayloadAndConfiguration:
    """Refusals that happen before any recipient is looked up."""

    def test_a_job_with_no_payload_fails_terminally(
        self,
        session: Session,
        session_factory: sessionmaker[Session],
        rows: _Fixtures,
        tenant_id: uuid.UUID,
    ):
        rows.build()
        context = CommandContext(
            job=JobRecord(
                id=rows.job_id,
                tenant_id=tenant_id,
                command_type=OUTREACH_SEND_COMMAND_TYPE,
                status=JobState.RUNNING,
                owning_unit_id=rows.unit_id,
                payload=None,
                actor_id=rows.actor_id,
                created_at=_NOW,
                updated_at=_NOW,
            ),
            emit=lambda event: 1,
            session=session,
        )

        with pytest.raises(PolicyFailure, match="no payload"):
            _handler(session_factory, FixtureEmailProvider())(context)

    def test_a_payload_naming_no_draft_is_refused(
        self,
        session: Session,
        session_factory: sessionmaker[Session],
        rows: _Fixtures,
    ):
        rows.build()

        with pytest.raises(PolicyFailure, match="draft_id is missing"):
            _handler(session_factory, FixtureEmailProvider())(rows.context(session, payload={}))

    def test_live_mode_without_a_secret_refuses_to_build_at_all(
        self, session_factory: sessionmaker[Session]
    ):
        """At boot, not at send time.

        A misconfigured live deployment must not accept commands it will refuse
        one at a time — and silently minting live unsubscribe links with the key
        printed in `smartmatch_worker/outreach.py` is the one outcome that has
        to be impossible.
        """
        with pytest.raises(ValueError, match="SMARTMATCH_UNSUBSCRIBE_SECRET"):
            _handler(session_factory, FixtureEmailProvider(), live_mode=True)
