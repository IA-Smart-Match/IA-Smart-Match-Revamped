/**
 * The invitation desk: shared class-exercise components, motion and tokens.
 * See README.md in this folder for each export's props and DESIGN.md section.
 *
 * Import from here: `import { Button, Notice } from "./desk";` (from a page in
 * `pages/exercise/`).
 */
export { Button, type ButtonProps, type ButtonVariant } from "./Button";
export { Notice, type NoticeProps, type NoticeTone } from "./Notice";
export {
  Skeleton,
  SkeletonCard,
  SkeletonRankedRows,
  SkeletonRegion,
  type SkeletonProps,
  type SkeletonRegionProps,
} from "./Skeleton";
export { MarkerChip, type MarkerChipProps } from "./MarkerChip";
export { WeightSlider, type WeightRefusal, type WeightSliderProps } from "./WeightSlider";
export {
  WEIGHT_MAX,
  WEIGHT_MIN,
  WEIGHT_PAGE_STEP,
  WEIGHT_STEP,
  clampWeight,
  formatWeight,
  formatWeightTotal,
  strictDecimal,
  weightFieldMessage,
  weightTotal,
} from "./weightValue";
export {
  CE_EASE,
  CE_MOTION_MS,
  CE_SPRING_ROW,
  ceMotion,
  useCountUp,
  usePrefersReducedMotion,
  type CeMotionName,
  type CeMotionProps,
  type CountUpOptions,
} from "./motion";
export {
  CONFIRM_GUARD_MS,
  ConfirmWindowUnderline,
  confirmWindowHelper,
  useConfirmWindow,
  type ConfirmWindow,
  type ConfirmWindowOptions,
  type ConfirmWindowUnderlineProps,
} from "./confirmWindow";
export {
  SEAT_FILL_DONE_MS,
  SEAT_FILL_STEP_MS,
  Seat,
  seatFillPlan,
  useSeatFill,
  type PlannedSeat,
  type SeatFillPlan,
  type SeatFillState,
  type SeatKind,
  type SeatProps,
} from "./seatFill";
export {
  CE_COLORS,
  CE_COLOR_TOKENS,
  contrastRatio,
  type CeColorToken,
  type CePalette,
} from "./tokens";
