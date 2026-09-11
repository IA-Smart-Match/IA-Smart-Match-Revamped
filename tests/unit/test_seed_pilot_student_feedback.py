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
from smartmatch_domain.student_speaker_feedback import EditWindowState  # noqa: E402

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


def test_the_report_distinguishes_a_created_rating_from_an_amended_one() -> None:
    """``200`` is the ordinary re-run path and is not the same fact as ``201``."""
    report = FeedbackReport(ratings_created=4, ratings_amended=2)
    lines = "\n".join(report.lines())
    assert "created      4" in lines
    assert "amended      2" in lines
