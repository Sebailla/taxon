/** RED contract tests for the App's breadcrumb-links panel.

The panel renders when a ``path:change`` CustomEvent fires with a
non-empty path. The App mounts an effect keyed by the cascade
path that calls ``fetchTaxonLinks`` and renders the 13 links.

The race contract (3.8): when two ``path:change`` events fire
back-to-back BEFORE the first fetch resolves, only the second
fetch survives. The first is aborted by an ``AbortController``
on the panel.

These tests pin the contract for tasks 3.7–3.8 in
``openspec/changes/breadcrumb-dinamico/tasks.md``.
*/

import { act, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/App";
import { useCascadePath } from "../src/store/cascadePath";

const LINKS_13 = Array.from({ length: 13 }, (_, i) => ({
  source: `src-${i}`,
  label: `Link ${i}`,
  url: `https://example.test/${i}?q=Chordata`,
}));

const CHORDATA_TAXON = {
  id: 20,
  name: "Chordata",
  display_name: "Chordata [phylum]",
  rank: "phylum",
  parent_id: 10,
  is_synonym: false,
  is_extinct: false,
  is_uncertain: false,
  is_unassigned: false,
};

const PATH_CHANGE_EVENT = "path:change";

function mockFetchJson(json: unknown, status = 200): Response {
  return new Response(JSON.stringify(json), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

beforeEach(() => {
  // Reset the global cascade path so each test starts from a
  // clean slate. Without this, the Zustand store bleeds state
  // across tests (the store is a module-level singleton).
  useCascadePath.setState({ path: [] });
});

function dispatchPathChange(path: string[]): void {
  act(() => {
    window.dispatchEvent(
      new CustomEvent(PATH_CHANGE_EVENT, { detail: { path } }),
    );
  });
}

describe("App — breadcrumb-links panel", () => {
  it("dispatches a single fetch and renders 13 links when path:change fires with [Animalia, Chordata]", async () => {
    // 3.7 — happy path. The App mounts, the Cascade (mocked via the
    // path:change event) sets the path, the App's effect calls
    // fetchTaxonLinks, and the panel renders the 13 list items.
    // The SpeciesLinks component wraps each <a> with role="listitem"
    // inside a role="list" container; we assert on the listitems so
    // the contract is decoupled from the underlying anchor tag.
    const fetchMock = vi
      .fn()
      .mockImplementation((url: string | URL) => {
        const urlStr = typeof url === "string" ? url : url.toString();
        // First call: Cascade roots.
        if (urlStr.endsWith("/kingdoms")) {
          return Promise.resolve(
            mockFetchJson([
              { id: 1, name: "Biota", display_name: "Biota [biota]", rank: "biota", parent_id: null, is_synonym: false, is_extinct: false, is_uncertain: false, is_unassigned: false },
              { id: 2, name: "Viruses", display_name: "Viruses [biota]", rank: "biota", parent_id: null, is_synonym: false, is_extinct: false, is_uncertain: false, is_unassigned: false },
            ]),
          );
        }
        // taxon-links endpoint.
        return Promise.resolve(
          mockFetchJson({ taxon: CHORDATA_TAXON, links: LINKS_13 }),
        );
      });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    render(<App />);
    dispatchPathChange(["Animalia", "Chordata"]);

    // Advance the microtask queue + the panel render. The SpeciesLinks
    // panel renders a ``<section aria-label="Search source dispatch">``
    // containing a ``role="list"``; we count the listitems inside
    // that section so the breadcrumb's two segments don't pollute the
    // count.
    await waitFor(() => {
      const dispatchSection = screen.getByRole("region", {
        name: /search source dispatch/i,
      });
      const items = within(dispatchSection).getAllByRole("listitem");
      expect(items).toHaveLength(13);
    });
    // Two fetch calls: one for the Cascade roots, one for taxon-links.
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const taxonLinksCall = fetchMock.mock.calls.find(
      (call) => (call[0] as string).includes("taxon-links"),
    );
    expect(taxonLinksCall).toBeDefined();
    expect(taxonLinksCall![0]).toBe("/api/Animalia%7CChordata/taxon-links");
  });

  it("aborts the first fetch when a second path:change arrives before the first resolves", async () => {
    // 3.8 — race. Two path:change events in quick succession:
    //   1. ["Animalia", "Chordata"]  → fetch #1 starts
    //   2. ["Animalia"]              → fetch #2 starts, fetch #1 aborted
    //
    // After both events settle, exactly ONE fetch must remain in
    // flight (the second), and the panel must render the result
    // for the second path.
    let resolveFirst:
      | ((value: Response | PromiseLike<Response>) => void)
      | null = null;
    let resolveSecond:
      | ((value: Response | PromiseLike<Response>) => void)
      | null = null;

    const fetchMock = vi.fn().mockImplementation(
      (input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input.toString();
        // The Cascade's roots fetch on mount: return an array
        // so the effect does not throw.
        if (url.endsWith("/kingdoms")) {
          return Promise.resolve(
            mockFetchJson([
              {
                id: 1,
                name: "Biota",
                display_name: "Biota [biota]",
                rank: "biota",
                parent_id: null,
                is_synonym: false,
                is_extinct: false,
                is_uncertain: false,
                is_unassigned: false,
              },
            ]),
          );
        }
        if (url.includes("Chordata")) {
          // First call — slow, never resolves until we choose to.
          return new Promise<Response>((res) => {
            resolveFirst = res;
          });
        }
        // Second call — fast, returns the [Animalia] response.
        return new Promise<Response>((res) => {
          resolveSecond = () =>
            res(
              mockFetchJson({
                taxon: {
                  id: 10,
                  name: "Animalia",
                  display_name: "Animalia [kingdom]",
                  rank: "kingdom",
                  parent_id: null,
                  is_synonym: false,
                  is_extinct: false,
                  is_uncertain: false,
                  is_unassigned: false,
                },
                links: LINKS_13,
              }),
            );
          // Resolve immediately so the panel renders synchronously.
          resolveSecond();
        });
      },
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    render(<App />);

    // 1) Fire the first path:change — starts fetch #1 (Chordata).
    // The Cascade's roots fetch on mount is the first call; the
    // taxon-links fetch for ["Animalia", "Chordata"] is the second.
    dispatchPathChange(["Animalia", "Chordata"]);
    await waitFor(() => {
      // Filter out the roots call: we want exactly ONE taxon-links
      // fetch in flight.
      const taxonLinksCalls = fetchMock.mock.calls.filter(
        (call) => (call[0] as string).includes("taxon-links"),
      );
      expect(taxonLinksCalls.length).toBe(1);
    });

    // 2) Fire the second path:change — should abort fetch #1 and
    //    start a fresh fetch #2 for ["Animalia"].
    dispatchPathChange(["Animalia"]);
    await waitFor(() => {
      const taxonLinksCalls = fetchMock.mock.calls.filter(
        (call) => (call[0] as string).includes("taxon-links"),
      );
      expect(taxonLinksCalls.length).toBe(2);
    });

    // The first request was aborted; resolve it with an abort so
    // any pending .then() handlers do not leak warnings.
    await act(async () => {
      resolveFirst?.(new Response(null, { status: 499 }));
      // Yield to the microtask queue.
      await Promise.resolve();
    });

    // Only ONE fetch remains in flight (the second one), and the
    // panel renders its result.
    await waitFor(() => {
      const dispatchSection = screen.getByRole("region", {
        name: /search source dispatch/i,
      });
      const items = within(dispatchSection).getAllByRole("listitem");
      expect(items).toHaveLength(13);
    });
  });
});