"""Validate the approved agent-memory ledger.

Memory records are committed Markdown with flat front matter. This script is the
gate that keeps them honest: it rejects malformed or unknown fields, and verifies
that the git blobs a record cites still match the ones it was approved against.

Stdlib only, deliberately. PyYAML appears in ``requirements/*.txt`` only as a
transitive dependency of ``uvicorn[standard]`` and is declared in no ``.in``
file, and a gate that runs on every ``make check`` must not rest on a package
nothing declares. The flat grammar this parser accepts is also narrower than
YAML on purpose: no implicit type coercion, no anchors, no tags, in a format
that carries security-relevant fields.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_FENCE = "---"

REQUIRED_FIELDS = frozenset(
    {
        "schema",
        "entry_id",
        "project_id",
        "repository_id",
        "status",
        "authority",
        "privacy_class",
        "claim",
        "sources",
        "produced_by_tool",
        "produced_by_session",
        "produced_by_commit",
        "reviewed_by",
        "approved_at",
        "expires_at",
        "supersedes",
        "superseded_by",
        "conflicts_with",
        "content_hash",
    }
)

STATUSES = frozenset({"approved", "superseded", "revoked", "stale"})

#: ``decision`` is deliberately absent. Architectural decisions are ADRs; a
#: memory record that believed itself to be one would create a second,
#: unreviewed decision store competing with docs/architecture/decisions/.
AUTHORITIES = frozenset({"observation", "convention", "external-research"})

#: The only class permitted in approved/. Anything else is not committed at all.
PRIVACY_CLASSES = frozenset({"repo-public"})


class FrontMatterError(Exception):
    """The record's front matter could not be parsed at all."""


@dataclass(frozen=True)
class Finding:
    """One problem with one record."""

    path: str
    code: str
    message: str


def parse_front_matter(text: str) -> tuple[dict[str, str | list[str]], str]:
    """Split a record into its front-matter fields and its prose body.

    A key with an empty value opens a list; the ``- item`` lines that follow
    become its entries, and a key with neither value nor items is an empty list.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FENCE:
        raise FrontMatterError("record does not open with '---'")

    closing = None
    for index in range(1, len(lines)):
        if lines[index].strip() == _FENCE:
            closing = index
            break
    if closing is None:
        raise FrontMatterError("front matter is never closed with '---'")

    fields: dict[str, str | list[str]] = {}
    current: str | None = None
    for raw in lines[1:closing]:
        if not raw.strip():
            continue
        stripped = raw.lstrip()
        if stripped.startswith("- "):
            if current is None:
                raise FrontMatterError(f"list item before any key: {raw!r}")
            existing = fields[current]
            if not isinstance(existing, list):
                raise FrontMatterError(f"{current!r} has both a scalar value and list items")
            existing.append(stripped[2:].strip())
            continue
        if raw[:1].isspace():
            raise FrontMatterError(f"nested mappings are not supported; flatten the key: {raw!r}")
        if ":" not in raw:
            raise FrontMatterError(f"line is not 'key: value': {raw!r}")
        key, _, value = raw.partition(":")
        key = key.strip()
        if key in fields:
            raise FrontMatterError(f"duplicate key: {key!r}")
        value = value.strip()
        fields[key] = value if value else []
        current = key

    body = "\n".join(lines[closing + 1 :]).strip()
    return fields, body


def validate_fields(fields: dict[str, str | list[str]], *, path: str) -> list[Finding]:
    """Check the field set against the schema. Does not touch the filesystem."""
    findings: list[Finding] = []

    for missing in sorted(REQUIRED_FIELDS - set(fields)):
        findings.append(Finding(path, "missing-field", f"required field {missing!r} is absent"))
    for unknown in sorted(set(fields) - REQUIRED_FIELDS):
        findings.append(Finding(path, "unknown-field", f"unrecognised field {unknown!r}"))

    status = fields.get("status")
    if isinstance(status, str) and status not in STATUSES:
        findings.append(
            Finding(
                path,
                "bad-status",
                f"status {status!r} is not one of {sorted(STATUSES)}",
            )
        )

    authority = fields.get("authority")
    if isinstance(authority, str) and authority not in AUTHORITIES:
        findings.append(
            Finding(
                path,
                "bad-authority",
                f"authority {authority!r} is not one of {sorted(AUTHORITIES)}. "
                "Decisions are ADRs, not memory records.",
            )
        )

    privacy = fields.get("privacy_class")
    if isinstance(privacy, str) and privacy not in PRIVACY_CLASSES:
        findings.append(
            Finding(
                path,
                "bad-privacy-class",
                f"privacy_class {privacy!r} may not be committed to approved/",
            )
        )

    expires = fields.get("expires_at")
    if authority == "external-research" and (not expires or expires == "null"):
        findings.append(
            Finding(
                path,
                "missing-expiry",
                "authority 'external-research' requires a non-null expires_at",
            )
        )

    sources = fields.get("sources")
    if isinstance(sources, list) and not sources:
        findings.append(
            Finding(
                path,
                "no-sources",
                "a record must cite at least one repository path; a claim with "
                "no source cannot be checked for staleness",
            )
        )

    return findings


def parse_source(entry: str) -> tuple[str, str]:
    """Split a ``path@blob_sha`` source entry.

    Split on the last ``@`` so a path containing one is still handled.
    """
    path, separator, sha = entry.rpartition("@")
    if not separator or not path.strip() or not sha.strip():
        raise FrontMatterError(f"source {entry!r} is not in 'path@blob_sha' form")
    return path.strip(), sha.strip()


def _git(repo_root: Path, *args: str) -> str | None:
    """Run a git plumbing command, returning stripped stdout or None."""
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def blob_sha(repo_root: Path, path: str) -> str | None:
    """The blob SHA git currently records for ``path`` at HEAD, or None."""
    output = _git(repo_root, "rev-parse", f"HEAD:{path}")
    return output or None


def is_dirty(repo_root: Path, path: str) -> bool:
    """Whether ``path`` differs from HEAD in the worktree or the index."""
    output = _git(repo_root, "status", "--porcelain", "--", path)
    return bool(output)


def validate_sources(
    fields: dict[str, str | list[str]], *, path: str, repo_root: Path
) -> list[Finding]:
    """Check every cited source exists, is in-repo, and is unchanged.

    A record whose source blob has moved is *stale*, not merely out of date: the
    claim was verified against content that no longer exists at that path, and
    nobody has confirmed it still holds. A record citing a path with uncommitted
    changes is unverifiable by anyone else, which is the same problem arriving
    earlier.
    """
    findings: list[Finding] = []
    sources = fields.get("sources")
    if not isinstance(sources, list):
        return findings

    for entry in sources:
        try:
            source_path, recorded = parse_source(entry)
        except FrontMatterError as error:
            findings.append(Finding(path, "bad-source", str(error)))
            continue

        if (
            source_path.startswith("/")
            or source_path.startswith("~")
            or "://" in source_path
            or ".." in Path(source_path).parts
        ):
            findings.append(
                Finding(
                    path,
                    "non-repo-source",
                    f"source {source_path!r} is not a repository-relative path. "
                    "Records point at repository files and nothing else.",
                )
            )
            continue

        current = blob_sha(repo_root, source_path)
        if current is None:
            findings.append(
                Finding(
                    path,
                    "source-missing",
                    f"source {source_path!r} is not tracked at HEAD",
                )
            )
            continue

        if is_dirty(repo_root, source_path):
            findings.append(
                Finding(
                    path,
                    "dirty-source",
                    f"source {source_path!r} has uncommitted changes; the claim "
                    "cannot be verified by anyone else",
                )
            )
            continue

        if current != recorded:
            findings.append(
                Finding(
                    path,
                    "stale-source",
                    f"source {source_path!r} is now blob {current[:12]} but the "
                    f"record was approved against {recorded[:12]}. Re-verify the "
                    "claim and update the record, or mark it superseded.",
                )
            )

    return findings


MAX_RECORDS = 50
MAX_BODY_CHARS = 4000

LEDGER_DIR = "docs/agent-memory/approved"

#: A record's body is read as context by every future agent session. Anything
#: shaped like an instruction is an injection vector, so the format is
#: descriptive prose about repository files and nothing else.
INSTRUCTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bignore (all |any )?previous\b", re.IGNORECASE),
    re.compile(r"\bdisregard (all |any )?(previous|prior|earlier)\b", re.IGNORECASE),
    re.compile(r"\byou (must|should|shall) always\b", re.IGNORECASE),
    re.compile(r"\byou (must|should|shall) never\b", re.IGNORECASE),
    re.compile(r"\balways (skip|bypass|disable|ignore)\b", re.IGNORECASE),
    re.compile(r"\bsystem prompt\b", re.IGNORECASE),
)


def validate_body(body: str, *, path: str) -> list[Finding]:
    """Check the prose body for length and for instruction-shaped language."""
    findings: list[Finding] = []

    if not body.strip():
        findings.append(Finding(path, "empty-body", "a record with no body states nothing"))
    if len(body) > MAX_BODY_CHARS:
        findings.append(
            Finding(
                path,
                "body-too-long",
                f"body is {len(body)} characters; the cap is {MAX_BODY_CHARS}. "
                "Records are signposts, not copies.",
            )
        )
    for pattern in INSTRUCTION_PATTERNS:
        match = pattern.search(body)
        if match:
            findings.append(
                Finding(
                    path,
                    "instruction-shaped",
                    f"body contains instruction-shaped text {match.group(0)!r}. "
                    "Records describe; they do not direct.",
                )
            )
    return findings


def validate_ledger(repo_root: Path) -> list[Finding]:
    """Validate every record in the ledger, in path order."""
    ledger = repo_root / LEDGER_DIR
    if not ledger.is_dir():
        return []

    records = sorted(ledger.glob("*.md"))
    findings: list[Finding] = []

    if len(records) > MAX_RECORDS:
        findings.append(
            Finding(
                LEDGER_DIR,
                "too-many-records",
                f"{len(records)} records; the cap is {MAX_RECORDS}. Reaching it "
                "is the signal to supersede or delete, not to raise the cap.",
            )
        )

    for record in records:
        relative = record.relative_to(repo_root).as_posix()
        text = record.read_text(encoding="utf-8")
        try:
            fields, body = parse_front_matter(text)
        except FrontMatterError as error:
            findings.append(Finding(relative, "unparseable", str(error)))
            continue
        findings.extend(validate_fields(fields, path=relative))
        findings.extend(validate_sources(fields, path=relative, repo_root=repo_root))
        findings.extend(validate_body(body, path=relative))

    return findings


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    ledger = repo_root / LEDGER_DIR
    findings = validate_ledger(repo_root)
    if not findings:
        count = len(sorted(ledger.glob("*.md"))) if ledger.is_dir() else 0
        print(f"Agent-memory ledger clean ({count} records).")
        return 0

    print(f"Agent-memory ledger problems found ({len(findings)}):\n")
    for finding in findings:
        print(f"  {finding.path}  [{finding.code}]")
        print(f"    -> {finding.message}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
