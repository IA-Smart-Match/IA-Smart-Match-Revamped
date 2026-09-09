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
 * Two of those four have had a `/v1` answer all along and were simply unwired,
 * and the panels above them were therefore saying something false about *this*
 * deployment while saying something true about the legacy one:
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
 *    only what that response says about its own completeness and links there.
 *
 * The old label said "hosted events **and staffing**". The `/v1` listing
 * carries no staffing of any kind, so the label went rather than being kept
 * over a response that does not answer it — see `CoordinatorEvents.tsx`.
 *
 * **Meeting bookings** still has no `/v1` answer and keeps its panel. Deleting
 * it alongside the others would turn a named absence into an unnamed one, which
 * is the direction this page is built to refuse.
 *
 * What *is* real on this page comes from `/v1` routes and nothing else:
 * `GET /v1/me` for who the caller is, `GET /v1/me/portals` for the portal the
 * server granted them and the role and unit behind it, and the four unit-scoped
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
 * The second is who arrives. `Dashboard.tsx` sits behind the IA admin shell
 * (`Layout`), not `CoordinatorPortalLayout`, and a Connector clicking through
 * the pilot never reaches it. Statistics nobody in the audience can see are not
 * statistics.
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

 * The review queue is the same shape of gap in the opposite direction: its
 * *size* is a registered metric and appears below, but there is still no route
 * that lists the items, so no queue is drawn.
 *
 * ## Not authorization
 *
 * Both reads are decided server-side per request against the loaded unit. This
 * page renders its sections and shows the server's `403` as the answer it is,
 * rather than hiding them and implying the capability is absent.
 */

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { BarChart3, CalendarDays, Info, MessageSquareHeart } from "lucide-react";

import {
  ApiRequestError,
  fetchAttendanceSummary,
  fetchCbaUnitMetrics,
  fetchUnitEvents,
  fetchUnitSpeakerFeedbackSummary,
  type AttendanceSummary,
  type MetricSummary,
  type UnitEventList,
  type UnitFeedbackSummary,
} from "../../../lib/api";
import { PortalDatasetUnavailable, PortalIdentityCard } from "../../components/PortalContent";
import { Tooltip, TooltipContent, TooltipTrigger } from "../../components/ui/tooltip";
import { grantedPortal } from "../../components/PortalGate";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";

/**
 * What one read returned, or why it returned nothing.
 *
 * The failure is kept beside the data rather than in a page-level banner
 * because the two reads fail independently: a Connector refused the attendance
 * summary can still be entitled to the register, and replacing both with one
 * message would misreport which capability the server withheld.
 */
type Loaded<T> = { data: T | null; error: string | null; settled: boolean };

const PENDING = { data: null, error: null, settled: false } as const;

function describeFailure(cause: unknown, subject: string): string {
  // The server's own words where it gave any. `ApiRequestError.message` carries
  // the API's error text, including the refusal a `403` explains, and a
  // rephrasing here would be this page's opinion about someone else's decision.
  return cause instanceof ApiRequestError
    ? cause.message
    : `${subject} could not be read and the server gave no reason.`;
}

/**
 * One registered metric, exactly as the register answered for it.
 *
 * Three states, and the middle one is the point of the whole register: a
 * measured number, a measured zero (which prints as `0` and means the query ran
 * and found none), and an unknown carrying the server's `unknown_reason`. There
 * is no fourth branch in which a missing value becomes a zero.
 *
 * ## Why the definition is behind an affordance and the reason is not
 *
 * The card face carries the display name and the value, and nothing else. The
 * `definition` is the register's own sentence about how a metric is counted —
 * `smartmatch_domain/metrics.py` writes it for a reader who has stopped to ask,
 * and the longest of the six runs to about ninety words. Six of those printed
 * on the face pushed the grid past the fold, so the first thing a Connector had
 * to do with their unit's numbers was scroll away from them.
 *
 * It moves behind an info control that opens on **hover and on keyboard
 * focus** — a real `<button>`, not a `<span>` with a mouse handler, because the
 * two are the same control to a mouse and only one of them exists to a keyboard
 * or a screen reader. Radix's `Tooltip` (`components/ui/tooltip.tsx`, already a
 * dependency of this app) gives both from the one trigger, which is why no new
 * component and no new package appears here.
 *
 * The tooltip prints `metric.definition` **verbatim**. Nothing is sliced,
 * clamped or elided: the register is the author of a registered definition, and
 * a browser that shortened one would be publishing a second, shorter definition
 * that no server owns and that nothing can drill into. A definition that is too
 * long is a sentence to rewrite in `metrics.py`, where every surface reading the
 * register gets the rewrite.
 *
 * `unknown_reason` stays on the face. It is not a footnote and it is not
 * optional reading: it is the entire content of an unmeasured metric, and
 * ADR-0011 rule 1 is about exactly this — the reason a number is missing has to
 * arrive with the missing number, not behind a gesture a reader has to guess to
 * make. A definition explains a figure that is on the screen; a reason explains
 * why one is not, and only the first of those can wait for a hover.
 */
function RegisteredMetricCard({ metric }: { metric: MetricSummary }) {
  const measured = metric.value !== null;

  return (
    <li className="rounded-xl border border-border/70 p-4">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {metric.display_name}
        </h3>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              // Labelled with the metric it belongs to: six controls all
              // reading "info" are six identical, unusable stops in a screen
              // reader's list of a page's buttons.
              aria-label={`How ${metric.display_name} is counted`}
              className="shrink-0 rounded-full p-0.5 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Info className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </TooltipTrigger>
          <TooltipContent className="max-w-xs text-left leading-5">
            {/* The register's sentence, exactly as it was written — no slice,
                no clamp, no ellipsis. See this component's docstring. */}
            {metric.definition}
          </TooltipContent>
        </Tooltip>
      </div>
      {measured ? (
        <p className="mt-1 text-2xl font-semibold tabular-nums text-foreground">{metric.value}</p>
      ) : (
        <>
          <p className="mt-1 text-sm font-medium text-foreground">Not measured</p>
          {/* Inline, never inside the tooltip above: ADR-0011 rule 1, and the
              reason a number is missing is not a footnote. */}
          <p className="mt-2 text-xs leading-5 text-muted-foreground">{metric.unknown_reason}</p>
        </>
      )}
    </li>
  );
}

/**
 * The registered metrics for this unit, as the CBA product presents them.
 *
 * The `surface=cba` view is the server's: `pipeline_member_inquiry` is absent
 * because `Capability.MEMBER_INQUIRY_NARRATIVE` is off under `ProductScope.CBA`,
 * and the funnel labels are written for a surface whose subject is a speaker.
 * Nothing is filtered or relabelled here, so there is no second copy of that
 * decision to fall out of date.
 */
function RegisteredMetrics({ state }: { state: Loaded<MetricSummary[]> }) {
  return (
    <section className="rounded-2xl border border-border p-6" aria-label="Registered metrics">
      <div className="flex items-start gap-2">
        <BarChart3 className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <div>
          <h2 className="font-semibold text-foreground">Where your unit&apos;s work stands</h2>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">
            Every figure below is counted by the server, and each one is a registered metric with
            a single owning query behind it. No total, mean or rounding is produced in your
            browser.
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
      ) : state.data === null ? (
        <p className="mt-4 text-sm text-muted-foreground">
          {state.settled ? "The register returned nothing." : "Loading…"}
        </p>
      ) : state.data.length === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">
          The server registered no metrics for this unit, so there is nothing to count. This is a
          statement about the register, not about your unit&apos;s activity.
        </p>
      ) : (
        <ul className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {state.data.map((metric) => (
            <RegisteredMetricCard key={metric.name} metric={metric} />
          ))}
        </ul>
      )}
    </section>
  );
}

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
 * The review queue, and why it is empty rather than absent.
 *
 * This is a *different* gap from the `/api/portals/*` panels above, and it is
 * stated separately because conflating them would hide it. The review workflow
 * genuinely lives in this API — `POST /v1/review-items/{review_item_id}/decision`
 * exists and works — but there is **no list route**. A coordinator can decide
 * a review item only if they already know its id, and no `/v1` path yields
 * one: `scripts/compose_smoke.sh` and the E2E suite both read the id straight
 * out of the database.
 *
 * TRACK 14 narrowed this by exactly one fact and no more. The *size* of the
 * queue is a registered metric (`pending_review_items`), so the count above is
 * real and server-owned. The items themselves are still unlistable, and drawing
 * an empty list beside a non-zero count would be worse than drawing nothing:
 * it would contradict a measured number on the same screen.
 *
 * So this portal still cannot render a queue, and it says so instead of
 * rendering an empty one. An empty list would be a claim that there is nothing
 * to review, which is a statement about the data; the truth is a statement
 * about the API (ADR-0011: unknown is never zero). Fetching the ids from the
 * database to fill it in was explicitly ruled out — a frontend that reaches
 * around a missing endpoint makes the endpoint's absence invisible and
 * un-fixable.
 *
 * Adding `GET /v1/review-items` is the follow-up. It was left out of this PR
 * deliberately: it needs decisions about filtering, pagination, and which
 * statuses are visible to which roles, and those are not decisions to make as
 * a side effect of a login change.
 */
function ReviewQueueUnavailable() {
  return (
    <section
      className="rounded-2xl border border-dashed border-border bg-muted/30 p-6"
      aria-label="Review queue unavailable"
    >
      <h2 className="font-semibold text-foreground">Review queue is not listable yet</h2>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">
        The count of pending review items above is real and comes from the register. What is
        missing is the queue itself: this API can record a review decision (
        <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
          POST /v1/review-items/&#123;id&#125;/decision
        </code>
        ) but has no route that lists the items awaiting one, so there is no queue to draw. An
        empty list here would contradict the count on the same screen — the items exist, and it
        is the reading of them that has no endpoint.
      </p>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">
        Needs: <code className="rounded bg-muted px-1.5 py-0.5">GET /v1/review-items</code>{" "}
        (follow-up; deferred because it requires decisions about filtering, pagination, and
        per-role visibility).
      </p>
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

  const [metrics, setMetrics] = useState<Loaded<MetricSummary[]>>(PENDING);
  const [attendance, setAttendance] = useState<Loaded<AttendanceSummary>>(PENDING);
  const [feedback, setFeedback] = useState<Loaded<UnitFeedbackSummary>>(PENDING);
  const [events, setEvents] = useState<Loaded<UnitEventList>>(PENDING);

  const load = useCallback(async () => {
    if (unitId === null) return;

    // Four independent reads, settled independently. Letting one refusal
    // decide what another section shows would misreport which capability the
    // server actually withheld.
    try {
      const response = await fetchCbaUnitMetrics(unitId);
      setMetrics({ data: response.metrics, error: null, settled: true });
    } catch (cause) {
      setMetrics({
        data: null,
        error: describeFailure(cause, "The registered metrics"),
        settled: true,
      });
    }

    try {
      const summary = await fetchAttendanceSummary(unitId);
      setAttendance({ data: summary, error: null, settled: true });
    } catch (cause) {
      setAttendance({
        data: null,
        error: describeFailure(cause, "The attendance summary"),
        settled: true,
      });
    }

    try {
      const summary = await fetchUnitSpeakerFeedbackSummary(unitId);
      setFeedback({ data: summary, error: null, settled: true });
    } catch (cause) {
      setFeedback({
        data: null,
        error: describeFailure(cause, "The unit feedback summary"),
        settled: true,
      });
    }

    try {
      const listing = await fetchUnitEvents(unitId);
      setEvents({ data: listing, error: null, settled: true });
    } catch (cause) {
      setEvents({
        data: null,
        error: describeFailure(cause, "The unit's event listing"),
        settled: true,
      });
    }
  }, [unitId]);

  useEffect(() => {
    void load();
  }, [load]);

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
          <RegisteredMetrics state={metrics} />
          <AttendanceEvidence state={attendance} />
          <StudentFeedbackPointer state={feedback} />
          <HostedEventsSummary state={events} />
        </>
      )}

      <div className="space-y-4">
        <PortalDatasetUnavailable
          dataset="Outreach threads"
          endpoints={["/api/portals/event-coordinators/{id}/threads"]}
        />
        {/* Meeting bookings has no `/v1` answer today, so it stays a named
            absence rather than being quietly dropped now that the panels
            around it have landed. */}
        <PortalDatasetUnavailable
          dataset="Meeting bookings"
          endpoints={["/api/portals/event-coordinators/{id}/meetings"]}
        />
      </div>

      <ReviewQueueUnavailable />
    </div>
  );
}
