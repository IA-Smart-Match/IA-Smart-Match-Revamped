"""How a term is compared, and nothing else.

**PLACEHOLDER (OQ-CE-01).** The value vocabularies behind majors, interests,
career goals, and event topics are undecided until Ann's sample file lands, so
this module declares none. A term is compared as an exact string after
``strip()`` and ``casefold()`` — the same rule
:mod:`smartmatch_domain.exercise.simulation` already applied — and no enum,
synonym table, or G3 mapping is introduced anywhere by this comparison.

The rule lives here rather than inside either caller because two copies of
"how a term is compared" is one more than the question has: the simulated
results rule and the four student factors must agree, or a profile could match
an event for the factors and not for the simulation.
"""

from __future__ import annotations

from collections.abc import Iterable

__all__ = [
    "jaccard",
    "normalized_term",
    "normalized_terms",
]


def normalized_term(term: str) -> str:
    """One term as it is compared: trimmed and case-folded, nothing more."""
    return term.strip().casefold()


def normalized_terms(terms: Iterable[str]) -> frozenset[str]:
    """A whole set of terms as they are compared.

    Blank terms are dropped rather than compared as the empty string: a data
    file's trailing separator should not become a term every other term fails
    to match.
    """
    return frozenset(
        normalized for normalized in (normalized_term(term) for term in terms) if normalized
    )


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    """The Jaccard index of two already-normalized term sets.

    Args:
        left: One normalized term set.
        right: The other.

    Returns:
        The size of the intersection over the size of the union, or ``0.0``
        when the union is
        empty. An empty union means neither side recorded a term to compare,
        which is an overlap of nothing rather than a division to perform; the
        decision about whether *that* situation is unknown belongs to the
        factor, which knows whether the record existed at all, and not to this
        arithmetic.
    """
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)
