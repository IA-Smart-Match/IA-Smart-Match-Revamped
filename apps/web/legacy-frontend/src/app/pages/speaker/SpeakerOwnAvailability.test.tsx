/**
 * The Speaker's own Availability page (B26 T6b-4 §5.4), against a stubbed
 * `fetch` and T5's real form. It reads `GET /v1/me/availability` and writes
 * `PATCH /v1/me/availability`, and nothing else; the words are the Speaker's
 * (`COPY.speaker`), and never "available".
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { SpeakerAvailability } from "@/lib/api";

import { SpeakerOwnAvailability } from "./SpeakerOwnAvailability";

const URL = "/v1/me/availability";

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
let calls: { method: string; url: string; init: RequestInit }[] = [];

function stub(answers: Record<string, Found>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit) => {
      const method = init.method ?? "GET";
      calls.push({ method, url, init });
      const found = answers[`${method} ${url}`];
      const answer =
        typeof found === "function"
          ? await found()
          : (found ?? { body: { error: { code: "test_unstubbed", message: url } }, status: 404 });
      return new Response(JSON.stringify(answer.body), { status: answer.status ?? 200 });
    }),
  );
}

function sequence(...answers: (Answer | (() => Promise<Answer>))[]): () => Promise<Answer> {
  let index = 0;
  return async () => {
    const next = answers[Math.min(index, answers.length - 1)];
    index += 1;
    return typeof next === "function" ? next() : next;
  };
}

function deferred(): { promise: Promise<Answer>; resolve: (answer: Answer) => void } {
  let resolve: (answer: Answer) => void = () => undefined;
  const promise = new Promise<Answer>((settle) => {
    resolve = settle;
  });
  return { promise, resolve };
}

function refusal(status: number, code: string): Answer {
  return { status, body: { error: { code, message: "SERVER-WORDS" } } };
}

function availability(overrides: Partial<SpeakerAvailability> = {}): SpeakerAvailability {
  return {
    professional_id: "p-self",
    stated: true,
    version: 4,
    invitations_paused_until: null,
    declared_capacity_hours_per_90_days: null,
    unavailable: [],
    updated_source: "connector",
    updated_at: "2026-10-01T12:00:00Z",
    ...overrides,
  };
}

const NOT_STATED = availability({
  stated: false,
  version: null,
  updated_source: null,
  updated_at: null,
});

let client: QueryClient;

function renderPage() {
  client = new QueryClient({
    defaultOptions: { queries: { retry: false, networkMode: "always", staleTime: 0 } },
  });
  const router = createMemoryRouter(
    [
      {
        path: "/speaker-portal/availability",
        element: (
          <main>
            <SpeakerOwnAvailability />
          </main>
        ),
      },
      { path: "/login", element: <p>Sign-in page</p> },
    ],
    { initialEntries: ["/speaker-portal/availability"] },
  );
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

function capacityInput(): HTMLInputElement {
  return screen.getByLabelText("Capacity (hours per 90 days)") as HTMLInputElement;
}

function pauseInput(): HTMLInputElement {
  return screen.getByLabelText("Pause invitations until") as HTMLInputElement;
}

function gets(): number {
  return calls.filter((call) => call.method === "GET").length;
}

function patches(): typeof calls {
  return calls.filter((call) => call.method === "PATCH");
}

beforeEach(() => {
  calls = [];
  principal.key = "principal-1";
  document.title = "Smart Match";
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-06T12:00:00Z"));
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("<SpeakerOwnAvailability />", () => {
  it("reads GET /v1/me/availability under [principal, 'my-availability'] and never a unit route", async () => {
    stub({ [`GET ${URL}`]: { body: availability() } });
    renderPage();
    await screen.findByText(/Stated: no dates blocked\./);
    expect(calls.map((call) => `${call.method} ${call.url}`)).toEqual([`GET ${URL}`]);
    expect(calls.some((call) => call.url.includes("/v1/units/"))).toBe(false);
    expect(
      client
        .getQueryCache()
        .getAll()
        .map((query) => query.queryKey),
    ).toEqual([["principal-1", "my-availability"]]);
  });

  it("Not stated uses Speaker copy and never says 'available'", async () => {
    stub({ [`GET ${URL}`]: { body: NOT_STATED } });
    renderPage();
    const main = screen.getByRole("main");
    await screen.findByText(
      "You have not said when you can speak, so Speaker Connectors see your availability as unknown.",
    );
    expect(screen.getByRole("button", { name: "Save: no dates blocked" })).toBeTruthy();
    expect(
      screen.getByText("Saving an empty form tells Speaker Connectors you have no dates blocked."),
    ).toBeTruthy();
    expect(screen.getByText("Dates you cannot speak")).toBeTruthy();
    expect(
      screen.getByText(
        "Optional. How many hours of speaking you can give in any 90 days. If you leave it blank, your workload cannot be measured.",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText("Optional. No new invitations are sent through this date. Latest October 6, 2027."),
    ).toBeTruthy();
    expect(main.textContent).not.toMatch(/\bavailable\b/i);
  });

  it("sources read 'Added by you' and 'Added by a Speaker Connector'", async () => {
    stub({
      [`GET ${URL}`]: {
        body: availability({
          updated_source: "speaker",
          unavailable: [
            { starts_on: "2026-11-02", ends_on: "2026-11-06", source: "speaker" },
            { starts_on: "2026-12-20", ends_on: "2026-12-31", source: "connector" },
          ],
        }),
      },
    });
    renderPage();
    const first = await screen.findByRole("group", { name: "Unavailable dates 1" });
    expect(within(first).getByText("Added by you")).toBeTruthy();
    const second = screen.getByRole("group", { name: "Unavailable dates 2" });
    expect(within(second).getByText("Added by a Speaker Connector")).toBeTruthy();
    expect(screen.getByText(/Last changed .* by you/)).toBeTruthy();
  });

  it("save sends one PATCH /v1/me/availability with the T5 body; Save is disabled while pending", async () => {
    const patch = deferred();
    stub({
      [`GET ${URL}`]: { body: availability() },
      [`PATCH ${URL}`]: () => patch.promise,
    });
    renderPage();
    await screen.findByText(/Stated: no dates blocked\./);
    fireEvent.change(capacityInput(), { target: { value: "12" } });
    fireEvent.change(pauseInput(), { target: { value: "2026-10-10" } });
    const save = screen.getByRole("button", { name: "Save availability" });
    fireEvent.click(save);
    await waitFor(() => expect(patches()).toHaveLength(1));
    expect(patches()[0].url).toBe(URL);
    expect(JSON.parse(String(patches()[0].init.body))).toEqual({
      expected_version: 4,
      invitations_paused_until: "2026-10-10",
      declared_capacity_hours_per_90_days: 12,
      unavailable: [],
    });
    await waitFor(() => expect((save as HTMLButtonElement).disabled).toBe(true));
    fireEvent.click(save);
    expect(patches()).toHaveLength(1);
    await act(async () => {
      patch.resolve({ body: availability({ version: 5, declared_capacity_hours_per_90_days: 12 }) });
    });
  });

  it("success writes the saved row with setQueryData and invalidates nothing", async () => {
    const saved = availability({
      version: 5,
      declared_capacity_hours_per_90_days: 12,
      updated_source: "speaker",
      updated_at: "2026-10-06T12:00:00Z",
    });
    stub({
      [`GET ${URL}`]: { body: availability() },
      [`PATCH ${URL}`]: { body: saved },
    });
    renderPage();
    await screen.findByText(/Stated: no dates blocked\./);
    const setData = vi.spyOn(client, "setQueryData");
    const invalidate = vi.spyOn(client, "invalidateQueries");
    fireEvent.change(capacityInput(), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: "Save availability" }));
    await waitFor(() => expect(setData).toHaveBeenCalledTimes(1));
    expect(setData.mock.calls[0][0]).toEqual(["principal-1", "my-availability"]);
    expect(setData.mock.calls[0][1]).toEqual(saved);
    expect(invalidate).not.toHaveBeenCalled();
    expect(gets()).toBe(1);
  });

  it("409 stale keeps every typed value, re-reads exactly my-availability, and says This changed", async () => {
    const fresh = availability({ version: 6, declared_capacity_hours_per_90_days: 40 });
    stub({
      [`GET ${URL}`]: sequence({ body: availability() }, { body: fresh }),
      [`PATCH ${URL}`]: refusal(409, "speaker_availability_stale"),
    });
    renderPage();
    await screen.findByText(/Stated: no dates blocked\./);
    const refetch = vi.spyOn(client, "refetchQueries");
    fireEvent.change(capacityInput(), { target: { value: "12" } });
    fireEvent.change(pauseInput(), { target: { value: "2026-10-10" } });
    fireEvent.click(screen.getByRole("button", { name: "Save availability" }));
    await screen.findByText(/This changed/);
    expect(
      screen.getByText(
        /since you opened it — a Speaker Connector may have updated it\. Your changes are still in the form and were not saved\./,
      ),
    ).toBeTruthy();
    await waitFor(() => expect(gets()).toBe(2));
    expect(refetch.mock.calls).toEqual([
      [{ queryKey: ["principal-1", "my-availability"], exact: true }],
    ]);
    expect(capacityInput().value).toBe("12");
    expect(pauseInput().value).toBe("2026-10-10");
    expect(
      await screen.findByRole("button", { name: "Save my changes over it" }),
    ).toBeTruthy();
    expect(screen.queryByText(/Someone changed this/)).toBeNull();
  });

  it("a response carrying a load field renders no number from it", async () => {
    stub({
      [`GET ${URL}`]: {
        body: { ...availability(), load: { band: "moderate", utilization: 0.61 } },
      },
    });
    renderPage();
    await screen.findByText(/Stated: no dates blocked\./);
    const text = screen.getByRole("main").textContent ?? "";
    expect(text).not.toContain("0.61");
    expect(text).not.toContain("61");
    expect(text).not.toMatch(/moderate/i);
  });

  it("404 speaker_profile_not_linked on GET shows the not-linked notice and no form", async () => {
    stub({ [`GET ${URL}`]: refusal(404, "speaker_profile_not_linked") });
    renderPage();
    expect(
      await screen.findByText(
        "Your account is not linked to a Speaker profile, so there is nothing to show here. Ask your Speaker Connector to send you a new portal invitation.",
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("form")).toBeNull();
    expect(screen.queryByLabelText("Capacity (hours per 90 days)")).toBeNull();
    expect(screen.queryByRole("button", { name: /Retry/ })).toBeNull();
  });

  it("404 speaker_profile_not_linked on PATCH keeps the draft and says so in the form alert", async () => {
    stub({
      [`GET ${URL}`]: { body: availability() },
      [`PATCH ${URL}`]: refusal(404, "speaker_profile_not_linked"),
    });
    renderPage();
    await screen.findByText(/Stated: no dates blocked\./);
    fireEvent.change(capacityInput(), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: "Save availability" }));
    await waitFor(() =>
      expect(document.getElementById("my-availability-form-error")?.textContent).toContain(
        "Your account is not linked to a Speaker profile",
      ),
    );
    expect(capacityInput().value).toBe("12");
    expect(document.body.textContent).not.toContain("SERVER-WORDS");
  });

  it("a domain 422 keeps T5's field message", async () => {
    stub({
      [`GET ${URL}`]: { body: availability() },
      [`PATCH ${URL}`]: {
        status: 422,
        body: {
          error: {
            code: "speaker_availability_capacity_invalid",
            message: "SERVER-WORDS",
            details: { field: "declared_capacity_hours_per_90_days" },
          },
        },
      },
    });
    renderPage();
    await screen.findByText(/Stated: no dates blocked\./);
    fireEvent.change(capacityInput(), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: "Save availability" }));
    expect(
      await screen.findByText(
        "Capacity must be more than 0 and at most 720 hours per 90 days, with at most one decimal place. Leave it blank if not stated.",
      ),
    ).toBeTruthy();
    expect(document.body.textContent).not.toContain("SERVER-WORDS");
  });

  it("GET 403 shows the denied notice and no form; GET 500 shows Retry, which re-reads", async () => {
    stub({ [`GET ${URL}`]: refusal(403, "forbidden") });
    renderPage();
    expect(
      await screen.findByText(
        "This account's Speaker access is not active, so this page cannot be shown or changed. Ask your Speaker Connector.",
      ),
    ).toBeTruthy();
    expect(screen.queryByLabelText("Capacity (hours per 90 days)")).toBeNull();

    cleanup();
    calls = [];
    stub({
      [`GET ${URL}`]: sequence(refusal(500, "internal_error"), { body: availability() }),
    });
    renderPage();
    const retry = await screen.findByRole("button", { name: "Retry loading your availability" });
    fireEvent.click(retry);
    expect(await screen.findByText(/Stated: no dates blocked\./)).toBeTruthy();
    expect(gets()).toBe(2);
  });

  it("while loading, the page is aria-busy with a text label", async () => {
    stub({ [`GET ${URL}`]: () => new Promise<Answer>(() => undefined) });
    renderPage();
    const label = await screen.findByText("Loading your availability…");
    expect(label.closest("[aria-busy='true']")).not.toBeNull();
    // Route-change focus lands on the h1; it must not sit inside the busy region.
    const heading = screen.getByRole("heading", { level: 1, name: "Your availability" });
    expect(heading.closest("[aria-busy='true']")).toBeNull();
  });

  it("the form is labelled by the page h1", async () => {
    stub({ [`GET ${URL}`]: { body: availability() } });
    renderPage();
    await screen.findByText(/Stated: no dates blocked\./);
    const heading = screen.getByRole("heading", { level: 1, name: "Your availability" });
    expect(heading.id).toBe("my-availability-heading");
    expect(screen.getByRole("form", { name: "Your availability" })).toBeTruthy();
  });

  it("switching principal re-reads and never shows the first principal's statement", async () => {
    let owner = "first";
    stub({
      [`GET ${URL}`]: () =>
        owner === "first"
          ? { body: availability({ declared_capacity_hours_per_90_days: 33 }) }
          : new Promise<Answer>(() => undefined),
    });
    renderPage();
    await screen.findByText("33 hours per 90 days");
    owner = "second";
    act(() => principal.set("principal-2"));
    expect(await screen.findByText("Loading your availability…")).toBeTruthy();
    expect(screen.queryByText("33 hours per 90 days")).toBeNull();
  });

  it("no request is sent while the principal key is null", async () => {
    principal.key = null;
    stub({ [`GET ${URL}`]: { body: availability() } });
    renderPage();
    await act(async () => {
      await Promise.resolve();
    });
    expect(calls).toHaveLength(0);
  });

  it("sets document.title to 'Your availability · Speaker Portal'", () => {
    stub({ [`GET ${URL}`]: { body: availability() } });
    renderPage();
    expect(document.title).toBe("Your availability · Speaker Portal");
  });
});
