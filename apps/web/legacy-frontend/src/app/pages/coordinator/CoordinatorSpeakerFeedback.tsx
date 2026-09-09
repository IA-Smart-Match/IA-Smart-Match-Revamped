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
 */

import { useCallback, useEffect, useState } from "react";
import { Info, Users } from "lucide-react";

import {
  ApiRequestError,
  fetchSpeakerContacts,
  fetchSpeakerFeedbackSummary,
  type SpeakerContact,
  type SpeakerFeedbackSummary,
} from "../../../lib/api";
import { PagedList } from "../../components/PagedList";
import { grantedPortal } from "../../components/PortalGate";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";

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

  const [rows, setRows] = useState<RosterRow[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    if (unitId === null) return;
    try {
      const roster = await fetchSpeakerContacts(unitId);
      setLoadError(null);

      // One aggregate read per speaker. Each may fail on its own — a speaker
      // whose summary the server refused is reported on that speaker's card
      // rather than replacing the whole roster with a banner.
      const resolved = await Promise.all(
        roster.contacts.map(async (contact) => {
          try {
            const summary = await fetchSpeakerFeedbackSummary(unitId, contact.professional_id);
            return { contact, summary, error: null as string | null };
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
        }),
      );
      setRows(resolved);
    } catch (cause) {
      setLoadError(
        cause instanceof ApiRequestError
          ? cause.message
          : "The roster could not be loaded and the server gave no reason.",
      );
    } finally {
      setLoaded(true);
    }
  }, [unitId]);

  useEffect(() => {
    void load();
  }, [load]);

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
        <PagedList items={rows} label="speaker summaries" idPrefix="speaker-feedback-summaries">
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
