/** RED-first contract tests for the typed API client.

The client wraps the seven endpoints shipped in Sub-PRs 2A/2B/2C
and translates the HTTP status into a discriminated union the React
components can branch on. These tests pin that contract:

- 200 → ``{status: 'ok', data}``.
- 404 → ``{status: 'not-found', detail}``.
- 409 → ``{status: 'ambiguous', candidates}``.
- 5xx / network → ``{status: 'error', detail}``.

Every fetch uses ``fetch-mock`` so the tests do not depend on the
real backend.
*/

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  type ApiResult,
  fetchChildren,
  fetchKingdoms,
  fetchLinks,
  fetchSpecies,
  fetchSpeciesByPair,
  inclusionCsv,
  splitSpeciesName,
} from "../src/api";

interface MockResponseInit {
  status?: number;
  body?: unknown;
}

function mockFetchResponse(init: MockResponseInit = {}): Response {
  const status = init.status ?? 200;
  const body = init.body ?? {};
  return new Response(JSON.stringify(body), {
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

describe("fetchKingdoms", () => {
  it("returns ok with the kingdoms list on 200", async () => {
    const body = [{ id: 1, name: "Animalia", display_name: "Animalia [kingdom]" }];
    mockFetchFetchOnce(mockFetchResponse({ status: 200, body }));
    const result = await fetchKingdoms();
    expect(result.status).toBe("ok");
    if (result.status === "ok") {
      expect(result.data).toEqual(body);
    }
  });

  it("returns not-found when the API returns 404", async () => {
    mockFetchFetchOnce(
      mockFetchResponse({ status: 404, body: { detail: "no kingdoms" } }),
    );
    const result = await fetchKingdoms();
    expect(result).toEqual({ status: "not-found", detail: "no kingdoms" });
  });
});

describe("fetchChildren", () => {
  it("hits the right path for phyla", async () => {
    const fetchMock = mockFetchFetchOnce(
      mockFetchResponse({ status: 200, body: [] }),
    );
    await fetchChildren(["Animalia"], "phyla");
    const url = (fetchMock.mock.calls[0] as [string])[0];
    expect(url).toBe("/api/Animalia/phyla");
  });

  it("encodes URL-unsafe segments", async () => {
    const fetchMock = mockFetchFetchOnce(
      mockFetchResponse({ status: 200, body: [] }),
    );
    await fetchChildren(["Animalia", "Genus (foo)"], "classes");
    const url = (fetchMock.mock.calls[0] as [string])[0];
    expect(url).toBe("/api/Animalia/Genus%20%28foo%29/classes");
  });
});

describe("fetchSpecies", () => {
  it("forwards the include CSV query param", async () => {
    const fetchMock = mockFetchFetchOnce(
      mockFetchResponse({ status: 200, body: { items: [], next_cursor: null } }),
    );
    await fetchSpecies(["Animalia"], { include: ["synonyms", "extinct"] });
    const url = (fetchMock.mock.calls[0] as [string])[0];
    expect(url).toBe("/api/Animalia/species?include=synonyms%2Cextinct");
  });

  it("forwards the cursor when present", async () => {
    const fetchMock = mockFetchFetchOnce(
      mockFetchResponse({ status: 200, body: { items: [], next_cursor: null } }),
    );
    await fetchSpecies(["Animalia"], { cursor: "name:Foo" });
    const url = (fetchMock.mock.calls[0] as [string])[0];
    expect(url).toBe("/api/Animalia/species?cursor=name%3AFoo");
  });

  it("omits the query string when no params are set", async () => {
    const fetchMock = mockFetchFetchOnce(
      mockFetchResponse({ status: 200, body: { items: [], next_cursor: null } }),
    );
    await fetchSpecies(["Animalia"]);
    const url = (fetchMock.mock.calls[0] as [string])[0];
    expect(url).toBe("/api/Animalia/species");
  });
});

describe("fetchSpeciesByPair", () => {
  it("returns ok with the species on 200", async () => {
    const body = {
      id: 7,
      canonical_name: "Genus species",
      display_name: "Genus species",
      markers: {
        is_synonym: false,
        is_extinct: false,
        is_uncertain: false,
        is_unassigned: false,
      },
      breadcrumb: ["Animalia"],
    };
    mockFetchFetchOnce(mockFetchResponse({ status: 200, body }));
    const result = await fetchSpeciesByPair("Genus", "species");
    expect(result.status).toBe("ok");
    if (result.status === "ok") {
      expect(result.data.canonical_name).toBe("Genus species");
    }
  });

  it("returns ambiguous with candidates on 409", async () => {
    const body = {
      detail: "ambiguous",
      candidates: [
        {
          id: 1,
          canonical_name: "Genus species",
          display_name: "Genus species",
          breadcrumb: ["Animalia"],
        },
        {
          id: 2,
          canonical_name: "Genus species",
          display_name: "Genus species",
          breadcrumb: ["Plantae"],
        },
      ],
    };
    mockFetchFetchOnce(mockFetchResponse({ status: 409, body }));
    const result = await fetchSpeciesByPair("Genus", "species");
    expect(result.status).toBe("ambiguous");
    if (result.status === "ambiguous") {
      expect(result.candidates).toHaveLength(2);
    }
  });

  it("returns not-found on 404", async () => {
    mockFetchFetchOnce(
      mockFetchResponse({ status: 404, body: { detail: "taxon not found" } }),
    );
    const result = await fetchSpeciesByPair("Genus", "species");
    expect(result.status).toBe("not-found");
  });
});

describe("fetchLinks", () => {
  it("hits the right path for the links endpoint", async () => {
    const fetchMock = mockFetchFetchOnce(
      mockFetchResponse({ status: 200, body: { species: {}, links: [] } }),
    );
    await fetchLinks(["Animalia"], "species");
    const url = (fetchMock.mock.calls[0] as [string])[0];
    expect(url).toBe("/api/Animalia/species/links");
  });
});

describe("error mapping", () => {
  it("maps 5xx to error status with the server detail", async () => {
    mockFetchFetchOnce(
      mockFetchResponse({ status: 500, body: { detail: "internal error" } }),
    );
    const result: ApiResult<unknown> = await fetchKingdoms();
    expect(result.status).toBe("error");
    if (result.status === "error") {
      expect(result.detail).toBe("internal error");
    }
  });

  it("maps AbortError to not-found 'aborted'", async () => {
    globalThis.fetch = vi.fn().mockImplementationOnce(
      () => new Promise<Response>((_, reject) => {
        setTimeout(
          () => reject(new DOMException("aborted", "AbortError")),
          0,
        );
      }),
    ) as unknown as typeof fetch;
    const result = await fetchKingdoms();
    expect(result.status).toBe("not-found");
    if (result.status === "not-found") {
      expect(result.detail).toBe("aborted");
    }
  });

  it("maps network failures to error status", async () => {
    globalThis.fetch = vi.fn().mockRejectedValueOnce(
      new Error("Failed to fetch"),
    ) as unknown as typeof fetch;
    const result = await fetchKingdoms();
    expect(result.status).toBe("error");
    if (result.status === "error") {
      expect(result.detail).toBe("Failed to fetch");
    }
  });
});

describe("pure helpers", () => {
  it("splitSpeciesName returns genus + epithet", () => {
    expect(splitSpeciesName("Girardinichthys multiradiatus")).toEqual({
      genus: "Girardinichthys",
      epithet: "multiradiatus",
    });
  });

  it("splitSpeciesName handles multi-word epithets", () => {
    expect(splitSpeciesName("Genus species")).toEqual({
      genus: "Genus",
      epithet: "species",
    });
  });

  it("splitSpeciesName handles missing epithet", () => {
    expect(splitSpeciesName("Genus")).toEqual({ genus: "Genus", epithet: "" });
  });

  it("inclusionCsv joins the set with commas", () => {
    expect(inclusionCsv(new Set(["synonyms", "extinct"]))).toBe(
      "synonyms,extinct",
    );
  });

  it("inclusionCsv returns empty string for empty set", () => {
    expect(inclusionCsv(new Set())).toBe("");
  });
});