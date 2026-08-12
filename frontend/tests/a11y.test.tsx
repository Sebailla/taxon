/** RED-first axe-core a11y regression tests.

The hand-rolled a11y audit (docs/audits/lighthouse-a11y.md) walks
the 10 dimensions from the impeccable skill. This file adds
automated axe-core coverage on top so we catch a wider range of
issues on every PR:

- Missing form labels
- Insufficient colour contrast
- Missing alt text
- Improper heading hierarchy
- Buttons without accessible names
- And 70+ other rules from axe-core 4.x

The tests run axe-core against the rendered App, Toggles, and
AmbiguityPicker. Each test asserts zero violations on the standard
rule set (wcag2a, wcag2aa, wcag21a, wcag21aa, best-practice).

We use the raw ``axe()`` return value rather than the
``toHaveNoViolations`` matcher because Vitest's ``Vi.Assertion``
augmentation via ``vitest-axe/extend-expect`` only takes effect
when the test runs in a Vitest context; mixing the augmented
matchers with the jsdom test environment sometimes drops them.
The raw check is one line and gives us a clear failure message
when a violation surfaces.
*/

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axe } from "vitest-axe";

import { App } from "../src/App";
import { Toggles } from "../src/components/Toggles";
import { AmbiguityPicker } from "../src/components/AmbiguityPicker";

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

describe("axe-core a11y", () => {
  it("App has no axe violations on the empty render", async () => {
    const { container } = render(<App />);
    const results = await axe(container, RUNNER_OPTIONS);
    expect(
      results.violations,
      `App a11y violations:\n${summariseViolations(results)}`,
    ).toEqual([]);
  });

  it("Toggles has no axe violations with default state", async () => {
    const { container } = render(
      <Toggles value={new Set()} onChange={() => {}} />,
    );
    const results = await axe(container, RUNNER_OPTIONS);
    expect(
      results.violations,
      `Toggles (default) a11y violations:\n${summariseViolations(results)}`,
    ).toEqual([]);
  });

  it("Toggles has no axe violations with active toggles", async () => {
    const { container } = render(
      <Toggles
        value={new Set(["extinct", "synonyms"])}
        onChange={() => {}}
      />,
    );
    const results = await axe(container, RUNNER_OPTIONS);
    expect(
      results.violations,
      `Toggles (active) a11y violations:\n${summariseViolations(results)}`,
    ).toEqual([]);
  });

  it("AmbiguityPicker has no axe violations when open", async () => {
    const candidates = [
      {
        id: 1,
        canonical_name: "Genus alpha",
        display_name: "Genus alpha (Meek, 1904)",
        breadcrumb: ["Animalia", "Chordata"],
      },
      {
        id: 2,
        canonical_name: "Genus beta",
        display_name: "Genus beta (Smith, 1920)",
        breadcrumb: ["Plantae", "Magnoliophyta"],
      },
    ];
    const { container } = render(
      <AmbiguityPicker
        candidates={candidates}
        onClose={() => {}}
        onPick={() => {}}
      />,
    );
    const results = await axe(container, RUNNER_OPTIONS);
    expect(
      results.violations,
      `AmbiguityPicker a11y violations:\n${summariseViolations(results)}`,
    ).toEqual([]);
  });
});