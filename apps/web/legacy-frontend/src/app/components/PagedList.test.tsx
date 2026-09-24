/**
 * `PagedList`'s optional `revealIndex` (B26 T6b-4 §1, G3): a caller can ask for
 * the page holding one row, so it can focus that row after it moved. Absent or
 * `null`, the list behaves exactly as before.
 */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PagedList } from "./PagedList";

const ROWS = Array.from({ length: 25 }, (_, index) => `row-${index}`);

function List({ revealIndex }: { revealIndex?: number | null }) {
  return (
    <PagedList items={ROWS} label="rows" idPrefix="rows" revealIndex={revealIndex}>
      {(visible) => (
        <ul aria-label="Visible rows">
          {visible.map((row) => (
            <li key={row}>{row}</li>
          ))}
        </ul>
      )}
    </PagedList>
  );
}

function shownRows(): string[] {
  return within(screen.getByRole("list", { name: "Visible rows" }))
    .getAllByRole("listitem")
    .map((item) => item.textContent ?? "");
}

afterEach(cleanup);

describe("<PagedList revealIndex>", () => {
  it("without revealIndex, behaviour is unchanged", () => {
    render(<List />);
    expect(shownRows()[0]).toBe("row-0");
    fireEvent.click(screen.getAllByRole("button", { name: "Next page of rows" })[0]);
    expect(shownRows()[0]).toBe("row-10");
  });

  it("revealIndex 12 at page size 10 shows page 2", () => {
    render(<List revealIndex={12} />);
    expect(shownRows()).toContain("row-12");
    expect(shownRows()[0]).toBe("row-10");
  });

  it("revealIndex null after a reveal leaves the page where it is; the same index can be revealed again after null", () => {
    const { rerender } = render(<List revealIndex={12} />);
    expect(shownRows()[0]).toBe("row-10");

    rerender(<List revealIndex={null} />);
    expect(shownRows()[0]).toBe("row-10");

    fireEvent.click(screen.getAllByRole("button", { name: "Page 1 of rows" })[0]);
    expect(shownRows()[0]).toBe("row-0");

    rerender(<List revealIndex={12} />);
    expect(shownRows()[0]).toBe("row-10");
  });

  it("revealing a later index moves again without passing through null", () => {
    const { rerender } = render(<List revealIndex={3} />);
    expect(shownRows()[0]).toBe("row-0");
    rerender(<List revealIndex={22} />);
    expect(shownRows()[0]).toBe("row-20");
  });
});
