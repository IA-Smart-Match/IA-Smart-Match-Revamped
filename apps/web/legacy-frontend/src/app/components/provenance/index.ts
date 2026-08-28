/**
 * Barrel for the accountable-number primitives (ADR-0011) and the
 * provenance taxonomy (`apps/web/DESIGN.md` §1.1).
 *
 * One import site for the later page pass:
 *
 *   import {
 *     AccountableValue,
 *     MetricValueDisplay,
 *     ProvenanceDisclosure,
 *     SyntheticDataBanner,
 *     knownValue, atLeastValue, unknownValue,
 *     type AccountableMetric, type MetricValue, type Provenance,
 *   } from "@/app/components/provenance";
 */

export type {
  AccountableMetric,
  AtLeastMetricValue,
  DrilldownRef,
  KnownMetricValue,
  MetricValue,
  MetricValueKind,
  Provenance,
  UnknownMetricValue,
} from "./types";

export {
  PROVENANCE_DESCRIPTIONS,
  PROVENANCE_LABELS,
  atLeastValue,
  isAtLeast,
  isKnown,
  isUnknown,
  knownValue,
  unknownValue,
} from "./types";

export {
  MetricValueDisplay,
  type MetricValueDisplayProps,
} from "./MetricValueDisplay";

export {
  MetricDrilldownTrigger,
  type MetricDrilldownTriggerProps,
  ProvenanceBadge,
  type ProvenanceBadgeProps,
  ProvenanceDisclosure,
  type ProvenanceDisclosureProps,
} from "./ProvenanceDisclosure";

export {
  SyntheticDataBadge,
  type SyntheticDataBadgeProps,
  SyntheticDataBanner,
  type SyntheticDataBannerProps,
} from "./SyntheticDataMarker";

export {
  AccountableValue,
  type AccountableValueProps,
} from "./AccountableValue";
