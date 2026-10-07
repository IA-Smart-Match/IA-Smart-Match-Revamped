"""How a term is compared, and nothing else.

This module declares no vocabulary. A term is compared as an exact string
after ``strip()`` and ``casefold()`` — the same rule
:mod:`smartmatch_domain.exercise.simulation` applies — and no enum, synonym
table, or G3 mapping is introduced anywhere by this comparison. The class
exercise's closed lists live in :mod:`smartmatch_domain.exercise.vocabulary`
and are enforced at ingest, before a term reaches this comparison.

The rule lives here rather than inside either caller because two copies of
"how a term is compared" is one more than the question has: the simulated
results rule and the four student factors must agree, or a profile could match
an event for the factors and not for the simulation.
"""

from __future__ import annotations

from collections.abc import Iterable

__all__ = [
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
