import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { BeforeAfterView } from "../../../lib/exerciseClient";
import { HarborBeforeAfter } from "./HarborBeforeAfter";

afterEach(cleanup);

const view: BeforeAfterView = {
  rows: [
    { label: "Your setting 'x', before asking", mass_email_signups: 5, with_list_signups: 8, list_added: 3, list_added_came: 2 },
    { label: "Your setting 'x', after asking", mass_email_signups: 5, with_list_signups: 11, list_added: 6, list_added_came: 4 },
    { label: "Major first, after asking", mass_email_signups: 5, with_list_signups: 7, list_added: 2, list_added_came: 1 },
  ],
};

describe("HarborBeforeAfter", () => {
  it("renders nothing without rows (round one)", () => {
    const { container } = render(<HarborBeforeAfter beforeAfter={null} />);
    expect(container.querySelector("[data-slot=exercise-before-after]")).toBeNull();
  });

  it("shows the heading, three rows, and the debrief line", () => {
    render(<HarborBeforeAfter beforeAfter={view} />);
    expect(screen.getByRole("heading", { name: "Before and after asking" })).toBeTruthy();
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(4);
    expect(within(table).getByRole("columnheader", { name: "Your list added" })).toBeTruthy();
    expect(screen.getByText("Major first, after asking")).toBeTruthy();
    expect(
      screen.getByText(
        "Same event, same students, same luck. The only difference is what we knew about them.",
      ),
    ).toBeTruthy();
  });
});
