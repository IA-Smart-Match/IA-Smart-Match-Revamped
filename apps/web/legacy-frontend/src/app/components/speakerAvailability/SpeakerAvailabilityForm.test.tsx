/**
 * The presentational availability form (B26 T5 §8 B).
 *
 * No network: the form takes the stored statement as a prop and hands a
 * payload to `onSave`. These tests pin the accessibility contract of plan §7
 * (labels, groups, names, focus, live regions) and the re-seed rule of §2.
 */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ComponentProps } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { SpeakerAvailability } from "@/lib/api";
import { COPY } from "@/lib/speakerAvailabilityDraft";

import { SpeakerAvailabilityForm } from "./SpeakerAvailabilityForm";

const TODAY = "2026-10-06";
const P = "availability-p1";

function stored(overrides: Partial<SpeakerAvailability> = {}): SpeakerAvailability {
  return {
    professional_id: "p1",
    stated: true,
    version: 4,
    invitations_paused_until: null,
    declared_capacity_hours_per_90_days: null,
    unavailable: [],
    updated_source: "connector",
    updated_at: "2026-10-01T15:00:00Z",
    ...overrides,
  };
}

function notStated(): SpeakerAvailability {
  return stored({ stated: false, version: null, updated_source: null, updated_at: null });
}

type Props = ComponentProps<typeof SpeakerAvailabilityForm>;

function props(overrides: Partial<Props> = {}): Props {
  return {
    idPrefix: P,
    headingId: `${P}-heading`,
    availability: stored(),
    reseedFrom: null,
    today: TODAY,
    copy: COPY.connector,
    saving: false,
    canSave: true,
    stale: null,
    readError: null,
    serverError: null,
    onSave: vi.fn(),
    onDiscardStale: vi.fn(),
    onRetryRead: vi.fn(),
    ...overrides,
  };
}

function renderForm(overrides: Partial<Props> = {}) {
  const p = props(overrides);
  const view = render(<SpeakerAvailabilityForm {...p} />);
  return { ...view, props: p };
}

const TWO_WINDOWS = stored({
  unavailable: [
    { starts_on: "2026-11-02", ends_on: "2026-11-06", source: "speaker" },
    { starts_on: "2026-12-20", ends_on: "2026-12-31", source: "connector" },
  ],
});

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-06T03:00:00Z"));
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("<SpeakerAvailabilityForm />", () => {
  it("pause and capacity are native inputs with visible labels", () => {
    renderForm();
    const pause = screen.getByLabelText("Pause invitations until") as HTMLInputElement;
    expect(pause.type).toBe("date");
    expect(pause.min).toBe("2026-10-06");
    expect(pause.max).toBe("2027-10-06");

    const capacity = screen.getByLabelText("Capacity (hours per 90 days)") as HTMLInputElement;
    expect(capacity.type).toBe("number");
    expect(capacity.getAttribute("min")).toBe("0.1");
    expect(capacity.getAttribute("max")).toBe("720");
    expect(capacity.getAttribute("step")).toBe("0.1");
    expect(capacity.value).toBe("");
  });

  it("each window is a group named by its legend", () => {
    renderForm({ availability: TWO_WINDOWS });
    const second = screen.getByRole("group", { name: "Unavailable dates 2" });
    const from = within(second).getByLabelText("From") as HTMLInputElement;
    const to = within(second).getByLabelText("To, inclusive") as HTMLInputElement;
    expect(from.type).toBe("date");
    expect(from.value).toBe("2026-12-20");
    expect(to.value).toBe("2026-12-31");
    expect(to.max).toBe("2028-04-06");
    expect(within(second).getByText("Added by a Speaker Connector")).toBeTruthy();
    const first = screen.getByRole("group", { name: "Unavailable dates 1" });
    expect(within(first).getByText("Added by the Speaker")).toBeTruthy();
  });

  it("remove buttons are named with their dates; a blank window says so", () => {
    renderForm({ availability: TWO_WINDOWS });
    expect(
      screen.getByRole("button", {
        name: "Remove unavailable dates November 2, 2026 to November 6, 2026",
      }),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Add unavailable dates" }));
    expect(
      screen.getByRole("button", { name: "Remove unavailable dates 3 (no dates yet)" }),
    ).toBeTruthy();
    const third = screen.getByRole("group", { name: "Unavailable dates 3" });
    expect(within(third).getByText("Not saved yet")).toBeTruthy();
  });

  it("adding focuses the new From input", () => {
    renderForm({ availability: TWO_WINDOWS });
    fireEvent.click(screen.getByRole("button", { name: "Add unavailable dates" }));
    const third = screen.getByRole("group", { name: "Unavailable dates 3" });
    expect(document.activeElement).toBe(within(third).getByLabelText("From"));
  });

  it("removing focuses the next, else previous, else Add", () => {
    const three = stored({
      unavailable: [
        { starts_on: "2026-11-02", ends_on: "2026-11-06", source: "speaker" },
        { starts_on: "2026-12-20", ends_on: "2026-12-31", source: "connector" },
        { starts_on: "2027-01-10", ends_on: "2027-01-12", source: "connector" },
      ],
    });
    renderForm({ availability: three });

    // Remove the first: focus moves to the next (was 2, now 1).
    fireEvent.click(
      screen.getByRole("button", {
        name: "Remove unavailable dates November 2, 2026 to November 6, 2026",
      }),
    );
    expect((document.activeElement as HTMLInputElement).value).toBe("2026-12-20");

    // Remove the last: no next, so the previous one's From.
    fireEvent.click(
      screen.getByRole("button", {
        name: "Remove unavailable dates January 10, 2027 to January 12, 2027",
      }),
    );
    expect((document.activeElement as HTMLInputElement).value).toBe("2026-12-20");

    // Remove the only one: focus lands on Add, never on <body>.
    fireEvent.click(
      screen.getByRole("button", {
        name: "Remove unavailable dates December 20, 2026 to December 31, 2026",
      }),
    );
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Add unavailable dates" }),
    );
  });

  it("Add is disabled at 20 with a described reason", () => {
    const twenty = stored({
      unavailable: Array.from({ length: 20 }, (_, i) => {
        const day = String(i + 1).padStart(2, "0");
        return { starts_on: `2026-12-${day}`, ends_on: `2026-12-${day}`, source: "speaker" as const };
      }),
    });
    renderForm({ availability: twenty });
    const add = screen.getByRole("button", { name: "Add unavailable dates" }) as HTMLButtonElement;
    expect(add.disabled).toBe(true);
    const reasonId = add.getAttribute("aria-describedby") ?? "";
    expect(document.getElementById(reasonId)?.textContent).toBe(
      "20 is the most a Speaker can have. Remove one to add another.",
    );
  });

  it("a client error sets role=alert, aria-invalid and aria-describedby, moves focus, and calls no onSave", () => {
    const { props: p } = renderForm();
    const capacity = screen.getByLabelText("Capacity (hours per 90 days)") as HTMLInputElement;
    fireEvent.change(capacity, { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "Save availability" }));

    expect(p.onSave).not.toHaveBeenCalled();
    expect(capacity.getAttribute("aria-invalid")).toBe("true");
    const describedBy = (capacity.getAttribute("aria-describedby") ?? "").split(" ");
    expect(describedBy).toHaveLength(2);
    const alert = document.getElementById(describedBy[1]) as HTMLElement;
    expect(alert.getAttribute("role")).toBe("alert");
    expect(alert.textContent).toMatch(/Capacity must be more than 0/);
    expect(screen.getAllByRole("alert").filter((el) => el.textContent !== "")).toHaveLength(1);
    expect(document.activeElement).toBe(capacity);
  });

  it("a window error names the reason and focuses that window's input", () => {
    const { props: p } = renderForm();
    fireEvent.click(screen.getByRole("button", { name: "Add unavailable dates" }));
    const group = screen.getByRole("group", { name: "Unavailable dates 1" });
    fireEvent.change(within(group).getByLabelText("From"), { target: { value: "2026-11-06" } });
    fireEvent.change(within(group).getByLabelText("To, inclusive"), {
      target: { value: "2026-11-02" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save availability" }));
    expect(p.onSave).not.toHaveBeenCalled();
    expect(screen.getByText("Window 1: the end date is before the start date.")).toBeTruthy();
    expect(document.activeElement).toBe(within(group).getByLabelText("From"));
  });

  it("a valid draft calls onSave with the full payload in form order", () => {
    const { props: p } = renderForm({ availability: TWO_WINDOWS });
    fireEvent.change(screen.getByLabelText("Capacity (hours per 90 days)"), {
      target: { value: "24.5" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save availability" }));
    expect(p.onSave).toHaveBeenCalledTimes(1);
    expect(p.onSave).toHaveBeenCalledWith({
      expected_version: 4,
      invitations_paused_until: null,
      declared_capacity_hours_per_90_days: 24.5,
      unavailable: [
        { starts_on: "2026-11-02", ends_on: "2026-11-06" },
        { starts_on: "2026-12-20", ends_on: "2026-12-31" },
      ],
    });
  });

  it("keyboard order follows the documented sequence", () => {
    renderForm({
      availability: stored({
        unavailable: [{ starts_on: "2026-11-02", ends_on: "2026-11-06", source: "speaker" }],
      }),
    });
    // Make a change so Save is enabled and "Discard changes" appears.
    fireEvent.change(screen.getByLabelText("Capacity (hours per 90 days)"), {
      target: { value: "12" },
    });
    const form = document.querySelector("form") as HTMLFormElement;
    const focusable = Array.from(
      form.querySelectorAll<HTMLElement>("input, button, select, textarea, [tabindex]"),
    ).filter((el) => !(el as HTMLButtonElement).disabled);
    for (const el of focusable) {
      expect(Number(el.getAttribute("tabindex") ?? "0")).toBeLessThanOrEqual(0);
    }
    const names = focusable.map((el) =>
      el instanceof HTMLInputElement
        ? (document.querySelector(`label[for="${el.id}"]`)?.textContent ?? "")
        : (el.textContent ?? ""),
    );
    expect(names).toEqual([
      "Pause invitations until",
      "Clear pause",
      "Capacity (hours per 90 days)",
      "From",
      "To, inclusive",
      "Remove unavailable dates November 2, 2026 to November 6, 2026",
      "Add unavailable dates",
      "Save availability",
      "Discard changes",
    ]);
  });

  it("there is exactly one role=status region", () => {
    renderForm({ availability: TWO_WINDOWS });
    expect(screen.getAllByRole("status")).toHaveLength(1);
    expect(screen.getByRole("status").id).toBe(`${P}-status`);
  });

  it("unchanged stated draft disables Save with a reason", () => {
    renderForm({ availability: TWO_WINDOWS });
    const save = screen.getByRole("button", { name: "Save availability" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    const ids = (save.getAttribute("aria-describedby") ?? "").split(" ");
    const reasons = ids.map((id) => document.getElementById(id)?.textContent ?? "");
    expect(reasons).toContain("No changes to save.");
    // The form-level alert is always mounted, so the reference resolves.
    expect(document.getElementById(`${P}-form-error`)).not.toBeNull();
  });

  it('not-stated empty draft offers "Save: no dates blocked"', () => {
    const { props: p } = renderForm({ availability: notStated() });
    expect(screen.getByText(/Not stated\./)).toBeTruthy();
    const save = screen.getByRole("button", { name: "Save: no dates blocked" }) as HTMLButtonElement;
    expect(save.disabled).toBe(false);
    expect(
      screen.getByText(
        "Saving an empty form records that this Speaker told you they have no dates blocked. Only save if they did.",
      ),
    ).toBeTruthy();
    fireEvent.click(save);
    expect(p.onSave).toHaveBeenCalledWith({
      expected_version: null,
      invitations_paused_until: null,
      declared_capacity_hours_per_90_days: null,
      unavailable: [],
    });

    fireEvent.change(screen.getByLabelText("Capacity (hours per 90 days)"), {
      target: { value: "10" },
    });
    expect(screen.getByRole("button", { name: "Save availability" })).toBeTruthy();
  });

  it("a new availability prop from a refetch does not overwrite typed input", () => {
    const { rerender, props: p } = renderForm({ availability: TWO_WINDOWS });
    const capacity = screen.getByLabelText("Capacity (hours per 90 days)") as HTMLInputElement;
    fireEvent.change(capacity, { target: { value: "30" } });

    rerender(
      <SpeakerAvailabilityForm
        {...p}
        availability={stored({ version: 5, declared_capacity_hours_per_90_days: 99 })}
      />,
    );
    expect(
      (screen.getByLabelText("Capacity (hours per 90 days)") as HTMLInputElement).value,
    ).toBe("30");
    expect(screen.getAllByRole("group", { name: /^Unavailable dates \d$/ })).toHaveLength(2);
  });

  it("every input shows the same focus-visible ring as the buttons", () => {
    renderForm({ availability: TWO_WINDOWS });
    const inputs = Array.from(document.querySelectorAll("form input"));
    expect(inputs.length).toBe(6);
    for (const input of inputs) {
      expect(input.className).toContain("focus-visible:ring-2");
      expect(input.className).toContain("focus-visible:ring-ring");
    }
  });

  it("every field is disabled while saving", () => {
    renderForm({ availability: TWO_WINDOWS, saving: true });
    const form = document.querySelector("form") as HTMLFormElement;
    const controls = Array.from(form.querySelectorAll<HTMLInputElement | HTMLButtonElement>("input, button"));
    expect(controls.length).toBeGreaterThan(0);
    for (const control of controls) {
      expect(control.matches(":disabled")).toBe(true);
    }
    expect(screen.getByRole("button", { name: "Saving…" })).toBeTruthy();
  });

  it("a read error is shown in stale mode even after the fresh read", () => {
    const { props: p } = renderForm({
      stale: { phase: "fresh" },
      readError: "Availability could not be loaded. Server says internal_error.",
    });
    const alert = document.getElementById(`${P}-form-error`) as HTMLElement;
    expect(alert.textContent).toMatch(/Someone changed this/);
    expect(alert.textContent).toMatch(/Availability could not be loaded\. Server says internal_error\./);
    fireEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(p.onRetryRead).toHaveBeenCalledTimes(1);
  });

  it("the Saved now box names an active pause once", () => {
    renderForm({
      availability: stored({ invitations_paused_until: "2026-10-20" }),
      stale: { phase: "fresh" },
    });
    const box = screen.getByText("Saved now").parentElement as HTMLElement;
    expect(box.textContent?.match(/October 20, 2026/g)).toHaveLength(1);
  });

  it("the Saved now box names an expired pause on its own line", () => {
    renderForm({
      availability: stored({ invitations_paused_until: "2026-09-30" }),
      stale: { phase: "fresh" },
    });
    const box = screen.getByText("Saved now").parentElement as HTMLElement;
    expect(within(box).getByText("Pause ended on September 30, 2026.")).toBeTruthy();
  });

  it("a reseed after a save replaces the draft and announces in the status region", () => {
    const { rerender, props: p } = renderForm({ availability: TWO_WINDOWS });
    fireEvent.change(screen.getByLabelText("Capacity (hours per 90 days)"), {
      target: { value: "30" },
    });
    const saved = stored({ version: 5, declared_capacity_hours_per_90_days: 30 });
    rerender(<SpeakerAvailabilityForm {...p} availability={saved} reseedFrom={saved} />);
    expect(screen.queryAllByRole("group", { name: /^Unavailable dates \d$/ })).toHaveLength(0);
    expect(screen.getByRole("status").textContent).toMatch(/^Availability saved /);
  });
});
