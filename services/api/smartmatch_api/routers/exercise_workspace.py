"""Team workspaces for the class exercise (design spec §15, requirements "Getting in").

A team enters a number 1-6. The server creates or returns *the* workspace for
that team, sets an opaque pointer to it in an httpOnly cookie, and a reload —
or a second tab, or the laptop next to it — gets the same workspace back. No
login, no account, no principal, and nothing in this module that could resolve
one.

Two routes
==========

* ``POST /v1/exercise/workspaces`` — enter a team number. Creates or returns.
* ``GET /v1/exercise/workspaces/current`` — what the cookie points at.

Reset is not one of them (owner ruling, 2026-09-19)
===================================================

Design spec §11's per-team reset used to live here as
``POST /v1/exercise/workspaces/current/reset``, addressed by the cookie alone.
The cookie is obtainable by anyone who types the team's number — that is what
the product is (OQ-CE-08's shared-per-team default; the requirements' "Getting
in" row: no login, a team enters its number) — so a destructive, irreversible
action was reachable by a class participant who entered somebody else's number,
and Session 2 has no backup.

The owner ruled on 2026-09-19 that per-team reset moves **behind the instructor
passcode**. ``POST /v1/exercise/instructor/workspaces/{team_number}/reset`` is
now the only reset, and the statements it runs are unchanged — it calls the
same ``ExerciseWorkspaceRepository.reset_team``. The path above is gone rather
than deprecated, so a request to it is answered by the router as the absence it
is.

Which data file an entry lands in (owner ruling, 2026-09-19)
============================================================

Not "the newest upload". A team that already has a workspace re-enters *that*
workspace, on whatever data file it is on; only an instructor re-point moves a
team. See :func:`enter_team_workspace` and
``ExerciseWorkspaceRepository.entry_dataset_for``.

What a response may carry, and what it may never
================================================

Three fields: the team number, the dataset's label, and the invite limit. Every
one of them is something the team's own screen shows.

Not the seed (design spec §11's chance element — publishing it would let a team
predict its own simulated results and, with another team's, theirs), not the
token, not the token's hash, and not the workspace id. The id is absent for a
specific reason rather than out of tidiness: the cookie token is derived from
it, so an id in a response body is one secret away from being a session, and
"the secret is not in the response" is a much weaker sentence than "neither
half is". ``tests/unit/test_exercise_workspace_router.py`` walks every model in
this module and refuses all four names, plus ``hidden_true_interests``
(ADR-0025 D6) and anything score-shaped (D8).

Why the team number is validated in the handler
===============================================

``EXERCISE_TEAM_NUMBERS`` is the source of the range, and the obvious place to
enforce it is a pydantic validator. A validator cannot deliver the *sentence*,
though: ``smartmatch_api.errors._describe_validation_error`` deliberately
replaces the message of any ``value_error`` with "The submitted value was
rejected by a validation rule", because a validator-authored message may
interpolate the value it rejected and that value may be a secret. The rule is
right and the exercise is not an exception to it — so the check is a handler
statement that raises :class:`~smartmatch_api.exercise_errors.ExerciseError`
with the sentence a class participant should read. A body whose
``team_number`` is not a whole number at all never reaches the handler and gets
pydantic's own 422, which is also the correct answer.

CSRF
====

This application had no cookie before this module and therefore no CSRF
machinery to reuse; the pilot login is a bearer exchange, which a cross-site
form cannot forge. A cookie can be, so the one state-changing route here
requires ``X-Exercise-Request`` on top of ``SameSite=Lax`` — see
:data:`~smartmatch_api.exercise_dependencies.EXERCISE_REQUEST_HEADER`.

Not in this module
==================

* **Rate limiting** (OQ-CE-06, owner Danny). Deliberately not built here. Two
  bounds already hold without it: ``uq_exercise_team_workspace_dataset_team``
  caps this product at six workspace rows per dataset no matter how many times
  anybody posts, and ``MaxBodySizeMiddleware`` caps the body ahead of routing.
* **The ``localStorage`` mirror** design spec §15 names. That is the front
  end's copy of "this browser has entered team 4", and it is CE-MOUNT's work.
  Nothing here writes it and the token is never exposed to a script.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict, Field
from smartmatch_domain.exercise import EXERCISE_TEAM_NUMBERS

from smartmatch_api.exercise_dependencies import (
    ActiveDataset,
    CookiePolicy,
    CurrentWorkspace,
    ExerciseSession,
    ExerciseWorkspace,
    WorkspaceRepository,
    WorkspaceSecret,
    require_exercise_request_header,
    workspace_token_for,
)
from smartmatch_api.exercise_errors import ExerciseError

#: A bare assignment, not an annotated one, for ``exercise_public.router``'s
#: reason: the route ledger in ``tests/authz/test_policy_matrix.py`` reads
#: router prefixes out of the AST and matches ``name = APIRouter(...)``.
router = APIRouter(prefix="/v1/exercise", tags=["class-exercise"])

#: Applied to every state-changing route in this module — one, since the reset
#: moved behind the instructor passcode. Declared as a list rather than inline
#: so a second such route cannot drift from the first, and passed as a
#: ``dependencies`` entry rather than as a parameter so it cannot be dropped by
#: editing a signature.
_STATE_CHANGING = [Depends(require_exercise_request_header)]


class EnterTeamRequest(BaseModel):
    """The entry screen's whole input: a team number."""

    model_config = ConfigDict(extra="forbid")

    team_number: int = Field(
        description=(
            "The team's number. One of 1-6, fixed by the requirements "
            "document's `Getting in` row and not configurable. Entering a "
            "number another team has already entered opens *that* team's "
            "workspace, which is the point: a team is its number."
        ),
    )


class TeamWorkspaceView(BaseModel):
    """What a team sees about its own workspace.

    Three fields, and see the module docstring for the four that are absent.
    """

    model_config = ConfigDict(extra="forbid")

    team_number: int = Field(description="The team number this workspace belongs to.")
    dataset_label: str = Field(
        description=(
            "The label of the loaded student body, so a screen can say which "
            "file it is working from. Every row in it is made up."
        ),
    )
    invite_limit: int = Field(
        description=(
            "How many names a ranked list may hold for this dataset (30 by "
            "default). The instructor page changes it; a team reads it."
        ),
    )


def _view(workspace: ExerciseWorkspace) -> TeamWorkspaceView:
    """The one place a workspace becomes a response.

    Field by field rather than by ``model_validate``: the repository dataclass
    carries the workspace id, and a from-attributes conversion would publish
    whatever a later track adds to it.
    """
    return TeamWorkspaceView(
        team_number=workspace.team_number,
        dataset_label=workspace.dataset_label,
        invite_limit=workspace.invite_limit,
    )


def _set_workspace_cookie(response: Response, *, policy: CookiePolicy, token: str) -> None:
    """Point this browser at a workspace.

    A session cookie — no ``max_age`` and no ``expires`` — so it dies with the
    browser. Nothing is lost when it does: the team re-enters its number and
    gets the same workspace back, because the workspace is identified by
    ``(dataset, team number)`` in the table and only addressed by the cookie.
    """
    response.set_cookie(
        key=policy.name,
        value=token,
        path=policy.path,
        httponly=policy.http_only,
        samesite=policy.same_site,
        secure=policy.secure,
    )


@router.post(
    "/workspaces",
    response_model=TeamWorkspaceView,
    status_code=status.HTTP_200_OK,
    dependencies=_STATE_CHANGING,
    summary="Enter a team number and open that team's workspace",
)
def enter_team_workspace(
    payload: EnterTeamRequest,
    response: Response,
    session: ExerciseSession,
    repository: WorkspaceRepository,
    dataset: ActiveDataset,
    secret: WorkspaceSecret,
    policy: CookiePolicy,
) -> TeamWorkspaceView:
    """Open *the* workspace for this team number, creating it if it is new.

    **Which data file it opens in is not "the newest upload"** (owner ruling,
    2026-09-19). A team that already has a workspace re-enters that workspace,
    on whatever file it is on; only an instructor re-point moves a team. A
    brand-new team joins the file the other teams are on, and the very first
    team of a lesson joins the newest upload because there is no classroom yet
    to join. The rule, with its tie-break for teams left on two files by rows
    written before the ruling, is
    ``ExerciseWorkspaceRepository.entry_dataset_for``; the ``dataset``
    dependency here is the fallback and the source of the 409 below.

    Before the ruling, a reload after an upload handed the team a second, empty
    workspace on the new file — its work apparently gone — while design spec §3
    says in as many words that uploading moves nobody.

    **200, not 201, in both cases.** A team entering its number is opening its
    workspace, not creating a resource; answering 201 the first time and 200
    afterwards would make the response tell whoever asked whether anyone on
    that team had been there yet, which is a fact about another team.

    Race-safe in the repository rather than here: two laptops on team 3 both
    reach ``get_or_create_workspace``, one row exists afterwards because the
    unique constraint admits one, and both get it.

    Commits explicitly — ``get_exercise_session`` rolls back on the way out, so
    a write that is not committed here is a write that did not happen.

    Raises:
        ExerciseError: 409 when no dataset has been uploaded (raised by the
            ``dataset`` dependency), 422 when the number is outside 1-6, 403
            when the request carries no ``X-Exercise-Request`` header.
    """
    if payload.team_number not in EXERCISE_TEAM_NUMBERS:
        raise ExerciseError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="exercise_team_number_unknown",
            message="Pick a team number from 1 to 6.",
        )
    dataset_id = repository.entry_dataset_for(session, team_number=payload.team_number)
    workspace = repository.get_or_create_workspace(
        session,
        dataset_id=dataset_id if dataset_id is not None else dataset.id,
        team_number=payload.team_number,
        workspace_secret=secret,
    )
    session.commit()
    _set_workspace_cookie(
        response, policy=policy, token=workspace_token_for(secret=secret, workspace=workspace)
    )
    return _view(workspace)


@router.get(
    "/workspaces/current",
    response_model=TeamWorkspaceView,
    summary="The workspace this browser is in",
)
def read_current_workspace(workspace: CurrentWorkspace) -> TeamWorkspaceView:
    """What the cookie points at, or one sentence saying to enter a team number.

    The reload case, and the second-tab case: both arrive here with the same
    cookie and both get the same workspace, which is OQ-CE-08's default
    behaviour made observable.

    Raises:
        ExerciseError: 401 when the cookie is absent or names no workspace.
    """
    return _view(workspace)
