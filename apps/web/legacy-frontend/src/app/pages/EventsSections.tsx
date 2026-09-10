import type { ManualEvent, ManualEventInput, ManualEventTimePrecision } from "@/lib/api";

/**
 * Form-state helpers and the field-group renderer for `Events.tsx`, split out
 * to keep that file under the design contract's file-size guidance. Owned by
 * the same track as `Events.tsx` — no other page imports from here.
 */

export const categoryOptions = [
  "hackathon",
  "datathon",
  "competition",
  "guest lecturer event",
  "school event",
] as const;

const defaultZone = Intl.DateTimeFormat().resolvedOptions().timeZone || "America/Los_Angeles";

export type EventFormState = {
  title: string;
  description: string;
  category: string;
  time_precision: ManualEventTimePrecision;
  starts_at: string;
  ends_at: string;
  on_date: string;
  time_zone: string;
  location: string;
  capacity: string;
  volunteer_openings: string;
  volunteer_needs: string;
  audience: string;
  contact_name: string;
  contact_email: string;
  speaker_topics: string;
  region: string;
};

export const blankEventForm = (): EventFormState => ({
  title: "",
  description: "",
  category: "",
  time_precision: "exact",
  starts_at: "",
  ends_at: "",
  on_date: "",
  time_zone: defaultZone,
  location: "",
  capacity: "",
  volunteer_openings: "",
  volunteer_needs: "",
  audience: "",
  contact_name: "",
  contact_email: "",
  speaker_topics: "",
  region: "",
});

/** Renders an ISO instant as the `datetime-local` value for the given IANA zone. */
function dateTimeLocal(value: string | null, zone: string | null): string {
  if (!value) return "";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: zone || defaultZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(value));
  const part = (type: string) => parts.find((item) => item.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}T${part("hour")}:${part("minute")}`;
}

export function formFromManualEvent(event: ManualEvent): EventFormState {
  return {
    title: event.title,
    description: event.description ?? "",
    category: event.category ?? "",
    time_precision: event.time_precision === "unresolved" ? "exact" : event.time_precision,
    starts_at: dateTimeLocal(event.starts_at, event.time_zone),
    ends_at: dateTimeLocal(event.ends_at, event.time_zone),
    on_date: event.on_date ?? "",
    time_zone: event.time_zone ?? defaultZone,
    location: event.location ?? "",
    capacity: event.capacity?.toString() ?? "",
    volunteer_openings: event.volunteer_openings?.toString() ?? "",
    volunteer_needs: event.volunteer_needs ?? "",
    audience: event.audience ?? "",
    contact_name: event.contact_name ?? "",
    contact_email: event.contact_email ?? "",
    speaker_topics: event.speaker_topics.join(", "),
    region: event.region ?? "",
  };
}

/** Converts a `datetime-local` value, read as wall-clock time in `timeZone`, to an ISO instant. */
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

export function inputFromEventForm(form: EventFormState): Partial<ManualEventInput> {
  const number = (value: string) => (value === "" ? null : Number(value));
  const exact = form.time_precision === "exact" && form.starts_at;
  const dateOnly = form.time_precision === "date_only" && form.on_date;
  const resolved = Boolean(exact || dateOnly);
  return {
    title: form.title.trim(),
    description: form.description.trim() || null,
    category: form.category || null,
    time_precision: resolved ? form.time_precision : "unresolved",
    starts_at: exact ? zonedLocalToIso(form.starts_at, form.time_zone) : null,
    ends_at: exact && form.ends_at ? zonedLocalToIso(form.ends_at, form.time_zone) : null,
    on_date: dateOnly ? form.on_date : null,
    time_zone: resolved ? form.time_zone : null,
    location: form.location.trim() || null,
    capacity: number(form.capacity),
    volunteer_openings: number(form.volunteer_openings),
    volunteer_needs: form.volunteer_needs.trim() || null,
    audience: form.audience.trim() || null,
    contact_name: form.contact_name.trim() || null,
    contact_email: form.contact_email.trim() || null,
    speaker_topics: form.speaker_topics
      .split(",")
      .map((topic) => topic.trim())
      .filter(Boolean),
    region: form.region.trim() || null,
  };
}

export function eventWhen(event: ManualEvent): string {
  if (event.time_precision === "date_only" && event.on_date) {
    return `${event.on_date} · All day · ${event.time_zone}`;
  }
  if (event.time_precision === "exact" && event.starts_at) {
    return (
      new Intl.DateTimeFormat("en-US", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: event.time_zone ?? undefined,
      }).format(new Date(event.starts_at)) + ` · ${event.time_zone}`
    );
  }
  return "Schedule not set";
}

const inputClass = "mt-1 w-full rounded-xl border bg-input-background px-3 py-2";

/** The create/edit form's fields, grouped for `Events.tsx`. */
export function EventFormFields({
  form,
  onChange,
  categories,
}: {
  form: EventFormState;
  onChange: (name: keyof EventFormState, value: string) => void;
  categories: readonly string[];
}) {
  return (
    <div className="mt-5 grid gap-4 sm:grid-cols-2">
      <label className="sm:col-span-2">
        Title
        <input
          required
          value={form.title}
          onChange={(event) => onChange("title", event.target.value)}
          className={inputClass}
        />
      </label>
      <label className="sm:col-span-2">
        Description
        <textarea
          rows={3}
          value={form.description}
          onChange={(event) => onChange("description", event.target.value)}
          className={inputClass}
        />
      </label>
      <label>
        Category
        <select
          value={form.category}
          onChange={(event) => onChange("category", event.target.value)}
          className={inputClass}
        >
          <option value="">Select category</option>
          {categories.map((category) => (
            <option key={category} value={category}>
              {category}
            </option>
          ))}
        </select>
      </label>
      <label>
        Schedule type
        <select
          value={form.time_precision}
          onChange={(event) => onChange("time_precision", event.target.value)}
          className={inputClass}
        >
          <option value="exact">Timed</option>
          <option value="date_only">All day</option>
        </select>
      </label>
      {form.time_precision === "exact" ? (
        <>
          <label>
            Starts
            <input
              type="datetime-local"
              value={form.starts_at}
              onChange={(event) => onChange("starts_at", event.target.value)}
              className={inputClass}
            />
          </label>
          <label>
            Ends
            <input
              type="datetime-local"
              value={form.ends_at}
              onChange={(event) => onChange("ends_at", event.target.value)}
              className={inputClass}
            />
          </label>
        </>
      ) : (
        <label>
          Event date
          <input
            type="date"
            value={form.on_date}
            onChange={(event) => onChange("on_date", event.target.value)}
            className={inputClass}
          />
        </label>
      )}
      <label>
        Time zone
        <input
          value={form.time_zone}
          onChange={(event) => onChange("time_zone", event.target.value)}
          placeholder="America/Los_Angeles"
          className={inputClass}
        />
        <span className="mt-1 block text-xs text-muted-foreground">An IANA zone name, e.g. America/Los_Angeles.</span>
      </label>
      <label>
        Location
        <input
          value={form.location}
          onChange={(event) => onChange("location", event.target.value)}
          className={inputClass}
        />
      </label>
      <label>
        Capacity
        <input
          type="number"
          min="0"
          value={form.capacity}
          onChange={(event) => onChange("capacity", event.target.value)}
          className={inputClass}
        />
      </label>
      <label>
        Speaker openings
        <input
          type="number"
          min="0"
          value={form.volunteer_openings}
          onChange={(event) => onChange("volunteer_openings", event.target.value)}
          className={inputClass}
        />
      </label>
      <label className="sm:col-span-2">
        Speaker needs
        <textarea
          rows={2}
          value={form.volunteer_needs}
          onChange={(event) => onChange("volunteer_needs", event.target.value)}
          className={inputClass}
        />
      </label>
      <label className="sm:col-span-2">
        Event topics <span className="text-xs text-muted-foreground">(comma separated)</span>
        <input
          value={form.speaker_topics}
          onChange={(event) => onChange("speaker_topics", event.target.value)}
          className={inputClass}
        />
      </label>
      <label>
        Event region
        <input
          value={form.region}
          onChange={(event) => onChange("region", event.target.value)}
          className={inputClass}
        />
      </label>
      <label>
        Audience
        <input
          value={form.audience}
          onChange={(event) => onChange("audience", event.target.value)}
          className={inputClass}
        />
      </label>
      <label>
        Contact name
        <input
          value={form.contact_name}
          onChange={(event) => onChange("contact_name", event.target.value)}
          className={inputClass}
        />
      </label>
      <label className="sm:col-span-2">
        Contact email
        <input
          type="email"
          value={form.contact_email}
          onChange={(event) => onChange("contact_email", event.target.value)}
          className={inputClass}
        />
      </label>
    </div>
  );
}
