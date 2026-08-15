/** RED contract tests for the ``cascadePath`` Zustand store.

The store is the single source of truth for the cascade path
across the App: ``Breadcrumb.onSelect`` writes via ``setPath``,
the App's panel effect reads via the subscriber. Without a
store the path only flows through DOM events, which makes the
panel race-prone (events fire before listeners mount).

The store API mirrors the spec:

- ``path``: ``string[]`` — the dense cascade path.
- ``setPath(p: string[]): void`` — replace the path; subscribers fire.

These tests pin the contract for task 3.4 in
``openspec/changes/breadcrumb-dinamico/tasks.md``.
*/

import { describe, expect, it, beforeEach } from "vitest";

import { useCascadePath } from "../src/store/cascadePath";

describe("cascadePath store", () => {
  beforeEach(() => {
    // Reset to the default so each test starts from a clean path.
    useCascadePath.setState({ path: [] });
  });

  it("defaults to an empty path", () => {
    expect(useCascadePath.getState().path).toEqual([]);
  });

  it("setPath replaces the path; subscribers fire on every change", () => {
    const subscriber = (
      path: string[],
      prev: string[],
    ): void => {
      // Capture each transition for the assertion below.
      subscriberCalls.push({ path: [...path], prev: [...prev] });
    };
    const subscriberCalls: Array<{ path: string[]; prev: string[] }> = [];
    const unsub = useCascadePath.subscribe(
      (state) => state.path,
      (path, prev) => subscriber(path, prev),
    );

    try {
      useCascadePath.getState().setPath(["A"]);
      useCascadePath.getState().setPath(["A", "B"]);
    } finally {
      unsub();
    }

    expect(useCascadePath.getState().path).toEqual(["A", "B"]);
    expect(subscriberCalls).toEqual([
      { path: ["A"], prev: [] },
      { path: ["A", "B"], prev: ["A"] },
    ]);
  });

  it("getState returns the latest path after each setPath call", () => {
    const store = useCascadePath.getState();
    store.setPath(["A"]);
    expect(useCascadePath.getState().path).toEqual(["A"]);
    store.setPath(["A", "B", "C"]);
    expect(useCascadePath.getState().path).toEqual(["A", "B", "C"]);
  });

  it("setPath with the same array reference fires the subscriber only when content changes", () => {
    // The subscriber must not fire on a no-op replace; otherwise the
    // App's effect would re-fetch for the same path on every render.
    let calls = 0;
    const unsub = useCascadePath.subscribe(
      (state) => state.path,
      () => {
        calls += 1;
      },
    );
    try {
      useCascadePath.getState().setPath(["X"]);
      const firstCount = calls;
      useCascadePath.getState().setPath(["X"]); // same content
      expect(calls).toBe(firstCount); // no extra fire
    } finally {
      unsub();
    }
  });
});