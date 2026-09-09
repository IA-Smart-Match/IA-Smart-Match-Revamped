import { Outlet, Link, useLocation, useNavigate } from "react-router";
import {
  LayoutDashboard,
  Users,
  CalendarDays,
  ClipboardList,
  Menu,
  X,
} from "lucide-react";
import { useState } from "react";
import { ScrollToTop } from "./ScrollToTop";
import { SessionGate } from "./SessionGate";
import { useSession, useSignOut } from "../hooks/useSession";
import { SyntheticDataBanner } from "./provenance";
import { principalDisplayName, principalInitials } from "../../lib/principal";
import { BrandLogo } from "./BrandLogo";
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
const navigationSections = [
  {
    label: "MANAGE",
    items: [
      { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard, tooltip: "Overview of metrics and pipeline health" },
      { name: "Events", href: "/events", icon: CalendarDays, tooltip: "Create and publish events" },
      { name: "Speakers", href: "/volunteers", icon: Users, tooltip: "Manage the available speaker roster" },
      { name: "Invitations", href: "/outreach", icon: ClipboardList, tooltip: "Track speaker invitations" },
      { name: "Calendar", href: "/calendar", icon: CalendarDays, tooltip: "View and manage event assignments" },
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
const offeredSections = navigationSections;

export function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const session = useSession();
  const signOut = useSignOut();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // The admin shell is a signed-in surface (it carries a sign-out control),
  // so it is gated exactly like the three portals: no verified principal,
  // no chrome. `/v1` authorization stays authoritative for the data itself.
  if (session.status !== "signed-in") {
    return <SessionGate state={session} />;
  }

  const displayName = principalDisplayName(session.me);
  const initials = principalInitials(session.me);

  function handleSignOut() {
    signOut();
    navigate("/");
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
          <div className="flex min-h-[104px] items-center justify-between border-b border-sidebar-border px-5 py-4">
            <BrandLogo label="Speaker Connector" />
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
                {initials}
              </div>
              <div className="flex-1 min-w-0">
                <p className="truncate text-sm font-medium text-sidebar-foreground">
                  {displayName}
                </p>
                <p className="truncate text-xs text-[#5a6472]">Speaker Connector</p>
              </div>
            </div>
            <button
              onClick={handleSignOut}
              className="mt-2 w-full rounded-xl px-3 py-2 text-left text-sm text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
            >
              Sign out
            </button>
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
            <BrandLogo compact className="w-[145px]" />
            <div className="w-6" /> {/* Spacer for centering */}
          </div>
        </header>

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
