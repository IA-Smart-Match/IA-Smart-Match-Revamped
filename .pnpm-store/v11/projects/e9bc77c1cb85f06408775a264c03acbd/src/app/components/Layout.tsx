import { Outlet, Link, useLocation, useNavigate } from "react-router";
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
  Loader2,
  LogOut,
} from "lucide-react";
import { useState } from "react";
import { ScrollToTop } from "./ScrollToTop";
import { CrawlerProvider, useCrawlerStatus } from "./CrawlerContext";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "./ui/tooltip";

const navigationSections = [
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
      { name: "Opportunities", href: "/opportunities", icon: Briefcase, tooltip: "Browse and filter discovered events" },
      { name: "AI Matching", href: "/ai-matching", icon: Sparkles, tooltip: "Rank specialists against open opportunities" },
      { name: "Outreach", href: "/outreach", icon: Mail, tooltip: "Generate emails, QR assets, and crawler feed" },
    ],
  },
];

const allNavItems = navigationSections.flatMap((s) => s.items);

function CrawlBanner() {
  const { status } = useCrawlerStatus();
  if (status?.state !== "running") return null;
  return (
    <div className="flex items-center gap-2 border-b border-white/10 bg-primary px-4 py-1.5 text-sm text-primary-foreground">
      <Loader2 className="h-3.5 w-3.5 animate-spin" />
      <span>Web crawl in progress…</span>
      <Link to="/outreach" className="ml-auto underline underline-offset-2 hover:no-underline">
        View feed
      </Link>
    </div>
  );
}

export function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  function handleLogout() {
    sessionStorage.removeItem("iaw_session");
    navigate("/login");
  }

  const currentPage = allNavItems.find(
    (item) =>
      location.pathname === item.href ||
      (item.href !== "/dashboard" && location.pathname.startsWith(item.href)),
  );

  return (
    <CrawlerProvider>
    <div className="portal-shell">
      <ScrollToTop />
      {/* Mobile sidebar backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-[#16092d]/50 backdrop-blur-[1px] lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed top-0 left-0 z-50 h-full w-64 transform border-r border-sidebar-border bg-sidebar text-sidebar-foreground shadow-[0_28px_80px_rgba(23,7,54,0.28)] transition-transform duration-200 ease-in-out lg:translate-x-0 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex flex-col h-full">
          <div className="flex items-center justify-end border-b border-white/10 px-5 py-5">
            <button
              onClick={() => setSidebarOpen(false)}
              className="rounded-md p-2 text-sidebar-foreground/80 transition-colors hover:bg-white/10 hover:text-white lg:hidden"
              aria-label="Close sidebar"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 px-4 py-4 space-y-4 overflow-y-auto">
            {navigationSections.map((section, sectionIndex) => (
              <div key={section.label}>
                {sectionIndex > 0 && (
                  <div className="mb-3 mt-1 border-t border-white/10" />
                )}
                <p className="px-3 pb-1 text-[10px] font-semibold tracking-[0.24em] text-white/55">
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
                                ? "bg-white/14 text-white shadow-[0_10px_30px_rgba(15,6,33,0.18)] ring-1 ring-white/10"
                                : "text-white/80 hover:bg-white/10 hover:text-white"
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
          <div className="border-t border-white/10 p-4">
            <div className="flex items-center gap-3 px-3 py-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-white/15 text-sm font-medium text-white">
                IA
              </div>
              <div className="flex-1 min-w-0">
                <p className="truncate text-sm font-medium text-white">
                  IA Admin
                </p>
                <p className="truncate text-xs text-white/65">admin@ia.org</p>
              </div>
              <button
                type="button"
                onClick={handleLogout}
                aria-label="Log out and return to portal login"
                title="Log out"
                className="shrink-0 rounded-lg p-2 text-white/70 transition-colors hover:bg-white/10 hover:text-white"
              >
                <LogOut className="h-4 w-4" aria-hidden />
              </button>
            </div>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="lg:pl-64">
        <CrawlBanner />
        {/* Mobile header */}
        <header className="sticky top-0 z-30 border-b border-white/10 bg-sidebar/96 px-4 py-3 backdrop-blur-xl lg:hidden">
          <div className="flex items-center justify-between">
            <button
              onClick={() => setSidebarOpen(true)}
              className="rounded-md p-2 text-white/80 transition-colors hover:bg-white/10 hover:text-white"
              aria-label="Open sidebar menu"
            >
              <Menu className="w-6 h-6" />
            </button>
            <span className="sr-only">Admin navigation</span>
            <div className="w-6" /> {/* Spacer for centering */}
          </div>
        </header>

        {/* Page title strip (desktop only) */}
        {currentPage && (
          <div className="hidden items-center gap-2.5 border-b border-white/70 bg-white/80 px-8 py-3 backdrop-blur-xl lg:flex">
            <currentPage.icon className="h-4 w-4 text-primary" />
            <span className="text-sm font-medium text-[#3a2857]">{currentPage.name}</span>
          </div>
        )}

        {/* Page content */}
        <main className="p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
    </CrawlerProvider>
  );
}
