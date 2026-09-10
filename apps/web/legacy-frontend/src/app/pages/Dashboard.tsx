/** Administrator dashboard backed only by the authenticated unit APIs. */
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { AlertTriangle, CalendarDays, ClipboardCheck, RefreshCw, Users } from "lucide-react";

import {
  fetchAttendanceSummary,
  fetchManualEvents,
  fetchReviewItems,
  fetchSpeakers,
  fetchSpeakerEvents,
  fetchUnitSpeakerFeedbackSummary,
  type AttendanceSummary,
  type ManualEvent,
  type ReviewItem,
  type SpeakerEventRecord,
  type SpeakerProfile,
  type UnitFeedbackSummary,
} from "@/lib/api";
import { useAuthorizedUnitId } from "@/app/hooks/useAuthorizedUnit";
import {
  accountableDemoMetric,
  accountableMetricFromSummary,
  MATCHING_UNAVAILABLE_REASON,
  OPPORTUNITIES_METRIC_NAME,
  unavailableOpportunitiesMetric,
} from "@/lib/metrics";
import { MetricCard } from "@/app/components/MetricCard";
import { PipelineFunnelTiles } from "@/app/components/PipelineFunnelTiles";
import { AccountableValue, type AccountableMetric } from "@/app/components/provenance";
import { MetricDrilldownSheet } from "@/app/components/provenance/MetricDrilldownSheet";
import { useUnitMetrics } from "@/app/hooks/useUnitMetrics";
import { Button } from "@/app/components/ui/button";

type Loadable<T> = { data: T | null; error: string | null };

function failureMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message.trim() ? error.message : fallback;
}

function formatEventWhen(event: ManualEvent): string {
  if (event.time_precision === "date_only" && event.on_date) {
    return `${event.on_date} · All day · ${event.time_zone ?? "time zone not set"}`;
  }
  if (event.time_precision === "exact" && event.starts_at) {
    return `${new Intl.DateTimeFormat("en-US", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: event.time_zone ?? undefined,
    }).format(new Date(event.starts_at))} · ${event.time_zone ?? "time zone not set"}`;
  }
  return "Schedule not set";
}

function UnknownPanel({ message }: { message: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-[#d9cbc4] bg-[#f8f6f1] p-6 text-sm text-gray-600">
      {message}
    </div>
  );
}

export function Dashboard() {
  const unitId = useAuthorizedUnitId("admin");
  const [events, setEvents] = useState<Loadable<{ data: ManualEvent[]; total: number }>>({ data: null, error: null });
  const [reviewItems, setReviewItems] = useState<Loadable<{ items: ReviewItem[]; truncated: boolean }>>({ data: null, error: null });
  const [speakers, setSpeakers] = useState<Loadable<{ data: SpeakerProfile[]; total: number }>>({ data: null, error: null });
  const [speakerEvents, setSpeakerEvents] = useState<Loadable<SpeakerEventRecord[]>>({ data: null, error: null });
  const [feedback, setFeedback] = useState<Loadable<UnitFeedbackSummary>>({ data: null, error: null });
  const [attendance, setAttendance] = useState<Loadable<AttendanceSummary>>({ data: null, error: null });
  const [loading, setLoading] = useState(true);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    if (!unitId) {
      setLoading(false);
      return;
    }

    const load = async () => {
      const results = await Promise.allSettled([
        fetchManualEvents(unitId, "all"),
        fetchReviewItems(unitId, "pending"),
        fetchSpeakers(unitId),
        fetchSpeakerEvents(unitId),
        fetchUnitSpeakerFeedbackSummary(unitId),
        fetchAttendanceSummary(unitId),
      ]);
      if (!active) return;
      const [eventResult, reviewResult, speakerResult, handoffResult, feedbackResult, attendanceResult] = results;
      setEvents(eventResult.status === "fulfilled" ? { data: eventResult.value, error: null } : { data: null, error: failureMessage(eventResult.reason, "Events could not be loaded.") });
      setReviewItems(reviewResult.status === "fulfilled" ? { data: { items: reviewResult.value.items, truncated: reviewResult.value.truncated }, error: null } : { data: null, error: failureMessage(reviewResult.reason, "Review items could not be loaded.") });
      setSpeakers(speakerResult.status === "fulfilled" ? { data: speakerResult.value, error: null } : { data: null, error: failureMessage(speakerResult.reason, "The speaker roster could not be loaded.") });
      setSpeakerEvents(handoffResult.status === "fulfilled" ? { data: handoffResult.value, error: null } : { data: null, error: failureMessage(handoffResult.reason, "Speaker handoffs could not be loaded.") });
      setFeedback(feedbackResult.status === "fulfilled" ? { data: feedbackResult.value, error: null } : { data: null, error: failureMessage(feedbackResult.reason, "Feedback summary could not be loaded.") });
      setAttendance(attendanceResult.status === "fulfilled" ? { data: attendanceResult.value, error: null } : { data: null, error: failureMessage(attendanceResult.reason, "Attendance summary could not be loaded.") });
      setLoading(false);
    };
    void load();
    return () => { active = false; };
  }, [reloadToken, unitId]);

  const { metricsByName, status: metricsStatus, loadError: metricsLoadError, metricsUnavailableReason, openDrilldown, drilldownOpen, setDrilldownOpen, drilldownLoading, drilldownError, drilldown } = useUnitMetrics(reloadToken, unitId);
  const metricFor = (metricName: string): AccountableMetric => {
    const summary = metricsByName[metricName];
    if (summary) return accountableMetricFromSummary(summary, { provenance: "observed", onOpenDrilldown: () => void openDrilldown(metricName) });
    if (metricName !== OPPORTUNITIES_METRIC_NAME) {
      return accountableDemoMetric(metricName, "This registered metric was not returned by the server.", null, {
        provenance: "observed",
        unknownReason: metricsStatus === "unavailable" ? metricsLoadError ?? metricsUnavailableReason : metricsStatus === "loading" ? "Loading registered metrics…" : `Registered metric \`${metricName}\` is not available.`,
      });
    }
    return unavailableOpportunitiesMetric(metricsStatus === "unavailable" ? metricsLoadError ?? metricsUnavailableReason : metricsStatus === "loading" ? "Loading registered metrics…" : `Registered metric \`${metricName}\` is not available.`);
  };

  const opportunities = metricFor(OPPORTUNITIES_METRIC_NAME);
  const feedbackAvailable = feedback.data !== null;
  const feedbackSummary = feedback.data;
  const assignmentsAvailable = speakerEvents.data !== null;
  const attendanceMetric = accountableDemoMetric("Recorded attendance", "Attendance evidence recorded for this authorized unit.", attendance.data?.total ?? null, { provenance: "observed", unknownReason: attendance.error ?? "Attendance data is unavailable." });
  const averageFatigueMetric = accountableDemoMetric("Average speaker break need", "Recent assignment workload is not included in the speaker-event summary.", null, { provenance: "observed", unknownReason: "Not enough recent assignment data." });
  const restRecommendedMetric = accountableDemoMetric("Break recommendations", "Break recommendations require recent assignment evidence.", null, { provenance: "observed", unknownReason: "Not enough recent assignment data." });
  const feedbackAcceptanceMetric = accountableDemoMetric("Feedback responses", "The server provides the pooled feedback response count; it does not provide an acceptance rate.", feedbackSummary?.response_count ?? null, { provenance: "observed", unknownReason: feedback.error ?? "Feedback data is unavailable." });

  if (!unitId) return <UnknownPanel message="Choose an authorized unit to view the administrator dashboard." />;
  if (loading) return <div className="mx-auto max-w-7xl space-y-6"><div className="h-10 w-48 animate-pulse rounded bg-gray-200" /><div className="h-64 animate-pulse rounded-2xl bg-white shadow-sm" /></div>;

  const publishedEvents = events.data?.data.filter((event) => event.status === "published") ?? [];
  const errors = [events, reviewItems, speakers, speakerEvents, feedback, attendance].map((result) => result.error).filter((message): message is string => Boolean(message));

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4"><div><h1 className="text-3xl font-semibold text-gray-900">Dashboard</h1><p className="mt-1 text-gray-600">Live operational information for your authorized unit.</p></div><div className="flex items-center gap-2"><Button asChild size="sm"><Link to="/events">Create event</Link></Button><Button variant="outline" size="sm" onClick={() => setReloadToken((value) => value + 1)} aria-label="Reload dashboard data"><RefreshCw className="h-4 w-4" />Refresh</Button></div></div>
      {errors.length ? <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"><AlertTriangle className="mr-2 inline h-4 w-4" />Some dashboard sections are unavailable. Values below remain unknown where the API did not provide evidence.</div> : null}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-4"><MetricCard title="Speaker requests" value={<AccountableValue metric={opportunities} />} icon={ClipboardCheck} href="/events" /><MetricCard title="Events returned" value={events.data ? events.data.total.toLocaleString("en-US") : <AccountableValue metric={accountableDemoMetric("Events returned", "Events returned by the server.", null, { provenance: "observed", unknownReason: events.error ?? "Events are unavailable." })} />} icon={CalendarDays} href="/events" /><MetricCard title="Available speakers" value={speakers.data ? speakers.data.total.toLocaleString("en-US") : <AccountableValue metric={accountableDemoMetric("Available speakers", "Speaker roster total returned by the server.", null, { provenance: "observed", unknownReason: speakers.error ?? "The speaker roster is unavailable." })} />} icon={Users} href="/volunteers" /><MetricCard title="Recorded attendance" value={<AccountableValue metric={attendanceMetric} />} icon={ClipboardCheck} /></div>
      {metricsStatus === "unavailable" ? <UnknownPanel message={metricsLoadError ?? metricsUnavailableReason} /> : null}
      <section><h2 className="mb-3 text-lg font-semibold text-gray-900">Pipeline funnel</h2><PipelineFunnelTiles reloadToken={reloadToken} unitId={unitId} /></section>
      <section className="rounded-2xl border border-[#d9cbc4] bg-white p-6 shadow-sm"><h2 className="text-xl font-semibold text-gray-900">Upcoming events</h2><p className="mt-1 text-sm text-gray-600">Published events created by your team.</p><div className="mt-5 space-y-3">{publishedEvents.length ? publishedEvents.slice(0, 5).map((event) => <div key={event.id} className="rounded-2xl border border-[#d9cbc4] bg-[#f8f6f1] p-4"><p className="font-semibold text-gray-900">{event.title}</p><p className="mt-1 text-sm text-gray-600">{formatEventWhen(event)}</p><p className="mt-1 text-sm text-gray-600">{event.location ?? "Location not set"}</p></div>) : <UnknownPanel message={events.error ?? "No published events have been returned by the server."} />}</div></section>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2"><section className="rounded-2xl border border-[#d9cbc4] bg-white p-6 shadow-sm"><h2 className="text-xl font-semibold text-gray-900">Speaker roster</h2><p className="mt-1 text-sm text-gray-600">Connector-managed speakers available to this unit.</p>{speakers.data?.data.length ? <div className="mt-5 space-y-2">{speakers.data.data.slice(0, 5).map((speaker) => <div key={speaker.id} className="rounded-xl border border-[#d9cbc4] bg-[#f8f6f1] p-3"><p className="font-semibold">{speaker.name}</p><p className="text-sm text-gray-600">{[speaker.title, speaker.company].filter(Boolean).join(" · ") || "Details not provided"}</p></div>)}</div> : <div className="mt-5"><UnknownPanel message={speakers.error ?? "No speaker roster rows have been returned."} /></div>}</section><section className="rounded-2xl border border-[#d9cbc4] bg-white p-6 shadow-sm"><h2 className="text-xl font-semibold text-gray-900">Speaker handoffs</h2><p className="mt-1 text-sm text-gray-600">Invitation tracking stays in Smart Match; email is handled outside the platform.</p>{speakerEvents.data?.length ? <div className="mt-5 space-y-2">{speakerEvents.data.slice(0, 5).map((record) => <div key={record.id} className="rounded-xl border border-[#d9cbc4] bg-[#f8f6f1] p-3"><div className="flex justify-between gap-3"><p className="font-semibold">{record.speaker_name}</p><span className="text-xs font-medium text-[#005030]">{record.status.replace(/_/g, " ")}</span></div><p className="text-sm text-gray-600">{record.event_title}</p></div>)}</div> : <div className="mt-5"><UnknownPanel message={speakerEvents.error ?? "No speaker handoffs have been returned."} /></div>}</section></div>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3"><section className="rounded-2xl border border-[#d9cbc4] bg-white p-6 shadow-sm"><h2 className="text-lg font-semibold">Review queue</h2><p className="mt-1 text-sm text-gray-600">Pending records awaiting an administrative decision.</p><div className="mt-5"><AccountableValue metric={metricFor("pending_review_items")} />{reviewItems.data ? <p className="mt-2 text-sm text-gray-600">Review data loaded from the server{reviewItems.data.truncated ? "; more records are available." : "."}</p> : <p className="mt-2 text-sm text-gray-600">{reviewItems.error ?? "Review data is unavailable."}</p>}</div></section><section className="rounded-2xl border border-[#d9cbc4] bg-white p-6 shadow-sm"><h2 className="text-lg font-semibold">Student feedback</h2><p className="mt-1 text-sm text-gray-600">Feedback does not feed matching.</p><div className="mt-5"><AccountableValue metric={feedbackAcceptanceMetric} />{feedbackSummary && feedbackSummary.mean_rating !== null ? <p className="mt-2 text-sm text-gray-600">Average rating: {feedbackSummary.mean_rating}</p> : null}</div></section><section className="rounded-2xl border border-[#d9cbc4] bg-white p-6 shadow-sm"><h2 className="text-lg font-semibold">Speaker break need</h2><p className="mt-1 text-sm text-gray-600">Higher workload may mean a speaker needs a break.</p><div className="mt-5 space-y-3"><AccountableValue metric={averageFatigueMetric} /><AccountableValue metric={restRecommendedMetric} /><p className="text-xs text-gray-500">{assignmentsAvailable ? "Recent assignment evidence is not included in the speaker-event response." : "Not enough recent assignment data."}</p></div></section></div>
      <section className="rounded-2xl border border-dashed border-[#d9cbc4] bg-[#f8f6f1] p-8 text-center text-gray-600"><p className="font-semibold text-gray-900">Matching unavailable</p><p className="mt-2 text-sm leading-6">{MATCHING_UNAVAILABLE_REASON}</p></section>
      <MetricDrilldownSheet open={drilldownOpen} onOpenChange={setDrilldownOpen} loading={drilldownLoading} drilldown={drilldown} error={drilldownError} />
    </div>
  );
}
