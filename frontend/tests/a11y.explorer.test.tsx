/** axe-core a11y regression for the ExplorerPanel.

The behavioural contract is pinned in ``ExplorerPanel.test.tsx``; this
file isolates the axe-core regression so a future change to the panel
or the iframe-wrapping markup fails the a11y gate before it ships.

The iframe render must be audited with ``iframes: false`` because
axe-core's iframe traversal crashes in jsdom (the iframe has no
contentDocument). The empty state + fallback card have no iframe
content to recurse into, so they use the standard ``axe`` helper.
*/

import { fireEvent, render, screen } from "@testing-library/react";
import * as axeCore from "axe-core";
import { afterEach, describe, expect, it } from "vitest";
import { axe } from "vitest-axe";

import { ExplorerPanel } from "../src/components/ExplorerPanel";
import { useWorkspace } from "../src/store/workspace";

afterEach(() => {
  useWorkspace.getState().clear();
});

describe("ExplorerPanel — axe-core a11y regression", () => {
  it("the empty state has no axe-core violations", async () => {
    const { container } = render(<ExplorerPanel />);
    expect((await axe(container)).violations).toEqual([]);
  });

  it("the iframe-rendering state has no axe-core violations (iframes disabled)", async () => {
    useWorkspace.getState().setActiveLink({
      speciesKey: "Panthera%7Ctigris",
      source: "Wikipedia",
      url: "https://example.test/wiki",
    });
    const { container } = render(<ExplorerPanel />);
    const results = await axeCore.run(container, {
      iframes: false,
      rules: {},
    });
    expect(results.violations).toEqual([]);
  });

  it("the fallback-card state has no axe-core violations", async () => {
    useWorkspace.getState().setActiveLink({
      speciesKey: "Panthera%7Ctigris",
      source: "Wikipedia",
      url: "https://example.test/wiki",
    });
    render(<ExplorerPanel />);
    fireEvent.error(screen.getByTitle(/Embedded search result for/));
    expect((await axe(document.body)).violations).toEqual([]);
  });
});
