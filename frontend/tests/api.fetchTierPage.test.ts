/** RED contract tests for ``fetchTierPage`` + widened ``TreeChildrenResponse``.

The backend envelope shipped in PR A.1 grows two new fields:

- ``TreeNodeTier`` — one cascade bucket per rank below the parent.
- ``TreeChildrenResponse.next_tiers`` — array of ``TreeNodeTier``.

The frontend client mirrors the addition and gains a new
``fetchTierPage(parentId, tier, cursor, init)`` helper that hits
``/api/tree/children?parent_id=...&tier=...&cursor=...&tier_limit=...``
and returns the single tier page the client asked for. The URL builder
gains two new optional params so the test can pin the exact
query-string order.

Behaviour pinned here:

1. ``buildTreeChildrenUrl`` embeds the tier + cursor params when set.
2. ``fetchTierPage`` issues ``GET`` on the documented URL.
3. ``fetchTierPage`` returns the payload on 200 (``ok`` discriminator).
4. ``fetchTierPage`` honours ``tier_limit`` when supplied.
5. ``fetchTierPage`` returns the ``error`` discriminator on 5xx.
*/

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildTreeChildrenUrl,
  fetchTierPage,
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

describe("buildTreeChildrenUrl — tier params", () => {
  it("embeds tier + cursor when supplied", () => {
    expect(
      buildTreeChildrenUrl({
        parentId: 5,
        tier: "phylum",
        cursor: "cursor-1",
      }),
    ).toBe(
      "/tree/children?parent_id=5&limit=200&tier=phylum&cursor=cursor-1",
    );
  });

  it("omits tier + cursor when not supplied", () => {
    expect(buildTreeChildrenUrl({ parentId: 5 })).toBe(
      "/tree/children?parent_id=5&limit=200",
    );
  });

  it("encodes special characters inside the cursor", () => {
    expect(
      buildTreeChildrenUrl({
        parentId: 5,
        tier: "phylum",
        cursor: "name=äø",
      }),
    ).toBe(
      "/tree/children?parent_id=5&limit=200&tier=phylum&cursor=name%3D%C3%A4%C3%B8",
    );
  });
});

describe("fetchTierPage", () => {
  const TIER_PAGE = {
    parent: {
      id: 5,
      name: "Animalia",
      display_name: "Animalia",
      rank: "kingdom",
      parent_id: 0,
      is_synonym: false,
      is_extinct: false,
      is_uncertain: false,
      is_unassigned: false,
    },
    children: [
      {
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
      },
    ],
    next_tiers: null,
    next_cursor: "next-cursor",
  };

  it("hits the documented URL on the first call", async () => {
    const fetchMock = mockFetchFetchOnce(mockFetchJson(TIER_PAGE));
    await fetchTierPage(5, "phylum", null);
    const url = (fetchMock.mock.calls[0] as [string])[0];
    expect(url).toBe(
      "/api/tree/children?parent_id=5&limit=200&tier=phylum&cursor=&tier_limit=50",
    );
  });

  it("returns the decoded payload on 200", async () => {
    mockFetchFetchOnce(mockFetchJson(TIER_PAGE));
    const result = await fetchTierPage(5, "phylum", null);
    expect(result.status).toBe("ok");
    if (result.status === "ok") {
      expect(result.data.children).toHaveLength(1);
      expect(result.data.children[0]?.name).toBe("Arthropoda");
      expect(result.data.next_cursor).toBe("next-cursor");
    }
  });

  it("forwards the cursor verbatim when supplied", async () => {
    const fetchMock = mockFetchFetchOnce(mockFetchJson(TIER_PAGE));
    await fetchTierPage(5, "phylum", "cursor-1");
    const url = (fetchMock.mock.calls[0] as [string])[0];
    expect(url).toBe(
      "/api/tree/children?parent_id=5&limit=200&tier=phylum&cursor=cursor-1&tier_limit=50",
    );
  });

  it("honors a custom tierLimit", async () => {
    const fetchMock = mockFetchFetchOnce(mockFetchJson(TIER_PAGE));
    await fetchTierPage(5, "phylum", null, { tierLimit: 25 });
    const url = (fetchMock.mock.calls[0] as [string])[0];
    expect(url).toBe(
      "/api/tree/children?parent_id=5&limit=200&tier=phylum&cursor=&tier_limit=25",
    );
  });

  it("returns error on 5xx with the server detail", async () => {
    mockFetchFetchOnce(
      mockFetchJson({ detail: "internal error" }, 500),
    );
    const result = await fetchTierPage(5, "phylum", null);
    expect(result.status).toBe("error");
    if (result.status === "error") {
      expect(result.detail).toBe("internal error");
    }
  });
});
