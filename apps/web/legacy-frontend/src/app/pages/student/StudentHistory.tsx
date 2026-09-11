/**
 * History — student portal.
 *
 * What a student has done, and what it earned. Both halves are `/v1` reads
 * now; the `PortalDatasetUnavailable` panel this page used to be made of is
 * gone, because a named absence beside a working read is a false statement.
 *
 * - `GET /v1/units/{unit_id}/student/agenda` — the events on this student's
 *   list, split into what has happened and what is still to come. Self-scoped
 *   by the server's own query, with no subject parameter (MM-A01).
 * - `GET /v1/units/{unit_id}/rewards` — the balance those events earned.
 *
 * ## The word this page does not use
 *
 * "Attended." The agenda route returns the **union** of `attendance_record`
 * and active `event_registration` and does not say which half a row came
 * from, so calling the past list "events you attended" would assert something
 * the response does not carry — the ADR-0011 defect applied to a capability
 * rather than to a number. `studentTimeline.agendaLinkText` says, per row,
 * exactly what the server established: a row with no registration at all, or
 * with a cancelled one, can only have arrived through attendance, and that is
 * stated; a row with an active registration is reported as a place held.
 *
 * ## Two things this page cannot show, and says so
 *
 * The speaker at a past event: `StudentEventSummary` carries no speaker field
 * and both roster reads are `admin`/`coordinator` server-side.
 *
 * The individual point credits: `GET .../rewards` folds `point_ledger_entry`
 * into one balance and a count. `PointsPanel` names that gap rather than
 * rendering an empty list a reader would take for "you have earned nothing".
 */
import { Link } from "react-router";
import { History as HistoryIcon, Info } from "lucide-react";

import { PagedList } from "../../components/PagedList";
import { Skeleton } from "../../components/ui/skeleton";
import { grantedPortal } from "../../components/PortalGate";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";
import { AgendaEventCard, PointsPanel } from "./studentPanels";
import { pointsSummary, splitAgenda } from "./studentTimeline";
import { useStudentPortalData } from "./useStudentPortalData";

/** See `StudentHome`: no unit is not an empty history, it is no history to have. */
const NO_UNIT_REASON =
  "The portal the server granted this account carries no department, so there is no history " +
  "to read. Ask your program administrator to attach one to your membership.";

export function StudentHistory() {
  // `GET /v1/me` — the only source of who this is. It throws rather than
  // substituting a fixture principal, which is the Fix #7 guard.
  const principal = useAuthenticatedPrincipal();
  // `GET /v1/me/portals` — the only source of what the server granted them.
  const portalAccess = usePortalAccess();
  const grant = grantedPortal(portalAccess, "student");
  const unitId = grant?.default_unit_id ?? null;

  const { status, agenda, agendaError, rewards, rewardsError } = useStudentPortalData(unitId);

  // `StudentLayout` already renders `PortalGate` when the server granted
  // no such portal, so reaching here without a grant means the mapping is
  // still resolving. Render nothing rather than a header about a portal that
  // may turn out not to be assigned.
  if (grant === null) {
    return null;
  }

  const groups = agenda === null ? null : splitAgenda(agenda.events, new Date());
  const past = groups?.past ?? [];
  const loading = status === "loading";
  const withheld = agenda?.withheld_unresolved_date ?? 0;

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-foreground">History</h1>
        <p className="text-sm text-muted-foreground">
          The events already on your record, and what they earned.
        </p>
        <p className="text-xs text-muted-foreground">
          Signed in as {principal.email} · {grant.role} · {grant.org_unit_path}
        </p>
      </header>

      {unitId === null && status === "idle" ? (
        <p className="rounded-2xl border border-border/70 bg-card p-6 text-sm leading-6 text-muted-foreground">
          {NO_UNIT_REASON}
        </p>
      ) : (
        <>
          <section
            className="rounded-2xl border border-border/70 bg-card p-6"
            aria-label="Events already on your record"
          >
            <h2 className="font-semibold text-foreground">Events already on your record</h2>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              Events your department recorded you at, and places you held that have now passed.
              The server returns both together and does not mark which is which, so each entry
              says what it can establish rather than guessing.
            </p>

            {loading ? (
              <div className="mt-4 space-y-3" aria-busy="true" aria-live="polite">
                <span className="sr-only">Loading your history…</span>
                <Skeleton className="h-24 w-full rounded-xl" />
                <Skeleton className="h-24 w-full rounded-xl" />
                <Skeleton className="h-24 w-full rounded-xl" />
              </div>
            ) : agendaError !== null ? (
              <p role="alert" className="mt-3 text-sm leading-6 text-foreground">
                {agendaError}
              </p>
            ) : past.length === 0 ? (
              <p className="mt-3 flex items-start gap-2 text-sm leading-6 text-muted-foreground">
                <HistoryIcon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                <span>
                  Nothing has happened on your record yet. An event lands here once it has passed
                  and either you held a place at it or your department recorded you there.{" "}
                  <Link
                    to="/events"
                    className="rounded text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    Browse what is coming up
                  </Link>
                  .
                </span>
              </p>
            ) : (
              /* The pager windows the rows this browser already holds. It
                 issues no read, and its count is of what arrived — the agenda
                 route caps its own listing and reports `truncated`. */
              <div className="mt-4">
                <PagedList items={past} label="past events" idPrefix="student-history-events">
                  {(visible) => (
                    <ul className="space-y-3">
                      {visible.map((event) => (
                        <AgendaEventCard key={event.id} event={event} />
                      ))}
                    </ul>
                  )}
                </PagedList>
              </div>
            )}

            {agenda?.truncated ? (
              <p className="mt-3 text-xs leading-5 text-muted-foreground">
                Your agenda was longer than the server returns in one answer, so the oldest
                entries are not on this page.
              </p>
            ) : null}

            {withheld > 0 ? (
              <p className="mt-2 text-xs leading-5 text-muted-foreground">
                {withheld}{" "}
                {withheld === 1 ? "event on your record has" : "events on your record have"} no
                confirmed date, so {withheld === 1 ? "it cannot" : "they cannot"} be placed in
                this order and {withheld === 1 ? "is" : "are"} not listed.
              </p>
            ) : null}

            <p className="mt-3 flex items-start gap-2 text-xs leading-5 text-muted-foreground">
              <Info className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
              <span>
                Who spoke at each event is not shown. Missing backend capability: a
                student-visible read of the speakers at an event. The two roster routes that
                exist are restricted to Speaker Connectors and Event Hosts, so this page has no
                name it is allowed to show — and inventing one would be worse than showing none.
                Ratings you have already left are on{" "}
                <Link
                  to="/speaker-feedback"
                  className="rounded text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  Speaker feedback
                </Link>
                .
              </span>
            </p>
          </section>

          {loading ? (
            <Skeleton className="h-48 w-full rounded-2xl" />
          ) : (
            <PointsPanel
              summary={rewards === null ? null : pointsSummary(rewards.balance)}
              pointsPerAttendance={rewards?.points_per_verified_attendance ?? null}
              earnPolicyRatified={rewards?.earn_policy_ratified ?? false}
              error={rewardsError}
            />
          )}
        </>
      )}
    </div>
  );
}
