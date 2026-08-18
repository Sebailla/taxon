/** RED contract tests for the activate-on-click isolation.

Pins MUST clauses 2 + 3 from
``openspec/changes/species-folder-explorer/specs/workspace-explorer/spec.md``:

2. Clicking a ``SpeciesLinks`` species-cell (with ``genus`` + ``epithet``
   props) populates ``activeLink`` with ``{speciesKey, source, url}``.
   The ``target="_blank"`` anchor behaviour is preserved.
3. Clicking a ``SpeciesLinks`` breadcrumb-cell (no ``genus`` /
   ``epithet`` props — the per-taxon breadcrumb-links panel) does NOT
   mutate ``activeLink``. The ``target="_blank"`` anchor behaviour is
   preserved.

The integration test mounts the real ``App`` + ``SpeciesLinks`` and
exercises the click flow. The fallback / aria-label / sandbox rules
are pinned in ``ExplorerPanel.test.tsx``; this file pins the act of
SETTING the active link through the species-link click.
*/

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/App";
import { speciesKey } from "../src/api";
import { useCascadePath } from "../src/store/cascadePath";
import { useWorkspace } from "../src/store/workspace";

const TAXON_SELECT_EVENT = "taxon:select";

const CHORDATA_TAXON = {
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
  breadcrumb: ["Animalia", "Chordata"],
};

const PANTHERA_TIGRIS = {
  id: 1,
  name: "Panthera tigris",
  canonical_name: "Panthera tigris",
  display_name: "Panthera tigris (Linnaeus, 1758)",
  rank: "species",
  parent_id: 6,
  is_synonym: false,
  is_extinct: false,
  is_uncertain: false,
  is_unassigned: false,
  markers: {
    is_synonym: false,
    is_extinct: false,
    is_uncertain: false,
    is_unassigned: false,
  },
  breadcrumb: ["Animalia", "Chordata", "Mammalia", "Carnivora", "Felidae", "Panthera"],
};

const SPECIES_LINKS = [
  { source: "Wikipedia", label: "Wikipedia", url: "https://example.test/wiki/Panthera_tigris" },
  { source: "Google", label: "Google", url: "https://example.test/google?q=Panthera+tigris" },
];

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
  useCascadePath.setState({ path: [] });
  useWorkspace.getState().clear();
});

function fireTaxonSelect(detail: { row: typeof PANTHERA_TIGRIS; breadcrumb: string[]; parentSegments: string[] }): void {
  act(() => {
    window.dispatchEvent(
      new CustomEvent(TAXON_SELECT_EVENT, {
        detail: {
          row: detail.row,
          breadcrumb: detail.breadcrumb,
          parentSegments: detail.parentSegments,
        },
      }),
    );
  });
}

describe("ExplorerPanel — activate on SpeciesLinks click", () => {
  it("sets activeLink when a species-cell link is clicked", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string | URL) => {
      const urlStr = typeof url === "string" ? url : url.toString();
      if (urlStr.includes("links")) {
        return Promise.resolve(
          mockFetchJson({
            species: PANTHERA_TIGRIS,
            links: SPECIES_LINKS,
          }),
        );
      }
      if (urlStr.includes("parent_id=0")) {
        return Promise.resolve(mockFetchJson({ parent: { id: 0 }, children: [CHORDATA_TAXON], next_cursor: null }));
      }
      return Promise.resolve(mockFetchJson({}));
    });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    render(<App />);
    fireTaxonSelect({
      row: PANTHERA_TIGRIS,
      breadcrumb: PANTHERA_TIGRIS.breadcrumb,
      parentSegments: ["Animalia", "Chordata", "Mammalia", "Carnivora", "Felidae", "Panthera"],
    });

    const user = userEvent.setup();
    const wikiLink = await screen.findByRole("link", { name: /Wikipedia \(opens in a new tab\)/ });
    await user.click(wikiLink);

    const expectedKey = speciesKey("Panthera", "tigris");
    await waitFor(() => {
      expect(useWorkspace.getState().activeLink).toEqual({
        speciesKey: expectedKey,
        source: "Wikipedia",
        url: "https://example.test/wiki/Panthera_tigris",
      });
    });
    expect(wikiLink).toHaveAttribute("target", "_blank");
  });

  it("does NOT set activeLink when a breadcrumb-links panel cell is clicked", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string | URL) => {
      const urlStr = typeof url === "string" ? url : url.toString();
      if (urlStr.includes("taxon-links")) {
        return Promise.resolve(
          mockFetchJson({
            taxon: CHORDATA_TAXON,
            links: SPECIES_LINKS,
          }),
        );
      }
      if (urlStr.includes("parent_id=0")) {
        return Promise.resolve(mockFetchJson({ parent: { id: 0 }, children: [CHORDATA_TAXON], next_cursor: null }));
      }
      return Promise.resolve(mockFetchJson({}));
    });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    render(<App />);
    // Pop the breadcrumb-links panel by selecting a cascade path.
    act(() => {
      window.dispatchEvent(
        new CustomEvent("path:change", { detail: { path: ["Chordata"] } }),
      );
    });
    await waitFor(() => {
      expect(useCascadePath.getState().path).toEqual(["Chordata"]);
    });

    const breadcrumbLink = await screen.findByRole("link", { name: /Wikipedia \(opens in a new tab\)/ });
    const user = userEvent.setup();
    await user.click(breadcrumbLink);
    // The speciesKey helper is not used here because the breadcrumb
    // panel has no genus/epithet; the contract is that activeLink
    // is NOT mutated.
    expect(useWorkspace.getState().activeLink).toBeNull();
    expect(breadcrumbLink).toHaveAttribute("target", "_blank");
  });
});
