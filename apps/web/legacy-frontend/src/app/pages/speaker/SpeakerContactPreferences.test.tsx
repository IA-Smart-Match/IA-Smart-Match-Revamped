/**
 * The Speaker's Contact preferences page (B26 T6b-4 §5.5), against a stubbed
 * `fetch`. It reads `GET /v1/me/contact-channels` and writes `POST
 * …/{id}/opt-in` and `…/opt-out`, and nothing else; each assertion checks the
 * request made, the words shown and where keyboard focus is.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { MyContactChannel } from "@/lib/api";

import { SpeakerContactPreferences } from "./SpeakerContactPreferences";

const LIST = "/v1/me/contact-channels";

const principal = vi.hoisted(() => ({ key: "principal-1" as string | null }));

vi.mock("@/app/components/PrincipalQueryProvider", () => ({
  usePrincipalKey: () => principal.key,
}));

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

/** Answers taken in order; the last one repeats. */
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

function channel(overrides: Partial<MyContactChannel>): MyContactChannel {
  return {
    contact_channel_id: "ch-work",
    channel_kind: "email",
    address: "dana@example.edu",
    contact_state: "active_candidate",
    send_eligible: true,
    suppressed: false,
    suppression_reason: null,
    speaker_choice: null,
    last_set_by: "connector",
    can_opt_in: false,
    can_opt_out: true,
    updated_at: "2026-10-01T12:00:00Z",
    ...overrides,
  };
}

const WORK = channel({});
const HOME = channel({
  contact_channel_id: "ch-home",
  address: "dana.home@example.com",
  send_eligible: false,
  suppressed: true,
  suppression_reason: "your_opt_out",
  speaker_choice: "opt_out",
  last_set_by: "speaker",
  can_opt_in: true,
  can_opt_out: false,
});
const OLD = channel({
  contact_channel_id: "ch-old",
  address: "old@example.org",
  send_eligible: false,
  suppressed: true,
  suppression_reason: "connector",
  speaker_choice: "opt_out",
  can_opt_in: false,
  can_opt_out: false,
});

const HOME_OPTED_IN = channel({
  ...HOME,
  send_eligible: true,
  suppressed: false,
  suppression_reason: null,
  speaker_choice: "opt_in",
  can_opt_in: false,
  can_opt_out: true,
});
const WORK_OPTED_OUT = channel({
  ...WORK,
  send_eligible: false,
  suppressed: true,
  suppression_reason: "your_opt_out",
  speaker_choice: "opt_out",
  last_set_by: "speaker",
  can_opt_in: true,
  can_opt_out: false,
});

function list(channels: MyContactChannel[], truncated = false): Answer {
  return { body: { channels, truncated } };
}

let client: QueryClient;

function renderPage() {
  client = new QueryClient({
    defaultOptions: { queries: { retry: false, networkMode: "always", staleTime: 0 } },
  });
  const router = createMemoryRouter(
    [
      { path: "/speaker-portal/contact-preferences", element: <SpeakerContactPreferences /> },
      { path: "/speaker-portal/availability", element: <p>Availability page</p> },
      { path: "/login", element: <p>Sign-in page</p> },
    ],
    { initialEntries: ["/speaker-portal/contact-preferences"] },
  );
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

function row(address: string): HTMLElement {
  const heading = screen.getByRole("heading", { level: 3, name: address });
  const item = heading.closest("li");
  if (item === null) throw new Error(`no row for ${address}`);
  return item;
}

function gets(): number {
  return calls.filter((call) => call.method === "GET" && call.url === LIST).length;
}

function posts(): typeof calls {
  return calls.filter((call) => call.method === "POST");
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

describe("<SpeakerContactPreferences />", () => {
  it("lists every channel with its address as an h3, status sentence and last set by", async () => {
    stub({ [`GET ${LIST}`]: list([WORK, HOME, OLD]) });
    renderPage();
    await screen.findByRole("heading", { level: 3, name: "dana@example.edu" });

    const work = row("dana@example.edu");
    expect(work.textContent).toContain("Invitations can be emailed here.");
    expect(work.textContent).toContain("Last set by your Speaker Connector");
    const home = row("dana.home@example.com");
    expect(home.textContent).toContain("You opted out.");
    expect(home.textContent).toContain("Last set by you");
    expect(row("old@example.org").textContent).toContain(
      "Your Speaker Connector stopped messages to this address.",
    );
    expect(calls.map((call) => `${call.method} ${call.url}`)).toEqual([`GET ${LIST}`]);
  });

  it("shows only Opt in when can_opt_in, only Opt out when can_opt_out, and the reason when neither", async () => {
    stub({ [`GET ${LIST}`]: list([WORK, HOME, OLD]) });
    renderPage();
    await screen.findByRole("heading", { level: 3, name: "dana@example.edu" });

    const work = within(row("dana@example.edu")).getAllByRole("button");
    expect(work.map((button) => button.textContent)).toEqual([
      "Opt out of invitations at dana@example.edu",
    ]);
    const home = within(row("dana.home@example.com")).getAllByRole("button");
    expect(home.map((button) => button.textContent)).toEqual([
      "Opt in to invitations at dana.home@example.com",
    ]);
    const old = row("old@example.org");
    expect(within(old).queryAllByRole("button")).toHaveLength(0);
    expect(old.textContent).toContain("To change this, ask your Speaker Connector.");
  });

  it("Opt out asks first; Confirm opt out moves focus in and Keep receiving returns it", async () => {
    stub({ [`GET ${LIST}`]: list([WORK]) });
    renderPage();
    const optOut = await screen.findByRole("button", {
      name: "Opt out of invitations at dana@example.edu",
    });
    fireEvent.click(optOut);

    expect(row("dana@example.edu").textContent).toContain(
      "Stop invitations to dana@example.edu? An invitation already being sent at this moment may still arrive.",
    );
    const confirm = screen.getByRole("button", {
      name: "Confirm opt out of invitations at dana@example.edu",
    });
    expect(document.activeElement).toBe(confirm);
    expect(posts()).toHaveLength(0);

    fireEvent.click(
      screen.getByRole("button", { name: "Keep receiving invitations at dana@example.edu" }),
    );
    const back = screen.getByRole("button", { name: "Opt out of invitations at dana@example.edu" });
    expect(document.activeElement).toBe(back);
    expect(posts()).toHaveLength(0);
  });

  it("Confirm opt out sends one POST …/opt-out with no body; Opt in sends one POST …/opt-in with no confirm step", async () => {
    stub({
      [`GET ${LIST}`]: list([WORK, HOME]),
      [`POST ${LIST}/ch-work/opt-out`]: { body: { channel: WORK_OPTED_OUT, changed: true } },
      [`POST ${LIST}/ch-home/opt-in`]: { body: { channel: HOME_OPTED_IN, changed: true } },
    });
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", { name: "Opt out of invitations at dana@example.edu" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm opt out of invitations at dana@example.edu" }),
    );
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(posts()[0].url).toBe(`${LIST}/ch-work/opt-out`);
    expect(posts()[0].init.body).toBeUndefined();
    await waitFor(() => expect(gets()).toBe(2));

    fireEvent.click(
      screen.getByRole("button", { name: "Opt in to invitations at dana.home@example.com" }),
    );
    await waitFor(() => expect(posts()).toHaveLength(2));
    expect(posts()[1].url).toBe(`${LIST}/ch-home/opt-in`);
    expect(posts()[1].init.body).toBeUndefined();
  });

  it("while pending, the pressed button has aria-disabled, keeps focus and ignores a second click; other choice buttons are disabled; all clear after the re-read; success invalidates exactly the channel list", async () => {
    const post = deferred();
    const reread = deferred();
    stub({
      [`GET ${LIST}`]: sequence(list([WORK, HOME]), () => reread.promise),
      [`POST ${LIST}/ch-home/opt-in`]: () => post.promise,
    });
    renderPage();
    const optIn = await screen.findByRole("button", {
      name: "Opt in to invitations at dana.home@example.com",
    });
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const setData = vi.spyOn(client, "setQueryData");

    optIn.focus();
    fireEvent.click(optIn);
    await waitFor(() => expect(optIn.getAttribute("aria-disabled")).toBe("true"));
    expect(optIn.hasAttribute("disabled")).toBe(false);
    expect(optIn.textContent).toContain("Saving…");
    expect(document.activeElement).toBe(optIn);
    const other = screen.getByRole("button", { name: /Opt out of invitations at dana@example\.edu/ });
    expect(other.hasAttribute("disabled")).toBe(true);

    fireEvent.click(optIn);
    expect(posts()).toHaveLength(1);

    await act(async () => {
      post.resolve({ body: { channel: HOME_OPTED_IN, changed: true } });
    });
    await waitFor(() => expect(gets()).toBe(2));
    // The re-read has not landed: the page is still blocked.
    expect(optIn.getAttribute("aria-disabled")).toBe("true");
    expect(other.hasAttribute("disabled")).toBe(true);

    await act(async () => {
      reread.resolve(list([WORK, HOME_OPTED_IN]));
    });
    await waitFor(() =>
      expect(
        within(row("dana.home@example.com")).getByRole("button", {
          name: "Opt out of invitations at dana.home@example.com",
        }),
      ).toBeTruthy(),
    );
    for (const button of screen.getAllByRole("button")) {
      expect(button.hasAttribute("disabled")).toBe(false);
      expect(button.getAttribute("aria-disabled")).toBeNull();
    }
    expect(invalidate.mock.calls).toEqual([
      [{ queryKey: ["principal-1", "my-contact-channels"], exact: true }],
    ]);
    expect(setData).not.toHaveBeenCalled();
  });

  it.each([
    [
      "opt-out changed",
      "ch-work",
      "out",
      { channel: WORK_OPTED_OUT, changed: true },
      "You opted out of invitations to dana@example.edu.",
    ],
    [
      "opt-out not changed",
      "ch-work",
      "out",
      { channel: WORK_OPTED_OUT, changed: false },
      "dana@example.edu was already opted out. Nothing changed.",
    ],
    [
      "opt-in changed and eligible",
      "ch-home",
      "in",
      { channel: HOME_OPTED_IN, changed: true },
      "Invitations can be emailed to dana.home@example.com again.",
    ],
    [
      "opt-in changed, not eligible",
      "ch-home",
      "in",
      {
        channel: { ...HOME_OPTED_IN, send_eligible: false, contact_state: "relationship_recorded" },
        changed: true,
      },
      "Your choice is saved. dana.home@example.com still cannot receive invitations: not yet confirmed for invitations.",
    ],
    [
      "opt-in not changed",
      "ch-home",
      "in",
      { channel: HOME_OPTED_IN, changed: false },
      "dana.home@example.com was already opted in. Nothing changed.",
    ],
  ])("C6 %s announces its sentence in role=status", async (_, id, direction, body, sentence) => {
    stub({
      [`GET ${LIST}`]: list([WORK, HOME]),
      [`POST ${LIST}/${id}/opt-${direction}`]: { body },
    });
    renderPage();
    await screen.findByRole("heading", { level: 3, name: "dana@example.edu" });
    const status = screen.getByRole("status");
    expect(status.textContent).toBe("");

    if (direction === "out") {
      fireEvent.click(
        screen.getByRole("button", { name: "Opt out of invitations at dana@example.edu" }),
      );
      fireEvent.click(
        screen.getByRole("button", { name: "Confirm opt out of invitations at dana@example.edu" }),
      );
    } else {
      fireEvent.click(
        screen.getByRole("button", { name: "Opt in to invitations at dana.home@example.com" }),
      );
    }
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe(sentence));
  });

  it.each([
    [
      404,
      "speaker_contact_channel_not_found",
      undefined,
      "This address is no longer on your record. The list has been refreshed.",
    ],
    [
      409,
      "speaker_contact_channel_suppression_not_liftable",
      { reason: "connector" },
      "Your Speaker Connector stopped messages to this address, so it cannot be turned back on here. Ask your Speaker Connector.",
    ],
    [
      409,
      "speaker_contact_channel_suppression_not_liftable",
      { reason: "delivery" },
      "Messages to this address could not be delivered, so it cannot be turned back on. Ask your Speaker Connector to add a different address.",
    ],
    [
      409,
      "speaker_contact_channel_address_unverified",
      undefined,
      "This address was unsubscribed and is not the one you sign in with. Ask your Speaker Connector.",
    ],
    [
      409,
      "speaker_contact_channel_opt_in_unavailable",
      { contact_state: "stale" },
      "This address has not been confirmed for invitations yet, so you cannot opt in here. Ask your Speaker Connector.",
    ],
    [
      409,
      "speaker_contact_channel_transition_conflict",
      undefined,
      "Something changed while you were opting in. The list has been refreshed; try again.",
    ],
  ])("%i %s shows its message and re-reads the list", async (status, code, details, message) => {
    stub({
      [`GET ${LIST}`]: list([WORK, HOME]),
      [`POST ${LIST}/ch-home/opt-in`]: {
        status,
        body: { error: { code, message: "server words", ...(details ? { details } : {}) } },
      },
    });
    renderPage();
    const optIn = await screen.findByRole("button", {
      name: "Opt in to invitations at dana.home@example.com",
    });
    optIn.focus();
    fireEvent.click(optIn);

    await waitFor(() => expect(gets()).toBe(2));
    const alert = await within(row("dana.home@example.com")).findByRole("alert");
    expect(alert.textContent).toBe(message);
    expect(alert.textContent).not.toContain("server words");
    expect(optIn.getAttribute("aria-describedby")).toContain(alert.id);
    expect(document.activeElement).toBe(optIn);
    expect(screen.getByRole("status").textContent).toBe("");
  });

  it("403, 429 and network errors keep the row and re-read nothing", async () => {
    let attempt = 0;
    stub({
      [`GET ${LIST}`]: list([WORK, HOME]),
      [`POST ${LIST}/ch-home/opt-in`]: () => {
        attempt += 1;
        if (attempt === 1) return { status: 403, body: { error: { code: "forbidden", message: "x" } } };
        return { status: 429, body: { error: { code: "rate_limited", message: "x" } } };
      },
    });
    renderPage();
    const optIn = await screen.findByRole("button", {
      name: "Opt in to invitations at dana.home@example.com",
    });
    fireEvent.click(optIn);
    const denied = await within(row("dana.home@example.com")).findByRole("alert");
    expect(denied.textContent).toBe(
      "This account's Speaker access is not active, so this page cannot be shown or changed. Ask your Speaker Connector.",
    );
    fireEvent.click(optIn);
    await waitFor(() =>
      expect(within(row("dana.home@example.com")).getByRole("alert").textContent).toBe(
        "Too many requests just now. Wait a minute, then try again.",
      ),
    );
    expect(gets()).toBe(1);
  });

  it("an address that vanished on the re-read keeps its message on the page and focus on the h1", async () => {
    stub({
      [`GET ${LIST}`]: sequence(list([WORK, HOME]), list([WORK])),
      [`POST ${LIST}/ch-home/opt-in`]: {
        status: 404,
        body: { error: { code: "speaker_contact_channel_not_found", message: "x" } },
      },
    });
    renderPage();
    const optIn = await screen.findByRole("button", {
      name: "Opt in to invitations at dana.home@example.com",
    });
    optIn.focus();
    fireEvent.click(optIn);
    await waitFor(() =>
      expect(screen.queryByRole("heading", { level: 3, name: "dana.home@example.com" })).toBeNull(),
    );
    expect(screen.getByRole("alert").textContent).toBe(
      "This address is no longer on your record. The list has been refreshed.",
    );
    await waitFor(() =>
      expect(document.activeElement).toBe(
        screen.getByRole("heading", { level: 1, name: "Contact preferences" }),
      ),
    );
  });

  it("accessible names carry the address, and start with the visible label", async () => {
    stub({ [`GET ${LIST}`]: list([WORK, HOME]) });
    renderPage();
    const optOut = await screen.findByRole("button", {
      name: "Opt out of invitations at dana@example.edu",
    });
    expect(optOut.hasAttribute("aria-label")).toBe(false);
    expect(optOut.textContent?.startsWith("Opt out")).toBe(true);
    fireEvent.click(optOut);
    for (const [visible, name] of [
      ["Confirm opt out", "Confirm opt out of invitations at dana@example.edu"],
      ["Keep receiving", "Keep receiving invitations at dana@example.edu"],
    ]) {
      const button = screen.getByRole("button", { name });
      expect(button.hasAttribute("aria-label")).toBe(false);
      expect(button.textContent?.startsWith(visible)).toBe(true);
    }
    const optIn = screen.getByRole("button", { name: "Opt in to invitations at dana.home@example.com" });
    expect(optIn.hasAttribute("aria-label")).toBe(false);
  });

  it("the intro links to the Availability page", async () => {
    stub({ [`GET ${LIST}`]: list([WORK]) });
    renderPage();
    const link = await screen.findByRole("link", { name: /Availability page/ });
    expect(link.getAttribute("href")).toBe("/speaker-portal/availability");
    expect(screen.getByText(/Opting out is immediate/).textContent).toBe(
      "Choose which of your addresses may receive invitations. Opting out is immediate. To stop invitations for a while instead, set a pause on the Availability page.",
    );
  });

  it("after the re-read, focus is on the channel's heading", async () => {
    stub({
      [`GET ${LIST}`]: sequence(list([WORK, HOME]), list([WORK, HOME_OPTED_IN])),
      [`POST ${LIST}/ch-home/opt-in`]: { body: { channel: HOME_OPTED_IN, changed: true } },
    });
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", { name: "Opt in to invitations at dana.home@example.com" }),
    );
    const heading = screen.getByRole("heading", { level: 3, name: "dana.home@example.com" });
    await waitFor(() => expect(document.activeElement).toBe(heading));
    expect(heading.getAttribute("tabindex")).toBe("-1");
  });

  it("truncated says 50", async () => {
    stub({ [`GET ${LIST}`]: list([WORK], true) });
    renderPage();
    expect(await screen.findByText("Showing the first 50 addresses.")).toBeTruthy();
  });

  it("an empty list says a Connector adds addresses", async () => {
    stub({ [`GET ${LIST}`]: list([]) });
    renderPage();
    expect(
      await screen.findByText("No addresses are on file for you. Your Speaker Connector adds them."),
    ).toBeTruthy();
  });

  it("while loading, the list is aria-busy with a text label", async () => {
    const pending = deferred();
    stub({ [`GET ${LIST}`]: () => pending.promise });
    renderPage();
    const label = await screen.findByText("Loading your addresses…");
    expect(label.closest("[aria-busy='true']")).not.toBeNull();
    await act(async () => {
      pending.resolve(list([WORK]));
    });
  });

  it("404 speaker_profile_not_linked shows the not-linked notice with no Retry", async () => {
    stub({
      [`GET ${LIST}`]: {
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
    expect(screen.queryByRole("button", { name: /Retry/ })).toBeNull();
  });

  it("GET 403 shows the denied notice; GET 500 shows Retry, which re-reads", async () => {
    stub({
      [`GET ${LIST}`]: sequence(
        { status: 500, body: { error: { code: "internal_error", message: "x" } } },
        list([WORK]),
      ),
    });
    renderPage();
    const retry = await screen.findByRole("button", { name: "Retry loading your addresses" });
    expect(screen.getByRole("alert").textContent).toContain(
      "Your addresses could not be loaded, and the server gave no reason. Try again.",
    );
    fireEvent.click(retry);
    expect(await screen.findByRole("heading", { level: 3, name: "dana@example.edu" })).toBeTruthy();

    cleanup();
    calls = [];
    stub({
      [`GET ${LIST}`]: { status: 403, body: { error: { code: "forbidden", message: "x" } } },
    });
    renderPage();
    expect(
      await screen.findByText(
        "This account's Speaker access is not active, so this page cannot be shown or changed. Ask your Speaker Connector.",
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Retry/ })).toBeNull();
  });

  it("no request is sent while the principal key is null", async () => {
    principal.key = null;
    stub({ [`GET ${LIST}`]: list([WORK]) });
    renderPage();
    await act(async () => {
      await Promise.resolve();
    });
    expect(calls).toHaveLength(0);
  });

  it("sets document.title to 'Contact preferences · Speaker Portal'", async () => {
    stub({ [`GET ${LIST}`]: list([WORK]) });
    const { unmount } = renderPage();
    expect(document.title).toBe("Contact preferences · Speaker Portal");
    expect(
      screen.getByRole("heading", { level: 1, name: "Contact preferences" }).getAttribute("tabindex"),
    ).toBe("-1");
    unmount();
    expect(document.title).toBe("Smart Match");
  });
});
