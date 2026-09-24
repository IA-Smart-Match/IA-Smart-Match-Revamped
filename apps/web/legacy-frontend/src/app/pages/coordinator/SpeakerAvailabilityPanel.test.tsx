/**
 * The Connector availability panel against a stubbed `fetch` (B26 T5 §8 C).
 *
 * The panel reads `GET …/speaker-contacts/{id}/availability` and writes
 * `PATCH` to the same path, through T3's real `api.ts` adapter. The stub
 * answers exactly those; assertions check the requests the panel made and the
 * cache calls it issued, not only what it drew.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { EngagementWithoutEndTime, SpeakerAvailability } from "@/lib/api";
import { speakerLoadFixture } from "@/test/speakerLoadFixture";

import { SpeakerAvailabilityPanel } from "./SpeakerAvailabilityPanel";

const UNIT = "11111111-1111-4111-8111-111111111111";
const PID = "22222222-2222-4222-8222-222222222222";
const PATH = `/v1/units/${UNIT}/speaker-contacts/${PID}/availability`;
const GET = `GET ${PATH}`;
const PATCH = `PATCH ${PATH}`;

const principal = vi.hoisted(() => ({ key: "principal-1" as string | null }));

vi.mock("@/app/components/PrincipalQueryProvider", () => ({
  usePrincipalKey: () => principal.key,
}));

type Answer = { body: unknown; status?: number };
type Responder = Answer | (() => Answer | Promise<Answer>);
let calls: { key: string; body: unknown }[] = [];

/** Each route answers its responders in turn; the last one repeats. */
function stub(routes: Record<string, Responder[]>): void {
  const queues = Object.fromEntries(
    Object.entries(routes).map(([key, list]) => [key, [...list]]),
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit) => {
      const key = `${init.method ?? "GET"} ${url}`;
      calls.push({ key, body: init.body ? JSON.parse(String(init.body)) : undefined });
      const queue = queues[key];
      const next = queue === undefined ? undefined : queue.length > 1 ? queue.shift() : queue[0];
      const answer: Answer =
        next === undefined
          ? { body: { error: { code: "test_unstubbed", message: key } }, status: 404 }
          : typeof next === "function"
            ? await next()
            : next;
      return new Response(JSON.stringify(answer.body), { status: answer.status ?? 200 });
    }),
  );
}

function deferred(): { promise: Promise<Answer>; resolve: (a: Answer) => void } {
  let resolve: (a: Answer) => void = () => undefined;
  const promise = new Promise<Answer>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

function availability(overrides: Partial<SpeakerAvailability> = {}): SpeakerAvailability {
  return {
    professional_id: PID,
    stated: true,
    version: 4,
    invitations_paused_until: null,
    declared_capacity_hours_per_90_days: null,
    unavailable: [],
    updated_source: "connector",
    updated_at: "2026-10-01T15:00:00Z",
    load: speakerLoadFixture(),
    ...overrides,
  };
}

function notStated(): SpeakerAvailability {
  return availability({ stated: false, version: null, updated_source: null, updated_at: null });
}

function ok(body: SpeakerAvailability): Answer {
  return { body };
}

function fail(status: number, code: string, details?: Record<string, unknown>): Answer {
  return {
    status,
    body: { error: { code, message: `Server says ${code}.`, ...(details ? { details } : {}) } },
  };
}

function makeClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, networkMode: "always", staleTime: 0 } },
  });
}

function renderPanel(client = makeClient()) {
  const view = render(
    <QueryClientProvider client={client}>
      <SpeakerAvailabilityPanel unitId={UNIT} professionalId={PID} contactName="Dana Reyes" />
    </QueryClientProvider>,
  );
  return { ...view, client };
}

function region(): HTMLElement {
  return screen.getByRole("region", { name: "Availability for Dana Reyes" });
}

function count(key: string): number {
  return calls.filter((c) => c.key === key).length;
}

function patches(): unknown[] {
  return calls.filter((c) => c.key === PATCH).map((c) => c.body);
}

function capacityInput(): HTMLInputElement {
  return screen.getByLabelText("Capacity (hours per 90 days)") as HTMLInputElement;
}

function pauseInput(): HTMLInputElement {
  return screen.getByLabelText("Pause invitations until") as HTMLInputElement;
}

const WINDOWED = availability({
  unavailable: [
    { starts_on: "2026-11-02", ends_on: "2026-11-06", source: "speaker" },
    { starts_on: "2026-12-20", ends_on: "2026-12-31", source: "connector" },
  ],
});

beforeEach(() => {
  calls = [];
  principal.key = "principal-1";
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-06T03:00:00Z"));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("<SpeakerAvailabilityPanel /> read states", () => {
  it("loading sets aria-busy and a label before GET resolves", async () => {
    const pending = deferred();
    stub({ [GET]: [() => pending.promise] });
    renderPanel();
    expect(region().getAttribute("aria-busy")).toBe("true");
    expect(within(region()).getByText("Loading availability…")).toBeTruthy();
    expect(screen.queryByLabelText("Capacity (hours per 90 days)")).toBeNull();

    await act(async () => pending.resolve(ok(notStated())));
    await screen.findByText(/Not stated\./);
    expect(region().getAttribute("aria-busy")).toBe("false");
  });

  it('not stated says Not stated and never "available"', async () => {
    stub({ [GET]: [ok(notStated())] });
    renderPanel();
    await screen.findByText(/Not stated\./);
    expect(region().textContent).toMatch(/matching treats their availability as unknown/);
    expect(region().textContent).not.toMatch(/\bavailable\b/i);
    expect(screen.getByRole("button", { name: "Save: no dates blocked" })).toBeTruthy();
  });

  it('stated with nothing blocked says so and shows "Capacity not stated", never 0', async () => {
    stub({ [GET]: [ok(availability())] });
    renderPanel();
    await screen.findByText(/Stated: no dates blocked\./);
    expect(within(region()).getByText("Capacity not stated")).toBeTruthy();
    expect(region().textContent).not.toMatch(/\b0 hours/);
    expect(capacityInput().value).toBe("");
    expect(region().textContent).toMatch(/Last changed .* by a Speaker Connector/);
    expect(region().textContent).not.toMatch(/\bavailable\b/i);
  });

  it("windows render with their source; an active pause is named", async () => {
    stub({
      [GET]: [
        ok(
          availability({
            ...WINDOWED,
            invitations_paused_until: "2026-10-20",
            declared_capacity_hours_per_90_days: 24,
          }),
        ),
      ],
    });
    renderPanel();
    await screen.findByText(/2 blocked date ranges\./);
    expect(region().textContent).toMatch(/Invitations paused until October 20, 2026\./);
    expect(within(region()).getByText("24 hours per 90 days")).toBeTruthy();
    const first = screen.getByRole("group", { name: "Unavailable dates 1" });
    expect(within(first).getByText("Added by the Speaker")).toBeTruthy();
    const second = screen.getByRole("group", { name: "Unavailable dates 2" });
    expect(within(second).getByText("Added by a Speaker Connector")).toBeTruthy();
  });

  it("an expired pause says saving clears it, and saving it is allowed", async () => {
    stub({
      [GET]: [ok(availability({ invitations_paused_until: "2026-09-30" }))],
      [PATCH]: [ok(availability({ version: 5, declared_capacity_hours_per_90_days: 8 }))],
    });
    renderPanel();
    await screen.findByText("This pause ended on September 30, 2026. Saving clears it.");
    expect(pauseInput().value).toBe("2026-09-30");
    fireEvent.change(capacityInput(), { target: { value: "8" } });
    fireEvent.click(screen.getByRole("button", { name: "Save availability" }));
    await waitFor(() => expect(count(PATCH)).toBe(1));
    expect(patches()[0]).toMatchObject({ invitations_paused_until: "2026-09-30" });
  });
});

describe("<SpeakerAvailabilityPanel /> saving", () => {
  it("save sends exactly one PATCH with the exact body", async () => {
    stub({
      [GET]: [ok(WINDOWED)],
      [PATCH]: [ok(availability({ ...WINDOWED, version: 5, declared_capacity_hours_per_90_days: 12 }))],
    });
    renderPanel();
    await screen.findByText(/2 blocked date ranges\./);
    fireEvent.change(capacityInput(), { target: { value: "12" } });
    fireEvent.change(pauseInput(), { target: { value: "2026-10-10" } });
    fireEvent.click(screen.getByRole("button", { name: "Save availability" }));

    await waitFor(() => expect(count(PATCH)).toBe(1));
    expect(patches()[0]).toEqual({
      expected_version: 4,
      invitations_paused_until: "2026-10-10",
      declared_capacity_hours_per_90_days: 12,
      unavailable: [
        { starts_on: "2026-11-02", ends_on: "2026-11-06" },
        { starts_on: "2026-12-20", ends_on: "2026-12-31" },
      ],
    });
  });

  it("Save is disabled and reads Saving… while pending", async () => {
    const pending = deferred();
    stub({ [GET]: [ok(availability())], [PATCH]: [() => pending.promise] });
    renderPanel();
    await screen.findByText(/Stated: no dates blocked\./);
    fireEvent.change(capacityInput(), { target: { value: "12" } });
    const save = screen.getByRole("button", { name: "Save availability" });
    fireEvent.click(save);
    await waitFor(() => expect(save.textContent).toBe("Saving…"));
    expect((save as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(save);
    expect(count(PATCH)).toBe(1);
    await act(async () =>
      pending.resolve(ok(availability({ version: 5, declared_capacity_hours_per_90_days: 12 }))),
    );
  });

  it("success announces in role=status and re-seeds from the response", async () => {
    stub({
      [GET]: [ok(WINDOWED)],
      [PATCH]: [
        ok(
          availability({
            version: 5,
            declared_capacity_hours_per_90_days: 12,
            updated_at: "2026-10-06T02:59:00Z",
          }),
        ),
      ],
    });
    renderPanel();
    await screen.findByText(/2 blocked date ranges\./);
    fireEvent.change(capacityInput(), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: "Save availability" }));
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toMatch(/^Availability saved /),
    );
    // The server's answer had no windows, so the form now has none.
    expect(screen.queryAllByRole("group", { name: /^Unavailable dates \d$/ })).toHaveLength(0);
    expect(capacityInput().value).toBe("12");
    expect(within(region()).getByText("12 hours per 90 days")).toBeTruthy();
  });

  it("a second save sends the new version without a GET in between", async () => {
    stub({
      [GET]: [ok(availability())],
      [PATCH]: [
        ok(availability({ version: 5, declared_capacity_hours_per_90_days: 12 })),
        ok(availability({ version: 6, declared_capacity_hours_per_90_days: 13 })),
      ],
    });
    renderPanel();
    await screen.findByText(/Stated: no dates blocked\./);
    fireEvent.change(capacityInput(), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: "Save availability" }));
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toMatch(/^Availability saved /),
    );
    const getsAfterFirstSave = count(GET);
    fireEvent.change(capacityInput(), { target: { value: "13" } });
    fireEvent.click(screen.getByRole("button", { name: "Save availability" }));
    await waitFor(() => expect(count(PATCH)).toBe(2));
    expect(patches()[1]).toMatchObject({ expected_version: 5 });
    expect(count(GET)).toBe(getsAfterFirstSave);
  });

  it("success writes the availability key and invalidates exactly the match-run and invitation-compose prefixes", async () => {
    const saved = availability({ version: 5, declared_capacity_hours_per_90_days: 12 });
    stub({ [GET]: [ok(availability())], [PATCH]: [ok(saved)] });
    const client = makeClient();
    const setSpy = vi.spyOn(client, "setQueryData");
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    renderPanel(client);
    await screen.findByText(/Stated: no dates blocked\./);
    fireEvent.change(capacityInput(), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: "Save availability" }));
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toMatch(/^Availability saved /),
    );
    expect(setSpy).toHaveBeenCalledTimes(1);
    expect(setSpy).toHaveBeenCalledWith(
      ["principal-1", "speaker-availability", UNIT, PID],
      saved,
    );
    expect(invalidateSpy.mock.calls.map((c) => c[0])).toEqual([
      { queryKey: ["principal-1", "match-run", UNIT] },
      { queryKey: ["principal-1", "invitation-compose", UNIT] },
    ]);
  });
});

describe("<SpeakerAvailabilityPanel /> stale (409)", () => {
  const fresh = availability({
    version: 6,
    declared_capacity_hours_per_90_days: 40,
    updated_source: "speaker",
    unavailable: [{ starts_on: "2027-01-10", ends_on: "2027-01-12", source: "speaker" }],
  });

  async function typeAndHitStale(): Promise<HTMLElement> {
    renderPanel();
    await screen.findByText(/Stated: no dates blocked\./);
    fireEvent.change(capacityInput(), { target: { value: "12" } });
    fireEvent.change(pauseInput(), { target: { value: "2026-10-10" } });
    fireEvent.click(screen.getByRole("button", { name: "Add unavailable dates" }));
    const group = screen.getByRole("group", { name: "Unavailable dates 1" });
    fireEvent.change(within(group).getByLabelText("From"), { target: { value: "2026-11-02" } });
    fireEvent.change(within(group).getByLabelText("To, inclusive"), {
      target: { value: "2026-11-06" },
    });
    const save = screen.getByRole("button", { name: "Save availability" });
    fireEvent.click(save);
    await screen.findByText(/Someone changed this/);
    return save;
  }

  function expectTypedValuesKept(): void {
    expect(capacityInput().value).toBe("12");
    expect(pauseInput().value).toBe("2026-10-10");
    const group = screen.getByRole("group", { name: "Unavailable dates 1" });
    expect((within(group).getByLabelText("From") as HTMLInputElement).value).toBe("2026-11-02");
    expect((within(group).getByLabelText("To, inclusive") as HTMLInputElement).value).toBe(
      "2026-11-06",
    );
  }

  it("keeps every typed value, re-reads with GET, and says Someone changed this", async () => {
    stub({
      [GET]: [ok(availability()), ok(fresh)],
      [PATCH]: [fail(409, "speaker_availability_stale")],
    });
    const save = await typeAndHitStale();
    await waitFor(() => expect(count(GET)).toBe(2));
    expectTypedValuesKept();
    expect(screen.getByText(/Your changes are still in the form and were not saved\./)).toBeTruthy();
    await screen.findByText("Saved now");
    expect(region().textContent).toMatch(/by the Speaker/);
    // Same element, new label: focus and DOM position are kept.
    await waitFor(() => expect(save.textContent).toBe("Save my changes over it"));
    expect((save as HTMLButtonElement).disabled).toBe(false);
  });

  it("Save my changes over it sends the fresh version with the draft", async () => {
    stub({
      [GET]: [ok(availability()), ok(fresh)],
      [PATCH]: [
        fail(409, "speaker_availability_stale"),
        ok(availability({ version: 7, declared_capacity_hours_per_90_days: 12 })),
      ],
    });
    await typeAndHitStale();
    const overwrite = await screen.findByRole("button", { name: "Save my changes over it" });
    await waitFor(() => expect((overwrite as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(overwrite);
    await waitFor(() => expect(count(PATCH)).toBe(2));
    expect(patches()[1]).toEqual({
      expected_version: 6,
      invitations_paused_until: "2026-10-10",
      declared_capacity_hours_per_90_days: 12,
      unavailable: [{ starts_on: "2026-11-02", ends_on: "2026-11-06" }],
    });
  });

  it("Discard my changes re-seeds from the fresh read", async () => {
    stub({
      [GET]: [ok(availability()), ok(fresh)],
      [PATCH]: [fail(409, "speaker_availability_stale")],
    });
    await typeAndHitStale();
    await screen.findByText("Saved now");
    fireEvent.click(screen.getByRole("button", { name: "Discard my changes" }));
    expect(capacityInput().value).toBe("40");
    expect(pauseInput().value).toBe("");
    const group = screen.getByRole("group", { name: "Unavailable dates 1" });
    expect((within(group).getByLabelText("From") as HTMLInputElement).value).toBe("2027-01-10");
    expect(screen.queryByText(/Someone changed this/)).toBeNull();
    expect(screen.getByRole("status").textContent).toBe("Changes discarded.");
  });

  it("Discard my changes is not offered while the saved version is being re-read", async () => {
    const reread = deferred();
    stub({
      [GET]: [ok(availability()), () => reread.promise],
      [PATCH]: [fail(409, "speaker_availability_stale")],
    });
    await typeAndHitStale();
    const discard = screen.getByRole("button", { name: "Discard my changes" }) as HTMLButtonElement;
    expect(discard.disabled).toBe(true);
    fireEvent.click(discard);
    expectTypedValuesKept();
    await act(async () => reread.resolve(ok(fresh)));
    await screen.findByText("Saved now");
    expect(
      (screen.getByRole("button", { name: "Discard my changes" }) as HTMLButtonElement).disabled,
    ).toBe(false);
  });

  it("a stale state cleared during the re-read stays cleared when the re-read lands", async () => {
    // The re-read is still in flight when the stale state is cleared (here by a
    // principal switch, which resets the panel). Its late answer must not bring
    // the stale view back.
    const reread = deferred();
    stub({
      [GET]: [
        ok(availability()),
        () => reread.promise,
        ok(availability({ declared_capacity_hours_per_90_days: 22 })),
      ],
      [PATCH]: [fail(409, "speaker_availability_stale")],
    });
    const client = makeClient();
    const view = render(
      <QueryClientProvider client={client}>
        <SpeakerAvailabilityPanel unitId={UNIT} professionalId={PID} contactName="Dana Reyes" />
      </QueryClientProvider>,
    );
    await screen.findByText(/Stated: no dates blocked\./);
    fireEvent.change(capacityInput(), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: "Save availability" }));
    await screen.findByText(/Someone changed this/);
    await waitFor(() => expect(count(GET)).toBe(2));

    principal.key = "principal-2";
    view.rerender(
      <QueryClientProvider client={client}>
        <SpeakerAvailabilityPanel unitId={UNIT} professionalId={PID} contactName="Dana Reyes" />
      </QueryClientProvider>,
    );
    await screen.findByText("22 hours per 90 days");
    expect(screen.queryByText(/Someone changed this/)).toBeNull();

    await act(async () => reread.resolve(ok(fresh)));
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.queryByText(/Someone changed this/)).toBeNull();
    expect(screen.queryByText(/Your changes are still in the form/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Save my changes over it" })).toBeNull();
    expect(screen.queryByText("Saved now")).toBeNull();
  });

  it("no automatic retry after 409", async () => {
    stub({
      [GET]: [ok(availability()), ok(fresh)],
      [PATCH]: [fail(409, "speaker_availability_stale")],
    });
    await typeAndHitStale();
    await screen.findByText("Saved now");
    await new Promise((r) => setTimeout(r, 50));
    expect(count(PATCH)).toBe(1);
  });

  it("stale re-read fails: every typed value kept, 'Save my changes over it' disabled with reason", async () => {
    stub({
      [GET]: [ok(availability()), fail(500, "internal_error")],
      [PATCH]: [fail(409, "speaker_availability_stale")],
    });
    await typeAndHitStale();
    await screen.findByText(/Availability could not be loaded\./);
    expectTypedValuesKept();
    const overwrite = screen.getByRole("button", {
      name: "Save my changes over it",
    }) as HTMLButtonElement;
    expect(overwrite.disabled).toBe(true);
    const reasons = (overwrite.getAttribute("aria-describedby") ?? "")
      .split(" ")
      .map((id) => document.getElementById(id)?.textContent ?? "");
    expect(reasons).toContain(
      "The saved version could not be re-read, so there is nothing to save over yet. Retry the read first.",
    );
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });
});

describe("<SpeakerAvailabilityPanel /> save errors", () => {
  it("422 window_invalid with details.index 1 attaches the error to window 2 and focuses its From input", async () => {
    stub({
      [GET]: [ok(WINDOWED)],
      [PATCH]: [
        fail(422, "speaker_availability_window_invalid", { field: "unavailable", index: 1 }),
      ],
    });
    renderPanel();
    await screen.findByText(/2 blocked date ranges\./);
    fireEvent.change(capacityInput(), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: "Save availability" }));
    const message = await screen.findByText(
      /^Window 2 \(December 20, 2026 to December 31, 2026\) cannot be saved\./,
    );
    const group = screen.getByRole("group", { name: "Unavailable dates 2" });
    const from = within(group).getByLabelText("From");
    expect(group.contains(message)).toBe(true);
    expect(message.getAttribute("role")).toBe("alert");
    expect(from.getAttribute("aria-invalid")).toBe("true");
    expect((from.getAttribute("aria-describedby") ?? "").split(" ")).toContain(message.id);
    await waitFor(() => expect(document.activeElement).toBe(from));
  });

  it.each([
    [422, "speaker_availability_too_many_windows", { field: "unavailable", limit: 20 }, /at most 20 blocked date ranges/],
    [422, "speaker_availability_pause_invalid", { field: "invitations_paused_until" }, /The pause must end today/],
    [422, "speaker_availability_capacity_invalid", { field: "declared_capacity_hours_per_90_days" }, /Capacity must be more than 0/],
    [404, "speaker_contact_not_found", undefined, /no longer in your unit's roster/],
    [404, "unit_not_found", undefined, /Server says unit_not_found\. Nothing was changed\./],
    [403, "forbidden", undefined, /^The server refused this request \(403\)\./],
    [422, "invalid_request", undefined, /The server could not read this form/],
    [429, "rate_limited", undefined, /Too many requests just now/],
    [401, "unauthenticated", undefined, /Your session has ended/],
    [500, "internal_error", undefined, /the server gave no reason/],
  ])("%s %s shows its message and keeps the draft", async (status, code, details, pattern) => {
    stub({ [GET]: [ok(availability())], [PATCH]: [fail(status, code, details)] });
    renderPanel();
    await screen.findByText(/Stated: no dates blocked\./);
    fireEvent.change(capacityInput(), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: "Save availability" }));
    await waitFor(() =>
      expect(
        screen.getAllByRole("alert").some((el) => pattern.test(el.textContent ?? "")),
      ).toBe(true),
    );
    expect(capacityInput().value).toBe("12");
    expect(count(PATCH)).toBe(1);
  });

  it("GET 403 renders the refusal and no form", async () => {
    stub({ [GET]: [fail(403, "forbidden")] });
    renderPanel();
    await screen.findByText(/^The server refused this request \(403\)\./);
    expect(region().textContent).toMatch(
      /Reading a Speaker's availability is granted to Speaker Connectors in this unit/,
    );
    expect(screen.queryByLabelText("Capacity (hours per 90 days)")).toBeNull();
    expect(count(GET)).toBe(1);
  });

  it("PATCH 403 keeps the draft", async () => {
    stub({ [GET]: [ok(availability())], [PATCH]: [fail(403, "forbidden")] });
    renderPanel();
    await screen.findByText(/Stated: no dates blocked\./);
    fireEvent.change(capacityInput(), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: "Save availability" }));
    await screen.findByText(/^The server refused this request \(403\)\./);
    expect(capacityInput().value).toBe("12");
  });
});

describe("<SpeakerAvailabilityPanel /> read errors", () => {
  it("GET 500 on first read shows Retry, which re-reads", async () => {
    stub({ [GET]: [fail(500, "internal_error"), ok(availability())] });
    renderPanel();
    await screen.findByText(/^Availability could not be loaded\./);
    expect(screen.queryByLabelText("Capacity (hours per 90 days)")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await screen.findByText(/Stated: no dates blocked\./);
    expect(count(GET)).toBe(2);
  });

  it("GET 404 unit_not_found on first read shows the read-error state", async () => {
    stub({ [GET]: [fail(404, "unit_not_found")] });
    renderPanel();
    await screen.findByText(/^Availability could not be loaded\. Server says unit_not_found\./);
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
    expect(screen.queryByLabelText("Capacity (hours per 90 days)")).toBeNull();
  });

  it("a failed background refetch after a good read keeps the form mounted and shows the error in the form alert", async () => {
    stub({ [GET]: [ok(availability()), fail(500, "internal_error")] });
    const { client } = renderPanel();
    await screen.findByText(/Stated: no dates blocked\./);
    fireEvent.change(capacityInput(), { target: { value: "12" } });
    await act(async () => {
      await client.refetchQueries();
    });
    await screen.findByText(/Availability could not be loaded\./);
    expect(capacityInput().value).toBe("12");
    const formAlert = document.getElementById(`availability-${PID}-form-error`) as HTMLElement;
    expect(formAlert.textContent).toMatch(/Availability could not be loaded\./);
    expect(within(formAlert).getByRole("button", { name: "Retry" })).toBeTruthy();
  });

  it("404 speaker_contact_not_found shows the roster message and invalidates the speaker-contacts prefix", async () => {
    stub({ [GET]: [fail(404, "speaker_contact_not_found")] });
    const client = makeClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    renderPanel(client);
    await screen.findByText(
      "This contact is no longer in your unit's roster, so its availability cannot be read or saved.",
    );
    expect(screen.queryByLabelText("Capacity (hours per 90 days)")).toBeNull();
    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: ["principal-1", "speaker-contacts", UNIT],
      }),
    );
  });
});

describe("<SpeakerAvailabilityPanel /> principal isolation", () => {
  it('the query key is [principal, "speaker-availability", unit, professional]', async () => {
    stub({ [GET]: [ok(availability())] });
    const { client } = renderPanel();
    await screen.findByText(/Stated: no dates blocked\./);
    expect(client.getQueryCache().getAll().map((q) => q.queryKey)).toEqual([
      ["principal-1", "speaker-availability", UNIT, PID],
    ]);
  });

  it("switching principal on one client fetches again and never shows the first principal's data", async () => {
    stub({
      [GET]: [
        () =>
          ok(
            availability({
              declared_capacity_hours_per_90_days: principal.key === "principal-1" ? 11 : 22,
            }),
          ),
      ],
    });
    const client = makeClient();
    const view = renderPanel(client);
    await screen.findByText("11 hours per 90 days");

    principal.key = "principal-2";
    view.rerender(
      <QueryClientProvider client={client}>
        <SpeakerAvailabilityPanel unitId={UNIT} professionalId={PID} contactName="Dana Reyes" />
      </QueryClientProvider>,
    );
    expect(screen.queryByText("11 hours per 90 days")).toBeNull();
    await screen.findByText("22 hours per 90 days");
    expect(count(GET)).toBe(2);
    expect(screen.queryByText("11 hours per 90 days")).toBeNull();
  });

  it("no request while the principal key is null", async () => {
    principal.key = null;
    stub({ [GET]: [ok(availability())] });
    renderPanel();
    await new Promise((r) => setTimeout(r, 30));
    expect(count(GET)).toBe(0);
    expect(within(region()).getByText("Loading availability…")).toBeTruthy();
  });
});

describe("<SpeakerAvailabilityPanel /> workload (B26 T8d V-D)", () => {
  const TITLE = "Corporate treasury guest lecture";
  const gaps: EngagementWithoutEndTime[] = [
    {
      engagement_id: "e-own",
      shown: "event",
      event_title: TITLE,
      local_date: "2026-10-20",
      time_precision: "date_only",
      editable_here: true,
    },
    {
      engagement_id: "e-imported",
      shown: "event",
      event_title: "Alumni mentoring breakfast",
      local_date: "2026-11-03",
      time_precision: "exact",
      editable_here: false,
    },
    {
      engagement_id: null,
      shown: "other_unit",
      event_title: null,
      local_date: null,
      time_precision: null,
      editable_here: false,
    },
  ];

  function renderRouted(client = makeClient()) {
    return render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <SpeakerAvailabilityPanel unitId={UNIT} professionalId={PID} contactName="Dana Reyes" />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it("the panel shows the workload section with the connector copy", async () => {
    stub({ [GET]: [ok(availability({ load: speakerLoadFixture({ band: "moderate" }) }))] });
    renderRouted();
    await screen.findByText(/Stated: no dates blocked\./);
    const group = within(region()).getByRole("group", { name: "Workload" });
    expect(within(group).getByRole("heading", { level: 4, name: "Workload" })).toBeTruthy();
    expect(within(group).getByText("Moderate")).toBeTruthy();
    expect(group.textContent).toContain("Matching does not use workload yet.");
    expect(group.textContent).toContain(
      "Recent and upcoming confirmed engagements, against the stated capacity.",
    );
    // Between the read states and the form.
    const form = screen.getByLabelText("Capacity (hours per 90 days)");
    expect(group.compareDocumentPosition(form) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it.each(["light", "moderate", "heavy", "full", "unknown"] as const)(
    "no /\\bavailable\\b/i in the panel for a %s band",
    async (band) => {
      stub({
        [GET]: [
          ok(
            availability({
              load: speakerLoadFixture({
                band,
                reason: band === "unknown" ? "hours_unknown" : "measured",
                used_in_matching: true,
                engagements_without_end_time: gaps,
                engagements_without_end_time_truncated: true,
              }),
            }),
          ),
        ],
      });
      renderRouted();
      await screen.findByText(/Stated: no dates blocked\./);
      expect(within(region()).getByRole("group", { name: "Workload" })).toBeTruthy();
      expect(region().textContent).not.toMatch(/\bavailable\b/i);
    },
  );

  it("the Events link is present only for an editable item", async () => {
    stub({
      [GET]: [
        ok(
          availability({
            load: speakerLoadFixture({
              band: "unknown",
              reason: "hours_unknown",
              engagements_without_end_time: gaps,
            }),
          }),
        ),
      ],
    });
    renderRouted();
    await screen.findByText(/Stated: no dates blocked\./);
    const group = within(region()).getByRole("group", { name: "Workload" });
    const links = within(group).getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(
      within(group).getByRole("link", {
        name: `Add the end time for ${TITLE} on the Events page`,
      }),
    ).toBeTruthy();
  });

  it("no workload section before the read answers", async () => {
    const pending = deferred();
    stub({ [GET]: [() => pending.promise] });
    renderRouted();
    expect(within(region()).queryByRole("group", { name: "Workload" })).toBeNull();
    await act(async () => pending.resolve(ok(availability())));
    await screen.findByText(/Stated: no dates blocked\./);
    expect(within(region()).getByRole("group", { name: "Workload" })).toBeTruthy();
  });
});
