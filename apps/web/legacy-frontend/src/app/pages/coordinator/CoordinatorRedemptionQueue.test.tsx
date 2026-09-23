/**
 * The coordinator redemption queue, against a stubbed `fetch`.
 *
 * Every test here is a sentence from the design doc's state matrix
 * (`docs/design/coordinator-redemption-queue.md` §5). The page reads
 * `GET /v1/units/{unit_id}/redemptions/queue` and writes
 * `POST …/redemptions/{id}/decision`, and nothing else; the stub answers
 * exactly those, and the assertions check the request the page made rather
 * than trusting what it drew.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CoordinatorRedemptionQueue } from "./CoordinatorRedemptionQueue";

const UNIT = "11111111-1111-4111-8111-111111111111";
const QUEUE = `/v1/units/${UNIT}/redemptions/queue`;

vi.mock("../../hooks/useSession", () => ({
  useAuthenticatedPrincipal: () => ({
    user_id: "u1",
    tenant_id: "t1",
    email: "connector@example.edu",
    suspended: false,
    memberships: [],
  }),
}));

// Mutable so one test can take the unit away; `vi.hoisted` because the mock
// factory is hoisted above every other statement in this file.
const portal = vi.hoisted(() => ({
  unitId: "11111111-1111-4111-8111-111111111111" as string | null,
}));

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
          default_unit_id: portal.unitId,
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
let calls: { url: string; init: RequestInit }[] = [];

function stub(answers: Record<string, Answer | (() => Answer)>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => {
      calls.push({ url, init });
      const method = init.method ?? "GET";
      const withQuery = `${method} ${url}`;
      const path = `${method} ${url.split("?")[0]}`;
      const found = answers[withQuery] ?? answers[path];
      const answer =
        typeof found === "function"
          ? found()
          : (found ?? {
              body: { error: { code: "test_unstubbed", message: url } },
              status: 404,
            });
      return Promise.resolve(
        new Response(JSON.stringify(answer.body), { status: answer.status ?? 200 }),
      );
    }),
  );
}

function ticket(
  id: string,
  item_name: string,
  state: "requested" | "approved" | "fulfilled" | "denied" | "expired",
  points_cost = 300,
) {
  return {
    redemption_id: id,
    item_name,
    points_cost,
    state,
    requested_at: "2026-09-18T09:12:00Z",
  };
}

function queue(
  status: string,
  redemptions: ReturnType<typeof ticket>[],
  truncated = false,
): Answer {
  return { body: { unit_id: UNIT, status, redemptions, truncated } };
}

function renderPage(staleTime = 0) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, networkMode: "always", staleTime } },
  });
  return render(
    <QueryClientProvider client={client}>
      <CoordinatorRedemptionQueue />
    </QueryClientProvider>,
  );
}

function queueCalls(): string[] {
  return calls.filter((c) => (c.init.method ?? "GET") === "GET").map((c) => c.url);
}

beforeEach(() => {
  calls = [];
  portal.unitId = UNIT;
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("<CoordinatorRedemptionQueue />", () => {
  it("asks for the requested queue by default and renders its rows", async () => {
    stub({
      [`GET ${QUEUE}?status=requested`]: queue("requested", [
        ticket("r1", "Bronco Bookstore $10 Gift Card", "requested", 300),
        ticket("r2", "CBA Career Closet Voucher", "requested", 600),
      ]),
    });
    renderPage();
    expect(await screen.findAllByText("Bronco Bookstore $10 Gift Card")).not.toHaveLength(0);
    expect(screen.getAllByText("CBA Career Closet Voucher")).not.toHaveLength(0);
    expect(screen.getAllByText("600 points")).not.toHaveLength(0);
    expect(queueCalls()[0]).toBe(`${QUEUE}?status=requested`);
    // The selected tab carries the loaded count; nothing else carries a number.
    expect(screen.getByRole("button", { name: /^Requested \(2\)/ })).toBeDefined();
    expect(screen.getByRole("button", { name: "Approved" })).toBeDefined();
  });

  it("renders no count before the response has loaded", () => {
    stub({ [`GET ${QUEUE}?status=requested`]: () => queue("requested", []) });
    renderPage();
    expect(screen.getByRole("button", { name: "Requested" })).toBeDefined();
    expect(screen.queryByText(/\(0\)/)).toBeNull();
    expect(screen.getByRole("status").textContent).toMatch(/Loading requested tickets/);
  });

  it("switching the filter refetches with that status", async () => {
    stub({
      [`GET ${QUEUE}?status=requested`]: queue("requested", []),
      [`GET ${QUEUE}?status=approved`]: queue("approved", [
        ticket("a1", "Professional Headshot Session", "approved", 1000),
      ]),
    });
    renderPage();
    await screen.findByText(/No tickets waiting/);
    fireEvent.click(screen.getByRole("button", { name: "Approved" }));
    expect(await screen.findAllByText("Professional Headshot Session")).not.toHaveLength(0);
    expect(queueCalls()).toContain(`${QUEUE}?status=approved`);
    expect(screen.getByRole("button", { name: /^Approved \(1\)/ })).toBeDefined();
  });

  it("offers only the actions the state machine permits", async () => {
    stub({
      [`GET ${QUEUE}?status=requested`]: queue("requested", [
        ticket("r1", "Gift Card", "requested"),
      ]),
      [`GET ${QUEUE}?status=approved`]: queue("approved", [ticket("a1", "Voucher", "approved")]),
      [`GET ${QUEUE}?status=fulfilled`]: queue("fulfilled", [
        ticket("f1", "Headshot", "fulfilled"),
      ]),
    });
    renderPage();
    await screen.findAllByText("Gift Card");
    expect(screen.getAllByRole("button", { name: "Approve Gift Card" })).not.toHaveLength(0);
    expect(screen.getAllByRole("button", { name: "Deny Gift Card" })).not.toHaveLength(0);
    expect(screen.queryByRole("button", { name: "Mark Gift Card fulfilled" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Approved" }));
    await screen.findAllByText("Voucher");
    expect(screen.getAllByRole("button", { name: "Mark Voucher fulfilled" })).not.toHaveLength(0);
    // The state machine allows approved -> fulfilled | expired only; a Deny
    // here could only ever answer 409.
    expect(screen.queryByRole("button", { name: "Deny Voucher" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Approve Voucher" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Fulfilled" }));
    await screen.findAllByText("Headshot");
    expect(screen.queryByRole("button", { name: /Headshot/ })).toBeNull();
    expect(screen.getAllByText(/No further decision is possible/)).not.toHaveLength(0);
  });

  it("Approve posts {decision: approved}, disables the row until the reload lands, then announces", async () => {
    let decided = false;
    stub({
      [`GET ${QUEUE}?status=requested`]: () =>
        decided ? queue("requested", []) : queue("requested", [ticket("r1", "Gift Card", "requested")]),
      [`POST /v1/units/${UNIT}/redemptions/r1/decision`]: () => {
        decided = true;
        return {
          body: {
            redemption_id: "r1",
            item_id: "i1",
            item_name: "Gift Card",
            points_cost: 300,
            state: "approved",
          },
        };
      },
    });
    renderPage();
    const approve = (await screen.findAllByRole("button", { name: "Approve Gift Card" }))[0];
    fireEvent.click(approve);
    expect(approve.hasAttribute("disabled")).toBe(true);
    await screen.findByText(/No tickets waiting/);
    const post = calls.find((c) => c.init.method === "POST");
    expect(post?.url).toBe(`/v1/units/${UNIT}/redemptions/r1/decision`);
    expect(JSON.parse(String(post?.init.body))).toEqual({ decision: "approved" });
    expect(screen.getByText("Gift Card approved.")).toBeDefined();
  });

  it("a decision re-reads every status tab, not only the one it was made on", async () => {
    let decided = false;
    stub({
      [`GET ${QUEUE}?status=requested`]: () =>
        decided ? queue("requested", []) : queue("requested", [ticket("r1", "Gift Card", "requested")]),
      [`GET ${QUEUE}?status=approved`]: () =>
        decided ? queue("approved", [ticket("r1", "Gift Card", "approved")]) : queue("approved", []),
      [`POST /v1/units/${UNIT}/redemptions/r1/decision`]: () => {
        decided = true;
        return {
          body: {
            redemption_id: "r1",
            item_id: "i1",
            item_name: "Gift Card",
            points_cost: 300,
            state: "approved",
          },
        };
      },
    });
    // The app's real staleTime: without invalidation the Approved tab's
    // empty read would be served from cache as fresh.
    renderPage(30_000);
    await screen.findAllByText("Gift Card");
    fireEvent.click(screen.getByRole("button", { name: "Approved" }));
    await screen.findByText(/No approved tickets/);
    fireEvent.click(screen.getByRole("button", { name: "Requested" }));
    fireEvent.click((await screen.findAllByRole("button", { name: "Approve Gift Card" }))[0]);
    await screen.findByText(/No tickets waiting/);

    fireEvent.click(screen.getByRole("button", { name: "Approved" }));
    expect(await screen.findAllByText("Gift Card")).not.toHaveLength(0);
    expect(screen.queryByText(/No approved tickets/)).toBeNull();
  });

  it("Deny asks for an inline confirmation before posting", async () => {
    stub({
      [`GET ${QUEUE}?status=requested`]: queue("requested", [ticket("r1", "Gift Card", "requested")]),
      [`POST /v1/units/${UNIT}/redemptions/r1/decision`]: {
        body: {
          redemption_id: "r1",
          item_id: "i1",
          item_name: "Gift Card",
          points_cost: 300,
          state: "denied",
        },
      },
    });
    renderPage();
    fireEvent.click((await screen.findAllByRole("button", { name: "Deny Gift Card" }))[0]);
    expect(calls.some((c) => c.init.method === "POST")).toBe(false);
    expect(screen.getAllByRole("button", { name: "Confirm deny Gift Card" })).not.toHaveLength(0);
    fireEvent.click(screen.getAllByRole("button", { name: "Keep Gift Card" })[0]);
    expect(screen.queryByRole("button", { name: "Confirm deny Gift Card" })).toBeNull();
    expect(calls.some((c) => c.init.method === "POST")).toBe(false);

    fireEvent.click((await screen.findAllByRole("button", { name: "Deny Gift Card" }))[0]);
    fireEvent.click(screen.getAllByRole("button", { name: "Confirm deny Gift Card" })[0]);
    await waitFor(() => expect(calls.some((c) => c.init.method === "POST")).toBe(true));
    const post = calls.find((c) => c.init.method === "POST");
    expect(JSON.parse(String(post?.init.body))).toEqual({ decision: "denied" });
  });

  it("a 409 is shown as a conflict sentence and the queue is re-read", async () => {
    stub({
      [`GET ${QUEUE}?status=requested`]: queue("requested", [ticket("r1", "Gift Card", "requested")]),
      [`POST /v1/units/${UNIT}/redemptions/r1/decision`]: {
        status: 409,
        body: {
          error: {
            code: "invalid_redemption_transition",
            message: "cannot move denied -> approved",
          },
        },
      },
    });
    renderPage();
    fireEvent.click((await screen.findAllByRole("button", { name: "Approve Gift Card" }))[0]);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/Someone already decided this ticket/);
    expect(alert.textContent).toMatch(/cannot move denied -> approved/);
    await waitFor(() => expect(queueCalls().length).toBeGreaterThanOrEqual(2));
  });

  it("a 403 on the read is the server's sentence and the filter stays usable", async () => {
    stub({
      [`GET ${QUEUE}?status=requested`]: {
        status: 403,
        body: { error: { code: "forbidden", message: "This account may not read this unit's queue." } },
      },
      [`GET ${QUEUE}?status=denied`]: queue("denied", []),
    });
    renderPage();
    expect((await screen.findByRole("alert")).textContent).toBe(
      "This account may not read this unit's queue.",
    );
    expect(screen.queryByText(/\(0\)/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Denied" }));
    await screen.findByText(/No denied tickets/);
  });

  it("a 429 renders the server's retry sentence", async () => {
    stub({
      [`GET ${QUEUE}?status=requested`]: {
        status: 429,
        body: {
          error: {
            code: "rate_limited",
            message: "Rate limit exceeded for 'redemption.queue.list'. Retry in 42 seconds.",
          },
        },
      },
    });
    renderPage();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/Retry in 42 seconds/);
    expect(alert.textContent).toMatch(/try again after that/);
  });

  it("a truncated response says so", async () => {
    stub({
      [`GET ${QUEUE}?status=requested`]: queue(
        "requested",
        [ticket("r1", "Gift Card", "requested")],
        true,
      ),
    });
    renderPage();
    expect((await screen.findByText(/Showing the oldest 1 tickets?/)).textContent).toMatch(
      /Decide these to see the rest/,
    );
    // The tab count is what arrived, marked as not the total.
    expect(screen.getByRole("button", { name: "Requested (1+)" })).toBeDefined();
  });

  it("an unreadable timestamp is a sentence, not a crash", async () => {
    stub({
      [`GET ${QUEUE}?status=requested`]: queue("requested", [
        { ...ticket("r1", "Gift Card", "requested"), requested_at: "not-a-date" },
      ]),
    });
    renderPage();
    await screen.findAllByText("Gift Card");
    expect(screen.getAllByText("Request time not readable")).not.toHaveLength(0);
  });

  it("empty states are per status", async () => {
    stub({
      [`GET ${QUEUE}?status=requested`]: queue("requested", []),
      [`GET ${QUEUE}?status=expired`]: queue("expired", []),
    });
    renderPage();
    expect((await screen.findByText(/No tickets waiting/)).textContent).toMatch(/anonymous/);
    fireEvent.click(screen.getByRole("button", { name: "Expired" }));
    await screen.findByText(/No expired tickets/);
  });

  it("a network failure is a sentence with a retry", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))),
    );
    renderPage();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/could not be loaded/);
    expect(screen.getByRole("button", { name: "Try again" })).toBeDefined();
  });

  it("a 5xx offers a retry; a 403 does not", async () => {
    stub({
      [`GET ${QUEUE}?status=requested`]: {
        status: 503,
        body: { error: { code: "internal_error", message: "upstream timeout" } },
      },
    });
    renderPage();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/could not answer/);
    expect(alert.textContent).not.toMatch(/upstream timeout/);
    expect(screen.getByRole("button", { name: "Try again" })).toBeDefined();
  });

  it("names the persona, not the stored role key, and moves focus to the result", async () => {
    let decided = false;
    stub({
      [`GET ${QUEUE}?status=requested`]: () =>
        decided ? queue("requested", []) : queue("requested", [ticket("r1", "Gift Card", "requested")]),
      [`POST /v1/units/${UNIT}/redemptions/r1/decision`]: () => {
        decided = true;
        return {
          body: { redemption_id: "r1", item_id: "i1", item_name: "Gift Card", points_cost: 300, state: "approved" },
        };
      },
    });
    renderPage();
    await screen.findAllByText("Gift Card");
    expect(screen.getByText(/Signed in as/).textContent).toMatch(/Speaker Connector/);
    expect(screen.getByText(/Signed in as/).textContent).not.toMatch(/· coordinator ·/);
    fireEvent.click(screen.getAllByRole("button", { name: "Approve Gift Card" })[0]);
    await screen.findByText("Gift Card approved.");
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("status")));
  });

  it("renders the absolute and relative request time", async () => {
    stub({
      [`GET ${QUEUE}?status=requested`]: queue("requested", [ticket("r1", "Gift Card", "requested")]),
    });
    renderPage();
    await screen.findAllByText("Gift Card");
    const times = document.querySelectorAll("time[datetime='2026-09-18T09:12:00Z']");
    expect(times.length).toBeGreaterThan(0);
    expect(within(times[0] as HTMLElement).getByText(/ago/)).toBeDefined();
  });

  it("Mark fulfilled posts {decision: fulfilled} and announces it", async () => {
    let decided = false;
    stub({
      [`GET ${QUEUE}?status=requested`]: queue("requested", []),
      [`GET ${QUEUE}?status=approved`]: () =>
        decided ? queue("approved", []) : queue("approved", [ticket("a1", "Voucher", "approved")]),
      [`POST /v1/units/${UNIT}/redemptions/a1/decision`]: () => {
        decided = true;
        return {
          body: { redemption_id: "a1", item_id: "i1", item_name: "Voucher", points_cost: 300, state: "fulfilled" },
        };
      },
    });
    renderPage();
    await screen.findByText(/No tickets waiting/);
    fireEvent.click(screen.getByRole("button", { name: "Approved" }));
    fireEvent.click((await screen.findAllByRole("button", { name: "Mark Voucher fulfilled" }))[0]);
    await screen.findByText(/No approved tickets/);
    const post = calls.find((c) => c.init.method === "POST");
    expect(post?.url).toBe(`/v1/units/${UNIT}/redemptions/a1/decision`);
    expect(JSON.parse(String(post?.init.body))).toEqual({ decision: "fulfilled" });
    expect(screen.getByText("Voucher marked fulfilled.")).toBeDefined();
  });

  it("with no unit on the grant it says so and reads nothing", async () => {
    portal.unitId = null;
    stub({});
    renderPage();
    expect(
      screen.getByText(
        "The server has not assigned this account a unit, so there is no redemption queue to show.",
      ),
    ).toBeDefined();
    // No loading sentence either: nothing is being loaded.
    expect(screen.getByRole("status").textContent).toBe("");
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(calls).toHaveLength(0);
  });

  it.each([
    [403, "forbidden", "This account may not decide tickets in this unit."],
    [404, "redemption_not_found", "No such redemption."],
  ])(
    "a %i on the decision is the server's sentence and the queue is re-read",
    async (status, code, message) => {
      stub({
        [`GET ${QUEUE}?status=requested`]: queue("requested", [ticket("r1", "Gift Card", "requested")]),
        [`POST /v1/units/${UNIT}/redemptions/r1/decision`]: { status, body: { error: { code, message } } },
      });
      renderPage();
      fireEvent.click((await screen.findAllByRole("button", { name: "Approve Gift Card" }))[0]);
      const alert = await screen.findByRole("alert");
      expect(alert.textContent).toBe(message);
      expect(alert.textContent).not.toMatch(/Someone already decided/);
      await waitFor(() => expect(queueCalls().length).toBeGreaterThanOrEqual(2));
    },
  );

  it("Keep returns focus to the Deny button", async () => {
    stub({
      [`GET ${QUEUE}?status=requested`]: queue("requested", [ticket("r1", "Gift Card", "requested")]),
    });
    renderPage();
    fireEvent.click((await screen.findAllByRole("button", { name: "Deny Gift Card" }))[0]);
    await waitFor(() =>
      expect(document.activeElement?.getAttribute("aria-label")).toBe("Confirm deny Gift Card"),
    );
    fireEvent.click(screen.getAllByRole("button", { name: "Keep Gift Card" })[0]);
    await waitFor(() =>
      expect(document.activeElement?.getAttribute("aria-label")).toBe("Deny Gift Card"),
    );
  });
});
