/**
 * A question that moves focus onto its own "yes" must not be answered by the
 * press that opened it (PR #346 review; issue #321).
 *
 * "Refresh every team…" and "Open results" / "Close results" put the question
 * in the page and move focus to the confirming button. A held Enter then
 * repeats on that button, and a double-click lands on it, so the class-wide
 * request went out with the question unread. Now a repeated Enter or Space is
 * ignored there, and so is any press inside `CONFIRM_GUARD_MS` of the question
 * opening. A deliberate press after that sends exactly once.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CONFIRM_GUARD_MS } from "./desk";
import {
  REFRESH_ALL_LABEL,
  REFRESH_ALL_QUESTION,
  RefreshAllPanel,
  UnlockPanel,
} from "./InstructorUnlock";

const EVENTS = "/v1/exercise/instructor/events";
const REFRESH_ALL = "/v1/exercise/instructor/refresh-all";
const FILE = "11111111-1111-1111-1111-111111111111";
const REPORT = { refreshed_team_numbers: [], refreshed: 0, skipped: 0, teams: [] };

let posts: string[] = [];

/** `harborOpen` is the state the Harbor row starts in; a POST flips it. */
function stub(harborOpen: boolean): void {
  let unlocked = harborOpen;
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => {
      const method = init.method ?? "GET";
      const path = url.split("?")[0];
      if (method === "POST") {
        posts.push(path);
        if (path === REFRESH_ALL) {
          return Promise.resolve(new Response(JSON.stringify(REPORT), { status: 200 }));
        }
        unlocked = path.endsWith("/unlock");
        return Promise.resolve(
          new Response(JSON.stringify({ event_key: "harbor", unlocked }), { status: 200 }),
        );
      }
      const body = {
        dataset_id: FILE,
        dataset_label: "October file",
        events: [{ event_key: "harbor", name: "Harbor Consumer Brands", unlocked }],
      };
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
    }),
  );
}

/**
 * A key held down, as the browser delivers it: a repeated `keydown` that
 * clicks the focused button unless the page prevents it.
 */
function heldKey(button: HTMLElement, key: "Enter" | " "): void {
  const allowed = fireEvent.keyDown(button, { key, repeat: true });
  if (allowed) {
    fireEvent.click(button);
  }
}

const pastTheGuard = (): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, CONFIRM_GUARD_MS + 20));
const aMoment = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 20));

beforeEach(() => {
  posts = [];
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("refresh every team: the question cannot be answered by the press that opened it", () => {
  function open(): HTMLElement {
    stub(false);
    render(<RefreshAllPanel onDone={vi.fn()} onSignedOut={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: REFRESH_ALL_LABEL }));
    const confirm = screen.getByRole("button", { name: "Refresh them now" });
    expect(document.activeElement).toBe(confirm);
    return confirm;
  }

  it("ignores a held Enter or Space on “Refresh them now”, however long it is held", async () => {
    const confirm = open();
    heldKey(confirm, "Enter");
    heldKey(confirm, " ");
    await pastTheGuard();
    heldKey(confirm, "Enter");
    heldKey(confirm, " ");
    await aMoment();

    expect(posts).toEqual([]);
    expect(screen.getByRole("button", { name: "Refresh them now" })).toBeDefined();
  });

  it("ignores a click that lands just after the question opens", async () => {
    const confirm = open();
    fireEvent.click(confirm);
    await aMoment();

    expect(posts).toEqual([]);
    // The question is still up, to be read and answered.
    expect(screen.getByRole("button", { name: "Refresh them now" })).toBeDefined();
  });

  it("sends exactly once on a deliberate press after that", async () => {
    const confirm = open();
    fireEvent.click(confirm);
    await pastTheGuard();
    fireEvent.click(confirm);

    await waitFor(() => expect(posts).toEqual([REFRESH_ALL]));
    await screen.findByText("No team has entered a number yet, so there was nothing to refresh.");
    expect(posts).toEqual([REFRESH_ALL]);
  });
});

describe("refresh every team: the question is read with its answer", () => {
  it("names the group the two buttons are in with the scope sentence, once", () => {
    stub(false);
    render(<RefreshAllPanel onDone={vi.fn()} onSignedOut={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: REFRESH_ALL_LABEL }));

    // Focus lands on the button, so the group's name is what is read with it.
    const group = screen.getByRole("group", { name: REFRESH_ALL_QUESTION });
    const confirm = within(group).getByRole("button", { name: "Refresh them now" });
    expect(document.activeElement).toBe(confirm);
    expect(within(group).getByRole("button", { name: "Not yet" })).toBeDefined();

    // Once: the sentence is the group's name only. It is not also the button's
    // description, and it is not a live region that would speak it again.
    expect(confirm.getAttribute("aria-describedby")).toBeNull();
    expect(confirm.getAttribute("aria-labelledby")).toBeNull();
    const sentence = within(group).getByText(REFRESH_ALL_QUESTION);
    expect(sentence.getAttribute("aria-live")).toBeNull();
    expect(sentence.getAttribute("role")).toBeNull();
    expect(group.getAttribute("aria-live")).toBeNull();
    expect(screen.getAllByText(REFRESH_ALL_QUESTION)).toHaveLength(1);
  });
});

describe.each([
  { starts: "closed", harborOpen: false, ask: "Open results", yes: "Open results now", path: "unlock" },
  { starts: "open", harborOpen: true, ask: "Close results", yes: "Close results now", path: "lock" },
])("$ask: the question cannot be answered by the press that opened it", ({ harborOpen, ask, yes, path }) => {
  async function open(): Promise<HTMLElement> {
    stub(harborOpen);
    render(
      <UnlockPanel onRefusal={vi.fn()} onUnlocked={vi.fn()} onSignedOut={vi.fn()} reloadKey={0} />,
    );
    const row = (await screen.findByText("Harbor Consumer Brands")).closest("li") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: ask }));
    const confirm = within(row).getByRole("button", { name: yes });
    await waitFor(() => expect(document.activeElement).toBe(confirm));
    return confirm;
  }

  it(`ignores a held Enter or Space on “${yes}”`, async () => {
    const confirm = await open();
    heldKey(confirm, "Enter");
    heldKey(confirm, " ");
    await pastTheGuard();
    heldKey(confirm, "Enter");
    await aMoment();

    expect(posts).toEqual([]);
    expect(screen.getByRole("button", { name: yes })).toBeDefined();
  });

  it("ignores a click that lands just after the question opens", async () => {
    const confirm = await open();
    fireEvent.click(confirm);
    await aMoment();

    expect(posts).toEqual([]);
    expect(screen.getByRole("button", { name: yes })).toBeDefined();
  });

  it("sends exactly once on a deliberate press after that", async () => {
    const confirm = await open();
    await pastTheGuard();
    fireEvent.click(confirm);

    await waitFor(() => expect(posts).toEqual([`${EVENTS}/harbor/${path}`]));
    await waitFor(() => expect(screen.queryByRole("button", { name: yes })).toBeNull());
    expect(posts).toEqual([`${EVENTS}/harbor/${path}`]);
  });
});
