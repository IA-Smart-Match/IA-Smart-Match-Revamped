/**
 * The Connector Dashboard shell — **one shell, two stored roles**.
 *
 * ## What changed, and why there used to be two
 *
 * A Speaker Connector's work was split across two parallel shells. This one
 * held the `/v1`-backed coordinator pages; a second, `components/Layout.tsx`,
 * held `/dashboard`, `/opportunities`, `/events`, `/volunteers`,
 * `/ai-matching`, `/pipeline`, `/calendar` and `/outreach`, was reachable only
 * by the stored `admin` role, and — the part that mattered — had **no sign-out
 * control at all**. An administrator who wanted to leave had to clear storage.
 *
 * The two shells were never two jobs. `role_presentation.py` maps `admin` and
 * `coordinator` onto the same persona, the Speaker Connector, and the customer
 * confirmed it: one persona, one account, one dashboard. So `Layout.tsx` is
 * gone, its eight addresses redirect here (`app/legacyRedirects.ts`), and both
 * stored roles land on this shell with the same brand, the same groups, and
 * the same sign-out.
 *
 * The single difference between the two roles is the **Administration** group,
 * drawn only for an account holding an active `admin` membership
 * (`lib/roles.ts`'s `hasActiveRole`). That is a visibility decision about which
 * doors are worth offering, not an access decision: `/v1` is deny-by-default
 * and tenant-scoped, per route, per request, against the stored role, whatever
 * this sidebar draws. Hiding a link removes a claim, never a path.
 *
 * ## Two gates, two different questions
 *
 * `SessionGate` asks whether anybody is signed in. `grantedPortal(access,
 * "coordinator")` asks whether the server granted *this* account *this*
 * portal, from `GET /v1/me/portals` and never from a role read here — see
 * `lib/principal.ts`'s `portalGrant()` on why the browser must not re-derive
 * that mapping. Both stored roles resolve to the `coordinator` portal
 * descriptor, so both pass the same gate and read the same `display_name`
 * ("Connector Dashboard") out of the one role-presentation map. The brand on
 * screen is therefore the server's own answer, not a literal chosen here.
 *
 * The unit every page in this shell scopes itself to is that descriptor's
 * `default_unit_id`, for both roles. There is no longer an `admin` portal to
 * look up, and nothing in this shell asks for one.
 *
 * ## The two counts, and what they are careful not to claim
 *
 * Two nav entries carry a count: Speaker requests and Review queue. Both are
 * the **length of the list the reader would see on clicking through**, read
 * from the same route that page reads, so the badge and the page can never
 * disagree. Three rules keep them honest:
 *
 *  - **No badge until the list has loaded.** Not a zero, not a dash, not a
 *    skeleton pretending to be a number. "We have not asked yet" is not "there
 *    are none" (ADR-0011 rule 1), and a `0` that later becomes `7` is the
 *    worst of the three because the reader has already decided not to look.
 *  - **A failed read draws no badge either**, for the same reason. The page
 *    behind the link renders the server's refusal in full; the sidebar is not
 *    the place to litigate it.
 *  - **A truncated list reads `N+`.** The server caps both responses and says
 *    so. Printing the cap as though it were the total would be this shell
 *    inventing a figure, so the `+` carries the fact that there are more.
 *
 * Each badge has its own `aria-label` spelling the count out in words, because
 * "Speaker requests 7" read aloud is ambiguous between a count and a name.
 *
 * ## Not authorization, restated where it matters
 *
 * Every page this sidebar links to is authorized server-side per request. The
 * links are visible to everyone this portal is granted to, and each page shows
 * the server's refusal as the answer it is rather than hiding its controls and
 * implying the capability is absent.
 */
import { Outlet, Link, useLocation, useNavigate } from "react-router";
import type { LucideIcon } from "lucide-react";
import {
  LayoutDashboard,
  Inbox,
  ClipboardCheck,
  CalendarDays,
  Target,
  Send,
  Video,
  Users,
  Mail,
  SlidersHorizontal,
  Menu,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";

import { fetchReviewItems, fetchSpeakerRequests } from "@/lib/api";
import { hasActiveRole } from "@/lib/roles";

import { ScrollToTop } from "./ScrollToTop";
import { SessionGate } from "./SessionGate";
import { PortalGate, grantedPortal } from "./PortalGate";
import { useSession, useSignOut } from "../hooks/useSession";
import { usePortalAccess } from "../hooks/usePortalAccess";
import { principalDisplayName, principalInitials } from "../../lib/principal";
import { BrandLogo } from "./BrandLogo";

/**
 * A count the sidebar may draw, or the honest absence of one.
 *
 * `null` covers loading *and* failure deliberately: the sidebar's answer to
 * both is the same — draw nothing — and collapsing them here keeps any caller
 * from accidentally rendering a placeholder for one of them.
 */
interface NavCount {
  readonly value: number;
  /** The server stopped sending before the end, so the real total is higher. */
  readonly atLeast: boolean;
}

interface NavItem {
  readonly name: string;
  readonly href: string;
  readonly icon: LucideIcon;
  /** Matched by equality rather than prefix. Only Home needs it. */
  readonly exact?: boolean;
  readonly count?: NavCount | null;
  /** Spoken form of the count, e.g. "7 speaker requests filed". */
  readonly countLabel?: (count: NavCount) => string;
}

interface NavGroup {
  readonly label: string;
  readonly items: readonly NavItem[];
}

/**
 * The two counts, read from the routes the pages behind them read.
 *
 * Plain `useEffect` rather than the shared query cache, matching every page in
 * this shell (`CoordinatorEvents`, `CoordinatorReviewQueue`): the shell mounts
 * once when the portal is entered and stays mounted across every child route,
 * so this is two requests per visit, not two per navigation.
 *
 * A failure is swallowed *here and only here*. The sidebar's job is to offer
 * the link; the page behind it owns reporting why its own read failed, and it
 * does so in full. A shell that rendered an error banner for a badge would put
 * the same failure on screen twice and make the navigation unusable for a
 * reader who only wanted a different page.
 */
function useInboxCounts(unitId: string | null) {
  const [speakerRequests, setSpeakerRequests] = useState<NavCount | null>(null);
  const [reviewItems, setReviewItems] = useState<NavCount | null>(null);

  useEffect(() => {
    if (unitId === null) {
      setSpeakerRequests(null);
      setReviewItems(null);
      return;
    }

    let cancelled = false;

    void fetchSpeakerRequests(unitId)
      .then((listing) => {
        if (!cancelled) {
          setSpeakerRequests({ value: listing.requests.length, atLeast: listing.truncated });
        }
      })
      .catch(() => {
        // No badge. See the note above: the page owns this failure.
        if (!cancelled) setSpeakerRequests(null);
      });

    void fetchReviewItems(unitId, "pending")
      .then((listing) => {
        if (!cancelled) {
          setReviewItems({ value: listing.items.length, atLeast: listing.truncated });
        }
      })
      .catch(() => {
        if (!cancelled) setReviewItems(null);
      });

    return () => {
      cancelled = true;
    };
  }, [unitId]);

  return { speakerRequests, reviewItems };
}

/**
 * The count chip.
 *
 * Not colour-coded. A count is not a status, and `DESIGN.md` forbids carrying
 * meaning in colour alone in any case — the number *is* the information, and a
 * red chip would read as an alarm this shell has no basis to raise.
 */
function CountBadge({ count, label }: { count: NavCount; label: string }) {
  return (
    <span
      aria-label={label}
      className="ml-auto inline-flex min-w-[1.5rem] shrink-0 items-center justify-center rounded-full border border-border bg-muted px-1.5 py-0.5 text-xs font-semibold tabular-nums text-foreground"
    >
      {/* `aria-hidden` on the glyph: the label above already says it in words,
          and without this a screen reader announces the number twice. */}
      <span aria-hidden="true">
        {count.value}
        {count.atLeast ? "+" : ""}
      </span>
    </span>
  );
}

export function CoordinatorPortalLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const session = useSession();
  const portalAccess = usePortalAccess();
  const signOut = useSignOut();

  const grant = grantedPortal(portalAccess, "coordinator");
  const { speakerRequests, reviewItems } = useInboxCounts(grant?.default_unit_id ?? null);

  function handleSignOut() {
    signOut();
    navigate("/");
  }

  if (session.status !== "signed-in") {
    return <SessionGate state={session} />;
  }

  if (grant === null) {
    return <PortalGate state={portalAccess} me={session.me} />;
  }

  // `GET /v1/me`'s membership rows, not a role inferred from the portal grant.
  // The grant says which shell; this says which group inside it.
  const isAdministrator = hasActiveRole(session.me, "admin");

  const groups: readonly NavGroup[] = [
    {
      label: "Inbox",
      items: [
        { name: "Home", href: "/coordinator-portal", icon: LayoutDashboard, exact: true },
        {
          name: "Speaker requests",
          href: "/coordinator-portal/speaker-requests",
          icon: Inbox,
          count: speakerRequests,
          countLabel: (count) =>
            count.atLeast
              ? `More than ${count.value} speaker requests filed`
              : `${count.value} speaker requests filed`,
        },
        {
          name: "Review queue",
          href: "/coordinator-portal/review-queue",
          icon: ClipboardCheck,
          count: reviewItems,
          countLabel: (count) =>
            count.atLeast
              ? `More than ${count.value} items waiting for review`
              : `${count.value} items waiting for review`,
        },
      ],
    },
    {
      label: "Coordinate",
      items: [
        { name: "Events", href: "/coordinator-portal/events", icon: CalendarDays },
        { name: "Run a match", href: "/coordinator-portal/match-runs", icon: Target },
        { name: "Invitations", href: "/coordinator-portal/invitations", icon: Send },
        { name: "Meetings", href: "/coordinator-portal/meetings", icon: Video },
      ],
    },
    {
      label: "People",
      items: [
        // Customer §13's roster of professionals this unit knows — who a
        // speaker is. Distinct from "Contact channels" below, which is the
        // consented outreach record over `contact_channel`.
        { name: "Speakers", href: "/coordinator-portal/speaker-contacts", icon: Users },
        { name: "Contact channels", href: "/coordinator-portal/outreach", icon: Mail },
      ],
    },
    // Drawn only for an account holding an active `admin` membership. The
    // group carries Matching weights alone: the import-review surface is the
    // Review queue in the Inbox above, and there is no separate imports page
    // to link to, so none is invented here.
    ...(isAdministrator
      ? [
          {
            label: "Administration",
            items: [
              {
                name: "Matching weights",
                href: "/coordinator-portal/matching-weights",
                icon: SlidersHorizontal,
              },
            ],
          } satisfies NavGroup,
        ]
      : []),
  ];

  const displayName = principalDisplayName(session.me);
  // The unit the granting membership covers, as the server reported it — not
  // whichever active membership happened to be listed first, which for an
  // account holding two roles could name the wrong one.
  const school = grant.org_unit_path;
  const initials = principalInitials(session.me);

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
        /* `transition-transform`, never `transition: all`, and disabled under
           `prefers-reduced-motion` — the drawer still opens, it just arrives
           rather than slides. No information depends on the movement. */
        className={`fixed left-0 top-0 z-50 h-full w-64 transform border-r border-sidebar-border bg-sidebar text-sidebar-foreground shadow-lg transition-transform duration-200 ease-out motion-reduce:transition-none lg:translate-x-0 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-full flex-col">
          <div className="flex min-h-[104px] items-center justify-between border-b border-sidebar-border px-5 py-4">
            {/* "Connector Dashboard" — the coordinator portal descriptor's own
                `display_name`, which both stored roles now resolve to through
                the one role-presentation map. Read from the server rather than
                written here so the shell cannot drift from what
                `/v1/me/portals` calls it. */}
            <BrandLogo label={grant.display_name} />
            <button
              onClick={() => setSidebarOpen(false)}
              className="rounded-md p-2 text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground lg:hidden"
              aria-label="Close sidebar"
            >
              <X className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>

          <nav
            className="flex-1 space-y-5 overflow-y-auto px-4 py-6"
            aria-label="Connector Dashboard navigation"
          >
            {groups.map((group) => (
              <div key={group.label}>
                <h2 className="px-3 pb-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                  {group.label}
                </h2>
                <ul className="space-y-1">
                  {group.items.map((item) => {
                    const Icon = item.icon;
                    const isActive = item.exact
                      ? location.pathname === item.href
                      : location.pathname === item.href ||
                        location.pathname.startsWith(item.href + "/");

                    return (
                      <li key={item.name}>
                        <Link
                          to={item.href}
                          onClick={() => setSidebarOpen(false)}
                          aria-current={isActive ? "page" : undefined}
                          /* `min-h-[40px]`: a nav row is a pointer target and
                             must stay comfortably hittable however the label
                             wraps. */
                          className={`flex min-h-[40px] items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-colors duration-150 motion-reduce:transition-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-sidebar ${
                            isActive
                              ? "border border-primary/30 bg-primary/10 text-primary shadow-sm"
                              : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                          }`}
                        >
                          <Icon className="h-5 w-5 shrink-0" aria-hidden="true" />
                          <span className="min-w-0">{item.name}</span>
                          {/* No badge while the list is loading and none if it
                              failed: a zero here would be a claim the server
                              never made. */}
                          {item.count && item.countLabel && (
                            <CountBadge count={item.count} label={item.countLabel(item.count)} />
                          )}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </nav>

          <div className="border-t border-sidebar-border p-4">
            <div className="flex items-center gap-3 px-3 py-2">
              <div
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-medium text-primary-foreground"
                aria-hidden="true"
              >
                {initials}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-sidebar-foreground">
                  {displayName}
                </p>
                <p className="truncate text-xs text-muted-foreground">{school}</p>
              </div>
            </div>
            <button
              onClick={handleSignOut}
              className="mt-2 flex min-h-[40px] w-full items-center rounded-xl px-3 py-2 text-left text-sm text-muted-foreground transition-colors duration-150 motion-reduce:transition-none hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-sidebar"
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>

      <div className="lg:pl-64">
        <header className="sticky top-0 z-30 border-b border-sidebar-border bg-sidebar px-4 py-3 lg:hidden">
          <div className="flex items-center justify-between">
            <button
              onClick={() => setSidebarOpen(true)}
              className="rounded-md p-2 text-muted-foreground transition-colors hover:bg-sidebar-accent"
              aria-label="Open sidebar menu"
              aria-expanded={sidebarOpen}
            >
              <Menu className="h-6 w-6" aria-hidden="true" />
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
