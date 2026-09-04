"""The match-run command resource and its read (plan cards M8b, M9, M10).

Architecture v1.1 §1.11 lists ``/match-runs`` among the explicit command
resources that replace the v1.0 generic job endpoint, and
``routers/imports.py`` records why it did not ship alongside the import
resource: "match-runs on G1 (factor registry)". Gate G1 closed on 2026-09-03
(``docs/plans/workshops/g1-workshop-output-worksheet.md``, ratified by the
named program owner), card M6j flipped
:data:`~smartmatch_domain.factor_registry.REGISTRY_STATUS` to ``"approved"``
with both approved factors actually implemented, and card M8a landed the
immutable ``match_run`` snapshot. This module is what those three make
admissible: two operations, one write and one read.

* ``POST /v1/units/{unit_id}/match-runs`` — score a submitted candidate pool
  and **enqueue the existing durable command**. See :func:`create_match_run`.
* ``GET /v1/units/{unit_id}/match-runs/{match_run_id}`` — the persisted
  snapshot, its shortlist, and the per-factor explanation behind every
  candidate. See :func:`read_match_run`.

## The write goes through the command path, not around it

Nothing here inserts a ``match_run`` row, and nothing here could: the table's
``job_id`` is a ``NOT NULL`` foreign key to ``job``, so a run without a durable
command behind it is unstorable by construction rather than by convention.
``smartmatch_persistence.match_runs`` is deliberately insert-only and its sole
caller is ``smartmatch_worker.handlers.handle_match_run_create``, already
registered on the worker's shipped command registry under
:data:`~smartmatch_domain.match_run.MATCH_RUN_COMMAND_TYPE`. This route submits
that command through :func:`~smartmatch_api.commands.submit_command` and
returns ``202``: nothing has been solved when it returns, and saying ``200``
would report success for work that has not started (v1.1 §3.6 N2).

## Why the API scores and the worker solves

The split is not arbitrary. **Scoring** is a pure function of evidence the
caller submits — ``smartmatch_domain.scoring.rank_candidates`` reads two factor
modules and the registry's normalized weights, touches no network, no provider
and no clock — and it has to happen here because
:class:`~smartmatch_domain.optimizer.PortfolioCandidate` refuses an unknown
utility rather than coercing it to ``0.0`` (ADR-0011). Somebody has to decide
what an unscorable candidate means before the pool reaches the solver, and the
M8a handler says explicitly that this "belongs to whoever assembled the pool".
That is this route, and its answer is in :func:`_partition_pool`: a candidate
whose evidence is incomplete is **excluded from the pool and reported**, never
entered at zero where it would sit below every measured candidate as though it
had been measured and found wanting.

**Solving** is the durable, possibly slow work whose result a coordinator acts
on, and v1.1 §1.6 puts every such write on the command path. So the request
records intent plus the evidence it scored, and the worker solves and snapshots.

## Where the shortlist comes from on the read

The M8a handler stores the run's pins and the solver's verdict but deliberately
**not** the selected professionals ("that shortlist is card M10's surface, it
has no table"). This card does not get to add one — it owns no migration — so
the read reconstructs the shortlist rather than inventing or storing it, and
only reconstructs it when the reconstruction is provably the same problem:

1. the candidate pool, the size and the seed come off the durable
   ``job.payload`` the command was accepted with — the same bytes the worker
   executed;
2. :func:`~smartmatch_domain.match_run.inputs_fingerprint` is recomputed over
   that pool with the **stored** weights and compared against the snapshot's
   ``inputs_hash``;
3. :func:`~smartmatch_domain.optimizer.solve_portfolio` — the same function the
   worker called, not a re-implementation of it — is run on the identical
   request, and its status is compared against the snapshot's stored
   ``portfolio_status``.

If any of those three disagrees, :attr:`MatchRunResponse.shortlist_available`
is ``false`` with a reason and the shortlist is empty. It is never
approximated. A shortlist that did not come from the recorded inputs is a
recommendation about a different problem, and showing one under this run's id
would be worse than showing none.

This is local, deterministic, bounded computation: no network call, no
provider, no LLM, and a pool capped at :data:`MAX_CANDIDATES`. The request path
still cannot reach out (``tests/unit/test_no_external_calls_on_request_path.py``
pins that structurally), and ``ALLOW_LIVE_PROVIDERS`` is neither consulted nor
relevant here.

## The presentation rules are ratified, not chosen here

The G1 worksheet's agenda item 1 settles all three, and
:mod:`smartmatch_domain.explanation` holds them so that this router imports
them rather than restating them: a shortlist of **2-3** candidates
(:data:`~smartmatch_domain.explanation.MIN_SHORTLIST_SIZE` /
:data:`~smartmatch_domain.explanation.MAX_SHORTLIST_SIZE`, enforced on the
request body, so a run that could only produce one name is refused at
submission), **no percentage anywhere** (a score is a bare number in
``[0.0, 1.0]``; nothing in this module or in the response models multiplies by
100 or formats a percent), and the label
:data:`~smartmatch_domain.explanation.SCORE_PROVENANCE_LABEL` —
"heuristic score" — carried on every scored object together with the registry
version that produced it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Annotated, Any, Final

import sqlalchemy as sa
from fastapi import APIRouter, Header, Path, status
from pydantic import BaseModel, Field
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_domain.explanation import (
    MAX_SHORTLIST_SIZE,
    MIN_SHORTLIST_SIZE,
    SCORE_PROVENANCE_LABEL,
    CandidateExplanation,
    ScoreState,
    explain_candidates,
    explanation_from_payload,
    explanation_to_payload,
)
from smartmatch_domain.factor_registry import (
    RegistryNotApprovedError,
    RegistryNotReadyError,
    assert_registry_approved,
    assert_scoring_ready,
)
from smartmatch_domain.factors.topic_relevance import TopicRelevanceInputs
from smartmatch_domain.factors.travel_burden import GeoPoint, TravelInputs
from smartmatch_domain.match_run import MATCH_RUN_COMMAND_TYPE, inputs_fingerprint
from smartmatch_domain.optimizer import (
    PortfolioCandidate,
    PortfolioRequest,
    solve_portfolio,
)
from smartmatch_domain.scoring import CandidateEvidence, rank_candidates
from smartmatch_persistence import schema
from smartmatch_persistence.match_runs import MatchRunRepository
from smartmatch_persistence.rate_limit import RateLimit
from sqlalchemy.orm import Session

from smartmatch_api.commands import submit_command
from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.errors import ApiError
from smartmatch_api.units import load_unit_or_404
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/units", tags=["match-runs"])

#: Roles permitted to submit and read a match run. ``admin`` and
#: ``coordinator``, matching ``imports.py::_IMPORT_ROLES``,
#: ``events.py::_EVENT_ROLES`` and ``review.py::_REVIEW_ROLES``. The G1
#: worksheet's program direction makes the shortlist a coordinator instrument —
#: "coordinator batch-invites" — and names no other role, and under
#: deny-by-default the absence of a permit is a denial rather than an
#: invitation to guess. A literal ``frozenset`` rather than an import of one of
#: the sets above, for the reason ``tests/authz/test_route_roles.py`` gives:
#: several role sets agreeing today is not a reason a widening of one should
#: silently widen the others.
_MATCH_RUN_ROLES: Final[frozenset[str]] = frozenset({"admin", "coordinator"})

#: v1.1 §3.4 pilot default, same shape as ``IMPORT_RATE_LIMIT``: a submission
#: queues durable work, so it is bounded tighter than a read. The operation
#: name is the command type, which is the bucket a coordinator's runs come out
#: of.
MATCH_RUN_RATE_LIMIT = RateLimit(
    operation=MATCH_RUN_COMMAND_TYPE,
    max_requests=10,
    window=timedelta(minutes=1),
)

#: Most candidates one submission may carry. Every candidate is scored on the
#: request path and re-solved on the read path, so an unbounded pool is a
#: compute denial-of-service surface rather than merely a large request. 200 is
#: G3 §2.2a's record cap reused — ``routers/events.py::MAX_ROWS`` uses the same
#: number for the same reason — rather than a second limit invented here.
MAX_CANDIDATES: Final[int] = 200


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class GeoPointRequest(BaseModel):
    """A synthetic pilot coordinate pair.

    Optional wherever it appears, and its absence is meaningful: no coordinate
    is *unknown* travel evidence, which
    :func:`~smartmatch_domain.factors.travel_burden.score_travel_burden`
    reports as ``None`` and never as a distance of zero. Synthetic fixtures
    only — nothing here geocodes, and no provider is consulted.
    """

    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)


class MatchCandidateRequest(BaseModel):
    """One professional's evidence, as the caller submits it.

    Carries evidence, never a score. A caller-supplied score would be a caller
    choosing their own shortlist, and the registry would be decoration.

    ``expertise_topics`` is nullable **and** that is different from ``[]``:
    ``null`` means no expertise record exists for this professional (unknown),
    an empty list means the record exists and is empty (measurable, and
    measurably zero against any declared topic). ADR-0011 lives in that
    distinction, and
    :class:`~smartmatch_domain.factors.topic_relevance.TopicRelevanceInputs`
    draws it the same way, so the field is passed through rather than
    normalized.
    """

    subject_id: str = Field(min_length=1, max_length=200)
    expertise_topics: list[str] | None = Field(
        default=None,
        description=(
            "Recorded expertise topics. null means no expertise record exists "
            "(unknown); [] means the record exists and is empty (a measured "
            "zero against any declared topic). The two are not interchangeable."
        ),
    )
    location: GeoPointRequest | None = Field(
        default=None,
        description="The professional's synthetic coordinates, or null when none are on file.",
    )


class MatchRunRequest(BaseModel):
    """One match-run submission.

    Carries no tenant, actor, or unit: all three are derived server-side. The
    unit comes from the authorized path parameter, never from the body — a
    caller naming the unit their run is filed under would be naming who may
    later read it (MM-A01, and ``submit_command``'s ``owning_unit_id``
    contract).
    """

    event_need_id: str = Field(min_length=1, max_length=200)
    required_topics: list[str] = Field(
        default_factory=list,
        description="Topics the event_need declares as required.",
    )
    preferred_topics: list[str] = Field(
        default_factory=list,
        description="Topics the event_need declares as preferred.",
    )
    event_location: GeoPointRequest | None = Field(
        default=None,
        description=(
            "The event_need's synthetic coordinates, or null when none are on "
            "file — in which case travel burden is unknown for every candidate "
            "and no distance is guessed."
        ),
    )
    portfolio_size: int = Field(
        default=MIN_SHORTLIST_SIZE,
        ge=MIN_SHORTLIST_SIZE,
        le=MAX_SHORTLIST_SIZE,
        description=(
            f"How many speakers to shortlist. Bounded to "
            f"{MIN_SHORTLIST_SIZE}-{MAX_SHORTLIST_SIZE} by the ratified G1 "
            "presentation rule, enforced here rather than at render time."
        ),
    )
    random_seed: int = Field(
        default=0,
        ge=0,
        description=(
            "Seed handed to the solver. Part of the reproducibility contract: "
            "the same pool, size and seed always produce the same selection."
        ),
    )
    candidates: list[MatchCandidateRequest] = Field(
        min_length=1,
        description=f"The candidate pool, at most {MAX_CANDIDATES} entries.",
        json_schema_extra={"maxItems": MAX_CANDIDATES},
    )


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class MatchRunAcceptedResponse(BaseModel):
    """Acknowledgement for an accepted match-run command.

    ``scored_candidates`` and ``unscorable_candidates`` are reported at
    submission rather than only on the read, because they are the one thing a
    caller cannot infer from a job id: a pool of forty that produced eleven
    scorable candidates is a different submission from one that produced forty,
    and both are accepted.
    """

    job_id: uuid.UUID
    status: str = Field(default="accepted")
    events_url: str = Field(description="Where to follow the work.")
    replayed: bool = Field(
        default=False,
        description="True when an identical request under the same key was already accepted.",
    )
    registry_version: str = Field(
        description="The factor registry version the pool was scored under."
    )
    score_label: str = Field(
        default=SCORE_PROVENANCE_LABEL,
        description="The only label these scores may be displayed under. Never a percentage.",
    )
    scored_candidates: int = Field(
        description="Candidates with complete evidence, entered into the pool."
    )
    unscorable_candidates: int = Field(
        description=(
            "Candidates excluded because at least one factor's evidence was "
            "absent. Reported, never entered at zero (ADR-0011)."
        )
    )


class FactorExplanationView(BaseModel):
    """One factor's contribution to one candidate's score, or its absence."""

    factor_key: str
    display_label: str
    kind: str = Field(description="suitability or penalty — the two read in opposite directions.")
    weight: float = Field(description="The normalized Stage B weight actually applied.")
    state: str = Field(description="measured or unknown. Read this before reading value.")
    value: float | None = Field(
        default=None,
        description=(
            "The factor value in [0.0, 1.0], or null when state is unknown. "
            "A null is an absence of evidence and is never a zero."
        ),
    )
    zero_classification: str | None = Field(
        default=None,
        description="measured_zero, unknown, or null when the value is neither.",
    )
    basis: str = Field(description="Where the number came from — or why there is none.")
    estimate_label: str | None = Field(
        default=None,
        description="Set when the value is an explicitly coarse estimate.",
    )


class CandidateExplanationView(BaseModel):
    """One candidate's heuristic score and every factor behind it."""

    subject_id: str
    heuristic_score: float | None = Field(
        default=None,
        description=(
            "The composite in [0.0, 1.0], or null when any factor's evidence "
            "was absent. Not a percentage and never rendered as one."
        ),
    )
    state: str = Field(description="measured or unknown.")
    score_label: str = Field(description='Always "heuristic score".')
    registry_version: str = Field(description="The registry version this score was produced under.")
    formula_version: str
    unknown_factor_keys: list[str] = Field(
        description="The factors that had no evidence, in registry order."
    )
    factors: list[FactorExplanationView] = Field(
        description="Every implemented Stage B factor, unknown ones included."
    )


class MatchRunResponse(BaseModel):
    """One persisted run, its shortlist, and the explanations behind it."""

    id: uuid.UUID
    unit_id: uuid.UUID
    job_id: uuid.UUID
    event_need_id: str
    created_at: datetime
    supersedes_run_id: uuid.UUID | None = Field(
        default=None,
        description="The run this one corrects, when it corrects one. A correction is a new run.",
    )

    score_label: str = Field(
        default=SCORE_PROVENANCE_LABEL,
        description=(
            "The ratified provenance label. Every score on this response is a "
            '"heuristic score" and none of them is a percentage.'
        ),
    )
    registry_version: str
    registry_hash: str
    weights: dict[str, float] = Field(description="The normalized weights this run applied.")
    optimizer_model_version: str
    solver_name: str
    solver_version: str
    route_estimate_source: str
    route_estimate_version: str
    inputs_hash: str
    portfolio_size: int
    random_seed: int
    portfolio_status: str = Field(
        description=(
            "The solver's recorded verdict: optimal, feasible, infeasible, or "
            "unknown. 'unknown' is a stalled search, never 'no valid portfolio "
            "exists'."
        )
    )

    shortlist: list[CandidateExplanationView] = Field(
        description=(
            f"The selected speakers, at most {MAX_SHORTLIST_SIZE} per the "
            "ratified presentation rule. Empty when shortlist_available is false."
        )
    )
    shortlist_available: bool = Field(
        description=(
            "False when the shortlist could not be reconstructed from the "
            "recorded inputs. It is then empty rather than approximated."
        )
    )
    shortlist_unavailable_reason: str | None = Field(
        default=None,
        description="Why the shortlist could not be reconstructed, when it could not be.",
    )
    considered: list[CandidateExplanationView] = Field(
        description="Scored candidates that were not selected, in ranked order."
    )
    unscorable: list[CandidateExplanationView] = Field(
        description=(
            "Candidates excluded from the pool because at least one factor's "
            "evidence was absent. Present so an absence is visible rather than "
            "silently dropped, and never scored at zero (ADR-0011)."
        )
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

#: Module-level, like every other repository instance in this codebase:
#: stateless, so one instance safely serves every call.
_match_runs: Final[MatchRunRepository] = MatchRunRepository()


def _authorize_match_run(
    session: Session,
    principal: CurrentPrincipal,
    unit_id: uuid.UUID,
) -> uuid.UUID:
    """Load the unit and authorize a coordinator against *that row's* path.

    Shared by both operations because both ask the identical question against
    the identical resource — may this caller work with this unit's match runs —
    in the same spirit as ``routers/events.py::_authorize_event_read`` and
    ``smartmatch_api.job_authz``: a widening applies to both surfaces or to
    neither, and cannot reach one by accident.

    The unit is loaded first and authorization runs against the loaded row's
    ``ltree`` path, never against anything taken from the request.
    ``load_unit_or_404`` scopes the lookup by the caller's own tenant, so a unit
    in another tenant is a 404 rather than a 403 that would confirm the id names
    something real.

    No ``require_membership`` and no ``tenant_wide_roles``: ``_MATCH_RUN_ROLES``
    is non-empty, so ``evaluate`` already refuses a bare ``resource_grant`` on
    the required-roles check (S-007), and the only committed artifact that makes
    anything tenant-wide is the metrics decision's §4, which says it of
    aggregate reads specifically.

    Returns:
        The loaded unit's own id — the value that is handed to
        ``submit_command`` as ``owning_unit_id``, so the job is filed under the
        subtree the request was actually permitted for.
    """
    unit = load_unit_or_404(session, tenant_id=principal.tenant_id, unit_id=unit_id)
    assert_allowed(
        principal.principal,
        Resource(
            resource_type="org_unit",
            resource_id=str(unit_id),
            tenant_id=str(principal.tenant_id),
            owning_unit_path=OrgPath.parse(unit.path),
        ),
        at=utc_now(),
        required_roles=_MATCH_RUN_ROLES,
    )
    return unit.id


def _assert_scoring_permitted() -> None:
    """Fail closed unless the registry is approved *and* fully implemented.

    The standing rule is "every scoring path calls
    ``assert_registry_approved()``", and both operations here are scoring paths:
    one computes scores, the other renders stored ones. ``assert_scoring_ready``
    is called with it for the reason card M6j gives — an "approved" registry
    scoring with only a subset of its approved factors is the legacy deflation
    defect in a new costume.

    Raises:
        ApiError: 503 ``registry_not_ready``. A 503 rather than a 500 because
            nothing is broken: the gate is a state of the deployment, and the
            honest answer to "show me a score" while it is open is that this
            capability is not available, not that the request was malformed.
    """
    try:
        assert_registry_approved()
        assert_scoring_ready()
    except (RegistryNotApprovedError, RegistryNotReadyError) as exc:
        raise ApiError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="registry_not_ready",
            message=(
                "Match scoring is unavailable: the factor registry is not "
                f"approved or not fully implemented. {exc}"
            ),
        ) from exc


def _to_view(explanation: CandidateExplanation) -> CandidateExplanationView:
    """Render one domain explanation onto the wire, field for field.

    No arithmetic, no formatting, no defaulting. In particular ``value`` and
    ``heuristic_score`` are copied as they are: the ``or 0.0`` that would keep a
    type checker quiet here is exactly the coercion ADR-0011 forbids, and
    ``state`` is carried beside them so a consumer never has to infer the
    difference from a null.
    """
    return CandidateExplanationView(
        subject_id=explanation.subject_id,
        heuristic_score=explanation.heuristic_score,
        state=explanation.state.value,
        score_label=explanation.score_label,
        registry_version=explanation.registry_version,
        formula_version=explanation.formula_version,
        unknown_factor_keys=list(explanation.unknown_factor_keys),
        factors=[
            FactorExplanationView(
                factor_key=factor.factor_key,
                display_label=factor.display_label,
                kind=factor.kind,
                weight=factor.weight,
                state=factor.state.value,
                value=factor.value,
                zero_classification=factor.zero_classification,
                basis=factor.basis,
                estimate_label=factor.estimate_label,
            )
            for factor in explanation.factors
        ],
    )


# ---------------------------------------------------------------------------
# POST — submit a match run
# ---------------------------------------------------------------------------


def _partition_pool(
    explanations: tuple[CandidateExplanation, ...],
) -> tuple[list[CandidateExplanation], list[CandidateExplanation]]:
    """Split a ranked pool into the candidates that can be solved and the rest.

    This is the ADR-0011 decision the M8a handler delegates to "whoever
    assembled the pool". A candidate whose composite is unknown has no utility;
    :class:`~smartmatch_domain.optimizer.PortfolioCandidate` refuses one rather
    than coercing it, and coercing it here would be worse than the refusal — an
    evidence-free candidate entered at ``0.0`` ranks below every measured
    candidate, which reads as "we measured them and they were poor" rather than
    "we know nothing about them".

    Returns:
        ``(scorable, unscorable)``, each preserving the ranked order it arrived
        in.
    """
    scorable = [item for item in explanations if item.is_shortlistable]
    unscorable = [item for item in explanations if not item.is_shortlistable]
    return scorable, unscorable


def _build_evidence(body: MatchRunRequest) -> list[CandidateEvidence]:
    """Turn the validated request body into domain evidence, unchanged.

    Nothing is normalized on the way through. ``expertise_topics`` keeps the
    ``None``/``[]`` distinction the request model documents, and a missing
    coordinate stays missing rather than becoming an origin — both are the
    ADR-0011 boundary, and this is where a well-meaning default would cross it.
    """
    destination = (
        None
        if body.event_location is None
        else GeoPoint(
            latitude=body.event_location.latitude,
            longitude=body.event_location.longitude,
        )
    )
    return [
        CandidateEvidence(
            subject_id=candidate.subject_id,
            topic=TopicRelevanceInputs(
                expertise_topics=(
                    None
                    if candidate.expertise_topics is None
                    else tuple(candidate.expertise_topics)
                ),
                required_topics=tuple(body.required_topics),
                preferred_topics=tuple(body.preferred_topics),
            ),
            travel=TravelInputs(
                origin=(
                    None
                    if candidate.location is None
                    else GeoPoint(
                        latitude=candidate.location.latitude,
                        longitude=candidate.location.longitude,
                    )
                ),
                destination=destination,
            ),
        )
        for candidate in body.candidates
    ]


@router.post(
    "/{unit_id}/match-runs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=MatchRunAcceptedResponse,
    summary="Submit a match-run command",
)
def create_match_run(
    principal: CurrentPrincipal,
    session: DbSession,
    body: MatchRunRequest,
    unit_id: Annotated[uuid.UUID, Path()],
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            description="Required. Makes retries safe.",
        ),
    ] = None,
) -> MatchRunAcceptedResponse:
    """Score the submitted pool and enqueue ``match-run.create``.

    Returns ``202``: nothing has been solved and no ``match_run`` row exists
    when this returns. The command is recorded and will be dispatched; follow
    ``events_url``, then read the run.

    Quota is charged first (ADR-0015), ahead of the load, the authorization and
    the validation, so a caller producing 404s against invented unit ids spends
    exactly what a caller submitting real runs spends.

    What is persisted on ``job.payload``, and why each part is there:

    * ``event_need_id``, ``portfolio_size``, ``random_seed`` and ``candidates``
      — the four keys ``smartmatch_worker.handlers._read_match_run_command``
      reads back. Renaming one here changes what the worker is given, so the two
      ends move together.
    * ``explanations`` — the per-factor account of every candidate, scorable and
      unscorable alike. The worker ignores this key (it reads its four with
      ``.get``), and the read route renders it. Recomputing the explanation on
      the read would be a second scoring of possibly different evidence under
      possibly newer weights; storing it means what a coordinator sees is what
      was actually scored, under the registry version recorded on it.

    Raises:
        ApiError: 503 when the registry is not ready; 400 when the pool is over
            :data:`MAX_CANDIDATES` or names a duplicate ``subject_id``; 422 when
            fewer candidates have complete evidence than the requested shortlist
            needs.
    """
    charge = charge_quota(session, principal, MATCH_RUN_RATE_LIMIT)

    owning_unit_id = _authorize_match_run(session, principal, unit_id)

    _assert_scoring_permitted()

    if len(body.candidates) > MAX_CANDIDATES:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="match_run_pool_too_large",
            message=(
                f"candidates must contain at most {MAX_CANDIDATES} entries; "
                f"got {len(body.candidates)}."
            ),
        )

    subject_ids = [candidate.subject_id for candidate in body.candidates]
    if len(set(subject_ids)) != len(subject_ids):
        # Refused here rather than left to `rank_candidates` so the caller is
        # told which field is wrong in this API's own error envelope, instead of
        # meeting a domain ValueError as a 500.
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="match_run_duplicate_candidate",
            message="candidates contains a duplicate subject_id.",
        )

    try:
        # `rank_candidates` calls `assert_registry_approved` and
        # `assert_scoring_ready` again, per candidate, before reading any
        # evidence. The check above is not redundant with it: it turns the gate
        # into this API's own 503 rather than an unhandled domain error, and it
        # runs before any evidence is even assembled.
        ranked = rank_candidates(_build_evidence(body))
    except ValueError as exc:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="match_run_invalid_evidence",
            message=f"The submitted candidate evidence could not be scored: {exc}",
        ) from exc

    explanations = explain_candidates(ranked)
    scorable, unscorable = _partition_pool(explanations)

    if len(scorable) < body.portfolio_size:
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="match_run_insufficient_scorable_candidates",
            message=(
                f"A shortlist of {body.portfolio_size} was requested but only "
                f"{len(scorable)} of {len(body.candidates)} candidates have "
                "complete evidence. The remainder are not scored at zero — "
                "their evidence is absent, which is a different fact — so there "
                "is no honest way to fill the shortlist. Supply the missing "
                "expertise or coordinates, or request a smaller shortlist."
            ),
            details={
                "requested_portfolio_size": str(body.portfolio_size),
                "scorable_candidates": str(len(scorable)),
                "unscorable_candidates": str(len(unscorable)),
            },
        )

    accepted = submit_command(
        session,
        principal,
        command_type=MATCH_RUN_COMMAND_TYPE,
        # The loaded row's own id, never a body value — see
        # `_authorize_match_run` and `submit_command`'s `owning_unit_id`
        # contract.
        owning_unit_id=owning_unit_id,
        payload={
            "unit_id": str(unit_id),
            "event_need_id": body.event_need_id,
            "portfolio_size": body.portfolio_size,
            "random_seed": body.random_seed,
            "candidates": [
                # `heuristic_score` is not None on this branch —
                # `is_shortlistable` is exactly that check — and
                # `PortfolioCandidate` would refuse it if it were.
                {"subject_id": item.subject_id, "utility": item.heuristic_score}
                for item in scorable
            ],
            "explanations": [explanation_to_payload(item) for item in explanations],
        },
        idempotency_key=idempotency_key,
        charge=charge,
    )

    return MatchRunAcceptedResponse(
        job_id=accepted.job_id,
        events_url=f"/v1/jobs/{accepted.job_id}/events",
        replayed=accepted.is_replay,
        registry_version=explanations[0].registry_version,
        scored_candidates=len(scorable),
        unscorable_candidates=len(unscorable),
    )


# ---------------------------------------------------------------------------
# GET — read one persisted run
# ---------------------------------------------------------------------------


def _load_command_payload(
    session: Session, *, tenant_id: uuid.UUID, job_id: uuid.UUID
) -> dict[str, Any] | None:
    """Read back the durable payload the run's command was accepted with.

    Scoped by ``tenant_id`` in the query itself rather than filtered afterwards,
    the same discipline ``load_unit_or_404`` and ``JobRepository.get`` state.
    """
    row = session.execute(
        sa.select(schema.job.c.payload).where(
            schema.job.c.tenant_id == tenant_id,
            schema.job.c.id == job_id,
        )
    ).one_or_none()
    if row is None or row.payload is None:
        return None
    payload = row.payload
    return payload if isinstance(payload, dict) else None


def _reconstruct_shortlist(
    run: sa.Row[Any], payload: dict[str, Any]
) -> tuple[list[str], str | None]:
    """Re-derive the run's selection, or say why it could not be re-derived.

    See the module docstring for the three checks and why an approximation is
    not offered. Every failure returns an empty selection with a reason rather
    than raising: a snapshot that cannot be reproduced is still a real run whose
    pins a coordinator is entitled to read, and refusing the whole response
    would hide the very inconsistency this function detected.

    Returns:
        ``(selected_subject_ids, unavailable_reason)``. Exactly one of the two
        is meaningful: a reason means the list is empty.
    """
    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list) or not raw_candidates:
        return [], "the command payload behind this run carries no candidate pool"

    pool: list[PortfolioCandidate] = []
    for entry in raw_candidates:
        if not isinstance(entry, dict):
            return [], "the stored candidate pool is not readable"
        subject = entry.get("subject_id")
        utility = entry.get("utility")
        if not isinstance(subject, str) or not subject.strip():
            return [], "the stored candidate pool is not readable"
        # `bool` before `float` for the reason PortfolioCandidate names: it
        # would otherwise be read as 1.0/0.0 and manufacture a utility.
        if isinstance(utility, bool) or not isinstance(utility, int | float):
            return [], "the stored candidate pool carries a utility that is not a number"
        try:
            pool.append(PortfolioCandidate(subject_id=subject.strip(), utility=float(utility)))
        except ValueError:
            return [], "the stored candidate pool carries a utility outside [0.0, 1.0]"

    stored_weights = run.weights
    if not isinstance(stored_weights, dict):
        return [], "the run's stored weights are not readable"

    recomputed = inputs_fingerprint(
        event_need_id=str(run.event_need_id),
        candidate_subject_ids=[candidate.subject_id for candidate in pool],
        candidate_utilities=[candidate.utility for candidate in pool],
        portfolio_size=int(run.portfolio_size),
        random_seed=int(run.random_seed),
        weights={name: float(weight) for name, weight in stored_weights.items()},
    )
    if recomputed != run.inputs_hash:
        return [], (
            "the command payload no longer fingerprints to this run's recorded "
            "inputs_hash, so any selection derived from it would be a selection "
            "for a different problem"
        )

    try:
        result = solve_portfolio(
            PortfolioRequest(
                event_need_id=str(run.event_need_id),
                candidates=tuple(pool),
                portfolio_size=int(run.portfolio_size),
                random_seed=int(run.random_seed),
            )
        )
    except ValueError:
        return [], "the recorded inputs no longer form a solvable request"

    if result.status.value != run.portfolio_status:
        return [], (
            "re-solving the recorded inputs produced status "
            f"{result.status.value!r} where the snapshot recorded "
            f"{str(run.portfolio_status)!r}"
        )

    return list(result.selected_subject_ids), None


def _read_stored_explanations(
    payload: dict[str, Any],
) -> tuple[list[CandidateExplanation], str | None]:
    """Read the stored per-factor explanations, or say why they are unreadable.

    Reported, never repaired. See
    :func:`~smartmatch_domain.explanation.explanation_from_payload`: a reader
    that filled in a missing ``state`` would resurrect exactly the
    unknown-as-zero collapse the explanation layer exists to prevent.
    """
    raw = payload.get("explanations")
    if not isinstance(raw, list):
        return [], "the command payload behind this run carries no explanations"
    try:
        return [explanation_from_payload(entry) for entry in raw], None
    except ValueError as exc:
        return [], f"the stored explanations are not readable: {exc}"


@router.get(
    "/{unit_id}/match-runs/{match_run_id}",
    response_model=MatchRunResponse,
    summary="Read one match run, its shortlist, and its per-factor explanations",
)
def read_match_run(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    match_run_id: Annotated[uuid.UUID, Path()],
) -> MatchRunResponse:
    """Return the persisted snapshot with the shortlist and the explanations.

    Authorization runs against the unit in the path, before the run is read. The
    run is then required to *belong* to that unit — a run filed under another
    subtree is a 404 here even when the caller could have read it at its own
    path, because a resource that answers to two paths is a resource whose
    authorization depends on which one the caller chose.

    Everything on the response about versions and weights comes off the
    snapshot, never off today's registry: a run recorded under an earlier
    registry version keeps saying so, which is the whole point of pinning it
    (worksheet agenda item 4). The explanations come off the durable command
    payload, which is what was actually scored.

    Raises:
        ApiError: 503 when the registry is not ready; 404 when no such run
            exists in this unit and tenant.
    """
    _authorize_match_run(session, principal, unit_id)
    _assert_scoring_permitted()

    run = _match_runs.get(session, tenant_id=principal.tenant_id, run_id=match_run_id)
    if run is None or run.owning_unit_id != unit_id:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="match_run_not_found",
            message="No such match run in this unit.",
        )

    payload = _load_command_payload(session, tenant_id=principal.tenant_id, job_id=run.job_id)

    explanations: list[CandidateExplanation] = []
    selected: list[str] = []
    unavailable_reason: str | None = None
    if payload is None:
        unavailable_reason = "the command behind this run no longer carries its payload"
    else:
        explanations, unavailable_reason = _read_stored_explanations(payload)
        if unavailable_reason is None:
            selected, unavailable_reason = _reconstruct_shortlist(run, payload)

    by_subject = {item.subject_id: item for item in explanations}
    # Capped at the ratified maximum as well as at the run's own
    # `portfolio_size`: the size was already bounded when the run was submitted,
    # and this holds the rule at the render boundary too, so a snapshot written
    # by some other path can never widen the shortlist past three.
    shortlist = [
        by_subject[subject] for subject in selected[:MAX_SHORTLIST_SIZE] if subject in by_subject
    ]
    shortlisted_ids = {item.subject_id for item in shortlist}

    considered = [
        item
        for item in explanations
        if item.state is ScoreState.MEASURED and item.subject_id not in shortlisted_ids
    ]
    unscorable = [item for item in explanations if item.state is ScoreState.UNKNOWN]

    return MatchRunResponse(
        id=run.id,
        unit_id=run.owning_unit_id,
        job_id=run.job_id,
        event_need_id=run.event_need_id,
        created_at=run.created_at,
        supersedes_run_id=run.supersedes_run_id,
        registry_version=run.registry_version,
        registry_hash=run.registry_hash,
        weights={name: float(weight) for name, weight in dict(run.weights).items()},
        optimizer_model_version=run.optimizer_model_version,
        solver_name=run.solver_name,
        solver_version=run.solver_version,
        route_estimate_source=run.route_estimate_source,
        route_estimate_version=run.route_estimate_version,
        inputs_hash=run.inputs_hash,
        portfolio_size=run.portfolio_size,
        random_seed=run.random_seed,
        portfolio_status=run.portfolio_status,
        shortlist=[_to_view(item) for item in shortlist],
        shortlist_available=unavailable_reason is None,
        shortlist_unavailable_reason=unavailable_reason,
        considered=[_to_view(item) for item in considered],
        unscorable=[_to_view(item) for item in unscorable],
    )
