/**
 * "Ask them now" asks before it spends the team's one refresh (issue #321).
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ASK_HINT, ASK_LABEL, ASK_QUESTION, AskOnceButton } from "./AskOnceButton";
import { CONFIRM_GUARD_MS } from "./desk";

const AT = "2026-10-16T10:42:00";

function hint(): string {
  return document.querySelector('[data-slot="exercise-ask-confirm"]')?.textContent ?? "";
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("<AskOnceButton />", () => {
  it("sends nothing on the first press: it asks, on the button itself", () => {
    const onAsk = vi.fn();
    render(<AskOnceButton asked={false} askedAt={null} disabled={false} pending={false} onAsk={onAsk} />);
    expect(hint()).toBe("");
    fireEvent.click(screen.getByRole("button", { name: ASK_LABEL }));

    expect(onAsk).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: ASK_QUESTION })).toBeDefined();
    expect(hint()).toBe(ASK_HINT);
  });

  it("asks on the second press", () => {
    const onAsk = vi.fn();
    render(<AskOnceButton asked={false} askedAt={null} disabled={false} pending={false} onAsk={onAsk} />);
    const button = screen.getByRole("button", { name: ASK_LABEL });
    fireEvent.click(button);
    vi.advanceTimersByTime(CONFIRM_GUARD_MS + 20);
    fireEvent.click(button);
    expect(onAsk).toHaveBeenCalledTimes(1);
  });

  it("treats a double-click as one press", () => {
    const onAsk = vi.fn();
    render(<AskOnceButton asked={false} askedAt={null} disabled={false} pending={false} onAsk={onAsk} />);
    const button = screen.getByRole("button", { name: ASK_LABEL });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(onAsk).not.toHaveBeenCalled();
  });

  it("puts the button back on Escape, and when nobody presses again", () => {
    const onAsk = vi.fn();
    render(<AskOnceButton asked={false} askedAt={null} disabled={false} pending={false} onAsk={onAsk} />);
    const button = screen.getByRole("button", { name: ASK_LABEL });
    fireEvent.click(button);
    fireEvent.keyDown(button, { key: "Escape" });
    expect(screen.getByRole("button", { name: ASK_LABEL })).toBeDefined();
    expect(hint()).toBe("");

    fireEvent.click(button);
    expect(screen.getByRole("button", { name: ASK_QUESTION })).toBeDefined();
    fireEvent.click(document.body);
    vi.advanceTimersByTime(6000);
    fireEvent.click(document.body);
    expect(onAsk).not.toHaveBeenCalled();
  });

  it("never confirms on a held key", () => {
    const onAsk = vi.fn();
    render(<AskOnceButton asked={false} askedAt={null} disabled={false} pending={false} onAsk={onAsk} />);
    const button = screen.getByRole("button", { name: ASK_LABEL });
    fireEvent.click(button);
    vi.advanceTimersByTime(CONFIRM_GUARD_MS + 20);
    const held = new KeyboardEvent("keydown", { key: "Enter", repeat: true, bubbles: true, cancelable: true });
    button.dispatchEvent(held);
    expect(held.defaultPrevented).toBe(true);
    expect(onAsk).not.toHaveBeenCalled();
  });

  it("is grey once asked and says so itself, with the time; a press does nothing", () => {
    const onAsk = vi.fn();
    render(<AskOnceButton asked askedAt={AT} disabled={false} pending={false} onAsk={onAsk} />);
    const button = screen.getByRole("button", { name: "Already refreshed at 10:42 AM" });
    expect(button.getAttribute("aria-disabled")).toBe("true");
    expect(button.hasAttribute("disabled")).toBe(false);
    fireEvent.click(button);
    vi.advanceTimersByTime(CONFIRM_GUARD_MS + 20);
    fireEvent.click(button);
    expect(onAsk).not.toHaveBeenCalled();
    expect(hint()).toBe("");
  });

  it("does not arm while it is shut for another reason, and points at the reason", () => {
    const onAsk = vi.fn();
    render(
      <>
        <AskOnceButton asked={false} askedAt={null} disabled pending={false} describedBy="why" onAsk={onAsk} />
        <p id="why">Pick a way of asking first.</p>
      </>,
    );
    const button = screen.getByRole("button", { name: ASK_LABEL });
    expect(button.getAttribute("aria-describedby")).toBe("why");
    fireEvent.click(button);
    expect(screen.queryByRole("button", { name: ASK_QUESTION })).toBeNull();
  });

  it("takes the question down if the button shuts while it is up", () => {
    const onAsk = vi.fn();
    const view = render(
      <AskOnceButton asked={false} askedAt={null} disabled={false} pending={false} onAsk={onAsk} />,
    );
    fireEvent.click(screen.getByRole("button", { name: ASK_LABEL }));
    view.rerender(<AskOnceButton asked askedAt={AT} disabled={false} pending={false} onAsk={onAsk} />);
    expect(screen.getByRole("button", { name: "Already refreshed at 10:42 AM" })).toBeDefined();
    expect(hint()).toBe("");
  });
});
