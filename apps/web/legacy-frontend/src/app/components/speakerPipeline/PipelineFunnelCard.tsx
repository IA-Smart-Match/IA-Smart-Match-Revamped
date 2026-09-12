/**
 * The funnel itself: four narrowing bands and the conversions between them.
 *
 * Four, not six. `pipeline_matched → contacted → confirmed → attended` is a
 * cohort funnel because `ck_pipeline_record_stage_prefix` makes each stage's
 * rows a subset of the previous stage's. The two review-queue measures count
 * `review_item` rows instead, so they appear in the card row above and in the
 * queue strip beside it — never as a band, and never with an arrow into one.
 *
 * Geometry is CSS: a clipped `div` per band, width driven by the server's
 * measured share. Nothing is charted by a library and no dependency was added
 * for it. Crucially the geometry is never the *only* carrier of the facts —
 * every band prints its stage name, its count and its share as text, and each
 * band also carries a screen-reader sentence saying the same thing, because a
 * trapezoid is unavailable to a screen reader.
 *
 * No transitions or animation: nothing here has motion that would add
 * information, so there is nothing for `prefers-reduced-motion` to suppress.
 *
 * `PipelineFunnelTiles.tsx` is an unrelated component for the admin shell and
 * is untouched by this surface.
 */
import { Filter } from "lucide-react";

import type { SpeakerPipelineConversion, SpeakerPipelineStage } from "@/lib/api";
import {
  funnelWidthPercent,
  stageAccessibleLabel,
  tintFor,
  UNMEASURED_FUNNEL_WIDTH_PCT,
} from "@/lib/speakerPipeline";

/** How far each side of a band slopes inward, in pixels. */
const BAND_TAPER_PX = 26;

function FunnelBand({ stage }: { stage: SpeakerPipelineStage }) {
  const tint = tintFor(stage.metric_name);
  const measuredWidth = funnelWidthPercent(stage.share_of_baseline_pct);
  const width = measuredWidth ?? UNMEASURED_FUNNEL_WIDTH_PCT;
  // A band with no measured share is outlined rather than filled, so that its
  // fallback width is not mistaken for a measurement.
  const unmeasured = measuredWidth === null;

  return (
    <div className="flex justify-center">
      <div
        className={
          unmeasured
            ? "flex min-h-[62px] flex-col items-center justify-center border-2 border-dashed border-border px-4 py-2"
            : `flex min-h-[62px] flex-col items-center justify-center px-4 py-2 ${tint.band}`
        }
        style={{
          width: `${width}%`,
          clipPath: unmeasured
            ? undefined
            : `polygon(0 0, 100% 0, calc(100% - ${BAND_TAPER_PX}px) 100%, ${BAND_TAPER_PX}px 100%)`,
        }}
      >
        {stage.value === null ? (
          <span className="text-xs font-medium text-muted-foreground">Not measured</span>
        ) : (
          <>
            <span
              className={`text-xl font-semibold leading-6 tabular-nums ${
                unmeasured ? "text-foreground" : tint.bandText
              }`}
            >
              {stage.value.toLocaleString("en-US")}
            </span>
            <span
              className={`text-[11px] leading-4 ${
                unmeasured ? "text-muted-foreground" : tint.bandText
              }`}
            >
              {stage.share_display}
            </span>
          </>
        )}
      </div>
    </div>
  );
}

/**
 * One conversion, drawn between the two bands it relates.
 *
 * Rendered only for transitions the server published, which are only the
 * adjacent lifecycle pairs. Where there is no rate — an unmeasured stage on
 * either side, or nobody at the upstream stage — the server's em dash is
 * shown together with its reason, rather than a `0%` that would read as a
 * measurement of failure.
 */
function ConversionAnnotation({ conversion }: { conversion: SpeakerPipelineConversion }) {
  return (
    <p className="px-1 text-center text-[11px] leading-4 text-muted-foreground">
      <span className="font-semibold text-foreground">{conversion.display}</span>{" "}
      <span>{conversion.accessible_label.toLowerCase()}</span>
      {conversion.unavailable_reason ? (
        <>
          {" — "}
          <span>{conversion.unavailable_reason}</span>
        </>
      ) : null}
    </p>
  );
}

export interface PipelineFunnelCardProps {
  stages: SpeakerPipelineStage[];
  conversions: SpeakerPipelineConversion[];
}

export function PipelineFunnelCard({ stages, conversions }: PipelineFunnelCardProps) {
  const conversionsFrom = new Map(conversions.map((conversion) => [conversion.from_metric, conversion]));

  return (
    <section
      className="rounded-2xl border border-border bg-card p-6"
      aria-labelledby="speaker-pipeline-funnel-heading"
    >
      <div className="flex items-start gap-2">
        <Filter className="mt-1 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <div>
          <h3
            id="speaker-pipeline-funnel-heading"
            className="text-lg font-semibold text-foreground"
          >
            Speaker Pipeline Funnel
          </h3>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">
            See how many speakers move through each stage, and where you can improve. These four
            stages are one lifecycle — each is a subset of the one above it, which is what makes
            the percentages between them conversions.
          </p>
        </div>
      </div>

      {stages.length === 0 ? (
        <p className="mt-6 text-sm text-muted-foreground">
          The register presented no funnel stages for this unit, so there is no funnel to draw.
          This is a statement about the register, not about your unit&apos;s activity.
        </p>
      ) : (
        <ol className="mt-6 space-y-1">
          {stages.map((stage) => {
            const onward = conversionsFrom.get(stage.metric_name);
            return (
              <li key={stage.metric_name}>
                <div className="grid grid-cols-1 items-center gap-2 sm:grid-cols-[minmax(9rem,14rem)_1fr]">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold leading-5 text-foreground">
                      {stage.display_name}
                    </p>
                    <p className="text-xs leading-5 text-muted-foreground">{stage.description}</p>
                  </div>
                  <div>
                    <FunnelBand stage={stage} />
                    {/*
                      The geometry above carries proportion visually. This is
                      the same fact in text, for a reader who gets no picture.
                    */}
                    <span className="sr-only">{stageAccessibleLabel(stage)}</span>
                  </div>
                </div>
                {onward ? (
                  <div className="grid grid-cols-1 gap-2 py-1 sm:grid-cols-[minmax(9rem,14rem)_1fr]">
                    <div aria-hidden="true" />
                    <ConversionAnnotation conversion={onward} />
                  </div>
                ) : null}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
