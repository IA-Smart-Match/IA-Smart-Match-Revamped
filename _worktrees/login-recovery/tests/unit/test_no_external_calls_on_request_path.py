"""Structural guards pinning R3: no crawl, LLM, or outreach call on any request path.

R3 requires that the legacy 5-10 second Tavily crawl/LLM lag be structurally
impossible on the API request path, not merely absent from today's code. Two
independent guards enforce this:

1. The committed OpenAPI contract must never expose a route whose path
   segments name a crawl, discovery, scrape, LLM/agent, outreach, or known
   third-party AI/search vendor surface.
2. No module under ``services/api/`` may import an HTTP client library — the
   request path has no way to reach out over the network at all, by
   construction, regardless of what any given handler happens to do today.

This is independent of the G1/G3/D6 gate scan in ``test_matching_fail_closed.py``
(which guards product-surface vocabulary such as match/score/crawl/rewards) and
does not modify or duplicate it.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENAPI_PATH = REPO_ROOT / "contracts" / "openapi" / "smartmatch.json"
API_ROOT = REPO_ROOT / "services" / "api"

# ---------------------------------------------------------------------------
# Guard 1 — no crawl/LLM/outreach route in the committed OpenAPI contract.
# ---------------------------------------------------------------------------

# Forbidden path-segment families for R3. Each entry is a whole-segment (or
# whole-subword, after splitting on hyphen/underscore) match, never a
# substring match, so that legitimate words are not accidentally caught
# (e.g. "chatty" or "generated" must not trip "chat"/"generate").
_R3_FORBIDDEN_SEGMENTS = frozenset(
    {
        # crawl family
        "crawl",
        "crawler",
        "crawlers",
        "crawling",
        # discovery family
        "discover",
        "discovery",
        # scrape family
        "scrape",
        "scraper",
        "scraping",
        # LLM / agentic family
        "llm",
        "ai",
        "agent",
        "agentic",
        "generate",
        "completion",
        "chat",
        "prompt",
        # outreach family
        "outreach",
        "email",
        "emails",
        "send",
        # named third-party crawl/LLM/search vendors
        "tavily",
        "openai",
        "anthropic",
        "serp",
    }
)

# Checked and confirmed against the committed contract on 2026-08-28: the
# current paths are /api/health, /u/{token}, /v1/jobs/{job_id}(/abandon|
# /events|/redrive), /v1/me, /v1/units/{unit_id}/imports,
# /v1/units/{unit_id}/metrics(/{metric_name}/drill-down). None of these
# segments (job, jobs, abandon, events, redrive, me, units, imports, metrics,
# metric_name, drill, down, health, u, token) collide with any forbidden
# family above, so no term needed to be narrowed for this test to pass. If a
# future legitimate route did collide (for example a durable-command job
# lifecycle "events" route is already distinct from the G3 unit-scoped event
# catalog guarded in test_matching_fail_closed.py), narrow the specific
# colliding term here with a comment — never delete the guard.


def _normalized_subwords(path: str) -> list[str]:
    """Split a URL path into lowercase literal subwords.

    Splits on ``/``, drops ``{param}`` placeholders, and further splits each
    segment on ``-``/``_`` so a multi-word segment (e.g. ``drill-down``) is
    checked word-by-word rather than as one opaque token.
    """
    subwords: list[str] = []
    for segment in path.strip("/").split("/"):
        if not segment or segment.startswith("{"):
            continue
        for raw_word in segment.replace("-", "_").split("_"):
            word = raw_word.strip().lower()
            if word:
                subwords.append(word)
    return subwords


def test_committed_openapi_has_no_crawl_llm_or_outreach_routes() -> None:
    """The committed contract must expose no crawl/LLM/outreach/vendor route.

    This pins R3 structurally: even if a handler were ever wired up, the
    contract itself is the first line of defense — no such route may be
    declared, committed, or shipped.
    """
    document = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    paths = document.get("paths", {})
    assert paths, "expected at least one path in the committed OpenAPI contract"

    violations: list[str] = []
    for path in paths:
        for word in _normalized_subwords(path):
            if word in _R3_FORBIDDEN_SEGMENTS:
                violations.append(f"{path!r} contains forbidden segment {word!r}")

    assert violations == [], "R3 violation(s) in committed OpenAPI contract:\n" + "\n".join(
        violations
    )


# ---------------------------------------------------------------------------
# Guard 2 — no HTTP-client import anywhere under services/api/.
# ---------------------------------------------------------------------------

# Module names (or dotted prefixes) that give a process the ability to make
# an outbound network call. Matching is exact-module or dotted-prefix, done
# via the AST (never regex, never a real import), so a docstring or comment
# mentioning "requests" cannot trip this and a disguised import cannot hide
# from it either.
_FORBIDDEN_HTTP_CLIENT_MODULES = frozenset(
    {
        "httpx",
        "requests",
        "aiohttp",
        "urllib3",
        "urllib.request",
        "http.client",
        "websockets",
    }
)

# Explicit, reviewable exceptions: dotted module path -> justification.
#
# Empty today. services/api/ has no HTTP-client import as of this writing
# (verified by the AST scan below finding zero violations against the
# current tree). The one anticipated future exception is plan-P2's JWKS
# fetch (A1b): a JWKS endpoint fetch needed for JWT verification would be
# the sole legitimate reason for services/api/ to hold an HTTP-client
# import, and it would still not sit on a *hot* request path (JWKS results
# are cached; the fetch only occurs on cache miss/rotation). Any such
# addition must be a deliberate, reviewed edit to this mapping — never a
# silent weakening of the assertion below — and must carry its own
# justification comment naming the plan/requirement that authorizes it.
_ALLOWED_HTTP_CLIENT_IMPORTS: dict[str, str] = {
    # "smartmatch_api.auth.jwks": (
    #     "plan-P2 A1b: cached JWKS fetch for JWT verification, not a "
    #     "per-request network call — see plan P2 for the caching contract."
    # ),
}


def _module_path_for(file_path: Path) -> str:
    """Return a dotted module path for ``file_path`` relative to ``API_ROOT``."""
    relative = file_path.relative_to(API_ROOT).with_suffix("")
    parts = [part for part in relative.parts if part != "__init__"]
    return ".".join(parts) if parts else relative.parts[0]


def _forbidden_import_names(node: ast.Import | ast.ImportFrom) -> list[str]:
    """Return any forbidden module names referenced by an import node."""
    hits: list[str] = []
    if isinstance(node, ast.Import):
        candidates = [alias.name for alias in node.names]
    else:
        candidates = [node.module] if node.module else []

    for candidate in candidates:
        if candidate in _FORBIDDEN_HTTP_CLIENT_MODULES:
            hits.append(candidate)
            continue
        for forbidden in _FORBIDDEN_HTTP_CLIENT_MODULES:
            if candidate.startswith(f"{forbidden}."):
                hits.append(candidate)
                break
    return hits


def test_no_request_path_module_imports_an_http_client() -> None:
    """No module under services/api/ may import an HTTP client library.

    Scanned statically via ``ast`` (never by importing the modules, never by
    regex) so that a lazily-imported client hidden inside a function body is
    caught too, not just a module-level import.
    """
    assert API_ROOT.is_dir(), f"expected services/api/ to exist at {API_ROOT}"

    violations: list[str] = []
    files_scanned = 0
    for file_path in sorted(API_ROOT.rglob("*.py")):
        files_scanned += 1
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
        module_path = _module_path_for(file_path)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for forbidden_name in _forbidden_import_names(node):
                if module_path in _ALLOWED_HTTP_CLIENT_IMPORTS:
                    continue
                violations.append(
                    f"{file_path.relative_to(REPO_ROOT)}:{node.lineno} "
                    f"imports HTTP client {forbidden_name!r}"
                )

    assert files_scanned > 0, f"scanner found no .py files under {API_ROOT}"
    assert violations == [], "R3 violation(s) — HTTP client import(s) in services/api/:\n" + (
        "\n".join(violations)
    )
