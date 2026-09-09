"""Unit-scoped matching-weight **overrides**, and what makes one admissible.

Customer §5 ("Configuration requirement") asks for two things at once, and they
pull in opposite directions if either is taken alone:

    Do **not** scatter or duplicate hard-coded weight values throughout the
    matching implementation. Store the weights in one configurable location so
    a **Speaker Connector** can adjust them later.

"One location" is :mod:`smartmatch_domain.factor_registry` — it already holds
the approved Industry / Role / Topic / Proximity weights and is the only place
those numbers are written down. "Configurable" is this module. The temptation is
to make the settings row the new source of truth, seeded with a copy of the
registry defaults; that is exactly the duplication §5 forbids, because the seed
is a second copy of four numbers that can drift from the registry the moment
either changes, and nothing would say which copy scored a run.

So a setting here is an **override layer and nothing else**:

* A factor with no override has no stored value anywhere. Its weight is read
  from the registry at scoring time, through
  :func:`~smartmatch_domain.factor_registry.normalize_weights`, which already
  takes exactly this shape of partial override map.
* Clearing an override does not write a default back; it deletes the entry, and
  the registry answers again.
* There is therefore no migration default, no dataclass default, and no fixture
  in this feature that states a registry weight as a literal. If ADR-0016
  revises a weight, every unit that never overrode it moves with the ADR —
  which is the behaviour "one configurable location" is asking for.

## Validation refuses; it never repairs

``normalize_weights`` divides by the total, so a caller could hand it almost
anything and get a plausible-looking normalized map back. That is the failure
mode this module exists to prevent. A Connector who types a negative weight, a
weight for a factor that does not exist, or a set that sums to nothing has made
a mistake, and quietly normalizing it into something that scores would hide the
mistake behind four numbers that add to 1.0. Every rejection below names the
field and says what is wrong with it.

Three refusals in particular are worth stating as rules rather than as code:

1. **An unknown factor key is refused, not ignored.** ``normalize_weights``
   ignores keys outside the model on purpose — a stored ``1.x`` run's map must
   be readable under a ``2.x`` model without exploding. A person typing into a
   settings form is the opposite case: ``industry`` instead of
   ``industry_match`` would be accepted, ignored, and would silently do
   nothing, and the Connector would conclude the feature is broken. So the
   settings boundary is strict where the scoring boundary is tolerant.
2. **A zero total is refused for every current model, not just the default
   one.** Setting Proximity high and the other three to zero is a coherent
   *physical* weighting and a completely broken *virtual* one:
   :data:`~smartmatch_domain.factor_registry.CBA_VIRTUAL_MODEL` drops Proximity
   (customer §11), so what is left sums to zero and ``normalize_weights``
   returns all-zero weights — every candidate scores 0.0 and the shortlist is
   the solver's arbitrary tie-break. The check therefore ranges over every
   current model, so a setting cannot be admissible for the event shape the
   Connector had in mind and broken for the other one.
3. **A weight has no upper bound.** Normalization makes the scale irrelevant —
   ``{a: 2, b: 1}`` and ``{a: 200, b: 100}`` are the same weighting — so a
   ceiling would be an invented number refusing a set that is not wrong. Only
   values that cannot be normalized at all are refused: negatives, NaN, and the
   infinities.

## What is *not* here

No storage, no session, no identifiers: this module is the pure half, the way
:mod:`smartmatch_domain.match_run` is the pure half of the run snapshot.
:mod:`smartmatch_persistence.match_weight_settings` writes the row and
``smartmatch_api.routers.matching_weights`` exposes it.

No history semantics either. Who changed a setting and when is recorded by the
persistence layer's revision table; what makes a *proposed* setting acceptable
is decided here, and the two are separable — a rejected change is never
recorded as a revision, because it never happened.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final

from smartmatch_domain.factor_registry import (
    APPROVED_SCORING_KEYS,
    SCORING_MODELS,
    ScoringModel,
    normalize_weights,
)

__all__ = [
    "CONFIGURABLE_FACTOR_KEYS",
    "InvalidWeightOverrideError",
    "MatchWeightSettings",
    "applied_weights",
    "configurable_factor_keys",
    "validate_weight_overrides",
]

#: The factor keys a Connector may set a weight for: exactly the registry's
#: approved scoring set, derived from it rather than restated. A key admitted
#: here that the registry does not score would be a setting with no effect, and
#: a key the registry scores but this set omits would be a factor nobody can
#: configure — both are the drift §5's "one configurable location" is about.
#:
#: Note this is the *union* over models, not one model's keys. Proximity stays
#: configurable even though a virtual run does not score it: the setting is
#: unit-scoped and long-lived, and one unit runs both event shapes.
CONFIGURABLE_FACTOR_KEYS: Final[frozenset[str]] = APPROVED_SCORING_KEYS


def configurable_factor_keys() -> tuple[str, ...]:
    """The configurable keys in a stable, sorted order, for wire rendering.

    Sorted rather than registry-declaration-ordered because this is what an API
    response and an error message enumerate, and a caller comparing two
    responses should not see the order change when the registry's declaration
    order does.
    """
    return tuple(sorted(CONFIGURABLE_FACTOR_KEYS))


class InvalidWeightOverrideError(ValueError):
    """A proposed override set that must be refused rather than normalized.

    A ``ValueError`` subclass so a caller that does not care about the
    distinction still catches it with the exception the domain raises
    everywhere else, and a named type so the API layer can turn it into a
    422 that names the offending field rather than into a 500.
    """


def _coerce_weight(key: str, value: object) -> float:
    """One override value as a float.

    Raises:
        TypeError: describing the single problem, for the caller to collect.
            A ``TypeError`` rather than the module's own error type because
            this is the per-field step: the caller decides that one or more
            field problems make the whole proposal inadmissible, and raising
            the public type here would let a partial failure escape as if it
            were the verdict on the set.
    """
    if isinstance(value, bool):
        # `bool` is an `int` in Python, so `True` would otherwise become 1.0. A
        # boolean is not a weight, and reading one as 1.0 would give a factor a
        # weight nobody typed.
        raise TypeError(f"{key}: must be a number, got a boolean")
    if not isinstance(value, (int, float)):
        raise TypeError(f"{key}: must be a number, got {type(value).__name__}")
    weight = float(value)
    if math.isnan(weight) or math.isinf(weight):
        raise TypeError(f"{key}: must be a finite number, got {weight}")
    if weight < 0.0:
        raise TypeError(f"{key}: must not be negative, got {weight}")
    return weight


def _effective_weights(
    overrides: Mapping[str, float],
    *,
    model: ScoringModel,
) -> Mapping[str, float]:
    """The weight each of ``model``'s factors would carry, before normalizing.

    The registry default is used for every factor the overrides do not name,
    read from :func:`~smartmatch_domain.factor_registry.normalize_weights`
    rather than copied — which is why this reaches for that function instead of
    walking ``PROPOSED_FACTORS`` and re-deriving the defaults here. The
    defaults it returns are already normalized, and that is fine: the zero-total
    check below only asks whether anything is left, and scaling every default by
    the same constant cannot change that answer.
    """
    defaults = normalize_weights(model=model)
    return {key: overrides.get(key, default) for key, default in defaults.items()}


def validate_weight_overrides(
    raw: Mapping[str, object],
    *,
    models: Mapping[str, ScoringModel] = SCORING_MODELS,
) -> Mapping[str, float]:
    """Return ``raw`` as an admissible override map, or refuse it.

    Args:
        raw: What the caller proposed, keyed by factor key. An **empty mapping
            is valid** and means "no overrides" — the reset, after which every
            factor reads its registry default again. That is deliberately not
            the same thing as a map setting every factor to ``0.0``, which is
            refused: the first says "use the approved weights", the second says
            "score nothing", and conflating them would let a reset be typed as
            a catastrophe or the other way round.
        models: The scoring models the result must be usable under. Defaults to
            every current model, which is what makes rule 2 in the module
            docstring hold; a caller narrows it only to reason about one model
            in a test.

    Returns:
        An immutable ``{factor_key: float}`` map containing exactly the keys the
        caller supplied. Absent keys are absent, not defaulted.

    Raises:
        InvalidWeightOverrideError: naming **every** offending field at once, in
            the collected style :class:`smartmatch_domain.match_run.MatchRunPins`
            uses — someone fixing a settings form should see the whole list
            rather than discovering the next problem on the next submission.
    """
    problems: list[str] = []
    weights: dict[str, float] = {}

    for key in sorted(raw):
        if key not in CONFIGURABLE_FACTOR_KEYS:
            problems.append(
                f"{key}: is not a configurable factor; expected one of "
                f"{list(configurable_factor_keys())}"
            )
            continue
        try:
            weights[key] = _coerce_weight(key, raw[key])
        except TypeError as exc:
            problems.append(str(exc))

    if not problems and weights:
        for mode, model in sorted(models.items()):
            # The registry supplies every weight this map does not, so the total
            # is the *effective* total and not the total of the overrides alone.
            # A map that overrides one factor to 0.0 is fine; a map that zeroes
            # out everything a model scores is not.
            total = sum(_effective_weights(weights, model=model).values())
            if total <= 0.0:
                problems.append(
                    f"the resulting weights sum to zero for scoring mode {mode!r} "
                    f"(factors {list(model.scoring_keys)}); every candidate would "
                    "score 0.0 and the shortlist would be an arbitrary tie-break. "
                    "Refused rather than normalized into something plausible."
                )

    if problems:
        raise InvalidWeightOverrideError("; ".join(problems))

    return MappingProxyType(dict(weights))


def applied_weights(
    overrides: Mapping[str, float] | None,
    *,
    model: ScoringModel,
) -> Mapping[str, float]:
    """The normalized weights a run under ``model`` actually scores with.

    One line, and deliberately so: the arithmetic is
    :func:`~smartmatch_domain.factor_registry.normalize_weights`'s and is not
    re-implemented here. What this adds is a *name* for the composition —
    "registry defaults, with this unit's overrides applied" — so a call site
    reads as that rather than as a bare ``normalize_weights(some_mapping)``
    whose second argument's provenance is not obvious at the point of use.

    Args:
        overrides: A validated override map, or ``None`` for a unit that has
            never configured anything. ``None`` and ``{}`` give the same answer,
            which is the registry's own weights; both are allowed because a unit
            with no row and a unit whose row is empty really are the same state
            *for scoring*, and forcing the caller to collapse one into the other
            would put that decision at every call site.
        model: The scoring model in force for the run.

    Returns:
        An immutable mapping over ``model``'s factors, summing to 1.0.
    """
    return normalize_weights(overrides or None, model=model)


@dataclass(frozen=True, slots=True)
class MatchWeightSettings:
    """One unit's stored override set, with the audit facts that came with it.

    Frozen, like every value type in this package. The audit fields are part of
    the value rather than a separate record because the question a Connector
    asks of a settings screen is "what is in force, and who put it there" — one
    question with one answer, and splitting it would let a screen render the
    weights without the accountability.

    Attributes:
        overrides: The stored overrides only. Empty for a unit that has reset
            its settings; the map is absent entirely for a unit that never had
            one, which the repository reports as ``None`` rather than as an
            empty :class:`MatchWeightSettings` — "never configured" and
            "configured back to the defaults" are different histories, and only
            the second has an author and a timestamp to report.
        version: Monotonic, starting at 1 and incremented on every accepted
            change. It is what a client echoes back to say which version it
            meant to modify, so two Connectors editing one unit's weights do not
            silently overwrite each other.
        updated_by_user_id: The account that made the change, as a string — the
            domain does not import identifier semantics it does not need.
        updated_at: When that change was accepted, in UTC.
    """

    overrides: Mapping[str, float]
    version: int
    updated_by_user_id: str
    updated_at: datetime

    def __post_init__(self) -> None:
        """Reject a settings value that could not have come from a real change.

        Raises:
            ValueError: naming every offending field at once.
        """
        problems: list[str] = []
        if self.version < 1:
            problems.append(f"version: must be 1 or greater, got {self.version}")
        if not str(self.updated_by_user_id).strip():
            problems.append(
                "updated_by_user_id: must name the account that made the change; "
                "a settings change with no author is not auditable"
            )
        unknown = sorted(set(self.overrides) - CONFIGURABLE_FACTOR_KEYS)
        if unknown:
            problems.append(f"overrides: contains non-configurable factors {unknown}")
        if problems:
            raise ValueError("; ".join(problems))

    def weights_for(self, model: ScoringModel) -> Mapping[str, float]:
        """The normalized weights a run under ``model`` would score with."""
        return applied_weights(self.overrides, model=model)
