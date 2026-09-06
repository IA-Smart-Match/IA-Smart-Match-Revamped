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
import { portalGrant } from "../src/lib/principal.ts";

test("portal access comes only from the server-provided mapping", () => {
  const coordinator = {
    portal: "coordinator" as const,
    display_name: "Event coordinator portal",
    home_path: "/coordinator-portal",
    role: "coordinator",
    org_unit_path: "iawest.cpp",
    units: [],
    default_unit_id: null,
  };
  const mapping = { portals: [coordinator], default_portal: "coordinator" };

  assert.equal(portalGrant(mapping, "coordinator"), coordinator);
  assert.equal(portalGrant(mapping, "student"), null);
  assert.equal(portalGrant(mapping, "volunteer"), null);
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
