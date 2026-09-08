import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CalendarDays, MapPin, Users } from "lucide-react";

import { usePrincipalKey } from "../../components/PrincipalQueryProvider";
import { fetchManualEvents, getConfiguredUnitId, type ManualEvent } from "../../../lib/api";

function schedule(event: ManualEvent) {
  if (event.time_precision === "date_only") return `${event.on_date} · All day · ${event.time_zone}`;
  if (event.time_precision === "exact" && event.starts_at) {
    const formatted = new Intl.DateTimeFormat("en-US", {
      dateStyle: "long", timeStyle: "short", timeZone: event.time_zone ?? undefined,
    }).format(new Date(event.starts_at));
    return `${formatted} · ${event.time_zone}`;
  }
  return "Schedule unavailable";
}

export function CoordinatorEvents() {
  const unitId = getConfiguredUnitId();
  const principalKey = usePrincipalKey();
  const query = useQuery({
    queryKey: [principalKey, "manual-events", unitId, "published"],
    queryFn: () => fetchManualEvents(unitId!, "published"),
    enabled: Boolean(principalKey && unitId),
  });

  if (!unitId) return <div className="rounded-2xl border border-border bg-card p-8"><h1 className="text-2xl">Events</h1><p className="mt-2 text-muted-foreground">Choose an authorized unit to view its published events.</p></div>;
  if (query.isLoading) return <div className="space-y-4"><h1 className="text-2xl">Events</h1><div className="h-32 animate-pulse rounded-2xl bg-muted" /><div className="h-32 animate-pulse rounded-2xl bg-muted" /></div>;
  if (query.error) return <div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-8 text-center"><AlertTriangle className="mx-auto mb-3 h-8 w-8 text-destructive" /><h1 className="text-2xl">Events</h1><p role="alert" className="mt-2 text-destructive">{query.error instanceof Error ? query.error.message : "Events could not be loaded."}</p></div>;

  const events = query.data?.data ?? [];
  return (
    <div className="space-y-6">
      <div><h1 className="text-2xl font-semibold text-foreground">Events</h1><p className="mt-2 text-muted-foreground">Published events available for volunteer coordination.</p></div>
      {events.length === 0 ? <div className="rounded-2xl border border-border bg-card p-10 text-center shadow-sm"><CalendarDays className="mx-auto mb-3 h-9 w-9 text-muted-foreground" /><p className="font-medium">No published events yet</p><p className="mt-1 text-sm text-muted-foreground">Events appear here after an administrator publishes them.</p></div> : <div className="grid gap-4 lg:grid-cols-2">{events.map((event) => (
        <article key={event.id} className="rounded-2xl border border-border bg-card p-6 shadow-sm">
          <div className="flex items-start justify-between gap-3"><div><h2 className="text-xl font-semibold">{event.title}</h2><p className="mt-1 text-sm capitalize text-primary">{event.category}</p></div><span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">Published</span></div>
          <p className="mt-4 text-sm leading-6 text-muted-foreground">{event.description}</p>
          <dl className="mt-5 space-y-3 text-sm">
            <div className="flex gap-2"><CalendarDays className="mt-0.5 h-4 w-4 shrink-0 text-primary" /><div><dt className="sr-only">Schedule</dt><dd>{schedule(event)}</dd></div></div>
            <div className="flex gap-2"><MapPin className="mt-0.5 h-4 w-4 shrink-0 text-primary" /><div><dt className="sr-only">Location</dt><dd>{event.location}</dd></div></div>
            <div className="flex gap-2"><Users className="mt-0.5 h-4 w-4 shrink-0 text-primary" /><div><dt className="sr-only">Volunteer openings</dt><dd>{event.volunteer_openings} volunteer openings · {event.volunteer_needs}</dd></div></div>
          </dl>
          <div className="mt-5 rounded-xl bg-muted px-4 py-3 text-sm"><p className="font-medium">Audience: {event.audience}</p><p className="mt-1 text-muted-foreground">Contact {event.contact_name} at {event.contact_email}</p></div>
          <p className="mt-3 text-xs text-muted-foreground">Source: Entered by an administrator</p>
        </article>
      ))}</div>}
    </div>
  );
}
