"""The instructor page (design spec §14, ADR-0025 D1/D2/D6/D8).

One passcode from the environment opens one page. Behind it: upload a data
file, set the invite limit, unlock results per event, see what the six teams
have done, reset one team, and re-point every team at a data file. No account,
no role, no principal, no CBA table — the instructor is not a *who* here, and
the passcode is a door rather than an identity.

One router, and why the gate is structural
==========================================

:data:`router` carries every instructor route that runs *inside* a session and
takes :func:`~smartmatch_api.exercise_dependencies.require_instructor_session`
as a **router-level** dependency. Written that way rather than per handler
because a gate that is a parameter is a gate that comes off when somebody edits
a signature, and the failure is silent: an open instructor route looks exactly
like a working one.

The two routes that must answer *before* there is a session — present the
passcode, clear the cookie — are not here at all: they are
``routers/exercise_instructor_session.py``, the one instructor router with no
session dependency on it. They used to be a second, ungated ``login_router`` in
this file, and the move is what brought this module back under the
repository's 800-line ceiling. It also made the arrangement harder to undo by
accident, which is the better half of the reason: a route added to *this* file
is gated by existing, and un-gating one now means moving it to a file whose
whole subject is the unauthenticated door.

It is a bare module-level assignment, for ``exercise_public.router``'s reason:
the route ledger in ``tests/authz/test_policy_matrix.py`` reads router prefixes
out of the AST and matches ``name = APIRouter(...)``.

The upload is a raw body, not multipart — an owner question
===========================================================

Design spec §3 says *multipart, one file*. FastAPI cannot parse a multipart
body without ``python-multipart``, which this repository does not have: adding
it is a new runtime dependency and a regeneration of the hash-pinned
requirement locks (``requirements/runtime.txt``, compiled ``--no-index``) for
one route on one screen.

So the upload is the same bytes by a simpler road: Ann's ``.xlsx`` **is** the
request body (OQ-CE-05, closed 2026-09-24), with the instructor's label and the
browser's file name as query parameters. The owner confirmed on 2026-09-21
that the body stays raw bytes. The ingest core takes bytes and neither knows nor
cares how they arrived, so switching to multipart later is a change to this
handler's signature and to nothing else. Recorded on this track's pull request
as an owner decision rather than made quietly: if the answer is "take the
dependency", CE-MOUNT gets a file input and this handler gets three lines
shorter.

What a response may carry, and what it may never
================================================

* **No** ``hidden_true_interests``, in any field, any log line, any exception
  text (ADR-0025 D6). Nothing in this module reads the column and nothing it
  calls returns it — the instructor repository's reads are counts and names.

  The rule reaches further than the fields, and it caught one line in this
  module: a **handler docstring becomes a route's ``description`` in the
  exported contract**, so naming the column while explaining why ``refresh-all``
  is switched off would have published the name D6 forbids publishing anywhere.
  Handler docstrings here say *the withheld column*; this module docstring is
  not served, which is why it may say it plainly.
* **No** score, percentage or confidence (ADR-0025 D8). A team's result run is
  described by how many were invited, signed up and attended, never by a
  number about how well it did. The instructor's screen is on the same
  projector as the teams'.
* **No** workspace id, token, token hash or seed, for
  ``exercise_workspace.py``'s reason: the cookie token is derived from the id,
  so an id in a response body is one secret away from being a session.
* **No** raw driver text. A refused write becomes one plain sentence; which
  constraint refused it goes to the server log with the dataset id, and no row
  value goes anywhere.

CSRF
====

Every state-changing route here requires ``X-Exercise-Request``, as the team
routes do. The login route's rate limit — a **PLACEHOLDER (OQ-CE-06)** — went
with the login route, to ``routers/exercise_instructor_session.py``.
"""

from __future__ import annotations

import logging
import uuid
from enum import Enum
from typing import Annotated, Final

from fastapi import APIRouter, Body, Depends, Query, status
from smartmatch_domain.exercise import EXERCISE_TEAM_NUMBERS
from smartmatch_domain.exercise.ingest import IngestRefusal, parse_exercise_file
from smartmatch_domain.exercise.workbook import XLSX_MEDIA_TYPE

from smartmatch_api.exercise_dependencies import (
    MAX_INVITE_LIMIT,
    MIN_INVITE_LIMIT,
    DatasetRepository,
    ExerciseDatasetLabelError,
    ExerciseDatasetWriteError,
    ExerciseSession,
    ExerciseWriteRefused,
    InstructorRepository,
    MaybeActiveDataset,
    TeamWorkspaceHandle,
    WorkingDataset,
    WorkspaceRepository,
    require_exercise_request_header,
    require_instructor_session,
)
from smartmatch_api.exercise_errors import ExerciseError
from smartmatch_api.routers.exercise_instructor_models import (
    TEAMS_HAVE_NOT_MOVED,
    DatasetView,
    InviteLimitRequest,
    RepointView,
    TeamDetailView,
    TeamListView,
    TeamSummaryView,
    UnlockView,
    UploadedDatasetView,
    dataset_view,
    report_view,
    run_view,
    setting_view,
    team_view,
)

_LOGGER = logging.getLogger(__name__)

#: The tag this router carries. The *prefix* is deliberately written out as a
#: literal on the ``APIRouter(...)`` below rather than hoisted into a constant
#: beside this one: the route ledger in ``tests/authz/test_policy_matrix.py``
#: reads prefixes out of the AST and only sees ``prefix="…"``, so a named
#: constant would make every route in this module appear at ``/datasets``,
#: ``/workspaces`` and so on — paths that match no ledger row and no real route.
_TAGS: Final[list[str | Enum]] = ["class-exercise"]

#: Applied to every state-changing route in this module, and declared once so
#: they cannot drift.
_STATE_CHANGING = [Depends(require_exercise_request_header)]

#: Every instructor route that runs inside a session. The session dependency is
#: on the *router*, so a route added below is gated by existing rather than by
#: remembering. Login and logout are ``exercise_instructor_session.router``.
router = APIRouter(
    prefix="/v1/exercise/instructor",
    tags=_TAGS,
    dependencies=[Depends(require_instructor_session)],
)


# ---------------------------------------------------------------------------
# Data files
# ---------------------------------------------------------------------------


#: How many uploads the list route returns. Bounded because an instructor page
#: showing every file ever uploaded is a page nobody scrolls.
_DATASET_LIST_LIMIT: Final[int] = 50


@router.get(
    "/datasets",
    response_model=tuple[DatasetView, ...],
    summary="Every uploaded data file, newest first",
)
def list_datasets(
    session: ExerciseSession,
    repository: DatasetRepository,
) -> tuple[DatasetView, ...]:
    """What the instructor may re-point the teams at."""
    return tuple(
        dataset_view(summary)
        for summary in repository.list_datasets(session, limit=_DATASET_LIST_LIMIT)
    )


@router.post(
    "/datasets",
    response_model=UploadedDatasetView,
    status_code=status.HTTP_201_CREATED,
    dependencies=_STATE_CHANGING,
    summary="Upload a data file (design spec §3)",
)
def upload_dataset(
    session: ExerciseSession,
    repository: DatasetRepository,
    content: Annotated[bytes, Body(media_type=XLSX_MEDIA_TYPE)],
    label: Annotated[str, Query(description="What to call this upload on the instructor page.")],
    source_filename: Annotated[
        str | None,
        Query(description="The browser's file name. Stored as a label; never opened as a path."),
    ] = None,
) -> UploadedDatasetView:
    """Read one workbook, validate it, store it — synchronously, in one transaction.

    Design spec §3: the instructor needs an answer on the spot, so the job and
    review pipeline behind ``routers/imports.py`` is not used and neither is
    its principal. See the module docstring for why the bytes arrive as a body
    rather than as a multipart part.

    The body is Ann's ``.xlsx`` as she sent it. Every refusal is one plain
    sentence from :func:`~smartmatch_domain.exercise.ingest.parse_exercise_file`,
    in §3's order, and the first failure is the whole answer; a missing sheet
    or column names the sheet and the column.

    **Touches no workspace row.** Design spec §3: existing workspaces keep
    pointing at their old dataset until the instructor re-points them. Uploading
    a file therefore changes nothing a team is currently looking at.

    Raises:
        ExerciseError: 422 when the file is refused or the label is unusable,
            409 when the database refuses the write, 403 without the
            ``X-Exercise-Request`` header, 401 without a session.
    """
    parsed = parse_exercise_file(content)
    if isinstance(parsed, IngestRefusal):
        raise ExerciseError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code=f"exercise_ingest_{parsed.code}",
            message=parsed.message,
        )
    try:
        summary = repository.create_dataset(
            session, parsed, label=label, source_filename=source_filename
        )
    except ExerciseDatasetLabelError as error:
        raise ExerciseError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="exercise_dataset_label_refused",
            message=str(error),
        ) from error
    except ExerciseDatasetWriteError as error:
        raise ExerciseError(
            status_code=status.HTTP_409_CONFLICT,
            code="exercise_dataset_write_refused",
            message=str(error),
        ) from error
    session.commit()
    return UploadedDatasetView(
        dataset=dataset_view(summary),
        report=report_view(parsed),
        notice=TEAMS_HAVE_NOT_MOVED,
    )


@router.patch(
    "/datasets/{dataset_id}",
    response_model=DatasetView,
    dependencies=_STATE_CHANGING,
    summary="Set the invite limit for a data file (design spec §5)",
)
def set_invite_limit(
    dataset_id: uuid.UUID,
    payload: InviteLimitRequest,
    session: ExerciseSession,
    repository: DatasetRepository,
    instructor: InstructorRepository,
) -> DatasetView:
    """Change how many names a ranked list may hold.

    The bound is checked here rather than by a pydantic validator, for
    ``exercise_workspace.enter_team_workspace``'s reason:
    ``errors._describe_validation_error`` replaces a validator's message with a
    generic one, because a validator-authored message may interpolate the value
    it rejected. The rule is right and this route is not an exception to it.

    Raises:
        ExerciseError: 422 when the limit is outside its bounds, 404 when no
            such data file exists, 409 when the write is refused.
    """
    if not MIN_INVITE_LIMIT <= payload.invite_limit <= MAX_INVITE_LIMIT:
        raise ExerciseError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="exercise_invite_limit_out_of_range",
            message=(f"Pick an invite limit between {MIN_INVITE_LIMIT} and {MAX_INVITE_LIMIT}."),
        )
    try:
        changed = instructor.set_invite_limit(
            session, dataset_id=dataset_id, invite_limit=payload.invite_limit
        )
    except ExerciseWriteRefused as error:
        raise ExerciseError(
            status_code=status.HTTP_409_CONFLICT,
            code="exercise_invite_limit_write_refused",
            message=str(error),
        ) from error
    if not changed:
        raise _no_such_dataset()
    session.commit()
    summary = repository.get_dataset_summary(session, dataset_id=dataset_id)
    if summary is None:  # pragma: no cover - the update above just matched it
        raise _no_such_dataset()
    return dataset_view(summary)


@router.post(
    "/datasets/{dataset_id}/repoint",
    response_model=RepointView,
    dependencies=_STATE_CHANGING,
    summary="Point every team at this data file, resetting them all",
)
def repoint_workspaces(
    dataset_id: uuid.UUID,
    session: ExerciseSession,
    repository: DatasetRepository,
    instructor: InstructorRepository,
) -> RepointView:
    """Design spec §3's re-point: *a re-point resets every team*.

    Destructive and deliberately so: every team's overlay, saved settings and
    result runs are deleted and its seed regenerated. The delete happens
    **before** each ``dataset_id`` is updated, in this one transaction, because
    the composite foreign keys are ``ON DELETE CASCADE`` and not
    ``ON UPDATE CASCADE`` — the repository's docstring and
    ``exercise/schema.py``'s comment state it at length, and
    ``tests/integration/test_exercise_instructor_persistence.py`` proves the
    order rather than trusting it.

    A moved workspace keeps its id and therefore its cookie. A team that had
    *already* entered on the target file keeps that workspace and its stale one
    is discarded.

    Raises:
        ExerciseError: 404 when no such data file exists, 409 when the write is
            refused.
    """
    summary = repository.get_dataset_summary(session, dataset_id=dataset_id)
    if summary is None:
        raise _no_such_dataset()
    try:
        outcome = instructor.repoint_workspaces(session, dataset_id=dataset_id)
    except ExerciseWriteRefused as error:
        raise ExerciseError(
            status_code=status.HTTP_409_CONFLICT,
            code="exercise_repoint_write_refused",
            message=str(error),
        ) from error
    session.commit()
    return RepointView(
        dataset_label=summary.label,
        teams_moved=outcome.moved,
        teams_discarded=outcome.discarded,
    )


def _no_such_dataset() -> ExerciseError:
    """One sentence for a data file that is not there."""
    return ExerciseError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="exercise_dataset_unknown",
        message="That data file is not on the server.",
    )


# ---------------------------------------------------------------------------
# Results lock
# ---------------------------------------------------------------------------


@router.post(
    "/events/{event_key}/unlock",
    response_model=UnlockView,
    dependencies=_STATE_CHANGING,
    summary="Open results for one event (design spec §9)",
)
def unlock_results(
    event_key: str,
    session: ExerciseSession,
    instructor: InstructorRepository,
    dataset_id: _DatasetChoice = None,
) -> UnlockView:
    """Write the ``exercise_result_unlock`` row design spec §9 reads.

    **Idempotent.** A second press inserts nothing, moves no ``unlocked_at``,
    and answers the same sentence — an instructor pressing a button twice in a
    classroom is the expected case, not the exceptional one.

    **Scoped to the data file the teams are on**, resolved by
    :func:`_teams_dataset`, and this is a correction rather than a preference.
    It used to be scoped to the *active* file — the newest upload — and since
    design spec §3 has an upload move nobody, one upload was enough to make
    every unlock write a row keyed to a file no team was in. The button
    reported success; the teams stayed locked out; nothing in the system was
    wrong enough to complain. A data file with no teams in it is now refused
    with a sentence instead.

    Raises:
        ExerciseError: 404 when the event is not in that data file, 409 when no
            data file can be resolved or the write is refused.
    """
    dataset = _teams_dataset(instructor, session, requested=dataset_id)
    if not instructor.event_exists(session, dataset_id=dataset.dataset_id, event_key=event_key):
        raise ExerciseError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="exercise_event_unknown",
            message="That event is not in the data file the teams are working in.",
        )
    try:
        newly = instructor.unlock_results(
            session, dataset_id=dataset.dataset_id, event_key=event_key
        )
    except ExerciseWriteRefused as error:
        raise ExerciseError(
            status_code=status.HTTP_409_CONFLICT,
            code="exercise_unlock_write_refused",
            message=str(error),
        ) from error
    session.commit()
    _LOGGER.info("exercise results unlocked: newly=%s", newly)
    return UnlockView(event_key=event_key, unlocked=True)


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------


@router.get(
    "/workspaces",
    response_model=TeamListView,
    summary="Every team that exists, with the data file each is on",
)
def list_team_workspaces(
    session: ExerciseSession,
    instructor: InstructorRepository,
    active: MaybeActiveDataset,
) -> TeamListView:
    """Design spec §14's "list workspaces".

    **Not scoped to the active data file**, and that is the fix for a defect
    rather than a preference. Design spec §3: uploading a file moves no team.
    This list used to be filtered by the newest upload, so the instructor
    pressing "upload" watched her own list of teams go empty while six teams
    carried on working — with nothing on the screen to say why, and a re-point
    she had no reason to think she needed as the only way back.

    Every team is listed with the file it is on. ``active_dataset_label`` says
    separately which file a team entering *now* would join, so the two facts are
    two fields instead of one misleading one.

    A team that has not entered its number is absent: there is no row for it,
    and inventing one would report six teams working when two are. Bounded by
    the repository's ``MAX_WORKSPACE_LIST_ROWS`` rather than by a second number
    here, so every caller of that read is capped and not only this one (F4).
    """
    return TeamListView(
        active_dataset_label=active.dataset.label if active.dataset else None,
        teams=tuple(team_view(row) for row in instructor.list_workspaces(session)),
    )


@router.get(
    "/workspaces/{team_number}",
    response_model=TeamDetailView,
    summary="One team's saved settings and result runs",
)
def read_team_workspace(
    team_number: int,
    session: ExerciseSession,
    instructor: InstructorRepository,
    dataset_id: _DatasetChoice = None,
) -> TeamDetailView:
    """Design spec §14's "open any team's saved settings and results". Read-only.

    Addressed by *the data file the teams are on* (see :func:`_teams_dataset`),
    not by the newest upload — which is why this no longer 404s on a team that
    is plainly still working the moment a new file is uploaded.

    ``result_runs`` is empty until the results track lands, which is a real
    answer: design spec §9's route does not exist yet, so no team can have run
    results.

    Raises:
        ExerciseError: 404 when that team has not entered its number, 422 for a
            team number outside 1-6, 409 when no data file can be resolved.
    """
    dataset = _teams_dataset(instructor, session, requested=dataset_id)
    workspace = _require_team(
        instructor, session, dataset_id=dataset.dataset_id, team_number=team_number
    )
    return TeamDetailView(
        team_number=workspace.team_number,
        saved_settings=tuple(
            setting_view(row)
            for row in instructor.list_saved_settings(session, workspace_id=workspace.id)
        ),
        result_runs=tuple(
            run_view(row) for row in instructor.list_result_runs(session, workspace_id=workspace.id)
        ),
    )


@router.post(
    "/workspaces/{team_number}/reset",
    response_model=TeamSummaryView,
    dependencies=_STATE_CHANGING,
    summary="Clear one team's work",
)
def reset_team_workspace(
    team_number: int,
    session: ExerciseSession,
    instructor: InstructorRepository,
    workspaces: WorkspaceRepository,
    dataset_id: _DatasetChoice = None,
) -> TeamSummaryView:
    """Design spec §11's per-team reset, and **the only reset there is**.

    Owner ruling, 2026-09-19: per-team reset sits behind this passcode. The
    team-addressed route was removed — it resolved the workspace from a cookie
    anyone who types the team's number can obtain, so an irreversible action
    was available to whoever wanted it, and Session 2 has no backup.

    **One team, and one set of statements.**
    ``ExerciseWorkspaceRepository.reset_team`` is reused rather than
    reimplemented, so "what a reset deletes" has one answer: this team's
    overlay, saved settings and result runs, and a new seed. Every statement is
    keyed on the workspace id resolved from ``(data file, team number)``, so no
    other team's rows are reachable from here.

    Addressed by the data file the teams are on (see :func:`_teams_dataset`),
    so a fresh upload does not make this 404 on a team that is still working.

    Raises:
        ExerciseError: 404 when that team has not entered its number, 422 for a
            team number outside 1-6, 409 when no data file can be resolved or
            the write is refused.
    """
    dataset = _teams_dataset(instructor, session, requested=dataset_id)
    workspace = _require_team(
        instructor, session, dataset_id=dataset.dataset_id, team_number=team_number
    )
    try:
        instructor.reset_team(
            session,
            dataset_id=dataset.dataset_id,
            workspace_id=workspace.id,
            workspaces=workspaces,
        )
    except ExerciseWriteRefused as error:
        raise ExerciseError(
            status_code=status.HTTP_409_CONFLICT,
            code="exercise_reset_write_refused",
            message=str(error),
        ) from error
    session.commit()
    for row in instructor.list_workspaces(session, dataset_id=dataset.dataset_id):
        if row.team_number == team_number:
            return team_view(row)
    raise _no_such_team()  # pragma: no cover - the row was just read back


#: The query parameter every team-addressed instructor route accepts.
#:
#: Optional, and what it addresses is *the data file the teams are on* — never
#: the newest upload. See :func:`_teams_dataset` for what happens when it is
#: omitted and why omitting it can be refused.
_DatasetChoice = Annotated[
    uuid.UUID | None,
    Query(
        alias="dataset_id",
        description=(
            "The data file to act on. Omit it when every team is in the same "
            "file, which is the ordinary case; pass the `dataset_id` from the "
            "team list when they are not."
        ),
    ),
]


def _teams_dataset(
    instructor: InstructorRepository,
    session: ExerciseSession,
    *,
    requested: uuid.UUID | None,
) -> WorkingDataset:
    """The data file an instructor action applies to, or one plain sentence.

    **Never the active data file.** "Active" means *most recently uploaded*,
    which is the file a team entering a number right now would join — and
    design spec §3 is explicit that uploading moves nobody. Routing the
    instructor's actions through it meant that, one upload later, ``unlock``
    wrote a row against a file no team could see, ``reset`` and the team detail
    404'd on teams that were plainly still working, and nothing said why.

    So the question this answers is the one that was always meant: *which file
    are the teams in*. The rule:

    * a ``dataset_id`` the instructor passed is honoured, and refused if no team
      is in it — never silently redirected, because a refusal she can read beats
      an action against a file she did not name;
    * omitted, with exactly one file in use, resolves to that file;
    * omitted, with several in use — which a re-point exists to end — is refused
      with a sentence asking which, rather than guessing;
    * omitted, with none in use, is refused with a sentence. **A data file with
      zero workspaces is never targeted**, which is the whole of what stopped
      the unlock-into-the-void.

    Raises:
        ExerciseError: 409, with the sentence for whichever case applies.
    """
    in_use = instructor.datasets_with_workspaces(session)
    if requested is not None:
        for candidate in in_use:
            if candidate.dataset_id == requested:
                return candidate
        raise ExerciseError(
            status_code=status.HTTP_409_CONFLICT,
            code="exercise_dataset_has_no_teams",
            message="No team is working in that data file.",
        )
    if not in_use:
        raise ExerciseError(
            status_code=status.HTTP_409_CONFLICT,
            code="exercise_no_teams_yet",
            message="No team has entered a number yet.",
        )
    if len(in_use) > 1:
        raise ExerciseError(
            status_code=status.HTTP_409_CONFLICT,
            code="exercise_teams_span_datasets",
            message=(
                "The teams are split across more than one data file; "
                "choose which one this applies to."
            ),
        )
    return in_use[0]


def _require_team(
    instructor: InstructorRepository,
    session: ExerciseSession,
    *,
    dataset_id: uuid.UUID,
    team_number: int,
) -> TeamWorkspaceHandle:
    """The workspace for ``team_number``, or one sentence.

    The number is checked against ``EXERCISE_TEAM_NUMBERS`` first, so "team 9"
    is answered as the typo it is rather than as an absent row.
    """
    if team_number not in EXERCISE_TEAM_NUMBERS:
        raise ExerciseError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="exercise_team_number_unknown",
            message="Pick a team number from 1 to 6.",
        )
    workspace = instructor.find_workspace(session, dataset_id=dataset_id, team_number=team_number)
    if workspace is None:
        raise _no_such_team()
    return workspace


def _no_such_team() -> ExerciseError:
    """One sentence for a team that has not entered its number."""
    return ExerciseError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="exercise_team_not_started",
        message="That team has not entered its number yet.",
    )
