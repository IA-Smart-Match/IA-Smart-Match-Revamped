import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CalendarDays, ClipboardCheck, Users } from "lucide-react";
import { Link } from "react-router";

import { usePrincipalKey } from "../../components/PrincipalQueryProvider";
import { useAuthorizedUnitId } from "../../hooks/useAuthorizedUnit";
import {
  fetchManualEvents,
  fetchSpeakerEvents,
  fetchSpeakers,
  type ManualEvent,
} from "../../../lib/api";

function eventWhen(event: ManualEvent): string {
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

function ErrorPanel({ message }: { message: string }) {
  return <p role="alert" className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">{message}</p>;
}

export function CoordinatorHome() {
  const unitId = useAuthorizedUnitId("coordinator");
  const principalKey = usePrincipalKey();
  const enabled = Boolean(principalKey && unitId);
  const events = useQuery({
    queryKey: [principalKey, "manual-events", unitId, "all"],
    queryFn: () => fetchManualEvents(unitId!, "all"),
    enabled,
  });
  const speakers = useQuery({
    queryKey: [principalKey, "speakers", unitId, "published"],
    queryFn: () => fetchSpeakers(unitId!),
    enabled,
  });
  const handoffs = useQuery({
    queryKey: [principalKey, "speaker-events", unitId],
    queryFn: () => fetchSpeakerEvents(unitId!),
    enabled,
  });

  if (!unitId) {
    return <section className="rounded-2xl border bg-card p-8"><h1 className="text-3xl font-semibold">Home</h1><p className="mt-2 text-muted-foreground">Your account does not have an authorized unit for the Event Host portal.</p></section>;
  }

  const eventRows = events.data?.data ?? [];
  const handoffRows = handoffs.data ?? [];

  return <div className="mx-auto max-w-7xl space-y-6">
    <header><h1 className="text-3xl font-semibold">Event Host home</h1><p className="mt-2 text-muted-foreground">Create events, choose speakers, and continue the handoffs assigned to you.</p></header>
    <section className="grid gap-4 md:grid-cols-3" aria-label="Event Host actions">
      <Link to="/coordinator-portal/events" className="rounded-2xl border bg-card p-5 shadow-sm transition hover:border-primary/50"><CalendarDays className="h-5 w-5 text-primary" aria-hidden="true" /><h2 className="mt-3 text-lg font-semibold">Create an event</h2><p className="mt-1 text-sm text-muted-foreground">Save a draft, publish it, and request one to three speakers.</p><span className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-primary">Open events <ArrowRight className="h-4 w-4" aria-hidden="true" /></span></Link>
      <Link to="/coordinator-portal/events" className="rounded-2xl border bg-card p-5 shadow-sm transition hover:border-primary/50"><Users className="h-5 w-5 text-primary" aria-hidden="true" /><h2 className="mt-3 text-lg font-semibold">Run Smart Match</h2><p className="mt-1 text-sm text-muted-foreground">Compare the published roster with a published event.</p><span className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-primary">Choose speakers <ArrowRight className="h-4 w-4" aria-hidden="true" /></span></Link>
      <Link to="/coordinator-portal/outreach" className="rounded-2xl border bg-card p-5 shadow-sm transition hover:border-primary/50"><ClipboardCheck className="h-5 w-5 text-primary" aria-hidden="true" /><h2 className="mt-3 text-lg font-semibold">Review handoffs</h2><p className="mt-1 text-sm text-muted-foreground">Record final confirmation and attendance after the Connector hands off a speaker.</p><span className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-primary">Open handoffs <ArrowRight className="h-4 w-4" aria-hidden="true" /></span></Link>
    </section>
    <div className="grid gap-6 xl:grid-cols-2">
      <section className="rounded-2xl border bg-card p-6 shadow-sm"><div className="flex items-center justify-between gap-3"><div><h2 className="text-xl font-semibold">Your events</h2><p className="mt-1 text-sm text-muted-foreground">Draft and published events from the authorized unit.</p></div><Link to="/coordinator-portal/events" className="text-sm font-semibold text-primary">View all</Link></div>{events.isLoading ? <div className="mt-5 h-28 animate-pulse rounded-xl bg-muted" /> : events.error ? <div className="mt-5"><ErrorPanel message={events.error instanceof Error ? events.error.message : "Events could not be loaded."} /></div> : eventRows.length ? <div className="mt-5 space-y-3">{eventRows.slice(0, 4).map((event) => <article key={event.id} className="rounded-xl border bg-muted/30 p-4"><div className="flex flex-wrap items-start justify-between gap-2"><h3 className="font-semibold">{event.title}</h3><span className="rounded-full border px-2 py-0.5 text-xs font-medium capitalize">{event.status}</span></div><p className="mt-1 text-sm text-muted-foreground">{eventWhen(event)}</p></article>)}</div> : <p className="mt-5 rounded-xl border border-dashed p-5 text-sm text-muted-foreground">No events yet. Create an event to begin.</p>}</section>
      <section className="rounded-2xl border bg-card p-6 shadow-sm"><div className="flex items-center justify-between gap-3"><div><h2 className="text-xl font-semibold">Speaker handoffs</h2><p className="mt-1 text-sm text-muted-foreground">Shared invitation records assigned to Event Hosts.</p></div><Link to="/coordinator-portal/outreach" className="text-sm font-semibold text-primary">View all</Link></div>{handoffs.isLoading ? <div className="mt-5 h-28 animate-pulse rounded-xl bg-muted" /> : handoffs.error ? <div className="mt-5"><ErrorPanel message={handoffs.error instanceof Error ? handoffs.error.message : "Handoffs could not be loaded."} /></div> : handoffRows.length ? <div className="mt-5 space-y-3">{handoffRows.slice(0, 4).map((record) => <article key={record.id} className="rounded-xl border bg-muted/30 p-4"><div className="flex flex-wrap items-start justify-between gap-2"><h3 className="font-semibold">{record.speaker_name}</h3><span className="text-xs font-semibold capitalize text-primary">{record.status.replace(/_/g, " ")}</span></div><p className="mt-1 text-sm text-muted-foreground">{record.event_title}</p></article>)}</div> : <p className="mt-5 rounded-xl border border-dashed p-5 text-sm text-muted-foreground">No speaker handoffs have been submitted yet.</p>}</section>
    </div>
    <section className="rounded-2xl border bg-card p-6 shadow-sm"><h2 className="text-xl font-semibold">Published speaker roster</h2><p className="mt-1 text-sm text-muted-foreground">Speaker Connectors publish the profiles available to Smart Match. Private contact details are not included here.</p>{speakers.isLoading ? <div className="mt-5 h-20 animate-pulse rounded-xl bg-muted" /> : speakers.error ? <div className="mt-5"><ErrorPanel message={speakers.error instanceof Error ? speakers.error.message : "The roster could not be loaded."} /></div> : speakers.data?.data.length ? <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">{speakers.data.data.slice(0, 6).map((speaker) => <article key={speaker.id} className="rounded-xl border bg-muted/30 p-4"><h3 className="font-semibold">{speaker.name}</h3><p className="mt-1 text-sm text-muted-foreground">{[speaker.title, speaker.company].filter(Boolean).join(" · ") || "Profile details not provided"}</p><p className="mt-2 text-xs text-primary">{speaker.expertise_topics.join(", ") || "Topics not provided"}</p></article>)}</div> : <p className="mt-5 rounded-xl border border-dashed p-5 text-sm text-muted-foreground">The Speaker Connector has not published a roster yet.</p>}</section>
  </div>;
}
