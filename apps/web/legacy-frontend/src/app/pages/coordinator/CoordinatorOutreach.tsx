/**
 * CBA contact — coordinator portal.
 *
 * This page used to load outreach *threads* from the legacy `/api/portals/*`
 * backend, which is not part of this repository. R4 made drafts and sends real
 * — they come from `/v1/units/{unit_id}/outreach/*`, and the Send button
 * submits a durable command — but the page went on rendering an unavailable
 * panel for threads beside them.
 *
 * That panel is now gone, and **not** because a thread list appeared. It is
 * gone because it was the wrong instrument for what is missing. An unavailable
 * panel says "this deployment does not carry that dataset", which invites the
 * reader to expect the dataset back; the truth is that `/v1` outreach was
 * designed to store something else. An `outreach_draft` is a composed message
 * and an `outreach_send` is one attempt to deliver it (OQ-008). There is no
 * inbound leg anywhere in this API, so a thread is not withheld here — it is a
 * shape this data does not have, and {@link UnitSends} says so in the place the
 * panel used to sit.
 *
 * What is emphatically not done is the easy version: renaming the sends listing
 * "threads" so the old copy survives. That is the fabricated equivalence the
 * unavailable panels exist to prevent, and a reader shown "threads" would go
 * looking for replies that do not exist.
 *
 * What *is* real on this page comes from five sources and nothing else:
 * `GET /v1/me` for who the caller is, `GET /v1/me/portals` for the portal the
 * server granted them, the two outreach reads behind {@link useOutreach}, and
 * `GET /v1/units/{unit_id}/outreach/sends` for the listing below. Neither is
 * derived in the browser, and no identifier on this page is chosen by it.
 *
 * ## What this page will not say
 *
 * `docs/plans/frontend-broken-buttons.md` B17 records what the legacy Send
 * button did: `console.log("Message sent:")`, then "Message sent!" for two
 * seconds, then close — with no request. The correction is not a fetch bolted
 * onto the same optimism. **Nothing below renders the word "sent".** The
 * furthest this page goes on its own is "queued", which is exactly what a
 * `202` means, and everything stronger is quoted from a server read: the
 * disposition, the provider, and the delivery events.
 *
 * A disposition of `null` renders as "waiting for the worker", never as a
 * failure and never as a success — ADR-0011's rule at the last boundary, which
 * is the boundary where it usually gets broken.
 *
 * ## Why there is no compose form here
 *
 * Composing needs a `contact_channel_id`, and this deployment has no screen
 * that lists contacts — `contact_channel` ships empty, because a migration is
 * not in a position to assert that a named person agreed to be contacted
 * (OQ-004). A form with a UUID field would be a control that only works for
 * someone who has already queried the database, which is not a coordinator.
 *
 * So this page renders the drafts the server has and sends them. When the
 * contact surface exists, the compose call is already here in
 * {@link useOutreach} waiting for it.
 */

import { AlertCircle, Clock, Mail, Send, UserCheck } from "lucide-react";

import {
  fetchOutreachSends,
  type OutreachSendSummary,
  type SpeakerInvitationOutcome,
} from "../../../lib/api";
import { grantedPortal } from "../../components/PortalGate";
import {
  OUTREACH_NO_UNIT_REASON,
  useOutreach,
  type QueuedSend,
} from "../../hooks/useOutreach";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useScopedQuery } from "../../hooks/useScopedQuery";
import {
  INVITATIONS_NO_UNIT_REASON,
  useSpeakerInvitations,
} from "../../hooks/useSpeakerInvitations";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";

/**
 * How a server disposition reads to a coordinator.
 *
 * `accepted` is deliberately not "delivered" or "sent". A provider message id
 * means the provider took custody; whether it arrives is a later delivery event
 * that may never come, and the send read carries those events for anyone who
 * needs to know more than this line.
 */
function describeDisposition(disposition: string | null): string {
  switch (disposition) {
    case null:
      return "Waiting for the worker. No message has been sent yet.";
    case "accepted":
      return "The email provider accepted the message. Delivery is reported separately.";
    case "blocked":
      return "Refused at send time. The recipient may no longer be contacted.";
    case "failed":
      return "The provider failed. This can be retried.";
    default:
      // An unrecognised value is reported verbatim rather than mapped to
      // anything reassuring: a disposition this build does not know about is
      // not thereby a success.
      return `The server reported "${disposition}".`;
  }
}

function QueuedSendPanel({ queued }: { queued: QueuedSend }) {
  const send = queued.send;

  return (
    <section
      className="rounded-2xl border border-border bg-muted/30 p-4 text-sm"
      aria-label="Send status"
    >
      <div className="flex items-center gap-2 font-medium text-foreground">
        <Clock className="h-4 w-4" aria-hidden />
        {/* "Queued", never "sent". The server answered 202 and the dispatcher
            has not moved the command. */}
        Queued
      </div>
      <p className="mt-1 text-muted-foreground">
        The send command was accepted and recorded. Nothing has been delivered yet.
      </p>
      <dl className="mt-2 space-y-1 text-xs text-muted-foreground">
        <div>
          <dt className="inline font-medium">Job: </dt>
          <dd className="inline font-mono">{queued.jobId}</dd>
        </div>
        <div>
          <dt className="inline font-medium">Events: </dt>
          <dd className="inline font-mono">{queued.eventsUrl}</dd>
        </div>
      </dl>

      {send !== null && (
        <div className="mt-3 border-t border-border pt-3">
          <p className="text-foreground">{describeDisposition(send.disposition)}</p>
          {send.failure_reason !== null && (
            <p className="mt-1 text-xs text-muted-foreground">{send.failure_reason}</p>
          )}
          {send.delivery_events.length > 0 && (
            <ul className="mt-2 space-y-0.5 text-xs text-muted-foreground">
              {send.delivery_events.map((event) => (
                <li key={`${event.event_type}-${event.occurred_at}`}>
                  {event.event_type} · {event.occurred_at}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

/**
 * How a skip reads to a Connector, in terms of what they can do about it.
 *
 * Every case names an action, because that is what a skip is for: a batch that
 * said "3 skipped" would be answering a question nobody asked.
 */
function describeSkip(reason: string): string {
  switch (reason) {
    case "not_on_roster":
      return "Not on this unit's speaker list. Add them first, then invite.";
    case "no_contact_channel":
      return "On the list, but this unit holds no address for them.";
    case "channel_suppressed":
      return "This person asked us to stop writing to them. That outranks everything.";
    case "channel_not_active_candidate":
      return "Their address has not been activated. Someone has to do that deliberately.";
    case "consent_source_not_approved":
      return "The consent behind this address cannot authorize a send.";
    default:
      // Reported verbatim rather than mapped to anything reassuring: a reason
      // this build does not recognise is not thereby a small problem.
      return `The server reported "${reason}".`;
  }
}

/**
 * How a **Speaker's** answer reads. Never how a provider's disposition reads.
 *
 * Deliberately a separate function from {@link describeDisposition}, taking a
 * separate field, and there is no code path in this file that could route one
 * value into the other. Two functions rather than one with a mode flag: a shared
 * renderer is a place where a caller can eventually pass the wrong fact.
 */
function describeSpeakerResponse(response: string): string {
  switch (response) {
    case "awaiting_response":
      return "No answer yet.";
    case "accepted_invitation":
      return "Agreed to speak.";
    case "declined_invitation":
      return "Declined this invitation.";
    default:
      return `The server reported "${response}".`;
  }
}

/**
 * One recipient's outcome, with the two facts on two separate lines.
 *
 * The layout is the argument. "The provider took custody" and "the professional
 * agreed to come" are rendered as different sentences under different labels,
 * because a single status column is where an Event Host reads the first as the
 * second and books a room for nobody.
 */
function InvitationOutcomeRow({
  outcome,
  onRecord,
}: {
  outcome: SpeakerInvitationOutcome;
  onRecord: (invitationId: string, response: "accept" | "decline") => void;
}) {
  const answered = outcome.speaker_response.response !== "awaiting_response";

  return (
    <li className="rounded-xl border border-border p-3 text-sm">
      <p className="font-medium text-foreground">
        {outcome.recipient_address ?? "(no address — nobody was written to)"}
      </p>

      {outcome.status === "skipped" && outcome.skip_reason !== null ? (
        <p className="mt-1 text-muted-foreground">
          Not invited. {describeSkip(outcome.skip_reason)}
        </p>
      ) : (
        <dl className="mt-2 space-y-1 text-xs">
          <div>
            <dt className="font-medium text-foreground">Message</dt>
            <dd className="text-muted-foreground">
              {outcome.status === "pending"
                ? "Composed. No send has been submitted."
                : outcome.delivery === null
                  ? // Two different unknowns, and this is the second: a command
                    // was submitted and the worker has not written a send yet.
                    "Send command submitted. The worker has not reported yet."
                  : describeDisposition(outcome.delivery.disposition)}
            </dd>
          </div>
          <div>
            <dt className="font-medium text-foreground">Speaker</dt>
            <dd className="text-muted-foreground">
              {describeSpeakerResponse(outcome.speaker_response.response)}
              {outcome.speaker_response.channel === "connector_recorded" && (
                // Surfaced rather than hidden: an answer a coordinator typed in
                // is a weaker claim than one the Speaker made themselves, and a
                // screen showing them alike would assert a directness nobody
                // has.
                <span> (recorded by a coordinator, not by the Speaker.)</span>
              )}
            </dd>
          </div>
        </dl>
      )}

      {outcome.status === "dispatched" && !answered && (
        <div className="mt-2 flex gap-2">
          {(["accept", "decline"] as const).map((verb) => (
            <button
              key={verb}
              type="button"
              className="inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-border px-2 py-1 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              onClick={() => onRecord(outcome.invitation_id, verb)}
            >
              <UserCheck className="h-3 w-3" aria-hidden />
              {/* "They told me they …", not "mark as …". The button records
                  something a person said, and its label says whose words. */}
              They {verb}ed
            </button>
          ))}
        </div>
      )}
    </li>
  );
}

/**
 * §13's invitation tracking, on the consented `/v1` path.
 *
 * There is no compose form here, for the reason this module's docstring gives
 * about outreach drafts and then some: composing a batch needs the roster ids a
 * Connector picked off a shortlist, which is the match-run screen's output
 * rather than something to retype. So this renders the batches the server has,
 * dispatches them, and tracks what came back.
 *
 * The unit arrives as a prop for the reason {@link UnitSends} gives: it is the
 * one the server granted, resolved once by {@link CoordinatorOutreach}, so this
 * section cannot end up describing a different unit from the drafts above it.
 */
function InvitationBatches({ unitId }: { unitId: string | null }) {
  const invitations = useSpeakerInvitations(unitId);
  const batch = invitations.openBatch;

  return (
    <section className="space-y-3" aria-label="Speaker invitations">
      <h2 className="text-lg font-medium text-foreground">Speaker invitations</h2>

      {invitations.status === "loading" && (
        <p className="text-sm text-muted-foreground">Loading invitation batches…</p>
      )}

      {invitations.status === "idle" && (
        // A third state, and the honest one on an account whose granted portal
        // carries no unit: nothing was asked for, so nothing failed and nothing
        // is empty. Reached only after the grant resolved — the page renders
        // nothing at all while it is still in flight.
        <p className="text-sm text-muted-foreground">{INVITATIONS_NO_UNIT_REASON}</p>
      )}

      {invitations.status === "unavailable" && (
        // Not an empty list, for the drafts section's reason: a read that failed
        // says nothing about how many batches exist.
        <p className="flex items-start gap-2 text-sm text-muted-foreground">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <span>{invitations.loadError}</span>
        </p>
      )}

      {invitations.status === "ready" && invitations.batches.length === 0 && (
        <p className="text-sm text-muted-foreground">No invitation batches in this unit.</p>
      )}

      {invitations.status === "ready" &&
        invitations.batches.map((summary) => (
          <article key={summary.batch_id} className="rounded-2xl border border-border p-4">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 space-y-1">
                <p className="font-medium text-foreground">{summary.event_name}</p>
                {/* Rendered exactly as the Connector typed it. The server does
                    not parse this string and neither does the browser. */}
                <p className="text-xs text-muted-foreground">{summary.event_date}</p>
              </div>
              <button
                type="button"
                className="min-h-11 shrink-0 rounded-lg border border-border px-3 py-1.5 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                onClick={() => {
                  void invitations.openBatchById(summary.batch_id);
                }}
              >
                Open
              </button>
            </div>
          </article>
        ))}

      {invitations.openBatchError !== null && (
        <p className="flex items-start gap-2 text-sm text-destructive" role="alert">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <span>{invitations.openBatchError}</span>
        </p>
      )}

      {batch !== null && (
        <section className="rounded-2xl border border-border p-4" aria-label="Batch outcomes">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="font-medium text-foreground">{batch.event_name}</p>
              <p className="text-xs text-muted-foreground">
                {batch.invited_count} invited · {batch.skipped_count} not invited
              </p>
            </div>
            <button
              type="button"
              className="inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm font-medium disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              disabled={invitations.dispatchState === "submitting"}
              onClick={() => {
                void invitations.dispatchBatch(batch.batch_id);
              }}
            >
              <Send className="h-4 w-4" aria-hidden />
              {/* "Send invitations", and the panel below says "queued" — never
                  "sent", which is B17's whole lesson applied to a batch. */}
              {invitations.dispatchState === "submitting" ? "Submitting…" : "Send invitations"}
            </button>
          </div>

          {invitations.dispatchState === "failed" && invitations.dispatchError !== null && (
            <p className="mt-2 flex items-start gap-2 text-sm text-destructive" role="alert">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <span>The dispatch was not accepted: {invitations.dispatchError}</span>
            </p>
          )}

          {invitations.lastDispatch !== null && (
            <div className="mt-3 rounded-xl border border-border bg-muted/30 p-3 text-sm">
              <p className="flex items-center gap-2 font-medium text-foreground">
                <Clock className="h-4 w-4" aria-hidden />
                {/* Queued. The server answered 202 per command and the
                    dispatcher has not moved any of them. */}
                {invitations.lastDispatch.dispatched.length} queued
              </p>
              <p className="mt-1 text-muted-foreground">
                The send commands were accepted and recorded. Nothing has been delivered yet.
              </p>
              {invitations.lastDispatch.not_dispatched.length > 0 && (
                <ul className="mt-2 space-y-0.5 text-xs text-muted-foreground">
                  {invitations.lastDispatch.not_dispatched.map((refused) => (
                    <li key={refused.invitation_id}>
                      {/* Refused *now*, on state read at dispatch time — a
                          channel can be suppressed between composing a batch
                          and sending it. The invitation stays pending. */}
                      Not sent — {describeSkip(refused.reason)}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <ul className="mt-3 space-y-2">
            {batch.invitations.map((outcome) => (
              <InvitationOutcomeRow
                key={outcome.invitation_id}
                outcome={outcome}
                onRecord={(invitationId, verb) => {
                  void invitations.recordResponse(invitationId, verb);
                }}
              />
            ))}
          </ul>
        </section>
      )}
    </section>
  );
}

/**
 * What this unit has actually attempted — the sends listing, and not a thread list.
 *
 * This section replaces a `PortalDatasetUnavailable` for "Outreach threads",
 * and the replacement is deliberately not a rename. The legacy
 * `/api/portals/event-coordinators/{id}/threads` is gone and what `/v1` holds
 * is a different shape: an `outreach_send` is one attempt to deliver one
 * composed message. OQ-008 records that this slice stores sends rather than
 * threads. There is no inbound leg in this API, so no row below is half of an
 * exchange, and nothing here implies anyone answered.
 *
 * Rendering these rows under the old heading would be the fabricated
 * equivalence the unavailable panel existed to prevent — a reader told they are
 * looking at threads goes looking for replies that are not withheld but absent.
 * So the heading, the copy and the labels all say sends.
 *
 * `GET /v1/units/{unit_id}/outreach/sends` was the missing half of this page.
 * Drafts could be listed and a single send could be read by id, so the only way
 * to see what a unit had attempted was to have kept the ids from when it
 * attempted them — which meant, in practice, that a send submitted in an
 * earlier session was unreadable.
 *
 * ## Two things this section will not do
 *
 * It does not count. Neither `limit` nor `offset` is a total — they are what
 * was asked for — and a count of one page presented as a number of attempts
 * would be a figure with no owning query behind it.
 *
 * It does not summarise a delivery stream, because the listing carries none.
 * The route omits it on purpose: folding a send's events into one word is a
 * choice about which fact to forget when a provider reports one thing and then
 * another, and making that choice once per row would bury it. A reader who
 * needs to explain what happened to one message opens that send.
 *
 * ## The unit this reads
 *
 * The unit the server granted the account — `default_unit_id` off
 * `grantedPortal(...)`, resolved once in {@link CoordinatorOutreach} and handed
 * to every read on the screen, so all three lists are one unit's.
 *
 * This used to be `getConfiguredUnitId()`, the `VITE_SMARTMATCH_UNIT_ID` build
 * variable, and this docstring named the resulting divergence from the
 * Connector dashboard rather than papering over it. That divergence is now
 * closed at its source: `useOutreach` and `useSpeakerInvitations` take the unit
 * as an argument, so there is no longer a second answer to which unit this
 * screen is about. On the classroom VM, where the variable is unset, the old
 * lookup returned `null` and every panel here reported "unavailable" while the
 * unit's drafts, batches and sends sat in the database.
 *
 * `null` here is rendered as {@link OUTREACH_NO_UNIT_REASON} and not as an
 * empty listing: "this unit has attempted no sends" is a claim about a unit,
 * and there is no unit to make it about.
 */
function UnitSends({ unitId }: { unitId: string | null }) {
  // The same cache slot `CoordinatorHome`'s sends read uses — the dashboard's
  // count is this listing's warm-up. The slot holds the sends array itself,
  // matching the dashboard's shape.
  const sendsQuery = useScopedQuery({
    resource: "outreach-sends",
    params: [unitId],
    queryFn: async () => (await fetchOutreachSends(unitId as string)).sends,
    enabled: unitId !== null,
  });

  // The list is left null rather than emptied. A read that failed says
  // nothing about how many sends exist, and an empty list would be a
  // claim this is not in a position to make (ADR-0011).
  const sends: OutreachSendSummary[] | null = sendsQuery.data ?? null;
  const error = sendsQuery.isError
    ? sendsQuery.error instanceof Error
      ? sendsQuery.error.message
      : "The send listing failed."
    : null;
  const settled = unitId === null || !sendsQuery.isPending;

  return (
    <section className="space-y-3" aria-label="Outreach sends">
      <h2 className="text-lg font-medium text-foreground">Sends</h2>
      <p className="text-sm leading-6 text-muted-foreground">
        Every attempt this unit has made to deliver a draft, newest first. These are send
        records, not conversations: this API has no inbound leg, and no row here is part of an
        exchange.
      </p>

      {unitId === null ? (
        <p className="text-sm text-muted-foreground">{OUTREACH_NO_UNIT_REASON}</p>
      ) : error !== null ? (
        <p className="flex items-start gap-2 text-sm text-muted-foreground">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <span>{error}</span>
        </p>
      ) : sends === null ? (
        <p className="text-sm text-muted-foreground" role="status">
          {settled ? "The send listing returned nothing." : "Loading sends…"}
        </p>
      ) : sends.length === 0 ? (
        // Safe to say here, and only here: the server answered, and its answer
        // was none.
        <p className="text-sm text-muted-foreground">This unit has attempted no sends.</p>
      ) : (
        <ul className="space-y-2">
          {sends.map((send) => (
            <li key={send.send_id} className="rounded-2xl border border-border p-4 text-sm">
              <p className="font-medium text-foreground">{send.recipient_address}</p>
              {/* `describeDisposition` and nothing stronger — the same function
                  the single-send panel uses, so the two cannot drift into
                  saying different things about one field. */}
              <p className="mt-1 text-muted-foreground">{describeDisposition(send.disposition)}</p>
              {send.failure_reason !== null && (
                <p className="mt-1 text-xs text-muted-foreground">{send.failure_reason}</p>
              )}
              <dl className="mt-2 space-y-0.5 text-xs text-muted-foreground">
                <div>
                  <dt className="inline font-medium">Attempted: </dt>
                  {/* The server's own timestamp string, rendered as received. */}
                  <dd className="inline font-mono">{send.created_at}</dd>
                </div>
                <div>
                  <dt className="inline font-medium">Concluded: </dt>
                  <dd className="inline font-mono">
                    {send.concluded_at ?? "not yet — the attempt has no outcome"}
                  </dd>
                </div>
                {send.provider !== null && (
                  <div>
                    <dt className="inline font-medium">Provider: </dt>
                    <dd className="inline">{send.provider}</dd>
                  </div>
                )}
              </dl>
            </li>
          ))}
        </ul>
      )}

      <p className="text-xs leading-5 text-muted-foreground">
        The server decides how many rows a page carries and reports no total, so this is a page
        of attempts rather than all of them. Delivery events are not listed per row — a stream
        folded into one word is a choice about which fact to forget, so it stays on the send
        itself.
      </p>
    </section>
  );
}

export function CoordinatorOutreach() {
  // `GET /v1/me` — the only source of who this is. It throws rather than
  // substituting a fixture principal, which is the Fix #7 guard.
  const principal = useAuthenticatedPrincipal();
  // `GET /v1/me/portals` — the only source of what the server granted them.
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "coordinator");
  // The unit is the one the grant carries, never the `VITE_SMARTMATCH_UNIT_ID`
  // build variable — the rule `CoordinatorEvents.tsx` states, now held by every
  // read on this page. Resolved once here and passed down, so the drafts, the
  // invitation batches and the sends listing cannot disagree about which unit
  // this screen is about.
  const unitId = grant?.default_unit_id ?? null;
  const outreach = useOutreach(unitId);

  // `CoordinatorPortalLayout` already renders `PortalGate` when the server granted
  // no such portal, so reaching here without a grant means the mapping is
  // still resolving. Render nothing rather than a header about a portal that
  // may turn out not to be assigned.
  if (grant === null) {
    return null;
  }

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-foreground">CBA contact</h1>
        <p className="text-sm text-muted-foreground">Your outreach conversations with the CBA team.</p>
        <p className="text-xs text-muted-foreground">
          Signed in as {principal.email} · {grant.role} · {grant.org_unit_path}
        </p>
      </header>

      <section className="space-y-3" aria-label="Outreach drafts">
        <h2 className="text-lg font-medium text-foreground">Drafts</h2>

        {outreach.status === "loading" && (
          <p className="text-sm text-muted-foreground">Loading drafts…</p>
        )}

        {outreach.status === "idle" && (
          // Distinct from both neighbours. Nothing was asked for, so this is
          // neither a failure nor an empty unit — and it is not "loading"
          // either, because the mapping has already answered by the time this
          // renders (the grant guard above returns null while it has not).
          <p className="text-sm text-muted-foreground">{OUTREACH_NO_UNIT_REASON}</p>
        )}

        {outreach.status === "unavailable" && (
          // Not an empty list. A read that failed says nothing about how many
          // drafts exist, and rendering "no drafts" would be a claim this is
          // not in a position to make (ADR-0011).
          <p className="flex items-start gap-2 text-sm text-muted-foreground">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>{outreach.loadError}</span>
          </p>
        )}

        {outreach.status === "ready" && outreach.drafts.length === 0 && (
          // Safe to say here, and only here: the server answered, and its
          // answer was none.
          <p className="text-sm text-muted-foreground">No drafts in this unit.</p>
        )}

        {outreach.status === "ready" &&
          outreach.drafts.map((draft) => (
            <article
              key={draft.draft_id}
              className="rounded-2xl border border-border p-4"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 space-y-1">
                  <p className="flex items-center gap-2 font-medium text-foreground">
                    <Mail className="h-4 w-4 shrink-0" aria-hidden />
                    <span className="truncate">{draft.subject}</span>
                  </p>
                  <p className="text-xs text-muted-foreground">
                    To {draft.recipient_address} · {draft.template_id} · v{draft.version} ·{" "}
                    {draft.status}
                  </p>
                  {draft.content_status === "synthetic" && (
                    // Surfaced rather than hidden: this is the fact that decides
                    // whether the message could go to a real person (OQ-003).
                    <p className="text-xs text-muted-foreground">
                      Pilot copy — this template has not been through institutional review,
                      and a live send would refuse it.
                    </p>
                  )}
                </div>

                <button
                  type="button"
                  className="inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm font-medium disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  // Disabled for an unapproved draft, because the server would
                  // refuse it with a 409 — offering a button that cannot work
                  // is the shape this page exists to stop.
                  disabled={
                    draft.status !== "approved" || outreach.sendState === "submitting"
                  }
                  onClick={() => {
                    void outreach.sendDraft(draft.draft_id);
                  }}
                >
                  <Send className="h-4 w-4" aria-hidden />
                  {outreach.sendState === "submitting" ? "Submitting…" : "Send"}
                </button>
              </div>
            </article>
          ))}

        {outreach.sendState === "failed" && outreach.sendError !== null && (
          <p
            className="flex items-start gap-2 text-sm text-destructive"
            role="alert"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>The send was not accepted: {outreach.sendError}</span>
          </p>
        )}

        {outreach.queued !== null && <QueuedSendPanel queued={outreach.queued} />}
      </section>

      <InvitationBatches unitId={unitId} />

      <UnitSends unitId={unitId} />
    </div>
  );
}
