import { useState, useEffect } from "react";
import { AlertTriangle, MapPin, Star } from "lucide-react";
import { Skeleton } from "../../components/ui/skeleton";
import { DemoModeBadge } from "../../components/ui/DemoModeBadge";
import { fetchVolunteerProfile, splitTags, type VolunteerProfile } from "../../../lib/api";

function getSession() {
  try {
    return JSON.parse(sessionStorage.getItem("iaw_session") ?? "{}") as {
      user?: Record<string, unknown>;
    };
  } catch {
    return {};
  }
}

const RECOVERY_COLORS: Record<string, string> = {
  Available: "bg-green-100 text-green-700",
  "Needs Rest": "bg-amber-100 text-amber-700",
  "Rest Recommended": "bg-red-100 text-red-700",
};

export function VolunteerProfile() {
  const session = getSession();
  const volunteerId = String(
    (session.user as Record<string, unknown> | undefined)?.volunteer_id ?? "shana-demarinis",
  );

  const [profile, setProfile] = useState<(VolunteerProfile & { source: string }) | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const prof = await fetchVolunteerProfile(volunteerId);
        if (!mounted) return;
        setProfile(prof);
      } catch (err) {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : "Failed to load profile");
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
      <div className="space-y-4">
        <Skeleton className="h-40 w-full rounded-2xl" />
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

  if (!profile) return null;

  const fatiguePercent = Math.round(profile.volunteer_fatigue * 100);
  const recoveryColor =
    RECOVERY_COLORS[profile.recovery_status] ?? "bg-muted text-muted-foreground";
  const tags = splitTags(profile.expertise_tags);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-foreground">My Profile</h1>

      {/* Profile header */}
      <div className="rounded-2xl border border-border/70 bg-card p-6 shadow-sm">
        <div className="flex flex-wrap items-start gap-5">
          <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-primary text-xl font-semibold text-primary-foreground">
            {profile.initials}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl font-semibold text-foreground">{profile.name}</h2>
              {profile.source === "demo" && <DemoModeBadge />}
            </div>
            <p className="mt-1 text-muted-foreground">
              {profile.title} at {profile.company}
            </p>
            <span className="mt-2 inline-block rounded-full bg-primary/10 px-3 py-1 text-sm font-medium text-primary">
              {profile.board_role}
            </span>
          </div>
        </div>
      </div>

      {/* Details grid */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-2xl border border-border/70 bg-card p-5 shadow-sm">
          <div className="mb-2 flex items-center gap-2 text-muted-foreground">
            <MapPin className="h-4 w-4" />
            <span className="text-xs uppercase tracking-wide">Metro Region</span>
          </div>
          <p className="font-semibold text-foreground">{profile.metro_region}</p>
        </div>

        <div className="rounded-2xl border border-border/70 bg-card p-5 shadow-sm">
          <div className="mb-2 flex items-center gap-2 text-muted-foreground">
            <Star className="h-4 w-4" />
            <span className="text-xs uppercase tracking-wide">Board Role</span>
          </div>
          <p className="font-semibold text-foreground">{profile.board_role}</p>
        </div>

        <div className="rounded-2xl border border-border/70 bg-card p-5 shadow-sm">
          <p className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">
            Recovery Status
          </p>
          <span
            className={`rounded-full px-3 py-1 text-sm font-semibold ${recoveryColor}`}
          >
            {profile.recovery_status}
          </span>
        </div>

        <div className="rounded-2xl border border-border/70 bg-card p-5 shadow-sm">
          <p className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">
            Fatigue Index
          </p>
          <p className="mb-2 text-2xl font-bold text-foreground">{fatiguePercent}%</p>
          <div className="h-2 w-full rounded-full bg-muted">
            <div
              className="h-2 rounded-full bg-primary transition-all"
              style={{ width: `${fatiguePercent}%` }}
            />
          </div>
        </div>
      </div>

      {/* Expertise tags */}
      {tags.length > 0 && (
        <div className="rounded-2xl border border-border/70 bg-card p-5 shadow-sm">
          <p className="mb-3 text-xs uppercase tracking-wide text-muted-foreground">
            Expertise
          </p>
          <div className="flex flex-wrap gap-2">
            {tags.map((tag) => (
              <span
                key={tag}
                className="rounded-full bg-slate-100 px-3 py-1 text-sm font-medium text-slate-700"
              >
                {tag}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
