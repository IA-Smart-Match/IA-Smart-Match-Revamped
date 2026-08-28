import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  BarChart3,
  Briefcase,
  Check,
  Clock,
  MapPin,
  QrCode,
  Search,
  TrendingUp,
  Users,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import {
  emptyQrStatsSummary,
  fetchCalendarAssignments,
  fetchPipeline,
  fetchQrStats,
  fetchSpecialists,
  splitTags,
  type CalendarAssignmentSummary,
  type PipelineRecord,
  type QrStatsSummary,
  type Specialist,
} from "@/lib/api";
import {
  MOCK_CALENDAR_ASSIGNMENTS,
  MOCK_PIPELINE,
  MOCK_QR_STATS,
  MOCK_SPECIALISTS,
} from "@/lib/mockData";
import { DemoModeBadge } from "@/app/components/ui/DemoModeBadge";
import { QRCodeCard } from "@/components/QRCodeCard";

function VolunteerSkeleton() {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm animate-pulse">
      <div className="flex items-start gap-4">
        <div className="h-16 w-16 rounded-full bg-slate-200" />
        <div className="flex-1 space-y-3">
          <div className="h-4 w-2/3 rounded bg-slate-200" />
          <div className="h-3 w-1/2 rounded bg-slate-200" />
          <div className="h-5 w-24 rounded-full bg-slate-200" />
        </div>
      </div>
      <div className="mt-5 space-y-2">
        <div className="h-3 rounded bg-slate-200" />
        <div className="h-3 rounded bg-slate-200" />
      </div>
      <div className="mt-6 flex gap-2">
        <div className="h-10 flex-1 rounded-xl bg-slate-200" />
        <div className="h-10 flex-1 rounded-xl bg-slate-200" />
        <div className="h-10 flex-1 rounded-xl bg-slate-200" />
      </div>
    </div>
  );
}

const stageWeights: Record<string, number> = {
  Matched: 1,
  Contacted: 2,
  Confirmed: 3,
  Attended: 4,
  "Member Inquiry": 5,
};

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function normalizeName(value: string) {
  return value.trim().toLowerCase();
}

function percentage(value: number) {
  const normalized = value <= 1 ? value * 100 : value;
  return `${Math.round(clamp(normalized, 0, 100))}%`;
}

function recoveryState(score: number) {
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

function summarizeVolunteer(
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

  let weightedLoad = 0;
  for (const row of volunteerRows) {
    stageCounts[row.stage as keyof typeof stageCounts] =
      (stageCounts[row.stage as keyof typeof stageCounts] ?? 0) + 1;
    weightedLoad += stageWeights[row.stage] ?? 1;
  }

  const matchedCount = volunteerRows.length;
  const acceptedCount = Math.max(Math.round(matchedCount * 0.6), stageCounts.Contacted);
  const attendedCount = Math.max(Math.round(acceptedCount * 0.75), stageCounts.Attended);
  const inquiryCount = stageCounts["Member Inquiry"];
  const eventCoverage = new Set(volunteerRows.map((row) => row.event_name)).size;
  const uniqueEvents = new Set(pipeline.map((row) => row.event_name)).size;
  const utilizationRate = uniqueEvents > 0 ? (eventCoverage / uniqueEvents) * 100 : 0;
  const backendFatigue =
    recoveryRows.length > 0
      ? recoveryRows.reduce((sum, row) => sum + row.volunteer_fatigue, 0) / recoveryRows.length
      : null;
  const fallbackFatigue = clamp(
    (12 + weightedLoad * 11 + stageCounts.Attended * 8 + inquiryCount * 10) / 100,
    0,
    1,
  );
  const volunteerFatigue = backendFatigue ?? fallbackFatigue;
  const fatigueScore = Math.round(volunteerFatigue * 100);
  const recovery = recoveryRows[0]
    ? {
        label: recoveryRows[0].recovery_label,
        tone: recoveryRows[0].recovery_status === "Available"
          ? "bg-emerald-50 text-emerald-700 border-emerald-200"
          : recoveryRows[0].recovery_status === "Needs Rest"
            ? "bg-amber-50 text-amber-700 border-amber-200"
            : "bg-rose-50 text-rose-700 border-rose-200",
      }
    : recoveryState(volunteerFatigue);
  const avgMatchScore =
    matchedCount > 0
      ? volunteerRows.reduce((sum, row) => sum + Number(row.match_score || 0), 0) / matchedCount
      : 0;
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
    avgMatchScore,
  };
}

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
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm font-medium text-slate-600">{title}</p>
        <Icon className="h-4 w-4 text-blue-600" />
      </div>
      <p className="text-2xl font-semibold text-slate-900">{value}</p>
      <p className="mt-1 text-sm text-slate-500">{subtitle}</p>
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
        <span className="font-medium text-slate-700">{label}</span>
        <span className="text-slate-500">{value}</span>
      </div>
      <div className="h-2 rounded-full bg-slate-100">
        <div className={`h-2 rounded-full ${tone}`} style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

export function Volunteers() {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedVolunteer, setSelectedVolunteer] = useState<string | null>(null);
  const [volunteers, setVolunteers] = useState<Specialist[]>([]);
  const [pipeline, setPipeline] = useState<PipelineRecord[]>([]);
  const [assignments, setAssignments] = useState<CalendarAssignmentSummary[]>([]);
  const [qrStats, setQrStats] = useState<QrStatsSummary>(emptyQrStatsSummary());
  const [isMockData, setIsMockData] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    Promise.allSettled([
      fetchSpecialists(),
      fetchPipeline(),
      fetchCalendarAssignments(),
      fetchQrStats(),
    ])
      .then(([specialistResult, pipelineResult, assignmentResult, qrResult]) => {
        if (!active) {
          return;
        }
        if (specialistResult.status !== "fulfilled" || pipelineResult.status !== "fulfilled") {
          throw (
            specialistResult.status === "rejected"
              ? specialistResult.reason
              : (pipelineResult as PromiseRejectedResult).reason
          );
        }

        let anyMock = false;

        setVolunteers(specialistResult.value.data);
        if (specialistResult.value.isMockData) anyMock = true;

        setPipeline(pipelineResult.value.data);
        if (pipelineResult.value.isMockData) anyMock = true;

        if (assignmentResult.status === "fulfilled") {
          setAssignments(assignmentResult.value.data);
          if (assignmentResult.value.isMockData) anyMock = true;
        } else {
          setAssignments(MOCK_CALENDAR_ASSIGNMENTS);
          anyMock = true;
        }

        if (qrResult.status === "fulfilled") {
          setQrStats(qrResult.value.data);
          if (qrResult.value.isMockData) anyMock = true;
        } else {
          setQrStats(MOCK_QR_STATS);
          anyMock = true;
        }

        setIsMockData(anyMock);

        const warnings = [];
        if (assignmentResult.status === "rejected") {
          warnings.push(
            assignmentResult.reason instanceof Error
              ? `Assignment overlays are unavailable: ${assignmentResult.reason.message}`
              : "Assignment overlays are unavailable.",
          );
        }
        if (qrResult.status === "rejected") {
          warnings.push(
            qrResult.reason instanceof Error
              ? `QR analytics are unavailable: ${qrResult.reason.message}`
              : "QR analytics are unavailable.",
          );
        }
        setError(warnings.length ? warnings.join(" ") : null);
      })
      .catch((err: unknown) => {
        if (!active) {
          return;
        }
        // Backend unreachable — use Layer-3 mock constants
        setVolunteers(MOCK_SPECIALISTS);
        setPipeline(MOCK_PIPELINE);
        setAssignments(MOCK_CALENDAR_ASSIGNMENTS);
        setQrStats(MOCK_QR_STATS);
        setIsMockData(true);
        setError(err instanceof Error ? err.message : "Failed to load volunteers.");
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  const filteredVolunteers = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();

    return volunteers.filter((volunteer) => {
      const expertise = splitTags(volunteer.expertise_tags);
      if (!query) {
        return true;
      }

      return (
        volunteer.name.toLowerCase().includes(query) ||
        volunteer.company.toLowerCase().includes(query) ||
        volunteer.metro_region.toLowerCase().includes(query) ||
        expertise.some((tag) => tag.toLowerCase().includes(query))
      );
    });
  }, [searchQuery, volunteers]);

  const selectedVol =
    volunteers.find((volunteer) => volunteer.name === selectedVolunteer) ?? null;
  const selectedInsights = selectedVol
    ? summarizeVolunteer(selectedVol, pipeline, assignments)
    : null;
  const selectedQrHistory = useMemo(() => {
    if (!selectedVol) {
      return [];
    }

    const selectedName = normalizeName(selectedVol.name);
    return [...qrStats.entries]
      .filter((entry) => normalizeName(entry.speaker_name) === selectedName)
      .sort((left, right) => {
        const leftTime = Date.parse(left.last_scanned_at || left.generated_at || "");
        const rightTime = Date.parse(right.last_scanned_at || right.generated_at || "");
        return (Number.isFinite(rightTime) ? rightTime : 0) - (Number.isFinite(leftTime) ? leftTime : 0);
      });
  }, [qrStats.entries, selectedVol]);
  const selectedQrAsset = selectedQrHistory[0] ?? null;

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="space-y-2">
        <p className="text-sm font-medium uppercase tracking-[0.18em] text-blue-700">
          Volunteer management
        </p>
        <h1 className="text-3xl font-semibold text-slate-900">
          Volunteer Profiles{isMockData && <DemoModeBadge />}
        </h1>
        <p className="text-slate-600">
          Browse the live roster, inspect assignment load, and open a dashboard-style detail view
          for any volunteer.
        </p>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search by name, company, region, or expertise..."
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            className="w-full rounded-xl border border-slate-300 py-3 pl-10 pr-4 text-slate-900 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          />
        </div>
      </div>

      {error ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-center text-red-700">
          {error}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {loading
          ? Array.from({ length: 6 }, (_, index) => <VolunteerSkeleton key={index} />)
          : filteredVolunteers.map((volunteer) => {
              const expertise = splitTags(volunteer.expertise_tags);
              const profile = summarizeVolunteer(volunteer, pipeline, assignments);

              return (
                <button
                  key={volunteer.name}
                  type="button"
                  onClick={() => setSelectedVolunteer(volunteer.name)}
                  className="rounded-2xl border border-slate-200 bg-white p-6 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
                >
                  <div className="mb-4 flex items-start gap-4">
                    <div className="flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br from-blue-600 to-sky-500 text-xl font-semibold text-white">
                      {volunteer.initials}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <h3 className="truncate font-semibold text-slate-900">{volunteer.name}</h3>
                          <p className="text-sm text-slate-600">
                            {volunteer.title || "Board volunteer"}
                          </p>
                        </div>
                        <span
                          className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium ${profile.recovery.tone}`}
                        >
                          <Activity className="h-3.5 w-3.5" />
                          {profile.recovery.label}
                        </span>
                      </div>
                      <div className="mt-3 flex items-center gap-2">
                        <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700">
                          <Check className="h-3 w-3" />
                          {volunteer.board_role || "Available"}
                        </span>
                        <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
                          <Users className="h-3 w-3" />
                          {profile.matchedCount} live matches
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-2 text-sm text-slate-600">
                    <div className="flex items-center gap-2">
                      <Briefcase className="h-4 w-4 text-blue-600" />
                      <span>{volunteer.company || "Independent"}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <MapPin className="h-4 w-4 text-blue-600" />
                      <span>{volunteer.metro_region || "Region not listed"}</span>
                    </div>
                  </div>

                  <div className="mt-4">
                    <div className="mb-2 flex items-center justify-between text-xs uppercase tracking-wide text-slate-500">
                      <span>Recovery / load</span>
                      <span>{percentage(profile.fatigueScore)}</span>
                    </div>
                    <div className="h-2 rounded-full bg-slate-100">
                      <div
                        className={`h-2 rounded-full ${
                          profile.fatigueScore >= 75
                            ? "bg-red-500"
                            : profile.fatigueScore >= 50
                              ? "bg-amber-500"
                              : profile.fatigueScore >= 25
                                ? "bg-blue-500"
                                : "bg-emerald-500"
                        }`}
                        style={{ width: `${profile.fatigueScore}%` }}
                      />
                    </div>
                  </div>

                  <div className="mt-5 flex items-center justify-between rounded-xl bg-slate-50 px-4 py-3">
                    <div>
                      <p className="text-xs uppercase tracking-wide text-slate-500">Match depth</p>
                      <p className="text-lg font-semibold text-slate-900">{profile.matchedCount}</p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-slate-500">Coverage</p>
                      <p className="text-lg font-semibold text-blue-600">
                        {percentage(profile.utilizationRate)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-slate-500">Avg score</p>
                      <p className="text-lg font-semibold text-slate-900">
                        {percentage(profile.avgMatchScore * 100)}
                      </p>
                    </div>
                  </div>

                  <div className="mt-4 rounded-2xl border border-blue-100 bg-blue-50/80 px-4 py-3">
                    <p className="text-xs uppercase tracking-[0.18em] text-blue-700">Recovery badge</p>
                    <p className="mt-1 text-sm font-semibold text-slate-900">
                      {profile.recovery.label}
                    </p>
                    <p className="mt-1 text-sm text-slate-600">
                      {profile.recoveryRows.length
                        ? `${profile.recoveryRows.length} assignment overlay rows from the backend contract`
                        : "Recovery is falling back to the live pipeline footprint."}
                    </p>
                  </div>

                  <div className="mt-4 flex flex-wrap gap-2">
                    {expertise.slice(0, 4).map((tag) => (
                      <span
                        key={tag}
                        className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </button>
              );
            })}
      </div>

      {!loading && !error && filteredVolunteers.length === 0 ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center text-slate-600 shadow-sm">
          No volunteers matched that search.
        </div>
      ) : null}

      {selectedVol && selectedInsights ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/55 p-4 backdrop-blur-sm"
          onClick={() => setSelectedVolunteer(null)}
        >
          <div
            className="max-h-[90vh] w-full max-w-5xl overflow-y-auto rounded-3xl border border-slate-200 bg-white shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="border-b border-slate-200 px-6 py-5">
              <div className="flex items-start gap-4">
                <div className="flex h-20 w-20 items-center justify-center rounded-full bg-gradient-to-br from-blue-600 to-sky-500 text-2xl font-semibold text-white">
                  {selectedVol.initials}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium uppercase tracking-[0.18em] text-blue-700">
                        Volunteer dashboard
                      </p>
                      <h2 className="text-2xl font-semibold text-slate-900">{selectedVol.name}</h2>
                      <p className="mt-1 text-slate-600">
                        {selectedVol.title || "Board volunteer"} · {selectedVol.company || "Independent"}
                      </p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-3 py-1 text-sm font-medium text-blue-700">
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
                      onClick={() => setSelectedVolunteer(null)}
                      className="rounded-full p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
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
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                  <div className="mb-4 flex items-center justify-between">
                    <div>
                      <h3 className="text-lg font-semibold text-slate-900">Engagement funnel</h3>
                      <p className="text-sm text-slate-600">
                        A lightweight coordinator view built from live assignments only.
                      </p>
                    </div>
                    <div className="rounded-full bg-white px-3 py-1 text-sm font-medium text-blue-700 shadow-sm">
                      {percentage(selectedInsights.avgMatchScore * 100)} avg match
                    </div>
                  </div>

                  <div className="space-y-4">
                    <FunnelRow
                      label="Matched"
                      value={selectedInsights.matchedCount}
                      maxValue={Math.max(1, selectedInsights.matchedCount)}
                      tone="bg-blue-600"
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

                <div className="rounded-2xl border border-slate-200 bg-white p-5">
                  <div className="mb-4 flex items-center justify-between">
                    <div>
                      <h3 className="text-lg font-semibold text-slate-900">Live workload</h3>
                      <p className="text-sm text-slate-600">
                        Fatigue is derived locally from the current pipeline footprint.
                      </p>
                    </div>
                    <BarChart3 className="h-5 w-5 text-blue-600" />
                  </div>

                  <div className="rounded-2xl bg-slate-50 p-4">
                    <div className="mb-3 flex items-center justify-between text-sm">
                      <span className="font-medium text-slate-700">Fatigue index</span>
                      <span className="font-semibold text-slate-900">
                        {percentage(selectedInsights.fatigueScore)}
                      </span>
                    </div>
                    <div className="h-3 rounded-full bg-slate-200">
                      <div
                        className={`h-3 rounded-full ${
                          selectedInsights.fatigueScore >= 75
                            ? "bg-red-500"
                            : selectedInsights.fatigueScore >= 50
                              ? "bg-amber-500"
                              : selectedInsights.fatigueScore >= 25
                                ? "bg-blue-500"
                                : "bg-emerald-500"
                        }`}
                        style={{ width: `${selectedInsights.fatigueScore}%` }}
                      />
                    </div>
                    <div className="mt-3 flex items-center justify-between text-sm text-slate-600">
                      <span>{selectedInsights.recovery.label} capacity</span>
                      <span>{selectedInsights.volunteerRows.length} live assignments</span>
                    </div>
                  </div>

                  <div className="mt-4 grid grid-cols-2 gap-3">
                    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                      <p className="text-xs uppercase tracking-wide text-slate-500">Profile</p>
                      <p className="mt-1 text-sm font-medium text-slate-900">
                        {selectedVol.metro_region || "Region not listed"}
                      </p>
                    </div>
                    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                      <p className="text-xs uppercase tracking-wide text-slate-500">Expertise tags</p>
                      <p className="mt-1 text-sm font-medium text-slate-900">
                        {splitTags(selectedVol.expertise_tags).length}
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-5">
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <h3 className="text-lg font-semibold text-slate-900">QR history</h3>
                    <p className="text-sm text-slate-600">
                      Referral assets and scan activity tied to this volunteer.
                    </p>
                  </div>
                  <QrCode className="h-5 w-5 text-blue-600" />
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
                          className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3"
                        >
                          <div className="flex flex-wrap items-start justify-between gap-2">
                            <div>
                              <p className="font-medium text-slate-900">{entry.event_name}</p>
                              <p className="text-sm text-slate-600">
                                {entry.referral_code} · Generated{" "}
                                {entry.generated_at || "date pending"}
                              </p>
                            </div>
                            <div className="text-right text-sm text-slate-600">
                              <p className="font-medium text-slate-900">
                                {entry.scan_count} scans
                              </p>
                              <p>{entry.conversion_count} conversions</p>
                            </div>
                          </div>
                          <div className="mt-3 h-2 rounded-full bg-white">
                            <div
                              className="h-2 rounded-full bg-gradient-to-r from-blue-600 to-sky-500"
                              style={{ width: `${Math.round(entry.conversion_rate * 100)}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-6 text-sm text-slate-600">
                    No QR history is available yet for this volunteer. Once the QR contract emits
                    referral assets, the latest code and scan history will appear here.
                  </div>
                )}
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-5">
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <h3 className="text-lg font-semibold text-slate-900">Assignment snapshot</h3>
                    <p className="text-sm text-slate-600">
                      Uses the live pipeline and assignment overlay, grouped by stage.
                    </p>
                  </div>
                  <Clock className="h-5 w-5 text-blue-600" />
                </div>

                <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                  <div className="rounded-xl bg-blue-50 p-4">
                    <p className="text-sm text-blue-700">Matched load</p>
                    <p className="mt-1 text-2xl font-semibold text-slate-900">
                      {selectedInsights.stageCounts.Matched}
                    </p>
                  </div>
                  <div className="rounded-xl bg-sky-50 p-4">
                    <p className="text-sm text-sky-700">Contacted</p>
                    <p className="mt-1 text-2xl font-semibold text-slate-900">
                      {selectedInsights.stageCounts.Contacted}
                    </p>
                  </div>
                  <div className="rounded-xl bg-cyan-50 p-4">
                    <p className="text-sm text-cyan-700">Confirmed</p>
                    <p className="mt-1 text-2xl font-semibold text-slate-900">
                      {selectedInsights.stageCounts.Confirmed}
                    </p>
                  </div>
                  <div className="rounded-xl bg-emerald-50 p-4">
                    <p className="text-sm text-emerald-700">Late-stage pressure</p>
                    <p className="mt-1 text-2xl font-semibold text-slate-900">
                      {selectedInsights.stageCounts.Attended + selectedInsights.inquiryCount}
                    </p>
                  </div>
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  {splitTags(selectedVol.expertise_tags).map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full bg-slate-100 px-3 py-1 text-sm font-medium text-slate-700"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
