/** Contract tests for the cascade subphylum aggregation rule.

When a phylum has subphylum children, the backend descends into
every subphylum and aggregates the class-rank children into a
single ``class`` tier (the **phylum class aggregation** rule). The
cascade UI therefore never renders a Subphylum dropdown — the
seven fixed slots (Biota, Kingdom, Phylum, Class, Order, Family,
Genus) absorb the subphylum hierarchy. After picking a phylum
that has subphylum children, the Class dropdown stays disabled
until the backend returns the aggregated class list.
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

describe("Cascade phylum class aggregation", () => {
  it(
    "Chordata's subphylum children never surface as a Subphylum dropdown",
    async () => {
      // The backend, after the phylum class aggregation rule,
      // returns every class under Chordata's subphyla as a single
      // ``class`` tier. The cascade UI renders exactly the seven
      // fixed dropdowns — no Subphylum picker.
      const fetchMock = vi
        .fn()
        // 1. Initial root fetch: Biota + Viruses.
        .mockResolvedValueOnce(
          mockFetchJson([
            taxon(1, "Biota", "biota"),
            taxon(2, "Viruses", "biota"),
          ]),
        )
        // 2. Pick Biota → kingdom-rank children.
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
        // 3. Pick Animalia → phyla (Chordata).
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
        // 4. Pick Chordata → the backend aggregates every class
        //    under every subphylum into a single ``class`` tier.
        //    The cascade renders the Class dropdown populated
        //    with Mammalia, Aves, Reptilia, ... regardless of
        //    how many subphyla sit between them.
        .mockResolvedValueOnce(
          mockFetchJson({
            parent: taxon(20, "Chordata", "phylum"),
            children: [
              taxon(30, "Mammalia", "class", 20),
              taxon(31, "Aves", "class", 20),
              taxon(32, "Reptilia", "class", 20),
            ],
            next_tiers: [
              {
                rank: "class",
                label: "Class",
                examples: ["Mammalia", "Aves", "Reptilia"],
                children: [
                  taxon(30, "Mammalia", "class", 20),
                  taxon(31, "Aves", "class", 20),
                  taxon(32, "Reptilia", "class", 20),
                ],
              },
            ],
          }),
        );
      globalThis.fetch = fetchMock as unknown as typeof fetch;

      const user = userEvent.setup();
      render(<Cascade />);

      // Walk to Phylum.
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

      // The Class dropdown is populated with the aggregated
      // classes. The subphylum hierarchy is invisible — no
      // Subphylum picker exists.
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
        within(classDropdown).getByRole("option", { name: "Reptilia" }),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("combobox", { name: "Subphylum" }),
      ).not.toBeInTheDocument();
    },
  );
});
