/**
 * Your confirmed speaker — Event Host portal (customer §6 step 9).
 *
 * `VolunteerSpeakerRequest.tsx` opens a loop: a Host describes an event and
 * files a request. This page closes it. Between the two sit a Speaker
 * Connector's match run and invitation batch, neither of which appears here.
 *
 * ## What a Host is handed, and what they are not
 *
 * `GET /v1/units/{unit_id}/cba/confirmed-speakers` answers with the speakers
 * whose acceptance is a stored fact, in the order they said yes. That is the
 * whole of what this page shows.
 *
 * It shows nothing about the professionals who were asked and did not accept —
 * not their answers, not how many of them there were, not a "1 of 4" that says
 * the same thing with arithmetic. **OQ-CBA-042**, in the register's own words:
 * an Event Host learning that three named professionals turned them down learns
 * "a fact about those people's availability and willingness that nobody agreed
 * to share", and customer §13 gives the invitation-tracking surface to the
 * Speaker Connector by name. Widening the hand-back to approximate it "would
 * ship the declines along with the acceptance".
 *
 * That is why the empty state here is one sentence with no explanation in it. A
 * helpful "nobody has accepted yet — four were invited" would publish exactly
 * the fact the narrow reading withholds, and an empty state that reasons about
 * *why* is the most natural place for it to leak. So this page does not know
 * how many invitations exist, does not read the batch surface that would tell
 * it, and says only that nobody is confirmed.
 *
 * ## Nothing here reports what it did not observe
 *
 * The list is a server response. The reconciliation renders the server's own
 * `applied` array — the funnel steps *this* request wrote — beside the speaker
 * the server read back out of the committed rows. A replay writes nothing and
 * comes back saying so, and this page renders that difference rather than
 * flattening it into a success message. A failure renders the server's refusal
 * verbatim and clears no field. This is `docs/plans/frontend-broken-buttons.md`
 * discipline and the direct opposite of the B17 defect.
 *
 * ## The controls are rendered, and the server decides
 *
 * Both routes are `admin`/`coordinator` server-side, and an Event Host account
 * may hold neither. The refusal is therefore rendered as the answer it is — the
 * status and the server's message — rather than hidden behind a role the
 * browser read for itself. Removing a control on the strength of a client-side
 * check would be the browser deciding a permission, and it would tell a Host
 * that a capability does not exist when what happened is that they were denied
 * it. A UI gate is not authorization.
 *
 * ## No identifier on this page is chosen by the browser
 *
 * `GET /v1/me` says who the caller is; `GET /v1/me/portals` says which portal
 * the server granted them and which unit it covers. That grant's
 * `default_unit_id` is the only unit read or written. Event and invitation ids
 * are values a person was given by the people running the event; the server
 * verifies every one of them against rows in this tenant before anything is
 * written.
 */

import { useCallback, useEffect, useState } from "react";
import { CalendarCheck, ShieldAlert, UserCheck } from "lucide-react";

import {
  ApiRequestError,
  type ConfirmedSpeaker,
  fetchConfirmedSpeakers,
  reconcileSpeakerHandoff,
  type SpeakerHandoffPayload,
  type SpeakerHandoffResult,
} from "../../../lib/api";
import { PagedList } from "../../components/PagedList";
import { grantedPortal } from "../../components/PortalGate";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";

/**
 * How the CBA funnel's own step names are read aloud.
 *
 * A token the server sends and this table does not name is rendered as itself.
 * The vocabulary grows server-side, and a friendly catch-all would report the
 * wrong thing the first time it did.
 */
const STAGE_LABELS: Record<string, string> = {
  matched: "Matched to your request",
  contacted: "Invited",
  confirmed: "Agreed to speak",
  attended: "Presented",
};

function stageLabel(token: string): string {
  return STAGE_LABELS[token] ?? token;
}

/** An instant the server sent, in the reader's own locale. */
function moment(value: string | null): string {
  return value === null ? "—" : new Date(value).toLocaleString();
}

/**
 * Turn an error into words a Host can act on.
 *
 * A `403` is named as the refusal it is. The alternative — a blank page, or a
 * control quietly removed — would leave a person unable to tell "the server
 * said no" from "this feature does not exist", and those call for different
 * next steps: one of them is a conversation with whoever administers the
 * account.
 */
function refusalMessage(cause: unknown, fallback: string): string {
  if (cause instanceof ApiRequestError) {
    if (cause.status === 403) {
      return (
        `The server refused this request (403). ${cause.message} ` +
        "Reading and reconciling a hand-off is granted to unit administrators and " +
        "Speaker Connectors; this account was not granted it here. Nothing was changed."
      );
    }
    return cause.message;
  }
  return fallback;
}

/** One confirmed speaker, as the server described them. */
function SpeakerCard({ speaker }: { speaker: ConfirmedSpeaker }) {
  return (
    <li className="space-y-3 rounded-2xl border border-border/70 bg-card p-5 shadow-sm">
      <div className="flex items-start gap-3">
        <UserCheck className="mt-1 h-5 w-5 text-primary" aria-hidden="true" />
        <div className="space-y-1">
          <h3 className="text-base font-semibold text-foreground">
            {speaker.full_name ?? "Name not held by this unit"}
          </h3>
          <p className="text-sm text-muted-foreground">
            {[speaker.title, speaker.company].filter(Boolean).join(" · ") ||
              "No title or company on record"}
          </p>
        </div>
      </div>
      <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[12rem_1fr]">
        <dt className="text-muted-foreground">Where they are</dt>
        <dd className="text-foreground">{stageLabel(speaker.current_stage)}</dd>
        <dt className="text-muted-foreground">Agreed to speak</dt>
        <dd className="text-foreground">{moment(speaker.confirmed_at)}</dd>
        <dt className="text-muted-foreground">Presented</dt>
        <dd className="text-foreground">
          {speaker.attended_at === null ? "Not yet" : moment(speaker.attended_at)}
        </dd>
        <dt className="text-muted-foreground">Speaker reference</dt>
        <dd className="font-mono text-xs text-foreground">{speaker.professional_id}</dd>
        <dt className="text-muted-foreground">Event reference</dt>
        <dd className="font-mono text-xs text-foreground">{speaker.event_id}</dd>
      </dl>
      {speaker.stages.length > 0 ? (
        <ul className="space-y-1 border-t border-border/60 pt-3 text-xs text-muted-foreground">
          {speaker.stages.map((item) => (
            <li key={`${speaker.record_id}-${item.stage}`}>
              {stageLabel(item.stage)} — recorded from {item.evidence} on {moment(item.occurred_at)}
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}

export function VolunteerConfirmedSpeaker() {
  // `GET /v1/me` — the only source of who this is. It throws rather than
  // substituting a fixture principal, which is the Fix #7 guard.
  const principal = useAuthenticatedPrincipal();
  // `GET /v1/me/portals` — the only source of what the server granted them,
  // including the unit id this page reads under.
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "volunteer");
  const unitId = grant?.default_unit_id ?? null;

  const [eventFilter, setEventFilter] = useState("");
  const [shownEventId, setShownEventId] = useState("");
  const [speakers, setSpeakers] = useState<ConfirmedSpeaker[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [invitationId, setInvitationId] = useState("");
  const [attendanceId, setAttendanceId] = useState("");
  const [reconciling, setReconciling] = useState(false);
  const [outcome, setOutcome] = useState<SpeakerHandoffResult | null>(null);
  const [reconcileError, setReconcileError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (unitId === null) return;
    try {
      const page = await fetchConfirmedSpeakers(
        unitId,
        shownEventId.trim().length > 0 ? shownEventId.trim() : undefined,
      );
      setSpeakers(page.speakers);
      setLoadError(null);
    } catch (cause) {
      setSpeakers([]);
      setLoadError(
        refusalMessage(
          cause,
          "The confirmed-speaker list could not be read and the server gave no reason.",
        ),
      );
    } finally {
      setLoaded(true);
    }
  }, [unitId, shownEventId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function handleReconcile(event: React.FormEvent) {
    event.preventDefault();
    const targetEvent = shownEventId.trim();
    if (unitId === null || targetEvent.length === 0 || invitationId.trim().length === 0) return;
    if (reconciling) return;

    const payload: SpeakerHandoffPayload = { invitation_id: invitationId.trim() };
    if (attendanceId.trim().length > 0) payload.attendance_id = attendanceId.trim();

    setReconciling(true);
    setReconcileError(null);
    try {
      // The response, not the form. `applied` is what this request itself
      // wrote, and the speaker is the row the server read back after
      // committing — so a replay renders "nothing to write" rather than a
      // second confirmation.
      setOutcome(await reconcileSpeakerHandoff(unitId, targetEvent, payload));
      await reload();
    } catch (cause) {
      setOutcome(null);
      setReconcileError(
        refusalMessage(cause, "The hand-off could not be recorded and the server gave no reason."),
      );
    } finally {
      setReconciling(false);
    }
  }

  // `VolunteerPortalLayout` already renders `PortalGate` when the server granted
  // no such portal, so reaching here without a grant means the mapping is still
  // resolving. Render nothing rather than a page about a portal that may turn
  // out not to be assigned.
  if (grant === null) {
    return null;
  }

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-foreground">Your confirmed speaker</h1>
        <p className="text-sm text-muted-foreground">
          Who agreed to speak at your event, in the order they said yes. A Speaker Connector runs
          the matching and sends the invitations; what appears here is the acceptance they were
          given.
        </p>
        <p className="text-xs text-muted-foreground">
          Signed in as {principal.email} · {grant.role} · {grant.org_unit_path}
        </p>
      </header>

      {unitId === null ? (
        <div className="rounded-2xl border border-border/70 bg-card p-6 text-sm text-muted-foreground">
          The server granted this portal but named no org unit for it, so there is nothing to read a
          speaker list under. Unit assignment is an administrator&apos;s decision and is not made
          here.
        </div>
      ) : null}

      <form
        className="flex flex-wrap items-end gap-3 rounded-2xl border border-border/70 bg-card p-5"
        onSubmit={(event) => {
          event.preventDefault();
          setShownEventId(eventFilter);
        }}
      >
        <div className="space-y-1">
          <label htmlFor="handoff-event" className="text-sm font-semibold text-foreground">
            Event reference
          </label>
          <input
            id="handoff-event"
            className="w-80 max-w-full rounded-lg border border-border/70 bg-background p-2 font-mono text-xs"
            value={eventFilter}
            onChange={(event) => setEventFilter(event.target.value)}
            placeholder="The event id you were given"
          />
        </div>
        <button
          type="submit"
          className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground"
        >
          Show this event
        </button>
        <p className="w-full text-xs text-muted-foreground">
          Leave it empty to see every confirmed speaker your unit can hand a host. The server scopes
          the answer to your unit either way.
        </p>
      </form>

      {loadError !== null ? (
        <p
          className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
          role="alert"
        >
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{loadError}</span>
        </p>
      ) : null}

      {loaded && loadError === null && speakers.length === 0 ? (
        <div
          className="rounded-2xl border border-border/70 bg-card p-6 text-sm text-muted-foreground"
          role="status"
        >
          No speaker is confirmed for this event yet.
        </div>
      ) : null}

      {speakers.length > 0 ? (
        /* The confirmed speakers, a page at a time. The pager only windows the
           rows this read already returned — it calls nothing, and its count is
           of what arrived rather than of what the server holds. */
        <PagedList
          items={speakers}
          label="confirmed speakers"
          idPrefix="volunteer-confirmed-speakers"
        >
          {(visibleSpeakers) => (
            <ul className="space-y-4">
              {visibleSpeakers.map((speaker) => (
                <SpeakerCard key={speaker.record_id} speaker={speaker} />
              ))}
            </ul>
          )}
        </PagedList>
      ) : null}

      <section className="space-y-4 rounded-2xl border border-border/70 bg-card p-6">
        <div className="flex items-start gap-3">
          <CalendarCheck className="mt-1 h-5 w-5 text-primary" aria-hidden="true" />
          <div className="space-y-1">
            <h2 className="text-lg font-semibold text-foreground">Record a hand-off</h2>
            <p className="text-sm text-muted-foreground">
              Names an invitation that already carries an acceptance, and brings the speaker&apos;s
              journey up to what the stored rows support. It asserts nothing: every step and every
              timestamp is read out of those rows by the server. Run it twice and the second run
              writes nothing.
            </p>
          </div>
        </div>

        <form className="grid gap-3 sm:grid-cols-2" onSubmit={handleReconcile}>
          <div className="space-y-1">
            <label htmlFor="handoff-invitation" className="text-sm font-semibold text-foreground">
              Invitation reference
            </label>
            <input
              id="handoff-invitation"
              className="w-full rounded-lg border border-border/70 bg-background p-2 font-mono text-xs"
              value={invitationId}
              onChange={(event) => setInvitationId(event.target.value)}
            />
          </div>
          <div className="space-y-1">
            <label htmlFor="handoff-attendance" className="text-sm font-semibold text-foreground">
              Attendance reference (optional)
            </label>
            <input
              id="handoff-attendance"
              className="w-full rounded-lg border border-border/70 bg-background p-2 font-mono text-xs"
              value={attendanceId}
              onChange={(event) => setAttendanceId(event.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Only once they have presented. A speaker who has agreed but not yet spoken is the
              ordinary state.
            </p>
          </div>
          <div className="sm:col-span-2">
            <button
              type="submit"
              className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50"
              disabled={
                reconciling ||
                unitId === null ||
                shownEventId.trim().length === 0 ||
                invitationId.trim().length === 0
              }
            >
              {reconciling ? "Recording…" : "Record the hand-off"}
            </button>
            {shownEventId.trim().length === 0 ? (
              <p className="mt-2 text-xs text-muted-foreground">
                Show an event above first — a hand-off is recorded against one event.
              </p>
            ) : null}
          </div>
        </form>

        {reconcileError !== null ? (
          <p
            className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
            role="alert"
          >
            {reconcileError}
          </p>
        ) : null}

        {outcome !== null ? (
          <div
            className="space-y-2 rounded-xl border border-border/70 p-4"
            role="status"
            aria-live="polite"
          >
            <p className="text-sm text-foreground">
              {outcome.applied.length === 0
                ? "The server wrote nothing: every step this evidence supports was already recorded."
                : `The server recorded: ${outcome.applied.map(stageLabel).join(", ")}.`}
            </p>
            <ul className="space-y-4">
              <SpeakerCard speaker={outcome.speaker} />
            </ul>
          </div>
        ) : null}
      </section>
    </div>
  );
}
