import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarDays } from "lucide-react";

import { usePrincipalKey } from "@/app/components/PrincipalQueryProvider";
import { useAuthorizedUnitId } from "@/app/hooks/useAuthorizedUnit";
import { QRCodeCard } from "@/components/QRCodeCard";
import { ApiRequestError, fetchFeedbackQr, fetchManualEvents, saveFeedbackQr, type ManualEvent } from "@/lib/api";

function eventWhen(event: ManualEvent) {
  if (event.time_precision === "date_only") return `${event.on_date} · All day · ${event.time_zone}`;
  if (event.starts_at) return new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short", timeZone: event.time_zone ?? undefined }).format(new Date(event.starts_at));
  return "Schedule not set";
}

export function Events() {
  const unitId = useAuthorizedUnitId("admin");
  const principalKey = usePrincipalKey();
  const [selected, setSelected] = useState<ManualEvent | null>(null);
  const events = useQuery({ queryKey: [principalKey, "manual-events", unitId, "all"], queryFn: () => fetchManualEvents(unitId!, "all"), enabled: Boolean(principalKey && unitId) });
  const qr = useQuery({ queryKey: [principalKey, "feedback-qr", unitId, selected?.id], queryFn: () => fetchFeedbackQr(unitId!, selected!.id), enabled: Boolean(principalKey && unitId && selected && selected.status !== "cancelled"), retry: false });

  if (!unitId) return <section className="rounded-2xl border bg-card p-8"><h1 className="text-3xl font-semibold">Feedback QR codes</h1><p className="mt-2 text-muted-foreground">Your account does not have an authorized unit for feedback QR codes.</p></section>;
  const qrError = qr.error instanceof ApiRequestError && qr.error.status === 404 ? null : qr.error;

  return <div className="mx-auto max-w-6xl space-y-6">
    <header><h1 className="text-3xl font-semibold">Feedback QR codes</h1><p className="mt-2 text-muted-foreground">Choose an Event Host’s event, then connect its QR code to an external feedback form.</p></header>
    {events.error ? <p role="alert" className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-destructive">{events.error instanceof Error ? events.error.message : "Events could not be loaded."}</p> : null}
    <div className="grid gap-6 lg:grid-cols-[0.8fr_1.2fr]">
      <section className="rounded-2xl border bg-card p-5" aria-label="Events">
        {events.isLoading ? <p>Loading events…</p> : null}
        <div className="space-y-2">{(events.data?.data ?? []).map((event) => <button key={event.id} type="button" onClick={() => setSelected(event)} className={`w-full rounded-xl border p-4 text-left transition ${selected?.id === event.id ? "border-primary bg-primary/5" : "border-border hover:bg-muted/50"}`}><span className="block font-semibold">{event.title}</span><span className="mt-1 block text-sm text-muted-foreground">{eventWhen(event)} · {event.status}</span></button>)}</div>
        {!events.isLoading && !events.data?.data.length ? <div className="py-10 text-center text-sm text-muted-foreground"><CalendarDays className="mx-auto mb-2 h-6 w-6" />No Event Host events are available yet.</div> : null}
      </section>
      {selected && selected.status !== "cancelled" ? <QRCodeCard asset={qr.data ?? null} loading={qr.isLoading} error={qrError instanceof Error ? qrError.message : null} onSave={async (url) => { await saveFeedbackQr(unitId, selected.id, url); await qr.refetch(); }} /> : <section className="rounded-2xl border border-dashed bg-muted/30 p-8 text-sm text-muted-foreground">{selected?.status === "cancelled" ? "QR redirects are inactive for cancelled events." : "Select an event to configure its feedback QR code."}</section>}
    </div>
  </div>;
}
