/**
 * The unlock confirm belongs to the list it was opened on, focus is never
 * dropped, and one confirm sends one unlock (#250 review).
 *
 * - An open confirm closes when its list is refused or re-read onto another
 *   data file, so no press can send an unlock the instructor did not see
 *   asked, and "Check again" does not bring back a confirm with focus on it.
 * - After "Open results now" lands or is refused, focus goes somewhere in the
 *   row rather than to `<body>` (§8.5).
 * - A second press while the unlock is in flight sends nothing.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { UnlockPanel } from "./InstructorUnlock";

const EVENTS = "/v1/exercise/instructor/events";
const FIRST_FILE = "11111111-1111-1111-1111-111111111111";
const SECOND_FILE = "22222222-2222-2222-2222-222222222222";

interface Answer {
  readonly body: unknown;
  readonly status?: number;
  readonly gate?: Promise<void>;
}

function list(datasetId: string, harborOpen: boolean): Answer {
  return {
    body: {
      dataset_id: datasetId,
      dataset_label: "Ann's file, 25 September",
      events: [
        { event_key: "northline", name: "Northline Analytics", unlocked: true },
        { event_key: "harbor", name: "Harbor Consumer Brands", unlocked: harborOpen },
      ],
    },
  };
}

const NO_TEAMS_YET: Answer = {
  body: { error: { code: "exercise_no_teams_yet", message: "No team has entered a number yet." } },
  status: 409,
};

const UNLOCK_REFUSED: Answer = {
  body: {
    error: { code: "exercise_dataset_has_no_teams", message: "No team is working in that data file." },
  },
  status: 409,
};

let calls: { url: string; method: string }[] = [];
/** The answers, by "METHOD path"; tests replace them between steps. */
let answers: Record<string, Answer> = {};

function stub(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit) => {
      const method = init.method ?? "GET";
      calls.push({ url, method });
      const answer = answers[`${method} ${url.split("?")[0]}`] ?? {
        body: { error: { code: "test_unstubbed", message: url } },
        status: 404,
      };
      const respond = () =>
        new Response(JSON.stringify(answer.body), { status: answer.status ?? 200 });
      return answer.gate === undefined ? Promise.resolve(respond()) : answer.gate.then(respond);
    }),
  );
}

function gate(): { readonly promise: Promise<void>; readonly open: () => void } {
  let open: () => void = () => undefined;
  const promise = new Promise<void>((resolve) => {
    open = resolve;
  });
  return { promise, open };
}

function unlockPosts(): { url: string; method: string }[] {
  return calls.filter((call) => call.method === "POST" && call.url.includes("/unlock"));
}

function panel(reloadKey: number): React.JSX.Element {
  return (
    <UnlockPanel
      onRefusal={vi.fn()}
      onUnlocked={vi.fn()}
      onSignedOut={vi.fn()}
      reloadKey={reloadKey}
    />
  );
}

function harborRow(): HTMLElement {
  return screen.getByText("Harbor Consumer Brands").closest("li") as HTMLElement;
}

async function openConfirm(): Promise<void> {
  await screen.findByText("Harbor Consumer Brands");
  fireEvent.click(within(harborRow()).getByRole("button", { name: /^open results$/i }));
  await waitFor(() =>
    expect(document.activeElement?.textContent).toBe("Open results now"),
  );
}

afterEach(() => {
  cleanup();
  calls = [];
  answers = {};
  vi.unstubAllGlobals();
});

describe("<UnlockPanel /> confirm belongs to its list", () => {
  it("closes when the list is refused, and Check again does not bring it back", async () => {
    answers = { [`GET ${EVENTS}`]: list(FIRST_FILE, false) };
    stub();
    const { rerender } = render(panel(0));
    await openConfirm();

    answers[`GET ${EVENTS}`] = NO_TEAMS_YET;
    rerender(panel(1));
    await screen.findByText("No team has entered a number yet.");

    answers[`GET ${EVENTS}`] = list(FIRST_FILE, false);
    fireEvent.click(screen.getByRole("button", { name: /check again/i }));
    await screen.findByText("Harbor Consumer Brands");

    expect(screen.queryByRole("button", { name: /open results now/i })).toBeNull();
    expect(document.activeElement?.textContent).not.toBe("Open results now");
    expect(unlockPosts()).toHaveLength(0);
  });

  it("closes when a re-read moves the list to another data file", async () => {
    answers = { [`GET ${EVENTS}`]: list(FIRST_FILE, false) };
    stub();
    const { rerender } = render(panel(0));
    await openConfirm();

    answers[`GET ${EVENTS}`] = list(SECOND_FILE, false);
    rerender(panel(1));
    await waitFor(() =>
      expect(calls.filter((call) => call.url === EVENTS)).toHaveLength(2),
    );
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /open results now/i })).toBeNull(),
    );
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.queryByRole("button", { name: /open results now/i })).toBeNull();
    expect(unlockPosts()).toHaveLength(0);
  });
});

describe("<UnlockPanel /> keeps focus in the row", () => {
  it("returns focus to Open results when the unlock is refused", async () => {
    answers = {
      [`GET ${EVENTS}`]: list(FIRST_FILE, false),
      [`POST ${EVENTS}/harbor/unlock`]: UNLOCK_REFUSED,
    };
    stub();
    render(panel(0));
    await openConfirm();
    fireEvent.click(screen.getByRole("button", { name: /^open results now$/i }));

    await waitFor(() => expect(unlockPosts()).toHaveLength(1));
    await waitFor(() =>
      expect(document.activeElement).toBe(
        within(harborRow()).getByRole("button", { name: /^open results$/i }),
      ),
    );
  });

  it("moves focus to the event's row when the unlock lands", async () => {
    answers = {
      [`GET ${EVENTS}`]: list(FIRST_FILE, false),
      [`POST ${EVENTS}/harbor/unlock`]: { body: { event_key: "harbor", unlocked: true } },
    };
    stub();
    render(panel(0));
    await openConfirm();
    answers[`GET ${EVENTS}`] = list(FIRST_FILE, true);
    fireEvent.click(screen.getByRole("button", { name: /^open results now$/i }));

    await waitFor(() => expect(harborRow().textContent).toContain("Results are open"));
    await waitFor(() => expect(document.activeElement).not.toBe(document.body));
    expect(harborRow().contains(document.activeElement)).toBe(true);
    expect(document.activeElement?.getAttribute("tabindex")).toBe("-1");
  });
});

describe("<UnlockPanel /> sends one unlock per confirm", () => {
  it("ignores a second press while the unlock is in flight", async () => {
    const held = gate();
    answers = {
      [`GET ${EVENTS}`]: list(FIRST_FILE, false),
      [`POST ${EVENTS}/harbor/unlock`]: {
        body: { event_key: "harbor", unlocked: true },
        gate: held.promise,
      },
    };
    stub();
    render(panel(0));
    await openConfirm();
    const confirm = screen.getByRole("button", { name: /^open results now$/i });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    fireEvent.click(screen.getByRole("button", { name: /opening/i }));

    held.open();
    await waitFor(() => expect(unlockPosts()).toHaveLength(1));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(unlockPosts()).toHaveLength(1);
  });
});
