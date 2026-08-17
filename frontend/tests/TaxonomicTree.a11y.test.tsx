/** RED-first axe-core a11y regression tests for the TaxonomicTree.

The hand-rolled audit in ``docs/design/taxonomic-tree-browse.md``
covers the 12 impeccable dimensions. This file adds automated
axe-core coverage so a wider range of issues (missing labels,
contrast, focus order, role/attribute pairing) surface on every
PR.

The test renders the TaxonomicTree with the 5-root mock fixture
and asserts zero violations on the standard rule set (wcag2a,
wcag2aa, wcag21a, wcag21aa, best-practice). The raw ``axe()``
return value is used rather than the ``toHaveNoViolations``
matcher (same rationale as ``tests/a11y.test.tsx``).
*/

import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

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

function mockFetchJson(json: unknown, status = 200): Response {
  return new Response(JSON.stringify(json), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const RUNNER_OPTIONS = {
  rules: {},
  runOptions: {
    tags: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"],
  },
} as const;

function summariseViolations(
  results: Awaited<ReturnType<typeof axe>>,
): string {
  if (results.violations.length === 0) return "no violations";
  return results.violations
    .map(
      (v) =>
        `[${v.impact}] ${v.id}: ${v.description} ` +
        `(nodes: ${v.nodes.length}; help: ${v.helpUrl})`,
    )
    .join("\n");
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

describe("TaxonomicTree a11y", () => {
  it("renders 5 root rows with no axe violations", async () => {
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("parent_id=0")) {
        return Promise.resolve(
          mockFetchJson({
            parent: { id: 0 },
            children: ROOTS_FIXTURE,
            next_cursor: null,
          }),
        );
      }
      return Promise.reject(new Error(`unexpected fetch: ${url}`));
    });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const { container } = render(<TaxonomicTree />);

    // Wait for the root fetch to populate the tree before
    // running axe on the rendered output.
    await waitFor(() => {
      expect(container.querySelectorAll('[role="treeitem"]').length).toBe(5);
    });

    const results = await axe(container, RUNNER_OPTIONS);
    expect(
      results.violations,
      `TaxonomicTree a11y violations:\n${summariseViolations(results)}`,
    ).toEqual([]);
  });
});
