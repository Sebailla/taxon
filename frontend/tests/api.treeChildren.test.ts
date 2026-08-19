/** RED-first contract tests for the new tree endpoints.

The frontend typed client gains two methods that wrap the
backend endpoints shipped in PR 1:

- ``fetchTreeNode(parentId, init?)`` → ``GET /api/tree/children?parent_id=N``
- ``fetchTreeSearch(q, init?)``     → ``GET /api/tree/search?q=…``

The wire envelopes are the same discriminated union the rest of
the client uses:

- 200 → ``{status: 'ok', data}``.
- 404 → ``{status: 'not-found', detail}`` (consumed by the empty
  state and the retry link).
- 422 → ``{status: 'error', detail}`` (the backend rejects a
  missing ``parent_id`` query param; the UI surfaces the server
  message in the retry row).
- 5xx / network → ``{status: 'error', detail}``.

The URL builder is exported separately so the test can pin the
exact query-string order without going through ``fetch``.
*/

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildTreeChildrenUrl,
  type TreeChildrenResponse,
  type TreeNodeResponse,
  type TreeSearchResponse,
  fetchTreeNode,
  fetchTreeSearch,
} from "../src/api";

function mockFetchJson(json: unknown, status = 200): Response {
  return new Response(JSON.stringify(json), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockFetchFetchOnce(response: Response): ReturnType<typeof vi.fn> {
  const fn = vi.fn().mockResolvedValueOnce(response);
  globalThis.fetch = fn as unknown as typeof fetch;
  return fn;
}

afterEach(() => {
  vi.restoreAllMocks();
});

const ARCHAEA: TreeNodeResponse = {
  id: 1,
  name: "Archaea",
  display_name: "Archaea Woese et al., 2024",
  rank: "domain",
  parent_id: null,
  is_synonym: false,
  is_extinct: false,
  is_uncertain: false,
  is_unassigned: false,
  has_children: true,
  species_count: 927,
  authorship: "Woese et al., 2024",
};

const BACTERIA: TreeNodeResponse = {
  id: 2,
  name: "Bacteria",
  display_name: "Bacteria Woese et al., 2024",
  rank: "domain",
  parent_id: null,
  is_synonym: false,
  is_extinct: false,
  is_uncertain: false,
  is_unassigned: false,
  has_children: true,
  species_count: 25000,
  authorship: "Woese et al., 2024",
};

const EUKARYOTA: TreeNodeResponse = {
  id: 5,
  name: "Eukaryota",
  display_name: "Eukaryota (Chatton, 1925) Whittaker & Margulis, 1978",
  rank: "domain",
  parent_id: null,
  is_synonym: false,
  is_extinct: false,
  is_uncertain: false,
  is_unassigned: false,
  has_children: true,
  species_count: 5_654_308,
  authorship: "(Chatton, 1925) Whittaker & Margulis, 1978",
};

const ROOTS_PAYLOAD: TreeChildrenResponse = {
  parent: {
    id: 0,
    name: "Biota",
    display_name: "Biota",
    rank: "biota",
    parent_id: null,
    is_synonym: false,
    is_extinct: false,
    is_uncertain: false,
    is_unassigned: false,
    has_children: true,
    species_count: 7_500_000,
    authorship: "",
  },
  children: [ARCHAEA, BACTERIA, EUKARYOTA],
  next_tiers: null,
  next_cursor: null,
};

describe("buildTreeChildrenUrl", () => {
  it("encodes the parent_id with the default limit", () => {
    expect(buildTreeChildrenUrl({ parentId: 5 })).toBe(
      "/tree/children?parent_id=5&limit=200",
    );
  });

  it("includes include_extinct when set to false", () => {
    expect(
      buildTreeChildrenUrl({ parentId: 5, includeExtinct: false }),
    ).toBe("/tree/children?parent_id=5&limit=200&include_extinct=false");
  });

  it("omits include_extinct when true (default)", () => {
    expect(
      buildTreeChildrenUrl({ parentId: 5, includeExtinct: true }),
    ).toBe("/tree/children?parent_id=5&limit=200");
  });

  it("honors a custom limit", () => {
    expect(buildTreeChildrenUrl({ parentId: 5, limit: 12 })).toBe(
      "/tree/children?parent_id=5&limit=12",
    );
  });
});

describe("fetchTreeNode", () => {
  it("returns the decoded envelope on 200", async () => {
    mockFetchFetchOnce(mockFetchJson(ROOTS_PAYLOAD));
    const result = await fetchTreeNode(0);
    expect(result.status).toBe("ok");
    if (result.status === "ok") {
      expect(result.data.children).toHaveLength(3);
      expect(result.data.children[0]?.name).toBe("Archaea");
      expect(result.data.children[0]?.has_children).toBe(true);
      expect(result.data.children[0]?.species_count).toBe(927);
      expect(result.data.children[0]?.authorship).toBe("Woese et al., 2024");
    }
  });

  it("hits the right URL with the parent_id query param", async () => {
    const fetchMock = mockFetchFetchOnce(mockFetchJson(ROOTS_PAYLOAD));
    await fetchTreeNode(5);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "/api/tree/children?parent_id=5&limit=200",
    );
  });

  it("forwards include_extinct=false when the caller sets it", async () => {
    const fetchMock = mockFetchFetchOnce(mockFetchJson(ROOTS_PAYLOAD));
    await fetchTreeNode(5, { includeExtinct: false });
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "/api/tree/children?parent_id=5&limit=200&include_extinct=false",
    );
  });

  it("returns not-found on 404", async () => {
    mockFetchFetchOnce(
      mockFetchJson({ detail: "parent not found" }, 404),
    );
    const result = await fetchTreeNode(999_999_999);
    expect(result.status).toBe("not-found");
    if (result.status === "not-found") {
      expect(result.detail).toBe("parent not found");
    }
  });

  it("returns error on 422 with the server detail", async () => {
    mockFetchFetchOnce(
      mockFetchJson({ detail: "missing parent_id" }, 422),
    );
    const result = await fetchTreeNode(0);
    expect(result.status).toBe("error");
    if (result.status === "error") {
      expect(result.detail).toBe("missing parent_id");
    }
  });

  it("returns error on 5xx", async () => {
    mockFetchFetchOnce(
      mockFetchJson({ detail: "internal error" }, 500),
    );
    const result = await fetchTreeNode(5);
    expect(result.status).toBe("error");
    if (result.status === "error") {
      expect(result.detail).toBe("internal error");
    }
  });

  it("returns error on network failure", async () => {
    globalThis.fetch = vi
      .fn()
      .mockRejectedValueOnce(new Error("Failed to fetch")) as unknown as typeof fetch;
    const result = await fetchTreeNode(5);
    expect(result.status).toBe("error");
    if (result.status === "error") {
      expect(result.detail).toBe("Failed to fetch");
    }
  });
});

describe("fetchTreeSearch", () => {
  const SEARCH_PAYLOAD: TreeSearchResponse = {
    items: [EUKARYOTA],
  };

  it("hits the right URL with the q query param", async () => {
    const fetchMock = mockFetchFetchOnce(mockFetchJson(SEARCH_PAYLOAD));
    await fetchTreeSearch("Euk");
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "/api/tree/search?q=Euk&limit=8",
    );
  });

  it("returns the decoded items on 200", async () => {
    mockFetchFetchOnce(mockFetchJson(SEARCH_PAYLOAD));
    const result = await fetchTreeSearch("Euk");
    expect(result.status).toBe("ok");
    if (result.status === "ok") {
      expect(result.data.items).toHaveLength(1);
      expect(result.data.items[0]?.name).toBe("Eukaryota");
    }
  });

  it("returns the empty-state hint when items is empty", async () => {
    mockFetchFetchOnce(mockFetchJson({ items: [] }));
    const result = await fetchTreeSearch("Zzzqxx");
    expect(result.status).toBe("ok");
    if (result.status === "ok") {
      expect(result.data.items).toEqual([]);
    }
  });

  it("returns error on 5xx", async () => {
    mockFetchFetchOnce(
      mockFetchJson({ detail: "search failed" }, 500),
    );
    const result = await fetchTreeSearch("Euk");
    expect(result.status).toBe("error");
  });
});
