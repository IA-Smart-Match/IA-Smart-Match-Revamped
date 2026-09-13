/**
 * The Speaker Pipeline section: header, KPI row, funnel, and the right rail.
 *
 * One read backs all of it — `GET /v1/units/{unit_id}/speaker-pipeline` — and
 * that is a correctness property before it is a performance one. Six separate
 * reads would count six numbers at six different moments, so a conversion's
 * numerator and denominator could disagree about which rows existed.
 *
 * ## Four states, and none of them lies
 *
 * **Loading** draws skeletons in the final layout's shape, so nothing jumps.
 * **Error** shows the server's own words and draws no funnel at all — a
 * funnel of zeros after a failed read is the single worst thing this section
 * could do, because it is indistinguishable from a unit with no activity.
 * **Measured zero** *does* draw the funnel, at its minimum widths, because a
 * query that ran and found nothing is a real answer. **Unknown** metrics keep
 * the server's `unknown_reason` and are never shown as `0`.
 *
 * ## The range control
 *
 * The reference design shows a "Last 90 days" dropdown. None of the owning
 * queries behind these metrics takes a date window, so there is no second
 * range to offer and the control is a label rather than a menu: an affordance
 * that opened onto one option — or worse, onto options that changed nothing —
 * would be a claim that the figures are filtered. The label and its
 * explanation both come from the server's `range`.
 */
import { BarChart3, CalendarDays } from "lucide-react";

import { ApiRequestError, fetchSpeakerPipeline } from "@/lib/api";
import { useScopedQuery } from "@/app/hooks/useScopedQuery";
import { ConversionRatesCard } from "@/app/components/speakerPipeline/ConversionRatesCard";
import { PipelineFunnelCard } from "@/app/components/speakerPipeline/PipelineFunnelCard";
import { PipelineInsightsCard } from "@/app/components/speakerPipeline/PipelineInsightsCard";
import { PipelineMetricGrid } from "@/app/components/speakerPipeline/PipelineMetricGrid";
import { SpeakerPipelineSkeleton } from "@/app/components/speakerPipeline/SpeakerPipelineSkeleton";
import { metricCardOrder } from "@/lib/speakerPipeline";

/** What the range control shows before the server has said what it covers. */
const RANGE_PLACEHOLDER = "Range not yet read";

function RangeLabel({ label, note }: { label: string; note: string }) {
  return (
    <div
      className="flex items-center gap-2 rounded-xl border border-border bg-card px-3 py-2"
      title={note}
    >
      <CalendarDays className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <div className="leading-tight">
        <p className="text-sm font-medium text-foreground">{label}</p>
        <p className="text-[11px] text-muted-foreground">Not filtered by date</p>
      </div>
    </div>
  );
}

function SectionHeader({ range }: { range: { label: string; note: string } | null }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex items-start gap-2">
        <BarChart3 className="mt-1.5 h-5 w-5 shrink-0 text-muted-foreground" aria-hidden="true" />
        <div>
          <p className="text-2xl font-semibold tracking-tight text-foreground">Speaker Pipeline</p>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
            From match to confirmed — see how your speakers move through each stage. Every figure
            is counted by the server, and each is a registered metric with a single owning query
            behind it. No total, rate or rounding is produced in your browser.
          </p>
        </div>
      </div>
      <RangeLabel label={range?.label ?? RANGE_PLACEHOLDER} note={range?.note ?? ""} />
    </div>
  );
}

export interface SpeakerPipelineSectionProps {
  /** The unit the server granted this account; every figure is scoped to it. */
  unitId: string;
}

export function SpeakerPipelineSection({ unitId }: SpeakerPipelineSectionProps) {
  // Through the shared cache like every other page-load read — a revisit to
  // the dashboard inside `staleTime` renders the funnel immediately.
  const pipelineQuery = useScopedQuery({
    resource: "speaker-pipeline",
    params: [unitId],
    queryFn: () => fetchSpeakerPipeline(unitId),
  });

  const payload = pipelineQuery.data ?? null;
  // The server's own words where it gave any: `ApiRequestError.message`
  // carries the API's error text, including the refusal a 403 explains,
  // and a rephrasing here would be this page's opinion about someone
  // else's decision.
  const error = pipelineQuery.isError
    ? pipelineQuery.error instanceof ApiRequestError
      ? pipelineQuery.error.message
      : "The speaker pipeline could not be read and the server gave no reason."
    : null;
  const settled = !pipelineQuery.isPending;

  return (
    <section
      className="rounded-3xl border border-border bg-background p-6"
      aria-labelledby="speaker-pipeline-heading"
    >
      <h2 id="speaker-pipeline-heading" className="sr-only">
        Speaker Pipeline
      </h2>
      <SectionHeader range={payload?.range ?? null} />

      {error !== null ? (
        <p
          role="alert"
          className="mt-6 rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm leading-6 text-foreground"
        >
          {error} Nothing below is drawn from a failed read — a funnel of zeros here would be
          indistinguishable from a unit with no activity.
        </p>
      ) : payload === null ? (
        <SpeakerPipelineSkeleton settled={settled} />
      ) : (
        <div className="mt-6 space-y-4">
          <PipelineMetricGrid entries={metricCardOrder(payload)} />

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <PipelineFunnelCard stages={payload.stages} conversions={payload.conversions} />
            </div>
            <div className="space-y-4 lg:col-span-1">
              <ConversionRatesCard conversions={payload.conversions} />
              <PipelineInsightsCard insights={payload.insights} />
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
