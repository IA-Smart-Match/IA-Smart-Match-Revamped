import { useState, useEffect } from "react";
import { ClipboardCheck, AlertTriangle } from "lucide-react";
import { Skeleton } from "../../components/ui/skeleton";
import { DemoModeBadge } from "../../components/ui/DemoModeBadge";
import { AppIcon } from "../../../components/AppIcon";
import {
  fetchStudentRegistrations,
  fetchStudentProfile,
  type StudentRegistration,
  type StudentProfile,
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

function formatDuration(checkIn: string | null, checkOut: string | null): string {
  if (!checkIn || !checkOut) return "—";
  const diff = new Date(checkOut).getTime() - new Date(checkIn).getTime();
  if (isNaN(diff) || diff <= 0) return "—";
  const hours = Math.floor(diff / 3600000);
  const minutes = Math.floor((diff % 3600000) / 60000);
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
}

export function StudentHistory() {
  const session = getSession();
  const studentId = String((session.user as Record<string, unknown> | undefined)?.student_id ?? "stu-001");

  const [registrations, setRegistrations] = useState<StudentRegistration[]>([]);
  const [profile, setProfile] = useState<(StudentProfile & { source: string }) | null>(null);
  const [source, setSource] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const pointsFromProfile = profile ? profile.attendance_streak * 100 + profile.events_attended * 25 : 0;

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [regsResult, prof] = await Promise.all([
          fetchStudentRegistrations(studentId),
          fetchStudentProfile(studentId),
        ]);
        setRegistrations(regsResult.data.filter((r) => r.status === "attended"));
        setSource(regsResult.source);
        setProfile(prof);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load history");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [studentId]);

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48 rounded-xl" />
        <Skeleton className="h-20 w-full rounded-2xl" />
        <Skeleton className="h-28 w-full rounded-2xl" />
        <Skeleton className="h-28 w-full rounded-2xl" />
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

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <h1 className="text-2xl font-semibold text-foreground">Past Events</h1>
        {source === "demo" && <DemoModeBadge />}
      </div>

      {/* Stats banner */}
      {profile && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <div className="rounded-2xl border border-border/70 bg-card p-5 shadow-sm text-center">
            <p className="text-3xl font-bold text-foreground">{profile.events_attended}</p>
            <p className="mt-1 text-sm text-muted-foreground">Total Attended</p>
          </div>
          <div className="rounded-2xl border border-border/70 bg-card p-5 shadow-sm text-center">
            <div className="flex items-center justify-center gap-2">
              <AppIcon name="points" className="h-5 w-5 text-amber-500" />
              <p className="text-3xl font-bold text-foreground">{pointsFromProfile}</p>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">Points</p>
          </div>
          {profile.membership_interest && (
            <div className="rounded-2xl border border-primary/30 bg-primary/5 p-5 shadow-sm text-center">
              <div className="flex items-center justify-center gap-2">
                <AppIcon name="membership" className="h-5 w-5 text-primary" />
                <p className="text-sm font-semibold text-primary">Membership Interest</p>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">You're a great candidate!</p>
            </div>
          )}
        </div>
      )}

      {registrations.length === 0 ? (
        <div className="rounded-2xl border border-border/70 bg-card p-10 text-center shadow-sm">
          <ClipboardCheck className="mx-auto mb-4 h-10 w-10 text-muted-foreground" />
          <p className="font-medium text-foreground">No attended events yet</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Attend events to build your history and earn points.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {registrations.map((reg) => (
            <div
              key={reg.registration_id}
              className="rounded-2xl border border-border/70 bg-card p-6 shadow-sm"
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-3">
                    <h2 className="font-semibold text-foreground">{reg.event_name}</h2>
                    <span className="rounded-full bg-green-100 px-3 py-0.5 text-xs font-semibold text-green-700">
                      Attended
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {reg.registered_at ? new Date(reg.registered_at).toLocaleDateString() : "—"}
                  </p>
                </div>
                <div className="text-right text-sm text-muted-foreground">
                  <span>Duration: </span>
                  <span className="font-medium text-foreground">
                    {formatDuration(reg.check_in_time, reg.check_out_time)}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
