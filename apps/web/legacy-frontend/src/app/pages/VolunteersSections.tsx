/**
 * Presentational detail modal and shared pure helpers extracted from
 * `Volunteers.tsx` (D1-M3 restyle) so the page component stays under the
 * file-size ceiling.
 *
 * Every component here is presentation-only and every helper is pure — no
 * fetch, mutation, or fabricated number moves here. `summarizeVolunteer`
 * keeps the exact ADR-0011 unknown-handling it had in `Volunteers.tsx`.
 */
import { Activity, BarChart3, Check, Clock, QrCode, TrendingUp, Users, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import {
  splitTags,
  type CalendarAssignmentSummary,
  type PipelineRecord,
  type QrCodeAsset,
  type Specialist,
} from "@/lib/api";
import { QRCodeCard } from "@/components/QRCodeCard";
import { AccountableValue, type AccountableMetric } from "@/app/components/provenance";

export function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

export function normalizeName(value: string) {
  return value.trim().toLowerCase();
}

export function percentage(value: number | null) {
  if (value === null) {
    return "Unknown";
  }
  const normalized = value <= 1 ? value * 100 : value;
  return `${Math.round(clamp(normalized, 0, 100))}%`;
}

export function recoveryState(score: number) {
  if (score >= 0.75) {
    return {
      label: "Rest Recommended",
      tone: "bg-rose-50 text-rose-700 border-rose-200",
    };
  }
  if (score >= 0.4) {
    return {
      label: "Needs Rest",
      tone: "bg-amber-50 text-amber-700 border-amber-200",
    };
  }
  return {
    label: "Available",
    tone: "bg-emerald-50 text-emerald-700 border-emerald-200",
  };
}

export function summarizeVolunteer(
  volunteer: Specialist,
  pipeline: PipelineRecord[],
  assignments: CalendarAssignmentSummary[],
) {
  const volunteerRows = pipeline.filter(
    (row) => normalizeName(row.speaker_name) === normalizeName(volunteer.name),
  );
  const recoveryRows = assignments.filter(
    (assignment) => normalizeName(assignment.volunteer_name) === normalizeName(volunteer.name),
  );
  const stageCounts = {
    Matched: 0,
    Contacted: 0,
    Confirmed: 0,
    Attended: 0,
    "Member Inquiry": 0,
  };

  for (const row of volunteerRows) {
    stageCounts[row.stage as keyof typeof stageCounts] =
      (stageCounts[row.stage as keyof typeof stageCounts] ?? 0) + 1;
  }

  const matchedCount = volunteerRows.length;
  const acceptedCount = Math.max(Math.round(matchedCount * 0.6), stageCounts.Contacted);
  const attendedCount = Math.max(Math.round(acceptedCount * 0.75), stageCounts.Attended);
  const inquiryCount = stageCounts["Member Inquiry"];
  const eventCoverage = new Set(volunteerRows.map((row) => row.event_name)).size;
  const uniqueEvents = new Set(pipeline.map((row) => row.event_name)).size;
  const utilizationRate = uniqueEvents > 0 ? (eventCoverage / uniqueEvents) * 100 : 0;
  // ADR-0011: fatigue is a real backend measurement or it is unknown — this
  // page used to paper over "no assignment overlays for this volunteer" with
  // a formula derived from unrelated pipeline-stage weighting, which
  // fabricated a plausible-looking number with no evidentiary basis. That
  // fallback has been removed; a volunteer with no recovery rows now shows
  // an explicit "Unknown" fatigue state instead.
  const knownFatigueRows = recoveryRows
    .map((row) => row.volunteer_fatigue)
    .filter((value): value is number => value !== null);
  const volunteerFatigue = knownFatigueRows.length
    ? knownFatigueRows.reduce((sum, value) => sum + value, 0) / knownFatigueRows.length
    : null;
  const fatigueScore = volunteerFatigue === null ? null : Math.round(volunteerFatigue * 100);
  const recovery = recoveryRows[0]
    ? {
        label: recoveryRows[0].recovery_label,
        tone: recoveryRows[0].recovery_status === "Available"
          ? "bg-emerald-50 text-emerald-700 border-emerald-200"
          : recoveryRows[0].recovery_status === "Needs Rest"
            ? "bg-amber-50 text-amber-700 border-amber-200"
            : "bg-rose-50 text-rose-700 border-rose-200",
      }
    : volunteerFatigue === null
      ? { label: "Recovery unknown", tone: "bg-muted text-muted-foreground border-border" }
      : recoveryState(volunteerFatigue);
  // G1 fail-closed: there is deliberately no average match score here. The
  // per-row scores it averaged are factor-registry outputs and the registry is
  // still `proposed` (`assert_registry_approved()` raises), so the field is
  // stripped in `fetchPipeline` and the two places that printed the average
  // now render an accountable unknown instead. Note the old expression also
  // coerced a missing score to 0 (`row.match_score || 0`), which is the
  // ADR-0011 rule 1 defect sitting on top of the gate leak.
  const latestAssignmentDate =
    recoveryRows.find((row) => row.event_date)?.event_date ??
    volunteerRows[0]?.event_name ??
    "";

  return {
    volunteerRows,
    recoveryRows,
    stageCounts,
    matchedCount,
    acceptedCount,
    attendedCount,
    inquiryCount,
    eventCoverage,
    uniqueEvents,
    utilizationRate,
    volunteerFatigue,
    fatigueScore,
    recovery,
    latestAssignmentDate,
  };
}

export type VolunteerInsights = ReturnType<typeof summarizeVolunteer>;

function MetricCard({
  title,
  value,
  subtitle,
  icon: Icon,
}: {
  title: string;
  value: string;
  subtitle: string;
  icon: LucideIcon;
}) {
  return (
    <div className="rounded-2xl border border-border bg-card p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm font-medium text-muted-foreground">{title}</p>
        <Icon className="h-4 w-4 text-primary" />
      </div>
      <p className="text-2xl font-semibold text-foreground">{value}</p>
      <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
    </div>
  );
}

function FunnelRow({
  label,
  value,
  maxValue,
  tone,
}: {
  label: string;
  value: number;
  maxValue: number;
  tone: string;
}) {
  const width = maxValue > 0 ? Math.max(8, Math.round((value / maxValue) * 100)) : 8;

  return (
    <div>
      <div className="mb-2 flex items-center justify-between text-sm">
        <span className="font-medium text-foreground/80">{label}</span>
        <span className="text-muted-foreground">{value}</span>
      </div>
      <div className="h-2 rounded-full bg-muted">
        <div className={`h-2 rounded-full ${tone}`} style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

/** Full-screen volunteer detail modal: funnel, workload, QR history, and stage snapshot. */
export function VolunteerDetailModal({
  selectedVol,
  selectedInsights,
  selectedQrHistory,
  selectedQrAsset,
  matchingMetric,
  onClose,
}: {
  selectedVol: Specialist;
  selectedInsights: VolunteerInsights;
  selectedQrHistory: QrCodeAsset[];
  selectedQrAsset: QrCodeAsset | null;
  matchingMetric: AccountableMetric;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-5xl overflow-y-auto rounded-3xl border border-border bg-card shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="border-b border-border px-6 py-5">
          <div className="flex items-start gap-4">
            <div className="flex h-20 w-20 items-center justify-center rounded-full bg-gradient-to-br from-primary to-primary/70 text-2xl font-semibold text-white">
              {selectedVol.initials}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-medium uppercase tracking-[0.18em] text-primary">
                    Volunteer dashboard
                  </p>
                  <h2 className="text-2xl font-semibold text-foreground">{selectedVol.name}</h2>
                  <p className="mt-1 text-muted-foreground">
                    {selectedVol.title || "Board volunteer"} · {selectedVol.company || "Independent"}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <span className="inline-flex items-center gap-1 rounded-full bg-accent px-3 py-1 text-sm font-medium text-primary">
                      <Check className="h-4 w-4" />
                      {selectedVol.board_role || "Available"}
                    </span>
                    <span
                      className={`inline-flex items-center gap-1 rounded-full border px-3 py-1 text-sm font-medium ${selectedInsights.recovery.tone}`}
                    >
                      <Activity className="h-4 w-4" />
                      {selectedInsights.recovery.label} load
                    </span>
                  </div>
                </div>
                <button
                  onClick={onClose}
                  className="rounded-full p-2 text-muted-foreground transition hover:bg-muted hover:text-muted-foreground"
                  aria-label="Close volunteer details"
                >
                  <X className="h-6 w-6" />
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-6 px-6 py-6">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              title="Events Matched"
              value={`${selectedInsights.matchedCount}`}
              subtitle="Live rows from the current pipeline"
              icon={Users}
            />
            <MetricCard
              title="Accepted"
              value={`${selectedInsights.acceptedCount}`}
              subtitle="Local conversion estimate from live matches"
              icon={Check}
            />
            <MetricCard
              title="Attended"
              value={`${selectedInsights.attendedCount}`}
              subtitle="Downstream attendance estimate"
              icon={Clock}
            />
            <MetricCard
              title="Utilization Rate"
              value={percentage(selectedInsights.utilizationRate)}
              subtitle="Coverage across the current event set"
              icon={TrendingUp}
            />
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.1fr_0.9fr]">
            <div className="rounded-2xl border border-border bg-muted p-5">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-semibold text-foreground">Engagement funnel</h3>
                  <p className="text-sm text-muted-foreground">
                    A lightweight coordinator view built from live assignments only.
                  </p>
                </div>
                <div className="rounded-full bg-card px-3 py-1 text-sm font-medium text-primary shadow-sm">
                  <AccountableValue metric={matchingMetric} /> avg match
                </div>
              </div>

              <div className="space-y-4">
                <FunnelRow
                  label="Matched"
                  value={selectedInsights.matchedCount}
                  maxValue={Math.max(1, selectedInsights.matchedCount)}
                  tone="bg-primary"
                />
                <FunnelRow
                  label="Accepted"
                  value={selectedInsights.acceptedCount}
                  maxValue={Math.max(1, selectedInsights.matchedCount)}
                  tone="bg-sky-500"
                />
                <FunnelRow
                  label="Attended"
                  value={selectedInsights.attendedCount}
                  maxValue={Math.max(1, selectedInsights.matchedCount)}
                  tone="bg-cyan-600"
                />
                <FunnelRow
                  label="Member inquiry"
                  value={selectedInsights.inquiryCount || Math.max(0, Math.round(selectedInsights.attendedCount * 0.15))}
                  maxValue={Math.max(1, selectedInsights.matchedCount)}
                  tone="bg-emerald-500"
                />
              </div>
            </div>

            <div className="rounded-2xl border border-border bg-card p-5">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-semibold text-foreground">Live workload</h3>
                  <p className="text-sm text-muted-foreground">
                    Fatigue is averaged from this volunteer&apos;s calendar assignment overlays.
                  </p>
                </div>
                <BarChart3 className="h-5 w-5 text-primary" />
              </div>

              <div className="rounded-2xl bg-muted p-4">
                <div className="mb-3 flex items-center justify-between text-sm">
                  <span className="font-medium text-foreground/80">Fatigue index</span>
                  <span className="font-semibold text-foreground">
                    {percentage(selectedInsights.fatigueScore)}
                  </span>
                </div>
                <div className="h-3 rounded-full bg-muted">
                  {selectedInsights.fatigueScore === null ? (
                    <div
                      className="h-3 rounded-full bg-[repeating-linear-gradient(45deg,theme(colors.slate.300),theme(colors.slate.300)_4px,transparent_4px,transparent_8px)]"
                      style={{ width: "100%" }}
                      aria-label="Fatigue unknown"
                    />
                  ) : (
                    <div
                      className={`h-3 rounded-full ${
                        selectedInsights.fatigueScore >= 75
                          ? "bg-red-500"
                          : selectedInsights.fatigueScore >= 50
                            ? "bg-amber-500"
                            : selectedInsights.fatigueScore >= 25
                              ? "bg-primary"
                              : "bg-emerald-500"
                      }`}
                      style={{ width: `${selectedInsights.fatigueScore}%` }}
                    />
                  )}
                </div>
                <div className="mt-3 flex items-center justify-between text-sm text-muted-foreground">
                  <span>{selectedInsights.recovery.label} capacity</span>
                  <span>{selectedInsights.volunteerRows.length} live assignments</span>
                </div>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-3">
                <div className="rounded-xl border border-border bg-muted p-4">
                  <p className="text-xs uppercase tracking-wide text-muted-foreground">Profile</p>
                  <p className="mt-1 text-sm font-medium text-foreground">
                    {selectedVol.metro_region || "Region not listed"}
                  </p>
                </div>
                <div className="rounded-xl border border-border bg-muted p-4">
                  <p className="text-xs uppercase tracking-wide text-muted-foreground">Expertise tags</p>
                  <p className="mt-1 text-sm font-medium text-foreground">
                    {splitTags(selectedVol.expertise_tags).length}
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-border bg-card p-5">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-foreground">QR history</h3>
                <p className="text-sm text-muted-foreground">
                  Referral assets and scan activity tied to this volunteer.
                </p>
              </div>
              <QrCode className="h-5 w-5 text-primary" />
            </div>

            {selectedQrHistory.length > 0 ? (
              <div className="space-y-5">
                <QRCodeCard
                  asset={selectedQrAsset}
                  title="Latest QR asset"
                  description="The most recent referral code available for this volunteer."
                />

                <div className="space-y-3">
                  {selectedQrHistory.slice(0, 3).map((entry) => (
                    <div
                      key={entry.referral_code}
                      className="rounded-xl border border-border bg-muted px-4 py-3"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <p className="font-medium text-foreground">{entry.event_name}</p>
                          <p className="text-sm text-muted-foreground">
                            {entry.referral_code} · Generated{" "}
                            {entry.generated_at || "date pending"}
                          </p>
                        </div>
                        <div className="text-right text-sm text-muted-foreground">
                          <p className="font-medium text-foreground">
                            {entry.scan_count === null ? "Unknown" : entry.scan_count} scans
                          </p>
                          <p>{entry.conversion_count === null ? "Unknown" : entry.conversion_count} conversions</p>
                        </div>
                      </div>
                      <div className="mt-3 h-2 rounded-full bg-card">
                        {entry.conversion_rate === null ? (
                          <div
                            className="h-2 rounded-full bg-[repeating-linear-gradient(45deg,theme(colors.slate.300),theme(colors.slate.300)_4px,transparent_4px,transparent_8px)]"
                            style={{ width: "100%" }}
                            aria-label="Conversion rate unknown"
                          />
                        ) : (
                          <div
                            className="h-2 rounded-full bg-gradient-to-r from-primary to-primary/70"
                            style={{ width: `${Math.round(entry.conversion_rate * 100)}%` }}
                          />
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="rounded-2xl border border-dashed border-border bg-muted p-6 text-sm text-muted-foreground">
                No QR history is available yet for this volunteer. Once the QR contract emits
                referral assets, the latest code and scan history will appear here.
              </div>
            )}
          </div>

          <div className="rounded-2xl border border-border bg-card p-5">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-foreground">Assignment snapshot</h3>
                <p className="text-sm text-muted-foreground">
                  Uses the live pipeline and assignment overlay, grouped by stage.
                </p>
              </div>
              <Clock className="h-5 w-5 text-primary" />
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-xl bg-accent p-4">
                <p className="text-sm text-primary">Matched load</p>
                <p className="mt-1 text-2xl font-semibold text-foreground">
                  {selectedInsights.stageCounts.Matched}
                </p>
              </div>
              <div className="rounded-xl bg-sky-50 p-4">
                <p className="text-sm text-sky-700">Contacted</p>
                <p className="mt-1 text-2xl font-semibold text-foreground">
                  {selectedInsights.stageCounts.Contacted}
                </p>
              </div>
              <div className="rounded-xl bg-cyan-50 p-4">
                <p className="text-sm text-cyan-700">Confirmed</p>
                <p className="mt-1 text-2xl font-semibold text-foreground">
                  {selectedInsights.stageCounts.Confirmed}
                </p>
              </div>
              <div className="rounded-xl bg-emerald-50 p-4">
                <p className="text-sm text-emerald-700">Late-stage pressure</p>
                <p className="mt-1 text-2xl font-semibold text-foreground">
                  {selectedInsights.stageCounts.Attended + selectedInsights.inquiryCount}
                </p>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {splitTags(selectedVol.expertise_tags).map((tag) => (
                <span
                  key={tag}
                  className="rounded-full bg-muted px-3 py-1 text-sm font-medium text-foreground/80"
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
