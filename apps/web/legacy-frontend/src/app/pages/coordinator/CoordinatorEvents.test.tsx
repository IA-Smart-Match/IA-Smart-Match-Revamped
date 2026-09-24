/**
 * B26 T8d V-H (plan §2 row 18): an event edit can add the end time an
 * engagement lacked, which changes a Speaker's load band, so a successful edit
 * also invalidates the unit's `speaker-availability` prefix. A new draft has
 * no engagement yet and invalidates only the event list.
 */
import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { invalidateAfterEventSave } from "./CoordinatorEvents";

const UNIT = "11111111-1111-4111-8111-111111111111";

function spiedClient() {
  const client = new QueryClient();
  const spy = vi.spyOn(client, "invalidateQueries");
  return { client, spy };
}

describe("invalidateAfterEventSave", () => {
  it("an event edit invalidates the unit's speaker-availability prefix; a new draft does not", async () => {
    const edit = spiedClient();
    await invalidateAfterEventSave(edit.client, {
      principalKey: "principal-1",
      unitId: UNIT,
      edited: true,
    });
    expect(edit.spy.mock.calls.map(([filters]) => filters?.queryKey)).toEqual([
      ["principal-1", "unit-events", UNIT],
      ["principal-1", "speaker-availability", UNIT],
    ]);

    const draft = spiedClient();
    await invalidateAfterEventSave(draft.client, {
      principalKey: "principal-1",
      unitId: UNIT,
      edited: false,
    });
    expect(draft.spy.mock.calls.map(([filters]) => filters?.queryKey)).toEqual([
      ["principal-1", "unit-events", UNIT],
    ]);
  });
});
