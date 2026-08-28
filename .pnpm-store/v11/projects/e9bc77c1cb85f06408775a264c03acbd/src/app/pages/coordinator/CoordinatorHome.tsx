import { useState, useEffect } from "react";
import { Link } from "react-router";
import { AlertTriangle } from "lucide-react";
import { Skeleton } from "../../components/ui/skeleton";
import { DemoModeBadge } from "../../components/ui/DemoModeBadge";
import { AppIcon } from "../../../components/AppIcon";
import {
  fetchCoordinatorProfile,
  fetchCoordinatorEvents,
  fetchCoordinatorThreads,
  fetchCoordinatorMeetings,
  type EventCoordinator,
  type OutreachThread,
  type MeetingBooking,
  type CalendarEventSummary,
} from "../../../lib/api";

function getSession() {
  try {
    return JSON.parse(sessionStorage.getItem("iaw_session") ?? "{}") as {
      user?: Record<string, unknown>;
    };
  } catch {
    return {};
  }
}

const THREAD_STATUS_COLORS: Record<OutreachThread["status"], string> = {
  confirmed: "bg-primary/10 text-primary",
  in_progress: "bg-muted text-muted-foreground",
  awaiting_response: "bg-destructive/10 text-destructive",
  new: "bg-muted text-muted-foreground",
};

export function CoordinatorHome() {
  const session = getSession();
  const coordinatorId = String((session.user as Record<string, unknown> | undefined)?.coordinator_id ?? "coord-001");

  const [profile, setProfile] = useState<(EventCoordinator & { source: string }) | null>(null);
  const [events, setEvents] = useState<(CalendarEventSummary & { staffing_open: boolean })[]>([]);
  const [threads, setThreads] = useState<OutreachThread[]>([]);
  const [meetings, setMeetings] = useState<MeetingBooking[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [prof, evts, thrs, mtgs] = await Promise.all([
          fetchCoordinatorProfile(coordinatorId),
          fetchCoordinatorEvents(coordinatorId),
          fetchCoordinatorThreads(coordinatorId),
          fetchCoordinatorMeetings(coordinatorId),
        ]);
        if (!mounted) return;
        setProfile(prof);
        if (!mounted) return;
        setEvents(evts.data);
        if (!mounted) return;
        setThreads(thrs.data);
        if (!mounted) return;
        setMeetings(mtgs.data);
      } catch (err) {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : "Failed to load dashboard");
      } finally {
        if (mounted) setLoading(false);
      }
    }
    load();
    return () => {
      mounted = false;
    };
  }, [coordinatorId]);

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-32 w-full rounded-2xl" />
        <div className="grid gap-4 sm:grid-cols-3">
          <Skeleton className="h-28 rounded-2xl" />
          <Skeleton className="h-28 rounded-2xl" />
          <Skeleton className="h-28 rounded-2xl" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-8 text-center">
        <AlertTriangle className="mx-auto mb-3 h-8 w-8 text-destructive" />
        <p className="font-medium text-destructive">{error}</p>
      </div>
    );
  }

  if (!profile) return null;

  const openStaffingCount = events.filter((e) => e.staffing_open).length;
  const statusBreakdown = threads.reduce(
    (acc, t) => {
      acc[t.status] = (acc[t.status] ?? 0) + 1;
      return acc;
    },
    {} as Record<string, number>,
  );

  const upcomingMeetings = meetings
    .filter((m) => m.status === "confirmed")
    .sort((a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime())
    .slice(0, 2);

  return (
    <div className="space-y-6">
      {/* Welcome banner */}
      <div className="rounded-2xl border border-border/70 bg-card p-6 shadow-sm">
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold text-foreground">
            Welcome, {profile.name.split(" ")[0]}!
          </h1>
          {profile.source === "demo" && <DemoModeBadge />}
        </div>
        <p className="mt-1 text-muted-foreground">
          {profile.school} · {profile.department}
        </p>
      </div>

      {/* Stats */}
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-2xl border border-border/70 bg-card p-5 shadow-sm">
          <AppIcon name="events" className="mb-3 h-5 w-5 text-primary" />
          <p className="text-2xl font-bold text-foreground">{events.length}</p>
          <p className="text-sm text-muted-foreground">Hosted Events</p>
          {openStaffingCount > 0 && (
            <p className="mt-1 text-xs text-destructive">{openStaffingCount} need staffing</p>
          )}
        </div>
        <div className="rounded-2xl border border-border/70 bg-card p-5 shadow-sm">
          <AppIcon name="outreach" className="mb-3 h-5 w-5 text-primary" />
          <p className="text-2xl font-bold text-foreground">{threads.length}</p>
          <p className="text-sm text-muted-foreground">Outreach Threads</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {Object.entries(statusBreakdown).map(([status, count]) => (
              <span
                key={status}
                className={`rounded-full px-2 py-0.5 text-xs font-semibold ${THREAD_STATUS_COLORS[status as OutreachThread["status"]] ?? "bg-muted text-muted-foreground"}`}
              >
                {count} {status.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        </div>
        <div className="rounded-2xl border border-border/70 bg-card p-5 shadow-sm">
          <AppIcon name="meetings" className="mb-3 h-5 w-5 text-primary" />
          <p className="text-2xl font-bold text-foreground">{meetings.length}</p>
          <p className="text-sm text-muted-foreground">Total Meetings</p>
        </div>
      </div>

      {/* Quick actions */}
      <div>
        <h2 className="mb-4 text-lg font-semibold text-foreground">Quick Actions</h2>
        <div className="grid gap-4 sm:grid-cols-3">
          <Link
            to="/coordinator-portal/events"
            className="flex items-center gap-3 rounded-2xl border border-border/70 bg-card p-5 shadow-sm transition hover:border-primary/40 hover:bg-primary/5"
          >
            <AppIcon name="events" className="h-6 w-6 text-primary" />
            <span className="font-medium text-foreground">View Events</span>
          </Link>
          <Link
            to="/coordinator-portal/outreach"
            className="flex items-center gap-3 rounded-2xl border border-border/70 bg-card p-5 shadow-sm transition hover:border-primary/40 hover:bg-primary/5"
          >
            <AppIcon name="outreach" className="h-6 w-6 text-primary" />
            <span className="font-medium text-foreground">Contact IA West</span>
          </Link>
          <Link
            to="/coordinator-portal/meetings"
            className="flex items-center gap-3 rounded-2xl border border-border/70 bg-card p-5 shadow-sm transition hover:border-primary/40 hover:bg-primary/5"
          >
            <AppIcon name="meetings" className="h-6 w-6 text-primary" />
            <span className="font-medium text-foreground">Book Meeting</span>
          </Link>
        </div>
      </div>

      {/* Upcoming meetings */}
      {upcomingMeetings.length > 0 && (
        <div>
          <h2 className="mb-4 text-lg font-semibold text-foreground">Upcoming Meetings</h2>
          <div className="space-y-3">
            {upcomingMeetings.map((mtg) => (
              <div
                key={mtg.booking_id}
                className="flex items-center gap-4 rounded-2xl border border-border/70 bg-card p-5 shadow-sm"
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10">
                  <AppIcon name="schedule" className="h-5 w-5 text-primary" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-foreground">{mtg.title}</p>
                  <p className="text-sm text-muted-foreground">
                    {new Date(mtg.scheduled_at).toLocaleString()} · {mtg.ia_contact}
                  </p>
                </div>
                <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
                  Confirmed
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
