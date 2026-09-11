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
import { useCallback, useEffect, useState } from "react";

import {
  ApiRequestError,
  fetchRewardCatalog,
  fetchStudentAgenda,
  type RewardCatalogResponse,
  type StudentAgenda,
} from "../../../lib/api";

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
  const [status, setStatus] = useState<StudentPortalStatus>(unitId === null ? "idle" : "loading");
  const [agenda, setAgenda] = useState<StudentAgenda | null>(null);
  const [agendaError, setAgendaError] = useState<string | null>(null);
  const [rewards, setRewards] = useState<RewardCatalogResponse | null>(null);
  const [rewardsError, setRewardsError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const reload = useCallback(() => setReloadToken((token) => token + 1), []);

  useEffect(() => {
    if (unitId === null) {
      setStatus("idle");
      setAgendaError(null);
      setRewardsError(null);
      return;
    }

    let mounted = true;
    setStatus("loading");

    async function load(id: string) {
      // `allSettled`, not `all`: one refusal must not discard the other answer.
      const [agendaResult, rewardsResult] = await Promise.allSettled([
        fetchStudentAgenda(id),
        fetchRewardCatalog(id),
      ]);
      if (!mounted) return;

      if (agendaResult.status === "fulfilled") {
        setAgenda(agendaResult.value);
        setAgendaError(null);
      } else {
        setAgendaError(
          reasonFrom(
            agendaResult.reason,
            "Your events could not be read, and the server gave no reason.",
          ),
        );
      }

      if (rewardsResult.status === "fulfilled") {
        setRewards(rewardsResult.value);
        setRewardsError(null);
      } else {
        setRewardsError(
          reasonFrom(
            rewardsResult.reason,
            "Your points could not be read, and the server gave no reason.",
          ),
        );
      }

      // "Unavailable" is reserved for both halves failing. One answer is a page
      // with something true on it, and calling that unavailable would hide the
      // half that worked.
      setStatus(
        agendaResult.status === "rejected" && rewardsResult.status === "rejected"
          ? "unavailable"
          : "ready",
      );
    }

    void load(unitId);
    return () => {
      mounted = false;
    };
  }, [unitId, reloadToken]);

  return { status, agenda, agendaError, rewards, rewardsError, reload };
}
