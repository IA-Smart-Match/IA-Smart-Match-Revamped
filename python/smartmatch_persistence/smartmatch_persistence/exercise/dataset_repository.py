"""Storing one accepted data file: the dataset row, the profiles, the events.

Design spec §3's second half. :mod:`smartmatch_domain.exercise.ingest` decides
whether a file is acceptable and this module writes the result down — the split
is deliberate and is the one the domain package's docstring states: a parser
that could also write would be a parser whose refusals were half-applied.

What this module does not touch
===============================
Only the three tables of a dataset: ``exercise_dataset``, ``exercise_profile``
and ``exercise_event``. Not ``exercise_team_workspace``, and that is design
spec §3's own sentence rather than an omission — *"Existing workspaces keep
pointing at their old dataset until the instructor re-points them; a re-point
resets every team."* Uploading a file therefore changes nothing a team is
looking at. The re-point, with the DELETE-then-UPDATE order that
``exercise/schema.py`` spells out, belongs to the instructor track;
``test_creating_a_dataset_leaves_every_workspace_alone`` is this module's half
of that claim.

Nothing outside the ``exercise_`` family is referenced at all — no tenant, no
``user_account``, no CBA table (ADR-0025 D2). The tables are imported from
``smartmatch_persistence.exercise.schema`` by object rather than looked up by
name on the shared ``MetaData``, so the allow-list test over this package can
see what is referenced without running a query.

One transaction, and who ends it
================================
:meth:`ExerciseDatasetRepository.create_dataset` takes the caller's session and
**commits nothing**, like every other repository in this package. It writes the
dataset row, then the profiles, then the events, and flushes — so a constraint
the file slipped past is raised inside the call rather than at some later
commit. The caller's transaction is what makes the three writes one: a failure
leaves the caller to roll back and nothing is stored, which
``test_a_refused_write_leaves_no_row_behind`` proves by counting rows in all
three tables afterwards.

ADR-0025 D6 — the withheld column, and the one reader of it
===========================================================
``hidden_true_interests`` is written by :meth:`create_dataset` and read by
:meth:`load_simulation_profiles` and by nothing else. Every other read here
projects through ``exercise_profile_public_columns()``, so a response built
from a row this module returned cannot carry the field by accident:
``sa.select(exercise_profile)`` would, which is exactly why that helper exists
and why no method below writes it.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Final

import sqlalchemy as sa
from smartmatch_domain.exercise.ingest import ParsedDataset, ParsedProfile
from sqlalchemy.orm import Session

from smartmatch_persistence.exercise.schema import (
    exercise_dataset,
    exercise_event,
    exercise_profile,
    exercise_profile_public_columns,
)

__all__ = [
    "MAX_SOURCE_FILENAME_CHARACTERS",
    "DatasetSummary",
    "ExerciseDatasetRepository",
    "ExerciseEventRow",
    "ExerciseProfileRow",
    "SimulationProfileRow",
    "sanitise_source_filename",
]

_LOGGER = logging.getLogger(__name__)

#: How much of an uploaded file's name is kept. Long enough to recognise a
#: file, short enough that a name is a label rather than a payload.
MAX_SOURCE_FILENAME_CHARACTERS: Final[int] = 120

#: What an upload is called when its name survives sanitising as nothing at
#: all. ``source_filename`` is ``NOT NULL`` and a blank would fail no
#: constraint while telling a reader nothing, so the absence is spelled out.
_UNNAMED_SOURCE: Final[str] = "(unnamed upload)"


@dataclass(frozen=True, slots=True)
class DatasetSummary:
    """One uploaded data file, as the instructor page lists it.

    Carries no profile and no event — a summary that carried three hundred
    rows would make every reader of a list a reader of the whole file. It
    carries no cell of ``hidden_true_interests`` either, in any form; the
    profile rows it summarises are not on it at all.

    Attributes:
        dataset_id: The dataset.
        label: What the instructor called this upload.
        source_filename: The uploaded file's name, sanitised to a basename.
            Never used as a path by anything.
        uploaded_at: When the row was written.
        row_count: The profile rows stored — design spec §3's "row count",
            which is what ``exercise_dataset.row_count`` holds.
        checksum: SHA-256 of the uploaded bytes, hex.
        invite_limit: §5's cap, 30 unless the instructor changed it.
        license_line: OQ-CE-09's sentence, or ``None`` while Ann has not
            provided one. ``None`` is "she has not said", not "there is none".
        event_count: How many events the file carried. Counted rather than
            stored, because a count with two homes is a count that can
            disagree with itself.
    """

    dataset_id: uuid.UUID
    label: str
    source_filename: str
    uploaded_at: datetime
    row_count: int
    checksum: str
    invite_limit: int
    license_line: str | None
    event_count: int


@dataclass(frozen=True, slots=True)
class ExerciseProfileRow:
    """One profile as anything but the simulation may read it.

    Built from ``exercise_profile_public_columns()``, so the withheld column
    is absent by construction rather than by a caller remembering to drop it.
    """

    profile_no: int
    display_name: str
    major: str | None
    class_year: str | None
    past_event_keys: tuple[str, ...]
    stated_interests: tuple[str, ...] | None
    career_goal: str | None


@dataclass(frozen=True, slots=True)
class ExerciseEventRow:
    """One of the twelve events, in the order the file put them in."""

    event_key: str
    name: str
    topic_tags: tuple[str, ...]
    target_majors: tuple[str, ...]
    is_exercise_event: bool
    sequence: int


@dataclass(frozen=True, slots=True)
class SimulationProfileRow:
    """A profile **including** its withheld true interests (ADR-0025 D6).

    The one type in this package that carries ``hidden_true_interests``, and
    :meth:`ExerciseDatasetRepository.load_simulation_profiles` is the one
    method that builds it. It exists for design spec §11's simulated-results
    rule, which is the only thing the column is for: no factor function reads
    it, no router returns it, and no response model has a field for it.

    A caller that wants to show a profile on a screen wants
    :class:`ExerciseProfileRow` instead — and if a screen ever appears to need
    this type, that is the moment to reread D6 rather than the moment to add a
    field.
    """

    profile_no: int
    display_name: str
    major: str | None
    class_year: str | None
    past_event_keys: tuple[str, ...]
    stated_interests: tuple[str, ...] | None
    career_goal: str | None
    hidden_true_interests: tuple[str, ...]


def sanitise_source_filename(name: str | None) -> str:
    """Reduce an uploaded file's name to a bounded, path-free label.

    The name arrives from a browser and is stored only so a person can tell
    two uploads apart. Directory parts are dropped on both separators, control
    characters are removed, leading dots are stripped so that ``".."`` cannot
    survive as a name, and the result is capped. Nothing in this package joins
    it to a directory, opens it, or serves it as a header — the point of
    sanitising it anyway is that the next person to write such a line inherits
    a value that was already safe.
    """
    candidate = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    printable = "".join(ch for ch in candidate if ch.isprintable())
    trimmed = printable.strip().lstrip(".").strip()
    return trimmed[:MAX_SOURCE_FILENAME_CHARACTERS] or _UNNAMED_SOURCE


def _tuple(value: object) -> tuple[str, ...]:
    """A PostgreSQL text array as a tuple. ``NULL`` reads as empty."""
    return tuple(str(item) for item in value) if isinstance(value, list) else ()


def _optional_tuple(value: object) -> tuple[str, ...] | None:
    """The same, keeping ``NULL`` distinct from ``{}`` (design spec §7)."""
    return None if value is None else _tuple(value)


class ExerciseDatasetRepository:
    """Reads and writes a dataset's three tables. Commits nothing."""

    # -----------------------------------------------------------------------
    # Write
    # -----------------------------------------------------------------------

    def create_dataset(
        self,
        session: Session,
        parsed: ParsedDataset,
        *,
        label: str,
        source_filename: str | None,
    ) -> DatasetSummary:
        """Store one accepted file, in the caller's transaction.

        Args:
            session: The caller's session. Not committed here.
            parsed: What :func:`parse_exercise_file` accepted. A refusal never
                reaches this method — the type says so.
            label: What the instructor called this upload. Its shape is
                enforced by ``ck_exercise_dataset_label_shape`` and by nothing
                here: one definition of "a usable label", in the place that
                cannot be bypassed, rather than two that can disagree.
            source_filename: The browser's file name, sanitised by
                :func:`sanitise_source_filename` before it is stored.

        Returns:
            The dataset as :meth:`get_dataset_summary` would read it back.

        Touches no workspace row. Design spec §3: existing workspaces keep
        pointing at their old dataset until the instructor re-points them.
        """
        dataset_id = uuid.uuid4()
        session.execute(
            sa.insert(exercise_dataset).values(
                id=dataset_id,
                label=label,
                source_filename=sanitise_source_filename(source_filename),
                row_count=parsed.row_count,
                checksum=parsed.checksum,
            )
        )
        if parsed.profiles:
            session.execute(
                sa.insert(exercise_profile),
                [_profile_values(dataset_id, profile) for profile in parsed.profiles],
            )
        if parsed.events:
            session.execute(
                sa.insert(exercise_event),
                [
                    {
                        "dataset_id": dataset_id,
                        "event_key": event.event_key,
                        "name": event.name,
                        "topic_tags": list(event.topic_tags),
                        "target_majors": list(event.target_majors),
                        "is_exercise_event": event.is_exercise_event,
                        "sequence": event.sequence,
                    }
                    for event in parsed.events
                ],
            )
        # Flushed here so that a constraint the parser did not model is raised
        # by this call rather than by a commit somewhere up the stack, where
        # the failure would name no upload.
        session.flush()
        _LOGGER.info(
            "exercise dataset stored: profiles=%d events=%d",
            len(parsed.profiles),
            len(parsed.events),
        )
        summary = self.get_dataset_summary(session, dataset_id=dataset_id)
        if summary is None:  # pragma: no cover - unreachable after a flush
            raise RuntimeError("the dataset row vanished between its insert and its read")
        return summary

    # -----------------------------------------------------------------------
    # Reads
    # -----------------------------------------------------------------------

    def get_dataset_summary(
        self, session: Session, *, dataset_id: uuid.UUID
    ) -> DatasetSummary | None:
        """One dataset, or ``None`` when no such row exists."""
        rows = self._summaries(session, extra=(exercise_dataset.c.id == dataset_id,), limit=1)
        return rows[0] if rows else None

    def list_datasets(self, session: Session, *, limit: int) -> tuple[DatasetSummary, ...]:
        """Every dataset, newest first, capped at ``limit``.

        ``id`` breaks a tie on ``uploaded_at`` so two uploads in the same
        instant never swap places between two identical reads, which is also
        what makes a truncation cut at a stable point.
        """
        return self._summaries(session, extra=(), limit=limit)

    def list_profiles(
        self, session: Session, *, dataset_id: uuid.UUID, limit: int
    ) -> tuple[ExerciseProfileRow, ...]:
        """A dataset's profiles by number, **without** the withheld column.

        Selected through ``exercise_profile_public_columns()``. This is the
        read for anything that will reach a screen.
        """
        statement = (
            sa.select(*exercise_profile_public_columns())
            .where(exercise_profile.c.dataset_id == dataset_id)
            .order_by(exercise_profile.c.profile_no)
            .limit(limit)
        )
        return tuple(
            ExerciseProfileRow(
                profile_no=row.profile_no,
                display_name=row.display_name,
                major=row.major,
                class_year=row.class_year,
                past_event_keys=_tuple(row.past_event_keys),
                stated_interests=_optional_tuple(row.stated_interests),
                career_goal=row.career_goal,
            )
            for row in session.execute(statement).all()
        )

    def list_events(
        self, session: Session, *, dataset_id: uuid.UUID
    ) -> tuple[ExerciseEventRow, ...]:
        """A dataset's events in file order: ten past, then the two rounds."""
        statement = (
            sa.select(
                exercise_event.c.event_key,
                exercise_event.c.name,
                exercise_event.c.topic_tags,
                exercise_event.c.target_majors,
                exercise_event.c.is_exercise_event,
                exercise_event.c.sequence,
            )
            .where(exercise_event.c.dataset_id == dataset_id)
            .order_by(exercise_event.c.sequence)
        )
        return tuple(
            ExerciseEventRow(
                event_key=row.event_key,
                name=row.name,
                topic_tags=_tuple(row.topic_tags),
                target_majors=_tuple(row.target_majors),
                is_exercise_event=row.is_exercise_event,
                sequence=row.sequence,
            )
            for row in session.execute(statement).all()
        )

    def load_simulation_profiles(
        self, session: Session, *, dataset_id: uuid.UUID
    ) -> tuple[SimulationProfileRow, ...]:
        """The **only** read in this package that selects the withheld column.

        ADR-0025 D6: ``hidden_true_interests`` is stored on the profile row and
        is read by the simulated-results rule of design spec §11 and by nothing
        else. The column is named explicitly below so that the exception is
        visible at the call site rather than implied by a ``select(table)``,
        and the method is named for its one caller so that a second caller has
        to explain itself.
        """
        statement = (
            sa.select(
                exercise_profile.c.profile_no,
                exercise_profile.c.display_name,
                exercise_profile.c.major,
                exercise_profile.c.class_year,
                exercise_profile.c.past_event_keys,
                exercise_profile.c.stated_interests,
                exercise_profile.c.career_goal,
                exercise_profile.c.hidden_true_interests,
            )
            .where(exercise_profile.c.dataset_id == dataset_id)
            .order_by(exercise_profile.c.profile_no)
        )
        return tuple(
            SimulationProfileRow(
                profile_no=row.profile_no,
                display_name=row.display_name,
                major=row.major,
                class_year=row.class_year,
                past_event_keys=_tuple(row.past_event_keys),
                stated_interests=_optional_tuple(row.stated_interests),
                career_goal=row.career_goal,
                hidden_true_interests=_tuple(row.hidden_true_interests),
            )
            for row in session.execute(statement).all()
        )

    # -----------------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------------

    def _summaries(
        self,
        session: Session,
        *,
        extra: tuple[sa.ColumnElement[bool], ...],
        limit: int,
    ) -> tuple[DatasetSummary, ...]:
        """The one query behind both dataset reads, with the event count on it."""
        events = (
            sa.select(sa.func.count())
            .select_from(exercise_event)
            .where(exercise_event.c.dataset_id == exercise_dataset.c.id)
            .scalar_subquery()
            .label("event_count")
        )
        statement = (
            sa.select(
                exercise_dataset.c.id,
                exercise_dataset.c.label,
                exercise_dataset.c.source_filename,
                exercise_dataset.c.uploaded_at,
                exercise_dataset.c.row_count,
                exercise_dataset.c.checksum,
                exercise_dataset.c.invite_limit,
                exercise_dataset.c.license_line,
                events,
            )
            .where(*extra)
            .order_by(exercise_dataset.c.uploaded_at.desc(), exercise_dataset.c.id)
            .limit(limit)
        )
        return tuple(
            DatasetSummary(
                dataset_id=row.id,
                label=row.label,
                source_filename=row.source_filename,
                uploaded_at=row.uploaded_at,
                row_count=row.row_count,
                checksum=row.checksum,
                invite_limit=row.invite_limit,
                license_line=row.license_line,
                event_count=row.event_count,
            )
            for row in session.execute(statement).all()
        )


def _profile_values(dataset_id: uuid.UUID, profile: ParsedProfile) -> dict[str, object]:
    """One profile as a row. ``stated_interests`` keeps ``None`` distinct from ``{}``.

    Design spec §7's three states: ``NULL`` is "no card on file" and ``{}`` is
    "a card with nothing on it". Collapsing them here would report an empty
    card as an absent one on every screen that reads the marker.
    """
    return {
        "dataset_id": dataset_id,
        "profile_no": profile.profile_no,
        "display_name": profile.display_name,
        "major": profile.major,
        "class_year": profile.class_year,
        "past_event_keys": list(profile.past_event_keys),
        "stated_interests": (
            None if profile.stated_interests is None else list(profile.stated_interests)
        ),
        "career_goal": profile.career_goal,
        "hidden_true_interests": list(profile.hidden_true_interests),
    }
