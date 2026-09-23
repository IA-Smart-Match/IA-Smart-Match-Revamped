"""The seeded demo student can afford every ticket the seed leaves open.

:data:`seed_pilot_engagement.REDEMPTION_PLAN` leaves one ``approved`` and one
``requested`` redemption for a coordinator to carry to ``fulfilled`` on the
redemption queue page. Fulfilment re-folds the balance and refuses an overdraw
(``RewardsRepository._debit_for``), so if the balance left after the seeded
fulfilment does not cover both open tickets, the demo's approve -> fulfill path
dead-ends on ``insufficient_balance``. With 12 attendances it did: 1,200 - 300
left 900 against the 1,000-point Headshot.

Pure arithmetic over the module's constants — no database.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# `tools/` on the path, as test_seed_pilot_engagement_subjects.py does: these
# modules are run by compose as bare siblings.
sys.path.insert(0, str(REPO_ROOT / "tools"))

import seed_pilot_engagement as sut  # noqa: E402
from smartmatch_domain.rewards import (  # noqa: E402
    POINTS_PER_VERIFIED_ATTENDANCE,
    RedemptionState,
)


def _cost(item_name: str) -> int:
    return next(item.points_cost for item in sut.WORKSHEET_ITEMS if item.name == item_name)


def _plan_cost(state: RedemptionState) -> int:
    return sum(_cost(step.item_name) for step in sut.REDEMPTION_PLAN if step.final_state is state)


def test_post_fulfilment_balance_covers_every_open_ticket() -> None:
    earned = sut.STUDENT_ATTENDANCES * POINTS_PER_VERIFIED_ATTENDANCE
    remaining = earned - _plan_cost(RedemptionState.FULFILLED)
    still_open = _plan_cost(RedemptionState.APPROVED) + _plan_cost(RedemptionState.REQUESTED)

    assert remaining >= still_open, (
        f"after the seeded fulfilment the student holds {remaining} points but the "
        f"plan leaves {still_open} points of tickets open; fulfilling them all fails"
    )
