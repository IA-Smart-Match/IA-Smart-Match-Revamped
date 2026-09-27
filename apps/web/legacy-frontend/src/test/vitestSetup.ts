/**
 * Component-test environment gaps jsdom leaves open.
 *
 * `ResizeObserver`: Radix Slider (the exercise's weight slider, DESIGN.md
 * §6.6) measures its thumb with one, and jsdom ships none. Added only when
 * missing, as a no-op — tests assert values and roles, never layout.
 */
if (typeof globalThis.ResizeObserver === "undefined") {
  class ResizeObserverStub {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;
}
