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

## The caller names who to consider. It does not supply their evidence.

OQ-CBA-031, approved. This route once took each candidate's expertise and
coordinates **on the request body**, which forced it onto
``smartmatch_domain.scoring.rank_candidates`` — the superseded two-factor
composition — and so every run any client could obtain was pinned to
``1.1.1-approved-g1-m6j`` with ``scoring_mode: null``, while registry
``2.0.0-approved-oq-cba-004`` sat approved and unreachable.

The body now carries a Speaker Request id, a shortlist size, a seed and a list
of subject ids. Everything scored is read server-side by
:mod:`smartmatch_api.match_run_evidence` — the run's description, targets and
physical/virtual switch off the filed request, each speaker's industry, role,
topic text and place off ``speaker_profile``. That is correctness under 2.0.0,
and it is also what makes a run *trustworthy*: a caller can no longer assert a
speaker's evidence and have the immutable snapshot record the assertion as fact.

## Both scoring modes run, and an unmeasured speaker is still absent

``cba-virtual-1`` scores three factors and does not score proximity (customer
§11). ``cba-physical-1`` scores four, and its fourth needs a distance in miles
from the CPP campus — which is why this route refused every physical request
with ``match_run_physical_scoring_unavailable`` until OQ-CBA-024 shipped the
static offline ZIP-centroid table. It has, so the refusal is gone and the mode
is taken off the filed request like any other run-level fact.

What is *not* gone is the reason the refusal existed. A distance is resolved
only for a speaker whose stored ZIP is in that Californian table; a blank,
malformed, or out-of-state ZIP still resolves to nothing, and nothing is an
**unknown** distance rather than the Far band. Under ``cba-physical-1`` an
unknown factor makes the composite unknown (ADR-0011), so such a candidate is
not shortlistable — and :func:`_partition_pool` puts them in ``unscorable``,
where they are counted and reported, rather than entering them at ``0.0`` where
they would sort below every measured candidate as though somebody had measured
them and found them wanting.

The consequence is visible and deliberate: a physical run against a roster
nobody has recorded ZIPs for is refused with
``match_run_insufficient_scorable_candidates`` and a count of exactly who could
not be scored. That is a different refusal from the old one — it names a gap in
*this tenant's records* that a Speaker Connector can close, not a capability the
deployment lacks.

## Why the API scores and the worker solves

The split is not arbitrary. **Scoring** is a pure function of evidence read from
this tenant's own rows — ``smartmatch_domain.scoring.rank_cba_candidates`` reads
the model's factor modules and the registry's normalized weights, touches no
network and no clock — and it has to happen here because
:class:`~smartmatch_domain.optimizer.PortfolioCandidate` refuses an unknown
utility rather than coercing it to ``0.0`` (ADR-0011). Somebody has to decide
what an unscorable candidate means before the pool reaches the solver, and the
M8a handler says explicitly that this "belongs to whoever assembled the pool".
That is this route, and its answer is in :func:`_partition_pool`: a candidate
whose evidence is incomplete is **excluded from the pool and reported**, never
entered at zero where it would sit below every measured candidate as though it
had been measured and found wanting.

The one provider this path constructs is the semantic topic comparator
(:func:`_topic_provider`), and under ``ALLOW_LIVE_PROVIDERS=false`` it is never
a live, external vendor: ``build_semantic_topic_provider`` refuses one under
every edition. By default it is ``FixtureSemanticTopicProvider``, which
replays recorded comparisons, opens no socket and reads no credential; a pair
it has no recording for is an *unknown* topic factor, never a guess — the
honest consequence of OQ-CBA-026 being open, and the reason a speaker with
topic text on file may be reported unscorable while one with none scores
under §9's neutral policy.

Since ADR-0017, a deployment may set
``SMARTMATCH_CBA_TOPIC_LOCAL_EMBEDDING_ENABLED=true`` to route this same seam
to ``LocalEmbeddingSemanticTopicProvider`` instead — an offline, in-process
averaged-GloVe model with no vendor, no per-run cost and no network call,
which turns exactly the pairs the fixture had no recording for into a
``measured`` score. It is a deployment setting, not a per-request or
per-principal one (:class:`~smartmatch_api.config.Settings`), and it is off by
default: an unconfigured deployment's behaviour, golden pins and CI are
unchanged by upgrading to a release that carries this flag.

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

The read is local, deterministic, bounded computation: no network call, no
provider at all, no LLM, and a pool capped at :data:`MAX_CANDIDATES`. The write
constructs exactly one provider — the §9 topic comparator, which is the
playback fixture and opens no socket — and neither path can reach out
(``tests/unit/test_no_external_calls_on_request_path.py`` pins that
structurally, by refusing any HTTP client import under ``services/api``).
``ALLOW_LIVE_PROVIDERS`` is a necessary gate for that provider and explicitly
not a sufficient one: there is no live adapter behind it (OQ-CBA-026).

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
from typing import Annotated, Any, Final, cast

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
from smartmatch_domain.factors.cba_semantic_topic import SemanticTopicProvider
from smartmatch_domain.match_run import MATCH_RUN_COMMAND_TYPE, inputs_fingerprint
from smartmatch_domain.optimizer import (
    PortfolioCandidate,
    PortfolioRequest,
    solve_portfolio,
)
from smartmatch_domain.scoring import rank_cba_candidates
from smartmatch_persistence import schema
from smartmatch_persistence.match_runs import MatchRunRepository
from smartmatch_persistence.match_weight_settings import MatchWeightSettingRepository
from smartmatch_persistence.rate_limit import RateLimit
from smartmatch_providers.topic_semantics import build_semantic_topic_provider
from sqlalchemy.orm import Session

from smartmatch_api.commands import submit_command
from smartmatch_api.config import get_settings
from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.errors import ApiError
from smartmatch_api.match_run_evidence import (
    ExcludedCandidate,
    SpeakerRequestEvidence,
    assemble_cba_pool,
    load_speaker_request,
)
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


class MatchRunRequest(BaseModel):
    """One match-run submission: who to consider, and against which request.

    Carries no tenant, actor, or unit: all three are derived server-side. The
    unit comes from the authorized path parameter, never from the body — a
    caller naming the unit their run is filed under would be naming who may
    later read it (MM-A01, and ``submit_command``'s ``owning_unit_id``
    contract).

    It also carries **no evidence**, and that is OQ-CBA-031's point. There is no
    field here for a speaker's industry, role, topic text or location, and none
    for the event's description or its physical/virtual switch: every one of
    those is read from this tenant's own rows by
    :mod:`smartmatch_api.match_run_evidence`. A request body that could state a
    speaker's expertise is a request body that can decide its own shortlist.
    """

    speaker_request_id: uuid.UUID = Field(
        description=(
            "The filed Speaker Request (customer §12) this run is for. Its "
            "description, its industry and role targets and its virtual/physical "
            "switch are read from the stored row, not from this body."
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
    candidate_subject_ids: list[uuid.UUID] = Field(
        min_length=1,
        description=(
            f"The professionals to consider, at most {MAX_CANDIDATES}. Each is "
            "a speaker_profile.professional_id as the §13 contact listing "
            "reports it — an identifier the caller was given, never one derived "
            "from a name. Their evidence is read from that row; naming somebody "
            "here does not assert anything about them."
        ),
        json_schema_extra={"maxItems": MAX_CANDIDATES},
    )


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ExcludedCandidateView(BaseModel):
    """One named subject that never entered the pool, and why.

    Distinct from ``unscorable_candidates`` and deliberately so. An unscorable
    candidate *was* evaluated and some factor had no evidence; an excluded one
    was never evaluated at all — no profile row, or a classification §19 says a
    person must review first. Collapsing the two would tell a Speaker Connector
    that somebody scored poorly when in fact nobody has looked at their record.
    """

    subject_id: str
    reason: str = Field(
        description=(
            "A stable token: speaker_profile_not_found, "
            "industry_classification_awaiting_review, "
            "role_classification_awaiting_review, "
            "industry_classification_missing, role_classification_missing, "
            "industry_classification_provenance_unknown, "
            "role_classification_provenance_unknown, "
            "industry_taxonomy_version_superseded, "
            "role_taxonomy_version_superseded, industry_code_unrecognised, or "
            "role_code_unrecognised."
        )
    )


class MatchRunAcceptedResponse(BaseModel):
    """Acknowledgement for an accepted match-run command.

    ``scored_candidates``, ``unscorable_candidates`` and ``excluded_candidates``
    are reported at submission rather than only on the read, because they are
    the one thing a caller cannot infer from a job id: a pool of forty that
    produced eleven scorable candidates is a different submission from one that
    produced forty, and both are accepted.
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
    scoring_mode: str = Field(
        description=(
            "The model within that registry the pool was scored under, resolved "
            "from the Speaker Request's virtual/physical switch and never from "
            "this body. cba-virtual-1 for a virtual request, cba-physical-1 for "
            "a physical one — both are reachable, because OQ-CBA-024's offline "
            "ZIP-centroid table retired the physical refusal."
        )
    )
    scoring_mode_version: str = Field(
        description="The mode vocabulary's version. Set exactly when scoring_mode is."
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
            "Candidates evaluated whose composite was unknown because at least "
            "one factor's evidence was absent. Reported, never entered at zero "
            "(ADR-0011)."
        )
    )
    excluded_candidates: list[ExcludedCandidateView] = Field(
        default_factory=list,
        description=(
            "Named subjects that were never evaluated — no profile row, or a "
            "classification awaiting the review customer §19 requires before a "
            "speaker becomes available for matching. Absent from the pool, not "
            "ranked last in it."
        ),
    )


class FactorExplanationView(BaseModel):
    """One factor's contribution to one candidate's score, or its absence."""

    factor_key: str
    display_label: str
    kind: str = Field(description="suitability or penalty — the two read in opposite directions.")
    weight: float = Field(description="The normalized Stage B weight actually applied.")
    state: str = Field(
        description=(
            "measured, policy_neutral, or unknown (ADR-0016's three states). "
            "Read this before reading value."
        )
    )
    value: float | None = Field(
        default=None,
        description=(
            "The factor value in [0.0, 1.0], or null when state is unknown. "
            "A null is an absence of evidence and is never a zero. A "
            "policy_neutral value is a stated customer policy, not a measurement."
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
    policy_id: str | None = Field(
        default=None,
        description=(
            "The customer policy behind a policy_neutral value, null otherwise. "
            "Carried so a neutral default is attributable rather than "
            "indistinguishable from a measurement that happened to land there."
        ),
    )
    policy_version: str | None = Field(
        default=None,
        description="The policy's version. Set exactly when policy_id is.",
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
    state: str = Field(description="measured, policy_neutral, or unknown.")
    score_label: str = Field(description='Always "heuristic score".')
    registry_version: str = Field(description="The registry version this score was produced under.")
    formula_version: str
    scoring_mode: str | None = Field(
        default=None,
        description=(
            "The model this score was produced under — cba-virtual-1, "
            "cba-physical-1, or null for a run stored before the vocabulary "
            "existed. null is not cba-physical-1: a pre-ADR-0016 run never "
            "asked the question, and reading it as physical would claim a "
            "proximity factor was scored."
        ),
    )
    scoring_mode_version: str | None = Field(
        default=None,
        description="The mode vocabulary's version. Set exactly when scoring_mode is.",
    )
    unknown_factor_keys: list[str] = Field(
        description="The factors that had no evidence, in registry order."
    )
    policy_neutral_factor_keys: list[str] = Field(
        default_factory=list,
        description=(
            "The factors whose value came from a stated customer policy rather "
            "than a measurement, in registry order. These participate in the "
            "composite; they are listed so a consumer can say which parts of a "
            "score were policy without comparing floats to a constant."
        ),
    )
    caption: str | None = Field(
        default=None,
        description=(
            "The approved caption a surface must show beside this score, "
            "verbatim, or null when none applies (ADR-0016 Proposal 8)."
        ),
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

#: Same reasoning. Read-only on this path: the route reads the unit's weight
#: overrides so the utilities it computes were produced by the same weights the
#: worker will fingerprint the run with.
_weight_settings: Final[MatchWeightSettingRepository] = MatchWeightSettingRepository()


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
        scoring_mode=explanation.scoring_mode,
        scoring_mode_version=explanation.scoring_mode_version,
        unknown_factor_keys=list(explanation.unknown_factor_keys),
        policy_neutral_factor_keys=list(explanation.policy_neutral_factor_keys),
        # The domain's own words, not this router's. ADR-0016 Proposal 8
        # approved the exact sentence, and a paraphrase composed here would be a
        # different decision wearing the same name.
        caption=explanation.caption,
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
                policy_id=factor.policy_id,
                policy_version=factor.policy_version,
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


def _load_request_or_404(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    speaker_request_id: uuid.UUID,
) -> SpeakerRequestEvidence:
    """The filed Speaker Request this run scores against, or a 404.

    A 404 rather than a 403 or a 422 for the reason ``load_unit_or_404`` gives:
    the lookup is already scoped to the caller's tenant and authorized unit, so
    an id outside that scope must not be answered in a way that confirms it
    names something real elsewhere.
    """
    request = load_speaker_request(
        session,
        tenant_id=tenant_id,
        host_org_unit_id=owning_unit_id,
        event_id=speaker_request_id,
    )
    if request is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="speaker_request_not_found",
            message="No such Speaker Request in this unit.",
        )
    return request


def _topic_provider() -> SemanticTopicProvider:
    """The §9 comparison adapter for one run.

    Constructed per request rather than held on module state:
    ``build_semantic_topic_provider`` refuses a live adapter under **every**
    edition and refuses to run at all if a model credential is present, so this
    is the place a misconfigured deployment fails loudly instead of scoring
    against something nobody approved (OQ-CBA-026). What it returns is
    ``FixtureSemanticTopicProvider`` unless this deployment has opted into
    ADR-0017's offline embedding path — see
    ``Settings.cba_topic_local_embedding_enabled`` for why that is a deployment
    fact and not a per-request choice. Neither adapter opens a socket.

    The ``cast`` is a typing accommodation and not a claim about behaviour.
    ``TopicSimilarity`` carries every member ``TopicComparison`` declares, and
    ``isinstance`` agrees at runtime — but the protocol declares them
    *settable*, and ``TopicSimilarity`` is a frozen dataclass, so mypy reads its
    fields as read-only and refuses the structural match. Making the protocol's
    members read-only is a change to :mod:`smartmatch_domain`, which this card
    does not own; it is recorded as OQ-CBA-062 rather than reached for.
    """
    settings = get_settings()
    return cast(
        SemanticTopicProvider,
        build_semantic_topic_provider(
            settings.edition,
            use_local_embedding=settings.cba_topic_local_embedding_enabled,
        ),
    )


def _excluded_views(excluded: tuple[ExcludedCandidate, ...]) -> list[ExcludedCandidateView]:
    """Render the absences onto the wire, reason token included."""
    return [
        ExcludedCandidateView(subject_id=item.subject_id, reason=item.reason) for item in excluded
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
    """Score this unit's named speakers against a filed Speaker Request.

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
      ends move together. ``event_need_id`` is the Speaker Request's own id,
      which is what makes a stored run traceable to the request it answered.
    * ``scoring_mode`` — resolved from that request's virtual/physical switch.
      The worker pins the registry, the weights and the route-estimate version
      off it, so this is the value that decides which rulebook the snapshot
      records.
    * ``explanations`` — the per-factor account of every candidate, scorable and
      unscorable alike. The worker ignores this key (it reads its four with
      ``.get``), and the read route renders it. Recomputing the explanation on
      the read would be a second scoring of possibly different evidence under
      possibly newer weights; storing it means what a coordinator sees is what
      was actually scored, under the registry version recorded on it.

    Raises:
        ApiError: 503 when the registry is not ready; 404 when no such Speaker
            Request exists in this unit; 400 when the pool is over
            :data:`MAX_CANDIDATES` or names a duplicate subject; 422 when fewer
            candidates can be scored than the requested shortlist needs, which
            is the physical model's ordinary answer for a roster whose ZIPs are
            missing, since an unresolved distance is unknown and never Far.
    """
    charge = charge_quota(session, principal, MATCH_RUN_RATE_LIMIT)

    owning_unit_id = _authorize_match_run(session, principal, unit_id)

    _assert_scoring_permitted()

    if len(body.candidate_subject_ids) > MAX_CANDIDATES:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="match_run_pool_too_large",
            message=(
                f"candidate_subject_ids must contain at most {MAX_CANDIDATES} "
                f"entries; got {len(body.candidate_subject_ids)}."
            ),
        )

    subject_ids = body.candidate_subject_ids
    if len(set(subject_ids)) != len(subject_ids):
        # Refused here rather than left to `rank_cba_candidates` so the caller
        # is told which field is wrong in this API's own error envelope, instead
        # of meeting a domain ValueError as a 500.
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="match_run_duplicate_candidate",
            message="candidate_subject_ids contains a duplicate subject_id.",
        )

    request = _load_request_or_404(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=owning_unit_id,
        speaker_request_id=body.speaker_request_id,
    )
    # Off the filed request, never off the body. ADR-0016 Proposal 5 requires
    # the mode to be resolved from the event before scoring, and
    # `SpeakerRequestEvidence.scoring_mode` is a property over `is_virtual` for
    # exactly that reason: there is no constructor parameter, and therefore no
    # request field, through which a caller could choose one.
    scoring_mode = request.scoring_mode

    pool = assemble_cba_pool(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=owning_unit_id,
        subject_ids=subject_ids,
        request=request,
    )

    # This unit's stored overrides, read from the *authorized* unit and never
    # from the body — the same read `handle_match_run_create` makes before it
    # fingerprints the run. Both ends must use one set of weights or the
    # snapshot records weights that never touched its own utilities, which is
    # the exact defect the immutable snapshot exists to make impossible.
    overrides = _weight_settings.overrides_for(
        session, tenant_id=principal.tenant_id, owning_unit_id=owning_unit_id
    )

    try:
        # `rank_cba_candidates` calls `assert_registry_approved` and
        # `assert_scoring_ready` again, per candidate, before reading any
        # evidence. The check above is not redundant with it: it turns the gate
        # into this API's own 503 rather than an unhandled domain error, and it
        # runs before any evidence is even assembled.
        ranked = rank_cba_candidates(
            pool.evidence,
            request_description=request.description,
            topic_provider=_topic_provider(),
            scoring_mode=scoring_mode,
            weight_overrides=overrides or None,
        )
    except ValueError as exc:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="match_run_invalid_evidence",
            message=f"The stored candidate evidence could not be scored: {exc}",
        ) from exc

    explanations = explain_candidates(ranked)
    scorable, unscorable = _partition_pool(explanations)

    if len(scorable) < body.portfolio_size:
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="match_run_insufficient_scorable_candidates",
            message=(
                f"A shortlist of {body.portfolio_size} was requested but only "
                f"{len(scorable)} of {len(subject_ids)} named speakers could be "
                f"scored: {len(unscorable)} were evaluated with a factor whose "
                f"evidence was absent, and {len(pool.excluded)} never entered "
                "the pool at all. Neither group is scored at zero — an absent "
                "record is a different fact from a poor one — so there is no "
                "honest way to fill the shortlist. Review the classifications "
                "customer §19 requires, add the missing profile evidence, or "
                "request a smaller shortlist."
            ),
            details={
                "requested_portfolio_size": str(body.portfolio_size),
                "scorable_candidates": str(len(scorable)),
                "unscorable_candidates": str(len(unscorable)),
                "excluded_candidates": str(len(pool.excluded)),
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
            # The Speaker Request's own id. `match_run.event_need_id` is Text,
            # so this needs no migration, and a run now names the filed request
            # it answered rather than a string the caller invented.
            "event_need_id": str(request.event_id),
            "portfolio_size": body.portfolio_size,
            "random_seed": body.random_seed,
            "candidates": [
                # `heuristic_score` is not None on this branch —
                # `is_shortlistable` is exactly that check — and
                # `PortfolioCandidate` would refuse it if it were.
                {"subject_id": item.subject_id, "utility": item.heuristic_score}
                for item in scorable
            ],
            # The mode the pool was *actually* scored under, read off the scores
            # rather than restated here, so the payload cannot disagree with the
            # arithmetic that produced its utilities. `ranked` is non-empty
            # whenever `scorable` is, and the 422 above already returned when it
            # was not.
            "scoring_mode": ranked[0].scoring_mode,
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
        # From the score, for the reason the payload's copy is: a mode reported
        # from the request while the utilities came from another composition
        # would be a caption over the wrong picture.
        scoring_mode=_mode_of(ranked[0].scoring_mode),
        scoring_mode_version=_mode_of(ranked[0].scoring_mode_version),
        scored_candidates=len(scorable),
        unscorable_candidates=len(unscorable),
        excluded_candidates=_excluded_views(pool.excluded),
    )


def _mode_of(value: str | None) -> str:
    """Narrow a scored run's mode to the non-null string the response promises.

    :class:`~smartmatch_domain.scoring.StageBScore` types both mode fields as
    nullable because the superseded model produces neither, and this route can
    no longer produce that model — ``rank_cba_candidates`` is the only scorer it
    calls, and it stamps both fields on every score it returns. A
    ``None`` arriving here would mean the CBA scorer returned a pre-ADR-0016
    score, which is a defect and not a state to render, so it is raised rather
    than coerced to a plausible string.
    """
    if value is None:  # pragma: no cover - unreachable via the CBA scorer
        raise ApiError(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="match_run_scoring_mode_missing",
            message=(
                "The CBA scorer returned a score with no scoring mode. A stored "
                "run must say which model produced it; none is recorded rather "
                "than one guessed at."
            ),
        )
    return value


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

    # `is_shortlistable`, not `state is MEASURED`. The two agreed while a score
    # had only two states; ADR-0016 added a third, and a `policy_neutral`
    # candidate who was not selected satisfied neither this filter nor the
    # `unscorable` one below — so they disappeared from the read entirely, which
    # is the one outcome worse than showing them with a caveat. The domain
    # property is the authority on which candidates could have entered the
    # portfolio, and asking it is what keeps a fourth state from reopening this.
    considered = [
        item
        for item in explanations
        if item.is_shortlistable and item.subject_id not in shortlisted_ids
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
