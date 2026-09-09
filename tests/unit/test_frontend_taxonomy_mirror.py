"""The frontend's copy of the two CBA vocabularies is a mirror, not a second opinion.

``apps/web/legacy-frontend/src/lib/cbaTaxonomies.ts`` transcribes customer §7's
twenty NAICS sector groups and §8's ten CBA career role categories so a Speaker
Request form can render them before any request is made.
``docs/product/cba-taxonomies.md`` says the domain modules are the only copy — so
the transcription is admissible only on migration ``0024``'s terms, which it
states plainly: a second copy is acceptable exactly when the divergence it risks
is "caught behaviourally rather than left to discipline". This file is that
catch.

Parsed rather than imported, for the reason ``tests/unit/test_cba_scope_policy.py``
gives about the capability mirror: the TypeScript literal is the artifact that
ships, and a test that imported some other representation of it would assert the
wrong thing. Order is compared as well as content — a form renders in list order,
and the customer's own ordering is part of what was approved.
"""

from __future__ import annotations

import re
from pathlib import Path

from smartmatch_domain.cba_role_categories import CBA_ROLE_CATEGORIES, CBA_ROLE_TAXONOMY_VERSION
from smartmatch_domain.naics_sectors import NAICS_SECTORS, NAICS_TAXONOMY_VERSION

REPO_ROOT = Path(__file__).resolve().parents[2]
MIRROR_PATH = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src" / "lib" / "cbaTaxonomies.ts"

#: One `{ code: "...", name: "..." }` entry, however the formatter wrapped it.
#: Whitespace-tolerant on purpose: prettier splits the long `Administrative and
#: Support...` entry across three lines, and a pattern that assumed one line per
#: entry would silently find nineteen sectors and fail for a confusing reason.
_ENTRY = re.compile(r'\{\s*code:\s*"([^"]+)",\s*name:\s*"([^"]+)",?\s*\}')


def _block(name: str) -> str:
    """The array literal assigned to ``name``, or fail naming what was missing."""
    source = MIRROR_PATH.read_text(encoding="utf-8")
    match = re.search(
        rf"export const {name}: readonly TaxonomyOption\[\] = \[(.*?)\n\] as const;",
        source,
        re.DOTALL,
    )
    assert match is not None, f"{MIRROR_PATH} declares no {name} array in the expected shape"
    return match.group(1)


def _entries(name: str) -> list[tuple[str, str]]:
    return [(code, label) for code, label in _ENTRY.findall(_block(name))]


def _version(name: str) -> str:
    source = MIRROR_PATH.read_text(encoding="utf-8")
    match = re.search(rf'export const {name} = "([^"]+)";', source)
    assert match is not None, f"{MIRROR_PATH} declares no {name}"
    return match.group(1)


def test_the_mirror_exists() -> None:
    assert MIRROR_PATH.is_file(), f"expected {MIRROR_PATH} to exist"


def test_the_industry_mirror_matches_the_released_taxonomy_exactly() -> None:
    """Code for code, name for name, in the customer's order.

    A sector added, removed, renamed or reordered in ``naics_sectors`` without
    this file being revisited fails here — which is the whole reason the
    transcription is allowed to exist.
    """
    assert _entries("CBA_INDUSTRY_SECTORS") == [
        (sector.code, sector.name) for sector in NAICS_SECTORS
    ]


def test_the_role_mirror_matches_the_released_taxonomy_exactly() -> None:
    assert _entries("CBA_ROLE_CATEGORIES") == [
        (category.code, category.name) for category in CBA_ROLE_CATEGORIES
    ]


def test_the_mirror_names_the_versions_it_was_transcribed_from() -> None:
    """A revision of either taxonomy must not leave this file quietly stale.

    The versions are not sent anywhere — the server stamps the version it
    actually resolved against onto every stored classification. They are here so
    a taxonomy revision cannot pass unnoticed even in the case where the two
    lists happen to still agree.
    """
    assert _version("CBA_NAICS_TAXONOMY_VERSION") == NAICS_TAXONOMY_VERSION
    assert _version("CBA_ROLE_TAXONOMY_VERSION") == CBA_ROLE_TAXONOMY_VERSION


def test_the_mirror_declares_its_source() -> None:
    """A mirror that does not name what it mirrors becomes a second truth."""
    source = MIRROR_PATH.read_text(encoding="utf-8")
    assert "smartmatch_domain/naics_sectors.py" in source
    assert "smartmatch_domain/cba_role_categories.py" in source


def test_the_mirror_says_it_validates_nothing() -> None:
    """The form renders options; the server decides what a code means.

    Stated in the file rather than only here, because the next person tempted to
    add a code to "make the form accept it" reads the file, not this test.
    """
    source = MIRROR_PATH.read_text(encoding="utf-8").lower()
    assert "validates" in source or "validation" in source
    assert "server-side" in source
