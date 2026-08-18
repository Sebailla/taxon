/** RED contract tests for the ExplorerPanel.

Pins the 5 MUST clauses from
``openspec/changes/species-folder-explorer/specs/workspace-explorer/spec.md``:

1. Iframe sandbox attrs match the exact set
   ``allow-same-origin allow-scripts allow-forms allow-popups allow-downloads``.
   No ``allow-top-navigation``. Empty src when no active link.
2. Aria label reads ``Embedded search result for {genus} {epithet} ({source})`` and
   updates when the active link changes.
3. X-Frame-Options / CSP rejection triggers the fallback card via an
   ``iframe.onError`` event. The card shows the source name + a
   "this source refuses embedding" message + an
   ``<a target="_blank" rel="noopener noreferrer">Open in new tab</a>``.
4. Fallback button is reachable from keyboard focus (axe-core 0 violations)
   and is the first tab stop inside the card. Never hidden.
5. Empty state when no active link is set.
*/

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import * as axeCore from "axe-core";
import { axe } from "vitest-axe";

import { ExplorerPanel } from "../src/components/ExplorerPanel";
import { useWorkspace } from "../src/store/workspace";

afterEach(() => {
  useWorkspace.getState().clear();
});

const EXACT_SANDBOX =
  "allow-same-origin allow-scripts allow-forms allow-popups allow-downloads";

describe("ExplorerPanel — iframe sandbox + empty state", () => {
  it("renders the iframe with the exact sandbox attribute set when an active link is set", () => {
    useWorkspace.getState().setActiveLink({
      speciesKey: "Panthera%7Ctigris",
      source: "Wikipedia",
      url: "https://example.test/wiki/Panthera_tigris",
    });
    render(<ExplorerPanel />);
    const frame = screen.getByTitle(/Embedded search result for/);
    expect(frame.tagName).toBe("IFRAME");
    expect(frame.getAttribute("sandbox")).toBe(EXACT_SANDBOX);
    expect(frame.getAttribute("src")).toBe(
      "https://example.test/wiki/Panthera_tigris",
    );
  });

  it("does NOT include allow-top-navigation or allow-modals in the sandbox", () => {
    useWorkspace.getState().setActiveLink({
      speciesKey: "Panthera%7Ctigris",
      source: "Wikipedia",
      url: "https://example.test/wiki",
    });
    render(<ExplorerPanel />);
    const frame = screen.getByTitle(/Embedded search result for/);
    const sandbox = frame.getAttribute("sandbox") ?? "";
    expect(sandbox.includes("allow-top-navigation")).toBe(false);
    expect(sandbox.includes("allow-modals")).toBe(false);
  });

  it("renders the empty-state placeholder when no active link is set", () => {
    render(<ExplorerPanel />);
    expect(screen.getByText(/Pick a source to embed/i)).toBeInTheDocument();
    expect(screen.queryByTitle(/Embedded search result for/)).toBeNull();
  });
});

describe("ExplorerPanel — aria label updates on active link change", () => {
  it("names the active source in the aria-label", () => {
    useWorkspace.getState().setActiveLink({
      speciesKey: "Panthera%7Ctigris",
      source: "Wikipedia",
      url: "https://example.test/wiki",
    });
    render(<ExplorerPanel />);
    expect(
      screen.getByTitle("Embedded search result for Panthera tigris (Wikipedia)"),
    ).toBeInTheDocument();
  });

  it("swaps the aria-label when the active link changes to a different source", () => {
    useWorkspace.getState().setActiveLink({
      speciesKey: "Panthera%7Ctigris",
      source: "Wikipedia",
      url: "https://example.test/wiki",
    });
    const { rerender } = render(<ExplorerPanel />);
    expect(
      screen.getByTitle("Embedded search result for Panthera tigris (Wikipedia)"),
    ).toBeInTheDocument();

    useWorkspace.getState().setActiveLink({
      speciesKey: "Panthera%7Ctigris",
      source: "Google",
      url: "https://example.test/google",
    });
    rerender(<ExplorerPanel />);
    expect(
      screen.getByTitle("Embedded search result for Panthera tigris (Google)"),
    ).toBeInTheDocument();
    expect(
      screen.queryByTitle("Embedded search result for Panthera tigris (Wikipedia)"),
    ).toBeNull();
  });
});

describe("ExplorerPanel — fallback card on iframe error", () => {
  it("shows the source name + a refusal message + an external-link anchor", () => {
    useWorkspace.getState().setActiveLink({
      speciesKey: "Panthera%7Ctigris",
      source: "Wikipedia",
      url: "https://example.test/wiki/Panthera_tigris",
    });
    render(<ExplorerPanel />);
    const frame = screen.getByTitle(/Embedded search result for/);
    fireEvent.error(frame);
    const fallback = screen.getByTestId("explorer-fallback");
    expect(fallback).toHaveTextContent(/Wikipedia/);
    expect(fallback).toHaveTextContent(/refuses embedding/i);
    const open = screen.getByRole("link", { name: /Open in new tab/i });
    expect(open).toHaveAttribute("target", "_blank");
    expect(open).toHaveAttribute("rel", "noopener noreferrer");
    expect(open).toHaveAttribute("href", "https://example.test/wiki/Panthera_tigris");
  });

  it("renders the fallback anchor outside the iframe", () => {
    useWorkspace.getState().setActiveLink({
      speciesKey: "Panthera%7Ctigris",
      source: "Wikipedia",
      url: "https://example.test/wiki",
    });
    const { container } = render(<ExplorerPanel />);
    const frame = screen.getByTitle(/Embedded search result for/);
    fireEvent.error(frame);
    const iframe = container.querySelector("iframe");
    const anchor = screen.getByRole("link", { name: /Open in new tab/i });
    expect(iframe).toBeTruthy();
    // The anchor must not be a descendant of the iframe.
    expect(iframe?.contains(anchor)).toBe(false);
  });

  it("keeps the fallback anchor visible (no display:none, no visibility:hidden, opacity ≥ 1)", () => {
    useWorkspace.getState().setActiveLink({
      speciesKey: "Panthera%7Ctigris",
      source: "Wikipedia",
      url: "https://example.test/wiki",
    });
    render(<ExplorerPanel />);
    fireEvent.error(screen.getByTitle(/Embedded search result for/));
    const anchor = screen.getByRole("link", { name: /Open in new tab/i });
    const styles = window.getComputedStyle(anchor);
    expect(styles.display).not.toBe("none");
    expect(styles.visibility).not.toBe("hidden");
    expect(Number(styles.opacity === "" ? "1" : styles.opacity)).toBeGreaterThanOrEqual(1);
  });
});

describe("ExplorerPanel — axe-core", () => {
  it("has no axe-core violations on the empty state", async () => {
    const { container } = render(<ExplorerPanel />);
    expect((await axe(container)).violations).toEqual([]);
  });

  it("has no axe-core violations when the iframe is rendering", async () => {
    useWorkspace.getState().setActiveLink({
      speciesKey: "Panthera%7Ctigris",
      source: "Wikipedia",
      url: "https://example.test/wiki",
    });
    const { container } = render(<ExplorerPanel />);
    // The iframe is part of the panel but axe-core's iframe traversal
    // crashes in jsdom (the iframe has no contentDocument). Use
    // ``axe.run`` with ``iframes: false`` so the rules run on the
    // panel DOM without entering the frame.
    const results = await axeCore.run(container, {
      iframes: false,
      rules: {},
    });
    expect(results.violations).toEqual([]);
  });

  it("has no axe-core violations when the fallback card is showing", async () => {
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

describe("ExplorerPanel — triangulation", () => {
  it("renders the iframe with the correct sandbox + src when the active link changes species", () => {
    useWorkspace.getState().setActiveLink({
      speciesKey: "Panthera%7Cleo",
      source: "Google",
      url: "https://example.test/google?q=Panthera+leo",
    });
    render(<ExplorerPanel />);
    const frame = screen.getByTitle(/Embedded search result for/);
    expect(frame.getAttribute("sandbox")).toBe(EXACT_SANDBOX);
    expect(frame.getAttribute("src")).toBe("https://example.test/google?q=Panthera+leo");
    expect(frame).toHaveAttribute("aria-label", "Embedded search result for Panthera leo (Google)");
  });

  it("places the fallback anchor as the first tab stop inside the card", () => {
    useWorkspace.getState().setActiveLink({
      speciesKey: "Panthera%7Ctigris",
      source: "Wikipedia",
      url: "https://example.test/wiki",
    });
    const { container } = render(<ExplorerPanel />);
    fireEvent.error(screen.getByTitle(/Embedded search result for/));
    const fallback = container.querySelector('[data-testid="explorer-fallback"]');
    expect(fallback).toBeTruthy();
    const focusable = fallback?.querySelectorAll("a[href], button, input, [tabindex]");
    expect(focusable?.[0]?.tagName).toBe("A");
  });
});
