"""Stage B portfolio optimizer — global CP-SAT assignment.

Architecture v1.1 §1.2 Stage B global optimization: choosing *which* subset
of already-scored candidates to present for one ``event_need`` is a
constraint-optimization problem, solved in-process by
`OR-Tools CP-SAT <https://developers.google.com/optimization/cp>`_. It is
never delegated to an LLM — the objective is a deterministic function of
known utilities, and an LLM cannot be made to reproduce a specific optimum on
demand.

**Determinism.** :func:`solve_portfolio` is deterministic for identical
inputs and seed: the same :class:`PortfolioRequest` solved twice, in any
process, returns byte-identical :class:`PortfolioResult` fields. This rests
on three things together: the solver is pinned to a single worker
(``num_workers = 1`` — CP-SAT's parallel portfolio search is not
reproducible), the random seed is set explicitly from
:attr:`PortfolioRequest.random_seed` rather than left to the solver's
default, and the objective itself is constructed with a strict lexicographic
tie-break (see the ``coefficients`` computation in :func:`solve_portfolio`)
so the optimum is mathematically unique — determinism does not rest on which
of several equally-good optima the solver happens to return.

**Reproducible evidence.** Every :class:`PortfolioResult` records
:attr:`~PortfolioResult.solver_name`, :attr:`~PortfolioResult.solver_version`
(read from ``ortools.__version__`` at solve time, never hardcoded), and
:attr:`~PortfolioResult.model_version`. A stored assignment (M8's
``match_run``) that cannot say which solver produced it is not reproducible
evidence, so a result carrying none of these is not a result this module
will construct.

**Unknown utility is not zero (ADR-0011).** :class:`PortfolioCandidate` takes
a known ``utility`` in ``[0.0, 1.0]`` — the caller's already-resolved
:attr:`smartmatch_domain.scoring.StageBScore.value`. A candidate whose Stage
B value is ``None`` must not be constructed as a :class:`PortfolioCandidate`
at all: doing so raises ``ValueError`` rather than silently coercing the
unknown to ``0.0``, which would reintroduce the ADR-0011 defect at the
optimizer layer. Deciding what to *do* with an unknown-utility candidate
(omit it from the pool, surface it separately, ask a coordinator) is a
caller decision this module does not make.

**Portfolio size is a parameter.** :attr:`PortfolioRequest.portfolio_size`
has no default and is required on every call. Returning 2-3 speakers is a
*presentation* rule owned by card M10, not this module — the literals ``2``
and ``3`` must never appear here as a portfolio-size default or fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

import ortools
from ortools.sat.python import cp_model

__all__ = [
    "OPTIMIZER_MODEL_VERSION",
    "SOLVER_NAME",
    "SOLVE_TIME_LIMIT_SECONDS",
    "UTILITY_SCALE",
    "PortfolioCandidate",
    "PortfolioRequest",
    "PortfolioResult",
    "PortfolioStatus",
    "solve_portfolio",
]

#: Versioned independently of the OR-Tools release: any change to *this*
#: module's model — the objective, the tie-break, the constraint shape —
#: is a new model version, because a stored ``match_run`` (M8) records which
#: model version produced it.
OPTIMIZER_MODEL_VERSION: Final[str] = "1.0.0-cpsat"

#: Recorded on every result alongside :data:`OPTIMIZER_MODEL_VERSION` so a
#: stored assignment names both which model and which solver produced it.
SOLVER_NAME: Final[str] = "ortools-cpsat"

#: Utilities are floats in [0, 1]; CP-SAT is an integer solver, so utilities are
#: scaled to integers. 1e6 keeps six decimal places, which is the precision
#: StageBScore.value is rounded to.
UTILITY_SCALE: Final[int] = 1_000_000

#: Wall-clock ceiling. A deterministic model this small never approaches it; the
#: bound exists so a pathological input cannot hang a worker.
SOLVE_TIME_LIMIT_SECONDS: Final[float] = 10.0


class PortfolioStatus(StrEnum):
    """Outcome of one :func:`solve_portfolio` call."""

    #: The solver proved the returned selection maximizes the objective.
    OPTIMAL = "optimal"
    #: The solver found a feasible selection but could not prove optimality
    #: before :data:`SOLVE_TIME_LIMIT_SECONDS`.
    FEASIBLE = "feasible"
    #: No selection satisfies the constraints. ``selected_subject_ids`` is
    #: empty.
    INFEASIBLE = "infeasible"


@dataclass(frozen=True, slots=True)
class PortfolioCandidate:
    """One candidate eligible for portfolio selection.

    Attributes:
        subject_id: Stable identifier for the professional. Non-empty.
        utility: A known score in ``[0.0, 1.0]`` — typically
            :attr:`smartmatch_domain.scoring.StageBScore.value`. Must not be
            ``None`` or ``NaN``: an unknown utility is rejected here, never
            coerced to ``0.0`` (ADR-0011). The caller decides how an
            unknown-utility candidate is presented before it ever reaches
            this type.
    """

    subject_id: str
    utility: float

    def __post_init__(self) -> None:
        if not self.subject_id.strip():
            raise ValueError("subject_id: must not be empty or blank")
        # `self.utility is None` first: comparing None to a float raises
        # TypeError rather than returning False, and a candidate constructed
        # at runtime from an un-narrowed `StageBScore.value` can carry None
        # despite the `float` annotation. `or` short-circuits, so the range
        # comparison below never runs against None. NaN needs no separate
        # check: every comparison against NaN is False, so
        # `0.0 <= NaN <= 1.0` is False and `not (...)` is True.
        if self.utility is None or not (0.0 <= self.utility <= 1.0):
            raise ValueError(
                f"utility: must be a known value in [0.0, 1.0], got {self.utility!r} "
                f"for subject_id={self.subject_id!r} (ADR-0011: unknown is not zero, "
                "and is rejected rather than coerced)"
            )


@dataclass(frozen=True, slots=True)
class PortfolioRequest:
    """One portfolio-selection request for a single ``event_need``.

    Attributes:
        event_need_id: Stable identifier for the event need. Non-empty.
        candidates: The eligible candidate pool. Every ``subject_id`` must be
            unique; order does not affect the result (see
            :func:`solve_portfolio`).
        portfolio_size: How many candidates to select. Required — has no
            default. Presentation rules (such as "2-3 speakers") belong to
            card M10, not the caller of this type.
        random_seed: Seed passed verbatim to the CP-SAT solver. Defaults to
            ``0`` for callers that have no reason to vary it; the same seed
            with the same ``candidates`` and ``portfolio_size`` always
            produces the same :class:`PortfolioResult`.
    """

    event_need_id: str
    candidates: tuple[PortfolioCandidate, ...]
    portfolio_size: int
    random_seed: int = 0

    def __post_init__(self) -> None:
        if not self.event_need_id.strip():
            raise ValueError("event_need_id: must not be empty or blank")
        if self.portfolio_size < 1:
            raise ValueError(f"portfolio_size: must be >= 1, got {self.portfolio_size!r}")
        subject_ids = [candidate.subject_id for candidate in self.candidates]
        if len(set(subject_ids)) != len(subject_ids):
            raise ValueError("candidates: duplicate subject_id in PortfolioRequest.candidates")


@dataclass(frozen=True, slots=True)
class PortfolioResult:
    """The outcome of one :func:`solve_portfolio` call.

    Attributes:
        event_need_id: Echoed from the request.
        selected_subject_ids: The selected candidates' ``subject_id`` values,
            sorted lexicographically ascending. Empty when
            :attr:`status` is :attr:`PortfolioStatus.INFEASIBLE` or the
            request's candidate pool was empty.
        objective_value: The CP-SAT objective value achieved. ``0`` when no
            candidates were selected.
        status: The solver outcome.
        solver_name: :data:`SOLVER_NAME`.
        solver_version: ``ortools.__version__`` at solve time, so a stored
            result names exactly which solver build produced it.
        model_version: :data:`OPTIMIZER_MODEL_VERSION`.
        random_seed: Echoed from the request.
        portfolio_size: Echoed from the request — the *requested* size, which
            may exceed the number of candidates actually selected when the
            candidate pool is smaller than the request.
    """

    event_need_id: str
    selected_subject_ids: tuple[str, ...]
    objective_value: int
    status: PortfolioStatus
    solver_name: str
    solver_version: str
    model_version: str
    random_seed: int
    portfolio_size: int


def _empty_result(request: PortfolioRequest) -> PortfolioResult:
    """Build the trivial result for a request with no candidates."""
    return PortfolioResult(
        event_need_id=request.event_need_id,
        selected_subject_ids=(),
        objective_value=0,
        status=PortfolioStatus.OPTIMAL,
        solver_name=SOLVER_NAME,
        solver_version=ortools.__version__,
        model_version=OPTIMIZER_MODEL_VERSION,
        random_seed=request.random_seed,
        portfolio_size=request.portfolio_size,
    )


def solve_portfolio(request: PortfolioRequest) -> PortfolioResult:
    """Select the highest-utility portfolio for one event need.

    Solves a single-knapsack-style CP-SAT model: choose exactly
    ``min(request.portfolio_size, len(request.candidates))`` candidates that
    maximize total utility, with ties broken lexicographically ascending by
    ``subject_id`` (the ratified tie-break) so the optimum is unique.

    Args:
        request: The candidates, requested portfolio size, and random seed.

    Returns:
        A :class:`PortfolioResult`. With an empty candidate pool this
        returns immediately: ``status=PortfolioStatus.OPTIMAL``,
        ``selected_subject_ids=()``, ``objective_value=0`` — an empty
        portfolio is not an error, it is the correct answer to "select from
        nothing".
    """
    ordered = sorted(request.candidates, key=lambda c: (-c.utility, c.subject_id))
    candidate_count = len(ordered)
    if candidate_count == 0:
        return _empty_result(request)

    target = min(request.portfolio_size, candidate_count)

    model = cp_model.CpModel()
    selectors = [model.NewBoolVar(f"select_{i}") for i in range(candidate_count)]
    model.Add(sum(selectors) == target)

    # Strict lexicographic tie-break: `(n - i)` lies in `[1, n]`, always
    # strictly less than the `(n + 1)` utility multiplier, so it can never
    # outweigh a utility difference of one scale unit. It ranks equal-utility
    # candidates by ascending subject_id (their position `i` in `ordered`,
    # which is already sorted that way), matching the ratified tie-break and
    # making the optimum unique — without it CP-SAT may return either of two
    # equally good portfolios, and "deterministic given identical inputs and
    # seed" would rest on solver internals instead of the model.
    coefficients = [
        round(ordered[i].utility * UTILITY_SCALE) * (candidate_count + 1) + (candidate_count - i)
        for i in range(candidate_count)
    ]
    model.Maximize(sum(coefficients[i] * selectors[i] for i in range(candidate_count)))

    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    solver.parameters.random_seed = request.random_seed
    solver.parameters.max_time_in_seconds = SOLVE_TIME_LIMIT_SECONDS

    solve_status = solver.Solve(model)

    if solve_status == cp_model.OPTIMAL:
        status = PortfolioStatus.OPTIMAL
    elif solve_status == cp_model.FEASIBLE:
        status = PortfolioStatus.FEASIBLE
    else:
        status = PortfolioStatus.INFEASIBLE

    if status is PortfolioStatus.INFEASIBLE:
        selected_subject_ids: tuple[str, ...] = ()
        objective_value = 0
    else:
        selected_subject_ids = tuple(
            sorted(
                ordered[i].subject_id for i in range(candidate_count) if solver.Value(selectors[i])
            )
        )
        objective_value = int(solver.ObjectiveValue())

    return PortfolioResult(
        event_need_id=request.event_need_id,
        selected_subject_ids=selected_subject_ids,
        objective_value=objective_value,
        status=status,
        solver_name=SOLVER_NAME,
        solver_version=ortools.__version__,
        model_version=OPTIMIZER_MODEL_VERSION,
        random_seed=request.random_seed,
        portfolio_size=request.portfolio_size,
    )
