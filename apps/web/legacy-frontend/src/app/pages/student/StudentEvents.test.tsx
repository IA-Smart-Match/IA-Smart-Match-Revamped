/**
 * The student Events page's month grid (B09, OQ-CBA-020 option A), against a
 * stubbed `fetch`.
 *
 * The owner's ruling: a day that has events opens a panel listing them, with
 * the same Register / Cancel controls the two lists above the grid carry. So
 * every write assertion here compares the request the panel sent with the one
 * the list sends for the same event — the panel must not have a command of its
 * own. A day with no events is not a control at all, the way an unmeasured
 * pipeline card has no button (B41).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { StudentEvent } from "../../../lib/api";
import { StudentEvents } from "./StudentEvents";

const UNIT = "22222222-2222-4222-8222-222222222222";
const CATALOG = `/v1/units/${UNIT}/student/events`;
const AGENDA = `/v1/units/${UNIT}/student/agenda`;
const registrationPath = (eventId: string) =>
  `/v1/units/${UNIT}/student/events/${eventId}/registration`;

vi.mock("../../hooks/useSession", () => ({
  useAuthenticatedPrincipal: () => ({
    user_id: "u1",
    tenant_id: "t1",
    email: "student@example.edu",
    suspended: false,
    memberships: [],
  }),
}));

vi.mock("../../hooks/usePortalAccess", () => ({
  usePortalAccess: () => ({
    status: "ready",
    mapping: {
      portals: [
        {
          portal: "student",
          display_name: "Student Portal",
          home_path: "/student-portal",
          role: "student",
          roles: ["student"],
          default_unit_id: UNIT,
          org_unit_path: "/cba/finance",
        },
      ],
    },
  }),
}));

vi.mock("@/app/components/PrincipalQueryProvider", () => ({
  usePrincipalKey: () => "principal-1",
}));

type Answer = { body: unknown; status?: number };
let calls: { url: string; method: string }[] = [];

function stub(answers: Record<string, Answer | (() => Answer)>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => {
      const method = init.method ?? "GET";
      calls.push({ url, method });
      const found = answers[`${method} ${url.split("?")[0]}`];
      const answer =
        typeof found === "function"
          ? found()
          : (found ?? { body: { error: { code: "test_unstubbed", message: url } }, status: 404 });
      return Promise.resolve(
        new Response(JSON.stringify(answer.body), { status: answer.status ?? 200 }),
      );
    }),
  );
}

function studentEvent(
  id: string,
  title: string,
  onDate: string,
  registration: "registered" | "cancelled" | null = null,
): StudentEvent {
  return {
    id,
    title,
    description: null,
    time: {
      precision: "date_only",
      starts_at: null,
      ends_at: null,
      on_date: onDate,
      time_zone: null,
    },
    is_virtual: false,
    location_city: null,
    location_postal_code: null,
    tags: [],
    on_my_agenda: registration === "registered",
    registration:
      registration === null
        ? null
        : {
            status: registration,
            registered_at: "2026-09-01T10:00:00Z",
            updated_at: "2026-09-01T10:00:00Z",
          },
    calendar: { available: false, download_path: null, unavailable_reason: "event_end_unknown" },
  };
}

const CLINIC = studentEvent("e-clinic", "Resume Clinic", "2026-09-18");
const PANEL = studentEvent("e-panel", "Alumni Panel", "2026-09-18", "registered");
const MIXER = studentEvent("e-mixer", "Networking Mixer", "2026-09-25");

function reads(events: StudentEvent[]): Record<string, () => Answer> {
  return {
    [`GET ${CATALOG}`]: () => ({
      body: { unit_id: UNIT, events, withheld_unpublished: 0, truncated: false },
    }),
    [`GET ${AGENDA}`]: () => ({
      body: {
        unit_id: UNIT,
        events: events.filter((event) => event.registration?.status === "registered"),
        withheld_unresolved_date: 0,
        truncated: false,
      },
    }),
  };
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, networkMode: "always" } },
  });
  return render(
    <QueryClientProvider client={client}>
      <StudentEvents />
    </QueryClientProvider>,
  );
}

function writes(): { url: string; method: string }[] {
  return calls.filter((call) => call.method !== "GET");
}

/** The card for `title` inside `scope`, found by its heading. */
function cardIn(scope: HTMLElement, title: string): HTMLElement {
  const heading = within(scope).getByRole("heading", { name: title });
  const card = heading.closest("li");
  if (card === null) throw new Error(`no card around ${title}`);
  return card;
}

async function openDay(name: string): Promise<{ trigger: HTMLElement; dialog: HTMLElement }> {
  const trigger = await screen.findByRole("button", { name });
  fireEvent.click(trigger);
  const dialog = await screen.findByRole("dialog");
  return { trigger, dialog };
}

beforeEach(() => {
  calls = [];
  // Only `Date` is faked, so the grid opens on September 2026 while React
  // Query's and waitFor's timers keep running for real.
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 8, 10, 12, 0, 0));
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("<StudentEvents /> month calendar (B09, OQ-CBA-020 option A)", () => {
  it("names each day that has events and makes no control of an empty day", async () => {
    stub(reads([CLINIC, PANEL, MIXER]));
    renderPage();

    const busy = await screen.findByRole("button", { name: "Events on 18 September, 2 events" });
    expect(busy.tagName).toBe("BUTTON");
    expect(busy.getAttribute("type")).toBe("button");
    expect(screen.getByRole("button", { name: "Events on 25 September, 1 event" })).toBeDefined();
    expect(screen.queryByRole("button", { name: /17 September/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Events on 1 September/ })).toBeNull();
  });

  it("clicking a day opens a labelled panel listing that day's events, and only those", async () => {
    stub(reads([CLINIC, PANEL, MIXER]));
    renderPage();

    const { dialog } = await openDay("Events on 18 September, 2 events");
    expect(dialog.getAttribute("aria-labelledby")).not.toBeNull();
    expect(
      within(dialog).getByRole("heading", { name: "Events on 18 September 2026" }),
    ).toBeDefined();
    expect(within(dialog).getByRole("heading", { name: "Resume Clinic" })).toBeDefined();
    expect(within(dialog).getByRole("heading", { name: "Alumni Panel" })).toBeDefined();
    expect(within(dialog).queryByRole("heading", { name: "Networking Mixer" })).toBeNull();
    // Focus moves into the panel, so a keyboard user lands on it.
    expect(dialog.contains(document.activeElement)).toBe(true);
    // One polite live region for outcomes, and only one.
    expect(within(dialog).getAllByRole("status")).toHaveLength(1);
  });

  it("Register in the panel sends the same POST as Register in the list", async () => {
    stub({
      ...reads([CLINIC, PANEL, MIXER]),
      [`POST ${registrationPath(CLINIC.id)}`]: () => ({
        body: { unit_id: UNIT, event_id: CLINIC.id, registration: null },
      }),
    });
    renderPage();

    // Wait for the reads to land: the region exists before its cards do.
    await screen.findByRole("button", { name: "Events on 18 September, 2 events" });
    const browse = screen.getByRole("region", { name: "Browse events" });
    fireEvent.click(
      within(cardIn(browse, "Resume Clinic")).getByRole("button", { name: "Register" }),
    );
    await waitFor(() => expect(writes()).toHaveLength(1));

    const { dialog } = await openDay("Events on 18 September, 2 events");
    fireEvent.click(
      within(cardIn(dialog, "Resume Clinic")).getByRole("button", { name: "Register" }),
    );
    await waitFor(() => expect(writes()).toHaveLength(2));

    const [fromList, fromPanel] = writes();
    expect(fromList).toEqual({ url: registrationPath(CLINIC.id), method: "POST" });
    expect(fromPanel).toEqual(fromList);
  });

  it("Cancel in the panel sends the same DELETE as Cancel in the list", async () => {
    stub({
      ...reads([CLINIC, PANEL, MIXER]),
      [`DELETE ${registrationPath(PANEL.id)}`]: () => ({
        body: { unit_id: UNIT, event_id: PANEL.id, registration: null },
      }),
    });
    renderPage();

    // Wait for the reads to land: the region exists before its cards do.
    await screen.findByRole("button", { name: "Events on 18 September, 2 events" });
    const agenda = screen.getByRole("region", { name: "Your agenda" });
    fireEvent.click(
      within(cardIn(agenda, "Alumni Panel")).getByRole("button", { name: "Cancel registration" }),
    );
    await waitFor(() => expect(writes()).toHaveLength(1));

    const { dialog } = await openDay("Events on 18 September, 2 events");
    fireEvent.click(
      within(cardIn(dialog, "Alumni Panel")).getByRole("button", { name: "Cancel registration" }),
    );
    await waitFor(() => expect(writes()).toHaveLength(2));

    const [fromList, fromPanel] = writes();
    expect(fromList).toEqual({ url: registrationPath(PANEL.id), method: "DELETE" });
    expect(fromPanel).toEqual(fromList);
  });

  it("announces the outcome the re-read reports, in the panel's one live region", async () => {
    let registered = false;
    const clinicNow = () =>
      registered ? studentEvent(CLINIC.id, CLINIC.title, "2026-09-18", "registered") : CLINIC;
    stub({
      [`GET ${CATALOG}`]: () => reads([clinicNow(), PANEL])[`GET ${CATALOG}`](),
      [`GET ${AGENDA}`]: () => reads([clinicNow(), PANEL])[`GET ${AGENDA}`](),
      [`POST ${registrationPath(CLINIC.id)}`]: () => {
        registered = true;
        return { body: { unit_id: UNIT, event_id: CLINIC.id, registration: null } };
      },
    });
    renderPage();

    const { dialog } = await openDay("Events on 18 September, 2 events");
    expect(within(dialog).getByRole("status").textContent).toBe("");
    fireEvent.click(
      within(cardIn(dialog, "Resume Clinic")).getByRole("button", { name: "Register" }),
    );

    await waitFor(() =>
      expect(within(dialog).getByRole("status").textContent).toBe(
        "You have registered for Resume Clinic.",
      ),
    );
    expect(
      within(cardIn(dialog, "Resume Clinic")).getByRole("button", { name: "Cancel registration" }),
    ).toBeDefined();
  });

  it("a refused write shows the server's message on the card and announces no success", async () => {
    stub({
      ...reads([CLINIC, PANEL]),
      [`POST ${registrationPath(CLINIC.id)}`]: {
        body: {
          error: { code: "event_closed", message: "Registration for this event is closed." },
        },
        status: 409,
      },
    });
    renderPage();

    const { dialog } = await openDay("Events on 18 September, 2 events");
    fireEvent.click(
      within(cardIn(dialog, "Resume Clinic")).getByRole("button", { name: "Register" }),
    );

    expect((await within(dialog).findByRole("alert")).textContent).toMatch(/closed/);
    expect(within(dialog).getByRole("status").textContent).toBe("");
  });

  it("Escape closes the panel and returns focus to the day cell", async () => {
    stub(reads([CLINIC, PANEL, MIXER]));
    renderPage();

    const { trigger, dialog } = await openDay("Events on 18 September, 2 events");
    fireEvent.keyDown(document.activeElement ?? dialog, { key: "Escape" });

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.activeElement).toBe(trigger);
  });

  it("the Close button closes the panel and returns focus to the day cell", async () => {
    stub(reads([CLINIC, PANEL, MIXER]));
    renderPage();

    const { trigger, dialog } = await openDay("Events on 25 September, 1 event");
    fireEvent.click(within(dialog).getByRole("button", { name: "Close" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.activeElement).toBe(trigger);
  });

  it("opening a day filters nothing: both lists still show every event", async () => {
    stub(reads([CLINIC, PANEL, MIXER]));
    renderPage();

    const { dialog } = await openDay("Events on 25 September, 1 event");
    fireEvent.keyDown(document.activeElement ?? dialog, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    const browse = screen.getByRole("region", { name: "Browse events" });
    for (const title of ["Resume Clinic", "Alumni Panel", "Networking Mixer"]) {
      expect(within(browse).getByRole("heading", { name: title })).toBeDefined();
    }
    const agenda = screen.getByRole("region", { name: "Your agenda" });
    expect(within(agenda).getByRole("heading", { name: "Alumni Panel" })).toBeDefined();
  });
});
