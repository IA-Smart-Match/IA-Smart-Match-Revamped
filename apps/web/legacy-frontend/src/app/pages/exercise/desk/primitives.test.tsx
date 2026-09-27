import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import * as React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Button } from "./Button";
import { MarkerChip } from "./MarkerChip";
import { Notice } from "./Notice";
import { Skeleton, SkeletonRankedRows, SkeletonRegion } from "./Skeleton";
import { stubReducedMotion } from "./testMatchMedia";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Button (§6.3)", () => {
  it("renders each variant and fires onClick", () => {
    const onClick = vi.fn();
    render(
      <>
        <Button variant="primary" onClick={onClick}>Save these weights</Button>
        <Button variant="secondary">Check again</Button>
        <Button variant="quiet">Keep it</Button>
        <Button variant="destructive">Delete it</Button>
      </>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Save these weights" }));
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Check again" }).dataset.variant).toBe("secondary");
    expect(screen.getByRole("button", { name: "Delete it" }).dataset.variant).toBe("destructive");
  });

  it("while pending shows the in-progress verb, is aria-disabled, and ignores clicks", () => {
    const onClick = vi.fn();
    render(
      <Button pending pendingLabel="Opening your team's work…" onClick={onClick}>
        Open this team's work
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Opening your team's work…" });
    expect(button.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("when disabled stays focusable and points at its reason", () => {
    const onClick = vi.fn();
    render(
      <>
        <Button disabled describedBy="why" onClick={onClick}>
          Run results for this event
        </Button>
        <p id="why">Choose one to run results.</p>
      </>,
    );
    const button = screen.getByRole("button", { name: "Run results for this event" });
    expect(button.hasAttribute("disabled")).toBe(false);
    expect(button.getAttribute("aria-disabled")).toBe("true");
    expect(button.getAttribute("aria-describedby")).toBe("why");
    button.focus();
    expect(document.activeElement).toBe(button);
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("defaults to type=button so it never submits a form by accident", () => {
    render(<Button>Go</Button>);
    expect(screen.getByRole("button", { name: "Go" }).getAttribute("type")).toBe("button");
  });
});

describe("Notice (§6.20)", () => {
  it("renders a calm refusal as role=status with the server sentence verbatim", () => {
    const sentence = "The instructor has not opened results for this event yet.";
    render(<Notice tone="calm" message={sentence} />);
    const notice = screen.getByRole("status");
    expect(notice.textContent).toContain(sentence);
    expect(notice.dataset.tone).toBe("calm");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("renders a transport problem as role=status with its action", () => {
    render(
      <Notice
        tone="problem"
        message="The exercise could not be reached. Check the connection and try again."
        action={<Button>Try again</Button>}
      />,
    );
    const notice = screen.getByRole("status");
    expect(notice.dataset.tone).toBe("problem");
    expect(screen.getByRole("button", { name: "Try again" })).toBeDefined();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("renders a done state as role=status", () => {
    render(<Notice tone="done" message="Saved." />);
    expect(screen.getByRole("status").dataset.tone).toBe("done");
  });

  it("never prefixes the sentence with Error", () => {
    render(<Notice tone="problem" message="Something went wrong." />);
    expect(screen.getByRole("status").textContent).not.toMatch(/^\s*error/i);
  });

  it("uses a static fade under reduced motion", () => {
    stubReducedMotion(true);
    render(<Notice tone="calm" message="Nothing yet." />);
    expect(screen.getByRole("status").dataset.reducedMotion).toBe("true");
  });
});

describe("Skeleton (§6.21)", () => {
  it("states the loading in a visually hidden status line", () => {
    render(
      <SkeletonRegion label="Loading the list…">
        <SkeletonRankedRows />
      </SkeletonRegion>,
    );
    const status = screen.getByRole("status");
    expect(status.textContent).toBe("Loading the list…");
    expect(status.className).toContain("sr-only");
  });

  it("draws 8 rank-shaped rows by default, hidden from screen readers", () => {
    const { container } = render(<SkeletonRankedRows />);
    const rows = container.querySelectorAll('[data-slot="ce-skeleton-row"]');
    expect(rows).toHaveLength(8);
    expect(container.firstElementChild?.getAttribute("aria-hidden")).toBe("true");
  });

  it("is a breathing block", () => {
    const { container } = render(<Skeleton className="h-6 w-40" />);
    expect(container.firstElementChild?.className).toContain("ce-skeleton");
  });
});

describe("MarkerChip (§6.8)", () => {
  it.each([
    ["major_only", "major only", "circle"],
    ["major_plus_events", "major plus events attended", "circle-dot"],
    ["completed_card", "completed card", "id-card"],
  ])("%s shows words and an icon, never colour alone", (marker, words, icon) => {
    const { container } = render(<MarkerChip marker={marker} />);
    expect(screen.getByText(words)).toBeDefined();
    expect(container.querySelector(`svg.lucide-${icon}`)).not.toBeNull();
    expect(container.firstElementChild?.getAttribute("data-marker")).toBe(marker);
  });

  it("renders an unknown marker as its raw string in the neutral style", () => {
    render(<MarkerChip marker="something_new" />);
    const chip = screen.getByText("something_new").closest('[data-slot="ce-marker-chip"]');
    expect(chip?.getAttribute("data-tone")).toBe("neutral");
  });
});
