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
} from "lucide-react";
import { useState } from "react";
import { ScrollToTop } from "./ScrollToTop";
import { BrandLogo } from "./BrandLogo";
import { SyntheticDataBanner } from "./provenance";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "./ui/tooltip";

const navigationSections = [
  {
    label: "MANAGE",
    items: [
      { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard, tooltip: "Overview of events and volunteer coverage" },
      { name: "Volunteers", href: "/volunteers", icon: Users, tooltip: "Volunteer profiles, assignments, and availability" },
      { name: "Match progress", href: "/pipeline", icon: TrendingUp, tooltip: "Follow each match from introduction to event" },
      { name: "Calendar", href: "/calendar", icon: CalendarDays, tooltip: "View and manage event assignments" },
    ],
  },
  {
    label: "DISCOVER",
    items: [
      { name: "Opportunities", href: "/opportunities", icon: Briefcase, tooltip: "Browse and filter discovered events" },
      { name: "Find matches", href: "/ai-matching", icon: Sparkles, tooltip: "Compare volunteers with open opportunities" },
      { name: "Outreach", href: "/outreach", icon: Mail, tooltip: "Generate outreach emails and QR assets" },
    ],
  },
];

export function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  function handleSignOut() {
    sessionStorage.removeItem("iaw_session");
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
            <BrandLogo label="Smart Match administration" />
            <button
              onClick={() => setSidebarOpen(false)}
              className="rounded-md p-2 text-[#59665f] transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground lg:hidden"
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
                <p className="px-3 pb-1 text-[10px] font-semibold tracking-[0.2em] text-[#59665f]">
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
                                ? "border border-primary/20 bg-primary/10 text-primary shadow-sm"
                                : "text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
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
                <p className="truncate text-xs text-[#59665f]">admin@ia.org</p>
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
              className="rounded-md p-2 text-[#59665f] transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
              aria-label="Open sidebar menu"
            >
              <Menu className="w-6 h-6" />
            </button>
            <div className="flex items-center gap-2">
              <BrandLogo compact className="w-[145px]" />
            </div>
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
