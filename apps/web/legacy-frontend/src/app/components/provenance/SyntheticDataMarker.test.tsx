/**
 * The banner's two volumes (DESIGN.md §6.2, §11 item 5).
 *
 * `tone="quiet"` and `label` are a variant, not a copy: the CBA screens call
 * the banner with neither prop and must render exactly as before, and the
 * exercise's ribbon must read "Fictional data —" with its `Info` icon and no
 * border.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SyntheticDataBanner } from "./SyntheticDataMarker";

afterEach(cleanup);

const REASON = "All student profiles are fictional, shaped by overall survey percentages.";

function banner(): HTMLElement {
  const element = document.querySelector<HTMLElement>('[data-slot="synthetic-data-banner"]');
  if (element === null) {
    throw new Error("no banner");
  }
  return element;
}

describe("<SyntheticDataBanner />", () => {
  it("keeps the CBA banner loud and unchanged when no variant is asked for", () => {
    render(<SyntheticDataBanner reason="The matching API is not live yet." />);
    const element = banner();
    expect(element.textContent).toBe("Synthetic / demo data — The matching API is not live yet.");
    expect(element.className).toContain("border-amber-400");
    expect(element.className).toContain("bg-amber-100");
    expect(element.getAttribute("data-tone")).toBeNull();
    expect(element.querySelector("span")?.className).toContain("uppercase");
  });

  it("renders the exercise ribbon quietly, with its own label", () => {
    render(<SyntheticDataBanner tone="quiet" label="Fictional data —" reason={REASON} />);
    const element = banner();
    expect(element.getAttribute("data-tone")).toBe("quiet");
    expect(element.textContent).toBe(`Fictional data — ${REASON}`);
    // A wash, not a box: no border, no amber, no uppercase band.
    expect(element.className).not.toMatch(/border-2|amber/);
    expect(element.innerHTML).not.toContain("uppercase");
    // Still a status, still an icon plus words.
    expect(screen.getByRole("status")).toBe(element);
    expect(element.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
  });

  it("uses the CBA label on the quiet tone when no label is passed", () => {
    render(<SyntheticDataBanner tone="quiet" reason={REASON} />);
    expect(banner().textContent).toBe(`Synthetic / demo data — ${REASON}`);
  });
});
