/**
 * The icon half of the Speaker Pipeline presentation rules.
 *
 * Split out from `speakerPipeline.ts` so that module has no runtime imports
 * and can be loaded directly by `node --test`. Nothing here decides anything
 * about a number; every table is keyed by a stable identifier the server
 * sends (a canonical metric name, an insight tone), never by matching on
 * displayed prose, so rewording a label server-side cannot silently change
 * which icon appears.
 */
import type { LucideIcon } from "lucide-react";
import {
  ArrowDownRight,
  CheckCircle2,
  ClipboardList,
  Clock,
  Info,
  Lightbulb,
  Presentation,
  Send,
  TrendingUp,
  TriangleAlert,
  Users,
} from "lucide-react";

/**
 * One icon per registered metric. Decorative in every case — the card already
 * names its metric in text, so these are `aria-hidden` where they are used.
 */
export const METRIC_ICONS: Record<string, LucideIcon> = {
  pipeline_matched: Users,
  pipeline_contacted: Send,
  pipeline_confirmed: CheckCircle2,
  pipeline_attended: Presentation,
  opportunities: ClipboardList,
  pending_review_items: Clock,
};

export function iconFor(metricName: string): LucideIcon {
  return METRIC_ICONS[metricName] ?? Info;
}

/** One icon per insight tone. Decorative; the tone is also named in text. */
export const TONE_ICONS: Record<string, LucideIcon> = {
  attention: TriangleAlert,
  opportunity: ArrowDownRight,
  strength: TrendingUp,
  neutral: Lightbulb,
};

/**
 * How each tone is shown, and what it is *called*.
 *
 * The label matters as much as the badge: an insight's severity must not be
 * conveyed by colour alone, so every insight prints its tone in words.
 */
export const TONE_STYLES: Record<string, { badge: string; label: string }> = {
  attention: {
    badge: "bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-200",
    label: "Needs attention",
  },
  opportunity: {
    badge: "bg-sky-100 text-sky-800 dark:bg-sky-950/60 dark:text-sky-200",
    label: "Opportunity",
  },
  strength: {
    badge: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-200",
    label: "Working well",
  },
  neutral: {
    badge: "bg-muted text-muted-foreground",
    label: "For information",
  },
};

export function toneIconFor(tone: string): LucideIcon {
  return TONE_ICONS[tone] ?? Lightbulb;
}

export function toneStyleFor(tone: string): { badge: string; label: string } {
  return TONE_STYLES[tone] ?? TONE_STYLES.neutral;
}
