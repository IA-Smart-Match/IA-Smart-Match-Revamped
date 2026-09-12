"""The engagement seeder must write under the accounts a person signs in as.

``tools/seed_pilot_engagement.py`` exists because several portal surfaces are
scoped by ``principal.user_id``: an agenda, a points balance, a redemption
history, an Event Host's own filed requests. It fills them for one named
account, and *which* account is the whole question — a row under the wrong
subject is indistinguishable, from the database, from a row under the right
one, and indistinguishable, from a screen, from no row at all.

It defaulted to the ``compose-pilot-*`` bearer-token fixtures. Those accounts
have no password and no login form; ``POST /v1/auth/login`` cannot produce one.
So the tool reported a seeded student portal while ``student@test.com`` looked
at a blank page, which is the same defect the tool was written to remove,
displaced by one level.

This file pins the corrected default, and pins that the fixture family is still
reachable — a token-driven stack with no browser is a real case; it is just not
the common one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# `tools/` on the path rather than the repository root: these modules are run by
# compose as bare siblings and importing them as `tools.…` would exercise a
# module shape nothing runs.
sys.path.insert(0, str(REPO_ROOT / "tools"))

from seed_pilot_engagement import (  # noqa: E402
    DEFAULT_SUBJECT_SET,
    FIXTURE_SUBJECT_SET,
    LOGIN_SUBJECT_SET,
    REQUIRED_ROLES,
    SUBJECT_SETS,
    SeedEngagementError,
    parse_args,
    subjects_for,
)
from seed_pilot_logins import ROLE_CREDENTIALS  # noqa: E402
from seed_pilot_principals import COMPOSE_DEV_PRINCIPALS  # noqa: E402


def test_the_default_family_is_the_browser_logins() -> None:
    """The correction, pinned at the default rather than described in a doc."""
    assert DEFAULT_SUBJECT_SET == "login"
    resolved = subjects_for()
    assert all(subject.startswith("pilot-login-") for subject in resolved.values())


def test_parse_args_defaults_to_the_login_family_and_names_no_subject() -> None:
    """The four --*-subject flags default to None so the family decides."""
    args = parse_args(["--items-from-worksheet"])
    assert args.subjects == "login"
    assert args.student_subject is None
    assert args.coordinator_subject is None
    assert args.host_subject is None
    assert args.budget_owner_subject is None


def test_the_fixture_family_is_opt_in_and_is_the_compose_principals() -> None:
    args = parse_args(["--items-from-worksheet", "--subjects", "fixture"])
    assert args.subjects == "fixture"
    resolved = subjects_for("fixture")
    assert set(resolved.values()) == {principal.subject for principal in COMPOSE_DEV_PRINCIPALS}


def test_neither_family_is_restated_in_this_tool() -> None:
    """One writer per account. A third copy of a subject string is the first to drift."""
    assert set(LOGIN_SUBJECT_SET.values()) == {entry.subject for entry in ROLE_CREDENTIALS}
    assert set(FIXTURE_SUBJECT_SET.values()) == {
        principal.subject for principal in COMPOSE_DEV_PRINCIPALS
    }


@pytest.mark.parametrize("family", sorted(SUBJECT_SETS))
def test_every_family_covers_every_role_this_tool_writes_under(family: str) -> None:
    """A family missing a role must fail at parse time, not three writes in."""
    resolved = subjects_for(family)
    assert all(resolved.get(role) for role in REQUIRED_ROLES)


def test_one_subject_can_be_overridden_without_restating_the_others() -> None:
    resolved = subjects_for(overrides={"student": "some-other-student"})
    assert resolved["student"] == "some-other-student"
    assert resolved["coordinator"] == LOGIN_SUBJECT_SET["coordinator"]


def test_an_override_of_none_means_not_given() -> None:
    """argparse hands every unset --*-subject through as None."""
    resolved = subjects_for(overrides={"student": None, "admin": None})
    assert resolved["student"] == LOGIN_SUBJECT_SET["student"]
    assert resolved["admin"] == LOGIN_SUBJECT_SET["admin"]


def test_an_unknown_family_is_refused_rather_than_silently_defaulted() -> None:
    """Falling back to the fixtures quietly is the failure this flag ends."""
    with pytest.raises(SeedEngagementError) as raised:
        subjects_for("whatever-the-caller-typed")
    assert "unknown subject family" in str(raised.value)


def test_a_family_with_a_missing_role_is_refused() -> None:
    """An empty subject would resolve to no account and write nothing visible."""
    with pytest.raises(SeedEngagementError) as raised:
        subjects_for(overrides={"student": ""})
    assert "student" in str(raised.value)


def test_the_worksheet_flag_is_still_required() -> None:
    """The catalog has one source and stating it is the operator's act, not a default."""
    with pytest.raises(SystemExit):
        parse_args([])
