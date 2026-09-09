"""The closed tag vocabulary G3 approved, as released terms (card S5).

ADR-0012 declines to name the terms — "picking them in an ADR would be exactly
the kind of silent decision this document exists to prevent" — and
`smartmatch_domain.events.TagVocabulary` is the mechanism it defers them into.
`docs/decisions/g3-crawler-decision.md` §6.2 is where a human actually made
the decision: twelve terms, approved 2026-08-29 by Danny Tran, Development
Lead, who is also §6.3's named owner of vocabulary growth. This module is that
decision expressed as code and nothing else.

**Every term below is copied verbatim from §6.2's table.** P6 forbids an
executor inventing one, and §6.3 extends that to editing one: "Terms must
arrive already normalized; an executor editing an approved term would be
inventing one, which P6 forbids." All twelve are already lowercase,
space-separated and unpunctuated, so `TagVocabulary.__post_init__` accepts
them unchanged — if a future edit broke that, construction would raise at
import rather than silently re-folding the term into something the owner did
not approve.

A module and not a data file, per §6.3: `smartmatch_domain`'s import-linter
contract forbids `os` and `pathlib`, so a vocabulary loaded from disk could not
live in this layer at all. The consequence is the intended one — every version
is a reviewed code diff.

One namespace, not two
----------------------
§6.1 considered splitting event-type terms from speaker-role terms and did not
adopt it. The accepted consequence is stated there rather than softened here:
`guest lecture` and `guest lecturer` sit undifferentiated in one namespace, so
`matchable_tags()` returns a list a consumer cannot partition by concept.
:data:`TERM_CONCEPTS` records which is which for a human reader, and is
deliberately *not* consulted by any resolution path — using it to partition
tags would be re-introducing the two-namespace design the owner declined.

Quarantine volume is measurement, not failure
----------------------------------------------
§6.2 cut eight candidate terms on purpose (`datathon`, `symposium`, `industry
night`, `networking mixer`, `info session`, `workshop facilitator`,
`moderator`, `sponsor contact`). Each will quarantine rather than resolve, and
§6.1 says that queue "is evidence of which terms were actually needed; the cap
is revisited after the pilot with real numbers." A later reader finding a high
quarantine rate against this vocabulary is looking at the instrument working,
not at a defect.

Adding a term is a new `TagVocabulary` with a new
:data:`VOCABULARY_VERSION`, approved by the §6.3 owner. It is never a mutation
of :data:`G3_VOCABULARY`, which is frozen, and it never requires DDL — card S5
is migration-free and `event_tag.vocabulary_version` is a text column
precisely so that adding a term stays a code change.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from smartmatch_domain.events import TagVocabulary

__all__ = [
    "G3_VOCABULARY",
    "TERM_CONCEPTS",
    "VOCABULARY_VERSION",
]

#: The released version token stamped onto every `MappedTag` and
#: `QuarantinedTag` this vocabulary produces. Dated by the day the owner signed
#: §6.2 rather than numbered, so a stored tag names the decision it was
#: evaluated against and not merely its ordinal.
VOCABULARY_VERSION: Final[str] = "g3-2026-08-29"

#: Each approved term and the concept §6.2's table files it under. Present for
#: a reader, never for a resolver: §6.1 declined the two-namespace split, and
#: partitioning tags by this mapping would quietly implement the design that
#: was not adopted. `resolve_tag` does not import it.
TERM_CONCEPTS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "hackathon": "type",
        "case competition": "type",
        "guest lecture": "type",
        "career panel": "type",
        "workshop": "type",
        "conference": "type",
        "capstone showcase": "type",
        "keynote": "role",
        "panelist": "role",
        "judge": "role",
        "mentor": "role",
        "guest lecturer": "role",
    }
)

#: The vocabulary itself. Built from :data:`TERM_CONCEPTS`' keys rather than a
#: second literal list, so the two can never disagree about which twelve terms
#: were approved — a duplicated list is a place for a thirteenth term to appear
#: in one copy and not the other.
G3_VOCABULARY: Final[TagVocabulary] = TagVocabulary(
    version=VOCABULARY_VERSION,
    terms=frozenset(TERM_CONCEPTS),
)
