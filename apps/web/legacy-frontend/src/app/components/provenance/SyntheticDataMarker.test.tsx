import { cleanup, render, screen } from "@testing-library/react";
import * as React from "react";
import { afterEach, describe, expect, it } from "vitest";

import { SyntheticDataBanner } from "./SyntheticDataMarker";

afterEach(cleanup);

const REASON = "All student profiles are fictional, shaped by overall survey percentages.";

describe("SyntheticDataBanner", () => {
  it("keeps the loud CBA banner as the default", () => {
    render(<SyntheticDataBanner reason="Fixture data." />);
    const banner = screen.getByRole("status");
    expect(banner.textContent).toBe("Synthetic / demo data — Fixture data.");
    expect(banner.dataset.tone).toBe("loud");
    expect(banner.className).toContain("border-amber-400");
  });

  it("has a quiet variant with its own label for the class exercise (§6.2)", () => {
    render(<SyntheticDataBanner tone="quiet" label="Fictional data —" reason={REASON} />);
    const banner = screen.getByRole("status");
    expect(banner.dataset.tone).toBe("quiet");
    expect(banner.textContent).toBe(`Fictional data — ${REASON}`);
    expect(banner.textContent).not.toMatch(/synthetic|demo/i);
    expect(banner.className).not.toContain("amber");
    // Info icon, not the flask.
    expect(banner.querySelector("svg.lucide-info")).not.toBeNull();
    expect(banner.querySelector("svg.lucide-flask-conical")).toBeNull();
  });

  it("keeps the same data-slot on both tones, so every screen check still finds it", () => {
    render(<SyntheticDataBanner tone="quiet" label="Fictional data —" reason={REASON} />);
    expect(document.querySelector('[data-slot="synthetic-data-banner"]')).not.toBeNull();
  });
});
