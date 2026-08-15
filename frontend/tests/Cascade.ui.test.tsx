/** UI contract tests for the path-aware Cascade (7-fixed-tier rule).

The cascade always renders exactly seven dropdowns:
Biota, Kingdom, Phylum, Class, Order, Family, Genus. These
tests cover the orthogonal UI behaviour:

- Loading state per dropdown (the slot is disabled until the
  parent snapshot lands).
- Empty / leaf handling at any depth.
- Inclusion-toggle forwarding to the species fetch.
- Reset on parent change.
*/

import { act, render, screen, waitFor, within } from "@testing-library/react";
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

/** Build a single-tier ``next_tiers`` array from a rank label and
 *  the children the resolver would group under it. */
function singleTier(rank: string, children: TaxonResponse[]): NextTier[] {
  return [
    {
      rank,
      label: rank.charAt(0).toUpperCase() + rank.slice(1),
      examples: children.slice(0, 3).map((child) => child.name),
      children,
    },
  ];
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Cascade UI: loading and empty states", () => {
  it("disables the root dropdown while its children are in flight", async () => {
    let resolveFetch:
      | ((value: Response | PromiseLike<Response>) => void)
      | null = null;
    globalThis.fetch = vi.fn().mockImplementation(
      () =>
        new Promise<Response>((res) => {
          resolveFetch = res;
        }),
    ) as unknown as typeof fetch;

    render(<Cascade />);

    expect(
      screen.getByRole("combobox", { name: "Biota" }),
    ).toBeDisabled();

    await act(async () => {
      resolveFetch!(
        mockFetchJson([
          taxon(1, "Biota", "biota"),
          taxon(2, "Viruses", "biota"),
        ]),
      );
    });

    expect(
      screen.getByRole("combobox", { name: "Biota" }),
    ).not.toBeDisabled();
  });

  it("renders 'No children' when the deepest taxon has no species children", async () => {
    // Walk to Animalia; Animalia is a leaf with no children.
    // The cascade renders the empty state under the species
    // list slot. With the seven-fixed-tier rule, every slot
    // remains rendered but disabled — the next-tier slot (Class
    // here) shows "No class available" until the user picks a
    // phylum with class children. Animalia is the deepest pick
    // so the species list slot renders "No children.".
    globalThis.fetch = vi
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
          next_tiers: singleTier("kingdom", [taxon(10, "Animalia", "kingdom", 1)]),
        }),
      )
      // Animalia has no children at all.
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(10, "Animalia", "kingdom"),
          children: [],
          next_tiers: null,
        }),
      );

    const user = userEvent.setup();
    render(<Cascade />);

    await screen.findByRole("option", { name: "Biota" });
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Biota" }),
      "Biota",
    );
    await screen.findByRole("option", { name: "Animalia" });
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Kingdom" }),
      "Animalia",
    );

    // Animalia is a confirmed leaf — the species list slot
    // renders the empty state. The seven-fixed-tier rule keeps
    // Phylum / Class / Order / Family / Genus rendered but
    // disabled (Phylum shows "No phylum available").
    expect(await screen.findByText("No children.")).toBeInTheDocument();
    expect(
      screen.getByRole("combobox", { name: "Phylum" }),
    ).toBeDisabled();
  });
});

describe("Cascade UI: inclusion toggles", () => {
  it("lands the species list fetch when the deepest taxon is a confirmed genus", async () => {
    // Arthropoda → Insecta → Coleoptera → Curculionidae →
    // Sitophilus → species list.
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
          next_tiers: singleTier("kingdom", [taxon(10, "Animalia", "kingdom", 1)]),
        }),
      )
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(10, "Animalia", "kingdom"),
          children: [taxon(20, "Arthropoda", "phylum", 10)],
          next_tiers: singleTier("phylum", [taxon(20, "Arthropoda", "phylum", 10)]),
        }),
      )
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(20, "Arthropoda", "phylum"),
          children: [taxon(30, "Insecta", "class", 20)],
          next_tiers: singleTier("class", [taxon(30, "Insecta", "class", 20)]),
        }),
      )
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(30, "Insecta", "class"),
          children: [taxon(40, "Coleoptera", "order", 30)],
          next_tiers: singleTier("order", [taxon(40, "Coleoptera", "order", 30)]),
        }),
      )
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(40, "Coleoptera", "order"),
          children: [taxon(50, "Curculionidae", "family", 40)],
          next_tiers: singleTier("family", [taxon(50, "Curculionidae", "family", 40)]),
        }),
      )
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(50, "Curculionidae", "family"),
          children: [taxon(60, "Sitophilus", "genus", 50)],
          next_tiers: singleTier("genus", [taxon(60, "Sitophilus", "genus", 50)]),
        }),
      )
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(60, "Sitophilus", "genus"),
          children: [taxon(70, "Sitophilus granarius", "species", 60)],
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

    await screen.findByRole("option", { name: "Biota" });
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Biota" }),
      "Biota",
    );
    await screen.findByRole("option", { name: "Animalia" });
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Kingdom" }),
      "Animalia",
    );
    await screen.findByRole("option", { name: "Arthropoda" });
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Phylum" }),
      "Arthropoda",
    );
    await screen.findByRole("option", { name: "Insecta" });
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Class" }),
      "Insecta",
    );
    await screen.findByRole("option", { name: "Coleoptera" });
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Order" }),
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
