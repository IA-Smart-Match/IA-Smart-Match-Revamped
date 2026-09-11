/**
 * The six-card KPI row.
 *
 * Each card renders one registered metric exactly as the server answered for
 * it, in three states that must stay visibly distinct: a measured number, a
 * measured zero (which prints as `0`, because the query ran and found none),
 * and an unknown carrying the server's own reason. There is no fourth branch
 * in which a missing value becomes a zero — ADR-0011 rule 1.
 *
 * The register's own sentence about what the number counts travels with every
 * card rather than being dropped for space. It is what lets a coordinator tell
 * "Speaker Requests" (an accepted, in-list opportunity row) from "Speakers
 * matched" (a pipeline record) without being told by this component's prose.
 *
 * `PipelineFunnelTiles.tsx` is a different component for a different shell
 * (the admin dashboard, scoped by the build-variable unit) and is untouched.
 */
import type { SpeakerPipelineCompanion, SpeakerPipelineStage } from "@/lib/api";
import { isFunnelStage, tintFor, type StageTint } from "@/lib/speakerPipeline";
import { iconFor } from "@/lib/speakerPipelineIcons";

type MetricCardEntry = SpeakerPipelineStage | SpeakerPipelineCompanion;

function MetricValue({ entry }: { entry: MetricCardEntry }) {
  if (entry.value === null) {
    return (
      <>
        <p className="mt-1 text-lg font-semibold text-foreground">Not measured</p>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          {entry.unknown_reason ?? "The register gave no value and no reason."}
        </p>
      </>
    );
  }
  return (
    <p className="mt-1 text-3xl font-semibold tabular-nums tracking-tight text-foreground">
      {entry.value.toLocaleString("en-US")}
    </p>
  );
}

export function PipelineMetricCard({ entry }: { entry: MetricCardEntry }) {
  const tint: StageTint = tintFor(entry.metric_name);
  const Icon = iconFor(entry.metric_name);
  // A companion measure is not a funnel stage, and the card says so in words
  // rather than relying on its position in the row to imply it.
  const isStage = isFunnelStage(entry);

  return (
    <li className={`rounded-2xl border border-border/60 p-4 ${tint.card}`}>
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-[11px] font-semibold uppercase leading-4 tracking-wide text-muted-foreground">
          {entry.display_name}
        </h3>
        <Icon className={`h-5 w-5 shrink-0 ${tint.icon}`} aria-hidden="true" />
      </div>

      <MetricValue entry={entry} />

      <p className="mt-2 text-xs leading-5 text-muted-foreground">{entry.description}</p>
      {isStage ? null : (
        <p className="mt-1 text-[11px] font-medium leading-4 text-muted-foreground">
          Review queue — not a funnel stage
        </p>
      )}
      {isStage ? null : (
        <details className="mt-2">
          <summary className="cursor-pointer text-[11px] text-muted-foreground underline underline-offset-2">
            What this counts
          </summary>
          <p className="mt-1 text-[11px] leading-4 text-muted-foreground">{entry.definition}</p>
        </details>
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
        <PipelineMetricCard key={entry.metric_name} entry={entry} />
      ))}
    </ul>
  );
}
