/** Mobile (< 640px) responsive behaviour for the ExplorerPanel.

The right column collapses to a sticky peek-card on mobile, showing
the active link's label + an "open in new tab" anchor. The iframe
still renders — the spec says "the iframe still renders but the
dispatch grid is collapsed" — so the peek-card is an affordance
overlay, not a replacement.
*/

import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ExplorerPanel } from "../src/components/ExplorerPanel";
import { useWorkspace } from "../src/store/workspace";

/** Install a ``matchMedia`` stub that treats the test viewport as
 *  mobile (matches the ``(max-width: 639px)`` query the panel
 *  reads). jsdom does not implement matchMedia natively. */
function stubMatchMedia(matches: boolean): void {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
}

beforeEach(() => {
  stubMatchMedia(true);
});

afterEach(() => {
  vi.restoreAllMocks();
  useWorkspace.getState().clear();
});

describe("ExplorerPanel — mobile peek-card", () => {
  it("renders a peek-card with the active link's label and an open-in-new-tab anchor when on a small viewport", () => {
    useWorkspace.getState().setActiveLink({
      speciesKey: "Panthera%7Ctigris",
      source: "Wikipedia",
      url: "https://example.test/wiki",
    });
    render(<ExplorerPanel />);
    const peek = screen.getByTestId("explorer-peek");
    expect(peek).toBeInTheDocument();
    expect(peek).toHaveTextContent(/Wikipedia/);
    const anchor = screen.getByRole("link", { name: /Open in new tab/i });
    expect(anchor).toHaveAttribute("target", "_blank");
    expect(anchor).toHaveAttribute("rel", "noopener noreferrer");
    expect(anchor).toHaveAttribute("href", "https://example.test/wiki");
  });

  it("still renders the iframe even on the mobile peek-card", () => {
    useWorkspace.getState().setActiveLink({
      speciesKey: "Panthera%7Ctigris",
      source: "Wikipedia",
      url: "https://example.test/wiki",
    });
    const { container } = render(<ExplorerPanel />);
    expect(container.querySelector("iframe")).toBeTruthy();
    expect(screen.getByTestId("explorer-peek")).toBeInTheDocument();
  });
});
