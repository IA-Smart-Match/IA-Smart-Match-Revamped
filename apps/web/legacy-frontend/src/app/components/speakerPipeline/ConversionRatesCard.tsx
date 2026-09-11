/**
 * The Conversion Rates panel: one row per published transition.
 *
 * Every row here was computed server-side and arrives with its percentage
 * already rendered. Nothing in this file divides anything. That is the point:
 * the same rate is annotated on the funnel beside this panel, and two
 * independent calculations of one published number is exactly the defect
 * ADR-0011 rule 4 names.
 *
 * The rows are whichever transitions the server published — three today, the
 * adjacent lifecycle pairs — rather than a fixed list of five written here. A
 * hard-coded row for "Requests → Review" would draw a conversion between two
 * `review_item` counts and one `pipeline_record` count, which is the mistake
 * the whole surface is shaped to refuse.
 *
 * The bar is decoration over the number, never instead of it: the percentage
 * is printed as text in every row, so nothing is conveyed by colour or by
 * length alone.
 */
import { BarChart3 } from "lucide-react";

import type { SpeakerPipelineConversion } from "@/lib/api";
import { tintFor } from "@/lib/speakerPipeline";

function ConversionRateRow({ conversion }: { conversion: SpeakerPipelineConversion }) {
  const tint = tintFor(conversion.to_metric);
  const rate = conversion.rate_pct;
  const measured = rate !== null;
  // The bar is clamped only for drawing. The printed percentage is always the
  // server's `display`, so a clamp can never become a reported figure.
  const barWidth = measured ? Math.min(100, Math.max(0, rate)) : 0;

  return (
    <li className="border-b border-border/60 py-2 last:border-b-0">
      <div className="flex items-center gap-3">
        <span className="min-w-0 flex-1 truncate text-sm text-foreground">{conversion.label}</span>
        <span className="shrink-0 text-sm font-semibold tabular-nums text-foreground">
          {conversion.display}
        </span>
        <span
          className="h-2 w-24 shrink-0 overflow-hidden rounded-full bg-muted"
          role="img"
          aria-label={
            measured
              ? `${conversion.label}: ${conversion.display}.`
              : `${conversion.label}: no rate. ${conversion.unavailable_reason ?? ""}`.trim()
          }
        >
          <span
            className={`block h-full rounded-full ${measured ? tint.bar : "bg-transparent"}`}
            style={{ width: `${barWidth}%` }}
          />
        </span>
      </div>
      {conversion.unavailable_reason ? (
        <p className="mt-1 text-[11px] leading-4 text-muted-foreground">
          {conversion.unavailable_reason}
        </p>
      ) : null}
    </li>
  );
}

export function ConversionRatesCard({
  conversions,
}: {
  conversions: SpeakerPipelineConversion[];
}) {
  return (
    <section
      className="rounded-2xl border border-border bg-card p-5"
      aria-labelledby="speaker-pipeline-conversions-heading"
    >
      <div className="flex items-center gap-2">
        <BarChart3 className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <h3
          id="speaker-pipeline-conversions-heading"
          className="text-base font-semibold text-foreground"
        >
          Conversion Rates
        </h3>
      </div>

      {conversions.length === 0 ? (
        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          No transition on this surface is a cohort conversion, so no rate is shown. A ratio
          between two figures that count different things would not be one.
        </p>
      ) : (
        <>
          <ul className="mt-3">
            {conversions.map((conversion) => (
              <ConversionRateRow
                key={`${conversion.from_metric}:${conversion.to_metric}`}
                conversion={conversion}
              />
            ))}
          </ul>
          <p className="mt-3 text-[11px] leading-4 text-muted-foreground">
            Only consecutive lifecycle stages appear here. The review-queue figures count a
            different kind of row, so no percentage between them and a stage would be a
            conversion.
          </p>
        </>
      )}
    </section>
  );
}
