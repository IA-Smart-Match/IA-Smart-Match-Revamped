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
from enum import Enum
from typing import Annotated, Final

from fastapi import APIRouter, Body, Depends, Query, Request, Response, status
from smartmatch_domain.exercise import EXERCISE_TEAM_NUMBERS
from smartmatch_domain.exercise.ingest import IngestRefusal, parse_exercise_file
from smartmatch_domain.exercise.instructor_session import (
    mint_instructor_session,
    spend_a_verification,
    verify_instructor_passcode,
)

from smartmatch_api.exercise_dependencies import (
    MAX_INVITE_LIMIT,
    MIN_INVITE_LIMIT,
    DatasetRepository,
    ExerciseDatasetLabelError,
    ExerciseDatasetWriteError,
    ExerciseSession,
    ExerciseWriteRefused,
    InstructorCookiePolicy,
    InstructorPasscode,
    InstructorRepository,
    MaybeActiveDataset,
    TeamWorkspaceHandle,
    WorkingDataset,
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
from smartmatch_api.routers.exercise_instructor_models import (
    TEAMS_HAVE_NOT_MOVED,
    DatasetView,
    InstructorLoginRequest,
    InstructorSessionView,
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

    **The two bounds are not the same bound** (OQ-CE-06 PLACEHOLDER; see
    :class:`~smartmatch_api.exercise_rate_limit.Allowance`).

    * The **per-key** bound is the caller's own budget and is charged first. If
      it is spent, this refuses without looking at the passcode at all: no key
      derivation, no global budget consumed. The earlier version charged the
      global window first, so fifty attempts a caller's own key had already
      refused still spent fifty units of everybody else's allowance — one
      script could lock the real instructor out for a lesson.
    * The **global** bound is the one an attacker can exhaust on somebody
      else's behalf, so it may not be the reason a *correct* passcode is
      refused. When it is spent the passcode is still checked, and a correct one
      is let in and **refunds** its unit. The window is left holding only the
      attempts that were wrong.

    **Fail closed, and at the same cost.** A deployment with no usable passcode
    reaches the same refusal as a wrong one *and pays the same key derivation*
    to get there — see
    :func:`~smartmatch_domain.exercise.instructor_session.spend_a_verification`.
    Returning early would have answered "is there an instructor page on this
    host?" to anyone with a stopwatch. The response cannot tell the cases apart;
    the server log records which, because an operator who mistyped the variable
    has to be able to find out.

    Raises:
        ExerciseError: 429 when this caller's attempts are spent or a wrong
            passcode arrives on a spent global window, 401 when the passcode is
            not this deployment's, 403 when the request carries no
            ``X-Exercise-Request`` header.
    """
    allowance = _LOGIN_LIMITER.charge(_client_key(request), now=utc_now())
    if not allowance.key_allows:
        _LOGGER.warning("exercise instructor login rate limited: this caller's attempts are spent")
        raise _too_many_attempts()

    if passcode.value is None:
        # The same work a real verification costs, discarded. Not an early
        # return: that is the timing oracle this branch used to be.
        spend_a_verification(payload.passcode, secret=secret)
        _LOGGER.error(
            "exercise instructor login refused: no usable "
            "SMARTMATCH_EXERCISE_INSTRUCTOR_PASSCODE is configured (OQ-CE-07)"
        )
        raise _passcode_refused()

    if not verify_instructor_passcode(payload.passcode, configured=passcode.value, secret=secret):
        _LOGGER.warning("exercise instructor login refused: passcode did not match")
        if not allowance.global_allows:
            raise _too_many_attempts()
        raise _passcode_refused()

    # Correct. The global window never holds a unit for an attempt that was
    # right, so a flood from many addresses cannot lock the passcode holder out.
    _LOGIN_LIMITER.refund_global()
    _set_instructor_cookie(
        response, policy=policy, token=mint_instructor_session(secret=secret, now=utc_now())
    )
    _LOGGER.info("exercise instructor signed in")
    return InstructorSessionView(signed_in=True)


def _too_many_attempts() -> ExerciseError:
    """One sentence for both ways of running out of attempts."""
    return ExerciseError(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        code="exercise_instructor_login_rate_limited",
        message="Too many passcode attempts. Please wait a few minutes and try again.",
    )


def _passcode_refused() -> ExerciseError:
    """One sentence for every way a passcode can be wrong. See :data:`_LOGIN_REFUSED`."""
    return ExerciseError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code="exercise_instructor_passcode_refused",
        message=_LOGIN_REFUSED,
    )


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
    and inventing one would report six teams working when two are.
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


@router.post(
    "/refresh-all",
    summary="PLACEHOLDER — refuses until the results track lands",
    dependencies=_STATE_CHANGING,
    responses={
        status.HTTP_409_CONFLICT: {
            "description": (
                "Always. Design spec §13's refresh needs the asking choice the "
                "results track stores; until then this route refuses."
            )
        }
    },
)
def refresh_all_workspaces() -> None:
    """Design spec §13's "refresh all", declared and deliberately not built.

    The refresh copies a share of the withheld column into each team's
    overlay, and that share is decided by the team's asking choice, which is
    stored by a route the results track owns. There is no asking choice to read
    yet, so a refresh here would either do nothing at all or invent a share —
    and inventing a share is inventing one of OQ-CE-04's numbers.

    It is a **route that refuses** rather than an absent one so the instructor
    page can show the button it will need with a sentence saying why it is off,
    instead of the frontend discovering a 404 in a classroom. It is registered
    in the route ledger as exactly that.

    Declared with a ``responses`` entry rather than ``status_code=409``: the
    latter is FastAPI's *success* status, and putting a refusal there told the
    generated contract that 409 was the happy path of a handler that has none.
    The route's only outcome is documented as the error it is.

    Raises:
        ExerciseError: 409, always, until CE-RESULTS lands.
    """
    raise ExerciseError(
        status_code=status.HTTP_409_CONFLICT,
        code="exercise_refresh_not_ready",
        message="Refreshing every team is not switched on yet.",
    )


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
