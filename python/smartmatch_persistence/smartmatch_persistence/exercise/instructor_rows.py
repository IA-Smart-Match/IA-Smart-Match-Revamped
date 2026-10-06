"""What the instructor page's reads hand back: seven value types, no statements.

Split out of ``instructor_repository.py`` in review round 2 (F4), which had
grown past this repository's 800-line ceiling. The cut is along the seam the
module already had: everything here is a frozen value with no query in it, and
what is left there is the statements.

Nothing in this module imports SQLAlchemy or touches a table (its one import
from this package is ``results_rows.InvitedProfile``, another value type), and
nothing in it carries a field of ``EXERCISE_WITHHELD_FIELDS`` (ADR-0025 D6) — the reads that
build these values project through ``exercise_profile_public_columns()``, and
none of these types has a place to put the withheld column even if one tried.

The types travel through ``smartmatch_api.exercise_dependencies`` to the
instructor routes: a router that may not import ``smartmatch_persistence`` may
not import a dataclass out of it either, so the door re-exports them and this
module gets its own single ``ignore_imports`` edge.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from smartmatch_persistence.exercise.results_rows import InvitedProfile

__all__ = [
    "InstructorEventRow",
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
class InstructorEventRow:
    """One exercise event of a data file, and whether its results are open.

    CE-INSTRUCTOR-UNLOCK: the unlock panel used to read its events from the
    team route and keep "open" as local state, so it was empty without a team
    cookie and forgot every unlock on reload. ``unlocked`` is the
    ``exercise_result_unlock`` row design spec §9 reads — present and not
    closed — so what the panel shows is what the teams' results route will
    answer.

    ``unlocked_at`` is when results were last opened and ``closed_at`` is when
    they were closed again; both are ``None`` for an event never opened, and
    ``closed_at`` is ``None`` while it is open (D16 amendment, 2026-10-06).

    ``description`` is the data file's short public text for the event, the
    same paragraph the teams read, or ``None`` when the file gave none (#318).
    """

    event_key: str
    name: str
    sequence: int
    unlocked: bool
    unlocked_at: datetime | None = None
    closed_at: datetime | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class InstructorSavedSetting:
    """One of a team's saved settings (design spec §6), with its four weights.

    This is the "later track that needs to *open* a setting" the earlier
    version of this type deferred to: Ann's revisions of 2026-10-02 ask that
    the instructor see each team's "saved settings with the four numbers"
    (issue #319). The weights are the team's own stated input — the one number
    ADR-0025 D8 lets a screen show — and never a normalized or computed one.
    """

    event_key: str
    name: str
    created_at: datetime
    weights: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class InstructorResultRun:
    """One of a team's result runs (design spec §9/§10): counts, and who.

    ``seats_empty`` is stored on the row rather than derived, so what is
    reported here is what the team was shown. No score, no percentage, no
    confidence (ADR-0025 D8).

    Since issue #319 a run is described by *who* as well as by how many: the
    instructor leads the discussion from this page and needs each team's list
    of names. ``invited`` is the snapshot the run stored of its own ranked list
    (revision 0046), so it is what that team's screen showed, and the two
    arrays say which of those names signed up and attended. Still no
    identifier, seed or token, and nothing from a withheld column.

    Attributes:
        invited: The invited list in rank order; empty for a run stored before
            revision 0046 that could not be backfilled.
        signed_up_profile_nos: The profile numbers that signed up.
        attended_profile_nos: The profile numbers that attended.
        setting_weights: The four stated weights the list was built with, or
            ``None`` when they were not recorded.
    """

    event_key: str
    round: int
    setting_name: str | None
    invited_count: int
    signed_up_count: int
    attended_count: int
    seats_empty: int
    created_at: datetime
    invited: tuple[InvitedProfile, ...] = ()
    signed_up_profile_nos: tuple[int, ...] = ()
    attended_profile_nos: tuple[int, ...] = ()
    setting_weights: Mapping[str, float] | None = None


@dataclass(frozen=True, slots=True)
class RepointOutcome:
    """What a re-point did, in the two numbers the instructor's sentence needs."""

    moved: int
    discarded: int
