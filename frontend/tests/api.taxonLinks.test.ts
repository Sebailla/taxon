/** RED contract tests for ``fetchTaxonLinks`` (the client for ``GET /api/{path}/taxon-links``).

The function mirrors ``fetchPathChildren``: encodes each segment
with ``encodeURIComponent``, joins them with ``|``, hits
``/{path}/taxon-links``, and returns the discriminated union:

- 200 → ``{status: "ok", data: TaxonLinksResponse}`` with ``taxon``
  and 13 ``links``.
- 404 → ``{status: "not-found", detail}`` whose detail names the
  bad segment.

These tests pin the contract for tasks 3.5–3.6 in
``openspec/changes/breadcrumb-dinamico/tasks.md``.
*/

import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchTaxonLinks } from "../src/api";

function mockFetchJson(json: unknown, status = 200): Response {
  return new Response(JSON.stringify(json), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockFetchOnce(response: Response): ReturnType<typeof vi.fn> {
  const fn = vi.fn().mockResolvedValueOnce(response);
  globalThis.fetch = fn as unknown as typeof fetch;
  return fn;
}

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

afterEach(() => {
  vi.restoreAllMocks();
});

describe("fetchTaxonLinks — happy path", () => {
  it("hits /Animalia%7CChordata/taxon-links with the %7C-encoded path", async () => {
    const fetchMock = mockFetchOnce(
      mockFetchJson({ taxon: CHORDATA_TAXON, links: LINKS_13 }),
    );
    const result = await fetchTaxonLinks(["Animalia", "Chordata"]);

    const url = (fetchMock.mock.calls[0] as [string])[0];
    expect(url).toBe("/api/Animalia%7CChordata/taxon-links");
    expect(result.status).toBe("ok");
    if (result.status === "ok") {
      expect(result.data.links).toHaveLength(13);
      expect(result.data.taxon.name).toBe("Chordata");
    }
  });

  it("encodes URL-unsafe segments inside the path", async () => {
    const fetchMock = mockFetchOnce(
      mockFetchJson({ taxon: CHORDATA_TAXON, links: LINKS_13 }),
    );
    await fetchTaxonLinks(["Animalia", "Genus (foo)"]);

    const url = (fetchMock.mock.calls[0] as [string])[0];
    expect(url).toBe("/api/Animalia%7CGenus%20%28foo%29/taxon-links");
  });
});

describe("fetchTaxonLinks — error mapping", () => {
  it("returns not-found with the server detail on 404", async () => {
    mockFetchOnce(
      mockFetchJson({
        detail: "taxon not found: 'Atlantis'",
      }, 404),
    );
    const result = await fetchTaxonLinks(["Atlantis"]);
    expect(result).toEqual({
      status: "not-found",
      detail: "taxon not found: 'Atlantis'",
    });
  });

  it("returns error on 5xx with the server detail", async () => {
    mockFetchOnce(
      mockFetchJson({ detail: "internal error" }, 500),
    );
    const result = await fetchTaxonLinks(["Animalia", "Chordata"]);
    expect(result.status).toBe("error");
    if (result.status === "error") {
      expect(result.detail).toBe("internal error");
    }
  });
});