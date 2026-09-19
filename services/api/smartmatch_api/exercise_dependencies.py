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

The cookie
==========

Design spec §15: "the server row is the truth; the cookie is a pointer". The
value is an opaque token derived in
:mod:`smartmatch_domain.exercise.workspace_token` (PLACEHOLDER, OQ-CE-08); the
server stores only its SHA-256. This module owns the cookie's *flags*, in one
place, because a cookie set with the right flags on one route and the wrong
ones on another is a cookie with the wrong flags.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated, Final, Literal

from fastapi import Cookie, Depends, Header, Request, status
from smartmatch_domain.exercise.workspace_token import (
    derive_workspace_token,
    hash_workspace_token,
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

__all__ = [
    "EXERCISE_REQUEST_HEADER",
    "WORKSPACE_COOKIE_NAME",
    "ActiveDataset",
    "CookiePolicy",
    "CurrentWorkspace",
    "ExerciseDatasetSummary",
    "ExerciseSession",
    "ExerciseWorkspace",
    "WorkspaceCookiePolicy",
    "WorkspaceRepository",
    "WorkspaceSecret",
    "get_active_dataset",
    "get_current_workspace",
    "get_exercise_session",
    "get_workspace_repository",
    "get_workspace_secret",
    "require_exercise_request_header",
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
        secure: ``True`` in every edition but ``dev``. A ``Secure`` cookie is
            simply not stored over plain ``http``, so pinning it ``True``
            everywhere would break the one environment that is reached over
            ``http://localhost`` — and pinning it ``False`` everywhere would
            put the classroom's cookie on the wire. It follows the edition,
            which is the deployment fact that answers "is this served over
            TLS".
    """

    name: str
    path: str
    http_only: bool
    same_site: Literal["lax", "strict", "none"]
    secure: bool


def workspace_cookie_policy(
    settings: Annotated[Settings, Depends(get_settings)],
) -> WorkspaceCookiePolicy:
    """The cookie flags for this deployment. See :class:`WorkspaceCookiePolicy`."""
    return WorkspaceCookiePolicy(
        name=WORKSPACE_COOKIE_NAME,
        path="/v1/exercise",
        http_only=True,
        same_site="lax",
        secure=settings.edition is not Edition.DEV,
    )


#: The annotation a handler writes to get the cookie flags.
CookiePolicy = Annotated[WorkspaceCookiePolicy, Depends(workspace_cookie_policy)]


def workspace_token_for(*, secret: str, workspace: ExerciseWorkspace) -> str:
    """The cookie value addressing ``workspace``.

    A one-line wrapper so that a router never imports the token arithmetic and
    never sees a workspace id and a secret in the same expression. PLACEHOLDER
    (OQ-CE-08): the derivation is what changes if Ann answers "per tab".
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


def get_current_workspace(
    session: ExerciseSession,
    repository: WorkspaceRepository,
    workspace_token: Annotated[str | None, Cookie(alias=WORKSPACE_COOKIE_NAME)] = None,
) -> ExerciseWorkspace:
    """The workspace this browser's cookie points at.

    One refusal for every way of not having one — no cookie, a cookie from a
    previous dataset, a cookie minted under a rotated secret, a cookie somebody
    typed — so the route cannot be used to tell a real workspace token from an
    invented one.

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
