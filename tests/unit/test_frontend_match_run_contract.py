"""Source contract for the Connector's match-run submission surface (TRACK 2).

``AIMatching.tsx`` reads a run somebody else submitted; card B24 in
``docs/plans/frontend-broken-buttons.md`` is the missing other half — a
coordinator control labelled "Request Match" that deep-linked to the admin
scoreboard and started nothing. This file guards the page that finally submits
one, and it guards it against the four ways a match UI goes wrong.

**It may not show a percentage.** OQ-CBA-005 and the ratified G1 presentation
rule. ``tests/unit/test_frontend_matching_contract.py`` already holds
``AIMatching.tsx`` to that; a *second* page that renders match output is a
second place the rule has to hold, and a submission page that previewed a
"92 percent fit" would satisfy every assertion in that file.

**It may not compute a score.** The server ranks and the UI displays. A client
that sorted, weighted, or thresholded anything would be a second matcher whose
answer nobody pinned, versioned, or reviewed — which is precisely the engine
the anti-patterns forbid porting.

**It may not carry a factor weight.** Weights live in ``factor_registry`` and
the persisted matching-weights row. A literal here is a weight nobody can
change without a frontend deploy, and one that would silently disagree with
the run it is drawn beside. So the page carries no decimal literal at all,
which is a cruder rule than "no weights" and a much easier one to keep.

**It may not report a match that has not happened.** ``POST /match-runs``
answers ``202``: no ``match_run`` row exists when it returns. The strongest
true thing the page may say is "queued" — the same discipline B17 taught the
outreach Send button, applied to a command whose result arrives later.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"

API_LIB = FRONTEND_SRC / "lib" / "api.ts"
MATCH_RUN_PAGE = FRONTEND_SRC / "app" / "pages" / "coordinator" / "CoordinatorMatchRuns.tsx"
AI_MATCHING_PAGE = FRONTEND_SRC / "app" / "pages" / "AIMatching.tsx"
ROUTES = FRONTEND_SRC / "app" / "routes.tsx"


def _code_only(source: str) -> str:
    """Strip JSDoc blocks and line comments before scanning.

    Same call ``test_frontend_no_fake_success_contract.py`` makes, for the same
    reason: these files explain the rules they obey, and a raw scan would fail
    on a file's own account of why it passes — which trains the next person to
    delete the explanation rather than keep the guard.
    """
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return "\n".join(
        line for line in without_blocks.splitlines() if not line.lstrip().startswith("//")
    )


# ---------------------------------------------------------------------------
# The client helpers
# ---------------------------------------------------------------------------


def test_api_lib_exposes_the_match_run_submission_and_follow_helpers() -> None:
    """Three helpers, because the flow has three server round trips.

    Submit (``202`` and a job id), follow the job to a terminal state, and then
    read the run. There is deliberately no fourth helper that guesses a run id
    from a job id: no route maps one to the other, and inventing the mapping in
    the browser would produce a URL that 404s at best.
    """
    source = API_LIB.read_text(encoding="utf-8")

    assert "export async function createMatchRun" in source
    assert "export async function fetchJobStatus" in source
    assert "export async function fetchJobCompletionSummary" in source
    # Already present from card M8b; named here so a refactor cannot drop the
    # read this whole flow terminates in.
    assert "export async function fetchMatchRun" in source


def test_create_match_run_sends_exactly_the_contract_body() -> None:
    """The three fields ``MatchRunRequest`` declares, and nothing else.

    ``contracts/openapi/smartmatch.json`` is explicit that this body carries no
    evidence: no industry, no role, no topic text, no location, no unit and no
    actor. A body that could state a speaker's expertise is a body that can
    decide its own shortlist (OQ-CBA-031). The unit travels in the authorized
    path; everything else is read server-side from this tenant's own rows.
    """
    source = API_LIB.read_text(encoding="utf-8")

    assert "speaker_request_id" in source
    assert "candidate_subject_ids" in source
    assert "portfolio_size" in source
    # Retries must be safe: the route documents `Idempotency-Key` as required.
    assert "Idempotency-Key" in source

    submission = source.split("export interface MatchRunSubmission", 1)
    assert len(submission) == 2, "api.ts must declare the submission body as a named type"
    body = submission[1].split("\n}", 1)[0]
    for forbidden in (
        "unit_id",
        "tenant",
        "actor",
        "industry",
        "role_code",
        "topic",
        "location",
        "is_virtual",
        "scoring_mode",
    ):
        assert forbidden not in body, (
            f"MatchRunSubmission gained a field the server derives itself: {forbidden!r}"
        )


def test_the_accepted_response_type_carries_the_registry_version() -> None:
    """``202`` is where provenance starts, not where it waits.

    ``MatchRunAcceptedResponse`` reports the registry version and scoring mode
    at submission precisely so a caller is never left rendering counts with no
    statement of which rulebook produced them.
    """
    source = API_LIB.read_text(encoding="utf-8")
    accepted = source.split("export interface MatchRunAccepted", 1)
    assert len(accepted) == 2, "api.ts must type the 202 body rather than returning unknown"
    body = accepted[1].split("\n}", 1)[0]

    for field in (
        "job_id",
        "events_url",
        "registry_version",
        "scoring_mode",
        "scored_candidates",
        "unscorable_candidates",
        "excluded_candidates",
    ):
        assert field in body, f"the accepted-response type drops {field!r}"


# ---------------------------------------------------------------------------
# The page: no percentage, no client-side scoring, no weights
# ---------------------------------------------------------------------------

PERCENTAGE_FORBIDDEN = (
    "* 100",
    "*100",
    "%",
    "percent",
    "Percent",
    "Match Score",
    "match_score",
    "heuristic_score",
    "fit score",
    "Fit Score",
)


def test_match_run_page_displays_no_percentage_anywhere() -> None:
    """OQ-CBA-005, held at the second surface that could break it.

    The percent sign is forbidden as a *character*, not as a rendered value.
    A page with no ``%`` in it cannot grow one in a Tailwind class, a template
    literal, or a copy tweak without this failing.
    """
    source = _code_only(MATCH_RUN_PAGE.read_text(encoding="utf-8"))
    for pattern in PERCENTAGE_FORBIDDEN:
        assert pattern not in source, (
            f"CoordinatorMatchRuns renders a match percentage: {pattern!r}"
        )


CLIENT_SCORING_FORBIDDEN = (
    ".sort(",
    ".reduce(",
    "Math.max",
    "Math.min",
    "Math.round",
    "weights",
    ".weight",
    "toFixed",
)


def test_match_run_page_computes_nothing_the_server_ranks() -> None:
    """The server ranks; the UI displays. There is no second matcher."""
    source = _code_only(MATCH_RUN_PAGE.read_text(encoding="utf-8"))
    for pattern in CLIENT_SCORING_FORBIDDEN:
        assert pattern not in source, (
            f"CoordinatorMatchRuns computes or orders results client-side: {pattern!r}"
        )


def test_match_run_page_carries_no_numeric_weight_literal() -> None:
    """No decimal literal at all — a blunter rule than "no weights", and firmer.

    A weight in this file is a weight nobody can change without a frontend
    deploy, and one that can silently disagree with the run rendered beside it.
    Integers survive (``2`` and ``3`` are the ratified portfolio bounds and the
    API enforces them); a decimal does not.
    """
    source = _code_only(MATCH_RUN_PAGE.read_text(encoding="utf-8"))
    offenders = re.findall(r"(?<![\w.\-])\d+\.\d+(?![\w])", source)
    assert offenders == [], (
        f"CoordinatorMatchRuns carries numeric literals that could be factor weights: {offenders}"
    )


def test_match_run_page_surfaces_the_registry_version_from_the_response() -> None:
    """Provenance is rendered, and it is rendered from the server's answer."""
    source = MATCH_RUN_PAGE.read_text(encoding="utf-8")
    assert "registry_version" in source
    assert "scoring_mode" in source


# ---------------------------------------------------------------------------
# The page: an accepted command is queued, not matched
# ---------------------------------------------------------------------------

FAKE_SUCCESS_FORBIDDEN = (
    "Matched",
    "Match complete",
    "Shortlist ready",
    "successfully",
    "Success!",
    "console.log",
    "setTimeout",
)


def test_match_run_page_never_claims_a_match_that_has_not_run() -> None:
    """B17's lesson, applied to a command whose result arrives later.

    ``POST /match-runs`` answers ``202`` and no ``match_run`` row exists when it
    returns. Every past tense here would be a claim about a shortlist rather
    than about a command.
    """
    source = _code_only(MATCH_RUN_PAGE.read_text(encoding="utf-8"))
    for pattern in FAKE_SUCCESS_FORBIDDEN:
        assert pattern not in source, (
            f"CoordinatorMatchRuns reintroduced a fabricated success: {pattern!r}"
        )


def test_match_run_page_reports_the_queued_state_it_actually_has() -> None:
    """The positive half. Forbidding "matched" is not a contract on its own."""
    source = MATCH_RUN_PAGE.read_text(encoding="utf-8")

    assert "Queued" in source
    assert "job_id" in source, "a queued run must name the job it became"
    assert "events_url" in source


def test_match_run_page_navigates_only_on_a_server_supplied_run_id() -> None:
    """``/coordinator-portal/match-runs?run={id}`` opens only once a run id exists.

    The ``202`` carries a *job* id, and no route maps a job to its run: the id
    arrives on the job's own terminal ``job.completed`` summary. So navigation
    waits for that summary. A page that redirected at ``202`` would have to
    invent the id in the query string, which is a fabricated result wearing a
    URL.

    The destination is this same route's detail state — ``?run=`` mounts the
    shortlist viewer in place of the submission form. Before the Connector
    Dashboard consolidation it was ``/ai-matching?run={id}``; the retired
    address still resolves because its redirect forwards the parameter.
    """
    source = MATCH_RUN_PAGE.read_text(encoding="utf-8")

    assert "/coordinator-portal/match-runs?run=" in source
    assert "match_run_id" in source
    assert "fetchJobCompletionSummary" in source


CBA_FORBIDDEN_SURFACES = (
    "fetchSpecialists",
    "/api/data/",
    "AgenticOutreachPanel",
    "rankSpeakers",
    "scoreSpeaker",
    "fetchPipeline",
)


def test_match_run_page_touches_none_of_the_retired_surfaces() -> None:
    """Non-negotiable: no ``fetchSpecialists``, no ``/api/data/*``, no agentic panel."""
    source = MATCH_RUN_PAGE.read_text(encoding="utf-8")
    for pattern in CBA_FORBIDDEN_SURFACES:
        assert pattern not in source, (
            f"CoordinatorMatchRuns reaches a retired legacy surface: {pattern!r}"
        )


# ---------------------------------------------------------------------------
# The shortlist page, extended for the CBA factor vocabulary
# ---------------------------------------------------------------------------


def test_shortlist_page_renders_all_three_adr_0016_states() -> None:
    """``policy_neutral`` is neither a measurement nor an absence.

    ADR-0016 gave factors three states, and a renderer that knew only two would
    print "Unknown" beside a value a stated customer policy actually supplied —
    the mirror image of the deflated-zero defect, and just as wrong.
    """
    source = AI_MATCHING_PAGE.read_text(encoding="utf-8")

    assert '"policy_neutral"' in source
    assert "policy_id" in source, "a policy value must be attributable to the policy behind it"


def test_shortlist_page_renders_the_approved_caption_verbatim() -> None:
    """ADR-0016 Proposal 8: the caption is shown beside the score, as written."""
    source = AI_MATCHING_PAGE.read_text(encoding="utf-8")
    assert "caption" in source


def test_shortlist_page_hardcodes_no_cba_factor_key() -> None:
    """Factor rows are rendered from the registry's own labels, not a local table.

    Every factor arrives with a ``display_label`` the registry supplied. A
    switch on ``cba_semantic_topic`` here would be a second vocabulary that
    goes stale the moment the registry gains a factor — and it would render
    nothing at all for the one it did not know about.
    """
    source = _code_only(AI_MATCHING_PAGE.read_text(encoding="utf-8"))
    for factor_key in (
        "cba_semantic_topic",
        "industry_match",
        "role_match",
        "proximity",
    ):
        assert f'"{factor_key}"' not in source, (
            f"AIMatching hardcodes the factor key {factor_key!r} instead of rendering the "
            "registry's own display label"
        )
    assert "factor.display_label" in source


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def test_the_match_run_page_is_mounted_in_the_coordinator_portal() -> None:
    """A UI route is a claim about what exists, never an authorization decision.

    The server authorizes ``POST /match-runs`` per request, deny-by-default and
    tenant-scoped, whatever the router renders.
    """
    source = ROUTES.read_text(encoding="utf-8")
    assert "CoordinatorMatchRuns" in source
    assert '"match-runs"' in source or "'match-runs'" in source


def test_the_shortlist_stays_reachable_inside_the_connector_shell() -> None:
    """``?run=`` on the match-runs route mounts the run's detail view.

    The consolidation retired ``/ai-matching``, the address the shortlist page
    owned. Route parity means the capability must survive the retirement:
    ``AIMatching`` mounts under the Connector shell, selected by the same
    ``run`` parameter, and the retired address's redirect forwards that
    parameter rather than stranding the run it named.
    """
    source = ROUTES.read_text(encoding="utf-8")
    assert "AIMatching" in source, (
        "the shortlist page is not mounted; /ai-matching?run={id} lost its successor"
    )
    assert 'searchParams.get("run")' in source, (
        "nothing selects the run-detail view; the ?run= parameter would be ignored"
    )

    redirects = (FRONTEND_SRC / "app" / "legacyRedirects.ts").read_text(encoding="utf-8")
    ai_matching = re.search(r'from:\s*"/ai-matching"\s*,\s*to:\s*"([^"]+)"([^}]*)}', redirects)
    assert ai_matching is not None, "the /ai-matching redirect is missing"
    assert '"run"' in ai_matching.group(0), (
        "/ai-matching must forward its ?run= parameter to the successor route"
    )
