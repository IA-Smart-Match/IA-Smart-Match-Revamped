"""Unit coverage for the development-only funded-reward seed tool.

On the pattern of ``tests/unit/test_seed_pilot.py``: a fake ``Connection`` that
returns queued results, so :func:`seed_pilot_rewards.seed_reward_item` is
proved against controlled rows rather than a live database — this file needs
none, unlike ``tests/integration/test_rewards_repository.py`` which proves the
same writer against real PostgreSQL constraints.
"""

from __future__ import annotations

import decimal
import sys
import uuid
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

# `tools/` on the path, not the repository root: `seed_pilot_rewards.py` is run
# by `make seed-pilot-rewards` with PYTHONPATH containing `tools`, where its
# sibling import of `seed_pilot` resolves as a bare module — the same reason
# `tests/unit/test_compose_dev_principals.py` does this for
# `seed_pilot_principals`. Importing it as `tools.…` instead would exercise an
# import shape the script never runs under.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import seed_pilot_rewards  # noqa: E402
from seed_pilot import SeedConflictError  # noqa: E402
from smartmatch_api.config import Settings  # noqa: E402
from smartmatch_providers import Edition  # noqa: E402


class _Result:
    def __init__(self, *, one: object | None = None) -> None:
        self._one = one

    def one_or_none(self) -> object | None:
        return self._one


class _Connection:
    """Queues one result per ``execute`` call, in call order."""

    def __init__(self, results: list[_Result]) -> None:
        self.results = results
        self.calls: list[object] = []

    def execute(self, statement: object, params: object | None = None) -> _Result:
        self.calls.append(statement)
        return self.results.pop(0)


TENANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
OWNER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
ITEM_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")


# ---------------------------------------------------------------------------
# Every argument is required — no default anywhere
# ---------------------------------------------------------------------------


REQUIRED_FLAGS = (
    ["--points-cost", "1", "--fulfilment-cost", "0", "--budget-owner-subject", "sub", "--funded"],
    ["--name", "x", "--fulfilment-cost", "0", "--budget-owner-subject", "sub", "--funded"],
    ["--name", "x", "--points-cost", "1", "--budget-owner-subject", "sub", "--funded"],
    ["--name", "x", "--points-cost", "1", "--fulfilment-cost", "0", "--funded"],
    ["--name", "x", "--points-cost", "1", "--fulfilment-cost", "0", "--budget-owner-subject", "sub"],
)


@pytest.mark.parametrize("argv", REQUIRED_FLAGS)
def test_omitting_any_required_argument_exits_non_zero(argv: list[str]):
    with pytest.raises(SystemExit):
        seed_pilot_rewards.parse_args(argv)


def test_every_value_supplied_parses_with_no_invented_default():
    args = seed_pilot_rewards.parse_args(
        [
            "--name",
            "Campus store $10 credit",
            "--points-cost",
            "300",
            "--fulfilment-cost",
            "10.00",
            "--budget-owner-subject",
            "pilot-login-coordinator",
            "--funded",
        ]
    )
    assert args.name == "Campus store $10 credit"
    assert args.points_cost == 300
    assert args.fulfilment_cost == decimal.Decimal("10.00")
    assert args.budget_owner_subject == "pilot-login-coordinator"
    assert args.funded is True


def test_funded_and_unfunded_are_mutually_exclusive_and_one_is_required():
    with pytest.raises(SystemExit):
        seed_pilot_rewards.parse_args(
            [
                "--name",
                "x",
                "--points-cost",
                "1",
                "--fulfilment-cost",
                "0",
                "--budget-owner-subject",
                "sub",
                "--funded",
                "--unfunded",
            ]
        )
    with pytest.raises(SystemExit):
        seed_pilot_rewards.parse_args(
            [
                "--name",
                "x",
                "--points-cost",
                "1",
                "--fulfilment-cost",
                "0",
                "--budget-owner-subject",
                "sub",
            ]
        )


# ---------------------------------------------------------------------------
# The settings gate, before any connection
# ---------------------------------------------------------------------------


def test_main_checks_settings_before_touching_the_database(monkeypatch: pytest.MonkeyPatch):
    events: list[str] = []
    monkeypatch.setattr(
        seed_pilot_rewards, "Settings", lambda: Settings(edition=Edition.STAGING)
    )
    monkeypatch.setattr(
        seed_pilot_rewards,
        "create_db_engine",
        lambda url: events.append("engine") or pytest.fail("engine created despite bad settings"),
    )

    exit_code = seed_pilot_rewards.main(
        [
            "--name",
            "x",
            "--points-cost",
            "1",
            "--fulfilment-cost",
            "0",
            "--budget-owner-subject",
            "sub",
            "--funded",
        ]
    )
    assert exit_code == 2
    assert events == []


def test_main_acquires_the_lock_before_seeding(monkeypatch: pytest.MonkeyPatch):
    settings = SimpleNamespace(
        edition=Edition.DEV,
        use_fixture_providers=True,
        database_url="postgresql+psycopg://configured.example.test/pilot",
    )
    events: list[str] = []
    connection = object()
    engine = SimpleNamespace(begin=lambda: nullcontext(connection), dispose=lambda: None)

    monkeypatch.setattr(seed_pilot_rewards, "Settings", lambda: settings)
    monkeypatch.setattr(
        seed_pilot_rewards, "create_db_engine", lambda url: events.append(url) or engine
    )
    monkeypatch.setattr(
        seed_pilot_rewards, "acquire_seed_lock", lambda conn: events.append("lock")
    )
    monkeypatch.setattr(
        seed_pilot_rewards,
        "seed_reward_item",
        lambda conn, **kwargs: events.append("seed")
        or seed_pilot_rewards.SeedRewardOutcome(
            created=True, item_id=ITEM_ID, satisfies_calibration=True
        ),
    )

    exit_code = seed_pilot_rewards.main(
        [
            "--name",
            "x",
            "--points-cost",
            "1",
            "--fulfilment-cost",
            "0",
            "--budget-owner-subject",
            "sub",
            "--funded",
        ]
    )
    assert exit_code == 0
    assert events == [settings.database_url, "lock", "seed"]


# ---------------------------------------------------------------------------
# seed_reward_item: resolution, idempotency, conflict
# ---------------------------------------------------------------------------


def test_seed_reward_item_creates_a_new_row_when_none_exists(monkeypatch: pytest.MonkeyPatch):
    connection = _Connection(
        [
            _Result(one=SimpleNamespace(id=TENANT_ID)),  # tenant lookup
            _Result(one=SimpleNamespace(id=OWNER_ID, tenant_id=TENANT_ID)),  # owner lookup
            _Result(one=None),  # no existing reward_item
        ]
    )

    created_calls: list[dict] = []

    class _FakeRepository:
        def create_item(self, conn, **kwargs):
            created_calls.append(kwargs)
            return ITEM_ID

    monkeypatch.setattr(seed_pilot_rewards, "RewardsRepository", _FakeRepository)

    outcome = seed_pilot_rewards.seed_reward_item(
        connection,  # type: ignore[arg-type]
        tenant_slug="pilot",
        name="Campus store $10 credit",
        points_cost=300,
        fulfilment_cost=decimal.Decimal("10.00"),
        budget_owner_subject="pilot-login-coordinator",
        funded=True,
    )

    assert outcome.created is True
    assert outcome.item_id == ITEM_ID
    assert outcome.satisfies_calibration is True
    assert created_calls == [
        {
            "tenant_id": TENANT_ID,
            "name": "Campus store $10 credit",
            "points_cost": 300,
            "fulfilment_cost": decimal.Decimal("10.00"),
            "budget_owner_id": OWNER_ID,
            "funded": True,
        }
    ]


def test_seed_reward_item_is_an_idempotent_repeat_for_identical_values():
    connection = _Connection(
        [
            _Result(one=SimpleNamespace(id=TENANT_ID)),
            _Result(one=SimpleNamespace(id=OWNER_ID, tenant_id=TENANT_ID)),
            _Result(
                one=SimpleNamespace(
                    id=ITEM_ID,
                    points_cost=300,
                    fulfilment_cost=decimal.Decimal("10.00"),
                    budget_owner_id=OWNER_ID,
                    funded=True,
                )
            ),
        ]
    )

    outcome = seed_pilot_rewards.seed_reward_item(
        connection,  # type: ignore[arg-type]
        tenant_slug="pilot",
        name="Campus store $10 credit",
        points_cost=300,
        fulfilment_cost=decimal.Decimal("10.00"),
        budget_owner_subject="pilot-login-coordinator",
        funded=True,
    )

    assert outcome.created is False
    assert outcome.item_id == ITEM_ID


def test_seed_reward_item_refuses_a_differing_repeat():
    connection = _Connection(
        [
            _Result(one=SimpleNamespace(id=TENANT_ID)),
            _Result(one=SimpleNamespace(id=OWNER_ID, tenant_id=TENANT_ID)),
            _Result(
                one=SimpleNamespace(
                    id=ITEM_ID,
                    points_cost=999,
                    fulfilment_cost=decimal.Decimal("10.00"),
                    budget_owner_id=OWNER_ID,
                    funded=True,
                )
            ),
        ]
    )

    with pytest.raises(SeedConflictError):
        seed_pilot_rewards.seed_reward_item(
            connection,  # type: ignore[arg-type]
            tenant_slug="pilot",
            name="Campus store $10 credit",
            points_cost=300,
            fulfilment_cost=decimal.Decimal("10.00"),
            budget_owner_subject="pilot-login-coordinator",
            funded=True,
        )


def test_seed_reward_item_refuses_an_unknown_tenant():
    connection = _Connection([_Result(one=None)])

    with pytest.raises(seed_pilot_rewards.UnknownTenantError):
        seed_pilot_rewards.seed_reward_item(
            connection,  # type: ignore[arg-type]
            tenant_slug="no-such-tenant",
            name="x",
            points_cost=1,
            fulfilment_cost=decimal.Decimal("0"),
            budget_owner_subject="sub",
            funded=True,
        )


def test_seed_reward_item_refuses_an_unknown_budget_owner_subject():
    connection = _Connection(
        [
            _Result(one=SimpleNamespace(id=TENANT_ID)),
            _Result(one=None),
        ]
    )

    with pytest.raises(seed_pilot_rewards.UnknownBudgetOwnerSubjectError):
        seed_pilot_rewards.seed_reward_item(
            connection,  # type: ignore[arg-type]
            tenant_slug="pilot",
            name="x",
            points_cost=1,
            fulfilment_cost=decimal.Decimal("0"),
            budget_owner_subject="no-such-subject",
            funded=True,
        )


def test_seed_reward_item_refuses_a_subject_in_a_different_tenant():
    other_tenant = uuid.uuid4()
    connection = _Connection(
        [
            _Result(one=SimpleNamespace(id=TENANT_ID)),
            _Result(one=SimpleNamespace(id=OWNER_ID, tenant_id=other_tenant)),
        ]
    )

    with pytest.raises(seed_pilot_rewards.UnknownBudgetOwnerSubjectError):
        seed_pilot_rewards.seed_reward_item(
            connection,  # type: ignore[arg-type]
            tenant_slug="pilot",
            name="x",
            points_cost=1,
            fulfilment_cost=decimal.Decimal("0"),
            budget_owner_subject="sub",
            funded=True,
        )


# ---------------------------------------------------------------------------
# The D7 calibration line: reported, never a refusal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("points_cost, expected", [(300, True), (1000, False)])
def test_calibration_is_reported_and_never_refuses(
    monkeypatch: pytest.MonkeyPatch, points_cost: int, expected: bool
):
    connection = _Connection(
        [
            _Result(one=SimpleNamespace(id=TENANT_ID)),
            _Result(one=SimpleNamespace(id=OWNER_ID, tenant_id=TENANT_ID)),
            _Result(one=None),
        ]
    )

    class _FakeRepository:
        def create_item(self, conn, **kwargs):
            return ITEM_ID

    monkeypatch.setattr(seed_pilot_rewards, "RewardsRepository", _FakeRepository)

    outcome = seed_pilot_rewards.seed_reward_item(
        connection,  # type: ignore[arg-type]
        tenant_slug="pilot",
        name="stretch reward" if not expected else "cheap reward",
        points_cost=points_cost,
        fulfilment_cost=decimal.Decimal("0"),
        budget_owner_subject="pilot-login-coordinator",
        funded=True,
    )

    # A stretch reward above the calibration line is still created — the
    # tool never refuses on this basis, only reports it.
    assert outcome.created is True
    assert outcome.satisfies_calibration is expected
