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
 * ## Readable at classroom distance, and not by colour alone
 *
 * Large type throughout; every bar carries its value as a direct label, so
 * nobody reads a number off an axis from the back of the room; each stage has
 * both a distinct high-contrast fill and a distinct hatch pattern; and the
 * whole chart is repeated as a real `<table>` for screen readers and for
 * anyone the colours fail.
 */
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
}: ExerciseResultsChartProps): JSX.Element {
  if (!hasDrawableCounts(series)) {
    return (
      <section aria-label={title} data-testid="exercise-results-chart-empty">
        <h2 style={{ fontSize: 30, margin: "0 0 12px" }}>{title}</h2>
        <p style={{ fontSize: 24, lineHeight: 1.4 }}>{emptyMessage}</p>
      </section>
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
    <section aria-label={title} data-testid="exercise-results-chart">
      <h2 style={{ fontSize: 30, margin: "0 0 12px" }}>{title}</h2>

      <BarChart
        width={880}
        height={460}
        data={rows}
        role="img"
        aria-label={title}
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

      {caption ? <p style={{ fontSize: 22, lineHeight: 1.4 }}>{caption}</p> : null}

      {unavailable.length > 0 ? (
        <p style={{ fontSize: 22, lineHeight: 1.4 }} data-testid="exercise-results-unavailable">
          Some counts are {NOT_AVAILABLE}: {unavailable.join("; ")}.
        </p>
      ) : null}

      <table data-testid="exercise-results-table" style={{ fontSize: 22, borderCollapse: "collapse" }}>
        <caption style={{ fontSize: 22, textAlign: "left" }}>
          {title} — the same counts as a table.
        </caption>
        <thead>
          <tr>
            <th scope="col">Panel</th>
            {STAGES.map((stage) => (
              <th key={stage.key} scope="col">
                {stage.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {series.map((panel) => (
            <tr key={panel.label}>
              <th scope="row">{panel.label}</th>
              {STAGES.map((stage) => (
                <td key={stage.key}>{formatHeadCount(panel[stage.key as StageKey])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export default ExerciseResultsChart;
