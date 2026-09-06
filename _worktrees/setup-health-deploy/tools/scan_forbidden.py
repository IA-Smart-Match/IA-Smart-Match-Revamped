#!/usr/bin/env python3
"""Forbidden-legacy-behavior scanner.

Implements §15 of the migration orchestrator contract as an executable gate.
Every pattern here corresponds to a specific defect observed in the legacy
baseline (Nebiux-Team-IA-West-SmartMatch@bdce024); the point is that the defect
cannot reappear in the target without the build failing.

A match must be explained, removed, or explicitly allowlisted with a contract
reference. The allowlist below carries a reason for every entry — an
unexplained allowlist entry defeats the gate.

Usage::

    python tools/scan_forbidden.py            # scan the repository
    python tools/scan_forbidden.py --json     # machine-readable output

Exit codes: ``0`` clean, ``1`` violations found.
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import subprocess
import sys
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Rule:
    """One forbidden pattern.

    Attributes:
        code: Stable identifier, cited by allowlist entries.
        pattern: Case-insensitive regular expression.
        message: What is wrong and why it matters.
        applies_to: Suffixes this rule applies to. Empty means all files.
    """

    code: str
    pattern: str
    message: str
    applies_to: tuple[str, ...] = ()

    @property
    def regex(self) -> re.Pattern[str]:
        return re.compile(self.pattern, re.IGNORECASE)


RULES: tuple[Rule, ...] = (
    Rule(
        code="mock-login",
        pattern=r"mock[-_]login|caller[-_]selected[-_]role|\brole\s*=\s*request\.(json|body)",
        message=(
            "Caller-selected identity. Legacy portals.py:435 let any caller choose "
            "their own role. Identity is derived server-side from a verified token."
        ),
    ),
    Rule(
        code="fabricated-score",
        pattern=r"(score|confidence|match_score)\s*=\s*(0\.\d+|[1-9]\d*)\s*(#.*)?$",
        message=(
            "Hard-coded score literal. Scores are computed from the factor registry "
            "or reported as unavailable — never invented (v1.1 §3.6 N1)."
        ),
        applies_to=(".py",),
    ),
    Rule(
        code="fabricated-meeting",
        pattern=r"(meet\.google\.com/[a-z]|zoom\.us/j/\d|teams\.microsoft\.com/l/meetup)",
        message=(
            "Hard-coded meeting URL. The legacy presented invented join links as "
            "real (v1.1 §3.6 N1)."
        ),
    ),
    Rule(
        code="local-business-persistence",
        pattern=(
            r"(to_csv|to_jsonl|\.jsonl['\"]|sqlite3\.connect|"
            r"create_engine\(\s*['\"]sqlite|\.db['\"]\s*\))"
        ),
        message=(
            "Business persistence to a local file or SQLite. PostgreSQL is the only "
            "system of record; the legacy wrote feedback to CSV/JSONL and events to "
            "demo.db."
        ),
        applies_to=(".py",),
    ),
    Rule(
        code="module-level-mutable-state",
        pattern=r"^(_?[A-Z_]*(QUEUE|STATE|CACHE|REGISTRY|STORE|BUS|RESULTS?))\s*(:[^=]+)?=\s*(\{\}|\[\]|dict\(\)|list\(\)|deque\()",
        message=(
            "Authoritative module-level mutable state. Legacy runtime_state.py and "
            "result_bus.py held job state in process memory, which is incorrect "
            "across multiple Cloud Run instances (v1.1 §2.4)."
        ),
        applies_to=(".py",),
    ),
    Rule(
        code="demo-mode-fallback",
        pattern=r"demo_mode|load_fixture\(|DEMO_MODE|if\s+demo\b",
        message=(
            "Demo-mode fallback. Serving seed content to keep a screen populated, "
            "unlabeled, is the anti-pattern v1.1 §5.5 exists to kill."
        ),
        applies_to=(".py", ".ts", ".tsx"),
    ),
    Rule(
        code="mutating-get",
        # A handler name ending in _page/_form/_confirmation/_view declares itself
        # a render, which is the corrected pattern — GET renders, POST mutates.
        # Those names are exempt; everything else with a mutation verb is flagged.
        pattern=(
            r"@(app|router)\.get\((?:.|\n){0,400}?def\s+"
            r"(?!\w+_(?:page|form|confirmation|view)\b)"
            r"\w*(?:unsubscribe|delete|remove|checkin|check_in|confirm|revoke|approve)\w*"
        ),
        message=(
            "A GET handler whose name implies mutation. GET must be safe — link "
            "scanners, prefetchers, and security proxies reach it (v1.1 §1.9, §1.10). "
            "Render from GET, mutate from a signed POST; name render handlers "
            "*_page, *_form, *_confirmation, or *_view."
        ),
        applies_to=(".py",),
    ),
    Rule(
        code="provider-call-in-request-path",
        pattern=r"@(app|router)\.(get|post|put|patch|delete)\((?:.|\n){0,600}?(resend\.|smtplib|sendgrid|\.send_email\(|genai\.|openai\.|requests\.get\(http)",
        message=(
            "A browser request handler calling a provider inline. Every "
            "consequential action is persisted as a command and dispatched through "
            "the outbox (v1.1 §1.6)."
        ),
        applies_to=(".py",),
    ),
    Rule(
        code="hard-coded-credential",
        # The optional closing quote after the key name matters: dict, JSON, and
        # YAML all write the key quoted ("api_key": "..."), which is the most
        # common way a credential actually gets committed.
        pattern=(
            r"(api[-_]?key|secret|password|token)['\"]?\s*[:=]\s*"
            r"['\"][A-Za-z0-9_\-]{16,}['\"]"
        ),
        message="Hard-coded credential. Secrets come from Secret Manager, never source.",
    ),
    Rule(
        code="legacy-import",
        pattern=r"^\s*(from|import)\s+src\.(matching|api|ui|coordinator|outreach|scraping|feedback|voice)",
        message=(
            "Direct import from a legacy source path. Ports are reimplemented "
            "against target interfaces, never wired back to the old tree."
        ),
        applies_to=(".py",),
    ),
    Rule(
        code="client-supplied-identity",
        pattern=r"(tenant_id|user_id|student_id|professional_id)\s*=\s*(payload|body|request\.json|data)\[",
        message=(
            "Identity taken from the request body. Tenant and actor are derived "
            "server-side from the verified token (v1.1 §2.2)."
        ),
        applies_to=(".py",),
    ),
    Rule(
        code="unconditional-success",
        pattern=r"return\s*\{[^}]*['\"]success['\"]\s*:\s*True[^}]*\}\s*$",
        message=(
            "Unconditional success response. Never report success when a write or "
            "provider action failed (v1.1 §3.6 N2)."
        ),
        applies_to=(".py",),
    ),
)


#: Files excluded from scanning entirely, with a reason each.
EXCLUDED_PREFIXES: tuple[tuple[str, str], ...] = (
    ("tools/scan_forbidden.py", "the scanner necessarily contains the patterns"),
    (
        "tests/unit/test_forbidden_scanner.py",
        "the scanner's self-tests feed it known-bad source on purpose; excluding "
        "them is what lets the gate be verified rather than merely trusted",
    ),
    (".venv/", "third-party dependencies are not our source"),
    ("node_modules/", "third-party dependencies are not our source"),
    ("clients/typescript/", "generated code, verified by the drift check instead"),
)

#: Specific (path, rule-code) pairs that are permitted, each with a contract
#: reference explaining why. An entry without a reason is a bug in this file.
ALLOWLIST: dict[tuple[str, str], str] = {
    (
        "docs/migration/migration-manifest.yaml",
        "mock-login",
    ): "The manifest records mock-login as ARCHIVED; naming it is the point.",
    (
        "docs/migration/rejected-components.md",
        "mock-login",
    ): "Rejection rationale must name what was rejected.",
    (
        "docs/migration/rejected-components.md",
        "demo-mode-fallback",
    ): "Rejection rationale must name what was rejected.",
    (
        "docs/migration/migration-manifest.yaml",
        "demo-mode-fallback",
    ): "The manifest records demo mode as ARCHIVED.",
    (
        "docs/architecture/review/contract-findings.md",
        "mock-login",
    ): "Findings cite the legacy defect by name.",
    (
        "tests/contract/test_api_health.py",
        "mock-login",
    ): "Asserts the archived endpoint returns 404.",
    (
        "tests/integration/test_command_path.py",
        "mock-login",
    ): "Asserts the archived endpoint returns 404 on the authenticated app too.",
    (
        "python/smartmatch_providers/smartmatch_providers/fixtures.py",
        "demo-mode-fallback",
    ): "Docstring explains why fixtures are not a demo-data source.",
    (
        "docs/security/scaffold-security-review.md",
        "mock-login",
    ): "Security review cites the archived pattern.",
    (
        "apps/web/DESIGN.md",
        "mock-login",
    ): "The design brief names the archived pattern to state that no frontend may reintroduce it.",
    (
        "docs/plans/stakeholder-audit-integration.md",
        "mock-login",
    ): "The plan records Fix #7 as the one already-closed item; naming it is the point.",
    (
        "docs/architecture/decisions/ADR-0008-globally-unique-external-subject.md",
        "mock-login",
    ): "The ADR names the archived pattern to argue why a tenant-scoped lookup revives it.",
    (
        "docs/architecture/review/stakeholder-test-log-audit.md",
        "mock-login",
    ): "The audit names the archived pattern to record Fix #7 as its one closed finding.",
}


@dataclass
class Violation:
    """One rule match that is not allowlisted."""

    path: str
    line_number: int
    rule_code: str
    message: str
    excerpt: str


@dataclass
class ScanResult:
    """The outcome of a scan."""

    violations: list[Violation] = field(default_factory=list)
    files_scanned: int = 0


def tracked_files() -> list[Path]:
    """Return the files CI would see, falling back to a filesystem walk.

    ``--cached --others --exclude-standard`` covers tracked files *and* untracked
    ones that are not gitignored. Both matter: in CI everything is committed, so
    a scan restricted to tracked files gives a different answer locally than it
    does in CI, and the difference is exactly the window in which a new file is
    written but not yet staged.

    That is not hypothetical — a design document naming an archived pattern was
    committed past a locally-clean scan because it was untracked when the scan
    ran. Gitignored files stay excluded, so build output and virtualenvs do not
    generate noise.
    """
    try:
        output = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        paths = [REPO_ROOT / line for line in output.splitlines() if line]
        if paths:
            return paths
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    return [p for p in REPO_ROOT.rglob("*") if p.is_file() and ".git" not in p.parts]


def _is_excluded(relative: str) -> bool:
    return any(relative.startswith(prefix) for prefix, _ in EXCLUDED_PREFIXES)


def strip_python_prose(source: str) -> str:
    """Blank out comments and docstrings, preserving line numbers.

    Documentation that *names* a forbidden pattern in order to explain why the
    code avoids it is not a violation — and the modules here deliberately do
    exactly that. Scanning prose produces false positives that train reviewers
    to wave the gate through, which is worse than not having it.

    Ordinary string literals are **kept**, so the hard-coded-credential rule
    still inspects them. Only comments and docstrings are removed.

    Line numbering is preserved by replacing removed spans with blank lines, so
    reported line numbers still point at the right source line.

    Args:
        source: Python source text.

    Returns:
        The source with comments and docstrings blanked. On a syntax error the
        input is returned unchanged — an unparseable file should still be
        scanned, conservatively.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    lines = source.splitlines(keepends=True)
    # 1-indexed set of line numbers to blank.
    blank: set[int] = set()

    # Docstrings: the first statement of a module, class, or function when it is
    # a bare string expression.
    doc_owners = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, doc_owners):
            continue
        body = getattr(node, "body", [])
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
            and first.end_lineno is not None
        ):
            blank.update(range(first.lineno, first.end_lineno + 1))

    # Comments, via the tokenizer.
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT:
                blank.add(token.start[0])
    except (tokenize.TokenError, IndentationError):
        pass

    out: list[str] = []
    for index, line in enumerate(lines, start=1):
        if index in blank:
            out.append("\n" if line.endswith("\n") else "")
        else:
            out.append(line)
    return "".join(out)


def scan() -> ScanResult:
    """Scan tracked files for forbidden patterns."""
    result = ScanResult()

    for path in tracked_files():
        if not path.is_file():
            continue
        relative = path.relative_to(REPO_ROOT).as_posix()
        if _is_excluded(relative):
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable; the binary-artifact check covers these

        result.files_scanned += 1
        # Comments and docstrings that name a forbidden pattern in order to
        # explain its absence are documentation, not a violation.
        searchable = strip_python_prose(text) if path.suffix == ".py" else text

        for rule in RULES:
            if rule.applies_to and path.suffix not in rule.applies_to:
                continue
            if (relative, rule.code) in ALLOWLIST:
                continue

            for match in rule.regex.finditer(searchable):
                line_number = searchable.count("\n", 0, match.start()) + 1
                excerpt = text.splitlines()[line_number - 1].strip()
                result.violations.append(
                    Violation(
                        path=relative,
                        line_number=line_number,
                        rule_code=rule.code,
                        message=rule.message,
                        excerpt=excerpt[:160],
                    )
                )

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    result = scan()

    if args.json:
        print(
            json.dumps(
                {
                    "files_scanned": result.files_scanned,
                    "violations": [v.__dict__ for v in result.violations],
                },
                indent=2,
            )
        )
    elif result.violations:
        print(f"Forbidden legacy behavior found ({len(result.violations)}):\n")
        for v in result.violations:
            print(f"  {v.path}:{v.line_number}  [{v.rule_code}]")
            print(f"    {v.excerpt}")
            print(f"    -> {v.message}\n")
    else:
        print(f"Forbidden-behavior scan clean ({result.files_scanned} files).")

    return 1 if result.violations else 0


if __name__ == "__main__":
    sys.exit(main())
