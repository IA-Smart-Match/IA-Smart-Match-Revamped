/**
 * Opening results asks first, inline (DESIGN.md §11.1).
 *
 * "Open results" becomes "Open results for {event}? Every team can then run
 * results once for this event." with "Open results now" and "Not yet". The
 * unlock POST is sent only by "Open results now"; "Not yet" and Escape put the
 * row back and send nothing.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { UnlockPanel } from "./InstructorUnlock";
import { pastTheConfirmGuard } from "./inlineConfirmGuard.testkit";

const EVENTS = "/v1/exercise/instructor/events";
const TEAMS_FILE = "11111111-1111-1111-1111-111111111111";

let calls: { url: string; method: string }[] = [];

function stub(): void {
  let unlocked = false;
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => {
      const method = init.method ?? "GET";
      calls.push({ url, method });
      const path = url.split("?")[0];
      if (method === "POST" && path === `${EVENTS}/harbor/unlock`) {
        unlocked = true;
        return Promise.resolve(
          new Response(JSON.stringify({ event_key: "harbor", unlocked: true }), { status: 200 }),
        );
      }
      const body = {
        dataset_id: TEAMS_FILE,
        dataset_label: "Ann's file, 25 September",
        events: [
          { event_key: "northline", name: "Northline Analytics", unlocked: true },
          { event_key: "harbor", name: "Harbor Consumer Brands", unlocked },
        ],
      };
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
    }),
  );
}

function unlockPosts(): number {
  return calls.filter((call) => call.method === "POST" && call.url.includes("/unlock")).length;
}

function renderPanel(): void {
  render(
    <UnlockPanel onRefusal={vi.fn()} onUnlocked={vi.fn()} onSignedOut={vi.fn()} reloadKey={0} />,
  );
}

async function harborRow(): Promise<HTMLElement> {
  return (await screen.findByText("Harbor Consumer Brands")).closest("li") as HTMLElement;
}

afterEach(() => {
  cleanup();
  calls = [];
  vi.unstubAllGlobals();
});

describe("<UnlockPanel /> lock chips", () => {
  it("read exactly as Ann's checklist of 2026-10-02: no trailing full stop", async () => {
    stub();
    renderPanel();
    const open = (await screen.findByText("Northline Analytics")).closest("li") as HTMLElement;
    const closed = (await harborRow()) as HTMLElement;
    expect(within(open).getByText("Results open")).toBeDefined();
    expect(within(closed).getByText("Results closed")).toBeDefined();
    expect(open.textContent).not.toContain("Results open.");
    expect(closed.textContent).not.toContain("Results closed.");
  });
});

describe("<UnlockPanel /> asks before it opens results", () => {
  it("sends no unlock on the first press, and asks in the §11.1 words", async () => {
    stub();
    renderPanel();
    const row = await harborRow();
    fireEvent.click(within(row).getByRole("button", { name: /^open results$/i }));

    expect(row.textContent).toContain(
      "Open results for Harbor Consumer Brands? Every team can then run results once for this event.",
    );
    expect(within(row).getByRole("button", { name: /^open results now$/i })).toBeDefined();
    expect(within(row).getByRole("button", { name: /^not yet$/i })).toBeDefined();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(unlockPosts()).toBe(0);
  });

  it("sends exactly one unlock on Open results now", async () => {
    stub();
    renderPanel();
    const row = await harborRow();
    fireEvent.click(within(row).getByRole("button", { name: /^open results$/i }));
    await pastTheConfirmGuard();
    fireEvent.click(within(row).getByRole("button", { name: /^open results now$/i }));

    await waitFor(() => expect(unlockPosts()).toBe(1));
    await waitFor(() =>
      expect(screen.getByText("Harbor Consumer Brands").closest("li")?.textContent).toContain(
        "Results open",
      ),
    );
    expect(unlockPosts()).toBe(1);
    const unlock = calls.find((call) => call.url.includes("/unlock"));
    expect(unlock?.url).toBe(`${EVENTS}/harbor/unlock?dataset_id=${TEAMS_FILE}`);
  });

  it("sends nothing on Not yet, and puts the button back", async () => {
    stub();
    renderPanel();
    const row = await harborRow();
    fireEvent.click(within(row).getByRole("button", { name: /^open results$/i }));
    fireEvent.click(within(row).getByRole("button", { name: /^not yet$/i }));

    expect(within(row).queryByRole("button", { name: /^open results now$/i })).toBeNull();
    expect(within(row).getByRole("button", { name: /^open results$/i })).toBeDefined();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(unlockPosts()).toBe(0);
  });

  it("sends nothing on Escape, and puts the button back", async () => {
    stub();
    renderPanel();
    const row = await harborRow();
    fireEvent.click(within(row).getByRole("button", { name: /^open results$/i }));
    const confirm = within(row).getByRole("button", { name: /^open results now$/i });
    fireEvent.keyDown(confirm, { key: "Escape" });

    expect(within(row).queryByRole("button", { name: /^open results now$/i })).toBeNull();
    expect(within(row).getByRole("button", { name: /^open results$/i })).toBeDefined();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(unlockPosts()).toBe(0);
  });
});
