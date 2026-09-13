/**
 * Hover/focus prefetch for portal navigation — the second half of the
 * page-switch latency fix.
 *
 * The query cache (`useScopedQuery`) already makes a *revisit* instant:
 * stale-while-revalidate serves the cached answer inside `staleTime`. What
 * it cannot help is the *first* visit to a page, which still pays the full
 * round trip after the click lands. Prefetching on hover/focus starts that
 * round trip when the reader's intent is visible — typically a few hundred
 * milliseconds before the click — so the page behind the link usually finds
 * its data already in flight or already cached.
 *
 * The map keys on the nav `href`, and each entry prefetches exactly the
 * page-load reads that page makes — the same resource names the pages use in
 * their own `scopedQueryKey` calls, so a prefetched entry and the page's own
 * query are the same cache slot. A page not listed here simply gets no
 * prefetch; nothing breaks.
 *
 * Every prefetch is `prefetchQuery`, which never throws to the caller: a
 * failed prefetch leaves no error on screen and the page's own query retries
 * or reports the failure as it always has. Prefetching is a hint, not a
 * second owner of the read.
 */
import type { QueryClient } from "@tanstack/react-query";

import {
  ApiRequestError,
  fetchHostOrganizations,
  fetchMatchingWeights,
  fetchMeetings,
  fetchMySpeakerRequests,
  fetchOutreachDrafts,
  fetchOutreachSends,
  fetchOwnHostOrganization,
  fetchOwnRedemptions,
  fetchReviewItems,
  fetchRewardCatalog,
  fetchSpeakerContacts,
  fetchSpeakerInvitationBatches,
  fetchSpeakerRequests,
  fetchStudentAgenda,
  fetchStudentEvents,
  fetchUnitEvents,
  type HostOwnOrganization,
} from "@/lib/api";
import { scopedQueryKey } from "@/lib/queryClient";

/** Meetings page's own page-size constant (`PAGE_LIMIT` there). */
const MEETINGS_PAGE_LIMIT = 50;

type PrefetchSpec = {
  readonly resource: string;
  readonly params: (unitId: string) => readonly unknown[];
  readonly queryFn: (unitId: string) => Promise<unknown>;
};

function spec(
  resource: string,
  params: (unitId: string) => readonly unknown[],
  queryFn: (unitId: string) => Promise<unknown>,
): PrefetchSpec {
  return { resource, params, queryFn };
}

/**
 * The 404→"none" mapping the volunteer pages' `own-host-organization` query
 * applies, mirrored so a prefetch fills the slot with the same shape the
 * pages' own queryFn would — a prefetched `HostOwnOrganization` and a
 * page-fetched one are interchangeable, and a 404 prefetches to `"none"`
 * rather than an error the page would have to re-resolve.
 */
async function fetchOwnHostOrganizationOrNone(
  unitId: string,
): Promise<HostOwnOrganization | "none"> {
  try {
    return await fetchOwnHostOrganization(unitId);
  } catch (cause) {
    if (cause instanceof ApiRequestError && cause.code === "host_organization_not_found") {
      return "none";
    }
    throw cause;
  }
}

const COORDINATOR_PREFETCH: Readonly<Record<string, readonly PrefetchSpec[]>> = {
  "/coordinator-portal/speaker-requests": [
    spec("speaker-requests", (u) => [u], (u) => fetchSpeakerRequests(u)),
    spec("host-organizations", (u) => [u], (u) => fetchHostOrganizations(u)),
  ],
  "/coordinator-portal/review-queue": [
    spec("review-items", (u) => [u, "pending"], (u) => fetchReviewItems(u, "pending")),
  ],
  "/coordinator-portal/events": [
    spec("unit-events", (u) => [u], (u) => fetchUnitEvents(u)),
  ],
  "/coordinator-portal/invitations": [
    spec("invitation-batches", (u) => [u], (u) => fetchSpeakerInvitationBatches(u)),
  ],
  "/coordinator-portal/meetings": [
    spec("meetings", (u) => [u, MEETINGS_PAGE_LIMIT], (u) => fetchMeetings(u, MEETINGS_PAGE_LIMIT)),
  ],
  "/coordinator-portal/speaker-contacts": [
    spec("speaker-contacts", (u) => [u], (u) => fetchSpeakerContacts(u)),
  ],
  "/coordinator-portal/matching-weights": [
    spec("matching-weights", (u) => [u], (u) => fetchMatchingWeights(u)),
  ],
  "/coordinator-portal/match-runs": [
    spec("speaker-requests", (u) => [u], (u) => fetchSpeakerRequests(u)),
    spec("speaker-contacts", (u) => [u], (u) => fetchSpeakerContacts(u)),
  ],
  "/coordinator-portal/outreach": [
    spec("outreach-drafts", (u) => [u], async (u) => (await fetchOutreachDrafts(u)).drafts),
    spec("outreach-sends", (u) => [u], async (u) => (await fetchOutreachSends(u)).sends),
    spec("invitation-batches", (u) => [u], (u) => fetchSpeakerInvitationBatches(u)),
  ],
};

const STUDENT_PREFETCH: Readonly<Record<string, readonly PrefetchSpec[]>> = {
  "/student-portal": [
    spec("student-agenda", (u) => [u], (u) => fetchStudentAgenda(u)),
    spec("reward-catalog", (u) => [u], (u) => fetchRewardCatalog(u)),
  ],
  "/student-portal/events": [
    spec("student-events", (u) => [u], (u) => fetchStudentEvents(u)),
    spec("student-agenda", (u) => [u], (u) => fetchStudentAgenda(u)),
  ],
  "/student-portal/history": [
    spec("student-agenda", (u) => [u], (u) => fetchStudentAgenda(u)),
    spec("reward-catalog", (u) => [u], (u) => fetchRewardCatalog(u)),
  ],
  "/student-portal/speaker-feedback": [
    spec("student-agenda", (u) => [u], (u) => fetchStudentAgenda(u)),
  ],
  "/student-portal/rewards": [
    spec("reward-catalog", (u) => [u], (u) => fetchRewardCatalog(u)),
    spec("own-redemptions", (u) => [u], (u) => fetchOwnRedemptions(u)),
  ],
};

const VOLUNTEER_PREFETCH: Readonly<Record<string, readonly PrefetchSpec[]>> = {
  "/volunteer-portal": [
    spec("my-speaker-requests", (u) => [u], (u) => fetchMySpeakerRequests(u)),
    spec("own-host-organization", (u) => [u], (u) => fetchOwnHostOrganizationOrNone(u)),
  ],
  "/volunteer-portal/my-requests": [
    spec("my-speaker-requests", (u) => [u], (u) => fetchMySpeakerRequests(u)),
  ],
  "/volunteer-portal/organization": [
    spec("own-host-organization", (u) => [u], (u) => fetchOwnHostOrganizationOrNone(u)),
  ],
};

const PORTAL_PREFETCH: Readonly<Record<string, readonly PrefetchSpec[]>> = {
  ...COORDINATOR_PREFETCH,
  ...STUDENT_PREFETCH,
  ...VOLUNTEER_PREFETCH,
};

/**
 * Fires the prefetch specs registered for `href`. A no-op for routes with no
 * entry, for a missing unit, or while the principal key is still resolving —
 * in every case the destination page's own queries remain the authority.
 */
export function prefetchPortalRoute(
  client: QueryClient,
  principalKey: string | null,
  unitId: string | null,
  href: string,
): void {
  if (principalKey === null || unitId === null) {
    return;
  }
  for (const { resource, params, queryFn } of PORTAL_PREFETCH[href] ?? []) {
    void client.prefetchQuery({
      queryKey: scopedQueryKey(principalKey, resource, ...params(unitId)),
      queryFn: () => queryFn(unitId),
    });
  }
}
