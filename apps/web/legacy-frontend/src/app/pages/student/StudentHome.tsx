/**
 * Student home — student portal.
 *
 * This page used to render three `PortalDatasetUnavailable` panels and nothing
 * else, because the reads it was written against — `/api/portals/students/{id}`
 * and its two siblings — belong to a backend that is not part of this
 * repository. Two of those three sections now have a `/v1` answer, and the
 * panels for them are gone: an unavailable panel is a claim, and left standing
 * beside a working read it is the same fabricated-equivalence defect pointed
 * the other way, telling a student a capability is absent while the page holds
 * its answer.
 *
 * ## Everything on this page is a server response
 *
 * - `GET /v1/me` — who the caller is.
 * - `GET /v1/me/portals` — the portal the server granted them, and the unit id
 *   the two reads below are addressed to. Never `VITE_SMARTMATCH_UNIT_ID`,
 *   which is unset on the classroom VM.
 * - `GET /v1/units/{unit_id}/student/agenda` — the events this student is
 *   recorded at or holds a place at. Self-scoped by the server's own query;
 *   there is no subject parameter and there must never be one (MM-A01).
 * - `GET /v1/units/{unit_id}/rewards` — their balance, and the unit's funded
 *   catalog.
 *
 * No identifier on this page is composed by the browser, no event is invented,
 * and no number is computed here from anything except values the server sent
 * in the same response.
 *
 * ## What is still missing, and is still said out loud
 *
 * Recommended events and next-step prompts have no `/v1` route at all — not a
 * refusal, not an empty list, no route — so they keep a named-absence panel and
 * {@link MissingCapability} states which server capability would have to exist.
 * Deleting the panel would turn a named absence into a silent one, which is the
 * defect the panel was written for.
 */
import { Link } from "react-router";
import { CalendarClock } from "lucide-react";

import { Skeleton } from "../../components/ui/skeleton";
import { PortalIdentityCard } from "../../components/PortalContent";
import { grantedPortal } from "../../components/PortalGate";
import { usePortalAccess } from "../../hooks/usePortalAccess";
import { useAuthenticatedPrincipal } from "../../hooks/useSession";
import { AgendaEventCard, MissingCapability, PointsPanel } from "./studentPanels";
import { pointsSummary, splitAgenda } from "./studentTimeline";
import { useStudentPortalData } from "./useStudentPortalData";

/** How many of the next events the home page shows before deferring to `/events`. */
const NEXT_EVENT_LIMIT = 3;

/**
 * Why there is nothing to read even though nothing failed: the granted portal
 * carries no unit. Not an empty agenda — an agenda that has no unit to be an
 * agenda of. `useRewards` states the same distinction for the catalog.
 */
const NO_UNIT_REASON =
  "The portal the server granted this account carries no department, so there are no events " +
  "or points to read. Ask your program administrator to attach one to your membership.";

export function StudentHome() {
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

  // The split is against "now" at render time. It is a reading of the server's
  // own timestamps, not a schedule this page keeps.
  const groups = agenda === null ? null : splitAgenda(agenda.events, new Date());
  const next = groups === null ? [] : groups.upcoming.slice(0, NEXT_EVENT_LIMIT);
  const loading = status === "loading";
  const withheld = agenda?.withheld_unresolved_date ?? 0;

  return (
    <div className="space-y-6">
      <PortalIdentityCard me={principal} grant={grant} />

      {unitId === null && status === "idle" ? (
        <p className="rounded-2xl border border-border/70 bg-card p-6 text-sm leading-6 text-muted-foreground">
          {NO_UNIT_REASON}
        </p>
      ) : (
        <>
          <section
            className="rounded-2xl border border-border/70 bg-card p-6"
            aria-labelledby="student-home-next-heading"
          >
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 id="student-home-next-heading" className="min-w-0 font-semibold text-foreground">
                What is next for you
              </h2>
              <Link
                to="/events"
                className="rounded text-sm text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                Browse all events
              </Link>
            </div>

            {loading ? (
              <div className="mt-4 space-y-3" aria-busy="true" aria-live="polite">
                <span className="sr-only">Loading your events…</span>
                <Skeleton className="h-20 w-full rounded-xl" />
                <Skeleton className="h-20 w-full rounded-xl" />
              </div>
            ) : agendaError !== null ? (
              <p role="alert" className="mt-3 text-sm leading-6 text-foreground">
                {agendaError}
              </p>
            ) : next.length === 0 ? (
              <p className="mt-3 flex items-start gap-2 text-sm leading-6 text-muted-foreground">
                <CalendarClock className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                <span>
                  Nothing is coming up on your agenda. Register for an event and it appears here,
                  as does anything your department records you at.
                </span>
              </p>
            ) : (
              <ul className="mt-4 space-y-3">
                {next.map((event) => (
                  <AgendaEventCard key={event.id} event={event} />
                ))}
              </ul>
            )}

            {groups !== null && groups.upcoming.length > next.length ? (
              <p className="mt-3 text-xs text-muted-foreground">
                {groups.upcoming.length - next.length} more still to come, on{" "}
                <Link
                  to="/events"
                  className="rounded text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  your agenda
                </Link>
                .
              </p>
            ) : null}

            {withheld > 0 ? (
              <p className="mt-2 text-xs leading-5 text-muted-foreground">
                {withheld} {withheld === 1 ? "event on your agenda has" : "events on your agenda have"}{" "}
                no confirmed date, so {withheld === 1 ? "it has" : "they have"} no place on a
                timeline and {withheld === 1 ? "is" : "are"} not listed above.
              </p>
            ) : null}
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

          {rewards !== null && rewards.items.length > 0 ? (
            <section
              className="rounded-2xl border border-border/70 bg-card p-6"
              aria-labelledby="student-home-rewards-heading"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2
                  id="student-home-rewards-heading"
                  className="min-w-0 font-semibold text-foreground"
                >
                  Rewards in your department
                </h2>
                <Link
                  to="/rewards"
                  className="rounded text-sm text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  See the catalogue
                </Link>
              </div>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                {/*
                  A count of the rows the server sent, both times. `affordable`
                  is the server's flag against the server's balance — this page
                  does not compare a cost to a number of its own.
                */}
                {rewards.items.filter((item) => item.affordable).length} of {rewards.items.length}{" "}
                funded {rewards.items.length === 1 ? "reward" : "rewards"} are within your balance
                today.
              </p>
            </section>
          ) : null}
        </>
      )}

      <MissingCapability
        dataset="Recommended events and next-step prompts"
        endpoints={[
          "/api/portals/students/{id}/recommendations",
          "/api/portals/students/{id}/nudge",
        ]}
        capability={
          "Missing backend capability: a student-scoped recommendation and nudge read. No /v1 " +
          "route recommends events to a student or produces next-step prompts — the server has " +
          "no such endpoint at any role, so this is an absent capability rather than a refusal " +
          "or an empty result. Your events and points above are unaffected."
        }
      />
    </div>
  );
}
