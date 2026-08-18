import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import { SpeciesList } from "../src/components/SpeciesList";
import { useWorkspace } from "../src/store/workspace";

const row = {
  id: 7, name: "Panthera tigris", display_name: "Panthera tigris", rank: "species",
  parent_id: 6, is_synonym: false, is_extinct: false, is_uncertain: false, is_unassigned: false,
};

function renderList(): ReturnType<typeof render> {
  return render(<SpeciesList rows={[row]} status="idle" cursor={null} parentSegments={["Animalia", "Panthera"]} breadcrumb={["Animalia", "Panthera"]} />);
}

afterEach(() => {
  vi.restoreAllMocks();
  useWorkspace.getState().clear();
});

describe("SpeciesList workspace controls", () => {
  it("toggles explored without selecting the species row", async () => {
    const user = userEvent.setup();
    globalThis.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ genus: "Panthera", epithet: "tigris", explored_at: "now" }), { status: 200 })) as unknown as typeof fetch;
    const selected = vi.fn();
    window.addEventListener("taxon:select", selected);
    renderList();

    await user.click(screen.getByRole("checkbox", { name: "Mark Panthera tigris as explored" }));
    expect(screen.getByRole("checkbox", { name: "Mark Panthera tigris as explored" })).toBeChecked();
    expect(selected).not.toHaveBeenCalled();
    window.removeEventListener("taxon:select", selected);
  });

  it("replaces the create button with the persisted folder badge", async () => {
    const user = userEvent.setup();
    globalThis.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ path: "/workspace/Panthera tigris", exists: true }), { status: 201 })) as unknown as typeof fetch;
    renderList();

    await user.click(screen.getByRole("button", { name: "Create folder for Panthera tigris" }));
    expect(screen.getByText("folder")).toHaveAttribute("title", "/workspace/Panthera tigris");
    expect(screen.queryByRole("button", { name: "Create folder for Panthera tigris" })).not.toBeInTheDocument();
  });

  it("has no axe-core violations", async () => {
    const { container } = renderList();
    expect((await axe(container)).violations).toEqual([]);
  });
});
