"""Team workspaces for the class exercise (design spec §15, requirements "Getting in").

A team enters a number 1-6 and its 4-digit code (issue #413: the site is
public, so the number alone no longer opens a team's work; the instructor page
shows the six codes). The server creates or returns *the* workspace for
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

* **A per-route rate limit.** Wrong team codes are bounded instead, by
  :class:`~smartmatch_api.exercise_rate_limit.WrongCodeGuard`; the row count
  is capped by ``uq_exercise_team_workspace_dataset_team`` and the body by
  ``MaxBodySizeMiddleware``.
* **The ``localStorage`` mirror** design spec §15 names. That is the front
  end's copy of "this browser has entered team 4", and it is CE-MOUNT's work.
  Nothing here writes it and the token is never exposed to a script.
"""

from __future__ import annotations

import hmac
import logging
from typing import Final

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from smartmatch_domain.exercise import EXERCISE_TEAM_NUMBERS

from smartmatch_api.exercise_dependencies import (
    ActiveDataset,
    CookiePolicy,
    CurrentWorkspace,
    ExerciseSession,
    ExerciseWorkspace,
    ResultsRepository,
    TeamCodeRepository,
    WorkspaceRepository,
    WorkspaceSecret,
    require_exercise_request_header,
    workspace_token_for,
)
from smartmatch_api.exercise_errors import ExerciseError
from smartmatch_api.exercise_rate_limit import UNRESOLVED_CALLER_KEY, WrongCodeGuard
from smartmatch_api.routers.exercise_results_run import round_two_open
from smartmatch_api.utils import utc_now

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

_LOGGER = logging.getLogger(__name__)

#: Wrong team codes, per (team, client address), in this process (issue #413).
#: Module-level for the reason the instructor login limiter is.
_CODE_GUARD: Final[WrongCodeGuard] = WrongCodeGuard()

#: Student-facing sentences for the team code (issue #413; need Dr. Wang's OK).
WRONG_CODE_SENTENCE: Final[str] = "That code is not right for this team. Your instructor has it."
CODE_LOCKED_SENTENCE: Final[str] = "Too many wrong codes. Wait one minute, then try again."


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
    code: str = Field(
        max_length=16,
        description=(
            "The team's 4-digit code (issue #413). The instructor page shows it; "
            "a wrong one is refused, and five wrong in ten minutes lock entry "
            "for that team for a minute."
        ),
    )


class TeamWorkspaceView(BaseModel):
    """What a team sees about its own workspace.

    Four fields, and see the module docstring for the four that are absent.
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
            "How many names a ranked list may hold for this dataset (60 by "
            "default). The instructor page changes it; a team reads it."
        ),
    )
    round_two_open: bool = Field(
        description=(
            "True once the team has its Northline (round-one) results. Until "
            "then every round-two write is refused with "
            "``exercise_round_two_locked``."
        ),
    )


def _view(workspace: ExerciseWorkspace, *, round_two_open: bool) -> TeamWorkspaceView:
    """The one place a workspace becomes a response.

    Field by field rather than by ``model_validate``: the repository dataclass
    carries the workspace id, and a from-attributes conversion would publish
    whatever a later track adds to it.
    """
    return TeamWorkspaceView(
        team_number=workspace.team_number,
        dataset_label=workspace.dataset_label,
        invite_limit=workspace.invite_limit,
        round_two_open=round_two_open,
    )


def _open(
    session: ExerciseSession, results: ResultsRepository, workspace: ExerciseWorkspace
) -> bool:
    return round_two_open(session, results, workspace=workspace)


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


def _check_team_code(
    request: Request,
    session: ExerciseSession,
    codes: TeamCodeRepository,
    *,
    team_number: int,
    given: str,
) -> None:
    """Refuse a wrong team code, and every attempt while the team is locked out.

    Compared as bytes with :func:`hmac.compare_digest`, so the time taken does
    not leak how many digits matched. A team with no code row is never
    entered. Neither code is ever logged.

    Raises:
        ExerciseError: 429 while locked out, 401 for a wrong code.
    """
    stored = codes.code_for(session, team_number=team_number)
    correct = stored is not None and hmac.compare_digest(given.strip().encode(), stored.encode())
    client = request.client
    key = f"{team_number}:{client.host if client and client.host else UNRESOLVED_CALLER_KEY}"
    if not _CODE_GUARD.attempt(key, correct=correct, now=utc_now()):
        _LOGGER.warning("exercise team code locked out for team %s", team_number)
        raise ExerciseError(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="exercise_team_code_locked",
            message=CODE_LOCKED_SENTENCE,
        )
    if not correct:
        _LOGGER.info("exercise team code refused for team %s", team_number)
        raise ExerciseError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="exercise_team_code_wrong",
            message=WRONG_CODE_SENTENCE,
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
    request: Request,
    response: Response,
    session: ExerciseSession,
    codes: TeamCodeRepository,
    repository: WorkspaceRepository,
    dataset: ActiveDataset,
    secret: WorkspaceSecret,
    policy: CookiePolicy,
    results: ResultsRepository,
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

    **The two repository calls below are one atomic step**, and the order of
    the statements in this handler is load-bearing rather than tidy: the same
    ``session``, no commit between them, so the membership lock
    ``entry_dataset_for`` takes is still held when ``get_or_create_workspace``
    inserts. A commit in between would release it and reopen the window a
    re-point races through — the team's row moves after the data file is
    chosen and before it is used, and the entry mints a second workspace on the
    file the team has just left.

    Commits explicitly — ``get_exercise_session`` rolls back on the way out, so
    a write that is not committed here is a write that did not happen, and the
    commit is also what releases the lock.

    Raises:
        ExerciseError: 409 when no dataset has been uploaded (raised by the
            ``dataset`` dependency), 422 when the number is outside 1-6, 401
            for a wrong team code, 429 while that team is locked out, 403
            when the request carries no ``X-Exercise-Request`` header.
    """
    if payload.team_number not in EXERCISE_TEAM_NUMBERS:
        raise ExerciseError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="exercise_team_number_unknown",
            message="Pick a team number from 1 to 6.",
        )
    _check_team_code(request, session, codes, team_number=payload.team_number, given=payload.code)
    dataset_id = repository.entry_dataset_for(session, team_number=payload.team_number)
    # Defensive, and **unreachable today** (review round 2, F5). Since PR #188
    # resolved the newest data file inside `entry_dataset_for`'s lock, `None`
    # means only "no data file exists at all" — and the `dataset` dependency has
    # already answered that with a 409 before this line runs. Nothing in the
    # application deletes an `exercise_dataset` row, so there is no window in
    # which the two can disagree. The branch is kept rather than removed because
    # what it costs is one comparison and what it buys, if a delete ever lands,
    # is the plain 409 sentence instead of a driver error from an insert handed
    # `dataset_id=None`. An earlier version of this comment justified it with a
    # delete that does not exist; that reason was false and is gone.
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
    return _view(workspace, round_two_open=_open(session, results, workspace))


@router.get(
    "/workspaces/current",
    response_model=TeamWorkspaceView,
    summary="The workspace this browser is in",
)
def read_current_workspace(
    workspace: CurrentWorkspace, session: ExerciseSession, results: ResultsRepository
) -> TeamWorkspaceView:
    """What the cookie points at, or one sentence saying to enter a team number.

    The reload case, and the second-tab case: both arrive here with the same
    cookie and both get the same workspace: one shared workspace per team,
    made observable.

    Raises:
        ExerciseError: 401 when the cookie is absent or names no workspace.
    """
    return _view(workspace, round_two_open=_open(session, results, workspace))
