/**
 * The load band a run stored for one candidate (B26 T8d plan §7.1): one `dl`
 * row, so a screen reader reads "Workload, Moderate", and the detail sentence.
 *
 * The caller renders it only when the run's `load_recorded` is true, inside its
 * own `dl`. A missing block reads "Workload not recorded for this Speaker": a
 * defect made visible, never a default band (ADR-0011). A word only, never a
 * number (OQ-CBA-005).
 */
import type { MatchLoad } from "@/lib/api";
import { LOAD_NOT_RECORDED, WORKLOAD_TERM, runLoadDetail, runLoadWord } from "@/lib/loadBandCopy";

export function RunLoadLine({ load }: { load: MatchLoad | null | undefined }) {
  const detail = load ? runLoadDetail(load) : null;
  return (
    <div className="flex flex-col gap-1 sm:flex-row sm:flex-wrap sm:items-baseline sm:gap-x-2">
      <dt className="text-muted-foreground">{WORKLOAD_TERM}</dt>
      <dd className="font-medium text-foreground">
        {load ? runLoadWord(load.band) : LOAD_NOT_RECORDED}
      </dd>
      {detail !== null ? (
        <dd className="basis-full break-words text-muted-foreground">{detail}</dd>
      ) : null}
    </div>
  );
}
