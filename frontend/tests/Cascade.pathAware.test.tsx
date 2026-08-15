/** Contract tests for the path-aware cascade frontend.

The cascade renders **exactly seven fixed dropdowns**:
Biota, Kingdom, Phylum, Class, Order, Family, Genus. Each
pick triggers a /path-children call with the cumulative path;
the next dropdown renders with the response's ``next_tiers``
(one ``NextTier`` per rank group). The cascade resolves the
phylum class aggregation rule transparently — subphylum /
infraphylum / parvphylum / megaclass tiers never surface as
dropdowns; the backend folds them into the class tier.
*/

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Cascade } from "../src/components/Cascade";
import type { NextTier, TaxonResponse } from "../src/api";

function mockFetchJson(json: unknown, status = 200): Response {
  return new Response(JSON.stringify(json), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function taxon(
  id: number,
  name: string,
  rank: string,
  parentId: number | null = null,
): TaxonResponse {
  return {
    id,
    name,
    display_name: `${name} [${rank}]`,
    rank,
    parent_id: parentId,
    is_synonym: false,
    is_extinct: false,
    is_uncertain: false,
    is_unassigned: false,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Path-aware cascade initial render", () => {
  it("loads the root list on mount via /api/kingdoms", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      mockFetchJson([
        taxon(1, "Biota", "biota"),
        taxon(2, "Viruses", "biota"),
      ]),
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    render(<Cascade />);

    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Biota" })).toBeInTheDocument();
    });
    expect(screen.getByRole("option", { name: "Viruses" })).toBeInTheDocument();
  });
});

describe("Path-aware cascade chains through the seven fixed tiers", () => {
  it("walks Biota → Animalia → Chordata and renders every class under the subphylum hierarchy", async () => {
    // Chordata's subphylum Vertebrata holds the classes
    // Mammalia + Aves. The backend, after the phylum class
    // aggregation rule, returns both as the ``class`` tier for
    // Chordata. The cascade renders the Class dropdown populated
    // with Mammalia + Aves (no Subphylum picker is exposed).
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        mockFetchJson([
          taxon(1, "Biota", "biota"),
          taxon(2, "Viruses", "biota"),
        ]),
      )
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(1, "Biota", "biota"),
          children: [taxon(10, "Animalia", "kingdom", 1)],
          next_tiers: [
            {
              rank: "kingdom",
              label: "Kingdom",
              examples: ["Animalia"],
              children: [taxon(10, "Animalia", "kingdom", 1)],
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(10, "Animalia", "kingdom"),
          children: [taxon(20, "Chordata", "phylum", 10)],
          next_tiers: [
            {
              rank: "phylum",
              label: "Phylum",
              examples: ["Chordata"],
              children: [taxon(20, "Chordata", "phylum", 10)],
            },
          ],
        }),
      )
      // Aggregated class tier — subphylum children folded in.
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(20, "Chordata", "phylum"),
          children: [
            taxon(30, "Mammalia", "class", 20),
            taxon(31, "Aves", "class", 20),
          ],
          next_tiers: [
            {
              rank: "class",
              label: "Class",
              examples: ["Mammalia", "Aves"],
              children: [
                taxon(30, "Mammalia", "class", 20),
                taxon(31, "Aves", "class", 20),
              ],
            },
          ],
        }),
      );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const user = userEvent.setup();
    render(<Cascade />);

    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Biota" }),
      "Biota",
    );
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Kingdom" }),
      "Animalia",
    );
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Phylum" }),
      "Chordata",
    );

    // The Class dropdown renders Mammalia + Aves — no
    // Subphylum picker is exposed. The seven fixed dropdowns
    // remain the only dropdowns on screen.
    const classDropdown = await screen.findByRole("combobox", { name: "Class" });
    await waitFor(() => {
      expect(
        within(classDropdown).getByRole("option", { name: "Mammalia" }),
      ).toBeInTheDocument();
    });
    expect(
      within(classDropdown).getByRole("option", { name: "Aves" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("combobox", { name: "Subphylum" }),
    ).not.toBeInTheDocument();
  });
});

describe("Path-aware cascade reaches species after a genus is picked", () => {
  it("fetches the species list when the user picks a genus", async () => {
    // Arthropoda (no subphylum) → Insecta → Coleoptera →
    // Curculionidae → Sitophilus → species list.
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        mockFetchJson([
          taxon(1, "Biota", "biota"),
          taxon(2, "Viruses", "biota"),
        ]),
      )
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(1, "Biota", "biota"),
          children: [taxon(10, "Animalia", "kingdom", 1)],
          next_tiers: [
            {
              rank: "kingdom",
              label: "Kingdom",
              examples: ["Animalia"],
              children: [taxon(10, "Animalia", "kingdom", 1)],
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(10, "Animalia", "kingdom"),
          children: [taxon(20, "Arthropoda", "phylum", 10)],
          next_tiers: [
            {
              rank: "phylum",
              label: "Phylum",
              examples: ["Arthropoda"],
              children: [taxon(20, "Arthropoda", "phylum", 10)],
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(20, "Arthropoda", "phylum"),
          children: [taxon(30, "Insecta", "class", 20)],
          next_tiers: [
            {
              rank: "class",
              label: "Class",
              examples: ["Insecta"],
              children: [taxon(30, "Insecta", "class", 20)],
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(30, "Insecta", "class"),
          children: [taxon(40, "Coleoptera", "order", 30)],
          next_tiers: [
            {
              rank: "order",
              label: "Order",
              examples: ["Coleoptera"],
              children: [taxon(40, "Coleoptera", "order", 30)],
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(40, "Coleoptera", "order"),
          children: [taxon(50, "Curculionidae", "family", 40)],
          next_tiers: [
            {
              rank: "family",
              label: "Family",
              examples: ["Curculionidae"],
              children: [taxon(50, "Curculionidae", "family", 40)],
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(50, "Curculionidae", "family"),
          children: [taxon(60, "Sitophilus", "genus", 50)],
          next_tiers: [
            {
              rank: "genus",
              label: "Genus",
              examples: ["Sitophilus"],
              children: [taxon(60, "Sitophilus", "genus", 50)],
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(60, "Sitophilus", "genus"),
          children: [
            taxon(70, "Sitophilus granarius", "species", 60),
            taxon(71, "Sitophilus oryzae", "species", 60),
          ],
          next_tiers: null,
        }),
      )
      .mockResolvedValueOnce(
        mockFetchJson({
          items: [
            taxon(70, "Sitophilus granarius", "species", 60),
            taxon(71, "Sitophilus oryzae", "species", 60),
          ],
          next_cursor: null,
        }),
      );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const user = userEvent.setup();
    render(<Cascade />);

    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Biota" }),
      "Biota",
    );
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Kingdom" }),
      "Animalia",
    );
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Phylum" }),
      "Arthropoda",
    );
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Class" }),
      "Insecta",
    );
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Order" }),
      "Coleoptera",
    );
    const familyDropdown = await screen.findByRole("combobox", { name: "Family" });
    await waitFor(() => {
      expect(
        within(familyDropdown).getByRole("option", { name: "Curculionidae" }),
      ).toBeInTheDocument();
    });
    await user.selectOptions(familyDropdown, "Curculionidae");
    const genusDropdown = await screen.findByRole("combobox", { name: "Genus" });
    await waitFor(() => {
      expect(
        within(genusDropdown).getByRole("option", { name: "Sitophilus" }),
      ).toBeInTheDocument();
    });
    await user.selectOptions(genusDropdown, "Sitophilus");

    const speciesList = await screen.findByRole("list", { name: /species list/i });
    expect(within(speciesList).getByText("Sitophilus granarius")).toBeInTheDocument();
    expect(within(speciesList).getByText("Sitophilus oryzae")).toBeInTheDocument();
  });
});

describe("Path-aware cascade resets children when a parent changes", () => {
  it("clears every segment after a parent pick so no stale state leaks", async () => {
    const callLog: string[] = [];
    const fetchSpy = vi.fn().mockImplementation((url: string) => {
      callLog.push(url);
      if (url.endsWith("/api/kingdoms")) {
        return Promise.resolve(
          mockFetchJson([
            taxon(1, "Biota", "biota"),
            taxon(2, "Viruses", "biota"),
          ]),
        );
      }
      if (url.includes("/path-children?path=Biota|Animalia")) {
        return Promise.resolve(
          mockFetchJson({
            parent: taxon(10, "Animalia", "kingdom"),
            children: [taxon(20, "Chordata", "phylum", 10)],
            next_tiers: [
              {
                rank: "phylum",
                label: "Phylum",
                examples: ["Chordata"],
                children: [taxon(20, "Chordata", "phylum", 10)],
              },
            ],
          }),
        );
      }
      if (url.includes("/path-children?path=Biota|Plantae")) {
        return Promise.resolve(
          mockFetchJson({
            parent: taxon(11, "Plantae", "kingdom"),
            children: [taxon(30, "Tracheophyta", "phylum", 11)],
            next_tiers: [
              {
                rank: "phylum",
                label: "Phylum",
                examples: ["Tracheophyta"],
                children: [taxon(30, "Tracheophyta", "phylum", 11)],
              },
            ],
          }),
        );
      }
      if (url.includes("/path-children?path=Biota")) {
        return Promise.resolve(
          mockFetchJson({
            parent: taxon(1, "Biota", "biota"),
            children: [
              taxon(10, "Animalia", "kingdom", 1),
              taxon(11, "Plantae", "kingdom", 1),
            ],
            next_tiers: [
              {
                rank: "kingdom",
                label: "Kingdom",
                examples: ["Animalia", "Plantae"],
                children: [
                  taxon(10, "Animalia", "kingdom", 1),
                  taxon(11, "Plantae", "kingdom", 1),
                ],
              },
            ],
          }),
        );
      }
      return Promise.reject(new Error(`unexpected fetch in test: ${url}`));
    });
    globalThis.fetch = fetchSpy as unknown as typeof fetch;

    const user = userEvent.setup();
    render(<Cascade />);

    // First chain: Biota → Animalia → Chordata.
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Biota" }),
      "Biota",
    );
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Kingdom" }),
      "Animalia",
    );
    await screen.findByRole("option", { name: "Chordata" });

    // Switch kingdoms: Animalia → Plantae. The Phylum dropdown
    // must reset and show Plantae's phylum children.
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Kingdom" }),
      "Plantae",
    );
    await waitFor(() => {
      expect(
        screen.getByRole("option", { name: "Tracheophyta" }),
      ).toBeInTheDocument();
    });
    // Chordata (the previous phylum pick) does not leak.
    expect(
      screen.queryByRole("option", { name: "Chordata" }),
    ).not.toBeInTheDocument();
    const animaliaCalls = callLog.filter((u) =>
      u.includes("/path-children?path=Biota|Animalia"),
    );
    const plantaeCalls = callLog.filter((u) =>
      u.includes("/path-children?path=Biota|Plantae"),
    );
    expect(animaliaCalls.length).toBeGreaterThanOrEqual(1);
    expect(plantaeCalls.length).toBeGreaterThanOrEqual(1);
  });
});

// Silence unused-import warnings when subsetting the suite.
const _silenceNextTier: NextTier | null = null;
void _silenceNextTier;
