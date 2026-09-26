"""The results-rule numbers are approved (wave-2 decision D7, closes OQ-CE-03).

Chau approved the team's translation of Ann's words — start 0.04, true fit
+0.40 split half interests / half goal, past attendance +0.10 from one event,
same major +0.04, chance up to 0.10 either way, attend given sign-up 0.75. This
file pins two things that follow from that decision:

* **The numbers did not move.** Approving a set is not changing it; the exact
  values D7 names are pinned here so a later edit shows up as a decision, not
  as a drive-by.
* **Nothing still calls them a placeholder.** The "Chau to confirm" and
  ``PLACEHOLDER (OQ-CE-03)`` markers were how the open question stayed
  greppable. With the question closed, a marker left behind would tell the next
  engineer the numbers are still waiting on somebody, which they are not.

New tests live here rather than in ``test_exercise_results_router.py``, which is
already past the repository's file-length limit.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from smartmatch_domain.exercise import simulation
from smartmatch_domain.exercise.simulation import (
    EXERCISE_SIMULATION_COEFFICIENTS,
    SimulationCoefficients,
    require_coefficients,
)

_REPO = Path(__file__).resolve().parents[2]

#: Every source file the exercise ships: the domain and persistence packages,
#: the API's exercise modules and routers, and the results screen.
_EXERCISE_SOURCES: tuple[Path, ...] = (
    *sorted((_REPO / "python").glob("*/*/exercise/*.py")),
    *sorted((_REPO / "services/api/smartmatch_api").glob("exercise_*.py")),
    *sorted((_REPO / "services/api/smartmatch_api/routers").glob("exercise_*.py")),
    _REPO / "apps/web/legacy-frontend/src/app/pages/exercise/ExerciseResults.tsx",
    _REPO / "apps/web/legacy-frontend/src/app/pages/exercise/ResultPanels.tsx",
)

#: Phrases that said the numbers were still waiting on a decision.
_OPEN_QUESTION_MARKERS: tuple[str, ...] = (
    "PLACEHOLDER (OQ-CE-03",
    "Chau to confirm",
    "OQ-CE-03 stays OPEN",
    "OQ-CE-03 is still OPEN",
    "OQ-CE-03 is open",
    "still to be confirmed",
    "not decided yet",
)

#: D7, exactly as the owner approved it.
_APPROVED = SimulationCoefficients(
    base_signup_rate=0.04,
    true_fit_lift=0.40,
    frequent_attender_lift=0.10,
    same_major_lift=0.04,
    chance_spread=0.20,
    attend_given_signup=0.75,
    frequent_attender_events=1,
    true_interest_share_of_fit=0.5,
)


def _flat(path: Path) -> str:
    """The file's text with comment prefixes and line breaks folded away."""
    raw = path.read_text(encoding="utf-8")
    for prefix in ("#: ", "# ", " * "):
        raw = raw.replace(prefix, " ")
    return " ".join(raw.split())


def test_the_source_list_found_the_exercise_code() -> None:
    """A glob that matched nothing would make every check below pass vacuously."""
    names = {path.name for path in _EXERCISE_SOURCES}
    assert {"simulation.py", "exercise_results.py", "ResultPanels.tsx"} <= names
    assert all(path.is_file() for path in _EXERCISE_SOURCES)


def test_the_shipped_numbers_are_exactly_the_approved_set() -> None:
    assert EXERCISE_SIMULATION_COEFFICIENTS == _APPROVED
    assert require_coefficients() == _APPROVED


@pytest.mark.parametrize("marker", _OPEN_QUESTION_MARKERS)
def test_no_exercise_source_still_calls_the_numbers_open(marker: str) -> None:
    offenders = [
        str(path.relative_to(_REPO)) for path in _EXERCISE_SOURCES if marker in _flat(path)
    ]
    assert offenders == [], f"{marker!r} is left in {offenders}"


def test_the_module_docstring_says_the_numbers_are_approved() -> None:
    """The statement Ann and Dr. Lin receive says who settled the numbers."""
    text = " ".join((simulation.__doc__ or "").split())
    assert "Chau approved" in text
    assert "not confirmed" not in text
    assert "OPEN" not in text
