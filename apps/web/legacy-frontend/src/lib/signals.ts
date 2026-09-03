/**
 * Red / yellow / green as a *presentation* of an accountable metric.
 *
 * The stakeholder direction recorded in
 * `docs/plans/workshops/g1-workshop-output-worksheet.md` ("Dashboard
 * discovery feed (R/Y/G) — Legacy frontend O4") asks for traffic-light
 * severity on the coordinator's discovery feed. The hazard in that ask is
 * that a traffic light is itself a number: pick a colour by eye and the
 * screen has invented a score, which is the exact habit ADR-0011 and
 * `apps/web/DESIGN.md` §1.9 exist to end.
 *
 * So severity here is a pure function of a {@link MetricValue} and an
 * explicitly declared, caller-visible threshold pair. It derives nothing,
 * weights nothing, and blends nothing. Three rules carry the honesty:
 *
 * 1. **Unknown is never green.** An absent measurement is not an all-clear;
 *    it is its own tone (`"unknown"`), rendered in a neutral colour with the
 *    reason attached. Colouring a missing value green is how a screen comes
 *    to report calm because it could not reach the server.
 * 2. **A lower bound can only raise severity, never lower it.** An
 *    `at_least` value is a truncated count (ADR-0011). If the bound already
 *    clears a threshold, the true value clears it too and the tone is real.
 *    If it does not, the true value still might, so the honest answer is
 *    `"unknown"` — not the reassuring tone the partial count would imply.
 * 3. **The thresholds travel with the value.** {@link SignalThresholds}
 *    carries the sentence that justifies the cut points, and the feed prints
 *    it, so a viewer can see why a number is amber rather than trusting the
 *    colour.
 *
 * Pure module, no React and no `@/` alias imports, so `node --test` can
 * exercise it directly.
 */
import type { MetricValue } from "../app/components/provenance/types.ts";

/**
 * Severity of one feed row.
 *
 * `"unknown"` is deliberately a *tone*, not the absence of one: every row
 * gets a visual treatment, and the treatment for "we could not measure this"
 * is distinct from all three measured outcomes.
 */
export type SignalTone = "critical" | "watch" | "clear" | "unknown";

/**
 * Where the cut points sit, and why.
 *
 * `criticalAtOrAbove` and `watchAtOrAbove` are counts, not scores, and they
 * are compared against a registered metric's own value — nothing is
 * normalised into a 0..1 "health" number on the way.
 */
export interface SignalThresholds {
  /** Value at or above this is `"critical"`. */
  readonly criticalAtOrAbove: number;
  /** Value at or above this (and below critical) is `"watch"`. */
  readonly watchAtOrAbove: number;
  /**
   * One sentence naming the rule, shown beside the row. A colour a viewer
   * cannot check is a score by another name.
   */
  readonly rationale: string;
}

/**
 * Severity for a metric where a *larger* count is worse — an open queue, an
 * uncovered window, a pending review backlog.
 *
 * Returns `"unknown"` for an unmeasured value and for a lower bound that has
 * not yet reached the `watch` cut point (rules 1 and 2 above).
 */
export function toneForBacklog(
  value: MetricValue,
  thresholds: SignalThresholds,
): SignalTone {
  switch (value.kind) {
    case "unknown":
      return "unknown";
    case "known":
      if (value.value >= thresholds.criticalAtOrAbove) {
        return "critical";
      }
      if (value.value >= thresholds.watchAtOrAbove) {
        return "watch";
      }
      return "clear";
    case "at_least":
      // A truncated count is evidence only for the severity it already
      // reaches. Below that, the true count is unconstrained upward, so
      // reporting "clear" or "watch" would be reporting an absence of
      // evidence as evidence of absence.
      if (value.value >= thresholds.criticalAtOrAbove) {
        return "critical";
      }
      if (value.value >= thresholds.watchAtOrAbove) {
        return "watch";
      }
      return "unknown";
  }
}

/** Human label for a tone. Carries the meaning without relying on colour (WCAG 2.2 AA). */
export const SIGNAL_TONE_LABELS: Readonly<Record<SignalTone, string>> = {
  critical: "Needs attention",
  watch: "Watch",
  clear: "Clear",
  unknown: "Not measured",
};

/**
 * Tailwind classes per tone.
 *
 * Every tone pairs its colour with a label from {@link SIGNAL_TONE_LABELS}
 * at the call site, so colour is never the only channel carrying severity.
 * `unknown` is slate rather than a washed-out green for the reason in rule 1.
 */
export const SIGNAL_TONE_CLASSES: Readonly<Record<SignalTone, string>> = {
  critical: "border-rose-200 bg-rose-50 text-rose-800",
  watch: "border-amber-200 bg-amber-50 text-amber-900",
  clear: "border-emerald-200 bg-emerald-50 text-emerald-800",
  unknown: "border-slate-200 bg-slate-50 text-slate-700",
};

/** Icon-well classes per tone, matched to {@link SIGNAL_TONE_CLASSES}. */
export const SIGNAL_TONE_ICON_CLASSES: Readonly<Record<SignalTone, string>> = {
  critical: "border-rose-200 bg-white text-rose-700",
  watch: "border-amber-200 bg-white text-amber-700",
  clear: "border-emerald-200 bg-white text-emerald-700",
  unknown: "border-slate-200 bg-white text-slate-600",
};

/** Sort order for the feed: unresolved severity first, measured calm last. */
export const SIGNAL_TONE_RANK: Readonly<Record<SignalTone, number>> = {
  critical: 0,
  watch: 1,
  unknown: 2,
  clear: 3,
};
