"""What the results routes hand back: five value types, no statements.

Split out of ``results_repository.py``, which had grown past this repository's
800-line ceiling — the same cut ``instructor_rows.py`` took out of
``instructor_repository.py`` in review round 2 (F4), along the same seam:
everything here is a frozen value with no query in it, and what is left there is
the statements.

Nothing in this module imports SQLAlchemy or touches a table, and nothing in it
carries a field of ``EXERCISE_WITHHELD_FIELDS`` (ADR-0025 D6) — design spec
§13's card copy happens inside ``results_repository.apply_refresh`` and never
reaches a value; none of these types has a place to put an interest term even if
one tried. Nothing here carries a score, a percentage or a share either
(ADR-0025 D8): a run is described by profile numbers and counts.

The types travel through ``smartmatch_api.exercise_dependencies`` to the results
routes: a router that may not import ``smartmatch_persistence`` may not import a
dataclass out of it either, so the door re-exports them and this module gets its
own single ``ignore_imports`` edge.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

__all__ = [
    "RefreshCandidate",
    "RefreshCounts",
    "ResultPanel",
    "StoredResultRun",
    "TeamResultsState",
]


@dataclass(frozen=True, slots=True)
class ResultPanel:
    """One run of the simulated-results rule, as profile numbers only.

    The shape design spec §10's panels share — the team's own list and "email
    everyone" are the same three sets over different inputs, so they are the
    same value here rather than two near-identical ones.

    Carries no name, no major, no interest and no number resembling a score
    (ADR-0025 D6 and D8). ``attended ⊆ signed_up ⊆ invited`` holds because
    ``smartmatch_domain.exercise.simulation`` produced it and this type only
    carries it.
    """

    invited_profile_nos: tuple[int, ...]
    signed_up_profile_nos: tuple[int, ...]
    attended_profile_nos: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class StoredResultRun:
    """One row of ``exercise_result_run``, as the API may read it back.

    Carries no ``id``, no ``workspace_id`` and no ``dataset_id``: a team
    addresses its own run through its own cookie, and an identifier on this
    value is an identifier one ``model_dump()`` away from a response.

    Attributes:
        event_key: The event the run was for.
        round: 1 or 2, as ``ck_exercise_result_run_round`` admits.
        setting_name: Which saved weighting the list came from, or ``None``.
            Nullable on purpose (``schema.py``): a setting renamed or deleted
            afterwards must not rewrite what was run.
        team: The team's own invited list through the rule.
        email_everyone: Design spec §10's second panel — everybody, same seed.
        seats_empty: ``60 - 8 - attended`` as it was stored, not as it would be
            recomputed, so what a team keeps is what it was shown.
        created_at: When the row was written.
    """

    event_key: str
    round: int
    setting_name: str | None
    team: ResultPanel
    email_everyone: ResultPanel
    seats_empty: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TeamResultsState:
    """The three per-team facts design spec §12 and §13 turn on.

    Attributes:
        seed: The team's seed. The simulated-results rule's only per-team input
            (design spec §11). Read here because
            ``workspace_repository.ExerciseWorkspace`` deliberately does not
            carry it; see this module's docstring.
        asking_choice: One of ``AskingChoice``'s three values, or ``None`` when
            the team has not chosen. ``None`` is a different fact from any
            choice, which is why the column is nullable.
        refreshed_at: When the one refresh happened, or ``None``.
    """

    seed: int
    asking_choice: str | None
    refreshed_at: datetime | None


@dataclass(frozen=True, slots=True)
class RefreshCandidate:
    """One workspace design spec §13's "refresh all" applies to.

    *Chosen and not yet refreshed* — the two conditions the instructor route
    filters on, expressed as the read rather than as a filter somebody applies
    afterwards.
    """

    workspace_id: uuid.UUID
    dataset_id: uuid.UUID
    team_number: int
    asking_choice: str
    seed: int


@dataclass(frozen=True, slots=True)
class RefreshCounts:
    """What one refresh changed, in three integers (ADR-0025 D8).

    Counts, never contents: which profiles were given a card is a fact the team
    discovers by looking at its own list, and reporting it here would put the
    shape of the withheld column on a response.
    """

    cards_completed: int
    non_responding: int
    topics_added: int
