"""``SpeakerChoiceRepository`` against a real PostgreSQL (B26 T6b-3 plan §4.2).

The Speaker's opt-in / opt-out log: append-only, ordered by a dense per-channel
``sequence``, and its ``professional_id`` always the channel's own.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from smartmatch_domain.speaker_channel_consent import SpeakerChoice
from smartmatch_persistence.speaker_channel_choice import SpeakerChoiceRepository
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from tests.integration.conftest import ensure_owning_unit, unique_subject

pytestmark = pytest.mark.integration

_REPO = SpeakerChoiceRepository()
_T0 = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)


@pytest.fixture
def session(session_factory: sessionmaker[Session], tenant_id: uuid.UUID) -> Iterator[Session]:
    with session_factory() as s:
        yield s
        s.rollback()


def _user(conn: Any, tenant_id: uuid.UUID) -> uuid.UUID:
    user_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :tid, :sub, :email)"
        ),
        {
            "id": user_id,
            "tid": tenant_id,
            "sub": unique_subject(f"choice-{user_id.hex[:8]}"),
            "email": f"{user_id.hex[:8]}@example.edu",
        },
    )
    return user_id


@pytest.fixture
def speaker(engine: Engine, tenant_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID, list[uuid.UUID]]:
    """(login, professional_id, [two channel ids]) for one bound Speaker."""
    with engine.begin() as conn:
        login = _user(conn, tenant_id)
        # A professional id is a user_account id (speaker_profile's key).
        professional_id = _user(conn, tenant_id)
        unit_id = ensure_owning_unit(conn, tenant_id)
        conn.execute(
            text(
                "INSERT INTO speaker_profile (tenant_id, professional_id, owning_unit_id, "
                "full_name, account_user_id, account_bound_at) "
                "VALUES (:t, :p, :u, 'Dana Reyes', :a, now())"
            ),
            {"t": tenant_id, "p": professional_id, "u": unit_id, "a": login},
        )
        channels = []
        for n in range(2):
            channel_id = uuid.uuid4()
            conn.execute(
                text(
                    "INSERT INTO contact_channel (id, tenant_id, owning_unit_id, "
                    "professional_id, channel_kind, address, contact_state) "
                    "VALUES (:id, :t, :u, :p, 'email', :a, 'discovered')"
                ),
                {
                    "id": channel_id,
                    "t": tenant_id,
                    "u": unit_id,
                    "p": professional_id,
                    "a": f"choice-{n}-{channel_id.hex[:6]}@synthetic.invalid",
                },
            )
            channels.append(channel_id)
    return login, professional_id, channels


def _append(
    session: Session, tenant_id: uuid.UUID, channel: uuid.UUID, login: uuid.UUID, choice, at
):
    return _REPO.append(
        session,
        tenant_id=tenant_id,
        contact_channel_id=channel,
        choice=choice,
        decided_at=at,
        actor_user_id=login,
    )


def test_sequence_is_dense_per_channel(session: Session, tenant_id: uuid.UUID, speaker) -> None:
    login, _, (a, b) = speaker
    seqs_a = [
        _append(session, tenant_id, a, login, SpeakerChoice.OPT_OUT, _T0).sequence,
        _append(session, tenant_id, a, login, SpeakerChoice.OPT_IN, _T0).sequence,
        _append(session, tenant_id, a, login, SpeakerChoice.OPT_OUT, _T0).sequence,
    ]
    seqs_b = [_append(session, tenant_id, b, login, SpeakerChoice.OPT_IN, _T0).sequence]
    assert seqs_a == [1, 2, 3]
    assert seqs_b == [1]


def test_duplicate_sequence_is_refused(session: Session, tenant_id: uuid.UUID, speaker) -> None:
    login, professional_id, (a, _) = speaker
    _append(session, tenant_id, a, login, SpeakerChoice.OPT_OUT, _T0)
    with pytest.raises(IntegrityError, match="uq_contact_channel_speaker_choice_sequence"):
        session.execute(
            text(
                "INSERT INTO contact_channel_speaker_choice (id, tenant_id, professional_id, "
                "contact_channel_id, sequence, choice, decided_at, actor_user_id) "
                "VALUES (:i, :t, :p, :c, 1, 'opt_in', :at, :u)"
            ),
            {
                "i": uuid.uuid4(),
                "t": tenant_id,
                "p": professional_id,
                "c": a,
                "at": _T0,
                "u": login,
            },
        )


def test_update_is_refused_by_the_trigger(session: Session, tenant_id: uuid.UUID, speaker) -> None:
    login, _, (a, _) = speaker
    row = _append(session, tenant_id, a, login, SpeakerChoice.OPT_OUT, _T0)
    with pytest.raises(DBAPIError):
        session.execute(
            text("UPDATE contact_channel_speaker_choice SET choice = 'opt_in' WHERE id = :i"),
            {"i": row.id},
        )


def test_latest_and_batch_latest(session: Session, tenant_id: uuid.UUID, speaker) -> None:
    login, _, (a, b) = speaker
    assert _REPO.latest_for_channel(session, tenant_id=tenant_id, contact_channel_id=a) is None
    _append(session, tenant_id, a, login, SpeakerChoice.OPT_OUT, _T0)
    # A later sequence with an earlier clock still wins: sequence orders the log.
    _append(session, tenant_id, a, login, SpeakerChoice.OPT_IN, _T0 - timedelta(minutes=5))
    _append(session, tenant_id, b, login, SpeakerChoice.OPT_OUT, _T0)

    latest = _REPO.latest_for_channel(session, tenant_id=tenant_id, contact_channel_id=a)
    assert latest is not None
    assert (latest.choice, latest.sequence) == (SpeakerChoice.OPT_IN, 2)

    unknown = uuid.uuid4()
    batch = _REPO.latest_for_channels(
        session, tenant_id=tenant_id, contact_channel_ids=[a, b, unknown]
    )
    assert {k: v.choice for k, v in batch.items()} == {
        a: SpeakerChoice.OPT_IN,
        b: SpeakerChoice.OPT_OUT,
    }
    assert _REPO.latest_for_channels(session, tenant_id=uuid.uuid4(), contact_channel_ids=[a]) == {}


def test_last_transition_at_for_channels(session: Session, tenant_id: uuid.UUID, speaker) -> None:
    login, _, (a, b) = speaker
    for at in (_T0, _T0 + timedelta(hours=1)):
        session.execute(
            text(
                "INSERT INTO contact_channel_transition (id, tenant_id, contact_channel_id, "
                "from_state, to_state, actor_user_id, occurred_at) "
                "VALUES (:i, :t, :c, NULL, 'discovered', :u, :at)"
            ),
            {"i": uuid.uuid4(), "t": tenant_id, "c": a, "u": login, "at": at},
        )
    got = _REPO.last_transition_at_for_channels(
        session, tenant_id=tenant_id, contact_channel_ids=[a, b]
    )
    assert got == {a: _T0 + timedelta(hours=1)}


def test_professional_matches_the_channel(session: Session, tenant_id: uuid.UUID, speaker) -> None:
    login, professional_id, (a, _) = speaker
    row = _append(session, tenant_id, a, login, SpeakerChoice.OPT_OUT, _T0)
    assert row.professional_id == professional_id
    stored = session.execute(
        text(
            "SELECT s.professional_id = c.professional_id AS same "
            "FROM contact_channel_speaker_choice s JOIN contact_channel c "
            "ON c.tenant_id = s.tenant_id AND c.id = s.contact_channel_id WHERE s.id = :i"
        ),
        {"i": row.id},
    ).scalar_one()
    assert stored is True


def test_an_opt_in_records_what_it_lifted(session: Session, tenant_id: uuid.UUID, speaker) -> None:
    login, _, (a, _) = speaker
    row = _REPO.append(
        session,
        tenant_id=tenant_id,
        contact_channel_id=a,
        choice=SpeakerChoice.OPT_IN,
        decided_at=_T0,
        actor_user_id=login,
        lifted_source="unsubscribe_link",
        lifted_suppressed_at=_T0 - timedelta(days=1),
    )
    assert (row.lifted_source, row.lifted_suppressed_at) == (
        "unsubscribe_link",
        _T0 - timedelta(days=1),
    )
