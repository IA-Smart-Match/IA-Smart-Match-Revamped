/**
 * Accountable-number primitives — types.
 *
 * Implements ADR-0011 ("Every user-visible number is accountable"),
 * `docs/architecture/decisions/ADR-0011-accountable-numbers.md`, and the
 * provenance taxonomy in `apps/web/DESIGN.md` §1.1.
 *
 * Why this file exists: ADR-0011 rule 1 ("unknown is not zero") has to
 * survive in the type, not be reconstructed by a render-time convention —
 * "By the time a `0` reaches the render layer the information that
 * distinguishes it from `unknown` is gone." (ADR-0011, Rationale). A
 * `MetricValue` therefore has no branch that lets an absent value collapse
 * into a numeral: it is a discriminated union of exactly three cases, and a
 * consumer that switches on `kind` without handling all three fails to
 * compile — see `assertNeverMetricValue` in `MetricValueDisplay.tsx`.
 */

/** Discriminant for {@link MetricValue}. */
export type MetricValueKind = "known" | "at_least" | "unknown";

/**
 * A precisely known value, computed from a specific, nameable row set.
 * `value` may legitimately be `0` — a real zero is not the defect this
 * module exists to prevent; a `0` standing in for `unknown` is.
 */
export interface KnownMetricValue {
  readonly kind: "known";
  readonly value: number;
}

/**
 * A lower bound: the row set backing this number was truncated (paging, a
 * result cap, a partial scan) before the true count was reached. `value` is
 * real evidence — it is what was actually counted — and the true count is
 * `>= value`. This is distinct from `unknown`: there is a number, it is just
 * not the whole number.
 */
export interface AtLeastMetricValue {
  readonly kind: "at_least";
  readonly value: number;
}

/**
 * No evidence exists to compute this number. ADR-0011 rule 1: this is not
 * `0`, and a render primitive must refuse to coerce it to one. `reason` is
 * shown to the user — "no data yet" and "the source it would come from is
 * unavailable" are different situations and the UI should say which.
 */
export interface UnknownMetricValue {
  readonly kind: "unknown";
  readonly reason: string;
}

/**
 * A metric value is one of: known, at-least (truncated), or unknown (with a
 * reason). Exhaustively narrowable — see `assertNeverMetricValue`.
 */
export type MetricValue =
  | KnownMetricValue
  | AtLeastMetricValue
  | UnknownMetricValue;

/** Constructs a {@link KnownMetricValue}. */
export function knownValue(value: number): KnownMetricValue {
  return { kind: "known", value };
}

/** Constructs an {@link AtLeastMetricValue}. */
export function atLeastValue(value: number): AtLeastMetricValue {
  return { kind: "at_least", value };
}

/** Constructs an {@link UnknownMetricValue}. */
export function unknownValue(reason: string): UnknownMetricValue {
  return { kind: "unknown", reason };
}

/**
 * Provenance taxonomy — `apps/web/DESIGN.md` §1.1. Every value on screen
 * must carry one of these five labels; there is no sixth, unlabeled state.
 */
export type Provenance =
  | "observed"
  | "inferred"
  | "heuristic"
  | "model"
  | "synthetic";

/** Human-facing label for each {@link Provenance}, per DESIGN.md §1.1's table. */
export const PROVENANCE_LABELS: Readonly<Record<Provenance, string>> = {
  observed: "Observed",
  inferred: "Inferred",
  heuristic: "Heuristic score",
  model: "Model output",
  synthetic: "Synthetic / demo",
};

/** One-sentence meaning of each {@link Provenance}, for the disclosure tooltip. */
export const PROVENANCE_DESCRIPTIONS: Readonly<Record<Provenance, string>> = {
  observed: "A recorded fact — someone entered it, or a system captured it.",
  inferred: "Derived from other data by a deterministic rule.",
  heuristic: "A computed score from the factor registry.",
  model: "Produced by a language or embedding model.",
  synthetic: "Fixture data. Not a real record.",
};

/**
 * Points at the exact row set a number was computed from — ADR-0011 rule 4.
 * A drill-down must open these same rows, not a similar-looking re-query;
 * `rowSetDigest` is what a contract test compares against the count the
 * drill-down actually returns (the check that catches Fix #12: a count of
 * 15 opening to 31 rows).
 */
export interface DrilldownRef {
  /** Stable identifier/digest of the row set (ADR-0011 rule 4). */
  readonly rowSetDigest: string;
  /**
   * Row count in that set, when known. For a `known` MetricValue this
   * should equal `value` — a mismatch is the Fix #12 defect surfacing.
   */
  readonly rowCount?: number;
  /**
   * Invoked when the viewer asks to see the rows. Left abstract on purpose:
   * this track builds the affordance, not the fetch or navigation behind
   * it — a later page pass supplies this.
   */
  readonly onOpen: () => void;
  /** Optional human label for the trigger, e.g. "View 15 events". */
  readonly label?: string;
}

/**
 * One registered metric (ADR-0011 rules 2 and 3) as delivered to a
 * component: its value, where it came from, and — when the metric is an
 * aggregate over rows — how to see them.
 */
export interface AccountableMetric {
  /** Canonical registered metric name (ADR-0011 rule 2). Shown, not just stored. */
  readonly name: string;
  /** One-sentence definition of what this metric counts (ADR-0011 rule 2). */
  readonly definition: string;
  readonly value: MetricValue;
  readonly provenance: Provenance;
  /** Present when the metric is an aggregate over rows a viewer can open. */
  readonly drilldown?: DrilldownRef;
}

/** Narrows `value` to {@link KnownMetricValue}. */
export function isKnown(value: MetricValue): value is KnownMetricValue {
  return value.kind === "known";
}

/** Narrows `value` to {@link AtLeastMetricValue}. */
export function isAtLeast(value: MetricValue): value is AtLeastMetricValue {
  return value.kind === "at_least";
}

/** Narrows `value` to {@link UnknownMetricValue}. */
export function isUnknown(value: MetricValue): value is UnknownMetricValue {
  return value.kind === "unknown";
}
