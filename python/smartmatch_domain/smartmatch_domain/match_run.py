"""What one match run pins, and how its inputs are fingerprinted (card M8a).

Plan `docs/plans/2026-08-28-g1-matching-m1-m10-plan.md` card M8 says a stored
run carries "inputs hash, registry version, weights, optimizer + route-estimate
version pins, tenant/unit scoping, created-at", and the G1 workshop worksheet
(`docs/plans/workshops/g1-workshop-output-worksheet.md`, agenda item 4) settles
why: weights may only change through the MM-005 shadow-evaluation gate, and
"every run records registry version hash". A weight set that changed without a
recorded pin would silently re-interpret every score already shown to a
coordinator — the run would still be there, and nothing would say it had been
produced under a different rulebook.

This module is the pure half of that: the pin record itself, and the two
digests that make a run's inputs reproducible. It holds no storage, no session,
and no identifiers of its own — :mod:`smartmatch_persistence.match_runs` writes
the row and :mod:`smartmatch_worker.handlers` assembles it on the durable
command path.

## Why a digest rather than the inputs themselves

A run's candidate pool is the thing that has to be identical for two runs to be
comparable, and storing the pool on the run row would make the row grow with
the pool while still not proving anything: two rows carrying the same list are
equal only if somebody compares them element by element. A digest makes that
comparison a single equality, and it makes an accidental difference — one extra
candidate, a utility that moved in the fourth decimal — loud rather than
invisible.

It is deliberately **not** an identity in the ADR-0012 sense: nothing dedupes
on it and nothing looks a run up by it. Two runs with the same inputs hash are
two honest runs of the same inputs, which is exactly what a re-run for
comparison is. The uniqueness that does exist lives on ``(tenant_id, job_id)``
in the database, because a command executes once.

## Floats are formatted before they are hashed

Every float is rendered with ``repr``, which for a Python float is the shortest
string that round-trips back to the identical value. Hashing
``str(round(x, 6))`` instead would let two genuinely different weight sets
fingerprint identically, and hashing a float's raw bytes would make the digest
depend on the platform. Rendering makes it stable across processes and machines
for identical values, and different for any value that is actually different.

## Unknown is not zero here either (ADR-0011)

Nothing in this module invents a value. A pin that is not known is not
recordable: :class:`MatchRunPins` refuses a blank string in every field rather
than storing ``""`` or ``"unknown"``, because a run whose registry version is
the empty string is a run nobody can reproduce, and that should fail at the
moment of assembly rather than years later when somebody tries.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import ClassVar, Final

__all__ = [
    "MATCH_RUN_COMMAND_TYPE",
    "ROUTE_ESTIMATE_SOURCES",
    "MatchRunPins",
    "inputs_fingerprint",
    "weights_fingerprint",
]

#: The durable command that produces a ``match_run`` row. One string, named
#: once, so the API router that submits it (card M8b) and the worker handler
#: that executes it cannot drift apart by a typo — the failure mode of a
#: mistyped command type is a job that is accepted, dispatched, and then failed
#: as unregistered, which reads to a coordinator as a broken platform rather
#: than as a broken constant.
MATCH_RUN_COMMAND_TYPE: Final[str] = "match-run.create"

#: Where a run's travel estimate came from. ``straight_line`` is the haversine
#: estimate behind
#: :data:`smartmatch_domain.factors.travel_burden.TRAVEL_BURDEN_FORMULA_VERSION`;
#: ``route_matrix`` is the D3 provider that is still deferred (that module:
#: "This module never calls a network, a provider, or a route-matrix API").
#: Both names exist now so a stored run says which one produced it, and so the
#: day D3 lands the older runs do not silently read as having used it.
ROUTE_ESTIMATE_SOURCES: Final[frozenset[str]] = frozenset({"straight_line", "route_matrix"})

#: Prefix on every digest this module returns. Recorded rather than implied: a
#: bare hex string is a hash of nothing in particular, and the day a stronger
#: digest is adopted the stored values have to stay distinguishable from the
#: ones that came before, or every historical comparison silently becomes a
#: comparison of unrelated numbers.
_DIGEST_PREFIX: Final[str] = "sha256:"


def _digest(payload: object) -> str:
    """Return the prefixed SHA-256 of ``payload`` rendered as canonical JSON.

    ``sort_keys`` and a separator pair with no spaces make the rendering
    independent of dictionary insertion order and of the ``json`` module's
    default spacing, so the same values always produce the same bytes.
    ``ensure_ascii`` is left at its default, which escapes every non-ASCII
    character — the digest is then a function of the string's code points
    rather than of the encoder's Unicode handling.
    """
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return _DIGEST_PREFIX + hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _rendered_weights(weights: Mapping[str, float]) -> dict[str, str]:
    """Render a weight map to round-trippable strings; see the module docstring."""
    return {name: repr(float(weight)) for name, weight in weights.items()}


def weights_fingerprint(weights: Mapping[str, float]) -> str:
    """Fingerprint the factor weights a run scored with.

    The worksheet's "every run records registry version hash" is two facts, not
    one, and this is the second. The version string
    (:data:`smartmatch_domain.factor_registry.REGISTRY_VERSION`) says which
    release of the registry was in force; this digest says what its weights
    actually were. They are stored side by side because either alone can lie: a
    version string is a label somebody types, and a weight map with no version
    attached cannot be traced back to the decision that approved it.

    Args:
        weights: Factor name to weight, typically
            :func:`smartmatch_domain.factor_registry.active_weights`'s output
            or its normalization. Order is irrelevant — the rendering sorts.

    Returns:
        ``"sha256:"`` followed by 64 hex characters.
    """
    return _digest(_rendered_weights(weights))


def inputs_fingerprint(
    *,
    event_need_id: str,
    candidate_subject_ids: Sequence[str],
    candidate_utilities: Sequence[float],
    portfolio_size: int,
    random_seed: int,
    weights: Mapping[str, float],
) -> str:
    """Fingerprint everything that determines a run's outcome.

    Every argument is an input the optimizer or the scoring path actually
    consumes, and nothing else is included: a digest that folded in a timestamp
    or a job identifier would differ on every run and could never answer the
    question it exists for, which is "were these two runs given the same
    problem?"

    The candidate pool is folded in **paired and sorted by subject id**, not in
    the order it arrived. ``solve_portfolio`` is explicitly order-independent
    ("order does not affect the result"), so two callers listing the same pool
    differently are posing the identical problem and must fingerprint alike —
    otherwise the digest would report a difference the solver does not have.

    Args:
        event_need_id: The need the portfolio is selected for.
        candidate_subject_ids: The pool's subject ids, positionally aligned
            with ``candidate_utilities``.
        candidate_utilities: Each candidate's known utility in ``[0.0, 1.0]``.
            An unknown utility never reaches here — ADR-0011 and
            :class:`smartmatch_domain.optimizer.PortfolioCandidate` both reject
            it rather than coercing it to ``0.0``, so there is no "missing"
            case for this function to invent a representation for.
        portfolio_size: The requested selection size.
        random_seed: The seed handed to CP-SAT.
        weights: The factor weights in force.

    Returns:
        ``"sha256:"`` followed by 64 hex characters.

    Raises:
        ValueError: when the two candidate sequences differ in length, which
            would otherwise silently fingerprint a pool nobody submitted.
    """
    if len(candidate_subject_ids) != len(candidate_utilities):
        raise ValueError(
            "candidate_subject_ids and candidate_utilities must be the same length; "
            f"got {len(candidate_subject_ids)} and {len(candidate_utilities)}"
        )
    pool = sorted(
        [subject, repr(float(utility))]
        for subject, utility in zip(candidate_subject_ids, candidate_utilities, strict=True)
    )
    return _digest(
        {
            "event_need_id": event_need_id,
            "candidates": pool,
            "portfolio_size": portfolio_size,
            "random_seed": random_seed,
            "weights": _rendered_weights(weights),
        }
    )


@dataclass(frozen=True, slots=True)
class MatchRunPins:
    """Every version a stored run is pinned to.

    Frozen, like every other value type here, and validated in
    :meth:`__post_init__` rather than only at the database boundary. The
    database also refuses a blank pin (migration ``0018``'s CHECK constraints),
    and the duplication is deliberate for the reason
    ``smartmatch_persistence.events`` gives for its own: a constraint violation
    surfaces as a driver error naming a constraint, and a caller assembling a
    run should instead be told which field it left empty, at the point it left
    it empty.

    Attributes:
        registry_version: :data:`smartmatch_domain.factor_registry.REGISTRY_VERSION`.
        registry_hash: :func:`weights_fingerprint` over the weights in force.
        optimizer_model_version:
            :data:`smartmatch_domain.optimizer.OPTIMIZER_MODEL_VERSION` — the
            CP-SAT model's own version, which changes when the model changes
            even if the solver build does not.
        solver_name: :data:`smartmatch_domain.optimizer.SOLVER_NAME`.
        solver_version: ``ortools.__version__`` as reported by the
            :class:`~smartmatch_domain.optimizer.PortfolioResult` that was
            actually produced — read off the result rather than off the
            worker's own import, so the recorded build is the one that solved
            and not merely the one that happened to be loaded.
        route_estimate_source: One of :data:`ROUTE_ESTIMATE_SOURCES`.
        route_estimate_version: The formula or provider version behind that
            source —
            :data:`smartmatch_domain.factors.travel_burden.TRAVEL_BURDEN_FORMULA_VERSION`
            for a run pinned to the superseded registry, and
            :data:`smartmatch_domain.factors.proximity.CBA_PROXIMITY_FORMULA_VERSION`
            for a CBA one.
        scoring_mode: ADR-0016 Proposal 9's second pin —
            ``"cba-physical-1"``, ``"cba-virtual-1"``, or ``None`` for a
            pre-ADR-0016 run. **A mode is never a registry version and a
            registry version is never a mode.** ``registry_version`` answers
            "which rulebook"; this answers "which of its models", and
            conflating them would make ``cba-virtual-1`` look like a different
            rulebook and mint a registry version per event shape.

            Optional rather than required, and ``None`` rather than defaulted,
            because a pre-ADR-0016 run genuinely has no mode: reading such a
            run as ``cba-physical-1`` would claim a proximity factor was scored
            under a rulebook that had no modes at all.

            **Not persisted on the ``match_run`` row.** That table (migration
            ``0018``) has no column for it and this card adds no DDL, so the
            durable record of a run's mode is the job summary event and the
            stored explanation payload, plus ``registry_hash`` — which differs
            between the two modes by construction, because they apply different
            weight sets. Giving the mode its own column is OQ-CBA-028, and
            until it lands the mode is recoverable but not queryable.
        scoring_mode_version: The mode vocabulary's version
            (:data:`smartmatch_domain.factor_registry.SCORING_MODE_VERSION`),
            set exactly when :attr:`scoring_mode` is, so a stored
            ``cba-virtual-1`` is never re-read under a later definition of that
            name.
    """

    #: Checked for blankness by :meth:`__post_init__`. A ``ClassVar``, so the
    #: dataclass machinery leaves it out of the generated fields;
    #: ``route_estimate_source`` is absent from it because a blank value fails
    #: the membership check below anyway, and naming one field in two problems
    #: reads as two separate defects.
    _REQUIRED_PINS: ClassVar[tuple[str, ...]] = (
        "registry_version",
        "registry_hash",
        "optimizer_model_version",
        "solver_name",
        "solver_version",
        "route_estimate_version",
    )

    registry_version: str
    registry_hash: str
    optimizer_model_version: str
    solver_name: str
    solver_version: str
    route_estimate_source: str
    route_estimate_version: str
    scoring_mode: str | None = None
    scoring_mode_version: str | None = None

    def __post_init__(self) -> None:
        """Reject a blank pin, and an unrecognised route-estimate source.

        Raises:
            ValueError: naming every offending field at once. Collected rather
                than reported one at a time, for the reason
                ``smartmatch_worker.handlers._read_import_command`` gives about
                its own findings: a caller fixing an assembly defect should see
                the whole list.
        """
        problems = [
            f"{name}: must not be empty or blank"
            for name in self._REQUIRED_PINS
            if not str(getattr(self, name)).strip()
        ]
        if self.route_estimate_source not in ROUTE_ESTIMATE_SOURCES:
            problems.append(
                "route_estimate_source: must be one of "
                f"{sorted(ROUTE_ESTIMATE_SOURCES)}, got {self.route_estimate_source!r}"
            )
        # Either both mode pins or neither. A mode with no version cannot be
        # re-read under the definition it actually used, and a version naming
        # no mode is a version of nothing — both are unrecordable in the same
        # sense a blank registry_version is, so both fail here rather than
        # years later.
        if (self.scoring_mode is None) != (self.scoring_mode_version is None):
            problems.append(
                "scoring_mode and scoring_mode_version: must be set or unset together; "
                f"got {self.scoring_mode!r} and {self.scoring_mode_version!r}"
            )
        for name in ("scoring_mode", "scoring_mode_version"):
            value = getattr(self, name)
            if value is not None and not value.strip():
                problems.append(
                    f"{name}: must be a non-blank string or None; a blank is neither a "
                    "mode nor the honest absence of one"
                )
        if problems:
            raise ValueError("; ".join(problems))
