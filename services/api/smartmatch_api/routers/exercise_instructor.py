"""The instructor page (design spec §14, ADR-0025 D1/D2/D6/D8).

One passcode from the environment opens one page. Behind it: upload a data
file, set the invite limit, unlock results per event, see what the six teams
have done, reset one team, and re-point every team at a data file. No account,
no role, no principal, no CBA table — the instructor is not a *who* here, and
the passcode is a door rather than an identity.

Two routers, and why the gate is structural
===========================================

``login_router`` carries the two routes that must work without a session;
:data:`router` carries every other route and takes
:func:`~smartmatch_api.exercise_dependencies.require_instructor_session` as a
**router-level** dependency. Written that way rather than per handler because a
gate that is a parameter is a gate that comes off when somebody edits a
signature, and the failure is silent: an open instructor route looks exactly
like a working one.

Both are bare module-level assignments, for ``exercise_public.router``'s
reason: the route ledger in ``tests/authz/test_policy_matrix.py`` reads router
prefixes out of the AST and matches ``name = APIRouter(...)``.

The upload is a raw body, not multipart — an owner question
===========================================================

Design spec §3 says *multipart, one file*. FastAPI cannot parse a multipart
body without ``python-multipart``, which this repository does not have: adding
it is a new runtime dependency and a regeneration of the hash-pinned
requirement locks (``requirements/runtime.txt``, compiled ``--no-index``) for
one route on one screen.

So the upload is the same bytes by a simpler road: the CSV **is** the request
body, with the instructor's label and the browser's file name as query
parameters. The ingest core takes bytes and a file name and neither knows nor
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

Rate limiting, CSRF, and what is still open
===========================================

The login route is bounded by
:mod:`smartmatch_api.exercise_rate_limit` — a **PLACEHOLDER (OQ-CE-06)**,
in-process and per worker, because the repository's real limiter needs a
principal or ``smartmatch_persistence`` and an exercise router may import
neither. Every state-changing route here requires ``X-Exercise-Request``, as
the team routes do.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from enum import Enum
from typing import Annotated, Final

from fastapi import APIRouter, Body, Depends, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from smartmatch_domain.exercise import EXERCISE_TEAM_NUMBERS
from smartmatch_domain.exercise.ingest import IngestRefusal, ParsedDataset, parse_exercise_file
from smartmatch_domain.exercise.instructor_session import (
    mint_instructor_session,
    verify_instructor_passcode,
)

from smartmatch_api.exercise_dependencies import (
    MAX_INVITE_LIMIT,
    MIN_INVITE_LIMIT,
    ActiveDataset,
    DatasetRepository,
    DatasetSummary,
    ExerciseDatasetLabelError,
    ExerciseDatasetWriteError,
    ExerciseSession,
    ExerciseWriteRefused,
    InstructorCookiePolicy,
    InstructorPasscode,
    InstructorRepository,
    InstructorResultRun,
    InstructorSavedSetting,
    InstructorWorkspaceRow,
    TeamWorkspaceHandle,
    WorkspaceRepository,
    WorkspaceSecret,
    require_exercise_request_header,
    require_instructor_session,
)
from smartmatch_api.exercise_errors import ExerciseError
from smartmatch_api.exercise_rate_limit import (
    INSTRUCTOR_LOGIN_ATTEMPTS_PER_CLIENT,
    INSTRUCTOR_LOGIN_ATTEMPTS_TOTAL,
    INSTRUCTOR_LOGIN_WINDOW,
    UNRESOLVED_CALLER_KEY,
    FixedWindowLimiter,
)
from smartmatch_api.utils import utc_now

_LOGGER = logging.getLogger(__name__)

#: The tag both routers carry. The *prefix* is deliberately written out as a
#: literal on each ``APIRouter(...)`` below rather than hoisted into a constant
#: beside this one: the route ledger in ``tests/authz/test_policy_matrix.py``
#: reads prefixes out of the AST and only sees ``prefix="…"``, so a named
#: constant would make every route in this module appear at ``/login``,
#: ``/datasets`` and so on — paths that match no ledger row and no real route.
_TAGS: Final[list[str | Enum]] = ["class-exercise"]

#: Applied to every state-changing route in this module, and declared once so
#: the two routers cannot drift.
_STATE_CHANGING = [Depends(require_exercise_request_header)]

#: The two routes that must answer before there is a session.
login_router = APIRouter(prefix="/v1/exercise/instructor", tags=_TAGS)

#: Every other instructor route. The session dependency is on the *router*, so
#: a route added below is gated by existing rather than by remembering.
router = APIRouter(
    prefix="/v1/exercise/instructor",
    tags=_TAGS,
    dependencies=[Depends(require_instructor_session)],
)

#: PLACEHOLDER (OQ-CE-06, owner Danny). Module-level because the counters are
#: this process's, which is the whole of what this limiter claims to be. See
#: :mod:`smartmatch_api.exercise_rate_limit`.
_LOGIN_LIMITER: Final[FixedWindowLimiter] = FixedWindowLimiter(
    per_key=INSTRUCTOR_LOGIN_ATTEMPTS_PER_CLIENT,
    total=INSTRUCTOR_LOGIN_ATTEMPTS_TOTAL,
    window=INSTRUCTOR_LOGIN_WINDOW,
)

#: One message for every way a login can fail that is not a rate limit. The
#: differences are real — an unconfigured passcode, a blank one, a wrong one —
#: and are deliberately not reported, so the response cannot be used to learn
#: whether this deployment has an instructor page at all.
_LOGIN_REFUSED: Final[str] = "That passcode was not recognised."


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class InstructorLoginRequest(BaseModel):
    """The login screen's whole input."""

    model_config = ConfigDict(extra="forbid")

    passcode: str = Field(
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

    Counts and the year values found, so the vocabulary can be read off the
    file rather than guessed at (OQ-CE-01 stays open — nothing here closes a
    vocabulary). No cell of the withheld column appears in any form.
    """

    model_config = ConfigDict(extra="forbid")

    profile_count: int
    event_count: int
    exercise_event_count: int
    distinct_class_years: tuple[str, ...] = Field(
        description="The year values this file used, sorted. Reported, never validated."
    )
    profiles_missing_major: int
    profiles_missing_class_year: int
    profiles_without_card: int
    distinct_stated_interest_terms: int
    distinct_topic_tag_terms: int
    events_without_topic_tags: int
    discarded_list_entries: int = Field(
        description=(
            "List-cell entries that were punctuation only and could not become "
            "a term. Counted rather than silently dropped (ADR-0011)."
        )
    )
    major_only: int
    major_plus_events: int
    completed_card: int


class UploadedDatasetView(BaseModel):
    """The answer to an upload: the stored file, and what was in it."""

    model_config = ConfigDict(extra="forbid")

    dataset: DatasetView
    report: IngestReportView


class TeamSummaryView(BaseModel):
    """One team, in the instructor's list of teams."""

    model_config = ConfigDict(extra="forbid")

    team_number: int
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
    """Every team working in the current data file."""

    model_config = ConfigDict(extra="forbid")

    dataset_label: str
    teams: tuple[TeamSummaryView, ...]


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


# ---------------------------------------------------------------------------
# Login and logout
# ---------------------------------------------------------------------------


def _client_key(request: Request) -> str:
    """The rate-limit bucket this request is charged against."""
    client = request.client
    return client.host if client and client.host else UNRESOLVED_CALLER_KEY


@login_router.post(
    "/login",
    response_model=InstructorSessionView,
    status_code=status.HTTP_200_OK,
    dependencies=_STATE_CHANGING,
    summary="Present the instructor passcode",
)
def instructor_login(
    payload: InstructorLoginRequest,
    request: Request,
    response: Response,
    passcode: InstructorPasscode,
    secret: WorkspaceSecret,
    policy: InstructorCookiePolicy,
) -> InstructorSessionView:
    """Design spec §14's one door.

    The rate limit is charged as the **first statement**, before the passcode
    is looked at, so a wrong passcode and a right one cost the same and a
    caller cannot spend unlimited attempts by never being right. It is a
    PLACEHOLDER (OQ-CE-06) — in-process, per worker — and is described as such
    on :mod:`smartmatch_api.exercise_rate_limit`.

    **Fail closed.** A deployment with no passcode, or one shorter than the
    floor, reaches the same refusal as a wrong passcode: there is no branch
    here that skips the check, so an unconfigured instructor page is a shut
    door rather than an open one. The response cannot be used to tell the three
    apart; the server log records which, because an operator who mistyped the
    variable has to be able to find out.

    Raises:
        ExerciseError: 429 when the attempt allowance is spent, 401 when the
            passcode is not this deployment's, 403 when the request carries no
            ``X-Exercise-Request`` header.
    """
    if not _LOGIN_LIMITER.charge(_client_key(request), now=utc_now()):
        _LOGGER.warning("exercise instructor login rate limited")
        raise ExerciseError(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="exercise_instructor_login_rate_limited",
            message="Too many passcode attempts. Please wait a few minutes and try again.",
        )
    if passcode.value is None:
        _LOGGER.error(
            "exercise instructor login refused: no usable "
            "SMARTMATCH_EXERCISE_INSTRUCTOR_PASSCODE is configured (OQ-CE-07)"
        )
        raise ExerciseError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="exercise_instructor_passcode_refused",
            message=_LOGIN_REFUSED,
        )
    if not verify_instructor_passcode(payload.passcode, configured=passcode.value, secret=secret):
        _LOGGER.warning("exercise instructor login refused: passcode did not match")
        raise ExerciseError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="exercise_instructor_passcode_refused",
            message=_LOGIN_REFUSED,
        )
    _set_instructor_cookie(
        response, policy=policy, token=mint_instructor_session(secret=secret, now=utc_now())
    )
    _LOGGER.info("exercise instructor signed in")
    return InstructorSessionView(signed_in=True)


@login_router.post(
    "/logout",
    response_model=InstructorSessionView,
    status_code=status.HTTP_200_OK,
    dependencies=_STATE_CHANGING,
    summary="Clear the instructor session cookie",
)
def instructor_logout(
    response: Response,
    policy: InstructorCookiePolicy,
) -> InstructorSessionView:
    """Drop this browser's session cookie.

    Takes no session of its own — a request with an expired or absent cookie
    still gets its cookie cleared, which is what a person pressing "sign out"
    means, and refusing them would be a refusal with nothing behind it.

    **What this does not do, said plainly:** the session is a signed value with
    no server-side row (see
    :mod:`smartmatch_domain.exercise.instructor_session`), so this clears the
    *browser's* copy and does not revoke anything. A token already captured
    stays usable until it expires. The levers that do revoke are the twelve-hour
    lifetime and rotating the exercise secret; a server-side store, with the
    migration it needs, is recorded on this track's pull request.
    """
    response.delete_cookie(
        key=policy.name,
        path=policy.path,
        httponly=policy.http_only,
        samesite=policy.same_site,
        secure=policy.secure,
    )
    return InstructorSessionView(signed_in=False)


def _set_instructor_cookie(
    response: Response, *, policy: InstructorCookiePolicy, token: str
) -> None:
    """Point this browser at a live session.

    A session cookie — no ``max_age`` and no ``expires`` — so it dies with the
    browser as well as with its own signed expiry. The two are independent and
    both are short on purpose.
    """
    response.set_cookie(
        key=policy.name,
        value=token,
        path=policy.path,
        httponly=policy.http_only,
        samesite=policy.same_site,
        secure=policy.secure,
    )


# ---------------------------------------------------------------------------
# Data files
# ---------------------------------------------------------------------------


def _dataset_view(summary: DatasetSummary) -> DatasetView:
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


def _report_view(parsed: ParsedDataset) -> IngestReportView:
    """The accepted file's counts. Named field by field, so a field added to
    the domain report is a deliberate addition here rather than an automatic
    disclosure."""
    report = parsed.report
    return IngestReportView(
        profile_count=report.profile_count,
        event_count=report.event_count,
        exercise_event_count=report.exercise_event_count,
        distinct_class_years=report.distinct_class_years,
        profiles_missing_major=report.profiles_missing_major,
        profiles_missing_class_year=report.profiles_missing_class_year,
        profiles_without_card=report.profiles_without_card,
        distinct_stated_interest_terms=report.distinct_stated_interest_terms,
        distinct_topic_tag_terms=report.distinct_topic_tag_terms,
        events_without_topic_tags=report.events_without_topic_tags,
        discarded_list_entries=report.discarded_list_entries,
        major_only=report.markers.major_only,
        major_plus_events=report.markers.major_plus_events,
        completed_card=report.markers.completed_card,
    )


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
        _dataset_view(summary)
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
    content: Annotated[bytes, Body(media_type="text/csv")],
    label: Annotated[str, Query(description="What to call this upload on the instructor page.")],
    source_filename: Annotated[
        str | None,
        Query(description="The browser's file name. Stored as a label; never opened as a path."),
    ] = None,
) -> UploadedDatasetView:
    """Read one CSV, validate it, store it — synchronously, in one transaction.

    Design spec §3: the instructor needs an answer on the spot, so the job and
    review pipeline behind ``routers/imports.py`` is not used and neither is
    its principal. See the module docstring for why the bytes arrive as a body
    rather than as a multipart part.

    Every refusal is one plain sentence from
    :func:`~smartmatch_domain.exercise.ingest.parse_exercise_file`, in §3's
    order, and the first failure is the whole answer. PLACEHOLDER (OQ-CE-01):
    the column names and the list separator are
    ``ingest.PLACEHOLDER_LAYOUT``'s, and nothing here closes a vocabulary.

    **Touches no workspace row.** Design spec §3: existing workspaces keep
    pointing at their old dataset until the instructor re-points them. Uploading
    a file therefore changes nothing a team is currently looking at.

    Raises:
        ExerciseError: 422 when the file is refused or the label is unusable,
            409 when the database refuses the write, 403 without the
            ``X-Exercise-Request`` header, 401 without a session.
    """
    parsed = parse_exercise_file(content, filename=source_filename)
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
    return UploadedDatasetView(dataset=_dataset_view(summary), report=_report_view(parsed))


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
    return _dataset_view(summary)


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
    dataset: ActiveDataset,
    instructor: InstructorRepository,
) -> UnlockView:
    """Write the ``exercise_result_unlock`` row design spec §9 reads.

    **Idempotent.** A second press inserts nothing, moves no ``unlocked_at``,
    and answers the same sentence — an instructor pressing a button twice in a
    classroom is the expected case, not the exceptional one.

    Scoped to the **active** data file, which is the one teams entering today
    join. Whether the instructor should be able to unlock an event of an older
    file is an owner question recorded on this track's pull request; the safe
    behaviour is the narrow one, because the wrong answer here opens results on
    a file nobody is using and looks like nothing happening.

    Raises:
        ExerciseError: 404 when the event is not in the active data file, 409
            when no data file has been uploaded or the write is refused.
    """
    if not instructor.event_exists(session, dataset_id=dataset.id, event_key=event_key):
        raise ExerciseError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="exercise_event_unknown",
            message="That event is not in the loaded data file.",
        )
    try:
        newly = instructor.unlock_results(session, dataset_id=dataset.id, event_key=event_key)
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


def _team_view(row: InstructorWorkspaceRow) -> TeamSummaryView:
    return TeamSummaryView(
        team_number=row.team_number,
        dataset_label=row.dataset_label,
        created_at=row.created_at,
        saved_setting_count=row.saved_setting_count,
        result_run_count=row.result_run_count,
        asking_choice=row.asking_choice,
        refreshed_at=row.refreshed_at,
    )


def _setting_view(row: InstructorSavedSetting) -> SavedSettingView:
    return SavedSettingView(event_key=row.event_key, name=row.name, created_at=row.created_at)


def _run_view(row: InstructorResultRun) -> ResultRunView:
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


@router.get(
    "/workspaces",
    response_model=TeamListView,
    summary="Every team working in the current data file",
)
def list_team_workspaces(
    session: ExerciseSession,
    dataset: ActiveDataset,
    instructor: InstructorRepository,
) -> TeamListView:
    """Design spec §14's "list workspaces".

    A team that has not entered its number yet is simply absent — there is no
    row for it, and inventing one would report six teams working when two are.
    """
    return TeamListView(
        dataset_label=dataset.label,
        teams=tuple(
            _team_view(row) for row in instructor.list_workspaces(session, dataset_id=dataset.id)
        ),
    )


@router.get(
    "/workspaces/{team_number}",
    response_model=TeamDetailView,
    summary="One team's saved settings and result runs",
)
def read_team_workspace(
    team_number: int,
    session: ExerciseSession,
    dataset: ActiveDataset,
    instructor: InstructorRepository,
) -> TeamDetailView:
    """Design spec §14's "open any team's saved settings and results". Read-only.

    ``result_runs`` is empty until the results track lands, which is a real
    answer: design spec §9's route does not exist yet, so no team can have run
    results.

    Raises:
        ExerciseError: 404 when that team has not entered its number.
    """
    workspace = _require_team(instructor, session, dataset_id=dataset.id, team_number=team_number)
    return TeamDetailView(
        team_number=workspace.team_number,
        saved_settings=tuple(
            _setting_view(row)
            for row in instructor.list_saved_settings(session, workspace_id=workspace.id)
        ),
        result_runs=tuple(
            _run_view(row)
            for row in instructor.list_result_runs(session, workspace_id=workspace.id)
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
    dataset: ActiveDataset,
    instructor: InstructorRepository,
    workspaces: WorkspaceRepository,
) -> TeamSummaryView:
    """Design spec §11's per-team reset, from the instructor's side.

    **One team, and the same statements the team's own route runs.**
    ``ExerciseWorkspaceRepository.reset_team`` is reused rather than
    reimplemented, so "what a reset deletes" has one answer: this team's
    overlay, saved settings and result runs, and a new seed. Every statement is
    keyed on the workspace id resolved from ``(active dataset, team number)``,
    so no other team's rows are reachable from here.

    The team's own ``POST /v1/exercise/workspaces/current/reset`` is unchanged
    and stays where it is. Whether per-team reset should move *behind* this
    passcode is an open owner decision recorded on the pull request; this route
    adds an instructor path to it without removing the team's.

    Raises:
        ExerciseError: 404 when that team has not entered its number.
    """
    workspace = _require_team(instructor, session, dataset_id=dataset.id, team_number=team_number)
    workspaces.reset_team(session, workspace_id=workspace.id)
    session.commit()
    rows = instructor.list_workspaces(session, dataset_id=dataset.id)
    for row in rows:
        if row.team_number == team_number:
            return _team_view(row)
    raise _no_such_team()  # pragma: no cover - the row was just read back


@router.post(
    "/refresh-all",
    status_code=status.HTTP_409_CONFLICT,
    summary="PLACEHOLDER — refuses until the results track lands",
    dependencies=_STATE_CHANGING,
)
def refresh_all_workspaces() -> None:
    """Design spec §13's "refresh all", declared and deliberately not built.

    The refresh copies a share of ``hidden_true_interests`` into each team's
    overlay, and that share is decided by the team's asking choice, which is
    stored by a route the results track owns. There is no asking choice to read
    yet, so a refresh here would either do nothing at all or invent a share —
    and inventing a share is inventing one of OQ-CE-04's numbers.

    It is a **route that refuses** rather than an absent one so the instructor
    page can show the button it will need with a sentence saying why it is off,
    instead of the frontend discovering a 404 in a classroom. It is registered
    in the route ledger as exactly that.

    Raises:
        ExerciseError: 409, always, until CE-RESULTS lands.
    """
    raise ExerciseError(
        status_code=status.HTTP_409_CONFLICT,
        code="exercise_refresh_not_ready",
        message="Refreshing every team is not switched on yet.",
    )


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
