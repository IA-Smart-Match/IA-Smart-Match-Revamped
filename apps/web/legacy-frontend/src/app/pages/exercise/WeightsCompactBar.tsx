/**
 * The phone's sticky compact weights bar (DESIGN.md §7.4, §10 "Use a sticky
 * compact weights bar on 390").
 *
 * Once the weights card scrolls out of view on the 390 layout, a slim bar
 * pins to the top of the viewport with the four numbers the list was built
 * from and "Edit weights", which scrolls back to the sliders and puts focus on
 * the first one. On wider layouts the weights card is sticky beside the list,
 * so the bar never shows.
 *
 * Words from §11.1: "Weights 0.40 · 0.25 · 0.25 · 0.10 · Total 1.00" and
 * "Edit weights". The numbers are the team's own input, not a score (§1.2);
 * the total is their sum, never a percentage.
 */
import * as React from "react";
import { SlidersHorizontal } from "lucide-react";

import { Button, formatWeight, formatWeightTotal, usePrefersReducedMotion, weightTotal } from "./desk";
import { useNarrowViewport } from "./useNarrowViewport";

export interface WeightsCompactBarProps {
  /** The weights card the bar stands in for. */
  readonly target: React.RefObject<HTMLElement | null>;
  /** The confirmed weights, in the order the sliders show them. */
  readonly values: readonly number[];
  /** Called after scrolling back, to put focus on the first slider. */
  readonly onEdit: () => void;
}

/** Whether `target` is out of view, watched only while `active`. */
function useOutOfView(target: React.RefObject<HTMLElement | null>, active: boolean): boolean {
  const [outOfView, setOutOfView] = React.useState(false);

  React.useEffect(() => {
    const element = target.current;
    if (!active || element === null || typeof IntersectionObserver === "undefined") {
      setOutOfView(false);
      return undefined;
    }
    const observer = new IntersectionObserver((entries) => {
      const last = entries[entries.length - 1];
      if (last !== undefined) {
        setOutOfView(!last.isIntersecting);
      }
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [target, active]);

  return outOfView;
}

export function WeightsCompactBar({
  target,
  values,
  onEdit,
}: WeightsCompactBarProps): React.JSX.Element | null {
  const narrow = useNarrowViewport();
  const reduced = usePrefersReducedMotion();
  const outOfView = useOutOfView(target, narrow);

  if (!narrow || !outOfView) {
    return null;
  }

  return (
    <div
      data-slot="exercise-weights-bar"
      className="fixed inset-x-0 top-0 z-30 bg-ce-surface shadow-ce-3"
    >
      <div className="ce-container flex items-center justify-between gap-ce-3 py-ce-2">
        <p className="ce-type-meta ce-tabular flex min-w-0 items-center gap-ce-2 text-ce-ink">
          <SlidersHorizontal aria-hidden="true" className="size-5 shrink-0 text-ce-primary" />
          <span>
            Weights {values.map((value) => formatWeight(value)).join(" · ")} · Total{" "}
            {formatWeightTotal(weightTotal(values))}
          </span>
        </p>
        <Button
          variant="quiet"
          className="shrink-0 whitespace-nowrap"
          onClick={() => {
            target.current?.scrollIntoView({ block: "start", behavior: reduced ? "auto" : "smooth" });
            onEdit();
          }}
        >
          Edit weights
        </Button>
      </div>
    </div>
  );
}
