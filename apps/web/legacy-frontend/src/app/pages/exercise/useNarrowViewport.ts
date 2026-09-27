/**
 * Whether the page is at the phone layout (DESIGN.md §3.8: the 390 grid,
 * below 768px), live.
 *
 * The matching screen changes structure there, not just styling: the ranked
 * list becomes an `<ol>` of cards (§8.7), the compare view becomes a
 * segmented control (§7.5), and the weights get a sticky compact bar (§7.4).
 * Rendering both structures and hiding one with CSS would put every name on
 * the page twice for a screen reader, so the choice is made here.
 *
 * With no `matchMedia` (jsdom, very old browsers) this answers `false`: the
 * desktop layout, which is also what a projector shows.
 */
import * as React from "react";

export const NARROW_QUERY = "(max-width: 767px)";

function query(): MediaQueryList | null {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return null;
  }
  return window.matchMedia(NARROW_QUERY);
}

export function useNarrowViewport(): boolean {
  const [narrow, setNarrow] = React.useState<boolean>(() => query()?.matches ?? false);

  React.useEffect(() => {
    const list = query();
    if (list === null) {
      return undefined;
    }
    const update = (): void => setNarrow(list.matches);
    update();
    list.addEventListener?.("change", update);
    return () => list.removeEventListener?.("change", update);
  }, []);

  return narrow;
}
