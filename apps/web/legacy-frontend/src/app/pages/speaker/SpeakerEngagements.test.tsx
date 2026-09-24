/**
 * The Speaker's Engagements page (B26 T6b-4 §5.3), against a stubbed `fetch`:
 * Upcoming / Past through `?when=`, paged, read-only, and never who
 * cancelled.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { MyEngagement } from "@/lib/api";

import { SpeakerEngagements } from "./SpeakerEngagements";

const UPCOMING = "/v1/me/engagements?when=upcoming";
const PAST = "/v1/me/engagements?when=past";

vi.mock("@/app/components/PrincipalQueryProvider", () => ({
  usePrincipalKey: () => "principal-1",
}));

type Answer = { body: unknown; status?: number };
let calls: string[] = [];

function stub(answers: Record<string, Answer>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit) => {
      const method = init.method ?? "GET";
      calls.push(`${method} ${url}`);
      const answer = answers[`${method} ${url}`] ?? {
        body: { error: { code: "test_unstubbed", message: url } },
        status: 404,
      };
      return new Response(JSON.stringify(answer.body), { status: answer.status ?? 200 });
    }),
  );
}

function engagement(id: string, title: string, overrides: Partial<MyEngagement> = {}): MyEngagement {
  return {
    engagement_id: id,
    event: {
      title,
      local_date: "2026-10-14",
      time_zone: "America/Los_Angeles",
      time_precision: "exact",
      starts_at: "2026-10-14T17:00:00Z",
      ends_at: "2026-10-14T18:15:00Z",
    },
    state: "confirmed",
    confirmed_at: "2026-09-20T12:00:00Z",
    attended_at: null,
    cancelled_at: null,
    ...overrides,
  };
}

function page(when: "upcoming" | "past", rows: MyEngagement[], truncated = false): Answer {
  return { body: { when, as_of: "2026-10-06", engagements: rows, truncated } };
}

let client: QueryClient;

function renderPage(path = "/speaker-portal/engagements") {
  client = new QueryClient({
    defaultOptions: { queries: { retry: false, networkMode: "always", staleTime: 0 } },
  });
  const router = createMemoryRouter(
    [{ path: "/speaker-portal/engagements", element: <SpeakerEngagements /> }],
    { initialEntries: [path] },
  );
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

function period(): HTMLElement {
  return screen.getByRole("navigation", { name: "Engagement period" });
}

beforeEach(() => {
  calls = [];
  document.title = "Smart Match";
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("<SpeakerEngagements />", () => {
  it("defaults to upcoming and reads ?when=upcoming", async () => {
    stub({ [`GET ${UPCOMING}`]: page("upcoming", [engagement("e1", "Guest lecture")]) });
    renderPage();
    await screen.findByText("Guest lecture");
    expect(calls).toEqual([`GET ${UPCOMING}`]);
    expect(within(period()).getByRole("link", { name: "Upcoming" }).getAttribute("aria-current")).toBe(
      "page",
    );
  });

  it("the Past link sets ?when=past, carries aria-current, and reads that key", async () => {
    stub({
      [`GET ${UPCOMING}`]: page("upcoming", [engagement("e1", "Guest lecture")]),
      [`GET ${PAST}`]: page("past", [engagement("e0", "Last spring's panel")]),
    });
    const router = renderPage();
    await screen.findByText("Guest lecture");
    const past = within(period()).getByRole("link", { name: "Past" });
    expect(past.getAttribute("href")).toBe("/speaker-portal/engagements?when=past");
    past.focus();
    await act(async () => {
      fireEvent.click(past);
    });
    await screen.findByText("Last spring's panel");
    expect(router.state.location.search).toBe("?when=past");
    expect(within(period()).getByRole("link", { name: "Past" }).getAttribute("aria-current")).toBe(
      "page",
    );
    expect(
      within(period()).getByRole("link", { name: "Upcoming" }).getAttribute("aria-current"),
    ).toBeNull();
    const keys = client
      .getQueryCache()
      .getAll()
      .map((query) => query.queryKey);
    expect(keys).toEqual(
      expect.arrayContaining([
        ["principal-1", "my-engagements", "upcoming"],
        ["principal-1", "my-engagements", "past"],
      ]),
    );
    // A `?when=` change keeps the pathname: focus stays on the link pressed.
    expect(document.activeElement).toBe(within(period()).getByRole("link", { name: "Past" }));
  });

  it("an unknown ?when value reads upcoming", async () => {
    stub({ [`GET ${UPCOMING}`]: page("upcoming", [engagement("e1", "Guest lecture")]) });
    renderPage("/speaker-portal/engagements?when=someday");
    await screen.findByText("Guest lecture");
    expect(calls).toEqual([`GET ${UPCOMING}`]);
  });

  it("cancelled shows Cancelled on {date} and nothing about who; chips have a word and an aria-hidden icon", async () => {
    stub({
      [`GET ${UPCOMING}`]: page("upcoming", [
        engagement("e1", "Guest lecture", {
          state: "cancelled",
          cancelled_at: "2026-09-22T12:00:00Z",
        }),
        engagement("e2", "Alumni night", { state: "attended", attended_at: "2026-10-01T12:00:00Z" }),
        engagement("e3", "Career panel"),
      ]),
    });
    renderPage();
    await screen.findByText("Guest lecture");
    const rows = screen.getAllByRole("listitem");
    const cancelled = rows.find((item) => item.textContent?.includes("Guest lecture"));
    expect(cancelled?.textContent).toContain("Cancelled");
    expect(cancelled?.textContent).toMatch(/Cancelled on Sep 22, 2026/);
    expect(cancelled?.querySelector("time[datetime='2026-09-22T12:00:00Z']")).not.toBeNull();
    expect(cancelled?.textContent).not.toMatch(/\bby\b/i);
    for (const [title, word] of [
      ["Alumni night", "Attended"],
      ["Career panel", "Confirmed"],
    ]) {
      const item = rows.find((candidate) => candidate.textContent?.includes(title));
      expect(item?.textContent).toContain(word);
      const icons = item?.querySelectorAll("svg") ?? [];
      expect(icons.length).toBeGreaterThan(0);
      for (const icon of Array.from(icons)) {
        expect(icon.getAttribute("aria-hidden")).toBe("true");
      }
    }
  });

  it("shows the time in the event's zone, and 'Date not set yet' for an unresolved date", async () => {
    stub({
      [`GET ${UPCOMING}`]: page("upcoming", [
        engagement("e1", "Guest lecture"),
        engagement("e2", "Undated talk", {
          event: {
            title: "Undated talk",
            local_date: null,
            time_zone: null,
            time_precision: "unresolved",
            starts_at: null,
            ends_at: null,
          },
        }),
      ]),
    });
    renderPage();
    await screen.findByText("Guest lecture");
    const text = (document.body.textContent ?? "").replace(/\s/g, " ");
    expect(text).toContain("October 14, 2026, 10:00 AM – 11:15 AM PDT");
    expect(text).toContain("Date not set yet");
  });

  it("empty upcoming and empty past have their own sentences; event null says details unavailable", async () => {
    stub({
      [`GET ${UPCOMING}`]: page("upcoming", []),
      [`GET ${PAST}`]: page("past", [engagement("e0", "ignored", { event: null })]),
    });
    renderPage();
    expect(await screen.findByText("No upcoming engagements.")).toBeTruthy();

    cleanup();
    stub({ [`GET ${PAST}`]: page("past", []) });
    renderPage("/speaker-portal/engagements?when=past");
    expect(await screen.findByText("No past engagements yet.")).toBeTruthy();

    cleanup();
    stub({ [`GET ${PAST}`]: page("past", [engagement("e0", "ignored", { event: null })]) });
    renderPage("/speaker-portal/engagements?when=past");
    expect(await screen.findAllByText("Event details are no longer available.")).not.toHaveLength(0);
  });

  it("no button renders in any row", async () => {
    stub({
      [`GET ${UPCOMING}`]: page("upcoming", [
        engagement("e1", "Guest lecture"),
        engagement("e2", "Alumni night", { state: "cancelled", cancelled_at: "2026-09-22T12:00:00Z" }),
      ]),
    });
    renderPage();
    await screen.findByText("Guest lecture");
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("engagements page through PagedList; switching Upcoming to Past returns to page 1", async () => {
    stub({
      [`GET ${UPCOMING}`]: page(
        "upcoming",
        Array.from({ length: 15 }, (_, i) => engagement(`u${i}`, `Upcoming ${i}`)),
      ),
      [`GET ${PAST}`]: page(
        "past",
        Array.from({ length: 15 }, (_, i) => engagement(`p${i}`, `Past ${i}`)),
      ),
    });
    renderPage();
    await screen.findByText("Upcoming 0");
    fireEvent.click(screen.getAllByRole("button", { name: "Next page of engagements" })[0]);
    expect(await screen.findByText("Upcoming 10")).toBeTruthy();
    await act(async () => {
      fireEvent.click(within(period()).getByRole("link", { name: "Past" }));
    });
    expect(await screen.findByText("Past 0")).toBeTruthy();
    expect(screen.queryByText("Past 10")).toBeNull();
  });

  it("truncated says the first 200", async () => {
    stub({ [`GET ${UPCOMING}`]: page("upcoming", [engagement("e1", "Guest lecture")], true) });
    renderPage();
    expect(await screen.findByText("Showing the first 200.")).toBeTruthy();
  });

  it("a 404 not linked replaces the list with the notice; a 500 offers Retry", async () => {
    stub({
      [`GET ${UPCOMING}`]: {
        status: 404,
        body: { error: { code: "speaker_profile_not_linked", message: "x" } },
      },
    });
    renderPage();
    expect(
      await screen.findByText(
        "Your account is not linked to a Speaker profile, so there is nothing to show here. Ask your Speaker Connector to send you a new portal invitation.",
      ),
    ).toBeTruthy();

    cleanup();
    stub({
      [`GET ${UPCOMING}`]: { status: 500, body: { error: { code: "internal_error", message: "x" } } },
    });
    renderPage();
    expect(
      await screen.findByRole("button", { name: "Retry loading your engagements" }),
    ).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain(
        "Your engagements could not be loaded, and the server gave no reason. Try again.",
      ),
    );
  });

  it("sets document.title to 'Engagements · Speaker Portal'", () => {
    stub({ [`GET ${UPCOMING}`]: page("upcoming", []) });
    renderPage();
    expect(document.title).toBe("Engagements · Speaker Portal");
  });
});
