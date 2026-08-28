import { useState, useEffect } from "react";
import { AlertTriangle } from "lucide-react";
import { Skeleton } from "../../components/ui/skeleton";
import { DemoModeBadge } from "../../components/ui/DemoModeBadge";
import {
  fetchVolunteerAssignments,
  type VolunteerAssignment,
  type AssignmentStage,
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

const STAGE_COLORS: Record<AssignmentStage, string> = {
  Confirmed: "bg-primary/10 text-primary",
  Contacted: "bg-amber-100 text-amber-700",
  Matched: "bg-muted text-muted-foreground",
  Attended: "bg-green-100 text-green-700",
};

const STAGE_ORDER: Record<AssignmentStage, number> = {
  Confirmed: 0,
  Contacted: 1,
  Matched: 2,
  Attended: 3,
};

export function VolunteerAssignments() {
  const session = getSession();
  const volunteerId = String(
    (session.user as Record<string, unknown> | undefined)?.volunteer_id ?? "shana-demarinis",
  );

  const [assignments, setAssignments] = useState<VolunteerAssignment[]>([]);
  const [source, setSource] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const result = await fetchVolunteerAssignments(volunteerId);
        if (!mounted) return;
        setAssignments(result.data);
        setSource(result.source);
      } catch (err) {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : "Failed to load assignments");
      } finally {
        if (mounted) setLoading(false);
      }
    }
    load();
    return () => {
      mounted = false;
    };
  }, [volunteerId]);

  const sorted = [...assignments].sort(
    (a, b) =>
      (STAGE_ORDER[a.stage] ?? 99) - (STAGE_ORDER[b.stage] ?? 99) ||
      new Date(a.event_date).getTime() - new Date(b.event_date).getTime(),
  );

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-48 rounded-xl" />
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-24 w-full rounded-2xl" />
        ))}
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
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold text-foreground">My Assignments</h1>
        {source === "demo" && <DemoModeBadge />}
      </div>

      {sorted.length === 0 ? (
        <div className="rounded-2xl border border-border/70 bg-card p-10 text-center text-muted-foreground shadow-sm">
          No assignments found.
        </div>
      ) : (
        <div className="space-y-4">
          {sorted.map((a) => (
            <div
              key={a.assignment_id}
              className="rounded-2xl border border-border/70 bg-card p-5 shadow-sm"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-semibold text-foreground">{a.event_name}</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {a.region} · {new Date(a.event_date).toLocaleDateString()}
                  </p>
                </div>
                <span
                  className={`rounded-full px-3 py-1 text-xs font-semibold ${STAGE_COLORS[a.stage] ?? "bg-muted text-muted-foreground"}`}
                >
                  {a.stage}
                </span>
              </div>
              <div className="mt-3 flex flex-wrap gap-4 text-sm text-muted-foreground">
                <span>
                  Match score:{" "}
                  <span className="font-medium text-foreground">
                    {Math.round(a.match_score * 100)}%
                  </span>
                </span>
                <span>
                  Recovery:{" "}
                  <span className="font-medium text-foreground">{a.recovery_label}</span>
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
