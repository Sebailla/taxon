/** Contract tests for the cascade root tier.

The cascade frontend renders **exactly seven fixed dropdowns**:
Biota, Kingdom, Phylum, Class, Order, Family, Genus. The root
dropdown is the Biota picker; the next picker after a Biota
pick is the Kingdom dropdown populated with the CLB
kingdom-rank children.
*/

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Cascade } from "../src/components/Cascade";
import type { TaxonResponse } from "../src/api";
import { waitForEnabledOption } from "./test-helpers";

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

describe("Cascade root tier", () => {
  it("renders a 'Biota' dropdown with the two CLB roots on mount", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      mockFetchJson([
        taxon(1, "Biota", "biota"),
        taxon(2, "Viruses", "biota"),
      ]),
    );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    render(<Cascade />);

    // The first dropdown is labelled "Biota" and lists both CLB
    // top-tier taxa.
    const rootDropdown = await screen.findByRole("combobox", { name: "Biota" });
    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Biota" })).toBeInTheDocument();
    });
    expect(screen.getByRole("option", { name: "Viruses" })).toBeInTheDocument();
    expect(rootDropdown).toBeInTheDocument();
  });

  it("labels the next picker 'Kingdom' once Biota is picked", async () => {
    const fetchMock = vi
      .fn()
      // 1. Initial root fetch.
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
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const user = userEvent.setup();
    render(<Cascade />);

    await user.selectOptions(
      await waitForEnabledOption("Biota"),
      "Biota",
    );

    // The next picker is labelled "Kingdom" — the second of the
    // seven fixed dropdowns.
    const kingdomDropdown = await screen.findByRole("combobox", {
      name: "Kingdom",
    });
    expect(kingdomDropdown).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Animalia" })).toBeInTheDocument();
    });
    expect(screen.getByRole("option", { name: "Plantae" })).toBeInTheDocument();
  });
});
