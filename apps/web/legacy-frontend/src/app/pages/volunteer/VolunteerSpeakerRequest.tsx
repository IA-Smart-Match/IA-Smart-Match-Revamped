/**
 * Request a speaker — Event Host portal (customer §12).
 *
 * The first page in this shell that does something. Its siblings render
 * `PortalDatasetUnavailable` because the legacy `/api/portals/*` backend is not
 * in this repository; this one posts to `/v1/units/{unit_id}/speaker-requests`,
 * which is.
 *
 * ## Nothing here reports success it did not observe
 *
 * The confirmation below is rendered from the **response**, not from the form:
 * the request id, the resolved industry and role names, the publication status
 * and the timestamps are all values the server read back out of the row it
 * committed. A submit that fails renders the server's own refusal — an
 * unreleased taxonomy code, an undated request, a virtual request carrying a
 * location — and clears no fields, so nothing is lost and nothing optimistic is
 * shown. This is the direct opposite of the B17 defect
 * (`docs/plans/frontend-broken-buttons.md`): a button that logged to the console,
 * said "sent", and made no request at all.
 *
 * ## No identifier on this page is chosen by the browser
 *
 * `GET /v1/me` says who the caller is and `GET /v1/me/portals` says which portal
 * the server granted them and which unit it covers. The unit posted to is that
 * grant's `default_unit_id` — never composed here, never read from a query
 * string, never typed by the host. The server authorizes it again anyway,
 * against the row it loads, which is what makes host power server-side rather
 * than a claim this page makes about itself.
 *
 * ## Two closed vocabularies, rendered from the mirror
 *
 * The industry and role options come from `lib/cbaTaxonomies.ts`, whose parity
 * with the released Python taxonomies is asserted by
 * `tests/unit/test_frontend_taxonomy_mirror.py`. Both are multi-selects because
 * customer §§7-8 say a request "may target multiple ... Do not restrict an event
 * request to one". A stale option here produces a server refusal a person can
 * read, never a stored classification the vocabulary does not contain.
 *
 * ## Time is ADR-0010's, not a single field
 *
 * A host who knows the hour picks "A specific time"; one who knows only the day
 * picks "A date". The zone is the *event's* zone and is chosen explicitly rather
 * than taken from the browser, because ADR-0010 rule 1 makes it a fact about the
 * event and a coordinator briefing a speaker in another region needs one shared
 * answer to "when is this".
 */

import { useMemo, useState } from "react";

import {
  ApiRequestError,
  type SpeakerRequest,
  type SpeakerRequestPayload,
  submitSpeakerRequest,
} from "../../../lib/api";
import {
  CBA_INDUSTRY_SECTORS,
  CBA_ROLE_CATEGORIES,
  type TaxonomyOption,
} from "../../../lib/cbaTaxonomies";
import { grantedPortal } from "../../components/PortalGate";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";

/**
 * The zones a CBA event is plausibly held in, offered explicitly.
 *
 * Short and campus-centred rather than the full IANA database: a host picking
 * from five options is choosing, and a host scrolling six hundred is guessing.
 * The server resolves whatever arrives against the real tz database and refuses
 * a name it does not contain, so this list bounds the form's convenience and not
 * the contract.
 */
const TIME_ZONES = [
  "America/Los_Angeles",
  "America/Denver",
  "America/Chicago",
  "America/New_York",
  "UTC",
] as const;

type Precision = "date_only" | "exact";

/** A checkbox list over one closed vocabulary. */
function TaxonomyPicker({
  legend,
  hint,
  options,
  selected,
  onToggle,
  idPrefix,
}: {
  legend: string;
  hint: string;
  options: readonly TaxonomyOption[];
  selected: readonly string[];
  onToggle: (code: string) => void;
  idPrefix: string;
}) {
  return (
    <fieldset className="space-y-2 rounded-xl border border-border/70 p-4">
      <legend className="px-1 text-sm font-semibold text-foreground">{legend}</legend>
      <p className="text-xs text-muted-foreground">{hint}</p>
      <div className="grid gap-2 sm:grid-cols-2">
        {options.map((option) => {
          const id = `${idPrefix}-${option.code}`;
          return (
            <label key={option.code} htmlFor={id} className="flex items-start gap-2 text-sm">
              <input
                id={id}
                type="checkbox"
                className="mt-1"
                checked={selected.includes(option.code)}
                onChange={() => onToggle(option.code)}
              />
              <span className="text-foreground">{option.name}</span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

/** The filed request, rendered from the server's response and nothing else. */
function FiledRequest({ request }: { request: SpeakerRequest }) {
  const zone = request.time.time_zone ?? "zone unstated";
  const when =
    request.time.precision === "exact" && request.time.starts_at !== null
      ? `${new Date(request.time.starts_at).toLocaleString()} (${zone})`
      : request.time.on_date !== null
        ? `${request.time.on_date} — day only, no time stated (${zone})`
        : "No date on record";

  return (
    <div
      className="space-y-3 rounded-2xl border border-border/70 bg-card p-6 shadow-sm"
      role="status"
      aria-live="polite"
    >
      <h2 className="text-lg font-semibold text-foreground">Request on record</h2>
      <p className="text-sm text-muted-foreground">
        This is what the server stored, read back after it was written. A Speaker Connector reviews
        it and runs matching; nothing here has been matched, published, or sent to anyone.
      </p>
      <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[10rem_1fr]">
        <dt className="text-muted-foreground">Request</dt>
        <dd className="text-foreground">{request.title}</dd>
        <dt className="text-muted-foreground">Reference</dt>
        <dd className="font-mono text-xs text-foreground">{request.request_id}</dd>
        <dt className="text-muted-foreground">When</dt>
        <dd className="text-foreground">{when}</dd>
        <dt className="text-muted-foreground">Format</dt>
        <dd className="text-foreground">
          {request.is_virtual
            ? "Virtual — proximity is not considered"
            : [request.location_city, request.location_postal_code].filter(Boolean).join(" ") ||
              "In person"}
        </dd>
        <dt className="text-muted-foreground">Industries</dt>
        <dd className="text-foreground">
          {request.industries.map((item) => item.display_name).join(", ")}
        </dd>
        <dt className="text-muted-foreground">Roles</dt>
        <dd className="text-foreground">
          {request.roles.map((item) => item.display_name).join(", ")}
        </dd>
        <dt className="text-muted-foreground">Status</dt>
        <dd className="text-foreground">
          {request.publication_status} · review {request.review_status}
        </dd>
        <dt className="text-muted-foreground">Last updated</dt>
        <dd className="text-foreground">{new Date(request.updated_at).toLocaleString()}</dd>
      </dl>
    </div>
  );
}

export function VolunteerSpeakerRequest() {
  // `GET /v1/me` — the only source of who this is. It throws rather than
  // substituting a fixture principal, which is the Fix #7 guard.
  const principal = useAuthenticatedPrincipal();
  // `GET /v1/me/portals` — the only source of what the server granted them,
  // including the unit id this page posts to.
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "volunteer");

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [precision, setPrecision] = useState<Precision>("date_only");
  const [onDate, setOnDate] = useState("");
  const [startsAtLocal, setStartsAtLocal] = useState("");
  const [timeZone, setTimeZone] = useState<string>(TIME_ZONES[0]);
  const [isVirtual, setIsVirtual] = useState(false);
  const [locationCity, setLocationCity] = useState("");
  const [locationPostalCode, setLocationPostalCode] = useState("");
  const [industryCodes, setIndustryCodes] = useState<string[]>([]);
  const [roleCodes, setRoleCodes] = useState<string[]>([]);

  const [submitting, setSubmitting] = useState(false);
  const [filed, setFiled] = useState<SpeakerRequest | null>(null);
  const [error, setError] = useState<string | null>(null);

  const unitId = grant?.default_unit_id ?? null;

  // Why the button is disabled, in the words the server would use. Computed
  // rather than stored so it can never disagree with the fields; it is a
  // courtesy and not a validation — every one of these rules is enforced
  // server-side, and this page never decides a request is acceptable.
  const blockingReason = useMemo(() => {
    if (unitId === null) {
      return "The server has not assigned this account a unit to file requests under.";
    }
    if (title.trim().length === 0) return "Give the event a title.";
    if (precision === "date_only" && onDate.trim().length === 0) {
      return "Choose the date the event happens.";
    }
    if (precision === "exact" && startsAtLocal.trim().length === 0) {
      return "Choose the date and time the event starts.";
    }
    if (industryCodes.length === 0) return "Select at least one industry.";
    if (roleCodes.length === 0) return "Select at least one role.";
    if (!isVirtual && locationCity.trim().length === 0 && locationPostalCode.trim().length === 0) {
      return "An in-person event needs a city or a ZIP code — proximity is scored from it.";
    }
    return null;
  }, [
    unitId,
    title,
    precision,
    onDate,
    startsAtLocal,
    industryCodes,
    roleCodes,
    isVirtual,
    locationCity,
    locationPostalCode,
  ]);

  function toggle(codes: string[], code: string): string[] {
    return codes.includes(code) ? codes.filter((item) => item !== code) : [...codes, code];
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (unitId === null || blockingReason !== null || submitting) {
      return;
    }

    const payload: SpeakerRequestPayload = {
      title: title.trim(),
      time_zone: timeZone,
      industry_codes: industryCodes,
      role_codes: roleCodes,
      is_virtual: isVirtual,
    };
    if (precision === "exact") {
      // `datetime-local` yields a local wall time with no offset, and the
      // server refuses a naive instant (ADR-0010). `new Date(...)` interprets
      // it in the *browser's* zone, which is not necessarily the event's, so
      // this is the one place the two can differ — the host's chosen zone is
      // still what is stored and rendered, and the instant is the one they saw
      // in the picker.
      payload.starts_at = new Date(startsAtLocal).toISOString();
    } else {
      payload.on_date = onDate;
    }
    if (description.trim().length > 0) payload.description = description.trim();
    if (!isVirtual) {
      if (locationCity.trim().length > 0) payload.location_city = locationCity.trim();
      if (locationPostalCode.trim().length > 0) {
        payload.location_postal_code = locationPostalCode.trim();
      }
    }

    setSubmitting(true);
    setError(null);
    try {
      // The response, not the payload. Everything the confirmation shows is a
      // value the server read back out of the committed row.
      setFiled(await submitSpeakerRequest(unitId, payload));
    } catch (cause) {
      setFiled(null);
      setError(
        cause instanceof ApiRequestError
          ? cause.message
          : "The request could not be filed and the server gave no reason. Nothing was stored.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  // `VolunteerPortalLayout` already renders `PortalGate` when the server granted
  // no such portal, so reaching here without a grant means the mapping is still
  // resolving. Render nothing rather than a form about a portal that may turn
  // out not to be assigned.
  if (grant === null) {
    return null;
  }

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-foreground">Request a speaker</h1>
        <p className="text-sm text-muted-foreground">
          Describe the event and who you would like to hear from. A Speaker Connector reviews the
          request and runs matching against speakers already in the system — nothing here searches
          the internet or contacts anyone.
        </p>
        <p className="text-xs text-muted-foreground">
          Signed in as {principal.email} · {grant.role} · {grant.org_unit_path}
        </p>
      </header>

      {unitId === null ? (
        <div className="rounded-2xl border border-border/70 bg-card p-6 text-sm text-muted-foreground">
          The server granted this portal but named no org unit for it, so there is nowhere to file a
          request. Unit assignment is an administrator&apos;s decision and is not made here.
        </div>
      ) : null}

      <form className="space-y-5" onSubmit={handleSubmit}>
        <div className="space-y-2">
          <label htmlFor="request-title" className="text-sm font-semibold text-foreground">
            Event title
          </label>
          <input
            id="request-title"
            className="w-full rounded-lg border border-border/70 bg-background p-2 text-sm"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            required
          />
        </div>

        <div className="space-y-2">
          <label htmlFor="request-description" className="text-sm font-semibold text-foreground">
            What is the event about?
          </label>
          <p className="text-xs text-muted-foreground">
            Optional. This text is what topic matching compares against a speaker&apos;s expertise,
            so the more concrete it is the better the shortlist. Leave it empty rather than writing
            a placeholder.
          </p>
          <textarea
            id="request-description"
            rows={4}
            className="w-full rounded-lg border border-border/70 bg-background p-2 text-sm"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </div>

        <fieldset className="space-y-3 rounded-xl border border-border/70 p-4">
          <legend className="px-1 text-sm font-semibold text-foreground">When</legend>
          <div className="flex flex-wrap gap-4 text-sm">
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name="precision"
                checked={precision === "date_only"}
                onChange={() => setPrecision("date_only")}
              />
              <span>A date — the hour is not settled yet</span>
            </label>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name="precision"
                checked={precision === "exact"}
                onChange={() => setPrecision("exact")}
              />
              <span>A specific time</span>
            </label>
          </div>
          {precision === "date_only" ? (
            <div className="space-y-1">
              <label htmlFor="request-date" className="text-sm text-foreground">
                Date
              </label>
              <input
                id="request-date"
                type="date"
                className="rounded-lg border border-border/70 bg-background p-2 text-sm"
                value={onDate}
                onChange={(event) => setOnDate(event.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Stored as a date with no time. It will not be shown as midnight.
              </p>
            </div>
          ) : (
            <div className="space-y-1">
              <label htmlFor="request-starts-at" className="text-sm text-foreground">
                Starts
              </label>
              <input
                id="request-starts-at"
                type="datetime-local"
                className="rounded-lg border border-border/70 bg-background p-2 text-sm"
                value={startsAtLocal}
                onChange={(event) => setStartsAtLocal(event.target.value)}
              />
            </div>
          )}
          <div className="space-y-1">
            <label htmlFor="request-zone" className="text-sm text-foreground">
              Time zone the event happens in
            </label>
            <select
              id="request-zone"
              className="rounded-lg border border-border/70 bg-background p-2 text-sm"
              value={timeZone}
              onChange={(event) => setTimeZone(event.target.value)}
            >
              {TIME_ZONES.map((zone) => (
                <option key={zone} value={zone}>
                  {zone}
                </option>
              ))}
            </select>
            <p className="text-xs text-muted-foreground">
              The event&apos;s own zone, not the viewer&apos;s. Everyone reading this request sees
              the time in this zone, named.
            </p>
          </div>
        </fieldset>

        <fieldset className="space-y-3 rounded-xl border border-border/70 p-4">
          <legend className="px-1 text-sm font-semibold text-foreground">Where</legend>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={isVirtual}
              onChange={(event) => setIsVirtual(event.target.checked)}
            />
            <span>This event is virtual</span>
          </label>
          {isVirtual ? (
            <p className="text-xs text-muted-foreground">
              A virtual event carries no location, and distance is not considered when matching.
            </p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <label htmlFor="request-city" className="text-sm text-foreground">
                  City
                </label>
                <input
                  id="request-city"
                  className="w-full rounded-lg border border-border/70 bg-background p-2 text-sm"
                  value={locationCity}
                  onChange={(event) => setLocationCity(event.target.value)}
                />
              </div>
              <div className="space-y-1">
                <label htmlFor="request-zip" className="text-sm text-foreground">
                  ZIP code
                </label>
                <input
                  id="request-zip"
                  className="w-full rounded-lg border border-border/70 bg-background p-2 text-sm"
                  value={locationPostalCode}
                  onChange={(event) => setLocationPostalCode(event.target.value)}
                />
              </div>
              <p className="text-xs text-muted-foreground sm:col-span-2">
                A city or a ZIP is enough. Distance from campus is part of the match score, so an
                in-person request without either cannot be scored.
              </p>
            </div>
          )}
        </fieldset>

        <TaxonomyPicker
          legend="Industries"
          hint="Select every industry a speaker could come from. More than one is normal."
          options={CBA_INDUSTRY_SECTORS}
          selected={industryCodes}
          onToggle={(code) => setIndustryCodes((codes) => toggle(codes, code))}
          idPrefix="industry"
        />

        <TaxonomyPicker
          legend="Roles"
          hint="Select every career area that would suit the event. More than one is normal."
          options={CBA_ROLE_CATEGORIES}
          selected={roleCodes}
          onToggle={(code) => setRoleCodes((codes) => toggle(codes, code))}
          idPrefix="role"
        />

        {blockingReason !== null ? (
          <p className="text-sm text-muted-foreground">{blockingReason}</p>
        ) : null}

        {error !== null ? (
          <p
            className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
            role="alert"
          >
            {error}
          </p>
        ) : null}

        <button
          type="submit"
          className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50"
          disabled={submitting || blockingReason !== null}
        >
          {submitting ? "Filing…" : "File this request"}
        </button>
      </form>

      {filed !== null ? <FiledRequest request={filed} /> : null}
    </div>
  );
}
