import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, Plus, Save, Sparkles } from "lucide-react";

import { usePrincipalKey } from "../../components/PrincipalQueryProvider";
import { useAuthorizedUnitId } from "../../hooks/useAuthorizedUnit";
import {
  ApiRequestError,
  cancelManualEvent,
  closeEventAttendance,
  createManualEvent,
  fetchManualEvents,
  publishManualEvent,
  runSpeakerMatch,
  submitSpeakerShortlist,
  updateManualEvent,
  type ManualEvent,
  type ManualEventInput,
  type ManualEventTimePrecision,
  type MatchRun,
} from "../../../lib/api";

const defaultZone = Intl.DateTimeFormat().resolvedOptions().timeZone || "America/Los_Angeles";
const categories = ["hackathon", "datathon", "competition", "guest lecturer event", "school event"];

type FormState = {
  title: string; time_precision: ManualEventTimePrecision; starts_at: string; ends_at: string;
  on_date: string; time_zone: string; location: string; volunteer_openings: string;
  speaker_topics: string; region: string; description: string; category: string;
  capacity: string; volunteer_needs: string; audience: string; contact_name: string; contact_email: string;
};

const blankForm = (): FormState => ({ title: "", time_precision: "exact", starts_at: "", ends_at: "", on_date: "", time_zone: defaultZone, location: "", volunteer_openings: "", speaker_topics: "", region: "", description: "", category: "", capacity: "", volunteer_needs: "", audience: "", contact_name: "", contact_email: "" });

function localValue(value: string | null, zone: string | null) {
  if (!value) return "";
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: zone || defaultZone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date(value));
  const part = (type: string) => parts.find((item) => item.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}T${part("hour")}:${part("minute")}`;
}

function toIso(value: string, timeZone: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) throw new Error("Enter a complete event date and time.");
  const wanted = match.slice(1).map(Number);
  const formatter = new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  const target = Date.UTC(wanted[0], wanted[1] - 1, wanted[2], wanted[3], wanted[4]);
  let instant = target;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const parts = formatter.formatToParts(new Date(instant));
    const part = (type: string) => Number(parts.find((item) => item.type === type)?.value ?? 0);
    const rendered = Date.UTC(part("year"), part("month") - 1, part("day"), part("hour"), part("minute"));
    instant = target - (rendered - instant);
  }
  if (localValue(new Date(instant).toISOString(), timeZone) !== value) throw new Error("That time does not exist in the selected time zone.");
  return new Date(instant).toISOString();
}

function formFromEvent(event: ManualEvent): FormState {
  return { title: event.title, time_precision: event.time_precision === "unresolved" ? "exact" : event.time_precision, starts_at: localValue(event.starts_at, event.time_zone), ends_at: localValue(event.ends_at, event.time_zone), on_date: event.on_date ?? "", time_zone: event.time_zone ?? defaultZone, location: event.location ?? "", volunteer_openings: event.volunteer_openings?.toString() ?? "", speaker_topics: event.speaker_topics.join(", "), region: event.region ?? "", description: event.description ?? "", category: event.category ?? "", capacity: event.capacity?.toString() ?? "", volunteer_needs: event.volunteer_needs ?? "", audience: event.audience ?? "", contact_name: event.contact_name ?? "", contact_email: event.contact_email ?? "" };
}

function inputFromForm(form: FormState): ManualEventInput {
  const exact = form.time_precision === "exact" && Boolean(form.starts_at);
  const allDay = form.time_precision === "date_only" && Boolean(form.on_date);
  const number = (value: string) => value ? Number(value) : null;
  return { title: form.title.trim(), time_precision: exact || allDay ? form.time_precision : "unresolved", starts_at: exact ? toIso(form.starts_at, form.time_zone) : null, ends_at: exact && form.ends_at ? toIso(form.ends_at, form.time_zone) : null, on_date: allDay ? form.on_date : null, time_zone: exact || allDay ? form.time_zone : null, location: form.location.trim() || null, volunteer_openings: number(form.volunteer_openings), speaker_topics: form.speaker_topics.split(",").map((value) => value.trim()).filter(Boolean), region: form.region.trim() || null, description: form.description.trim() || null, category: form.category || null, capacity: number(form.capacity), volunteer_needs: form.volunteer_needs.trim() || null, audience: form.audience.trim() || null, contact_name: form.contact_name.trim() || null, contact_email: form.contact_email.trim() || null };
}

function eventWhen(event: ManualEvent) {
  if (event.time_precision === "date_only") return `${event.on_date} · All day · ${event.time_zone}`;
  if (event.starts_at) return `${new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short", timeZone: event.time_zone ?? undefined }).format(new Date(event.starts_at))} · ${event.time_zone}`;
  return "Schedule not set";
}

function errorMessage(error: unknown) {
  if (error instanceof ApiRequestError && Array.isArray(error.details?.fields)) return `Complete these details before publishing: ${error.details.fields.map(String).map((value) => value.replace(/_/g, " ")).join(", ")}.`;
  return error instanceof Error ? error.message : "The event could not be saved.";
}

function MatchPanel({ event, unitId }: { event: ManualEvent; unitId: string }) {
  const principalKey = usePrincipalKey(); const client = useQueryClient();
  const runKey = useRef(crypto.randomUUID()); const shortlistKey = useRef(crypto.randomUUID());
  const [run, setRun] = useState<MatchRun | null>(null); const [chosen, setChosen] = useState<string[]>([]); const [submitted, setSubmitted] = useState(false);
  const match = useMutation({ mutationFn: () => runSpeakerMatch(unitId, event.id, runKey.current), onSuccess: (result) => { setRun(result); setChosen([]); setSubmitted(false); runKey.current = crypto.randomUUID(); } });
  const shortlist = useMutation({ mutationFn: () => submitSpeakerShortlist(unitId, run!.id, chosen, shortlistKey.current), onSuccess: async () => { setSubmitted(true); await client.invalidateQueries({ queryKey: [principalKey, "speaker-events", unitId] }); } });
  const close = useMutation({ mutationFn: () => closeEventAttendance(unitId, event.id, event.version), onSuccess: async () => { await Promise.all([client.invalidateQueries({ queryKey: [principalKey, "speaker-events", unitId] }), client.invalidateQueries({ queryKey: [principalKey, "manual-events", unitId] })]); } });
  return <section className="mt-6 border-t pt-5" aria-labelledby={`match-${event.id}`}><h3 id={`match-${event.id}`} className="text-lg font-semibold">Choose speakers</h3><p className="mt-1 text-sm text-muted-foreground">Smart Match compares the topics and service regions in the published roster. It never contacts a speaker.</p><button type="button" disabled={match.isPending} onClick={() => match.mutate()} className="mt-3 inline-flex min-h-11 items-center gap-2 rounded-xl bg-primary px-4 text-sm font-semibold text-primary-foreground disabled:opacity-60"><Sparkles className="h-4 w-4" />{match.isPending ? "Finding speakers…" : "Run Smart Match"}</button>{match.error ? <p role="alert" className="mt-3 text-sm text-destructive">{errorMessage(match.error)}</p> : null}{run ? <div className="mt-4 space-y-2">{run.suggestions.length ? run.suggestions.map((speaker) => <label key={speaker.speaker_id} className="flex min-h-11 gap-3 rounded-xl border p-3"><input type="checkbox" checked={chosen.includes(speaker.speaker_id)} disabled={!chosen.includes(speaker.speaker_id) && chosen.length >= 3} onChange={(e) => setChosen((current) => e.target.checked ? [...current, speaker.speaker_id] : current.filter((id) => id !== speaker.speaker_id))} /><span><strong>{speaker.name}</strong><span className="block text-sm text-muted-foreground">{[speaker.title, speaker.company].filter(Boolean).join(" · ")}</span><span className="block text-xs text-primary">{speaker.explanations.join(" · ")}</span></span></label>) : <p className="rounded-xl bg-muted p-3 text-sm">No published speaker has enough topic or region information for this event.</p>}{run.suggestions.length ? <button type="button" disabled={!chosen.length || shortlist.isPending || submitted} onClick={() => shortlist.mutate()} className="mt-2 min-h-11 rounded-xl border border-primary px-4 text-sm font-semibold text-primary disabled:opacity-60">{submitted ? "Speakers submitted to the Connector" : shortlist.isPending ? "Submitting…" : "Submit selected speakers"}</button> : null}{shortlist.error ? <p role="alert" className="text-sm text-destructive">{errorMessage(shortlist.error)}</p> : null}</div> : null}<div className="mt-5 border-t pt-4"><button type="button" disabled={close.isPending || Boolean(event.attendance_closed_at)} onClick={() => { if (window.confirm("Close attendance? Confirmed speakers without a check-in will be marked Did Not Attend.")) close.mutate(); }} className="min-h-11 rounded-xl border px-4 text-sm font-semibold disabled:opacity-60">{event.attendance_closed_at ? "Attendance closed" : close.isPending ? "Closing…" : "Close attendance"}</button>{close.error ? <p role="alert" className="mt-2 text-sm text-destructive">{errorMessage(close.error)}</p> : null}</div></section>;
}

export function CoordinatorEvents() {
  const unitId = useAuthorizedUnitId("coordinator"); const principalKey = usePrincipalKey(); const client = useQueryClient();
  const [selected, setSelected] = useState<ManualEvent | null>(null); const [form, setForm] = useState<FormState>(blankForm); const [notice, setNotice] = useState(""); const [cancelReason, setCancelReason] = useState(""); const createKey = useRef(crypto.randomUUID());
  const key = [principalKey, "manual-events", unitId, "all"] as const;
  const query = useQuery({ queryKey: key, queryFn: () => fetchManualEvents(unitId!, "all"), enabled: Boolean(principalKey && unitId) });
  useEffect(() => { if (selected) setForm(formFromEvent(selected)); }, [selected]);
  const refresh = async () => client.invalidateQueries({ queryKey: [principalKey, "manual-events", unitId] });
  const save = useMutation({ mutationFn: () => selected ? updateManualEvent(unitId!, selected.id, selected.version, inputFromForm(form)) : createManualEvent(unitId!, inputFromForm(form), createKey.current), onSuccess: async (event) => { setSelected(event); setNotice("Draft saved."); await refresh(); } });
  const publish = useMutation({ mutationFn: () => publishManualEvent(unitId!, selected!.id), onSuccess: async (event) => { setSelected(event); setNotice("Event published. Students can now find it, and Smart Match is ready."); await refresh(); } });
  const cancel = useMutation({ mutationFn: () => cancelManualEvent(unitId!, selected!.id, selected!.version, cancelReason), onSuccess: async () => { setSelected(null); setCancelReason(""); setNotice("Event cancelled."); await refresh(); } });
  if (!unitId) return <section className="rounded-2xl border bg-card p-8"><h1 className="text-3xl font-semibold">Events</h1><p className="mt-2 text-muted-foreground">Your account does not have an authorized unit for events.</p></section>;
  const field = (name: keyof FormState, value: string) => setForm((current) => ({ ...current, [name]: value }));
  const events = query.data?.data ?? [];
  return <div className="mx-auto max-w-7xl space-y-6"><header className="flex flex-wrap items-start justify-between gap-4"><div><h1 className="text-3xl font-semibold">Events</h1><p className="mt-2 text-muted-foreground">Create an event, request the right number of speakers, and run Smart Match in one place.</p></div><button type="button" onClick={() => { setSelected(null); setForm(blankForm()); setNotice(""); createKey.current = crypto.randomUUID(); }} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-primary px-4 text-sm font-semibold text-primary-foreground"><Plus className="h-4 w-4" />Create an event and request speakers</button></header>
    {query.error ? <p role="alert" className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-destructive">{errorMessage(query.error)}</p> : null}
    <div className="grid gap-6 xl:grid-cols-[0.75fr_1.25fr]"><section className="rounded-2xl border bg-card p-5" aria-label="Saved events">{query.isLoading ? <p>Loading events…</p> : <div className="space-y-2">{events.map((event) => <button key={event.id} type="button" onClick={() => { setSelected(event); setNotice(""); }} className={`w-full rounded-xl border p-4 text-left ${selected?.id === event.id ? "border-primary bg-primary/5" : "hover:bg-muted/50"}`}><span className="flex justify-between gap-2 font-semibold"><span>{event.title}</span><span className="text-xs font-normal capitalize text-muted-foreground">{event.status}</span></span><span className="mt-1 block text-sm text-muted-foreground">{eventWhen(event)}</span></button>)}{!events.length ? <div className="py-10 text-center text-sm text-muted-foreground"><CalendarDays className="mx-auto mb-2 h-6 w-6" />No events yet. Create one to begin.</div> : null}</div>}</section>
      <div className="space-y-6"><form onSubmit={(e) => { e.preventDefault(); setNotice(""); save.mutate(); }} className="rounded-2xl border bg-card p-6 shadow-sm"><h2 className="text-2xl font-semibold">{selected ? "Event details" : "Create an event and request speakers"}</h2><p className="mt-1 text-sm text-muted-foreground">An event name is enough to save a draft. The marked details are needed to publish and match speakers.</p><div className="mt-5 grid gap-4 sm:grid-cols-2"><label className="sm:col-span-2">Event name *<input required value={form.title} onChange={(e) => field("title", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label><label>Schedule type *<select value={form.time_precision} onChange={(e) => field("time_precision", e.target.value as ManualEventTimePrecision)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2"><option value="exact">Timed event</option><option value="date_only">All-day event</option></select></label><label>Time zone *<input value={form.time_zone} onChange={(e) => field("time_zone", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label>{form.time_precision === "exact" ? <><label>Starts *<input type="datetime-local" value={form.starts_at} onChange={(e) => field("starts_at", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label><label>Ends <input type="datetime-local" value={form.ends_at} onChange={(e) => field("ends_at", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label></> : <label>Event date *<input type="date" value={form.on_date} onChange={(e) => field("on_date", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label>}<label>Location *<input value={form.location} onChange={(e) => field("location", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label><label>Speakers needed *<input type="number" min="1" max="3" value={form.volunteer_openings} onChange={(e) => field("volunteer_openings", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label><label className="sm:col-span-2">Speaker topics * <span className="text-xs text-muted-foreground">Separate topics with commas</span><input value={form.speaker_topics} onChange={(e) => field("speaker_topics", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label><label className="sm:col-span-2">Event region <span className="text-xs text-muted-foreground">Helps match nearby speakers</span><input value={form.region} onChange={(e) => field("region", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label></div>
        <details className="mt-5 rounded-xl border p-4"><summary className="cursor-pointer font-semibold">More details</summary><div className="mt-4 grid gap-4 sm:grid-cols-2"><label className="sm:col-span-2">Description<textarea rows={3} value={form.description} onChange={(e) => field("description", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label><label>Category<select value={form.category} onChange={(e) => field("category", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2"><option value="">Not specified</option>{categories.map((value) => <option key={value}>{value}</option>)}</select></label><label>Capacity<input type="number" min="0" value={form.capacity} onChange={(e) => field("capacity", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label><label className="sm:col-span-2">What speakers should prepare<textarea rows={2} value={form.volunteer_needs} onChange={(e) => field("volunteer_needs", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label><label>Audience<input value={form.audience} onChange={(e) => field("audience", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label><label>Contact name<input value={form.contact_name} onChange={(e) => field("contact_name", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label><label className="sm:col-span-2">Contact email<input type="email" value={form.contact_email} onChange={(e) => field("contact_email", e.target.value)} className="mt-1 w-full rounded-xl border bg-input-background px-3 py-2" /></label></div></details>
        {save.error || publish.error ? <p role="alert" className="mt-4 rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{errorMessage(save.error ?? publish.error)}</p> : null}{notice ? <p role="status" className="mt-4 rounded-xl bg-primary/5 p-3 text-sm text-primary">{notice}</p> : null}<div className="mt-5 flex flex-wrap gap-3"><button disabled={save.isPending} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-primary px-4 text-sm font-semibold text-primary-foreground disabled:opacity-60"><Save className="h-4 w-4" />{save.isPending ? "Saving…" : "Save draft"}</button>{selected?.status === "draft" ? <button type="button" disabled={publish.isPending} onClick={() => publish.mutate()} className="min-h-11 rounded-xl border border-primary px-4 text-sm font-semibold text-primary disabled:opacity-60">{publish.isPending ? "Publishing…" : "Publish event"}</button> : null}</div>
        {selected?.status === "published" ? <MatchPanel event={selected} unitId={unitId} /> : null}{selected && selected.status !== "cancelled" ? <details className="mt-6 border-t pt-5"><summary className="cursor-pointer text-sm font-semibold text-destructive">Cancel event</summary><div className="mt-3 flex flex-wrap gap-2"><input value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} placeholder="Reason for cancellation" aria-label="Reason for cancellation" className="min-w-64 flex-1 rounded-xl border px-3 py-2" /><button type="button" disabled={!cancelReason.trim() || cancel.isPending} onClick={() => cancel.mutate()} className="min-h-11 rounded-xl border border-destructive px-4 text-sm font-semibold text-destructive disabled:opacity-60">{cancel.isPending ? "Cancelling…" : "Cancel event"}</button></div>{cancel.error ? <p role="alert" className="mt-2 text-sm text-destructive">{errorMessage(cancel.error)}</p> : null}</details> : null}
      </form></div></div>
  </div>;
}
