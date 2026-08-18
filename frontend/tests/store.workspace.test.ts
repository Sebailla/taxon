import { afterEach, describe, expect, it, vi } from "vitest";

import { speciesKey } from "../src/api";
import { useWorkspace } from "../src/store/workspace";

function response(status: number, body?: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockFetch(...responses: Response[]): void {
  const fn = vi.fn();
  for (const item of responses) fn.mockResolvedValueOnce(item);
  globalThis.fetch = fn as unknown as typeof fetch;
}

afterEach(() => {
  vi.restoreAllMocks();
  useWorkspace.getState().clear();
});

describe("workspace store", () => {
  it("hydrates explored state and lazily loads folders and visited sources", async () => {
    mockFetch(
      response(200, { species: [{ genus: "Panthera", epithet: "tigris", explored_at: "2026-08-18T00:00:00Z" }] }),
      response(200, { path: "/workspace/Panthera tigris", exists: true }),
      response(200, { genus: "Panthera", epithet: "tigris", sources: [{ source: "Wikipedia", visited_at: "2026-08-18T00:00:00Z" }] }),
    );
    const key = speciesKey("Panthera", "tigris");

    await useWorkspace.getState().loadExploredList();
    await useWorkspace.getState().loadFolder("Panthera", "tigris");
    await useWorkspace.getState().loadVisited("Panthera", "tigris");

    expect(useWorkspace.getState().explored.has(key)).toBe(true);
    expect(useWorkspace.getState().folders.get(key)).toBe("/workspace/Panthera tigris");
    expect(useWorkspace.getState().visitedLinks.get(key)).toEqual(new Set(["Wikipedia"]));
  });

  it("toggles explored and visited state through durable string keys", async () => {
    mockFetch(response(200, { genus: "Panthera", epithet: "tigris", explored_at: "now" }), response(204), response(204), response(204));
    const key = speciesKey("Panthera", "tigris");

    await useWorkspace.getState().toggleExplored("Panthera", "tigris");
    expect(useWorkspace.getState().explored.has(key)).toBe(true);
    await useWorkspace.getState().toggleExplored("Panthera", "tigris");
    expect(useWorkspace.getState().explored.has(key)).toBe(false);
    await useWorkspace.getState().toggleVisited("Panthera", "tigris", "Wikipedia");
    expect(useWorkspace.getState().visitedLinks.get(key)).toEqual(new Set(["Wikipedia"]));
    await useWorkspace.getState().toggleVisited("Panthera", "tigris", "Wikipedia");
    expect(useWorkspace.getState().visitedLinks.get(key)).toEqual(new Set());
  });

  it("creates a folder, stores its path, and clears all cascade-scoped state", async () => {
    mockFetch(response(201, { path: "/workspace/Panthera tigris", exists: true }));
    const key = speciesKey("Panthera", "tigris");

    await useWorkspace.getState().createFolder("Panthera", "tigris");
    useWorkspace.getState().setActiveLink({ speciesKey: key, source: "Wikipedia", url: "https://example.test" });
    expect(useWorkspace.getState().folders.get(key)).toBe("/workspace/Panthera tigris");
    expect(useWorkspace.getState().activeLink?.source).toBe("Wikipedia");

    useWorkspace.getState().clear();
    expect(useWorkspace.getState().folders.size).toBe(0);
    expect(useWorkspace.getState().activeLink).toBeNull();
  });
});
