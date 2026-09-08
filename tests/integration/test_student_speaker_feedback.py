"""Student speaker feedback against real PostgreSQL (migration ``0031``).

Two things are asserted here that cannot be asserted anywhere else.

**Eligibility is a foreign key, not a promise.** The route refuses a student who
did not attend, in words; this file proves the *database* refuses one too, by
inserting a rating for a student with no ``attendance_record`` and watching it
fail. A rule that lives only in a route is a rule the next writer of that table
does not have.

**Every CHECK the migration added is exercised in both directions.**
``test_check_constraints.py::BEHAVIOURAL_COVERAGE`` names this file for all five
and names the exact test methods below, so a constraint quietly re-added with an
inverted expression fails here rather than staying green under a name-only
comparison. The permitted half matters as much as the refused half: an inverted
``ck_student_speaker_feedback_rating_range`` reading ``rating < 1 OR rating > 5``
would refuse ``0`` for the wrong reason *and* refuse ``3``, and only
``test_every_admitted_rating_is_storable`` notices.

Everything behavioural goes through
:class:`~smartmatch_persistence.student_speaker_feedback.StudentSpeakerFeedbackRepository`
and is then read back **out of the table with raw SQL**, never through the
writer that put it there and never through an HTTP response. ``get_session``
rolls back unconditionally, so a route that forgets to commit returns a clean
``201`` and stores nothing; a test that believed a status code would pass on
exactly that defect. Asking the writer what it wrote would only prove the writer
self-consistent — these assertions ask PostgreSQL.

Requires a live migrated PostgreSQL and skips when none is reachable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

pytest.importorskip("sqlalchemy")

from conftest import ensure_owning_unit, unique_subject
from smartmatch_domain.events import normalize_title
from smartmatch_domain.student_speaker_feedback import (
    FEEDBACK_EDIT_WINDOW_DAYS,
    MAX_COMMENT_LENGTH,
    MIN_RESPONSES_FOR_AGGREGATE,
    NOT_ENOUGH_RESPONSES,
    EditWindowState,
    Rating,
    aggregate_speaker_feedback,
    aggregate_unit_feedback,
    resolve_edit_window,
)
from smartmatch_persistence.student_speaker_feedback import StudentSpeakerFeedbackRepository
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_feedback(engine: Engine, tenant_id: uuid.UUID):
    """Delete this file's rows before ``tenant_id`` tears its own down.

    Belt to ``conftest._TENANT_SCOPED_TABLES``' braces, and the order matters:
    ``student_speaker_feedback`` holds ``ON DELETE RESTRICT`` references to
    ``org_unit``, ``speaker_profile`` *and* ``attendance_record``, and
    ``attendance_record`` is deliberately absent from that tuple — so this
    fixture owns both deletes, feedback first.
    """
    yield
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM student_speaker_feedback WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )
        conn.execute(
            text("DELETE FROM attendance_record WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )


def _make_account(conn, tenant_id: uuid.UUID, label: str) -> uuid.UUID:
    """One ``user_account``, through :func:`conftest.unique_subject`.

    ``uq_user_account_external_subject`` is **global** — migration ``0007``
    dropped the tenant-scoped constraint beside it — so a fixed literal here
    would collide with a row left behind by any earlier run in any tenant.
    """
    account_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :tid, :sub, :email)"
        ),
        {
            "id": account_id,
            "tid": tenant_id,
            "sub": unique_subject(f"feedback-{label}-{account_id.hex[:8]}"),
            "email": f"{account_id.hex[:8]}@example.edu",
        },
    )
    return account_id


def _make_event(conn, tenant_id: uuid.UUID, unit_id: uuid.UUID, *, on: date) -> uuid.UUID:
    """A ``date_only`` event on a chosen day.

    ``conftest.ensure_event`` exists and is deliberately not used: it pins one
    date, and this file's whole point in one of its classes is that the cutoff is
    measured from the event, so it has to be able to put one in the past.
    """
    event_id = uuid.uuid4()
    title = f"Feedback fixture event {event_id.hex[:8]}"
    conn.execute(
        text(
            "INSERT INTO event (id, tenant_id, host_org_unit_id, title, normalized_title, "
            "on_date, time_zone, time_precision, resolved_date, origin) "
            "VALUES (:id, :tid, :unit, :title, :normalized, :on_date, "
            "'America/Los_Angeles', 'date_only', :on_date, 'coordinator_entry')"
        ),
        {
            "id": event_id,
            "tid": tenant_id,
            "unit": unit_id,
            "title": title,
            "normalized": normalize_title(title),
            "on_date": on,
        },
    )
    return event_id


@pytest.fixture
def unit_id(engine: Engine, tenant_id: uuid.UUID) -> uuid.UUID:
    with engine.begin() as conn:
        return ensure_owning_unit(conn, tenant_id)


@pytest.fixture
def student_id(engine: Engine, tenant_id: uuid.UUID) -> uuid.UUID:
    with engine.begin() as conn:
        return _make_account(conn, tenant_id, "student")


@pytest.fixture
def speaker_id(engine: Engine, tenant_id: uuid.UUID, unit_id: uuid.UUID) -> uuid.UUID:
    """A §13 roster contact.

    ``speaker_profile``'s key is ``(tenant_id, professional_id)`` and
    ``professional_id`` references ``user_account`` — so a speaker needs an
    account row the way an event needs a unit. Referenced **by id only**: nothing
    in this file derives a speaker from a name, which is what keeps it correct
    across ``0030``'s re-key of that column.
    """
    with engine.begin() as conn:
        professional_id = _make_account(conn, tenant_id, "speaker")
        conn.execute(
            text(
                "INSERT INTO speaker_profile (tenant_id, professional_id, owning_unit_id, "
                "full_name) VALUES (:tid, :pid, :unit, 'Fixture Speaker')"
            ),
            {"tid": tenant_id, "pid": professional_id, "unit": unit_id},
        )
        return professional_id


@pytest.fixture
def event_id(engine: Engine, tenant_id: uuid.UUID, unit_id: uuid.UUID) -> uuid.UUID:
    """An event whose feedback window is comfortably open in every test but one."""
    with engine.begin() as conn:
        return _make_event(conn, tenant_id, unit_id, on=date(2026, 9, 14))


@pytest.fixture
def attended(
    engine: Engine,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    student_id: uuid.UUID,
    event_id: uuid.UUID,
) -> None:
    """The evidence a rating rests on: this student was at this event."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO attendance_record (id, tenant_id, owning_unit_id, subject_id, "
                "event_id, method) VALUES (:id, :tid, :unit, :sid, :eid, 'coordinator_entry')"
            ),
            {
                "id": uuid.uuid4(),
                "tid": tenant_id,
                "unit": unit_id,
                "sid": student_id,
                "eid": event_id,
            },
        )


@pytest.fixture
def session(session_factory: sessionmaker[Session]):
    """A session the tests drive the repository through, committed explicitly.

    The repository commits nothing — transaction boundaries belong to its caller
    — so every test here commits for itself and then reads back. That is not
    ceremony: it is the same sequence the route performs, and it is what makes
    "the row is actually there" an assertion about storage rather than about a
    return value.
    """
    with session_factory() as db:
        yield db
        db.rollback()


@pytest.fixture
def feedback() -> StudentSpeakerFeedbackRepository:
    return StudentSpeakerFeedbackRepository()


def _stored(session: Session, *, tenant_id, student_id, event_id, speaker_id):
    """Read the row straight out of the table.

    Deliberately not routed through the repository: a test that asked the writer
    what it wrote would prove the writer self-consistent. This asks PostgreSQL.
    """
    return session.execute(
        text(
            "SELECT status, rating, comment, submitted_at, updated_at "
            "FROM student_speaker_feedback WHERE tenant_id = :tid AND student_id = :sid "
            "AND event_id = :eid AND speaker_professional_id = :pid"
        ),
        {"tid": tenant_id, "sid": student_id, "eid": event_id, "pid": speaker_id},
    ).one_or_none()


def _row_count(session: Session, *, tenant_id, student_id, event_id, speaker_id) -> int:
    return session.execute(
        text(
            "SELECT count(*) FROM student_speaker_feedback WHERE tenant_id = :tid "
            "AND student_id = :sid AND event_id = :eid AND speaker_professional_id = :pid"
        ),
        {"tid": tenant_id, "sid": student_id, "eid": event_id, "pid": speaker_id},
    ).scalar_one()


def _raw_insert(
    session: Session,
    *,
    tenant_id,
    unit_id,
    student_id,
    event_id,
    speaker_id,
    status: str = "submitted",
    rating: int | None = 4,
    comment: str | None = None,
) -> None:
    """Insert a row the repository would never build.

    The only way to reach most of the CHECKs: every path through the repository
    produces well-formed rows on purpose, so a constraint whose forbidden state
    is unreachable through the writer has to be attempted directly.
    """
    session.execute(
        text(
            "INSERT INTO student_speaker_feedback (id, tenant_id, owning_unit_id, event_id, "
            "student_id, speaker_professional_id, status, rating, comment) "
            "VALUES (:id, :tid, :unit, :eid, :sid, :pid, :status, :rating, :comment)"
        ),
        {
            "id": uuid.uuid4(),
            "tid": tenant_id,
            "unit": unit_id,
            "eid": event_id,
            "sid": student_id,
            "pid": speaker_id,
            "status": status,
            "rating": rating,
            "comment": comment,
        },
    )


# ---------------------------------------------------------------------------
# Eligibility, as the schema enforces it
# ---------------------------------------------------------------------------


class TestEligibilityIsAForeignKeyAndNotAPromise:
    """A student who did not attend has nowhere to store a rating of the event."""

    def test_a_rating_without_an_attendance_record_cannot_be_stored_at_all(
        self,
        session: Session,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        student_id: uuid.UUID,
        event_id: uuid.UUID,
        speaker_id: uuid.UUID,
    ) -> None:
        """The ``attended`` fixture is deliberately not requested.

        This is the assertion the route's worded ``403`` cannot make. A refusal
        that lives only in a route protects only the paths that route owns; the
        composite foreign key on ``(tenant_id, student_id, event_id)`` protects
        the table from every writer, including the next one.
        """
        with pytest.raises(IntegrityError):
            _raw_insert(
                session,
                tenant_id=tenant_id,
                unit_id=unit_id,
                student_id=student_id,
                event_id=event_id,
                speaker_id=speaker_id,
            )
        session.rollback()

    @pytest.mark.usefixtures("attended")
    def test_the_same_write_succeeds_once_the_attendance_exists(
        self,
        session: Session,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        student_id: uuid.UUID,
        event_id: uuid.UUID,
        speaker_id: uuid.UUID,
    ) -> None:
        """The permitted half, and what proves the refusal above is about
        attendance rather than about some other constraint failing first.
        """
        _raw_insert(
            session,
            tenant_id=tenant_id,
            unit_id=unit_id,
            student_id=student_id,
            event_id=event_id,
            speaker_id=speaker_id,
        )
        session.commit()
        assert (
            _row_count(
                session,
                tenant_id=tenant_id,
                student_id=student_id,
                event_id=event_id,
                speaker_id=speaker_id,
            )
            == 1
        )

    @pytest.mark.usefixtures("attended")
    def test_the_repository_reports_attendance_and_roster_separately(
        self,
        session: Session,
        feedback: StudentSpeakerFeedbackRepository,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        student_id: uuid.UUID,
        event_id: uuid.UUID,
        speaker_id: uuid.UUID,
    ) -> None:
        """Two facts, two fields, so the route can word two different refusals."""
        facts = feedback.eligibility(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            student_id=student_id,
            event_id=event_id,
            speaker_professional_id=speaker_id,
        )
        assert (facts.event_exists, facts.attended, facts.speaker_on_roster) == (True, True, True)

    @pytest.mark.usefixtures("attended")
    def test_a_speaker_who_is_not_on_the_roster_is_reported_as_such(
        self,
        session: Session,
        feedback: StudentSpeakerFeedbackRepository,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        student_id: uuid.UUID,
        event_id: uuid.UUID,
    ) -> None:
        """An id naming nobody is not an empty result, it is a wrong id.

        This is the nearest evidence available that a speaker had anything to do
        with an event: **nothing in this schema records an appearance**, so
        roster membership is what stands in for it. OQ-CBA-051.
        """
        facts = feedback.eligibility(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            student_id=student_id,
            event_id=event_id,
            speaker_professional_id=uuid.uuid4(),
        )
        assert facts.attended is True
        assert facts.speaker_on_roster is False


# ---------------------------------------------------------------------------
# The CHECK constraints, both directions
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("attended")
class TestTheDatabaseRefusesWhatTheDecisionForbids:
    """All five CHECKs from migration ``0031``, forbidden half and permitted half.

    Named test by test in ``test_check_constraints.py::BEHAVIOURAL_COVERAGE``.
    """

    def test_the_status_vocabulary_is_exactly_two_values(
        self, session, tenant_id, unit_id, student_id, event_id, speaker_id
    ) -> None:
        """``retracted`` is the word a reader would expect to work.

        It is not admitted, and that is why this constraint is tested with a
        plausible synonym rather than with ``'zzz'``: the failure mode is a
        second spelling of an existing state, not a typo.

        ``rating=None`` is load-bearing and was not the first thing tried.
        With a rating present, ``ck_student_speaker_feedback_rating_present``
        fires first — ``(status = 'submitted') = (rating IS NOT NULL)`` is
        ``False = True`` for any unknown status — and the test passed while
        proving nothing about the vocabulary. Every constraint here has to be
        reached with its *siblings satisfied*, or a green assertion is only
        evidence that some constraint refused something.
        """
        with pytest.raises(IntegrityError, match="ck_student_speaker_feedback_status"):
            _raw_insert(
                session,
                tenant_id=tenant_id,
                unit_id=unit_id,
                student_id=student_id,
                event_id=event_id,
                speaker_id=speaker_id,
                status="retracted",
                rating=None,
            )
        session.rollback()

    @pytest.mark.parametrize("value", [0, 6, -1])
    def test_a_rating_outside_one_to_five_is_refused(
        self, session, tenant_id, unit_id, student_id, event_id, speaker_id, value: int
    ) -> None:
        """Both ends of OQ-CBA-003's scale, plus the zero ADR-0011 warns about."""
        with pytest.raises(IntegrityError, match="ck_student_speaker_feedback_rating_range"):
            _raw_insert(
                session,
                tenant_id=tenant_id,
                unit_id=unit_id,
                student_id=student_id,
                event_id=event_id,
                speaker_id=speaker_id,
                rating=value,
            )
        session.rollback()

    @pytest.mark.parametrize("value", [1, 2, 3, 4, 5])
    def test_every_admitted_rating_is_storable(
        self, session, tenant_id, unit_id, student_id, event_id, speaker_id, value: int
    ) -> None:
        """The permitted half, and the one that catches an inverted expression.

        A bound written ``rating < 1 OR rating > 5`` would refuse ``0`` above for
        entirely the wrong reason and would also refuse ``3``, which nothing in
        the forbidden half would notice.
        """
        _raw_insert(
            session,
            tenant_id=tenant_id,
            unit_id=unit_id,
            student_id=student_id,
            event_id=event_id,
            speaker_id=speaker_id,
            rating=value,
        )
        session.commit()
        stored = _stored(
            session,
            tenant_id=tenant_id,
            student_id=student_id,
            event_id=event_id,
            speaker_id=speaker_id,
        )
        assert stored is not None and stored.rating == value

    def test_a_submitted_row_must_carry_a_rating(
        self, session, tenant_id, unit_id, student_id, event_id, speaker_id
    ) -> None:
        """One arm of the equivalence: feedback that says nothing is not feedback."""
        with pytest.raises(IntegrityError, match="ck_student_speaker_feedback_rating_present"):
            _raw_insert(
                session,
                tenant_id=tenant_id,
                unit_id=unit_id,
                student_id=student_id,
                event_id=event_id,
                speaker_id=speaker_id,
                status="submitted",
                rating=None,
            )
        session.rollback()

    def test_a_withdrawn_row_cannot_still_carry_one(
        self, session, tenant_id, unit_id, student_id, event_id, speaker_id
    ) -> None:
        """The other arm, attempted separately.

        Written as an equivalence in the migration precisely so relaxing one half
        cannot go unnoticed, and tested as two cases for the same reason.
        """
        with pytest.raises(IntegrityError, match="ck_student_speaker_feedback_rating_present"):
            _raw_insert(
                session,
                tenant_id=tenant_id,
                unit_id=unit_id,
                student_id=student_id,
                event_id=event_id,
                speaker_id=speaker_id,
                status="withdrawn",
                rating=3,
            )
        session.rollback()

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_a_blank_comment_is_refused_rather_than_stored_as_a_third_state(
        self, session, tenant_id, unit_id, student_id, event_id, speaker_id, blank: str
    ) -> None:
        """``''`` would be a state between "wrote nothing" and "wrote something".

        No surface distinguishes it from NULL and no reader would render it
        differently, so it is refused rather than admitted and then ignored.
        """
        with pytest.raises(IntegrityError, match="ck_student_speaker_feedback_comment_shape"):
            _raw_insert(
                session,
                tenant_id=tenant_id,
                unit_id=unit_id,
                student_id=student_id,
                event_id=event_id,
                speaker_id=speaker_id,
                comment=blank,
            )
        session.rollback()

    def test_a_comment_past_the_length_bound_is_refused(
        self, session, tenant_id, unit_id, student_id, event_id, speaker_id
    ) -> None:
        """The database's bound and the domain's ``MAX_COMMENT_LENGTH`` agree.

        Asserted against the constant rather than against ``2000`` so the two
        cannot drift apart silently.
        """
        with pytest.raises(IntegrityError, match="ck_student_speaker_feedback_comment_shape"):
            _raw_insert(
                session,
                tenant_id=tenant_id,
                unit_id=unit_id,
                student_id=student_id,
                event_id=event_id,
                speaker_id=speaker_id,
                comment="x" * (MAX_COMMENT_LENGTH + 1),
            )
        session.rollback()

    def test_a_rating_may_carry_no_comment_at_all(
        self, session, tenant_id, unit_id, student_id, event_id, speaker_id
    ) -> None:
        """The comment constraint's permitted half. NULL is the ordinary case."""
        _raw_insert(
            session,
            tenant_id=tenant_id,
            unit_id=unit_id,
            student_id=student_id,
            event_id=event_id,
            speaker_id=speaker_id,
            comment=None,
        )
        session.commit()
        stored = _stored(
            session,
            tenant_id=tenant_id,
            student_id=student_id,
            event_id=event_id,
            speaker_id=speaker_id,
        )
        assert stored is not None and stored.comment is None


# ---------------------------------------------------------------------------
# Submitting and editing
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("attended")
class TestSubmittingIsIdempotentAndEditable:
    """One row per student per speaker per event, edited in place."""

    def test_a_submitted_rating_is_in_the_table_not_only_in_the_response(
        self, session, feedback, tenant_id, unit_id, student_id, event_id, speaker_id
    ) -> None:
        """The assertion three tracks have shipped a bug past.

        ``get_session`` rolls back unconditionally, so a route that returns
        ``201`` without committing stores nothing. This reads the table.
        """
        feedback.submit(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            student_id=student_id,
            event_id=event_id,
            speaker_professional_id=speaker_id,
            rating=Rating(value=5, comment="Clear and specific."),
        )
        session.commit()

        stored = _stored(
            session,
            tenant_id=tenant_id,
            student_id=student_id,
            event_id=event_id,
            speaker_id=speaker_id,
        )
        assert stored is not None
        assert (stored.status, stored.rating, stored.comment) == (
            "submitted",
            5,
            "Clear and specific.",
        )

    def test_a_second_submission_edits_the_same_row_rather_than_adding_one(
        self, session, feedback, tenant_id, unit_id, student_id, event_id, speaker_id
    ) -> None:
        """Part 3 of the decision. An edit is a write to the row that exists.

        ``uq_student_speaker_feedback_subject`` is what makes this true rather
        than an implementation detail: a second rating has nowhere else to go.
        """
        for value in (3, 5):
            feedback.submit(
                session,
                tenant_id=tenant_id,
                owning_unit_id=unit_id,
                student_id=student_id,
                event_id=event_id,
                speaker_professional_id=speaker_id,
                rating=Rating(value=value),
            )
            session.commit()

        assert (
            _row_count(
                session,
                tenant_id=tenant_id,
                student_id=student_id,
                event_id=event_id,
                speaker_id=speaker_id,
            )
            == 1
        )
        stored = _stored(
            session,
            tenant_id=tenant_id,
            student_id=student_id,
            event_id=event_id,
            speaker_id=speaker_id,
        )
        assert stored is not None and stored.rating == 5

    def test_an_identical_resubmission_moves_nothing_including_updated_at(
        self, session, feedback, tenant_id, unit_id, student_id, event_id, speaker_id
    ) -> None:
        """``updated_at`` means "when this last moved", so a no-op must not touch it.

        A double-clicked Submit that stamped a fresh timestamp would make the row
        claim an edit that never happened — the defect
        ``event_registration``'s writer avoids by reading before it writes.
        """
        first = feedback.submit(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            student_id=student_id,
            event_id=event_id,
            speaker_professional_id=speaker_id,
            rating=Rating(value=4, comment="Useful."),
        )
        session.commit()
        before = _stored(
            session,
            tenant_id=tenant_id,
            student_id=student_id,
            event_id=event_id,
            speaker_id=speaker_id,
        )

        again = feedback.submit(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            student_id=student_id,
            event_id=event_id,
            speaker_professional_id=speaker_id,
            rating=Rating(value=4, comment="Useful."),
        )
        session.commit()
        after = _stored(
            session,
            tenant_id=tenant_id,
            student_id=student_id,
            event_id=event_id,
            speaker_id=speaker_id,
        )

        assert first.created is True and first.changed is True
        assert again.created is False and again.changed is False
        assert before is not None and after is not None
        assert after.updated_at == before.updated_at

    def test_a_blank_comment_never_reaches_the_database_as_an_empty_string(
        self, session, feedback, tenant_id, unit_id, student_id, event_id, speaker_id
    ) -> None:
        """The domain normalizes it to absent, so the CHECK is never reached.

        Two defences on the same rule, and this is the one that decides what a
        student's blank text box actually stores.
        """
        feedback.submit(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            student_id=student_id,
            event_id=event_id,
            speaker_professional_id=speaker_id,
            rating=Rating(value=4, comment="   "),
        )
        session.commit()
        stored = _stored(
            session,
            tenant_id=tenant_id,
            student_id=student_id,
            event_id=event_id,
            speaker_id=speaker_id,
        )
        assert stored is not None and stored.comment is None


# ---------------------------------------------------------------------------
# Withdrawal
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("attended")
class TestWithdrawalIsATransitionAndNotADelete:
    """The row survives; the opinion does not."""

    def test_a_withdrawn_rating_keeps_its_row_and_its_student(
        self, session, feedback, tenant_id, unit_id, student_id, event_id, speaker_id
    ) -> None:
        """ "Withdrawn" and "never rated" must stay distinguishable.

        And ``student_id`` survives the withdrawal, which is what keeps the row
        able to stop the same student rating this speaker again as though it were
        the first time. This is the concrete reason part 1 of the decision stores
        the column rather than omitting it.
        """
        feedback.submit(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            student_id=student_id,
            event_id=event_id,
            speaker_professional_id=speaker_id,
            rating=Rating(value=2, comment="Hard to follow."),
        )
        session.commit()
        result = feedback.withdraw(
            session,
            tenant_id=tenant_id,
            student_id=student_id,
            event_id=event_id,
            speaker_professional_id=speaker_id,
        )
        session.commit()

        assert result.changed is True
        assert (
            _row_count(
                session,
                tenant_id=tenant_id,
                student_id=student_id,
                event_id=event_id,
                speaker_id=speaker_id,
            )
            == 1
        )
        stored = _stored(
            session,
            tenant_id=tenant_id,
            student_id=student_id,
            event_id=event_id,
            speaker_id=speaker_id,
        )
        assert stored is not None and stored.status == "withdrawn"

    def test_a_withdrawal_takes_the_words_back_too(
        self, session, feedback, tenant_id, unit_id, student_id, event_id, speaker_id
    ) -> None:
        """Both the rating and the comment are cleared.

        The constraint half follows: a withdrawn row that regained its comment is
        refused outright, so a future writer cannot honour half a retraction. The
        free text is the part most likely to name somebody, and leaving it behind
        while removing the number would be the wrong half to keep.
        """
        feedback.submit(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            student_id=student_id,
            event_id=event_id,
            speaker_professional_id=speaker_id,
            rating=Rating(value=2, comment="He talked over the students."),
        )
        session.commit()
        feedback.withdraw(
            session,
            tenant_id=tenant_id,
            student_id=student_id,
            event_id=event_id,
            speaker_professional_id=speaker_id,
        )
        session.commit()

        stored = _stored(
            session,
            tenant_id=tenant_id,
            student_id=student_id,
            event_id=event_id,
            speaker_id=speaker_id,
        )
        assert stored is not None
        assert (stored.rating, stored.comment) == (None, None)

        with pytest.raises(IntegrityError, match="ck_student_speaker_feedback_withdrawn_is_silent"):
            session.execute(
                text(
                    "UPDATE student_speaker_feedback SET comment = 'still here' "
                    "WHERE tenant_id = :tid AND student_id = :sid AND event_id = :eid "
                    "AND speaker_professional_id = :pid"
                ),
                {"tid": tenant_id, "sid": student_id, "eid": event_id, "pid": speaker_id},
            )
            session.commit()
        session.rollback()

    def test_withdrawing_something_never_rated_writes_no_row(
        self, session, feedback, tenant_id, student_id, event_id, speaker_id
    ) -> None:
        """A stray click must not manufacture a pre-withdrawn row.

        One would assert that this student rated this speaker, which they never
        did — and it would occupy the de-duplication key for a rating that does
        not exist.
        """
        result = feedback.withdraw(
            session,
            tenant_id=tenant_id,
            student_id=student_id,
            event_id=event_id,
            speaker_professional_id=speaker_id,
        )
        session.commit()
        assert (result.row, result.created, result.changed) == (None, False, False)
        assert (
            _row_count(
                session,
                tenant_id=tenant_id,
                student_id=student_id,
                event_id=event_id,
                speaker_id=speaker_id,
            )
            == 0
        )

    def test_a_student_may_rate_again_after_withdrawing(
        self, session, feedback, tenant_id, unit_id, student_id, event_id, speaker_id
    ) -> None:
        """A re-submission is an idempotent flip on the same row, not a new one.

        ``submitted_at`` stays put across the round trip, so it keeps meaning
        "when this student first said something about this speaker".
        """
        feedback.submit(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            student_id=student_id,
            event_id=event_id,
            speaker_professional_id=speaker_id,
            rating=Rating(value=2),
        )
        session.commit()
        first = _stored(
            session,
            tenant_id=tenant_id,
            student_id=student_id,
            event_id=event_id,
            speaker_id=speaker_id,
        )

        feedback.withdraw(
            session,
            tenant_id=tenant_id,
            student_id=student_id,
            event_id=event_id,
            speaker_professional_id=speaker_id,
        )
        session.commit()
        again = feedback.submit(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            student_id=student_id,
            event_id=event_id,
            speaker_professional_id=speaker_id,
            rating=Rating(value=5),
        )
        session.commit()

        assert again.created is False
        assert (
            _row_count(
                session,
                tenant_id=tenant_id,
                student_id=student_id,
                event_id=event_id,
                speaker_id=speaker_id,
            )
            == 1
        )
        final = _stored(
            session,
            tenant_id=tenant_id,
            student_id=student_id,
            event_id=event_id,
            speaker_id=speaker_id,
        )
        assert first is not None and final is not None
        assert (final.status, final.rating) == ("submitted", 5)
        assert final.submitted_at == first.submitted_at


# ---------------------------------------------------------------------------
# The cutoff, measured from the stored event
# ---------------------------------------------------------------------------


class TestTheEditWindowIsMeasuredFromTheStoredEvent:
    """Part 3 of the decision, read out of ``event`` rather than out of a constant."""

    def test_a_recent_event_leaves_the_window_open(
        self, session, feedback, tenant_id, event_id
    ) -> None:
        exists, anchor = feedback.event_anchor(session, tenant_id=tenant_id, event_id=event_id)
        assert exists is True and anchor is not None
        window = resolve_edit_window(anchor=anchor, now=anchor + timedelta(days=1))
        assert window.state is EditWindowState.OPEN

    def test_an_event_past_the_cutoff_locks_the_rating(
        self, engine: Engine, session, feedback, tenant_id, unit_id
    ) -> None:
        """The whole reason this file builds events with a chosen date.

        The boundary is asserted in both directions, and the arithmetic is driven
        by :data:`FEEDBACK_EDIT_WINDOW_DAYS` rather than by a literal, so moving
        the constant moves this test with it.
        """
        with engine.begin() as conn:
            old_event = _make_event(conn, tenant_id, unit_id, on=date(2026, 1, 5))

        exists, anchor = feedback.event_anchor(session, tenant_id=tenant_id, event_id=old_event)
        assert exists is True and anchor is not None
        assert anchor == datetime(2026, 1, 6, 0, 0, tzinfo=UTC)

        closes = anchor + timedelta(days=FEEDBACK_EDIT_WINDOW_DAYS)
        assert resolve_edit_window(anchor=anchor, now=closes).state is EditWindowState.CLOSED
        assert (
            resolve_edit_window(anchor=anchor, now=closes - timedelta(seconds=1)).state
            is EditWindowState.OPEN
        )

    def test_an_event_that_does_not_exist_is_told_apart_from_one_with_no_date(
        self, session, feedback, tenant_id
    ) -> None:
        """Both give a ``None`` anchor, and they are different facts.

        The boolean is what keeps a route able to answer ``404`` for the first
        and "no cutoff is knowable" for the second.
        """
        exists, anchor = feedback.event_anchor(session, tenant_id=tenant_id, event_id=uuid.uuid4())
        assert (exists, anchor) == (False, None)


# ---------------------------------------------------------------------------
# The aggregate a Connector reads
# ---------------------------------------------------------------------------


class TestTheAggregateSuppressesSmallSamplesAgainstRealRows:
    """Part 4, end to end from the table rather than from a list literal."""

    def _rate(
        self, engine: Engine, session, feedback, tenant_id, unit_id, event_id, speaker_id, values
    ) -> None:
        """One rating per student, each by a different account.

        Different students, not one student many times — which the unique key
        would refuse anyway, and that refusal is the de-duplication part 1 keeps
        ``student_id`` for.
        """
        for value in values:
            with engine.begin() as conn:
                student = _make_account(conn, tenant_id, "rater")
                conn.execute(
                    text(
                        "INSERT INTO attendance_record (id, tenant_id, owning_unit_id, "
                        "subject_id, event_id, method) "
                        "VALUES (:id, :tid, :unit, :sid, :eid, 'coordinator_entry')"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "tid": tenant_id,
                        "unit": unit_id,
                        "sid": student,
                        "eid": event_id,
                    },
                )
            feedback.submit(
                session,
                tenant_id=tenant_id,
                owning_unit_id=unit_id,
                student_id=student,
                event_id=event_id,
                speaker_professional_id=speaker_id,
                rating=Rating(value=value),
            )
            session.commit()

    def test_two_responses_publish_no_number_at_all(
        self, engine, session, feedback, tenant_id, unit_id, event_id, speaker_id
    ) -> None:
        """Not a mean, and not a count either.

        "Two students rated this speaker" is itself re-identifying in a class, so
        a suppression that published n would have suppressed only the harmless
        half.
        """
        self._rate(engine, session, feedback, tenant_id, unit_id, event_id, speaker_id, [5, 5])
        ratings = feedback.submitted_ratings(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            speaker_professional_id=speaker_id,
        )
        aggregate = aggregate_speaker_feedback(ratings)

        assert len(ratings) == 2
        assert aggregate.suppressed is True
        assert aggregate.mean_rating is None
        assert aggregate.response_count is None
        assert aggregate.display_text == NOT_ENOUGH_RESPONSES

    def test_a_speaker_nobody_rated_reads_as_unknown_rather_than_zero(
        self, session, feedback, tenant_id, unit_id, speaker_id
    ) -> None:
        """ADR-0011 rule 1 verbatim, and the defect Fix #8 reported.

        A speaker nobody rated and a speaker rated 0.0 are different claims, and
        only one of them is true here.
        """
        aggregate = aggregate_speaker_feedback(
            feedback.submitted_ratings(
                session,
                tenant_id=tenant_id,
                owning_unit_id=unit_id,
                speaker_professional_id=speaker_id,
            )
        )
        assert aggregate.mean_rating is None
        assert aggregate.response_count is None
        assert aggregate.display_text == NOT_ENOUGH_RESPONSES

    def test_at_the_threshold_the_numbers_appear(
        self, engine, session, feedback, tenant_id, unit_id, event_id, speaker_id
    ) -> None:
        """The permitted half. A surface that suppressed everything would satisfy
        every assertion above and would be useless.
        """
        self._rate(engine, session, feedback, tenant_id, unit_id, event_id, speaker_id, [3, 4, 5])
        aggregate = aggregate_speaker_feedback(
            feedback.submitted_ratings(
                session,
                tenant_id=tenant_id,
                owning_unit_id=unit_id,
                speaker_professional_id=speaker_id,
            )
        )
        assert aggregate.suppressed is False
        assert aggregate.response_count == MIN_RESPONSES_FOR_AGGREGATE
        assert aggregate.mean_rating == 4.0

    def test_a_withdrawal_drops_the_speaker_back_below_the_threshold(
        self, engine, session, feedback, tenant_id, unit_id, event_id, speaker_id
    ) -> None:
        """The case a stored or cached aggregate gets wrong.

        A Connector who saw 4.0 yesterday sees "not enough responses yet" today,
        and that is correct: the evidence for the number was withdrawn. It works
        because ``submitted_ratings`` filters on ``status`` in the database and
        the aggregate is computed on read, never stored.
        """
        self._rate(engine, session, feedback, tenant_id, unit_id, event_id, speaker_id, [3, 4, 5])
        assert (
            aggregate_speaker_feedback(
                feedback.submitted_ratings(
                    session,
                    tenant_id=tenant_id,
                    owning_unit_id=unit_id,
                    speaker_professional_id=speaker_id,
                )
            ).mean_rating
            == 4.0
        )

        one_rater = session.execute(
            text(
                "SELECT student_id FROM student_speaker_feedback WHERE tenant_id = :tid "
                "AND speaker_professional_id = :pid LIMIT 1"
            ),
            {"tid": tenant_id, "pid": speaker_id},
        ).scalar_one()
        feedback.withdraw(
            session,
            tenant_id=tenant_id,
            student_id=one_rater,
            event_id=event_id,
            speaker_professional_id=speaker_id,
        )
        session.commit()

        after = aggregate_speaker_feedback(
            feedback.submitted_ratings(
                session,
                tenant_id=tenant_id,
                owning_unit_id=unit_id,
                speaker_professional_id=speaker_id,
            )
        )
        assert after.suppressed is True
        assert after.mean_rating is None
        assert after.display_text == NOT_ENOUGH_RESPONSES

    def test_the_aggregate_read_selects_no_student_identifier(
        self, engine, session, feedback, tenant_id, unit_id, event_id, speaker_id
    ) -> None:
        """Part 1, at the layer where it can be proved structurally.

        ``submitted_ratings`` returns bare integers. There is no row type here
        for a ``student_id`` to travel in and no column in the result set for a
        route to forget to strip — a stronger guarantee than a route that
        remembers to leave one out.
        """
        self._rate(engine, session, feedback, tenant_id, unit_id, event_id, speaker_id, [3, 4, 5])
        ratings = feedback.submitted_ratings(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            speaker_professional_id=speaker_id,
        )
        assert all(isinstance(value, int) for value in ratings)
        assert sorted(ratings) == [3, 4, 5]


class TestTheUnitPoolIsReadWithoutAStudentColumn:
    """``submitted_ratings_by_speaker``, against real rows.

    The unit aggregate needs to know which speaker each rating belongs to — that
    is what the residual rule is computed from — so this read selects two columns
    where the per-speaker one selects a single ``rating``. The second column is a
    *speaker* id, never a student's, and that is the property asserted here:
    ``submitted_ratings``'s claim that "there is no ``student_id`` in the result
    set for a route to forget to strip" has to survive the widening.
    """

    def _rate(
        self, engine: Engine, session, feedback, tenant_id, unit_id, event_id, speaker_id, values
    ) -> None:
        """One rating per student, each by a different account."""
        for value in values:
            with engine.begin() as conn:
                student = _make_account(conn, tenant_id, "rater")
                conn.execute(
                    text(
                        "INSERT INTO attendance_record (id, tenant_id, owning_unit_id, "
                        "subject_id, event_id, method) "
                        "VALUES (:id, :tid, :unit, :sid, :eid, 'coordinator_entry')"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "tid": tenant_id,
                        "unit": unit_id,
                        "sid": student,
                        "eid": event_id,
                    },
                )
            feedback.submit(
                session,
                tenant_id=tenant_id,
                owning_unit_id=unit_id,
                student_id=student,
                event_id=event_id,
                speaker_professional_id=speaker_id,
                rating=Rating(value=value),
            )
            session.commit()

    @staticmethod
    def _second_speaker(engine: Engine, tenant_id: uuid.UUID, unit_id: uuid.UUID) -> uuid.UUID:
        """Another §13 roster contact in the same unit.

        The differencing case needs two speakers, and the ``speaker_id`` fixture
        makes one. Built the same way, by id, for the reason that fixture gives.
        """
        with engine.begin() as conn:
            professional_id = _make_account(conn, tenant_id, "speaker")
            conn.execute(
                text(
                    "INSERT INTO speaker_profile (tenant_id, professional_id, owning_unit_id, "
                    "full_name) VALUES (:tid, :pid, :unit, 'Second Fixture Speaker')"
                ),
                {"tid": tenant_id, "pid": professional_id, "unit": unit_id},
            )
            return professional_id

    def test_ratings_by_speaker_selects_no_student_column(
        self, engine, session, feedback, tenant_id, unit_id, event_id, speaker_id
    ) -> None:
        """Part 1, at the layer where it can be proved structurally.

        Keys are speaker ids and values are bare integers. A ``student_id`` has
        nowhere to travel: there is no row type, and the mapping's key is already
        taken by the speaker.
        """
        self._rate(engine, session, feedback, tenant_id, unit_id, event_id, speaker_id, [3, 4, 5])
        by_speaker = feedback.submitted_ratings_by_speaker(
            session, tenant_id=tenant_id, owning_unit_id=unit_id
        )

        assert set(by_speaker) == {speaker_id}
        assert sorted(by_speaker[speaker_id]) == [3, 4, 5]
        assert all(isinstance(value, int) for values in by_speaker.values() for value in values)

    def test_ratings_by_speaker_excludes_withdrawn_rows(
        self, engine, session, feedback, tenant_id, unit_id, event_id, speaker_id
    ) -> None:
        """A withdrawal is not evidence any more, and drops the pool below three.

        Filtered in the database, like ``submitted_ratings``: a withdrawn row's
        rating is ``NULL``, and a caller filtering ``None`` out of a list of
        scores would be doing the database's job badly.
        """
        self._rate(engine, session, feedback, tenant_id, unit_id, event_id, speaker_id, [3, 4, 5])
        one_rater = session.execute(
            text(
                "SELECT student_id FROM student_speaker_feedback WHERE tenant_id = :tid "
                "AND speaker_professional_id = :pid LIMIT 1"
            ),
            {"tid": tenant_id, "pid": speaker_id},
        ).scalar_one()
        feedback.withdraw(
            session,
            tenant_id=tenant_id,
            student_id=one_rater,
            event_id=event_id,
            speaker_professional_id=speaker_id,
        )
        session.commit()

        by_speaker = feedback.submitted_ratings_by_speaker(
            session, tenant_id=tenant_id, owning_unit_id=unit_id
        )
        assert len(by_speaker[speaker_id]) == 2
        assert aggregate_unit_feedback(by_speaker).suppressed is True

    def test_ratings_by_speaker_is_scoped_to_unit_and_tenant(
        self, engine, session, feedback, tenant_id, unit_id, event_id, speaker_id
    ) -> None:
        """Both scopes are in the query, not applied to the result afterwards.

        Asserted by reading a unit that has no ratings and a tenant that is not
        this one: either scope missing would return this unit's rows for both.
        """
        self._rate(engine, session, feedback, tenant_id, unit_id, event_id, speaker_id, [3, 4, 5])

        assert (
            feedback.submitted_ratings_by_speaker(
                session, tenant_id=tenant_id, owning_unit_id=uuid.uuid4()
            )
            == {}
        )
        assert (
            feedback.submitted_ratings_by_speaker(
                session, tenant_id=uuid.uuid4(), owning_unit_id=unit_id
            )
            == {}
        )

    def test_the_pool_is_suppressed_when_a_published_speaker_could_be_subtracted(
        self, engine, session, feedback, tenant_id, unit_id, event_id, speaker_id
    ) -> None:
        """The differencing case against real rows.

        Speaker A has three ratings and is published by the per-speaker route.
        Speaker B has two and is not. The unit pool is five — comfortably over
        the threshold — and is suppressed anyway, because ``5 - 3 = 2`` would
        hand the reader a mean over B's two students.
        """
        speaker_b = self._second_speaker(engine, tenant_id, unit_id)
        self._rate(engine, session, feedback, tenant_id, unit_id, event_id, speaker_id, [5, 5, 5])
        self._rate(engine, session, feedback, tenant_id, unit_id, event_id, speaker_b, [1, 2])

        by_speaker = feedback.submitted_ratings_by_speaker(
            session, tenant_id=tenant_id, owning_unit_id=unit_id
        )
        published = aggregate_speaker_feedback(
            feedback.submitted_ratings(
                session,
                tenant_id=tenant_id,
                owning_unit_id=unit_id,
                speaker_professional_id=speaker_id,
            )
        )
        unit = aggregate_unit_feedback(by_speaker)

        assert sum(len(values) for values in by_speaker.values()) == 5
        assert published.suppressed is False
        assert unit.suppressed is True
        assert unit.response_count is None
        assert unit.mean_rating is None
        assert unit.display_text == NOT_ENOUGH_RESPONSES

    def test_the_pool_publishes_when_no_speaker_is_published(
        self, engine, session, feedback, tenant_id, unit_id, event_id, speaker_id
    ) -> None:
        """Two speakers with two ratings each: nothing to subtract, so publish.

        The reason the endpoint exists — a unit can say something true about
        itself out of samples too small to say anything about a speaker.
        """
        speaker_b = self._second_speaker(engine, tenant_id, unit_id)
        self._rate(engine, session, feedback, tenant_id, unit_id, event_id, speaker_id, [4, 4])
        self._rate(engine, session, feedback, tenant_id, unit_id, event_id, speaker_b, [5, 5])

        unit = aggregate_unit_feedback(
            feedback.submitted_ratings_by_speaker(
                session, tenant_id=tenant_id, owning_unit_id=unit_id
            )
        )
        assert unit.suppressed is False
        assert unit.response_count == 4
        assert unit.mean_rating == 4.5
