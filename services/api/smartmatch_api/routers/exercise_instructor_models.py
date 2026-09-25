"""The instructor page's request and response models, and the five view builders.

Split out of ``exercise_instructor.py`` so neither file is a long one, on
``routers/manual_events_models.py``'s precedent. It holds **no route, no
router, and no dependency**: everything here is a shape and a conversion, which
is what makes "what may a response carry" a question with one file's worth of
answer.

What a response may never carry (ADR-0025 D6, D8)
=================================================

No ``hidden_true_interests`` in any field, no workspace id, token, token hash
or seed, and no score, percentage or confidence — a result run is described by
how many were invited, signed up and attended, never by a number about how
well a team did. ``tests/unit/test_exercise_instructor_router.py`` walks every
model in the router's namespace and refuses all three classes by name.

Why every view is built field by field
======================================

Not one ``model_validate``: a from-attributes conversion publishes whatever a
later track adds to the repository dataclass it reads from, and the dataclasses
behind these views are the ones that grow. Naming each field means a new column
reaching a screen is a line somebody wrote.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from pydantic import BaseModel, ConfigDict, Field
from smartmatch_domain.exercise.ingest import ParsedDataset

from smartmatch_api.exercise_dependencies import (
    DatasetSummary,
    InstructorEventRow,
    InstructorResultRun,
    InstructorSavedSetting,
    InstructorWorkspaceRow,
)

#: The longest passcode the login will read. A bound rather than a policy: the
#: value is a human-shared string (OQ-CE-07), and the cost of *not* bounding it
#: is that every oversized body reaching the route buys a key derivation over
#: however many kilobytes somebody cared to send. Refused by the model, before
#: the handler and before the KDF.
MAX_PASSCODE_CHARACTERS: Final[int] = 256

__all__ = [
    "MAX_PASSCODE_CHARACTERS",
    "TEAMS_HAVE_NOT_MOVED",
    "DatasetView",
    "IngestReportView",
    "InstructorEventView",
    "InstructorEventsView",
    "InstructorLoginRequest",
    "InstructorSessionView",
    "InviteLimitRequest",
    "RepointView",
    "ResultRunView",
    "SavedSettingView",
    "TeamDetailView",
    "TeamListView",
    "TeamSummaryView",
    "UnlockView",
    "UploadedDatasetView",
    "dataset_view",
    "event_view",
    "report_view",
    "run_view",
    "setting_view",
    "team_view",
]


class InstructorLoginRequest(BaseModel):
    """The login screen's whole input."""

    model_config = ConfigDict(extra="forbid")

    passcode: str = Field(
        max_length=MAX_PASSCODE_CHARACTERS,
        description=(
            "The instructor passcode for this deployment (OQ-CE-07: one "
            "environment variable, shared out of band). Never logged, never "
            "echoed, and never compared with `==`."
        ),
    )


class InstructorSessionView(BaseModel):
    """What a successful login says. Deliberately almost nothing.

    There is no account to name, no role to report and no expiry to publish:
    the expiry is inside the signed cookie and saying it again here would be a
    second copy to disagree with the first.
    """

    model_config = ConfigDict(extra="forbid")

    signed_in: bool = Field(description="True. The screen switches on this and nothing else.")


class InviteLimitRequest(BaseModel):
    """Design spec §5: how many names a ranked list may hold."""

    model_config = ConfigDict(extra="forbid")

    invite_limit: int = Field(
        description=(
            "The cap on a ranked list for this data file. Thirty by default — "
            "Ann's stated number, held in the column's server default rather "
            "than repeated here."
        ),
    )


class DatasetView(BaseModel):
    """One uploaded data file, as the instructor page lists it.

    Every field is something the instructor's own screen shows. No profile and
    no event row is on it, so a list of files is not a reader of every file.
    """

    model_config = ConfigDict(extra="forbid")

    dataset_id: uuid.UUID = Field(description="The data file, for the re-point and limit routes.")
    label: str = Field(description="What the instructor called this upload.")
    source_filename: str = Field(description="The uploaded file's name, reduced to a basename.")
    uploaded_at: datetime = Field(description="When it was stored.")
    row_count: int = Field(description="How many made-up profiles it carried.")
    event_count: int = Field(description="How many events it carried.")
    checksum: str = Field(description="SHA-256 of the uploaded bytes, hex. Two uploads compare.")
    invite_limit: int = Field(description="Design spec §5's cap for this file.")
    license_line: str | None = Field(
        description=(
            "OQ-CE-09's sentence, or null while Ann has not provided one. Null "
            "is 'she has not said', not 'there is none'."
        ),
    )


class IngestReportView(BaseModel):
    """What an accepted file turned out to contain (design spec §3).

    Counts, and which of the four years the file used. No cell of either
    withheld column appears in any form.
    """

    model_config = ConfigDict(extra="forbid")

    profile_count: int
    event_count: int
    exercise_event_count: int
    distinct_class_years: tuple[str, ...] = Field(
        description="Which of the four years this file used, youngest first."
    )
    profiles_without_card: int
    distinct_stated_interest_terms: int
    distinct_topic_tag_terms: int
    events_without_topic_tags: int
    major_only: int
    major_plus_events: int
    completed_card: int


#: What an upload says about the teams, in one plain sentence. Design spec §3:
#: *existing workspaces keep pointing at their old dataset until the instructor
#: re-points them.* The rule is right and it is not what an instructor expects
#: from a button labelled "upload the data file", so the response says it out
#: loud rather than leaving her to notice that nothing changed.
TEAMS_HAVE_NOT_MOVED: Final[str] = (
    "The teams are still working in the data file they entered on; "
    "re-point them to move them to this one."
)


class UploadedDatasetView(BaseModel):
    """The answer to an upload: the stored file, what was in it, and one warning."""

    model_config = ConfigDict(extra="forbid")

    dataset: DatasetView
    report: IngestReportView
    notice: str = Field(
        description=(
            "One plain sentence saying that uploading a file moves no team "
            "(design spec §3). Constant; the screen shows it beside the "
            "re-point button."
        )
    )


class TeamSummaryView(BaseModel):
    """One team, in the instructor's list of teams.

    Carries the **data file this team is actually on**, not the newest upload.
    Design spec §3 keeps a team where it is until an instructor re-points it,
    so a list that named one file for every team would be wrong the moment a
    file was uploaded — which is exactly the defect this field fixes.
    """

    model_config = ConfigDict(extra="forbid")

    team_number: int
    dataset_id: uuid.UUID = Field(
        description=(
            "The data file this team is working in. Pass it to the unlock, "
            "reset and detail routes to act on this team's file rather than "
            "letting the server guess."
        )
    )
    dataset_label: str
    created_at: datetime = Field(description="When this team first entered its number.")
    saved_setting_count: int
    result_run_count: int
    asking_choice: str | None = Field(
        description="Design spec §12's choice, or null when the team has not chosen."
    )
    refreshed_at: datetime | None = Field(
        description="Design spec §13's one refresh, or null when it has not happened."
    )


class TeamListView(BaseModel):
    """Every team that exists, each with the data file it is on.

    Not "every team in the active data file". Uploading a file moves no team
    (design spec §3), so scoping this list to the newest upload emptied the
    instructor's own screen the moment she used the upload button.
    """

    model_config = ConfigDict(extra="forbid")

    teams: tuple[TeamSummaryView, ...]
    active_dataset_label: str | None = Field(
        description=(
            "The data file a team entering a number right now would join, or "
            "null when nothing has been uploaded. It is *not* necessarily the "
            "file the teams below are on — only a re-point moves them."
        )
    )


class SavedSettingView(BaseModel):
    """One saved setting, by name. The weights are the team's own work."""

    model_config = ConfigDict(extra="forbid")

    event_key: str
    name: str
    created_at: datetime


class ResultRunView(BaseModel):
    """One result run, by counts (ADR-0025 D8: no number about how well)."""

    model_config = ConfigDict(extra="forbid")

    event_key: str
    round: int
    setting_name: str | None
    invited_count: int
    signed_up_count: int
    attended_count: int
    seats_empty: int
    created_at: datetime


class TeamDetailView(BaseModel):
    """One team's saved settings and result runs, read-only.

    ``result_runs`` is empty until the results track lands, and that is a real
    answer rather than a gap: design spec §9's route does not exist yet, so no
    team can have run results.
    """

    model_config = ConfigDict(extra="forbid")

    team_number: int
    saved_settings: tuple[SavedSettingView, ...]
    result_runs: tuple[ResultRunView, ...]


class InstructorEventView(BaseModel):
    """One event the teams run, and whether its results are open (design spec §9)."""

    model_config = ConfigDict(extra="forbid")

    event_key: str
    name: str
    unlocked: bool = Field(
        description="Whether the instructor has opened results for this event in this data file."
    )


class InstructorEventsView(BaseModel):
    """The unlock panel's list: the teams' data file and its exercise events.

    ``dataset_id`` is the file the unlock will write to when it is passed back,
    so the list and the button cannot address two different files.
    """

    model_config = ConfigDict(extra="forbid")

    dataset_id: uuid.UUID
    dataset_label: str
    events: tuple[InstructorEventView, ...]


class UnlockView(BaseModel):
    """Design spec §9: results for one event are now open to the teams."""

    model_config = ConfigDict(extra="forbid")

    event_key: str
    unlocked: bool = Field(description="True. A second press says the same thing.")


class RepointView(BaseModel):
    """What a re-point did (design spec §3: it resets every team)."""

    model_config = ConfigDict(extra="forbid")

    dataset_label: str
    teams_moved: int
    teams_discarded: int = Field(
        description=(
            "Stale workspaces dropped because the team already had one on this "
            "data file. Their work was already unreachable; a re-point resets "
            "every team in any case."
        )
    )


def dataset_view(summary: DatasetSummary) -> DatasetView:
    """The one place a dataset becomes a response.

    Field by field rather than by ``model_validate``, for
    ``exercise_workspace._view``'s reason: a from-attributes conversion
    publishes whatever a later track adds to the dataclass.
    """
    return DatasetView(
        dataset_id=summary.dataset_id,
        label=summary.label,
        source_filename=summary.source_filename,
        uploaded_at=summary.uploaded_at,
        row_count=summary.row_count,
        event_count=summary.event_count,
        checksum=summary.checksum,
        invite_limit=summary.invite_limit,
        license_line=summary.license_line,
    )


def report_view(parsed: ParsedDataset) -> IngestReportView:
    """The accepted file's counts. Named field by field, so a field added to
    the domain report is a deliberate addition here rather than an automatic
    disclosure."""
    report = parsed.report
    return IngestReportView(
        profile_count=report.profile_count,
        event_count=report.event_count,
        exercise_event_count=report.exercise_event_count,
        distinct_class_years=report.distinct_class_years,
        profiles_without_card=report.profiles_without_card,
        distinct_stated_interest_terms=report.distinct_stated_interest_terms,
        distinct_topic_tag_terms=report.distinct_topic_tag_terms,
        events_without_topic_tags=report.events_without_topic_tags,
        major_only=report.markers.major_only,
        major_plus_events=report.markers.major_plus_events,
        completed_card=report.markers.completed_card,
    )


def team_view(row: InstructorWorkspaceRow) -> TeamSummaryView:
    return TeamSummaryView(
        team_number=row.team_number,
        dataset_id=row.dataset_id,
        dataset_label=row.dataset_label,
        created_at=row.created_at,
        saved_setting_count=row.saved_setting_count,
        result_run_count=row.result_run_count,
        asking_choice=row.asking_choice,
        refreshed_at=row.refreshed_at,
    )


def event_view(row: InstructorEventRow) -> InstructorEventView:
    return InstructorEventView(event_key=row.event_key, name=row.name, unlocked=row.unlocked)


def setting_view(row: InstructorSavedSetting) -> SavedSettingView:
    return SavedSettingView(event_key=row.event_key, name=row.name, created_at=row.created_at)


def run_view(row: InstructorResultRun) -> ResultRunView:
    return ResultRunView(
        event_key=row.event_key,
        round=row.round,
        setting_name=row.setting_name,
        invited_count=row.invited_count,
        signed_up_count=row.signed_up_count,
        attended_count=row.attended_count,
        seats_empty=row.seats_empty,
        created_at=row.created_at,
    )
