/**
 * Test helper: a `window.matchMedia` stub that answers
 * `(prefers-reduced-motion: reduce)` as told. jsdom ships no `matchMedia`.
 * Not exported from `desk/index.ts`; tests import it directly.
 */
import { vi } from "vitest";

export function stubReducedMotion(reduce: boolean): void {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: reduce && query.includes("prefers-reduced-motion: reduce"),
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(() => false),
    })),
  );
}
