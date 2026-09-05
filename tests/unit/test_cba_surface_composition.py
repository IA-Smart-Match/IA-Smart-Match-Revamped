"""CBA surface composition: what the product routes to, navigates to, and claims.

``tests/unit/test_cba_scope_policy.py`` pins the *policy* — which named
capabilities the CBA product includes — and proves the API composition reads it.
This file pins the other half: that the **frontend composition** reads the same
policy, so a capability the policy disables owns no CBA route, no CBA navigation
entry, and no CBA claim.

Three properties, and the difference between them matters:

1. **Gated surfaces are unreachable, not deleted.** Every file behind a gated
   capability still exists and still compiles. ``docs/plans/open-questions/
   cba-phase-deferred.md`` is explicit that gated capabilities "remain in the
   repository but are not mounted, routed, advertised, or presented as
   successful on CBA paths" — the customer put them out of scope for *this
   phase* (§20), which is not the same as declaring them defective.
2. **Preserved surfaces are asserted present.** A gate that quietly took the
   discovery feed, consented coordinator outreach, or server-backed rewards with
   it would satisfy "nothing out of scope is reachable" and fail the customer's
   §17/§22 "do not rebuild what works". Each preserved surface therefore gets an
   explicit regression assertion rather than being left to inference.
3. **A UI gate is not authorization.** Removing a link removes a *claim*. Every
   route the API keeps mounted still enforces its own deny-by-default,
   tenant-scoped authorization (``smartmatch_authz``), and nothing here may be
   read as a security control. These tests exist because advertising a scraping
   console the customer put out of scope is a false statement about the product
   long before it is a security question.

The expectations below are derived from ``smartmatch_domain.product_scope``
rather than restated, so this file cannot drift into being a second opinion
about scope: if the policy ever enabled one of these capabilities, the
corresponding test would demand the surface be reachable again.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from smartmatch_domain.product_scope import Capability, ProductScope, is_capability_enabled

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"

ROUTES = FRONTEND_SRC / "app" / "routes.tsx"
LAYOUT = FRONTEND_SRC / "app" / "components" / "Layout.tsx"
LANDING_PAGE = FRONTEND_SRC / "app" / "pages" / "LandingPage.tsx"
PIPELINE_FUNNEL_TILES = FRONTEND_SRC / "app" / "components" / "PipelineFunnelTiles.tsx"
DASHBOARD = FRONTEND_SRC / "app" / "pages" / "Dashboard.tsx"
METRICS_LIB = FRONTEND_SRC / "lib" / "metrics.ts"
PRODUCT_SCOPE_TS = FRONTEND_SRC / "lib" / "productScope.ts"

LEGACY_OUTREACH_PAGE = FRONTEND_SRC / "app" / "pages" / "Outreach.tsx"
AGENTIC_OUTREACH_PANEL = FRONTEND_SRC / "components" / "AgenticOutreachPanel.tsx"
CRAWLER_FEED = FRONTEND_SRC / "components" / "CrawlerFeed.tsx"
DISCOVERY_FEED = FRONTEND_SRC / "app" / "components" / "DiscoveryFeed.tsx"
COORDINATOR_OUTREACH = FRONTEND_SRC / "app" / "pages" / "coordinator" / "CoordinatorOutreach.tsx"
STUDENT_REWARDS = FRONTEND_SRC / "app" / "pages" / "student" / "StudentRewards.tsx"

#: The capabilities the legacy admin ``/outreach`` surface would need in order
#: to be an honest offer. It composes both: the page reaches unknown university
#: contacts from the legacy ``/api/data/*`` reads, and it embeds ``CrawlerFeed``.
#: Naming both is deliberate — a later phase that re-enabled only one of them
#: must not silently restore the whole page.
LEGACY_OUTREACH_CAPABILITIES = (
    Capability.COLD_UNKNOWN_CONTACT_OUTREACH,
    Capability.EXTERNAL_SPEAKER_ACQUISITION,
)

#: Capability names as the frontend mirror spells them, for source assertions.
_COLD = Capability.COLD_UNKNOWN_CONTACT_OUTREACH.value
_EXTERNAL = Capability.EXTERNAL_SPEAKER_ACQUISITION.value
_MEMBER_INQUIRY = Capability.MEMBER_INQUIRY_NARRATIVE.value


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_comments(source: str) -> str:
    """Drop ``/* ... */`` and ``//`` text so prose cannot satisfy an assertion.

    Every "this string must be absent" test below is a claim about *code and
    rendered copy*, not about whether a file is allowed to explain itself. A
    comment recording that the scraping narrative was removed is the opposite of
    a violation, and a naive substring check would fail it.
    """
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", without_blocks, flags=re.MULTILINE)


# ---------------------------------------------------------------------------
# The policy this file reads. If these fail, the rest is meaningless.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("capability", LEGACY_OUTREACH_CAPABILITIES)
def test_legacy_outreach_capabilities_are_disabled_under_cba(capability: Capability) -> None:
    assert not is_capability_enabled(ProductScope.CBA, capability)


def test_member_inquiry_narrative_is_disabled_under_cba() -> None:
    assert not is_capability_enabled(ProductScope.CBA, Capability.MEMBER_INQUIRY_NARRATIVE)


# ---------------------------------------------------------------------------
# Route composition
# ---------------------------------------------------------------------------


class TestRouteComposition:
    """``routes.tsx`` asks the policy instead of hard-coding a product decision."""

    def test_routes_read_the_shared_policy(self) -> None:
        source = _read(ROUTES)
        assert "productScope" in source, (
            "routes.tsx must compose from the shared capability policy "
            "(src/lib/productScope.ts), not from an ad-hoc flag"
        )
        assert "isCapabilityEnabled" in source

    def test_the_legacy_admin_outreach_route_is_capability_gated(self) -> None:
        source = _read(ROUTES)
        assert _COLD in source and _EXTERNAL in source, (
            "the legacy admin /outreach route must name the capabilities it needs; "
            f"expected both {_COLD!r} and {_EXTERNAL!r} in routes.tsx"
        )

    def test_no_unconditional_legacy_outreach_route(self) -> None:
        """The gated page must not sit in a route array the policy never sees.

        Checked structurally rather than by substring: strip the capability-
        guarded spreads out of the admin layout's ``children`` array, and what
        remains is the set of routes mounted *whatever the policy says*. The
        legacy ``/outreach`` path must not be among them.
        """
        code = _strip_comments(_read(ROUTES))
        admin_children = re.search(
            r"Component:\s*Layout\s*,\s*children:\s*\[(.*?)\n\s*\]", code, flags=re.DOTALL
        )
        assert admin_children is not None, "could not locate the admin layout children array"

        guarded = re.search(
            r"whenCapable\(\s*LEGACY_COLD_OUTREACH_CAPABILITIES\s*,\s*\{\s*path:\s*\"outreach\"",
            admin_children.group(1),
        )
        assert guarded is not None, (
            "the legacy /outreach route must be composed through whenCapable(...) with the "
            "capabilities it needs"
        )

        unconditional = re.sub(
            r"\.\.\.whenCapable\(.*?\}\),", "", admin_children.group(1), flags=re.DOTALL
        )
        assert '"outreach"' not in unconditional, (
            "the legacy admin /outreach route is mounted unconditionally; it must be composed "
            "through the capability policy so the CBA product does not route to it"
        )

    def test_the_consented_coordinator_outreach_route_is_preserved(self) -> None:
        """Regression guard for the preserved capability, not a formality.

        ``CONSENTED_OUTREACH`` is enabled under CBA. Gating the coordinator
        portal's outreach alongside the legacy page — they share a word and
        nothing else — would remove a capability the customer kept.
        """
        assert is_capability_enabled(ProductScope.CBA, Capability.CONSENTED_OUTREACH)
        code = _strip_comments(_read(ROUTES))
        coordinator = re.search(
            r'path:\s*"coordinator-portal".*?children:\s*\[(.*?)\n\s*\]', code, flags=re.DOTALL
        )
        assert coordinator is not None, "could not locate the coordinator portal children array"
        assert '"outreach"' in coordinator.group(1), (
            "coordinator-portal/outreach is the preserved consented /v1 path and must stay routed"
        )

    def test_the_student_rewards_route_is_preserved(self) -> None:
        assert is_capability_enabled(ProductScope.CBA, Capability.REWARDS_LEDGER)
        code = _strip_comments(_read(ROUTES))
        assert '"rewards"' in code, (
            'customer §4 says "Rewards / points — Keep"; the route must stay mounted'
        )

    @pytest.mark.parametrize(
        "path_literal",
        ["dashboard", "opportunities", "pipeline", "calendar", "ai-matching"],
    )
    def test_preserved_admin_routes_stay_mounted(self, path_literal: str) -> None:
        code = _strip_comments(_read(ROUTES))
        assert f'"{path_literal}"' in code, (
            f"/{path_literal} is preserved under CBA (customer §§17, 22) and must stay routed"
        )


# ---------------------------------------------------------------------------
# Navigation composition
# ---------------------------------------------------------------------------


class TestNavigationComposition:
    """The sidebar advertises only what the product offers."""

    def test_navigation_reads_the_shared_policy(self) -> None:
        source = _read(LAYOUT)
        assert "productScope" in source and "isCapabilityEnabled" in source, (
            "Layout.tsx navigation must be composed from the shared capability policy"
        )

    def test_the_legacy_outreach_nav_entry_is_capability_gated(self) -> None:
        source = _read(LAYOUT)
        assert _COLD in source and _EXTERNAL in source, (
            "the legacy Outreach nav entry must declare the capabilities it requires"
        )

    def test_no_navigation_entry_links_to_the_gated_page_unconditionally(self) -> None:
        """Every entry pointing at the gated page must declare what it needs.

        The entry is allowed to keep its `href` — a nav item that stopped
        naming its own destination would be harder to read, not safer. What it
        may not do is reach the rendered sidebar without the policy having been
        asked, so each object literal carrying `/outreach` must also carry a
        `requires`, and the rendered list must be the filtered one.
        """
        code = _strip_comments(_read(LAYOUT))

        for entry in re.findall(r"\{[^{}]*?href:\s*\"/outreach\"[^{}]*?\}", code, flags=re.DOTALL):
            assert "requires:" in entry, (
                "a nav item points at /outreach without declaring the capabilities it needs; "
                "under CBA this advertises a page the customer put out of scope (§20)"
            )

        assert re.search(r"offeredSections\.map\(", code), (
            "the sidebar must render the capability-filtered sections, not the raw declaration"
        )

    @pytest.mark.parametrize(
        "href", ["/dashboard", "/volunteers", "/pipeline", "/calendar", "/opportunities"]
    )
    def test_preserved_navigation_entries_remain(self, href: str) -> None:
        code = _strip_comments(_read(LAYOUT))
        assert f'"{href}"' in code, f"preserved navigation entry {href} disappeared"


# ---------------------------------------------------------------------------
# member_inquiry: suppressed as a CBA narrative, preserved as stored history
# ---------------------------------------------------------------------------


class TestMemberInquirySuppression:
    def test_the_funnel_tiles_gate_the_member_inquiry_tile(self) -> None:
        source = _read(PIPELINE_FUNNEL_TILES)
        assert "isCapabilityEnabled" in source and _MEMBER_INQUIRY in source, (
            "PipelineFunnelTiles must ask the policy before offering a member_inquiry tile"
        )

    def test_the_dashboard_gates_its_member_inquiry_card(self) -> None:
        source = _read(DASHBOARD)
        assert "isCapabilityEnabled" in source and _MEMBER_INQUIRY in source, (
            "the Dashboard's headline Member Inquiry card is the same CBA claim as the "
            "funnel tile and must be gated by the same policy"
        )

    def test_the_registered_metric_name_is_preserved(self) -> None:
        """Suppressing the narrative must not delete the metric or its history.

        ``cba-phase-deferred.md`` keeps the stage, its rows, and migration 0011.
        Dropping ``pipeline_member_inquiry`` from the frontend's registered-name
        list would be deletion cleanup, and would also desynchronise the client
        from ``METRIC_REGISTER``.
        """
        source = _read(METRICS_LIB)
        assert '"pipeline_member_inquiry"' in source
        assert "pipeline_member_inquiry:" in source, (
            "the stage label must survive; only its CBA presentation is gated"
        )

    @pytest.mark.parametrize(
        "metric_name",
        ["pipeline_matched", "pipeline_contacted", "pipeline_confirmed", "pipeline_attended"],
    )
    def test_the_other_funnel_stages_are_untouched(self, metric_name: str) -> None:
        source = _read(METRICS_LIB)
        assert f'"{metric_name}"' in source


# ---------------------------------------------------------------------------
# Landing-page claims
# ---------------------------------------------------------------------------

#: Copy that asserts external acquisition or a CRM the product does not have.
#: Customer §20 puts scraping, external discovery, and a contact-acquisition CRM
#: out of scope; ``cba-phase-deferred.md`` requires the narrative be replaced or
#: hidden rather than left standing as a false claim.
FORBIDDEN_LANDING_CLAIMS = (
    "scraping",
    "Scraping",
    "web crawler",
    "Web Crawler",
    "Discovery Automation",
    "Platforms Monitored",
    "career.ucla.edu",
    "PARSING",
    "CRM",
    "in real-time",
)

#: Unsourced performance numbers rendered as product facts. ADR-0011 rule 1: a
#: number on screen is a measurement or it is "unknown" — never a decoration.
FORBIDDEN_LANDING_FIGURES = ("2,481", "842", "94%")


class TestLandingPageClaims:
    @pytest.mark.parametrize("claim", FORBIDDEN_LANDING_CLAIMS)
    def test_landing_page_claims_no_external_acquisition(self, claim: str) -> None:
        code = _strip_comments(_read(LANDING_PAGE))
        assert claim not in code, (
            f"LandingPage advertises out-of-scope external acquisition: {claim!r} (customer §20)"
        )

    @pytest.mark.parametrize("figure", FORBIDDEN_LANDING_FIGURES)
    def test_landing_page_shows_no_unsourced_metric(self, figure: str) -> None:
        code = _strip_comments(_read(LANDING_PAGE))
        assert figure not in code, (
            f"LandingPage renders an unsourced performance figure {figure!r}; no measurement "
            "backs it (ADR-0011 rule 1)"
        )

    def test_landing_page_still_describes_the_in_scope_product(self) -> None:
        """Truthfulness is not silence. The page must still say what this does."""
        source = _read(LANDING_PAGE)
        for expected in ("Sign in", "Intelligent Matching"):
            assert expected in source, f"LandingPage lost in-scope content: {expected!r}"


# ---------------------------------------------------------------------------
# Nothing was deleted
# ---------------------------------------------------------------------------


class TestNoDeletionCleanup:
    """Gated implementation stays in the repository. ``cba-phase-deferred.md``."""

    @pytest.mark.parametrize(
        "path",
        [
            LEGACY_OUTREACH_PAGE,
            AGENTIC_OUTREACH_PANEL,
            CRAWLER_FEED,
            DISCOVERY_FEED,
            COORDINATOR_OUTREACH,
            STUDENT_REWARDS,
            PRODUCT_SCOPE_TS,
        ],
        ids=lambda path: path.name,
    )
    def test_the_file_still_exists(self, path: Path) -> None:
        assert path.is_file(), (
            f"{path.name} was deleted. Gated capabilities are out of scope for this phase, "
            "not defective; this card removes reachability, never implementation."
        )

    def test_the_crawler_surface_is_reachable_only_through_the_gated_page(self) -> None:
        """``CrawlerFeed`` has exactly one referrer, and that referrer is gated.

        Complements ``tests/unit/test_fixture_ingest_wiring.py``, which proves no
        *backend* crawl surface exists. This is the frontend half: even the inert
        placeholder card must not appear on a CBA-reachable screen.
        """
        referrers = sorted(
            path.relative_to(FRONTEND_SRC).as_posix()
            for path in FRONTEND_SRC.rglob("*.tsx")
            if path != CRAWLER_FEED
            and "CrawlerFeed" in _strip_comments(path.read_text(encoding="utf-8"))
        )
        assert referrers == ["app/pages/Outreach.tsx"], (
            f"CrawlerFeed gained a reference outside the capability-gated legacy page: {referrers}"
        )


# ---------------------------------------------------------------------------
# Preserved capabilities
# ---------------------------------------------------------------------------


class TestPreservedCapabilities:
    """Explicit regressions for everything this card must not take with it."""

    def test_the_discovery_feed_keeps_red_yellow_green(self) -> None:
        """Customer §17: do not redesign this because the customer changed."""
        assert is_capability_enabled(ProductScope.CBA, Capability.DISCOVERY_METRICS)
        source = _read(DISCOVERY_FEED)
        assert "toneForBacklog" in source and "SIGNAL_TONE_LABELS" in source, (
            "the R/Y/G severity grading disappeared from the discovery feed"
        )

    def test_coordinator_outreach_still_uses_the_consented_v1_path(self) -> None:
        source = _read(COORDINATOR_OUTREACH)
        assert "useOutreach" in source, (
            "the preserved consented outreach path (/v1/units/{unit_id}/outreach/*) was removed"
        )

    def test_coordinator_outreach_does_not_reuse_the_legacy_cold_path(self) -> None:
        source = _read(COORDINATOR_OUTREACH)
        for forbidden in ("fetchSpecialists", "/api/data/", "AgenticOutreachPanel"):
            assert forbidden not in source, (
                "the coordinator's consented path reached for the legacy cold surface: "
                f"{forbidden!r}"
            )

    def test_student_rewards_stay_server_backed(self) -> None:
        """No blanket rewards disable. Customer §4: "Rewards / points — Keep"."""
        assert is_capability_enabled(ProductScope.CBA, Capability.REWARDS_LEDGER)
        source = _read(STUDENT_REWARDS)
        assert "useRewards" in source, "StudentRewards no longer reads the server rewards API"
        assert "?? 0" not in _strip_comments(source), (
            "a client-side zero fallback reappeared (ADR-0011 rule 1)"
        )

    def test_rewards_are_not_gated_by_the_chapter_dues_capability(self) -> None:
        """The two are different things and must not be collapsed.

        Chapter membership/dues is removed (§4, §20); the points ledger is kept.
        A gate that hid rewards because dues went away would delete a working,
        server-backed capability the customer explicitly retained.
        """
        assert not is_capability_enabled(ProductScope.CBA, Capability.CHAPTER_MEMBERSHIP_DUES)
        assert is_capability_enabled(ProductScope.CBA, Capability.REWARDS_LEDGER)
        assert Capability.CHAPTER_MEMBERSHIP_DUES.value not in _read(STUDENT_REWARDS)
