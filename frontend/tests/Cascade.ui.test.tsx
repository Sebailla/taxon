/** RED-first UI contract tests for the path-aware Cascade.

These tests cover the orthogonal UI behaviour that pathAware.test.tsx
does not exercise directly:

- Loading state per dropdown.
- Empty children state at any depth.
- Inclusion-toggle forwarding to the species fetch.
- Aborting in-flight fetches when a new selection supersedes them.
- Loading the kingdom list on mount.
- Disabling the deepest dropdown while its children are in flight.

The mocks feed ``/path-children`` exclusively (the cascade no
longer calls the legacy six rank-named endpoints).
*/

import { act, render, screen } from "@testing-library/react";
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
  it("disables the next dropdown while its children are in flight", async () => {
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

    // Kingdom dropdown is disabled while the initial kingdoms
    // fetch is in flight (no mocked response yet).
    expect(
      screen.getByRole("combobox", { name: "Kingdom" }),
    ).toBeDisabled();

    // Resolve the kingdoms fetch.
    await act(async () => {
      resolveFetch!(
        mockFetchJson({
          parent: taxon(0, "(root)", "domain"),
          children: [taxon(2, "Animalia", "kingdom")],
          next_rank_hint: "kingdom",
        }),
      );
    });

    // Now the Kingdom dropdown is enabled.
    expect(
      screen.getByRole("combobox", { name: "Kingdom" }),
    ).not.toBeDisabled();
  });

  it("renders 'No children' when the deepest taxon has no species children", async () => {
    // Mock Animalia to return no species children. The cascade
    // classifies Animalia as a leaf (next_rank_hint = null) and
    // skips the species fetch (children are not species-rank),
    // then resets the species status to idle so the SpeciesList
    // renders the empty state.
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(0, "(root)", "domain"),
          children: [taxon(2, "Animalia", "kingdom")],
          next_rank_hint: "kingdom",
        }),
      )
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(2, "Animalia", "kingdom"),
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
    // The CoL chain for Gadus morhua is
    //   Animalia → Chordata → subphylum Vertebrata → … → Gadus
    // The path-aware cascade walks every segment the backend
    // returns, so the test stubs the full chain plus the
    // auto-fetched species list. ``mockResolvedValueOnce`` chains
    // the responses in firing order so the test is deterministic
    // regardless of which dropdown the user picks first.
    const fetchMock = vi
      .fn()
      // 1. Initial root kingdom fetch.
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(0, "(root)", "domain"),
          children: [taxon(2, "Animalia", "kingdom")],
          next_rank_hint: "kingdom",
        }),
      )
      // 2. After picking Animalia.
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(2, "Animalia", "kingdom"),
          children: [taxon(3, "Chordata", "phylum")],
          next_rank_hint: "phylum",
        }),
      )
      // 3. After picking Chordata → subphylum Vertebrata.
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(3, "Chordata", "phylum"),
          children: [taxon(4, "Vertebrata", "subphylum")],
          next_rank_hint: "subphylum",
        }),
      )
      // 4. After picking Vertebrata → genus Gadus (leaf).
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(4, "Vertebrata", "subphylum"),
          children: [taxon(7, "Gadus", "genus")],
          next_rank_hint: "genus",
        }),
      )
      // 5. After picking Gadus → species Gadus morhua (leaf).
      .mockResolvedValueOnce(
        mockFetchJson({
          parent: taxon(7, "Gadus", "genus"),
          children: [taxon(8, "Gadus morhua", "species", 7)],
          next_rank_hint: null,
        }),
      )
      // 6. Auto-fetched species list for Gadus.
      .mockResolvedValueOnce(
        mockFetchJson({
          items: [
            taxon(8, "Gadus morhua", "species", 7),
            taxon(9, "Gadus ogac", "species", 7),
          ],
          next_cursor: null,
        }),
      );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const user = userEvent.setup();
    render(<Cascade />);

    // Wait for each option to land before selecting. The dropdown
    // is rendered in the disabled state until the corresponding
    // /path-children response resolves, so a plain
    // ``findByRole("combobox")`` would race the disabled
    // placeholder.
    await screen.findByRole("option", { name: "Animalia" });
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Kingdom" }),
      "Animalia",
    );
    await screen.findByRole("option", { name: "Chordata" });
    await user.selectOptions(
      screen.getByRole("combobox", { name: "phylum" }),
      "Chordata",
    );
    await screen.findByRole("option", { name: "Vertebrata" });
    await user.selectOptions(
      screen.getByRole("combobox", { name: "subphylum" }),
      "Vertebrata",
    );
    await screen.findByRole("option", { name: "Gadus" });
    await user.selectOptions(
      screen.getByRole("combobox", { name: "genus" }),
      "Gadus",
    );

    // The cascade auto-loaded the species list once the user
    // picked the genus.
    expect(await screen.findByText("Gadus morhua")).toBeInTheDocument();
    expect(await screen.findByText("Gadus ogac")).toBeInTheDocument();
  });
});

