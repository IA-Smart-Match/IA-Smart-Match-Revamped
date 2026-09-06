"""Role Match scoring factor.

Customer §8 gives each speaker one primary CBA role category and lets a
Speaker Request target several ("Do not restrict an event request to one
role"). The shape is therefore identical to
:mod:`smartmatch_domain.factors.industry_match`: one value tested for
membership in a set, with no ratio to take on the speaker side.

A career discipline, never an event function
============================================

The single thing most worth guarding here. ADR-0012's closed tag vocabulary
(:mod:`smartmatch_domain.event_vocabulary`) holds `panelist`, `judge`,
`keynote`, `mentor` — the function a person performs *at an event*. A CBA role
category is the discipline a speaker *works in*: `Finance`, `Human Resources`.
The two use the word "role" for unrelated things, and reusing an event tag as
a role category would score a keynote speaker against an accounting request.

The separation is structural rather than disciplinary: this module accepts
only :class:`~smartmatch_domain.cba_role_categories.RoleCategoryResolution`
values, which an event tag cannot become, and it imports nothing from the
event vocabulary. `tests/unit/test_role_match.py` asserts that the four event
functions above resolve to quarantine and therefore score unknown.

Weights live elsewhere
======================

No weight literal appears in this module. Customer §5's Role weight belongs to
:mod:`smartmatch_domain.factor_registry`, another track's file. ``1.0`` and
``0.0`` below are the endpoints of the ``FactorScore`` scale, not weights, and
ADR-0016's rule that weights are never re-spread per candidate is unreachable
from here by construction.

Evidence states
===============

ADR-0016 names ``measured``, ``policy_neutral`` and ``unknown``. Only two
arise here: §9's neutral policy covers a speaker with no *topic* evidence, and
§8 states no policy for a speaker with no role classification, so this factor
never invents one.

The boundary, stated once: **a classification that was read and does not match
is a measured zero; a classification that could not be evaluated is unknown.**

* Speaker's role resolved and is one of the requested roles — measured ``1.0``.
* Speaker's role resolved and is not one of them — measured ``0.0``. The
  comparison ran and the answer was no; that is a real claim, and it must stay
  distinguishable from an unknown.
* No role on file (``None``) — unknown; nothing was read.
* Speaker's role quarantined — unknown. `HR` is not established to be outside
  every requested role; it is established to be unclassified, and a later
  taxonomy version may resolve it to `Human Resources`.
* Request names no roles at all — unknown; nothing to measure against.
* Request names roles but none resolved — unknown; a speaker cannot miss a
  target set that was never established.

Deferred: alias and fuzzy matching
==================================

`HR` does not become `Human Resources` and `Sales` does not become `Sales &
Business Development` here. :mod:`smartmatch_domain.cba_role_categories` owns
that decision and defers it to a later versioned rule learned from pilot data;
this module adds no matching of its own, so the rule has one place to land.

Deferred: a speaker with more than one role
===========================================

§8 says a speaker "should **normally** have one primary role category". This
factor takes §8's normal case literally and accepts exactly one, enforced by
the type — :attr:`RoleMatchInputs.speaker_role` is a single value, not a
tuple. What the exception should score is undecided and is **not** guessed
here: whether a dual-discipline speaker takes the best of their roles, an
average, or is refused is a customer decision with ranking consequences.
Recorded as **OQ-CBA-022**.

Not wired into the registry
===========================

Registration of ``role_match`` in :mod:`smartmatch_domain.factor_registry` is
a separate track's work. :data:`ROLE_MATCH_FACTOR_KEY` is exported so that
track references one string rather than retyping it.

Sources
=======

* ``docs/product/cba-smart-match-customer-requirements.md`` §§5, 8
* ``docs/architecture/decisions/ADR-0016-cba-scoring-policy.md`` (Proposal 1)
* ADR-0011 (measured zero versus unknown); ADR-0012 (event tag vocabulary)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from smartmatch_domain.cba_role_categories import (
    CBA_ROLE_CATEGORIES,
    CBA_ROLE_TAXONOMY_VERSION,
    ClassifiedRoleCategory,
    QuarantinedRoleCategory,
    RoleCategoryResolution,
)
from smartmatch_domain.factors import FACTOR_SCORE_PRECISION, FactorScore

__all__ = [
    "ROLE_MATCH_FACTOR_KEY",
    "ROLE_MATCH_FORMULA_VERSION",
    "RoleMatchInputs",
    "score_role_match",
]

#: The registry key this factor's scores carry. Exported so the registry track
#: references one string instead of retyping it, and so a rename is one edit.
ROLE_MATCH_FACTOR_KEY: Final[str] = "role_match"

#: Versioned independently of the registry and of the taxonomy: any change to
#: the comparison rules above is a new formula version, even when neither the
#: weights nor the category list moved.
ROLE_MATCH_FORMULA_VERSION: Final[str] = "1.0.0"

_KNOWN_CATEGORIES: Final[frozenset[tuple[str, str]]] = frozenset(
    (category.code, category.name) for category in CBA_ROLE_CATEGORIES
)


@dataclass(frozen=True, slots=True)
class RoleMatchInputs:
    """Everything :func:`score_role_match` is permitted to see.

    Both sides arrive already resolved against
    :mod:`smartmatch_domain.cba_role_categories`, so a raw title string never
    reaches the comparison and no second resolution rule can drift from the
    first.

    Attributes:
        speaker_role: The speaker's one primary role category, or ``None``
            when no role value is on file. ``None`` and a
            :class:`~smartmatch_domain.cba_role_categories.QuarantinedRoleCategory`
            are both unknown but for different reasons, and the ``basis``
            string distinguishes them for the Speaker Connector who has to
            act. Cardinality is enforced by the type; the multi-role case §8
            leaves open is OQ-CBA-022 and is not guessed at here.
        requested_roles: The role categories the Speaker Request targets, in
            the order the request named them. May hold several (§8: "Do not
            restrict an event request to one role"), may be empty, and may mix
            classified and quarantined entries. Duplicates are permitted and
            cannot change the score — the comparison is over a set.
    """

    speaker_role: RoleCategoryResolution | None
    requested_roles: tuple[RoleCategoryResolution, ...]

    def __post_init__(self) -> None:
        if self.speaker_role is not None:
            _validate("speaker_role", self.speaker_role)
        for resolution in self.requested_roles:
            _validate("requested_roles", resolution)


def _validate(label: str, resolution: RoleCategoryResolution) -> None:
    """Refuse a resolution this factor cannot honestly compare.

    Both refusals are :class:`ValueError` because both are caller bugs rather
    than missing evidence, and both raise rather than return an unknown — a
    construction error filed as "we could not tell" is the same information
    loss ADR-0011 forbids in the other direction.
    """
    if resolution.taxonomy_version != CBA_ROLE_TAXONOMY_VERSION:
        raise ValueError(
            f"{label}: was resolved against taxonomy version "
            f"{resolution.taxonomy_version!r}, but this factor scores against "
            f"{CBA_ROLE_TAXONOMY_VERSION!r}; a classification from another "
            "version must be resolved again before it is scored, never "
            "compared across versions"
        )
    if (
        isinstance(resolution, ClassifiedRoleCategory)
        and (
            resolution.category.code,
            resolution.category.name,
        )
        not in _KNOWN_CATEGORIES
    ):
        raise ValueError(
            f"{label}: {resolution.category!r} is not a row of the CBA role "
            f"taxonomy customer §8 supplies ({CBA_ROLE_TAXONOMY_VERSION}); a "
            "classified category the released list does not contain was "
            "assembled by hand and is not scorable"
        )


def _requested_codes(inputs: RoleMatchInputs) -> frozenset[str]:
    """The codes of the requested role categories that actually resolved.

    Quarantined request entries are dropped from the comparison rather than
    counted against the speaker: an unresolvable target is not a target the
    speaker failed to hit. They stay on the request for a Speaker Connector to
    reclassify, and the "none of them resolved" case gets its own unknown
    branch below rather than becoming a silent empty set.
    """
    return frozenset(
        r.category.code for r in inputs.requested_roles if isinstance(r, ClassifiedRoleCategory)
    )


def score_role_match(inputs: RoleMatchInputs) -> FactorScore:
    """Score a speaker's primary role category against a request's targets.

    Args:
        inputs: The speaker's resolved primary role category and the request's
            resolved target categories.

    Returns:
        A :class:`~smartmatch_domain.factors.FactorScore` keyed
        :data:`ROLE_MATCH_FACTOR_KEY`. ``value`` is ``1.0`` when the speaker's
        role is among the requested ones, a measured ``0.0`` when it was read
        and is not, and ``None`` when either side could not be evaluated.
        Every ``basis`` names
        :data:`~smartmatch_domain.cba_role_categories.CBA_ROLE_TAXONOMY_VERSION`,
        so a stored score states which list produced it.

    Raises:
        ValueError: if either side carries a classification from another
            taxonomy version, or a category the released list does not
            contain. (Raised from :class:`RoleMatchInputs` construction.)
    """
    speaker = inputs.speaker_role

    if speaker is None:
        return FactorScore(
            ROLE_MATCH_FACTOR_KEY,
            None,
            basis=(
                f"no role classification on file for this speaker ({CBA_ROLE_TAXONOMY_VERSION})"
            ),
        )

    if isinstance(speaker, QuarantinedRoleCategory):
        return FactorScore(
            ROLE_MATCH_FACTOR_KEY,
            None,
            basis=(
                f"speaker role value {speaker.raw_value!r} is not classified "
                f"under {CBA_ROLE_TAXONOMY_VERSION} and awaits review; not evaluable"
            ),
        )

    if not inputs.requested_roles:
        return FactorScore(
            ROLE_MATCH_FACTOR_KEY,
            None,
            basis=f"speaker request names no role categories ({CBA_ROLE_TAXONOMY_VERSION})",
        )

    requested = _requested_codes(inputs)
    if not requested:
        return FactorScore(
            ROLE_MATCH_FACTOR_KEY,
            None,
            basis=(
                f"none of the {len(inputs.requested_roles)} role categories the "
                f"request names is classified under {CBA_ROLE_TAXONOMY_VERSION}; "
                "not evaluable"
            ),
        )

    matched = speaker.category.code in requested
    speaker_label = f"{speaker.category.code} ({speaker.category.name})"
    relation = "is one of" if matched else "is not among"
    return FactorScore(
        ROLE_MATCH_FACTOR_KEY,
        round(1.0 if matched else 0.0, FACTOR_SCORE_PRECISION),
        basis=(
            f"speaker role {speaker_label} {relation} the {len(requested)} "
            f"requested role categor(ies) ({CBA_ROLE_TAXONOMY_VERSION})"
        ),
    )
