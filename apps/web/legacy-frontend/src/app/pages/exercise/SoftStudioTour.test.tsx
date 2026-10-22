import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SoftStudioTour } from "./SoftStudioTour";

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

describe("SoftStudioTour", () => {
  it("records that the tour has been seen when the launcher is used", async () => {
    render(<SoftStudioTour />);

    await screen.getByRole("button", { name: "Replay the exercise tour" }).click();

    expect(window.localStorage.getItem("smartmatch-exercise-tour-v1")).toBe("seen");
    expect(screen.getByRole("dialog")).toBeDefined();
  });
});
