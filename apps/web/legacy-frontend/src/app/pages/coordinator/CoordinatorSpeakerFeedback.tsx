/**
 * Speaker feedback — coordinator portal, aggregate only (OQ-CBA-003 part 1).
 *
 * Customer §16 asks that Speaker Connectors and admins be able to view student
 * feedback. OQ-CBA-003 settles *how*: an aggregate, never a transcript. This
 * page is the browser end of that decision, and it is worth being explicit
 * about what protects it, because it is not this file.
 *
 * The server holds the guarantee structurally. Its aggregate response has no
 * field a student could be assigned to; the repository read behind it selects
 * one column and returns a list of integers; and there is deliberately no route
 * that lists individual ratings to a Connector, with or without names. Thirty
 * rows carrying timestamps and free text re-identify their authors whether or
 * not a column says so, which is why the route a reader might expect does not
 * exist.
 *
 * What this page adds is the discipline of not going looking. It calls exactly
 * one feedback read — the aggregate — and never the student list route, which
 * would be refused anyway but whose presence here would say a Connector surface
 * is entitled to individual rows.
 *
 * ## Suppression is the server's answer, and arithmetic is not a way around it
 *
 * Below the threshold both numbers come back null *and* the count is withheld
 * with them, because "two students rated this speaker" narrows the field
 * considerably on its own. So this page computes nothing: no mean, no total, no
 * rounding. Every number on screen is one the server chose to send, and where
 * it declined, `display_text` is rendered instead — a sentence, so a reader can
 * tell "we are not telling you" from "the answer is nothing".
 *
 * The threshold itself travels in `minimum_responses` rather than being written
 * down here. It is a decided value that can move, and a page carrying its own
 * copy would keep explaining the old one after it did.
 *
 * A missing mean is rendered as absent, never as zero (ADR-0011 rule 1). A
 * speaker nobody rated must not read as a speaker rated badly.
 *
 * ## OQ-CBA-053 — these ratings are not a matching input
 *
 * No factor reads this table and nothing derived from it enters a score. The
 * way a frontend breaks that is not by computing anything: it is by placing a
 * number beside a roster and letting a reader draw the obvious wrong
 * conclusion. A Connector who believed these ratings fed matching would manage
 * the roster accordingly. So the page says otherwise, in a sentence, where the
 * numbers are.
 *
 * ## Not authorization
 *
 * The route is `admin`/`coordinator`, decided per request against the loaded
 * unit. This page renders its controls and shows the server's `403` as the
 * answer it is, rather than hiding them and implying the capability is absent.
 *
 * ## Why this page fans out, and why it is bounded
 *
 * This page reads one aggregate per speaker, and a reader who has seen
 * `CoordinatorHome.tsx` will reasonably ask why it does not call
 * `GET /v1/units/{unit_id}/speaker-feedback-summary` once instead. That route
 * exists, but it is not a bulk form of this one: it returns a *single pooled
 * mean and count for the whole unit* — `unit_id`, `suppressed`,
 * `response_count`, `mean_rating`, `display_text`, `minimum_responses` — and
 * carries no speaker id, no per-speaker breakdown and not even a count of how
 * many speakers were rated.
 *
 * That absence is the privacy rule, not an oversight. The server's own
 * docstring refuses a `speakers: [...]` list explicitly: the per-speaker route
 * is public to the same reader, so any extra number on the pooled response is
 * a handle to *difference* against. With one speaker published at `n=3` and
 * the unit at `n=5`, `5 - 3 = 2` recovers a mean over two students — the exact
 * statement `minimum_responses` exists to withhold. So the unit route is one
 * number for the dashboard, and a per-speaker roster genuinely cannot be
 * served by a single call. Adding a bulk per-speaker route would re-open the
 * residual leak that rule closes, which is why this page does not ask for one.
 *
 * What *was* wrong here was the fan-out being unbounded. `Promise.all` over the
 * whole roster opened one request per speaker at once — ~116 on the pilot unit
 * — and each one holds a connection from a pool of 5 + 5 overflow for the
 * length of its auth dependency alone, so the roster exhausted the pool,
 * queued for `pool_timeout`, and failed with `QueuePool limit of size 5
 * overflow 5 reached`. The page did not load slowly; it hung and refused to
 * navigate. `mapWithConcurrency` keeps the same reads and the same per-speaker
 * error handling, with at most `DEFAULT_READ_CONCURRENCY` in flight.
 */

import { Info, Users } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import {
  ApiRequestError,
  fetchSpeakerContacts,
  fetchSpeakerFeedbackSummary,
  type SpeakerContact,
  type SpeakerFeedbackSummary,
} from "../../../lib/api";
import { DEFAULT_READ_CONCURRENCY, mapWithConcurrency } from "../../../lib/concurrency";
import { scopedQueryKey } from "../../../lib/queryClient";
import { PagedList } from "../../components/PagedList";
import { grantedPortal } from "../../components/PortalGate";
import { usePrincipalKey } from "../../components/PrincipalQueryProvider";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";
import { useScopedQuery } from "../../hooks/useScopedQuery";

/** One roster speaker beside whatever the server was willing to publish. */
type RosterRow = {
  contact: SpeakerContact;
  summary: SpeakerFeedbackSummary | null;
  error: string | null;
};

/**
 * What a Connector is told about one speaker.
 *
 * Four fields, all of them the server's. Nothing on this card is derived, and
 * the two numbers appear only when `suppressed` is false — which is the
 * server's decision, read rather than re-made.
 */
function SpeakerSummaryCard({ row }: { row: RosterRow }) {
  const { contact, summary, error } = row;
  const place = [contact.company, contact.title].filter(Boolean).join(" · ");

  return (
    <li className="rounded-xl border border-border/70 p-4">
      <div className="space-y-1">
        <h3 className="font-semibold text-foreground">{contact.full_name}</h3>
        {place.length === 0 ? null : <p className="text-xs text-muted-foreground">{place}</p>}
      </div>

      {error !== null ? (
        <p
          role="alert"
          className="mt-3 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-xs text-foreground"
        >
          {error}
        </p>
      ) : summary === null ? (
        <p className="mt-3 text-xs text-muted-foreground">Loading…</p>
      ) : (
        <div className="mt-3 space-y-2">
          {/*
            The server's own sentence, rendered whether or not it suppressed
            anything. It is the one field guaranteed to say something true about
            the state of the data, and a dash in its place would lose the
            distinction it exists to draw.
          */}
          <p className="text-sm text-foreground">{summary.display_text}</p>

          {summary.suppressed ? (
            <p className="flex items-start gap-2 text-xs leading-5 text-muted-foreground">
              <Info className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
              <span>
                Nothing is published until at least {summary.minimum_responses} students have
                answered. Below that, both the rating and the number of responses are withheld
                together — a count on its own would narrow the field almost as much as a name.
              </span>
            </p>
          ) : (
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-xs text-muted-foreground">Mean rating, out of 5</dt>
                {/*
                  Rendered only where the server sent one. Never coerced: null is
                  an absence of evidence, and a speaker nobody rated must not
                  read as a speaker rated zero (ADR-0011 rule 1).
                */}
                <dd className="text-foreground">
                  {summary.mean_rating === null ? "Not published" : summary.mean_rating}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Responses counted</dt>
                <dd className="text-foreground">
                  {summary.response_count === null ? "Not published" : summary.response_count}
                </dd>
              </div>
            </dl>
          )}
        </div>
      )}
    </li>
  );
}

export function CoordinatorSpeakerFeedback() {
  // `GET /v1/me` — the only source of who this is. It throws rather than
  // substituting a fixture principal, which is the Fix #7 guard.
  const principal = useAuthenticatedPrincipal();
  // `GET /v1/me/portals` — the only source of the unit id this page reads.
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "coordinator");
  const unitId = grant?.default_unit_id ?? null;

  const queryClient = useQueryClient();
  const principalKey = usePrincipalKey();

  // The whole page is one cached read: the roster (shared with the
  // `speaker-contacts` slot, so the Speakers page and the sidebar prefetch
  // warm it) plus the bounded per-speaker fan-out. The fan-out stays inside
  // one `queryFn` deliberately — `useQueries` would fire every speaker's read
  // at once and re-open the pool exhaustion `mapWithConcurrency` was added to
  // close (see "Why this page fans out, and why it is bounded" above).
  //
  // Each per-speaker read may still fail on its own — a speaker whose summary
  // the server refused is reported on that speaker's card rather than
  // replacing the whole roster with a banner. The `catch` inside the worker
  // turns a rejection into a value, so one refused speaker never discards the
  // summaries that did come back.
  const rosterQuery = useScopedQuery({
    resource: "speaker-feedback-roster",
    params: [unitId],
    enabled: unitId !== null && principalKey !== null,
    queryFn: async (): Promise<RosterRow[]> => {
      const id = unitId as string;
      const roster = await queryClient.fetchQuery({
        queryKey: scopedQueryKey(principalKey as string, "speaker-contacts", id),
        queryFn: () => fetchSpeakerContacts(id),
      });
      return mapWithConcurrency(
        roster.contacts,
        DEFAULT_READ_CONCURRENCY,
        async (contact): Promise<RosterRow> => {
          try {
            const summary = await fetchSpeakerFeedbackSummary(id, contact.professional_id);
            return { contact, summary, error: null };
          } catch (cause) {
            return {
              contact,
              summary: null,
              error:
                cause instanceof ApiRequestError
                  ? cause.message
                  : "This summary could not be read and the server gave no reason.",
            };
          }
        },
      );
    },
  });

  const rows: RosterRow[] = rosterQuery.isSuccess ? rosterQuery.data : [];
  const loadError = rosterQuery.isError
    ? rosterQuery.error instanceof ApiRequestError
      ? rosterQuery.error.message
      : "The roster could not be loaded and the server gave no reason."
    : null;
  const loaded = !rosterQuery.isPending;

  // `CoordinatorPortalLayout` already renders `PortalGate` when the server
  // granted no such portal, so reaching here without a grant means the mapping
  // is still resolving.
  if (grant === null) {
    return null;
  }

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-foreground">Speaker feedback</h1>
        <p className="text-sm text-muted-foreground">
          How students rated the speakers on your roster, in aggregate.
        </p>
        <p className="text-xs text-muted-foreground">
          Signed in as {principal.email} · {grant.role} · {grant.org_unit_path}
        </p>
      </header>

      <div className="space-y-2 rounded-xl border border-border/70 p-4 text-sm leading-6 text-muted-foreground">
        <p className="flex items-start gap-2">
          <Users className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            You see a mean rating and a response count, and nothing else. Which student said what
            is not available on this surface, and there is no route that would return it — a
            handful of dated entries identifies its authors in a class of thirty whether or not
            anybody is named.
          </span>
        </p>
        {/*
          OQ-CBA-053, said out loud rather than left to inference. A number beside
          a roster reads as an input to matching unless a reader is told it is
          not, and a Connector who believed that would manage the roster on it.
        */}
        <p>
          Student feedback <strong>does not feed matching</strong>. It records how an event went;
          no part of it is read when candidates are ranked, and changing a rating changes nothing
          about who is put forward.
        </p>
      </div>

      {loadError === null ? null : (
        <p
          role="alert"
          className="rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-foreground"
        >
          {loadError}
        </p>
      )}

      {unitId === null ? (
        <p className="rounded-xl border border-border/70 p-4 text-sm text-muted-foreground">
          The server has not assigned this account a unit, so there is no roster to summarise.
        </p>
      ) : rows.length === 0 ? (
        <p className="rounded-xl border border-border/70 p-4 text-sm text-muted-foreground">
          {!loaded
            ? "Loading…"
            : "This unit has no speaker contacts yet, so there is nothing to summarise."}
        </p>
      ) : (
        // The summaries are windowed client-side over the rows this browser
        // already holds. Turning a page draws fewer cards; it asks the server
        // for nothing and makes no claim about how many speakers the unit has.
        // The prefix deliberately avoids the substring `speaker-feedback`:
        // that is the tail of the per-student route this surface must never
        // reach, and `test_frontend_student_feedback_contract.py` forbids the
        // token outright rather than trying to tell a route from an element id.
        <PagedList items={rows} label="speaker summaries" idPrefix="unit-speaker-summaries">
          {(visibleRows) => (
            <ul className="space-y-3">
              {visibleRows.map((row) => (
                <SpeakerSummaryCard key={row.contact.professional_id} row={row} />
              ))}
            </ul>
          )}
        </PagedList>
      )}
    </div>
  );
}
