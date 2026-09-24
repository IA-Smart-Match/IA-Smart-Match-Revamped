/**
 * `useSpeakerPageTitle` (T6b-4 §2.4, WCAG 2.4.2): each page names the tab
 * after its own `h1`, and leaving the page gives the old title back.
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { useSpeakerPageTitle } from "./useSpeakerPageTitle";

function Page({ heading }: { heading: string }) {
  useSpeakerPageTitle(heading);
  return <h1>{heading}</h1>;
}

beforeEach(() => {
  document.title = "Smart Match";
});

afterEach(cleanup);

describe("useSpeakerPageTitle", () => {
  it("sets '{h1} · Speaker Portal' and restores the previous title on unmount", () => {
    const { unmount } = render(<Page heading="Invitations" />);
    expect(document.title).toBe("Invitations · Speaker Portal");
    unmount();
    expect(document.title).toBe("Smart Match");
  });

  it("follows a new heading while mounted", () => {
    const { rerender, unmount } = render(<Page heading="Home" />);
    rerender(<Page heading="Engagements" />);
    expect(document.title).toBe("Engagements · Speaker Portal");
    unmount();
    expect(document.title).toBe("Smart Match");
  });
});
