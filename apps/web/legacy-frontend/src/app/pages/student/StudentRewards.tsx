import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { AlertTriangle, ArrowLeft, Check, Lock } from "lucide-react";
import { Skeleton } from "../../components/ui/skeleton";
import { DemoModeBadge } from "../../components/ui/DemoModeBadge";
import { AppIcon } from "../../../components/AppIcon";
import { Button } from "../../components/ui/button";
import { Progress } from "../../components/ui/progress";
import { fetchStudentProfile, type StudentProfile } from "../../../lib/api";
import { getStudentTotalPoints } from "../../../lib/studentPoints";
import {
  REWARD_CATEGORY_LABELS,
  STUDENT_REWARD_CATALOG,
  type RewardCategoryId,
  type StudentRewardItem,
} from "../../../lib/studentRewardsCatalog";

function getSession() {
  try {
    return JSON.parse(sessionStorage.getItem("iaw_session") ?? "{}") as {
      user?: Record<string, unknown>;
    };
  } catch {
    return {};
  }
}

function groupByCategory(items: StudentRewardItem[]): Map<RewardCategoryId, StudentRewardItem[]> {
  const map = new Map<RewardCategoryId, StudentRewardItem[]>();
  for (const item of items) {
    const list = map.get(item.category) ?? [];
    list.push(item);
    map.set(item.category, list);
  }
  for (const list of map.values()) {
    list.sort((a, b) => a.pointsCost - b.pointsCost);
  }
  return map;
}

export function StudentRewards() {
  const session = getSession();
  const studentId = String((session.user as Record<string, unknown> | undefined)?.student_id ?? "stu-001");

  const [profile, setProfile] = useState<(StudentProfile & { source: string }) | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [demoRequested, setDemoRequested] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    let mounted = true;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const prof = await fetchStudentProfile(studentId);
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
  }, [studentId]);

  const totalPoints = profile ? getStudentTotalPoints(profile) : 0;
  const nextAffordable = useMemo(() => {
    const affordable = STUDENT_REWARD_CATALOG.filter((r) => r.pointsCost <= totalPoints);
    const unaffordable = STUDENT_REWARD_CATALOG.filter((r) => r.pointsCost > totalPoints).sort(
      (a, b) => a.pointsCost - b.pointsCost,
    );
    return { affordable, next: unaffordable[0] ?? null };
  }, [totalPoints]);

  const grouped = useMemo(() => groupByCategory(STUDENT_REWARD_CATALOG), []);
  const categoryOrder: RewardCategoryId[] = ["linkedin", "platforms", "certs", "growth"];

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-40 w-full rounded-2xl" />
        <div className="grid gap-4 md:grid-cols-2">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-48 rounded-2xl" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-8 text-center">
        <AlertTriangle className="mx-auto mb-3 h-8 w-8 text-destructive" />
        <p className="font-medium text-destructive">{error}</p>
        <Link
          to="/student-portal"
          className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-primary hover:underline"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          Back to home
        </Link>
      </div>
    );
  }

  if (!profile) return null;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <Link
          to="/student-portal"
          className="inline-flex items-center gap-2 text-sm font-medium text-muted-foreground transition hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          Back to home
        </Link>
      </div>

      <div className="rounded-2xl border border-border/70 bg-card p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-semibold text-foreground">Rewards & professional development</h1>
              {profile.source === "demo" && <DemoModeBadge />}
            </div>
            <p className="mt-1 max-w-2xl text-muted-foreground">
              Redeem chapter engagement points for curated learning tools and career resources. Redemptions are
              reviewed by your coordinator (demo: requests are simulated only).
            </p>
            {nextAffordable.affordable.length > 0 ? (
              <p className="mt-3 text-sm text-foreground">
                You qualify for{" "}
                <span className="font-semibold text-primary">{nextAffordable.affordable.length}</span> catalog
                reward{nextAffordable.affordable.length === 1 ? "" : "s"} at your current balance.
              </p>
            ) : null}
          </div>
          <div className="flex items-center gap-2 rounded-full border border-primary/20 bg-primary/10 px-4 py-2 text-primary">
            <AppIcon name="points" className="h-4 w-4 text-primary" aria-hidden />
            <span className="text-sm font-semibold text-primary">{totalPoints} points</span>
          </div>
        </div>

        {nextAffordable.next ? (
          <div className="mt-6 rounded-2xl border border-primary/25 bg-primary/5 p-4">
            <p className="text-sm font-medium text-foreground">Closest unlock</p>
            <p className="mt-1 text-sm text-muted-foreground">
              <span className="font-semibold text-primary">{nextAffordable.next.title}</span> — need{" "}
              <span className="font-semibold text-foreground">
                {nextAffordable.next.pointsCost - totalPoints} more pts
              </span>{" "}
              ({nextAffordable.next.pointsCost.toLocaleString()} total).
            </p>
            <Progress
              className="mt-3 h-2 bg-primary/15"
              value={Math.min(100, Math.round((totalPoints / nextAffordable.next.pointsCost) * 100))}
            />
          </div>
        ) : (
          <div className="mt-6 rounded-2xl border border-primary/25 bg-primary/5 p-4 text-sm text-foreground">
            You have enough points for every catalog item right now — pick a reward below to request it.
          </div>
        )}
      </div>

      {categoryOrder.map((cat) => {
        const items = grouped.get(cat);
        if (!items?.length) return null;
        return (
          <section key={cat} className="space-y-4">
            <div className="flex items-center gap-2">
              <AppIcon name="sparkles" className="h-5 w-5 text-primary" aria-hidden />
              <h2 className="text-lg font-semibold text-foreground">{REWARD_CATEGORY_LABELS[cat]}</h2>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {items.map((reward) => {
                const Icon = reward.icon;
                const canAfford = totalPoints >= reward.pointsCost;
                const requested = demoRequested.has(reward.id);
                return (
                  <div
                    key={reward.id}
                    className={`flex flex-col rounded-2xl border p-6 shadow-sm transition ${
                      canAfford
                        ? "border-primary/25 bg-[linear-gradient(180deg,hsl(var(--card))_0%,hsl(var(--primary)/0.06)_100%)]"
                        : "border-border/70 bg-card"
                    }`}
                  >
                    <div className="flex items-start gap-4">
                      <div
                        className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border ${
                          canAfford ? "border-primary/30 bg-primary/10 text-primary" : "border-border/70 bg-muted/40 text-muted-foreground"
                        }`}
                      >
                        <Icon className="h-6 w-6" aria-hidden />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="font-semibold text-foreground">{reward.title}</h3>
                          {!canAfford ? (
                            <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                              <Lock className="h-3 w-3" aria-hidden />
                              Locked
                            </span>
                          ) : null}
                        </div>
                        <p className="mt-1 text-sm text-muted-foreground">{reward.subtitle}</p>
                        <p className="mt-3 text-sm font-semibold text-primary">
                          {reward.pointsCost.toLocaleString()} points
                        </p>
                      </div>
                    </div>
                    <div className="mt-5 flex flex-wrap items-center gap-3 border-t border-border/60 pt-4">
                      <Button
                        type="button"
                        className="rounded-xl"
                        disabled={!canAfford || requested}
                        onClick={() => {
                          setDemoRequested((prev) => new Set([...prev, reward.id]));
                        }}
                      >
                        {requested ? (
                          <>
                            <Check className="mr-2 h-4 w-4" aria-hidden />
                            Request sent (demo)
                          </>
                        ) : canAfford ? (
                          "Request redemption"
                        ) : (
                          <>
                            <Lock className="mr-2 h-4 w-4" aria-hidden />
                            Not enough points
                          </>
                        )}
                      </Button>
                      {!canAfford ? (
                        <span className="text-xs text-muted-foreground">
                          Earn {(reward.pointsCost - totalPoints).toLocaleString()} more points to unlock.
                        </span>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}
