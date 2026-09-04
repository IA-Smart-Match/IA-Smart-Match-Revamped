#!/usr/bin/env python3
"""Dependency license policy and CycloneDX SBOM, from the standard library only.

Two gates over one dependency inventory (Foundation item F2b):

``licenses``
    Every distribution the lock files pin must resolve to a license on the
    allowlist in this file. A license that cannot be determined is a **finding,
    not a pass** — fail closed, because "no license declared" is the state of a
    package nobody may legally redistribute, not the state of a safe one.

``sbom``
    A CycloneDX 1.5 JSON bill of materials for the pinned dependency set,
    carrying the ``--hash=sha256:`` digests the lock files already pin. The
    hashes are what make this more than a package list: a consumer can check
    that the artifact they hold is the artifact this build declared.

The trade, stated plainly
-------------------------
A purpose-built tool — ``cyclonedx-py``, ``pip-licenses``, ``syft`` — would
normally be preferred here, and each is better at this than this file is. This
exists because adding a dependency was ruled out of scope for this branch: a new
dependency is itself a supply-chain change, and an open pull request is already
touching ``requirements/*.txt``, so recompiling the locks here would collide.
The same constraint produced ``tools/agent_memory_check.py``'s hand-rolled
front-matter parser, for the same reason.

What this does NOT do, and where a real tool would be better:

* **No dependency graph.** CycloneDX ``dependencies`` is emitted as a flat list
  under the root component. pip-compile's ``# via`` comments record the edges,
  but reconstructing a graph from comments is guesswork and a wrong graph is
  worse than an absent one.
* **No license *text* verification.** It reads *declared* metadata — the
  ``License-Expression``, ``License``, and ``License ::`` classifier fields.
  It does not read ``LICENSE`` files and does not detect a package whose
  declared license contradicts its bundled text, nor vendored third-party code
  under a different license (``pip`` vendors twenty-odd packages; ``mypy``
  ships typeshed).
* **No SPDX license list validation.** The identifiers below are matched
  against the table in this file, not against the authoritative SPDX list.
* **Approximate free-text normalization.** ``License: "BSD 2-Clause License"``
  is mapped to ``BSD-2-Clause`` by the table in ``_FREE_TEXT``. Anything the
  table does not recognize falls through to classifiers, and then to *unknown*.

What is in scope
----------------
**The lock files are the authority for the package set; the environment is
consulted only for license metadata.** The distinction matters and is the one
thing most easily gotten wrong here. ``importlib.metadata`` describes what is
installed in the interpreter running this script, which is not the same set as
what the locks pin: a virtualenv also holds ``pip``, ``setuptools``, and this
repository's own editable workspace packages, none of which are locked, and it
may be missing something the locks pin. So:

* The package set, versions, and hashes come from ``requirements/runtime.txt``
  and ``requirements/dev.txt``.
* Licenses come from ``importlib.metadata`` for those distributions.
* A locked distribution that is **not installed** is reported as
  ``not-installed`` and fails the check — its license is unknown, and an
  unknown license is a finding.
* A locked distribution installed at a **different version** than the lock pins
  is reported as ``version-mismatch`` and fails the check: the license read then
  describes an artifact other than the one that ships.
* ``pip``, ``setuptools``, ``wheel``, and the first-party ``smartmatch-*``
  packages are outside the lock and therefore outside this check. They are not
  shipped by ``Dockerfile.api``/``Dockerfile.worker`` as dependencies; the
  first-party packages are this repository.

Usage::

    python tools/supply_chain.py licenses              # policy gate
    python tools/supply_chain.py licenses --json
    python tools/supply_chain.py sbom                  # CycloneDX 1.5 to stdout
    python tools/supply_chain.py sbom -o sbom.json --include-dev

Exit codes: ``0`` clean, ``1`` findings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from dataclasses import dataclass, field
from importlib.metadata import Distribution, distributions
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The locks, and what each one describes. ``runtime`` is what the container
#: ships; ``dev`` is additionally installed in CI and on developer machines.
RUNTIME_LOCK = REPO_ROOT / "requirements" / "runtime.txt"
DEV_LOCK = REPO_ROOT / "requirements" / "dev.txt"

# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

#: Licenses permitted without further discussion, each with the reason it is
#: acceptable *for this project* — a permissive license imposes no obligation
#: on a hosted service beyond attribution.
#:
#: Adding a line here is the visible act: it is a diff in a reviewed file that
#: has to name a rationale, and ``tests/unit/test_supply_chain.py`` fails if the
#: rationale is missing or empty. Do not widen this table to make a build green;
#: widen it when the program has decided the obligation is acceptable.
ALLOWED_LICENSES: dict[str, str] = {
    "MIT": "Permissive; attribution only.",
    "BSD-2-Clause": "Permissive; attribution only.",
    "BSD-3-Clause": "Permissive; attribution and no-endorsement only.",
    "BSD": (
        "Only reachable from the OSI-approved 'License :: OSI Approved :: BSD "
        "License' classifier, which does not say which BSD variant. Every "
        "OSI-approved BSD variant is permissive, so the ambiguity does not "
        "change the answer — but it is recorded as its own identifier rather "
        "than silently promoted to BSD-3-Clause, which would claim a precision "
        "the metadata does not carry."
    ),
    "Apache-2.0": "Permissive; attribution, notice retention, and a patent grant.",
    "ISC": "Permissive; attribution only.",
    "PSF-2.0": "Permissive; the license CPython itself ships under.",
    "0BSD": "Public-domain-equivalent.",
    "Unlicense": "Public-domain-equivalent.",
    "Python-2.0": "Permissive; the historical CPython license.",
}

#: Per-distribution exceptions: a license NOT on the allowlist, permitted for
#: one named distribution, with the reason and the conditions the reason rests
#: on. Each entry is keyed by ``(normalized distribution name, license id)`` so
#: it stops applying the moment the distribution relicenses.
#:
#: An exception is a weaker control than an allowlist entry, on purpose: it is
#: narrow, it names conditions that can be checked by a human, and it shows up
#: in the output of every single run (see ``main``) rather than disappearing
#: into a green check.
LICENSE_EXCEPTIONS: dict[tuple[str, str], str] = {
    ("psycopg", "LGPL-3.0-only"): (
        "The PostgreSQL driver, and the only one the architecture names (v1.1 "
        "§3.1). LGPL obligations attach to distributing the library or a "
        "derivative of it. This service imports it unmodified at runtime, is "
        "not distributed to users, and neither statically links nor vendors it; "
        "the container image is an internal deployment artifact. If the project "
        "ever ships an image to a third party, or patches psycopg, this entry "
        "stops being sufficient and the obligation becomes real."
    ),
    ("psycopg-binary", "LGPL-3.0-only"): (
        "The prebuilt binary wheel for the same driver, same version, same "
        "license, and the same reasoning as the psycopg entry above. It is a "
        "separate distribution and so needs its own entry rather than "
        "inheriting one."
    ),
    ("certifi", "MPL-2.0"): (
        "Mozilla's CA bundle, pulled in transitively by httpx (dev/test only — "
        "it is not in requirements/runtime.txt). MPL-2.0 copyleft is per-file: "
        "it obliges publishing changes to MPL-licensed files, and there are no "
        "changes to them. The bundle is used verbatim."
    ),
    ("pathspec", "MPL-2.0"): (
        "Gitignore-style path matching, pulled in transitively by mypy "
        "(dev/test only — it is not in requirements/runtime.txt, and no "
        "shipped image contains it). Same per-file MPL reasoning as certifi: "
        "used verbatim, unmodified."
    ),
    # Controller ruling (Task 5 / M7, 2026-09-03), pending program-owner sign-off
    # on the PR: numpy is transitive from ortools, required by the architecture
    # for CP-SAT Stage B portfolio assignment (v1.1 §1.2). Its License-Expression
    # is "BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0" — three of the five
    # component licenses are already on ALLOWED_LICENSES; Zlib and CC0-1.0 cover
    # vendored components inside a distribution whose primary license is the
    # already-allowed BSD-3-Clause. ALLOWED_LICENSES is deliberately not widened
    # for either, so a future dependency does not silently inherit them.
    ("numpy", "Zlib"): (
        "Covers a vendored component inside numpy, whose primary license is the "
        "already-allowed BSD-3-Clause. Zlib is OSI-approved permissive: "
        "attribution, no misrepresentation of the software's origin, and notice "
        "retention on redistribution of source — no copyleft. numpy is imported "
        "unmodified at runtime and is neither vendored nor patched by this "
        "project. If this project ever patches or vendors numpy, this entry "
        "stops being sufficient and the obligation becomes real."
    ),
    ("numpy", "CC0-1.0"): (
        "Covers a vendored component inside numpy, whose primary license is the "
        "already-allowed BSD-3-Clause. CC0-1.0 is a public-domain dedication: it "
        "imposes no obligation at all. numpy is imported unmodified at runtime "
        "and is neither vendored nor patched by this project. If this project "
        "ever patches or vendors numpy, this entry stops being sufficient and "
        "the obligation becomes real."
    ),
}

# ---------------------------------------------------------------------------
# License metadata resolution
# ---------------------------------------------------------------------------

#: Free-text ``License:`` values, lowercased and stripped of punctuation, mapped
#: to an SPDX identifier. Deliberately conservative: anything absent falls
#: through to classifiers and then to *unknown*, which fails the gate. Guessing
#: here would turn a fail-closed gate into a fail-open one.
_FREE_TEXT: dict[str, str] = {
    "mit": "MIT",
    "mit license": "MIT",
    "the mit license": "MIT",
    "mit license mit": "MIT",
    "bsd": "BSD",
    "bsd license": "BSD",
    "bsd 2 clause": "BSD-2-Clause",
    "bsd 2 clause license": "BSD-2-Clause",
    "bsd 2 clause simplified license": "BSD-2-Clause",
    "simplified bsd": "BSD-2-Clause",
    "bsd 3 clause": "BSD-3-Clause",
    "bsd 3 clause license": "BSD-3-Clause",
    "3 clause bsd license": "BSD-3-Clause",
    "bsd 3 clause new or revised license": "BSD-3-Clause",
    "new bsd": "BSD-3-Clause",
    "new bsd license": "BSD-3-Clause",
    "modified bsd license": "BSD-3-Clause",
    "apache 2 0": "Apache-2.0",
    "apache 2": "Apache-2.0",
    "apache license 2 0": "Apache-2.0",
    "apache software license": "Apache-2.0",
    "apache software license 2 0": "Apache-2.0",
    "isc": "ISC",
    "isc license": "ISC",
    "isc license iscl": "ISC",
    "mpl 2 0": "MPL-2.0",
    "mozilla public license 2 0": "MPL-2.0",
    "mozilla public license 2 0 mpl 2 0": "MPL-2.0",
    "lgpl 3 0 only": "LGPL-3.0-only",
    "lgplv3": "LGPL-3.0-only",
    "gnu lesser general public license v3 lgplv3": "LGPL-3.0-only",
    "gpl 3 0 only": "GPL-3.0-only",
    "gplv3": "GPL-3.0-only",
    "psf 2 0": "PSF-2.0",
    "python software foundation license": "PSF-2.0",
    "python 2 0": "Python-2.0",
    "0bsd": "0BSD",
    "the unlicense unlicense": "Unlicense",
    "unlicense": "Unlicense",
}

#: The trailing segment of a ``License :: OSI Approved :: X`` classifier,
#: normalized the same way, maps through ``_FREE_TEXT``. Two classifiers that
#: need their own line because the normalized form is not in that table.
_CLASSIFIER_EXTRA: dict[str, str] = {
    "gnu general public license v3 gplv3": "GPL-3.0-only",
    "gnu affero general public license v3": "AGPL-3.0-only",
}

#: A ``License:`` value longer than this, or containing a newline, is the full
#: license *text* rather than a name. Those are not normalized — falling through
#: to classifiers gives a better answer than pattern-matching prose.
_MAX_FREE_TEXT = 64


def normalize_name(name: str) -> str:
    """Normalize a distribution name per PEP 503."""
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def _normalize_license_text(value: str) -> str:
    """Lowercase, drop punctuation, and collapse whitespace for table lookup."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def license_from_free_text(value: str) -> str | None:
    """Map a free-text ``License:`` value to an SPDX identifier, or ``None``."""
    if not value or "\n" in value or len(value) > _MAX_FREE_TEXT:
        return None
    stripped = value.strip()
    # Already an SPDX identifier or expression we recognize verbatim.
    if stripped in ALLOWED_LICENSES or stripped in {lic for _dist, lic in LICENSE_EXCEPTIONS}:
        return stripped
    if _EXPRESSION_TOKEN.fullmatch(stripped) is None and _looks_like_expression(stripped):
        return stripped
    return _FREE_TEXT.get(_normalize_license_text(stripped))


def license_from_classifiers(classifiers: list[str]) -> str | None:
    """Map ``License :: ...`` classifiers to an SPDX expression, or ``None``.

    Several classifiers mean the package is offered under any of them, which is
    an SPDX ``OR``. ``License :: OSI Approved`` on its own carries no identifier
    and is ignored.
    """
    ids: list[str] = []
    for classifier in classifiers:
        parts = [part.strip() for part in classifier.split("::")]
        if not parts or parts[0] != "License" or len(parts) < 2:
            continue
        tail = parts[-1]
        if tail in {"License", "OSI Approved"}:
            continue
        normalized = _normalize_license_text(tail)
        resolved = _FREE_TEXT.get(normalized) or _CLASSIFIER_EXTRA.get(normalized)
        if resolved and resolved not in ids:
            ids.append(resolved)
    if not ids:
        return None
    return " OR ".join(ids)


def declared_license(dist: Distribution) -> tuple[str | None, str]:
    """Return ``(license expression, where it came from)`` for a distribution.

    Precedence runs most-specific first: PEP 639's ``License-Expression`` is an
    SPDX expression by definition, ``License`` is free text that sometimes
    normalizes, and classifiers are a coarse taxonomy. The source is returned
    alongside the answer so a surprising result can be traced to the field that
    produced it rather than re-derived by hand.
    """
    metadata = dist.metadata

    expression = (metadata.get("License-Expression") or "").strip()
    if expression:
        return expression, "License-Expression"

    free_text = (metadata.get("License") or "").strip()
    if free_text:
        resolved = license_from_free_text(free_text)
        if resolved:
            return resolved, "License"

    classifiers = [c for c in (metadata.get_all("Classifier") or []) if isinstance(c, str)]
    from_classifiers = license_from_classifiers(classifiers)
    if from_classifiers:
        return from_classifiers, "Classifier"

    if free_text:
        # Present but unrecognized: report it verbatim so a human sees what the
        # package actually said, rather than a bare "unknown".
        return None, f"License (unrecognized: {free_text[:60]!r})"
    return None, "none"


# ---------------------------------------------------------------------------
# SPDX expression evaluation
# ---------------------------------------------------------------------------

_EXPRESSION_TOKEN = re.compile(r"[A-Za-z0-9.+-]+")
_TOKEN_PATTERN = re.compile(r"\(|\)|[A-Za-z0-9.+-]+")


def _looks_like_expression(value: str) -> bool:
    """Whether a string is plausibly an SPDX expression rather than prose."""
    tokens = _TOKEN_PATTERN.findall(value)
    if "".join(value.split()) != "".join("".join(tokens).split()):
        return False
    upper = {t.upper() for t in tokens}
    return bool(upper & {"AND", "OR", "WITH"})


class ExpressionError(ValueError):
    """An SPDX expression that cannot be parsed."""


def _tokenize(expression: str) -> list[str]:
    tokens = _TOKEN_PATTERN.findall(expression)
    if not tokens:
        raise ExpressionError(f"empty license expression: {expression!r}")
    return tokens


def license_ids(expression: str) -> list[str]:
    """Every license identifier mentioned by an expression, in order."""
    out: list[str] = []
    skip_next = False
    for token in _tokenize(expression):
        if token in {"(", ")"}:
            continue
        if token.upper() in {"AND", "OR"}:
            continue
        if token.upper() == "WITH":
            # The operand after WITH is an exception identifier, not a license.
            skip_next = True
            continue
        if skip_next:
            skip_next = False
            continue
        if token not in out:
            out.append(token)
    return out


def evaluate(expression: str, allowed: set[str]) -> bool:
    """Evaluate an SPDX expression against a set of acceptable identifiers.

    ``AND`` requires every operand (the obligations compose), ``OR`` requires
    one (the recipient may choose), and ``WITH`` attaches an exception to the
    preceding identifier — the exception can only *narrow* an obligation, so
    the identifier alone decides. Unparseable input raises rather than
    defaulting to allowed: a gate that fails open on malformed input is not a
    gate.
    """
    tokens = _tokenize(expression)
    position = 0

    def peek() -> str | None:
        return tokens[position] if position < len(tokens) else None

    def take() -> str:
        nonlocal position
        token = tokens[position]
        position += 1
        return token

    def parse_or() -> bool:
        value = parse_and()
        while (token := peek()) is not None and token.upper() == "OR":
            take()
            value = parse_and() or value
        return value

    def parse_and() -> bool:
        value = parse_atom()
        while (token := peek()) is not None and token.upper() == "AND":
            take()
            value = parse_atom() and value
        return value

    def parse_atom() -> bool:
        token = peek()
        if token is None:
            raise ExpressionError(f"truncated license expression: {expression!r}")
        if token == "(":
            take()
            value = parse_or()
            if peek() != ")":
                raise ExpressionError(f"unbalanced parentheses: {expression!r}")
            take()
        else:
            identifier = take()
            if identifier.upper() in {"AND", "OR", "WITH", ")"}:
                raise ExpressionError(f"misplaced operator {identifier!r}: {expression!r}")
            value = identifier in allowed
            if (nxt := peek()) is not None and nxt.upper() == "WITH":
                take()
                if peek() is None:
                    raise ExpressionError(f"WITH without an exception: {expression!r}")
                take()
        return value

    result = parse_or()
    if position != len(tokens):
        raise ExpressionError(f"trailing tokens in license expression: {expression!r}")
    return result


# ---------------------------------------------------------------------------
# Lock parsing
# ---------------------------------------------------------------------------

_PIN = re.compile(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?==(?P<version>[^\s;\\]+)")
_HASH = re.compile(r"--hash=sha256:([0-9a-f]{64})")


@dataclass(frozen=True)
class LockedDistribution:
    """One distribution pinned by the lock files."""

    name: str
    version: str
    sha256: tuple[str, ...]
    locks: tuple[str, ...]


def parse_lock(text: str) -> dict[str, tuple[str, tuple[str, ...]]]:
    """Parse a pip-compile lock into ``{name: (version, sha256 hashes)}``.

    Only the pinned-requirement grammar pip-compile emits is accepted: a
    ``name==version`` line, optionally with an extras group, followed by
    backslash-continued ``--hash=sha256:`` lines. Options (``--index-url``),
    blank lines, and comments are ignored.
    """
    joined = text.replace("\\\n", " ")
    found: dict[str, tuple[str, tuple[str, ...]]] = {}
    for raw in joined.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        match = _PIN.match(line)
        if not match:
            continue
        name = normalize_name(match.group("name"))
        version = match.group("version")
        hashes = tuple(sorted(set(_HASH.findall(line))))
        if name in found:
            previous_version, previous_hashes = found[name]
            if previous_version != version:
                raise ValueError(
                    f"{name} is pinned twice at different versions in one lock: "
                    f"{previous_version} and {version}"
                )
            hashes = tuple(sorted(set(previous_hashes) | set(hashes)))
        found[name] = (version, hashes)
    return found


def lock_label(path: Path) -> str:
    """A repository-relative label for a lock file, or its path if it is outside.

    Test fixtures live in a temporary directory, so this must not assume every
    lock it is handed sits under the repository root.
    """
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def load_locks(paths: list[Path]) -> tuple[dict[str, LockedDistribution], list[str]]:
    """Merge several locks, reporting any disagreement rather than resolving it.

    Two locks pinning the same distribution at different versions is a real
    defect — CI would install one of them and the other file would be a lie —
    so it is returned as a conflict instead of being silently reconciled.
    """
    merged: dict[str, LockedDistribution] = {}
    conflicts: list[str] = []
    for path in paths:
        label = lock_label(path)
        for name, (version, hashes) in parse_lock(path.read_text(encoding="utf-8")).items():
            existing = merged.get(name)
            if existing is None:
                merged[name] = LockedDistribution(name, version, hashes, (label,))
                continue
            if existing.version != version:
                conflicts.append(
                    f"{name} is pinned at {existing.version} in "
                    f"{', '.join(existing.locks)} and at {version} in {label}"
                )
                continue
            merged[name] = LockedDistribution(
                name,
                version,
                tuple(sorted(set(existing.sha256) | set(hashes))),
                (*existing.locks, label),
            )
    return merged, conflicts


def installed_distributions() -> dict[str, Distribution]:
    """Every distribution visible to the running interpreter, by normalized name."""
    found: dict[str, Distribution] = {}
    for dist in distributions():
        raw = dist.metadata["Name"]
        if not raw:
            continue
        found.setdefault(normalize_name(raw), dist)
    return found


# ---------------------------------------------------------------------------
# The license gate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Resolution:
    """What the check concluded about one locked distribution."""

    name: str
    version: str
    locks: tuple[str, ...]
    expression: str | None
    source: str
    status: str  # allowed | exception | disallowed | unknown | not-installed | version-mismatch
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status in {"allowed", "exception"}


@dataclass
class LicenseReport:
    """The outcome of a license-policy run."""

    resolutions: list[Resolution] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    @property
    def findings(self) -> list[Resolution]:
        return [r for r in self.resolutions if not r.ok]

    @property
    def exceptions_used(self) -> list[Resolution]:
        return [r for r in self.resolutions if r.status == "exception"]

    @property
    def ok(self) -> bool:
        return not self.findings and not self.conflicts


def resolve_one(
    locked: LockedDistribution,
    installed: dict[str, Distribution],
    allowed: set[str] | None = None,
    exceptions: dict[tuple[str, str], str] | None = None,
) -> Resolution:
    """Decide whether one locked distribution satisfies the license policy."""
    allowed = set(ALLOWED_LICENSES) if allowed is None else allowed
    exceptions = LICENSE_EXCEPTIONS if exceptions is None else exceptions

    dist = installed.get(locked.name)
    if dist is None:
        return Resolution(
            locked.name,
            locked.version,
            locked.locks,
            None,
            "none",
            "not-installed",
            "pinned by the lock but not installed here, so its license cannot be read",
        )

    if dist.version != locked.version:
        return Resolution(
            locked.name,
            locked.version,
            locked.locks,
            None,
            "none",
            "version-mismatch",
            f"lock pins {locked.version}, environment has {dist.version}; "
            "any license read here would describe the wrong artifact",
        )

    expression, source = declared_license(dist)
    if expression is None:
        return Resolution(
            locked.name,
            locked.version,
            locked.locks,
            None,
            source,
            "unknown",
            "no License-Expression, no recognizable License field, and no License :: classifier",
        )

    try:
        if evaluate(expression, allowed):
            return Resolution(
                locked.name, locked.version, locked.locks, expression, source, "allowed"
            )
    except ExpressionError as exc:
        return Resolution(
            locked.name,
            locked.version,
            locked.locks,
            expression,
            source,
            "unknown",
            str(exc),
        )

    # Not satisfied by the allowlist alone. Retry with any recorded exceptions
    # for this distribution folded in — an exception is per-distribution, so it
    # cannot leak into the evaluation of any other package.
    widened = set(allowed) | {lic for (dist_name, lic) in exceptions if dist_name == locked.name}
    if widened != allowed and evaluate(expression, widened):
        used = sorted(
            lic
            for lic in license_ids(expression)
            if (locked.name, lic) in exceptions and lic not in allowed
        )
        return Resolution(
            locked.name,
            locked.version,
            locked.locks,
            expression,
            source,
            "exception",
            "; ".join(exceptions[(locked.name, lic)] for lic in used),
        )

    outside = sorted(lic for lic in license_ids(expression) if lic not in widened)
    return Resolution(
        locked.name,
        locked.version,
        locked.locks,
        expression,
        source,
        "disallowed",
        f"not on the allowlist and not excepted: {', '.join(outside)}",
    )


def check_licenses(lock_paths: list[Path] | None = None) -> LicenseReport:
    """Run the license policy over the locked dependency set."""
    paths = [RUNTIME_LOCK, DEV_LOCK] if lock_paths is None else lock_paths
    locked, conflicts = load_locks(paths)
    installed = installed_distributions()
    report = LicenseReport(conflicts=conflicts)
    for name in sorted(locked):
        report.resolutions.append(resolve_one(locked[name], installed))
    return report


# ---------------------------------------------------------------------------
# CycloneDX 1.5
# ---------------------------------------------------------------------------

SPEC_VERSION = "1.5"

#: Fixed namespace for deriving a stable serial number from the BOM's content.
#: A random UUID would make every run of this tool produce a different document
#: for identical input, which defeats diffing one build's SBOM against another's.
_SERIAL_NAMESPACE = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")


def _license_entry(expression: str | None) -> list[dict[str, Any]]:
    if expression is None:
        return []
    ids = license_ids(expression)
    if len(ids) == 1 and ids[0] == expression.strip():
        known = expression.strip() in ALLOWED_LICENSES or any(
            lic == expression.strip() for _dist, lic in LICENSE_EXCEPTIONS
        )
        key = "id" if known else "name"
        return [{"license": {key: expression.strip()}}]
    return [{"expression": expression.strip()}]


def build_sbom(
    lock_paths: list[Path] | None = None,
    application_name: str = "smartmatch-platform",
    application_version: str = "0.1.0",
) -> dict[str, Any]:
    """Build a CycloneDX 1.5 document for the locked dependency set.

    The component set and the hashes come from the locks; licenses come from
    installed metadata, and a component whose license could not be determined
    carries a property saying so rather than an invented license.

    Every ``--hash`` the lock pins for a component is emitted. A pinned package
    usually has several — one per wheel platform, plus the sdist — and the lock
    accepts any of them, so listing them all is what the lock actually asserts.
    It is *not* a claim about which single artifact was installed; ``pip
    install --require-hashes`` is the thing that enforces the match.

    The document is deterministic: no timestamp, and a serial number derived
    from the content, so two runs over the same locks produce identical bytes.
    """
    paths = [RUNTIME_LOCK] if lock_paths is None else lock_paths
    locked, conflicts = load_locks(paths)
    if conflicts:
        raise ValueError("; ".join(conflicts))
    installed = installed_distributions()

    components: list[dict[str, Any]] = []
    for name in sorted(locked):
        entry = locked[name]
        dist = installed.get(name)
        expression: str | None = None
        source = "not-installed"
        if dist is not None and dist.version == entry.version:
            expression, source = declared_license(dist)
        elif dist is not None:
            source = f"installed-version-mismatch ({dist.version})"

        purl = f"pkg:pypi/{entry.name}@{entry.version}"
        component: dict[str, Any] = {
            "type": "library",
            "bom-ref": purl,
            "name": entry.name,
            "version": entry.version,
            "purl": purl,
            "hashes": [{"alg": "SHA-256", "content": h} for h in entry.sha256],
            "properties": [
                {"name": "smartmatch:lock", "value": ",".join(entry.locks)},
                {"name": "smartmatch:license-source", "value": source},
            ],
        }
        licenses = _license_entry(expression)
        if licenses:
            component["licenses"] = licenses
        else:
            component["properties"].append({"name": "smartmatch:license", "value": "undetermined"})
        components.append(component)

    root_ref = f"pkg:generic/{application_name}@{application_version}"
    digest = hashlib.sha256(
        json.dumps(components, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    serial = uuid.uuid5(_SERIAL_NAMESPACE, digest)

    return {
        "bomFormat": "CycloneDX",
        "specVersion": SPEC_VERSION,
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": root_ref,
                "name": application_name,
                "version": application_version,
            },
            "tools": [
                {
                    "vendor": "IA-Smart-Match",
                    "name": "tools/supply_chain.py",
                    "version": application_version,
                }
            ],
            "properties": [
                {
                    "name": "smartmatch:sources",
                    "value": ",".join(lock_label(p) for p in paths),
                },
                {
                    "name": "smartmatch:scope",
                    "value": (
                        "component set and hashes from the lock files; licenses from "
                        "installed metadata; no dependency graph (see the module "
                        "docstring for what this does not do)"
                    ),
                },
            ],
        },
        "components": components,
        "dependencies": [
            {"ref": root_ref, "dependsOn": [c["bom-ref"] for c in components]},
            *({"ref": c["bom-ref"], "dependsOn": []} for c in components),
        ],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _run_licenses(args: argparse.Namespace) -> int:
    report = check_licenses()

    if args.json:
        print(
            json.dumps(
                {
                    "ok": report.ok,
                    "conflicts": report.conflicts,
                    "distributions": [r.__dict__ for r in report.resolutions],
                },
                indent=2,
                default=list,
            )
        )
        return 0 if report.ok else 1

    for conflict in report.conflicts:
        print(f"  lock conflict: {conflict}")

    # Exceptions are printed on every run, green or not. An exception that only
    # shows up when something breaks is an exception nobody reviews.
    if report.exceptions_used:
        print(f"Recorded license exceptions in force ({len(report.exceptions_used)}):\n")
        for resolution in report.exceptions_used:
            print(f"  {resolution.name}=={resolution.version}  {resolution.expression}")
            print(f"    -> {resolution.detail}\n")

    if report.findings:
        print(f"License policy findings ({len(report.findings)}):\n")
        for resolution in report.findings:
            print(
                f"  {resolution.name}=={resolution.version}  [{resolution.status}]  "
                f"{resolution.expression or '(undetermined)'}"
            )
            print(f"    source: {resolution.source}")
            print(f"    -> {resolution.detail}\n")
        print(
            "Every finding must be resolved by removing the dependency, or by a "
            "reviewed\nentry in ALLOWED_LICENSES or LICENSE_EXCEPTIONS in "
            "tools/supply_chain.py that\nstates why the obligation is acceptable."
        )
    else:
        allowed = len([r for r in report.resolutions if r.status == "allowed"])
        print(
            f"License policy clean: {allowed} allowed, "
            f"{len(report.exceptions_used)} under a recorded exception, "
            f"0 undetermined ({len(report.resolutions)} locked distributions)."
        )

    return 0 if report.ok else 1


def _run_sbom(args: argparse.Namespace) -> int:
    paths = [RUNTIME_LOCK]
    if args.include_dev:
        paths.append(DEV_LOCK)
    document = build_sbom(paths)
    rendered = json.dumps(document, indent=2) + "\n"

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        undetermined = sum(1 for c in document["components"] if "licenses" not in c)
        print(
            f"Wrote CycloneDX {SPEC_VERSION} SBOM to {output}: "
            f"{len(document['components'])} components, "
            f"{sum(len(c['hashes']) for c in document['components'])} pinned hashes, "
            f"{undetermined} with an undetermined license."
        )
    else:
        sys.stdout.write(rendered)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    licenses = subparsers.add_parser(
        "licenses", help="fail the build on a dependency license outside the policy"
    )
    licenses.add_argument("--json", action="store_true", help="machine-readable output")
    licenses.set_defaults(handler=_run_licenses)

    sbom = subparsers.add_parser("sbom", help="emit a CycloneDX 1.5 JSON bill of materials")
    sbom.add_argument("-o", "--output", help="write to this path instead of stdout")
    sbom.add_argument(
        "--include-dev",
        action="store_true",
        help="also include requirements/dev.txt (default: runtime only, which is what ships)",
    )
    sbom.set_defaults(handler=_run_sbom)

    args = parser.parse_args(argv)
    handler: Any = args.handler
    result: int = handler(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
