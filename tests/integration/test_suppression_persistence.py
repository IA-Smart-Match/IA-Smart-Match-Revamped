"""``SuppressionRepository`` against a real PostgreSQL (B26 T6b-3 plan §5.1).

The one module that reads or writes ``suppression_record``. Checked here:

1. ``record`` merges by rank into the address's one row: insert, no-op,
   escalate, re-open.
2. ``lift`` touches only the sources the verdict allowed for *this* address
   (S6), and sets both lift columns.
3. ``ck_suppression_record_lift_source`` refuses a raw lift of a bounce,
   complaint or coordinator row, whatever the application does.
4. ``active_suppression_exists`` ignores a lifted row, per tenant.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from smartmatch_domain.suppression import MergeAction, SuppressionSource
from smartmatch_persistence import schema
from smartmatch_persistence.suppression import (
    SuppressionLiftError,
    SuppressionRepository,
    active_suppression_exists,
)
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from tests.integration.conftest import ensure_owning_unit, unique_subject

pytestmark = pytest.mark.integration

_REPO = SuppressionRepository()
_NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
_ADDRESS = "speaker-0001@synthetic.invalid"
_SPEAKER_ONLY = frozenset({SuppressionSource.SPEAKER_PORTAL})
_LOGIN_SET = frozenset(
    {
        SuppressionSource.SPEAKER_PORTAL,
        SuppressionSource.UNSUBSCRIBE_LINK,
        SuppressionSource.ONE_CLICK,
    }
)


@pytest.fixture
def session(session_factory: sessionmaker[Session], tenant_id: uuid.UUID) -> Iterator[Session]:
    """Uncommitted and rolled back; depends on ``tenant_id`` so it finalizes first."""
    with session_factory() as s:
        yield s
        s.rollback()


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
                "sub": unique_subject("sub-suppression-speaker"),
                "email": _ADDRESS,
            },
        )
    return account_id


def _stored(session: Session, tenant_id: uuid.UUID, address: str = _ADDRESS) -> sa.Row:  # type: ignore[type-arg]
    return session.execute(
        text(
            "SELECT source, suppressed_at, origin_send_id, lifted_at, lifted_by_user_id "
            "FROM suppression_record WHERE tenant_id = :t AND address = :a"
        ),
        {"t": tenant_id, "a": address},
    ).one()


def _record(session: Session, tenant_id: uuid.UUID, source: SuppressionSource, at: datetime):
    return _REPO.record(session, tenant_id=tenant_id, address=_ADDRESS, source=source, at=at)


class TestRecord:
    def test_a_first_suppression_inserts(self, session: Session, tenant_id: uuid.UUID):
        outcome = _record(session, tenant_id, SuppressionSource.UNSUBSCRIBE_LINK, _NOW)
        assert outcome.write.action is MergeAction.INSERT
        assert outcome.was_already_suppressed is False
        assert _REPO.is_active(session, tenant_id=tenant_id, address=_ADDRESS)

    def test_an_equal_or_lower_rank_is_a_noop(self, session: Session, tenant_id: uuid.UUID):
        _record(session, tenant_id, SuppressionSource.COORDINATOR, _NOW)
        outcome = _record(
            session, tenant_id, SuppressionSource.SPEAKER_PORTAL, _NOW + timedelta(days=1)
        )
        assert outcome.write.action is MergeAction.NOOP
        assert outcome.was_already_suppressed is True
        row = _stored(session, tenant_id)
        assert (row.source, row.suppressed_at) == ("coordinator", _NOW)

    def test_a_higher_rank_escalates_and_keeps_the_first_date(
        self, session: Session, tenant_id: uuid.UUID
    ):
        _record(session, tenant_id, SuppressionSource.SPEAKER_PORTAL, _NOW)
        outcome = _record(session, tenant_id, SuppressionSource.BOUNCE, _NOW + timedelta(days=1))
        assert outcome.write.action is MergeAction.ESCALATE
        assert outcome.was_already_suppressed is True
        row = _stored(session, tenant_id)
        assert (row.source, row.suppressed_at) == ("bounce", _NOW)

    def test_a_suppression_after_a_lift_reopens(
        self, session: Session, tenant_id: uuid.UUID, actor_id: uuid.UUID
    ):
        _record(session, tenant_id, SuppressionSource.SPEAKER_PORTAL, _NOW)
        _REPO.lift(
            session,
            tenant_id=tenant_id,
            address=_ADDRESS,
            allowed_sources=_SPEAKER_ONLY,
            lifted_at=_NOW + timedelta(hours=1),
            lifted_by_user_id=actor_id,
        )
        later = _NOW + timedelta(days=2)
        outcome = _record(session, tenant_id, SuppressionSource.UNSUBSCRIBE_LINK, later)
        assert outcome.write.action is MergeAction.REOPEN
        assert outcome.was_already_suppressed is False
        row = _stored(session, tenant_id)
        assert (row.source, row.suppressed_at, row.lifted_at, row.lifted_by_user_id) == (
            "unsubscribe_link",
            later,
            None,
            None,
        )
        assert _REPO.is_active(session, tenant_id=tenant_id, address=_ADDRESS)


class TestLift:
    def test_lift_sets_both_columns(
        self, session: Session, tenant_id: uuid.UUID, actor_id: uuid.UUID
    ):
        _record(session, tenant_id, SuppressionSource.UNSUBSCRIBE_LINK, _NOW)
        at = _NOW + timedelta(hours=1)
        _REPO.lift(
            session,
            tenant_id=tenant_id,
            address=_ADDRESS,
            allowed_sources=_LOGIN_SET,
            lifted_at=at,
            lifted_by_user_id=actor_id,
        )
        row = _stored(session, tenant_id)
        assert (row.lifted_at, row.lifted_by_user_id) == (at, actor_id)
        assert not _REPO.is_active(session, tenant_id=tenant_id, address=_ADDRESS)

    def test_lift_only_touches_the_allowed_sources(
        self, session: Session, tenant_id: uuid.UUID, actor_id: uuid.UUID
    ):
        """S6: the set is the verdict's for this address, never the fixed liftable list."""
        _record(session, tenant_id, SuppressionSource.UNSUBSCRIBE_LINK, _NOW)
        with pytest.raises(SuppressionLiftError):
            _REPO.lift(
                session,
                tenant_id=tenant_id,
                address=_ADDRESS,
                allowed_sources=_SPEAKER_ONLY,
                lifted_at=_NOW + timedelta(hours=1),
                lifted_by_user_id=actor_id,
            )
        assert _stored(session, tenant_id).lifted_at is None

    def test_lift_of_nothing_raises(
        self, session: Session, tenant_id: uuid.UUID, actor_id: uuid.UUID
    ):
        with pytest.raises(SuppressionLiftError):
            _REPO.lift(
                session,
                tenant_id=tenant_id,
                address=_ADDRESS,
                allowed_sources=_LOGIN_SET,
                lifted_at=_NOW,
                lifted_by_user_id=actor_id,
            )

    def test_lift_at_suppressed_at_satisfies_the_check(
        self, session: Session, tenant_id: uuid.UUID, actor_id: uuid.UUID
    ):
        """S2 boundary: ``now = max(utc_now(), suppressed_at)`` may equal it."""
        _record(session, tenant_id, SuppressionSource.SPEAKER_PORTAL, _NOW)
        _REPO.lift(
            session,
            tenant_id=tenant_id,
            address=_ADDRESS,
            allowed_sources=_SPEAKER_ONLY,
            lifted_at=_NOW,
            lifted_by_user_id=actor_id,
        )
        session.flush()
        assert _stored(session, tenant_id).lifted_at == _NOW

    @pytest.mark.parametrize("source", ["bounce", "complaint", "coordinator"])
    def test_a_raw_lift_of_bounce_complaint_or_coordinator_is_refused_by_the_check(
        self, session: Session, tenant_id: uuid.UUID, actor_id: uuid.UUID, source: str
    ):
        _record(session, tenant_id, SuppressionSource(source), _NOW)
        with pytest.raises(IntegrityError, match="ck_suppression_record_lift_source"):
            session.execute(
                text(
                    "UPDATE suppression_record SET lifted_at = :at, lifted_by_user_id = :u "
                    "WHERE tenant_id = :t AND address = :a"
                ),
                {"at": _NOW + timedelta(hours=1), "u": actor_id, "t": tenant_id, "a": _ADDRESS},
            )


class TestActiveSuppressionExists:
    def _contact(self, session: Session, tenant_id: uuid.UUID, address: str) -> uuid.UUID:
        unit_id = ensure_owning_unit(session, tenant_id)
        contact_id = uuid.uuid4()
        session.execute(
            text(
                "INSERT INTO contact_channel (id, tenant_id, owning_unit_id, professional_id, "
                "channel_kind, address, contact_state) "
                "VALUES (:id, :t, :u, :p, 'email', :a, 'discovered')"
            ),
            {"id": contact_id, "t": tenant_id, "u": unit_id, "p": uuid.uuid4(), "a": address},
        )
        return contact_id

    def _flag(self, session: Session, contact_id: uuid.UUID) -> bool:
        channel = schema.contact_channel
        return bool(
            session.execute(
                sa.select(active_suppression_exists(channel)).where(channel.c.id == contact_id)
            ).scalar_one()
        )

    def test_active_suppression_exists_ignores_a_lifted_row(
        self, session: Session, tenant_id: uuid.UUID, actor_id: uuid.UUID
    ):
        contact_id = self._contact(session, tenant_id, _ADDRESS)
        assert self._flag(session, contact_id) is False
        _record(session, tenant_id, SuppressionSource.SPEAKER_PORTAL, _NOW)
        assert self._flag(session, contact_id) is True
        _REPO.lift(
            session,
            tenant_id=tenant_id,
            address=_ADDRESS,
            allowed_sources=_SPEAKER_ONLY,
            lifted_at=_NOW + timedelta(hours=1),
            lifted_by_user_id=actor_id,
        )
        assert self._flag(session, contact_id) is False

    def test_lift_in_one_tenant_leaves_another_suppressed(
        self,
        session: Session,
        engine: Engine,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
    ):
        other_tenant = uuid.uuid4()
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO tenant (id, slug, display_name) VALUES (:i, :s, 'Other')"),
                {"i": other_tenant, "s": f"test-suppression-{other_tenant.hex[:8]}"},
            )
        try:
            _REPO.record(
                session,
                tenant_id=other_tenant,
                address=_ADDRESS,
                source=SuppressionSource.SPEAKER_PORTAL,
                at=_NOW,
            )
            _record(session, tenant_id, SuppressionSource.SPEAKER_PORTAL, _NOW)
            _REPO.lift(
                session,
                tenant_id=tenant_id,
                address=_ADDRESS,
                allowed_sources=_SPEAKER_ONLY,
                lifted_at=_NOW + timedelta(hours=1),
                lifted_by_user_id=actor_id,
            )
            assert not _REPO.is_active(session, tenant_id=tenant_id, address=_ADDRESS)
            assert _REPO.is_active(session, tenant_id=other_tenant, address=_ADDRESS)
        finally:
            session.rollback()
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM tenant WHERE id = :i"), {"i": other_tenant})
