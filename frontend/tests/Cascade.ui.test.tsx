/** UI contract tests for the path-aware Cascade.

These tests cover the orthogonal UI behaviour that
pathAware.test.tsx does not exercise directly:

- Loading state per dropdown.
- Empty children state at any depth.
- Inclusion-toggle forwarding to the species fetch.
- Loading the root tier on mount.
- Disabling the deepest dropdown while its children are in
  flight.

The mocks feed ``/path-children`` exclusively (the cascade no
longer calls the legacy six rank-named endpoints).
*/

import { act, render, screen, within } from "@testing-library/react";
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

    // Root dropdown is disabled while the initial /api/kingdoms
    // fetch is in flight (no mocked response yet).
    expect(
      screen.getByRole("combobox", { name: "Biota" }),
    ).toBeDisabled();

    // Resolve the root fetch. /api/kingdoms returns the two
    // CLB top-tier taxa (Biota, Viruses) under the new root tier.
    await act(async () => {
      resolveFetch!(
        mockFetchJson([
          taxon(1, "Biota", "biota"),
          taxon(2, "Viruses", "biota"),
        ]),
      );
    });

    // Now the root dropdown is enabled.
    expect(
      screen.getByRole("combobox", { name: "Biota" }),
    ).not.toBeDisabled();
  });

  it("renders 'No children' when the deepest taxon has no species children", async () => {
    // Mock Animalia's children to return empty. The cascade
    // classifies Animalia as a leaf (next_rank_hint = null) and
    // skips the species fetch (children are not species-rank),
    // then resets the species status to idle so the SpeciesList
    // renders the empty state.
    globalThis.fetch = vi
      .fn()
      // 1. /api/kingdoms (root tier).
      .mockResolvedValueOnce(
        mockFetchJson([
          taxon(1, "Biota", "biota"),
          taxon(2, "Viruses", "biota"),
        ]),
      )
      // 2. /path-children?path=Biota.
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(1, "Biota", "biota"),
          children: [taxon(10, "Animalia", "kingdom", 1)],
          next_rank_hint: "kingdom",
        }),
      )
      // 3. /path-children?path=Biota|Animalia — leaves.
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(10, "Animalia", "kingdom"),
          children: [],
          next_rank_hint: null,
        }),
      );

    const user = userEvent.setup();
    render(<Cascade />);

    // Wait for the kingdom option to land in the DOM before
    // attempting a select. ``findByRole("combobox")`` would
    // return the disabled placeholder select and the next
    // ``selectOptions`` call would fail.
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

    // Animalia is a leaf with no species children → the empty
    // state renders.
    expect(await screen.findByText("No children.")).toBeInTheDocument();
  });
});

describe("Cascade UI: inclusion toggles", () => {
  it("lands the species list fetch when the deepest taxon is a confirmed genus", async () => {
    // The chain for Gadus morhua is
    //   Biota → Animalia → Chordata → subphylum Vertebrata → … → Gadus
    // The path-aware cascade walks every segment the backend
    // returns, so the test stubs the full chain plus the
    // auto-fetched species list. ``mockResolvedValueOnce`` chains
    // the responses in firing order so the test is deterministic
    // regardless of which dropdown the user picks first.
    const fetchMock = vi
      .fn()
      // 1. Initial root fetch via /api/kingdoms.
      .mockResolvedValueOnce(
        mockFetchJson([
          taxon(1, "Biota", "biota"),
          taxon(2, "Viruses", "biota"),
        ]),
      )
      // 2. After picking Biota.
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(1, "Biota", "biota"),
          children: [taxon(10, "Animalia", "kingdom", 1)],
          next_rank_hint: "kingdom",
        }),
      )
      // 3. After picking Animalia.
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(10, "Animalia", "kingdom"),
          children: [taxon(20, "Chordata", "phylum", 10)],
          next_rank_hint: "phylum",
        }),
      )
      // 4. After picking Chordata → subphylum children (the
      //    resolver returns next_rank_hint = "class" because
      //    subphylum advances to class in the cascade tuple).
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(20, "Chordata", "phylum"),
          children: [taxon(30, "Vertebrata", "subphylum", 20)],
          next_rank_hint: "class",
        }),
      )
      // 5. After picking Vertebrata (from the "Class" picker)
      //    → genus Gadus (leaf).
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(30, "Vertebrata", "subphylum"),
          children: [taxon(40, "Gadus", "genus", 30)],
          next_rank_hint: "genus",
        }),
      )
      // 6. After picking Gadus → species Gadus morhua (leaf).
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(40, "Gadus", "genus"),
          children: [taxon(50, "Gadus morhua", "species", 40)],
          next_rank_hint: null,
        }),
      )
      // 7. Auto-fetched species list for Gadus.
      .mockResolvedValueOnce(
        mockFetchJson({
          items: [
            taxon(50, "Gadus morhua", "species", 40),
            taxon(51, "Gadus ogac", "species", 40),
          ],
          next_cursor: null,
        }),
      );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const user = userEvent.setup();
    render(<Cascade />);

    // Wait for each option to land before selecting. The dropdown
    // is rendered in the disabled state until the corresponding
    // path-children response resolves, so a plain
    // ``findByRole("combobox")`` would race the disabled
    // placeholder.
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
    await screen.findByRole("option", { name: "Chordata" });
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Phylum" }),
      "Chordata",
    );
    // Chordata returns subphylum children under the "Class" picker.
    await screen.findByRole("option", { name: "Vertebrata" });
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Class" }),
      "Vertebrata",
    );
    await screen.findByRole("option", { name: "Gadus" });
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Genus" }),
      "Gadus",
    );

    // The cascade auto-loaded the species list once the user
    // picked the genus. "Gadus morhua" appears in both the
    // species list and the species dropdown; the list copy is
    // the one we want.
    const speciesList = await screen.findByRole("list");
    expect(within(speciesList).getByText("Gadus morhua")).toBeInTheDocument();
    expect(within(speciesList).getByText("Gadus ogac")).toBeInTheDocument();
  });
});
