/** Contract tests for the cascade subphylum tier.

This file pins the cascade's behaviour when a /path-children call
returns ``next_tiers = [{rank: "subphylum", ...}]``. The CLB
resolver drops the ``rank=`` filter on the children fetch and
groups children by their actual CLB rank label; the wire envelope
exposes ``next_tiers`` (one ``NextTier`` per rank group) so the
cascade UI renders one dropdown per group with the dropdown
label taken from the tier's ``label`` field.

The cascade renders the chain with one dropdown per picked
segment plus a trailing picker for the next segment. The trailing
picker's label is the tier's ``label`` ("Subphylum" in this case)
and its options are the response's children (the three chordate
subphyla).
*/

import { render, screen, waitFor } from "@testing-library/react";
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

describe("Cascade subphylum tier renders next picker as 'Subphylum'", () => {
  it(
    "renders Biota → Animalia → Chordata → Subphylum with the response children",
    async () => {
      const fetchMock = vi
        .fn()
        // 1. Initial root fetch: Biota + Viruses.
        .mockResolvedValueOnce(
          mockFetchJson([
            taxon(1, "Biota", "biota"),
            taxon(2, "Viruses", "biota"),
          ]),
        )
        // 2. Pick Biota → root children (kingdom rank).
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
        // 4. Pick Chordata → subphylum children (Cephalochordata,
        //    Tunicata, Vertebrata). The best-effort resolver emits
        //    one ``NextTier`` per rank group.
        .mockResolvedValueOnce(
          mockFetchJson({
            parent: taxon(20, "Chordata", "phylum"),
            children: [
              taxon(30, "Cephalochordata", "subphylum", 20),
              taxon(31, "Tunicata", "subphylum", 20),
              taxon(32, "Vertebrata", "subphylum", 20),
            ],
            next_tiers: [
              {
                rank: "subphylum",
                label: "Subphylum",
                examples: [
                  "Cephalochordata",
                  "Tunicata",
                  "Vertebrata",
                ],
                children: [
                  taxon(30, "Cephalochordata", "subphylum", 20),
                  taxon(31, "Tunicata", "subphylum", 20),
                  taxon(32, "Vertebrata", "subphylum", 20),
                ],
              },
            ],
          }),
        );
      globalThis.fetch = fetchMock as unknown as typeof fetch;

      const user = userEvent.setup();
      render(<Cascade />);

      // Step 1: pick Biota in the root dropdown.
      await user.selectOptions(
        await screen.findByRole("combobox", { name: "Biota" }),
        "Biota",
      );
      // Step 2: pick Animalia in the Kingdom picker.
      await user.selectOptions(
        await screen.findByRole("combobox", { name: "Kingdom" }),
        "Animalia",
      );
      // Step 3: pick Chordata in the Phylum picker.
      await user.selectOptions(
        await screen.findByRole("combobox", { name: "Phylum" }),
        "Chordata",
      );

      // The trailing picker is labelled "Subphylum" (the tier
      // label the resolver returned in ``next_tiers[0]``) and
      // lists the three chordate subphyla.
      const subphylumDropdown = await screen.findByRole("combobox", {
        name: "Subphylum",
      });
      expect(subphylumDropdown).toBeInTheDocument();
      await waitFor(() => {
        expect(
          screen.getByRole("option", { name: "Cephalochordata" }),
        ).toBeInTheDocument();
      });
      expect(screen.getByRole("option", { name: "Tunicata" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "Vertebrata" })).toBeInTheDocument();
    },
  );
});
