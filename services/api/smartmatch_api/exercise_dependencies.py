"""The one database door for class-exercise routers (ADR-0025 D2).

The exercise routers are forbidden the CBA request machinery: no
``smartmatch_api.dependencies``, no ``smartmatch_authz``, no tenant-scoped
repository, and no ``request.app.state`` poking of their own. That rule is
enforced by the import-linter contract "Class exercise routers carry no
principal or tenancy" and by the source walk in
``tests/unit/test_exercise_router_reachability.py``.

A rule with no door is a rule that gets broken the first time somebody needs a
row. The exercise's later tracks — CE-WORKSPACE, CE-SIMULATION, CE-INGEST,
CE-INSTRUCTOR — genuinely need to read and write the ``exercise_`` tables, so
this module is that door, named now, before anybody needs it, so that "the
exercise router reached the database" has exactly one shape a reviewer has to
recognise.

**This is the only way an exercise router may reach a database session, and the
repositories used behind it may touch only ``exercise_``-prefixed tables**
(ADR-0025 D2: those tables carry no ``tenant_id``, no ``owning_unit_id``, and no
foreign key to ``user_account``). A repository behind this dependency that
selected from ``user_account``, ``membership``, ``event``, or any other CBA
table would be the process mixing ADR-0025 D1 exists to prevent, and no test
here can see inside a repository — that half is the reviewer's, and this
paragraph is what they are checking against.

Why not ``smartmatch_api.dependencies.get_session``
===================================================

It would work, and that is the problem. That module also defines
``get_current_principal``, ``CurrentPrincipal``, ``charge_quota`` and the
rate-limit machinery, all of which need a ``ResolvedPrincipal``. An exercise
router that imported it for a session would have the principal one name away,
and the import-linter contract that makes the absence structural would have to
be dropped to allow it. Two functions that look alike are cheaper than one
import that opens a door nobody meant to open.

This module deliberately holds **no principal, no quota, no authorization, and
no query of its own**. What it does hold, as of CE-WORKSPACE, is the *wiring*
that keeps those absences true: the repository handles an exercise router is
allowed to use, the cookie that addresses a team's workspace, and the two
refusals that go with it.

Why the repositories are injected from here (CE-WORKSPACE design decision 1)
============================================================================

The exercise's routers need rows. Two shapes were available:

(a) **Amend the import contract** so that an exercise router may import
    ``smartmatch_persistence.exercise`` while the rest of
    ``smartmatch_persistence`` stays forbidden. Import-linter cannot express
    "forbidden except this subpackage" — a ``forbidden`` contract's
    ``forbidden_modules`` covers descendants, and the only escape hatch is
    ``ignore_imports``, an edge list. Written per router it becomes a line per
    router per repository, and every one of those lines also blinds the
    contract to whatever *that router* reaches through *that* repository.

(b) **Inject through this module.** A router imports this module and nothing
    else; this module imports the exercise repositories; one ignored edge —
    ``smartmatch_api.exercise_dependencies -> smartmatch_persistence.exercise.*``
    — lets the chain-following contract see the wall without seeing the door.

(b) is what is built, for the reason the contract comment in ``pyproject.toml``
states: the ignored edge is *one* edge, on *this* module, restricted to the
``exercise`` subpackage, and everything else the contract forbids it still
forbids. An exercise router that imports any repository directly still fails.
An exercise router that reaches a tenant-scoped repository through this module
still fails, because the ignore names only ``smartmatch_persistence.exercise``.
The negative probe in the PR body is the evidence, not this paragraph.

The value types travel through the door too
===========================================

A router that may not import ``smartmatch_persistence`` may not import the
*dataclasses* a repository returns or the *exceptions* it raises either — the
contract forbids the module, not a subset of its names. So this module
re-exports them: :class:`ExerciseWorkspace` and :class:`DatasetSummary`, the
instructor rows, the two write refusals, and the invite-limit bounds. It is
not tidiness. A handler that caught ``ExerciseDatasetWriteError`` by importing
it directly would be a handler that had walked around the wall to reach a
name, and the next thing imported that way is a repository.

The cookie
==========

Design spec §15: "the server row is the truth; the cookie is a pointer". The
value is an opaque token derived in
:mod:`smartmatch_domain.exercise.workspace_token` (OQ-CE-08, closed); the
server stores only its SHA-256. This module owns the cookie's *flags*, in one
place, because a cookie set with the right flags on one route and the wrong
ones on another is a cookie with the wrong flags.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Annotated, Final, Literal

from fastapi import Cookie, Depends, Header, Request, status
from smartmatch_domain.exercise.instructor_session import (
    instructor_session_is_live,
    usable_passcode,
)
from smartmatch_domain.exercise.workspace_token import (
    derive_workspace_token,
    hash_workspace_token,
)
from smartmatch_persistence.exercise.dataset_repository import (
    DatasetSummary,
    ExerciseDatasetLabelError,
    ExerciseDatasetRepository,
    ExerciseDatasetWriteError,
    ExerciseEventRow,
    SimulationProfileRow,
)
from smartmatch_persistence.exercise.instructor_repository import (
    MAX_INVITE_LIMIT,
    MIN_INVITE_LIMIT,
    ExerciseInstructorRepository,
    ExerciseWriteRefused,
)
from smartmatch_persistence.exercise.instructor_rows import (
    InstructorResultRun,
    InstructorSavedSetting,
    InstructorWorkspaceRow,
    TeamWorkspaceHandle,
    WorkingDataset,
)
from smartmatch_persistence.exercise.results_repository import (
    ALREADY_RUN_SENTENCE,
    AlreadyRunError,
    ExerciseResultsRepository,
    ExerciseResultsWriteRefused,
)
from smartmatch_persistence.exercise.results_rows import (
    RefreshCandidate,
    RefreshCounts,
    ResultPanel,
    StoredResultRun,
    TeamResultsState,
)
from smartmatch_persistence.exercise.settings_repository import (
    MAX_SAVED_SETTINGS_PER_EVENT,
    ExerciseSettingsRepository,
    ExerciseSettingsWriteRefused,
    SavedSetting,
    TooManySavedSettingsError,
)
from smartmatch_persistence.exercise.team_view_repository import (
    ExerciseTeamViewRepository,
    TeamProfileRow,
)
from smartmatch_persistence.exercise.workspace_repository import (
    ExerciseDatasetSummary,
    ExerciseWorkspace,
    ExerciseWorkspaceRepository,
    active_dataset,
)
from smartmatch_providers import Edition
from sqlalchemy.orm import Session

from smartmatch_api.config import Settings, get_settings, require_exercise_workspace_secret
from smartmatch_api.exercise_errors import ExerciseError
from smartmatch_api.utils import utc_now

__all__ = [
    "ALREADY_RUN_SENTENCE",
    "EXERCISE_REQUEST_HEADER",
    "INSTRUCTOR_COOKIE_NAME",
    "MAX_INVITE_LIMIT",
    "MAX_SAVED_SETTINGS_PER_EVENT",
    "MIN_INVITE_LIMIT",
    "WORKSPACE_COOKIE_NAME",
    "ActiveDataset",
    "AlreadyRunError",
    "ConfiguredPasscode",
    "CookiePolicy",
    "CurrentWorkspace",
    "DatasetRepository",
    "DatasetSummary",
    "ExerciseCookiePolicy",
    "ExerciseDatasetLabelError",
    "ExerciseDatasetSummary",
    "ExerciseDatasetWriteError",
    "ExerciseEventRow",
    "ExerciseResultsWriteRefused",
    "ExerciseSession",
    "ExerciseSettingsWriteRefused",
    "ExerciseWorkspace",
    "ExerciseWriteRefused",
    "InstructorCookiePolicy",
    "InstructorPasscode",
    "InstructorRepository",
    "InstructorResultRun",
    "InstructorSavedSetting",
    "InstructorWorkspaceRow",
    "MaybeActiveDataset",
    "MaybeDataset",
    "RefreshCandidate",
    "RefreshCounts",
    "ResultPanel",
    "ResultsRepository",
    "SavedSetting",
    "SettingsRepository",
    "SimulationProfileRow",
    "StoredResultRun",
    "TeamProfileRow",
    "TeamResultsState",
    "TeamViewRepository",
    "TeamWorkspaceHandle",
    "TooManySavedSettingsError",
    "WorkingDataset",
    "WorkspaceCookiePolicy",
    "WorkspaceRepository",
    "WorkspaceSecret",
    "get_active_dataset",
    "get_current_workspace",
    "get_dataset_repository",
    "get_exercise_session",
    "get_instructor_passcode",
    "get_instructor_repository",
    "get_maybe_active_dataset",
    "get_results_repository",
    "get_settings_repository",
    "get_team_view_repository",
    "get_workspace_repository",
    "get_workspace_secret",
    "instructor_cookie_policy",
    "require_exercise_request_header",
    "require_instructor_session",
    "workspace_cookie_policy",
    "workspace_token_for",
]

#: The cookie a team's browser carries. Scoped to ``/v1/exercise`` by
#: :func:`workspace_cookie_policy`, so it is not sent to any other path this
#: host may ever serve.
WORKSPACE_COOKIE_NAME: Final[str] = "exercise_workspace"

#: The header every state-changing exercise route requires.
#:
#: This repository has no CSRF machinery to reuse — a grep for ``csrf``, an
#: origin check, or ``set_cookie`` finds nothing, because the pilot login is a
#: ``Authorization: Bearer`` exchange and a bearer header is not sent by a
#: cross-site form. The exercise's cookie *is*, so it needs the protection the
#: bearer scheme got for free.
#:
#: ``SameSite=Lax`` is the first line and stops the cross-site form post on
#: every browser that honours it. This header is the second: a cross-origin
#: page cannot add a custom header to a request without a CORS preflight, and
#: this application configures no permissive CORS, so the preflight fails. Two
#: independent mechanisms, because the whole exercise is a cookie with no login
#: behind it.
#:
#: The frontend track (CE-MOUNT) sends ``X-Exercise-Request: 1`` on every POST.
EXERCISE_REQUEST_HEADER: Final[str] = "X-Exercise-Request"

#: The cookie the instructor's browser carries after presenting the passcode
#: (design spec §14). Scoped to ``/v1/exercise/instructor`` by
#: :func:`instructor_cookie_policy` — *narrower* than the workspace cookie's
#: ``/v1/exercise``, so a class participant's browser on an ordinary exercise
#: route is never sent it and it cannot be read back off a team's request.
INSTRUCTOR_COOKIE_NAME: Final[str] = "exercise_instructor"


def get_exercise_session(request: Request) -> Iterator[Session]:
    """Yield a request-scoped session for the ``exercise_`` tables.

    Rolled back rather than committed on exit, for
    ``smartmatch_api.dependencies.get_session``'s reason: a route that changes
    state commits explicitly, and anything that got here without committing
    either failed or only read. Committing by default would turn a half-finished
    request into a persisted one.

    Issues no query of its own. The session comes from the process-wide factory
    the ``lifespan`` builds in *every* scope — the exercise has its own tables
    and will need it; what it must not have is a principal.
    """
    session_factory = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


#: The annotation an exercise route handler writes.
#:
#: Exported as an alias so a handler can take a session without importing
#: SQLAlchemy — which is what lets "class exercise routers do not touch
#: SQLAlchemy directly" be a contract in ``pyproject.toml`` rather than a habit.
ExerciseSession = Annotated[Session, Depends(get_exercise_session)]


def get_workspace_repository() -> ExerciseWorkspaceRepository:
    """The one repository an exercise router may reach team workspaces through.

    A dependency rather than a module-level singleton so a test can override it
    the way it overrides any other dependency, and so the router's signature
    says where its rows come from.
    """
    return ExerciseWorkspaceRepository()


#: The annotation a handler writes to get :class:`ExerciseWorkspaceRepository`.
WorkspaceRepository = Annotated[ExerciseWorkspaceRepository, Depends(get_workspace_repository)]


def get_workspace_secret(settings: Annotated[Settings, Depends(get_settings)]) -> str:
    """The deployment's workspace secret, re-checked per request.

    ``smartmatch_api.main`` already refuses to boot a class-exercise process
    without it, so this cannot normally fail. It is checked again here rather
    than read raw because the two callers are different programs — one is the
    import of a module, one is a request — and a secret that went missing
    between them (a reloaded environment, a test that built its own settings)
    must produce the same refusal rather than an HMAC over ``None``.
    """
    return require_exercise_workspace_secret(settings)


#: The annotation a handler writes to get the workspace secret. Handlers that
#: take it pass it straight to the repository; nothing renders it.
WorkspaceSecret = Annotated[str, Depends(get_workspace_secret)]


@dataclass(frozen=True, slots=True)
class WorkspaceCookiePolicy:
    """Every flag the workspace cookie is set with, decided once.

    Attributes:
        name: The cookie name.
        path: ``/v1/exercise``. The cookie is a pointer into this product's own
            routes and is sent nowhere else, so a static file, a health probe,
            or any future path on the same host never receives it.
        http_only: Always ``True``. The token is not a value any script needs —
            design spec §15's ``localStorage`` mirror is the *team number* and
            the front end's own record that it has entered, which is CE-MOUNT's
            work, not a copy of this token.
        same_site: ``lax``. The first of the two cross-site protections; see
            :data:`EXERCISE_REQUEST_HEADER` for the second. ``strict`` was
            considered and rejected: a team following a link to the exercise
            from the course page would arrive logged out of its own workspace,
            which in a classroom reads as the site being broken.
        secure: Whether the cookie is withheld from a plain ``http`` request.
            Decided by ``SMARTMATCH_EXERCISE_COOKIE_SECURE`` when the
            deployment sets it, and otherwise by a *fallback* rule: off in
            ``dev``, on in every other edition.

            The fallback is a guess and is named as one. ``edition`` answers
            "which deployment is this", not "is this served over TLS", and the
            two come apart exactly where it matters: the pilot VM is reached
            over HTTPS while its compose file pins ``SMARTMATCH_EDITION=dev``,
            so the classroom cookie would have gone over the wire without
            ``Secure``. A deployment that knows the answer says so; ``true``
            belongs on any TLS host. Pinning ``True`` unconditionally is not
            the fix, because a ``Secure`` cookie is simply not stored over
            plain ``http`` and local development would break instead.
    """

    name: str
    path: str
    http_only: bool
    same_site: Literal["lax", "strict", "none"]
    secure: bool


def workspace_cookie_policy(
    settings: Annotated[Settings, Depends(get_settings)],
) -> WorkspaceCookiePolicy:
    """The cookie flags for this deployment. See :class:`WorkspaceCookiePolicy`.

    ``exercise_cookie_secure`` is honoured when set — including when it is set
    to ``False``, which is a deployment saying "this really is plain HTTP"
    rather than a value to second-guess. ``None`` falls back to the edition
    rule, which is documented as a guess on the attribute above.
    """
    configured = settings.exercise_cookie_secure
    return WorkspaceCookiePolicy(
        name=WORKSPACE_COOKIE_NAME,
        path="/v1/exercise",
        http_only=True,
        same_site="lax",
        secure=configured if configured is not None else settings.edition is not Edition.DEV,
    )


#: The annotation a handler writes to get the cookie flags.
CookiePolicy = Annotated[WorkspaceCookiePolicy, Depends(workspace_cookie_policy)]

#: The same flags object under the name the instructor half reads by.
#:
#: One dataclass for both exercise cookies, deliberately: ``http_only``,
#: ``same_site`` and ``secure`` are answers to questions about *this
#: deployment*, and two structures would be two places for them to drift. What
#: differs between the two cookies is the ``name`` and the ``path``, which is
#: exactly what the two factory functions set.
ExerciseCookiePolicy = WorkspaceCookiePolicy


def instructor_cookie_policy(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ExerciseCookiePolicy:
    """The instructor session cookie's flags (design spec §14).

    Every flag is the workspace cookie's, read from the same settings, with two
    differences:

    * **the name**, so the two cookies cannot be confused for one another, and
    * **the path**, ``/v1/exercise/instructor`` rather than ``/v1/exercise``.
      The narrower scope is the point: a browser sitting on a team's matching
      screen sends the workspace cookie and *not* this one, so the instructor's
      session is not attached to thirty ordinary requests a lesson, and a
      handler on a team route could not read it even if one tried.

    ``SameSite=Lax`` and the ``X-Exercise-Request`` header still both apply —
    this cookie is the one whose forgery would matter most.

    **And a third difference, on ``Secure``, which is the one that matters.**
    The workspace cookie falls back to the edition when
    ``SMARTMATCH_EXERCISE_COOKIE_SECURE`` is unset: off in ``dev``, on
    elsewhere. That fallback is documented as a guess, and on the pilot VM it
    guesses **wrong** — the site is served over HTTPS while
    ``docker-compose.vm.yml`` pins ``SMARTMATCH_EDITION=dev``, so an unset
    variable would have sent the instructor's session cookie over the wire
    without ``Secure``.

    A team's workspace token is a pointer to made-up rows and every participant
    in the room is handed one. This cookie is the only credential in the
    product. They do not deserve the same default, so this one **defaults to
    ``True``** and is turned off only by a deployment saying ``false``
    explicitly — a statement of fact about plain HTTP, not a value to
    second-guess.

    The cost, named rather than discovered: **local development over plain
    ``http`` must set ``SMARTMATCH_EXERCISE_COOKIE_SECURE=false``** to use the
    instructor page at all, because a browser does not store a ``Secure``
    cookie on an ``http`` origin. That is the right way round — the failure is
    immediate and local, where the old default's failure was silent and in a
    classroom.

    The workspace cookie's own behaviour is deliberately unchanged.
    """
    workspace = workspace_cookie_policy(settings)
    configured = settings.exercise_cookie_secure
    return ExerciseCookiePolicy(
        name=INSTRUCTOR_COOKIE_NAME,
        path="/v1/exercise/instructor",
        http_only=workspace.http_only,
        same_site=workspace.same_site,
        secure=configured if configured is not None else True,
    )


#: The annotation an instructor handler writes to get its cookie's flags.
InstructorCookiePolicy = Annotated[ExerciseCookiePolicy, Depends(instructor_cookie_policy)]


@dataclass(frozen=True, slots=True)
class ConfiguredPasscode:
    """This deployment's instructor passcode, or the absence of one.

    A one-field wrapper rather than a bare ``str | None``, for two reasons that
    both matter more than the extra line:

    * ``repr=False``. This object reaches a handler's local scope, and a
      default ``repr`` is what a log line, an assertion message and a debugger
      transcript print — the same argument
      :class:`~smartmatch_domain.exercise.layout.ParsedProfile` makes for the
      withheld column, applied to the one credential in this product.
    * The door's export check walks the *type* behind every annotation in
      ``__all__`` and demands it come from a permitted module. A bare
      ``str | None`` answers ``types`` — the module of every union — so
      admitting it would admit ``str | ResolvedPrincipal`` too. A named type
      from this module answers this module.
    """

    value: str | None = field(repr=False)


def get_instructor_passcode(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ConfiguredPasscode:
    """This deployment's instructor passcode, or ``None`` if it has none.

    OQ-CE-07 (closed 2026-09-25): one environment variable, set per
    deployment, ``SMARTMATCH_EXERCISE_INSTRUCTOR_PASSCODE``, shared out of band
    and rotated by changing the value.

    ``None`` covers both *unset* and *set to something unusable* — blank, or
    shorter than
    :data:`~smartmatch_domain.exercise.instructor_session.MINIMUM_INSTRUCTOR_PASSCODE_LENGTH`.
    The two are one answer on purpose: the login's behaviour is the same
    refusal either way, so a caller cannot learn from the response whether the
    variable is set.

    **Fail closed, and not at boot.** Unlike
    ``SMARTMATCH_EXERCISE_WORKSPACE_SECRET``, a missing passcode does not stop
    the process: the exercise's team-facing routes are the product and they
    work without an instructor page, so refusing to boot would take the
    classroom down over a screen only Ann uses. What it must never do is open
    the door — a deployment with no passcode serves an instructor login that
    refuses every attempt, which is the shut door, not the missing one.

    **Stripped here, once.** ``usable_passcode`` returns the value that will be
    compared rather than a verdict about the value that was read, which is what
    keeps "long enough to be usable" and "what a person has to type" the same
    string. A trailing newline is the ordinary way a value leaves an ``.env``
    file, and the earlier version of this function measured the stripped length
    and then stored the raw value — a configured passcode that could never
    match, reported to the instructor as simply wrong.
    """
    stored = settings.exercise_instructor_passcode
    raw = stored.get_secret_value() if stored is not None else None
    return ConfiguredPasscode(value=usable_passcode(raw))


#: The annotation the login handler writes to get the configured passcode.
InstructorPasscode = Annotated[ConfiguredPasscode, Depends(get_instructor_passcode)]


def require_instructor_session(
    instructor_cookie: Annotated[str | None, Cookie(alias=INSTRUCTOR_COOKIE_NAME)] = None,
    secret: str = Depends(get_workspace_secret),
) -> None:
    """Refuse an instructor request whose cookie is not a live session.

    One refusal for every way of not having one — no cookie, a forged
    signature, an edited expiry, a session minted under a secret that has since
    been rotated, an expired one, or a team's workspace cookie pasted in — so
    the route cannot be used to tell a real session from an invented one.

    Declared as a router-level dependency rather than a handler parameter, so
    it cannot be dropped by editing a signature, and it yields **nothing**:
    there is no principal here, no account, and no identity to hand a handler
    (ADR-0025 D1). What it establishes is that the passcode was presented, and
    that is the whole of what the instructor page knows about its caller.

    Raises:
        ExerciseError: 401, when the cookie is absent or is not a live session.
    """
    if instructor_cookie and instructor_session_is_live(
        instructor_cookie, secret=secret, now=utc_now()
    ):
        return
    raise ExerciseError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code="exercise_instructor_session_required",
        message="Enter the instructor passcode to open this page.",
    )


def get_dataset_repository() -> ExerciseDatasetRepository:
    """The one repository an exercise router may reach datasets through."""
    return ExerciseDatasetRepository()


#: The annotation a handler writes to get :class:`ExerciseDatasetRepository`.
DatasetRepository = Annotated[ExerciseDatasetRepository, Depends(get_dataset_repository)]


def get_instructor_repository() -> ExerciseInstructorRepository:
    """The one repository the instructor routes reach their cross-team rows through.

    Separate from :func:`get_workspace_repository` because the statements
    behind it are: they span teams, they change a dataset-wide setting, and
    they move workspaces. A team's own route takes the workspace repository and
    therefore cannot reach any of them.
    """
    return ExerciseInstructorRepository()


#: The annotation a handler writes to get :class:`ExerciseInstructorRepository`.
InstructorRepository = Annotated[ExerciseInstructorRepository, Depends(get_instructor_repository)]


def get_settings_repository() -> ExerciseSettingsRepository:
    """The one repository a team's routes reach their saved weightings through.

    Separate from :func:`get_team_view_repository` although the two share a
    module: they answer different questions, and a route that ranks a list has
    no business holding a handle that can write a settings row.
    """
    return ExerciseSettingsRepository()


#: The annotation a handler writes to get :class:`ExerciseSettingsRepository`.
SettingsRepository = Annotated[ExerciseSettingsRepository, Depends(get_settings_repository)]


def get_results_repository() -> ExerciseResultsRepository:
    """The one repository a team's routes reach design spec §9-§13 through.

    Separate from :func:`get_settings_repository` and
    :func:`get_team_view_repository` because it answers a different question and
    because it is the only handle in the exercise that can write a result run, an
    asking choice or an overlay row. A route that ranks a list has no business
    holding it.

    It is also the handle behind which the refresh's card copy happens — inside
    ``apply_refresh``, through ``load_simulation_profiles``, and never in a value
    a router holds (ADR-0025 D6).
    """
    return ExerciseResultsRepository()


#: The annotation a handler writes to get :class:`ExerciseResultsRepository`.
ResultsRepository = Annotated[ExerciseResultsRepository, Depends(get_results_repository)]


def get_team_view_repository() -> ExerciseTeamViewRepository:
    """The one repository a team's routes read *their own view* of profiles through.

    Design spec §2's ``base row ⟕ overlay``. The read behind it projects through
    ``exercise_profile_public_columns()``, so no route reached from here can
    serve the withheld column (ADR-0025 D6); the simulation loader that does
    read it is on ``ExerciseDatasetRepository`` and is not reachable from a
    matching route.
    """
    return ExerciseTeamViewRepository()


#: The annotation a handler writes to get :class:`ExerciseTeamViewRepository`.
TeamViewRepository = Annotated[ExerciseTeamViewRepository, Depends(get_team_view_repository)]


def workspace_token_for(*, secret: str, workspace: ExerciseWorkspace) -> str:
    """The cookie value addressing ``workspace``.

    A one-line wrapper so that a router never imports the token arithmetic and
    never sees a workspace id and a secret in the same expression. OQ-CE-08
    (closed 2026-09-25): one shared workspace per team number, as built.
    """
    return derive_workspace_token(secret=secret, workspace_id=workspace.id)


def get_active_dataset(session: ExerciseSession) -> ExerciseDatasetSummary:
    """The dataset a team entering a number joins, or one plain sentence.

    409 rather than 404: the route exists, the request was well formed, and the
    answer is that the site is not ready yet — a state the instructor changes
    by uploading the file, not a state the team can fix by asking for something
    else.

    Raises:
        ExerciseError: 409, when no dataset has been uploaded.
    """
    dataset = active_dataset(session)
    if dataset is None:
        raise ExerciseError(
            status_code=status.HTTP_409_CONFLICT,
            code="exercise_no_dataset",
            message="The instructor has not loaded the student body yet.",
        )
    return dataset


#: The annotation a handler writes to require an uploaded dataset.
ActiveDataset = Annotated[ExerciseDatasetSummary, Depends(get_active_dataset)]


@dataclass(frozen=True, slots=True)
class MaybeDataset:
    """The newest uploaded dataset, or the fact that there is not one.

    A named wrapper rather than ``ExerciseDatasetSummary | None``, for
    :class:`ConfiguredPasscode`'s second reason — which is a real guard and not
    a style rule. The door's export check walks the type behind every
    annotation in ``__all__``, and a union answers ``types``: the module of
    *every* union. Admitting it here to allow this one would also admit
    ``ExerciseDatasetSummary | ResolvedPrincipal`` tomorrow. A named type from
    this module answers this module.
    """

    dataset: ExerciseDatasetSummary | None


def get_maybe_active_dataset(session: ExerciseSession) -> MaybeDataset:
    """The dataset a team entering a number would join, or the absence of one.

    The same question :func:`get_active_dataset` asks, without the refusal. A
    team route cannot do anything useful before a file exists, so 409 is the
    right answer there. The instructor's own screens are the place where "no
    file has been uploaded yet" is *information* — it is the state her next
    action changes — and a 409 would blank a page that should be telling her
    what to do next.

    Note what this is **not** for. It answers "which file is newest", never
    "which file are the teams in". Design spec §3 keeps those apart, and
    confusing them is exactly the defect the instructor routes were corrected
    for; the second question is
    ``ExerciseInstructorRepository.datasets_with_workspaces``.
    """
    return MaybeDataset(dataset=active_dataset(session))


#: The annotation an instructor handler writes to ask which dataset is newest
#: without refusing when there is none.
MaybeActiveDataset = Annotated[MaybeDataset, Depends(get_maybe_active_dataset)]


def get_current_workspace(
    session: ExerciseSession,
    repository: WorkspaceRepository,
    workspace_token: Annotated[str | None, Cookie(alias=WORKSPACE_COOKIE_NAME)] = None,
) -> ExerciseWorkspace:
    """The workspace this browser's cookie points at.

    One refusal for every way of not having one — no cookie, a cookie minted
    under a secret that has since been rotated, a cookie whose workspace was
    deleted, a cookie somebody typed — so the route cannot be used to tell a
    real workspace token from an invented one.

    A cookie from a **previous dataset** is not one of those ways, and an
    earlier draft of this docstring said it was. Design spec §3: existing
    workspaces keep pointing at their old dataset until the instructor
    re-points them, and a re-point resets every team. So a team holding a
    cookie from before an upload keeps working, in its old dataset, and that is
    the specified behaviour rather than a gap. See the repository's
    ``find_by_token_hash`` for why the lookup is deliberately not scoped to the
    active dataset.

    The status is 401 and the code is the exercise's own. It is deliberately
    **not** the CBA ``unauthenticated`` code and carries no
    ``WWW-Authenticate`` header: there is no authentication scheme in this
    product to name, and naming one would advertise a login that does not
    exist. What the sentence says instead is the thing the team can actually
    do, which is enter its team number.

    Raises:
        ExerciseError: 401, when the cookie is absent or names no workspace.
    """
    if workspace_token:
        workspace = repository.find_by_token_hash(
            session, token_hash=hash_workspace_token(workspace_token)
        )
        if workspace is not None:
            return workspace
    raise ExerciseError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code="exercise_workspace_required",
        message="Enter your team number to open your team's workspace.",
    )


#: The annotation a handler writes to require a team's workspace.
CurrentWorkspace = Annotated[ExerciseWorkspace, Depends(get_current_workspace)]


def require_exercise_request_header(
    x_exercise_request: Annotated[str | None, Header(alias=EXERCISE_REQUEST_HEADER)] = None,
) -> None:
    """Refuse a state-changing exercise request that no exercise page sent.

    See :data:`EXERCISE_REQUEST_HEADER` for why this exists and what it is the
    second half of. The value is not checked beyond being present and
    non-empty: the protection is that a cross-origin page cannot set the header
    at all, not that it could not guess a value.

    Raises:
        ExerciseError: 403, when the header is missing or empty.
    """
    if not (x_exercise_request and x_exercise_request.strip()):
        raise ExerciseError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="exercise_request_header_required",
            message="This request did not come from the exercise site.",
        )
