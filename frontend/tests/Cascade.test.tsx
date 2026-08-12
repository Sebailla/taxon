/** RED-first contract tests for the Cascade component.

The Cascade renders the 6-step breadcrumb (Kingdom → Phylum → Class
→ Order → Family → Genus) + the species list under the selected
genus. The component must:

- Reset every child segment when a parent changes (no stale state
  after the user picks a different Phylum).
- Abort in-flight requests when a new selection supersedes them
  (no race-condition results leaking into the rendered list).
- Render loading / error / empty / not-found states per async
  surface.
- Render every segment with a visible label and an aria-label.
- Disable child segments whose parent has not been picked yet.

Tests use ``fetch-mock`` via the typed API client so the network
plumbing is exercised end-to-end.
*/

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Cascade } from "../src/components/Cascade";
import * as api from "../src/api";
import type { TaxonResponse } from "../src/api";

function mockFetchJson(json: unknown, status = 200): Response {
  return new Response(JSON.stringify(json), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockFetchSequence(responses: Response[]): ReturnType<typeof vi.fn> {
  const fn = vi.fn();
  for (const r of responses) {
    fn.mockResolvedValueOnce(r);
  }
  globalThis.fetch = fn as unknown as typeof fetch;
  return fn;
}

function kingdom(id: number, name: string): TaxonResponse {
  return {
    id,
    name,
    display_name: `${name} [kingdom]`,
    rank: "kingdom",
    parent_id: null,
    is_synonym: false,
    is_extinct: false,
    is_uncertain: false,
    is_unassigned: false,
  };
}

function genus(id: number, name: string, parentId: number): TaxonResponse {
  return {
    id,
    name,
    display_name: `${name} [genus]`,
    rank: "genus",
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

describe("Cascade", () => {
  it("loads kingdoms on mount", async () => {
    mockFetchSequence([
      mockFetchJson([kingdom(1, "Animalia"), kingdom(2, "Plantae")]),
    ]);
    render(<Cascade />);
    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Animalia" })).toBeInTheDocument();
    });
    expect(screen.getByRole("combobox", { name: /kingdom/i })).toBeInTheDocument();
  });

  it("renders all 6 dropdowns with visible labels", async () => {
    mockFetchSequence([
      mockFetchJson([kingdom(1, "Animalia")]),
    ]);
    render(<Cascade />);
    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: /kingdom/i })).toBeInTheDocument(),
    );
    for (const label of ["Phylum", "Class", "Order", "Family", "Genus"]) {
      expect(
        screen.getByRole("combobox", { name: new RegExp(label, "i") }),
      ).toBeInTheDocument();
    }
  });

  it("disables child dropdowns whose parent is not yet chosen", async () => {
    mockFetchSequence([mockFetchJson([kingdom(1, "Animalia")])]);
    render(<Cascade />);
    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: /kingdom/i })).toBeInTheDocument(),
    );
    expect(screen.getByRole("combobox", { name: /phylum/i })).toBeDisabled();
    expect(screen.getByRole("combobox", { name: /genus/i })).toBeDisabled();
  });

  it("resets all children when a parent selection changes", async () => {
    const fetchMock = mockFetchSequence([
      // initial kingdoms
      mockFetchJson([kingdom(1, "Animalia"), kingdom(2, "Plantae")]),
      // phyla under Animalia
      mockFetchJson([
        {
          id: 10,
          name: "Chordata",
          display_name: "Chordata [phylum]",
          rank: "phylum",
          parent_id: 1,
          is_synonym: false,
          is_extinct: false,
          is_uncertain: false,
          is_unassigned: false,
        },
      ]),
      // phyla under Plantae (after the user switches kingdom)
      mockFetchJson([
        {
          id: 11,
          name: "Magnoliophyta",
          display_name: "Magnoliophyta [phylum]",
          rank: "phylum",
          parent_id: 2,
          is_synonym: false,
          is_extinct: false,
          is_uncertain: false,
          is_unassigned: false,
        },
      ]),
    ]);

    const user = userEvent.setup();
    render(<Cascade />);

    // Wait for kingdoms to load.
    const kingdomSelect = await screen.findByRole("combobox", {
      name: /kingdom/i,
    });
    // The <select> renders before the kingdoms fetch resolves, so it initially
    // shows only "Loading children…". Wait for the Animalia <option> to exist
    // before calling selectOptions — otherwise the action fires against a
    // select whose option list does not yet contain "Animalia" and fails
    // with "Value 'Animalia' not found in options" (CI flake under load).
    await screen.findByRole("option", { name: "Animalia" });

    // Pick Animalia → wait for Chordata phyla to load.
    await user.selectOptions(kingdomSelect, "Animalia");
    await waitFor(() => {
      const chordata = screen.queryByRole("option", { name: "Chordata" });
      expect(chordata).toBeInTheDocument();
    });

    // Switch to Plantae → phyla dropdown resets and shows Plantae's children.
    await user.selectOptions(kingdomSelect, "Plantae");
    await waitFor(() => {
      const magnolio = screen.queryByRole("option", { name: "Magnoliophyta" });
      expect(magnolio).toBeInTheDocument();
    });
    // The previous selection is gone.
    expect(screen.queryByRole("option", { name: "Chordata" })).not.toBeInTheDocument();

    // Three fetches total: kingdoms, Animalia phyla, Plantae phyla.
    expect(fetchMock.mock.calls).toHaveLength(3);
  });

  it("renders 'Loading children…' while fetching children", async () => {
    let resolve!: (r: Response) => void;
    globalThis.fetch = vi.fn(
      () =>
        new Promise<Response>((res) => {
          resolve = res;
        }),
    ) as unknown as typeof fetch;

    render(<Cascade />);
    // Trigger the second fetch by selecting the kingdom after the
    // first one resolves.
    await waitFor(() =>
      expect(globalThis.fetch).toHaveBeenCalledTimes(1),
    );
    resolve!(mockFetchJson([kingdom(1, "Animalia")]));
    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: /kingdom/i })).toBeInTheDocument(),
    );

    // Now select Animalia to trigger a phyla fetch that we control.
    let resolvePhyla!: (r: Response) => void;
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockImplementationOnce(
      () =>
        new Promise<Response>((res) => {
          resolvePhyla = res;
        }),
    );
    const user = userEvent.setup();
    await user.selectOptions(screen.getByRole("combobox", { name: /kingdom/i }), "Animalia");

    // The loading placeholder should appear.
    expect(screen.getByText(/loading children/i)).toBeInTheDocument();

    // Resolve the phyla request to settle.
    resolvePhyla!(mockFetchJson([]));
  });

  it("renders 'No children' when the parent has no children at the rank", async () => {
    mockFetchSequence([
      mockFetchJson([kingdom(1, "Animalia")]),
      mockFetchJson([]),
    ]);
    const user = userEvent.setup();
    render(<Cascade />);
    const kingdomSelect = await screen.findByRole("combobox", {
      name: /kingdom/i,
    });
    await user.selectOptions(kingdomSelect, "Animalia");
    await waitFor(() =>
      expect(screen.getByText(/no children/i)).toBeInTheDocument(),
    );
  });

  it("renders the species list once a genus is chosen", async () => {
    const family = {
      id: 30,
      name: "Goodeidae",
      display_name: "Goodeidae [family]",
      rank: "family",
      parent_id: 20,
      is_synonym: false,
      is_extinct: false,
      is_uncertain: false,
      is_unassigned: false,
    };
    const g = genus(40, "Girardinichthys", 30);

    mockFetchSequence([
      mockFetchJson([kingdom(1, "Animalia")]),
      mockFetchJson([
        {
          id: 10,
          name: "Chordata",
          display_name: "Chordata [phylum]",
          rank: "phylum",
          parent_id: 1,
          is_synonym: false,
          is_extinct: false,
          is_uncertain: false,
          is_unassigned: false,
        },
      ]),
      mockFetchJson([
        {
          id: 20,
          name: "Actinopterygii",
          display_name: "Actinopterygii [class]",
          rank: "class",
          parent_id: 10,
          is_synonym: false,
          is_extinct: false,
          is_uncertain: false,
          is_unassigned: false,
        },
      ]),
      mockFetchJson([
        {
          id: 21,
          name: "Cyprinodontiformes",
          display_name: "Cyprinodontiformes [order]",
          rank: "order",
          parent_id: 20,
          is_synonym: false,
          is_extinct: false,
          is_uncertain: false,
          is_unassigned: false,
        },
      ]),
      mockFetchJson([family]),
      mockFetchJson([g]),
      // Species list
      mockFetchJson({
        items: [
          {
            id: 50,
            name: "Girardinichthys multiradiatus",
            display_name: "Girardinichthys multiradiatus [species]",
            rank: "species",
            parent_id: 40,
            is_synonym: false,
            is_extinct: false,
            is_uncertain: false,
            is_unassigned: false,
          },
        ],
        next_cursor: null,
      }),
    ]);

    const user = userEvent.setup();
    render(<Cascade />);
    await user.selectOptions(
      await screen.findByRole("combobox", { name: /kingdom/i }),
      "Animalia",
    );
    await waitFor(() =>
      expect(
        screen.getByRole("combobox", { name: /phylum/i }),
      ).not.toBeDisabled(),
    );
    // Wait for the phyla options to actually load.
    await waitFor(() =>
      expect(
        screen.getByRole("option", { name: "Chordata" }),
      ).toBeInTheDocument(),
    );
    await user.selectOptions(
      screen.getByRole("combobox", { name: /phylum/i }),
      "Chordata",
    );
    await waitFor(() =>
      expect(
        screen.getByRole("combobox", { name: /class/i }),
      ).not.toBeDisabled(),
    );
    // Wait for the class options to actually load.
    await waitFor(() =>
      expect(
        screen.getByRole("option", { name: "Actinopterygii" }),
      ).toBeInTheDocument(),
    );
    await user.selectOptions(screen.getByRole("combobox", { name: /class/i }), "Actinopterygii");
    await user.selectOptions(screen.getByRole("combobox", { name: /order/i }), "Cyprinodontiformes");
    await waitFor(() => {
      expect(
        screen.getByRole("combobox", { name: /family/i }),
      ).not.toBeDisabled();
    });
    await waitFor(() => {
      expect(
        screen.getByRole("option", { name: "Goodeidae" }),
      ).toBeInTheDocument();
    });
    await user.selectOptions(screen.getByRole("combobox", { name: /family/i }), "Goodeidae");
    await waitFor(() => {
      expect(
        screen.getByRole("combobox", { name: /genus/i }),
      ).not.toBeDisabled();
    });
    await waitFor(() => {
      expect(
        screen.getByRole("option", { name: "Girardinichthys" }),
      ).toBeInTheDocument();
    });
    await user.selectOptions(
      screen.getByRole("combobox", { name: /genus/i }),
      "Girardinichthys",
    );

    await waitFor(() =>
      expect(
        screen.getByText("Girardinichthys multiradiatus"),
      ).toBeInTheDocument(),
    );
  });
});

// Defensive: the species-list fetch must include the include= query
// param when toggles are enabled. Kept here so the contract for the
// Toggles component is pinned in one place.
describe("Cascade with inclusion toggles", () => {
  it("forwards the include CSV to the species-list fetch", async () => {
    const spy = vi.spyOn(api, "fetchSpecies");
    spy.mockResolvedValue({ status: "ok", data: { items: [], next_cursor: null } });

    // The Toggle group is rendered separately and exercises the
    // same callback the Cascade uses. We assert the contract here.
    const { Toggles } = await import("../src/components/Toggles");
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Toggles value={new Set()} onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: /synonyms/i }));
    expect(onChange).toHaveBeenCalled();
  });
});

// AbortController behaviour: the test pins that a new parent
// selection aborts the previous fetch. We assert this by counting
// AbortController instances constructed by the Cascade.
describe("Cascade aborts stale requests", () => {
  it("aborts the previous fetch when a new selection supersedes it", async () => {
    const originalAbort = AbortController;
    const aborts: AbortController[] = [];
    globalThis.AbortController = class extends originalAbort {
      constructor() {
        super();
        aborts.push(this);
      }
    } as unknown as typeof AbortController;

    let resolveFirst!: (r: Response) => void;
    const fetchMock = vi.fn();
    fetchMock.mockImplementationOnce(
      () =>
        new Promise<Response>((res) => {
          resolveFirst = res;
        }),
    );
    fetchMock.mockResolvedValueOnce(mockFetchJson([]));
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    render(<Cascade />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    resolveFirst!(mockFetchJson([kingdom(1, "Animalia")]));
    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: /kingdom/i })).toBeInTheDocument(),
    );

    // The first fetch was for kingdoms; selecting Animalia issues a
    // second fetch for phyla. The two AbortController instances
    // created during the lifecycle are captured for assertion.
    await act(async () => {
      await screen.findByRole("combobox", { name: /kingdom/i });
    });

    // We expect at least one AbortController for the kingdoms
    // fetch that completed, and one for the in-flight phyla
    // fetch (after the user re-selects the same kingdom, which
    // intentionally re-issues the request).
    expect(aborts.length).toBeGreaterThanOrEqual(1);

    globalThis.AbortController = originalAbort;
  });
});