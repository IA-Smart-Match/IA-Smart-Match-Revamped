/**
 * The Key Insights panel.
 *
 * Every sentence here was written by the server from named, documented
 * thresholds (`smartmatch_domain.speaker_pipeline`), and this component
 * composes none of them. That is deliberate rather than fastidious: an
 * insight is a claim about the numbers, so a claim assembled in the browser
 * would be a second, unauditable opinion sitting beside the measured ones and
 * looking exactly as authoritative.
 *
 * The client's only judgement is which icon and which badge to show, and it
 * makes that from the insight's stable `code`/`tone` rather than by matching
 * on prose — so rewording a sentence server-side can never silently change
 * how it is presented.
 *
 * The tone is printed in words as well as coloured, so severity is never
 * carried by colour alone.
 */
import { Lightbulb } from "lucide-react";

import type { SpeakerPipelineInsight } from "@/lib/api";
import { toneIconFor, toneStyleFor } from "@/lib/speakerPipelineIcons";

function PipelineInsight({ insight }: { insight: SpeakerPipelineInsight }) {
  const Icon = toneIconFor(insight.tone);
  const style = toneStyleFor(insight.tone);

  return (
    <li className="flex items-start gap-3">
      <span
        className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${style.badge}`}
      >
        <Icon className="h-4 w-4" aria-hidden="true" />
      </span>
      <div className="min-w-0">
        <p className="text-sm font-semibold leading-5 text-foreground">
          {insight.title}{" "}
          <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            · {style.label}
          </span>
        </p>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">{insight.detail}</p>
      </div>
    </li>
  );
}

export function PipelineInsightsCard({ insights }: { insights: SpeakerPipelineInsight[] }) {
  return (
    <section
      className="rounded-2xl border border-border bg-card p-5"
      aria-labelledby="speaker-pipeline-insights-heading"
    >
      <div className="flex items-center gap-2">
        <Lightbulb className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <h3
          id="speaker-pipeline-insights-heading"
          className="text-base font-semibold text-foreground"
        >
          Key Insights
        </h3>
      </div>

      {insights.length === 0 ? (
        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          The server produced no insights for this period.
        </p>
      ) : (
        <ul className="mt-4 space-y-4">
          {insights.map((insight) => (
            <PipelineInsight key={insight.code} insight={insight} />
          ))}
        </ul>
      )}
    </section>
  );
}
