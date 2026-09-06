"""The four parts of OQ-CBA-003, held as executable statements.

The decision (6 September 2026, Danny Tran, program owner of record) has four
parts, and each one has a failure mode that looks like an improvement:

1. **Anonymity is a display rule, not a missing column.** Dropping ``student_id``
   would read as a privacy win and would break retraction, de-duplication and
   abuse tracing at once. Nothing in this file can prove a route does not leak
   the column — that is ``tests/contract/test_student_feedback_api.py``'s job —
   but the domain here never carries a student identifier into an aggregate, and
   :class:`SpeakerFeedbackAggregate` has no field one could be put in.
2. **One dimension, 1-5, required.** The tempting improvement is a second
   criterion. Customer §16 says not to over-design, and the decision names one
   scale.
3. **Editable and withdrawable until a ~7-day post-event cutoff.** The tempting
   improvement is a magic ``7`` inlined at the call site.
   :data:`FEEDBACK_EDIT_WINDOW_DAYS` is asserted to exist and to be the number
   the arithmetic actually uses.
4. **Mean and count, suppressed below n=3.** The tempting improvement is
   returning ``0.0`` or ``count=2`` "so the UI has something to show". That is
   the ADR-0011 defect exactly — unknown rendered as zero — and in a class of
   thirty an average over two students also names them. Half of this file is
   about that one rule.

Pure-domain only: no database, no HTTP, and no clock of its own. Every function
under test takes ``now`` as an argument, because a test that cannot choose the
time cannot test a deadline.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from smartmatch_domain.student_speaker_feedback import (
    FEEDBACK_EDIT_WINDOW_DAYS,
    MAX_COMMENT_LENGTH,
    MAX_RATING,
    MIN_RATING,
    MIN_RESPONSES_FOR_AGGREGATE,
    NOT_ENOUGH_RESPONSES,
    EditWindow,
    EditWindowState,
    FeedbackStatus,
    Rating,
    SpeakerFeedbackAggregate,
    aggregate_speaker_feedback,
    feedback_anchor,
    resolve_edit_window,
)


class TestTheScaleIsTheOneThatWasApproved:
    """OQ-CBA-003 part 2: one required overall 1-5 rating, one optional comment."""

    def test_the_bounds_are_one_and_five(self) -> None:
        """Named constants, so the range is one edit rather than four literals."""
        assert (MIN_RATING, MAX_RATING) == (1, 5)

    @pytest.mark.parametrize("value", [1, 2, 3, 4, 5])
    def test_every_value_on_the_scale_is_accepted(self, value: int) -> None:
        """The permitted half. An inverted bound would refuse 3, not only 0."""
        assert Rating(value=value).value == value

    @pytest.mark.parametrize("value", [0, 6, -1, 100])
    def test_a_value_off_the_scale_is_refused(self, value: int) -> None:
        """Both ends, plus the two ways a caller usually gets it wrong.

        ``0`` is the interesting one: it is what an uninitialised slider sends
        and what ADR-0011 calls a fabricated zero. It is not a rating.
        """
        with pytest.raises(ValueError, match="1 and 5"):
            Rating(value=value)

    def test_a_rating_may_carry_no_comment(self) -> None:
        """The comment is optional in the honest sense: absent means unwritten."""
        assert Rating(value=4).comment is None

    @pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
    def test_a_blank_comment_is_not_a_comment(self, blank: str) -> None:
        """``''`` would be a third state — "opened the box, wrote nothing" — that
        no surface distinguishes from absent. It normalizes to absent rather than
        being stored as a value of its own.
        """
        assert Rating(value=4, comment=blank).comment is None

    def test_a_comment_is_stripped_but_not_otherwise_rewritten(self) -> None:
        assert Rating(value=4, comment="  she was great  ").comment == "she was great"

    def test_a_comment_past_the_bound_is_refused(self) -> None:
        """The bound is a named constant and matches the database's CHECK."""
        assert MAX_COMMENT_LENGTH == 2000
        with pytest.raises(ValueError, match="2000"):
            Rating(value=4, comment="x" * (MAX_COMMENT_LENGTH + 1))

    def test_there_is_no_second_dimension_to_score(self) -> None:
        """Customer §16: do not over-design. One scale was approved; one exists.

        Asserted structurally rather than in prose, so a later card that adds
        ``clarity``/``relevance``/``delivery`` fields has to delete this test and
        say why, instead of quietly widening the form.
        """
        assert set(Rating.__slots__) == {"value", "comment"}


class TestTheStatusVocabulary:
    """A withdrawal is a transition, never a DELETE (OQ-CBA-018's shape)."""

    def test_there_are_exactly_two_states(self) -> None:
        assert {s.value for s in FeedbackStatus} == {"submitted", "withdrawn"}

    def test_never_rated_is_not_one_of_them(self) -> None:
        """"Never rated" is the absence of a row, not a status.

        Spelling it as a third value would make it storable, and a stored
        "never rated" is a row asserting something nobody did.
        """
        assert "never_rated" not in {s.value for s in FeedbackStatus}


class TestTheAnchorTheDeadlineIsMeasuredFrom:
    """ADR-0010's temporal triple, and the state it has that a deadline cannot use."""

    def test_an_exact_event_anchors_on_when_it_ended(self) -> None:
        starts = datetime(2026, 9, 1, 18, 0, tzinfo=UTC)
        ends = datetime(2026, 9, 1, 20, 0, tzinfo=UTC)
        anchor = feedback_anchor(
            time_precision="exact", starts_at=starts, ends_at=ends, on_date=None
        )
        assert anchor == ends

    def test_an_exact_event_with_no_stated_end_anchors_on_its_start(self) -> None:
        """``ends_at IS NULL`` means the source stated no end (migration 0022), not
        that the event had none. The start is the latest moment actually known,
        so it is what the window is measured from.
        """
        starts = datetime(2026, 9, 1, 18, 0, tzinfo=UTC)
        anchor = feedback_anchor(
            time_precision="exact", starts_at=starts, ends_at=None, on_date=None
        )
        assert anchor == starts

    def test_a_date_only_event_anchors_on_the_end_of_that_day(self) -> None:
        """The window is seven days; resolving a date to its own end costs at most
        one of them, and picking the *end* is the choice that never closes the
        window early on a student.
        """
        anchor = feedback_anchor(
            time_precision="date_only", starts_at=None, ends_at=None, on_date=date(2026, 9, 1)
        )
        assert anchor == datetime(2026, 9, 2, 0, 0, tzinfo=UTC)

    def test_an_unresolved_event_has_no_anchor_at_all(self) -> None:
        """ADR-0010: an unresolved date is a real state, not a missing value.

        There is no moment to count seven days from, and inventing one — today,
        the row's creation, the epoch — would be a deadline nobody set.
        """
        anchor = feedback_anchor(
            time_precision="unresolved", starts_at=None, ends_at=None, on_date=None
        )
        assert anchor is None


class TestTheEditWindow:
    """OQ-CBA-003 part 3: editable and withdrawable until a ~7-day cutoff."""

    def test_the_cutoff_is_a_named_constant_of_seven_days(self) -> None:
        assert FEEDBACK_EDIT_WINDOW_DAYS == 7

    def test_the_window_closes_exactly_that_many_days_after_the_anchor(self) -> None:
        """Derived from the constant, not from a literal 7, so moving the constant
        moves the arithmetic rather than leaving the two disagreeing.
        """
        anchor = datetime(2026, 9, 1, 20, 0, tzinfo=UTC)
        window = resolve_edit_window(anchor=anchor, now=anchor)
        assert window.closes_at == anchor + timedelta(days=FEEDBACK_EDIT_WINDOW_DAYS)

    def test_a_rating_is_editable_the_day_after_the_event(self) -> None:
        anchor = datetime(2026, 9, 1, 20, 0, tzinfo=UTC)
        window = resolve_edit_window(anchor=anchor, now=anchor + timedelta(days=1))
        assert window.state is EditWindowState.OPEN
        assert window.permits_change is True

    def test_a_rating_is_locked_once_the_window_has_passed(self) -> None:
        anchor = datetime(2026, 9, 1, 20, 0, tzinfo=UTC)
        window = resolve_edit_window(anchor=anchor, now=anchor + timedelta(days=8))
        assert window.state is EditWindowState.CLOSED
        assert window.permits_change is False

    def test_the_boundary_is_lower_inclusive_like_every_other_band_here(self) -> None:
        """One instant before the cutoff is open; the cutoff itself is closed.

        The convention is ADR-0016's for proximity bands — lower-inclusive,
        upper-exclusive — chosen so the two do not disagree about what "at the
        boundary" means.
        """
        anchor = datetime(2026, 9, 1, 20, 0, tzinfo=UTC)
        closes = anchor + timedelta(days=FEEDBACK_EDIT_WINDOW_DAYS)
        just_inside = resolve_edit_window(anchor=anchor, now=closes - timedelta(microseconds=1))
        assert just_inside.state is EditWindowState.OPEN
        assert resolve_edit_window(anchor=anchor, now=closes).state is EditWindowState.CLOSED

    def test_an_event_with_no_anchor_has_an_unknown_close_and_stays_changeable(self) -> None:
        """The honest answer for an unresolved event date, in both halves.

        ``closes_at`` is ``None`` — no date is asserted, because none is known.
        And ``permits_change`` is ``True``, because locking would assert that a
        deadline nobody can name has passed. The asymmetry is deliberate: an
        unknown cutoff that stays open leaves a student able to correct or
        retract their own words, and an unknown cutoff that locks takes that
        away on the strength of a date the system admits it does not have.
        """
        window = resolve_edit_window(anchor=None, now=datetime(2030, 1, 1, tzinfo=UTC))
        assert window.state is EditWindowState.UNKNOWN
        assert window.closes_at is None
        assert window.permits_change is True

    def test_an_unknown_window_is_never_reported_as_an_open_one(self) -> None:
        """Both permit a change, and they are still different facts.

        Collapsing them would let a surface say "you have until the 8th" about an
        event whose date nobody knows.
        """
        anchor = datetime(2026, 9, 1, 20, 0, tzinfo=UTC)
        window = resolve_edit_window(anchor=anchor, now=anchor)
        assert window.state is not EditWindowState.UNKNOWN


class TestSuppressionBelowThreeResponses:
    """OQ-CBA-003 part 4, and the rule this whole file exists to protect.

    ADR-0011 rule 1: a value with no evidence is unknown and renders as unknown,
    never as ``0``. Here it is stronger than that — below the threshold the
    aggregate withholds the *count* as well as the mean, because "2 students
    rated this speaker" is itself re-identifying in a class.
    """

    def test_the_threshold_is_a_named_constant_of_three(self) -> None:
        assert MIN_RESPONSES_FOR_AGGREGATE == 3

    @pytest.mark.parametrize("ratings", [[], [5], [5, 5]])
    def test_below_the_threshold_no_number_is_returned_at_all(self, ratings: list[int]) -> None:
        """Not a mean, and not a count either. Both are withheld."""
        aggregate = aggregate_speaker_feedback(ratings)
        assert aggregate.suppressed is True
        assert aggregate.mean_rating is None
        assert aggregate.response_count is None

    def test_no_responses_is_suppressed_rather_than_reported_as_zero(self) -> None:
        """The ADR-0011 defect verbatim: absence rendered as a measurement.

        A speaker nobody rated and a speaker rated 0.0 are different claims, and
        only one of them is true of a speaker nobody rated.
        """
        aggregate = aggregate_speaker_feedback([])
        assert aggregate.mean_rating is None
        assert aggregate.response_count is None

    def test_the_suppressed_reading_says_so_in_words(self) -> None:
        assert aggregate_speaker_feedback([5, 5]).display_text == NOT_ENOUGH_RESPONSES
        assert NOT_ENOUGH_RESPONSES == "not enough responses yet"

    def test_at_the_threshold_the_mean_and_the_count_are_both_reported(self) -> None:
        """The permitted half. Without it, an aggregate that suppressed
        *everything* would satisfy every test above.
        """
        aggregate = aggregate_speaker_feedback([3, 4, 5])
        assert aggregate.suppressed is False
        assert aggregate.response_count == 3
        assert aggregate.mean_rating == 4.0

    def test_the_mean_is_rounded_rather_than_carried_to_full_precision(self) -> None:
        """Two decimals. An average printed as 3.6666666666666665 asserts a
        precision that thirty opinions on a five-point scale do not support.
        """
        assert aggregate_speaker_feedback([3, 4, 4]).mean_rating == 3.67

    def test_an_aggregate_has_nowhere_to_put_a_student_identifier(self) -> None:
        """Part 1, as far as the domain can hold it.

        ``student_id`` is stored in the table and never travels into an
        aggregate. The type has no field one could be assigned to, which is a
        stronger guarantee than remembering not to.
        """
        assert set(SpeakerFeedbackAggregate.__slots__) == {
            "response_count",
            "mean_rating",
            "suppressed",
        }

    def test_an_aggregate_cannot_be_constructed_claiming_a_suppressed_number(self) -> None:
        """The type refuses the incoherent state rather than trusting its callers.

        A suppressed aggregate carrying a mean is precisely the leak this rule
        exists to prevent, and it should be unrepresentable rather than merely
        unproduced.
        """
        with pytest.raises(ValueError, match="suppressed"):
            SpeakerFeedbackAggregate(response_count=2, mean_rating=4.5, suppressed=True)

    def test_an_unsuppressed_aggregate_must_actually_carry_its_numbers(self) -> None:
        with pytest.raises(ValueError, match="suppressed"):
            SpeakerFeedbackAggregate(response_count=None, mean_rating=None, suppressed=False)

    def test_this_function_counts_what_it_is_given_and_filters_nothing(self) -> None:
        """Withdrawn ratings are the caller's to exclude, not this function's.

        Stated as a test because the alternative — passing rows and filtering
        here — is where a withdrawn rating gets counted by a caller who forgot.
        The repository's query filters on ``status = 'submitted'``; see
        ``tests/integration/test_student_speaker_feedback.py``.
        """
        assert aggregate_speaker_feedback([4, 4, 4]).response_count == 3


class TestTheSuppressionRuleAndTheEditRuleDoNotInteract:
    """A withdrawal can push a speaker back below the threshold, and must."""

    def test_a_withdrawal_that_drops_the_count_to_two_re_suppresses_the_aggregate(self) -> None:
        """Three ratings show a mean; one is retracted and the mean disappears.

        This is the case a cached or stored aggregate gets wrong, and the reason
        the aggregate is computed on read and stored nowhere. A Connector who saw
        4.0 yesterday sees "not enough responses yet" today, which is correct:
        the evidence for that number was withdrawn.
        """
        before = aggregate_speaker_feedback([3, 4, 5])
        after = aggregate_speaker_feedback([3, 4])
        assert before.mean_rating == 4.0
        assert after.mean_rating is None
        assert after.display_text == NOT_ENOUGH_RESPONSES


class TestEditWindowIsAValueNotAnOpinion:
    """Frozen, so a caller cannot widen its own deadline."""

    def test_the_window_cannot_be_mutated_after_it_is_resolved(self) -> None:
        window = EditWindow(
            state=EditWindowState.CLOSED,
            closes_at=datetime(2026, 9, 8, 20, 0, tzinfo=UTC),
        )
        with pytest.raises((AttributeError, TypeError)):
            window.state = EditWindowState.OPEN  # type: ignore[misc]
