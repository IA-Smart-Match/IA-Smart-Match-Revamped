/**
 * The Speaker Portal home (B26 T6b-4 §5.1), against a stubbed `fetch`: open
 * invitations first, then upcoming engagements; two independent reads; one
 * notice when the account is not linked; no answer buttons.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { MyEngagement, MyInvitation } from "@/lib/api";

import { SpeakerHome } from "./SpeakerHome";

const INVITATIONS = "/v1/me/invitations";
const UPCOMING = "/v1/me/engagements?when=upcoming";

// A mutable principal the mocked hook subscribes to, so a test can switch it
// and every reader re-renders, as the real provider's context would.
const principal = vi.hoisted(() => {
  const listeners = new Set<() => void>();
  return {
    key: "principal-1" as string | null,
    listeners,
    set(next: string | null) {
      this.key = next;
      for (const listener of listeners) listener();
    },
  };
});

vi.mock("@/app/components/PrincipalQueryProvider", async () => {
  const { useSyncExternalStore } = await import("react");
  return {
    usePrincipalKey: () =>
      useSyncExternalStore(
        (listener: () => void) => {
          principal.listeners.add(listener);
          return () => principal.listeners.delete(listener);
        },
        () => principal.key,
      ),
  };
});

type Answer = { body: unknown; status?: number };
type Found = Answer | (() => Answer | Promise<Answer>);
let calls: { method: string; url: string }[] = [];

function stub(answers: Record<string, Found>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit) => {
      const method = init.method ?? "GET";
      calls.push({ method, url });
      const found = answers[`${method} ${url}`];
      const answer =
        typeof found === "function"
          ? await found()
          : (found ?? { body: { error: { code: "test_unstubbed", message: url } }, status: 404 });
      return new Response(JSON.stringify(answer.body), { status: answer.status ?? 200 });
    }),
  );
}

function refusal(status: number, code: string): Answer {
  return { status, body: { error: { code, message: "server words" } } };
}

function invitation(id: string, title: string, answerable = true): MyInvitation {
  return {
    invitation_id: id,
    event: { title, date_text: `Date text of ${title}`, local_date: null, time_zone: null },
    dispatched_at: "2026-10-01T12:00:00Z",
    status: answerable ? "awaiting_response" : "accepted_invitation",
    response: answerable ? null : { recorded_at: "2026-10-02T12:00:00Z", recorded_by: "speaker" },
    answerable,
  };
}

function engagement(id: string, title: string): MyEngagement {
  return {
    engagement_id: id,
    event: {
      title,
      local_date: "2026-10-14",
      time_zone: "America/Los_Angeles",
      time_precision: "date_only",
      starts_at: null,
      ends_at: null,
    },
    state: "confirmed",
    confirmed_at: "2026-09-20T12:00:00Z",
    attended_at: null,
    cancelled_at: null,
  };
}

function invitations(rows: MyInvitation[], truncated = false): Answer {
  return { body: { invitations: rows, truncated } };
}

function upcoming(rows: MyEngagement[], truncated = false): Answer {
  return { body: { when: "upcoming", as_of: "2026-10-06", engagements: rows, truncated } };
}

let client: QueryClient;

function renderPage() {
  client = new QueryClient({
    defaultOptions: { queries: { retry: false, networkMode: "always", staleTime: 0 } },
  });
  const router = createMemoryRouter(
    [
      { path: "/speaker-portal", element: <SpeakerHome /> },
      { path: "/speaker-portal/invitations", element: <p>Invitations page</p> },
      { path: "/speaker-portal/engagements", element: <p>Engagements page</p> },
      { path: "/login", element: <p>Sign-in page</p> },
    ],
    { initialEntries: ["/speaker-portal"] },
  );
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

function section(name: string): HTMLElement {
  const heading = screen.getByRole("heading", { level: 2, name });
  const container = heading.closest("section");
  if (container === null) throw new Error(`no section ${name}`);
  return container;
}

const NOT_LINKED =
  "Your account is not linked to a Speaker profile, so there is nothing to show here. Ask your Speaker Connector to send you a new portal invitation.";

beforeEach(() => {
  calls = [];
  principal.key = "principal-1";
  document.title = "Smart Match";
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("<SpeakerHome />", () => {
  it("loads invitations and upcoming engagements and nothing else", async () => {
    stub({
      [`GET ${INVITATIONS}`]: invitations([invitation("i1", "Spring Mixer")]),
      [`GET ${UPCOMING}`]: upcoming([engagement("e1", "ACCT 4100 guest lecture")]),
    });
    renderPage();
    await screen.findByText("ACCT 4100 guest lecture");
    expect(calls.map((call) => `${call.method} ${call.url}`).sort()).toEqual(
      [`GET ${INVITATIONS}`, `GET ${UPCOMING}`].sort(),
    );
  });

  it("open invitations come before engagements in DOM order", async () => {
    stub({
      [`GET ${INVITATIONS}`]: invitations([invitation("i1", "Spring Mixer")]),
      [`GET ${UPCOMING}`]: upcoming([engagement("e1", "ACCT 4100 guest lecture")]),
    });
    renderPage();
    await screen.findByText("ACCT 4100 guest lecture");
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual(["Invitations waiting for your answer", "Your upcoming engagements"]);
  });

  it("shows answerable invitations only, at most 5, with a link to the Invitations page and no answer buttons", async () => {
    const rows = [
      ...Array.from({ length: 7 }, (_, i) => invitation(`open-${i}`, `Open event ${i}`)),
      invitation("done", "Answered event", false),
    ];
    stub({
      [`GET ${INVITATIONS}`]: invitations(rows),
      [`GET ${UPCOMING}`]: upcoming([]),
    });
    renderPage();
    await screen.findByText("Open event 0");
    const open = section("Invitations waiting for your answer");
    expect(open.textContent).toContain("7 invitations waiting for your answer");
    const titles = within(open)
      .getAllByRole("heading", { level: 3 })
      .map((h) => h.textContent);
    expect(titles).toEqual(["Open event 0", "Open event 1", "Open event 2", "Open event 3", "Open event 4"]);
    expect(open.textContent).toContain("Date text of Open event 0");
    expect(screen.queryByText("Answered event")).toBeNull();
    const link = within(open).getByRole("link", { name: "Answer on the Invitations page" });
    expect(link.getAttribute("href")).toBe("/speaker-portal/invitations");
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("says one invitation in the singular, and 'at least' when the list is truncated", async () => {
    stub({
      [`GET ${INVITATIONS}`]: invitations([invitation("i1", "Spring Mixer")], true),
      [`GET ${UPCOMING}`]: upcoming([]),
    });
    renderPage();
    await screen.findByText("Spring Mixer");
    expect(section("Invitations waiting for your answer").textContent).toContain(
      "At least 1 invitation waiting for your answer",
    );
  });

  it("each section's empty state", async () => {
    stub({
      [`GET ${INVITATIONS}`]: invitations([invitation("done", "Answered event", false)]),
      [`GET ${UPCOMING}`]: upcoming([]),
    });
    renderPage();
    expect(await screen.findByText("No invitations are waiting for your answer.")).toBeTruthy();
    expect(
      await screen.findByText(
        "No upcoming engagements. An engagement appears here once a Speaker Connector confirms you for an event.",
      ),
    ).toBeTruthy();
  });

  it("shows at most 5 upcoming engagements in server order, and a link to all", async () => {
    stub({
      [`GET ${INVITATIONS}`]: invitations([]),
      [`GET ${UPCOMING}`]: upcoming(
        Array.from({ length: 6 }, (_, i) => engagement(`e${i}`, `Engagement ${i}`)),
      ),
    });
    renderPage();
    await screen.findByText("Engagement 0");
    const upcomingSection = section("Your upcoming engagements");
    expect(
      within(upcomingSection)
        .getAllByRole("heading", { level: 3 })
        .map((h) => h.textContent),
    ).toEqual(["Engagement 0", "Engagement 1", "Engagement 2", "Engagement 3", "Engagement 4"]);
    const link = within(upcomingSection).getByRole("link", { name: "See all engagements" });
    expect(link.getAttribute("href")).toBe("/speaker-portal/engagements");
  });

  it("a failed invitations read leaves the engagements section working, with Retry", async () => {
    let attempt = 0;
    stub({
      [`GET ${INVITATIONS}`]: () => {
        attempt += 1;
        return attempt === 1
          ? refusal(500, "internal_error")
          : invitations([invitation("i1", "Spring Mixer")]);
      },
      [`GET ${UPCOMING}`]: upcoming([engagement("e1", "ACCT 4100 guest lecture")]),
    });
    renderPage();
    const retry = await screen.findByRole("button", { name: "Retry loading your invitations" });
    expect(section("Invitations waiting for your answer").textContent).toContain(
      "Your invitations could not be loaded, and the server gave no reason. Try again.",
    );
    expect(await screen.findByText("ACCT 4100 guest lecture")).toBeTruthy();
    fireEvent.click(retry);
    expect(await screen.findByText("Spring Mixer")).toBeTruthy();
  });

  it("while loading, each section is aria-busy with a text label", async () => {
    stub({
      [`GET ${INVITATIONS}`]: () => new Promise<Answer>(() => undefined),
      [`GET ${UPCOMING}`]: () => new Promise<Answer>(() => undefined),
    });
    renderPage();
    const invitationsLabel = await screen.findByText("Loading invitations…");
    expect(invitationsLabel.closest("[aria-busy='true']")).not.toBeNull();
    const engagementsLabel = screen.getByText("Loading engagements…");
    expect(engagementsLabel.closest("[aria-busy='true']")).not.toBeNull();
  });

  it("not linked from either read renders one notice, not two", async () => {
    stub({
      [`GET ${INVITATIONS}`]: refusal(404, "speaker_profile_not_linked"),
      [`GET ${UPCOMING}`]: refusal(404, "speaker_profile_not_linked"),
    });
    renderPage();
    await screen.findByText(NOT_LINKED);
    await waitFor(() => expect(calls).toHaveLength(2));
    expect(screen.getAllByText(NOT_LINKED)).toHaveLength(1);
    expect(screen.queryByRole("heading", { level: 2 })).toBeNull();
  });

  it("a 403 on one read replaces both sections with the denied notice", async () => {
    stub({
      [`GET ${INVITATIONS}`]: invitations([invitation("i1", "Spring Mixer")]),
      [`GET ${UPCOMING}`]: refusal(403, "forbidden"),
    });
    renderPage();
    expect(
      await screen.findByText(
        "This account's Speaker access is not active, so this page cannot be shown or changed. Ask your Speaker Connector.",
      ),
    ).toBeTruthy();
    expect(screen.queryByText("Spring Mixer")).toBeNull();
  });

  it("query keys are [principal, 'my-invitations'] and [principal, 'my-engagements', 'upcoming']", async () => {
    stub({
      [`GET ${INVITATIONS}`]: invitations([]),
      [`GET ${UPCOMING}`]: upcoming([]),
    });
    renderPage();
    await screen.findByText("No invitations are waiting for your answer.");
    const keys = client
      .getQueryCache()
      .getAll()
      .map((query) => query.queryKey);
    expect(keys).toEqual(
      expect.arrayContaining([
        ["principal-1", "my-invitations"],
        ["principal-1", "my-engagements", "upcoming"],
      ]),
    );
    expect(keys).toHaveLength(2);
  });

  it("switching principal re-reads and never shows the first principal's rows", async () => {
    let owner = "first";
    stub({
      [`GET ${INVITATIONS}`]: () =>
        owner === "first"
          ? invitations([invitation("i1", "First principal's event")])
          : new Promise<Answer>(() => undefined),
      [`GET ${UPCOMING}`]: upcoming([]),
    });
    renderPage();
    await screen.findByText("First principal's event");
    owner = "second";
    act(() => principal.set("principal-2"));
    expect(await screen.findByText("Loading invitations…")).toBeTruthy();
    expect(screen.queryByText("First principal's event")).toBeNull();
  });

  it("no request is sent while the principal key is null", async () => {
    principal.key = null;
    stub({ [`GET ${INVITATIONS}`]: invitations([]), [`GET ${UPCOMING}`]: upcoming([]) });
    renderPage();
    await act(async () => {
      await Promise.resolve();
    });
    expect(calls).toHaveLength(0);
  });

  it("sets document.title to 'Home · Speaker Portal'", () => {
    stub({ [`GET ${INVITATIONS}`]: invitations([]), [`GET ${UPCOMING}`]: upcoming([]) });
    renderPage();
    expect(document.title).toBe("Home · Speaker Portal");
    expect(screen.getByRole("heading", { level: 1, name: "Home" }).getAttribute("tabindex")).toBe(
      "-1",
    );
  });
});
