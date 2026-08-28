import { useState, useEffect } from "react";
import { Link } from "react-router";
import { AlertTriangle, ClipboardList, UserCircle } from "lucide-react";
import { Skeleton } from "../../components/ui/skeleton";
import { DemoModeBadge } from "../../components/ui/DemoModeBadge";
import {
  fetchVolunteerProfile,
  fetchVolunteerAssignments,
  type VolunteerProfile,
  type VolunteerAssignment,
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

export function VolunteerHome() {
  const session = getSession();
  const volunteerId = String(
    (session.user as Record<string, unknown> | undefined)?.volunteer_id ?? "shana-demarinis",
  );

  const [profile, setProfile] = useState<(VolunteerProfile & { source: string }) | null>(null);
  const [assignments, setAssignments] = useState<VolunteerAssignment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [prof, asns] = await Promise.all([
          fetchVolunteerProfile(volunteerId),
          fetchVolunteerAssignments(volunteerId),
        ]);
        if (!mounted) return;
        setProfile(prof);
        if (!mounted) return;
        setAssignments(asns.data);
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
  }, [volunteerId]);

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

  const totalAssignments = assignments.length;
  const confirmedEvents = assignments.filter(
    (a) => a.stage === "Confirmed" || a.stage === "Attended",
  ).length;
  const fatiguePercent = Math.round(profile.volunteer_fatigue * 100);
  const fatigueColor =
    profile.volunteer_fatigue >= 0.75
      ? "text-destructive"
      : profile.volunteer_fatigue >= 0.4
        ? "text-amber-600"
        : "text-green-600";

  const upcomingConfirmed = assignments
    .filter((a) => a.stage === "Confirmed")
    .sort((a, b) => new Date(a.event_date).getTime() - new Date(b.event_date).getTime())
    .slice(0, 3);

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
          {profile.board_role} · {profile.company}
        </p>
      </div>

      {/* Stats */}
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-2xl border border-border/70 bg-card p-5 shadow-sm">
          <p className="text-2xl font-bold text-foreground">{totalAssignments}</p>
          <p className="text-sm text-muted-foreground">Total Assignments</p>
        </div>
        <div className="rounded-2xl border border-border/70 bg-card p-5 shadow-sm">
          <p className="text-2xl font-bold text-foreground">{confirmedEvents}</p>
          <p className="text-sm text-muted-foreground">Confirmed &amp; Attended</p>
        </div>
        <div className="rounded-2xl border border-border/70 bg-card p-5 shadow-sm">
          <p className={`text-2xl font-bold ${fatigueColor}`}>{fatiguePercent}%</p>
          <p className="text-sm text-muted-foreground">Fatigue Index</p>
          <p className="mt-1 text-xs text-muted-foreground">{profile.recovery_label}</p>
        </div>
      </div>

      {/* Upcoming confirmed events */}
      {upcomingConfirmed.length > 0 && (
        <div>
          <h2 className="mb-4 text-lg font-semibold text-foreground">Upcoming Confirmed Events</h2>
          <div className="space-y-3">
            {upcomingConfirmed.map((a) => (
              <div
                key={a.assignment_id}
                className="flex items-center gap-4 rounded-2xl border border-border/70 bg-card p-5 shadow-sm"
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10">
                  <ClipboardList className="h-5 w-5 text-primary" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-foreground">{a.event_name}</p>
                  <p className="text-sm text-muted-foreground">
                    {a.region} · {new Date(a.event_date).toLocaleDateString()}
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

      {/* Quick actions */}
      <div>
        <h2 className="mb-4 text-lg font-semibold text-foreground">Quick Actions</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <Link
            to="/volunteer-portal/assignments"
            className="flex items-center gap-3 rounded-2xl border border-border/70 bg-card p-5 shadow-sm transition hover:border-primary/40 hover:bg-primary/5"
          >
            <ClipboardList className="h-6 w-6 text-primary" />
            <span className="font-medium text-foreground">View My Assignments</span>
          </Link>
          <Link
            to="/volunteer-portal/profile"
            className="flex items-center gap-3 rounded-2xl border border-border/70 bg-card p-5 shadow-sm transition hover:border-primary/40 hover:bg-primary/5"
          >
            <UserCircle className="h-6 w-6 text-primary" />
            <span className="font-medium text-foreground">View My Profile</span>
          </Link>
        </div>
      </div>
    </div>
  );
}
