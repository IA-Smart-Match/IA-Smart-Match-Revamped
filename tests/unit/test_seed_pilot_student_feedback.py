"""The student feedback seeder must sign in, not insert, and must not carry a password.

``student_speaker_feedback`` is the one empty table on a generated pilot tenant
that cannot be filled by writing rows. ``routers/student_speaker_feedback.py``
takes ``student_id`` from the verified principal and from nowhere else — the
structural guarantee against MM-A01's caller-selected identity — so a seeder
that INSERTed would exercise none of the attendance check, the roster check or
the seven-day edit window, and would leave the thing the surface exists for
undemonstrated.

Two properties are pinned here and neither needs a database:

* the credential is read from the environment, never defaulted and never
  written down in this repository; and
* the edit window is the domain's, imported rather than guessed, so an event
  the API would refuse with ``409`` is not offered to the poster.
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# `tools/` on the path rather than the repository root: these modules are run by
# compose as bare siblings and importing them as `tools.…` would exercise a
# module shape nothing runs.
sys.path.insert(0, str(REPO_ROOT / "tools"))

from seed_pilot_student_feedback import (  # noqa: E402
    COHORT_RESPONSE_SHAPE,
    EMAIL_VARIABLE,
    MAX_EVENTS,
    MAX_SPEAKERS_PER_EVENT,
    PASSWORD_VARIABLE,
    RATING_CYCLE,
    FeedbackReport,
    SeedFeedbackError,
    _window_state,
    login,
    parse_args,
)
from smartmatch_domain.student_speaker_feedback import (  # noqa: E402
    MIN_RESPONSES_FOR_AGGREGATE,
    EditWindowState,
)

# -- the credential ---------------------------------------------------------


def test_the_password_variables_are_the_ones_the_login_seed_uses() -> None:
    """One place a pilot credential is written down, and this file is not it."""
    from seed_pilot_logins import ROLE_CREDENTIALS

    student = next(entry for entry in ROLE_CREDENTIALS if entry.role == "student")
    assert student.email_var == EMAIL_VARIABLE
    assert student.password_var == PASSWORD_VARIABLE


def test_no_password_literal_lives_in_this_tool() -> None:
    """A default password in a file is a credential in a file.

    Read as text rather than asserted about behaviour, because the failure this
    guards against is somebody adding a convenient fallback that every test
    would otherwise still pass over.
    """
    source = (REPO_ROOT / "tools" / "seed_pilot_student_feedback.py").read_text(encoding="utf-8")
    for forbidden in ('password="', "password='", 'PASSWORD = "', "Testing123"):
        assert forbidden not in source, (
            f"tools/seed_pilot_student_feedback.py contains {forbidden!r}; the credential "
            f"must come from ${PASSWORD_VARIABLE} and from nowhere else"
        )


def test_an_unset_credential_is_refused_and_names_the_variable() -> None:
    """A refusal an operator can act on, rather than a 401 from the API."""
    with pytest.raises(SeedFeedbackError) as raised:
        login(api_base="http://127.0.0.1:1", environ={})
    message = str(raised.value)
    assert EMAIL_VARIABLE in message
    assert PASSWORD_VARIABLE in message


def test_a_half_set_credential_names_only_the_missing_half() -> None:
    with pytest.raises(SeedFeedbackError) as raised:
        login(api_base="http://127.0.0.1:1", environ={EMAIL_VARIABLE: "student@example.invalid"})
    message = str(raised.value)
    assert PASSWORD_VARIABLE in message
    assert "student@example.invalid" not in message, "a refusal must not echo the credential"


def test_login_never_reaches_the_network_without_a_credential() -> None:
    """The refusal is before the request, so an unset variable cannot become a 401.

    ``http://127.0.0.1:1`` is a port nothing listens on: if this test ever fails
    with a connection error rather than a ``SeedFeedbackError``, the check moved
    after the request.
    """
    with pytest.raises(SeedFeedbackError):
        login(api_base="http://127.0.0.1:1", environ={PASSWORD_VARIABLE: "x"})


# -- the window -------------------------------------------------------------

_NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def test_a_date_only_event_inside_seven_days_is_open() -> None:
    state = _window_state(
        time_precision="date_only",
        starts_at=None,
        ends_at=None,
        on_date=_NOW.date() - timedelta(days=2),
        now=_NOW,
    )
    assert state is EditWindowState.OPEN


def test_a_date_only_event_older_than_the_window_is_closed_not_offered() -> None:
    """Most of a generated calendar is closed; that is the calendar being honest."""
    state = _window_state(
        time_precision="date_only",
        starts_at=None,
        ends_at=None,
        on_date=date(2026, 3, 29),
        now=_NOW,
    )
    assert state is EditWindowState.CLOSED


def test_an_unresolved_event_has_no_anchor_and_is_not_open() -> None:
    """OQ-CBA-052 is open on what a rating of an undated event means.

    ``resolve_edit_window`` permits a change because there is nothing to have
    closed, and the seeder deliberately does not use that: a tool writing rows
    into an open question would be answering it in code. The assertion here is
    that the state is distinguishable from ``OPEN`` so the seeder's filter can
    tell them apart.
    """
    state = _window_state(
        time_precision="unresolved", starts_at=None, ends_at=None, on_date=None, now=_NOW
    )
    assert state is not EditWindowState.OPEN


# -- the plan ---------------------------------------------------------------


def test_ratings_are_spread_rather_than_uniform() -> None:
    """Five identical fours demonstrate a form, not an opinion."""
    assert len(set(RATING_CYCLE)) > 1


def test_the_bounds_are_small_enough_to_be_deliberate() -> None:
    """A large cap would silently mean "all of them" and read as a missed target."""
    assert 1 <= MAX_EVENTS <= 5
    assert 1 <= MAX_SPEAKERS_PER_EVENT <= 5


def test_parse_args_requires_a_running_api_and_defaults_to_the_login_student() -> None:
    """There is no database-only mode: the whole point is to go through the route."""
    with pytest.raises(SystemExit):
        parse_args([])
    args = parse_args(["--api-base", "http://127.0.0.1:18080"])
    assert args.subjects == "login"
    assert args.student_subject is None
    assert args.cohort is False


def test_the_report_distinguishes_a_created_rating_from_an_amended_one() -> None:
    """``200`` is the ordinary re-run path and is not the same fact as ``201``."""
    report = FeedbackReport(ratings_created=4, ratings_amended=2)
    lines = "\n".join(report.lines())
    assert "created      4" in lines
    assert "amended      2" in lines


# -- the cohort leg ---------------------------------------------------------


def test_the_cohort_shape_fits_the_cohort() -> None:
    """No entry may call for more students than the cohort holds.

    ``build_speaker_feedback`` refuses a shape whose widest entry needs more
    opportunities than ``FEEDBACK_STUDENT_COUNT`` provides — this test turns
    that runtime refusal into a load-time guarantee, so a shape bump that
    outgrew the cohort fails here and not fifty requests into a live run.
    """
    from pilot_dataset_plan import (
        FEEDBACK_STUDENT_COUNT,
        FEEDBACK_WITHHELD_SHARE,
        build_speaker_feedback,
    )

    widest = max(
        round(posted / (1.0 - FEEDBACK_WITHHELD_SHARE)) for posted in COHORT_RESPONSE_SHAPE
    )
    assert widest <= FEEDBACK_STUDENT_COUNT
    # And the module agrees: the shape must build, not merely look buildable.
    build_speaker_feedback(shape=COHORT_RESPONSE_SHAPE)


def test_the_cohort_shape_shows_both_sides_of_the_publish_line() -> None:
    """The demo needs published aggregates *and* suppressed ones to compare them."""
    assert any(count >= MIN_RESPONSES_FOR_AGGREGATE for count in COHORT_RESPONSE_SHAPE)
    assert any(0 < count < MIN_RESPONSES_FOR_AGGREGATE for count in COHORT_RESPONSE_SHAPE)


def test_the_cohort_plan_publishes_varied_means() -> None:
    """Every published mean landing on one number would demonstrate nothing.

    Pinned as a property — more than one distinct published mean — rather than
    the exact values, which are the plan module's seeded draw to change.
    """
    from pilot_dataset_plan import build_speaker_feedback

    planned = build_speaker_feedback(shape=COHORT_RESPONSE_SHAPE)
    by_speaker: dict[int, list[int]] = {}
    for entry in planned:
        if entry.rating is not None:
            by_speaker.setdefault(entry.speaker_rank, []).append(entry.rating)
    published_means = {
        round(sum(ratings) / len(ratings), 2)
        for ratings in by_speaker.values()
        if len(ratings) >= MIN_RESPONSES_FOR_AGGREGATE
    }
    assert len(published_means) > 1


def test_the_cohort_report_is_a_separate_set_of_lines() -> None:
    """The cohort's counts are printed only when the leg ran — a skipped leg
    must not look like a leg that ran and found nothing to do."""
    quiet = FeedbackReport(ratings_created=1)
    assert "cohort" not in "\n".join(quiet.lines())
    ran = FeedbackReport(cohort_ran=True, cohort_ratings_created=50)
    lines = "\n".join(ran.lines())
    assert "cohort ratings created" in lines
    assert "50" in lines
