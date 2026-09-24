"""The §7 races of B26 T6b-3, two sessions at a time (the T6b-1 activation pattern).

Session A does its whole write and holds its transaction open; a thread runs
session B, which must block on A's lock; A commits; B finishes against what A
committed. Every B session sets ``lock_timeout`` to 10 s, so a deadlock or a
missing lock order shows up as a failure rather than a hang, and no outcome may
be ``DeadlockDetected``.

The Speaker side runs the real service (``smartmatch_api.speaker_channel_consent``).
The Connector side runs the same steps G1/G2 run, in the same order: lock the
channel, read it and the Speaker's latest choice, ask
``connector_transition_conflict`` and ``assert_transition``, apply.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from smartmatch_api import speaker_channel_consent as consent
from smartmatch_api.errors import ApiError
from smartmatch_domain.consent import ConsentViolationError, ContactState, assert_transition
from smartmatch_domain.speaker_channel_consent import connector_transition_conflict
from smartmatch_domain.suppression import SuppressionSource
from smartmatch_persistence.contacts import ContactChannelRepository
from smartmatch_persistence.speaker_channel_choice import SpeakerChoiceRepository
from smartmatch_persistence.speaker_portal import BoundSpeakerProfile, SpeakerPortalRepository
from smartmatch_persistence.suppression import SuppressionRepository
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from tests.integration.conftest import ensure_owning_unit, unique_subject

pytestmark = pytest.mark.integration

_BLOCK_SECONDS = 1.5
_contacts = ContactChannelRepository()
_choices = SpeakerChoiceRepository()
_suppressions = SuppressionRepository()
_portal = SpeakerPortalRepository()


class _World:
    def __init__(self, engine: Engine, factory: sessionmaker[Session], tenant_id: uuid.UUID):
        self.engine = engine
        self.factory = factory
        self.tenant_id = tenant_id
        with engine.begin() as conn:
            unit_id = ensure_owning_unit(conn, tenant_id)
            unit_path = conn.execute(
                text("SELECT CAST(path AS text) FROM org_unit WHERE id = :u"), {"u": unit_id}
            ).scalar_one()
            self.coordinator = self._user(conn)
            self.professional_id = self._user(conn)
            self.login = self._user(conn)
            self.login_email = f"login-{self.login.hex[:8]}@synthetic.invalid"
            conn.execute(
                text("UPDATE user_account SET email = :e WHERE id = :u"),
                {"e": self.login_email, "u": self.login},
            )
            conn.execute(
                text(
                    "INSERT INTO speaker_profile (tenant_id, professional_id, owning_unit_id, "
                    "full_name, account_user_id, account_bound_at) "
                    "VALUES (:t, :p, :u, 'Dana Reyes', :l, now())"
                ),
                {"t": tenant_id, "p": self.professional_id, "u": unit_id, "l": self.login},
            )
            self.unit_id = unit_id
        self.bound = BoundSpeakerProfile(
            professional_id=self.professional_id,
            owning_unit_id=unit_id,
            owning_unit_path=str(unit_path),
        )

    def _user(self, conn: Any) -> uuid.UUID:
        user_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                "VALUES (:id, :t, :s, :e)"
            ),
            {
                "id": user_id,
                "t": self.tenant_id,
                "s": unique_subject(f"race-{user_id.hex[:8]}"),
                "e": f"{user_id.hex[:8]}@example.edu",
            },
        )
        return user_id

    def channel(self, state: str, *, address: str | None = None) -> uuid.UUID:
        channel_id = uuid.uuid4()
        consented = state in {"consented", "active_candidate"}
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO contact_channel (id, tenant_id, owning_unit_id, "
                    "professional_id, channel_kind, address, contact_state, consent_source, "
                    "consent_recorded_at) VALUES (:id, :t, :u, :p, 'email', :a, :s, :src, :at)"
                ),
                {
                    "id": channel_id,
                    "t": self.tenant_id,
                    "u": self.unit_id,
                    "p": self.professional_id,
                    "a": address or f"race-{channel_id.hex[:8]}@synthetic.invalid",
                    "s": state,
                    "src": "in_person" if consented else None,
                    "at": datetime.now(UTC) - timedelta(days=1) if consented else None,
                },
            )
        return channel_id

    def address(self, channel_id: uuid.UUID) -> str:
        with self.engine.connect() as conn:
            return str(
                conn.execute(
                    text("SELECT address FROM contact_channel WHERE id = :c"), {"c": channel_id}
                ).scalar_one()
            )

    def session(self) -> Session:
        session = self.factory()
        session.execute(text("SET LOCAL lock_timeout = '10s'"))
        return session

    # -- the two sides -----------------------------------------------------

    def opt_in(self, session: Session, channel_id: uuid.UUID) -> bool:
        return consent.opt_in(
            session,
            tenant_id=self.tenant_id,
            bound=self.bound,
            actor_user_id=self.login,
            contact_channel_id=channel_id,
        )

    def opt_out(self, session: Session, channel_id: uuid.UUID) -> bool:
        return consent.opt_out(
            session,
            tenant_id=self.tenant_id,
            bound=self.bound,
            actor_user_id=self.login,
            contact_channel_id=channel_id,
        )

    def connector_move(self, session: Session, channel_id: uuid.UUID, to_state: str) -> str:
        """G1/G2's steps: lock, re-read, Speaker wins, suppression, apply."""
        _contacts.lock(session, tenant_id=self.tenant_id, contact_channel_id=channel_id)
        row = _contacts.get(session, tenant_id=self.tenant_id, contact_channel_id=channel_id)
        assert row is not None
        current, requested = ContactState(row.contact_state), ContactState(to_state)
        latest = _choices.latest_for_channel(
            session, tenant_id=self.tenant_id, contact_channel_id=channel_id
        )
        conflict = connector_transition_conflict(
            None if latest is None else latest.choice, current, requested
        )
        if conflict is not None:
            return conflict
        try:
            assert_transition(current, requested, suppressed=row.suppressed)
        except ConsentViolationError:
            return "refused"
        moved = _contacts.apply_transition(
            session,
            tenant_id=self.tenant_id,
            contact_channel_id=channel_id,
            expected_state=current.value,
            to_state=requested.value,
            actor_user_id=self.coordinator,
            occurred_at=datetime.now(UTC),
        )
        return "moved" if moved is not None else "conflict"

    def coordinator_suppress(self, session: Session, channel_id: uuid.UUID) -> str:
        """G3's suppress: channel lock, then the suppression row (W1)."""
        _contacts.lock(session, tenant_id=self.tenant_id, contact_channel_id=channel_id)
        _suppressions.record(
            session,
            tenant_id=self.tenant_id,
            address=self.address(channel_id),
            source=SuppressionSource.COORDINATOR,
            at=datetime.now(UTC),
        )
        return "suppressed"

    # -- reads -------------------------------------------------------------

    def state(self, channel_id: uuid.UUID) -> str:
        with self.factory() as session:
            row = _contacts.get(session, tenant_id=self.tenant_id, contact_channel_id=channel_id)
            assert row is not None
            return row.contact_state

    def suppressed(self, channel_id: uuid.UUID) -> bool:
        with self.factory() as session:
            row = _contacts.get(session, tenant_id=self.tenant_id, contact_channel_id=channel_id)
            assert row is not None
            return row.suppressed

    def choice_log(self, channel_id: uuid.UUID) -> list[tuple[int, str]]:
        with self.engine.connect() as conn:
            return [
                (r.sequence, r.choice)
                for r in conn.execute(
                    text(
                        "SELECT sequence, choice FROM contact_channel_speaker_choice "
                        "WHERE contact_channel_id = :c ORDER BY sequence"
                    ),
                    {"c": channel_id},
                )
            ]


def _outcome(fn: Callable[[Session], Any], world: _World) -> tuple[threading.Thread, list[Any]]:
    """Run ``fn`` in its own session on a thread; record its result or its error code."""
    outcome: list[Any] = []

    def run() -> None:
        session = world.session()
        try:
            result = fn(session)
            session.commit()
            outcome.append(result)
        except ApiError as exc:
            session.rollback()
            outcome.append(exc.code)
        except Exception as exc:  # recorded, then asserted on: DeadlockDetected must not appear
            session.rollback()
            outcome.append(type(exc).__name__ + ": " + str(exc).splitlines()[0])
        finally:
            session.close()

    thread = threading.Thread(target=run)
    thread.start()
    return thread, outcome


def _race(
    world: _World,
    first: Callable[[Session], Any],
    second: Callable[[Session], Any],
) -> tuple[Any, Any]:
    """``first`` holds its locks; ``second`` must wait for them; then both finish."""
    session = world.session()
    try:
        first_result = first(session)
        thread, outcome = _outcome(second, world)
        thread.join(_BLOCK_SECONDS)
        assert thread.is_alive(), "the second writer should wait on the first one's lock"
        session.commit()
    except ApiError as exc:
        session.rollback()
        raise AssertionError(f"first writer refused: {exc.code}") from exc
    finally:
        session.close()
    thread.join(15)
    assert not thread.is_alive(), "the second writer never finished"
    assert outcome, "the second writer recorded nothing"
    assert "Deadlock" not in str(outcome[0])
    return first_result, outcome[0]


@pytest.fixture
def world(engine: Engine, session_factory: sessionmaker[Session], tenant_id: uuid.UUID) -> _World:
    return _World(engine, session_factory, tenant_id)


# ---------------------------------------------------------------------------
# Race 1: opt-out against a Connector escalation
# ---------------------------------------------------------------------------


def test_race_1_opt_out_first_refuses_the_connector(world: _World) -> None:
    channel = world.channel("consented")
    _, second = _race(
        world,
        lambda s: world.opt_out(s, channel),
        lambda s: world.connector_move(s, channel, "active_candidate"),
    )
    assert second == "speaker_contact_channel_speaker_opted_out"
    assert world.state(channel) == "consented"
    assert world.suppressed(channel) is True


def test_race_1_connector_first_then_opt_out_still_suppresses(world: _World) -> None:
    channel = world.channel("consented")
    first, second = _race(
        world,
        lambda s: world.connector_move(s, channel, "active_candidate"),
        lambda s: world.opt_out(s, channel),
    )
    assert (first, second) == ("moved", True)
    assert world.state(channel) == "active_candidate"
    assert world.suppressed(channel) is True


# ---------------------------------------------------------------------------
# Race 2: opt-in against a Connector marking the channel stale
# ---------------------------------------------------------------------------


def test_race_2_opt_in_first_refuses_stale(world: _World) -> None:
    channel = world.channel("consented")
    _, second = _race(
        world,
        lambda s: world.opt_in(s, channel),
        lambda s: world.connector_move(s, channel, "stale"),
    )
    assert second == "speaker_contact_channel_speaker_opted_in"
    assert world.state(channel) == "active_candidate"


def test_race_2_stale_first_makes_the_opt_in_unavailable(world: _World) -> None:
    channel = world.channel("active_candidate")
    _, second = _race(
        world,
        lambda s: world.connector_move(s, channel, "stale"),
        lambda s: world.opt_in(s, channel),
    )
    assert second == "speaker_contact_channel_opt_in_unavailable"
    assert world.choice_log(channel) == []


# ---------------------------------------------------------------------------
# Race 3: two tabs
# ---------------------------------------------------------------------------


def test_race_3_opt_out_and_opt_in_serialize_and_the_last_wins(world: _World) -> None:
    channel = world.channel("active_candidate")
    first, second = _race(
        world,
        lambda s: world.opt_out(s, channel),
        lambda s: world.opt_in(s, channel),
    )
    assert (first, second) == (True, True)
    assert world.choice_log(channel) == [(1, "opt_out"), (2, "opt_in")]
    assert world.suppressed(channel) is False


# ---------------------------------------------------------------------------
# Race 4: opt-in against a coordinator suppression
# ---------------------------------------------------------------------------


def test_race_4_suppress_first_refuses_the_opt_in(world: _World) -> None:
    channel = world.channel("active_candidate")
    _, second = _race(
        world,
        lambda s: world.coordinator_suppress(s, channel),
        lambda s: world.opt_in(s, channel),
    )
    assert second == "speaker_contact_channel_suppression_not_liftable"
    assert world.suppressed(channel) is True


def test_race_4_opt_in_first_then_suppress_reopens(world: _World) -> None:
    channel = world.channel("active_candidate")
    with world.factory() as setup:
        world.opt_out(setup, channel)
        setup.commit()
    first, second = _race(
        world,
        lambda s: world.opt_in(s, channel),
        lambda s: world.coordinator_suppress(s, channel),
    )
    assert (first, second) == (True, "suppressed")
    assert world.suppressed(channel) is True


# ---------------------------------------------------------------------------
# Race 7: opt-out against a T6b-1 invite (the profile lock)
# ---------------------------------------------------------------------------


def test_race_7_invite_holding_the_profile_lock_delays_the_opt_out(world: _World) -> None:
    channel = world.channel("active_candidate")
    _, second = _race(
        world,
        lambda s: _portal.lock_profile(
            s, tenant_id=world.tenant_id, professional_id=world.professional_id
        ),
        lambda s: world.opt_out(s, channel),
    )
    assert second is True
    assert world.suppressed(channel) is True


# ---------------------------------------------------------------------------
# Race 9: two first suppressions for one address
# ---------------------------------------------------------------------------


def test_race_9_two_first_suppressions_merge_on_one_row(world: _World) -> None:
    address = f"race9-{uuid.uuid4().hex[:8]}@synthetic.invalid"

    def record(source: SuppressionSource) -> Callable[[Session], Any]:
        return lambda s: (
            _suppressions.record(
                s, tenant_id=world.tenant_id, address=address, source=source, at=datetime.now(UTC)
            ).write.action.value
        )

    first, second = _race(
        world, record(SuppressionSource.UNSUBSCRIBE_LINK), record(SuppressionSource.BOUNCE)
    )
    assert (first, second) == ("insert", "escalate")
    with world.engine.connect() as conn:
        rows = conn.execute(
            text("SELECT source FROM suppression_record WHERE tenant_id = :t AND address = :a"),
            {"t": world.tenant_id, "a": address},
        ).all()
    assert [r.source for r in rows] == ["bounce"]


# ---------------------------------------------------------------------------
# Race 10: an unsubscribe re-opens the row while the opt-in waits (S2)
# ---------------------------------------------------------------------------


def test_race_10_opt_in_after_a_reopen_lifts_at_or_after_suppressed_at(world: _World) -> None:
    channel = world.channel("active_candidate", address=world.login_email)
    with world.factory() as setup:
        world.opt_out(setup, channel)
        setup.commit()
    with world.factory() as setup:
        world.opt_in(setup, channel)
        setup.commit()
    # Another process whose clock runs 5 minutes ahead re-opens the row.
    ahead = datetime.now(UTC) + timedelta(minutes=5)
    first, second = _race(
        world,
        lambda s: (
            _suppressions.record(
                s,
                tenant_id=world.tenant_id,
                address=world.login_email,
                source=SuppressionSource.UNSUBSCRIBE_LINK,
                at=ahead,
            ).write.action.value
        ),
        lambda s: world.opt_in(s, channel),
    )
    assert (first, second) == ("reopen", True)
    with world.engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT suppressed_at, lifted_at FROM suppression_record "
                "WHERE tenant_id = :t AND address = :a"
            ),
            {"t": world.tenant_id, "a": world.login_email},
        ).one()
    assert row.lifted_at is not None
    assert row.lifted_at >= row.suppressed_at == ahead
