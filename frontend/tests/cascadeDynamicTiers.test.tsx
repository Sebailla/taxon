/** Contract tests for the cascade best-effort walk with off-tuple ranks.

The CLB / CoL taxonomy publishes intermediate ranks between the locked
9-tier tuple the legacy cascade projected onto:

- between subphylum and class: infraphylum, parvphylum, megaclass
- between class and order: subclass
- between order and family: suborder

The legacy cascade dead-ended at any off-tuple tier (Issue #43). The
new resolver fetches children with no rank filter and groups them by
their actual CLB rank; the wire envelope exposes ``next_tiers`` (list
of ``{rank, label, examples, children}``) so the cascade UI renders
one dropdown per group with the dropdown label taken from the rank
itself ("Infraphylum", "Parvphylum", "Megaclass", "Subclass",
"Suborder").
*/

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Cascade } from "../src/components/Cascade";
import type { TaxonResponse } from "../src/api";

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

describe("Cascade dynamic tiers driven by next_tiers", () => {
  it("renders one dropdown per tier in next_tiers", async () => {
    // Chordata's children include BOTH subphylum and class rows in
    // this chain (Vertebrata is a subphylum child, Mammalia is a
    // class child of Vertebrata but the test mocks Mammalia as a
    // class child of Chordata to exercise the two-tier rendering).
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
      // Chordata emits two tier groups: subphylum + class.
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(20, "Chordata", "phylum"),
          children: [
            taxon(30, "Vertebrata", "subphylum", 20),
            taxon(40, "Mammalia", "class", 20),
          ],
          next_tiers: [
            {
              rank: "subphylum",
              label: "Subphylum",
              examples: ["Vertebrata"],
              children: [taxon(30, "Vertebrata", "subphylum", 20)],
            },
            {
              rank: "class",
              label: "Class",
              examples: ["Mammalia"],
              children: [taxon(40, "Mammalia", "class", 20)],
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

    // Two tier dropdowns render after Chordata: Subphylum + Class.
    const subphylumDropdown = await screen.findByRole("combobox", {
      name: "Subphylum",
    });
    const classDropdown = await screen.findByRole("combobox", { name: "Class" });
    expect(subphylumDropdown).toBeInTheDocument();
    expect(classDropdown).toBeInTheDocument();
    await waitFor(() => {
      expect(
        within(subphylumDropdown).getByRole("option", { name: "Vertebrata" }),
      ).toBeInTheDocument();
    });
    expect(
      within(classDropdown).getByRole("option", { name: "Mammalia" }),
    ).toBeInTheDocument();
  });

  it("reaches Panthera via infraphylum + parvphylum + megaclass + subclass + suborder chain", async () => {
    // Full mock chain:
    //   Biota → Animalia → Chordata → Vertebrata →
    //   Gnathostomata (infraphylum) → Osteichthyes (parvphylum) →
    //   Tetrapoda (megaclass) → Mammalia (class) →
    //   Theria (subclass) → Carnivora (order) →
    //   Feliformia (suborder) → Felidae (family) → Panthera (genus)
    // The cascade emits a dropdown per next_tiers entry with the
    // dropdown label taken from the rank itself ("Infraphylum",
    // "Parvphylum", "Megaclass", "Subclass", "Suborder").
    const fetchMock = vi
      .fn()
      // 1. Initial root fetch.
      .mockResolvedValueOnce(
        mockFetchJson([
          taxon(1, "Biota", "biota"),
          taxon(2, "Viruses", "biota"),
        ]),
      )
      // 2. Pick Biota.
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
      // 3. Pick Animalia.
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
      // 4. Pick Chordata → subphylum.
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(20, "Chordata", "phylum"),
          children: [taxon(30, "Vertebrata", "subphylum", 20)],
          next_tiers: [
            {
              rank: "subphylum",
              label: "Subphylum",
              examples: ["Vertebrata"],
              children: [taxon(30, "Vertebrata", "subphylum", 20)],
            },
          ],
        }),
      )
      // 5. Pick Vertebrata → infraphylum.
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(30, "Vertebrata", "subphylum"),
          children: [taxon(40, "Gnathostomata", "infraphylum", 30)],
          next_tiers: [
            {
              rank: "infraphylum",
              label: "Infraphylum",
              examples: ["Gnathostomata"],
              children: [taxon(40, "Gnathostomata", "infraphylum", 30)],
            },
          ],
        }),
      )
      // 6. Pick Gnathostomata → parvphylum.
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(40, "Gnathostomata", "infraphylum"),
          children: [taxon(50, "Osteichthyes", "parvphylum", 40)],
          next_tiers: [
            {
              rank: "parvphylum",
              label: "Parvphylum",
              examples: ["Osteichthyes"],
              children: [taxon(50, "Osteichthyes", "parvphylum", 40)],
            },
          ],
        }),
      )
      // 7. Pick Osteichthyes → megaclass.
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(50, "Osteichthyes", "parvphylum"),
          children: [taxon(60, "Tetrapoda", "megaclass", 50)],
          next_tiers: [
            {
              rank: "megaclass",
              label: "Megaclass",
              examples: ["Tetrapoda"],
              children: [taxon(60, "Tetrapoda", "megaclass", 50)],
            },
          ],
        }),
      )
      // 8. Pick Tetrapoda → class.
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(60, "Tetrapoda", "megaclass"),
          children: [taxon(70, "Mammalia", "class", 60)],
          next_tiers: [
            {
              rank: "class",
              label: "Class",
              examples: ["Mammalia"],
              children: [taxon(70, "Mammalia", "class", 60)],
            },
          ],
        }),
      )
      // 9. Pick Mammalia → subclass.
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(70, "Mammalia", "class"),
          children: [taxon(80, "Theria", "subclass", 70)],
          next_tiers: [
            {
              rank: "subclass",
              label: "Subclass",
              examples: ["Theria"],
              children: [taxon(80, "Theria", "subclass", 70)],
            },
          ],
        }),
      )
      // 10. Pick Theria → order.
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(80, "Theria", "subclass"),
          children: [taxon(90, "Carnivora", "order", 80)],
          next_tiers: [
            {
              rank: "order",
              label: "Order",
              examples: ["Carnivora"],
              children: [taxon(90, "Carnivora", "order", 80)],
            },
          ],
        }),
      )
      // 11. Pick Carnivora → suborder.
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(90, "Carnivora", "order"),
          children: [taxon(100, "Feliformia", "suborder", 90)],
          next_tiers: [
            {
              rank: "suborder",
              label: "Suborder",
              examples: ["Feliformia"],
              children: [taxon(100, "Feliformia", "suborder", 90)],
            },
          ],
        }),
      )
      // 12. Pick Feliformia → family.
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(100, "Feliformia", "suborder"),
          children: [taxon(110, "Felidae", "family", 100)],
          next_tiers: [
            {
              rank: "family",
              label: "Family",
              examples: ["Felidae"],
              children: [taxon(110, "Felidae", "family", 100)],
            },
          ],
        }),
      )
      // 13. Pick Felidae → genus.
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(110, "Felidae", "family"),
          children: [taxon(120, "Panthera", "genus", 110)],
          next_tiers: [
            {
              rank: "genus",
              label: "Genus",
              examples: ["Panthera"],
              children: [taxon(120, "Panthera", "genus", 110)],
            },
          ],
        }),
      )
      // 14. Pick Panthera → species (leaf).
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(120, "Panthera", "genus"),
          children: [
            taxon(130, "Panthera leo", "species", 120),
            taxon(131, "Panthera tigris", "species", 120),
          ],
          next_tiers: null,
        }),
      )
      // 15. Species list endpoint.
      .mockResolvedValueOnce(
        mockFetchJson({
          items: [
            taxon(130, "Panthera leo", "species", 120),
            taxon(131, "Panthera tigris", "species", 120),
          ],
          next_cursor: null,
        }),
      );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const user = userEvent.setup();
    render(<Cascade />);

    // Walk every tier step-by-step.
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
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Subphylum" }),
      "Vertebrata",
    );
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Infraphylum" }),
      "Gnathostomata",
    );
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Parvphylum" }),
      "Osteichthyes",
    );
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Megaclass" }),
      "Tetrapoda",
    );
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Class" }),
      "Mammalia",
    );
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Subclass" }),
      "Theria",
    );
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Order" }),
      "Carnivora",
    );
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Suborder" }),
      "Feliformia",
    );
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Family" }),
      "Felidae",
    );
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Genus" }),
      "Panthera",
    );

    // The species list renders Panthera leo + Panthera tigris.
    const speciesList = await screen.findByRole("list");
    expect(within(speciesList).getByText("Panthera leo")).toBeInTheDocument();
    expect(within(speciesList).getByText("Panthera tigris")).toBeInTheDocument();
  });
});
