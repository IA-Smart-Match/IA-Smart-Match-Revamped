"""``--feedback-students`` must refuse a size the generator cannot honour.

The flag used to read as a dial: "how many of the feedback cohort to create",
with help text promising that "lowering this is safe". It was not. Phase C's
plan comes from :data:`pilot_dataset_plan.FEEDBACK_SPEAKER_RESPONSE_SHAPE` —
``build_speaker_feedback()`` takes a seed and a shape and nothing else — and
that shape reaches cohort ranks ``1..FEEDBACK_STUDENT_COUNT`` whatever the flag
says. So a run with a partial cohort created that many accounts and then POSTed
a rating as a rank it had never seeded, and the API answered ``401``.

What makes that expensive rather than merely wrong is *when* it happened. Phase
C is last. By the time the first feedback POST is attempted, Phase A has put
three imports through the HTTP path and Phase B has written the roster, the
events, the funnel and the points — and the generator is not re-runnable over
its own half-written tenant, because Phase B resolves rows Phase A would
create. A rejected argument costs nothing; the same argument accepted costs the
whole run and the database it was writing into.

The compose ``dataset`` service is what surfaced this: that stack's
``SMARTMATCH_DEV_PRINCIPALS`` is a fixed four, one per portal, so it passes ``0``
— and ``0`` has to mean "skip the phase", not "seed nobody and post anyway".

Two properties are pinned here, both against the real module:

* ``0`` and the full cohort are accepted, and nothing between them is;
* the refusal happens in argument parsing, before anything is written.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

from tools import pilot_dataset_plan as plan

#: The two arguments a run can honour. Anything else is a run that would fail
#: partway through with a 401 it could have refused for free.
ACCEPTED = (0, plan.FEEDBACK_STUDENT_COUNT)


def _generator() -> ModuleType:
    """Import ``tools/generate_pilot_dataset.py``, which needs ``tools/`` on the path.

    It does a bare ``from pilot_dataset_plan import ...`` rather than
    ``from tools import ...``, so the package import alone is not enough. Copied
    in shape from ``test_pilot_generator_match_run.py``, including undoing the
    insertion so nothing else in the session sees a widened path.
    """
    tools_dir = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, tools_dir)
    try:
        from tools import generate_pilot_dataset

        return generate_pilot_dataset
    finally:
        if sys.path and sys.path[0] == tools_dir:
            sys.path.pop(0)


def _argv(feedback_students: int) -> list[str]:
    """A minimal command line: the two required arguments, plus the one under test."""
    return [
        "--api-base",
        "http://api:8080",
        "--bearer-token",
        "compose-api",
        "--feedback-students",
        str(feedback_students),
    ]


@pytest.mark.parametrize("count", ACCEPTED)
def test_the_whole_cohort_and_none_of_it_are_both_accepted(count: int) -> None:
    args = _generator().parse_args(_argv(count))
    assert args.feedback_students == count


@pytest.mark.parametrize(
    "count",
    [count for count in range(1, plan.FEEDBACK_STUDENT_COUNT)]
    + [plan.FEEDBACK_STUDENT_COUNT + 1, -1],
)
def test_a_cohort_the_plan_would_overrun_is_refused_at_parse_time(count: int) -> None:
    """Refused while refusing it is still free — see this module's docstring."""
    with pytest.raises(SystemExit) as refusal:
        _generator().parse_args(_argv(count))

    # argparse's own exit status for a bad invocation. Asserted so a future
    # `raise ValueError` — which would surface as a traceback rather than a
    # usage message — does not pass this test.
    assert refusal.value.code == 2


def test_the_default_is_the_whole_cohort() -> None:
    """Omitting the flag must not quietly skip the phase."""
    args = _generator().parse_args(["--api-base", "http://api:8080", "--bearer-token", "x"])
    assert args.feedback_students == plan.FEEDBACK_STUDENT_COUNT
