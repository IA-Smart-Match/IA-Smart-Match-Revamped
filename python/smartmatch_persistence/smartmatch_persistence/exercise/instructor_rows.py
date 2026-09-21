"""What the instructor page's reads hand back: six value types, no statements.

Split out of ``instructor_repository.py`` in review round 2 (F4), which had
grown past this repository's 800-line ceiling. The cut is along the seam the
module already had: everything here is a frozen value with no query in it, and
what is left there is the statements.

Nothing in this module imports SQLAlchemy or touches a table, and nothing in it
carries a field of ``EXERCISE_WITHHELD_FIELDS`` (ADR-0025 D6) — the reads that
build these values project through ``exercise_profile_public_columns()``, and
none of these types has a place to put the withheld column even if one tried.

The types travel through ``smartmatch_api.exercise_dependencies`` to the
instructor routes: a router that may not import ``smartmatch_persistence`` may
not import a dataclass out of it either, so the door re-exports them and this
module gets its own single ``ignore_imports`` edge.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

__all__ = [
    "InstructorResultRun",
    "InstructorSavedSetting",
    "InstructorWorkspaceRow",
    "RepointOutcome",
    "TeamWorkspaceHandle",
    "WorkingDataset",
]


@dataclass(frozen=True, slots=True)
class TeamWorkspaceHandle:
    """Enough of a workspace for an instructor route to act on it.

    Carries no ``seed`` and no ``workspace_token_hash``, for
    ``workspace_repository.ExerciseWorkspace``'s reason: a value a handler
    already holds is a value one ``model_dump()`` away from a response.
    """

    id: uuid.UUID
    dataset_id: uuid.UUID
    team_number: int


@dataclass(frozen=True, slots=True)
class InstructorWorkspaceRow:
    """One team, as the instructor's list of teams shows it.

    Counts rather than contents: the list answers "which teams are working and
    how far have they got", and a list that carried each team's saved weights
    would put six teams' work on one screen for no one's benefit.
    """

    team_number: int
    dataset_id: uuid.UUID
    dataset_label: str
    created_at: datetime
    saved_setting_count: int
    result_run_count: int
    asking_choice: str | None
    refreshed_at: datetime | None


@dataclass(frozen=True, slots=True)
class WorkingDataset:
    """A data file that at least one team is actually working in.

    Distinct from "the active data file" — the newest upload, which teams join
    only on a fresh entry — because design spec §3 keeps existing workspaces
    where they are until an instructor re-points them. Every instructor action
    that operates on teams is addressed by one of these, never by the newest
    row.
    """

    dataset_id: uuid.UUID
    label: str
    team_count: int


@dataclass(frozen=True, slots=True)
class InstructorSavedSetting:
    """One of a team's saved settings (design spec §6), without its weights.

    The weights are the team's work and the instructor's screen lists what
    exists rather than reproducing it; a later track that needs to *open* a
    setting adds a read that names the column, at which point the exception is
    visible at the call site.
    """

    event_key: str
    name: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class InstructorResultRun:
    """One of a team's result runs (design spec §9/§10), summarised by counts.

    ``seats_empty`` is stored on the row rather than derived, so what is
    reported here is what the team was shown. No score, no percentage, no
    confidence (ADR-0025 D8), and no profile number — a run is described by how
    many, never by who.
    """

    event_key: str
    round: int
    setting_name: str | None
    invited_count: int
    signed_up_count: int
    attended_count: int
    seats_empty: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RepointOutcome:
    """What a re-point did, in the two numbers the instructor's sentence needs."""

    moved: int
    discarded: int
