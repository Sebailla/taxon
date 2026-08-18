import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import { speciesKey } from "../src/api";
import { SpeciesLinks } from "../src/components/SpeciesLinks";
import { useWorkspace } from "../src/store/workspace";

const links = [
  { source: "Wikipedia", label: "Wikipedia", url: "https://example.test/wiki" },
  { source: "Google", label: "Google", url: "https://example.test/google" },
];

afterEach(() => {
  vi.restoreAllMocks();
  useWorkspace.getState().clear();
});

describe("SpeciesLinks visited switches", () => {
  it("marks a source visited without removing the external link", async () => {
    const user = userEvent.setup();
    globalThis.fetch = vi.fn().mockResolvedValue(new Response(null, { status: 204 })) as unknown as typeof fetch;
    render(<SpeciesLinks links={links} genus="Panthera" epithet="tigris" />);

    const toggle = screen.getByRole("switch", { name: "Mark Wikipedia as visited" });
    await user.click(toggle);
    expect(toggle).toBeChecked();
    expect(screen.getByRole("link", { name: "Wikipedia (opens in a new tab)" })).toHaveAttribute("target", "_blank");
    expect(useWorkspace.getState().visitedLinks.get(speciesKey("Panthera", "tigris"))).toEqual(new Set(["Wikipedia"]));
  });

  it("unmarks one source without changing another species", async () => {
    const user = userEvent.setup();
    const tigerKey = speciesKey("Panthera", "tigris");
    const lionKey = speciesKey("Panthera", "leo");
    useWorkspace.setState({ visitedLinks: new Map([[tigerKey, new Set(["Wikipedia"])], [lionKey, new Set(["Wikipedia"])]]) });
    globalThis.fetch = vi.fn().mockResolvedValue(new Response(null, { status: 204 })) as unknown as typeof fetch;
    render(<SpeciesLinks links={links} genus="Panthera" epithet="tigris" />);

    await user.click(screen.getByRole("switch", { name: "Mark Wikipedia as visited" }));
    expect(screen.getByRole("switch", { name: "Mark Wikipedia as visited" })).not.toBeChecked();
    expect(useWorkspace.getState().visitedLinks.get(lionKey)).toEqual(new Set(["Wikipedia"]));
  });

  it("has no axe-core violations", async () => {
    const { container } = render(<SpeciesLinks links={links} genus="Panthera" epithet="tigris" />);
    expect((await axe(container)).violations).toEqual([]);
  });
});
