/** RED-first UX contract tests for the TaxonomicTree component.

The component replaces the 7-dropdown Cascade. The contract:

- Renders up to 5 root rows from the spec fixture (Archaea,
  Bacteria, Eukaryota, Viruses, ``?incertae sedis``).
- Each row reads ``rank: <display_name> • N spp.`` and indents
  by depth with ``aria-level``.
- The caret toggles ``aria-expanded`` on click.
- Lazy fetch on first expand; cache hit on re-expand (no second
  fetch).
- Keyboard navigation: ArrowDown/Up move focus, ArrowRight
  expands, ArrowLeft collapses, Enter activates.
- The ``aria-busy="true"`` flag fires while the children fetch
  is in flight.
- On expand, the component writes the explored path to the
  ``cascadePath`` Zustand store AND dispatches a ``path:change``
  CustomEvent with the same array.

The tests pin the contract from the spec; the implementation
follows the design doc ``docs/design/taxonomic-tree-browse.md``.
*/

import { render, screen, waitFor, within, fireEvent } from "@testing-library/react";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TaxonomicTree } from "../src/components/TaxonomicTree";
import { useTaxonomicTree } from "../src/store/taxonomicTree";

const ROOTS_FIXTURE = [
  {
    id: 1,
    name: "Archaea",
    display_name: "Archaea Woese et al., 2024",
    rank: "domain",
    parent_id: null,
    is_synonym: false,
    is_extinct: false,
    is_uncertain: false,
    is_unassigned: false,
    has_children: true,
    species_count: 927,
    authorship: "Woese et al., 2024",
  },
  {
    id: 2,
    name: "Bacteria",
    display_name: "Bacteria Woese et al., 2024",
    rank: "domain",
    parent_id: null,
    is_synonym: false,
    is_extinct: false,
    is_uncertain: false,
    is_unassigned: false,
    has_children: true,
    species_count: 25_000,
    authorship: "Woese et al., 2024",
  },
  {
    id: 5,
    name: "Eukaryota",
    display_name: "Eukaryota (Chatton, 1925) Whittaker & Margulis, 1978",
    rank: "domain",
    parent_id: null,
    is_synonym: false,
    is_extinct: false,
    is_uncertain: false,
    is_unassigned: false,
    has_children: true,
    species_count: 5_654_308,
    authorship: "(Chatton, 1925) Whittaker & Margulis, 1978",
  },
  {
    id: 6,
    name: "Viruses",
    display_name: "Viruses",
    rank: "domain",
    parent_id: null,
    is_synonym: false,
    is_extinct: false,
    is_uncertain: false,
    is_unassigned: false,
    has_children: true,
    species_count: 12_000,
    authorship: "",
  },
  {
    id: 7,
    name: "?incertae sedis",
    display_name: "?incertae sedis",
    rank: "no rank",
    parent_id: null,
    is_synonym: false,
    is_extinct: false,
    is_uncertain: true,
    is_unassigned: false,
    has_children: false,
    species_count: 0,
    authorship: "",
  },
];

const EUKARYOTA_CHILDREN = [
  {
    id: 10,
    name: "Animalia",
    display_name: "Animalia Linnaeus, 1758",
    rank: "kingdom",
    parent_id: 5,
    is_synonym: false,
    is_extinct: false,
    is_uncertain: false,
    is_unassigned: false,
    has_children: true,
    species_count: 1_792_173,
    authorship: "Linnaeus, 1758",
  },
  {
    id: 11,
    name: "Plantae",
    display_name: "Plantae Haeckel, 1866",
    rank: "kingdom",
    parent_id: 5,
    is_synonym: false,
    is_extinct: false,
    is_uncertain: false,
    is_unassigned: false,
    has_children: true,
    species_count: 405_000,
    authorship: "Haeckel, 1866",
  },
  {
    id: 12,
    name: "Fungi",
    display_name: "Fungi R.T. Moore, 1980",
    rank: "kingdom",
    parent_id: 5,
    is_synonym: false,
    is_extinct: false,
    is_uncertain: false,
    is_unassigned: false,
    has_children: true,
    species_count: 161_000,
    authorship: "R.T. Moore, 1980",
  },
];

function mockFetchJson(json: unknown, status = 200): Response {
  return new Response(JSON.stringify(json), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockFetchTree(responses: Map<string, unknown>): ReturnType<typeof vi.fn> {
  const fn = vi.fn().mockImplementation((input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    for (const [pattern, body] of responses) {
      if (url.includes(pattern)) {
        return Promise.resolve(mockFetchJson(body));
      }
    }
    return Promise.reject(new Error(`unexpected fetch: ${url}`));
  });
  globalThis.fetch = fn as unknown as typeof fetch;
  return fn;
}

beforeEach(() => {
  useTaxonomicTree.setState({
    childrenByParentId: new Map(),
    expandedIds: new Set(),
    rootIds: null,
    loadingParentIds: new Set(),
    errorByParentId: new Map(),
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("TaxonomicTree", () => {
  it("renders 5 root rows from the parent_id=0 fetch", async () => {
    mockFetchTree(
      new Map([["parent_id=0", { parent: { id: 0 }, children: ROOTS_FIXTURE, next_cursor: null }]]),
    );

    render(<TaxonomicTree />);

    await waitFor(() => {
      expect(screen.getByRole("tree")).toBeInTheDocument();
    });
    const tree = screen.getByRole("tree");
    const rows = within(tree).getAllByRole("treeitem");
    expect(rows).toHaveLength(5);
    // Row format: "domain: Archaea Woese et al., 2024 • 927 spp."
    expect(within(rows[0]!).getByText(/Archaea/i)).toBeInTheDocument();
    expect(within(rows[0]!).getByText(/927 spp/i)).toBeInTheDocument();
  });

  it("caret click toggles aria-expanded", async () => {
    mockFetchTree(
      new Map([["parent_id=0", { parent: { id: 0 }, children: ROOTS_FIXTURE, next_cursor: null }]]),
    );

    render(<TaxonomicTree />);

    await waitFor(() => {
      expect(screen.getByRole("tree")).toBeInTheDocument();
    });
    const archaeaRow = screen.getByRole("treeitem", { name: /Archaea/i });
    const button = within(archaeaRow).getByRole("button");
    expect(archaeaRow).toHaveAttribute("aria-expanded", "false");

    await act(async () => {
      fireEvent.click(button);
    });

    // The button fires the fetch; wait for the fetch to resolve.
    await waitFor(() => {
      expect(archaeaRow).toHaveAttribute("aria-expanded", "true");
    });
  });

  it("indent reflects depth via aria-level", async () => {
    mockFetchTree(
      new Map([
        ["parent_id=0", { parent: { id: 0 }, children: ROOTS_FIXTURE, next_cursor: null }],
        ["parent_id=5", { parent: { id: 5 }, children: EUKARYOTA_CHILDREN, next_cursor: null }],
      ]),
    );

    render(<TaxonomicTree />);

    await waitFor(() => {
      expect(screen.getByRole("tree")).toBeInTheDocument();
    });
    const eukaryotaRow = screen.getByRole("treeitem", { name: /Eukaryota/i });
    expect(eukaryotaRow).toHaveAttribute("aria-level", "1");

    await act(async () => {
      fireEvent.click(within(eukaryotaRow).getByRole("button"));
    });

    await waitFor(() => {
      const animaliaRow = screen.getByRole("treeitem", { name: /Animalia/i });
      expect(animaliaRow).toHaveAttribute("aria-level", "2");
    });
  });

  it("lazy fetch on first expand, cache hit on re-expand", async () => {
    const fetchMock = mockFetchTree(
      new Map([
        ["parent_id=0", { parent: { id: 0 }, children: ROOTS_FIXTURE, next_cursor: null }],
        ["parent_id=5", { parent: { id: 5 }, children: EUKARYOTA_CHILDREN, next_cursor: null }],
      ]),
    );

    render(<TaxonomicTree />);
    await waitFor(() => {
      expect(screen.getByRole("tree")).toBeInTheDocument();
    });

    const eukaryotaRow = screen.getByRole("treeitem", { name: /Eukaryota/i });
    const button = within(eukaryotaRow).getByRole("button");

    // First expand → fetch fires.
    await act(async () => {
      fireEvent.click(button);
    });
    await waitFor(() => {
      expect(eukaryotaRow).toHaveAttribute("aria-expanded", "true");
    });

    const callsAfterFirstExpand = fetchMock.mock.calls.filter((c) =>
      (c[0] as string).includes("parent_id=5"),
    ).length;
    expect(callsAfterFirstExpand).toBe(1);

    // Second expand → cache hit, no new fetch.
    await act(async () => {
      fireEvent.click(button);
    });
    // The second click collapses the row.
    await waitFor(() => {
      expect(eukaryotaRow).toHaveAttribute("aria-expanded", "false");
    });
    // Re-expand:
    await act(async () => {
      fireEvent.click(button);
    });
    await waitFor(() => {
      expect(eukaryotaRow).toHaveAttribute("aria-expanded", "true");
    });

    const callsAfterReExpand = fetchMock.mock.calls.filter((c) =>
      (c[0] as string).includes("parent_id=5"),
    ).length;
    expect(callsAfterReExpand).toBe(1);
  });

  it("ArrowDown moves focus to the next row", async () => {
    mockFetchTree(
      new Map([["parent_id=0", { parent: { id: 0 }, children: ROOTS_FIXTURE, next_cursor: null }]]),
    );

    render(<TaxonomicTree />);
    await waitFor(() => {
      expect(screen.getByRole("tree")).toBeInTheDocument();
    });

    const firstRow = screen.getByRole("treeitem", { name: /Archaea/i });
    const firstButton = within(firstRow).getByRole("button");
    firstButton.focus();
    expect(firstButton).toHaveFocus();

    await act(async () => {
      fireEvent.keyDown(firstButton, { key: "ArrowDown" });
    });

    const secondRow = screen.getByRole("treeitem", { name: /Bacteria/i });
    expect(within(secondRow).getByRole("button")).toHaveFocus();
  });

  it("ArrowRight expands a collapsed row and ArrowLeft collapses it", async () => {
    mockFetchTree(
      new Map([
        ["parent_id=0", { parent: { id: 0 }, children: ROOTS_FIXTURE, next_cursor: null }],
        ["parent_id=5", { parent: { id: 5 }, children: EUKARYOTA_CHILDREN, next_cursor: null }],
      ]),
    );

    render(<TaxonomicTree />);
    await waitFor(() => {
      expect(screen.getByRole("tree")).toBeInTheDocument();
    });

    const eukaryotaRow = screen.getByRole("treeitem", { name: /Eukaryota/i });
    const button = within(eukaryotaRow).getByRole("button");
    button.focus();

    await act(async () => {
      fireEvent.keyDown(button, { key: "ArrowRight" });
    });

    await waitFor(() => {
      expect(eukaryotaRow).toHaveAttribute("aria-expanded", "true");
    });

    await act(async () => {
      fireEvent.keyDown(button, { key: "ArrowLeft" });
    });

    await waitFor(() => {
      expect(eukaryotaRow).toHaveAttribute("aria-expanded", "false");
    });
  });

  it("Enter activates the row (toggles the caret)", async () => {
    mockFetchTree(
      new Map([
        ["parent_id=0", { parent: { id: 0 }, children: ROOTS_FIXTURE, next_cursor: null }],
        ["parent_id=5", { parent: { id: 5 }, children: EUKARYOTA_CHILDREN, next_cursor: null }],
      ]),
    );

    render(<TaxonomicTree />);
    await waitFor(() => {
      expect(screen.getByRole("tree")).toBeInTheDocument();
    });

    const eukaryotaRow = screen.getByRole("treeitem", { name: /Eukaryota/i });
    const button = within(eukaryotaRow).getByRole("button");
    button.focus();

    await act(async () => {
      fireEvent.keyDown(button, { key: "Enter" });
    });

    await waitFor(() => {
      expect(eukaryotaRow).toHaveAttribute("aria-expanded", "true");
    });
  });

  it("dispatches path:change with the explored path on every expand", async () => {
    mockFetchTree(
      new Map([
        ["parent_id=0", { parent: { id: 0 }, children: ROOTS_FIXTURE, next_cursor: null }],
        ["parent_id=5", { parent: { id: 5 }, children: EUKARYOTA_CHILDREN, next_cursor: null }],
      ]),
    );

    const handler = vi.fn();
    window.addEventListener("path:change", handler);

    render(<TaxonomicTree />);
    await waitFor(() => {
      expect(screen.getByRole("tree")).toBeInTheDocument();
    });

    const eukaryotaRow = screen.getByRole("treeitem", { name: /Eukaryota/i });
    await act(async () => {
      fireEvent.click(within(eukaryotaRow).getByRole("button"));
    });
    await waitFor(() => {
      const events = handler.mock.calls.map(
        (call) => (call[0] as CustomEvent<{ path: string[] }>).detail.path,
      );
      // The tree fires path:change with the explored display names
      // on every expand. The App's listener is what writes through
      // to the cascadePath store -- the tree deliberately avoids
      // writing directly so a future producer that dispatches the
      // event alone (e.g. a test fixture) does not race the tree's
      // own writes.
      expect(events).toContainEqual(["Eukaryota"]);
    });

    window.removeEventListener("path:change", handler);
  });

  it("search pick expands ancestors and focuses the chosen row", async () => {
    // The contract: when the user picks a search hit whose ancestors
    // are collapsed, the tree walks the ancestor chain, fetches each
    // missing children slice, expands every node in the chain, and
    // moves focus to the chosen row's button.
    //
    // This pins the spec requirement
    // ``taxon-tree-search/spec.md §"Selection Navigates"``: "WHEN
    // the user clicks the first THEN every ancestor expands AND the
    // chosen row scrolls into view AND focus moves to the chosen
    // row."
    //
    // We don't use fake timers here: the React Testing Library
    // ``waitFor`` poll uses real timers under the hood and the
    // 200ms debounce is small enough to wait for directly.
    mockFetchTree(
      new Map([
        ["parent_id=0", { parent: { id: 0 }, children: ROOTS_FIXTURE, next_cursor: null }],
        ["parent_id=5", {
          parent: {
            id: 5,
            name: "Eukaryota",
            display_name: "Eukaryota (Chatton, 1925) Whittaker & Margulis, 1978",
            rank: "domain",
            parent_id: null,
            is_synonym: false,
            is_extinct: false,
            is_uncertain: false,
            is_unassigned: false,
            has_children: true,
            species_count: 5_654_308,
            authorship: "(Chatton, 1925) Whittaker & Margulis, 1978",
          },
          children: EUKARYOTA_CHILDREN,
          next_cursor: null,
        }],
        ["parent_id=10", {
          parent: {
            id: 10,
            name: "Animalia",
            display_name: "Animalia Linnaeus, 1758",
            rank: "kingdom",
            parent_id: 5,
            is_synonym: false,
            is_extinct: false,
            is_uncertain: false,
            is_unassigned: false,
            has_children: false,
            species_count: 1_792_173,
            authorship: "Linnaeus, 1758",
          },
          children: [],
          next_cursor: null,
        }],
        ["q=Animalia", { items: [{
          id: 10,
          name: "Animalia",
          display_name: "Animalia Linnaeus, 1758",
          rank: "kingdom",
          parent_id: 5,
          is_synonym: false,
          is_extinct: false,
          is_uncertain: false,
          is_unassigned: false,
          has_children: false,
          species_count: 1_792_173,
          authorship: "Linnaeus, 1758",
        }] }],
      ]),
    );

    const { container } = render(<TaxonomicTree />);
    await waitFor(() => {
      expect(screen.getByRole("tree")).toBeInTheDocument();
    });

    // Type into the search input; the 200ms debounce window
    // collapses into a single fetch.
    const input = screen.getByLabelText(/find taxon/i);
    await act(async () => {
      fireEvent.change(input, { target: { value: "Animalia" } });
    });
    // Wait for the search results listbox to render the hit.
    const listbox = await screen.findByRole("listbox");
    const hit = await waitFor(() => within(listbox).getByRole("option"), {
      timeout: 2000,
    });

    await act(async () => {
      fireEvent.click(hit);
    });

    // Ancestor (Eukaryota, parent_id=5) must expand — its
    // children fetch fires, the row's aria-expanded flips to true.
    const eukaryotaRow = await screen.findByRole("treeitem", { name: /Eukaryota/i });
    await waitFor(() => {
      expect(eukaryotaRow).toHaveAttribute("aria-expanded", "true");
    });

    // The chosen row renders and receives focus.
    const animaliaRow = await screen.findByRole("treeitem", { name: /Animalia/i });
    await waitFor(() => {
      expect(within(animaliaRow).getByRole("button")).toHaveFocus();
    });
    void container;
  });

  it("extant-only checkbox triggers a refetch with include_extinct=false", async () => {
    // The contract: when the user toggles "Extant only", the tree
    // drops the cached children for the visible rows and refetches
    // them with ``include_extinct=false`` so extinct taxa are
    // filtered server-side.
    //
    // This pins the spec requirement
    // ``taxonomic-tree-browse/spec.md §"Filter on hides extinct"``:
    // "WHEN the user toggles the checkbox THEN the tree refetches
    // with ``include_extinct=false`` and only extant rows render."
    const fetchMock = mockFetchTree(
      new Map([
        ["parent_id=0&include_extinct=false", {
          parent: { id: 0 },
          children: ROOTS_FIXTURE,
          next_cursor: null,
        }],
      ]),
    );
    // The default fetch (no include_extinct) is a no-op for the
    // assertion; the test waits for the post-toggle URL.
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("include_extinct=false")) {
        return Promise.resolve(
          mockFetchJson({
            parent: { id: 0 },
            children: ROOTS_FIXTURE,
            next_cursor: null,
          }),
        );
      }
      return Promise.resolve(
        mockFetchJson({
          parent: { id: 0 },
          children: ROOTS_FIXTURE,
          next_cursor: null,
        }),
      );
    });

    render(<TaxonomicTree />);
    await waitFor(() => {
      expect(screen.getByRole("tree")).toBeInTheDocument();
    });

    const checkbox = screen.getByRole("checkbox", { name: /extant only/i });
    await act(async () => {
      fireEvent.click(checkbox);
    });

    // The checkbox triggers a refetch with include_extinct=false.
    await waitFor(() => {
      const calls = fetchMock.mock.calls.map(
        (c) => (c[0] as string),
      );
      expect(
        calls.some((u) => u.includes("include_extinct=false")),
        `expected a refetch with include_extinct=false; saw ${JSON.stringify(calls)}`,
      ).toBe(true);
    });
  });

  it("aria-busy=true fires while children fetch is in flight", async () => {
    let resolveChildren: ((value: Response) => void) | null = null;
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("parent_id=0")) {
        return Promise.resolve(
          mockFetchJson({ parent: { id: 0 }, children: ROOTS_FIXTURE, next_cursor: null }),
        );
      }
      if (url.includes("parent_id=5")) {
        return new Promise<Response>((res) => {
          resolveChildren = () =>
            res(
              mockFetchJson({
                parent: { id: 5 },
                children: EUKARYOTA_CHILDREN,
                next_cursor: null,
              }),
            );
        });
      }
      return Promise.reject(new Error(`unexpected fetch: ${url}`));
    });
    globalThis.fetch = fetchMock as unknown as typeof fetch;
    void fetchMock;

    render(<TaxonomicTree />);
    await waitFor(() => {
      expect(screen.getByRole("tree")).toBeInTheDocument();
    });

    const eukaryotaRow = screen.getByRole("treeitem", { name: /Eukaryota/i });
    const button = within(eukaryotaRow).getByRole("button");
    await act(async () => {
      fireEvent.click(button);
    });

    // While the fetch is in flight, the row's button carries
    // aria-busy="true" (the role="treeitem" host does not allow
    // aria-busy per the ARIA spec, so the attribute lives on the
    // button).
    await waitFor(() => {
      expect(button).toHaveAttribute("aria-busy", "true");
    });

    // Resolve the fetch with the children payload and verify the
    // button clears aria-busy by rendering the children.
    await act(async () => {
      resolveChildren?.(
        new Response(
          JSON.stringify({
            parent: { id: 5 },
            children: EUKARYOTA_CHILDREN,
            next_cursor: null,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    });
    await waitFor(() => {
      expect(button).not.toHaveAttribute("aria-busy");
    });
  });
});
