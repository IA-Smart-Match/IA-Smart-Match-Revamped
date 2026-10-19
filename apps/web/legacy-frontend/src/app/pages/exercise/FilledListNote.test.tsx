// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { FilledListNote } from "./FilledListNote";

afterEach(cleanup);

const row = (n: number, keys: string[]) =>
  ({ rank: n, profile_no: n, contributing_factor_keys: keys }) as never;

describe("<FilledListNote />", () => {
  it("counts rows that matched nothing as filler", () => {
    render(<FilledListNote entries={[row(1, ["same_major"]), row(2, []), row(3, [])]} />);
    expect(
      screen.getByText("1 of your list matched what you asked for. The other 2 were added to fill the list."),
    ).toBeDefined();
  });
  it("shows nothing when every row matched", () => {
    render(<FilledListNote entries={[row(1, ["same_major"])]} />);
    expect(document.querySelector('[data-slot="exercise-filled-list-note"]')).toBeNull();
  });
});
