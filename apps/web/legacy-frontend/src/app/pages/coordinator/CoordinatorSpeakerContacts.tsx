/**
 * Speaker contacts — Speaker Connector portal (customer §13).
 *
 * The other end of the arrow from `pages/volunteer/VolunteerSpeakerRequest.tsx`.
 * That page is an Event Host asking for a speaker (§12); this one is the
 * Connector recording who their unit already knows, and correcting the
 * classification the pipeline assigned (§§7-8, §19).
 *
 * ## Nothing here reports what it did not observe
 *
 * The roster and every confirmation are rendered from **server responses**, not
 * from the form. A create that fails renders the server's own refusal — a name
 * this unit already holds, a code outside the closed taxonomy — and clears no
 * fields, so nothing is lost and nothing optimistic is shown. This is the same
 * discipline `VolunteerSpeakerRequest` states and the direct opposite of the
 * B17 defect in `docs/plans/frontend-broken-buttons.md`.
 *
 * ## The contact email is collected and visibly discarded
 *
 * §13's form collects an address; OQ-CBA-011's ratified posture is that an
 * address entered this way never becomes sendable. So the field is on the form,
 * the value is sent, the server stores none of it, and **this page renders the
 * `withheld_fields` the server reports** in a notice the Connector cannot miss.
 *
 * Rendering it is the whole point. Dropping the field silently would be
 * indistinguishable from saving it, and a Connector who sees no complaint will
 * conclude the contact can be emailed — the belief the posture exists to
 * prevent. Nothing on this page offers to email anybody, and no row carries an
 * address, because there is nothing to send to. **OQ-CBA-015.**
 *
 * ## One primary classification, from the mirror
 *
 * Industry and role are single-selects, not the multi-selects
 * `VolunteerSpeakerRequest` uses. That asymmetry is customer §§7-8: a speaker
 * has **one** primary sector and one primary role category, while a request may
 * target many. The options come from `lib/cbaTaxonomies.ts`, whose parity with
 * the released Python taxonomies is asserted by
 * `tests/unit/test_frontend_taxonomy_mirror.py`; a stale option here produces a
 * server refusal a person can read, never a stored value the vocabulary does not
 * contain. There is no free-text industry field and no "other" option.
 *
 * ## A correction shows no provenance, because none is stored
 *
 * The server keeps the current value only — no history, no corrected-by, no
 * inferred-versus-human flag (OQ-CBA-008). So this page renders what the
 * classification *is* and never who set it or what it was. A "corrected by you
 * just now" line would be a claim the database cannot support the moment the
 * page is reloaded.
 *
 * ## No identifier on this page is chosen by the browser
 *
 * `GET /v1/me` says who the caller is and `GET /v1/me/portals` says which portal
 * the server granted them and which unit it covers. The unit read and written is
 * that grant's `default_unit_id` — never composed here, never read from a query
 * string. The `professional_id` a correction targets comes from a row the server
 * returned. The server authorizes all of it again anyway, per request.
 *
 * A Connector label in this shell is not permission: `coordinator-portal` being
 * reachable says the server granted this account the portal, and every route
 * behind it is still authorized server-side, deny-by-default and tenant-scoped.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, Building2, Check, MapPin, ShieldAlert, UserPlus } from "lucide-react";

import {
  ApiRequestError,
  correctSpeakerContactClassification,
  createSpeakerContact,
  fetchSpeakerContacts,
  type SpeakerContact,
  type SpeakerContactPayload,
} from "../../../lib/api";
import {
  CBA_INDUSTRY_SECTORS,
  CBA_ROLE_CATEGORIES,
  type TaxonomyOption,
} from "../../../lib/cbaTaxonomies";
import { grantedPortal } from "../../components/PortalGate";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";

/** The display name a released taxonomy gives a stored code, or the code itself. */
function displayName(options: readonly TaxonomyOption[], code: string | null): string | null {
  if (code === null) return null;
  // A code with no matching option means the server's taxonomy is ahead of this
  // mirror. Rendering the raw code is honest; inventing a label would not be.
  return options.find((option) => option.code === code)?.name ?? code;
}

/** A single-select over one closed vocabulary. §§7-8: one primary value. */
function TaxonomySelect({
  label,
  hint,
  options,
  value,
  onChange,
  id,
}: {
  label: string;
  hint: string;
  options: readonly TaxonomyOption[];
  value: string;
  onChange: (code: string) => void;
  id: string;
}) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="text-sm font-medium text-foreground">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-lg border border-border/70 bg-background px-3 py-2 text-sm"
      >
        {/* Not "Other" and not free text — the vocabulary is closed. "Not yet
            classified" is a real state: §19 records a contact first and
            classifies them after. */}
        <option value="">Not yet classified</option>
        {options.map((option) => (
          <option key={option.code} value={option.code}>
            {option.name}
          </option>
        ))}
      </select>
      <p className="text-xs text-muted-foreground">{hint}</p>
    </div>
  );
}

/** One roster row, with its own correction form. */
function ContactRow({
  contact,
  onCorrect,
  correcting,
}: {
  contact: SpeakerContact;
  onCorrect: (professionalId: string, industry: string, role: string) => void;
  correcting: boolean;
}) {
  const [industry, setIndustry] = useState(contact.primary_industry_code ?? "");
  const [role, setRole] = useState(contact.primary_role_code ?? "");
  const [open, setOpen] = useState(false);

  const industryLabel = displayName(CBA_INDUSTRY_SECTORS, contact.primary_industry_code);
  const roleLabel = displayName(CBA_ROLE_CATEGORIES, contact.primary_role_code);
  // An unchanged pair is not a correction. The server refuses one naming
  // neither axis; this keeps the button from producing that refusal.
  const unchanged =
    industry === (contact.primary_industry_code ?? "") &&
    role === (contact.primary_role_code ?? "");

  return (
    <li className="rounded-xl border border-border/70 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <p className="font-semibold text-foreground">{contact.full_name}</p>
          {contact.company !== null || contact.title !== null ? (
            <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <Building2 className="h-3.5 w-3.5" aria-hidden="true" />
              {[contact.title, contact.company].filter(Boolean).join(" · ")}
            </p>
          ) : null}
          {contact.location_city !== null || contact.location_postal_code !== null ? (
            <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <MapPin className="h-3.5 w-3.5" aria-hidden="true" />
              {[contact.location_city, contact.location_postal_code].filter(Boolean).join(" ")}
            </p>
          ) : null}
          <p className="text-sm text-muted-foreground">
            {/* Rendered as the classification *is*, with no claim about who set
                it or what it was — the server stores no such thing
                (OQ-CBA-008). */}
            {industryLabel ?? "No industry recorded"} · {roleLabel ?? "No role category recorded"}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOpen((previous) => !previous)}
          className="rounded-lg border border-border/70 px-3 py-1.5 text-sm font-medium"
        >
          {open ? "Cancel" : "Correct classification"}
        </button>
      </div>

      {open ? (
        <div className="mt-4 space-y-3 border-t border-border/70 pt-4">
          <p className="text-xs text-muted-foreground">
            Customer §§7-8: a Speaker Connector may correct an assigned
            classification. Only the value you change is written — the other axis
            is left as it is, never cleared.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <TaxonomySelect
              id={`industry-${contact.professional_id}`}
              label="Primary industry"
              hint="One primary sector (§7)."
              options={CBA_INDUSTRY_SECTORS}
              value={industry}
              onChange={setIndustry}
            />
            <TaxonomySelect
              id={`role-${contact.professional_id}`}
              label="Primary role category"
              hint="One primary role category (§8)."
              options={CBA_ROLE_CATEGORIES}
              value={role}
              onChange={setRole}
            />
          </div>
          <button
            type="button"
            disabled={correcting || unchanged}
            onClick={() => onCorrect(contact.professional_id, industry, role)}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50"
          >
            {correcting ? "Saving…" : "Save correction"}
          </button>
          {unchanged ? (
            <p className="text-xs text-muted-foreground">Change a value to save a correction.</p>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

export function CoordinatorSpeakerContacts() {
  // `GET /v1/me` — the only source of who this is. It throws rather than
  // substituting a fixture principal, which is the Fix #7 guard.
  useAuthenticatedPrincipal();
  // `GET /v1/me/portals` — the only source of the unit id this page reads and
  // writes. Never composed in the browser.
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "coordinator");
  const unitId = grant?.default_unit_id ?? null;

  const [contacts, setContacts] = useState<SpeakerContact[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [fullName, setFullName] = useState("");
  const [company, setCompany] = useState("");
  const [title, setTitle] = useState("");
  const [topicText, setTopicText] = useState("");
  const [locationCity, setLocationCity] = useState("");
  const [industryCode, setIndustryCode] = useState("");
  const [roleCode, setRoleCode] = useState("");
  const [contactEmail, setContactEmail] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [correctingId, setCorrectingId] = useState<string | null>(null);
  const [added, setAdded] = useState<SpeakerContact | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (unitId === null) return;
    try {
      const page = await fetchSpeakerContacts(unitId);
      setContacts(page.contacts);
      setTruncated(page.truncated);
      setLoadError(null);
    } catch (cause) {
      setLoadError(
        cause instanceof ApiRequestError
          ? cause.message
          : "The roster could not be loaded and the server gave no reason.",
      );
    }
  }, [unitId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  // Why the button is disabled, in the words the server would use. A courtesy
  // and not a validation — every rule here is enforced server-side, and this
  // page never decides a contact is acceptable.
  const blockingReason = useMemo(() => {
    if (unitId === null) {
      return "The server has not assigned this account a unit to record contacts under.";
    }
    if (fullName.trim().length === 0) {
      return "Give the contact a name — it is the one field without which there is no record.";
    }
    return null;
  }, [unitId, fullName]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (unitId === null || blockingReason !== null || submitting) return;

    const payload: SpeakerContactPayload = { full_name: fullName.trim() };
    if (company.trim().length > 0) payload.company = company.trim();
    if (title.trim().length > 0) payload.title = title.trim();
    if (topicText.trim().length > 0) payload.topic_text = topicText.trim();
    if (locationCity.trim().length > 0) payload.location_city = locationCity.trim();
    if (industryCode.length > 0) payload.primary_industry_code = industryCode;
    if (roleCode.length > 0) payload.primary_role_code = roleCode;
    // Sent, and the server discards it. See the module docstring.
    if (contactEmail.trim().length > 0) payload.contact_email = contactEmail.trim();

    setSubmitting(true);
    setError(null);
    try {
      // The response, not the payload. Everything the confirmation shows is a
      // value the server read back out of the committed rows.
      const stored = await createSpeakerContact(unitId, payload);
      setAdded(stored);
      setFullName("");
      setCompany("");
      setTitle("");
      setTopicText("");
      setLocationCity("");
      setIndustryCode("");
      setRoleCode("");
      setContactEmail("");
      await reload();
    } catch (cause) {
      setAdded(null);
      // The server's own message, which for a duplicate names who is already
      // there. Not a message this page made up, and no field is cleared.
      setError(
        cause instanceof ApiRequestError
          ? cause.message
          : "The contact could not be added and the server gave no reason. Nothing was stored.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCorrect(professionalId: string, industry: string, role: string) {
    if (unitId === null || correctingId !== null) return;

    setCorrectingId(professionalId);
    setError(null);
    try {
      await correctSpeakerContactClassification(unitId, professionalId, {
        // An axis left blank is omitted, which the server reads as "leave it
        // alone". Sending an empty string would be a code the taxonomy does not
        // contain.
        ...(industry.length > 0 ? { primary_industry_code: industry } : {}),
        ...(role.length > 0 ? { primary_role_code: role } : {}),
      });
      await reload();
    } catch (cause) {
      setError(
        cause instanceof ApiRequestError
          ? cause.message
          : "The correction could not be saved and the server gave no reason.",
      );
    } finally {
      setCorrectingId(null);
    }
  }

  // `CoordinatorPortalLayout` already renders `PortalGate` when the server
  // granted no such portal, so reaching here without a grant means the mapping
  // is still resolving. Render nothing rather than a form about a portal that
  // may turn out not to be assigned.
  if (grant === null) {
    return null;
  }

  return (
    <div className="space-y-8 p-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-foreground">Speaker contacts</h1>
        <p className="text-sm text-muted-foreground">
          Professionals your unit knows, recorded by hand. Customer §13.
        </p>
      </header>

      {unitId === null ? (
        <p className="rounded-xl border border-border/70 p-4 text-sm text-muted-foreground">
          The server has not assigned this account a unit, so there is no roster to show.
        </p>
      ) : (
        <>
          <form onSubmit={handleSubmit} className="space-y-4 rounded-xl border border-border/70 p-5">
            <h2 className="flex items-center gap-2 text-lg font-semibold text-foreground">
              <UserPlus className="h-4 w-4" aria-hidden="true" />
              Add a contact
            </h2>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1">
                <label htmlFor="full-name" className="text-sm font-medium text-foreground">
                  Name
                </label>
                <input
                  id="full-name"
                  value={fullName}
                  onChange={(event) => setFullName(event.target.value)}
                  className="w-full rounded-lg border border-border/70 bg-background px-3 py-2 text-sm"
                />
              </div>
              <div className="space-y-1">
                <label htmlFor="company" className="text-sm font-medium text-foreground">
                  Company <span className="text-muted-foreground">(optional)</span>
                </label>
                <input
                  id="company"
                  value={company}
                  onChange={(event) => setCompany(event.target.value)}
                  className="w-full rounded-lg border border-border/70 bg-background px-3 py-2 text-sm"
                />
              </div>
              <div className="space-y-1">
                <label htmlFor="job-title" className="text-sm font-medium text-foreground">
                  Job title <span className="text-muted-foreground">(optional)</span>
                </label>
                <input
                  id="job-title"
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  className="w-full rounded-lg border border-border/70 bg-background px-3 py-2 text-sm"
                />
              </div>
              <div className="space-y-1">
                <label htmlFor="location-city" className="text-sm font-medium text-foreground">
                  City <span className="text-muted-foreground">(optional)</span>
                </label>
                <input
                  id="location-city"
                  value={locationCity}
                  onChange={(event) => setLocationCity(event.target.value)}
                  className="w-full rounded-lg border border-border/70 bg-background px-3 py-2 text-sm"
                />
              </div>
              <TaxonomySelect
                id="new-industry"
                label="Primary industry"
                hint="One primary sector (§7). Leave unclassified if you do not know yet."
                options={CBA_INDUSTRY_SECTORS}
                value={industryCode}
                onChange={setIndustryCode}
              />
              <TaxonomySelect
                id="new-role"
                label="Primary role category"
                hint="One primary role category (§8)."
                options={CBA_ROLE_CATEGORIES}
                value={roleCode}
                onChange={setRoleCode}
              />
            </div>

            <div className="space-y-1">
              <label htmlFor="topic-text" className="text-sm font-medium text-foreground">
                Topics, interests, expertise{" "}
                <span className="text-muted-foreground">(optional)</span>
              </label>
              <textarea
                id="topic-text"
                rows={3}
                value={topicText}
                onChange={(event) => setTopicText(event.target.value)}
                className="w-full rounded-lg border border-border/70 bg-background px-3 py-2 text-sm"
              />
            </div>

            {/* Collected because §13's form has this field, and discarded by the
                server. The notice states that before the Connector types, and
                the confirmation states it again afterwards from the server's own
                `withheld_fields`. */}
            <div className="space-y-1 rounded-lg border border-amber-500/40 bg-amber-500/5 p-3">
              <label htmlFor="contact-email" className="text-sm font-medium text-foreground">
                Contact email <span className="text-muted-foreground">(not stored)</span>
              </label>
              <input
                id="contact-email"
                value={contactEmail}
                onChange={(event) => setContactEmail(event.target.value)}
                className="w-full rounded-lg border border-border/70 bg-background px-3 py-2 text-sm"
              />
              <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
                <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                This address is <strong>not saved</strong> and this contact cannot be
                emailed from SmartMatch. Storing a personal contact address is
                waiting on a privacy decision (OQ-CBA-011), so anything entered here
                is discarded and reported back to you.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <button
                type="submit"
                disabled={submitting || blockingReason !== null}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50"
              >
                {submitting ? "Adding…" : "Add contact"}
              </button>
              {blockingReason !== null ? (
                <p className="text-sm text-muted-foreground">{blockingReason}</p>
              ) : null}
            </div>

            {error !== null ? (
              <p className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-foreground">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                {error}
              </p>
            ) : null}

            {added !== null ? (
              <div className="space-y-2 rounded-lg border border-emerald-500/40 bg-emerald-500/5 p-3 text-sm">
                <p className="flex items-center gap-2 font-medium text-foreground">
                  <Check className="h-4 w-4" aria-hidden="true" />
                  {added.full_name} was added to this unit.
                </p>
                {added.withheld_fields.length > 0 ? (
                  <p className="text-muted-foreground">
                    Not stored: {added.withheld_fields.join(", ")}. The rest of the
                    record was saved.
                  </p>
                ) : null}
              </div>
            ) : null}
          </form>

          <section className="space-y-3">
            <h2 className="text-lg font-semibold text-foreground">This unit&rsquo;s contacts</h2>
            {loadError !== null ? (
              <p className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                {loadError}
              </p>
            ) : contacts.length === 0 ? (
              <p className="rounded-xl border border-border/70 p-4 text-sm text-muted-foreground">
                No contacts recorded yet.
              </p>
            ) : (
              <>
                <ul className="space-y-3">
                  {contacts.map((contact) => (
                    <ContactRow
                      key={contact.professional_id}
                      contact={contact}
                      correcting={correctingId === contact.professional_id}
                      onCorrect={handleCorrect}
                    />
                  ))}
                </ul>
                {truncated ? (
                  <p className="text-xs text-muted-foreground">
                    This unit has more contacts than are shown here.
                  </p>
                ) : null}
              </>
            )}
          </section>
        </>
      )}
    </div>
  );
}
