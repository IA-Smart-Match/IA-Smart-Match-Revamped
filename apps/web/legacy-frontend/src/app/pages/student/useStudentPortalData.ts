/**
 * The two `/v1` reads `StudentHome` and `StudentHistory` both need, loaded once.
 *
 * `GET /v1/units/{unit_id}/student/agenda` — the caller's own events, and
 * `GET /v1/units/{unit_id}/rewards` — the caller's own balance beside the
 * unit's funded catalog. Neither takes a subject parameter: the server resolves
 * the student from the bearer token, which is why nothing here composes an
 * identifier and why there is nothing on these pages for MM-A01's
 * caller-selected identity to enter through.
 *
 * It lives beside its two callers rather than in `app/hooks/` because it is
 * theirs: `useRewards` is the hook `StudentRewards` needs (catalog plus the
 * redemption command) and this is the pair the two summary pages need. Sharing
 * one hook between them would have made every page load what only one of them
 * renders.
 *
 * ## Four states, and the failures do not merge
 *
 * `status` is `"idle" | "loading" | "ready" | "unavailable"` — the machine
 * `useRewards` and `useUnitMetrics` already use. The difference here is that
 * the two reads fail **separately**: an agenda that could not be read is
 * reported against the agenda, and a rewards read refused with `403` is
 * reported against points, because collapsing both into one banner would tell
 * a student their whole portal is broken when one half of it answered.
 *
 * `unitId === null` is `"idle"`, not `"unavailable"`. Nothing was asked for,
 * which is not the same as something having failed; the page owns the
 * difference between "the grant is still resolving" and "the grant carries no
 * unit", because only the page knows which.
 *
 * A read that fails leaves the previous value in place rather than clearing it
 * to an empty list. An empty agenda is a claim — "you are recorded at nothing"
 * — and a failed read is not, so the error carries the failure and the page
 * renders that instead of an emptied list.
 */
import { useCallback } from "react";

import {
  ApiRequestError,
  fetchRewardCatalog,
  fetchStudentAgenda,
  type RewardCatalogResponse,
  type StudentAgenda,
} from "../../../lib/api";
import { useScopedQuery } from "../../hooks/useScopedQuery";

export type StudentPortalStatus = "idle" | "loading" | "ready" | "unavailable";

export interface StudentPortalData {
  status: StudentPortalStatus;
  agenda: StudentAgenda | null;
  /** The server's own words for why the agenda could not be read, or null. */
  agendaError: string | null;
  rewards: RewardCatalogResponse | null;
  /** The server's own words for why the rewards read was refused, or null. */
  rewardsError: string | null;
  reload: () => void;
}

/** The server's refusal text, or a sentence that does not pretend to know it. */
function reasonFrom(cause: unknown, fallback: string): string {
  return cause instanceof ApiRequestError ? cause.message : fallback;
}

/**
 * @param unitId `PortalDescriptor.default_unit_id` from `GET /v1/me/portals`,
 *   passed in by the page holding the grant — never `VITE_SMARTMATCH_UNIT_ID`,
 *   which is unset on the classroom VM, and never a browser-composed id.
 */
export function useStudentPortalData(unitId: string | null): StudentPortalData {
  // Two independent cached reads — the `allSettled` the hand-rolled version
  // used, kept: one refusal must not discard the other answer, and each error
  // is reported against its own half. Both are shared across `StudentHome`,
  // `StudentHistory` and `StudentConnect`, so the second page a student opens
  // renders from cache.
  const agendaQuery = useScopedQuery({
    resource: "student-agenda",
    params: [unitId],
    queryFn: () => fetchStudentAgenda(unitId as string),
    enabled: unitId !== null,
  });
  const rewardsQuery = useScopedQuery({
    resource: "reward-catalog",
    params: [unitId],
    queryFn: () => fetchRewardCatalog(unitId as string),
    enabled: unitId !== null,
  });

  const reload = useCallback(() => {
    void agendaQuery.refetch();
    void rewardsQuery.refetch();
  }, [agendaQuery, rewardsQuery]);

  // `.data ?? null`, not an `isSuccess` gate: a failed *re*fetch keeps the
  // last good answer in `data`, and the rule above is that a failed read
  // leaves the previous value in place rather than clearing it to an empty
  // list — the error carries the failure beside it.
  const agenda = agendaQuery.data ?? null;
  const agendaError = agendaQuery.isError
    ? reasonFrom(agendaQuery.error, "Your events could not be read, and the server gave no reason.")
    : null;
  const rewards = rewardsQuery.data ?? null;
  const rewardsError = rewardsQuery.isError
    ? reasonFrom(rewardsQuery.error, "Your points could not be read, and the server gave no reason.")
    : null;

  const status: StudentPortalStatus =
    unitId === null
      ? "idle"
      : agendaQuery.isPending || rewardsQuery.isPending
        ? "loading"
        : // "Unavailable" is reserved for both halves failing. One answer is a
          // page with something true on it, and calling that unavailable would
          // hide the half that worked.
          agendaQuery.isError && rewardsQuery.isError
          ? "unavailable"
          : "ready";

  return { status, agenda, agendaError, rewards, rewardsError, reload };
}
