/** RED contract tests for the App's breadcrumb-links panel.

The panel renders when a ``path:change`` CustomEvent fires with a
non-empty path. The App mounts an effect keyed by the cascade
path that calls ``fetchTaxonLinks`` and renders the 13 links.

The race contract: when two ``path:change`` events fire
back-to-back BEFORE the first fetch resolves, only the second
fetch survives. The first is aborted by an ``AbortController``
on the panel.

These tests pin the contract for the TaxonomicTree (PR 3) which
replaces the Cascade.
*/

import { act, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/App";
import { useCascadePath } from "../src/store/cascadePath";
import { useTaxonomicTree } from "../src/store/taxonomicTree";

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
  has_children: true,
  species_count: 86_602,
  authorship: "Bateson, 1885",
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
  // Reset the global cascade path + tree state so each test
  // starts from a clean slate. Without this, the Zustand
  // stores bleed state across tests.
  useCascadePath.setState({ path: [] });
  useTaxonomicTree.setState({
    childrenByParentId: new Map(),
    expandedIds: new Set(),
    rootIds: null,
    loadingParentIds: new Set(),
    errorByParentId: new Map(),
  });
});

function dispatchPathChange(path: string[]): void {
  act(() => {
    window.dispatchEvent(
      new CustomEvent(PATH_CHANGE_EVENT, { detail: { path } }),
    );
  });
}

describe("App — breadcrumb-links panel (TaxonomicTree PR 3)", () => {
  it("renders 13 links when the user expands a tree row", async () => {
    // The TaxonomicTree calls /api/tree/children?parent_id=0 on
    // mount and /api/tree/children?parent_id=N on each expand.
    // The App's breadcrumb-links panel fires on the path:change
    // event the tree emits on every expand.
    const fetchMock = vi.fn().mockImplementation((url: string | URL) => {
      const urlStr = typeof url === "string" ? url : url.toString();
      if (urlStr.includes("parent_id=0")) {
        return Promise.resolve(
          mockFetchJson({
            parent: { id: 0 },
            children: [
              {
                id: 10,
                name: "Animalia",
                display_name: "Animalia Linnaeus, 1758",
                rank: "kingdom",
                parent_id: 0,
                is_synonym: false,
                is_extinct: false,
                is_uncertain: false,
                is_unassigned: false,
                has_children: true,
                species_count: 1_792_173,
                authorship: "Linnaeus, 1758",
              },
              {
                id: 20,
                name: "Chordata",
                display_name: "Chordata Bateson, 1885",
                rank: "phylum",
                parent_id: 10,
                is_synonym: false,
                is_extinct: false,
                is_uncertain: false,
                is_unassigned: false,
                has_children: true,
                species_count: 86_602,
                authorship: "Bateson, 1885",
              },
            ],
            next_cursor: null,
          }),
        );
      }
      return Promise.resolve(
        mockFetchJson({ taxon: CHORDATA_TAXON, links: LINKS_13 }),
      );
    });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    render(<App />);

    // The TaxonomicTree fires path:change when the tree
    // payload is rendered. Dispatch it directly to bypass the
    // user-interaction step and feed the panel.
    dispatchPathChange(["Chordata"]);

    // Wait for the cascadePath store to reflect the dispatch
    // before checking the panel — the App's listener writes
    // through the store, and the panel's effect is keyed on the
    // store reference.
    await waitFor(() => {
      expect(useCascadePath.getState().path).toEqual(["Chordata"]);
    });

    await waitFor(() => {
      const dispatchSection = screen.getByRole("region", {
        name: /search source dispatch/i,
      });
      const items = within(dispatchSection).getAllByRole("listitem");
      expect(items).toHaveLength(13);
    });

    const taxonLinksCall = fetchMock.mock.calls.find((call) =>
      (call[0] as string).includes("taxon-links"),
    );
    expect(taxonLinksCall).toBeDefined();
    expect(taxonLinksCall![0]).toBe("/api/Chordata/taxon-links");
  });

  it("aborts the first fetch when a second path:change arrives before the first resolves", async () => {
    let resolveFirst: ((value: Response) => void) | null = null;
    let resolveSecond: ((value: Response) => void) | null = null;

    const fetchMock = vi.fn().mockImplementation(
      (input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("parent_id=0")) {
          return Promise.resolve(
            mockFetchJson({
              parent: { id: 0 },
              children: [
                {
                  id: 10,
                  name: "Animalia",
                  display_name: "Animalia Linnaeus, 1758",
                  rank: "kingdom",
                  parent_id: 0,
                  is_synonym: false,
                  is_extinct: false,
                  is_uncertain: false,
                  is_unassigned: false,
                  has_children: true,
                  species_count: 1_792_173,
                  authorship: "Linnaeus, 1758",
                },
                {
                  id: 20,
                  name: "Chordata",
                  display_name: "Chordata Bateson, 1885",
                  rank: "phylum",
                  parent_id: 10,
                  is_synonym: false,
                  is_extinct: false,
                  is_uncertain: false,
                  is_unassigned: false,
                  has_children: true,
                  species_count: 86_602,
                  authorship: "Bateson, 1885",
                },
              ],
              next_cursor: null,
            }),
          );
        }
        if (url.includes("Chordata")) {
          return new Promise<Response>((res) => {
            resolveFirst = res;
          });
        }
        return new Promise<Response>((res) => {
          resolveSecond = () =>
            res(
              mockFetchJson({
                taxon: {
                  id: 10,
                  name: "Animalia",
                  display_name: "Animalia Linnaeus, 1758",
                  rank: "kingdom",
                  parent_id: 0,
                  is_synonym: false,
                  is_extinct: false,
                  is_uncertain: false,
                  is_unassigned: false,
                  has_children: true,
                  species_count: 1_792_173,
                  authorship: "Linnaeus, 1758",
                },
                links: LINKS_13,
              }),
            );
        });
      },
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    render(<App />);

    // 1) First path:change — starts the Chordata fetch.
    dispatchPathChange(["Chordata"]);
    await waitFor(() => {
      const taxonLinksCalls = fetchMock.mock.calls.filter((call) =>
        (call[0] as string).includes("taxon-links"),
      );
      expect(taxonLinksCalls.length).toBe(1);
    });

    // 2) Second path:change — should abort the first and start a
    //    fresh fetch for ["Animalia"].
    dispatchPathChange(["Animalia"]);
    await waitFor(() => {
      const taxonLinksCalls = fetchMock.mock.calls.filter((call) =>
        (call[0] as string).includes("taxon-links"),
      );
      expect(taxonLinksCalls.length).toBe(2);
    });

    // Resolve the first fetch with an abort so any pending
    // .then() handlers do not leak warnings.
    await act(async () => {
      resolveFirst?.(new Response(null, { status: 499 }));
      await Promise.resolve();
    });

    // Resolve the second fetch so the panel renders.
    await act(async () => {
      resolveSecond?.(
        new Response(
          JSON.stringify({
            taxon: {
              id: 10,
              name: "Animalia",
              display_name: "Animalia Linnaeus, 1758",
              rank: "kingdom",
              parent_id: 0,
              is_synonym: false,
              is_extinct: false,
              is_uncertain: false,
              is_unassigned: false,
              has_children: true,
              species_count: 1_792_173,
              authorship: "Linnaeus, 1758",
            },
            links: LINKS_13,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    });

    await waitFor(() => {
      const dispatchSection = screen.getByRole("region", {
        name: /search source dispatch/i,
      });
      const items = within(dispatchSection).getAllByRole("listitem");
      expect(items).toHaveLength(13);
    });
  });
});
