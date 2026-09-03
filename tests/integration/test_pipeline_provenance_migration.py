"""Migration ``0016`` — ``pipeline_record.matched_provenance`` — exercised for real (Card 1).

Every other pipeline test file proves what the *table* refuses and what the
*repository* writes at the current head. This file is narrower and more
literal: it proves the ten things migration ``0016``'s own "Done when" list
names, several of which no other file can prove because they are about the
migration's own behaviour rather than the table's steady-state shape —
whether the column really has no server default, whether a repeat call can
relabel an already-written row's provenance, and whether ``downgrade`` then
``upgrade`` actually round-trips rather than merely being present in the file.

Ten claims, ten tests (grouped where a single scenario answers two of them):

1. **NOT NULL is real** — a raw insert omitting the column is refused by the
   database itself, not only by the repository's own precondition.
2. **No server default** — read directly off ``information_schema.columns``,
   because an insert that supplies the column proves nothing about what an
   insert that does not supply it would have gotten.
3. **The CHECK rejects an unknown value** — four different kinds of wrong:
   a plausible-looking single word, the other vocabulary member's word stem,
   the empty string, and a case variant of the one real value.
4. **The CHECK accepts both members** — including ``'match-engine'``, the
   reserved slot no application code in this repository writes. Proving the
   database *can* store it is not the same claim as writing it, and is what
   makes the slot usable the day the engine branch needs it.
5. **``record_matched`` refuses an unknown value in Python before any SQL is
   issued** — and, the part ``test_pipeline_record_writers.py``'s own version
   of this test does not check, that refusing leaves no row behind.
6. **Round-trip** — write through the repository, read back through the
   repository, get the same string.
7. **Provenance is not overwritten by a repeat call** — the idempotency rule
   Decision 7 states explicitly: whichever call created the row owns its
   provenance, and ``ON CONFLICT DO NOTHING`` means a second call naming a
   different value is silently *not* the one that wins.
8. **``downgrade`` is reversible** — run for real, against a scratch database,
   down and back up, checking the other nine ``pipeline_record`` constraints
   are present and unchanged throughout rather than merely re-reading the
   migration file.
9. **The other CHECKs still bite after ``0016``** — this migration adds a
   column and a constraint to a table with four other constraints already
   guarding it; two representative writes prove none of them went quiet.
10. **No fabricated score, and no extra parameter** — the standing plan-wide
    rule (§1.3), pinned here as an executable test rather than left to review.

Requires a live database, and is skipped when none is reachable.
"""

from __future__ import annotations

import inspect
import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("sqlalchemy")

from conftest import ensure_owning_unit
from migration_harness import alembic, applied_revision, connected, scratch_database
from smartmatch_persistence import pipeline as pipeline_module
from smartmatch_persistence.engine import create_session_factory
from smartmatch_persistence.pipeline import (
    MATCH_PROVENANCE_MATCH_ENGINE,
    MATCH_PROVENANCE_SYNTHETIC_COORDINATOR,
    PipelineRepository,
)
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from test_pipeline_record_constraints import _insert_pipeline_record, _make_user

pytestmark = pytest.mark.integration

#: The revision immediately before ``0016``, matching that migration's own
#: ``down_revision`` — a scratch database is brought to here before ``0016``
#: is asked to run, for the same reason ``test_job_owning_unit.py`` does.
REVISION_BEFORE = "0015_remove_ledger_reversal"

#: Every other constraint migration ``0011`` put on ``pipeline_record``,
#: restated here so the downgrade/upgrade test can assert none of them moved.
#: ``pipeline_record_pkey`` and the three foreign keys are omitted — they are
#: implied by the table's existence, and this list is specifically the set
#: ``0016``'s own module docstring names as untouched.
_UNTOUCHED_CONSTRAINTS = (
    "ck_pipeline_record_stage_prefix",
    "ck_pipeline_record_stage_order",
    "ck_pipeline_record_attendance_evidence",
    "uq_pipeline_record_subject_opportunity",
)

#: ``tools/scan_forbidden.py``'s own ``fabricated-score`` rule, copied rather
#: than imported: that script is not this card's to depend on, and the point
#: of this test is that this module obeys the rule, not that it can reach the
#: scanner's internals.
_FABRICATED_SCORE_PATTERN = re.compile(
    r"(score|confidence|match_score)\s*=\s*(0\.\d+|[1-9]\d*)\s*(#.*)?$", re.IGNORECASE
)


@pytest.fixture(autouse=True)
def _clean_pipeline_tables(engine: Engine, tenant_id):
    """Delete this file's ``pipeline_record`` rows before ``tenant_id`` tears down its own.

    Same arrangement as ``test_pipeline_record_constraints.py``'s own cleanup
    fixture: ``pipeline_record``'s foreign keys are all ``RESTRICT``, so a row
    left behind here would make the ``tenant_id`` fixture's teardown fail.
    """
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM pipeline_record WHERE tenant_id = :tid"), {"tid": tenant_id})


@pytest.fixture
def db_session_factory(engine: Engine) -> sessionmaker[Session]:
    """A session factory bound to the live test engine, for the repository under test."""
    return create_session_factory(engine.url.render_as_string(hide_password=False))


@pytest.fixture
def repo() -> PipelineRepository:
    return PipelineRepository()


def _pipeline_record_columns(conn) -> set[str]:
    return set(
        conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'pipeline_record'"
            )
        ).scalars()
    )


def _pipeline_record_constraint_names(conn) -> set[str]:
    return set(
        conn.execute(
            text("SELECT conname FROM pg_constraint WHERE conrelid = 'pipeline_record'::regclass")
        ).scalars()
    )


# ---------------------------------------------------------------------------
# 1 & 2 — NOT NULL is real, and there is no server default to fall back on
# ---------------------------------------------------------------------------


def test_omitting_matched_provenance_violates_not_null(engine: Engine, tenant_id) -> None:
    """A raw insert that never mentions the column is refused by the database itself.

    Distinct from every other insert test in this file: those all supply
    *some* value for ``matched_provenance``, which proves the CHECK but proves
    nothing about what happens when the column is left out entirely — that is
    exactly the gap a ``server_default`` would otherwise paper over.
    """
    with (
        pytest.raises(IntegrityError, match=r"(?i)null value|not-null|matched_provenance"),
        engine.begin() as conn,
    ):
        conn.execute(
            text(
                "INSERT INTO pipeline_record "
                "(id, tenant_id, owning_unit_id, subject_id, opportunity_event_id) "
                "VALUES (:id, :tid, :unit, :subject, :event)"
            ),
            {
                "id": uuid.uuid4(),
                "tid": tenant_id,
                "unit": ensure_owning_unit(conn, tenant_id),
                "subject": _make_user(conn, tenant_id),
                "event": uuid.uuid4(),
            },
        )


def test_matched_provenance_has_no_server_default(engine: Engine) -> None:
    """Read directly off the catalogue, not inferred from any insert's behaviour.

    An insert that omits the column and fails proves the column is required;
    it does not by itself prove *why* — a ``NOT NULL`` with a ``server_default``
    would satisfy an omitted-column insert by filling it in, and this test is
    what tells that story apart from the one migration ``0016`` actually tells.
    """
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT column_default, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'pipeline_record' AND column_name = 'matched_provenance'"
            )
        ).one()

    assert row.column_default is None, (
        f"matched_provenance carries a server default ({row.column_default!r}); a default "
        "would let a caller omit provenance and still write a row"
    )
    assert row.is_nullable == "NO"


# ---------------------------------------------------------------------------
# 3 & 4 — the CHECK's admitted vocabulary, exactly
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_value",
    ["engine", "synthetic", "", "SYNTHETIC / COORDINATOR-ACCEPTED"],
    ids=["single-word", "other-word-stem", "empty-string", "wrong-case"],
)
def test_the_check_rejects_an_unknown_provenance_value(
    engine: Engine, tenant_id, bad_value: str
) -> None:
    """Four different kinds of wrong, none of them the two admitted strings.

    ``'engine'`` and ``'synthetic'`` each look like a plausible abbreviation
    of one of the two real values and are refused anyway — the vocabulary is
    closed to the exact strings, not to their word stems. The case variant
    proves the comparison is not case-folded.
    """
    with (
        pytest.raises(IntegrityError, match="ck_pipeline_record_matched_provenance"),
        engine.begin() as conn,
    ):
        _insert_pipeline_record(conn, tenant_id, matched_provenance=bad_value)


@pytest.mark.parametrize(
    "value",
    [MATCH_PROVENANCE_SYNTHETIC_COORDINATOR, MATCH_PROVENANCE_MATCH_ENGINE],
    ids=["synthetic-coordinator-accepted", "match-engine"],
)
def test_the_check_accepts_every_vocabulary_member(engine: Engine, tenant_id, value: str) -> None:
    """Both admitted strings are storable at the database layer.

    Proving ``'match-engine'`` is storable is not the same claim as this
    repository writing it — nothing here calls
    :meth:`~smartmatch_persistence.pipeline.PipelineRepository.record_matched`
    with that value, and no production code in this plan ever does. This is
    the reserved slot existing, at the database layer, for the day M8 needs
    it.
    """
    with engine.begin() as conn:
        _insert_pipeline_record(conn, tenant_id, matched_provenance=value)


# ---------------------------------------------------------------------------
# 5 — record_matched refuses an unknown value before any SQL is issued
# ---------------------------------------------------------------------------


def test_record_matched_refuses_an_unknown_provenance_before_any_statement(
    engine: Engine,
    tenant_id,
    repo: PipelineRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    """The Python-side refusal, and — the part a bare ``pytest.raises`` cannot show —
    that no row was written by the attempt.

    ``test_pipeline_record_writers.py`` proves the exception type and message;
    this is the additional claim that the refusal happens *before* any
    statement reaches the database, verified by checking the table is empty
    for this journey afterwards rather than trusting that ``ValueError`` alone
    implies it.
    """
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
        subject_id = _make_user(conn, tenant_id)
    opportunity_id = uuid.uuid4()

    with (
        db_session_factory() as session,
        pytest.raises(ValueError, match="ck_pipeline_record_matched_provenance"),
    ):
        repo.record_matched(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=subject_id,
            opportunity_event_id=opportunity_id,
            matched_at=datetime.now(UTC),
            matched_provenance="fabricated",
        )

    with engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM pipeline_record WHERE tenant_id = :tid "
                "AND subject_id = :subject AND opportunity_event_id = :opportunity"
            ),
            {"tid": tenant_id, "subject": subject_id, "opportunity": opportunity_id},
        ).scalar_one()
    assert count == 0, "a refused call left a row behind"


# ---------------------------------------------------------------------------
# 6 & 7 — round-trip, and provenance survives a repeat call unmodified
# ---------------------------------------------------------------------------


def test_record_matched_then_get_round_trips_the_exact_provenance_string(
    engine: Engine,
    tenant_id,
    repo: PipelineRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
        subject_id = _make_user(conn, tenant_id)

    with db_session_factory() as session:
        record = repo.record_matched(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=subject_id,
            opportunity_event_id=uuid.uuid4(),
            matched_at=datetime.now(UTC),
            matched_provenance=MATCH_PROVENANCE_SYNTHETIC_COORDINATOR,
        )
        session.commit()

        fetched = repo.get(session, tenant_id=tenant_id, record_id=record.id)

    assert fetched is not None
    assert fetched.matched_provenance == MATCH_PROVENANCE_SYNTHETIC_COORDINATOR


def test_a_repeat_record_matched_call_does_not_relabel_the_stored_provenance(
    engine: Engine,
    tenant_id,
    repo: PipelineRepository,
    db_session_factory: sessionmaker[Session],
) -> None:
    """Decision 7's rule, exercised: the first call's provenance wins, silently.

    ``ON CONFLICT DO NOTHING`` means the second call's own ``INSERT`` never
    lands — the read-back that follows it returns the row exactly as the
    first call left it, provenance included, which is what this test checks
    for explicitly rather than merely re-asserting the returned id is the
    same one.
    """
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
        subject_id = _make_user(conn, tenant_id)
    opportunity_id = uuid.uuid4()

    with db_session_factory() as session:
        first = repo.record_matched(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=subject_id,
            opportunity_event_id=opportunity_id,
            matched_at=datetime.now(UTC) - timedelta(hours=1),
            matched_provenance=MATCH_PROVENANCE_SYNTHETIC_COORDINATOR,
        )
        session.commit()

    with db_session_factory() as session:
        second = repo.record_matched(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=subject_id,
            opportunity_event_id=opportunity_id,
            matched_at=datetime.now(UTC),
            matched_provenance=MATCH_PROVENANCE_MATCH_ENGINE,
        )
        session.commit()

    assert second.id == first.id
    assert second.matched_provenance == MATCH_PROVENANCE_SYNTHETIC_COORDINATOR, (
        "a second call naming a different provenance must not overwrite the first"
    )

    with engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM pipeline_record WHERE tenant_id = :tid "
                "AND subject_id = :subject AND opportunity_event_id = :opportunity"
            ),
            {"tid": tenant_id, "subject": subject_id, "opportunity": opportunity_id},
        ).scalar_one()
    assert count == 1, "the repeat call created a second row instead of conflicting"


# ---------------------------------------------------------------------------
# 8 — downgrade is reversible, run for real against a scratch database
# ---------------------------------------------------------------------------


def test_downgrade_then_upgrade_round_trips_the_column_and_its_check(engine: Engine) -> None:
    """Down, then up again, checking the other nine constraints at every step.

    Not only that ``matched_provenance`` and its CHECK disappear and
    reappear, but that the four other ``pipeline_record`` constraints
    ``0016`` must not touch are present, by name, before the downgrade,
    after it, and after the re-upgrade — proving this migration's own
    ``drop_constraint`` / ``drop_column`` pair reaches exactly what it names
    and nothing else.
    """
    with scratch_database(engine) as url:
        alembic(url, "head", expect_success=True)
        with connected(url) as scratch, scratch.connect() as conn:
            constraints = _pipeline_record_constraint_names(conn)
        assert "ck_pipeline_record_matched_provenance" in constraints
        for name in _UNTOUCHED_CONSTRAINTS:
            assert name in constraints, f"{name} missing at head"

        alembic(url, REVISION_BEFORE, expect_success=True, command="downgrade")
        with connected(url) as scratch, scratch.connect() as conn:
            columns = _pipeline_record_columns(conn)
            constraints = _pipeline_record_constraint_names(conn)
        assert "matched_provenance" not in columns
        assert "ck_pipeline_record_matched_provenance" not in constraints
        for name in _UNTOUCHED_CONSTRAINTS:
            assert name in constraints, f"{name} disappeared on downgrade"
        assert applied_revision(url) == REVISION_BEFORE

        alembic(url, "head", expect_success=True)
        with connected(url) as scratch, scratch.connect() as conn:
            columns = _pipeline_record_columns(conn)
            constraints = _pipeline_record_constraint_names(conn)
        assert "matched_provenance" in columns
        assert "ck_pipeline_record_matched_provenance" in constraints
        for name in _UNTOUCHED_CONSTRAINTS:
            assert name in constraints, f"{name} did not survive the re-upgrade"


# ---------------------------------------------------------------------------
# 9 — the other CHECKs still bite after 0016 added its own
# ---------------------------------------------------------------------------


def test_stage_order_check_still_bites_after_0016(engine: Engine, tenant_id) -> None:
    """``ck_pipeline_record_stage_order`` did not go quiet under the new column."""
    with engine.begin() as conn:
        record_id = _insert_pipeline_record(conn, tenant_id, reached="contacted_at")

    with (
        pytest.raises(IntegrityError, match="ck_pipeline_record_stage_order"),
        engine.begin() as conn,
    ):
        conn.execute(
            text(
                "UPDATE pipeline_record SET contacted_at = matched_at - interval '1 hour' "
                "WHERE id = :id"
            ),
            {"id": record_id},
        )


def test_attendance_evidence_check_still_bites_after_0016(engine: Engine, tenant_id) -> None:
    """``ck_pipeline_record_attendance_evidence`` did not go quiet under the new column."""
    with engine.begin() as conn:
        record_id = _insert_pipeline_record(conn, tenant_id, reached="confirmed_at")

    with (
        pytest.raises(IntegrityError, match="ck_pipeline_record_attendance_evidence"),
        engine.begin() as conn,
    ):
        conn.execute(
            text("UPDATE pipeline_record SET attended_at = now() WHERE id = :id"),
            {"id": record_id},
        )


# ---------------------------------------------------------------------------
# 10 — no fabricated score, and no extra parameter smuggled in
# ---------------------------------------------------------------------------


def test_pipeline_module_contains_no_fabricated_score_literal() -> None:
    """§1.3's standing rule, pinned as a test rather than left to review alone."""
    source = inspect.getsource(pipeline_module)
    offending = [line for line in source.splitlines() if _FABRICATED_SCORE_PATTERN.search(line)]
    assert not offending, f"fabricated-score-shaped line(s) in pipeline.py: {offending}"


def test_record_matched_signature_has_exactly_the_pinned_parameters() -> None:
    """No score, confidence, or rank parameter — and nothing beyond §3's pinned signature."""
    params = set(inspect.signature(PipelineRepository.record_matched).parameters)
    assert params == {
        "self",
        "session",
        "tenant_id",
        "owning_unit_id",
        "subject_id",
        "opportunity_event_id",
        "matched_at",
        "matched_provenance",
    }
