/**
 * The profile-card mock-up on the invitation desk (DESIGN.md §6.22, §7.6).
 *
 * It sits inside the shared exercise shell, so it carries the quiet
 * "Fictional data —" ribbon like every other exercise screen, and its own
 * mock-up sentence moves into the caption beside the card.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";

import { ProfileCardMockup } from "./ProfileCardMockup";

function renderCard() {
  return render(
    <MemoryRouter>
      <ProfileCardMockup />
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
});

describe("<ProfileCardMockup />", () => {
  it("sits in the exercise shell with the quiet fictional-data ribbon, not a loud banner", () => {
    renderCard();
    const banners = document.querySelectorAll('[data-slot="synthetic-data-banner"]');
    expect(banners.length).toBe(1);
    expect(banners[0].getAttribute("data-tone")).toBe("quiet");
    expect(banners[0].textContent).toContain("Fictional data —");
    expect(document.querySelector(".ce-root")).not.toBeNull();
  });

  it("names the page for the room and keeps the mock-up sentence in the caption", () => {
    renderCard();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "What a profile would be asked",
    );
    expect(
      screen.getByText(
        "Major and year are already on file, and past events are recorded when someone attends. So the card asks only two things, and asks the person to confirm their major.",
      ),
    ).toBeDefined();
    expect(
      screen.getByText(
        "This is a mock-up of the card, shown to the class. It asks nobody anything, keeps no answers, and is not connected to any list.",
      ),
    ).toBeDefined();
  });

  it("draws a phone-sized card marked \"Mock-up only\" with the major confirm and two questions", () => {
    renderCard();
    const card = document.querySelector('[data-slot="exercise-profile-card"]') as HTMLElement;
    expect(card).not.toBeNull();
    expect(within(card).getByText("Mock-up only")).toBeDefined();
    expect(within(card).getByRole("heading", { name: "Two quick questions" })).toBeDefined();
    expect(within(card).getByText("Confirm your major")).toBeDefined();
    const questions = card.querySelectorAll('[data-slot="exercise-card-question"]');
    expect([...questions].map((row) => row.getAttribute("data-field"))).toEqual([
      "stated_interests",
      "career_goal",
    ]);
  });

  it("has no inputs, no form, and only inert buttons that say so", () => {
    renderCard();
    expect(document.querySelector("input, textarea, select, form")).toBeNull();
    const buttons = screen.getAllByRole("button") as HTMLButtonElement[];
    expect(buttons.length).toBe(2);
    for (const button of buttons) {
      expect(button.disabled).toBe(true);
      expect(button.textContent?.toLowerCase()).toContain("mock-up only");
    }
  });
});
