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
        #
        # NARROWED for R4/G4 (plan card L7,
        # `docs/plans/2026-09-04-r4-outreach-g4-implementation-plan.md`). This
        # guard was never about outreach being forbidden — it is about the
        # *request path* reaching a provider, which is the R3 lag defect. G4
        # closed, the outreach routes shipped, and they submit a durable command
        # rather than sending anything, so the segments they use are removed
        # here and the guard's real subject is untouched.
        #
        # Removed: "outreach" (four routes), "send" (the command-submission
        # route `.../drafts/{draft_id}/send`), "email" and "emails" (no route
        # uses them today, dropped with the family so a later `/outreach/emails`
        # read does not have to reopen this discussion).
        #
        # What still holds, and is what actually pins R3: Guard 2 below, which
        # forbids every module under `services/api/` from importing an HTTP
        # client at all. A synchronous send from a route is not merely absent
        # from the contract — it has nothing to send *with*. The crawl, LLM, and
        # vendor families below are unchanged.
        # named third-party crawl/LLM/search vendors
        "tavily",
        "openai",
        "anthropic",
        "serp",
    }
)

# Re-checked against the committed contract on 2026-09-04. The outreach family
# above is the first term this guard has had to narrow, and it was narrowed the
# way the original note asked for — the specific colliding terms, with a comment
# naming the plan card that authorized it, and nothing deleted. Every other
# family is intact and no current path collides with one.
#
# The rule for the next person stands unchanged: if a future legitimate route
# collides, narrow the specific colliding term here with a comment. Never delete
# the guard, and never narrow a term because a route you are adding happens to
# be named awkwardly — the question to answer first is whether the route
# genuinely does no provider work on the request path.


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


# ---------------------------------------------------------------------------
# Guard 3 — the CBA product scope names external acquisition as out of scope.
# ---------------------------------------------------------------------------
#
# Guards 1 and 2 are structural: no such route is declared, and no request-path
# module can reach the network. This third guard is the *product* statement
# behind them — customer §20 puts finding speakers on the internet, scraping
# LinkedIn, scraping other external sources, automatic external event
# discovery, and cold outreach to unknown contacts out of scope for this phase.
#
# It belongs beside guards 1 and 2 rather than only in the scope-policy test
# file: if a later change ever re-enables the capability, the person reading
# *this* file needs to see it, because these guards are what would otherwise
# have to be narrowed to let such a route exist.


def test_cba_scope_disables_external_acquisition_capabilities() -> None:
    """Customer §20: external acquisition and cold outreach are out of scope."""
    from smartmatch_domain.product_scope import (
        DEFAULT_PRODUCT_SCOPE,
        Capability,
        is_capability_enabled,
    )

    for capability in (
        Capability.EXTERNAL_SPEAKER_ACQUISITION,
        Capability.COLD_UNKNOWN_CONTACT_OUTREACH,
    ):
        assert not is_capability_enabled(DEFAULT_PRODUCT_SCOPE, capability), (
            f"{capability} is out of scope for the CBA phase (customer §20); "
            "re-enabling it requires an explicit customer authorization, not a code edit"
        )


def test_consented_outreach_is_not_gated_by_the_external_acquisition_gate() -> None:
    """Gating cold outreach must not take the consented path down with it.

    The two share the word "outreach" and nothing else: one contacts people who
    never agreed to be contacted, the other sends an approved draft to a
    consented contact and is explicitly preserved. A blanket gate on the word
    would remove a working, in-scope capability.
    """
    from smartmatch_domain.product_scope import (
        DEFAULT_PRODUCT_SCOPE,
        Capability,
        is_capability_enabled,
    )

    assert is_capability_enabled(DEFAULT_PRODUCT_SCOPE, Capability.CONSENTED_OUTREACH)
