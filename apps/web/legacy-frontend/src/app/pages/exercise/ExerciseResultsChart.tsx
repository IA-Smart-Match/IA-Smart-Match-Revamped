/**
 * The class exercise's results bar chart, readable from a projector.
 *
 * The requirements table's "Simulated results" row asks, as a nice-to-have,
 * for "results as a simple bar chart readable from the projector". This is
 * that chart and only that chart: it is driven entirely by its props, holds no
 * fetch, no simulation, and no knowledge of how a result was produced. The
 * exercise base — the scope, the `exercise_` tables, the routers, the §11
 * simulation rule — does not exist yet (ADR-0025 is Accepted, unbuilt); when
 * it does, the results screen passes its panels in through `series`.
 *
 * ## The only numbers here are head counts
 *
 * ADR-0025 D8, carried from ADR-0024 D8: no percentage, rate, match score, or
 * confidence reaches a class participant. Invited / signed up / attended are
 * head counts of made-up profiles, which the requirements explicitly ask to
 * show, so they are all this component knows how to render. It computes no
 * sign-up rate, no conversion, and no share, and a prop for one must not be
 * added — the arithmetic would be one division away and the screen would then
 * carry the number the ADR forbids.
 *
 * ## "Not available" is never drawn as zero
 *
 * A count the caller does not have is `null`, and `null` renders as the words
 * "not available" — in the bar's place and in the table. Zero is a counted
 * zero and draws an honest empty bar labelled `0`. Conflating them would let a
 * screen assert "nobody signed up" on the strength of a result that was never
 * run, which is exactly the failure a projector makes unarguable.
 *
 * ## No chart from placeholder numbers
 *
 * With no series, or with every count in every series unavailable, there is
 * nothing to draw and the component says so. It never substitutes example
 * data, and there is no fallback dataset in this file.
 *
 * ## The title is written once and announced once
 *
 * The visible heading is the chart's only name. The graphic points at it with
 * `aria-labelledby`, so the words exist in one place and a screen reader
 * reaches them once; the wrapper carries no `aria-label`, and the table's
 * caption says what the table is rather than repeating the heading. Naming the
 * same thing in several ways does not make it clearer — it makes the title
 * arrive three or four times before any count does.
 *
 * ## Readable at classroom distance, and not by colour alone
 *
 * Large type throughout; every bar carries its value as a direct label, so
 * nobody reads a number off an axis from the back of the room; each stage has
 * both a distinct high-contrast fill and a distinct hatch pattern; and the
 * whole chart is repeated as a real `<table>` for screen readers and for
 * anyone the colours fail.
 */
import { useId } from "react";
import { Bar, BarChart, CartesianGrid, LabelList, Legend, XAxis, YAxis } from "recharts";

/**
 * One head count, or `null` when the caller does not have it.
 *
 * Deliberately not `number | undefined`: a missing property and an absent
 * count read the same way at a call site, and the distinction this type exists
 * to keep is the one between "counted none" and "did not look".
 */
export type ExerciseHeadCount = number | null;

/** One panel of the results screen — a team's list, "email everyone", or a stored round. */
export interface ExerciseResultsSeries {
  /** What this panel is, in the words a participant reads. */
  readonly label: string;
  /** How many profiles the panel invited. */
  readonly invited: ExerciseHeadCount;
  /** How many of them signed up. */
  readonly signedUp: ExerciseHeadCount;
  /** How many of them attended. */
  readonly attended: ExerciseHeadCount;
}

export interface ExerciseResultsChartProps {
  /**
   * The panels to compare, in the order they should read left to right. The
   * §10 comparison view passes the team's list, "email everyone", and — in
   * round two — the team's stored round one.
   */
  readonly series: readonly ExerciseResultsSeries[];
  /** An accessible name for the chart. */
  readonly title: string;
  /** Optional sentence under the chart, e.g. which event these results are for. */
  readonly caption?: string;
  /** What to say when there is nothing to draw. */
  readonly emptyMessage?: string;
  /**
   * `"default"` is the chart as it has always been drawn. `"exercise"` is the
   * invitation desk's restyle (`docs/design/class-exercise/DESIGN.md` §3.3,
   * §6.16): CPP series fills with a hatch/solid/open cue each, a legend in
   * words, horizontal bars on a phone, and the table folded under "Show these
   * counts as a table". A variant, not a copy: the counts, the empty state,
   * "not available" and the one accessible name are the same code path.
   */
  readonly variant?: "default" | "exercise";
  /** Exercise variant only: draw horizontal bars (the 390 layout, §7.8). */
  readonly horizontal?: boolean;
}

/** The three stages, in the order the case moves through them. */
const STAGES = [
  { key: "invited", label: "Invited", fill: "#1f3a93", pattern: "exercise-results-hatch-invited" },
  {
    key: "signedUp",
    label: "Signed up",
    fill: "#0b6b53",
    pattern: "exercise-results-hatch-signed-up",
  },
  {
    key: "attended",
    label: "Attended",
    fill: "#8a3b00",
    pattern: "exercise-results-hatch-attended",
  },
] as const;

type StageKey = (typeof STAGES)[number]["key"];

/** Projector type sizes. Small enough to fit three panels, large enough to read from the back. */
const AXIS_FONT_SIZE = 20;
const VALUE_FONT_SIZE = 26;
const LEGEND_FONT_SIZE = 20;

const NOT_AVAILABLE = "not available";

/**
 * Whether anything at all can be drawn.
 *
 * Exported because the honest-empty-state rule is the one behaviour a caller
 * may need to ask about before it decides to mount a chart at all, and because
 * a rule this load-bearing deserves a test that does not go through the DOM.
 */
export function hasDrawableCounts(series: readonly ExerciseResultsSeries[]): boolean {
  return series.some((panel) =>
    STAGES.some((stage) => typeof panel[stage.key as StageKey] === "number"),
  );
}

/** Renders a count for a human: a number as itself, an absent count in words. */
export function formatHeadCount(count: ExerciseHeadCount): string {
  return typeof count === "number" ? String(count) : NOT_AVAILABLE;
}

/**
 * The direct label on a bar.
 *
 * Recharts omits the bar entirely for a `null` value, so an unavailable count
 * has no label to attach; the table below the chart carries the words instead.
 */
function renderValueLabel(value: unknown): string {
  return typeof value === "number" ? String(value) : "";
}

export function ExerciseResultsChart({
  series,
  title,
  caption,
  emptyMessage = "No results to show yet. Run the results for this event to see the counts here.",
  variant = "default",
  horizontal = false,
}: ExerciseResultsChartProps): JSX.Element {
  const baseId = useId();
  const headingId = `${baseId}-exercise-results-title`;

  if (!hasDrawableCounts(series)) {
    return (
      <section data-testid="exercise-results-chart-empty">
        <h2
          id={headingId}
          className={variant === "exercise" ? "ce-h2 mb-3 text-ce-ink" : undefined}
          style={variant === "exercise" ? undefined : { fontSize: 30, margin: "0 0 12px" }}
        >
          {title}
        </h2>
        <p
          className={variant === "exercise" ? "ce-body text-ce-ink" : undefined}
          style={variant === "exercise" ? undefined : { fontSize: 24, lineHeight: 1.4 }}
        >
          {emptyMessage}
        </p>
      </section>
    );
  }

  if (variant === "exercise") {
    return (
      <ExerciseVariant
        series={series}
        title={title}
        caption={caption}
        headingId={headingId}
        patternPrefix={baseId.replace(/[^a-zA-Z0-9_-]/g, "")}
        horizontal={horizontal}
      />
    );
  }

  const rows = series.map((panel) => ({
    label: panel.label,
    invited: panel.invited,
    signedUp: panel.signedUp,
    attended: panel.attended,
  }));

  const unavailable = series.flatMap((panel) =>
    STAGES.filter((stage) => typeof panel[stage.key as StageKey] !== "number").map(
      (stage) => `${panel.label}: ${stage.label.toLowerCase()} ${NOT_AVAILABLE}`,
    ),
  );

  return (
    <section data-testid="exercise-results-chart" className="min-w-0 max-w-full">
      <h2 id={headingId} style={{ fontSize: 30, margin: "0 0 12px" }}>
        {title}
      </h2>

      {/* M2 B2: the chart is drawn at a fixed width for the projector. On a
          phone it scrolls inside this box instead of widening the page; the
          table below repeats every count. Focusable and named so a keyboard
          can scroll it (axe scrollable-region-focusable). Its name is not the
          title: the chart graphic already carries that, once. */}
      <div
        className="max-w-full overflow-x-auto"
        data-testid="exercise-results-chart-scroll"
        tabIndex={0}
        role="region"
        aria-label="Results chart. Scroll sideways to see all of it."
      >
        <BarChart
          width={880}
          height={460}
          data={rows}
          role="img"
          aria-labelledby={headingId}
          margin={{ top: 32, right: 24, bottom: 16, left: 16 }}
        >
          <defs>
            {STAGES.map((stage) => (
              <pattern
                key={stage.pattern}
                id={stage.pattern}
                patternUnits="userSpaceOnUse"
                width={8}
                height={8}
                patternTransform={`rotate(${STAGES.indexOf(stage) * 45})`}
              >
                <rect width={8} height={8} fill={stage.fill} />
                <line x1={0} y1={0} x2={0} y2={8} stroke="#ffffff" strokeWidth={3} />
              </pattern>
            ))}
          </defs>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: AXIS_FONT_SIZE }} interval={0} />
          <YAxis tick={{ fontSize: AXIS_FONT_SIZE }} allowDecimals={false} />
          <Legend wrapperStyle={{ fontSize: LEGEND_FONT_SIZE }} />
          {STAGES.map((stage) => (
            <Bar
              key={stage.key}
              dataKey={stage.key}
              name={stage.label}
              fill={`url(#${stage.pattern})`}
              stroke={stage.fill}
              strokeWidth={2}
              isAnimationActive={false}
            >
              <LabelList
                dataKey={stage.key}
                position="top"
                formatter={renderValueLabel}
                style={{ fontSize: VALUE_FONT_SIZE, fontWeight: 700, fill: "#111111" }}
              />
            </Bar>
          ))}
        </BarChart>
      </div>

      {caption ? <p style={{ fontSize: 22, lineHeight: 1.4 }}>{caption}</p> : null}

      {unavailable.length > 0 ? (
        <p style={{ fontSize: 22, lineHeight: 1.4 }} data-testid="exercise-results-unavailable">
          Some counts are {NOT_AVAILABLE}: {unavailable.join("; ")}.
        </p>
      ) : null}

      <div className="max-w-full overflow-x-auto">
        <table data-testid="exercise-results-table" style={{ fontSize: 22, borderCollapse: "collapse" }}>
          <caption style={{ fontSize: 22, textAlign: "left" }}>
            The same counts as a table.
          </caption>
          <thead>
            <tr>
              <th scope="col" className={CELL}>
                Panel
              </th>
              {STAGES.map((stage) => (
                <th key={stage.key} scope="col" className={CELL}>
                  {stage.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {series.map((panel) => (
              <tr key={panel.label}>
                <th scope="row" className={CELL}>
                  {panel.label}
                </th>
                {STAGES.map((stage) => (
                  <td key={stage.key} className={CELL}>
                    {formatHeadCount(panel[stage.key as StageKey])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/** M2 B6: room around every number, read from the left like the labels. */
const CELL = "px-3 py-1 text-left";

/**
 * The exercise variant's series (DESIGN.md §3.3). Colours are `--ce-*`
 * tokens, so dark mode follows `.dark` without a second table here. Each
 * series also has a non-colour cue: Invited is an open bar, Signed up is
 * hatched at 45°, Attended is solid — and every bar carries its number.
 */
const EXERCISE_STAGES = [
  {
    key: "invited",
    label: "Invited",
    fill: "var(--ce-chart-invited-fill)",
    stroke: "var(--ce-chart-invited-stroke)",
    hatch: false,
  },
  {
    key: "signedUp",
    label: "Signed up",
    fill: "var(--ce-chart-signed-fill)",
    stroke: "var(--ce-chart-signed-stroke)",
    hatch: true,
  },
  {
    key: "attended",
    label: "Attended",
    fill: "var(--ce-chart-attended)",
    stroke: "var(--ce-chart-attended)",
    hatch: false,
  },
] as const;

function ExerciseVariant({
  series,
  title,
  caption,
  headingId,
  patternPrefix,
  horizontal,
}: {
  readonly series: readonly ExerciseResultsSeries[];
  readonly title: string;
  readonly caption: string | undefined;
  readonly headingId: string;
  readonly patternPrefix: string;
  readonly horizontal: boolean;
}): JSX.Element {
  const rows = series.map((panel) => ({
    label: panel.label,
    invited: panel.invited,
    signedUp: panel.signedUp,
    attended: panel.attended,
  }));
  const unavailable = series.flatMap((panel) =>
    STAGES.filter((stage) => typeof panel[stage.key as StageKey] !== "number").map(
      (stage) => `${panel.label}: ${stage.label.toLowerCase()} ${NOT_AVAILABLE}`,
    ),
  );
  const patternId = (key: string): string => `${patternPrefix}-ce-${key}`;
  const tick = { fontSize: 18, fill: "var(--ce-ink)" };
  const width = horizontal ? 340 : Math.max(760, Math.min(1040, series.length * 360));
  const height = horizontal ? 150 * series.length + 40 : 420;

  return (
    <section data-testid="exercise-results-chart" data-variant="exercise" className="min-w-0 max-w-full">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3 border-b border-ce-line pb-4">
        <h2 id={headingId} className="ce-h2 text-ce-ink">
          {title}
        </h2>
        <ul className="ce-meta flex flex-wrap gap-4 text-ce-ink" aria-label="Key">
          {EXERCISE_STAGES.map((stage) => (
            <li key={stage.key} className="flex items-center gap-2">
              <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16">
                <rect
                  x="1"
                  y="1"
                  width="14"
                  height="14"
                  rx="2"
                  fill={`url(#${patternId(stage.key)})`}
                  stroke={stage.stroke}
                  strokeWidth="2"
                />
              </svg>
              {stage.label}
            </li>
          ))}
        </ul>
      </div>

      {/* The chart is drawn at a fixed width; on a narrow window it scrolls in
          this box instead of widening the page, and the table repeats every
          count. Focusable and named so a keyboard can scroll it. */}
      <div
        className="ce-scroll max-w-full overflow-x-auto"
        data-testid="exercise-results-chart-scroll"
        tabIndex={0}
        role="region"
        aria-label="Results chart. Scroll sideways to see all of it."
      >
        <BarChart
          width={width}
          height={height}
          data={rows}
          layout={horizontal ? "vertical" : "horizontal"}
          role="img"
          aria-labelledby={headingId}
          barCategoryGap={horizontal ? "18%" : "22%"}
          margin={{ top: 32, right: horizontal ? 48 : 16, bottom: 8, left: horizontal ? 8 : 0 }}
        >
          <defs>
            {EXERCISE_STAGES.map((stage) => (
              <pattern
                key={stage.key}
                id={patternId(stage.key)}
                patternUnits="userSpaceOnUse"
                width={10}
                height={10}
                patternTransform={stage.hatch ? "rotate(45)" : undefined}
              >
                <rect width={10} height={10} fill={stage.fill} />
                {stage.hatch ? (
                  <line x1={0} y1={0} x2={0} y2={10} stroke={stage.stroke} strokeWidth={3} />
                ) : null}
              </pattern>
            ))}
          </defs>
          <CartesianGrid
            stroke="var(--ce-line)"
            vertical={horizontal}
            horizontal={!horizontal}
          />
          {horizontal ? (
            <>
              <XAxis type="number" tick={tick} allowDecimals={false} stroke="var(--ce-line-strong)" />
              <YAxis
                type="category"
                dataKey="label"
                tick={tick}
                width={120}
                interval={0}
                stroke="var(--ce-line-strong)"
              />
            </>
          ) : (
            <>
              <XAxis dataKey="label" tick={tick} interval={0} stroke="var(--ce-line-strong)" />
              <YAxis tick={tick} allowDecimals={false} stroke="var(--ce-line-strong)" />
            </>
          )}
          {EXERCISE_STAGES.map((stage) => (
            <Bar
              key={stage.key}
              dataKey={stage.key}
              name={stage.label}
              fill={`url(#${patternId(stage.key)})`}
              stroke={stage.stroke}
              strokeWidth={2}
              radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]}
              // The chart keeps no animation: the seat chart carries the
              // results moment (DESIGN.md §5 rules).
              isAnimationActive={false}
            >
              <LabelList
                dataKey={stage.key}
                position={horizontal ? "right" : "top"}
                formatter={renderValueLabel}
                style={{ fontSize: 22, fontWeight: 700, fill: "var(--ce-ink)" }}
              />
            </Bar>
          ))}
        </BarChart>
      </div>

      {caption ? <p className="ce-meta mt-3 text-ce-muted">{caption}</p> : null}

      {unavailable.length > 0 ? (
        <p className="ce-body mt-2 text-ce-ink" data-testid="exercise-results-unavailable">
          Some counts are {NOT_AVAILABLE}: {unavailable.join("; ")}.
        </p>
      ) : null}

      <details className="mt-4 border-t border-ce-line pt-3" open={horizontal}>
        <summary className="ce-btn ce-btn-quiet min-h-11 cursor-pointer justify-start">
          Show these counts as a table
        </summary>
        <div className="ce-scroll mt-2 max-w-full overflow-x-auto">
          <table data-testid="exercise-results-table" className="ce-body ce-num w-full border-collapse">
            <caption className="sr-only">The same counts as a table.</caption>
            <thead>
              <tr className="ce-label bg-ce-sunk text-ce-ink">
                <th scope="col" className={CELL}>
                  Panel
                </th>
                {STAGES.map((stage) => (
                  <th key={stage.key} scope="col" className={CELL}>
                    {stage.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {series.map((panel) => (
                <tr key={panel.label} className="border-b border-ce-line">
                  <th scope="row" className={`${CELL} font-normal`}>
                    {panel.label}
                  </th>
                  {STAGES.map((stage) => (
                    <td key={stage.key} className={CELL}>
                      {formatHeadCount(panel[stage.key as StageKey])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}

export default ExerciseResultsChart;
