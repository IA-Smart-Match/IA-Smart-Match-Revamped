/**
 * The Speaker Portal shell (B26 T6b-4 §2.2) — the fourth signed-in shell.
 *
 * Mounted only while the `speaker_portal` capability is on
 * (`speakerPortalRoutes`). The volunteer shell's structure with the Connector
 * shell's nav accessibility, plus the focus management neither has:
 *
 * - **Two gates, before any chrome.** `SessionGate` while nobody verified is
 *   signed in; `PortalGate` while the server has not granted this account the
 *   `speaker` portal. Both answers come from the server (`GET /v1/me`,
 *   `GET /v1/me/portals`); no role is read here.
 * - **The server's names.** The brand label and the footer name the portal by
 *   the grant's own `display_name`; the unit by its `org_unit_path`.
 * - **Focus.** The mobile menu moves focus to its Close button when it opens
 *   and back to the menu button when Escape, the overlay, Close or a link
 *   closes it. A route change moves focus to the new page's `h1`; the shell's
 *   first render (sign-in, reload) moves nothing.
 * - **Portal switcher (T6b-5).** For a login that also holds the Event Host
 *   role: above the profile block on desktop, so Sign out stays directly
 *   beneath the profile, and in the mobile header's right-hand slot. It
 *   renders nothing with one portal.
 *
 * Route guarding is UX only: every `/v1/me/*` request is authorized
 * server-side, deny-by-default.
 */
import { useEffect, useRef, useState, type RefObject } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { BellRing, CalendarCheck, CalendarX, LayoutDashboard, Mail, Menu, X } from "lucide-react";

import { useSession, useSignOut } from "../hooks/useSession";
import { usePortalAccess } from "../hooks/usePortalAccess";
import { prefetchPortalRoute } from "../navPrefetch";
import { principalDisplayName, principalInitials } from "../../lib/principal";
import { BrandLogo } from "./BrandLogo";
import { PortalGate, grantedPortal } from "./PortalGate";
import { PortalSwitcher } from "./PortalSwitcher";
import { usePrincipalKey } from "./PrincipalQueryProvider";
import { ScrollToTop } from "./ScrollToTop";
import { SessionGate } from "./SessionGate";

const SIDEBAR_ID = "speaker-portal-sidebar";
const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-sidebar";

/** Tailwind's `lg` breakpoint: at and above it the sidebar is always shown. */
const LG_MEDIA_QUERY = "(min-width: 1024px)";

const navigation = [
  { name: "Home", href: "/speaker-portal", icon: LayoutDashboard, exact: true },
  { name: "Invitations", href: "/speaker-portal/invitations", icon: Mail },
  { name: "Engagements", href: "/speaker-portal/engagements", icon: CalendarCheck },
  { name: "Availability", href: "/speaker-portal/availability", icon: CalendarX },
  { name: "Contact preferences", href: "/speaker-portal/contact-preferences", icon: BellRing },
] as const;

/**
 * Moves focus to the new page's `h1` when the pathname changes, and never on
 * the first render. Pages are code-split, so the heading may arrive after the
 * route commits; an observer waits for it rather than guessing a delay. A
 * `?when=` change keeps the pathname, so focus stays where the reader put it.
 */
function useFocusHeadingOnRouteChange(main: RefObject<HTMLElement | null>): void {
  const { pathname } = useLocation();
  // The pathname last acted on, not a first-render flag: StrictMode runs mount
  // effects twice in development, and a flag would focus on the second run.
  const previousPathname = useRef(pathname);

  useEffect(() => {
    if (previousPathname.current === pathname) return undefined;
    previousPathname.current = pathname;
    const container = main.current;
    if (container === null) return undefined;
    const focusHeading = (): boolean => {
      const heading = container.querySelector<HTMLElement>("h1");
      if (heading === null) return false;
      heading.focus();
      return true;
    };
    if (focusHeading()) return undefined;
    const observer = new MutationObserver(() => {
      if (focusHeading()) observer.disconnect();
    });
    observer.observe(container, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [pathname, main]);
}

export function SpeakerPortalLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const mainRef = useRef<HTMLElement>(null);
  const pageRef = useRef<HTMLDivElement>(null);
  // Whether closing the menu should hand focus back to the menu button. A
  // nav link closes it too, and then the route change focuses the new h1.
  const returnFocusRef = useRef(false);

  const session = useSession();
  const portalAccess = usePortalAccess();
  const signOut = useSignOut();
  const queryClient = useQueryClient();
  const principalKey = usePrincipalKey();

  useFocusHeadingOnRouteChange(mainRef);

  // While the drawer is open (below `lg` only: the menu button is hidden at
  // `lg`), the page behind it is `inert`, so Tab cannot reach the menu button
  // or content the drawer covers (2.4.11). React 18 has no `inert` prop.
  useEffect(() => {
    const page = pageRef.current;
    if (page === null) return undefined;
    if (!sidebarOpen) {
      page.removeAttribute("inert");
      return undefined;
    }
    page.setAttribute("inert", "");
    const wide =
      typeof window.matchMedia === "function" ? window.matchMedia(LG_MEDIA_QUERY) : null;
    const onWide = (event: MediaQueryListEvent) => {
      if (event.matches) closeMenu(false);
    };
    wide?.addEventListener("change", onWide);
    return () => {
      wide?.removeEventListener("change", onWide);
      page.removeAttribute("inert");
    };
  }, [sidebarOpen]);

  useEffect(() => {
    if (sidebarOpen) {
      closeButtonRef.current?.focus();
      const onKeyDown = (event: KeyboardEvent) => {
        if (event.key === "Escape") closeMenu(true);
      };
      document.addEventListener("keydown", onKeyDown);
      return () => document.removeEventListener("keydown", onKeyDown);
    }
    if (returnFocusRef.current) {
      returnFocusRef.current = false;
      menuButtonRef.current?.focus();
    }
    return undefined;
  }, [sidebarOpen]);

  function closeMenu(returnFocus: boolean): void {
    returnFocusRef.current = returnFocus;
    setSidebarOpen(false);
  }

  function handleSignOut() {
    signOut();
    navigate("/");
  }

  if (session.status !== "signed-in") {
    return <SessionGate state={session} />;
  }

  const grant = grantedPortal(portalAccess, "speaker");
  if (grant === null) {
    return <PortalGate state={portalAccess} me={session.me} />;
  }

  const unitId = grant.default_unit_id;

  return (
    <div className="min-h-screen bg-background">
      <ScrollToTop />

      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-foreground/50 lg:hidden"
          aria-hidden="true"
          onClick={() => closeMenu(true)}
        />
      )}

      <aside
        id={SIDEBAR_ID}
        className={`fixed left-0 top-0 z-50 h-full w-64 transform border-r border-sidebar-border bg-sidebar text-sidebar-foreground shadow-lg transition-transform duration-200 ease-out motion-reduce:transition-none lg:translate-x-0 ${
          // Closed below `lg`, the drawer is also `invisible`, so its links
          // leave the tab order instead of taking focus off-screen.
          sidebarOpen ? "translate-x-0" : "invisible -translate-x-full lg:visible"
        }`}
      >
        <div className="flex h-full flex-col">
          <div className="flex min-h-[104px] items-center justify-between border-b border-sidebar-border px-5 py-4">
            <BrandLogo label={grant.display_name} />
            <button
              ref={closeButtonRef}
              type="button"
              onClick={() => closeMenu(true)}
              className={`inline-flex min-h-11 min-w-11 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground lg:hidden ${FOCUS_RING}`}
              aria-label="Close navigation"
            >
              <X className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>

          <nav
            className="flex-1 space-y-1 overflow-y-auto px-4 py-6"
            aria-label="Speaker Portal navigation"
          >
            <ul className="space-y-1">
              {navigation.map((item) => {
                const Icon = item.icon;
                const isActive =
                  "exact" in item && item.exact
                    ? location.pathname === item.href
                    : location.pathname === item.href ||
                      location.pathname.startsWith(item.href + "/");
                return (
                  <li key={item.href}>
                    <Link
                      to={item.href}
                      // The current page's link changes no pathname, so no
                      // h1 takes focus: hand it back to the menu button.
                      onClick={() => closeMenu(location.pathname === item.href)}
                      onMouseEnter={() =>
                        prefetchPortalRoute(queryClient, principalKey, unitId, item.href)
                      }
                      onFocus={() =>
                        prefetchPortalRoute(queryClient, principalKey, unitId, item.href)
                      }
                      aria-current={isActive ? "page" : undefined}
                      className={`flex min-h-11 items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-colors duration-150 motion-reduce:transition-none ${FOCUS_RING} ${
                        isActive
                          ? "border border-primary/30 bg-primary/10 text-primary shadow-sm"
                          : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                      }`}
                    >
                      <Icon className="h-5 w-5 shrink-0" aria-hidden="true" />
                      <span className="min-w-0">{item.name}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>

          <div className="border-t border-sidebar-border p-4">
            <div className="hidden lg:block">
              <PortalSwitcher current="speaker" placement="sidebar" />
            </div>
            <div className="flex items-center gap-3 px-3 py-2">
              <div
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-medium text-primary-foreground"
                aria-hidden="true"
              >
                {principalInitials(session.me)}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-sidebar-foreground">
                  {principalDisplayName(session.me)}
                </p>
                <p className="truncate text-xs text-muted-foreground">{grant.org_unit_path}</p>
                <p className="truncate text-xs text-muted-foreground">{grant.display_name}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={handleSignOut}
              className={`mt-2 flex min-h-11 w-full items-center rounded-xl px-3 py-2 text-left text-sm text-muted-foreground transition-colors duration-150 motion-reduce:transition-none hover:bg-sidebar-accent hover:text-sidebar-accent-foreground ${FOCUS_RING}`}
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>

      <div ref={pageRef} className="lg:pl-64">
        <header className="sticky top-0 z-30 border-b border-sidebar-border bg-sidebar px-4 py-3 lg:hidden">
          <div className="flex items-center justify-between">
            <button
              ref={menuButtonRef}
              type="button"
              onClick={() => setSidebarOpen(true)}
              className={`inline-flex min-h-11 min-w-11 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-sidebar-accent ${FOCUS_RING}`}
              aria-label="Open navigation"
              aria-expanded={sidebarOpen}
              aria-controls={SIDEBAR_ID}
            >
              <Menu className="h-6 w-6" aria-hidden="true" />
            </button>
            <BrandLogo compact className="w-[145px]" />
            <div className="flex min-w-11 justify-end">
              <PortalSwitcher current="speaker" placement="header" />
            </div>
          </div>
        </header>

        <main ref={mainRef} className="p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
