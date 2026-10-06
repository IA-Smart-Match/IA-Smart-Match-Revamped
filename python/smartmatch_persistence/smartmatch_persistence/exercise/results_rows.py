"""What the results routes hand back: six value types, no statements.

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
(ADR-0025 D8): a run is described by profile numbers, counts, and — since
revision 0046 — the names and reason lines its own ranked list showed.

The two pairs of functions at the foot are the JSONB shapes of that snapshot.
They are value conversions, not statements, and they are here rather than in
``results_repository`` so that the instructor's read and the team's read parse
one stored shape with one piece of code.

The types travel through ``smartmatch_api.exercise_dependencies`` to the results
routes: a router that may not import ``smartmatch_persistence`` may not import a
dataclass out of it either, so the door re-exports them and this module gets its
own single ``ignore_imports`` edge.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

__all__ = [
    "InvitedProfile",
    "RefreshCandidate",
    "RefreshCounts",
    "ResultPanel",
    "StoredResultRun",
    "TeamResultsState",
    "WorkspaceRefreshStatus",
    "invited_as_json",
    "invited_from_json",
    "weights_as_json",
    "weights_from_json",
]


@dataclass(frozen=True, slots=True)
class InvitedProfile:
    """One name a run invited, as the team's ranked list showed it then.

    The snapshot ``exercise_result_run.invited_profiles`` stores (issues #271
    and #319). Every field is one a team already reads on its own ranked list;
    there is no place here for a withheld column, a score or a weight
    (ADR-0025 D6, D8).

    Attributes:
        profile_no: The profile's number in the data file.
        display_name: The made-up name.
        major: The major, or ``None`` when the file recorded none.
        class_year: The year, as the data file spells it, or ``None``.
        rank: Position on the invited list, from 1. ``None`` on a run stored
            before revision 0046: its order depended on weights and a view of
            the profiles that can no longer be rebuilt, so none is invented.
        marker: The "how much we know" group at the moment of the run, or
            ``None`` on such a run, for the same reason.
        reason: The one-sentence reason line, or ``None`` on such a run.
    """

    profile_no: int
    display_name: str
    major: str | None = None
    class_year: str | None = None
    rank: int | None = None
    marker: str | None = None
    reason: str | None = None


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
        invited: The invited list as the team's screen showed it at the moment
            of the run, in rank order. Empty for a run stored before revision
            0046 that could not be backfilled.
        setting_weights: The four stated weights the list was built with, or
            ``None`` when they were not recorded.
    """

    event_key: str
    round: int
    setting_name: str | None
    team: ResultPanel
    email_everyone: ResultPanel
    seats_empty: int
    created_at: datetime
    invited: tuple[InvitedProfile, ...] = ()
    setting_weights: Mapping[str, float] | None = None


@dataclass(frozen=True, slots=True)
class TeamResultsState:
    """The three per-team facts design spec §12 and §13 turn on.

    Attributes:
        seed: The team's seed. The simulated-results rule's only per-team input
            (design spec §11). Read here because
            ``workspace_repository.ExerciseWorkspace`` deliberately does not
            carry it; see this module's docstring.

            ``repr=False`` (review round 1, F4). A seed is not a credential —
            possession of it forges nothing and the workspace token is derived
            from the id under a separate secret — but it **is** the whole of
            what makes one team's results that team's, and a default ``repr``
            is what a log line, an assertion message and a debugger transcript
            print. Two teams handed the same seed see the same answers, so a
            seed on a projector or in a shared log is an invitation to compare
            notes with a number instead of with a screen. It is left out of the
            printed form for the reason ``ExerciseWorkspace`` leaves it out of
            the type altogether: reaching it should be deliberate.
        asking_choice: One of ``AskingChoice``'s three values, or ``None`` when
            the team has not chosen. ``None`` is a different fact from any
            choice, which is why the column is nullable.
        refreshed_at: When the one refresh happened, or ``None``.
    """

    seed: int = field(repr=False)
    asking_choice: str | None
    refreshed_at: datetime | None


@dataclass(frozen=True, slots=True)
class RefreshCandidate:
    """One workspace design spec §13's "refresh all" applies to.

    *Chosen and not yet refreshed* — the two conditions the instructor route
    filters on, expressed as the read rather than as a filter somebody applies
    afterwards.

    ``seed`` is ``repr=False`` for :class:`TeamResultsState`'s reason, and more
    sharply here: "refresh all" builds a list of these, so one ``repr`` of that
    list would print every team's seed at once.
    """

    workspace_id: uuid.UUID
    dataset_id: uuid.UUID
    team_number: int
    asking_choice: str
    seed: int = field(repr=False)


@dataclass(frozen=True, slots=True)
class WorkspaceRefreshStatus:
    """One team, as the instructor's every-team refresh has to report it.

    **Every** workspace, not only the ones :class:`RefreshCandidate` selects:
    the report says which teams were refreshed *and which were not, and why*, so
    a team that has not chosen and a team that already refreshed each need a
    row to be named from.

    ``dataset_label`` is the data file's own label, carried so that two "Team
    3"s in a classroom split across two files can be told apart on the report
    without an identifier leaving the server. ``seed`` is ``repr=False`` for
    :class:`RefreshCandidate`'s reason.
    """

    workspace_id: uuid.UUID
    dataset_id: uuid.UUID
    dataset_label: str
    team_number: int
    asking_choice: str | None
    refreshed_at: datetime | None
    seed: int = field(repr=False)


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


# ---------------------------------------------------------------------------
# The stored shape of a run's snapshot (revision 0046)
# ---------------------------------------------------------------------------


def _text_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _int_or_none(value: object) -> int | None:
    # ``bool`` is an ``int`` in Python and is never a rank.
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def invited_as_json(invited: Sequence[InvitedProfile]) -> list[dict[str, object]]:
    """A run's invited list as ``exercise_result_run.invited_profiles`` stores it."""
    return [
        {
            "rank": entry.rank,
            "profile_no": entry.profile_no,
            "display_name": entry.display_name,
            "major": entry.major,
            "class_year": entry.class_year,
            "marker": entry.marker,
            "reason": entry.reason,
        }
        for entry in invited
    ]


def invited_from_json(value: object) -> tuple[InvitedProfile, ...]:
    """``exercise_result_run.invited_profiles`` as values, in the stored order.

    Defensive about the stored shape, for ``_panel_from_json``'s reason: the
    column is JSONB, so a row written by an older version — or backfilled by
    revision 0046 without ``rank``, ``marker`` and ``reason`` — is data this
    version is reading. A missing key reads as ``None``; an entry with no
    usable number or name is dropped rather than shown as a blank; ``NULL``
    reads as nobody.
    """
    if not isinstance(value, list):
        return ()
    found: list[InvitedProfile] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        profile_no = _int_or_none(item.get("profile_no"))
        display_name = _text_or_none(item.get("display_name"))
        if profile_no is None or display_name is None:
            continue
        found.append(
            InvitedProfile(
                profile_no=profile_no,
                display_name=display_name,
                major=_text_or_none(item.get("major")),
                class_year=_text_or_none(item.get("class_year")),
                rank=_int_or_none(item.get("rank")),
                marker=_text_or_none(item.get("marker")),
                reason=_text_or_none(item.get("reason")),
            )
        )
    return tuple(found)


def weights_as_json(weights: Mapping[str, float] | None) -> dict[str, float] | None:
    """A run's stated weights as ``exercise_result_run.setting_weights`` stores them."""
    return None if weights is None else {str(key): float(value) for key, value in weights.items()}


def weights_from_json(value: object) -> Mapping[str, float] | None:
    """``setting_weights`` as a mapping, or ``None`` when nothing usable is stored.

    Non-numeric entries are dropped rather than raised on: the column is JSONB
    and a backfilled row carries whatever the saved setting held.
    """
    if not isinstance(value, Mapping):
        return None
    weights = {
        str(key): float(item)
        for key, item in value.items()
        if isinstance(item, (int, float)) and not isinstance(item, bool)
    }
    return weights or None
