import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, Plus, Save } from "lucide-react";

import { usePrincipalKey } from "@/app/components/PrincipalQueryProvider";
import { QRCodeCard } from "@/components/QRCodeCard";
import {
  ApiRequestError,
  cancelManualEvent,
  createManualEvent,
  fetchFeedbackQr,
  fetchManualEvents,
  getConfiguredUnitId,
  publishManualEvent,
  saveFeedbackQr,
  updateManualEvent,
  type ManualEvent,
  type ManualEventInput,
  type ManualEventTimePrecision,
} from "@/lib/api";

const categories = ["hackathon", "datathon", "competition", "guest lecturer event", "school event"];
const defaultZone = Intl.DateTimeFormat().resolvedOptions().timeZone || "America/Los_Angeles";

type FormState = {
  title: string; description: string; category: string; time_precision: ManualEventTimePrecision;
  starts_at: string; ends_at: string; on_date: string; time_zone: string; location: string;
  capacity: string; volunteer_openings: string; volunteer_needs: string; audience: string;
  contact_name: string; contact_email: string;
  speaker_topics: string; region: string;
};

const blankForm = (): FormState => ({
  title: "", description: "", category: "", time_precision: "exact", starts_at: "", ends_at: "",
  on_date: "", time_zone: defaultZone, location: "", capacity: "", volunteer_openings: "",
  volunteer_needs: "", audience: "", contact_name: "", contact_email: "", speaker_topics: "", region: "",
});

function dateTimeLocal(value: string | null, zone: string | null) {
  if (!value) return "";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: zone || defaultZone, year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(new Date(value));
  const part = (type: string) => parts.find((item) => item.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}T${part("hour")}:${part("minute")}`;
}

function formFromEvent(event: ManualEvent): FormState {
  return {
    title: event.title, description: event.description ?? "", category: event.category ?? "",
    time_precision: event.time_precision === "unresolved" ? "exact" : event.time_precision,
    starts_at: dateTimeLocal(event.starts_at, event.time_zone), ends_at: dateTimeLocal(event.ends_at, event.time_zone),
    on_date: event.on_date ?? "", time_zone: event.time_zone ?? defaultZone, location: event.location ?? "",
    capacity: event.capacity?.toString() ?? "", volunteer_openings: event.volunteer_openings?.toString() ?? "",
    volunteer_needs: event.volunteer_needs ?? "", audience: event.audience ?? "",
    contact_name: event.contact_name ?? "", contact_email: event.contact_email ?? "",
    speaker_topics: event.speaker_topics.join(", "), region: event.region ?? "",
  };
}

function zonedLocalToIso(value: string, timeZone: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) throw new Error("Enter a complete event date and time.");
  const wanted = match.slice(1).map(Number);
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  });
  const naiveUtc = Date.UTC(wanted[0], wanted[1] - 1, wanted[2], wanted[3], wanted[4]);
  let instant = naiveUtc;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const parts = formatter.formatToParts(new Date(instant));
    const part = (type: string) => Number(parts.find((item) => item.type === type)?.value ?? 0);
    const renderedAsUtc = Date.UTC(part("year"), part("month") - 1, part("day"), part("hour"), part("minute"));
    instant = naiveUtc - (renderedAsUtc - instant);
  }
  const rendered = dateTimeLocal(new Date(instant).toISOString(), timeZone);
  if (rendered !== value) {
    throw new Error("That local time does not exist in the selected time zone.");
  }
  return new Date(instant).toISOString();
}

function inputFromForm(form: FormState): ManualEventInput {
  const number = (value: string) => value === "" ? null : Number(value);
  const exact = form.time_precision === "exact" && form.starts_at;
  const dateOnly = form.time_precision === "date_only" && form.on_date;
  const resolved = Boolean(exact || dateOnly);
  return {
    title: form.title.trim(), description: form.description.trim() || null, category: form.category || null,
    time_precision: resolved ? form.time_precision : "unresolved",
    starts_at: exact ? zonedLocalToIso(form.starts_at, form.time_zone) : null,
    ends_at: exact && form.ends_at ? zonedLocalToIso(form.ends_at, form.time_zone) : null,
    on_date: dateOnly ? form.on_date : null,
    time_zone: resolved ? form.time_zone : null,
    location: form.location.trim() || null, capacity: number(form.capacity),
    volunteer_openings: number(form.volunteer_openings), volunteer_needs: form.volunteer_needs.trim() || null,
    audience: form.audience.trim() || null, contact_name: form.contact_name.trim() || null,
    contact_email: form.contact_email.trim() || null,
    speaker_topics: form.speaker_topics.split(",").map((topic) => topic.trim()).filter(Boolean),
    region: form.region.trim() || null,
  };
}

function eventWhen(event: ManualEvent) {
  if (event.time_precision === "date_only") return `${event.on_date} · All day · ${event.time_zone}`;
  if (event.time_precision === "exact" && event.starts_at) {
    return new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short", timeZone: event.time_zone ?? undefined }).format(new Date(event.starts_at)) + ` · ${event.time_zone}`;
  }
  return "Schedule not set";
}

function eventErrorMessage(error: unknown): string {
  if (error instanceof ApiRequestError) {
    const fields = error.details?.fields;
    if (Array.isArray(fields) && fields.every((field) => typeof field === "string")) {
      return `Complete these fields before publishing: ${fields.map((field) => field.replace(/_/g, " ")).join(", ")}.`;
    }
    return error.message;
  }
  return error instanceof Error ? error.message : "The event could not be saved.";
}

export function Events() {
  const unitId = getConfiguredUnitId();
  const principalKey = usePrincipalKey();
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<ManualEvent | null>(null);
  const [form, setForm] = useState<FormState>(blankForm);
  const [notice, setNotice] = useState("");
  const [cancellationReason, setCancellationReason] = useState("");
  const createKey = useRef(crypto.randomUUID());
  const key = [principalKey, "manual-events", unitId, "all"] as const;
  const eventsQuery = useQuery({ queryKey: key, queryFn: () => fetchManualEvents(unitId!, "all"), enabled: Boolean(principalKey && unitId) });
  const qrQuery = useQuery({ queryKey: [principalKey, "feedback-qr", unitId, selected?.id], queryFn: () => fetchFeedbackQr(unitId!, selected!.id), enabled: Boolean(principalKey && unitId && selected?.id) });

  useEffect(() => { if (selected) setForm(formFromEvent(selected)); }, [selected]);
  const invalidate = async () => { await queryClient.invalidateQueries({ queryKey: [principalKey, "manual-events", unitId] }); };
  const saveMutation = useMutation({
    mutationFn: async () => selected
      ? updateManualEvent(unitId!, selected.id, inputFromForm(form))
      : createManualEvent(unitId!, inputFromForm(form), createKey.current),
    onSuccess: async (event) => { setSelected(event); setNotice("Draft saved."); await invalidate(); },
  });
  const publishMutation = useMutation({ mutationFn: () => publishManualEvent(unitId!, selected!.id), onSuccess: async (event) => { setSelected(event); setNotice("Event published. Event Hosts can now see it."); await invalidate(); } });
  const qrMutation = useMutation({ mutationFn: (url: string) => saveFeedbackQr(unitId!, selected!.id, url), onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: [principalKey, "feedback-qr", unitId, selected?.id] }); } });
  const events = eventsQuery.data?.data ?? [];
  const drafts = useMemo(() => events.filter((event) => event.status === "draft"), [events]);
  const published = useMemo(() => events.filter((event) => event.status === "published"), [events]);
  const cancelled = useMemo(() => events.filter((event) => event.status === "cancelled"), [events]);
  const cancelMutation = useMutation({ mutationFn: () => cancelManualEvent(unitId!, selected!.id, selected!.version, cancellationReason), onSuccess: async () => { setSelected(null); setNotice("Event cancelled. Its feedback QR is now inactive."); setCancellationReason(""); await invalidate(); } });
  const mutationError = saveMutation.error ?? publishMutation.error;

  if (!unitId) return <div className="rounded-2xl border border-border bg-card p-8"><h1 className="text-2xl">Events</h1><p className="mt-2 text-muted-foreground">Choose an authorized unit before managing events.</p></div>;

  const field = (name: keyof FormState, value: string) => setForm((current) => ({ ...current, [name]: value }));
  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div><h1 className="text-3xl font-semibold">Events</h1><p className="mt-2 text-muted-foreground">Create events, publish them for Event Hosts, and prepare an external feedback QR.</p></div>
        <button type="button" onClick={() => { setSelected(null); setForm(blankForm()); setNotice(""); createKey.current = crypto.randomUUID(); }} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground"><Plus className="h-4 w-4" />Create event</button>
      </div>

      {eventsQuery.error ? <p role="alert" className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-destructive">{eventsQuery.error instanceof Error ? eventsQuery.error.message : "Events could not be loaded."}</p> : null}
      <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
        <section className="space-y-4" aria-label="Saved events">
          {eventsQuery.isLoading ? <p className="rounded-2xl border border-border bg-card p-6">Loading events…</p> : null}
          {[{ title: "Drafts", items: drafts }, { title: "Published", items: published }, { title: "Cancelled", items: cancelled }].map((group) => (
            <div key={group.title} className="rounded-2xl border border-border bg-card p-5 shadow-sm">
              <h2 className="text-lg font-semibold">{group.title}</h2>
              <div className="mt-3 space-y-2">{group.items.length ? group.items.map((event) => (
                <button key={event.id} type="button" onClick={() => { setSelected(event); setNotice(""); }} className={`w-full rounded-xl border p-4 text-left ${selected?.id === event.id ? "border-primary bg-primary/5" : "border-border hover:bg-muted/50"}`}>
                  <p className="font-semibold text-foreground">{event.title}</p><p className="mt-1 text-sm text-muted-foreground">{eventWhen(event)}</p>
                </button>
              )) : <p className="text-sm text-muted-foreground">No {group.title.toLowerCase()} yet.</p>}</div>
            </div>
          ))}
        </section>

        <div className="space-y-6">
          <form onSubmit={(event) => { event.preventDefault(); setNotice(""); saveMutation.mutate(); }} className="rounded-2xl border border-border bg-card p-6 shadow-sm">
            <h2 className="text-2xl font-semibold">{selected ? "Edit event" : "New event"}</h2>
            <p className="mt-1 text-sm text-muted-foreground">Only the title is required for a draft. Complete every field before publishing.</p>
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <label className="sm:col-span-2">Title<input required value={form.title} onChange={(e) => field("title", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label>
              <label className="sm:col-span-2">Description<textarea rows={3} value={form.description} onChange={(e) => field("description", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label>
              <label>Category<select value={form.category} onChange={(e) => field("category", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2"><option value="">Select category</option>{categories.map((category) => <option key={category}>{category}</option>)}</select></label>
              <label>Schedule type<select value={form.time_precision} onChange={(e) => field("time_precision", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2"><option value="exact">Timed</option><option value="date_only">All day</option></select></label>
              {form.time_precision === "exact" ? <><label>Starts<input type="datetime-local" value={form.starts_at} onChange={(e) => field("starts_at", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label><label>Ends<input type="datetime-local" value={form.ends_at} onChange={(e) => field("ends_at", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label></> : <label>Event date<input type="date" value={form.on_date} onChange={(e) => field("on_date", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label>}
              <label>Time zone<input value={form.time_zone} onChange={(e) => field("time_zone", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label>
              <label>Location<input value={form.location} onChange={(e) => field("location", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label>
              <label>Capacity<input type="number" min="0" value={form.capacity} onChange={(e) => field("capacity", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label>
              <label>Speaker openings<input type="number" min="0" value={form.volunteer_openings} onChange={(e) => field("volunteer_openings", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label>
              <label className="sm:col-span-2">Speaker needs<textarea rows={2} value={form.volunteer_needs} onChange={(e) => field("volunteer_needs", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label>
              <label className="sm:col-span-2">Event topics <span className="text-xs text-muted-foreground">(comma separated)</span><input value={form.speaker_topics} onChange={(e) => field("speaker_topics", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label>
              <label>Event region<input value={form.region} onChange={(e) => field("region", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label>
              <label>Audience<input value={form.audience} onChange={(e) => field("audience", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label>
              <label>Contact name<input value={form.contact_name} onChange={(e) => field("contact_name", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label>
              <label className="sm:col-span-2">Contact email<input type="email" value={form.contact_email} onChange={(e) => field("contact_email", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label>
            </div>
            {mutationError ? <p role="alert" className="mt-4 rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{eventErrorMessage(mutationError)}</p> : null}
            {notice ? <p role="status" className="mt-4 rounded-xl bg-primary/5 p-3 text-sm text-primary">{notice}</p> : null}
            <div className="mt-5 flex flex-wrap gap-3"><button disabled={saveMutation.isPending} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground disabled:opacity-60"><Save className="h-4 w-4" />{saveMutation.isPending ? "Saving…" : "Save draft"}</button>{selected?.status === "draft" ? <button type="button" disabled={publishMutation.isPending} onClick={() => publishMutation.mutate()} className="rounded-xl border border-primary px-4 py-2.5 text-sm font-semibold text-primary disabled:opacity-60">{publishMutation.isPending ? "Publishing…" : "Publish event"}</button> : null}</div>
            {selected && selected.status !== "cancelled" ? <div className="mt-6 border-t pt-5"><h3 className="font-semibold">Cancel event</h3><p className="mt-1 text-xs text-muted-foreground">Cancellation closes active invitations and disables the feedback QR. It cannot be undone here.</p><div className="mt-3 flex flex-wrap gap-2"><input required value={cancellationReason} onChange={(e) => setCancellationReason(e.target.value)} placeholder="Reason for cancellation" className="min-w-64 flex-1 rounded-xl border bg-input-background px-3 py-2" /><button type="button" disabled={!cancellationReason.trim() || cancelMutation.isPending} onClick={() => cancelMutation.mutate()} className="rounded-xl border border-destructive px-4 text-sm font-semibold text-destructive disabled:opacity-60">{cancelMutation.isPending ? "Cancelling…" : "Cancel event"}</button></div>{cancelMutation.error ? <p role="alert" className="mt-2 text-sm text-destructive">{cancelMutation.error instanceof Error ? cancelMutation.error.message : "The event could not be cancelled."}</p> : null}</div> : null}
          </form>
          {selected && selected.status !== "cancelled" ? <QRCodeCard asset={qrQuery.data ?? null} loading={qrMutation.isPending || qrQuery.isLoading} error={qrMutation.error instanceof Error ? qrMutation.error.message : null} onSave={async (url) => { await qrMutation.mutateAsync(url); }} /> : <div className="rounded-2xl border border-dashed border-border bg-muted/30 p-6 text-sm text-muted-foreground"><CalendarDays className="mb-2 h-5 w-5" />{selected?.status === "cancelled" ? "Feedback QR redirects are inactive for cancelled events." : "Save or select an event to configure its feedback QR code."}</div>}
        </div>
      </div>
    </div>
  );
}
