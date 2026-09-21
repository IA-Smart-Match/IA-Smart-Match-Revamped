"""``--skip-redemptions`` must skip only the redemption writer, and nothing else.

``tools/seed_pilot_engagement.py --items-from-worksheet`` unconditionally wrote
:data:`seed_pilot_engagement.REDEMPTION_PLAN` — a fixed three-state demo
history that closes the catalog's cheapest item as ``fulfilled``. That is
correct for a demo appliance and wrong for a suite about to open its own
redemption against a catalog it expects untouched (the pilot-e2e CI job): the
history collided with
``test_14_the_rewards_catalog_is_a_students_to_read_and_nobody_elses``'s
"a freshly seeded appliance hands back no tickets nobody requested" assertion.

``--skip-redemptions`` leaves the catalog and the student's
attendance-derived balance seeded as usual and only skips
:func:`seed_pilot_engagement._seed_redemptions`. This file pins the argparse
wiring and that exact selectivity — following
``test_seed_pilot_engagement_subjects.py``'s pattern of importing the module
from ``tools/`` and never touching a database.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# `tools/` on the path rather than the repository root, for the same reason
# test_seed_pilot_engagement_subjects.py gives: these modules are run by
# compose as bare siblings, and importing them as `tools.…` would exercise a
# module shape nothing runs.
sys.path.insert(0, str(REPO_ROOT / "tools"))

import seed_pilot_engagement as sut  # noqa: E402


def test_parse_args_defaults_skip_redemptions_to_false() -> None:
    """Unset, the flag must not change today's behaviour."""
    args = sut.parse_args(["--items-from-worksheet"])
    assert args.skip_redemptions is False


def test_parse_args_sets_skip_redemptions_true() -> None:
    args = sut.parse_args(["--items-from-worksheet", "--skip-redemptions"])
    assert args.skip_redemptions is True


class _FakeSession:
    """Stands in for a ``Session``: nothing here ever executes SQL.

    Every module-level writer ``seed_engagement`` calls is monkeypatched below,
    so the session itself is passed through unopened and unused — a sentinel
    that would raise loudly if any real code ever tried to use it.
    """


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Monkeypatch every writer ``seed_engagement`` calls; count invocations.

    Faked at module scope, exactly where ``seed_engagement`` looks them up —
    they are plain module-level functions, not methods on an injectable
    collaborator, so patching ``sut.<name>`` is how a call is observed without
    a database.
    """
    seen: dict[str, int] = {
        "resolve_tenant_id": 0,
        "resolve_unit_id": 0,
        "_subject_id": 0,
        "_seed_catalog": 0,
        "_seed_student": 0,
        "_seed_redemptions": 0,
        "_seed_meetings": 0,
        "_seed_host_request": 0,
    }

    def _count(name: str) -> Any:
        def _fake(*_args: Any, **_kwargs: Any) -> Any:
            seen[name] += 1
            if name in {"resolve_tenant_id", "resolve_unit_id", "_subject_id"}:
                return "11111111-1111-1111-1111-111111111111"
            if name == "_seed_catalog":
                return {
                    item.name: "22222222-2222-2222-2222-222222222222"
                    for item in sut.WORKSHEET_ITEMS
                }
            return None

        return _fake

    for name in seen:
        monkeypatch.setattr(sut, name, _count(name))

    return seen


def test_skip_redemptions_true_never_calls_the_redemption_writer(
    calls: dict[str, int],
) -> None:
    """The one writer this flag exists to skip, and no other."""
    sut.seed_engagement(
        _FakeSession(),
        tenant_slug="pilot",
        unit_path="pilot",
        student_subject="pilot-login-student",
        coordinator_subject="pilot-login-coordinator",
        host_subject="pilot-login-volunteer",
        budget_owner_subject="pilot-login-admin",
        skip_redemptions=True,
    )

    assert calls["_seed_redemptions"] == 0, (
        "skip_redemptions=True still called _seed_redemptions — the fixed "
        "demo history was written anyway"
    )
    # Everything else still ran: the catalog and the balance are seeded either
    # way, and so is the meeting/host-request pair.
    assert calls["_seed_catalog"] == 1
    assert calls["_seed_student"] == 1
    assert calls["_seed_meetings"] == 1
    assert calls["_seed_host_request"] == 1


def test_skip_redemptions_false_still_calls_the_redemption_writer(
    calls: dict[str, int],
) -> None:
    """The default (unset --skip-redemptions) is unchanged: the demo history writes."""
    sut.seed_engagement(
        _FakeSession(),
        tenant_slug="pilot",
        unit_path="pilot",
        student_subject="pilot-login-student",
        coordinator_subject="pilot-login-coordinator",
        host_subject="pilot-login-volunteer",
        budget_owner_subject="pilot-login-admin",
        skip_redemptions=False,
    )

    assert calls["_seed_redemptions"] == 1
    assert calls["_seed_catalog"] == 1
    assert calls["_seed_student"] == 1
    assert calls["_seed_meetings"] == 1
    assert calls["_seed_host_request"] == 1


def test_skip_redemptions_defaults_to_false_on_seed_engagement_itself(
    calls: dict[str, int],
) -> None:
    """The kwarg's own default, not only argparse's, keeps today's behaviour."""
    sut.seed_engagement(
        _FakeSession(),
        tenant_slug="pilot",
        unit_path="pilot",
        student_subject="pilot-login-student",
        coordinator_subject="pilot-login-coordinator",
        host_subject="pilot-login-volunteer",
        budget_owner_subject="pilot-login-admin",
    )

    assert calls["_seed_redemptions"] == 1
