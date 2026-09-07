/**
 * Coordinator home — coordinator portal, and the Connector's pilot statistics.
 *
 * This page used to load your coordinator profile, hosted events and staffing, outreach threads, meeting bookings from the legacy `/api/portals/*` backend.
 * That backend is not part of this repository, so there is no request here
 * that could succeed and no data to render. Rather than a red failure banner
 * blaming an outage for a capability that was never present, each section
 * says plainly what it would have shown and where that would have come from
 * (`PortalDatasetUnavailable`).
 *
 * What *is* real on this page comes from four `/v1` routes and nothing else:
 * `GET /v1/me` for who the caller is, `GET /v1/me/portals` for the portal the
 * server granted them and the role and unit behind it, and the two reads the
 * statistics are drawn from. Neither identity route is derived in the browser,
 * and no identifier on this page is chosen by it.
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
 * Two reads, both of which count server-side:
 * `GET /v1/units/{unit_id}/metrics?surface=cba` for the registered metrics —
 * the review queue's size, Speaker Requests, and the four funnel counts as the
 * CBA product labels them — and
 * `GET /v1/units/{unit_id}/engagement/attendance-summary` for how much
 * attendance evidence the unit holds.
 *
 * Nothing on this page is folded, averaged, totalled or rounded. That is not
 * fastidiousness: a browser-side total is a second calculation of a published
 * number, it looks exactly as authoritative as the measured one, and it can be
 * drilled into by nothing. Where the two responses each carry a total, it is
 * the server's own — `AttendanceSummaryResponse.total` is documented as the
 * fold of `by_method`, computed from the same query that produced the parts.
 *
 * A `null` metric value is rendered as unknown *with the server's reason*, and
 * never as `0`. A measured `0` is rendered as `0`, because the query ran and
 * found none — a different claim, and the one ADR-0011 rule 1 exists to keep
 * apart from the first.
 *
 * ## What this surface cannot report, and says so
 *
 * Student feedback has no unit-level aggregate anywhere in this API. The only
 * Connector read is per speaker
 * (`GET /v1/units/{unit_id}/speakers/{speaker_id}/feedback-summary`), it is
 * aggregate-only by construction, and its suppression is the server's decision
 * carried in the response. So this page renders no feedback figure at all and
 * links to the page that does. Composing a unit-wide "average rating" here
 * would mean averaging aggregates in the browser — publishing a number no query
 * owns, out of values the server suppressed individually for anonymity.
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
import { BarChart3, Info, MessageSquareHeart } from "lucide-react";

import {
  ApiRequestError,
  fetchAttendanceSummary,
  fetchCbaUnitMetrics,
  type AttendanceSummary,
  type MetricSummary,
} from "../../../lib/api";
import { PortalDatasetUnavailable, PortalIdentityCard } from "../../components/PortalContent";
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
 */
function RegisteredMetricCard({ metric }: { metric: MetricSummary }) {
  const measured = metric.value !== null;

  return (
    <li className="rounded-xl border border-border/70 p-4">
      <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {metric.display_name}
      </h3>
      {measured ? (
        <p className="mt-1 text-2xl font-semibold tabular-nums text-foreground">{metric.value}</p>
      ) : (
        <p className="mt-1 text-sm font-medium text-foreground">Not measured</p>
      )}
      <p className="mt-2 text-xs leading-5 text-muted-foreground">{metric.definition}</p>
      {measured ? null : (
        <p className="mt-2 text-xs leading-5 text-muted-foreground">{metric.unknown_reason}</p>
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
 * Student feedback, and why no number for it appears on this page.
 *
 * Customer §16 asks that a Connector be able to view student feedback, and they
 * can — one speaker at a time, on the page this links to. What does not exist
 * anywhere in this API is a *unit-level* aggregate, and the honest thing is to
 * say so rather than to build one here out of the per-speaker summaries. Those
 * are suppressed individually below a threshold precisely so that small numbers
 * of responses are not published; averaging what survived would republish, in a
 * figure nobody can drill into, exactly what the suppression withheld.
 *
 * OQ-CBA-053 is stated here rather than left to the reader. This section sits
 * directly beneath a funnel of matching counts, and a rating placed near
 * "speakers matched" reads as an input to it unless the page says otherwise.
 */
function StudentFeedbackPointer() {
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
        <div className="space-y-2">
          <h2 className="font-semibold text-foreground">Student feedback on your speakers</h2>
          <p className="text-sm leading-6 text-muted-foreground">
            Student feedback <strong>does not feed matching</strong>. It records how an event
            went; no part of it is read when candidates are ranked, and changing a rating changes
            nothing about who is put forward. It is shown here beside the funnel counts for that
            reason — so the two are not mistaken for one number.
          </p>
          <p className="text-sm leading-6 text-muted-foreground">
            No figure for it appears on this page, and that is a limit of the API rather than a
            layout choice. Feedback is answerable one speaker at a time (
            <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
              GET /v1/units/&#123;unit_id&#125;/speakers/&#123;speaker_id&#125;/feedback-summary
            </code>
            ) and there is no unit-wide aggregate to read. Each speaker&apos;s summary is withheld
            entirely until enough students have answered, with the threshold travelling in the
            response, so combining the ones that survive would publish here what the server
            declined to publish there.
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
  // and of the unit the two statistics reads below are scoped to.
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "coordinator");
  const unitId = grant?.default_unit_id ?? null;

  const [metrics, setMetrics] = useState<Loaded<MetricSummary[]>>(PENDING);
  const [attendance, setAttendance] = useState<Loaded<AttendanceSummary>>(PENDING);

  const load = useCallback(async () => {
    if (unitId === null) return;

    // Two independent reads, settled independently. Letting one refusal decide
    // what the other section shows would misreport which capability the server
    // actually withheld.
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
          <StudentFeedbackPointer />
        </>
      )}

      <div className="space-y-4">
        <PortalDatasetUnavailable
          dataset="Your coordinator profile"
          endpoints={["/api/portals/event-coordinators/{id}"]}
        />
        <PortalDatasetUnavailable
          dataset="Hosted events and staffing"
          endpoints={["/api/portals/event-coordinators/{id}/events"]}
        />
        <PortalDatasetUnavailable
          dataset="Outreach threads"
          endpoints={["/api/portals/event-coordinators/{id}/threads"]}
        />
        <PortalDatasetUnavailable
          dataset="Meeting bookings"
          endpoints={["/api/portals/event-coordinators/{id}/meetings"]}
        />
      </div>

      <ReviewQueueUnavailable />
    </div>
  );
}
