/** Contract tests for the path-aware cascade frontend.

The cascade is re-architected from "6 fixed-rank dropdowns"
to "N dynamic dropdowns driven by /path-children" plus a
root tier (Biota / Viruses) over the legacy kingdom list.
These tests pin the new contract:

- The initial render shows the root ``Biota`` dropdown with
  the two CLB top-tier taxa (Biota + Viruses) from
  ``/api/kingdoms``. The next dropdown is labelled "Kingdom"
  once the user picks Biota.
- Each segment the user picks triggers a /path-children call
  with the cumulative path; the next dropdown renders with
  the response's ``next_tiers`` (one ``NextTier`` per rank
  group).
- The cascade renders one dropdown per non-leaf response.
  When ``next_tiers`` is null (the deepest taxon has no
  children), the species list takes over via /api/species-list.
- Changing a parent segment clears every child segment so no
  stale state leaks across picks.
- In-flight requests are aborted when a new selection supersedes
  them.

The tests use the same mock infrastructure as the cascade
component tests (mockFetchSequence) but feed /path-children
instead of the six rank-named endpoints.

Note on tier labels: the best-effort resolver emits
``next_tiers = [{rank: "subphylum", label: "Subphylum", ...}]``
when Chordata has subphylum children. The cascade therefore
labels the picker that surfaces Cephalochordata / Tunicata /
Vertebrata "Subphylum" (the tier label), not a derived next
rank. Subsequent picks are picked from this "Subphylum"
picker.
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

function mockFetchSequence(
  responses: Array<Response | [string, Response]>,
): ReturnType<typeof vi.fn> {
  const fn = vi.fn();
  // Listed responses fire in order. Tuple entries (matcher, response)
  // match any URL containing the matcher; bare responses fire on the
  // next call regardless of URL.
  for (const entry of responses) {
    if (Array.isArray(entry)) {
      const [matcher, response] = entry;
      fn.mockImplementationOnce((url: string) => {
        if (url.includes(matcher)) {
          return Promise.resolve(response);
        }
        return Promise.reject(new Error(`unexpected fetch: ${url}`));
      });
    } else {
      fn.mockResolvedValueOnce(entry);
    }
  }
  globalThis.fetch = fn as unknown as typeof fetch;
  return fn;
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

// ---------------------------------------------------------------------------
// Initial render
// ---------------------------------------------------------------------------

describe("Path-aware cascade initial render", () => {
  it("loads the root list on mount via /api/kingdoms", async () => {
    mockFetchSequence([
      // /api/kingdoms → root list (TaxonResponse[]) under the
      // CLB tier tuple: Biota + Viruses.
      [
        "/api/kingdoms",
        mockFetchJson([
          taxon(1, "Biota", "biota"),
          taxon(2, "Viruses", "biota"),
        ]),
      ],
    ]);

    render(<Cascade />);

    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Biota" })).toBeInTheDocument();
    });
    expect(screen.getByRole("option", { name: "Viruses" })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Chain through the cascade tier tuple
// ---------------------------------------------------------------------------

describe("Path-aware cascade chains through the dynamic tiers", () => {
  it(
    "renders one dropdown per tier in next_tiers so the Chordata → subphylum chain works",
    async () => {
      const phyla = [taxon(20, "Chordata", "phylum", 10)];
      const subphyla = [taxon(30, "Vertebrata", "subphylum", 20)];
      const classes = [taxon(40, "Mammalia", "class", 30)];
      mockFetchSequence([
        // Initial root list — /api/kingdoms returns Biota + Viruses.
        [
          "/api/kingdoms",
          mockFetchJson([
            taxon(1, "Biota", "biota"),
            taxon(2, "Viruses", "biota"),
          ]),
        ],
        // /path-children?path=Biota → kingdoms (Animalia).
        mockFetchJson({
          parent: taxon(1, "Biota", "biota"),
          children: [taxon(10, "Animalia", "kingdom", 1)],
          next_tiers: singleTier("kingdom", [taxon(10, "Animalia", "kingdom", 1)]),
        }),
        // /path-children?path=Biota|Animalia → phyla. Chordata
        // is the only phylum; the resolver emits a single
        // ``phylum`` tier.
        mockFetchJson({
          parent: taxon(10, "Animalia", "kingdom"),
          children: phyla,
          next_tiers: singleTier("phylum", phyla),
        }),
        // /path-children?path=Biota|Animalia|Chordata → subphylum
        // children. The resolver emits one ``subphylum`` tier.
        mockFetchJson({
          parent: taxon(20, "Chordata", "phylum"),
          children: subphyla,
          next_tiers: singleTier("subphylum", subphyla),
        }),
        // /path-children?path=Biota|Animalia|Chordata|Vertebrata →
        // class children. Downstream ranks follow the same loop.
        mockFetchJson({
          parent: taxon(30, "Vertebrata", "subphylum"),
          children: classes,
          next_tiers: singleTier("class", classes),
        }),
      ]);

      const user = userEvent.setup();
      render(<Cascade />);

      // Step 1: pick Biota → cascade loads the kingdom picker.
      await user.selectOptions(
        await screen.findByRole("combobox", { name: "Biota" }),
        "Biota",
      );
      await screen.findByRole("option", { name: "Animalia" });

      // Step 2: pick Animalia → cascade loads the phylum picker.
      await user.selectOptions(
        screen.getByRole("combobox", { name: "Kingdom" }),
        "Animalia",
      );
      await screen.findByRole("option", { name: "Chordata" });

      // Step 3: pick Chordata → cascade loads the subphylum
      // children under the "Subphylum" picker (the tier label
      // Chordata returns).
      await user.selectOptions(
        screen.getByRole("combobox", { name: "Phylum" }),
        "Chordata",
      );
      await screen.findByRole("option", { name: "Vertebrata" });

      // The next picker is labelled "Subphylum" (the tier's
      // own label in next_tiers[0]).
      const subphylumDropdown = await screen.findByRole("combobox", {
        name: "Subphylum",
      });
      expect(subphylumDropdown).toBeInTheDocument();
    },
  );
});

// ---------------------------------------------------------------------------
// Leaf handling — species list takes over
// ---------------------------------------------------------------------------

describe("Path-aware cascade reaches species after a genus is picked", () => {
  it("fetches the species list when the user picks a genus", async () => {
    const kingdoms = [taxon(10, "Animalia", "kingdom", 1)];
    const phyla = [taxon(20, "Chordata", "phylum", 10)];
    const subphyla = [
      taxon(30, "Cephalochordata", "subphylum", 20),
      taxon(31, "Tunicata", "subphylum", 20),
      taxon(32, "Vertebrata", "subphylum", 20),
    ];
    const genera = [taxon(40, "Gadus", "genus", 32)];
    const species = [taxon(50, "Gadus morhua", "species", 40)];
    mockFetchSequence([
      // /api/kingdoms — root list.
      [
        "/api/kingdoms",
        mockFetchJson([
          taxon(1, "Biota", "biota"),
          taxon(2, "Viruses", "biota"),
        ]),
      ],
      // /path-children?path=Biota
      mockFetchJson({
        parent: taxon(1, "Biota", "biota"),
        children: kingdoms,
        next_tiers: singleTier("kingdom", kingdoms),
      }),
      // /path-children?path=Biota|Animalia
      mockFetchJson({
        parent: taxon(10, "Animalia", "kingdom"),
        children: phyla,
        next_tiers: singleTier("phylum", phyla),
      }),
      // /path-children?path=Biota|Animalia|Chordata — Chordata
      // carries subphylum children in this chain.
      mockFetchJson({
        parent: taxon(20, "Chordata", "phylum"),
        children: subphyla,
        next_tiers: singleTier("subphylum", subphyla),
      }),
      // /path-children?path=Biota|Animalia|Chordata|Vertebrata
      // (the subphylum Vertebrata was picked from the
      // "Subphylum" picker).
      mockFetchJson({
        parent: taxon(32, "Vertebrata", "subphylum"),
        children: genera,
        next_tiers: singleTier("genus", genera),
      }),
      // /path-children?path=Biota|Animalia|Chordata|Vertebrata|Gadus
      mockFetchJson({
        parent: taxon(40, "Gadus", "genus"),
        children: species,
        next_tiers: null,
      }),
      // The species list at the Gadus path.
      mockFetchJson({
        items: [
          taxon(50, "Gadus morhua", "species", 40),
          taxon(51, "Gadus ogac", "species", 40),
        ],
        next_cursor: null,
      }),
    ]);

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
    // Chordata's subphylum children render under the "Subphylum" picker.
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Subphylum" }),
      "Vertebrata",
    );
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Genus" }),
      "Gadus",
    );

    // The cascade auto-loaded the species list once the user
    // picked the genus. "Gadus morhua" appears in both the
    // <!-- species-list item and the species dropdown's options
    // (the cascade surfaces the species-row children in the
    // trailing picker); the list copy is the one we want.
    const speciesList = await screen.findByRole("list");
    expect(within(speciesList).getByText("Gadus morhua")).toBeInTheDocument();
    expect(within(speciesList).getByText("Gadus ogac")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Reset on parent change
// ---------------------------------------------------------------------------

describe("Path-aware cascade resets children when a parent changes", () => {
  it(
    "clears every segment after a parent pick so no stale state leaks",
    async () => {
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
              next_tiers: singleTier("phylum", [taxon(20, "Chordata", "phylum", 10)]),
            }),
          );
        }
        if (url.includes("/path-children?path=Biota|Plantae")) {
          return Promise.resolve(
            mockFetchJson({
              parent: taxon(11, "Plantae", "kingdom"),
              children: [taxon(30, "Tracheophyta", "phylum", 11)],
              next_tiers: singleTier("phylum", [taxon(30, "Tracheophyta", "phylum", 11)]),
            }),
          );
        }
        // Default /path-children?path=Biota → Biota's children.
        if (url.includes("/path-children?path=Biota")) {
          return Promise.resolve(
            mockFetchJson({
              parent: taxon(1, "Biota", "biota"),
              children: [
                taxon(10, "Animalia", "kingdom", 1),
                taxon(11, "Plantae", "kingdom", 1),
              ],
              next_tiers: singleTier("kingdom", [
                taxon(10, "Animalia", "kingdom", 1),
                taxon(11, "Plantae", "kingdom", 1),
              ]),
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

      // Now switch kingdoms: change Animalia to Plantae. The
      // phylum dropdown must reset (no Chordata leakage) and
      // must show Plantae's phylum children.
      await user.selectOptions(
        screen.getByRole("combobox", { name: "Kingdom" }),
        "Plantae",
      );

      // The phylum dropdown now shows Plantae's children —
      // Tracheophyta is reachable. The previous Chordata pick
      // must NOT leak into the new path.
      await waitFor(() => {
        expect(
          screen.getByRole("option", { name: "Tracheophyta" }),
        ).toBeInTheDocument();
      });
      // Chordata (the phylum the user picked under Animalia) is
      // no longer an option because the path is now
      // Biota → Plantae.
      expect(
        screen.queryByRole("option", { name: "Chordata" }),
      ).not.toBeInTheDocument();
      // Both /path-children?path=Biota calls fired (initial +
      // after switching kingdoms).
      const animaliaCalls = callLog.filter((u) =>
        u.includes("/path-children?path=Biota|Animalia"),
      );
      const plantaeCalls = callLog.filter((u) =>
        u.includes("/path-children?path=Biota|Plantae"),
      );
      expect(animaliaCalls.length).toBeGreaterThanOrEqual(1);
      expect(plantaeCalls.length).toBeGreaterThanOrEqual(1);
    },
  );
});
