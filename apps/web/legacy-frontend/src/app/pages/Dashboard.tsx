/** Administrator dashboard backed only by the authenticated unit APIs. */
import { useEffect, useState } from "react";
import { AlertTriangle, CalendarDays, ClipboardCheck, RefreshCw, Users } from "lucide-react";

import {
  fetchAttendanceSummary,
  fetchManualEvents,
  fetchSpeakers,
  fetchSpeakerEvents,
  fetchUnitSpeakerFeedbackSummary,
  type AttendanceSummary,
  type ManualEvent,
  type SpeakerEventRecord,
  type SpeakerProfile,
  type UnitFeedbackSummary,
} from "@/lib/api";
import { useAuthorizedUnitId } from "@/app/hooks/useAuthorizedUnit";
import { MetricCard } from "@/app/components/MetricCard";
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
    <div className="rounded-2xl border border-dashed bg-muted/40 p-6 text-sm text-muted-foreground">
      {message}
    </div>
  );
}

export function Dashboard() {
  const unitId = useAuthorizedUnitId("admin");
  const [events, setEvents] = useState<Loadable<{ data: ManualEvent[]; total: number }>>({ data: null, error: null });
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
        fetchSpeakers(unitId),
        fetchSpeakerEvents(unitId),
        fetchUnitSpeakerFeedbackSummary(unitId),
        fetchAttendanceSummary(unitId),
      ]);
      if (!active) return;
      const [eventResult, speakerResult, handoffResult, feedbackResult, attendanceResult] = results;
      setEvents(eventResult.status === "fulfilled" ? { data: eventResult.value, error: null } : { data: null, error: failureMessage(eventResult.reason, "Events could not be loaded.") });
      setSpeakers(speakerResult.status === "fulfilled" ? { data: speakerResult.value, error: null } : { data: null, error: failureMessage(speakerResult.reason, "The speaker roster could not be loaded.") });
      setSpeakerEvents(handoffResult.status === "fulfilled" ? { data: handoffResult.value, error: null } : { data: null, error: failureMessage(handoffResult.reason, "Speaker handoffs could not be loaded.") });
      setFeedback(feedbackResult.status === "fulfilled" ? { data: feedbackResult.value, error: null } : { data: null, error: failureMessage(feedbackResult.reason, "Feedback summary could not be loaded.") });
      setAttendance(attendanceResult.status === "fulfilled" ? { data: attendanceResult.value, error: null } : { data: null, error: failureMessage(attendanceResult.reason, "Attendance summary could not be loaded.") });
      setLoading(false);
    };
    void load();
    return () => { active = false; };
  }, [reloadToken, unitId]);

  const feedbackSummary = feedback.data;

  if (!unitId) return <UnknownPanel message="Choose an authorized unit to view the administrator dashboard." />;
  if (loading) return <div className="mx-auto max-w-7xl space-y-6"><div className="h-10 w-48 animate-pulse rounded bg-gray-200" /><div className="h-64 animate-pulse rounded-2xl bg-white shadow-sm" /></div>;

  const publishedEvents = events.data?.data.filter((event) => event.status === "published") ?? [];
  const errors = [events, speakers, speakerEvents, feedback, attendance].map((result) => result.error).filter((message): message is string => Boolean(message));

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4"><div><h1 className="text-3xl font-semibold">Dashboard</h1><p className="mt-1 text-muted-foreground">Invitation, speaker, event, and attendance information for your authorized unit.</p></div><Button variant="outline" size="sm" onClick={() => setReloadToken((value) => value + 1)} aria-label="Reload dashboard data"><RefreshCw className="h-4 w-4" />Refresh</Button></div>
      {errors.length ? <div className="rounded-2xl border border-accent bg-accent/15 p-4 text-sm text-foreground"><AlertTriangle className="mr-2 inline h-4 w-4" />Some dashboard sections are unavailable. Values below remain unknown where the API did not provide evidence.</div> : null}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-4"><MetricCard title="Events" value={events.data ? events.data.total.toLocaleString("en-US") : "Unavailable"} icon={CalendarDays} href="/events" /><MetricCard title="Available speakers" value={speakers.data ? speakers.data.total.toLocaleString("en-US") : "Unavailable"} icon={Users} href="/volunteers" /><MetricCard title="Invitation records" value={speakerEvents.data ? speakerEvents.data.length.toLocaleString("en-US") : "Unavailable"} icon={ClipboardCheck} href="/outreach" /><MetricCard title="Recorded attendance" value={attendance.data ? attendance.data.total.toLocaleString("en-US") : "Unavailable"} icon={ClipboardCheck} /></div>
      <section className="rounded-2xl border bg-card p-6 shadow-sm"><h2 className="text-xl font-semibold">Upcoming events</h2><p className="mt-1 text-sm text-muted-foreground">Published events created by your team.</p><div className="mt-5 space-y-3">{publishedEvents.length ? publishedEvents.slice(0, 5).map((event) => <div key={event.id} className="rounded-2xl border bg-muted/40 p-4"><p className="font-semibold">{event.title}</p><p className="mt-1 text-sm text-muted-foreground">{formatEventWhen(event)}</p><p className="mt-1 text-sm text-muted-foreground">{event.location ?? "Location not set"}</p></div>) : <UnknownPanel message={events.error ?? "No published events have been returned by the server."} />}</div></section>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2"><section className="rounded-2xl border bg-card p-6 shadow-sm"><h2 className="text-xl font-semibold">Speaker roster</h2><p className="mt-1 text-sm text-muted-foreground">Connector-managed speakers available to this unit.</p>{speakers.data?.data.length ? <div className="mt-5 space-y-2">{speakers.data.data.slice(0, 5).map((speaker) => <div key={speaker.id} className="rounded-xl border bg-muted/40 p-3"><p className="font-semibold">{speaker.name}</p><p className="text-sm text-muted-foreground">{[speaker.title, speaker.company].filter(Boolean).join(" · ") || "Details not provided"}</p></div>)}</div> : <div className="mt-5"><UnknownPanel message={speakers.error ?? "No speaker roster rows have been returned."} /></div>}</section><section className="rounded-2xl border bg-card p-6 shadow-sm"><h2 className="text-xl font-semibold">Speaker handoffs</h2><p className="mt-1 text-sm text-muted-foreground">Invitation tracking stays in Smart Match; email is handled outside the platform.</p>{speakerEvents.data?.length ? <div className="mt-5 space-y-2">{speakerEvents.data.slice(0, 5).map((record) => <div key={record.id} className="rounded-xl border bg-muted/40 p-3"><div className="flex justify-between gap-3"><p className="font-semibold">{record.speaker_name}</p><span className="text-xs font-medium text-primary">{record.status.replace(/_/g, " ")}</span></div><p className="text-sm text-muted-foreground">{record.event_title}</p></div>)}</div> : <div className="mt-5"><UnknownPanel message={speakerEvents.error ?? "No speaker handoffs have been returned."} /></div>}</section></div>
      <section className="rounded-2xl border bg-card p-6 shadow-sm"><h2 className="text-lg font-semibold">Student feedback</h2><p className="mt-1 text-sm text-muted-foreground">Feedback is shown only as a privacy-protected summary and does not affect matching.</p>{feedbackSummary ? feedbackSummary.response_count !== null ? <div className="mt-5"><p className="text-3xl font-semibold text-primary">{feedbackSummary.response_count}</p><p className="mt-1 text-sm text-muted-foreground">responses{feedbackSummary.mean_rating !== null ? ` · Average rating ${feedbackSummary.mean_rating}` : ""}</p></div> : <p className="mt-5 text-sm text-muted-foreground">{feedbackSummary.display_text}</p> : <UnknownPanel message={feedback.error ?? "Feedback data is unavailable."} />}</section>
    </div>
  );
}
