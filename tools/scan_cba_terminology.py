#!/usr/bin/env python3
"""Scoped scanner for retired IA-West terminology in CBA-visible copy.

Customer requirements §4 replaces an institutional vocabulary and §25 lists
seven of those renames as P0. This scanner is the executable half of that
decision: it fails the build when copy a CBA user can read still says *IA
West*, *Insights Association*, *chapter*, *Chapter Admin*, *Member Portal*,
*volunteer opportunity*, or *membership / dues* as a product concept.

**Scope is the whole design.** A repository-wide grep for these words would be
a blind global replace with a green tick attached: it would demand renaming the
backend authorization ``membership`` record, the ``ia_west_legacy`` product
scope that exists precisely because CBA is the *other* product, and the
historical decision records that cite the legacy baseline by name. So this
scanner reads exactly two things:

* :data:`SCANNED_ROOTS` — the legacy frontend source tree, minus its tests,
  because that is where CBA-visible copy lives; and
* :data:`SCANNED_FILES` — named backend files whose *string literals are
  rendered to the user* (a registered metric's definition is shown verbatim on
  the page that reports it).

Comments are stripped from TypeScript sources before matching. A comment
explaining why the authorization ``membership`` row is untouched is not copy,
and a gate that cannot tell the difference forces engineers to delete their
own explanations.

Usage::

    python tools/scan_cba_terminology.py           # scan the repository
    python tools/scan_cba_terminology.py --json    # machine-readable output

Exit codes: ``0`` clean, ``1`` violations found.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Rule:
    """One retired term.

    Attributes:
        code: Stable identifier, cited by allowlist entries.
        pattern: Case-insensitive regular expression.
        replacement: The customer-approved term (§4), for the failure message.
        message: What is wrong and why it matters.
    """

    code: str
    pattern: str
    replacement: str
    message: str

    @property
    def regex(self) -> re.Pattern[str]:
        return re.compile(self.pattern, re.IGNORECASE)


#: Every pattern is deliberately narrower than the English word it names.
#:
#: The ``ia-west`` pattern does not match ``ia_west_legacy`` or
#: ``ia_west_chapter``: those are wire values in a server contract, not copy.
#: The ``chapter`` pattern does not match ``chapter_membership_dues`` because
#: ``_`` is a word character, so the capability identifier the policy defines
#: survives the sweep that its own policy authorised. ``membership`` alone is
#: never a rule — only *chapter* membership and *dues*, which together are the
#: product concept §4 removes.
RULES: tuple[Rule, ...] = (
    Rule(
        code="ia-west",
        pattern=r"IA[-\s]West\b|\biawest\b",
        replacement="CBA",
        message=(
            "The institutional name a CBA user reads is CBA (§4). The legacy "
            "product name survives only as the `ia_west_legacy` product scope."
        ),
    ),
    Rule(
        code="insights-association",
        pattern=r"Insights\s+Association",
        replacement="CBA",
        message="§4 retires the parent-organisation name from CBA-visible copy.",
    ),
    Rule(
        code="chapter",
        pattern=r"\bchapters?\b",
        replacement="CBA (or College)",
        message=(
            "CBA has no chapters. §4 maps Chapter to CBA/College. The gated "
            "capability identifier `chapter_membership_dues` is unaffected: "
            "an underscore is a word character, so this rule cannot match it."
        ),
    ),
    Rule(
        code="chapter-admin",
        pattern=r"Chapter\s+Admin",
        replacement="Speaker Connector / Connector Dashboard",
        message=(
            "§4: Chapter Admin becomes Speaker Connector; its dashboard, Connector Dashboard."
        ),
    ),
    Rule(
        code="member-portal",
        pattern=r"Member\s+Portal",
        replacement="Student Portal",
        message="§4: Member Portal becomes Student Portal.",
    ),
    Rule(
        code="membership-dues",
        pattern=r"\bdues\b|chapter\s+members(hip)?\b",
        replacement="(removed)",
        message=(
            "§4 removes chapter membership and dues as a product concept rather "
            "than renaming them. The backend authorization `membership` record "
            "is a different thing and is not matched by this rule."
        ),
    ),
    Rule(
        code="volunteer-opportunity",
        pattern=r"volunteer\s+opportunit(y|ies)",
        replacement="Speaker Request",
        message="§4: a volunteer opportunity is a Speaker Request.",
    ),
)


@dataclass(frozen=True)
class Allow:
    """One deliberate exclusion.

    Attributes:
        path: Repository-relative path, or a ``*``-terminated prefix.
        code: Rule this exclusion covers, or ``"*"`` for every rule.
        reason: Why the term is correct here. Never optional — an
            unexplained allowlist entry defeats the gate.
    """

    path: str
    code: str
    reason: str


#: Exclusions inside the scanned scope. Everything *outside* the scope
#: (historical documents, decision records, tests, the authorization stack,
#: migrations) is excluded structurally by :data:`SCANNED_ROOTS` and is
#: documented in ``tests/unit/test_cba_terminology_strings.py``.
ALLOWLIST: tuple[Allow, ...] = (
    Allow(
        path="apps/web/legacy-frontend/src/lib/api.ts",
        code="ia-west",
        reason=(
            "`ia_west_chapter` is a value of the server's `OutreachEmailVoice` "
            "field. Changing it would change an API contract, not copy."
        ),
    ),
    Allow(
        path="apps/web/legacy-frontend/src/lib/productScope.ts",
        code="*",
        reason=(
            "The product-scope module names the legacy scope `ia_west_legacy` "
            "and the gated `chapter_membership_dues` capability verbatim. It is "
            "the policy that authorises this sweep; it cannot be swept."
        ),
    ),
)

#: Directory trees scanned in full (repository-relative).
SCANNED_ROOTS: tuple[Path, ...] = (Path("apps/web/legacy-frontend/src"),)

#: Individual backend files whose string literals reach the user verbatim.
SCANNED_FILES: tuple[Path, ...] = (
    # A registered metric's `definition` is rendered on the page that reports
    # the metric (`Opportunities.tsx` shows `summary.definition`).
    Path("python/smartmatch_domain/smartmatch_domain/metrics.py"),
)

#: Suffixes considered inside :data:`SCANNED_ROOTS`.
SCANNED_SUFFIXES: frozenset[str] = frozenset({".ts", ".tsx", ".css", ".html"})

#: Path fragments skipped inside :data:`SCANNED_ROOTS`.
SKIPPED_FRAGMENTS: tuple[str, ...] = ("__tests__", ".test.", ".spec.", "node_modules")


@dataclass(frozen=True)
class Finding:
    """One violation."""

    path: str
    line: int
    code: str
    text: str
    replacement: str
    message: str


_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?<![:\\])//[^\n]*")


def strip_ts_comments(source: str) -> str:
    """Blank out TS/CSS comments, preserving line numbering.

    Comments are engineering prose, not copy. The negative lookbehind on ``:``
    keeps ``https://`` inside a string literal from swallowing the rest of its
    line — a false *negative* is the failure mode worth avoiding here, and a
    URL scheme is the one common way ``//`` appears outside a comment.
    """

    def _blank(match: re.Match[str]) -> str:
        return "".join("\n" if char == "\n" else " " for char in match.group(0))

    return _LINE_COMMENT.sub(_blank, _BLOCK_COMMENT.sub(_blank, source))


def _is_allowed(relative: str, code: str) -> bool:
    for entry in ALLOWLIST:
        if entry.code not in (code, "*"):
            continue
        if entry.path.endswith("*"):
            if relative.startswith(entry.path[:-1]):
                return True
        elif relative == entry.path:
            return True
    return False


def scanned_paths(repo_root: Path) -> list[Path]:
    """Every file in scope, sorted, so a run is reproducible."""
    paths: list[Path] = []
    for root in SCANNED_ROOTS:
        base = repo_root / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
                continue
            relative = path.relative_to(repo_root).as_posix()
            if any(fragment in relative for fragment in SKIPPED_FRAGMENTS):
                continue
            paths.append(path)
    for named in SCANNED_FILES:
        candidate = repo_root / named
        if candidate.is_file():
            paths.append(candidate)
    return paths


def scan(repo_root: Path = REPO_ROOT) -> list[Finding]:
    """Findings across the scoped surfaces, in path order."""
    findings: list[Finding] = []
    for path in scanned_paths(repo_root):
        relative = path.relative_to(repo_root).as_posix()
        source = path.read_text(encoding="utf-8")
        searchable = source if path.suffix == ".py" else strip_ts_comments(source)
        lines = searchable.splitlines()
        for rule in RULES:
            if _is_allowed(relative, rule.code):
                continue
            for number, text in enumerate(lines, start=1):
                if rule.regex.search(text):
                    findings.append(
                        Finding(
                            path=relative,
                            line=number,
                            code=rule.code,
                            text=text,
                            replacement=rule.replacement,
                            message=rule.message,
                        )
                    )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    findings = scan(REPO_ROOT)

    if args.json:
        print(json.dumps([finding.__dict__ for finding in findings], indent=2))
    elif findings:
        print(f"{len(findings)} retired term(s) in CBA-visible copy:\n", file=sys.stderr)
        for finding in findings:
            print(f"{finding.path}:{finding.line}: [{finding.code}]", file=sys.stderr)
            print(f"    {finding.text.strip()}", file=sys.stderr)
            print(f"    use: {finding.replacement} — {finding.message}\n", file=sys.stderr)
    else:
        print(f"clean: {len(scanned_paths(REPO_ROOT))} CBA-visible file(s) scanned")

    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
