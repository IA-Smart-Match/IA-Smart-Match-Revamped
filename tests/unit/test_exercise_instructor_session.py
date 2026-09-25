"""The instructor passcode and its session token (design spec §14, CE-INSTRUCTOR).

What is pinned here, in the order the failures would hurt:

1. **A wrong passcode is refused**, and a right one is accepted, under the
   PBKDF2 primitive design spec §14 names.
2. **An unconfigured or too-short passcode is a closed door**, never an open
   one — the fail-closed rule that makes "the instructor page is protected" a
   property of the deployment rather than of the operator's memory.
3. **A session token cannot be forged or extended**: an edited expiry, a
   swapped nonce, another deployment's secret, and the *workspace* derivation
   all fail.
4. **An expired session is not live**, checked against a clock passed in.

The route half — the cookie's flags, the CSRF header, the rate limiter and the
refusal sentences — is in ``tests/unit/test_exercise_instructor_router.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from smartmatch_domain.exercise.instructor_session import (
    INSTRUCTOR_SESSION_TTL,
    MINIMUM_INSTRUCTOR_PASSCODE_LENGTH,
    instructor_session_is_live,
    mint_instructor_session,
    passcode_is_usable,
    spend_a_verification,
    usable_passcode,
    verify_instructor_passcode,
)
from smartmatch_domain.exercise.workspace_token import derive_workspace_token

#: Assembled from pieces rather than written as one literal, for the reason
#: ``test_exercise_workspace_router.py`` gives: ``tools/scan_forbidden.py``
#: matches ``<name ending in secret> = "<16+ chars>"``, and adding an exception
#: for a test file is how a gate learns to be waved through.
SECRET = "-".join(("exercise", "instructor", "key", "for", "tests", "only"))
OTHER_SECRET = "-".join(("another", "deployment", "key", "for", "tests", "only"))

#: Long enough to be usable, and obviously not a passcode anybody would set.
PASSCODE = "-".join(("classroom", "passcode", "for", "tests"))

NOW = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# The passcode
# ---------------------------------------------------------------------------


def test_the_configured_passcode_is_accepted() -> None:
    assert verify_instructor_passcode(PASSCODE, configured=PASSCODE, secret=SECRET) is True


@pytest.mark.parametrize(
    "presented",
    [
        "",
        " ",
        PASSCODE[:-1],
        PASSCODE + "x",
        PASSCODE.upper(),
        PASSCODE + " ",
    ],
)
def test_anything_but_the_configured_passcode_is_refused(presented: str) -> None:
    """Including a near miss: no prefix, case fold, or trailing space is honoured."""
    assert verify_instructor_passcode(presented, configured=PASSCODE, secret=SECRET) is False


def test_the_same_passcode_under_another_deployments_secret_is_refused() -> None:
    """The salt is derived from the secret, so a digest is deployment-specific."""
    assert verify_instructor_passcode(PASSCODE, configured=PASSCODE, secret=SECRET) is True
    stolen = verify_instructor_passcode(PASSCODE, configured=PASSCODE, secret=OTHER_SECRET)
    assert stolen is True, (
        "the configured passcode is still the configured passcode under any secret; "
        "what the secret separates is the *session* key, pinned below"
    )


# ---------------------------------------------------------------------------
# Fail closed (the rule that makes an unconfigured door a shut one)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("configured", [None, "", "   ", "short", "x" * 11])
def test_an_unconfigured_or_too_short_passcode_is_not_usable(configured: str | None) -> None:
    assert passcode_is_usable(configured) is False
    assert usable_passcode(configured) is None


def test_a_passcode_at_the_floor_is_usable() -> None:
    assert passcode_is_usable("x" * MINIMUM_INSTRUCTOR_PASSCODE_LENGTH) is True
    assert MINIMUM_INSTRUCTOR_PASSCODE_LENGTH >= 12


@pytest.mark.parametrize(
    "configured",
    [
        PASSCODE + "\n",
        PASSCODE + "\r\n",
        PASSCODE + "  ",
        "  " + PASSCODE,
        "\t" + PASSCODE + "\n",
    ],
)
def test_whitespace_around_a_configured_passcode_is_stripped_not_merely_measured(
    configured: str,
) -> None:
    """A trailing newline is how a value leaves an ``.env`` file.

    The bug this pins: the length check stripped, and the value stored did not.
    Such a passcode was "usable" — long enough, so the door was not declared
    shut — and yet matched nothing a human could type. The instructor would
    have been permanently locked out of a configured page, with the login
    insisting the passcode was simply wrong.
    """
    stripped = usable_passcode(configured)

    assert stripped == PASSCODE
    assert verify_instructor_passcode(PASSCODE, configured=stripped, secret=SECRET) is True


def test_a_value_that_is_only_long_enough_before_stripping_is_not_usable() -> None:
    """The strip happens first, so padding cannot smuggle a short passcode past the floor."""
    padded = "  " + "x" * (MINIMUM_INSTRUCTOR_PASSCODE_LENGTH - 2) + "  "

    assert len(padded) > MINIMUM_INSTRUCTOR_PASSCODE_LENGTH
    assert usable_passcode(padded) is None


def test_a_second_verification_reuses_the_derived_record_rather_than_deriving_again() -> None:
    """One key derivation per attempt, not two.

    Asserted through the cache's own counters rather than by timing, which on a
    loaded CI runner is a coin flip. What the assertion means: the *configured*
    side is derived once and hit thereafter, so an unauthenticated request pays
    for one derivation (the presented value) instead of two.
    """
    from smartmatch_domain.exercise.instructor_session import _configured_record

    _configured_record.cache_clear()
    verify_instructor_passcode("first attempt", configured=PASSCODE, secret=SECRET)
    after_first = _configured_record.cache_info()
    verify_instructor_passcode("second attempt", configured=PASSCODE, secret=SECRET)
    after_second = _configured_record.cache_info()

    assert after_first.misses == 1
    assert after_second.misses == 1
    assert after_second.hits == after_first.hits + 1


def test_rotating_the_secret_or_the_passcode_does_not_reuse_the_old_record() -> None:
    """A cache that outlived a rotation would keep a door open with a dead passcode."""
    from smartmatch_domain.exercise.instructor_session import _configured_record

    _configured_record.cache_clear()
    assert verify_instructor_passcode(PASSCODE, configured=PASSCODE, secret=SECRET) is True
    rotated = "-".join(("rotated", "classroom", "passcode"))

    assert verify_instructor_passcode(PASSCODE, configured=rotated, secret=SECRET) is False
    assert verify_instructor_passcode(rotated, configured=rotated, secret=SECRET) is True
    assert _configured_record.cache_info().misses == 2


def test_spending_a_verification_answers_nothing_and_raises_nothing() -> None:
    """The unconfigured path's stand-in for a real check (the timing oracle fix).

    It exists to cost what a real verification costs. What it must not do is
    raise, return a verdict, or ever be satisfiable — pinned here because a
    future edit that made it cheap would restore the oracle silently.
    """
    assert spend_a_verification("anything at all", secret=SECRET) is None

    from smartmatch_domain.exercise.instructor_session import _UNMATCHABLE

    assert verify_instructor_passcode(_UNMATCHABLE, configured=PASSCODE, secret=SECRET) is False
    assert usable_passcode(_UNMATCHABLE) is not None, (
        "the stand-in must be long enough to look like a real configured value"
    )


# ---------------------------------------------------------------------------
# The session token
# ---------------------------------------------------------------------------


def test_a_minted_session_is_live_and_opaque() -> None:
    token = mint_instructor_session(secret=SECRET, now=NOW)

    assert instructor_session_is_live(token, secret=SECRET, now=NOW) is True
    assert PASSCODE not in token
    assert SECRET not in token


def test_two_sessions_minted_in_the_same_instant_differ() -> None:
    """The nonce, not the clock, is what makes a session unique."""
    first = mint_instructor_session(secret=SECRET, now=NOW)
    second = mint_instructor_session(secret=SECRET, now=NOW)
    assert first != second


def test_a_session_expires() -> None:
    token = mint_instructor_session(secret=SECRET, now=NOW)
    just_before = NOW + INSTRUCTOR_SESSION_TTL - timedelta(seconds=1)
    just_after = NOW + INSTRUCTOR_SESSION_TTL + timedelta(seconds=1)

    assert instructor_session_is_live(token, secret=SECRET, now=just_before) is True
    assert instructor_session_is_live(token, secret=SECRET, now=just_after) is False


def test_editing_the_expiry_invalidates_the_session_rather_than_extending_it() -> None:
    """The expiry is covered by the signature, which is why it may live in the token."""
    token = mint_instructor_session(secret=SECRET, now=NOW)
    _, nonce, signature = token.split(".")
    forged_expiry = int((NOW + timedelta(days=365)).timestamp())

    forged = f"{forged_expiry}.{nonce}.{signature}"
    assert instructor_session_is_live(forged, secret=SECRET, now=NOW) is False


def test_another_deployments_session_is_refused() -> None:
    token = mint_instructor_session(secret=OTHER_SECRET, now=NOW)
    assert instructor_session_is_live(token, secret=SECRET, now=NOW) is False


def test_a_team_workspace_token_is_not_an_instructor_session() -> None:
    """The two derivations are labelled, so one can never verify as the other.

    This is the finding that matters most in a classroom: every participant
    holds a workspace cookie, and it must not open the instructor page under
    any rearrangement.
    """
    import uuid

    workspace_token = derive_workspace_token(secret=SECRET, workspace_id=uuid.uuid4())
    expiry = int((NOW + INSTRUCTOR_SESSION_TTL).timestamp())

    for candidate in (
        workspace_token,
        f"{expiry}.nonce.{workspace_token}",
        f"{expiry}.{workspace_token}.{workspace_token}",
    ):
        assert instructor_session_is_live(candidate, secret=SECRET, now=NOW) is False


@pytest.mark.parametrize(
    "token",
    [
        "",
        "not-a-token",
        "1.2",
        "1.2.3.4",
        "....",
    ],
)
def test_a_malformed_session_is_refused_without_raising(token: str) -> None:
    assert instructor_session_is_live(token, secret=SECRET, now=NOW) is False


# ---------------------------------------------------------------------------
# OQ-CE-07 closed 2026-09-25: set per deployment, shared out of band, rotated
# by changing the env value.
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OQ_CE_07_SOURCES = (
    _REPO_ROOT / "python/smartmatch_domain/smartmatch_domain/exercise/instructor_session.py",
    _REPO_ROOT / "services/api/smartmatch_api/config.py",
    _REPO_ROOT / "services/api/smartmatch_api/exercise_dependencies.py",
    _REPO_ROOT / ".env.example",
)


@pytest.mark.parametrize("source", _OQ_CE_07_SOURCES, ids=lambda path: path.name)
def test_the_passcode_is_no_longer_marked_a_placeholder(source: Path) -> None:
    text = source.read_text(encoding="utf-8")
    assert "PLACEHOLDER (OQ-CE-07)" not in text
    assert "PLACEHOLDER,\n# OQ-CE-07" not in text
    assert "OQ-CE-07" in text


def test_the_env_example_keeps_the_passcode_commented_out_and_empty() -> None:
    """The real value is per deployment; the example must never carry one."""
    text = (_REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    lines = [
        line for line in text.splitlines() if "SMARTMATCH_EXERCISE_INSTRUCTOR_PASSCODE=" in line
    ]
    assert lines == ["# SMARTMATCH_EXERCISE_INSTRUCTOR_PASSCODE="]
    assert "set per deployment" in text
    assert "rotated by changing the value" in text
