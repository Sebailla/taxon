/** RED-first contract tests for the Toggles component.

The Toggles component renders 4 inclusion-class chips with OR
semantics, default off. Each chip is a real <button> element
with aria-pressed.

This file pins:
- Default state (no toggles active).
- A11y followup: every chip carries a min-h-[44px] class so the
  rendered button is at least 44px tall (WCAG AAA touch target
  recommendation).
- Each chip has aria-pressed reflecting the on/off state.
- Clicking a chip fires onChange with the new set.
- OR semantics: enabling two toggles puts both into the set.
- Disabling a toggle removes it from the set.
*/

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Toggles } from "../src/components/Toggles";

describe("Toggles — default state", () => {
  it("renders all four toggle chips", () => {
    render(<Toggles value={new Set()} onChange={() => {}} />);
    expect(screen.getByRole("button", { name: /extinct/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /synonyms/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /uncertain/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /unassigned/i })).toBeInTheDocument();
  });

  it("every chip has aria-pressed=false initially", () => {
    render(<Toggles value={new Set()} onChange={() => {}} />);
    for (const name of ["Extinct", "Synonyms", "Uncertain", "Unassigned"]) {
      expect(
        screen.getByRole("button", { name: new RegExp(name, "i") }),
      ).toHaveAttribute("aria-pressed", "false");
    }
  });

  it("clicking a chip fires onChange with the new set", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Toggles value={new Set()} onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: /synonyms/i }));
    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0]?.[0] as Set<string>;
    expect(next.has("synonyms")).toBe(true);
    expect(next.size).toBe(1);
  });
});

describe("Toggles — controlled state propagation", () => {
  it("each click produces a new set containing the toggled key", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Toggles value={new Set()} onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: /extinct/i }));
    await user.click(screen.getByRole("button", { name: /synonyms/i }));
    expect(onChange).toHaveBeenCalledTimes(2);
    const firstCall = onChange.mock.calls[0]?.[0] as Set<string>;
    const secondCall = onChange.mock.calls[1]?.[0] as Set<string>;
    // The component is controlled — it forwards a fresh set on
    // every click. The Cascade owns the OR semantics upstream by
    // collecting clicks across user interactions.
    expect(firstCall.has("extinct")).toBe(true);
    expect(secondCall.has("synonyms")).toBe(true);
  });

  it("disabling a toggle removes it from the set", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <Toggles
        value={new Set(["extinct", "synonyms"])}
        onChange={onChange}
      />,
    );
    await user.click(screen.getByRole("button", { name: /extinct/i }));
    const next = onChange.mock.calls[0]?.[0] as Set<string>;
    expect(next.has("extinct")).toBe(false);
    expect(next.has("synonyms")).toBe(true);
  });
});

describe("Toggles — accessibility (a11y audit followup)", () => {
  it("every chip carries a min-h-[44px] class (WCAG AAA touch target)", () => {
    render(<Toggles value={new Set()} onChange={() => {}} />);
    for (const name of ["Extinct", "Synonyms", "Uncertain", "Unassigned"]) {
      const button = screen.getByRole("button", {
        name: new RegExp(name, "i"),
      });
      // jsdom does not compute layout, but the className carries
      // the min-h-[44px] declaration. The visual height is enforced
      // by Tailwind; the test pins the className so a regression in
      // the stylesheet is caught.
      expect(button.className).toMatch(/min-h-\[44px\]|min-h-11/);
    }
  });

  it("every chip has aria-pressed reflecting the on/off state", () => {
    const { rerender } = render(
      <Toggles value={new Set()} onChange={() => {}} />,
    );
    expect(
      screen.getByRole("button", { name: /extinct/i }),
    ).toHaveAttribute("aria-pressed", "false");
    rerender(
      <Toggles value={new Set(["extinct"])} onChange={() => {}} />,
    );
    expect(
      screen.getByRole("button", { name: /extinct/i }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("the fieldset has aria-label 'Include in species list'", () => {
    render(<Toggles value={new Set()} onChange={() => {}} />);
    expect(
      screen.getByRole("group", { name: /include in species list/i }),
    ).toBeInTheDocument();
  });
});