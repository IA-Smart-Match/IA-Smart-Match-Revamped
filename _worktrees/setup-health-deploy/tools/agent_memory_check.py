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

import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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

#: Fields whose value must be a single scalar, and fields that must be a list.
#: Front matter turns an empty value into a list, so every field can arrive as
#: either type. Checking this centrally is the fix for a whole class of
#: fail-open bugs: each individual rule below guarded with `isinstance(x, str)`
#: and, on a list, simply did not fire.
LIST_FIELDS = frozenset({"sources", "conflicts_with"})
SCALAR_FIELDS = REQUIRED_FIELDS - LIST_FIELDS

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

    for name in sorted(SCALAR_FIELDS & set(fields)):
        if not isinstance(fields[name], str):
            findings.append(
                Finding(
                    path,
                    "bad-field-type",
                    f"{name!r} must be a single value; it parsed as "
                    f"{type(fields[name]).__name__}, which every rule below would "
                    "then skip rather than reject",
                )
            )
    for name in sorted(LIST_FIELDS & set(fields)):
        if not isinstance(fields[name], list):
            findings.append(
                Finding(
                    path,
                    "bad-field-type",
                    f"{name!r} must be a list of '- item' lines; it parsed as "
                    f"{type(fields[name]).__name__}",
                )
            )

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


def _blob_belonged_to(repo_root: Path, path: str, sha: str) -> bool:
    """Whether ``sha`` was ever the blob at ``path`` in reachable history.

    ``cat-file -e`` would only prove the object exists somewhere, which is not
    provenance: any blob in the database would satisfy it, so a record could
    cite a real object under a path it never belonged to. Walking the commits
    that touched the path is the check that actually binds the two.

    Only historical records reach this, and only for paths they cite, so the
    walk is bounded by that path's own history.
    """
    commits = _git(repo_root, "rev-list", "--all", "--", path)
    if not commits:
        return False
    for commit in commits.splitlines():
        found = _git(repo_root, "rev-parse", f"{commit}:{path}")
        if found == sha:
            return True
    return False


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

    # Freshness applies only to records still claiming to be current. A
    # superseded, revoked or already-stale record is history: the README tells a
    # maintainer to supersede a record whose source moved, and if superseding
    # still failed the gate that remedy would not work. Format rules below still
    # apply to every status — "repository files only" is never suspended.
    # Stated as an exemption list rather than an allow-list on purpose: a record
    # with a missing or unrecognised status is still checked. Defaulting the
    # other way would let a malformed record escape the staleness rule silently,
    # which is the failure this gate exists to prevent.
    status = fields.get("status")
    check_freshness = not (isinstance(status, str) and status in {"superseded", "revoked", "stale"})

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

        if not _SHA.fullmatch(recorded):
            findings.append(
                Finding(
                    path,
                    "bad-source-sha",
                    f"source {source_path!r} cites {recorded!r}, which is not a git object name",
                )
            )
            continue

        if not check_freshness:
            # A historical record is exempt from comparison with HEAD, not from
            # citing something real. Without this the ledger could carry
            # fabricated provenance that nothing would ever check.
            if not _blob_belonged_to(repo_root, source_path, recorded):
                findings.append(
                    Finding(
                        path,
                        "unknown-source-blob",
                        f"source {source_path!r} cites blob {recorded[:12]}, which "
                        "never existed at that path in this repository's history",
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
    re.compile(
        r"\bignore (all |any |your )?(previous|prior|earlier|standing|above)\b",
        re.IGNORECASE,
    ),
    # Unqualified: descriptive prose about a codebase essentially never asks the
    # reader to disregard something, whereas an injection almost always does.
    re.compile(r"\bdisregard\b", re.IGNORECASE),
    re.compile(r"\bforget (everything|all|the|what|any)\b", re.IGNORECASE),
    re.compile(
        r"\boverride\b[^.]{0,40}\b(constraint|rule|instruction|guidance|order)s?\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bstanding orders\b", re.IGNORECASE),
    re.compile(r"\byou (must|should|shall) always\b", re.IGNORECASE),
    re.compile(r"\byou (must|should|shall) never\b", re.IGNORECASE),
    re.compile(r"\balways (skip|bypass|disable|ignore)\b", re.IGNORECASE),
    re.compile(r"\bsystem prompt\b", re.IGNORECASE),
)


def _instruction_findings(text: str, *, path: str) -> list[Finding]:
    """Instruction-shaped matches in any agent-consumed text."""
    findings: list[Finding] = []
    for pattern in INSTRUCTION_PATTERNS:
        match = pattern.search(text)
        if match:
            findings.append(
                Finding(
                    path,
                    "instruction-shaped",
                    f"contains instruction-shaped text {match.group(0)!r}. "
                    "Records describe; they do not direct.",
                )
            )
    return findings


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
    findings.extend(_instruction_findings(body, path=path))
    return findings


def body_hash(body: str) -> str:
    """The canonical content hash for a record body.

    Computed over the stripped body so that trailing-whitespace churn does not
    invalidate a record, and prefixed so the algorithm is visible in the file.
    """
    digest = hashlib.sha256(body.strip().encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def validate_content_hash(
    fields: dict[str, str | list[str]], body: str, *, path: str
) -> list[Finding]:
    """The recorded hash must match the body it was approved against.

    Without this the field is decoration. With it, a body edited after approval
    is caught by the gate rather than by whoever later trusts the record.
    """
    recorded = fields.get("content_hash")
    if not isinstance(recorded, str) or not recorded or recorded == "null":
        return [
            Finding(
                path,
                "missing-content-hash",
                f"content_hash is unset; it should be {body_hash(body)}",
            )
        ]
    expected = body_hash(body)
    if recorded != expected:
        return [
            Finding(
                path,
                "content-hash-mismatch",
                f"content_hash records {recorded[:19]}... but the body hashes to "
                f"{expected[:19]}.... The body changed after approval; re-review "
                "it rather than updating the hash alone.",
            )
        ]
    return []


MAX_RESEARCH_DAYS = 30

#: A full git object name. Abbreviations are refused rather than accepted and
#: then compared by equality, which would report a valid short prefix as stale.
_SHA = re.compile(r"[0-9a-f]{40}")

CONFIG_FILE = ".agent-memory.yaml"

CONFIG_KEYS = frozenset({"project_id", "repository_id", "policy_version"})

#: Bump when the record schema changes incompatibly.
SUPPORTED_POLICY_VERSIONS = frozenset({"1"})


def validate_config(config: dict[str, str]) -> list[Finding]:
    """The config is a three-key contract, and is held to it.

    A loader that accepts anything shaped like a mapping lets a policy version
    the validator does not implement pass as though it were supported.
    """
    findings: list[Finding] = []
    for missing in sorted(CONFIG_KEYS - set(config)):
        findings.append(Finding(CONFIG_FILE, "config-incomplete", f"{missing!r} is absent"))
    for unknown in sorted(set(config) - CONFIG_KEYS):
        findings.append(Finding(CONFIG_FILE, "config-unknown-key", f"unrecognised key {unknown!r}"))
    version = config.get("policy_version")
    if version is not None and version not in SUPPORTED_POLICY_VERSIONS:
        findings.append(
            Finding(
                CONFIG_FILE,
                "unsupported-policy-version",
                f"policy_version {version!r} is not one of "
                f"{sorted(SUPPORTED_POLICY_VERSIONS)}; this validator does not "
                "implement it",
            )
        )
    return findings


def load_config(repo_root: Path) -> tuple[dict[str, str], list[Finding]]:
    """Read ``.agent-memory.yaml``.

    A three-key flat file, read by the same stdlib-only rule as the records —
    see this module's docstring. Comments and blank lines are skipped.
    """
    config_path = repo_root / CONFIG_FILE
    if not config_path.is_file():
        return {}, []
    return parse_config_lines(config_path.read_text(encoding="utf-8").splitlines())


def parse_config_lines(lines: list[str]) -> tuple[dict[str, str], list[Finding]]:
    """Parse config lines, reporting what it could not use.

    Separated from file access so the parse rules can be tested directly.
    """
    config: dict[str, str] = {}
    findings: list[Finding] = []
    for number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Reported rather than skipped. A silently discarded line is how a typo
        # — or an unresolved merge conflict marker — leaves a config that still
        # reduces to the expected three keys and passes validation.
        if ":" not in stripped:
            findings.append(
                Finding(
                    CONFIG_FILE,
                    "config-malformed",
                    f"line {number} is not 'key: value': {stripped!r}",
                )
            )
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        if key in config:
            findings.append(
                Finding(CONFIG_FILE, "config-duplicate-key", f"line {number}: {key!r} again")
            )
            continue
        config[key] = value.strip()
    return config, findings


def validate_identity(
    fields: dict[str, str | list[str]], *, path: str, config: dict[str, str]
) -> list[Finding]:
    """Every record must belong to this repository.

    Presence of the field is not enough: a record copied from elsewhere carries
    a well-formed identity that is not this one, and the whole point of minting
    ``repository_id`` once is that it answers "which repository" independently
    of the remote URL.
    """
    findings: list[Finding] = []
    for key in ("project_id", "repository_id"):
        expected = config.get(key)
        actual = fields.get(key)
        # Every branch below reports. A missing config key or a record field
        # that parsed as anything but a non-empty string must not silently skip
        # the comparison — that would let precisely the copied record this check
        # exists to catch through the gate.
        if not expected:
            findings.append(
                Finding(
                    path,
                    "identity-unverifiable",
                    f"{CONFIG_FILE} declares no {key}, so record identity cannot be checked",
                )
            )
            continue
        if not isinstance(actual, str) or not actual:
            findings.append(Finding(path, "identity-mismatch", f"{key} is absent or empty"))
            continue
        if actual != expected:
            findings.append(
                Finding(
                    path,
                    "identity-mismatch",
                    f"{key} is {actual!r} but {CONFIG_FILE} declares {expected!r}",
                )
            )
    return findings


def validate_claim(fields: dict[str, str | list[str]], *, path: str) -> list[Finding]:
    """The claim is agent-consumed content, and is held to the same rule as the body.

    A record whose body is impeccable and whose claim carries an injection
    phrase is the obvious way around a body-only check.
    """
    claim = fields.get("claim")
    if not isinstance(claim, str) or not claim.strip():
        return [
            Finding(
                path,
                "bad-claim",
                "claim must be a single non-empty line of text; a list-valued "
                "claim would bypass the instruction scan",
            )
        ]
    return [
        Finding(finding.path, finding.code, f"claim: {finding.message}")
        for finding in _instruction_findings(claim, path=path)
    ]


def _parse_timestamp(value: object) -> datetime | None:
    """Parse an ISO-8601 timestamp, accepting a trailing ``Z``."""
    if not isinstance(value, str) or not value or value == "null":
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # A naive timestamp is rejected rather than assumed to be UTC. Comparing a
    # naive and an aware datetime raises TypeError, which would crash the whole
    # gate on one malformed record instead of reporting it.
    return parsed if parsed.tzinfo is not None else None


def validate_expiry(
    fields: dict[str, str | list[str]], *, path: str, now: datetime | None = None
) -> list[Finding]:
    """External research expires after 30 days, and the window is enforced.

    Checking only for a non-null value would let ``never`` or a date years out
    satisfy a freshness rule the policy states in days.
    """
    authority = fields.get("authority")
    expires_raw = fields.get("expires_at")

    if authority != "external-research":
        # observation and convention live until superseded or stale, and the
        # schema says so with an explicit null. Accepting anything else here
        # would let a record carry an expiry nothing ever acts on.
        if not (expires_raw == "null" or expires_raw == [] or expires_raw is None):
            return [
                Finding(
                    path,
                    "unexpected-expiry",
                    f"authority {authority!r} requires 'expires_at: null'; this "
                    f"record sets {expires_raw!r}",
                )
            ]
        return []

    # Only the *wall-clock* check below is exempt for historical records. The
    # static rules — parseable timestamps, correct ordering, a window within the
    # policy — describe the record's own metadata and stay true forever.
    status = fields.get("status")
    is_historical = isinstance(status, str) and status in {
        "superseded",
        "revoked",
        "stale",
    }

    approved = _parse_timestamp(fields.get("approved_at"))
    expires = _parse_timestamp(fields.get("expires_at"))
    if expires is None:
        return [
            Finding(
                path,
                "bad-expiry",
                f"expires_at {fields.get('expires_at')!r} is not an ISO-8601 timestamp",
            )
        ]
    if approved is None:
        return [
            Finding(
                path,
                "bad-expiry",
                f"approved_at {fields.get('approved_at')!r} is not an ISO-8601 timestamp",
            )
        ]
    if expires <= approved:
        return [Finding(path, "bad-expiry", "expires_at is not after approved_at")]
    if expires - approved > timedelta(days=MAX_RESEARCH_DAYS):
        return [
            Finding(
                path,
                "expiry-too-far",
                f"external research expires after {MAX_RESEARCH_DAYS} days; this "
                f"record claims {(expires - approved).days}",
            )
        ]
    if is_historical:
        return []

    moment = now or datetime.now(UTC)
    if approved > moment:
        return [
            Finding(
                path,
                "bad-expiry",
                f"approved_at {approved.date().isoformat()} is in the future; a "
                "future approval would slide the 30-day window forward "
                "indefinitely",
            )
        ]
    if expires < moment:
        return [
            Finding(
                path,
                "expired",
                f"expired on {expires.date().isoformat()}; re-verify the research "
                "and re-approve it, or remove the record",
            )
        ]
    return []


def validate_ledger(repo_root: Path) -> list[Finding]:
    """Validate every record in the ledger, in path order."""
    ledger = repo_root / LEDGER_DIR
    if not ledger.is_dir():
        return []

    records = sorted(ledger.glob("*.md"))
    config, config_findings = load_config(repo_root)
    findings: list[Finding] = list(config_findings)

    if not config:
        findings.append(
            Finding(
                CONFIG_FILE,
                "missing-config",
                f"{CONFIG_FILE} is absent; record identity cannot be checked",
            )
        )
    else:
        findings.extend(validate_config(config))

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
        # Reading is inside the guard: a single undecodable byte would otherwise
        # raise UnicodeDecodeError out of the whole run, so one malformed record
        # would suppress every finding in the ledger rather than adding one.
        try:
            text = record.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as error:
            findings.append(Finding(relative, "unreadable", str(error)))
            continue
        try:
            fields, body = parse_front_matter(text)
        except FrontMatterError as error:
            findings.append(Finding(relative, "unparseable", str(error)))
            continue
        findings.extend(validate_fields(fields, path=relative))
        findings.extend(validate_sources(fields, path=relative, repo_root=repo_root))
        findings.extend(validate_body(body, path=relative))
        findings.extend(validate_content_hash(fields, body, path=relative))
        findings.extend(validate_identity(fields, path=relative, config=config))
        findings.extend(validate_claim(fields, path=relative))
        findings.extend(validate_expiry(fields, path=relative))

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
