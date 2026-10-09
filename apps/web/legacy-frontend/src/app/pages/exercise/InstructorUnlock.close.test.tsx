/**
 * Results can be closed again, and each row says when (issue #326).
 *
 * Ann, 2026-10-02: "Opening or closing results for an event shows the time it
 * was done, and results can be closed again." Her checklist reads the labels
 * as "Results closed" and "Results open".
 *
 * - The chip words are the checklist's, and the time sits beside them.
 * - "Close results" asks first, in the row. Only "Close results now" sends the
 *   lock; "Keep them open" and Escape put the row back and send nothing.
 * - After a close lands, focus is on the event's name, not on "Open results":
 *   a repeated Enter must not undo what was just done.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { clockTime } from "./exerciseTime";
import { UnlockPanel } from "./InstructorUnlock";
import { pastTheConfirmGuard } from "./inlineConfirmGuard.testkit";

const EVENTS = "/v1/exercise/instructor/events";
const TEAMS_FILE = "11111111-1111-1111-1111-111111111111";
const OPENED_AT = "2026-10-16T17:42:00Z";
const CLOSED_AT = "2026-10-16T17:50:00Z";
const REOPENED_AT = "2026-10-16T17:55:00Z";

let calls: { url: string; method: string }[] = [];

interface Lock {
  unlocked: boolean;
  unlocked_at: string | null;
  closed_at: string | null;
}

function stub(northline: Lock): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => {
      const method = init.method ?? "GET";
      calls.push({ url, method });
      const path = url.split("?")[0];
      if (method === "POST" && path === `${EVENTS}/northline/lock`) {
        northline.unlocked = false;
        northline.closed_at = CLOSED_AT;
        return Promise.resolve(
          new Response(
            JSON.stringify({ event_key: "northline", unlocked: false, closed_at: CLOSED_AT }),
            { status: 200 },
          ),
        );
      }
      if (method === "POST" && path === `${EVENTS}/northline/unlock`) {
        northline.unlocked = true;
        northline.unlocked_at = REOPENED_AT;
        northline.closed_at = null;
        return Promise.resolve(
          new Response(
            JSON.stringify({ event_key: "northline", unlocked: true, unlocked_at: REOPENED_AT }),
            { status: 200 },
          ),
        );
      }
      const body = {
        dataset_id: TEAMS_FILE,
        dataset_label: "Ann's file, 2 October",
        events: [
          { event_key: "northline", name: "Northline Analytics", ...northline },
          {
            event_key: "harbor",
            name: "Harbor Consumer Brands",
            unlocked: false,
            unlocked_at: null,
            closed_at: null,
          },
        ],
      };
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
    }),
  );
}

function open(): Lock {
  return { unlocked: true, unlocked_at: OPENED_AT, closed_at: null };
}

function posts(action: "lock" | "unlock"): { url: string; method: string }[] {
  return calls.filter((call) => call.method === "POST" && call.url.includes(`/${action}`));
}

function renderPanel(onUnlocked: () => void = vi.fn()): void {
  render(
    <UnlockPanel onRefusal={vi.fn()} onUnlocked={onUnlocked} onSignedOut={vi.fn()} reloadKey={0} />,
  );
}

async function row(name: string): Promise<HTMLElement> {
  return (await screen.findByText(name)).closest("li") as HTMLElement;
}

function northlineRow(): HTMLElement {
  return screen.getByText("Northline Analytics").closest("li") as HTMLElement;
}

afterEach(() => {
  cleanup();
  calls = [];
  vi.unstubAllGlobals();
});

describe("<UnlockPanel /> says whether results are open, and when", () => {
  it("reads “Results open” with the time it was opened, and offers to close", async () => {
    stub(open());
    renderPanel();
    const northline = await row("Northline Analytics");

    expect(within(northline).getByText("Results open")).toBeDefined();
    expect(within(northline).getByRole("status").textContent).toBe(
      `Opened at ${clockTime(OPENED_AT)}.`,
    );
    expect(within(northline).getByRole("button", { name: /^close results$/i })).toBeDefined();
    expect(within(northline).queryByRole("button", { name: /^open results$/i })).toBeNull();
  });

  it("reads “Results closed” with no time for an event never opened", async () => {
    stub(open());
    renderPanel();
    const harbor = await row("Harbor Consumer Brands");

    expect(within(harbor).getByText("Results closed")).toBeDefined();
    expect(within(harbor).getByRole("status").textContent).toBe("");
    expect(within(harbor).getByRole("button", { name: /^open results$/i })).toBeDefined();
  });

  it("reads “Results closed” with the time it was closed, and offers to open again", async () => {
    stub({ unlocked: false, unlocked_at: OPENED_AT, closed_at: CLOSED_AT });
    renderPanel();
    const northline = await row("Northline Analytics");

    expect(within(northline).getByText("Results closed")).toBeDefined();
    expect(within(northline).getByRole("status").textContent).toBe(
      `Closed at ${clockTime(CLOSED_AT)}.`,
    );
    expect(within(northline).getByRole("button", { name: /^open results$/i })).toBeDefined();
  });
});

describe("<UnlockPanel /> asks before it closes results", () => {
  it("sends no lock on the first press, and says what will change", async () => {
    stub(open());
    renderPanel();
    const northline = await row("Northline Analytics");
    fireEvent.click(within(northline).getByRole("button", { name: /^close results$/i }));

    expect(northline.textContent).toContain(
      "Close results for Northline Analytics? Teams that have not run results yet cannot run them until you open results again. Results already run stay on each team's screen.",
    );
    expect(within(northline).getByRole("button", { name: /^close results now$/i })).toBeDefined();
    expect(within(northline).getByRole("button", { name: /^keep them open$/i })).toBeDefined();
    await waitFor(() => expect(document.activeElement?.textContent).toBe("Close results now"));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(posts("lock")).toHaveLength(0);
  });

  it("sends exactly one lock on Close results now, then shows the closing time", async () => {
    stub(open());
    const onUnlocked = vi.fn();
    renderPanel(onUnlocked);
    const northline = await row("Northline Analytics");
    fireEvent.click(within(northline).getByRole("button", { name: /^close results$/i }));
    await pastTheConfirmGuard();
    fireEvent.click(within(northline).getByRole("button", { name: /^close results now$/i }));

    await waitFor(() =>
      expect(within(northlineRow()).getByRole("status").textContent).toBe(
        `Closed at ${clockTime(CLOSED_AT)}.`,
      ),
    );
    expect(within(northlineRow()).getByText("Results closed")).toBeDefined();
    expect(posts("lock").map((call) => call.url)).toEqual([
      `${EVENTS}/northline/lock?dataset_id=${TEAMS_FILE}`,
    ]);
    expect(posts("unlock")).toHaveLength(0);
    expect(onUnlocked).toHaveBeenCalledTimes(1);
  });

  it("puts focus on the event's name after closing, not on Open results", async () => {
    stub(open());
    renderPanel();
    const northline = await row("Northline Analytics");
    fireEvent.click(within(northline).getByRole("button", { name: /^close results$/i }));
    await waitFor(() => expect(document.activeElement?.textContent).toBe("Close results now"));
    await pastTheConfirmGuard();
    fireEvent.click(within(northline).getByRole("button", { name: /^close results now$/i }));

    await waitFor(() => expect(within(northlineRow()).getByText("Results closed")).toBeDefined());
    await waitFor(() => expect(document.activeElement?.textContent).toBe("Northline Analytics"));
  });

  it.each([
    ["Keep them open", (confirm: HTMLElement, keep: HTMLElement) => fireEvent.click(keep)],
    ["Escape", (confirm: HTMLElement) => fireEvent.keyDown(confirm, { key: "Escape" })],
  ])("sends nothing on %s, and puts the button back", async (_name, dismiss) => {
    stub(open());
    renderPanel();
    const northline = await row("Northline Analytics");
    fireEvent.click(within(northline).getByRole("button", { name: /^close results$/i }));
    dismiss(
      within(northline).getByRole("button", { name: /^close results now$/i }),
      within(northline).getByRole("button", { name: /^keep them open$/i }),
    );

    expect(within(northline).queryByRole("button", { name: /^close results now$/i })).toBeNull();
    expect(within(northline).getByRole("button", { name: /^close results$/i })).toBeDefined();
    expect(within(northline).getByText("Results open")).toBeDefined();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(posts("lock")).toHaveLength(0);
  });

  it("opens a closed event again and shows the time of that opening", async () => {
    stub({ unlocked: false, unlocked_at: OPENED_AT, closed_at: CLOSED_AT });
    renderPanel();
    const northline = await row("Northline Analytics");
    fireEvent.click(within(northline).getByRole("button", { name: /^open results$/i }));
    await pastTheConfirmGuard();
    fireEvent.click(within(northline).getByRole("button", { name: /^open results now$/i }));

    await waitFor(() =>
      expect(within(northlineRow()).getByRole("status").textContent).toBe(
        `Opened at ${clockTime(REOPENED_AT)}.`,
      ),
    );
    expect(within(northlineRow()).getByText("Results open")).toBeDefined();
    expect(posts("unlock")).toHaveLength(1);
  });
});
