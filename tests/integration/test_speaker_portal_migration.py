"""Migration ``0039_speaker_portal``: shape, constraints and lifecycle (B26 T6b-1).

``0039`` adds two tables and widens three:

* ``speaker_portal_invitation`` — one row per invitation a Speaker Connector
  sends. It stores the SHA-256 of the token, never the token.
* ``speaker_profile`` gains ``account_user_id`` / ``account_bound_at``: the
  login a Speaker activated, at most one per profile and one profile per login.
* ``suppression_record`` gains ``lifted_at`` / ``lifted_by_user_id`` (schema
  only; no T6b-1 code sets them) and admits the ``speaker_portal`` source.
  Added for T6b-3: only a Speaker-side or link suppression can be lifted.
* ``contact_channel_speaker_choice`` (added for T6b-3): an append-only log of
  a Speaker's opt-in / opt-out per channel.
* ``cba_invitation.response_channel`` admits ``speaker_portal``, which names its
  actor (ruling C2 = b, from T6b-2).

The upgrade and downgrade are run for real against a scratch database seeded at
``0038``. Every constraint is exercised against the suite's database at head:
its forbidden half and its permitted half. The pinned expressions live in
``test_check_constraints.py``, which points back here.

Requires a live database; skipped otherwise. A local skip is not proof — CI is.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("sqlalchemy")

from conftest import _TENANT_SCOPED_TABLES, ensure_owning_unit, unique_subject
from migration_harness import alembic, applied_revision, connected, scratch_database
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

#: Read off the ``revision =`` line of ``0038_speaker_availability.py``.
REVISION_BEFORE = "0038_speaker_availability"

#: The revision under test. Upgrades target it rather than ``head``: B26 T8a's
#: ``0040_booking_cancellation`` chains to it, and a downgrade from ``head``
#: would run 0040's downgrade first.
REVISION = "0039_speaker_portal"

_NOW = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _user(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    user_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :tid, :sub, :email)"
        ),
        {
            "id": user_id,
            "tid": tenant_id,
            "sub": unique_subject(f"portal-{user_id.hex[:8]}"),
            "email": f"{user_id.hex[:8]}@example.edu",
        },
    )
    return user_id


def _profile(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    professional_id = _user(conn, tenant_id)
    conn.execute(
        text(
            "INSERT INTO speaker_profile (tenant_id, professional_id, owning_unit_id, full_name) "
            "VALUES (:tid, :pid, :unit, 'Dana Reyes')"
        ),
        {"tid": tenant_id, "pid": professional_id, "unit": ensure_owning_unit(conn, tenant_id)},
    )
    return professional_id


def _channel(conn, tenant_id: uuid.UUID, professional_id: uuid.UUID) -> uuid.UUID:
    channel_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO contact_channel (id, tenant_id, owning_unit_id, professional_id, "
            " channel_kind, address, contact_state, consent_source, consent_recorded_at) "
            "VALUES (:id, :tid, :unit, :pid, 'email', :address, 'active_candidate', "
            " 'in_person', :now)"
        ),
        {
            "id": channel_id,
            "tid": tenant_id,
            "unit": ensure_owning_unit(conn, tenant_id),
            "pid": professional_id,
            "address": f"{channel_id.hex[:10]}@example.org",
            "now": _NOW,
        },
    )
    return channel_id


def _digest() -> bytes:
    return hashlib.sha256(uuid.uuid4().bytes).digest()


def _invitation(
    conn,
    tenant_id: uuid.UUID,
    professional_id: uuid.UUID,
    channel_id: uuid.UUID,
    issuer_id: uuid.UUID,
    **overrides: object,
) -> uuid.UUID:
    row: dict[str, object] = {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "professional_id": professional_id,
        "contact_channel_id": channel_id,
        "issued_by_user_id": issuer_id,
        "token_hash": _digest(),
        "issued_at": _NOW,
        "expires_at": _NOW + timedelta(days=7),
        "accepted_at": None,
        "revoked_at": None,
        "bound_account_user_id": None,
        "binding_mode": None,
    }
    row.update(overrides)
    columns = ", ".join(row)
    values = ", ".join(f":{name}" for name in row)
    conn.execute(text(f"INSERT INTO speaker_portal_invitation ({columns}) VALUES ({values})"), row)
    return row["id"]  # type: ignore[return-value]


def _suppression(conn, tenant_id: uuid.UUID, **overrides: object) -> None:
    row: dict[str, object] = {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "address": f"{uuid.uuid4().hex[:10]}@example.org",
        "suppressed_at": _NOW,
        "source": "coordinator",
        "lifted_at": None,
        "lifted_by_user_id": None,
    }
    row.update(overrides)
    columns = ", ".join(row)
    values = ", ".join(f":{name}" for name in row)
    conn.execute(text(f"INSERT INTO suppression_record ({columns}) VALUES ({values})"), row)


def _bind(conn, tenant_id, professional_id, account_id, bound_at) -> None:
    conn.execute(
        text(
            "UPDATE speaker_profile SET account_user_id = :acct, account_bound_at = :at "
            "WHERE tenant_id = :tid AND professional_id = :pid"
        ),
        {"acct": account_id, "at": bound_at, "tid": tenant_id, "pid": professional_id},
    )


@pytest.fixture
def speaker(engine: Engine, tenant_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """``(professional_id, channel_id, issuer_id)`` in the test tenant."""
    with engine.begin() as conn:
        professional_id = _profile(conn, tenant_id)
        channel_id = _channel(conn, tenant_id, professional_id)
        issuer_id = _user(conn, tenant_id)
    return professional_id, channel_id, issuer_id


@pytest.fixture
def other_tenant_id(engine: Engine) -> Iterator[uuid.UUID]:
    tid = uuid.uuid4()
    slug = f"test-other-{tid.hex[:12]}"
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :name)"),
            {"id": tid, "slug": slug, "name": slug},
        )
    yield tid
    with engine.begin() as conn:
        for table in _TENANT_SCOPED_TABLES:
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tid})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tid})


def _refused(engine: Engine, statement) -> str:
    with pytest.raises(IntegrityError) as raised, engine.begin() as conn:
        statement(conn)
    return str(raised.value)


def _accepted(engine: Engine, statement) -> None:
    with engine.begin() as conn:
        statement(conn)


# ---------------------------------------------------------------------------
# Upgrade and downgrade, for real
# ---------------------------------------------------------------------------


def _seed_at_0038(scratch) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    tenant_id = uuid.uuid4()
    with scratch.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"scratch-{tenant_id.hex[:12]}"},
        )
        professional_id = _profile(conn, tenant_id)
        channel_id = _channel(conn, tenant_id, professional_id)
        issuer_id = _user(conn, tenant_id)
    return tenant_id, professional_id, channel_id, issuer_id


def _has_table(conn, name: str) -> bool:
    return bool(
        conn.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = :name"
            ),
            {"name": name},
        ).scalar_one()
    )


def _columns(conn, table: str) -> set[str]:
    return set(
        conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :t"
            ),
            {"t": table},
        ).scalars()
    )


def test_downgrade_then_upgrade_round_trips(engine: Engine):
    """Up from a populated 0038, down, up again: the profile survives every step."""
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)
        with connected(url) as scratch:
            tenant_id, professional_id, channel_id, issuer_id = _seed_at_0038(scratch)
            alembic(url, REVISION, expect_success=True)
            assert applied_revision(url) == REVISION
            with scratch.begin() as conn:
                assert _has_table(conn, "speaker_portal_invitation")
                assert {"account_user_id", "account_bound_at"} <= _columns(conn, "speaker_profile")
                assert {"lifted_at", "lifted_by_user_id"} <= _columns(conn, "suppression_record")
                # A live (not accepted) invitation does not block the downgrade.
                _invitation(conn, tenant_id, professional_id, channel_id, issuer_id)

            alembic(url, REVISION_BEFORE, expect_success=True, command="downgrade")
            assert applied_revision(url) == REVISION_BEFORE
            with scratch.connect() as conn:
                assert not _has_table(conn, "speaker_portal_invitation")
                assert not {"account_user_id", "account_bound_at"} & _columns(
                    conn, "speaker_profile"
                )
                assert not {"lifted_at", "lifted_by_user_id"} & _columns(conn, "suppression_record")
                profiles = conn.execute(
                    text("SELECT count(*) FROM speaker_profile WHERE professional_id = :pid"),
                    {"pid": professional_id},
                ).scalar_one()
            assert profiles == 1

            alembic(url, REVISION, expect_success=True)
            assert applied_revision(url) == REVISION


def test_downgrade_refuses_while_an_accepted_invitation_exists(engine: Engine):
    """R7: an accepted invitation means a login exists; the guard raises before any DDL."""
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)
        with connected(url) as scratch:
            tenant_id, professional_id, channel_id, issuer_id = _seed_at_0038(scratch)
            alembic(url, REVISION, expect_success=True)
            with scratch.begin() as conn:
                invitation_id = _invitation(
                    conn,
                    tenant_id,
                    professional_id,
                    channel_id,
                    issuer_id,
                    accepted_at=_NOW + timedelta(hours=1),
                    bound_account_user_id=professional_id,
                    binding_mode="new_login",
                )

            refused = alembic(url, REVISION_BEFORE, expect_success=False, command="downgrade")
            assert applied_revision(url) == REVISION
            assert "1 accepted" in refused.stderr
            with scratch.connect() as conn:
                survivor = conn.execute(
                    text("SELECT count(*) FROM speaker_portal_invitation WHERE id = :id"),
                    {"id": invitation_id},
                ).scalar_one()
            assert survivor == 1


# ---------------------------------------------------------------------------
# speaker_portal_invitation CHECKs
# ---------------------------------------------------------------------------


def test_token_hash_must_be_32_bytes(engine, tenant_id, speaker):
    pid, ch, iss = speaker
    message = _refused(
        engine,
        lambda c: _invitation(c, tenant_id, pid, ch, iss, token_hash=b"\x01" * 31),
    )
    assert "ck_speaker_portal_invitation_token_hash" in message
    _accepted(engine, lambda c: _invitation(c, tenant_id, pid, ch, iss, token_hash=_digest()))


@pytest.mark.parametrize(
    "expires_at",
    [_NOW, _NOW - timedelta(seconds=1), _NOW + timedelta(days=7, seconds=1)],
    ids=["equal", "before", "over-seven-days"],
)
def test_window_refuses_a_bad_expiry(engine, tenant_id, speaker, expires_at):
    pid, ch, iss = speaker
    message = _refused(
        engine, lambda c: _invitation(c, tenant_id, pid, ch, iss, expires_at=expires_at)
    )
    assert "ck_speaker_portal_invitation_window" in message


def test_window_accepts_exactly_seven_days(engine, tenant_id, speaker):
    pid, ch, iss = speaker
    _accepted(
        engine,
        lambda c: _invitation(c, tenant_id, pid, ch, iss, expires_at=_NOW + timedelta(days=7)),
    )


def test_one_outcome_refuses_accepted_and_revoked(engine, tenant_id, speaker):
    pid, ch, iss = speaker
    later = _NOW + timedelta(hours=1)
    message = _refused(
        engine,
        lambda c: _invitation(
            c,
            tenant_id,
            pid,
            ch,
            iss,
            accepted_at=later,
            revoked_at=later,
            bound_account_user_id=pid,
            binding_mode="new_login",
        ),
    )
    assert "ck_speaker_portal_invitation_one_outcome" in message


def test_one_outcome_accepts_revoked_alone(engine, tenant_id, speaker):
    pid, ch, iss = speaker
    _accepted(
        engine,
        lambda c: _invitation(c, tenant_id, pid, ch, iss, revoked_at=_NOW + timedelta(hours=1)),
    )


@pytest.mark.parametrize("column", ["accepted_at", "revoked_at"])
def test_outcome_after_issue_refuses_an_earlier_outcome(engine, tenant_id, speaker, column):
    pid, ch, iss = speaker
    extra: dict[str, object] = {column: _NOW - timedelta(seconds=1)}
    if column == "accepted_at":
        extra |= {"bound_account_user_id": pid, "binding_mode": "new_login"}
    message = _refused(engine, lambda c: _invitation(c, tenant_id, pid, ch, iss, **extra))
    assert "ck_speaker_portal_invitation_outcome_after_issue" in message


def test_outcome_after_issue_accepts_an_outcome_at_issue(engine, tenant_id, speaker):
    pid, ch, iss = speaker
    _accepted(
        engine,
        lambda c: _invitation(
            c,
            tenant_id,
            pid,
            ch,
            iss,
            accepted_at=_NOW,
            bound_account_user_id=pid,
            binding_mode="new_login",
        ),
    )


@pytest.mark.parametrize(
    "extra",
    [
        {"accepted_at": _NOW + timedelta(hours=1)},
        {"accepted_at": _NOW + timedelta(hours=1), "binding_mode": "new_login"},
        {"binding_mode": "new_login"},
    ],
    ids=["accepted-alone", "accepted-no-account", "mode-without-acceptance"],
)
def test_binding_refuses_a_partial_binding(engine, tenant_id, speaker, extra):
    pid, ch, iss = speaker
    message = _refused(engine, lambda c: _invitation(c, tenant_id, pid, ch, iss, **extra))
    assert "ck_speaker_portal_invitation_binding" in message


def test_binding_mode_refuses_an_unknown_mode(engine, tenant_id, speaker):
    pid, ch, iss = speaker
    message = _refused(
        engine,
        lambda c: _invitation(
            c,
            tenant_id,
            pid,
            ch,
            iss,
            accepted_at=_NOW + timedelta(hours=1),
            bound_account_user_id=pid,
            binding_mode="sso",
        ),
    )
    assert "ck_speaker_portal_invitation_binding_mode" in message


def test_binding_mode_accepts_existing_login_on_another_account(engine, tenant_id, speaker):
    pid, ch, iss = speaker
    _accepted(
        engine,
        lambda c: _invitation(
            c,
            tenant_id,
            pid,
            ch,
            iss,
            accepted_at=_NOW + timedelta(hours=1),
            bound_account_user_id=iss,
            binding_mode="existing_login",
        ),
    )


def test_new_login_must_bind_the_contact_account(engine, tenant_id, speaker):
    pid, ch, iss = speaker
    message = _refused(
        engine,
        lambda c: _invitation(
            c,
            tenant_id,
            pid,
            ch,
            iss,
            accepted_at=_NOW + timedelta(hours=1),
            bound_account_user_id=iss,
            binding_mode="new_login",
        ),
    )
    assert "ck_speaker_portal_invitation_new_login_self" in message


def test_issued_at_has_no_default(engine, tenant_id, speaker):
    """R6: a writer that forgets ``issued_at`` fails instead of using the DB clock."""
    pid, ch, iss = speaker

    def insert(conn) -> None:
        conn.execute(
            text(
                "INSERT INTO speaker_portal_invitation (id, tenant_id, professional_id, "
                " contact_channel_id, issued_by_user_id, token_hash, expires_at) "
                "VALUES (:id, :tid, :pid, :ch, :iss, :hash, :exp)"
            ),
            {
                "id": uuid.uuid4(),
                "tid": tenant_id,
                "pid": pid,
                "ch": ch,
                "iss": iss,
                "hash": _digest(),
                "exp": _NOW + timedelta(days=1),
            },
        )

    message = _refused(engine, insert)
    assert "issued_at" in message


def test_token_hash_is_unique(engine, tenant_id, speaker):
    pid, ch, iss = speaker
    digest = _digest()
    _accepted(
        engine,
        lambda c: _invitation(c, tenant_id, pid, ch, iss, token_hash=digest, revoked_at=_NOW),
    )
    message = _refused(engine, lambda c: _invitation(c, tenant_id, pid, ch, iss, token_hash=digest))
    assert "uq_speaker_portal_invitation_token_hash" in message


def test_one_live_invitation_per_profile(engine, tenant_id, speaker):
    pid, ch, iss = speaker
    _accepted(engine, lambda c: _invitation(c, tenant_id, pid, ch, iss))
    message = _refused(engine, lambda c: _invitation(c, tenant_id, pid, ch, iss))
    assert "uq_speaker_portal_invitation_live" in message
    # A revoked one alongside the live one is fine.
    _accepted(engine, lambda c: _invitation(c, tenant_id, pid, ch, iss, revoked_at=_NOW))


# ---------------------------------------------------------------------------
# Tenant isolation: every composite FK refuses a cross-tenant row
# ---------------------------------------------------------------------------


def test_invitation_profile_from_other_tenant_is_refused(
    engine, tenant_id, speaker, other_tenant_id
):
    _, ch, iss = speaker
    with engine.begin() as conn:
        foreign = _profile(conn, other_tenant_id)
    message = _refused(engine, lambda c: _invitation(c, tenant_id, foreign, ch, iss))
    assert "fk_speaker_portal_invitation_profile" in message


def test_invitation_channel_from_other_tenant_is_refused(
    engine, tenant_id, speaker, other_tenant_id
):
    pid, _, iss = speaker
    with engine.begin() as conn:
        foreign_channel = _channel(conn, other_tenant_id, _profile(conn, other_tenant_id))
    message = _refused(engine, lambda c: _invitation(c, tenant_id, pid, foreign_channel, iss))
    assert "fk_speaker_portal_invitation_channel" in message


def test_invitation_issuer_from_other_tenant_is_refused(
    engine, tenant_id, speaker, other_tenant_id
):
    pid, ch, _ = speaker
    with engine.begin() as conn:
        intruder = _user(conn, other_tenant_id)
    message = _refused(engine, lambda c: _invitation(c, tenant_id, pid, ch, intruder))
    assert "fk_speaker_portal_invitation_issued_by" in message


def test_invitation_bound_account_from_other_tenant_is_refused(
    engine, tenant_id, speaker, other_tenant_id
):
    pid, ch, iss = speaker
    with engine.begin() as conn:
        intruder = _user(conn, other_tenant_id)
    message = _refused(
        engine,
        lambda c: _invitation(
            c,
            tenant_id,
            pid,
            ch,
            iss,
            accepted_at=_NOW,
            bound_account_user_id=intruder,
            binding_mode="existing_login",
        ),
    )
    assert "fk_speaker_portal_invitation_bound_account" in message


def test_profile_account_from_other_tenant_is_refused(engine, tenant_id, speaker, other_tenant_id):
    pid, _, _ = speaker
    with engine.begin() as conn:
        intruder = _user(conn, other_tenant_id)
    message = _refused(engine, lambda c: _bind(c, tenant_id, pid, intruder, _NOW))
    assert "fk_speaker_profile_account" in message


def test_lifted_by_from_other_tenant_is_refused(engine, tenant_id, other_tenant_id):
    with engine.begin() as conn:
        intruder = _user(conn, other_tenant_id)
    message = _refused(
        engine,
        lambda c: _suppression(
            c, tenant_id, source="one_click", lifted_at=_NOW, lifted_by_user_id=intruder
        ),
    )
    assert "fk_suppression_record_lifted_by" in message


# ---------------------------------------------------------------------------
# speaker_profile.account_*
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("half", ["account-only", "time-only"])
def test_profile_account_bound_refuses_half_a_binding(engine, tenant_id, speaker, half):
    pid, _, _ = speaker
    account, at = (pid, None) if half == "account-only" else (None, _NOW)
    message = _refused(engine, lambda c: _bind(c, tenant_id, pid, account, at))
    assert "ck_speaker_profile_account_bound" in message


def test_profile_account_bound_accepts_a_full_binding(engine, tenant_id, speaker):
    pid, _, _ = speaker
    _accepted(engine, lambda c: _bind(c, tenant_id, pid, pid, _NOW))


def test_one_profile_per_account(engine, tenant_id, speaker):
    pid, _, _ = speaker
    with engine.begin() as conn:
        second = _profile(conn, tenant_id)
        _bind(conn, tenant_id, pid, pid, _NOW)
    message = _refused(engine, lambda c: _bind(c, tenant_id, second, pid, _NOW))
    assert "uq_speaker_profile_account" in message


# ---------------------------------------------------------------------------
# suppression_record.lifted_* and the widened source
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "extra",
    [
        {"lifted_at": _NOW},
        {"lifted_by_user_id": "actor"},
        {"lifted_at": _NOW - timedelta(seconds=1), "lifted_by_user_id": "actor"},
    ],
    ids=["time-only", "actor-only", "before-suppression"],
)
def test_lifted_refuses_a_bad_lift(engine, tenant_id, extra):
    with engine.begin() as conn:
        actor = _user(conn, tenant_id)
    resolved = {k: (actor if v == "actor" else v) for k, v in extra.items()}
    message = _refused(engine, lambda c: _suppression(c, tenant_id, source="one_click", **resolved))
    assert "ck_suppression_record_lifted" in message


def test_lifted_accepts_a_complete_lift(engine, tenant_id):
    with engine.begin() as conn:
        actor = _user(conn, tenant_id)
    _accepted(
        engine,
        lambda c: _suppression(
            c, tenant_id, source="unsubscribe_link", lifted_at=_NOW, lifted_by_user_id=actor
        ),
    )


def test_source_admits_speaker_portal(engine, tenant_id):
    _accepted(engine, lambda c: _suppression(c, tenant_id, source="speaker_portal"))
    message = _refused(engine, lambda c: _suppression(c, tenant_id, source="speaker"))
    assert "ck_suppression_record_source" in message


@pytest.mark.parametrize("source", ["bounce", "complaint", "coordinator"])
def test_lift_source_refuses_lifting_a_non_speaker_suppression(engine, tenant_id, source):
    """Added for T6b-3: bounce, complaint and coordinator suppressions are never lifted."""
    with engine.begin() as conn:
        actor = _user(conn, tenant_id)
    message = _refused(
        engine,
        lambda c: _suppression(
            c, tenant_id, source=source, lifted_at=_NOW, lifted_by_user_id=actor
        ),
    )
    assert "ck_suppression_record_lift_source" in message


@pytest.mark.parametrize("source", ["speaker_portal", "unsubscribe_link", "one_click"])
def test_lift_source_accepts_lifting_a_speaker_or_link_suppression(engine, tenant_id, source):
    with engine.begin() as conn:
        actor = _user(conn, tenant_id)
    _accepted(
        engine,
        lambda c: _suppression(
            c, tenant_id, source=source, lifted_at=_NOW, lifted_by_user_id=actor
        ),
    )


# ---------------------------------------------------------------------------
# cba_invitation.response_channel = 'speaker_portal' (ruling C2 = b, T6b-2)
# ---------------------------------------------------------------------------


def _cba_invitation(conn, tenant_id, professional_id, actor_id, *, channel, recorded_by):
    """A pending, answered invitation: the smallest row the other CHECKs admit."""
    unit = ensure_owning_unit(conn, tenant_id)
    batch_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO cba_invitation_batch (id, tenant_id, owning_unit_id, idempotency_key, "
            " template_id, event_name, event_date, created_by_user_id) "
            "VALUES (:id, :tid, :unit, :idem, 'cba.speaker_invitation.v1', 'Panel', "
            " '2026-11-10', :actor)"
        ),
        {"id": batch_id, "tid": tenant_id, "unit": unit, "idem": batch_id.hex, "actor": actor_id},
    )
    conn.execute(
        text(
            "INSERT INTO cba_invitation (id, tenant_id, owning_unit_id, batch_id, "
            " professional_id, status, recipient_address, response_status, "
            " response_recorded_at, response_channel, response_recorded_by_user_id) "
            "VALUES (:id, :tid, :unit, :batch, :pid, 'pending', 'dana@example.org', "
            " 'accepted_invitation', :now, :channel, :by)"
        ),
        {
            "id": uuid.uuid4(),
            "tid": tenant_id,
            "unit": unit,
            "batch": batch_id,
            "pid": professional_id,
            "now": _NOW,
            "channel": channel,
            "by": recorded_by,
        },
    )


def test_portal_answer_with_its_actor_is_accepted(engine, tenant_id, speaker):
    pid, _, iss = speaker
    _accepted(
        engine,
        lambda c: _cba_invitation(
            c, tenant_id, pid, iss, channel="speaker_portal", recorded_by=pid
        ),
    )


def test_portal_answer_without_an_actor_is_refused(engine, tenant_id, speaker):
    pid, _, iss = speaker
    message = _refused(
        engine,
        lambda c: _cba_invitation(
            c, tenant_id, pid, iss, channel="speaker_portal", recorded_by=None
        ),
    )
    assert "ck_cba_invitation_response_actor" in message


def test_link_answer_with_an_actor_is_still_refused(engine, tenant_id, speaker):
    pid, _, iss = speaker
    message = _refused(
        engine,
        lambda c: _cba_invitation(c, tenant_id, pid, iss, channel="speaker_link", recorded_by=pid),
    )
    assert "ck_cba_invitation_response_actor" in message


def test_link_answer_without_an_actor_is_still_accepted(engine, tenant_id, speaker):
    pid, _, iss = speaker
    _accepted(
        engine,
        lambda c: _cba_invitation(c, tenant_id, pid, iss, channel="speaker_link", recorded_by=None),
    )


def test_response_channel_refuses_an_unknown_channel(engine, tenant_id, speaker):
    pid, _, iss = speaker
    message = _refused(
        engine,
        lambda c: _cba_invitation(c, tenant_id, pid, iss, channel="portal", recorded_by=None),
    )
    assert "ck_cba_invitation_response_channel" in message


# ---------------------------------------------------------------------------
# contact_channel_speaker_choice (added for T6b-3)
# ---------------------------------------------------------------------------


def _choice(conn, tenant_id, professional_id, channel_id, actor_id, **overrides) -> uuid.UUID:
    row: dict[str, object] = {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "professional_id": professional_id,
        "contact_channel_id": channel_id,
        "sequence": 1,
        "choice": "opt_out",
        "decided_at": _NOW,
        "actor_user_id": actor_id,
        "lifted_source": None,
        "lifted_suppressed_at": None,
    }
    row.update(overrides)
    columns = ", ".join(row)
    values = ", ".join(f":{name}" for name in row)
    conn.execute(
        text(f"INSERT INTO contact_channel_speaker_choice ({columns}) VALUES ({values})"), row
    )
    return row["id"]  # type: ignore[return-value]


def test_choice_refuses_an_unknown_choice(engine, tenant_id, speaker):
    pid, ch, _ = speaker
    message = _refused(engine, lambda c: _choice(c, tenant_id, pid, ch, pid, choice="pause"))
    assert "ck_contact_channel_speaker_choice_choice" in message


@pytest.mark.parametrize("choice", ["opt_in", "opt_out"])
def test_choice_accepts_opt_in_and_opt_out(engine, tenant_id, speaker, choice):
    pid, ch, _ = speaker
    _accepted(engine, lambda c: _choice(c, tenant_id, pid, ch, pid, choice=choice))


def test_choice_sequence_refuses_zero(engine, tenant_id, speaker):
    pid, ch, _ = speaker
    message = _refused(engine, lambda c: _choice(c, tenant_id, pid, ch, pid, sequence=0))
    assert "ck_contact_channel_speaker_choice_sequence" in message


def test_choice_sequence_is_unique_per_channel(engine, tenant_id, speaker):
    pid, ch, _ = speaker
    _accepted(engine, lambda c: _choice(c, tenant_id, pid, ch, pid, sequence=1))
    _accepted(engine, lambda c: _choice(c, tenant_id, pid, ch, pid, sequence=2))
    message = _refused(engine, lambda c: _choice(c, tenant_id, pid, ch, pid, sequence=2))
    assert "uq_contact_channel_speaker_choice_sequence" in message


@pytest.mark.parametrize(
    "extra",
    [
        {"choice": "opt_in", "lifted_source": "one_click"},
        {"choice": "opt_in", "lifted_suppressed_at": _NOW},
        {"choice": "opt_out", "lifted_source": "one_click", "lifted_suppressed_at": _NOW},
    ],
    ids=["source-only", "time-only", "opt-out-lifts"],
)
def test_choice_lift_refuses_a_bad_lift(engine, tenant_id, speaker, extra):
    pid, ch, _ = speaker
    message = _refused(engine, lambda c: _choice(c, tenant_id, pid, ch, pid, **extra))
    assert "ck_contact_channel_speaker_choice_lift" in message


@pytest.mark.parametrize("source", ["speaker_portal", "unsubscribe_link", "one_click"])
def test_choice_lift_accepts_an_opt_in_lifting_a_speaker_suppression(
    engine, tenant_id, speaker, source
):
    pid, ch, _ = speaker
    _accepted(
        engine,
        lambda c: _choice(
            c,
            tenant_id,
            pid,
            ch,
            pid,
            choice="opt_in",
            lifted_source=source,
            lifted_suppressed_at=_NOW,
        ),
    )


@pytest.mark.parametrize("source", ["bounce", "complaint", "coordinator"])
def test_choice_lift_source_refuses_a_non_speaker_source(engine, tenant_id, speaker, source):
    pid, ch, _ = speaker
    message = _refused(
        engine,
        lambda c: _choice(
            c,
            tenant_id,
            pid,
            ch,
            pid,
            choice="opt_in",
            lifted_source=source,
            lifted_suppressed_at=_NOW,
        ),
    )
    assert "ck_contact_channel_speaker_choice_lift_source" in message


def test_choice_decided_at_has_no_default(engine, tenant_id, speaker):
    pid, ch, _ = speaker

    def insert(conn) -> None:
        conn.execute(
            text(
                "INSERT INTO contact_channel_speaker_choice (id, tenant_id, professional_id, "
                " contact_channel_id, sequence, choice, actor_user_id) "
                "VALUES (:id, :tid, :pid, :ch, 1, 'opt_out', :pid)"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "pid": pid, "ch": ch},
        )

    message = _refused(engine, insert)
    assert "decided_at" in message


def test_choice_rows_are_append_only(engine, tenant_id, speaker):
    """The 0023 pattern: a changed choice is a new row, never an UPDATE."""
    pid, ch, _ = speaker
    with engine.begin() as conn:
        choice_id = _choice(conn, tenant_id, pid, ch, pid)
    with pytest.raises(Exception) as raised, engine.begin() as conn:
        conn.execute(
            text("UPDATE contact_channel_speaker_choice SET choice = 'opt_in' WHERE id = :id"),
            {"id": choice_id},
        )
    assert "append-only" in str(raised.value)
    with engine.connect() as conn:
        stored = conn.execute(
            text("SELECT choice FROM contact_channel_speaker_choice WHERE id = :id"),
            {"id": choice_id},
        ).scalar_one()
    assert stored == "opt_out"


def test_choice_channel_from_other_tenant_is_refused(engine, tenant_id, speaker, other_tenant_id):
    pid, _, _ = speaker
    with engine.begin() as conn:
        foreign_channel = _channel(conn, other_tenant_id, _profile(conn, other_tenant_id))
    message = _refused(engine, lambda c: _choice(c, tenant_id, pid, foreign_channel, pid))
    assert "fk_contact_channel_speaker_choice_channel" in message


def test_choice_profile_from_other_tenant_is_refused(engine, tenant_id, speaker, other_tenant_id):
    _, ch, iss = speaker
    with engine.begin() as conn:
        foreign = _profile(conn, other_tenant_id)
    message = _refused(engine, lambda c: _choice(c, tenant_id, foreign, ch, iss))
    assert "fk_contact_channel_speaker_choice_profile" in message


def test_choice_actor_from_other_tenant_is_refused(engine, tenant_id, speaker, other_tenant_id):
    pid, ch, _ = speaker
    with engine.begin() as conn:
        intruder = _user(conn, other_tenant_id)
    message = _refused(engine, lambda c: _choice(c, tenant_id, pid, ch, intruder))
    assert "fk_contact_channel_speaker_choice_actor" in message


@pytest.mark.parametrize("kind", ["choice", "portal-answer"])
def test_downgrade_refuses_while_speaker_made_rows_exist(engine: Engine, kind: str):
    """A Speaker's channel choice or portal answer cannot survive the earlier schema."""
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)
        with connected(url) as scratch:
            tenant_id, professional_id, channel_id, issuer_id = _seed_at_0038(scratch)
            alembic(url, REVISION, expect_success=True)
            with scratch.begin() as conn:
                if kind == "choice":
                    _choice(conn, tenant_id, professional_id, channel_id, professional_id)
                else:
                    _cba_invitation(
                        conn,
                        tenant_id,
                        professional_id,
                        issuer_id,
                        channel="speaker_portal",
                        recorded_by=professional_id,
                    )

            refused = alembic(url, REVISION_BEFORE, expect_success=False, command="downgrade")
            assert applied_revision(url) == REVISION
            assert "cannot downgrade 0039" in refused.stderr


# ---------------------------------------------------------------------------
# Unbind columns (added for T6b-5, its plan §4.4 / ruling Q2)
# ---------------------------------------------------------------------------


def _accepted_kwargs(pid: uuid.UUID) -> dict[str, object]:
    return {
        "accepted_at": _NOW + timedelta(hours=1),
        "bound_account_user_id": pid,
        "binding_mode": "new_login",
    }


@pytest.mark.parametrize("half", ["time-only", "actor-only"])
def test_unbound_pair_refuses_half_an_unbind(engine, tenant_id, speaker, half):
    pid, ch, iss = speaker
    extra = (
        {"unbound_at": _NOW + timedelta(hours=2)}
        if half == "time-only"
        else {"unbound_by_user_id": iss}
    )
    message = _refused(
        engine,
        lambda c: _invitation(c, tenant_id, pid, ch, iss, **_accepted_kwargs(pid), **extra),
    )
    assert "ck_speaker_portal_invitation_unbound_pair" in message


def test_unbound_pair_accepts_a_complete_unbind(engine, tenant_id, speaker):
    pid, ch, iss = speaker
    _accepted(
        engine,
        lambda c: _invitation(
            c,
            tenant_id,
            pid,
            ch,
            iss,
            **_accepted_kwargs(pid),
            unbound_at=_NOW + timedelta(hours=1),
            unbound_by_user_id=iss,
        ),
    )


@pytest.mark.parametrize(
    "extra",
    [
        {"revoked_at": _NOW + timedelta(hours=1)},
        {"accepted": True, "unbound_at": _NOW + timedelta(minutes=30)},
    ],
    ids=["never-accepted", "before-acceptance"],
)
def test_unbound_after_accept_refuses_an_early_unbind(engine, tenant_id, speaker, extra):
    pid, ch, iss = speaker
    fields = dict(extra)
    if fields.pop("accepted", False):
        fields |= _accepted_kwargs(pid)
    fields.setdefault("unbound_at", _NOW + timedelta(hours=2))
    message = _refused(
        engine,
        lambda c: _invitation(c, tenant_id, pid, ch, iss, unbound_by_user_id=iss, **fields),
    )
    assert "ck_speaker_portal_invitation_unbound_after_accept" in message


def test_unbound_by_from_other_tenant_is_refused(engine, tenant_id, speaker, other_tenant_id):
    pid, ch, iss = speaker
    with engine.begin() as conn:
        intruder = _user(conn, other_tenant_id)
    message = _refused(
        engine,
        lambda c: _invitation(
            c,
            tenant_id,
            pid,
            ch,
            iss,
            **_accepted_kwargs(pid),
            unbound_at=_NOW + timedelta(hours=2),
            unbound_by_user_id=intruder,
        ),
    )
    assert "fk_speaker_portal_invitation_unbound_by" in message
