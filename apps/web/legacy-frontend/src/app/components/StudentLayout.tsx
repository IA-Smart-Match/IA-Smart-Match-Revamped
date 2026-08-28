import { Outlet, Link, useLocation, useNavigate } from "react-router";
import {
  House,
  CalendarDays,
  ClipboardCheck,
  Users,
  GraduationCap,
  Menu,
  X,
  Gift,
} from "lucide-react";
import { useState } from "react";
import { ScrollToTop } from "./ScrollToTop";

const navigation = [
  { name: "Home", href: "/student-portal", icon: House, exact: true },
  { name: "My Events", href: "/student-portal/events", icon: CalendarDays },
  { name: "Past Events", href: "/student-portal/history", icon: ClipboardCheck },
  { name: "Connect", href: "/student-portal/connect", icon: Users },
  { name: "Rewards", href: "/student-portal/rewards", icon: Gift },
];

export function StudentLayout() {
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
  const displayName = String(user.name ?? "Student");
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
          <div className="flex items-center justify-between border-b border-sidebar-border p-6">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
                <GraduationCap className="h-6 w-6" />
              </div>
              <div>
                <h1 className="font-semibold text-sidebar-foreground">Smart Match</h1>
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">
                  Student Portal
                </p>
              </div>
            </div>
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
                <p className="truncate text-xs text-muted-foreground">{school}</p>
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
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <GraduationCap className="h-5 w-5" />
              </div>
              <span className="font-semibold text-sidebar-foreground">Student Portal</span>
            </div>
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
