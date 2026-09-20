"""What a team's four weights are allowed to be, and what a refusal may say.

Split out of ``exercise_matching.py`` in review round 2 (F4), which had grown
past this repository's 800-line ceiling. The cut is along a seam the module
already had: everything here answers "is this weighting admissible, and what do
we say if it is not", and none of it is a route.

The bounds are a security property, not tidiness (review round 2, F2, and round
1's item 2). These routes take no login; the rulebook's validator names every
offending field at once and quotes each rejected key verbatim, so an unbounded
weighting is a request whose *response* grows with it. Every door into the
validator goes through :func:`validated`, which is what keeps the rule from
being true of one route and not another — the body route also carries a bound on
``SaveSettingRequest`` itself, because pydantic runs before any handler and puts
the caller's key in an error ``loc``.

Nothing here reads a table or issues a query. It raises
:class:`~smartmatch_api.exercise_errors.ExerciseError`, which the API's one
envelope renders.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import Query, status
from smartmatch_domain.exercise.registry import (
    EXERCISE_DEFAULT_WEIGHTS,
    InvalidExerciseWeightError,
    validate_exercise_weight_overrides,
)

from smartmatch_api.exercise_errors import ExerciseError
from smartmatch_api.routers.exercise_matching_models import (
    MAX_WEIGHT_KEY_CHARACTERS,
    MAX_WEIGHT_KEYS,
    MAX_WEIGHT_REFUSAL_CHARACTERS,
)

__all__ = [
    "capped",
    "effective_weights",
    "requested_weights",
    "validated",
    "weight_query",
    "within_bounds_or_refusal",
]


def weight_query(label: str) -> Any:
    """One factor's weight, as an optional query parameter.

    Four parameters rather than one JSON blob, because a ranked list is a
    ``GET``: a body on a ``GET`` is not sent by every client and is not
    cacheable, and four named numbers are what a screen's four sliders produce.
    """
    return Query(
        default=None,
        ge=0.0,
        description=(
            f"The weight your team set for “{label}”. Leave every weight out to "
            "use the course's starting values."
        ),
    )


def requested_weights(
    *,
    same_major: float | None,
    stated_interest_overlap: float | None,
    career_goal_fit: float | None,
    past_event_topic_overlap: float | None,
) -> Mapping[str, float] | None:
    """The weights a query string asked for, or ``None`` when it asked for none.

    Keyed by the rulebook's own factor keys, which is what the parameter names
    are — ``tests/unit/test_exercise_matching_router.py`` asserts the four names
    equal ``EXERCISE_APPROVED_SCORING_KEYS`` rather than trusting this list.
    """
    supplied = {
        "same_major": same_major,
        "stated_interest_overlap": stated_interest_overlap,
        "career_goal_fit": career_goal_fit,
        "past_event_topic_overlap": past_event_topic_overlap,
    }
    present = {key: value for key, value in supplied.items() if value is not None}
    return present or None


def within_bounds_or_refusal(raw: Mapping[str, object]) -> None:
    """Refuse a weighting that is too large to describe before describing it.

    **The refusal is the attack surface, not the weighting.** These routes take
    no login. ``validate_exercise_weight_overrides`` names every offending field
    at once and quotes each rejected key verbatim, at roughly 190 bytes per key,
    so an unbounded body of short unknown keys is a request that returns
    megabytes and reflects the caller's own text onto a classroom projector.
    Bounding the input is what stops that at the door; capping the message in
    :func:`validated` is the second line, for a validator that grows more to
    say per key later.

    The two refusals quote **nothing the caller sent** — not a key, not a count
    of the caller's making — because a refusal about a payload being too large
    is the last place to echo the payload.

    Raises:
        ExerciseError: 422, with one plain sentence, for too many keys or a key
            that is too long.
    """
    if len(raw) > MAX_WEIGHT_KEYS:
        raise ExerciseError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="exercise_weights_too_many",
            message=f"Send at most {MAX_WEIGHT_KEYS} weights.",
        )
    if any(len(key) > MAX_WEIGHT_KEY_CHARACTERS for key in raw):
        raise ExerciseError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="exercise_weights_key_too_long",
            message="One of those weights is not named like a factor.",
        )


def validated(raw: Mapping[str, object]) -> Mapping[str, float]:
    """Run a team's proposed weighting through the rulebook's own check.

    ``smartmatch_domain.weight_settings.validate_weight_overrides`` is the
    function design spec §6 names, and it cannot be used here: its admissible
    key set is the CBA four and its zero-total check resolves defaults through
    ``CBA_REGISTRY``, so it would refuse every exercise key and then read CBA
    defaults for the ones it accepted. ``exercise/registry.py`` says so at
    length and supplies :func:`validate_exercise_weight_overrides`, the minimal
    exercise equivalent written to the same rule — refuse, never repair, and
    name every offending field at once. Widening the shared function would be an
    edit to a G1-governed module this track is not authorised to make. Noted as
    a deviation on this track's pull request.

    Bounded twice: :func:`within_bounds_or_refusal` first, so a body too large
    to describe is refused without describing it, and the resulting sentence
    truncated to :data:`MAX_WEIGHT_REFUSAL_CHARACTERS` so the response cannot
    amplify the request whatever the validator decides to say. Both apply to
    weights arriving in a body and to weights arriving on a query string,
    because both arrive here.
    """
    within_bounds_or_refusal(raw)
    try:
        return validate_exercise_weight_overrides(raw)
    except InvalidExerciseWeightError as error:
        raise ExerciseError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="exercise_weights_invalid",
            message=f"Those weights were not accepted. {capped(str(error))}",
        ) from None


def capped(detail: str) -> str:
    """One refusal's detail, cut to a length a response may carry."""
    if len(detail) <= MAX_WEIGHT_REFUSAL_CHARACTERS:
        return detail
    return f"{detail[:MAX_WEIGHT_REFUSAL_CHARACTERS].rstrip()}…"


def effective_weights(overrides: Mapping[str, float] | None) -> Mapping[str, float]:
    """What a screen is told the list was built with.

    The placeholder defaults (OQ-CE-02) with the team's own values written over
    them, so a team that moved one slider sees four numbers rather than one.
    These are the *stated* weights and not the normalized ones: normalizing is
    the composition's business, and a normalized weight is an output (ADR-0025
    D8).
    """
    effective = dict(EXERCISE_DEFAULT_WEIGHTS)
    effective.update(overrides or {})
    return effective
