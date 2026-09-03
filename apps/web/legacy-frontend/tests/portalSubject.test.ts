import assert from "node:assert/strict";
import test from "node:test";

import {
  PortalSubjectUnavailableError,
  fetchCoordinatorEvents,
  fetchCoordinatorMeetings,
  fetchCoordinatorProfile,
  fetchCoordinatorThreads,
  fetchStudentConnectionSuggestions,
  fetchStudentNudge,
  fetchStudentProfile,
  fetchStudentRecommendations,
  fetchStudentRegistrations,
  fetchVolunteerAssignments,
  fetchVolunteerProfile,
} from "../src/lib/api.ts";
import { portalSubjectId } from "../src/lib/principal.ts";

const me = {
  user_id: "1c83eb7d-f38d-4a9c-9dcb-08cb7d28c38a",
  tenant_id: "1bdb8fec-a535-47ff-9396-861542cc4ac8",
  email: "verified@example.invalid",
  suspended: false,
  memberships: [],
};

test("an account UUID is never reused as a legacy portal record id", () => {
  assert.equal(portalSubjectId(me, "student"), null);
  assert.equal(portalSubjectId(me, "coordinator"), null);
  assert.equal(portalSubjectId(me, "volunteer"), null);
});

type PortalRequest = (subjectId: string) => Promise<unknown>;

const portalRequests: PortalRequest[] = [
  fetchStudentProfile,
  fetchStudentRegistrations,
  fetchStudentConnectionSuggestions,
  fetchStudentRecommendations,
  fetchStudentNudge,
  fetchCoordinatorProfile,
  fetchCoordinatorThreads,
  fetchCoordinatorMeetings,
  fetchCoordinatorEvents,
  fetchVolunteerProfile,
  fetchVolunteerAssignments,
];

test("an unresolved portal subject is rejected before any legacy request", async () => {
  const originalFetch = globalThis.fetch;
  let fetchCalls = 0;
  globalThis.fetch = async () => {
    fetchCalls += 1;
    return new Response("unexpected request", { status: 500 });
  };

  try {
    for (const request of portalRequests) {
      await assert.rejects(request(""), PortalSubjectUnavailableError);
    }
    assert.equal(fetchCalls, 0);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
