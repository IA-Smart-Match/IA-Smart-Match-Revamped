"""Canonical, versioned matching factor registry.

Architecture v1.1 §1.2 requires **one** registry before any matching port, and
gate G1 ("factor registry + golden cases approved") blocks R1 until a named
program owner signs off on its contents.

Status: **APPROVED** — registry ``2.0.0-approved-oq-cba-004``, accepted
2026-09-05 by Danny Tran, Development Lead / program owner of record, per
``docs/architecture/decisions/ADR-0016-cba-scoring-policy.md``. The G1 approval
of 2026-09-03 (registry ``1.1.1-approved-g1-m6j``) is **superseded, not
deleted** — see "What supersession means here", below.

Legacy evidence (Nebiux-Team-IA-West-SmartMatch@bdce024, verified):

    src/config.py:97       FACTOR_REGISTRY declares 9 factors, weights sum 1.00
    src/matching/engine.py:109  compute_match_score computes only 7 of them
    README.md:229          documents the system as "8-factor matching"

`event_urgency` (0.05) and `coverage_diversity` (0.05) are declared and carry
normalized weight, but no implementation ever writes them into
`weighted_factor_scores`. Because `_normalize_weights` normalizes across all
nine declared keys while the sum is taken over only the seven computed ones,
**every legacy match score is systematically deflated: the maximum attainable
total is 0.90, not 1.00.** That is a correctness defect, not a naming
inconsistency, and it is why porting the legacy scoring path is blocked rather
than merely deferred.

See docs/architecture/review/contract-findings.md (F-001) and
docs/migration/migration-manifest.yaml (MM-002).

## What supersession means here (ADR-0016 Proposal 9, OQ-CBA-025)

The CBA four-factor set — Industry 30 / Role 25 / Topic 15 / Proximity 30 —
**replaces** the G1 two-factor set (``topic_relevance`` 0.70 /
``travel_burden`` 0.30) rather than extending it, and a score is not comparable
across that change. That is why the bump is major.

Replacing is not deleting. ``topic_relevance`` and ``travel_burden`` remain
declared, remain implemented, and keep the weights they were approved with,
because runs already stored against ``1.1.1-approved-g1-m6j`` must stay
**readable and reproducible** — the owner's OQ-CBA-025 decision is *coexist*,
and retirement waits until no pinned run references them. What they lose is
*active* weight: :attr:`FactorSpec.retired_in_version` takes them out of the
current model's denominator and numerator together, which is the one thing the
legacy defect got wrong.

The two models are therefore both nameable, and neither is reachable by
accident: :data:`CBA_PHYSICAL_MODEL` / :data:`CBA_VIRTUAL_MODEL` are the
current rulebook, :data:`SUPERSEDED_G1_MODEL` is the one that came before, and
:class:`ScoringModel` carries the registry version and the scoring mode a run
was actually produced under so no consumer has to infer either.

## Registry version and scoring mode are two independent pins

``REGISTRY_VERSION`` answers "which rulebook". A **scoring mode** answers
"which of that rulebook's models" — ``cba-physical-1`` scores four factors,
``cba-virtual-1`` scores three, and customer §11 is the reason the second
exists. A mode is never a registry version and a registry version is never a
mode (ADR-0016 Proposal 9): conflating them would make ``cba-virtual-1`` look
like a different rulebook, and would mint a registry version per event shape.

Two runs of the same registry in different modes carry the **same**
``registry_version`` and **different** ``registry_hash`` values — same
rulebook, different model. That is the intended reading, and golden case
``G-CBA-09`` pins it.

## Weights are computed here and nowhere else

The virtual weights are the physical weights re-normalized over the three
surviving factors: 0.30/0.70, 0.25/0.70, 0.15/0.70. They are **computed by
:func:`normalize_weights`, never typed**, which is why no float literal for
them appears in this module or in any factor module. :func:`display_weights`
renders them to six places for a screen or a fingerprint discussion; the
approved values (``0.428571`` / ``0.357143`` / ``0.214286``) are asserted
against that rendering in ``tests/unit/test_factor_registry.py`` rather than
declared anywhere in the runtime.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from smartmatch_domain.factors.cba_semantic_topic import CBA_SEMANTIC_TOPIC_FACTOR_KEY
from smartmatch_domain.factors.industry_match import INDUSTRY_MATCH_FACTOR_KEY
from smartmatch_domain.factors.proximity import (
    CBA_PHYSICAL_SCORING_MODE,
    CBA_PROXIMITY_FACTOR_KEY,
    CBA_SCORING_MODES,
    CBA_VIRTUAL_SCORING_MODE,
    UnknownScoringModeError,
)
from smartmatch_domain.factors.role_match import ROLE_MATCH_FACTOR_KEY

__all__ = [
    "APPROVED_SCORING_KEYS",
    "CBA_PHYSICAL_MODEL",
    "CBA_VIRTUAL_MODEL",
    "PROHIBITED_INPUTS",
    "PROPOSED_FACTORS",
    "REGISTRY_APPROVED_ON",
    "REGISTRY_APPROVER",
    "REGISTRY_STATUS",
    "REGISTRY_VERSION",
    "SCORING_MODELS",
    "SCORING_MODE_VERSION",
    "SUPERSEDED_G1_MODEL",
    "SUPERSEDED_REGISTRY_VERSION",
    "SUPERSEDED_SCORING_KEYS",
    "FactorKind",
    "FactorSpec",
    "RegistryNotApprovedError",
    "RegistryNotReadyError",
    "ScoringModel",
    "active_weights",
    "assert_registry_approved",
    "assert_scoring_ready",
    "display_weights",
    "factor_keys",
    "implemented_scoring_keys",
    "normalize_weights",
    "proposed_weights",
    "resolve_scoring_model",
]

#: ADR-0016 (accepted 2026-09-05) takes the registry from
#: ``1.1.1-approved-g1-m6j`` to ``2.0.0-approved-oq-cba-004``. A **major** bump,
#: because the CBA four-factor set replaces the G1 two-factor set rather than
#: extending it: a ``1.x`` score and a ``2.x`` score are not comparable, must
#: never be averaged, ranked, or charted together, and stay distinguishable by
#: this string alone. The version names the gate that approved it, as
#: ``1.1.1-approved-g1-m6j`` named G1 and this one names the open question
#: ADR-0016 closed.
REGISTRY_VERSION: Final[str] = "2.0.0-approved-oq-cba-004"

#: The pin every pre-ADR-0016 run carries. Kept as a named constant rather than
#: left in a changelog: a stored run pinned to it is read at *its own* pin, is
#: not re-scored, is not re-labelled, and is excluded from any aggregate
#: spanning both registries (ADR-0016 Proposal 9).
SUPERSEDED_REGISTRY_VERSION: Final[str] = "1.1.1-approved-g1-m6j"

#: Approved 2026-09-05 by Danny Tran (@dangt) per
#: ``docs/architecture/decisions/ADR-0016-cba-scoring-policy.md``, which records
#: all ten proposals approved as drafted with no amendments. The prior approval
#: (2026-09-03, gate G1) stands for :data:`SUPERSEDED_REGISTRY_VERSION`.
REGISTRY_STATUS: Final[str] = "approved"

#: Named rather than implied. "Approved" with no approver is a checkbox; the
#: registry's whole reason for existing is that somebody is accountable for
#: these numbers.
REGISTRY_APPROVER: Final[str] = "Danny Tran, Development Lead / program owner of record"

#: The date of the acceptance recorded in ADR-0016.
REGISTRY_APPROVED_ON: Final[str] = "2026-09-05"

#: The scoring-mode vocabulary's own version, pinned beside the mode name on
#: every run. Bumped when the *meaning* of a mode changes — which factors it
#: admits — so a stored ``cba-virtual-1`` is never re-read under a later
#: definition of that name.
SCORING_MODE_VERSION: Final[str] = "1.0.0"


class FactorKind(StrEnum):
    """How a factor participates in assignment.

    Architecture v1.1 §1.2 splits matching into Stage A (hard eligibility
    filtering) and Stage B (global CP-SAT optimization). A factor is one or the
    other; the same quantity may appear as both only when the contract says so
    explicitly, as the Engagement Load Index does (§1.3: hard cap in Stage A,
    soft penalty in Stage B).
    """

    #: Contributes positively to the Stage B utility function.
    SUITABILITY = "suitability"
    #: Subtracts from the Stage B utility function.
    PENALTY = "penalty"
    #: Removes a (professional, event) pair in Stage A. Never scored.
    ELIGIBILITY = "eligibility"


@dataclass(frozen=True, slots=True)
class FactorSpec:
    """One factor's canonical definition.

    The distinction between :attr:`proposed_weight` and :attr:`active_weight` is
    what prevents the legacy defect. The registry may *propose* a weight for a
    factor that is not built yet — that is what a proposal is for — but only an
    implemented factor contributes an *active* weight, and normalization ranges
    over active weights alone. The legacy conflated the two: it normalized
    across all nine declared weights while summing over the seven it computed,
    silently discarding the difference.

    :attr:`retired_in_version` is the same guard pointed the other way. A
    superseded factor is still implemented and still carries the weight it was
    approved with, because a stored run pinned to the registry version that
    approved it must stay reproducible; what it must not do is contribute to
    the *current* model. Taking it out of the numerator without taking it out
    of the denominator would be the legacy defect exactly, so
    :attr:`active_weight` and :func:`normalize_weights` both read this field
    before they read anything else.

    Attributes:
        key: Stable identifier. Never reused for a different meaning.
        display_label: Coordinator-facing name.
        kind: Stage A eligibility, or Stage B suitability/penalty.
        proposed_weight: The Stage B weight this registry proposes. For a
            retired factor this is the weight it was approved with, retained so
            :data:`SUPERSEDED_G1_MODEL` reproduces rather than re-derives.
            Zero for eligibility factors, which are not scored.
        implemented: Whether a verified implementation exists in this package.
            Active Stage B weight is governed by ``is_scoring and implemented
            and not is_retired`` together, not by this flag alone: an
            ELIGIBILITY factor may be ``implemented=True`` (a real Stage A
            filter exists for it) yet still carry zero Stage B weight, because
            :attr:`active_weight` and :func:`implemented_scoring_keys` both
            filter on :attr:`is_scoring` before they ever look at this flag.
        rationale: Why the factor exists, in operational terms.
        retired_in_version: The registry version in which this factor stopped
            carrying active weight, or ``None`` while it still does. Retired is
            not removed: the spec stays declared so an older stored score can
            still be labelled, explained, and reproduced.
    """

    key: str
    display_label: str
    kind: FactorKind
    proposed_weight: float
    implemented: bool
    rationale: str
    retired_in_version: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.proposed_weight <= 1.0:
            raise ValueError(f"{self.key}: proposed_weight must be in [0.0, 1.0]")
        if self.kind is FactorKind.ELIGIBILITY and self.proposed_weight != 0.0:
            raise ValueError(
                f"{self.key}: eligibility factors are Stage A filters and carry no Stage B weight"
            )
        if self.retired_in_version is not None and not self.retired_in_version.strip():
            raise ValueError(
                f"{self.key}: retired_in_version must name a registry version or be None; "
                "a blank string would say 'retired in nothing in particular'"
            )

    @property
    def is_scoring(self) -> bool:
        """Whether this factor participates in the Stage B utility function."""
        return self.kind is not FactorKind.ELIGIBILITY

    @property
    def is_retired(self) -> bool:
        """Whether a later registry version took this factor's active weight."""
        return self.retired_in_version is not None

    @property
    def active_weight(self) -> float:
        """The weight this factor actually contributes today.

        Zero unless the factor is a scoring factor, implemented, and not
        retired. A proposed-but-unbuilt factor contributes nothing, a retired
        one contributes nothing, and — critically — :func:`normalize_weights`
        never counts either in the denominator.
        """
        if not self.is_scoring or not self.implemented or self.is_retired:
            return 0.0
        return self.proposed_weight


#: The canonical set. Registry order is the order an explanation renders in, so
#: the current CBA model's four factors come first, the two factors
#: ``2.0.0-approved-oq-cba-004`` superseded keep their relative order after
#: them, and the Stage A filter comes last.
#:
#: Weights over the *current* model's factors sum to 1.0 — asserted by
#: ``tests/unit/test_factor_registry.py``, so the legacy deflation defect
#: cannot recur unnoticed in either direction.
PROPOSED_FACTORS: Final[tuple[FactorSpec, ...]] = (
    FactorSpec(
        key=INDUSTRY_MATCH_FACTOR_KEY,
        display_label="Industry Match",
        kind=FactorKind.SUITABILITY,
        proposed_weight=0.30,
        implemented=True,
        rationale=(
            "Customer §5/§7: whether the speaker's one primary NAICS sector is "
            "among the sectors the Speaker Request targets. Joint-heaviest CBA "
            "factor per ADR-0016 (accepted 2026-09-05)."
        ),
    ),
    FactorSpec(
        key=ROLE_MATCH_FACTOR_KEY,
        display_label="Role Match",
        kind=FactorKind.SUITABILITY,
        proposed_weight=0.25,
        implemented=True,
        rationale=(
            "Customer §5/§8: whether the speaker's one primary role category is "
            "among the categories the Speaker Request targets. Per ADR-0016."
        ),
    ),
    FactorSpec(
        key=CBA_SEMANTIC_TOPIC_FACTOR_KEY,
        display_label="Topic Fit",
        kind=FactorKind.SUITABILITY,
        proposed_weight=0.15,
        implemented=True,
        rationale=(
            "Customer §5/§9: semantic fit between the request's description and "
            "the speaker's recorded topic evidence, with §9's stated neutral "
            "policy for an observed absence. Binds the registry's Topic slot to "
            "cba_semantic_topic rather than topic_relevance (OQ-CBA-027): §9 "
            "asks for a semantic comparison and a policy-neutral third state, "
            "and the lexical set-overlap factor implements neither."
        ),
    ),
    FactorSpec(
        key=CBA_PROXIMITY_FACTOR_KEY,
        display_label="Proximity",
        kind=FactorKind.SUITABILITY,
        proposed_weight=0.30,
        implemented=True,
        rationale=(
            "Customer §5/§10: banded distance from the CPP campus — Near/Mid/Far, "
            "scored 1.00/0.60/0.20. A SUITABILITY factor, not a penalty: the band "
            "table is stated on the proximity scale (nearer is better), so it "
            "contributes directly and is never complemented. Excluded entirely "
            "under cba-virtual-1 (customer §11). Joint-heaviest per ADR-0016."
        ),
    ),
    FactorSpec(
        key="topic_relevance",
        display_label="Topic Relevance",
        kind=FactorKind.SUITABILITY,
        proposed_weight=0.70,
        implemented=True,
        rationale=(
            "Lexical expertise/topic set overlap. Primary scoring factor of the "
            "G1-approved two-factor set (2026-09-03). Superseded by "
            "cba_semantic_topic in 2.0.0-approved-oq-cba-004 (OQ-CBA-027) and "
            "retained, not deleted, so runs pinned to 1.1.1-approved-g1-m6j stay "
            "reproducible (OQ-CBA-025: coexist)."
        ),
        retired_in_version=REGISTRY_VERSION,
    ),
    FactorSpec(
        key="travel_burden",
        display_label="Travel Burden (proximity)",
        kind=FactorKind.PENALTY,
        proposed_weight=0.30,
        implemented=True,
        rationale=(
            "Continuous straight-line travel penalty (v1.1 §3.1). Secondary "
            "scoring factor of the G1-approved set. Superseded by the banded "
            "'proximity' factor in 2.0.0-approved-oq-cba-004 and retained under "
            "OQ-CBA-025 (coexist): retirement waits until no pinned run "
            "references it, and stored 1.x runs must stay reproducible."
        ),
        retired_in_version=REGISTRY_VERSION,
    ),
    FactorSpec(
        key="availability",
        display_label="Availability / Blackout",
        kind=FactorKind.ELIGIBILITY,
        proposed_weight=0.0,
        implemented=True,
        rationale=(
            "Applied after shortlist per program direction: match before "
            "availability; coordinator batch-invites and tracks responses. "
            "Implemented by smartmatch_domain.eligibility."
            "apply_availability_filter — a Stage A filter, never a Stage B "
            "scorer, so it stays weight 0 regardless of this flag."
        ),
    ),
)

#: The Stage B scoring factors ADR-0016 approved on 2026-09-05. The readiness
#: assertion below requires the current model's implemented set to equal this
#: set exactly — neither a missing implementation nor an extra one is
#: acceptable.
APPROVED_SCORING_KEYS: Final[frozenset[str]] = frozenset(
    {
        INDUSTRY_MATCH_FACTOR_KEY,
        ROLE_MATCH_FACTOR_KEY,
        CBA_SEMANTIC_TOPIC_FACTOR_KEY,
        CBA_PROXIMITY_FACTOR_KEY,
    }
)

#: What gate G1 approved on 2026-09-03, kept so a ``1.x`` run can be reproduced
#: by name rather than by remembering which two factors used to be in force.
SUPERSEDED_SCORING_KEYS: Final[frozenset[str]] = frozenset({"topic_relevance", "travel_burden"})

#: Inputs the registry schema refuses, enforced by :class:`FactorSpec` review and
#: by ``tests/unit/test_factor_registry.py`` — not by convention (v1.1 §1.3).
PROHIBITED_INPUTS: Final[frozenset[str]] = frozenset(
    {
        "age",
        "disability",
        "health_inference",
        "protected_characteristic",
        "subjective_admin_opinion",
        "unrelated_student_feedback",
        "unverified_external_activity",
        "llm_generated_assumption",
    }
)


@dataclass(frozen=True, slots=True)
class ScoringModel:
    """The factor set, registry version, and mode one run actually scored under.

    A run needs three facts to be reproducible, and all three travel together
    here rather than being re-derived at each call site: which rulebook
    (:attr:`registry_version`), which of its models (:attr:`scoring_mode`), and
    which factors that model admits (:attr:`scoring_keys`).

    Attributes:
        registry_version: The rulebook. :data:`REGISTRY_VERSION` for a current
            model, :data:`SUPERSEDED_REGISTRY_VERSION` for the G1 one.
        scoring_mode: A member of
            :data:`~smartmatch_domain.factors.proximity.CBA_SCORING_MODES`, or
            ``None`` for the superseded model. ``None`` is not a default and is
            not ``cba-physical-1``: a run with no mode is a **pre-ADR-0016**
            run, which is exactly how ADR-0016 Proposal 7 says a stored payload
            lacking the field must be read.
        scoring_mode_version: :data:`SCORING_MODE_VERSION` when a mode is set,
            ``None`` otherwise.
        scoring_keys: The factor keys this model scores, in registry order.
        is_current: Whether this model is the one :data:`REGISTRY_VERSION`
            declares. ``False`` means the model is retained for reproducing
            stored runs and must not be selected for a new one.
    """

    registry_version: str
    scoring_mode: str | None
    scoring_mode_version: str | None
    scoring_keys: tuple[str, ...]
    is_current: bool

    def __post_init__(self) -> None:
        if not self.scoring_keys:
            raise ValueError("scoring_keys: a scoring model must score at least one factor")
        if (self.scoring_mode is None) != (self.scoring_mode_version is None):
            raise ValueError(
                "scoring_mode and scoring_mode_version must be set or unset together; "
                f"got {self.scoring_mode!r} and {self.scoring_mode_version!r}"
            )
        if self.scoring_mode is not None and self.scoring_mode not in CBA_SCORING_MODES:
            raise UnknownScoringModeError(
                f"scoring_mode: must be one of {sorted(CBA_SCORING_MODES)} or None, got "
                f"{self.scoring_mode!r}. The mode vocabulary is closed (ADR-0016 Proposal 5)."
            )


def _keys_in_registry_order(keys: frozenset[str]) -> tuple[str, ...]:
    """Order a key set the way the registry declares it, so output is stable."""
    return tuple(spec.key for spec in PROPOSED_FACTORS if spec.key in keys)


#: Customer §5's four factors. The default model for a new run.
CBA_PHYSICAL_MODEL: Final[ScoringModel] = ScoringModel(
    registry_version=REGISTRY_VERSION,
    scoring_mode=CBA_PHYSICAL_SCORING_MODE,
    scoring_mode_version=SCORING_MODE_VERSION,
    scoring_keys=_keys_in_registry_order(APPROVED_SCORING_KEYS),
    is_current=True,
)

#: Customer §11: proximity is excluded outright for a virtual event, and the
#: three survivors' weights are re-normalized over the surviving set by
#: :func:`normalize_weights`. The exclusion is known before any candidate is
#: read, which is what distinguishes it from re-spreading weight around a
#: per-candidate unknown — that stays refused (ADR-0016 Proposal 6).
CBA_VIRTUAL_MODEL: Final[ScoringModel] = ScoringModel(
    registry_version=REGISTRY_VERSION,
    scoring_mode=CBA_VIRTUAL_SCORING_MODE,
    scoring_mode_version=SCORING_MODE_VERSION,
    scoring_keys=_keys_in_registry_order(APPROVED_SCORING_KEYS - {CBA_PROXIMITY_FACTOR_KEY}),
    is_current=True,
)

#: The G1 two-factor model. Not selectable for a new run (``is_current`` is
#: ``False``); it exists so a run stored under
#: :data:`SUPERSEDED_REGISTRY_VERSION` can be reproduced and explained at its
#: own pin rather than re-scored under a rulebook it never saw.
SUPERSEDED_G1_MODEL: Final[ScoringModel] = ScoringModel(
    registry_version=SUPERSEDED_REGISTRY_VERSION,
    scoring_mode=None,
    scoring_mode_version=None,
    scoring_keys=_keys_in_registry_order(SUPERSEDED_SCORING_KEYS),
    is_current=False,
)

#: Every model a caller may name, keyed by scoring mode. The superseded model
#: is deliberately absent: it has no mode, and giving it one would put a
#: pre-ADR-0016 rulebook inside the ADR's closed vocabulary.
SCORING_MODELS: Final[Mapping[str, ScoringModel]] = MappingProxyType(
    {
        CBA_PHYSICAL_SCORING_MODE: CBA_PHYSICAL_MODEL,
        CBA_VIRTUAL_SCORING_MODE: CBA_VIRTUAL_MODEL,
    }
)


def resolve_scoring_model(scoring_mode: str | None) -> ScoringModel:
    """Return the model a run scores under, from its mode.

    Args:
        scoring_mode: A member of :data:`SCORING_MODELS`, or ``None`` for a
            pre-ADR-0016 run.

    Returns:
        The matching :class:`ScoringModel`. ``None`` resolves to
        :data:`SUPERSEDED_G1_MODEL` — a run that names no mode predates the
        vocabulary and is read at the pin it was produced under, never
        upgraded to ``cba-physical-1`` (ADR-0016 Proposal 7).

    Raises:
        UnknownScoringModeError: for any string outside the closed vocabulary.
            Refused rather than defaulted: a typo'd mode that silently became
            the physical model would score a virtual event on proximity.
    """
    if scoring_mode is None:
        return SUPERSEDED_G1_MODEL
    try:
        return SCORING_MODELS[scoring_mode]
    except KeyError:
        raise UnknownScoringModeError(
            f"scoring_mode: must be one of {sorted(SCORING_MODELS)} or None, got "
            f"{scoring_mode!r}. The mode vocabulary is closed (ADR-0016 Proposal 5); "
            "an unrecognised mode is refused rather than defaulted."
        ) from None


class RegistryNotApprovedError(RuntimeError):
    """Raised when scoring is attempted before the G1 gate closes."""


def assert_registry_approved() -> None:
    """Fail closed unless the factor registry has been approved.

    Any code path that produces a user-visible match score must call this first.
    Architecture v1.1 gate G1 blocks R1 on registry approval; failing closed here
    means the gate is enforced by the code rather than by a checklist.

    Raises:
        RegistryNotApprovedError: while ``REGISTRY_STATUS`` is not ``"approved"``.
    """
    if REGISTRY_STATUS != "approved":
        raise RegistryNotApprovedError(
            f"Factor registry {REGISTRY_VERSION} is {REGISTRY_STATUS!r}. "
            "Architecture v1.1 gate G1 blocks match scoring until the program owner "
            "approves the registry contents and the golden case set. "
            "See docs/architecture/review/contract-findings.md (F-001)."
        )


class RegistryNotReadyError(RuntimeError):
    """Raised when the implemented scoring set is not the approved scoring set."""


def factor_keys() -> tuple[str, ...]:
    """Return every declared factor key, in registry order.

    Includes retired factors. An explanation for a stored ``1.x`` run still has
    to order ``topic_relevance`` and ``travel_burden``, and dropping them from
    this tuple would leave that ordering undefined.
    """
    return tuple(spec.key for spec in PROPOSED_FACTORS)


def implemented_scoring_keys() -> frozenset[str]:
    """Return the keys of every implemented, non-retired Stage B factor."""
    return frozenset(
        spec.key
        for spec in PROPOSED_FACTORS
        if spec.implemented and spec.is_scoring and not spec.is_retired
    )


def assert_scoring_ready() -> None:
    """Fail closed unless the implemented scoring set is exactly the approved set.

    :func:`assert_registry_approved` proves the program owner signed off. This
    proves the code actually built what was signed off — the window this closes
    is an "approved" registry scoring with only a subset of the approved
    factors, which is the legacy deflation defect in a new costume.

    Both current models are checked, not just the physical one: ``cba-virtual-1``
    is reachable from any run whose event is virtual, and a virtual model whose
    weights did not sum to one would deflate exactly the way the legacy engine
    did, on a code path a physical-only check never touches.

    Raises:
        RegistryNotReadyError: when the implemented scoring set differs from
            :data:`APPROVED_SCORING_KEYS`, or when either current model's
            normalized weights do not sum to 1.0 within ``1e-9``.
    """
    implemented = implemented_scoring_keys()
    if implemented != APPROVED_SCORING_KEYS:
        missing = APPROVED_SCORING_KEYS - implemented
        extra = implemented - APPROVED_SCORING_KEYS
        raise RegistryNotReadyError(
            "Implemented Stage B scoring set does not match the approved set "
            f"{sorted(APPROVED_SCORING_KEYS)}. "
            f"Missing: {sorted(missing) or 'none'}. Extra: {sorted(extra) or 'none'}."
        )

    for model in (CBA_PHYSICAL_MODEL, CBA_VIRTUAL_MODEL):
        weight_total = sum(normalize_weights(model=model).values())
        if abs(weight_total - 1.0) > 1e-9:
            raise RegistryNotReadyError(
                f"Normalized Stage B weights for {model.scoring_mode!r} sum to "
                f"{weight_total!r}, not 1.0. The implemented scoring set is approved "
                "but normalize_weights() is not sum-to-one; scoring must not proceed."
            )


def proposed_weights() -> Mapping[str, float]:
    """Return the weights this registry *proposes*, including retired factors.

    For review and documentation. Never use this to score — it includes factors
    no current model admits, and summing scores against them is exactly the
    legacy defect. Use :func:`normalize_weights` instead.
    """
    return MappingProxyType({spec.key: spec.proposed_weight for spec in PROPOSED_FACTORS})


def active_weights() -> Mapping[str, float]:
    """Return the unnormalized weights the current model's factors carry."""
    return MappingProxyType(
        {spec.key: spec.active_weight for spec in PROPOSED_FACTORS if spec.active_weight > 0.0}
    )


def normalize_weights(
    weights: Mapping[str, float] | None = None,
    *,
    model: ScoringModel = CBA_PHYSICAL_MODEL,
) -> Mapping[str, float]:
    """Normalize Stage B weights across **one model's factor set only**.

    This is the corrected form of the legacy ``_normalize_weights``. The legacy
    normalized across all nine declared keys but summed over the seven it
    actually computed, losing the remaining weight mass and capping every score
    at 0.90. Here the denominator and the numerator range over the same set, so
    the returned weights always sum to 1.0 (or are all zero when no factor in
    the model has positive weight).

    This is also where customer §11's virtual redistribution happens, and it
    introduces no new arithmetic to do it: :data:`CBA_VIRTUAL_MODEL` names three
    factors instead of four, and proportional re-normalization over that set is
    what this function already did. The §11 weights are therefore *computed*,
    never typed.

    Args:
        weights: Optional overrides keyed by factor key. Keys outside
            ``model.scoring_keys`` are ignored. Omitted keys fall back to the
            registry default. Negative values are rejected.
        model: The scoring model to normalize over. Defaults to
            :data:`CBA_PHYSICAL_MODEL`; pass :data:`CBA_VIRTUAL_MODEL` for a
            virtual event, or :data:`SUPERSEDED_G1_MODEL` to reproduce a stored
            ``1.x`` run.

    Returns:
        An immutable mapping over the model's factors summing to 1.0, or all
        zeros when the total is zero.

    Raises:
        ValueError: if any supplied weight is negative.
    """
    by_key = {spec.key: spec for spec in PROPOSED_FACTORS}
    scoring = {
        key: by_key[key].proposed_weight
        for key in model.scoring_keys
        if key in by_key and by_key[key].implemented and by_key[key].is_scoring
    }

    if weights is not None:
        for key, value in weights.items():
            if value < 0.0:
                raise ValueError(f"{key}: weight must not be negative (got {value})")
            if key in scoring:
                scoring[key] = float(value)

    total = sum(scoring.values())
    if total <= 0.0:
        return MappingProxyType(dict.fromkeys(scoring, 0.0))

    return MappingProxyType({key: value / total for key, value in scoring.items()})


#: Decimal places :func:`display_weights` renders to. Six, because ADR-0016
#: Proposal 6 states the virtual weights to six places — for display and for a
#: fingerprint discussion, never for the arithmetic, which uses the unrounded
#: quotient so two models that differ in the seventh place still differ.
_WEIGHT_DISPLAY_PRECISION: Final[int] = 6


def display_weights(model: ScoringModel = CBA_PHYSICAL_MODEL) -> Mapping[str, float]:
    """Render a model's normalized weights to six places, for a human.

    The approved §11 values — Industry ``0.428571``, Role ``0.357143``, Topic
    ``0.214286`` — are what this returns for :data:`CBA_VIRTUAL_MODEL`. They are
    stated in ADR-0016 and asserted in ``tests/unit/test_factor_registry.py``
    against this function's output; they are deliberately not typed as literals
    anywhere in the runtime, because a typed weight is a second source of truth
    that can drift from the division that produced it.

    Never use the result to score. Rounding before composing would let two
    genuinely different weight sets compose identically.
    """
    return MappingProxyType(
        {
            key: round(value, _WEIGHT_DISPLAY_PRECISION)
            for key, value in normalize_weights(model=model).items()
        }
    )
