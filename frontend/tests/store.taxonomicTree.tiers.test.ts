/** RED contract tests for the taxonomic tree store's per-tier cache.

The store gains two new map slices and a ``loadMore`` action:

- ``nextTiersByParentId`` — ``Map<parentId, TreeNodeTier[]>`` seeded
  from the ``next_tiers`` envelope of the direct-children fetch.
- ``tierRowsByKey`` — ``Map<key, {rows, nextCursor}>`` carrying the
  paginated rows for each ``(parentId, rank)`` pair. Keyed by
  ``"${parentId}:${rank}"`` so a parent's tier rows never collide.
- ``loadMore(parentId, rank)`` — calls ``fetchTierPage`` with the
  current cursor, appends rows to the key, and updates the cursor.

The four behaviours pinned here:

1. The children envelope seeds ``nextTiersByParentId``.
2. ``loadMore`` fetches the first page when the key is missing.
3. ``loadMore`` appends rows on subsequent calls (cursor advances).
4. ``setIncludeExtinct(true→false)`` nukes both caches so the next
   refetch rebuilds them with the new flag.

The tests use the existing zustand store factory so we exercise the
real ``set``/``get`` path the components consume.
*/

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useTaxonomicTree } from "../src/store/taxonomicTree";
import type { TreeNodeResponse } from "../src/api";

const ANIMALIA: TreeNodeResponse = {
  id: 5,
  name: "Animalia",
  display_name: "Animalia",
  rank: "kingdom",
  parent_id: 0,
  is_synonym: false,
  is_extinct: false,
  is_uncertain: false,
  is_unassigned: false,
  has_children: true,
  species_count: 1_500_000,
  authorship: "",
};

const PHYLUM_ARTHROPODA: TreeNodeResponse = {
  id: 100,
  name: "Arthropoda",
  display_name: "Arthropoda",
  rank: "phylum",
  parent_id: 5,
  is_synonym: false,
  is_extinct: false,
  is_uncertain: false,
  is_unassigned: false,
  has_children: true,
  species_count: 1_000_000,
  authorship: "",
};

const PHYLUM_MOLLUSCA: TreeNodeResponse = {
  id: 101,
  name: "Mollusca",
  display_name: "Mollusca",
  rank: "phylum",
  parent_id: 5,
  is_synonym: false,
  is_extinct: false,
  is_uncertain: false,
  is_unassigned: false,
  has_children: true,
  species_count: 80_000,
  authorship: "",
};

const FIRST_TIER = {
  rank: "phylum",
  label: "Phylum",
  examples: ["Arthropoda", "Mollusca", "Chordata"],
  children: [PHYLUM_ARTHROPODA],
  next_cursor: "cursor-1",
};

const SECOND_PAGE = {
  children: [PHYLUM_MOLLUSCA],
  next_cursor: null,
};

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
  // Reset the store between tests so each scenario starts from the
  // documented default state. Use a generic ``setState`` so the
  // shape of new fields (nextTiersByParentId, tierRowsByKey) can
  // grow without the test fixture changing.
  useTaxonomicTree.setState({
    childrenByParentId: new Map(),
    expandedIds: new Set(),
    rootIds: null,
    loadingParentIds: new Set(),
    errorByParentId: new Map(),
    includeExtinct: true,
    // ``nextTiersByParentId`` and ``tierRowsByKey`` are added
    // by the GREEN step; force a fresh ``Map`` via the surrounding
    // state reset that the production store will own.
    nextTiersByParentId: new Map(),
    tierRowsByKey: new Map(),
  } as Partial<ReturnType<typeof useTaxonomicTree.getState>>);
});

describe("taxonomic tree store — tier cache", () => {
  it("seeds nextTiersByParentId from the children envelope", async () => {
    globalThis.fetch = vi.fn().mockResolvedValueOnce(
      mockFetchJson({
        parent: { ...ANIMALIA, parent_id: null },
        children: [ANIMALIA],
        next_tiers: [FIRST_TIER],
        next_cursor: null,
      }),
    ) as unknown as typeof fetch;

    await useTaxonomicTree.getState().ensureChildren(5);

    const cached = useTaxonomicTree.getState().nextTiersByParentId.get(5);
    expect(cached).toBeDefined();
    expect(cached).toHaveLength(1);
    expect(cached?.[0]?.rank).toBe("phylum");
    expect(cached?.[0]?.next_cursor).toBe("cursor-1");
  });

  it("loadMore fetches the first page when tierRowsByKey is missing", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      mockFetchJson(SECOND_PAGE),
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await useTaxonomicTree.getState().loadMore(5, "phylum");

    const cached = useTaxonomicTree.getState().tierRowsByKey.get("5:phylum");
    expect(cached).toBeDefined();
    expect(cached?.rows).toHaveLength(1);
    expect(cached?.rows[0]?.name).toBe("Mollusca");
    expect(cached?.nextCursor).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const url = (fetchMock.mock.calls[0] as [string])[0];
    expect(url).toBe(
      "/api/tree/children?parent_id=5&tier=phylum&cursor=&tier_limit=50&limit=200",
    );
  });

  it("loadMore appends rows on a subsequent call and passes the prior cursor", async () => {
    // Seed the cache with one row + a non-null cursor so the next
    // call must advance.
    useTaxonomicTree.setState({
      tierRowsByKey: new Map([
        [
          "5:phylum",
          {
            rows: [PHYLUM_ARTHROPODA],
            nextCursor: "cursor-1",
          },
        ],
      ]),
    });

    const fetchMock = vi.fn().mockResolvedValueOnce(
      mockFetchJson(SECOND_PAGE),
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await useTaxonomicTree.getState().loadMore(5, "phylum");

    const cached = useTaxonomicTree.getState().tierRowsByKey.get("5:phylum");
    expect(cached?.rows).toHaveLength(2);
    expect(cached?.rows.map((r) => r.name)).toEqual(["Arthropoda", "Mollusca"]);
    expect(cached?.nextCursor).toBeNull();

    const url = (fetchMock.mock.calls[0] as [string])[0];
    expect(url).toBe(
      "/api/tree/children?parent_id=5&tier=phylum&cursor=cursor-1&tier_limit=50&limit=200",
    );
  });

  it("setIncludeExtinct nukes nextTiersByParentId and tierRowsByKey", async () => {
    // Seed both new caches + a base childrenByParentId so the test
    // proves the nuke covers the new maps AND preserves the
    // children-by-parent discipline the existing tests rely on.
    useTaxonomicTree.setState({
      nextTiersByParentId: new Map([[5, [FIRST_TIER]]]),
      tierRowsByKey: new Map([
        ["5:phylum", { rows: [PHYLUM_ARTHROPODA], nextCursor: null }],
      ]),
      childrenByParentId: new Map([[5, [ANIMALIA]]]),
    });

    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: { ...ANIMALIA, parent_id: null },
          children: [ANIMALIA],
          next_tiers: null,
          next_cursor: null,
        }),
      ) as unknown as typeof fetch;

    await useTaxonomicTree.getState().setIncludeExtinct(false);

    const state = useTaxonomicTree.getState();
    expect(state.nextTiersByParentId.size).toBe(0);
    expect(state.tierRowsByKey.size).toBe(0);
    expect(state.childrenByParentId.size).toBe(0);
    expect(state.includeExtinct).toBe(false);
  });
});
