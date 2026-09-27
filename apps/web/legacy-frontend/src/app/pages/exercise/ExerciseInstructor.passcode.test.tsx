/**
 * The passcode field's show/hide toggle (DESIGN.md §6.24).
 *
 * A toggle button with `aria-pressed` switches the field between password and
 * text. It never submits the form, and the passcode never appears anywhere
 * but the field's own value: not in text, not in another attribute, not in
 * the console.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExerciseInstructor } from "./ExerciseInstructor";

// Spaces keep this plainly a test string, not a credential shape.
const TYPED = "open sesame 4821";
let calls: string[] = [];

function stub(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      calls.push(url);
      return Promise.resolve(
        new Response(
          JSON.stringify({
            error: {
              code: "exercise_instructor_session_required",
              message: "Enter the instructor passcode to open this page.",
            },
          }),
          { status: 401 },
        ),
      );
    }),
  );
}

function renderPage(): void {
  const router = createMemoryRouter(
    [{ path: "/exercise/instructor", element: <ExerciseInstructor /> }],
    { initialEntries: ["/exercise/instructor"] },
  );
  render(<RouterProvider router={router} />);
}

afterEach(() => {
  cleanup();
  calls = [];
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("the passcode show/hide toggle", () => {
  it("switches the field between hidden and shown: one fixed label, aria-pressed carries the state", async () => {
    // A label that swaps *and* aria-pressed reads "Hide what is typed,
    // pressed": two signals that contradict. The label stays put.
    stub();
    renderPage();
    const field = (await screen.findByLabelText("Passcode")) as HTMLInputElement;
    expect(field.type).toBe("password");

    const toggle = screen.getByRole("button", { name: "Show what is typed" });
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(toggle);

    expect(screen.getByRole("button", { name: "Show what is typed" })).toBe(toggle);
    expect(toggle.getAttribute("aria-pressed")).toBe("true");
    expect(screen.queryByRole("button", { name: /hide/i })).toBeNull();
    expect(field.type).toBe("text");

    fireEvent.click(toggle);
    expect(field.type).toBe("password");
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
  });

  it("keeps the passcode out of storage and the address after a submit", async () => {
    stub();
    renderPage();
    fireEvent.change(await screen.findByLabelText("Passcode"), { target: { value: TYPED } });
    fireEvent.click(screen.getByRole("button", { name: "Show what is typed" }));
    fireEvent.click(screen.getByRole("button", { name: "Open the instructor page" }));
    await screen.findByText("Enter the instructor passcode to open this page.");

    const stored = (storage: Storage): string =>
      JSON.stringify(
        Array.from({ length: storage.length }, (_, index) => {
          const key = storage.key(index) ?? "";
          return [key, storage.getItem(key)];
        }),
      );
    expect(stored(sessionStorage)).not.toContain(TYPED);
    expect(stored(localStorage)).not.toContain(TYPED);
    expect(decodeURIComponent(window.location.href)).not.toContain(TYPED);
    expect(decodeURIComponent(window.location.href.replace(/\+/g, " "))).not.toContain(TYPED);
  });

  it("does not submit the form", async () => {
    stub();
    renderPage();
    fireEvent.change(await screen.findByLabelText("Passcode"), { target: { value: TYPED } });
    const before = calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Show what is typed" }));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(calls.slice(before).some((url) => url.includes("/login"))).toBe(false);
  });

  it("never puts the passcode anywhere but the field's value, or in the console", async () => {
    stub();
    const consoleCalls = (["log", "info", "warn", "error", "debug"] as const).map((level) =>
      vi.spyOn(console, level).mockImplementation(() => undefined),
    );
    renderPage();
    const field = (await screen.findByLabelText("Passcode")) as HTMLInputElement;
    fireEvent.change(field, { target: { value: TYPED } });
    fireEvent.click(screen.getByRole("button", { name: "Show what is typed" }));

    expect(field.value).toBe(TYPED);
    expect(document.body.textContent).not.toContain(TYPED);
    const elsewhere = [...document.body.querySelectorAll("*")].filter(
      (element) =>
        element !== field &&
        [...element.attributes].some((attribute) => attribute.value.includes(TYPED)),
    );
    expect(elsewhere).toEqual([]);
    for (const spy of consoleCalls) {
      expect(JSON.stringify(spy.mock.calls)).not.toContain(TYPED);
    }
  });
});
