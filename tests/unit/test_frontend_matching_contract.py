"""Source contract for the matching UI, after card M10 wired it to the real API.

Until this card the rule was simple and total: the matching page called nothing
and displayed nothing, because gate G1 was open. G1 closed on 2026-09-03, card
M8b landed ``GET /v1/units/{unit_id}/match-runs/{match_run_id}``, and
``AIMatching.tsx`` now reads it. So the assertions here change deliberately, in
the commit that lands the capability — and they get *stricter*, not looser,
because "the page shows nothing" was a rule that enforced itself and "the page
shows the right thing" is not.

What is unchanged: :data:`MATCHING_FORBIDDEN_PATTERNS` still refuses every
legacy matching call and every legacy score field, so this page cannot reach
``/api/matching``, ``rankSpeakers``, or the deflated legacy ``match_score``.
``Dashboard.tsx`` is unchanged too — it displays no score and calls nothing, and
this file still holds it to that.

What is new: the page must actually call ``fetchMatchRun``, and it must not
fabricate. The forbidden list therefore grew a *percentage* family and a
*zero-coercion* family, which is how the ratified "no percentage display" rule
and ADR-0011 are held at the last boundary a Python source check can see.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_MATCHING_PAGE = (
    REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src" / "app" / "pages" / "AIMatching.tsx"
)
DASHBOARD_PAGE = (
    REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src" / "app" / "pages" / "Dashboard.tsx"
)
METRICS_LIB = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src" / "lib" / "metrics.ts"

MATCHING_FORBIDDEN_PATTERNS = (
    "rankSpeakers",
    "rankSpeakersForCourse",
    "/api/matching",
    "fetchFeedbackStats",
    "fetchPipeline",
    "fetchEvents",
    "Match Score",
    "match.score",
    # The ratified G1 presentation rule: "no percentage display to
    # coordinators". A score arrives in [0, 1] and is rendered in [0, 1]; the
    # two ways it could stop being one are a multiplication and a literal
    # percent sign, so both are named. This is what makes the rule hold in the
    # file rather than in a reviewer's memory.
    "* 100",
    "*100",
    "%</",
    'toLocaleString(undefined, { style: "percent"',
    # ADR-0011 at the last boundary. `state` is on the wire precisely so no
    # consumer has to turn a null into a number; a coalescing default here
    # would be the unknown-as-zero defect arriving in the render layer, which
    # is where the legacy system had it.
    "?? 0",
    "|| 0",
)

DASHBOARD_MATCHING_FORBIDDEN_PATTERNS = (
    "rankSpeakers",
    "/api/matching",
    "topMatches",
    "Match Score",
    "match.score",
)


def test_ai_matching_page_does_not_invoke_legacy_matching_api() -> None:
    source = AI_MATCHING_PAGE.read_text(encoding="utf-8")
    for pattern in MATCHING_FORBIDDEN_PATTERNS:
        assert pattern not in source, (
            f"AIMatching still contains forbidden matching pattern: {pattern!r}"
        )


def test_ai_matching_page_reads_the_real_match_run_api() -> None:
    """The successor to "this page shows a gate notice".

    Before card M10 this asserted the page named ``gate G1`` and
    ``REGISTRY_STATUS`` and displayed nothing. Both are gone because both are
    now false: the gate closed and the routes exist, so a page still explaining
    that scoring is blocked would be the honest-looking half of the same defect
    — a surface stating something about the platform that is not true.

    What replaces it is the stronger claim: the page calls the real endpoint. A
    matching page that displayed a shortlist without calling anything is the
    failure this whole plan exists to prevent, and it would pass every
    *forbidden*-pattern assertion in this file.
    """
    source = AI_MATCHING_PAGE.read_text(encoding="utf-8")
    assert "fetchMatchRun" in source, "the shortlist page must read the real match-run API"
    assert "match-runs" in source
    assert "getConfiguredUnitId" in source, "match runs are unit-scoped; the page must say which"


def test_ai_matching_page_still_has_an_honest_unavailable_state() -> None:
    """Reading a real API does not licence an empty page with no explanation.

    There are four ways this page legitimately has nothing to show — no bearer
    token, no configured unit, no run named in the URL, and a failed request —
    and each has to say which. ADR-0011 rule 1 is about numbers, but its reason
    generalizes: a blank is indistinguishable from a zero result unless
    something says what it is.
    """
    source = AI_MATCHING_PAGE.read_text(encoding="utf-8")
    assert "MatchingUnavailable" in source
    assert "MATCHING_UNAVAILABLE_REASON" in source
    assert "unavailableMatchingMetric" in source


def test_ai_matching_page_distinguishes_unknown_from_measured_zero() -> None:
    """The page branches on ``state``, not on the value being null.

    ADR-0011's whole point is that the discriminator travels beside the value.
    A renderer that tested ``value === null`` alone would still be correct
    today and would silently become wrong the moment anything upstream started
    sending a number for an absent measurement — which is precisely how the
    legacy "Topic Relevance 0%" surface came about.
    """
    source = AI_MATCHING_PAGE.read_text(encoding="utf-8")
    assert 'state === "unknown"' in source
    assert '"measured_zero"' in source, "a measured zero must be labelled as one"
    assert "Unknown" in source


def test_metrics_lib_exports_matching_unavailable_reason() -> None:
    source = METRICS_LIB.read_text(encoding="utf-8")
    assert "MATCHING_UNAVAILABLE_REASON" in source
    assert "factor registry is approved" in source
    assert "unavailableMatchingMetric" in source


def test_dashboard_does_not_invoke_legacy_matching_api() -> None:
    source = DASHBOARD_PAGE.read_text(encoding="utf-8")
    for pattern in DASHBOARD_MATCHING_FORBIDDEN_PATTERNS:
        assert pattern not in source, (
            f"Dashboard still contains forbidden matching pattern: {pattern!r}"
        )
    assert "MATCHING_UNAVAILABLE_REASON" in source
