import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createSpeciesFolder,
  deleteExplored,
  deleteLinkVisited,
  fetchExploredList,
  fetchLinkVisited,
  fetchSpeciesFolder,
  postExplored,
  postLinkVisited,
  speciesKey,
} from "../src/api";

function response(status: number, body?: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockFetch(...responses: Response[]): ReturnType<typeof vi.fn> {
  const fn = vi.fn();
  for (const item of responses) fn.mockResolvedValueOnce(item);
  globalThis.fetch = fn as unknown as typeof fetch;
  return fn;
}

afterEach(() => vi.restoreAllMocks());

describe("workspace API", () => {
  it("uses encoded durable species keys and validates explored responses", async () => {
    const fetchMock = mockFetch(
      response(200, { species: [{ genus: "Panthera", epithet: "tigris", explored_at: "2026-08-18T00:00:00Z" }] }),
      response(200, { genus: "Panthera", epithet: "tigris", explored_at: "2026-08-18T00:00:00Z" }),
      response(204),
    );

    expect(speciesKey("Panthera", "tigris")).toBe("Panthera%7Ctigris");
    expect(await fetchExploredList()).toMatchObject({ status: "ok", data: { species: [{ genus: "Panthera" }] } });
    expect((await postExplored("Panthera", "tigris")).status).toBe("ok");
    expect((await deleteExplored("Panthera", "tigris")).status).toBe("ok");
    expect(fetchMock.mock.calls.map((call) => [call[0], call[1]?.method])).toEqual([
      ["/api/explored/list", "GET"],
      ["/api/explored/Panthera/tigris", "POST"],
      ["/api/explored/Panthera/tigris", "DELETE"],
    ]);
  });

  it("maps folder 201, 404, and 409 envelopes", async () => {
    mockFetch(
      response(201, { path: "/workspace/Panthera tigris", exists: true }),
      response(404, { detail: "missing" }),
      response(409, { detail: "exists" }),
    );

    expect(await createSpeciesFolder("Panthera", "tigris")).toMatchObject({ status: "ok", data: { exists: true } });
    expect(await fetchSpeciesFolder("Panthera", "leo")).toEqual({ status: "not-found", detail: "missing" });
    expect(await createSpeciesFolder("Panthera", "tigris")).toEqual({ status: "error", detail: "exists" });
  });

  it("validates visited lists and maps mutation and server outcomes", async () => {
    const fetchMock = mockFetch(
      response(200, { genus: "Panthera", epithet: "tigris", sources: [{ source: "Wikipedia", visited_at: "2026-08-18T00:00:00Z" }] }),
      response(204),
      response(204),
      response(500, { detail: "database unavailable" }),
    );

    expect(await fetchLinkVisited("Panthera", "tigris")).toMatchObject({ status: "ok", data: { sources: [{ source: "Wikipedia" }] } });
    expect((await postLinkVisited("Panthera", "tigris", "Sci-hub")).status).toBe("ok");
    expect((await deleteLinkVisited("Panthera", "tigris", "Sci-hub")).status).toBe("ok");
    expect(await fetchExploredList()).toEqual({ status: "error", detail: "database unavailable" });
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/link-visited/Panthera/tigris/Sci-hub");
  });

  it("rejects malformed successful payloads through zod", async () => {
    mockFetch(response(200, { species: [{ genus: "Panthera" }] }));
    const result = await fetchExploredList();
    expect(result.status).toBe("error");
    if (result.status === "error") expect(result.detail).toContain("Invalid response");
  });
});
