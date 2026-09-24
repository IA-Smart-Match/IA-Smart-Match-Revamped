/**
 * The coordinator Bookings page (B26 T8a), against a stubbed `fetch`.
 *
 * The page reads `GET /v1/units/{unit_id}/cba/confirmed-speakers` and the unit's
 * events, and writes `POST …/pipeline-records/{id}/cancellation`. The stub
 * answers exactly those; assertions check the requests the page made.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CoordinatorBookings } from "./CoordinatorBookings";

const UNIT = "11111111-1111-4111-8111-111111111111";
const EVENT = "22222222-2222-4222-8222-222222222222";
const LIST = `/v1/units/${UNIT}/cba/confirmed-speakers`;
const EVENTS = `/v1/units/${UNIT}/events`;
const cancelUrl = (recordId: string) =>
  `/v1/units/${UNIT}/pipeline-records/${recordId}/cancellation`;

const principal = vi.hoisted(() => ({ key: "principal-1" }));

vi.mock("../../hooks/usePortalAccess", () => ({
  usePortalAccess: () => ({
    status: "ready",
    mapping: {
      portals: [
        {
          portal: "coordinator",
          display_name: "Connector Dashboard",
          home_path: "/coordinator-portal",
          role: "coordinator",
          roles: ["coordinator"],
          default_unit_id: "11111111-1111-4111-8111-111111111111",
          org_unit_path: "/cba/finance",
        },
      ],
    },
  }),
}));

vi.mock("../../components/PrincipalQueryProvider", () => ({
  usePrincipalKey: () => principal.key,
}));

type Answer = { body: unknown; status?: number };
type Responder = Answer | (() => Answer | Promise<Answer>);
let calls: { url: string; method: string }[] = [];

function stub(answers: Record<string, Responder>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit) => {
      const method = init.method ?? "GET";
      calls.push({ url, method });
      const found = answers[`${method} ${url}`] ?? answers[`${method} ${url.split("?")[0]}`];
      const answer =
        typeof found === "function"
          ? await found()
          : (found ?? { body: { error: { code: "test_unstubbed", message: url } }, status: 404 });
      return new Response(JSON.stringify(answer.body), { status: answer.status ?? 200 });
    }),
  );
}

function speaker(recordId: string, name: string | null, attendedAt: string | null = null) {
  return {
    record_id: recordId,
    professional_id: `p-${recordId}`,
    event_id: EVENT,
    full_name: name,
    company: "Acme Analytics",
    title: "Director",
    current_stage: attendedAt === null ? "confirmed" : "attended",
    matched_at: "2026-09-01T10:00:00Z",
    contacted_at: "2026-09-02T10:00:00Z",
    confirmed_at: "2026-09-03T10:00:00Z",
    attended_at: attendedAt,
    attendance_id: attendedAt === null ? null : "att-1",
    stages: [],
  };
}

function list(speakers: ReturnType<typeof speaker>[]): Answer {
  return { body: { unit_id: UNIT, event_id: null, speakers } };
}

const eventsAnswer: Answer = {
  body: {
    unit_id: UNIT,
    events: [{ id: EVENT, title: "Analytics Careers Panel" }],
    withheld_unresolved_date: 0,
    withheld_quarantined_tags: 0,
    truncated: false,
  },
};

function cancelled(recordId: string, transitioned = true): Answer {
  return {
    body: {
      transitioned,
      already_cancelled: !transitioned,
      record: { id: recordId, cancelled_at: "2026-09-23T12:00:00Z" },
    },
  };
}

function renderPage(client?: QueryClient) {
  const queryClient =
    client ??
    new QueryClient({
      defaultOptions: { queries: { retry: false, networkMode: "always", staleTime: 0 } },
    });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/coordinator-portal/bookings"]}>
        <CoordinatorBookings />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...view, queryClient };
}

function deferred(): { promise: Promise<Answer>; resolve: (answer: Answer) => void } {
  let resolve: (answer: Answer) => void = () => undefined;
  const promise = new Promise<Answer>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

function posts(): string[] {
  return calls.filter((c) => c.method === "POST").map((c) => c.url);
}

async function openCancelFor(name: string) {
  const [button] = await screen.findAllByRole("button", {
    name: `Cancel booking for ${name} at Analytics Careers Panel`,
  });
  fireEvent.click(button);
  return screen.findByRole("alertdialog");
}

beforeEach(() => {
  calls = [];
  principal.key = "principal-1";
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("<CoordinatorBookings />", () => {
  it("renders loading, then the list", async () => {
    const gate = deferred();
    stub({
      [`GET ${LIST}`]: () => gate.promise,
      [`GET ${EVENTS}`]: eventsAnswer,
    });
    renderPage();

    expect(screen.getByLabelText("Loading bookings").getAttribute("aria-busy")).toBe("true");
    await act(async () => gate.resolve(list([speaker("r1", "Dana Reyes")])));

    expect((await screen.findAllByText("Dana Reyes")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Analytics Careers Panel").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Booked").length).toBeGreaterThan(0);
  });

  it("renders the empty state", async () => {
    stub({ [`GET ${LIST}`]: list([]), [`GET ${EVENTS}`]: eventsAnswer });
    renderPage();
    expect(await screen.findByText("No confirmed speakers in this unit.")).toBeTruthy();
  });

  it("renders the server's error with Retry", async () => {
    let fail = true;
    stub({
      [`GET ${LIST}`]: () =>
        fail
          ? { body: { error: { code: "boom", message: "The database is resting." } }, status: 500 }
          : list([speaker("r1", "Dana Reyes")]),
      [`GET ${EVENTS}`]: eventsAnswer,
    });
    renderPage();

    const alert = await screen.findByRole("alert", {}, { timeout: 3000 });
    expect(alert.textContent).toContain("The database is resting.");
    fail = false;
    fireEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    expect((await screen.findAllByText("Dana Reyes")).length).toBeGreaterThan(0);
  });

  it("renders 403 as a refusal", async () => {
    stub({
      [`GET ${LIST}`]: {
        body: { error: { code: "forbidden", message: "Not in this unit." } },
        status: 403,
      },
      [`GET ${EVENTS}`]: eventsAnswer,
    });
    renderPage();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("The server refused this request (403).");
    expect(alert.textContent).toContain("Not in this unit.");
  });

  it("Cancel opens an alertdialog focused on Keep booking", async () => {
    stub({ [`GET ${LIST}`]: list([speaker("r1", "Dana Reyes")]), [`GET ${EVENTS}`]: eventsAnswer });
    renderPage();
    const dialog = await openCancelFor("Dana Reyes");

    expect(within(dialog).getByText("Cancel this booking?")).toBeTruthy();
    await waitFor(() =>
      expect(document.activeElement).toBe(
        within(dialog).getByRole("button", { name: "Keep booking" }),
      ),
    );
  });

  it("Escape closes it and sends nothing", async () => {
    stub({ [`GET ${LIST}`]: list([speaker("r1", "Dana Reyes")]), [`GET ${EVENTS}`]: eventsAnswer });
    renderPage();
    const dialog = await openCancelFor("Dana Reyes");

    fireEvent.keyDown(dialog, { key: "Escape" });

    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(posts()).toEqual([]);
  });

  it("confirm sends exactly one POST and disables while pending", async () => {
    const gate = deferred();
    stub({
      [`GET ${LIST}`]: list([speaker("r1", "Dana Reyes")]),
      [`GET ${EVENTS}`]: eventsAnswer,
      [`POST ${cancelUrl("r1")}`]: () => gate.promise,
    });
    renderPage();
    const dialog = await openCancelFor("Dana Reyes");

    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel booking" }));
    const busy = await within(dialog).findByRole("button", { name: "Cancelling…" });
    expect((busy as HTMLButtonElement).disabled).toBe(true);
    expect(
      (within(dialog).getByRole("button", { name: "Keep booking" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    fireEvent.click(busy);

    expect(posts()).toEqual([cancelUrl("r1")]);
    await act(async () => gate.resolve(cancelled("r1")));
  });

  it("success announces in role=status and re-reads the list", async () => {
    let gone = false;
    stub({
      [`GET ${LIST}`]: () => list(gone ? [] : [speaker("r1", "Dana Reyes")]),
      [`GET ${EVENTS}`]: eventsAnswer,
      [`POST ${cancelUrl("r1")}`]: () => {
        gone = true;
        return cancelled("r1");
      },
    });
    renderPage();
    const dialog = await openCancelFor("Dana Reyes");
    const readsBefore = calls.filter((c) => c.url.startsWith(LIST)).length;

    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel booking" }));

    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Booking cancelled."));
    expect(calls.filter((c) => c.url.startsWith(LIST)).length).toBeGreaterThan(readsBefore);
    expect(await screen.findByText("No confirmed speakers in this unit.")).toBeTruthy();
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("already-cancelled response announces nothing changed", async () => {
    stub({
      [`GET ${LIST}`]: list([speaker("r1", "Dana Reyes")]),
      [`GET ${EVENTS}`]: eventsAnswer,
      [`POST ${cancelUrl("r1")}`]: cancelled("r1", false),
    });
    renderPage();
    const dialog = await openCancelFor("Dana Reyes");

    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel booking" }));

    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe("Already cancelled — nothing changed."),
    );
  });

  it("409 attended keeps the dialog open with role=alert", async () => {
    stub({
      [`GET ${LIST}`]: list([speaker("r1", "Dana Reyes")]),
      [`GET ${EVENTS}`]: eventsAnswer,
      [`POST ${cancelUrl("r1")}`]: {
        body: { error: { code: "pipeline_booking_already_attended", message: "server words" } },
        status: 409,
      },
    });
    renderPage();
    const dialog = await openCancelFor("Dana Reyes");

    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel booking" }));

    await waitFor(() =>
      expect(within(dialog).getByRole("alert").textContent).toBe(
        "This speaker already presented. An attended booking cannot be cancelled.",
      ),
    );
    expect(screen.getByRole("alertdialog")).toBeTruthy();
  });

  it("presented rows have no Cancel button", async () => {
    stub({
      [`GET ${LIST}`]: list([speaker("r2", "Sam Lee", "2026-09-10T18:00:00Z")]),
      [`GET ${EVENTS}`]: eventsAnswer,
    });
    renderPage();

    expect((await screen.findAllByText("Sam Lee")).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/^Presented /).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /Cancel booking for/ })).toBeNull();
  });

  it("query keys are isolated per principal", async () => {
    stub({ [`GET ${LIST}`]: list([speaker("r1", "Dana Reyes")]), [`GET ${EVENTS}`]: eventsAnswer });
    const { queryClient } = renderPage();
    await screen.findAllByText("Dana Reyes");

    expect(queryClient.getQueryData(["principal-1", "confirmed-speakers", UNIT, "all"])).toBeTruthy();
    expect(queryClient.getQueryData(["principal-2", "confirmed-speakers", UNIT, "all"])).toBe(
      undefined,
    );
  });

  it("while pending, Escape and an outside click do not close the dialog", async () => {
    const gate = deferred();
    stub({
      [`GET ${LIST}`]: list([speaker("r1", "Dana Reyes")]),
      [`GET ${EVENTS}`]: eventsAnswer,
      [`POST ${cancelUrl("r1")}`]: () => gate.promise,
    });
    renderPage();
    const dialog = await openCancelFor("Dana Reyes");
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel booking" }));
    await within(dialog).findByRole("button", { name: "Cancelling…" });

    fireEvent.keyDown(dialog, { key: "Escape" });
    fireEvent.pointerDown(document.body);

    expect(screen.getByRole("alertdialog")).toBeTruthy();
    await act(async () => gate.resolve(cancelled("r1")));
  });

  it("after a successful cancel, focus moves to the page heading because the row is gone", async () => {
    let gone = false;
    stub({
      [`GET ${LIST}`]: () => list(gone ? [] : [speaker("r1", "Dana Reyes")]),
      [`GET ${EVENTS}`]: eventsAnswer,
      [`POST ${cancelUrl("r1")}`]: () => {
        gone = true;
        return cancelled("r1");
      },
    });
    renderPage();
    const dialog = await openCancelFor("Dana Reyes");

    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel booking" }));

    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByRole("heading", { level: 1 })),
    );
  });

  it("the dialog's aria-describedby resolves to both the description and the error", async () => {
    stub({ [`GET ${LIST}`]: list([speaker("r1", "Dana Reyes")]), [`GET ${EVENTS}`]: eventsAnswer });
    renderPage();
    const dialog = await openCancelFor("Dana Reyes");

    const ids = (dialog.getAttribute("aria-describedby") ?? "").split(" ");
    expect(ids).toEqual(["booking-cancel-desc", "booking-cancel-error"]);
    for (const id of ids) {
      expect(document.getElementById(id)).not.toBeNull();
    }
    expect(document.getElementById("booking-cancel-desc")?.textContent).toContain(
      "Dana Reyes will no longer count as booked for Analytics Careers Panel",
    );
  });

  it("success invalidates the confirmed-speakers prefix and the unit metrics key", async () => {
    stub({
      [`GET ${LIST}`]: list([speaker("r1", "Dana Reyes")]),
      [`GET ${EVENTS}`]: eventsAnswer,
      [`POST ${cancelUrl("r1")}`]: cancelled("r1"),
    });
    const { queryClient } = renderPage();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const dialog = await openCancelFor("Dana Reyes");

    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel booking" }));

    await waitFor(() => expect(spy).toHaveBeenCalledTimes(2));
    const keys = spy.mock.calls.map(([filters]) => filters?.queryKey);
    expect(keys).toEqual([
      ["principal-1", "confirmed-speakers", UNIT],
      ["principal-1", "metrics", UNIT],
    ]);
  });
});
