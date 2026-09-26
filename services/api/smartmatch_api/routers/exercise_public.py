"""The class exercise's public surface (ADR-0025 D1).

Ann Wang's Spring 2027 class exercise is a **no-login** site over made-up
profiles. This module is its entire public API surface today: one route that
answers what a front end needs to know before anything exists.

Unauthenticated by design, and by construction
==============================================
There is no principal here, and no way to add one. The exercise routers are
mounted only when ``Capability.CLASS_EXERCISE`` is enabled, which happens only
under ``ProductScope.CLASS_EXERCISE`` — a scope that mounts none of the
authenticated CBA routers, so ``get_current_principal`` is *unreachable* in
this process rather than bypassed in this module. ADR-0025 D9 rejected the
alternative (a per-route bypass inside the CBA scope) precisely because it
would put a no-auth route in the same process as real records.

This module accordingly imports no ``smartmatch_authz``, no
``smartmatch_api.dependencies``, no ``routers/auth.py``, and no repository. The
rule is enforced three ways rather than trusted once: the import-linter
contract "Class exercise routers carry no principal or tenancy" in
``pyproject.toml`` (``make imports``), a source walk in
``tests/unit/test_exercise_public_router.py``, and the absence of any import
below that a reader would have to take on faith.

What is deliberately not here
=============================
The exercise's real screens — team workspaces, saved settings, the ranked
list, the simulated results, downloads, and the passcode-gated instructor page
(design spec §§5-15) — each need an ``exercise_`` table, and those tables are
another track's migration. Routes that cannot answer are worse than absent
routes: a front end would code against a shape and get a ``500``. So:

* ``exercise_instructor.router`` (``/v1/exercise/instructor``, passcode
  session) is **track CE-INSTRUCTOR's**. It is named in the design spec's §1
  declaration list and is deliberately not stubbed here — a route mounted
  before its passcode machinery exists is an unprotected route, not a
  placeholder.
* the workspace, matching, results, and ingest routes are tracks
  CE-WORKSPACE, CE-SIMULATION, and CE-INGEST's.

None of them is blocked on this module beyond adding its router to the same
declaration table this one is in.

What this route does answer
===========================
Three facts that are true before the first upload, that a front end needs to
render its entry screen, and that no table supplies:

* the scope it is talking to, so a page served by a misconfigured deployment
  can say so rather than silently behaving like the CBA product;
* the team numbers the entry screen may offer — six, from the requirements
  document's "Getting in" row, read from
  :data:`smartmatch_domain.exercise.EXERCISE_TEAM_NUMBERS`;
* that every row this product will ever show is made up, which every screen
  must mark (design spec §16).

It deliberately does **not** answer the invite limit, the default weights, the
"asking for more" percentages, the simulation coefficients, or the opening
screen's license line. Each of those belongs to a register row —
``OQ-CE-02``/``OQ-CE-03``/``OQ-CE-04``/``OQ-CE-09``, all four now closed — or is
a per-dataset stored value, and each lives with the code
that owns it (the domain's constants, or the opening screen's license line)
rather than in this contract.

ADR-0025 D8 applies to every response here: the exercise shows rank, the
weights a team set, and one reason per name. No field on any model in this
module is named like a score, a percentage, or a confidence, and a test asserts
that of every model here rather than of the one that exists today.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from smartmatch_domain.exercise import EXERCISE_TEAM_NUMBERS
from smartmatch_domain.product_scope import ProductScope

#: The exercise's public router. Named ``router`` (not ``public_router``) for
#: the reason ``outreach`` needs the second name and this module does not:
#: there is no authenticated sibling here to distinguish it from. Every route
#: this module will ever hold is unauthenticated, which is a property of the
#: *module*, stated in its docstring, rather than of one router inside it.
#:
#: Deliberately a bare assignment rather than an annotated one: the route ledger
#: in ``tests/authz/test_policy_matrix.py`` reads router prefixes out of the AST
#: and matches ``name = APIRouter(...)``, so an annotation here would make this
#: module's routes invisible to the completeness check that requires every
#: unauthenticated route to be declared with a reason. Being seen by that check
#: is worth more than the annotation.
router = APIRouter(prefix="/v1/exercise", tags=["class-exercise"])


class ExerciseScopeFacts(BaseModel):
    """What is true about this deployment before any data file is uploaded."""

    model_config = ConfigDict(extra="forbid")

    scope: str = Field(
        description=(
            "The product scope serving this response. Always `class_exercise`: "
            "a process in any other scope does not mount this route."
        ),
    )
    team_numbers: list[int] = Field(
        description=(
            "The team numbers the entry screen may offer, in the order to show "
            "them. Fixed by the requirements document, not configurable."
        ),
    )
    synthetic_data: bool = Field(
        description=(
            "Always true. Every profile and event in this scope is made up; no "
            "real record can be served by this process. Screens mark it."
        ),
    )


@router.get(
    "",
    response_model=ExerciseScopeFacts,
    summary="Facts about the class-exercise scope",
)
def exercise_scope_facts() -> ExerciseScopeFacts:
    """Report the scope, the team numbers, and the synthetic-data marker.

    **Unauthenticated by design** — see this module's docstring. Reads nothing,
    writes nothing, and touches no database: every value it returns is a
    constant of the scope rather than a fact about a dataset, which is why it
    can answer correctly in a process with no ``exercise_`` tables yet.
    """
    return ExerciseScopeFacts(
        scope=ProductScope.CLASS_EXERCISE.value,
        team_numbers=list(EXERCISE_TEAM_NUMBERS),
        synthetic_data=True,
    )
