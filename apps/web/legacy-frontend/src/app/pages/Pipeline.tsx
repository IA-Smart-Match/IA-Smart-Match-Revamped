/**
 * Pipeline tracking (P8 card O4c).
 *
 * The funnel numbers come from the registered metrics served by
 * `GET /v1/units/{unit_id}/metrics`, with drill-down from
 * `GET …/metrics/{name}/drill-down`. What this card removed is the *merge*:
 * the page used to join legacy `/api` CSV pipeline rows against the events CSV
 * in the browser to produce five independent stage counters, a host breakdown
 * and conversion rates, so this page and Opportunities could disagree about
 * the same question (`docs/plans/frontend-broken-buttons.md` B42, Fix #5).
 *
 * The QR ROI and matcher-feedback sections are *not* that merge — each reads
 * one endpoint and reports what it returned. They stay, with every value routed
 * through `AccountableValue` so a missing measurement renders as unknown rather
 * than as zero.
 *
 */
import { useEffect, useState } from "react";
import { AlertTriangle, RefreshCw, TrendingUp } from "lucide-react";
import {
  CartesianGrid,
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
  fetchFeedbackStats,
  fetchQrStats,
  type FeedbackStatsSummary,
  type QrStatsSummary,
} from "@/lib/api";
import { PipelineFunnelTiles } from "@/app/components/PipelineFunnelTiles";
import { AccountableValue } from "@/app/components/provenance";
import { DemoModeBadge } from "@/app/components/ui/DemoModeBadge";
import { Button } from "@/app/components/ui/button";
import { useUnitMetrics } from "@/app/hooks/useUnitMetrics";
import {
  accountableDemoMetric,
} from "@/lib/metrics";

/**
 * Reads a human message off a thrown value without assuming a specific error
 * shape. Tolerates plain Error instances, the API layer's ApiRequestError,
 * and anything else that merely looks like an error.
 */
function getErrorMessage(err: unknown, fallback: string): string {
  if (err && typeof err === "object") {
    const maybeMessage = (err as { message?: unknown }).message;
    if (typeof maybeMessage === "string" && maybeMessage.trim().length > 0) {
      return maybeMessage;
    }
  }
  if (typeof err === "string" && err.trim().length > 0) {
    return err;
  }
  return fallback;
}

function FailureState({
  title = "We couldn't load this data",
  message,
  onRetry,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
      <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-red-100">
        <AlertTriangle className="h-5 w-5 text-red-600" />
      </div>
      <p className="mt-3 text-sm font-semibold text-red-800">{title}</p>
      <p className="mt-1 text-sm text-red-700">{message}</p>
      {onRetry ? (
        <Button variant="outline" size="sm" className="mt-4" onClick={onRetry}>
          <RefreshCw className="h-4 w-4" />
          Retry
        </Button>
      ) : null}
    </div>
  );
}

function formatFactorName(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

/** Status pill copy that distinguishes "none yet" from "we don't know". */
function availabilityPill(available: boolean, count: number | null, activeLabel: string, idleLabel: string): string {
  if (!available || count === null) {
    return "Unavailable";
  }
  return count > 0 ? activeLabel : idleLabel;
}

export function Pipeline() {
  const [qrStats, setQrStats] = useState<QrStatsSummary>(emptyQrStatsSummary());
  const [feedbackStats, setFeedbackStats] = useState<FeedbackStatsSummary>(
    emptyFeedbackStatsSummary(),
  );
  const [qrAvailable, setQrAvailable] = useState(false);
  const [feedbackAvailable, setFeedbackAvailable] = useState(false);
  const [isMockData, setIsMockData] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const {
    status: metricsStatus,
    loadError,
    metricsUnavailableReason,
  } = useUnitMetrics(reloadToken);

  const unavailableReason =
    metricsStatus === "unavailable"
      ? (loadError ?? metricsUnavailableReason)
      : metricsStatus === "loading"
        ? "Loading registered metrics…"
        : "The registered metric is not present in this unit's register.";

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    Promise.allSettled([fetchQrStats(), fetchFeedbackStats()])
      .then(([qrResult, feedbackResult]) => {
        if (!active) {
          return;
        }

        let anyMock = false;

        if (qrResult.status === "fulfilled") {
          setQrStats(qrResult.value.data);
          setQrAvailable(true);
          if (qrResult.value.isMockData) anyMock = true;
        } else {
          // Never fabricate QR analytics: the empty summary is all nulls, so
          // every tile below renders unknown rather than zero.
          setQrStats(emptyQrStatsSummary());
          setQrAvailable(false);
        }

        if (feedbackResult.status === "fulfilled") {
          setFeedbackStats(feedbackResult.value.data);
          setFeedbackAvailable(true);
          if (feedbackResult.value.isMockData) anyMock = true;
        } else {
          setFeedbackStats(emptyFeedbackStatsSummary());
          setFeedbackAvailable(false);
        }

        setIsMockData(anyMock);

        const warnings = [];
        if (qrResult.status === "rejected") {
          warnings.push(
            `QR analytics are unavailable: ${getErrorMessage(qrResult.reason, "Request failed.")}`,
          );
        }
        if (feedbackResult.status === "rejected") {
          warnings.push(
            `Feedback optimizer stats are unavailable: ${getErrorMessage(feedbackResult.reason, "Request failed.")}`,
          );
        }
        setError(warnings.length ? warnings.join(" ") : null);
      })
      .catch((err: unknown) => {
        if (active) {
          setQrStats(emptyQrStatsSummary());
          setQrAvailable(false);
          setFeedbackStats(emptyFeedbackStatsSummary());
          setFeedbackAvailable(false);
          setIsMockData(false);
          setError(getErrorMessage(err, "Failed to load supplementary pipeline analytics."));
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
  }, [reloadToken]);

  const demoProvenance = isMockData ? ("synthetic" as const) : ("observed" as const);
  const qrProvenance = qrAvailable ? demoProvenance : ("synthetic" as const);
  const feedbackProvenance = feedbackAvailable ? demoProvenance : ("synthetic" as const);

  const qrCodesGenerated = accountableDemoMetric(
    "QR codes generated",
    "Deterministic referral assets created for speaker–event pairs.",
    qrAvailable ? qrStats.total_generated : null,
    { provenance: qrProvenance, unknownReason: "QR analytics are unavailable." },
  );
  const qrTotalScans = accountableDemoMetric(
    "QR total scans",
    "Redirect endpoint activity attributed to referral codes.",
    qrAvailable ? qrStats.total_scans : null,
    { provenance: qrProvenance, unknownReason: "QR analytics are unavailable." },
  );
  const qrConversions = accountableDemoMetric(
    "QR conversions",
    "Membership-interest outcomes attributed to QR referrals.",
    qrAvailable ? qrStats.total_conversions : null,
    { provenance: qrProvenance, unknownReason: "QR analytics are unavailable." },
  );
  const qrConversionRate = accountableDemoMetric(
    "QR scan-to-conversion rate",
    "Conversions divided by scans across all referral codes.",
    qrAvailable && qrStats.total_scans !== null && qrStats.total_scans > 0
      ? qrStats.conversion_rate
      : null,
    {
      provenance: qrProvenance,
      unknownReason:
        qrAvailable && qrStats.total_scans === 0
          ? "No scans recorded yet, so there is no denominator for a conversion rate."
          : "QR analytics are unavailable.",
    },
  );

  const feedbackRows = accountableDemoMetric(
    "Feedback rows",
    "Coordinator accept/decline submissions captured for matcher tuning.",
    feedbackAvailable ? feedbackStats.total_feedback : null,
    { provenance: feedbackProvenance, unknownReason: "Feedback optimizer stats are unavailable." },
  );
  const feedbackAcceptance = accountableDemoMetric(
    "Feedback acceptance rate",
    "Accepted decisions divided by all coordinator feedback rows.",
    feedbackAvailable && feedbackStats.total_feedback !== null && feedbackStats.total_feedback > 0
      ? feedbackStats.acceptance_rate
      : null,
    {
      provenance: feedbackProvenance,
      unknownReason:
        feedbackAvailable && feedbackStats.total_feedback === 0
          ? "No coordinator feedback submitted yet, so there is no rate to report."
          : "Feedback optimizer stats are unavailable.",
    },
  );
  const feedbackPain = accountableDemoMetric(
    "Matcher pain score",
    "How much correction pressure the matcher is under from recent feedback.",
    feedbackAvailable ? feedbackStats.pain_score : null,
    { provenance: feedbackProvenance, unknownReason: "Feedback optimizer stats are unavailable." },
  );

  // Unknown counts (null) sort after known counts of any value, including 0 —
  // they are not treated as lower measurements, just unranked.
  const qrEntries = [...qrStats.entries].sort((left, right) => {
    if (left.scan_count !== right.scan_count) {
      if (left.scan_count === null) return 1;
      if (right.scan_count === null) return -1;
      return right.scan_count - left.scan_count;
    }
    if (left.conversion_count === right.conversion_count) return 0;
    if (left.conversion_count === null) return 1;
    if (right.conversion_count === null) return -1;
    return right.conversion_count - left.conversion_count;
  });
  const qrTopEntries = qrEntries.slice(0, 3);
  const leadAdjustment = feedbackAvailable
    ? (feedbackStats.recommended_adjustments[0] ?? null)
    : null;

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-green-500 to-blue-500">
              <TrendingUp className="h-6 w-6 text-white" />
            </div>
            <h1 className="text-3xl font-semibold text-gray-900">
              Pipeline Tracking{isMockData && <DemoModeBadge />}
            </h1>
          </div>
          <p className="text-gray-600">
            Funnel stages read from the registered metrics API. Each tile drills down to exactly the
            rows its aggregate was calculated from.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setReloadToken((token) => token + 1)}
          aria-label="Reload pipeline data"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </Button>
      </div>

      {metricsStatus === "unavailable" ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-6">
          <p className="text-sm font-semibold text-amber-900">
            Registered metrics could not be read
          </p>
          <p className="mt-1 text-sm text-amber-800">{unavailableReason}</p>
          <p className="mt-2 text-sm text-amber-800">
            Every stage below stays unknown until the register answers. Unknown is not zero, and this
            page will not substitute a locally counted number for one.
          </p>
        </div>
      ) : null}

      {error ? (
        <FailureState
          title="Some pipeline analytics are unavailable"
          message={error}
          onRetry={() => setReloadToken((token) => token + 1)}
        />
      ) : null}

      <PipelineFunnelTiles reloadToken={reloadToken} />

      {loading ? (
        <div className="h-80 animate-pulse rounded-xl border border-gray-200 bg-white shadow-sm" />
      ) : (
        <>
          <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-xl font-semibold text-gray-900">QR ROI Tracking</h3>
                <p className="mt-1 text-sm text-gray-600">
                  Referral codes, scans, and downstream conversion signals from the QR contract.
                </p>
              </div>
              <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">
                {availabilityPill(
                  qrAvailable,
                  qrStats.total_generated,
                  "Live referrals",
                  "Awaiting QR data",
                )}
              </span>
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-xl border border-blue-100 bg-blue-50/70 p-4">
                <p className="text-sm font-medium text-blue-700">Codes generated</p>
                <p className="mt-2 text-3xl font-semibold text-gray-900">
                  <AccountableValue
                    metric={qrCodesGenerated}
                    formatNumber={(value) => value.toLocaleString("en-US")}
                  />
                </p>
                <p className="mt-1 text-xs text-gray-600">Deterministic referral assets created.</p>
              </div>
              <div className="rounded-xl border border-blue-100 bg-blue-50/70 p-4">
                <p className="text-sm font-medium text-blue-700">Total scans</p>
                <p className="mt-2 text-3xl font-semibold text-gray-900">
                  <AccountableValue
                    metric={qrTotalScans}
                    formatNumber={(value) => value.toLocaleString("en-US")}
                  />
                </p>
                <p className="mt-1 text-xs text-gray-600">Tracks the redirect endpoint activity.</p>
              </div>
              <div className="rounded-xl border border-blue-100 bg-blue-50/70 p-4">
                <p className="text-sm font-medium text-blue-700">Conversions</p>
                <p className="mt-2 text-3xl font-semibold text-gray-900">
                  <AccountableValue
                    metric={qrConversions}
                    formatNumber={(value) => value.toLocaleString("en-US")}
                  />
                </p>
                <p className="mt-1 text-xs text-gray-600">
                  Membership-interest outcomes attributed to QR.
                </p>
              </div>
              <div className="rounded-xl border border-blue-100 bg-blue-50/70 p-4">
                <p className="text-sm font-medium text-blue-700">Scan-to-conversion</p>
                <p className="mt-2 text-3xl font-semibold text-gray-900">
                  <AccountableValue
                    metric={qrConversionRate}
                    formatNumber={(value) => `${Math.round(value * 100)}%`}
                  />
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
                      {qrAvailable
                        ? "QR rows will appear here once the backend emits referral assets."
                        : "QR analytics are unavailable, so no referral history can be listed."}
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
                          <p className="text-sm font-semibold text-gray-900">
                            {entry.scan_count === null ? "Unknown" : entry.scan_count} scans
                          </p>
                          <p className="text-xs text-gray-500">
                            {entry.conversion_count === null ? "Unknown" : entry.conversion_count}{" "}
                            conversions
                          </p>
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
                    Referral codes stay deterministic per speaker-event pair, so repeated outreach
                    can reuse the same attribution key.
                  </p>
                  <p>
                    Scans are the leading signal, while downstream membership-interest conversions
                    are the primary ROI target for this phase.
                  </p>
                  <p>
                    If the QR service is unavailable, the tiles above say so and read Unknown. They
                    are never backfilled with zeros, which would claim a measurement nobody took.
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-xl font-semibold text-gray-900">Continuous Improvement</h3>
                <p className="mt-1 text-sm text-gray-600">
                  Feedback-driven acceptance, pain-score, and weight-shift telemetry for the matcher.
                </p>
              </div>
              <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">
                {availabilityPill(
                  feedbackAvailable,
                  feedbackStats.total_feedback,
                  "Optimizer active",
                  "Awaiting feedback",
                )}
              </span>
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-xl border border-blue-100 bg-blue-50/70 p-4">
                <p className="text-sm font-medium text-blue-700">Feedback rows</p>
                <p className="mt-2 text-3xl font-semibold text-gray-900">
                  <AccountableValue
                    metric={feedbackRows}
                    formatNumber={(value) => value.toLocaleString("en-US")}
                  />
                </p>
                <p className="mt-1 text-xs text-gray-600">Coordinator submissions captured so far.</p>
              </div>
              <div className="rounded-xl border border-blue-100 bg-blue-50/70 p-4">
                <p className="text-sm font-medium text-blue-700">Acceptance rate</p>
                <p className="mt-2 text-3xl font-semibold text-gray-900">
                  <AccountableValue
                    metric={feedbackAcceptance}
                    formatNumber={(value) => `${Math.round(value * 100)}%`}
                  />
                </p>
                <p className="mt-1 text-xs text-gray-600">
                  Accept vs. decline signal from the feedback loop.
                </p>
              </div>
              <div className="rounded-xl border border-blue-100 bg-blue-50/70 p-4">
                <p className="text-sm font-medium text-blue-700">Pain score</p>
                <p className="mt-2 text-3xl font-semibold text-gray-900">
                  <AccountableValue
                    metric={feedbackPain}
                    formatNumber={(value) => Math.round(value).toLocaleString("en-US")}
                  />
                </p>
                <p className="mt-1 text-xs text-gray-600">
                  Tracks how much correction pressure the matcher is under.
                </p>
              </div>
              <div className="rounded-xl border border-blue-100 bg-blue-50/70 p-4">
                <p className="text-sm font-medium text-blue-700">Lead shift</p>
                <p className="mt-2 text-lg font-semibold text-gray-900">
                  {leadAdjustment
                    ? formatFactorName(leadAdjustment.factor)
                    : feedbackAvailable
                      ? "No shift yet"
                      : "Unknown"}
                </p>
                <p className="mt-1 text-xs text-gray-600">
                  {leadAdjustment
                    ? `${leadAdjustment.delta > 0 ? "+" : ""}${(leadAdjustment.delta * 100).toFixed(1)} pts`
                    : feedbackAvailable
                      ? "Needs more coordinator outcomes."
                      : "Feedback optimizer stats are unavailable."}
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
                    {feedbackAvailable
                      ? "Trend rows will appear here once feedback is submitted from the coordinator workflow."
                      : "Feedback optimizer stats are unavailable, so there is no trend to plot."}
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
                      {feedbackAvailable
                        ? "The optimizer has not proposed any bounded weight changes yet."
                        : "Feedback optimizer stats are unavailable."}
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
        </>
      )}

      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-semibold text-gray-900">Host breakdown not shown here</h2>
        <div className="mt-3 space-y-3 text-sm leading-6 text-gray-600">
          <p>
            The per-host funnel table and bar chart used to be assembled in the browser by joining
            legacy <code>/api</code> pipeline rows against the events CSV. That join produced stage
            counts no server query owned, which is how this page and Opportunities could disagree
            about the same funnel.
          </p>
          <p>
            It returns when a host-scoped registered metric with an owning query exists. Until then
            the honest answer is that the number does not exist yet — not a zero, and not a
            client-side estimate.
          </p>
          <p>
            Match scores, ranks, and factor explanations remain out of this surface entirely; they
            are blocked on gate G1.
          </p>
        </div>
      </div>
    </div>
  );
}
