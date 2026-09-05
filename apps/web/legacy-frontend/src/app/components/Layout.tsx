import { Outlet, Link, useLocation } from "react-router";
import type { LucideIcon } from "lucide-react";
import {
  LayoutDashboard,
  Briefcase,
  Users,
  Sparkles,
  TrendingUp,
  CalendarDays,
  Mail,
  Menu,
  X,
} from "lucide-react";
import { useState } from "react";
import { ScrollToTop } from "./ScrollToTop";
import { SessionGate } from "./SessionGate";
import { useSession } from "../hooks/useSession";
import { SyntheticDataBanner } from "./provenance";
import { isCapabilityEnabled, type Capability } from "@/lib/productScope";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "./ui/tooltip";

/**
 * A navigation entry, and the capabilities the product must offer before it is
 * honest to show one.
 *
 * `requires` is read against the shared policy (`src/lib/productScope.ts`,
 * mirroring `smartmatch_domain.product_scope`) — the same named decisions the
 * router and the API composition read, so "which product is this" is answered
 * once and consulted rather than restated in each place.
 *
 * Hiding a link removes a *claim*, not an access path: `/v1` stays
 * deny-by-default and tenant-scoped whatever this sidebar shows. What it buys
 * is that the product stops advertising a page the customer put out of scope
 * (customer §20).
 */
interface NavItem {
  readonly name: string;
  readonly href: string;
  readonly icon: LucideIcon;
  readonly tooltip: string;
  /** Every capability must be enabled. Omitted means "always offered". */
  readonly requires?: readonly Capability[];
}

/**
 * The legacy admin Outreach page needs both: it reaches unknown university
 * contacts through the legacy `/api/data/*` reads, and it embeds the retired
 * external-discovery `CrawlerFeed`. Kept in step with `routes.tsx`, which
 * gates the route itself on the same pair — a nav entry pointing at a route
 * the router does not have would be a dead link rather than a gate.
 */
const LEGACY_COLD_OUTREACH_CAPABILITIES: readonly Capability[] = [
  "cold_unknown_contact_outreach",
  "external_speaker_acquisition",
];

const navigationSections: readonly { label: string; items: readonly NavItem[] }[] = [
  {
    label: "MANAGE",
    items: [
      { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard, tooltip: "Overview of metrics and pipeline health" },
      { name: "Volunteers", href: "/volunteers", icon: Users, tooltip: "Specialist roster and engagement metrics" },
      { name: "Pipeline", href: "/pipeline", icon: TrendingUp, tooltip: "Track matches through each stage" },
      { name: "Calendar", href: "/calendar", icon: CalendarDays, tooltip: "View and manage event assignments" },
    ],
  },
  {
    label: "DISCOVER",
    items: [
      { name: "Speaker Requests", href: "/opportunities", icon: Briefcase, tooltip: "Browse and filter discovered events" },
      { name: "AI Matching", href: "/ai-matching", icon: Sparkles, tooltip: "Rank speakers against open speaker requests" },
      // CBA-TERMINOLOGY owns the wording here; this card owns the `requires`.
      // The two are orthogonal on purpose: renaming a label must never change
      // what the product offers, and gating a capability must never depend on
      // how its entry happens to be spelled.
      {
        name: "Outreach",
        href: "/outreach",
        icon: Mail,
        tooltip: "Generate outreach emails and QR assets",
        requires: LEGACY_COLD_OUTREACH_CAPABILITIES,
      },
    ],
  },
];

/**
 * The sections this product actually offers.
 *
 * Computed once at module load, from the settings the build was composed with,
 * for the same reason `main.py` mounts routers once at import: a menu that
 * changed shape per render would be a different product on every paint, and
 * the page title lookup below would disagree with the sidebar beside it.
 *
 * A section whose every item is gated is dropped entirely rather than rendered
 * as an empty heading — a lone "DISCOVER" label above nothing still advertises
 * a capability, just less legibly.
 */
const offeredSections = navigationSections
  .map((section) => ({
    ...section,
    items: section.items.filter((item) => (item.requires ?? []).every(isCapabilityEnabled)),
  }))
  .filter((section) => section.items.length > 0);

const allNavItems = offeredSections.flatMap((s) => s.items);

export function Layout() {
  const location = useLocation();
  const session = useSession();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const currentPage = allNavItems.find(
    (item) =>
      location.pathname === item.href ||
      (item.href !== "/dashboard" && location.pathname.startsWith(item.href)),
  );

  // The admin shell is a signed-in surface (it carries a sign-out control),
  // so it is gated exactly like the three portals: no verified principal,
  // no chrome. `/v1` authorization stays authoritative for the data itself.
  if (session.status !== "signed-in") {
    return <SessionGate state={session} />;
  }

  return (
    <div className="min-h-screen bg-background">
      <ScrollToTop />
      {/* Mobile sidebar backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed top-0 left-0 z-50 h-full w-64 transform border-r border-sidebar-border bg-sidebar text-sidebar-foreground shadow-[0_20px_60px_rgba(15,23,42,0.08)] transition-transform duration-200 ease-in-out lg:translate-x-0 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="flex items-center justify-between border-b border-sidebar-border p-6">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
                <Sparkles className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="font-semibold text-sidebar-foreground">Smart Match</h1>
                <p className="text-xs text-[#5a6472]">CBA</p>
              </div>
            </div>
            <button
              onClick={() => setSidebarOpen(false)}
              className="rounded-md p-2 text-[#5a6472] transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground lg:hidden"
              aria-label="Close sidebar"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 px-4 py-4 space-y-4 overflow-y-auto">
            {offeredSections.map((section, sectionIndex) => (
              <div key={section.label}>
                {sectionIndex > 0 && (
                  <div className="mb-3 mt-1 border-t border-sidebar-border" />
                )}
                <p className="px-3 pb-1 text-[10px] font-semibold tracking-[0.2em] text-[#5a6472]">
                  {section.label}
                </p>
                <div className="space-y-1">
                  {section.items.map((item) => {
                    const Icon = item.icon;
                    const isActive =
                      location.pathname === item.href ||
                      (item.href !== "/dashboard" &&
                        location.pathname.startsWith(item.href));

                    return (
                      <Tooltip key={item.name}>
                        <TooltipTrigger asChild>
                          <Link
                            to={item.href}
                            onClick={() => setSidebarOpen(false)}
                            className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors ${
                              isActive
                                ? "border border-[#c9d9ee] bg-[#eef4ff] text-[#005394] shadow-sm"
                                : "text-[#394454] hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                            }`}
                          >
                            <Icon className="w-5 h-5" />
                            <span>{item.name}</span>
                          </Link>
                        </TooltipTrigger>
                        <TooltipContent side="right" sideOffset={8}>
                          {item.tooltip}
                        </TooltipContent>
                      </Tooltip>
                    );
                  })}
                </div>
              </div>
            ))}
          </nav>

          {/* Footer */}
          <div className="border-t border-sidebar-border p-4">
            <div className="flex items-center gap-3 px-3 py-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-sm font-medium text-primary-foreground">
                IA
              </div>
              <div className="flex-1 min-w-0">
                <p className="truncate text-sm font-medium text-sidebar-foreground">
                  IA Admin
                </p>
                <p className="truncate text-xs text-[#5a6472]">admin@ia.org</p>
              </div>
            </div>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="lg:pl-64">
        {/* Mobile header */}
        <header className="sticky top-0 z-30 border-b border-sidebar-border bg-sidebar px-4 py-3 lg:hidden">
          <div className="flex items-center justify-between">
            <button
              onClick={() => setSidebarOpen(true)}
              className="rounded-md p-2 text-[#5a6472] transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
              aria-label="Open sidebar menu"
            >
              <Menu className="w-6 h-6" />
            </button>
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <Sparkles className="w-5 h-5 text-white" />
              </div>
              <span className="font-semibold text-sidebar-foreground">Smart Match</span>
            </div>
            <div className="w-6" /> {/* Spacer for centering */}
          </div>
        </header>

        {/* Page title strip (desktop only) */}
        {currentPage && (
          <div className="hidden lg:flex items-center gap-2.5 border-b border-sidebar-border bg-white px-8 py-3">
            <currentPage.icon className="h-4 w-4 text-[#005394]" />
            <span className="text-sm font-medium text-[#394454]">{currentPage.name}</span>
          </div>
        )}

        {/* Page content */}
        <main className="p-6 lg:p-8">
          <SyntheticDataBanner
            className="mb-6"
            reason="This preview runs on copied legacy screens and fixture-backed /api routes. It is development-only and not the product."
          />
          <Outlet />
        </main>
      </div>
    </div>
  );
}
