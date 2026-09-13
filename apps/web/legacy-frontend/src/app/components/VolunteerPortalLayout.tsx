import { Outlet, Link, useLocation, useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import {
  LayoutDashboard,
  ListChecks,
  UserCircle,
  Briefcase,
  Building2,
  Menu,
  X,
} from "lucide-react";
import { useState } from "react";
import { ScrollToTop } from "./ScrollToTop";
import { SessionGate } from "./SessionGate";
import { PortalGate, grantedPortal } from "./PortalGate";
import { useSession, useSignOut } from "../hooks/useSession";
import { usePortalAccess } from "../hooks/usePortalAccess";
import { prefetchPortalRoute } from "../navPrefetch";
import { usePrincipalKey } from "./PrincipalQueryProvider";
import { principalDisplayName, principalInitials } from "../../lib/principal";
import { BrandLogo } from "./BrandLogo";

// One entry per mounted page — nothing here links a retired address. Two
// entries this sidebar used to carry were removed rather than repointed,
// because their successors are already on this list: "Confirmed speaker" was
// folded into My requests (its only data routes are `admin`/`coordinator`
// server-side, so it answered the hosts it named with a 403), and "My
// Assignments" was folded into Home, which names the absent assignments
// dataset honestly instead of opening a page for it.
const navigation = [
  { name: "Home", href: "/volunteer-portal", icon: LayoutDashboard, exact: true },
  // Customer §12: the Event Host's own capability, backed by a `/v1` route
  // rather than by the absent legacy portal API — as is the page below it.
  // Sentence case per DESIGN.md's navigation rule.
  { name: "Request a speaker", href: "/volunteer-portal/speaker-request", icon: Briefcase },
  // OQ-CBA-014, closed 7 September 2026: the Event Host's own read of what
  // they filed, over `GET .../host/speaker-requests` — `volunteer`-scoped
  // server-side, and a different query from the Connector's queue, not a
  // wider permit on it.
  { name: "My requests", href: "/volunteer-portal/my-requests", icon: ListChecks },
  // Migration `0036`: the host's own organization, self-asserted until a
  // coordinator grant exists (owner decision 4).
  { name: "Organization", href: "/volunteer-portal/organization", icon: Building2 },
  { name: "Profile", href: "/volunteer-portal/profile", icon: UserCircle },
];

export function VolunteerPortalLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const session = useSession();
  // The account-to-portal mapping, from `GET /v1/me/portals`. The shell used
  // to have no way to ask whether this account was actually assigned this
  // portal, which is what the pages inside it rendered a banner about.
  const portalAccess = usePortalAccess();
  const signOut = useSignOut();

  const queryClient = useQueryClient();
  const principalKey = usePrincipalKey();

  function handleSignOut() {
    signOut();
    navigate("/");
  }

  if (session.status !== "signed-in") {
    return <SessionGate state={session} />;
  }

  // Second gate, and a different question from the first: the caller is
  // verified, but did the server grant them *this* portal? Answered by
  // `GET /v1/me/portals` and never by reading a role here — see
  // `lib/principal.ts`'s `portalGrant()`. Route guarding is UX only; `/v1`
  // authorization remains the authority.
  const grant = grantedPortal(portalAccess, "volunteer");
  if (grant === null) {
    return <PortalGate state={portalAccess} me={session.me} />;
  }

  // Every value below comes from `GET /v1/me`. There is no fallback name,
  // company, or id: an unverified visitor never reaches this line.
  const displayName = principalDisplayName(session.me);
  // The unit the granting membership covers, as the server reported it —
  // not whichever active membership `principalOrgUnitLabel` happened to list
  // first, which for an account holding two roles could name the wrong one.
  const company = grant.org_unit_path;
  const initials = principalInitials(session.me);
  // The unit the nav's hover prefetch scopes its reads to — the same
  // `default_unit_id` every page behind these links reads.
  const unitId = grant.default_unit_id;

  return (
    <div className="min-h-screen bg-background">
      <ScrollToTop />

      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-foreground/50 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside
        className={`fixed left-0 top-0 z-50 h-full w-64 transform border-r border-sidebar-border bg-sidebar text-sidebar-foreground shadow-lg transition-transform duration-200 ease-in-out lg:translate-x-0 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-full flex-col">
          {/* Logo */}
          <div className="flex min-h-[104px] items-center justify-between border-b border-sidebar-border px-5 py-4">
            {/* The portal descriptor's own `display_name` ("Event Host
                Portal") — the server names this shell, the way it names the
                Connector Dashboard for the coordinator grant. A literal here
                was how this sidebar came to call event hosts "speakers". */}
            <BrandLogo label={grant.display_name} />
            <button
              onClick={() => setSidebarOpen(false)}
              className="rounded-md p-2 text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground lg:hidden"
              aria-label="Close sidebar"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 space-y-1 overflow-y-auto px-4 py-6">
            {navigation.map((item) => {
              const Icon = item.icon;
              const isActive = item.exact
                ? location.pathname === item.href
                : location.pathname === item.href || location.pathname.startsWith(item.href + "/");

              return (
                <Link
                  key={item.name}
                  to={item.href}
                  onClick={() => setSidebarOpen(false)}
                  onMouseEnter={() =>
                    prefetchPortalRoute(queryClient, principalKey, unitId, item.href)
                  }
                  onFocus={() =>
                    prefetchPortalRoute(queryClient, principalKey, unitId, item.href)
                  }
                  className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors ${
                    isActive
                      ? "border border-primary/30 bg-primary/10 text-primary shadow-sm"
                      : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                  }`}
                >
                  <Icon className="h-5 w-5" />
                  <span>{item.name}</span>
                </Link>
              );
            })}
          </nav>

          {/* Footer */}
          <div className="border-t border-sidebar-border p-4">
            <div className="flex items-center gap-3 px-3 py-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-sm font-medium text-primary-foreground">
                {initials}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-sidebar-foreground">{displayName}</p>
                <p className="truncate text-xs text-muted-foreground">{company}</p>
                <p className="truncate text-xs text-muted-foreground">{grant.display_name}</p>
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
              className="rounded-md p-2 text-muted-foreground transition-colors hover:bg-sidebar-accent"
              aria-label="Open sidebar menu"
            >
              <Menu className="h-6 w-6" />
            </button>
            <BrandLogo compact className="w-[145px]" />
            <div className="w-6" />
          </div>
        </header>

        <main className="p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
