/**
 * The loading placeholder, in the finished section's shape.
 *
 * Six card outlines, a funnel-sized block and a two-card rail, so the layout
 * does not jump when the read settles. Nothing here contains a number, not
 * even a greyed-out one: a placeholder digit is a figure a reader can
 * misremember having seen.
 *
 * The pulsing block itself is `components/ui/skeleton.tsx`, the primitive the
 * rest of the app already uses; this file contributes only the arrangement.
 * `motion-reduce:animate-none` is added on top of it here rather than in the
 * shared primitive, which is not this section's to change.
 *
 * `settled` distinguishes the two ways this can be on screen. Before the read
 * returns it is loading. After it returns carrying neither a payload nor an
 * error — a shape the current caller cannot produce, but one a later refactor
 * could — saying "still loading" would be a claim about a request that has
 * already finished, so it says what it actually knows instead.
 */
import { Skeleton } from "@/app/components/ui/skeleton";

/** Placeholder count, matching the six cards the register presents. */
const SKELETON_CARD_COUNT = 6;

export function SpeakerPipelineSkeleton({ settled }: { settled: boolean }) {
  return (
    <div className="mt-6 space-y-4">
      <p className="text-sm text-muted-foreground" role="status" aria-live="polite">
        {settled ? "The speaker pipeline read returned nothing." : "Loading the speaker pipeline…"}
      </p>

      <div
        className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6"
        aria-hidden="true"
      >
        {Array.from({ length: SKELETON_CARD_COUNT }, (_unused, index) => (
          <Skeleton key={index} className="h-28 rounded-2xl motion-reduce:animate-none" />
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3" aria-hidden="true">
        <Skeleton className="h-96 rounded-2xl motion-reduce:animate-none lg:col-span-2" />
        <div className="space-y-4 lg:col-span-1">
          <Skeleton className="h-44 rounded-2xl motion-reduce:animate-none" />
          <Skeleton className="h-48 rounded-2xl motion-reduce:animate-none" />
        </div>
      </div>
    </div>
  );
}
