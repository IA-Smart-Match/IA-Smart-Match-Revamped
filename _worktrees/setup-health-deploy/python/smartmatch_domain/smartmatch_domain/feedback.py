"""Coordinator feedback validation and shadow-mode weight proposals.

Ported from Nebiux-Team-IA-West-SmartMatch@bdce024:src/feedback/acceptance.py
under migration manifest entry MM-005.

Retained: the *shape* of the loop — aggregation of accept/decline decisions into
counts, and a bounded per-factor weight-delta proposal computed as
min(MAX_FACTOR_DELTA, PER_REASON_BUMP * count), with both constants carried
forward unchanged (0.08 and 0.03, from the legacy src/config.py:125-129
env-var defaults).

Replaced, not retained: the decline-reason vocabulary (finding F-18) and the
reason-to-factor mapping (finding F-19). The legacy vocabulary was five prose
strings; ``DeclineReason`` here is a seven-member enum of snake_case codes.
The legacy contained *two* reason-to-factor maps that contradict each other —
"Speaker already committed" maps to historical_conversion in acceptance.py and
to volunteer_fatigue in service.py — so there was no single mapping to carry
forward. The closed-enum redesign is defensible, but it is a replacement;
calling it retention hid the decision. See MM-005 ``behavior_replaced``.

Rejected: the Streamlit imports and ``render_*`` functions (presentation in a
domain module); ``st.session_state`` as authoritative storage; the CSV/JSONL
append in ``_persist_to_csv`` (business writes to repository-local files are
prohibited — PostgreSQL is the system of record); and the demo-fixture fallback
in ``render_feedback_sidebar`` (src/feedback/acceptance.py:299-311), which
served fabricated aggregates when ``demo_mode`` was set in session state.
(Finding F-22: this was previously attributed here to ``aggregate_feedback``.
It is not there — ``aggregate_feedback`` returns an explicit all-zero dict on
an empty log and never loads a fixture.)

Architecture v1.1 Appendix B requires this loop stay **shadow-mode**: it
proposes weight deltas, and a human approves them. Generative AI never chooses
ranking weights (v1.1 §1.2), and neither does this module — it only computes an
arithmetic proposal from recorded human decisions, bounded so no single feedback
round can swing the model.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final, final

__all__ = [
    "MAX_FACTOR_DELTA",
    "MIN_DECLINES_PER_FACTOR",
    "PER_REASON_BUMP",
    "REASON_TO_FACTOR",
    "Decision",
    "DeclineReason",
    "FeedbackEntry",
    "WeightProposal",
    "aggregate",
    "propose_weight_adjustments",
]

#: Maximum a single factor's weight may move in one proposal. Carried forward
#: from the legacy ``OPTIMIZER_MAX_FACTOR_DELTA`` default (0.08), which was a
#: reasonable bound; here it is a domain constant rather than an env var, so a
#: misconfigured environment cannot widen the blast radius.
MAX_FACTOR_DELTA: Final[float] = 0.08

#: Weight bump applied per net decline attributed to a factor. Carried forward
#: from the legacy ``OPTIMIZER_REASON_WEIGHT_BUMP`` default (0.03).
PER_REASON_BUMP: Final[float] = 0.03

#: Below this many declines *implicating one factor*, that factor's weight is
#: not proposed to move at all. The legacy had no floor and would happily
#: "learn" from a single click. The floor counts declines rather than decisions
#: because declines are the only evidence a proposal is derived from: counting
#: every decision let unrelated accepts unlock a movement driven by one decline,
#: which is the failure the floor exists to prevent, and it counts them per
#: factor because a floor met in aggregate still moves an individual weight off
#: a single decline.
MIN_DECLINES_PER_FACTOR: Final[int] = 5


class Decision(StrEnum):
    """A coordinator's decision on a proposed assignment."""

    ACCEPTED = "accepted"
    DECLINED = "declined"


class DeclineReason(StrEnum):
    """Why a coordinator declined a proposal.

    A closed vocabulary, ported from the legacy ``DECLINE_REASONS`` list. Free
    text is deliberately not a reason code: it cannot be aggregated, and the
    legacy's attempt to map free text to factors by substring matching was the
    source of its noisiest weight suggestions.
    """

    WRONG_TOPIC = "wrong_topic"
    WRONG_ROLE = "wrong_role"
    TOO_FAR = "too_far"
    UNAVAILABLE = "unavailable"
    OVERCOMMITTED = "overcommitted"
    RECENTLY_ENGAGED = "recently_engaged"
    OTHER = "other"


#: Which factor a decline reason implicates. ``OTHER`` maps to nothing on
#: purpose — an uncategorized decline must not move any weight.
REASON_TO_FACTOR: Final[Mapping[DeclineReason, str | None]] = MappingProxyType(
    {
        DeclineReason.WRONG_TOPIC: "topic_relevance",
        DeclineReason.WRONG_ROLE: "role_fit",
        DeclineReason.TOO_FAR: "travel_burden",
        DeclineReason.UNAVAILABLE: "availability",
        DeclineReason.OVERCOMMITTED: "engagement_load",
        DeclineReason.RECENTLY_ENGAGED: "repeat_penalty",
        DeclineReason.OTHER: None,
    }
)


@dataclass(frozen=True, slots=True)
class FeedbackEntry:
    """One recorded coordinator decision.

    Attributes:
        match_run_id: The immutable match run the proposal came from. Feedback
            is always attributed to a specific versioned run, so a weight
            proposal can be traced to the exact model that produced the
            proposals being judged.
        decision: Accepted or declined.
        reason: Required when declined, forbidden when accepted.
    """

    match_run_id: str
    decision: Decision
    reason: DeclineReason | None = None

    def __post_init__(self) -> None:
        if not self.match_run_id.strip():
            raise ValueError("feedback must be attributed to a match run")
        if self.decision is Decision.DECLINED and self.reason is None:
            raise ValueError("a declined proposal must carry a decline reason")
        if self.decision is Decision.ACCEPTED and self.reason is not None:
            raise ValueError("an accepted proposal must not carry a decline reason")


@dataclass(frozen=True, slots=True)
class FeedbackAggregate:
    """Counts derived from a set of feedback entries."""

    total: int
    accepted: int
    declined: int
    reason_counts: Mapping[DeclineReason, int]

    @property
    def acceptance_rate(self) -> float | None:
        """Fraction accepted, or ``None`` when there is no feedback.

        ``None`` rather than ``0.0``: an empty feedback set means *unknown*, and
        rendering it as a 0% acceptance rate is the kind of confident-looking
        fabrication v1.1 §5.5 exists to eliminate.
        """
        if self.total == 0:
            return None
        return round(self.accepted / self.total, 4)


@final
@dataclass(frozen=True, slots=True)
class WeightProposal:
    """A shadow-mode proposal to adjust factor weights.

    Never applied automatically. Architecture v1.1 Appendix B requires human
    approval, and :attr:`requires_approval` is always ``True`` — it exists so
    the requirement is visible in the payload the UI renders, not so it can be
    toggled.

    Attributes:
        deltas: Per-factor weight change, each bounded by :data:`MAX_FACTOR_DELTA`.
        based_on: The aggregate the proposal was derived from.
        rationale: Human-readable explanation, one line per implicated factor.
    """

    deltas: Mapping[str, float]
    based_on: FeedbackAggregate
    rationale: tuple[str, ...]

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Refuse subclassing.

        ``@final`` closes the override route for anything type-checked, but a
        subclass overriding :attr:`requires_approval` still satisfies
        ``isinstance(x, WeightProposal)`` at runtime, and a consumer typed on
        this class would accept it. The control is structural everywhere else —
        frozen, slotted, not a constructor field — so it is structural here too.
        """
        raise TypeError("WeightProposal is final: human approval is not an overridable property")

    @property
    def requires_approval(self) -> bool:
        """Always ``True``. Weight changes are a human decision."""
        return True


def aggregate(entries: Sequence[FeedbackEntry]) -> FeedbackAggregate:
    """Count decisions and decline reasons.

    Returns zeroed counts for an empty input rather than substituting demo
    fixtures, which is what the legacy did when no feedback had been recorded.
    """
    accepted = sum(1 for e in entries if e.decision is Decision.ACCEPTED)
    declined = sum(1 for e in entries if e.decision is Decision.DECLINED)
    reasons: Counter[DeclineReason] = Counter(e.reason for e in entries if e.reason is not None)
    return FeedbackAggregate(
        total=len(entries),
        accepted=accepted,
        declined=declined,
        reason_counts=MappingProxyType(dict(reasons)),
    )


def propose_weight_adjustments(entries: Sequence[FeedbackEntry]) -> WeightProposal | None:
    """Derive a bounded, shadow-mode weight proposal from recorded decisions.

    A factor implicated by declines gets its weight nudged up, on the reasoning
    that the model under-weighted something coordinators clearly care about. The
    nudge is ``PER_REASON_BUMP`` per decline, clamped to ``MAX_FACTOR_DELTA``.

    **The proposal is un-normalized, and its application semantics are not
    specified.** Each delta is bounded; their sum is not, so a round that
    implicates every factor proposes +0.48 against weights that total 1.0.
    Whether that is corrected by normalizing on apply, by bounding the sum
    here at proposal time, or by both is a decision that belongs with the
    consumer applying it — weight sets arrive in M1/M8 behind gate G1, and
    until one exists there is nothing to normalize against and no way to tell
    which number a human is actually approving. This is a recorded deferral
    (review finding F-25, ``docs/plans/defect-remediation.md`` §4.5), not an
    oversight, and ``test_aggregate_movement_is_deliberately_unbounded`` pins
    the present behavior so the deferral cannot be mistaken for a bound.

    Args:
        entries: Recorded decisions, typically scoped to one tenant and a recent
            window by the caller.

    Returns:
        A proposal, or ``None`` when there is too little feedback to justify one
        (no factor reaching :data:`MIN_DECLINES_PER_FACTOR` declines of its own,
        or no categorized declines at all). ``None`` means "no opinion" and must
        be rendered as such — never as a proposal of zero deltas, which would
        read as a positive finding that the current weights are correct.
    """
    counts = aggregate(entries)

    deltas: dict[str, float] = {}
    rationale: list[str] = []

    for reason, count in sorted(counts.reason_counts.items(), key=lambda kv: kv[0].value):
        factor = REASON_TO_FACTOR[reason]
        if factor is None or count < MIN_DECLINES_PER_FACTOR:
            continue
        delta = min(MAX_FACTOR_DELTA, PER_REASON_BUMP * count)
        deltas[factor] = round(delta, 4)
        rationale.append(
            f"{count} decline(s) for {reason.value!r} suggest {factor!r} is "
            f"under-weighted; proposing +{delta:.4f}"
        )

    if not deltas:
        return None

    return WeightProposal(
        deltas=MappingProxyType(deltas),
        based_on=counts,
        rationale=tuple(rationale),
    )
