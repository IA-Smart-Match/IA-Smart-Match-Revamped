/**
 * Coordinator home — coordinator portal, and the Connector's pilot statistics.
 *
 * This page used to load your coordinator profile, hosted events and staffing,
 * outreach threads and meeting bookings from the legacy `/api/portals/*`
 * backend. That backend is not part of this repository, so each of the four was
 * a `PortalDatasetUnavailable` panel naming the dataset and the route that
 * would have served it, rather than a red failure banner blaming an outage for
 * a capability that was never present.
 *
 * Three of those four have had a `/v1` answer all along and were simply
 * unwired, and the panels above them were therefore saying something false
 * about *this* deployment while saying something true about the legacy one:
 *
 *  - **your coordinator profile** is `GET /v1/me` and `GET /v1/me/portals`,
 *    which this page already called for its own scoping. `PortalIdentityCard`
 *    at the top of the page is that profile — who the server says you are, the
 *    role that granted your portal, the org unit it covers, and the units that
 *    grant reaches. There was never anything to fetch that was not already
 *    fetched;
 *  - **hosted events** is `GET /v1/units/{unit_id}/events`
 *    (`routers/events.py`), which no portal page was calling.
 *    `CoordinatorEvents.tsx` is the page for it; the panel below summarises
 *    only what that response says about its own completeness and links there;
 *  - **outreach** is `GET /v1/units/{unit_id}/outreach/drafts` and
 *    `.../outreach/sends`. Both are read here against the *granted* unit,
 *    which is now the only unit any outreach surface reads — `useOutreach`
 *    takes it as an argument rather than looking up the build variable, so the
 *    divergence this note used to warn about is closed at its source.
 *
 * Two labels did not survive being wired up, and that is the point rather than
 * a casualty of it.
 *
 * The old panel said "hosted events **and staffing**". The `/v1` listing
 * carries no staffing of any kind, so the label went rather than being kept
 * over a response that does not answer it — see `CoordinatorEvents.tsx`.
 *
 * The old panel said "outreach **threads**". `/v1` outreach stores drafts and
 * sends — a composed message and one attempt to deliver it — and there is no
 * inbound leg in this API for a thread to be made of (OQ-008). The section
 * below says drafts and sends in its heading, its copy and its labels.
 * Renaming a surface to match the old word would be the fabricated-equivalence
 * defect these placeholders exist to prevent: a reader told they are looking at
 * threads goes looking for replies that are not withheld but absent.
 *
 * **Meeting bookings** was the fourth, and kept its panel while that was true.
 * It no longer is: `GET`/`POST /v1/units/{unit_id}/meetings` (migration
 * `0034`) are live and `CoordinatorMeetings` reads and writes them. The panel
 * came down with the others — see the addendum below — and this page now
 * renders no unavailable panel at all.
 *
 * What *is* real on this page comes from `/v1` routes and nothing else:
 * `GET /v1/me` for who the caller is, `GET /v1/me/portals` for the portal the
 * server granted them and the role and unit behind it, and the six unit-scoped
 * reads below. Neither identity route is derived in the browser, and no
 * identifier on this page is chosen by it.
 *
 * ## Why the statistics are here and not on `Dashboard.tsx` (TRACK 14)
 *
 * `Dashboard.tsx` already renders the same register, and it was the obvious
 * place to add to. It is the wrong one for a Connector, for two reasons that
 * are about correctness rather than layout.
 *
 * The first is the unit. `Dashboard.tsx` scopes itself with
 * `getConfiguredUnitId()` — the `VITE_SMARTMATCH_UNIT_ID` build variable, one
 * value baked into the bundle for every reader of it. A Connector's unit is
 * whatever `GET /v1/me/portals` granted *this account*, and on a multi-unit
 * pilot the two are different units; a page that showed the build variable's
 * numbers under a Connector's name would be attributing one unit's work to
 * another. This page already holds the granted unit, because its identity card
 * is built from it.
 *
 * The second is who arrives. `Dashboard.tsx` sat behind a second, admin-only
 * shell that a Connector clicking through the pilot never reached, and
 * statistics nobody in the audience can see are not statistics.
 *
 * Both shells are now one. `admin` and `coordinator` are the same persona, so
 * `Layout.tsx` and `Dashboard.tsx` are retired and `/dashboard` redirects
 * here. This page is the Connector home screen for both stored roles, and it
 * is still scoped by the *granted* unit rather than a build variable — which
 * is why the retirement was a redirect to this page rather than the reverse.
 *
 * ## Every number here has one owning server query (ADR-0011)
 *
 * Two reads count server-side:
 * `GET /v1/units/{unit_id}/metrics?surface=cba` for the registered metrics —
 * the review queue's size, Speaker Requests, and the four funnel counts as the
 * CBA product labels them — and
 * `GET /v1/units/{unit_id}/engagement/attendance-summary` for how much
 * attendance evidence the unit holds.
 *
 * The event listing added below contributes two more server-owned figures and
 * no computed one: `withheld_unresolved_date` and `withheld_quarantined_tags`
 * are counted by the same query the listing is partitioned out of. The count
 * this page pointedly does **not** show is a count of the events themselves —
 * `events.length` is arithmetic the browser did, and it would sit among figures
 * whose whole claim is that a server query owns each of them.
 *
 * Nothing on this page is folded, averaged, totalled or rounded. That is not
 * fastidiousness: a browser-side total is a second calculation of a published
 * number, it looks exactly as authoritative as the measured one, and it can be
 * drilled into by nothing. Where a response carries a total, it is the server's
 * own — `AttendanceSummaryResponse.total` is documented as the fold of
 * `by_method`, computed from the same query that produced the parts.
 *
 * A `null` metric value is rendered as unknown *with the server's reason*, and
 * never as `0`. A measured `0` is rendered as `0`, because the query ran and
 * found none — a different claim, and the one ADR-0011 rule 1 exists to keep
 * apart from the first.
 *
 * ## Student feedback: a pooled aggregate, addendum 7 September 2026
 *
 * `GET /v1/units/{unit_id}/speaker-feedback-summary` is a second Connector
 * feedback read, added under OQ-CBA-003's decision rather than widening it:
 * one mean and one count over the whole unit's submitted ratings, suppressed
 * below `minimum_responses` exactly like the per-speaker route. It is **not**
 * a sum of the per-speaker aggregates computed here — a suppressed per-speaker
 * summary contributes `null`, so a client-side fold would either undercount
 * or republish what suppression withheld. It is one server query with its own
 * rule.
 *
 * That rule is stricter than "the pool clears the threshold". The per-speaker
 * route is public to the same reader, so a pooled count can be *differenced*
 * against an already-published speaker's count to isolate a smaller,
 * still-suppressed group. The server therefore also suppresses the unit
 * aggregate when that differencing would work — a unit with many responses
 * can still read `suppressed`, and that is the rule holding, not a bug. This
 * page renders three states this suppression makes distinguishable, and only
 * from server fields: **published** (`suppressed: false`, both numbers
 * present), **suppressed with a reason** (`suppressed: true`, the server's own
 * `display_text`, both numbers `null`), and **unavailable** (the read itself
 * failed or has not settled — a `403`, a network error, or still loading). A
 * suppressed aggregate is not an error and not a zero, and none of the three
 * states may be rendered as either of the other two.
 *
 * Nothing about *why* a group is small is composed here, and no per-speaker
 * number is read to explain it — the response carries none, on purpose.
 *
 * The per-speaker summary is still the only route that names one speaker's
 * ratings, so this page keeps its link to
 * `CoordinatorSpeakerFeedback.tsx`.
 *

 * ## Two gaps that closed, addendum 10 September 2026
 *
 * This header used to say the review queue was "the same shape of gap in the
 * opposite direction" — size measurable, items unlistable — and a panel at the
 * foot of the page said so at length, naming `GET /v1/review-items` as a
 * deferred follow-up. That route landed:
 * `GET /v1/units/{unit_id}/review-items` (`routers/review.py`) has existed
 * since before this page was last read, and `CoordinatorReviewQueue` has been
 * rendering it at `/coordinator-portal/review-queue` the whole time —
 * reachable by URL and linked from nowhere. The page was telling a Connector
 * that a working page did not exist.
 *
 * `Meeting bookings` was the second. It carried a `PortalDatasetUnavailable`
 * panel naming the retired `/api/portals/event-coordinators/{id}/meetings`
 * feed, while `GET`/`POST /v1/units/{unit_id}/meetings` (migration `0034`)
 * were live and `CoordinatorMeetings` was already reading and writing them.
 *
 * An unavailable panel is a claim, and it has to come down when it stops
 * being true — the same fabricated-equivalence defect those panels exist to
 * prevent, pointed the other way. Both are gone. The action queue at the top
 * counts the pending review items from the real route and links straight to
 * them; the count and the queue derive a row's owning unit through the same
 * join, which is why the badge and the page cannot disagree.
 *
 * ## Order: what to do, then what is coming, then what happened
 *
 * `DESIGN.md` puts the action queue before summary statistics on a Speaker
 * Connector home page, and this page now reads in that order — the queue, then
 * this week's events, then the measured aggregates. A reader arriving at work
 * wants the four things waiting for them, not six metric cards about last
 * month; the metrics are why the work matters and they keep their place, at
 * the bottom.
 *
 * ## Not authorization
 *
 * Both reads are decided server-side per request against the loaded unit. This
 * page renders its sections and shows the server's `403` as the answer it is,
 * rather than hiding them and implying the capability is absent.
 */

import { Link } from "react-router";
import {
  BarChart3,
  CalendarDays,
  ClipboardCheck,
  Inbox,
  Info,
  Mail,
  MessageSquareHeart,
  Send,
  Target,
} from "lucide-react";

import {
  ApiRequestError,
  fetchAttendanceSummary,
  fetchOutreachDrafts,
  fetchOutreachSends,
  fetchReviewItems,
  fetchSpeakerInvitationBatches,
  fetchSpeakerRequests,
  fetchUnitEvents,
  fetchUnitSpeakerFeedbackSummary,
  type AttendanceSummary,
  type OutreachDraft,
  type OutreachSendSummary,
  type ReviewItemListResponse,
  type SpeakerInvitationBatchListResponse,
  type SpeakerRequestList,
  type UnitEventList,
  type UnitEventSummary,
  type UnitFeedbackSummary,
} from "../../../lib/api";
import { PortalIdentityCard } from "../../components/PortalContent";
import { SpeakerPipelineSection } from "../../components/speakerPipeline/SpeakerPipelineSection";
import { Tooltip, TooltipContent, TooltipTrigger } from "../../components/ui/tooltip";
import { grantedPortal } from "../../components/PortalGate";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";
import {
  queryToLoaded,
  useScopedQuery,
  type Loaded,
} from "../../hooks/useScopedQuery";

/**
 * What one read returned, or why it returned nothing.
 *
 * The failure is kept beside the data rather than in a page-level banner
 * because the two reads fail independently: a Connector refused the attendance
 * summary can still be entitled to the register, and replacing both with one
 * message would misreport which capability the server withheld.
 */
// `Loaded`, `PENDING` and `describeFailure` now live in
// `../../hooks/useScopedQuery` — the shape is unchanged, only shared.

/**
 * How much attendance evidence the unit holds, by mechanism.
 *
 * `total` is rendered from the field, not from the three method counts beside
 * it. The response documents that total as its own server-side fold of exactly
 * those counts; adding them here would be a second calculation of a published
 * number, and the two would disagree the first time a mechanism is added.
 *
 * `distinct_subjects` is a count of accounts and nothing more. There is no
 * route that lists them while D8 is open, and this section offers no control
 * that would suggest otherwise.
 */
function AttendanceEvidence({ state }: { state: Loaded<AttendanceSummary> }) {
  const summary = state.data;

  return (
    <section className="rounded-2xl border border-border p-6" aria-label="Attendance evidence">
      <h2 className="font-semibold text-foreground">Recorded attendance</h2>
      <p className="mt-1 text-sm leading-6 text-muted-foreground">
        Counted from the attendance rows this unit owns. A zero here is measured — the query ran
        and found none — rather than a gap in what was asked.
      </p>

      {state.error !== null ? (
        <p
          role="alert"
          className="mt-4 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-foreground"
        >
          {state.error}
        </p>
      ) : summary === null ? (
        <p className="mt-4 text-sm text-muted-foreground">
          {state.settled ? "No summary was returned." : "Loading…"}
        </p>
      ) : (
        <>
          <dl className="mt-4 grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl border border-border/70 p-4">
              <dt className="text-xs uppercase tracking-wide text-muted-foreground">
                Attendance rows
              </dt>
              <dd className="mt-1 text-2xl font-semibold tabular-nums text-foreground">
                {summary.total}
              </dd>
            </div>
            <div className="rounded-xl border border-border/70 p-4">
              <dt className="text-xs uppercase tracking-wide text-muted-foreground">
                Events attested
              </dt>
              <dd className="mt-1 text-2xl font-semibold tabular-nums text-foreground">
                {summary.distinct_events}
              </dd>
            </div>
            <div className="rounded-xl border border-border/70 p-4">
              <dt className="text-xs uppercase tracking-wide text-muted-foreground">
                Accounts attested
              </dt>
              <dd className="mt-1 text-2xl font-semibold tabular-nums text-foreground">
                {summary.distinct_subjects}
              </dd>
            </div>
          </dl>

          <dl className="mt-3 grid gap-3 sm:grid-cols-3">
            {/*
              Iterating the map the server sent, rather than naming the three
              mechanisms here. `ck_attendance_record_method` is the register of
              them and it can gain one; a page listing its own copy would go on
              showing three after it did.
            */}
            {Object.entries(summary.by_method).map(([method, count]) => (
              <div key={method} className="rounded-xl border border-border/70 p-3">
                <dt className="text-xs text-muted-foreground">Recorded by {method}</dt>
                <dd className="text-sm tabular-nums text-foreground">{count}</dd>
              </div>
            ))}
          </dl>

          <p className="mt-3 text-xs leading-5 text-muted-foreground">
            {summary.first_recorded_at === null || summary.last_recorded_at === null
              ? "Nothing has been recorded yet, so there is no first or last entry to date."
              : `Recorded between ${new Date(summary.first_recorded_at).toLocaleString()} and ${new Date(
                  summary.last_recorded_at,
                ).toLocaleString()}.`}
          </p>
        </>
      )}
    </section>
  );
}

/**
 * Student feedback, pooled across the unit — three states, and only one of
 * them is a number.
 *
 * Customer §16 asks that a Connector be able to view student feedback. The
 * per-speaker read (linked below) answers it one speaker at a time; this
 * section answers it for the whole unit, from
 * `GET /v1/units/{unit_id}/speaker-feedback-summary` and that route alone.
 * Nothing here is folded from the per-speaker summaries — see the module
 * docstring's "Student feedback: a pooled aggregate" section for why that
 * would republish what suppression withheld.
 *
 * The three states below are the server's `suppressed` flag plus whether the
 * read itself settled, and they render as three visibly different things: a
 * measured mean and count; a named withholding with the server's own
 * sentence and no numbers; or "not read yet / refused", which is a statement
 * about this request, not about the unit's ratings. ADR-0011 rule 1 holds
 * here as everywhere else on this page — a suppressed or unread aggregate is
 * never printed as `0` or as a bare dash with no explanation.
 *
 * OQ-CBA-053 is stated here rather than left to the reader. This section sits
 * directly beneath a funnel of matching counts, and a rating placed near
 * "speakers matched" reads as an input to it unless the page says otherwise.
 */
function StudentFeedbackPointer({ state }: { state: Loaded<UnitFeedbackSummary> }) {
  const summary = state.data;

  return (
    <section
      className="rounded-2xl border border-border p-6"
      aria-label="Student speaker feedback"
    >
      <div className="flex items-start gap-2">
        <MessageSquareHeart
          className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground"
          aria-hidden="true"
        />
        <div className="w-full space-y-2">
          <h2 className="font-semibold text-foreground">Student feedback on your speakers</h2>
          <p className="text-sm leading-6 text-muted-foreground">
            Student feedback <strong>does not feed matching</strong>. It records how an event
            went; no part of it is read when candidates are ranked, and changing a rating changes
            nothing about who is put forward. It is shown here beside the funnel counts for that
            reason — so the two are not mistaken for one number.
          </p>

          {state.error !== null ? (
            <p
              role="alert"
              className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-foreground"
            >
              {state.error}
            </p>
          ) : summary === null ? (
            <p className="text-sm text-muted-foreground" role="status">
              {state.settled
                ? "The unit feedback summary was not returned."
                : "Loading the unit feedback summary…"}
            </p>
          ) : summary.suppressed ? (
            <div
              className="rounded-xl border border-border/70 bg-muted/30 p-4"
              role="status"
              aria-live="polite"
            >
              <p className="text-sm font-medium text-foreground">Withheld: {summary.display_text}</p>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                This is not zero and it is not an error — the server is withholding this figure
                because publishing it (alone, or alongside an already-published per-speaker
                summary) would let the ratings of a smaller, still-suppressed group of speakers be
                worked out by subtraction. Nothing is published below{" "}
                {summary.minimum_responses} responses either way.
              </p>
            </div>
          ) : (
            <dl className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-border/70 p-4">
                <dt className="text-xs uppercase tracking-wide text-muted-foreground">
                  Unit mean rating
                </dt>
                <dd className="mt-1 text-2xl font-semibold tabular-nums text-foreground">
                  {summary.mean_rating}
                </dd>
              </div>
              <div className="rounded-xl border border-border/70 p-4">
                <dt className="text-xs uppercase tracking-wide text-muted-foreground">
                  Responses counted
                </dt>
                <dd className="mt-1 text-2xl font-semibold tabular-nums text-foreground">
                  {summary.response_count}
                </dd>
              </div>
            </dl>
          )}

          <p className="text-sm leading-6 text-muted-foreground">
            This is a pooled figure over the whole unit, not a sum of individual speakers&apos;
            summaries. Each speaker&apos;s own summary is withheld until enough students have
            answered it specifically, with its threshold travelling in that response too.
          </p>
          <p className="text-sm leading-6">
            <Link
              className="font-medium text-foreground underline underline-offset-4"
              to="/coordinator-portal/speaker-feedback"
            >
              Read the per-speaker summaries
            </Link>
          </p>
        </div>
      </div>
    </section>
  );
}

/**
 * Hosted events, summarised — the panel, and the page it defers to.
 *
 * This section used to be a `PortalDatasetUnavailable` for "Hosted events and
 * staffing", which said something true about the legacy `/api/portals/*`
 * backend and something false about this deployment:
 * `GET /v1/units/{unit_id}/events` exists and no portal page was calling it.
 *
 * What it renders here is deliberately not the listing. `CoordinatorEvents.tsx`
 * is the page for that, and duplicating rows onto a statistics surface would
 * put two renderings of one response on two screens, to disagree the first time
 * one of them is changed. This panel carries only what the *response itself*
 * says about its own completeness — the two withheld counts and `truncated` —
 * and hands the reader the page.
 *
 * There is deliberately **no count of listed events here**. `events.length`
 * would be a figure this browser computed, sitting in a section whose whole
 * claim is that every number on it has one owning server query; the register
 * above is where a count of anything belongs, and it has no metric for this.
 *
 * The withheld counts are not decoration. Without them "no events" and "seven
 * events the pipeline could not finish" are the same silence, which is
 * ADR-0011's rule about zeros applied to an omission.
 *
 * Staffing is not summarised because the route carries none — see
 * `CoordinatorEvents.tsx`'s docstring. The old panel's label is gone rather
 * than kept over a response that does not answer it.
 */
function HostedEventsSummary({ state }: { state: Loaded<UnitEventList> }) {
  const listing = state.data;

  return (
    <section className="rounded-2xl border border-border p-6" aria-label="Hosted events">
      <div className="flex items-start gap-2">
        <CalendarDays
          className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground"
          aria-hidden="true"
        />
        <div className="w-full space-y-2">
          <h2 className="font-semibold text-foreground">Events your unit hosts</h2>
          <p className="text-sm leading-6 text-muted-foreground">
            The server lists this unit&apos;s presentable events. Two kinds are held back — an
            event with no resolved date, and one whose tag value is still awaiting human review —
            and the response counts both rather than dropping them quietly.
          </p>

          {state.error !== null ? (
            <p
              role="alert"
              className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-foreground"
            >
              {state.error}
            </p>
          ) : listing === null ? (
            <p className="text-sm text-muted-foreground" role="status">
              {state.settled ? "The listing returned nothing." : "Loading the event listing…"}
            </p>
          ) : (
            <>
              <dl className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl border border-border/70 p-3">
                  <dt className="text-xs text-muted-foreground">Not listed — no resolved date</dt>
                  <dd className="text-sm tabular-nums text-foreground">
                    {listing.withheld_unresolved_date}
                  </dd>
                </div>
                <div className="rounded-xl border border-border/70 p-3">
                  <dt className="text-xs text-muted-foreground">
                    Not listed — tag awaiting review
                  </dt>
                  <dd className="text-sm tabular-nums text-foreground">
                    {listing.withheld_quarantined_tags}
                  </dd>
                </div>
              </dl>
              {listing.truncated && (
                <p className="text-xs leading-5 text-muted-foreground">
                  This unit holds more presentable events than one response returns.
                </p>
              )}
            </>
          )}

          <p className="text-sm leading-6">
            <Link
              className="font-medium text-foreground underline underline-offset-4"
              to="/coordinator-portal/events"
            >
              Open my events
            </Link>
          </p>
        </div>
      </div>
    </section>
  );
}

/**
 * How one send attempt reads, from the server's own field and no further.
 *
 * Deliberately not shared with `CoordinatorOutreach.tsx`'s `describeDisposition`
 * and deliberately weaker than it. That page reads a single send with its whole
 * delivery stream beside it and can afford a sentence; this panel has a row in
 * a listing, and the listing carries no stream — the route omits it on purpose,
 * because folding a send's events into one word is a choice about which fact to
 * forget when a provider reports `delivered` and then `complained`.
 *
 * So this reports the server's value and stops. `null` is the third state and
 * reads as in flight — never as a failure, and never as the word this whole
 * surface refuses. **Nothing here says "sent" or "delivered".** B17's defect was
 * a button that announced a message had been sent having issued no request; a
 * dashboard that announced delivery from a disposition would be the same claim
 * one layer further from the evidence.
 */
function describeSendState(send: OutreachSendSummary): string {
  return send.disposition === null
    ? "In flight — the worker has not reported an outcome."
    : `The server reported "${send.disposition}".`;
}

/**
 * Outreach drafts and sends — and why this section is not called threads.
 *
 * This was a `PortalDatasetUnavailable` for "Outreach threads". The legacy
 * `/api/portals/event-coordinators/{id}/threads` really is gone, and what
 * replaced it is **not the same shape**: `/v1` outreach stores an
 * `outreach_draft` and an `outreach_send`, which are a composed message and one
 * attempt to deliver it. OQ-008 records that decision. Nothing in either
 * response implies a reply exists, no row belongs to an exchange, and there is
 * no inbound leg anywhere in this API.
 *
 * That is why the heading, the copy and the field labels below all say drafts
 * and sends. Rendering these rows under the old word would be the
 * fabricated-equivalence defect the unavailable panels exist to prevent: a
 * reader who saw "threads" would reasonably believe they were looking at
 * conversations, and would go looking for replies that are not withheld but
 * absent.
 *
 * Two reads, `GET /v1/units/{unit_id}/outreach/drafts` and
 * `.../outreach/sends`, both scoped to the unit the server *granted this
 * account* rather than to `VITE_SMARTMATCH_UNIT_ID`. This panel calls the
 * helpers directly because it composes them with the rest of the dashboard's
 * `Loaded<T>` reads, not because `useOutreach` would answer about a different
 * unit: that hook now takes the granted unit as an argument, and
 * `CoordinatorOutreach.tsx` passes it the same `default_unit_id` this page
 * uses.
 *
 * No count is rendered. Neither response carries a total — `limit` and `offset`
 * are what was asked for, not what exists — so a number here would be a count
 * of one page, computed in the browser, presented beside figures that each have
 * an owning query.
 */
function OutreachDraftsAndSends({
  drafts,
  sends,
}: {
  drafts: Loaded<OutreachDraft[]>;
  sends: Loaded<OutreachSendSummary[]>;
}) {
  return (
    <section className="rounded-2xl border border-border p-6" aria-label="Outreach drafts and sends">
      <div className="flex items-start gap-2">
        <Mail className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <div className="w-full space-y-3">
          <h2 className="font-semibold text-foreground">Outreach drafts and sends</h2>
          <p className="text-sm leading-6 text-muted-foreground">
            A draft is a message composed from a registered template; a send is one attempt to
            deliver one. They are not conversations — this API has no inbound leg, so nothing
            below implies anyone replied.
          </p>

          <div className="space-y-2">
            <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Drafts
            </h3>
            {drafts.error !== null ? (
              <p
                role="alert"
                className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-foreground"
              >
                {drafts.error}
              </p>
            ) : drafts.data === null ? (
              <p className="text-sm text-muted-foreground" role="status">
                {drafts.settled ? "The draft listing returned nothing." : "Loading drafts…"}
              </p>
            ) : drafts.data.length === 0 ? (
              // Safe to say here, and only here: the server answered, and its
              // answer was none. A failed read above says nothing at all about
              // how many drafts exist (ADR-0011).
              <p className="text-sm text-muted-foreground">No drafts in this unit.</p>
            ) : (
              <ul className="space-y-2">
                {drafts.data.map((draft) => (
                  <li key={draft.draft_id} className="rounded-xl border border-border/70 p-3">
                    <p className="text-sm font-medium text-foreground">{draft.subject}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      To {draft.recipient_address} · {draft.status}
                    </p>
                    {draft.content_status === "synthetic" && (
                      // Surfaced rather than hidden: this is the fact that
                      // decides whether the message could go to a real person.
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        Pilot copy — not through institutional review.
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="space-y-2">
            <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Sends
            </h3>
            {sends.error !== null ? (
              <p
                role="alert"
                className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-foreground"
              >
                {sends.error}
              </p>
            ) : sends.data === null ? (
              <p className="text-sm text-muted-foreground" role="status">
                {sends.settled ? "The send listing returned nothing." : "Loading sends…"}
              </p>
            ) : sends.data.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                This unit has attempted no sends.
              </p>
            ) : (
              <ul className="space-y-2">
                {sends.data.map((send) => (
                  <li key={send.send_id} className="rounded-xl border border-border/70 p-3">
                    <p className="text-sm font-medium text-foreground">{send.recipient_address}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {describeSendState(send)}
                    </p>
                    {send.failure_reason !== null && (
                      <p className="mt-0.5 text-xs text-muted-foreground">{send.failure_reason}</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
            <p className="text-xs leading-5 text-muted-foreground">
              The server decides how many rows one page carries, and the response reports no
              total — so this is a page of sends rather than all of them, and no number here
              claims otherwise.
            </p>
          </div>

          <p className="text-sm leading-6">
            <Link
              className="font-medium text-foreground underline underline-offset-4"
              to="/coordinator-portal/outreach"
            >
              Open CBA contact
            </Link>
          </p>
        </div>
      </div>
    </section>
  );
}

/**
 * The action queue: the four things waiting for a Connector, before anything
 * that merely describes the past.
 *
 * `DESIGN.md` puts the action queue ahead of summary statistics on this page,
 * and the reason is the shape of the job. A Speaker Connector arriving at work
 * needs to know what is unanswered — a host has filed a request, an import is
 * waiting on a decision — not what the mean attendance was. The metrics are
 * still here; they are last, which is where a figure you consult belongs
 * relative to a task you owe.
 *
 * ## Four rows, and three different kinds of honesty
 *
 * Each row links to the page that acts on it, and each says exactly what its
 * number is a number of:
 *
 *  - **Speaker requests** and **Items waiting for review** are counts of the
 *    rows the linked page will show, read from the same route that page reads.
 *    Badge and page cannot disagree.
 *  - **Invitation batches** is deliberately *not* labelled "open invitations".
 *    `GET .../speaker-invitations/batches` returns batch summaries, and a
 *    summary carries no per-invitation answer — accepted, declined, or
 *    unanswered are on the batch detail. Counting batches and calling them
 *    open invitations would be this page inventing a figure the response does
 *    not contain, so it counts what it has and names it.
 *  - **Match runs with a shortlist** has no count at all, because there is no
 *    route that lists match runs. `GET /v1/units/{u}/match-runs/{id}` fetches
 *    one by id; nothing enumerates them. The row stays — the work is real and
 *    reachable — and says why it carries no number instead of showing a zero.
 *    ADR-0011 rule 1: "we cannot ask" is never "there are none".
 *
 * A row whose read has not settled shows no number either, and a row whose
 * read failed shows the server's own refusal. Neither is drawn as a zero.
 *
 * Nothing here is computed. Every number is the length of a list the server
 * sent, and where a list arrived truncated the row says `N+` rather than
 * printing the server's cap as though it were a total.
 */
function ActionRow({
  icon: Icon,
  title,
  to,
  linkLabel,
  state,
  count,
  truncated,
  unavailable,
}: {
  icon: typeof Inbox;
  title: string;
  to: string;
  linkLabel: string;
  /** The read behind the count, for its error and settled facts. */
  state: { error: string | null; settled: boolean };
  /** The number of rows the linked page will show, or `null` when unknown. */
  count: number | null;
  truncated: boolean;
  /** Why this row can carry no number at all, when that is a property of the API. */
  unavailable?: string;
}) {
  return (
    <li className="flex min-h-[40px] flex-wrap items-baseline gap-x-3 gap-y-1 rounded-xl border border-border/70 p-4">
      <Icon className="h-4 w-4 shrink-0 self-center text-muted-foreground" aria-hidden="true" />
      <span className="font-medium text-foreground">{title}</span>

      {unavailable !== undefined ? (
        <span className="basis-full text-sm leading-6 text-muted-foreground">{unavailable}</span>
      ) : state.error !== null ? (
        <span className="basis-full text-sm leading-6 text-foreground" role="alert">
          {state.error}
        </span>
      ) : count === null ? (
        <span className="text-sm text-muted-foreground">
          {state.settled ? "The server returned no list." : "Loading…"}
        </span>
      ) : (
        <span className="text-sm tabular-nums text-foreground">
          {count}
          {truncated ? "+" : ""}
        </span>
      )}

      <Link
        className="ml-auto shrink-0 text-sm font-medium text-foreground underline underline-offset-4"
        to={to}
      >
        {linkLabel}
      </Link>
    </li>
  );
}

function ActionQueue({
  speakerRequests,
  reviewItems,
  invitationBatches,
}: {
  speakerRequests: Loaded<SpeakerRequestList>;
  reviewItems: Loaded<ReviewItemListResponse>;
  invitationBatches: Loaded<SpeakerInvitationBatchListResponse>;
}) {
  return (
    <section className="rounded-2xl border border-border p-6" aria-label="What needs your attention">
      <h2 className="font-semibold text-foreground">What needs your attention</h2>
      <p className="mt-1 text-sm leading-6 text-muted-foreground">
        Each line counts the rows the linked page will show, read from the same route that page
        reads. A line with no number says why it has none.
      </p>

      <ul className="mt-4 space-y-3">
        <ActionRow
          icon={Inbox}
          title="Speaker requests filed by event hosts"
          to="/coordinator-portal/speaker-requests"
          linkLabel="Open speaker requests"
          state={speakerRequests}
          count={speakerRequests.data?.requests.length ?? null}
          truncated={speakerRequests.data?.truncated ?? false}
        />
        <ActionRow
          icon={ClipboardCheck}
          title="Imported records waiting for a decision"
          to="/coordinator-portal/review-queue"
          linkLabel="Open review queue"
          state={reviewItems}
          count={reviewItems.data?.items.length ?? null}
          truncated={reviewItems.data?.truncated ?? false}
        />
        <ActionRow
          icon={Target}
          title="Match runs with a shortlist"
          to="/coordinator-portal/match-runs"
          linkLabel="Run a match"
          state={{ error: null, settled: true }}
          count={null}
          truncated={false}
          unavailable={
            "This API fetches one match run by id and has no route that lists them, so there is " +
            "no number to show here. Runs you start are reachable from the shortlist link the " +
            "run itself returns."
          }
        />
        <ActionRow
          icon={Send}
          title="Invitation batches composed"
          to="/coordinator-portal/invitations"
          linkLabel="Open invitations"
          state={invitationBatches}
          count={invitationBatches.data?.batches.length ?? null}
          truncated={false}
        />
      </ul>

      <p className="mt-3 text-xs leading-5 text-muted-foreground">
        Batches, not invitations: the batch list carries no per-invitation answer, so who accepted
        or declined is on each batch rather than in this count. The batch list is also a server
        page rather than a total — it reports its own limit and offset and no count of everything
        behind them.
      </p>
    </section>
  );
}

/**
 * The events starting in the next seven days.
 *
 * A window over the listing already fetched for the summary panel below — no
 * second request, and no second opinion about which events this unit has.
 *
 * ## Which events can be in it, and which cannot
 *
 * Only an event whose time the server resolved to an **instant** can be
 * compared against "now". A `date_only` event has a calendar date and no hour,
 * and placing it in or out of a seven-day window would mean choosing a moment
 * for it — the invented midnight ADR-0010 exists to forbid, which moves an
 * event across a day boundary for any reader west of the source.
 *
 * So those events are excluded, and the exclusion is stated on screen. An
 * unexplained short list is indistinguishable from a quiet week, and telling
 * those two apart is the whole point of this section.
 *
 * ## It is stated in words and not as a count
 *
 * The notice says *that* some events were left out, never *how many*. This
 * surface computes nothing — every number on it is one the server chose to
 * send (`test_frontend_dashboard_stats_contract.py`), and a tally of excluded
 * rows would be a figure this browser derived and no query owns. The link to
 * the full events page is what a reader who wants the actual set follows.
 *
 * Selecting and ordering rows is not computing a value: no number below is
 * rendered from an arithmetic result.
 */
function ThisWeeksEvents({ state }: { state: Loaded<UnitEventList> }) {
  const listing = state.data;
  const now = Date.now();
  const horizon = now + 7 * 24 * 60 * 60 * 1000;

  /** An event the server pinned to an instant, which is the only kind this window can judge. */
  function startsAtInstant(event: UnitEventSummary): number | null {
    if (event.time.precision !== "exact" || event.time.starts_at === null) {
      return null;
    }
    const parsed = new Date(event.time.starts_at).getTime();
    return Number.isFinite(parsed) ? parsed : null;
  }

  const all = listing?.events ?? [];
  const upcoming = all
    .filter((event) => {
      const at = startsAtInstant(event);
      return at !== null && at >= now && at <= horizon;
    })
    .sort((a, b) => (startsAtInstant(a) as number) - (startsAtInstant(b) as number));
  const someHaveNoSettledHour = all.some((event) => startsAtInstant(event) === null);

  return (
    <section className="rounded-2xl border border-border p-6" aria-label="This week">
      <div className="flex items-start gap-2">
        <CalendarDays
          className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground"
          aria-hidden="true"
        />
        <div>
          <h2 className="font-semibold text-foreground">Starting in the next seven days</h2>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">
            From the same listing the events panel below reads. Each time is shown in the
            event&apos;s own zone, not yours.
          </p>
        </div>
      </div>

      {state.error !== null ? (
        <p
          role="alert"
          className="mt-4 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-foreground"
        >
          {state.error}
        </p>
      ) : listing === null ? (
        <p className="mt-4 text-sm text-muted-foreground" role="status">
          {state.settled ? "The listing returned nothing." : "Loading this unit's events…"}
        </p>
      ) : (
        <>
          {upcoming.length === 0 ? (
            <p className="mt-4 text-sm leading-6 text-muted-foreground">
              No event with a resolved start time falls in the next seven days.
            </p>
          ) : (
            <ul className="mt-4 space-y-2">
              {upcoming.map((event) => (
                <li
                  key={event.id}
                  className="flex min-h-[40px] flex-wrap items-baseline justify-between gap-x-4 gap-y-1 rounded-xl border border-border/70 p-3"
                >
                  <span className="font-medium text-foreground">{event.title}</span>
                  <span className="text-sm text-muted-foreground">
                    {new Date(event.time.starts_at as string).toLocaleString(undefined, {
                      timeZone: event.time.time_zone ?? undefined,
                      timeZoneName: "short",
                    })}
                  </span>
                </li>
              ))}
            </ul>
          )}

          {someHaveNoSettledHour && (
            <p className="mt-3 text-xs leading-5 text-muted-foreground">
              This unit also holds events with a date but no settled hour. They are not placed in
              or out of this window, because choosing a time for them would move them across a day
              boundary for some readers. No tally of them is shown here — this page states only
              figures the server sent.{" "}
              <Link
                className="font-medium text-foreground underline underline-offset-4"
                to="/coordinator-portal/events"
              >
                See all events
              </Link>
              .
            </p>
          )}
        </>
      )}
    </section>
  );
}

export function CoordinatorHome() {
  // `GET /v1/me` — the only source of who this is. It throws rather than
  // substituting a fixture principal, which is the Fix #7 guard.
  const principal = useAuthenticatedPrincipal();
  // `GET /v1/me/portals` — the only source of what the server granted them,
  // and of the unit the three statistics reads below are scoped to.
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "coordinator");
  const unitId = grant?.default_unit_id ?? null;

  // Eight independent reads through the shared cache, settled independently.
  // Letting one refusal decide what another section shows would misreport
  // which capability the server actually withheld — the same reason the
  // hand-rolled version settled each read on its own. They now also run in
  // parallel (the old `load()` awaited them sequentially, which was most of
  // this page's switch-to latency) and are cached, so a revisit inside
  // `staleTime` renders instantly.
  //
  // The registered metrics are not among these reads. `SpeakerPipelineSection`
  // performs its own single one, because it needs the funnel, the conversions
  // and the insights the register listing does not carry — and re-reading the
  // register here would be a second request for numbers already on the screen.
  const speakerRequestsQuery = useScopedQuery({
    resource: "speaker-requests",
    params: [unitId],
    queryFn: () => fetchSpeakerRequests(unitId as string),
    enabled: unitId !== null,
  });
  const reviewItemsQuery = useScopedQuery({
    resource: "review-items",
    params: [unitId, "pending"],
    queryFn: () => fetchReviewItems(unitId as string, "pending"),
    enabled: unitId !== null,
  });
  const invitationBatchesQuery = useScopedQuery({
    resource: "invitation-batches",
    params: [unitId],
    queryFn: () => fetchSpeakerInvitationBatches(unitId as string),
    enabled: unitId !== null,
  });
  const attendanceQuery = useScopedQuery({
    resource: "attendance-summary",
    params: [unitId],
    queryFn: () => fetchAttendanceSummary(unitId as string),
    enabled: unitId !== null,
  });
  const feedbackQuery = useScopedQuery({
    resource: "unit-feedback-summary",
    params: [unitId],
    queryFn: () => fetchUnitSpeakerFeedbackSummary(unitId as string),
    enabled: unitId !== null,
  });
  const eventsQuery = useScopedQuery({
    resource: "unit-events",
    params: [unitId],
    queryFn: () => fetchUnitEvents(unitId as string),
    enabled: unitId !== null,
  });
  // The two outreach reads settle apart from each other as well as from
  // everything above: a unit can hold drafts it has never sent, and a refusal
  // on one of these routes says nothing about the other.
  const draftsQuery = useScopedQuery({
    resource: "outreach-drafts",
    params: [unitId],
    queryFn: async () => (await fetchOutreachDrafts(unitId as string)).drafts,
    enabled: unitId !== null,
  });
  const sendsQuery = useScopedQuery({
    resource: "outreach-sends",
    params: [unitId],
    queryFn: async () => (await fetchOutreachSends(unitId as string)).sends,
    enabled: unitId !== null,
  });

  const speakerRequests = queryToLoaded(speakerRequestsQuery, "The unit's speaker requests");
  const reviewItems = queryToLoaded(reviewItemsQuery, "The review queue");
  const invitationBatches = queryToLoaded(invitationBatchesQuery, "The invitation batches");
  const attendance = queryToLoaded(attendanceQuery, "The attendance summary");
  const feedback = queryToLoaded(feedbackQuery, "The unit feedback summary");
  const events = queryToLoaded(eventsQuery, "The unit's event listing");
  const drafts = queryToLoaded(draftsQuery, "The outreach drafts");
  const sends = queryToLoaded(sendsQuery, "The outreach sends");

  // `CoordinatorPortalLayout` already renders `PortalGate` when the server granted
  // no such portal, so reaching here without a grant means the mapping is
  // still resolving. Render nothing rather than a header about a portal that
  // may turn out not to be assigned.
  if (grant === null) {
    return null;
  }

  return (
    <div className="space-y-6">
      <PortalIdentityCard me={principal} grant={grant} />

      {unitId === null ? (
        <section
          className="rounded-2xl border border-dashed border-border bg-muted/30 p-6"
          aria-label="No unit assigned"
        >
          <h2 className="font-semibold text-foreground">No unit to count</h2>
          <p className="mt-2 flex items-start gap-2 text-sm leading-6 text-muted-foreground">
            <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span>
              The server granted this account no default unit, and every statistic below is
              scoped to one. Nothing is shown rather than a figure for some other unit.
            </span>
          </p>
        </section>
      ) : (
        <>
          {/* Action queue first, then what is coming, then the measured
              aggregates — `DESIGN.md`'s order for a Connector home page. */}
          <ActionQueue
            speakerRequests={speakerRequests}
            reviewItems={reviewItems}
            invitationBatches={invitationBatches}
          />
          <ThisWeeksEvents state={events} />

          <SpeakerPipelineSection unitId={unitId} />
          <AttendanceEvidence state={attendance} />
          <StudentFeedbackPointer state={feedback} />
          <HostedEventsSummary state={events} />
          <OutreachDraftsAndSends drafts={drafts} sends={sends} />
        </>
      )}
    </div>
  );
}
