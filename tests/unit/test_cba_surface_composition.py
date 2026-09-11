"""CBA surface composition: what the product routes to, navigates to, and claims.

``tests/unit/test_cba_scope_policy.py`` pins the *policy* — which named
capabilities the CBA product includes — and proves the API composition reads it.
This file pins the other half: that the **frontend composition** honours the same
policy, so a capability the policy disables owns no CBA route, no CBA navigation
entry, and no CBA claim.

Addendum — the Connector Dashboard consolidation (September 2026)
================================================================

``admin`` and ``coordinator`` are one persona (``role_presentation.py``), so the
two Speaker Connector shells became one. ``components/Layout.tsx`` — the admin
shell that carried the capability-gated ``/outreach`` entry and the eight
top-level addresses — is deleted, and every address it owned redirects to its
successor in ``app/legacyRedirects.ts``. The assertions below therefore read
different files than they used to, for the same guarantees:

* where a test once asserted the router *asked the policy* before mounting the
  gated legacy ``/outreach`` page, it now asserts the gated page is **mounted
  nowhere** and its address redirects to the consented ``/v1`` successor. That
  is the stronger form of the same property: a surface with no route at all is
  unreachable no matter what the policy says, and nothing out of scope is
  offered a gate to hide behind.
* where a test once asserted a *preserved* admin route stayed mounted at its
  own address, it now asserts the address still resolves — through the redirect
  table — *and* that its successor page is mounted in the Connector shell. A
  redirect that pointed nowhere would pass a naive "the address resolves" check;
  both halves are asserted so neither can rot.

Three properties, and the difference between them matters:

1. **Gated surfaces are unreachable, not deleted.** Every file behind a gated
   capability still exists and still compiles. ``docs/plans/open-questions/
   cba-phase-deferred.md`` is explicit that gated capabilities "remain in the
   repository but are not mounted, routed, advertised, or presented as
   successful on CBA paths" — the customer put them out of scope for *this
   phase* (§20), which is not the same as declaring them defective.
2. **Preserved surfaces are asserted present.** A consolidation that quietly
   took the discovery feed, consented coordinator outreach, or server-backed
   rewards with it would satisfy "nothing out of scope is reachable" and fail
   the customer's §17/§22 "do not rebuild what works". Each preserved surface
   therefore gets an explicit regression assertion rather than being left to
   inference.
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
REDIRECTS = FRONTEND_SRC / "app" / "legacyRedirects.ts"
#: The shell the consolidation kept. ``Layout.tsx`` — the admin shell this file
#: used to read — is deleted; its capability-gated nav structure went with it.
CONNECTOR_SHELL = FRONTEND_SRC / "app" / "components" / "CoordinatorPortalLayout.tsx"
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

#: The admin-shell addresses this file once asserted were mounted as pages,
#: and the Connector surface each one lands on now. They are redirects —
#: "preserved" means the address still resolves to a mounted successor, not
#: that a literal still sits in the router.
RETIRED_ADMIN_ADDRESSES = {
    "dashboard": "/coordinator-portal",
    "opportunities": "/coordinator-portal/speaker-requests",
    "pipeline": "/coordinator-portal/speaker-requests",
    "calendar": "/coordinator-portal/events",
    "ai-matching": "/coordinator-portal/match-runs",
}

#: The retired admin-shell nav hrefs and the Connector-shell successor each
#: maps to. Written out rather than derived: this is the independent
#: inventory of what the sidebar must still offer.
RETIRED_ADMIN_NAV = {
    "/dashboard": "/coordinator-portal",
    "/volunteers": "/coordinator-portal/speaker-contacts",
    "/pipeline": "/coordinator-portal/speaker-requests",
    "/calendar": "/coordinator-portal/events",
    "/opportunities": "/coordinator-portal/speaker-requests",
}


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
    """``routes.tsx`` mounts nothing the policy disables, and loses nothing it kept.

    The shape of this guarantee changed with the consolidation. The admin shell
    whose children the policy used to filter is deleted, so there is no route
    left for a capability gate to decide: the gated pages are simply mounted
    nowhere, and their addresses resolve through the redirect table instead.
    """

    def test_no_route_mounts_a_capability_gated_page(self) -> None:
        """The retired admin pages are unreachable, not filtered.

        Where this file once asserted ``routes.tsx`` asked the policy before
        mounting the gated legacy ``/outreach`` page, it now asserts the
        stronger fact: the router imports none of the retired pages at all. A
        page with no route is unreachable whatever the policy says — there is
        no gate left to get wrong.
        """
        code = _strip_comments(_read(ROUTES))
        for page in ("Outreach", "Dashboard", "Opportunities", "Pipeline", "Calendar"):
            assert f'import("./pages/{page}")' not in code, (
                f"the retired admin {page} page is still routed; gated surfaces are "
                "unreachable, not merely unlinked"
            )

    def test_the_gated_capabilities_own_no_route(self) -> None:
        """Nothing the router mounts is decided by a disabled capability.

        The only route the capability policy ever had to gate was the legacy
        cold-outreach page, and it is retired rather than gated. Asserting the
        mechanism survives (``productScope``/``isCapabilityEnabled`` in
        ``routes.tsx``) would pin scaffolding with nothing left to scaffold —
        so this asserts the outcome instead: no capability name appears in the
        route table, because no route's existence depends on one.
        """
        code = _strip_comments(_read(ROUTES))
        assert _COLD not in code and _EXTERNAL not in code, (
            "a route still names a disabled capability; the only route that needed "
            "one is retired, so this is either a remnant or a new out-of-scope surface"
        )

    def test_the_legacy_admin_outreach_address_redirects_to_the_consented_page(self) -> None:
        """``/outreach`` still resolves — to the page that does its in-scope half.

        The retired page composed cold unknown-contact outreach *and* external
        speaker acquisition (both §20-disabled); its address now lands on the
        coordinator portal's consented ``/v1`` outreach page, which is a
        different thing sharing a word. Asserting the redirect — rather than
        the page's absence — is what keeps a bookmarked address from 404ing.
        """
        redirects = _read(REDIRECTS)
        assert re.search(
            r'from:\s*"/outreach"\s*,\s*to:\s*"/coordinator-portal/outreach"', redirects
        ), (
            "the retired /outreach address must redirect to the consented coordinator "
            "outreach page; dropping the address would 404 a URL that used to work"
        )
        # And the gated page itself must not also be mounted — a route and a
        # redirect on one address would shadow each other unpredictably.
        code = _strip_comments(_read(ROUTES))
        assert not re.search(r'path:\s*"/outreach"', code), (
            "/outreach is still registered as a page as well as a redirect"
        )

    def test_no_unconditional_legacy_outreach_route(self) -> None:
        """The only ``outreach`` route is the coordinator portal's consented one.

        Checked structurally: the single ``path: "outreach"`` registration sits
        inside the ``coordinator-portal`` children array — the preserved
        consented ``/v1`` surface — and nowhere else. A second registration
        outside it would be a top-level page the redirect table does not own.
        """
        code = _strip_comments(_read(ROUTES))
        coordinator = re.search(
            r'path:\s*"coordinator-portal".*?children:\s*\[(.*?)\n\s*\]', code, flags=re.DOTALL
        )
        assert coordinator is not None, "could not locate the coordinator portal children array"
        assert 'path: "outreach"' in coordinator.group(1), (
            "coordinator-portal/outreach is the preserved consented /v1 path and must stay routed"
        )
        # Every other `path:` registration, outside that children array.
        remainder = code[: coordinator.start()] + code[coordinator.end() :]
        assert not re.search(r'path:\s*"/?outreach"', remainder), (
            "an /outreach page is still mounted outside the coordinator portal; "
            "the consented successor is the only outreach route there may be"
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
        "path_literal", sorted(RETIRED_ADMIN_ADDRESSES.keys())
    )
    def test_preserved_admin_addresses_still_resolve(self, path_literal: str) -> None:
        """Every preserved admin address redirects to a mounted successor.

        Customer §§17, 22 — "do not rebuild what works" — survive the
        consolidation as a promise about *addresses*, not file names: the URL
        in a bookmark or a walkthrough still lands on the surface that does
        the job now. Both halves are checked: the redirect exists, and its
        destination is a route this router actually registers.
        """
        successor = RETIRED_ADMIN_ADDRESSES[path_literal]
        redirects = _read(REDIRECTS)
        assert re.search(
            rf'from:\s*"/{path_literal}"\s*,\s*to:\s*"{re.escape(successor)}"', redirects
        ), f"/{path_literal} no longer resolves; it must redirect to {successor}"

        code = _strip_comments(_read(ROUTES))
        leaf = successor.rsplit("/", 1)[-1]
        assert f'path: "{leaf}"' in code or f'path: "{successor.strip("/")}"' in code, (
            f"/{path_literal} redirects to {successor}, which routes.tsx does not register"
        )


# ---------------------------------------------------------------------------
# Navigation composition
# ---------------------------------------------------------------------------


class TestNavigationComposition:
    """The sidebar advertises only what the product offers.

    The guarantee is the same as it was under the admin ``Layout.tsx``; the
    mechanism is not. That shell carried a capability-filtered section list
    because one of its entries — the cold-outreach page — was gated. The
    Connector shell links nothing out of scope, so there is no filter left to
    assert: what must hold is that every entry it draws resolves to a mounted,
    in-scope successor and that no disabled capability is offered.
    """

    def test_the_connector_shell_offers_no_disabled_capability(self) -> None:
        """The successors, present; the gated page, absent.

        The one nav entry the policy ever had to hide belonged to the retired
        cold-outreach page. The Connector shell's only outreach link is the
        preserved consented ``/v1`` page — so the assertion is that the
        disabled capability names never appear in the shell's code at all.
        """
        code = _strip_comments(_read(CONNECTOR_SHELL))
        assert _COLD not in code and _EXTERNAL not in code, (
            "the Connector shell still declares a need for a disabled capability; "
            "the only entry that needed one is retired"
        )
        assert "isCapabilityEnabled" not in code and "productScope" not in code, (
            "the Connector shell grew a capability gate with nothing gated behind it; "
            "a filter over an all-in-scope list is a claim that something is hidden"
        )

    def test_no_navigation_entry_links_to_the_retired_outreach_page(self) -> None:
        """The shell's outreach link is the consented successor, only.

        The retired top-level ``/outreach`` address still resolves — it
        redirects — but the sidebar must offer the real surface, not the
        forwarding address. An ``href`` on the retired spelling would work and
        still be wrong: it would advertise a URL the product retired rather
        than the page it keeps.
        """
        code = _strip_comments(_read(CONNECTOR_SHELL))
        for entry in re.findall(
            r"\{[^{}]*?href:\s*\"[^\"]*outreach[^\"]*\"[^{}]*?\}", code, flags=re.DOTALL
        ):
            assert 'href: "/coordinator-portal/outreach"' in entry, (
                "a nav item points at an outreach address that is not the consented "
                "coordinator-portal successor"
            )
        assert 'href: "/outreach"' not in code, (
            "a nav entry still carries the retired top-level /outreach address"
        )
        assert 'href: "/coordinator-portal/outreach"' in code, (
            "the consented outreach page lost its navigation entry entirely"
        )

    @pytest.mark.parametrize(
        "retired,successor", sorted(RETIRED_ADMIN_NAV.items())
    )
    def test_preserved_navigation_entries_remain(
        self, retired: str, successor: str
    ) -> None:
        """Every admin-shell nav entry's successor is still in the sidebar.

        The entry moved shells and addresses with the consolidation; what may
        not move is the offer. The sidebar must carry the successor href — and
        each of those destinations is asserted mounted by the route tests
        above, so a linked dead end cannot pass.
        """
        code = _strip_comments(_read(CONNECTOR_SHELL))
        assert f'href: "{successor}"' in code, (
            f"the Connector shell has no nav entry for {successor} "
            f"(the {retired} entry's successor)"
        )


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
