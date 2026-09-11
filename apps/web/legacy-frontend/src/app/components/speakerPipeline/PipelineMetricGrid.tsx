/**
 * The six-card KPI row.
 *
 * Each card renders one registered metric exactly as the server answered for
 * it, in three states that must stay visibly distinct: a measured number, a
 * measured zero (which prints as `0`, because the query ran and found none),
 * and an unknown carrying the server's own reason. There is no fourth branch
 * in which a missing value becomes a zero — ADR-0011 rule 1.
 *
 * ## Why the definition is behind a button
 *
 * The register's `definition` is a paragraph, and six of them printed on the
 * card faces ran the grid past the fold — so the first thing a Connector could
 * do with their unit's numbers was scroll away from them. The affordance that
 * fixes it is this repository's existing decision, ported here rather than
 * reinvented: the definition renders once, inside `<TooltipContent>`, opened
 * by a real `<button type="button">` carrying an `aria-label`. A `<span>` with
 * a mouse handler is the same control to a mouse and no control at all to a
 * keyboard, which is why the element type is load-bearing rather than
 * stylistic, and an unqualified `<button>` inside a form submits it. The
 * tooltip is this app's own primitive over `@radix-ui/react-tooltip`, already
 * a declared dependency, so the affordance adds none.
 * `tests/unit/test_frontend_dashboard_stats_contract.py` holds all of it.
 *
 * `unknown_reason` is the deliberate exception: it renders *inline* on the
 * card face, never in the tooltip. A reader must not have to go hunting for
 * why a number is missing — that would make an absence as easy to overlook as
 * a zero, which is the confusion the whole register exists to prevent.
 *
 * `PipelineFunnelTiles.tsx` is a different component for a different shell and
 * is untouched.
 */
import { Tooltip, TooltipContent, TooltipTrigger } from "@/app/components/ui/tooltip";
import type { SpeakerPipelineCompanion, SpeakerPipelineStage } from "@/lib/api";
import { isFunnelStage, tintFor, type StageTint } from "@/lib/speakerPipeline";
import { iconFor } from "@/lib/speakerPipelineIcons";

type MetricCardEntry = SpeakerPipelineStage | SpeakerPipelineCompanion;

function MetricValue({ metric }: { metric: MetricCardEntry }) {
  if (metric.value === null) {
    return (
      <>
        <p className="mt-1 text-lg font-semibold text-foreground">Not measured</p>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          {metric.unknown_reason ?? "The register gave no value and no reason."}
        </p>
      </>
    );
  }
  return (
    <p className="mt-1 text-3xl font-semibold tracking-tight tabular-nums text-foreground">
      {metric.value.toLocaleString("en-US")}
    </p>
  );
}

export function PipelineMetricCard({ metric }: { metric: MetricCardEntry }) {
  const tint: StageTint = tintFor(metric.metric_name);
  const Icon = iconFor(metric.metric_name);
  // A companion measure is not a funnel stage, and the card says so in words
  // rather than relying on its position in the row to imply it.
  const isStage = isFunnelStage(metric);

  return (
    <li className={`rounded-2xl border border-border/60 p-4 ${tint.card}`}>
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-[11px] font-semibold uppercase leading-4 tracking-wide text-muted-foreground">
          {metric.display_name}
        </h3>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              aria-label={`What ${metric.display_name} counts`}
              className="shrink-0 rounded focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              <Icon className={`h-5 w-5 ${tint.icon}`} aria-hidden="true" />
            </button>
          </TooltipTrigger>
          <TooltipContent className="max-w-xs text-xs leading-5">
            {metric.definition}
          </TooltipContent>
        </Tooltip>
      </div>

      <MetricValue metric={metric} />

      <p className="mt-2 text-xs leading-5 text-muted-foreground">{metric.description}</p>
      {isStage ? null : (
        <p className="mt-1 text-[11px] font-medium leading-4 text-muted-foreground">
          Review queue — not a funnel stage
        </p>
      )}
    </li>
  );
}

export function PipelineMetricGrid({ entries }: { entries: MetricCardEntry[] }) {
  return (
    <ul
      className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6"
      aria-label="Speaker pipeline figures"
    >
      {entries.map((entry) => (
        <PipelineMetricCard key={entry.metric_name} metric={entry} />
      ))}
    </ul>
  );
}
