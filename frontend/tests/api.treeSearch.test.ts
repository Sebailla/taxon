/** RED-first contract tests for the search-input debounce wrapper.

The "Find taxon" input sits in the TaxonomicTree header and
issues ``GET /api/tree/search?q=…`` on every keystroke. The
spec pins a 200ms debounce:

- Rapid keystrokes (``E``, ``u``, ``k`` in 50ms) collapse into
  ONE request with the final value.
- A pause longer than 200ms between keystrokes issues separate
  requests.

The wrapper is a pure factory — it takes a fetch function and a
delay, returns a debounced function plus a teardown — so the
test can pin the contract without touching React or fake timers.
Vitest's fake timers (``vi.useFakeTimers`` + ``vi.advanceTimersByTime``)
replace the wall clock so the test runs in microseconds, not
200ms.
*/

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createDebouncedSearch } from "../src/api";

describe("createDebouncedSearch", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("collapses 5 rapid keystrokes into a single fetch with the final value", async () => {
    const fetch = vi.fn().mockResolvedValue({
      status: "ok" as const,
      data: { items: [] },
    });
    const debounced = createDebouncedSearch({ fetch, delay: 200 });

    // Five rapid keystrokes (50ms apart). The debounce should
    // collapse them into ONE fetch with the final value ``"r"``
    // -- the wrapper passes through whatever the caller passed
    // last, not a cumulative string. The caller's React handler
    // passes the current input value, so the final value is the
    // verbatim input state at the moment the 200ms window closes.
    debounced("E");
    vi.advanceTimersByTime(50);
    debounced("u");
    vi.advanceTimersByTime(50);
    debounced("k");
    vi.advanceTimersByTime(50);
    debounced("a");
    vi.advanceTimersByTime(50);
    debounced("r");
    // Flush the pending 200ms debounce.
    vi.advanceTimersByTime(200);

    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledWith("r");
  });

  it("issues a separate fetch when a pause exceeds the delay", () => {
    const fetch = vi.fn().mockResolvedValue({
      status: "ok" as const,
      data: { items: [] },
    });
    const debounced = createDebouncedSearch({ fetch, delay: 200 });

    debounced("E");
    vi.advanceTimersByTime(250); // > 200ms
    debounced("u");
    vi.advanceTimersByTime(250);

    expect(fetch).toHaveBeenCalledTimes(2);
    expect(fetch).toHaveBeenNthCalledWith(1, "E");
    expect(fetch).toHaveBeenNthCalledWith(2, "u");
  });

  it("cancels a pending fetch when teardown is called", () => {
    const fetch = vi.fn().mockResolvedValue({
      status: "ok" as const,
      data: { items: [] },
    });
    const debounced = createDebouncedSearch({ fetch, delay: 200 });

    debounced("E");
    debounced.cancel();
    vi.advanceTimersByTime(500);

    expect(fetch).not.toHaveBeenCalled();
  });

  it("returns the latest fetch result to the caller", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce({
        status: "ok" as const,
        data: { items: [{ id: 1, name: "Eukarya" }] },
      })
      .mockResolvedValueOnce({
        status: "ok" as const,
        data: { items: [] },
      });
    const debounced = createDebouncedSearch({ fetch, delay: 200 });

    const first = debounced("Euk");
    vi.advanceTimersByTime(200);
    await expect(first).resolves.toEqual({
      status: "ok",
      data: { items: [{ id: 1, name: "Eukarya" }] },
    });
  });

  it("resolves with the error result when the fetch rejects", async () => {
    const fetch = vi.fn().mockResolvedValue({
      status: "error" as const,
      detail: "search failed",
    });
    const debounced = createDebouncedSearch({ fetch, delay: 200 });

    const pending = debounced("Euk");
    vi.advanceTimersByTime(200);
    await expect(pending).resolves.toEqual({
      status: "error",
      detail: "search failed",
    });
  });
});
