// vitest-axe must register its custom matcher before the
// testing-library matchers so the global `Vi.Assertion` interface
// is augmented in time.
import "vitest-axe/extend-expect";
import "@testing-library/jest-dom/vitest";

// jsdom does not implement HTMLCanvasElement.getContext. axe-core
// uses canvas to compute colour-contrast ratios; the implementation
// falls back to a no-op stub when the context is unavailable, but
// jsdom prints a noisy warning to stderr for every call. Stub the
// method so the tests run silently.
if (typeof HTMLCanvasElement !== "undefined") {
  HTMLCanvasElement.prototype.getContext = function getContextStub(): null {
    return null;
  };
}