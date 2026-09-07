#!/usr/bin/env python3
"""Generate the California ZCTA centroid table from public-domain Census data.

OQ-CBA-024. Customer §10 measures Proximity in miles from the CPP campus, and
``smartmatch_domain.factors.proximity`` refuses to invent a distance: it scores
an already-resolved ``distance_miles`` and answers *unknown* when the caller has
none. Something has to turn a speaker's postal code into a coordinate without
calling a geocoding provider, and this script is that something — run once at
**build time**, never on a request path.

Why a generator and not a hand-written table
============================================

Every coordinate this emits is copied, unmodified, out of the US Census
Bureau's ZIP Code Tabulation Area Gazetteer. None is typed by a person, rounded
by hand, interpolated between neighbours, or "looked up" and transcribed. That
is the whole point: a fabricated coordinate is a guess wearing a measurement's
clothes, which is the defect ADR-0011 exists to forbid, and it would be worse
here than shipping no table at all — a wrong centroid does not announce itself,
it just quietly moves a speaker across a 25- or 75-mile band.

The generator therefore verifies a **pinned SHA-256** of each source before
reading it. If the Census reissues a file at the same URL the digest stops
matching and the script refuses, rather than silently regenerating the table
from data nobody reviewed.

Sources (both public domain, US Census Bureau)
==============================================

``2023_Gaz_zcta_national.zip``
    The 2023 national ZCTA Gazetteer. Supplies ``INTPTLAT``/``INTPTLONG`` —
    the ZCTA's internal point, which the Census guarantees lies inside the
    area — for every ZCTA in the country. This is the only source of
    coordinates.

``tab20_zcta520_county20_natl.txt``
    The 2020 ZCTA-to-County relationship file. Supplies the *membership*
    answer, and it is used because the 2023 Gazetteer has no state column and
    a ZIP-prefix rule ("900xx-961xx is California") would be a heuristic, not
    data. Six California ZCTAs fall outside that prefix range because they
    straddle the Nevada and Oregon lines; a prefix rule would drop them, and
    nothing in the file would say so.

A ZCTA is Californian here when **any part of it lies in a county whose state
FIPS code is 06**. That is a deliberately inclusive reading: a ZCTA straddling
a state line is a real place with a real Census centroid, and a speaker who
lives in it has a real distance from Pomona. What the rule never does is
*guess* — a ZCTA with no California county part is simply absent from the
table, and an absent ZIP resolves to unknown rather than to a nearest match.

Usage
=====

Download both sources and regenerate the module in place::

    python tools/generate_zcta_centroids.py

Point at already-downloaded copies (no network at all)::

    python tools/generate_zcta_centroids.py \\
        --gazetteer /path/to/2023_Gaz_zcta_national.zip \\
        --relationship /path/to/tab20_zcta520_county20_natl.txt

Fail instead of writing, to prove the committed module is current::

    python tools/generate_zcta_centroids.py --check

Exit codes: ``0`` written or current, ``1`` stale under ``--check``, ``2`` a
source failed its digest check.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import sys
import urllib.request
import zipfile
from collections.abc import Iterator, Mapping
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Where the generated module is written. Inside the domain package, following
#: ``naics_sectors.py``'s precedent: that package's import-linter contract
#: forbids ``os`` and ``pathlib``, so a table loaded from disk could not live in
#: the layer at all. The consequence is the intended one — every version of the
#: table is a reviewed code diff.
OUTPUT_PATH = REPO_ROOT / "python" / "smartmatch_domain" / "smartmatch_domain" / "zcta_centroids.py"

GAZETTEER_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/"
    "2023_Gaz_zcta_national.zip"
)
GAZETTEER_SHA256 = "75191ab2d3df4b668fb511d2726d97c521d6d1ff555725704a5d9bb3bc2077ce"
GAZETTEER_MEMBER = "2023_Gaz_zcta_national.txt"

RELATIONSHIP_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/"
    "tab20_zcta520_county20_natl.txt"
)
RELATIONSHIP_SHA256 = "3ed41278d637dc249e0323306f68be8a6c234e3090f4de88ef328dee71aeaaaf"

#: The Gazetteer vintage, recorded in the generated module and echoed by the
#: resolver as a distance's provenance. Bumping the source means bumping this.
VINTAGE = "2023"

#: The token every distance resolved from this table carries into its score.
PROVENANCE = "zcta-centroid-2023"

#: California. The relationship file's ``GEOID_COUNTY_20`` is ``SSCCC``.
CALIFORNIA_STATE_FIPS = "06"


class SourceDigestError(RuntimeError):
    """A source file did not match its pinned SHA-256."""


def _read_source(url: str, expected_sha256: str, local: Path | None) -> bytes:
    """Return the source bytes, refusing anything that fails its pinned digest.

    Args:
        url: Where the file is fetched from when ``local`` is ``None``. This is
            a build-time fetch; nothing on a request path reaches here.
        expected_sha256: The digest the bytes must have.
        local: An already-downloaded copy to read instead of fetching.

    Raises:
        SourceDigestError: If the bytes do not match ``expected_sha256``.
    """
    if local is not None:
        payload = local.read_bytes()
        origin = str(local)
    else:
        with urllib.request.urlopen(url) as response:
            payload = response.read()
        origin = url

    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected_sha256:
        raise SourceDigestError(
            f"{origin}: expected sha256 {expected_sha256}, got {actual}. The source "
            "changed under a pinned digest. Review the new file and update the pin "
            "deliberately; do not regenerate the table from data nobody has read."
        )
    return payload


def california_zctas(relationship_bytes: bytes) -> frozenset[str]:
    """Every ZCTA with land in a California county, per the relationship file.

    The file is pipe-delimited with a UTF-8 BOM. ``GEOID_ZCTA5_20`` is the ZCTA
    and ``GEOID_COUNTY_20`` is ``SSCCC``; rows describing a county with no ZCTA
    part carry an empty ZCTA id and are skipped rather than guessed at.
    """
    lines = relationship_bytes.decode("utf-8-sig").splitlines()
    header = [column.strip() for column in lines[0].split("|")]
    zcta_index = header.index("GEOID_ZCTA5_20")
    county_index = header.index("GEOID_COUNTY_20")

    found: set[str] = set()
    for line in lines[1:]:
        if not line.strip():
            continue
        fields = line.split("|")
        zcta = fields[zcta_index].strip()
        county = fields[county_index].strip()
        if not zcta or not county.startswith(CALIFORNIA_STATE_FIPS):
            continue
        found.add(zcta)
    return frozenset(found)


def gazetteer_centroids(gazetteer_bytes: bytes) -> Mapping[str, tuple[float, float]]:
    """Every national ZCTA's internal point, keyed by 5-digit ZCTA.

    ``INTPTLAT``/``INTPTLONG`` are the Census's own internal point for the
    area, not a bounding-box midpoint computed here. The values are parsed and
    never rounded: rounding a published coordinate is a small edit to somebody
    else's measurement.
    """
    with zipfile.ZipFile(io.BytesIO(gazetteer_bytes)) as archive:
        raw = archive.read(GAZETTEER_MEMBER)

    lines = raw.decode("utf-8-sig").splitlines()
    header = [column.strip() for column in lines[0].split("\t")]
    geoid_index = header.index("GEOID")
    lat_index = header.index("INTPTLAT")
    lon_index = header.index("INTPTLONG")

    centroids: dict[str, tuple[float, float]] = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        fields = [column.strip() for column in line.split("\t")]
        centroids[fields[geoid_index]] = (float(fields[lat_index]), float(fields[lon_index]))
    return centroids


def _entries(
    centroids: Mapping[str, tuple[float, float]],
    wanted: frozenset[str],
) -> list[tuple[str, float, float]]:
    """The wanted ZCTAs' centroids, sorted by ZCTA for a stable diff.

    Raises:
        KeyError: If a California ZCTA has no Gazetteer row. That is a source
            mismatch worth stopping on, not a row to omit quietly.
    """
    missing = sorted(wanted - set(centroids))
    if missing:
        raise KeyError(
            f"{len(missing)} California ZCTA(s) have no row in the {VINTAGE} Gazetteer: "
            f"{missing[:10]}. The two sources disagree; resolve that before generating."
        )
    return [(zcta, *centroids[zcta]) for zcta in sorted(wanted)]


def _header_lines(entry_count: int) -> Iterator[str]:
    """The generated module's docstring and constants."""
    yield '"""California ZIP Code Tabulation Area centroids (OQ-CBA-024).'
    yield ""
    yield "GENERATED FILE -- DO NOT EDIT BY HAND."
    yield ""
    yield "Regenerate with::"
    yield ""
    yield "    python tools/generate_zcta_centroids.py"
    yield ""
    yield "Every coordinate below is copied unmodified from the US Census Bureau's"
    yield f"{VINTAGE} national ZIP Code Tabulation Area Gazetteer (public domain). None was"
    yield "typed, rounded, interpolated, or estimated by a person or by this project, and"
    yield "no geocoding provider was called to obtain one or is called to use one. A"
    yield "hand-written coordinate here would be a guess wearing a measurement's clothes,"
    yield "which is the defect ADR-0011 exists to forbid."
    yield ""
    yield "Sources, pinned by digest in ``tools/generate_zcta_centroids.py``:"
    yield ""
    yield "* coordinates -- 2023_Gaz_zcta_national.zip, sha256"
    yield f"  {GAZETTEER_SHA256}, from"
    yield "  https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/"
    yield "* California membership -- tab20_zcta520_county20_natl.txt, sha256"
    yield f"  {RELATIONSHIP_SHA256}, from"
    yield "  https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/"
    yield ""
    yield "California only, deliberately. A ZCTA appears here when any part of it lies in a"
    yield f"county whose state FIPS code is {CALIFORNIA_STATE_FIPS}, which is why a handful"
    yield "of entries fall outside the 900xx-961xx ZIP prefix range: they straddle the"
    yield "Nevada and Oregon lines. A ZIP this table does not name resolves to **unknown**"
    yield "-- never to a nearest match, a state centroid, or the Far band."
    yield '"""'
    yield ""
    yield "from __future__ import annotations"
    yield ""
    yield "from collections.abc import Mapping"
    yield "from types import MappingProxyType"
    yield "from typing import Final"
    yield ""
    yield "__all__ = ["
    yield '    "CALIFORNIA_STATE_FIPS",'
    yield '    "CA_ZCTA_CENTROIDS",'
    yield '    "ZCTA_CENTROID_PROVENANCE",'
    yield '    "ZCTA_CENTROID_VINTAGE",'
    yield '    "ZCTA_GAZETTEER_SHA256",'
    yield '    "ZCTA_GAZETTEER_URL",'
    yield '    "ZCTA_STATE_RELATIONSHIP_SHA256",'
    yield '    "ZCTA_STATE_RELATIONSHIP_URL",'
    yield "]"
    yield ""
    yield "#: The Gazetteer vintage every coordinate below was taken from. A stored score's"
    yield "#: provenance names it, so a distance measured under one vintage is never read"
    yield "#: as though it had been measured under another."
    yield f'ZCTA_CENTROID_VINTAGE: Final[str] = "{VINTAGE}"'
    yield ""
    yield "#: The provenance token a distance resolved from this table carries."
    yield f'ZCTA_CENTROID_PROVENANCE: Final[str] = "{PROVENANCE}"'
    yield ""
    yield "#: Where the coordinates came from, and the digest they were verified against."
    yield "ZCTA_GAZETTEER_URL: Final[str] = ("
    yield '    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/"'
    yield '    "2023_Gaz_zcta_national.zip"'
    yield ")"
    yield "ZCTA_GAZETTEER_SHA256: Final[str] = ("
    yield f'    "{GAZETTEER_SHA256}"'
    yield ")"
    yield ""
    yield "#: Where the California membership answer came from. The Gazetteer has no state"
    yield "#: column, and a ZIP-prefix rule would be a heuristic rather than data."
    yield "ZCTA_STATE_RELATIONSHIP_URL: Final[str] = ("
    yield '    "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/"'
    yield '    "tab20_zcta520_county20_natl.txt"'
    yield ")"
    yield "ZCTA_STATE_RELATIONSHIP_SHA256: Final[str] = ("
    yield f'    "{RELATIONSHIP_SHA256}"'
    yield ")"
    yield ""
    yield "#: California's state FIPS code, the membership test applied to the"
    yield "#: relationship file's ``GEOID_COUNTY_20``."
    yield f'CALIFORNIA_STATE_FIPS: Final[str] = "{CALIFORNIA_STATE_FIPS}"'
    yield ""
    yield f"#: {entry_count} ZCTAs, keyed by 5-digit ZCTA, valued ``(latitude, longitude)``"
    yield "#: in degrees. Read-only: a mutable module-level table is one any caller can"
    yield "#: edit at runtime, and a coordinate nobody can trace is worse than none."
    yield "CA_ZCTA_CENTROIDS: Final[Mapping[str, tuple[float, float]]] = MappingProxyType("
    yield "    {"


def render_module(entries: list[tuple[str, float, float]]) -> str:
    """The full text of the generated module."""
    lines = list(_header_lines(len(entries)))
    lines.extend(f'        "{zcta}": ({lat!r}, {lon!r}),' for zcta, lat, lon in entries)
    lines.append("    }")
    lines.append(")")
    return "\n".join(lines) + "\n"


def build(gazetteer: Path | None, relationship: Path | None) -> str:
    """Fetch or read both sources and render the module text."""
    relationship_bytes = _read_source(RELATIONSHIP_URL, RELATIONSHIP_SHA256, relationship)
    gazetteer_bytes = _read_source(GAZETTEER_URL, GAZETTEER_SHA256, gazetteer)
    wanted = california_zctas(relationship_bytes)
    centroids = gazetteer_centroids(gazetteer_bytes)
    return render_module(_entries(centroids, wanted))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the CA ZCTA centroid module.")
    parser.add_argument("--gazetteer", type=Path, default=None, help="Local Gazetteer .zip")
    parser.add_argument("--relationship", type=Path, default=None, help="Local relationship .txt")
    parser.add_argument("--out", type=Path, default=OUTPUT_PATH, help="Module to write")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; exit 1 if the committed module is not what would be written.",
    )
    args = parser.parse_args()

    try:
        rendered = build(args.gazetteer, args.relationship)
    except SourceDigestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.check:
        current = args.out.read_text(encoding="utf-8") if args.out.exists() else ""
        if current == rendered:
            print(f"{args.out} is current.")
            return 0
        print(f"{args.out} is stale; regenerate it.", file=sys.stderr)
        return 1

    args.out.write_text(rendered, encoding="utf-8")
    print(f"Wrote {args.out}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
