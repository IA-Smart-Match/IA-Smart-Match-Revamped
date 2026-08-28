import { Outlet, Link, useLocation, useNavigate } from "react-router";
import {
  LayoutDashboard,
  CalendarDays,
  Mail,
  Video,
  Building,
  Menu,
  X,
} from "lucide-react";
import { useState } from "react";
import { ScrollToTop } from "./ScrollToTop";
import { BrandLogo } from "./BrandLogo";

const navigation = [
  { name: "Home", href: "/coordinator-portal", icon: LayoutDashboard, exact: true },
  { name: "My Events", href: "/coordinator-portal/events", icon: CalendarDays },
  { name: "IA West Contact", href: "/coordinator-portal/outreach", icon: Mail },
  { name: "Meetings", href: "/coordinator-portal/meetings", icon: Video },
];

export function CoordinatorPortalLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const session = (() => {
    try {
      return JSON.parse(sessionStorage.getItem("iaw_session") ?? "{}") as {
        user?: Record<string, unknown>;
        role?: string;
      };
    } catch {
      return {};
    }
  })();

  const user = session.user ?? {};
  const displayName = String(user.name ?? "Coordinator");
  const school = String(user.school ?? "IA West");
  const initials = displayName
    .split(" ")
    .map((n) => n[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  function handleSignOut() {
    sessionStorage.removeItem("iaw_session");
    navigate("/");
  }

  return (
    <div className="portal-shell">
      <ScrollToTop />

      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-[#16092d]/50 backdrop-blur-[1px] lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside
        className={`fixed left-0 top-0 z-50 h-full w-64 transform border-r border-sidebar-border bg-sidebar text-sidebar-foreground shadow-[0_28px_80px_rgba(23,7,54,0.28)] transition-transform duration-200 ease-in-out lg:translate-x-0 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-full flex-col">
          {/* Logo */}
          <div className="flex items-center justify-between border-b border-white/10 px-5 py-5">
            <BrandLogo
              href="/coordinator-portal"
              direction="column"
              caption="Event Coordinator"
              subcaption="Insights Association"
              imageClassName="h-8"
              textClassName="text-white"
            />
            <button
              onClick={() => setSidebarOpen(false)}
              className="rounded-md p-2 text-white/80 transition-colors hover:bg-white/10 hover:text-white lg:hidden"
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
                  className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-white/14 text-white shadow-[0_10px_30px_rgba(15,6,33,0.18)] ring-1 ring-white/10"
                      : "text-white/80 hover:bg-white/10 hover:text-white"
                  }`}
                >
                  <Icon className="h-5 w-5" />
                  <span>{item.name}</span>
                </Link>
              );
            })}
          </nav>

          {/* Footer */}
          <div className="border-t border-white/10 p-4">
            <div className="flex items-center gap-3 px-3 py-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-white/15 text-sm font-medium text-white">
                {initials}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-white">{displayName}</p>
                <p className="truncate text-xs text-white/65">{school}</p>
              </div>
            </div>
            <button
              onClick={handleSignOut}
              className="mt-2 w-full rounded-xl px-3 py-2 text-left text-sm text-white/70 transition-colors hover:bg-white/10 hover:text-white"
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="lg:pl-64">
        {/* Mobile header */}
        <header className="sticky top-0 z-30 border-b border-white/10 bg-sidebar/96 px-4 py-3 backdrop-blur-xl lg:hidden">
          <div className="flex items-center justify-between">
            <button
              onClick={() => setSidebarOpen(true)}
              className="rounded-md p-2 text-white/80 transition-colors hover:bg-white/10 hover:text-white"
              aria-label="Open sidebar menu"
            >
              <Menu className="h-6 w-6" />
            </button>
            <BrandLogo
              href="/coordinator-portal"
              direction="row"
              caption="Event Coordinator"
              subcaption="Insights Association"
              imageClassName="h-6"
              textClassName="text-white"
            />
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
