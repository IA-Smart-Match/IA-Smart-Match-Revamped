"""Design spec §13's card copy: what a refreshed profile's card says.

Split out of ``results_repository.py``, which reached 799 lines — one under this
repository's 800-line ceiling — when the copied card gained a career goal. The
same cut ``results_rows.py`` took, along the seam the module docstring there
describes: what is left in the repository is **statements**, and what comes here
is the one read that is about the *content* of a card rather than about the
shape of a write.

The seam is worth having on its own account. This is the one function in the
package whose purpose is to touch ``hidden_true_interests``, and a reviewer
checking ADR-0025 D6 now has a file to read rather than a method to find.

ADR-0025 D6 — the withheld column
=================================
:func:`copied_cards` goes through
``ExerciseDatasetRepository.load_simulation_profiles``, which stays the **one**
reader of ``hidden_true_interests`` in this package: nothing here writes that
column name into a ``SELECT``. The values it returns have exactly one caller —
``results_repository.apply_refresh`` — which writes them straight into
``exercise_profile_overlay.card_interests`` and hands its own caller counts. They
are not logged, not returned to a router, and not carried on any value that a
response model is built from.

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

    Two mappings rather than one row type: the interests are withheld values and
    the career goals are public ones, and keeping them apart is what stops a
    single ``repr`` of "the copied card" printing both (ADR-0025 D6). Neither
    mapping travels further than the overlay write.

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
