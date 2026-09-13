/**
 * Compose speaker invitations from a shortlist — Connector portal (§§6, 13).
 *
 * `CoordinatorOutreach.tsx` stated the precondition for this page in its own
 * words: "composing a batch needs the roster ids a Connector picked off a
 * shortlist, which is the match-run screen's output rather than something to
 * retype." That shortlist now exists as a server row, so this page composes
 * against it — and every recipient it offers arrives from
 * `GET /v1/units/{unit_id}/match-runs/{match_run_id}`.
 *
 * ## Four things it does not do, each for a stated reason
 *
 * **It asks nobody to type an identifier.** The unit comes from
 * `GET /v1/me/portals`, the run id from the link the shortlist page carried,
 * and each recipient's id from that run's own `subject_id`s. A form with an id
 * box is a control that only works for someone who has already queried the
 * database, which is not a Connector.
 *
 * **It composes nothing for a person who has not consented.** The batch route
 * checks consent, the dispatch checks it again against state read then, and
 * the worker checks it a third time at delivery. All three are real and none of
 * them helps a Connector who finds out from a job log that three of their names
 * could not be written to. So this page reads each shortlisted person's
 * channels first and renders the server's own `send_eligible` — with
 * `suppressed`, `contact_state` and `consent_source` beside it as the
 * explanation, never as a recomputation. An ineligible recipient is shown,
 * disabled, with the reason, rather than hidden: the reason is what tells a
 * Connector what to do next.
 *
 * That gating is a courtesy and a disclosure. It is **not** authorization —
 * `/v1` stays deny-by-default and tenant-scoped, and the server re-decides
 * every one of these calls whatever this browser renders.
 *
 * **It says nothing was sent.** `POST .../batches` writes invitation rows and
 * submits no send at all. "Queued" is the strongest true word for what comes
 * back, which is B17's lesson applied one step earlier than the outreach Send
 * button had to learn it.
 *
 * **It does not dispatch or track.** Both live on `CoordinatorOutreach.tsx` and
 * stay there. A second control submitting `outreach.send` would be a second
 * place the delivery-time consent recheck has to be reasoned about, and this
 * page links to the first one instead of growing a copy.
 *
 * ## No score, no ranking, no arithmetic
 *
 * The run's shortlist is rendered in the order the server returned it. Nothing
 * here sorts, thresholds or displays a number the optimizer produced — the
 * ratified G1 presentation rule and OQ-CBA-005 hold on this surface as they do
 * on the two before it. What the page does show is the run's
 * `registry_version`, because provenance should travel with a shortlist
 * somebody is about to act on.
 */

import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { AlertCircle, CheckCircle2, ListChecks, Mail, ShieldAlert } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import {
  ApiRequestError,
  createSpeakerInvitationBatch,
  fetchMatchRun,
  fetchSpeakerContactChannels,
  fetchSpeakerContacts,
  type MatchRunRead,
  type SpeakerContact,
  type SpeakerContactChannel,
  type SpeakerInvitationBatch,
} from "../../../lib/api";
import { scopedQueryKey } from "../../../lib/queryClient";
import { PagedList } from "../../components/PagedList";
import { grantedPortal } from "../../components/PortalGate";
import { usePrincipalKey } from "../../components/PrincipalQueryProvider";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";
import { useScopedQuery } from "../../hooks/useScopedQuery";

/**
 * How a skip reads to a Connector, in terms of what they can do about it.
 *
 * A local copy of the vocabulary `CoordinatorOutreach.tsx` renders, and
 * deliberately a copy rather than a shared helper: these are two screens
 * answering two different questions ("why was nobody written to" there, "why
 * can I not pick this person" here), and a shared renderer is a place where one
 * screen's wording quietly becomes the other's.
 */
function describeSkip(reason: string): string {
  switch (reason) {
    case "not_on_roster":
      return "Not on this unit's speaker list. Add them first, then invite.";
    case "no_contact_channel":
      return "On the list, and this unit holds no address for them.";
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

/** One shortlisted person, with the two server reads behind their row. */
interface Recipient {
  subjectId: string;
  /** From the §13 roster read, or null when this unit's page did not carry them. */
  contact: SpeakerContact | null;
  /** The server's channel rows, or null when that read failed for this person. */
  channels: SpeakerContactChannel[] | null;
  channelsError: string | null;
}

/** Whether this person may be picked, and the sentence that says why not. */
interface ConsentVerdict {
  selectable: boolean;
  explanation: string;
  /** The address a send would use, when the server says one is usable. */
  address: string | null;
}

/**
 * The server's `send_eligible`, read — plus the fields behind it, rendered as
 * explanation.
 *
 * Note what this does not do: it never decides eligibility. `send_eligible` is
 * computed server-side from lifecycle state, consent source and a live
 * suppression join together, and a browser that recombined those itself would
 * be a second answer to "may we write to this person". The branches below only
 * pick which already-true fact to say out loud.
 */
function judgeConsent(recipient: Recipient): ConsentVerdict {
  if (recipient.channels === null) {
    return {
      selectable: false,
      explanation:
        recipient.channelsError ??
        "The server did not answer when asked which addresses it holds for this person, so " +
          "this page cannot say whether they may be written to.",
      address: null,
    };
  }

  const usable = recipient.channels.find((channel) => channel.send_eligible);
  if (usable !== undefined) {
    return {
      selectable: true,
      explanation: `${usable.channel_kind} · consent recorded as ${
        usable.consent_source ?? "an unnamed source"
      }`,
      address: usable.address,
    };
  }

  if (recipient.channels.length === 0) {
    return {
      selectable: false,
      explanation: describeSkip("no_contact_channel"),
      address: null,
    };
  }

  const blocked = recipient.channels[0];
  if (blocked.suppressed) {
    return { selectable: false, explanation: describeSkip("channel_suppressed"), address: null };
  }
  if (blocked.contact_state !== "active_candidate") {
    return {
      selectable: false,
      explanation: `${describeSkip("channel_not_active_candidate")} The server records it as "${
        blocked.contact_state
      }".`,
      address: null,
    };
  }
  return {
    selectable: false,
    explanation: `${describeSkip("consent_source_not_approved")} The recorded source is "${
      blocked.consent_source ?? "none"
    }".`,
    address: null,
  };
}

/** One shortlisted person. Ineligible rows are shown, disabled, with the reason. */
function RecipientRow({
  recipient,
  verdict,
  selected,
  onToggle,
}: {
  recipient: Recipient;
  verdict: ConsentVerdict;
  selected: boolean;
  onToggle: (subjectId: string) => void;
}) {
  return (
    <li className="rounded-xl border border-border/70 p-4">
      <label
        className={
          verdict.selectable ? "flex items-start gap-3" : "flex items-start gap-3 opacity-70"
        }
      >
        <input
          type="checkbox"
          className="mt-1"
          checked={selected}
          disabled={!verdict.selectable}
          onChange={() => onToggle(recipient.subjectId)}
        />
        <span className="space-y-1">
          <span className="block font-semibold text-foreground">
            {recipient.contact?.full_name ??
              "A shortlisted person this unit's roster page did not carry"}
          </span>
          {recipient.contact !== null &&
          (recipient.contact.company !== null || recipient.contact.title !== null) ? (
            <span className="block text-sm text-muted-foreground">
              {[recipient.contact.title, recipient.contact.company].filter(Boolean).join(" · ")}
            </span>
          ) : null}
          {verdict.selectable ? (
            <span className="flex items-start gap-2 text-sm text-muted-foreground">
              <Mail className="mt-1 h-4 w-4 shrink-0" aria-hidden="true" />
              {verdict.address} — {verdict.explanation}
            </span>
          ) : (
            <span className="flex items-start gap-2 text-sm text-amber-700">
              <ShieldAlert className="mt-1 h-4 w-4 shrink-0" aria-hidden="true" />
              {verdict.explanation}
            </span>
          )}
        </span>
      </label>
    </li>
  );
}

/**
 * What the server composed, and what it declined to compose.
 *
 * Every figure is a server figure, and the heading is "Queued" because that is
 * what a composed batch is: rows written, no send submitted, nothing delivered.
 */
function ComposedBatchPanel({ batch }: { batch: SpeakerInvitationBatch }) {
  return (
    <section className="space-y-3 rounded-xl border border-border/70 p-5">
      <h2 className="flex items-center gap-2 text-lg font-semibold text-foreground">
        <ListChecks className="h-4 w-4" aria-hidden="true" />
        Queued
      </h2>
      <p className="text-sm text-muted-foreground">
        The server composed this batch and submitted nothing. No message has left the platform, and
        none will until the batch is dispatched from the CBA contact page.
      </p>
      {batch.replayed ? (
        <p className="rounded-lg border border-border/70 p-3 text-sm text-muted-foreground">
          This answer replayed a batch that already existed. Nobody was invited twice, and these are
          the outcomes of the first submission.
        </p>
      ) : null}
      <dl className="grid gap-2 text-sm sm:grid-cols-2">
        <div>
          <dt className="inline text-muted-foreground">Event&nbsp;</dt>
          <dd className="inline">{batch.event_name}</dd>
        </div>
        <div>
          <dt className="inline text-muted-foreground">Date as written&nbsp;</dt>
          <dd className="inline">{batch.event_date}</dd>
        </div>
        <div>
          <dt className="inline text-muted-foreground">Invitations composed&nbsp;</dt>
          <dd className="inline">{batch.invited_count}</dd>
        </div>
        <div>
          <dt className="inline text-muted-foreground">Not invited&nbsp;</dt>
          <dd className="inline">{batch.skipped_count}</dd>
        </div>
      </dl>

      <ul className="space-y-2">
        {batch.invitations.map((outcome) => (
          <li key={outcome.invitation_id} className="rounded-lg border border-border/70 p-3 text-sm">
            <p className="font-medium text-foreground">
              {outcome.recipient_address ?? "(no address — nobody was written to)"}
            </p>
            <p className="text-muted-foreground">
              {outcome.status === "skipped" && outcome.skip_reason !== null
                ? `Not invited. ${describeSkip(outcome.skip_reason)}`
                : "Composed. No send has been submitted for it."}
            </p>
          </li>
        ))}
      </ul>

      <p className="text-sm">
        <Link className="font-medium underline" to="/coordinator-portal/outreach">
          Open CBA contact to dispatch and track this batch
        </Link>
      </p>
    </section>
  );
}

export function CoordinatorInvitations() {
  // `GET /v1/me` — the only source of who this is. It throws rather than
  // substituting a fixture principal, which is the Fix #7 guard.
  useAuthenticatedPrincipal();
  // `GET /v1/me/portals` — the only source of the unit this page reads and
  // writes. Never composed in the browser.
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "coordinator");
  const unitId = grant?.default_unit_id ?? null;

  // The run whose shortlist this composes against. It arrives in the link the
  // shortlist page carried, which is where the server put it.
  const [searchParams] = useSearchParams();
  const matchRunId = searchParams.get("run");

  const queryClient = useQueryClient();
  const principalKey = usePrincipalKey();

  // One cached composite per run: the run itself, the roster (shared with the
  // `speaker-contacts` slot), and one channel read per shortlisted candidate.
  // Each channel read may still fail on its own — a candidate whose channels
  // the server refused is reported on that row rather than collapsing the
  // whole composition into a banner.
  const composeQuery = useScopedQuery({
    resource: "invitation-compose",
    params: [unitId, matchRunId],
    enabled: unitId !== null && matchRunId !== null && principalKey !== null,
    queryFn: async () => {
      const id = unitId as string;
      const runParam = matchRunId as string;
      const [readRun, roster] = await Promise.all([
        fetchMatchRun(id, runParam),
        queryClient.fetchQuery({
          queryKey: scopedQueryKey(principalKey as string, "speaker-contacts", id),
          queryFn: () => fetchSpeakerContacts(id),
        }),
      ]);

      // The recipients are the run's shortlist, in the order the server
      // returned it. Nothing here re-orders or re-selects them.
      const rows = await Promise.all(
        readRun.shortlist.map(async (candidate): Promise<Recipient> => {
          const contact =
            roster.contacts.find((entry) => entry.professional_id === candidate.subject_id) ?? null;
          try {
            const channels = await fetchSpeakerContactChannels(id, candidate.subject_id);
            return {
              subjectId: candidate.subject_id,
              contact,
              channels: channels.channels.map((entry) => entry.channel),
              channelsError: null,
            };
          } catch (cause) {
            return {
              subjectId: candidate.subject_id,
              contact,
              channels: null,
              channelsError:
                cause instanceof ApiRequestError
                  ? cause.message
                  : "The channel read failed and the server gave no reason.",
            };
          }
        }),
      );
      return { run: readRun, recipients: rows };
    },
  });

  const run: MatchRunRead | null = composeQuery.data?.run ?? null;
  const recipients: readonly Recipient[] = composeQuery.data?.recipients ?? [];
  const loadError = composeQuery.isError
    ? composeQuery.error instanceof ApiRequestError
      ? composeQuery.error.message
      : "The shortlist could not be read, and the server gave no reason. Nothing was composed."
    : null;
  const loading = composeQuery.isPending;

  const [selected, setSelected] = useState<readonly string[]>([]);
  const [eventName, setEventName] = useState("");
  const [eventDate, setEventDate] = useState("");
  const [coordinatorName, setCoordinatorName] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [composed, setComposed] = useState<SpeakerInvitationBatch | null>(null);


  const verdicts = useMemo(
    () => new Map(recipients.map((recipient) => [recipient.subjectId, judgeConsent(recipient)])),
    [recipients],
  );

  const selectableCount = useMemo(
    () => recipients.filter((recipient) => verdicts.get(recipient.subjectId)?.selectable).length,
    [recipients, verdicts],
  );

  // Why the button is disabled, in the words the server would use. A courtesy
  // and not a validation — every rule here is enforced server-side too.
  const blockingReason = useMemo(() => {
    if (unitId === null) {
      return "The server has not assigned this account a unit to compose invitations under.";
    }
    if (matchRunId === null) {
      return "Open a shortlist first. This page composes from a run the server recorded.";
    }
    if (selected.length === 0) {
      return "Choose at least one person the server says may be written to.";
    }
    if (eventName.trim() === "" || eventDate.trim() === "" || coordinatorName.trim() === "") {
      return "The event name, the date as it should read, and how you sign the message are all required.";
    }
    return null;
  }, [unitId, matchRunId, selected, eventName, eventDate, coordinatorName]);

  function toggleRecipient(subjectId: string) {
    setSelected((previous) =>
      previous.includes(subjectId)
        ? previous.filter((entry) => entry !== subjectId)
        : [...previous, subjectId],
    );
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (unitId === null || matchRunId === null || blockingReason !== null || submitting) {
      return;
    }

    setSubmitting(true);
    setSubmitError(null);
    try {
      // The response, not the payload. Every outcome the panel shows is one the
      // server wrote — including the ones it declined to compose.
      const batch = await createSpeakerInvitationBatch(unitId, {
        professionalIds: [...selected],
        eventName,
        eventDate,
        coordinatorName,
        matchRunId,
      });
      setComposed(batch);
    } catch (cause) {
      setComposed(null);
      // The server's own refusal — a repeated id, an over-large list, a rate
      // limit. Not a message this page made up, and no selection is cleared.
      setSubmitError(
        cause instanceof ApiRequestError
          ? cause.message
          : "The batch could not be composed and the server gave no reason. Nothing was written.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  // `CoordinatorPortalLayout` already renders `PortalGate` when the server
  // granted no such portal, so reaching here without a grant means the mapping
  // is still resolving.
  if (grant === null) {
    return null;
  }

  return (
    <div className="space-y-8 p-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-foreground">Compose speaker invitations</h1>
        <p className="text-sm text-muted-foreground">
          The people on a recorded shortlist, each with what the server says about writing to them.
          Composing a batch writes invitations and submits nothing; dispatch and tracking live on
          the CBA contact page.
        </p>
      </header>

      {unitId === null ? (
        <p className="rounded-xl border border-border/70 p-4 text-sm text-muted-foreground">
          The server has not assigned this account a unit, so there is nothing to compose under.
        </p>
      ) : matchRunId === null ? (
        <p className="rounded-xl border border-border/70 p-4 text-sm text-muted-foreground">
          This page composes against a shortlist the server recorded, and none is open. Submit a run
          from{" "}
          <Link className="font-medium underline" to="/coordinator-portal/match-runs">
            Run a match
          </Link>
          , then follow the shortlist link it opens. There is no field here for a run identifier,
          because a run nobody can reach from a link is a run this page has no business composing
          against.
        </p>
      ) : (
        <>
          {loadError !== null ? (
            <p className="flex items-start gap-2 rounded-xl border border-destructive/40 p-4 text-sm text-destructive">
              <AlertCircle className="mt-1 h-4 w-4 shrink-0" aria-hidden="true" />
              {loadError}
            </p>
          ) : null}

          {loading ? (
            <p className="text-sm text-muted-foreground">Reading the shortlist and its consent…</p>
          ) : null}

          {run !== null ? (
            <>
              <section className="space-y-2 rounded-xl border border-border/70 p-4 text-sm">
                <p className="text-muted-foreground">
                  The shortlist from the run this link named, in the order the server returned it.
                  No ranking, ordering or figure on this page is computed in the browser.
                </p>
                <dl className="grid gap-2 sm:grid-cols-2">
                  <div>
                    <dt className="inline text-muted-foreground">Factor registry&nbsp;</dt>
                    <dd className="inline">{run.registry_version}</dd>
                  </div>
                  <div>
                    <dt className="inline text-muted-foreground">Shortlist size&nbsp;</dt>
                    <dd className="inline">{run.portfolio_size}</dd>
                  </div>
                </dl>
                {run.shortlist_available ? null : (
                  <p className="flex items-start gap-2 text-amber-700">
                    <AlertCircle className="mt-1 h-4 w-4 shrink-0" aria-hidden="true" />
                    {run.shortlist_unavailable_reason ??
                      "This run carries no shortlist and the server named no reason, so there is nobody to invite."}
                  </p>
                )}
              </section>

              <form onSubmit={handleSubmit} className="space-y-8">
                <section className="space-y-3">
                  <h2 className="text-lg font-semibold text-foreground">Who to invite</h2>
                  <p className="text-sm text-muted-foreground">
                    {selectableCount} of {recipients.length} may be written to. The rest are listed
                    with the server&rsquo;s reason rather than hidden, because the reason is what
                    tells you what to do next. Nobody on this list was typed in — every one of them
                    came from the run.
                  </p>
                  {recipients.length === 0 ? (
                    <p className="rounded-xl border border-border/70 p-4 text-sm text-muted-foreground">
                      This run&rsquo;s shortlist is empty, so there is nobody to invite.
                    </p>
                  ) : (
                    // The shortlist is drawn a page at a time over the
                    // recipients this run already handed us — a window on what
                    // arrived, not a fresh read, and not a count of the run.
                    // Who is ticked stays in `selected`, so paging cannot
                    // unpick anybody.
                    <PagedList
                      items={recipients}
                      label="recipients"
                      idPrefix="invitation-recipients"
                    >
                      {(visibleRecipients) => (
                        <ul className="space-y-3">
                          {visibleRecipients.map((recipient) => {
                            const verdict = verdicts.get(recipient.subjectId);
                            if (verdict === undefined) return null;
                            return (
                              <RecipientRow
                                key={recipient.subjectId}
                                recipient={recipient}
                                verdict={verdict}
                                selected={selected.includes(recipient.subjectId)}
                                onToggle={toggleRecipient}
                              />
                            );
                          })}
                        </ul>
                      )}
                    </PagedList>
                  )}
                </section>

                <section className="space-y-3">
                  <h2 className="text-lg font-semibold text-foreground">What the message says</h2>
                  <p className="text-sm text-muted-foreground">
                    The wording itself is the server&rsquo;s closed template registry, and there is
                    no body, address or link field here for that reason. These three are what the
                    template leaves to you.
                  </p>
                  <div className="space-y-1">
                    <label htmlFor="event-name" className="text-sm font-medium text-foreground">
                      Event name
                    </label>
                    <input
                      id="event-name"
                      type="text"
                      value={eventName}
                      onChange={(event) => setEventName(event.target.value)}
                      className="w-full rounded-lg border border-border/70 bg-background px-3 py-2 text-sm"
                    />
                  </div>
                  <div className="space-y-1">
                    <label htmlFor="event-date" className="text-sm font-medium text-foreground">
                      Date, as it should read in the message
                    </label>
                    <input
                      id="event-date"
                      type="text"
                      value={eventDate}
                      onChange={(event) => setEventDate(event.target.value)}
                      className="w-full rounded-lg border border-border/70 bg-background px-3 py-2 text-sm"
                    />
                    <p className="text-xs text-muted-foreground">
                      Stored and rendered exactly as written. The server does not parse it, and
                      neither does this page — parsing it would mean guessing a timezone for it.
                    </p>
                  </div>
                  <div className="space-y-1">
                    <label
                      htmlFor="coordinator-name"
                      className="text-sm font-medium text-foreground"
                    >
                      How you sign the message
                    </label>
                    <input
                      id="coordinator-name"
                      type="text"
                      value={coordinatorName}
                      onChange={(event) => setCoordinatorName(event.target.value)}
                      className="w-full rounded-lg border border-border/70 bg-background px-3 py-2 text-sm"
                    />
                    <p className="text-xs text-muted-foreground">
                      A display name, not an identity. Who submitted the batch is the authenticated
                      caller, and the server records that separately.
                    </p>
                  </div>
                </section>

                <div className="space-y-2">
                  <button
                    type="submit"
                    disabled={submitting || blockingReason !== null}
                    className="min-h-11 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  >
                    {submitting ? "Composing…" : "Compose invitations"}
                  </button>
                  {blockingReason !== null ? (
                    <p className="text-xs text-muted-foreground">{blockingReason}</p>
                  ) : (
                    <p className="flex items-center gap-2 text-xs text-muted-foreground">
                      <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                      {selected.length} invitations will be composed. Nothing is delivered by this
                      button.
                    </p>
                  )}
                  {submitError !== null ? (
                    <p className="flex items-start gap-2 rounded-lg border border-destructive/40 p-3 text-sm text-destructive">
                      <AlertCircle className="mt-1 h-4 w-4 shrink-0" aria-hidden="true" />
                      {submitError}
                    </p>
                  ) : null}
                </div>
              </form>
            </>
          ) : null}

          {composed !== null ? <ComposedBatchPanel batch={composed} /> : null}
        </>
      )}
    </div>
  );
}
