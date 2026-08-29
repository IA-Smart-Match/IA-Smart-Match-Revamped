import { Loader2 } from "lucide-react";

/**
 * Suspense fallback shown while a lazily-loaded route chunk downloads.
 *
 * Intentionally minimal: a neutral loading indicator only. Per ADR-0011,
 * this must never render fabricated content, skeleton numbers, zeroes, or
 * placeholder metrics that could be mistaken for real data.
 */
export function RouteFallback() {
  return (
    <div className="flex min-h-[50vh] w-full items-center justify-center gap-2 py-24 text-sm text-gray-500">
      <Loader2 className="h-4 w-4 animate-spin" />
      <span>Loading…</span>
    </div>
  );
}
