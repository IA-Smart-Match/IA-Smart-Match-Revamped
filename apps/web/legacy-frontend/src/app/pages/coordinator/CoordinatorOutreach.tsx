/**
 * IA West contact — coordinator portal.
 *
 * This page used to load outreach *threads* from the legacy `/api/portals/*`
 * backend, which is not part of this repository. That is still true and the
 * thread panel still says so. What changed in R4 is that outreach drafts and
 * sends are now real: they come from `/v1/units/{unit_id}/outreach/*`, and the
 * Send button submits a durable command.
 *
 * What *is* real on this page comes from four sources and nothing else:
 * `GET /v1/me` for who the caller is, `GET /v1/me/portals` for the portal the
 * server granted them, and the two outreach reads behind {@link useOutreach}.
 * Neither is derived in the browser, and no identifier on this page is chosen
 * by it.
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

import { AlertCircle, Clock, Mail, Send } from "lucide-react";

import { PortalDatasetUnavailable } from "../../components/PortalContent";
import { grantedPortal } from "../../components/PortalGate";
import { useOutreach, type QueuedSend } from "../../hooks/useOutreach";
import { usePortalAccess } from "../../hooks/usePortalAccess";
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

export function CoordinatorOutreach() {
  // `GET /v1/me` — the only source of who this is. It throws rather than
  // substituting a fixture principal, which is the Fix #7 guard.
  const principal = useAuthenticatedPrincipal();
  // `GET /v1/me/portals` — the only source of what the server granted them.
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "coordinator");
  const outreach = useOutreach();

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
        <h1 className="text-2xl font-semibold text-foreground">IA West contact</h1>
        <p className="text-sm text-muted-foreground">Your outreach conversations with the IA West team.</p>
        <p className="text-xs text-muted-foreground">
          Signed in as {principal.email} · {grant.role} · {grant.org_unit_path}
        </p>
      </header>

      <section className="space-y-3" aria-label="Outreach drafts">
        <h2 className="text-lg font-medium text-foreground">Drafts</h2>

        {outreach.status === "loading" && (
          <p className="text-sm text-muted-foreground">Loading drafts…</p>
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
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm font-medium disabled:opacity-50"
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

      <div className="space-y-4">
        {/* Still true, and unchanged by R4: threads are a legacy dataset this
            repository does not carry, and this slice deliberately did not
            invent one (OQ-008). Sends are not threads. */}
        <PortalDatasetUnavailable
          dataset="Outreach threads"
          endpoints={["/api/portals/event-coordinators/{id}/threads"]}
        />
      </div>
    </div>
  );
}
