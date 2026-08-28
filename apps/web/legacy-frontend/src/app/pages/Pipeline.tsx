import { useEffect, useState } from "react";
import {
  Filter,
  TrendingUp,
  Users,
  UserPlus,
  Briefcase,
  CheckCircle2,
  CalendarDays,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Funnel,
  FunnelChart,
  LabelList,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  emptyFeedbackStatsSummary,
  emptyQrStatsSummary,
  fetchEvents,
  fetchFeedbackStats,
  fetchPipeline,
  fetchQrStats,
  type CppEvent,
  type FeedbackStatsSummary,
  type PipelineRecord,
  type QrStatsSummary,
} from "@/lib/api";
import {
  MOCK_EVENTS,
  MOCK_FEEDBACK_STATS,
  MOCK_PIPELINE,
  MOCK_QR_STATS,
} from "@/lib/mockData";
import { DemoModeBadge } from "@/app/components/ui/DemoModeBadge";

const stagePalette = ["#a78bfa", "#8b5cf6", "#7c3aed", "#6d28d9", "#5b21b6"];

type StageSummary = {
  name: string;
  count: number;
  order: number;
  fill: string;
};

type UniversityRow = {
  name: string;
  Matched: number;
  Contacted: number;
  Confirmed: number;
  Attended: number;
  "Member Inquiry": number;
};

function formatFactorName(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function summarizeStages(records: PipelineRecord[]): StageSummary[] {
  const counts = new Map<string, { count: number; order: number }>();
  for (const record of records) {
    const stage = record.stage || "Unknown";
    const order = Number(record.stage_order) || 0;
    const current = counts.get(stage);
    counts.set(stage, {
      count: (current?.count ?? 0) + 1,
      order: current?.order ?? order,
    });
  }
  return Array.from(counts.entries())
    .sort((a, b) => a[1].order - b[1].order)
    .map(([name, value], index) => ({
      name,
      count: value.count,
      order: value.order,
      fill: stagePalette[index % stagePalette.length],
    }));
}

function buildUniversityBreakdown(records: PipelineRecord[], events: CppEvent[]): UniversityRow[] {
  const hostByEvent = new Map<string, string>();
  for (const event of events) {
    hostByEvent.set(
      event["Event / Program"],
      event["Host / Unit"] || "Unknown Host",
    );
  }

  const grouped = new Map<string, UniversityRow>();
  for (const record of records) {
    const host = hostByEvent.get(record.event_name) || "Unknown Host";
    const row =
      grouped.get(host) ?? {
        name: host,
        Matched: 0,
        Contacted: 0,
        Confirmed: 0,
        Attended: 0,
        "Member Inquiry": 0,
      };
    const numericKeys = ["Matched", "Contacted", "Confirmed", "Attended", "Member Inquiry"] as const;
    type NumericKey = (typeof numericKeys)[number];
    if (numericKeys.includes(record.stage as NumericKey)) {
      row[record.stage as NumericKey] += 1;
    }
    grouped.set(host, row);
  }

  return Array.from(grouped.values()).sort(
    (a, b) =>
      b.Matched + b.Contacted + b.Confirmed + b.Attended + b["Member Inquiry"] -
      (a.Matched + a.Contacted + a.Confirmed + a.Attended + a["Member Inquiry"]),
  );
}

export function Pipeline() {
  const [pipelineRecords, setPipelineRecords] = useState<PipelineRecord[]>([]);
  const [events, setEvents] = useState<CppEvent[]>([]);
  const [qrStats, setQrStats] = useState<QrStatsSummary>(emptyQrStatsSummary());
  const [feedbackStats, setFeedbackStats] = useState<FeedbackStatsSummary>(
    emptyFeedbackStatsSummary(),
  );
  const [isMockData, setIsMockData] = useState(false);
  const [selectedUniversity, setSelectedUniversity] = useState("All Hosts");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    Promise.allSettled([
      fetchPipeline(),
      fetchEvents(),
      fetchQrStats(),
      fetchFeedbackStats(),
    ])
      .then(([pipelineResult, eventResult, qrResult, feedbackResult]) => {
        if (!active) {
          return;
        }
        if (pipelineResult.status !== "fulfilled" || eventResult.status !== "fulfilled") {
          throw (
            pipelineResult.status === "rejected"
              ? pipelineResult.reason
              : (eventResult as PromiseRejectedResult).reason
          );
        }

        let anyMock = false;

        setPipelineRecords(pipelineResult.value.data);
        if (pipelineResult.value.isMockData) anyMock = true;

        setEvents(eventResult.value.data);
        if (eventResult.value.isMockData) anyMock = true;

        if (qrResult.status === "fulfilled") {
          setQrStats(qrResult.value.data);
          if (qrResult.value.isMockData) anyMock = true;
        } else {
          setQrStats(MOCK_QR_STATS);
          anyMock = true;
        }

        if (feedbackResult.status === "fulfilled") {
          setFeedbackStats(feedbackResult.value.data);
          if (feedbackResult.value.isMockData) anyMock = true;
        } else {
          setFeedbackStats(MOCK_FEEDBACK_STATS);
          anyMock = true;
        }

        setIsMockData(anyMock);

        const warnings = [];
        if (qrResult.status === "rejected") {
          warnings.push(
            qrResult.reason instanceof Error
              ? `QR analytics are unavailable: ${qrResult.reason.message}`
              : "QR analytics are unavailable.",
          );
        }
        if (feedbackResult.status === "rejected") {
          warnings.push(
            feedbackResult.reason instanceof Error
              ? `Feedback optimizer stats are unavailable: ${feedbackResult.reason.message}`
              : "Feedback optimizer stats are unavailable.",
          );
        }
        setError(warnings.length ? warnings.join(" ") : null);
      })
      .catch((err: unknown) => {
        if (active) {
          // Backend unreachable — use Layer-3 mock constants
          setPipelineRecords(MOCK_PIPELINE);
          setEvents(MOCK_EVENTS);
          setQrStats(MOCK_QR_STATS);
          setFeedbackStats(MOCK_FEEDBACK_STATS);
          setIsMockData(true);
          setError(err instanceof Error ? err.message : "Failed to load pipeline data.");
        }
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

  const breakdown = buildUniversityBreakdown(pipelineRecords, events);
  const hosts = ["All Hosts", ...breakdown.map((row) => row.name)];
  const filteredBreakdown =
    selectedUniversity === "All Hosts"
      ? breakdown
      : breakdown.filter((row) => row.name === selectedUniversity);
  const filteredRecords =
    selectedUniversity === "All Hosts"
      ? pipelineRecords
      : pipelineRecords.filter((record) => {
          const matchingEvent = events.find(
            (event) => event["Event / Program"] === record.event_name,
          );
          return (matchingEvent?.["Host / Unit"] || "Unknown Host") === selectedUniversity;
        });

  const stageSummary = summarizeStages(filteredRecords);
  const conversions = stageSummary.slice(0, -1).map((stage, index) => {
    const next = stageSummary[index + 1];
    return {
      from: stage.name,
      to: next.name,
      rate: stage.count ? ((next.count / stage.count) * 100).toFixed(1) : "0.0",
    };
  });

  const stageCount = (stageName: string) =>
    stageSummary.find((stage) => stage.name === stageName)?.count ?? 0;
  const qrEntries = [...qrStats.entries].sort(
    (left, right) => right.scan_count - left.scan_count || right.conversion_count - left.conversion_count,
  );
  const qrTopEntries = qrEntries.slice(0, 3);
  const leadAdjustment = feedbackStats.recommended_adjustments[0] ?? null;

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div>
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 bg-gradient-to-br from-green-500 to-blue-500 rounded-lg flex items-center justify-center">
            <TrendingUp className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-3xl font-semibold text-gray-900">
            Pipeline Tracking{isMockData && <DemoModeBadge />}
          </h1>
        </div>
        <p className="text-gray-600">
          Monitor how ranked matches move through the live sample pipeline.
        </p>
      </div>

      <div className="bg-white rounded-xl p-4 border border-gray-200 shadow-sm">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <Filter className="w-5 h-5 text-gray-500" />
            <span className="text-sm font-medium text-gray-700">Host Filter:</span>
          </div>

          <select
            value={selectedUniversity}
            onChange={(event) => setSelectedUniversity(event.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
          >
            {hosts.map((host) => (
              <option key={host} value={host}>
                {host}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error ? (
        <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-red-700 text-center">
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="h-80 rounded-xl border border-gray-200 bg-white shadow-sm animate-pulse" />
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
            <div className="bg-white rounded-xl p-6 border border-gray-200 shadow-sm">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                  <Users className="w-5 h-5 text-blue-600" />
                </div>
                <div>
                  <p className="text-sm text-gray-600">Matched</p>
                  <p className="text-2xl font-semibold text-gray-900">{stageCount("Matched")}</p>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-xl p-6 border border-gray-200 shadow-sm">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                  <CalendarDays className="w-5 h-5 text-blue-600" />
                </div>
                <div>
                  <p className="text-sm text-gray-600">Contacted</p>
                  <p className="text-2xl font-semibold text-gray-900">
                    {stageCount("Contacted")}
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-xl p-6 border border-gray-200 shadow-sm">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
                  <CheckCircle2 className="w-5 h-5 text-green-600" />
                </div>
                <div>
                  <p className="text-sm text-gray-600">Confirmed</p>
                  <p className="text-2xl font-semibold text-gray-900">
                    {stageCount("Confirmed")}
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-xl p-6 border border-gray-200 shadow-sm">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 bg-orange-100 rounded-lg flex items-center justify-center">
                  <UserPlus className="w-5 h-5 text-orange-600" />
                </div>
                <div>
                  <p className="text-sm text-gray-600">Attended</p>
                  <p className="text-2xl font-semibold text-gray-900">
                    {stageCount("Attended")}
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-xl p-6 border border-gray-200 shadow-sm">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 bg-indigo-100 rounded-lg flex items-center justify-center">
                  <Briefcase className="w-5 h-5 text-indigo-600" />
                </div>
                <div>
                  <p className="text-sm text-gray-600">Member Inquiry</p>
                  <p className="text-2xl font-semibold text-gray-900">
                    {stageCount("Member Inquiry")}
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-xl p-6 border border-gray-200 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3 mb-6">
              <div>
                <h3 className="text-xl font-semibold text-gray-900">QR ROI Tracking</h3>
                <p className="text-sm text-gray-600 mt-1">
                  Referral codes, scans, and downstream conversion signals from the QR contract.
                </p>
              </div>
              <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">
                {qrStats.total_generated > 0 ? "Live referrals" : "Awaiting QR data"}
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
              <div className="rounded-xl border border-blue-100 bg-blue-50/70 p-4">
                <p className="text-sm font-medium text-blue-700">Codes generated</p>
                <p className="mt-2 text-3xl font-semibold text-gray-900">{qrStats.total_generated}</p>
                <p className="mt-1 text-xs text-gray-600">Deterministic referral assets created.</p>
              </div>
              <div className="rounded-xl border border-blue-100 bg-blue-50/70 p-4">
                <p className="text-sm font-medium text-blue-700">Total scans</p>
                <p className="mt-2 text-3xl font-semibold text-gray-900">{qrStats.total_scans}</p>
                <p className="mt-1 text-xs text-gray-600">Tracks the redirect endpoint activity.</p>
              </div>
              <div className="rounded-xl border border-blue-100 bg-blue-50/70 p-4">
                <p className="text-sm font-medium text-blue-700">Conversions</p>
                <p className="mt-2 text-3xl font-semibold text-gray-900">{qrStats.total_conversions}</p>
                <p className="mt-1 text-xs text-gray-600">Membership-interest outcomes attributed to QR.</p>
              </div>
              <div className="rounded-xl border border-blue-100 bg-blue-50/70 p-4">
                <p className="text-sm font-medium text-blue-700">Scan-to-conversion</p>
                <p className="mt-2 text-3xl font-semibold text-gray-900">
                  {Math.round(qrStats.conversion_rate * 100)}%
                </p>
                <p className="mt-1 text-xs text-gray-600">Rollup efficiency across all referrals.</p>
              </div>
            </div>

            <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-[1.1fr_0.9fr]">
              <div className="rounded-xl border border-gray-200 bg-slate-50 p-4">
                <div className="mb-4 flex items-center justify-between">
                  <h4 className="font-semibold text-gray-900">Top referral history</h4>
                  <span className="text-xs uppercase tracking-wide text-gray-500">scan volume</span>
                </div>
                <div className="space-y-3">
                  {qrTopEntries.length === 0 ? (
                    <div className="rounded-lg border border-dashed border-gray-300 bg-white p-4 text-sm text-gray-600">
                      QR rows will appear here once the backend emits referral assets.
                    </div>
                  ) : (
                    qrTopEntries.map((entry) => (
                      <div
                        key={entry.referral_code}
                        className="flex items-center justify-between gap-3 rounded-lg border border-white bg-white px-4 py-3 shadow-sm"
                      >
                        <div className="min-w-0">
                          <p className="truncate font-medium text-gray-900">{entry.speaker_name}</p>
                          <p className="truncate text-sm text-gray-600">
                            {entry.event_name || "Event pending"} · {entry.referral_code}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-sm font-semibold text-gray-900">{entry.scan_count} scans</p>
                          <p className="text-xs text-gray-500">{entry.conversion_count} conversions</p>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              <div className="rounded-xl border border-gray-200 bg-white p-4">
                <h4 className="mb-4 font-semibold text-gray-900">ROI notes</h4>
                <div className="space-y-3 text-sm text-gray-600">
                  <p>
                    Referral codes stay deterministic per speaker-event pair, so repeated outreach can
                    reuse the same attribution key.
                  </p>
                  <p>
                    Scans are the leading signal, while downstream membership-interest conversions are
                    the primary ROI target for this phase.
                  </p>
                  <p>
                    If the QR service is unavailable, the page keeps rendering with zeroed analytics
                    instead of failing the entire pipeline surface.
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-xl p-6 border border-gray-200 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3 mb-6">
              <div>
                <h3 className="text-xl font-semibold text-gray-900">Continuous Improvement</h3>
                <p className="text-sm text-gray-600 mt-1">
                  Feedback-driven acceptance, pain-score, and weight-shift telemetry for the matcher.
                </p>
              </div>
              <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">
                {feedbackStats.total_feedback > 0 ? "Optimizer active" : "Awaiting feedback"}
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
              <div className="rounded-xl border border-blue-100 bg-blue-50/70 p-4">
                <p className="text-sm font-medium text-blue-700">Feedback rows</p>
                <p className="mt-2 text-3xl font-semibold text-gray-900">{feedbackStats.total_feedback}</p>
                <p className="mt-1 text-xs text-gray-600">Coordinator submissions captured so far.</p>
              </div>
              <div className="rounded-xl border border-blue-100 bg-blue-50/70 p-4">
                <p className="text-sm font-medium text-blue-700">Acceptance rate</p>
                <p className="mt-2 text-3xl font-semibold text-gray-900">
                  {Math.round(feedbackStats.acceptance_rate * 100)}%
                </p>
                <p className="mt-1 text-xs text-gray-600">Accept vs. decline signal from the new feedback loop.</p>
              </div>
              <div className="rounded-xl border border-blue-100 bg-blue-50/70 p-4">
                <p className="text-sm font-medium text-blue-700">Pain score</p>
                <p className="mt-2 text-3xl font-semibold text-gray-900">
                  {Math.round(feedbackStats.pain_score)}
                </p>
                <p className="mt-1 text-xs text-gray-600">Tracks how much correction pressure the matcher is under.</p>
              </div>
              <div className="rounded-xl border border-blue-100 bg-blue-50/70 p-4">
                <p className="text-sm font-medium text-blue-700">Lead shift</p>
                <p className="mt-2 text-lg font-semibold text-gray-900">
                  {leadAdjustment ? formatFactorName(leadAdjustment.factor) : "No shift yet"}
                </p>
                <p className="mt-1 text-xs text-gray-600">
                  {leadAdjustment
                    ? `${leadAdjustment.delta > 0 ? "+" : ""}${(leadAdjustment.delta * 100).toFixed(1)} pts`
                    : "Needs more coordinator outcomes."}
                </p>
              </div>
            </div>

            <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-[1.05fr_0.95fr]">
              <div className="rounded-xl border border-gray-200 bg-slate-50 p-4">
                <div className="mb-4 flex items-center justify-between">
                  <h4 className="font-semibold text-gray-900">Acceptance trend</h4>
                  <span className="text-xs uppercase tracking-wide text-gray-500">feedback loop</span>
                </div>
                {feedbackStats.trend.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-gray-300 bg-white p-4 text-sm text-gray-600">
                    Trend rows will appear here once feedback is submitted from the coordinator workflow.
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height={220}>
                    <LineChart
                      data={feedbackStats.trend.map((point) => ({
                        ...point,
                        acceptance_percent: Math.round(point.acceptance_rate * 100),
                      }))}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                      <XAxis dataKey="date" />
                      <YAxis />
                      <Tooltip />
                      <Line
                        type="monotone"
                        dataKey="acceptance_percent"
                        stroke="#2563eb"
                        strokeWidth={3}
                        name="Acceptance %"
                      />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </div>

              <div className="rounded-xl border border-gray-200 bg-white p-4">
                <h4 className="mb-4 font-semibold text-gray-900">Weight-shift watchlist</h4>
                <div className="space-y-3">
                  {feedbackStats.recommended_adjustments.length === 0 ? (
                    <div className="rounded-lg border border-dashed border-gray-300 bg-slate-50 p-4 text-sm text-gray-600">
                      The optimizer has not proposed any bounded weight changes yet.
                    </div>
                  ) : (
                    feedbackStats.recommended_adjustments.slice(0, 4).map((adjustment) => (
                      <div
                        key={adjustment.factor}
                        className="rounded-lg border border-gray-200 bg-slate-50 px-4 py-3"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <p className="font-medium text-gray-900">
                            {formatFactorName(adjustment.factor)}
                          </p>
                          <span className="text-sm font-semibold text-blue-700">
                            {adjustment.delta > 0 ? "+" : ""}
                            {(adjustment.delta * 100).toFixed(1)} pts
                          </span>
                        </div>
                        <p className="mt-2 text-sm text-gray-600">{adjustment.rationale}</p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-xl p-6 border border-gray-200 shadow-sm">
            <h3 className="text-xl font-semibold text-gray-900 mb-6">Conversion Funnel</h3>
            <ResponsiveContainer width="100%" height={400}>
              <FunnelChart>
                <Tooltip />
                <Funnel dataKey="count" data={stageSummary}>
                  <LabelList position="right" fill="#000" stroke="none" dataKey="name" />
                </Funnel>
              </FunnelChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white rounded-xl p-6 border border-gray-200 shadow-sm">
            <h3 className="text-xl font-semibold text-gray-900 mb-6">
              Stage-to-Stage Conversion Rates
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              {conversions.map((conversion) => (
                <div
                  key={`${conversion.from}-${conversion.to}`}
                  className="bg-gradient-to-br from-blue-50 to-blue-50 rounded-xl p-6 border border-blue-200"
                >
                  <div className="flex items-center justify-between mb-3">
                    <p className="text-sm text-gray-700 font-medium">{conversion.from}</p>
                    <TrendingUp className="w-5 h-5 text-blue-600" />
                    <p className="text-sm text-gray-700 font-medium">{conversion.to}</p>
                  </div>
                  <p className="text-3xl font-bold text-blue-600 text-center">
                    {conversion.rate}%
                  </p>
                  <p className="text-xs text-gray-600 text-center mt-1">conversion rate</p>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-white rounded-xl p-6 border border-gray-200 shadow-sm">
            <h3 className="text-xl font-semibold text-gray-900 mb-6">Pipeline by Host</h3>
            <ResponsiveContainer width="100%" height={400}>
              <BarChart data={filteredBreakdown}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip />
                <Legend />
                {["Matched", "Contacted", "Confirmed", "Attended", "Member Inquiry"].map(
                  (stage, index) => (
                    <Bar
                      key={stage}
                      dataKey={stage}
                      fill={stagePalette[index % stagePalette.length]}
                      name={stage}
                    />
                  ),
                )}
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white rounded-xl p-6 border border-gray-200 shadow-sm">
            <h3 className="text-xl font-semibold text-gray-900 mb-6">Detailed Host Performance</h3>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-200">
                    <th className="text-left py-3 px-4 text-sm font-medium text-gray-700">
                      Host
                    </th>
                    {["Matched", "Contacted", "Confirmed", "Attended", "Member Inquiry"].map(
                      (stage) => (
                        <th
                          key={stage}
                          className="text-center py-3 px-4 text-sm font-medium text-gray-700"
                        >
                          {stage}
                        </th>
                      ),
                    )}
                  </tr>
                </thead>
                <tbody>
                  {filteredBreakdown.map((row) => (
                    <tr key={row.name} className="border-b border-gray-100 hover:bg-gray-50">
                      <td className="py-4 px-4">
                        <span className="font-medium text-gray-900">{row.name}</span>
                      </td>
                      <td className="text-center py-4 px-4 text-gray-700">{row.Matched}</td>
                      <td className="text-center py-4 px-4 text-gray-700">{row.Contacted}</td>
                      <td className="text-center py-4 px-4 text-gray-700">{row.Confirmed}</td>
                      <td className="text-center py-4 px-4 text-gray-700">{row.Attended}</td>
                      <td className="text-center py-4 px-4 text-gray-700">
                        {row["Member Inquiry"]}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
