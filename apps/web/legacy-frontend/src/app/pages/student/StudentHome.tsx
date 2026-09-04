import { useState, useEffect } from "react";
import { Link } from "react-router";
import { AlertTriangle, ChevronRight } from "lucide-react";
import { Skeleton } from "../../components/ui/skeleton";
import { DemoModeBadge } from "../../components/ui/DemoModeBadge";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "../../components/ui/hover-card";
import { AppIcon } from "../../../components/AppIcon";
import { useRewards } from "../../hooks/useRewards";
import {
  fetchStudentProfile,
  fetchStudentNudge,
  fetchStudentRecommendations,
  type StudentProfile,
  type RetentionNudge,
  type CalendarEventSummary,
} from "../../../lib/api";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";
import { portalSubjectId } from "../../../lib/principal";

export function StudentHome() {
  // `/v1/me` authenticates the account but does not yet map it to a legacy
  // student record. The empty transport value is rejected by the API client
  // before any caller-selectable `/api/portals/*` request is issued.
  const principal = useAuthenticatedPrincipal();
  const studentId = portalSubjectId(principal, "student") ?? "";

  // Points and the reward preview come from the server, never from `profile`.
  // The formula that used to live here — `attendance_streak * 100 +
  // events_attended * 25`, in the deleted `lib/studentPoints.ts` — was a browser
  // computing a balance, which ADR-0013 forbids outright, and it rendered `0`
  // whenever the profile had not loaded.
  const rewards = useRewards();
  const rewardsReady = rewards.status === "ready" && rewards.catalog !== null;
  const balancePoints = rewardsReady ? rewards.catalog!.balance.points : null;
  const rewardPreview = rewardsReady ? rewards.catalog!.items.slice(0, 5) : [];

  const [profile, setProfile] = useState<(StudentProfile & { source: string }) | null>(null);
  const [nudge, setNudge] = useState<(RetentionNudge & { source: string }) | null>(null);
  const [recommendations, setRecommendations] = useState<(CalendarEventSummary & { is_recommended: boolean })[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [prof, nud, recs] = await Promise.all([
          fetchStudentProfile(studentId),
          fetchStudentNudge(studentId),
          fetchStudentRecommendations(studentId),
        ]);
        if (!mounted) return;
        setProfile(prof);
        if (!mounted) return;
        setNudge(nud);
        if (!mounted) return;
        setRecommendations(recs.recommendations.slice(0, 3));
      } catch (err) {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : "Failed to load data");
      } finally {
        if (mounted) setLoading(false);
      }
    }
    load();
    return () => {
      mounted = false;
    };
  }, [studentId]);

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-32 w-full rounded-2xl" />
        <Skeleton className="h-24 w-full rounded-2xl" />
        <div className="grid gap-4 sm:grid-cols-3">
          <Skeleton className="h-40 rounded-2xl" />
          <Skeleton className="h-40 rounded-2xl" />
          <Skeleton className="h-40 rounded-2xl" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-8 text-center">
        <AlertTriangle className="mx-auto mb-3 h-8 w-8 text-destructive" />
        <p className="font-medium text-destructive">{error}</p>
        <p className="mt-1 text-sm text-muted-foreground">Please try refreshing the page.</p>
      </div>
    );
  }

  if (!profile) return null;

  const churnHigh = profile.churn_risk === "high";
  // Rendered wherever a points figure appears. Never `?? 0`: `null` means the
  // server has not established this balance (or the catalog has not loaded), and
  // a zero there is precisely the ADR-0011 defect this page carried before.
  const pointsLabel = balancePoints === null ? "—" : balancePoints.toLocaleString();

  return (
    <div className="space-y-6">
      {/* Churn risk banner */}
      {churnHigh && (
        <div className="flex items-start gap-3 rounded-2xl border border-destructive/20 bg-destructive/10 p-4 text-destructive">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
          <div>
            <p className="font-semibold text-destructive">We miss you!</p>
            <p className="text-sm text-destructive">
              It looks like you haven't been active lately. Check out upcoming events and earn points toward membership.
            </p>
          </div>
        </div>
      )}

      {/* Welcome card */}
      <div className="rounded-2xl border border-border/70 bg-card p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-semibold text-foreground">
                Welcome back, {profile.name.split(" ")[0]}!
              </h1>
              {profile.source === "demo" && <DemoModeBadge />}
            </div>
            <p className="mt-1 text-muted-foreground">
              {profile.school} · {profile.major} · {profile.year}
            </p>
          </div>
          <HoverCard openDelay={120} closeDelay={80}>
            <HoverCardTrigger asChild>
              <Link
                to="/student-portal/rewards"
                className="flex items-center gap-2 rounded-full border border-primary/20 bg-primary/10 px-4 py-2 text-primary outline-none transition hover:bg-primary/15 focus-visible:ring-2 focus-visible:ring-ring/40"
                aria-label={
                  balancePoints === null
                    ? "Points not established — open rewards catalog"
                    : `${balancePoints} points — open rewards catalog`
                }
              >
                <AppIcon name="points" className="h-4 w-4 shrink-0 text-primary" aria-hidden />
                <span className="text-sm font-semibold text-primary">{pointsLabel} points</span>
                <ChevronRight className="h-4 w-4 shrink-0 opacity-60" aria-hidden />
              </Link>
            </HoverCardTrigger>
            <HoverCardContent
              align="end"
              side="bottom"
              sideOffset={10}
              className="w-[min(22rem,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-border/70 bg-card p-0 shadow-lg"
            >
              <div className="border-b border-border/70 bg-primary/5 px-4 py-3">
                <p className="text-sm font-semibold text-foreground">Redeem your points</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Hover preview — tap or click to see the full catalog and request redemptions.
                </p>
              </div>
              {rewardPreview.length === 0 ? (
                <p className="px-4 py-4 text-xs text-muted-foreground">
                  {rewardsReady
                    ? "No reward currently has both a named budget owner and confirmed funding."
                    : "The rewards catalog has not loaded, so nothing is listed here."}
                </p>
              ) : (
                <ul className="max-h-[min(22rem,50vh)] divide-y divide-border/60 overflow-y-auto px-1 py-1">
                  {rewardPreview.map((item) => (
                    // `affordable` is the server's answer, not a comparison this
                    // component makes — a browser deciding what a student can
                    // afford is the arithmetic ADR-0013 moved server-side.
                    <li key={item.item_id} className="px-3 py-2.5">
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-sm font-medium leading-snug text-foreground">
                          {item.name}
                        </p>
                        <span
                          className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${
                            item.affordable
                              ? "bg-primary/15 text-primary"
                              : "bg-muted text-muted-foreground"
                          }`}
                        >
                          {item.points_cost.toLocaleString()} pts
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              <div className="border-t border-border/70 p-3">
                <Link
                  to="/student-portal/rewards"
                  className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-3 py-2.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
                >
                  View all rewards
                  <ChevronRight className="h-4 w-4" aria-hidden />
                </Link>
              </div>
            </HoverCardContent>
          </HoverCard>
        </div>

        {/* Stats bar */}
        <div className="mt-6 grid grid-cols-3 gap-4 border-t border-border/70 pt-5">
          <div className="text-center">
            <p className="text-2xl font-bold text-foreground">{profile.events_attended}</p>
            <p className="text-xs text-muted-foreground">Events Attended</p>
          </div>
          {/* "Streak Points" stood here and was `attendance_streak * 100` — a
              second browser-side reward formula, and one for an earn rule that
              does not exist: points derive from recorded attendance and nothing
              else (ADR-0013), so a streak earns nothing. Replaced with the
              evidence behind the balance rather than deleted silently. */}
          <div className="text-center">
            <p className="text-2xl font-bold text-foreground">
              {rewardsReady ? rewards.catalog!.balance.ledger_entry_count : "—"}
            </p>
            <p className="text-xs text-muted-foreground">Point ledger entries</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-foreground">{pointsLabel}</p>
            <p className="text-xs text-muted-foreground">Redeemable points</p>
          </div>
        </div>
      </div>

      {/* Nudge card */}
      {nudge && (
        <div
          className={`rounded-2xl border p-6 ${
            nudge.nudge_type === "membership" || nudge.nudge_type === "streak"
              ? "border-primary/30 bg-primary/5"
              : "border-border/70 bg-card"
          }`}
        >
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10">
              <AppIcon name="membership" className="h-5 w-5 text-primary" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <p className="font-semibold text-foreground">{nudge.message}</p>
                {nudge.source === "demo" && <DemoModeBadge />}
              </div>
              {nudge.points_earned > 0 && (
                <p className="mt-1 text-sm text-muted-foreground">
                  Earn <span className="font-semibold text-primary">+{nudge.points_earned} pts</span>
                </p>
              )}
              <button className="mt-3 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90">
                {nudge.cta_label}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Recommendations */}
      <div>
        <div className="mb-4 flex items-center gap-2">
          <AppIcon name="sparkles" className="h-5 w-5 text-primary" />
          <h2 className="text-lg font-semibold text-foreground">Recommended for You</h2>
        </div>
        {recommendations.length === 0 ? (
          <p className="text-muted-foreground">No recommendations available right now.</p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-3">
            {recommendations.map((event) => (
              <div
                key={event.event_id}
                className="rounded-2xl border border-border/70 bg-card p-5 shadow-sm"
              >
                <div className="mb-3 flex items-center gap-2">
                  <AppIcon name="events" className="h-4 w-4 text-primary" />
                  <span className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">
                    {event.region}
                  </span>
                </div>
                <h3 className="font-semibold text-foreground leading-snug">{event.event_name}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{event.event_date}</p>
                <Link
                  to="/student-portal/events"
                  className="mt-4 block w-full rounded-xl bg-primary px-4 py-2 text-center text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
                >
                  Register
                </Link>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
