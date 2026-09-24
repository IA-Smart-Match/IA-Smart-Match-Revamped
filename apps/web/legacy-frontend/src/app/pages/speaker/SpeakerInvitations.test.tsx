/**
 * The Speaker's Invitations page (B26 T6b-4 §5.2, §8.3), against a stubbed
 * `fetch`. It reads `GET /v1/me/invitations` and writes `POST
 * /v1/me/invitations/{id}/response`, and nothing else. Both answers confirm
 * inline; the pressed Confirm button keeps focus with `aria-disabled`; the
 * list re-reads after an answer and focus lands on the answered row.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { MyInvitation } from "@/lib/api";

import { SpeakerInvitations } from "./SpeakerInvitations";

const LIST = "/v1/me/invitations";

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

function open(id: string, title: string, overrides: Partial<MyInvitation> = {}): MyInvitation {
  return {
    invitation_id: id,
    event: { title, date_text: `Thursday 12 March 2027`, local_date: null, time_zone: null },
    dispatched_at: "2026-10-01T12:00:00Z",
    status: "awaiting_response",
    response: null,
    answerable: true,
    ...overrides,
  };
}

function answered(
  row: MyInvitation,
  status: "accepted_invitation" | "declined_invitation",
  by: "speaker" | "speaker_connector" = "speaker",
): MyInvitation {
  return {
    ...row,
    status,
    response: { recorded_at: "2026-10-06T12:00:00Z", recorded_by: by },
    answerable: false,
  };
}

const MIXER = open("inv/1 a", "Spring Mixer", {
  event: {
    title: "Spring Mixer",
    date_text: "Thursday 12 March 2027",
    local_date: "2027-03-12",
    time_zone: "America/Los_Angeles",
  },
});
const LECTURE = open("inv-2", "ACCT 4100 guest lecture");
const PANEL = answered(open("inv-3", "Career panel"), "declined_invitation", "speaker_connector");

function list(rows: MyInvitation[], truncated = false): Answer {
  return { body: { invitations: rows, truncated } };
}

let client: QueryClient;

function renderPage() {
  client = new QueryClient({
    defaultOptions: { queries: { retry: false, networkMode: "always", staleTime: 0 } },
  });
  const router = createMemoryRouter(
    [
      { path: "/speaker-portal/invitations", element: <SpeakerInvitations /> },
      { path: "/login", element: <p>Sign-in page</p> },
    ],
    { initialEntries: ["/speaker-portal/invitations"] },
  );
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

function section(name: string): HTMLElement {
  const container = screen.getByRole("heading", { level: 2, name }).closest("section");
  if (container === null) throw new Error(`no section ${name}`);
  return container;
}

function row(title: string): HTMLElement {
  const item = screen.getByRole("heading", { level: 3, name: title }).closest("li");
  if (item === null) throw new Error(`no row ${title}`);
  return item;
}

function gets(): number {
  return calls.filter((call) => call.method === "GET").length;
}

function posts(): typeof calls {
  return calls.filter((call) => call.method === "POST");
}

const MIXER_URL = `${LIST}/inv%2F1%20a/response`;

/**
 * An accessible-name matcher. jsdom's name computation puts a space between a
 * text node and the sr-only span that follows it ("Go back , keep…"), which a
 * browser does not do for an inline span; collapse it before comparing.
 */
function named(expected: string): (name: string) => boolean {
  return (name) => name.replace(/\s+,/g, ",") === expected;
}

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

describe("<SpeakerInvitations />", () => {
  it("groups rows into Waiting for your answer and Answered", async () => {
    stub({ [`GET ${LIST}`]: list([MIXER, PANEL, LECTURE]) });
    renderPage();
    await screen.findByText("Spring Mixer");
    const waiting = within(section("Waiting for your answer"))
      .getAllByRole("heading", { level: 3 })
      .map((h) => h.textContent);
    expect(waiting).toEqual(["Spring Mixer", "ACCT 4100 guest lecture"]);
    const done = within(section("Answered"))
      .getAllByRole("heading", { level: 3 })
      .map((h) => h.textContent);
    expect(done).toEqual(["Career panel"]);
    expect(within(section("Answered")).queryAllByRole("button")).toHaveLength(0);
  });

  it("shows date_text verbatim and the local date when present; says Sent, never delivered", async () => {
    stub({ [`GET ${LIST}`]: list([MIXER, LECTURE]) });
    renderPage();
    await screen.findByText("Spring Mixer");
    const mixer = row("Spring Mixer");
    expect(mixer.textContent).toContain("Date in the invitation: Thursday 12 March 2027");
    expect(mixer.textContent).toContain("March 12, 2027");
    expect(mixer.querySelector("time[datetime='2027-03-12']")).not.toBeNull();
    expect(mixer.textContent).toMatch(/Sent Oct 1, 2026/);
    expect(mixer.querySelector("time[datetime='2026-10-01T12:00:00Z']")).not.toBeNull();
    expect(document.body.textContent).not.toMatch(/deliver/i);
    expect(row("ACCT 4100 guest lecture").textContent).not.toContain("Event date");
  });

  it("answered rows say who recorded the answer and never show an id", async () => {
    const mine = answered(open("inv-4", "Alumni night"), "accepted_invitation");
    stub({ [`GET ${LIST}`]: list([PANEL, mine]) });
    renderPage();
    await screen.findByText("Career panel");
    expect(row("Career panel").textContent).toContain(
      "Your Speaker Connector recorded that you declined",
    );
    expect(row("Alumni night").textContent).toContain("You accepted");
    expect(document.body.textContent).not.toContain("inv-4");
    expect(document.body.textContent).not.toContain("inv-3");
  });

  it("Accept opens the confirm row and moves focus to Confirm accept; Go back returns focus to Accept", async () => {
    stub({ [`GET ${LIST}`]: list([MIXER]) });
    renderPage();
    const accept = await screen.findByRole("button", { name: "Accept invitation to Spring Mixer" });
    fireEvent.click(accept);
    expect(row("Spring Mixer").textContent).toContain(
      "Accept this invitation? Your first answer is final. To change it later, contact your Speaker Connector.",
    );
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Confirm accept invitation to Spring Mixer" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: named("Go back, keep invitation to Spring Mixer unanswered") }),
    );
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Accept invitation to Spring Mixer" }),
    );
    expect(posts()).toHaveLength(0);
  });

  it("Decline confirms too, and Go back returns focus to Decline", async () => {
    stub({ [`GET ${LIST}`]: list([MIXER]) });
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", { name: "Decline invitation to Spring Mixer" }),
    );
    expect(row("Spring Mixer").textContent).toContain(
      "Decline this invitation? Your first answer is final. To change it later, contact your Speaker Connector.",
    );
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Confirm decline invitation to Spring Mixer" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: named("Go back, keep invitation to Spring Mixer unanswered") }),
    );
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Decline invitation to Spring Mixer" }),
    );
  });

  it("Confirm accept sends exactly one POST {response: accept} to the encoded id", async () => {
    stub({
      [`GET ${LIST}`]: sequence(list([MIXER]), list([answered(MIXER, "accepted_invitation")])),
      [`POST ${MIXER_URL}`]: {
        body: { invitation: answered(MIXER, "accepted_invitation"), recorded: true },
      },
    });
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", { name: "Accept invitation to Spring Mixer" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm accept invitation to Spring Mixer" }),
    );
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(posts()[0].url).toBe(MIXER_URL);
    expect(JSON.parse(String(posts()[0].init.body))).toEqual({ response: "accept" });
    await waitFor(() => expect(gets()).toBe(2));
    expect(posts()).toHaveLength(1);
  });

  it("while pending, the pressed button has aria-disabled, keeps focus, reads Saving…, ignores a second click; every other answer button is disabled; all clear only after the re-read", async () => {
    const post = deferred();
    const reread = deferred();
    stub({
      [`GET ${LIST}`]: sequence(list([MIXER, LECTURE]), () => reread.promise),
      [`POST ${MIXER_URL}`]: () => post.promise,
    });
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", { name: "Accept invitation to Spring Mixer" }),
    );
    const confirm = screen.getByRole("button", {
      name: "Confirm accept invitation to Spring Mixer",
    });
    expect(document.activeElement).toBe(confirm);
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const setData = vi.spyOn(client, "setQueryData");

    fireEvent.click(confirm);
    await waitFor(() => expect(confirm.getAttribute("aria-disabled")).toBe("true"));
    expect(confirm.hasAttribute("disabled")).toBe(false);
    expect(confirm.textContent).toContain("Saving…");
    expect(document.activeElement).toBe(confirm);
    for (const name of [
      "Go back, keep invitation to Spring Mixer unanswered",
      "Accept invitation to ACCT 4100 guest lecture",
      "Decline invitation to ACCT 4100 guest lecture",
    ]) {
      expect(screen.getByRole("button", { name: named(name) }).hasAttribute("disabled")).toBe(
        true,
      );
    }

    fireEvent.click(confirm);
    expect(posts()).toHaveLength(1);

    await act(async () => {
      post.resolve({ body: { invitation: answered(MIXER, "accepted_invitation"), recorded: true } });
    });
    await waitFor(() => expect(gets()).toBe(2));
    expect(confirm.getAttribute("aria-disabled")).toBe("true");
    expect(
      screen.getByRole("button", { name: "Accept invitation to ACCT 4100 guest lecture" })
        .hasAttribute("disabled"),
    ).toBe(true);

    await act(async () => {
      reread.resolve(list([answered(MIXER, "accepted_invitation"), LECTURE]));
    });
    await waitFor(() =>
      expect(
        screen
          .getByRole("button", { name: "Accept invitation to ACCT 4100 guest lecture" })
          .hasAttribute("disabled"),
      ).toBe(false),
    );
    for (const button of screen.getAllByRole("button")) {
      expect(button.getAttribute("aria-disabled")).toBeNull();
    }
    expect(invalidate.mock.calls).toEqual([
      [{ queryKey: ["principal-1", "my-invitations"], exact: true }],
    ]);
    expect(setData).not.toHaveBeenCalled();
  });

  it("success announces in role=status only after the 200; recorded:false says nothing changed", async () => {
    const post = deferred();
    stub({
      [`GET ${LIST}`]: sequence(list([MIXER]), list([answered(MIXER, "declined_invitation")])),
      [`POST ${MIXER_URL}`]: () => post.promise,
    });
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", { name: "Decline invitation to Spring Mixer" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm decline invitation to Spring Mixer" }),
    );
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(screen.getByRole("status").textContent).toBe("");
    await act(async () => {
      post.resolve({
        body: { invitation: answered(MIXER, "declined_invitation"), recorded: true },
      });
    });
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe("You declined Spring Mixer."),
    );

    cleanup();
    calls = [];
    stub({
      [`GET ${LIST}`]: sequence(list([MIXER]), list([answered(MIXER, "accepted_invitation")])),
      [`POST ${MIXER_URL}`]: {
        body: { invitation: answered(MIXER, "accepted_invitation"), recorded: false },
      },
    });
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", { name: "Accept invitation to Spring Mixer" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm accept invitation to Spring Mixer" }),
    );
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe(
        "Your answer to Spring Mixer was already recorded. Nothing changed.",
      ),
    );
  });

  it("after the re-read, focus is on the answered row's heading", async () => {
    stub({
      [`GET ${LIST}`]: sequence(list([MIXER]), list([answered(MIXER, "accepted_invitation")])),
      [`POST ${MIXER_URL}`]: {
        body: { invitation: answered(MIXER, "accepted_invitation"), recorded: true },
      },
    });
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", { name: "Accept invitation to Spring Mixer" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm accept invitation to Spring Mixer" }),
    );
    await waitFor(() =>
      expect(document.activeElement).toBe(
        within(section("Answered")).getByRole("heading", { level: 3, name: "Spring Mixer" }),
      ),
    );
    expect(screen.getByRole("status").textContent).toBe("You accepted Spring Mixer.");
  });

  it.each([
    [
      404,
      "speaker_invitation_not_found",
      "This invitation is no longer open to you. The list has been refreshed.",
    ],
    [
      409,
      "speaker_invitation_already_answered",
      "This invitation already has a different answer, and the first answer is final. To change it, contact your Speaker Connector.",
    ],
    [
      409,
      "speaker_invitation_response_conflict",
      "Your answer could not be recorded just now. The list has been refreshed; try again.",
    ],
  ])("%i %s shows its message and re-reads the list", async (status, code, message) => {
    stub({
      [`GET ${LIST}`]: list([MIXER]),
      [`POST ${MIXER_URL}`]: refusal(status, code),
    });
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", { name: "Accept invitation to Spring Mixer" }),
    );
    const confirm = screen.getByRole("button", {
      name: "Confirm accept invitation to Spring Mixer",
    });
    fireEvent.click(confirm);
    await waitFor(() => expect(gets()).toBe(2));
    const alert = await within(row("Spring Mixer")).findByRole("alert");
    expect(alert.textContent).toBe(message);
    expect(alert.textContent).not.toContain("SERVER-WORDS");
    expect(confirm.getAttribute("aria-describedby")).toContain(alert.id);
    expect(document.activeElement).toBe(confirm);
    expect(screen.getByRole("status").textContent).toBe("");
  });

  it("an answer that the re-read shows already answered moves focus to that row, with its message", async () => {
    stub({
      [`GET ${LIST}`]: sequence(list([MIXER]), list([answered(MIXER, "declined_invitation")])),
      [`POST ${MIXER_URL}`]: refusal(409, "speaker_invitation_already_answered"),
    });
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", { name: "Accept invitation to Spring Mixer" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm accept invitation to Spring Mixer" }),
    );
    const heading = await within(await waitFor(() => section("Answered"))).findByRole("heading", {
      level: 3,
      name: "Spring Mixer",
    });
    await waitFor(() => expect(document.activeElement).toBe(heading));
    expect(within(row("Spring Mixer")).getByRole("alert").textContent).toBe(
      "This invitation already has a different answer, and the first answer is final. To change it, contact your Speaker Connector.",
    );
  });

  it("an invitation gone from the re-read keeps its message at page level, with focus on the h1", async () => {
    stub({
      [`GET ${LIST}`]: sequence(list([MIXER, LECTURE]), list([LECTURE])),
      [`POST ${MIXER_URL}`]: refusal(404, "speaker_invitation_not_found"),
    });
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", { name: "Accept invitation to Spring Mixer" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm accept invitation to Spring Mixer" }),
    );
    await waitFor(() =>
      expect(screen.queryByRole("heading", { level: 3, name: "Spring Mixer" })).toBeNull(),
    );
    expect(screen.getByRole("alert").textContent).toBe(
      "This invitation is no longer open to you. The list has been refreshed.",
    );
    await waitFor(() =>
      expect(document.activeElement).toBe(
        screen.getByRole("heading", { level: 1, name: "Invitations" }),
      ),
    );
  });

  it("403, 429 and network errors keep the row and re-read nothing", async () => {
    let attempt = 0;
    stub({
      [`GET ${LIST}`]: list([MIXER]),
      [`POST ${MIXER_URL}`]: () => {
        attempt += 1;
        if (attempt === 1) return refusal(403, "forbidden");
        if (attempt === 2) return refusal(429, "rate_limited");
        return Promise.reject(new TypeError("Failed to fetch"));
      },
    });
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", { name: "Accept invitation to Spring Mixer" }),
    );
    const confirm = screen.getByRole("button", {
      name: "Confirm accept invitation to Spring Mixer",
    });
    const alertText = () => within(row("Spring Mixer")).queryByRole("alert")?.textContent;

    fireEvent.click(confirm);
    await waitFor(() =>
      expect(alertText()).toBe(
        "This account's Speaker access is not active, so this page cannot be shown or changed. Ask your Speaker Connector.",
      ),
    );
    fireEvent.click(confirm);
    await waitFor(() =>
      expect(alertText()).toBe("Too many requests just now. Wait a minute, then try again."),
    );
    fireEvent.click(confirm);
    await waitFor(() =>
      expect(alertText()).toBe(
        "This could not be saved, and the server gave no reason. Nothing was changed. Try again.",
      ),
    );
    expect(gets()).toBe(1);
    expect(document.activeElement).toBe(confirm);
  });

  it.each([
    ["Accept", "Accept invitation to Spring Mixer", false],
    ["Decline", "Decline invitation to Spring Mixer", false],
    ["Confirm accept", "Confirm accept invitation to Spring Mixer", "Accept"],
    ["Confirm decline", "Confirm decline invitation to Spring Mixer", "Decline"],
    ["Go back", "Go back, keep invitation to Spring Mixer unanswered", "Accept"],
  ])(
    "%s: the accessible name contains and starts with the visible text, and carries the title",
    async (visible, name, opener) => {
      stub({ [`GET ${LIST}`]: list([MIXER]) });
      renderPage();
      await screen.findByText("Spring Mixer");
      if (opener) {
        fireEvent.click(
          screen.getByRole("button", { name: `${opener} invitation to Spring Mixer` }),
        );
      }
      const button = screen.getByRole("button", { name: named(name) });
      expect(button.hasAttribute("aria-label")).toBe(false);
      const visibleText = Array.from(button.childNodes)
        .filter((node) => !(node instanceof HTMLElement && node.classList.contains("sr-only")))
        .map((node) => node.textContent)
        .join("");
      expect(visibleText).toBe(visible);
      expect(name.startsWith(visibleText)).toBe(true);
      expect(name).toContain("Spring Mixer");
    },
  );

  it("truncated says 200", async () => {
    stub({ [`GET ${LIST}`]: list([MIXER], true) });
    renderPage();
    expect(await screen.findByText("Showing your 200 most recent invitations.")).toBeTruthy();
  });

  it("an empty list says how invitations arrive", async () => {
    stub({ [`GET ${LIST}`]: list([]) });
    renderPage();
    expect(
      await screen.findByText(
        "No invitations yet. When a Speaker Connector invites you to an event, it appears here.",
      ),
    ).toBeTruthy();
  });

  it("Answered pages through PagedList; answering a row that lands on page 2 shows page 2 and focuses that row's heading", async () => {
    const earlier = Array.from({ length: 11 }, (_, i) =>
      answered(open(`old-${i}`, `Earlier event ${i}`), "accepted_invitation"),
    );
    const later = Array.from({ length: 3 }, (_, i) =>
      answered(open(`late-${i}`, `Later event ${i}`), "declined_invitation"),
    );
    // Server order after the answer: the answered row sorts 12th of 15.
    const after = [...earlier, answered(MIXER, "accepted_invitation"), ...later];
    stub({
      [`GET ${LIST}`]: sequence(list([MIXER, ...earlier, ...later]), list(after)),
      [`POST ${MIXER_URL}`]: {
        body: { invitation: answered(MIXER, "accepted_invitation"), recorded: true },
      },
    });
    renderPage();
    await screen.findByText("Earlier event 0");
    expect(
      within(section("Answered")).getAllByRole("button", { name: "Page 1 of answered invitations" })[0]
        .getAttribute("aria-current"),
    ).toBe("page");

    fireEvent.click(screen.getByRole("button", { name: "Accept invitation to Spring Mixer" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm accept invitation to Spring Mixer" }),
    );
    const heading = await within(section("Answered")).findByRole("heading", {
      level: 3,
      name: "Spring Mixer",
    });
    await waitFor(() => expect(document.activeElement).toBe(heading));
    expect(
      within(section("Answered")).getAllByRole("button", { name: "Page 2 of answered invitations" })[0]
        .getAttribute("aria-current"),
    ).toBe("page");
  });

  it("switching principal re-reads and never shows the first principal's rows", async () => {
    let owner = "first";
    stub({
      [`GET ${LIST}`]: () =>
        owner === "first" ? list([MIXER]) : new Promise<Answer>(() => undefined),
    });
    renderPage();
    await screen.findByText("Spring Mixer");
    owner = "second";
    act(() => principal.set("principal-2"));
    expect(await screen.findByText("Loading invitations…")).toBeTruthy();
    expect(screen.queryByText("Spring Mixer")).toBeNull();
    expect(gets()).toBe(2);
  });

  it("no request is sent while the principal key is null", async () => {
    principal.key = null;
    stub({ [`GET ${LIST}`]: list([MIXER]) });
    renderPage();
    await act(async () => {
      await Promise.resolve();
    });
    expect(calls).toHaveLength(0);
  });

  it("sets document.title to 'Invitations · Speaker Portal' and restores the previous title on unmount", () => {
    stub({ [`GET ${LIST}`]: list([]) });
    const { unmount } = renderPage();
    expect(document.title).toBe("Invitations · Speaker Portal");
    unmount();
    expect(document.title).toBe("Smart Match");
  });
});
