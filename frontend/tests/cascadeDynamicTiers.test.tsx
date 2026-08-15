/** Contract tests for the 7-fixed-tier cascade.

The cascade always renders **exactly 7 dropdowns** in this fixed order:

  1. Biota       — populated from ``GET /api/kingdoms``.
  2. Kingdom     — children of the picked Biota whose ``rank === "kingdom"``.
  3. Phylum      — children of the picked Kingdom whose ``rank === "phylum"``.
  4. Class       — children of the picked Phylum whose ``rank === "class"``.
  5. Order       — children of the picked Class whose ``rank === "order"``.
  6. Family      — children of the picked Order whose ``rank === "family"``.
  7. Genus       — children of the picked Family whose ``rank === "genus"``.

When the picked parent does not have children at the rank the next
dropdown expects, that dropdown stays rendered but is **disabled** with
a "No <rank> available" placeholder. CoL inter-tier intermediates
(subphylum, infraphylum, ...) never appear as dropdowns — they only
shape the path the backend walks internally.

The species list shows up under the Genus dropdown when the picked
genus has species-rank children (``next_tiers === null`` and the
snapshot contains at least one ``species`` row).

Clicking a species emits ``taxon-select`` so the parent ``App``
component can show the breadcrumb + the 12-link dispatch panel on
the right column.
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

const FIXED_LABELS = ["Biota", "Kingdom", "Phylum", "Class", "Order", "Family", "Genus"];

/** Assert the cascade currently renders exactly the 7 fixed dropdowns. */
async function expectSevenFixedDropdowns(): Promise<void> {
  for (const label of FIXED_LABELS) {
    expect(
      await screen.findByRole("combobox", { name: label }),
      `expected a "${label}" dropdown to be rendered`,
    ).toBeInTheDocument();
  }
  // No tier outside the fixed seven should ever appear.
  const dropdowns = await screen.findAllByRole("combobox");
  expect(dropdowns).toHaveLength(7);
}

describe("Cascade — always 7 fixed dropdowns", () => {
  it("renders exactly the seven fixed dropdowns on first paint", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      mockFetchJson([
        taxon(1, "Biota", "biota"),
        taxon(2, "Viruses", "biota"),
      ]),
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    render(<Cascade />);

    await expectSevenFixedDropdowns();

    // Only Biota is enabled — Kingdom and below wait for a Biota pick.
    const biota = screen.getByRole("combobox", { name: "Biota" });
    expect(biota).toBeEnabled();
    for (const label of ["Kingdom", "Phylum", "Class", "Order", "Family", "Genus"]) {
      expect(
        screen.getByRole("combobox", { name: label }),
        `${label} should be disabled before Biota is picked`,
      ).toBeDisabled();
    }
  });

  it("Phylum without subphylum: Class populates immediately with the phylum's class children", async () => {
    // Arthropoda has no subphylum, so the backend returns only a
    // "class" tier for Arthropoda's children. The Class dropdown
    // must populate without forcing the user through a subphylum.
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
      // Arthropoda's children are class-rank only (subphylum collapse).
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(20, "Arthropoda", "phylum"),
          children: [
            taxon(30, "Insecta", "class", 20),
            taxon(31, "Arachnida", "class", 20),
          ],
          next_tiers: [
            {
              rank: "class",
              label: "Class",
              examples: ["Insecta", "Arachnida"],
              children: [
                taxon(30, "Insecta", "class", 20),
                taxon(31, "Arachnida", "class", 20),
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
      "Arthropoda",
    );

    // Class dropdown is populated immediately — no subphylum to pass through.
    const classDropdown = await screen.findByRole("combobox", { name: "Class" });
    await waitFor(() => {
      expect(
        within(classDropdown).getByRole("option", { name: "Insecta" }),
      ).toBeInTheDocument();
      expect(
        within(classDropdown).getByRole("option", { name: "Arachnida" }),
      ).toBeInTheDocument();
    });

    // Order / Family / Genus remain disabled (Insecta not picked yet).
    expect(screen.getByRole("combobox", { name: "Order" })).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "Family" })).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "Genus" })).toBeDisabled();

    // Still exactly seven dropdowns — no extra tier rendered.
    expect(await screen.findAllByRole("combobox")).toHaveLength(7);
  });

  it("Phylum with subphylum: Class stays disabled until subphylum is picked", async () => {
    // Chordata has subphylum children. The backend returns ONLY the
    // subphylum tier (no class tier) — so the Class dropdown must
    // remain disabled until the user picks a subphylum.
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
      // Chordata's children are subphylum-rank only.
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

    // Class dropdown is rendered but disabled — backend did not emit a
    // "class" tier for Chordata (the subphylum collapse only fires
    // when the phylum has NO subphylum). The user must pick a
    // subphylum before the Class dropdown can populate.
    const classDropdown = screen.getByRole("combobox", { name: "Class" });
    expect(classDropdown).toBeDisabled();

    // Order / Family / Genus are also still disabled.
    expect(screen.getByRole("combobox", { name: "Order" })).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "Family" })).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "Genus" })).toBeDisabled();

    // The seven fixed dropdowns are still rendered (no Subphylum
    // picker — subphylum is one of the tiers the backend hides inside
    // the path walk).
    expect(await screen.findAllByRole("combobox")).toHaveLength(7);
  });

  it("Family without genus-rank children: Genus dropdown is disabled", async () => {
    // Pick a path that walks into a family with zero genus children.
    // The backend returns next_tiers: null for the family row (leaf)
    // OR returns no genus tier — in either case the Genus dropdown
    // must stay rendered but disabled, and the species list must not
    // show (the family has no genera → no species either).
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
          // Curculionidae is the family-rank child Coleoptera exposes.
          // The next_tiers points to the "family" tier so the
          // slot-5 (Family) dropdown can populate with it.
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
      // Picking Curculionidae resolves to a family-rank leaf with
      // no genus children — the genus dropdown must stay disabled.
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(50, "Curculionidae", "family"),
          children: [],
          next_tiers: null,
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
    // Wait for the Family dropdown to populate with Curculionidae
    // — the /path-children fetch for Coleoptera is in flight after
    // the Order pick, and the Family dropdown is loading until it
    // resolves.
    const familyDropdown = await screen.findByRole("combobox", { name: "Family" });
    await waitFor(() => {
      expect(
        within(familyDropdown).getByRole("option", { name: "Curculionidae" }),
      ).toBeInTheDocument();
    });
    await user.selectOptions(familyDropdown, "Curculionidae");

    // Genus dropdown rendered but disabled.
    const genusDropdown = screen.getByRole("combobox", { name: "Genus" });
    expect(genusDropdown).toBeDisabled();

    // No species list visible.
    expect(screen.queryByRole("list", { name: /species list/i })).not.toBeInTheDocument();

    // Still exactly seven dropdowns.
    expect(await screen.findAllByRole("combobox")).toHaveLength(7);
  });

  it("full chain: Biota → Animalia → Arthropoda → ... → Sitophilus → species list", async () => {
    // Walks the full chain with the seven-dropdown rule.
    // Arthropoda has no subphylum, so the path goes straight from
    // Phylum to Class. Walks: Biota → Animalia → Arthropoda (phylum)
    // → Insecta (class) → Coleoptera (order) → Curculionidae (family)
    // → Sitophilus (genus) → species list.
    const fetchMock = vi
      .fn()
      // 1. Root.
      .mockResolvedValueOnce(
        mockFetchJson([
          taxon(1, "Biota", "biota"),
          taxon(2, "Viruses", "biota"),
        ]),
      )
      // 2. Biota → kingdom.
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
      // 3. Animalia → phylum.
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
      // 4. Arthropoda → class (no subphylum).
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
      // 5. Insecta → order.
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
      // 6. Coleoptera → family.
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
      // 7. Curculionidae → genus.
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
      // 8. Sitophilus → species (leaf).
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
      // 9. Species list fetch.
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

    // Walk the seven fixed dropdowns in order.
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
    // Wait for the Family dropdown to populate with Curculionidae
    // — the /path-children fetch for Coleoptera is in flight after
    // the Order pick, and the Family dropdown is loading until it
    // resolves.
    const familyDropdown = await screen.findByRole("combobox", { name: "Family" });
    await waitFor(() => {
      expect(
        within(familyDropdown).getByRole("option", { name: "Curculionidae" }),
      ).toBeInTheDocument();
    });
    await user.selectOptions(familyDropdown, "Curculionidae");
    // Wait for the Genus dropdown to populate with Sitophilus.
    const genusDropdown = await screen.findByRole("combobox", { name: "Genus" });
    await waitFor(() => {
      expect(
        within(genusDropdown).getByRole("option", { name: "Sitophilus" }),
      ).toBeInTheDocument();
    });
    await user.selectOptions(genusDropdown, "Sitophilus");

    // Species list renders both Sitophilus species.
    const speciesList = await screen.findByRole("list", { name: /species list/i });
    expect(within(speciesList).getByText("Sitophilus granarius")).toBeInTheDocument();
    expect(within(speciesList).getByText("Sitophilus oryzae")).toBeInTheDocument();
  });

  it("clicking a species row emits a taxon-select event with the parent segments", async () => {
    // Same shape as the full-chain test, plus a click on the first
    // species row. We assert the dispatched event carries the parent
    // segments so the App component can fetch the 12-link dispatch.
    const dispatchSpy = vi.spyOn(window, "dispatchEvent");

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
          children: [taxon(70, "Sitophilus granarius", "species", 60)],
          next_tiers: null,
        }),
      )
      .mockResolvedValueOnce(
        mockFetchJson({
          items: [taxon(70, "Sitophilus granarius", "species", 60)],
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
    // Wait for the Family dropdown to populate with Curculionidae
    // — the /path-children fetch for Coleoptera is in flight after
    // the Order pick, and the Family dropdown is loading until it
    // resolves.
    const familyDropdown = await screen.findByRole("combobox", { name: "Family" });
    await waitFor(() => {
      expect(
        within(familyDropdown).getByRole("option", { name: "Curculionidae" }),
      ).toBeInTheDocument();
    });
    await user.selectOptions(familyDropdown, "Curculionidae");
    // Wait for the Genus dropdown to populate with Sitophilus.
    const genusDropdown = await screen.findByRole("combobox", { name: "Genus" });
    await waitFor(() => {
      expect(
        within(genusDropdown).getByRole("option", { name: "Sitophilus" }),
      ).toBeInTheDocument();
    });
    await user.selectOptions(genusDropdown, "Sitophilus");

    const speciesList = await screen.findByRole("list", { name: /species list/i });
    await user.click(within(speciesList).getByText("Sitophilus granarius"));

    // The Cascade dispatches a `taxon-select` CustomEvent with the
    // parent segments in its detail. The App component listens for
    // this event and fetches the links panel.
    const taxonSelectEvent = dispatchSpy.mock.calls
      .map((call) => call[0])
      .find((evt) => evt instanceof CustomEvent && evt.type === "taxon:select") as
      | CustomEvent
      | undefined;
    expect(taxonSelectEvent).toBeDefined();
    const detail = (taxonSelectEvent as CustomEvent).detail as {
      row: { name: string };
      parentSegments: string[];
      breadcrumb: string[];
    };
    expect(detail.row.name).toBe("Sitophilus granarius");
    expect(detail.parentSegments).toEqual([
      "Biota",
      "Animalia",
      "Arthropoda",
      "Insecta",
      "Coleoptera",
      "Curculionidae",
      "Sitophilus",
    ]);
    // Breadcrumb drops the Biota root by convention.
    expect(detail.breadcrumb).toEqual([
      "Animalia",
      "Arthropoda",
      "Insecta",
      "Coleoptera",
      "Curculionidae",
      "Sitophilus",
    ]);
  });
});
