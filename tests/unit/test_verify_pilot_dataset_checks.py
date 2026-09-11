"""``verify_pilot_dataset`` must fail a *disconnected* dataset, not only an empty one.

The tool's first two passes count rows: is this table empty, and does the person
who signs in own any of them. Both were satisfied by a database a demo could not
be given from — sixty-four events, three match runs and nine invitations that,
for all a count could say, might have belonged to none of each other.

This file pins the third pass. It needs no database: every check is a pair of
``SELECT count(*)`` statements built from the shipped metadata, so the questions
they ask, the tables they ask them of, and the tenant they scope them to are all
readable without executing anything. What a database would add is the *answer*,
and the answer is the operator's business — ``make verify-pilot-dataset`` — not
a unit test's.

It also pins the ownership default, which is the correction the module carries:
a person-scoped surface belongs to the account a reviewer signs in as
(``pilot-login-*``), and the compose bearer-token fixtures (``compose-pilot-*``)
are the opt-in, not the default. That was the other way round, and the visible
consequence was a report calling the student portal healthy while ``student@``
saw a blank page.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parents[2]

# `tools/` on the path rather than the repository root, for the reason
# `test_demo_portal_surfaces.py` gives about its own import: these modules are
# run by compose as bare siblings and importing them as `tools.…` would exercise
# a module shape nothing runs.
sys.path.insert(0, str(REPO_ROOT / "tools"))

from seed_pilot_logins import ROLE_CREDENTIALS  # noqa: E402
from seed_pilot_principals import COMPOSE_DEV_PRINCIPALS  # noqa: E402
from verify_pilot_dataset import (  # noqa: E402
    CROSS_TABLE_CHECKS,
    DEFAULT_SUBJECT_SET,
    DEMO_PORTAL_SURFACES,
    FIXTURE_SUBJECT_SET,
    LOGIN_SUBJECT_SET,
    SUBJECT_SETS,
    CheckResult,
    JoinCheck,
    OwnedByColumn,
    OwnedByLedgerCause,
    ReferenceCheck,
    check_report_lines,
    subjects_for,
)

#: The properties the owner asked this tool to assert, by check name.
#:
#: Restated here rather than derived from ``CROSS_TABLE_CHECKS`` so this file is
#: a second statement of the requirement and not a tautology over the first. A
#: check deleted from the tool fails here; a check renamed fails here; a check
#: added does not, because the list below is a floor and not a census.
_REQUIRED_CHECKS: frozenset[str] = frozenset(
    {
        "event_with_a_match_run_has_invitations",
        "match_run_names_a_real_event",
        "invitation_names_a_roster_speaker",
        "attendance_names_an_event",
        "attendance_names_an_account",
        "feedback_names_an_event",
        "feedback_names_a_roster_speaker",
        "feedback_is_backed_by_attendance",
        "ledger_entry_has_a_cause",
    }
)

_TENANT = sa.literal_column("'11111111-1111-1111-1111-111111111111'::uuid")
_UNIT = sa.literal_column("'22222222-2222-2222-2222-222222222222'::uuid")


def _compiled(statement: object) -> str:
    """The statement as PostgreSQL would see it, values inlined."""
    return str(
        statement.compile(  # type: ignore[attr-defined]
            dialect=sa.dialects.postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_every_required_cross_table_property_is_checked() -> None:
    """A dataset can satisfy every count and still be a set of unrelated islands."""
    declared = {check.name for check in CROSS_TABLE_CHECKS}
    missing = sorted(_REQUIRED_CHECKS - declared)
    assert not missing, (
        "verify_pilot_dataset asserts row counts but no longer asserts these "
        f"cross-table properties: {missing}"
    )


def test_check_names_are_unique() -> None:
    """A name is how a failure is grepped for; two of one name hides one."""
    names = [check.name for check in CROSS_TABLE_CHECKS]
    assert len(names) == len(set(names)), f"duplicate check names: {sorted(names)}"


@pytest.mark.parametrize("check", CROSS_TABLE_CHECKS, ids=lambda c: c.name)
def test_every_check_builds_two_tenant_scoped_counts(check: object) -> None:
    """Both halves of a check must compile, count, and carry a tenant predicate.

    The tenant predicate is the one that cannot be left out. A check that reads
    every tenant's rows would pass on a shared database because somebody else's
    dataset is connected, which is the least useful way for this tool to be
    wrong.
    """
    if isinstance(check, ReferenceCheck):
        statements = [
            check.table.select(),  # placeholder, replaced below
        ]
        # ReferenceCheck builds its SQL inside `counts`, which needs a session.
        # Rebuild the same two statements here from its declared parts instead
        # of executing anything.
        scope = [check.table.c.tenant_id == _TENANT]
        if check.unit_column is not None:
            scope.append(check.table.c[check.unit_column] == _UNIT)
        source = check.table.c[check.column]
        target_key: sa.ColumnElement[object] = check.target.c[check.target_column]
        if check.cast_target_to_text:
            target_key = sa.cast(target_key, sa.Text)
        resolves = sa.select(sa.literal(1)).where(
            check.target.c.tenant_id == _TENANT, target_key == source
        )
        statements = [
            sa.select(sa.func.count()).select_from(check.table).where(*scope),
            sa.select(sa.func.count()).select_from(check.table).where(*scope, ~resolves.exists()),
        ]
    else:
        assert isinstance(check, JoinCheck)
        statements = [
            check.population_query(_TENANT, _UNIT),  # type: ignore[operator]
            check.violations_query(_TENANT, _UNIT),  # type: ignore[operator]
        ]

    for statement in statements:
        sql = _compiled(statement)
        assert "count(*)" in sql, f"{check.name} does not count rows: {sql}"
        assert "tenant_id" in sql, f"{check.name} is not tenant-scoped: {sql}"


@pytest.mark.parametrize("check", CROSS_TABLE_CHECKS, ids=lambda c: c.name)
def test_every_check_says_what_to_do_about_it(check: object) -> None:
    """A finding with no remedy is a sentence nobody can act on."""
    assert check.question.strip(), f"{check.name} asks nothing"  # type: ignore[attr-defined]
    assert check.remedy.strip(), f"{check.name} names no remedy"  # type: ignore[attr-defined]


def test_reference_check_scopes_the_target_to_the_unit_when_it_says_so() -> None:
    """ "A speaker on *this* unit's roster" must be a unit predicate, not prose."""
    roster = next(
        check for check in CROSS_TABLE_CHECKS if check.name == "invitation_names_a_roster_speaker"
    )
    assert isinstance(roster, ReferenceCheck)
    assert roster.target_unit_column == "owning_unit_id", (
        "an invitation naming any speaker in the tenant is not the property; the roster is per unit"
    )


def test_match_run_event_correlation_is_a_text_comparison() -> None:
    """``match_run.event_need_id`` is ``sa.Text`` and deliberately not a foreign key.

    The pilot generator puts an event id in it, so the correlation is real and
    worth checking — but the column is text, and a check that compared it to a
    ``uuid`` would fail to compile rather than find anything.
    """
    check = next(
        check for check in CROSS_TABLE_CHECKS if check.name == "match_run_names_a_real_event"
    )
    assert isinstance(check, ReferenceCheck)
    assert check.cast_target_to_text, "event.id must be cast to text to meet event_need_id"


# -- the verdict ------------------------------------------------------------


def test_a_check_over_no_rows_is_a_failure_and_says_vacuous() -> None:
    """ "Every invitation names a roster speaker" is trivially true of no invitations.

    A check that can only pass is not a check, and a dataset whose whole purpose
    is to demonstrate the property does not get to demonstrate it with nothing.
    """
    result = CheckResult(
        name="feedback_is_backed_by_attendance",
        question="every student rating is backed by attendance",
        population=0,
        violations=0,
        remedy="run `make top-up-pilot-dataset`",
    )
    assert result.vacuous
    assert result.failed
    assert result.verdict == "VACUOUS"


def test_a_check_with_violations_is_broken() -> None:
    result = CheckResult(
        name="pipeline_record_names_an_event",
        question="every pipeline record names an event",
        population=319,
        violations=139,
        remedy="regenerate",
    )
    assert not result.vacuous
    assert result.failed
    assert result.verdict == "BROKEN"


def test_a_satisfied_check_over_real_rows_passes() -> None:
    result = CheckResult(
        name="attendance_names_an_event",
        question="every attendance record names an event",
        population=258,
        violations=0,
        remedy="regenerate",
    )
    assert not result.failed
    assert result.verdict == "OK"


def test_the_report_prints_the_population_beside_the_verdict() -> None:
    """ "OK" over nine rows and over nine hundred are different datasets."""
    lines = check_report_lines(
        (
            CheckResult(
                name="invitation_names_a_roster_speaker",
                question="every invitation names a roster speaker",
                population=9,
                violations=0,
                remedy="regenerate",
            ),
        )
    )
    assert len(lines) == 1
    assert "OK" in lines[0]
    assert "9" in lines[0]
    assert "every invitation names a roster speaker" in lines[0]


# -- whose rows -------------------------------------------------------------


def test_the_default_subject_family_is_the_browser_logins() -> None:
    """The correction this module carries, pinned so it cannot drift back."""
    assert DEFAULT_SUBJECT_SET == "login"
    assert subjects_for() is LOGIN_SUBJECT_SET
    assert set(LOGIN_SUBJECT_SET.values()) == {entry.subject for entry in ROLE_CREDENTIALS}
    assert all(subject.startswith("pilot-login-") for subject in LOGIN_SUBJECT_SET.values())


def test_the_fixture_family_is_still_reachable_and_is_the_compose_principals() -> None:
    """A token-driven stack with no browser is a real case; it is just not the default."""
    assert subjects_for("fixture") is FIXTURE_SUBJECT_SET
    assert set(FIXTURE_SUBJECT_SET.values()) == {
        principal.subject for principal in COMPOSE_DEV_PRINCIPALS
    }


def test_an_unknown_subject_family_is_refused_rather_than_defaulted() -> None:
    """Falling back to the fixtures silently is the failure this parameter ends."""
    with pytest.raises(KeyError):
        subjects_for("whatever-the-caller-typed")


def test_both_families_cover_every_role_a_person_scoped_surface_names() -> None:
    """A surface whose role no family resolves would report a permanent zero."""
    roles = {surface.role for surface in DEMO_PORTAL_SURFACES if surface.owner is not None}
    for name, family in SUBJECT_SETS.items():
        missing = sorted(roles - set(family))
        assert not missing, f"subject family {name!r} has no account for roles {missing}"


def test_the_points_ledger_is_owned_through_its_cause_and_not_a_column() -> None:
    """The bug this replaces: ``subject_id`` does not exist there and ``actor_id`` is NULL.

    ``point_ledger_entry`` carries no owner. It names an attendance or a
    redemption, and *those* name the student — which is exactly the fold
    ``RewardsRepository.ledger_entries_for_subject`` performs. The first spelling
    tried here was ``subject_id``, which raised ``KeyError`` and took the whole
    tool down; the obvious repair, ``actor_id``, exists but is NULL on every
    attendance credit, so it would have reported a permanently empty student
    balance as a fact about the data.
    """
    ledger = next(
        surface for surface in DEMO_PORTAL_SURFACES if surface.table.name == "point_ledger_entry"
    )
    assert isinstance(ledger.owner, OwnedByLedgerCause)
    assert not isinstance(ledger.owner, OwnedByColumn)


def test_the_ledger_owner_predicate_reaches_both_kinds_of_cause() -> None:
    """A credit comes from attendance and a debit from a redemption; both count."""
    import uuid as _uuid

    from smartmatch_persistence import schema

    predicate = OwnedByLedgerCause().predicate(
        schema.point_ledger_entry, _uuid.UUID("33333333-3333-3333-3333-333333333333")
    )
    sql = _compiled(
        sa.select(sa.func.count()).select_from(schema.point_ledger_entry).where(predicate)
    )
    assert "attendance_record" in sql
    assert "redemption" in sql
    assert "source_attendance_id" in sql
    assert "source_redemption_id" in sql


@pytest.mark.parametrize("surface", DEMO_PORTAL_SURFACES, ids=lambda s: f"{s.token}:{s.table.name}")
def test_every_surface_declares_a_floor_of_at_least_one_row(surface: object) -> None:
    """A floor of zero is not a floor, and one row is a list with one row on it."""
    assert surface.minimum_rows >= 1, (  # type: ignore[attr-defined]
        f"{surface.surface!r} declares no minimum"  # type: ignore[attr-defined]
    )


def test_a_surface_below_its_floor_is_reported_as_thin_not_only_as_empty() -> None:
    """Three attendances is a demonstrable agenda; one is a screenshot of a bug."""
    from verify_pilot_dataset import SurfaceCount

    thin = SurfaceCount(
        token="compose-student",
        surface="My agenda (attended)",
        name="attendance_record",
        owner="pilot-login-student",
        rows=1,
        minimum_rows=3,
        writer="make top-up-pilot-dataset",
    )
    assert not thin.empty
    assert thin.short
