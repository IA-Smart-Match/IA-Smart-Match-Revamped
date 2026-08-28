import { Outlet, Link, useLocation } from "react-router";
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
    <div className="flex items-center gap-2 bg-blue-600 px-4 py-1.5 text-sm text-white">
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
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const currentPage = allNavItems.find(
    (item) =>
      location.pathname === item.href ||
      (item.href !== "/dashboard" && location.pathname.startsWith(item.href)),
  );

  return (
    <CrawlerProvider>
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
                <p className="text-xs text-[#5a6472]">IA West Chapter</p>
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
            {navigationSections.map((section, sectionIndex) => (
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
        <CrawlBanner />
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
          <Outlet />
        </main>
      </div>
    </div>
    </CrawlerProvider>
  );
}
