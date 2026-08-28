import { useState, useEffect } from "react";
import { Link } from "react-router";
import { AlertTriangle } from "lucide-react";
import { Skeleton } from "../../components/ui/skeleton";
import { DemoModeBadge } from "../../components/ui/DemoModeBadge";
import { AppIcon } from "../../../components/AppIcon";
import { fetchCoordinatorEvents, type CalendarEventSummary } from "../../../lib/api";

function getSession() {
  try {
    return JSON.parse(sessionStorage.getItem("iaw_session") ?? "{}") as {
      user?: Record<string, unknown>;
    };
  } catch {
    return {};
  }
}

const COVERAGE_COLORS: Record<string, string> = {
  covered: "bg-green-100 text-green-700",
  partial: "bg-amber-100 text-amber-700",
  needs_coverage: "bg-red-100 text-red-700",
  unknown: "bg-muted text-muted-foreground",
};

const COVERAGE_LABELS: Record<string, string> = {
  covered: "Fully Staffed",
  partial: "Partial Coverage",
  needs_coverage: "Needs Staff",
  unknown: "Coverage Pending",
};

export function CoordinatorEvents() {
  const session = getSession();
  const coordinatorId = String((session.user as Record<string, unknown> | undefined)?.coordinator_id ?? "coord-001");

  const [events, setEvents] = useState<(CalendarEventSummary & { staffing_open: boolean })[]>([]);
  const [source, setSource] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const result = await fetchCoordinatorEvents(coordinatorId);
        setEvents(result.data);
        setSource(result.source);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load events");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [coordinatorId]);

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48 rounded-xl" />
        <Skeleton className="h-32 w-full rounded-2xl" />
        <Skeleton className="h-32 w-full rounded-2xl" />
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
        <h1 className="text-2xl font-semibold text-foreground">My Events</h1>
        {source === "demo" && <DemoModeBadge />}
      </div>

      {events.length === 0 ? (
        <div className="rounded-2xl border border-border/70 bg-card p-10 text-center shadow-sm">
          <AppIcon name="events" className="mx-auto mb-4 h-10 w-10 text-muted-foreground" />
          <p className="font-medium text-foreground">No events found</p>
        </div>
      ) : (
        <div className="space-y-4">
          {events.map((event) => {
            const coverageClass = COVERAGE_COLORS[event.coverage_status] ?? COVERAGE_COLORS.unknown;
            const coverageLabel = COVERAGE_LABELS[event.coverage_status] ?? "Coverage Pending";
            const needsStaff = event.staffing_open || event.coverage_status === "needs_coverage";

            return (
              <div
                key={event.event_id}
                className="rounded-2xl border border-border/70 bg-card p-6 shadow-sm"
              >
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-3">
                      <h2 className="font-semibold text-foreground">{event.event_name}</h2>
                      <span className={`rounded-full px-3 py-0.5 text-xs font-semibold ${coverageClass}`}>
                        {coverageLabel}
                      </span>
                      {needsStaff && (
                        <span className="rounded-full bg-red-100 px-3 py-0.5 text-xs font-semibold text-red-700">
                          Needs Staff
                        </span>
                      )}
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
                      <div className="flex items-center gap-1.5">
                        <AppIcon name="calendar" className="h-4 w-4" />
                        <span>{event.event_date}</span>
                      </div>
                      <span>{event.region}</span>
                      {event.open_slots > 0 && (
                        <div className="flex items-center gap-1.5 text-amber-600">
                          <AppIcon name="staffing" className="h-4 w-4" />
                          <span>{event.open_slots} open slots</span>
                        </div>
                      )}
                    </div>
                    {event.assigned_volunteers.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {event.assigned_volunteers.map((vol) => (
                          <span key={vol} className="rounded-full border border-border/70 px-2.5 py-0.5 text-xs text-muted-foreground">
                            {vol}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  {needsStaff && (
                    <Link
                      to="/ai-matching"
                      className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
                    >
                      Request Match
                    </Link>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
