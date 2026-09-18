/**
 * Tests for the class exercise's per-profile points counter.
 *
 * The component holds no arithmetic, so what is asserted here is what it says:
 * the figures it was given, an absent figure in words, and the difference
 * between a card nobody has asked for and a card somebody declined.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  ProfilePointsCounter,
  cardCompletionLabel,
  formatPoints,
} from "./ProfilePointsCounter";

afterEach(cleanup);

describe("formatPoints", () => {
  it("prints an earned zero as 0", () => {
    expect(formatPoints(0)).toBe("0");
  });

  it("prints an absent figure in words", () => {
    expect(formatPoints(null)).toBe("not available");
  });
});

describe("cardCompletionLabel", () => {
  it("says a card nobody has asked for has not been asked for", () => {
    expect(cardCompletionLabel("unknown")).toBe("Card not asked yet");
  });

  it("keeps 'not completed' distinct from 'not asked yet'", () => {
    expect(cardCompletionLabel("not_completed")).toBe("Card not completed");
    expect(cardCompletionLabel("not_completed")).not.toBe(cardCompletionLabel("unknown"));
  });

  it("says a completed card is completed", () => {
    expect(cardCompletionLabel("completed")).toBe("Card completed");
  });
});

describe("<ProfilePointsCounter />", () => {
  it("shows the total it was given and does not recompute it", () => {
    render(
      <ProfilePointsCounter
        profileName="Profile 118"
        total={5}
        attendancePoints={4}
        cardPoints={1}
        cardCompletion="completed"
      />,
    );

    expect(screen.getByTestId("profile-points-total").textContent).toContain("5");
    expect(screen.getByTestId("profile-points-attendance").textContent).toContain("4");
    expect(screen.getByTestId("profile-points-card").textContent).toContain("1");
  });

  it("names the profile it belongs to, accessibly", () => {
    render(
      <ProfilePointsCounter
        profileName="Profile 118"
        total={5}
        attendancePoints={4}
        cardPoints={1}
        cardCompletion="completed"
      />,
    );

    expect(screen.getByRole("region", { name: "Points for Profile 118" })).toBeTruthy();
  });

  it("says 'not asked yet' while the card state is unknown", () => {
    render(
      <ProfilePointsCounter
        profileName="Profile 118"
        total={3}
        attendancePoints={3}
        cardPoints={0}
        cardCompletion="unknown"
      />,
    );

    expect(screen.getByTestId("profile-points-card-state").textContent).toBe(
      "Card not asked yet",
    );
  });

  it("renders an unavailable figure as words, never as 0", () => {
    render(
      <ProfilePointsCounter
        profileName="Profile 118"
        total={null}
        attendancePoints={null}
        cardPoints={null}
        cardCompletion="unknown"
      />,
    );

    expect(screen.getByTestId("profile-points-total").textContent).toBe("not available");
    expect(screen.getByTestId("profile-points-attendance").textContent).toContain(
      "not available",
    );
    expect(screen.getByTestId("profile-points-card").textContent).toContain("not available");
  });

  it("shows an earned zero as a zero", () => {
    render(
      <ProfilePointsCounter
        profileName="Profile 118"
        total={0}
        attendancePoints={0}
        cardPoints={0}
        cardCompletion="not_completed"
      />,
    );

    expect(screen.getByTestId("profile-points-total").textContent).toContain("0");
    expect(screen.getByTestId("profile-points-total").textContent).not.toContain(
      "not available",
    );
  });

  it("shows no percentage, rate, score, or confidence", () => {
    const { container } = render(
      <ProfilePointsCounter
        profileName="Profile 118"
        total={5}
        attendancePoints={4}
        cardPoints={1}
        cardCompletion="completed"
      />,
    );

    const text = container.textContent ?? "";
    expect(text).not.toContain("%");
    expect(text).not.toMatch(/percent|rate|score|confidence|reward|redeem|extra credit/i);
  });
});
