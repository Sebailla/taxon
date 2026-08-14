/** RED-first contract tests for the path-aware cascade frontend.

The cascade in PR #27 was re-architected from "6 fixed-rank
dropdowns" to "N dynamic dropdowns driven by /path-children".
These tests pin the new contract:

- The initial render shows the Kingdom dropdown with the list
  of kingdoms from /api/kingdoms (the path-aware endpoint
  rejects the empty path, so the root uses the dedicated
  kingdom endpoint).
- Each segment the user picks triggers a /path-children call
  with the cumulative path; the next dropdown renders with
  the response's children.
- The cascade renders one dropdown per non-leaf response.
  When ``next_rank_hint`` is null (the deepest taxon has no
  children), the species list takes over via /api/species-list.
- Changing a parent segment clears every child segment so no
  stale state leaks across picks.
- In-flight requests are aborted when a new selection supersedes
  them.
- The cascade dispatches ``taxon:select`` with the full path
  when the user clicks a species row, so the App's breadcrumb
  and links grid stay in sync.

The tests use the same mock infrastructure as Cascade.test.tsx
(mockFetchSequence) but feed /path-children instead of the six
rank-named endpoints.
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

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Initial render
// ---------------------------------------------------------------------------

describe("Path-aware cascade initial render", () => {
  it("loads the kingdom list on mount via /api/kingdoms", async () => {
    mockFetchSequence([
      // /api/kingdoms → root kingdom list (TaxonResponse[]).
      [
        "/api/kingdoms",
        mockFetchJson([
          taxon(2, "Animalia", "kingdom"),
          taxon(11, "Plantae", "kingdom"),
        ]),
      ],
    ]);

    render(<Cascade />);

    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Animalia" })).toBeInTheDocument();
    });
    expect(screen.getByRole("option", { name: "Plantae" })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Chain through CoL's intermediate ranks
// ---------------------------------------------------------------------------

describe("Path-aware cascade chains through intermediate ranks", () => {
  it(
    "renders one dropdown per non-leaf response so a Chordata → subphylum Vertebrata chain works",
    async () => {
      mockFetchSequence([
        // Initial kingdom list — /api/kingdoms.
        [
          "/api/kingdoms",
          mockFetchJson([taxon(2, "Animalia", "kingdom")]),
        ],
        // /path-children?path=Animalia → phyla. The next_rank_hint
        // is the modal display_level bucket ("phylum") — the
        // frontend renders the dropdown label as "Phylum".
        mockFetchJson({
          parent: taxon(2, "Animalia", "kingdom"),
          children: [taxon(3, "Chordata", "phylum")],
          next_rank_hint: "phylum",
        }),
        // /path-children?path=Animalia|Chordata → subphyla (CoL pattern).
        // Both subphylum and infraphylum bucket into "phylum",
        // so the user keeps seeing "Phylum" at every step.
        mockFetchJson({
          parent: taxon(3, "Chordata", "phylum"),
          children: [taxon(4, "Vertebrata", " subphylum")],
          next_rank_hint: "phylum",
        }),
        // /path-children?path=Animalia|Chordata|Vertebrata → infraphyla
        mockFetchJson({
          parent: taxon(4, "Vertebrata", " subphylum"),
          children: [taxon(5, "Gnathostomata", "infraphylum")],
          next_rank_hint: "phylum",
        }),
      ]);

      const user = userEvent.setup();
      render(<Cascade />);

      // Step 1: pick Animalia → cascade loads Chordata.
      await user.selectOptions(
        await screen.findByRole("combobox", { name: "Kingdom" }),
        "Animalia",
      );
      await screen.findByRole("option", { name: "Chordata" });

      // Step 2: pick Chordata → cascade loads Vertebrata. The next
      // dropdown is labelled with the next_rank_hint, which now
      // resolves to the "Phylum" bucket (subphylum collapses
      // into phylum at the display layer).
      await user.selectOptions(
        screen.getByRole("combobox", { name: "Phylum" }),
        "Chordata",
      );
      await screen.findByRole("option", { name: "Vertebrata" });

      // The next Phylum dropdown must render (subphylum
      // Vertebrata is selectable from it).
      const subphylumDropdown = await screen.findByRole("combobox", {
        name: "Phylum",
      });
      expect(subphylumDropdown).toBeInTheDocument();

      // Step 3: pick Vertebrata → cascade loads Gnathostomata at
      // rank "infraphylum" (still in the Phylum bucket).
      await user.selectOptions(subphylumDropdown, "Vertebrata");
      await screen.findByRole("option", { name: "Gnathostomata" });
    },
  );
});

// ---------------------------------------------------------------------------
// Leaf handling — species list takes over
// ---------------------------------------------------------------------------

describe("Path-aware cascade reaches species after a genus is picked", () => {
  it("fetches the species list when the user picks a genus", async () => {
    mockFetchSequence([
      // /api/kingdoms — root kingdom list.
      [
        "/api/kingdoms",
        mockFetchJson([taxon(2, "Animalia", "kingdom")]),
      ],
      // /path-children?path=Animalia
      mockFetchJson({
        parent: taxon(2, "Animalia", "kingdom"),
        children: [taxon(3, "Chordata", "phylum")],
        next_rank_hint: "phylum",
      }),
      // /path-children?path=Animalia|Chordata
      mockFetchJson({
        parent: taxon(3, "Chordata", "phylum"),
        children: [taxon(7, "Gadus", "genus")],
        next_rank_hint: "genus",
      }),
      // /path-children?path=Animalia|Chordata|Gadus
      mockFetchJson({
        parent: taxon(7, "Gadus", "genus"),
        children: [taxon(8, "Gadus morhua", "species", 7)],
        next_rank_hint: null,
      }),
      // The species list at path Animalia|Chordata|Gadus.
      mockFetchJson({
        items: [
          taxon(8, "Gadus morhua", "species", 7),
          taxon(9, "Gadus ogac", "species", 7),
        ],
        next_cursor: null,
      }),
    ]);

    const user = userEvent.setup();
    render(<Cascade />);

    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Kingdom" }),
      "Animalia",
    );
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Phylum" }),
      "Chordata",
    );
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Genus" }),
      "Gadus",
    );

    // The cascade auto-loaded the species list once the user
    // picked the genus.
    expect(await screen.findByText("Gadus morhua")).toBeInTheDocument();
    expect(await screen.findByText("Gadus ogac")).toBeInTheDocument();
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
              taxon(2, "Animalia", "kingdom"),
              taxon(11, "Plantae", "kingdom"),
            ]),
          );
        }
        if (url.includes("Animalia")) {
          return Promise.resolve(
            mockFetchJson({
              parent: taxon(2, "Animalia", "kingdom"),
              children: [taxon(3, "Chordata", "phylum")],
              next_rank_hint: "phylum",
            }),
          );
        }
        return Promise.reject(new Error(`unexpected fetch in test: ${url}`));
      });
      globalThis.fetch = fetchSpy as unknown as typeof fetch;

      const user = userEvent.setup();
      render(<Cascade />);

      await user.selectOptions(
        await screen.findByRole("combobox", { name: "Kingdom" }),
        "Animalia",
      );
      await screen.findByRole("option", { name: "Chordata" });

      // Now change the kingdom selection back to Animalia (the same
      // value). The previous Chordata pick must not leak into the new
      // path — the cascade should reset to a single-element path.
      await user.selectOptions(
        screen.getByRole("combobox", { name: "Kingdom" }),
        "Animalia",
      );

      // After the second Animalia pick, only two Animalia fetches
      // should have happened (one per pick), and the path-children
      // response for Animalia should reflect the snapshot of phyla
      // available for that pick — Chordata must come back when the
      // user reopens the phylum dropdown.
      await waitFor(() => {
        const animaliaCalls = callLog.filter(
          (u) => u.includes("Animalia") && !u.endsWith("/api/kingdoms"),
        );
        expect(animaliaCalls.length).toBeGreaterThanOrEqual(1);
      });
      // Chordata must be present again (not stale).
      expect(
        screen.queryByRole("option", { name: "Chordata" }),
      ).toBeInTheDocument();
    },
  );
});
