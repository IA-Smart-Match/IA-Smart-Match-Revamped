/**
 * Coordinator discovery feed with red / yellow / green severity.
 *
 * Stakeholder direction (`docs/plans/workshops/g1-workshop-output-worksheet.md`,
 * directive "Dashboard discovery feed (R/Y/G) — Legacy frontend O4"): the
 * coordinator's home should say what needs doing, and say it at a glance.
 *
 * What this component does *not* do is decide any of it. Each row is handed
 * an {@link AccountableMetric} — a registered metric read from
 * `GET /v1/units/{unit_id}/metrics` — plus the threshold rule that turns
 * that metric's value into a colour (`src/lib/signals.ts`). The component
 * renders the value through `AccountableValue`, so an unmeasured number
 * reaches the screen as "Unknown" with its reason and never as `0`
 * (ADR-0011 rule 1, `apps/web/DESIGN.md` §1.9), and it renders the colour
 * that `toneForBacklog` returned, which for an unknown value is the neutral
 * "Not measured" tone rather than green.
 *
 * Every row whose metric carries a drill-down is a button that opens exactly
 * the rows the number was computed from (ADR-0011 rule 4 / DESIGN.md §1.10),
 * so the colour is checkable rather than asserted. Rows without one are
 * static text — an aggregate is never given a fake affordance.
 *
 * `apps/web/DESIGN.md` §1.11 ("action queue before statistics") is why the
 * feed sorts by severity rather than by an arbitrary fixed order.
 */
import type { LucideIcon } from "lucide-react";

import { AccountableValue, type AccountableMetric } from "./provenance";
import {
  SIGNAL_TONE_CLASSES,
  SIGNAL_TONE_ICON_CLASSES,
  SIGNAL_TONE_LABELS,
  SIGNAL_TONE_RANK,
  toneForBacklog,
  type SignalThresholds,
  type SignalTone,
} from "@/lib/signals";

export interface DiscoveryFeedItem {
  /** Stable key and heading for the row. */
  readonly title: string;
  readonly icon: LucideIcon;
  /**
   * The registered metric this row reports. Its value — known, truncated, or
   * unknown-with-a-reason — is what the row renders and what the tone is
   * derived from.
   */
  readonly metric: AccountableMetric;
  /**
   * Threshold rule for this metric, or `null` for a row that reports a
   * *state* rather than a count (e.g. "matching is gated on G1"). A row with
   * no thresholds is always the neutral tone: there is no measurement to
   * grade, so grading one would be inventing it.
   */
  readonly thresholds: SignalThresholds | null;
  /** Sentence under the value. Should say what the number means or why it is absent. */
  readonly detail: string;
}

export interface DiscoveryFeedProps {
  readonly items: readonly DiscoveryFeedItem[];
  readonly className?: string;
}

interface GradedItem extends DiscoveryFeedItem {
  /**
   * The row's severity, or `null` when the row carries no threshold rule.
   *
   * `null` is *not* the same as the `"unknown"` tone, and conflating the two
   * is a lie in its own right: a row with no grading rule can still hold a
   * perfectly well-measured value (the registered `opportunities` count, for
   * instance), so badging it "Not measured" would assert an absence of
   * evidence that the number visible right beside it contradicts. An
   * ungraded row therefore shows no severity badge at all — there is no
   * severity to report — and the value speaks for itself through
   * `AccountableValue`.
   */
  readonly tone: SignalTone | null;
}

/**
 * Grades every row, then orders unresolved severity ahead of measured calm,
 * with ungraded context rows last (DESIGN.md §1.11: what needs doing comes
 * before how things are going).
 */
function gradeAndSort(items: readonly DiscoveryFeedItem[]): GradedItem[] {
  const rank = (tone: SignalTone | null) =>
    tone === null ? Object.keys(SIGNAL_TONE_RANK).length : SIGNAL_TONE_RANK[tone];

  return items
    .map((item) => ({
      ...item,
      tone: item.thresholds ? toneForBacklog(item.metric.value, item.thresholds) : null,
    }))
    .sort((left, right) => rank(left.tone) - rank(right.tone));
}

export function DiscoveryFeed({ items, className }: DiscoveryFeedProps) {
  const graded = gradeAndSort(items);

  if (graded.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-[#cfd8e5] bg-[#f7f9fc] p-8 text-sm text-gray-600">
        No registered metric is currently readable, so there is nothing this feed can report.
      </div>
    );
  }

  return (
    <ul className={className ? `space-y-3 ${className}` : "space-y-3"}>
      {graded.map((item) => {
        const Icon = item.icon;

        return (
          <li
            key={item.title}
            className={`flex gap-4 rounded-2xl border p-4 shadow-sm ${SIGNAL_TONE_CLASSES[item.tone ?? "unknown"]}`}
          >
            <div
              className={`mt-0.5 flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border ${SIGNAL_TONE_ICON_CLASSES[item.tone ?? "unknown"]}`}
            >
              <Icon className="h-5 w-5" aria-hidden="true" />
            </div>

            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <p className="font-semibold">{item.title}</p>
                {/* The label, not the colour, is what carries severity for a
                    screen-reader or a viewer who cannot distinguish the hues
                    (DESIGN.md §1.5, WCAG 2.2 AA). A row with no threshold
                    rule gets no badge rather than a misleading one. */}
                {item.tone ? (
                  <span className="rounded-full border border-current/25 bg-white/80 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.18em]">
                    {SIGNAL_TONE_LABELS[item.tone]}
                  </span>
                ) : null}
              </div>

              <p className="mt-2 text-2xl font-semibold tracking-tight">
                <AccountableValue
                  metric={item.metric}
                  formatNumber={(value) => value.toLocaleString("en-US")}
                />
              </p>

              <p className="mt-2 text-sm leading-6 opacity-90">{item.detail}</p>

              {item.thresholds ? (
                <p className="mt-2 text-xs leading-5 opacity-75">{item.thresholds.rationale}</p>
              ) : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
