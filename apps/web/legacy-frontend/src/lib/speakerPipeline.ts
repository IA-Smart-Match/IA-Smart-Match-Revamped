/**
 * Presentation rules for the Speaker Pipeline section. No arithmetic on
 * business numbers lives here.
 *
 * Everything this module decides is about pixels and pictures: how wide a
 * trapezoid may be drawn, which tint a stage carries, which icon sits beside
 * an insight. Every *number* the section shows — each count, each conversion
 * rate, each percentage string — arrives already computed and already
 * formatted from `GET /v1/units/{unit_id}/speaker-pipeline`, because a rate
 * recomputed in the browser is a second definition of a published number.
 *
 * The one thing here that touches a number at all is
 * {@link funnelWidthPercent}, and it deliberately does not produce one a
 * reader can read: it maps a measured share onto a drawable width, and the
 * clamp it applies is the reason it must never be used as a value. A stage at
 * 1% is drawn at {@link MIN_FUNNEL_WIDTH_PCT} so its label stays legible; if
 * that clamped number were ever printed as a percentage it would be a lie
 * about the data. The measured share is printed from the server's own
 * `share_display` instead, which is why both travel separately.
 *
 * `src/lib/metrics.ts` is the neighbouring module and does a different job:
 * it maps register payloads onto the `AccountableMetric` provenance
 * primitives the older tiles render. Nothing here duplicates it.
 *
 * This module imports nothing at runtime — only erased type imports — which
 * is what lets `tests/speakerPipeline.test.ts` load it directly under
 * `node --test`. The icon tables live in `speakerPipelineIcons.ts` for that
 * reason and no other: they are the one part of these presentation rules that
 * needs a value import.
 *
 * Pure functions and plain maps — verified by `tsc --noEmit` and exercised by
 * `tests/speakerPipeline.test.ts`.
 */
import type {
  SpeakerPipelineCompanion,
  SpeakerPipelineResponse,
  SpeakerPipelineStage,
} from "@/lib/api";

/**
 * Narrowest a funnel band may be drawn, as a percentage of the card's width.
 *
 * A stage measured at 1% of the baseline would otherwise be a sliver with its
 * number outside it. This is a floor on the *drawing*, never on the value:
 * see this module's docstring for why the two must not be confused.
 */
export const MIN_FUNNEL_WIDTH_PCT = 22;

/** Widest a funnel band may be drawn. The baseline stage sits here. */
export const MAX_FUNNEL_WIDTH_PCT = 100;

/**
 * Width to draw a band whose share could not be calculated.
 *
 * Deliberately the minimum rather than something mid-range: a stage with no
 * measured share must not be drawn at a width that reads as a measurement.
 * Such a band is also outlined rather than filled, so the absence is carried
 * by more than width alone.
 */
export const UNMEASURED_FUNNEL_WIDTH_PCT = MIN_FUNNEL_WIDTH_PCT;

/**
 * Map a measured share of the baseline onto a drawable band width.
 *
 * `null` in, `null` out — the caller decides how to draw an absence, and this
 * function will not manufacture a width to stand in for one.
 */
export function funnelWidthPercent(shareOfBaselinePct: number | null): number | null {
  if (shareOfBaselinePct === null || !Number.isFinite(shareOfBaselinePct)) {
    return null;
  }
  return Math.min(MAX_FUNNEL_WIDTH_PCT, Math.max(MIN_FUNNEL_WIDTH_PCT, shareOfBaselinePct));
}

/** Per-metric tint classes, keyed by the register's canonical metric name. */
export interface StageTint {
  /** Filled funnel band. */
  band: string;
  /** Text on the filled band. */
  bandText: string;
  /** The metric card's pastel wash. */
  card: string;
  /** The metric card's icon colour. */
  icon: string;
  /** The conversion panel's progress fill. */
  bar: string;
}

/**
 * One tint per registered metric this section presents.
 *
 * Written out rather than generated, because Tailwind's static extraction
 * only emits classes it can see as literals — a template-built class name
 * simply would not exist in the stylesheet. Every tint carries an explicit
 * `dark:` counterpart: the app's theme swaps `--background` and `--card`, and
 * a pastel chosen for a cream page is unreadable on a charcoal one.
 *
 * Colour is never the only carrier of meaning here. Each band also shows its
 * stage label, its count and its share as text, and each conversion row shows
 * its percentage beside its bar.
 */
export const STAGE_TINTS: Record<string, StageTint> = {
  pipeline_matched: {
    band: "bg-sky-300/80 dark:bg-sky-500/60",
    bandText: "text-sky-950 dark:text-sky-50",
    card: "bg-sky-50 dark:bg-sky-950/40",
    icon: "text-sky-600 dark:text-sky-300",
    bar: "bg-sky-500 dark:bg-sky-400",
  },
  pipeline_contacted: {
    band: "bg-emerald-300/80 dark:bg-emerald-500/60",
    bandText: "text-emerald-950 dark:text-emerald-50",
    card: "bg-emerald-50 dark:bg-emerald-950/40",
    icon: "text-emerald-600 dark:text-emerald-300",
    bar: "bg-emerald-500 dark:bg-emerald-400",
  },
  pipeline_confirmed: {
    band: "bg-violet-300/80 dark:bg-violet-500/60",
    bandText: "text-violet-950 dark:text-violet-50",
    card: "bg-violet-50 dark:bg-violet-950/40",
    icon: "text-violet-600 dark:text-violet-300",
    bar: "bg-violet-500 dark:bg-violet-400",
  },
  pipeline_attended: {
    band: "bg-rose-300/80 dark:bg-rose-500/60",
    bandText: "text-rose-950 dark:text-rose-50",
    card: "bg-rose-50 dark:bg-rose-950/40",
    icon: "text-rose-600 dark:text-rose-300",
    bar: "bg-rose-500 dark:bg-rose-400",
  },
  opportunities: {
    band: "bg-amber-300/80 dark:bg-amber-500/60",
    bandText: "text-amber-950 dark:text-amber-50",
    card: "bg-amber-50 dark:bg-amber-950/40",
    icon: "text-amber-600 dark:text-amber-300",
    bar: "bg-amber-500 dark:bg-amber-400",
  },
  pending_review_items: {
    band: "bg-indigo-300/80 dark:bg-indigo-500/60",
    bandText: "text-indigo-950 dark:text-indigo-50",
    card: "bg-indigo-50 dark:bg-indigo-950/40",
    icon: "text-indigo-600 dark:text-indigo-300",
    bar: "bg-indigo-500 dark:bg-indigo-400",
  },
};

/** Wash for a metric name this surface has not been taught a tint for. */
export const NEUTRAL_TINT: StageTint = {
  band: "bg-muted",
  bandText: "text-foreground",
  card: "bg-muted/40",
  icon: "text-muted-foreground",
  bar: "bg-muted-foreground",
};

export function tintFor(metricName: string): StageTint {
  return STAGE_TINTS[metricName] ?? NEUTRAL_TINT;
}

/**
 * The metric cards, in the order the section presents them.
 *
 * The reading order interleaves the two review measures among the lifecycle
 * stages, which is how a coordinator thinks about their week. What is *not*
 * implied is that the order is a sequence: the funnel below draws only the
 * lifecycle stages, and the review measures are labelled as a separate queue
 * wherever they appear.
 *
 * Built from the payload rather than from a hard-coded list of six names, so
 * a metric the server stops presenting disappears from the row instead of
 * rendering as a permanently unknown card — and one it starts presenting gets
 * a card at the end rather than silently vanishing from the screen.
 */
export function metricCardOrder(
  payload: SpeakerPipelineResponse,
): Array<SpeakerPipelineStage | SpeakerPipelineCompanion> {
  const byName = new Map<string, SpeakerPipelineStage | SpeakerPipelineCompanion>();
  for (const stage of payload.stages) {
    byName.set(stage.metric_name, stage);
  }
  for (const companion of payload.companions) {
    byName.set(companion.metric_name, companion);
  }

  const preferred = [
    "pipeline_matched",
    "pipeline_contacted",
    "opportunities",
    "pending_review_items",
    "pipeline_attended",
    "pipeline_confirmed",
  ];

  const ordered: Array<SpeakerPipelineStage | SpeakerPipelineCompanion> = [];
  for (const name of preferred) {
    const entry = byName.get(name);
    if (entry !== undefined) {
      ordered.push(entry);
      byName.delete(name);
    }
  }
  return [...ordered, ...byName.values()];
}

/** Whether a card entry is a funnel stage rather than a companion measure. */
export function isFunnelStage(
  entry: SpeakerPipelineStage | SpeakerPipelineCompanion,
): entry is SpeakerPipelineStage {
  return "share_of_baseline_pct" in entry;
}

/**
 * A sentence naming one stage's count for a screen reader.
 *
 * The funnel's geometry conveys proportion, and geometry is unavailable to a
 * screen reader; this is the text equivalent carrying the same facts. It
 * quotes the server's `share_display` rather than formatting a number, for
 * the same reason everything else here does.
 */
export function stageAccessibleLabel(stage: SpeakerPipelineStage): string {
  if (stage.value === null) {
    return `${stage.display_name}: not measured. ${stage.unknown_reason ?? ""}`.trim();
  }
  if (stage.share_of_baseline_pct === null) {
    return `${stage.display_name}: ${stage.value}.`;
  }
  return `${stage.display_name}: ${stage.value}, ${stage.share_display} of the widest stage.`;
}
