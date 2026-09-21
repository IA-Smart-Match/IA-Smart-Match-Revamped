"""Design spec §13's card copy: what a refreshed profile's card says.

Split out of ``results_repository.py``, along the seam ``results_rows.py``
already cut: what stays in the repository is **statements**, and what comes here
is the one read that is about the *content* of a card rather than about the
shape of a write.

The reason for the seam is D6, not arithmetic. :func:`copied_cards` is the one
function in this package whose *purpose* is to touch ``hidden_true_interests``,
so a reviewer checking ADR-0025 D6 has a file to read rather than a method to
find inside a repository that answers four other questions.

ADR-0025 D6 — the withheld column
=================================
:func:`copied_cards` goes through
``ExerciseDatasetRepository.load_simulation_profiles``, which stays the **one**
reader of ``hidden_true_interests`` in this package: nothing here writes that
column name into a ``SELECT``. The values it returns have exactly one caller —
``results_repository.apply_refresh`` — which writes them straight into
``exercise_profile_overlay.card_interests``, and hands its own caller counts.
They are not logged.

**They do reach a response, by design.** Design spec §13 (§13 "Profile
refresh"): "a share ... gets a card copied from ``hidden_true_interests``" —
the withheld column is the *source* of a copied card's interests, not a value
this module happens to also touch. Once written to
``exercise_profile_overlay.card_interests``, the value crosses through exactly
one further path: ``team_view_repository.list_team_profiles`` selects
``overlay.c.card_interests`` onto ``TeamProfileRow.overlay_card_interests``
(``team_view_repository.py:153,180``), and
``exercise_matching_models._profile_evidence`` reads it, preferring it over
``stated_interests`` when present, to build the ``ProfileCard`` a matching
response is built from (``routers/exercise_matching_models.py:280-286``). That
is the one transform design spec §13 names, and the withheld value stops being
withheld exactly there, on the team's own copied card — not anywhere else.
Every other module in this package is held to zero readers of the column by
``tests/unit/test_exercise_persistence_tables.py``'s D6 walk.

Nothing here commits, takes a lock, or opens a transaction: it is a read inside
whatever transaction its caller already holds.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from smartmatch_domain.exercise.asking import (
    COPIED_CARD_CAREER_GOAL,
    CopiedCardCareerGoal,
    copied_card_career_goal,
)
from sqlalchemy.orm import Session

from smartmatch_persistence.exercise.dataset_repository import ExerciseDatasetRepository

__all__ = ["copied_cards"]


def copied_cards(
    session: Session,
    *,
    dataset_id: uuid.UUID,
    profile_nos: Sequence[int],
    career_goal_policy: CopiedCardCareerGoal = COPIED_CARD_CAREER_GOAL,
) -> tuple[dict[int, list[str]], dict[int, str]]:
    """The cards design spec §13 copies, for the chosen profiles only.

    **Exactly one intended caller**, ``results_repository.apply_refresh``. It is
    public only because it lives in another module now; a second caller is a
    reason to reread ADR-0025 D6 rather than to import this. The pin in
    ``tests/unit/test_exercise_persistence_tables.py`` is what holds that.

    Two mappings rather than one row type: the interests are withheld values and
    the career goals are public ones, and a single mapping would put both behind
    one name that a later caller could pass around whole. Neither mapping travels
    further than the overlay write. (The two are returned in one tuple, so this
    buys no ``repr`` protection — what keeps a withheld value out of a printed
    form is that nothing holds this result beyond ``apply_refresh``, and that
    ``SimulationProfileRow.hidden_true_interests`` is ``field(repr=False)``.)

    **The career goal follows a named policy.** The owner ruled on 2026-09-21
    that a copied card carries the base row's ``career_goal``, and ``NULL`` only
    when the base has none — PLACEHOLDER (OQ-CE-13), written once in
    ``smartmatch_domain.exercise.asking.copied_card_career_goal`` and switched by
    the one constant this parameter defaults to. ``career_goal`` is a **public**
    column, already on every team's own list, and it is read off the rows this
    function has loaded for the card copy — so no query is added and no reader of
    the withheld column is added either.

    The goals come back **without their ``None`` entries**, so a policy that says
    nothing writes no statement at all and the refresh's statement sequence is
    the one PR #190 shipped. A profile whose base row has no goal is simply
    absent and the column keeps its ``NULL`` default, which is the ruling's
    second half read as a row rather than as a write.

    Args:
        session: Not committed here. Reads only.
        dataset_id: The workspace's dataset.
        profile_nos: The profiles the card share fell on. Repeats are folded.
        career_goal_policy: PLACEHOLDER (OQ-CE-13). Defaults to
            ``asking.COPIED_CARD_CAREER_GOAL``, so a caller never states it.

    Returns:
        ``(interests, career_goals)``, both keyed by profile number. A profile
        number with no row in the data file contributes nothing — which cannot
        happen for a number that came off a ranked list, and is handled anyway
        rather than raising on a screen.
    """
    wanted = set(profile_nos)
    if not wanted:
        return {}, {}
    rows = ExerciseDatasetRepository().load_simulation_profiles(session, dataset_id=dataset_id)
    chosen = [row for row in rows if row.profile_no in wanted]
    interests = {row.profile_no: list(row.hidden_true_interests) for row in chosen}
    career_goals = {
        row.profile_no: goal
        for row in chosen
        if (goal := copied_card_career_goal(row.career_goal, career_goal_policy)) is not None
    }
    return interests, career_goals
