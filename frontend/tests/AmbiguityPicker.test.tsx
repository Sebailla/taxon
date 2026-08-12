/** RED-first contract tests for the AmbiguityPicker focus trap. */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AmbiguityPicker } from "../src/components/AmbiguityPicker";

function makeCandidates() {
  return [
    {
      id: 1,
      canonical_name: "Genus alpha",
      display_name: "Genus alpha (Meek, 1904)",
      breadcrumb: ["Animalia", "Chordata", "Mammalia"],
    },
    {
      id: 2,
      canonical_name: "Genus beta",
      display_name: "Genus beta (Smith, 1920)",
      breadcrumb: ["Plantae", "Magnoliophyta", "Magnoliopsida"],
    },
    {
      id: 3,
      canonical_name: "Genus gamma",
      display_name: "Genus gamma (Doe, 1985)",
      breadcrumb: ["Fungi", "Basidiomycota", "Agaricomycetes"],
    },
  ];
}

describe("AmbiguityPicker — focus trap", () => {
  it("moves focus to the first Select button when the dialog opens", async () => {
    const onPick = vi.fn();
    const onClose = vi.fn();
    render(
      <AmbiguityPicker
        candidates={makeCandidates()}
        onClose={onClose}
        onPick={onPick}
      />,
    );
    const firstSelect = screen.getAllByRole("button", { name: /select/i })[0];
    await waitFor(() => {
      expect(document.activeElement).toBe(firstSelect);
    });
  });

  it("Tab from the last focusable element wraps to the first", async () => {
    const onPick = vi.fn();
    const onClose = vi.fn();
    render(
      <AmbiguityPicker
        candidates={makeCandidates()}
        onClose={onClose}
        onPick={onPick}
      />,
    );
    const cancelButton = screen.getByRole("button", { name: /cancel/i });
    const firstSelect = screen.getAllByRole("button", { name: /select/i })[0];

    cancelButton.focus();
    expect(document.activeElement).toBe(cancelButton);

    const user = userEvent.setup();
    await user.tab();
    expect(document.activeElement).toBe(firstSelect);
  });

  it("Shift+Tab from the first focusable element wraps to the last", async () => {
    const onPick = vi.fn();
    const onClose = vi.fn();
    render(
      <AmbiguityPicker
        candidates={makeCandidates()}
        onClose={onClose}
        onPick={onPick}
      />,
    );
    const firstSelect = screen.getAllByRole("button", { name: /select/i })[0];
    const cancelButton = screen.getByRole("button", { name: /cancel/i });

    firstSelect.focus();
    expect(document.activeElement).toBe(firstSelect);

    const user = userEvent.setup();
    await user.tab({ shift: true });
    expect(document.activeElement).toBe(cancelButton);
  });

  it("Escape closes the dialog", async () => {
    const onPick = vi.fn();
    const onClose = vi.fn();
    render(
      <AmbiguityPicker
        candidates={makeCandidates()}
        onClose={onClose}
        onPick={onPick}
      />,
    );
    const user = userEvent.setup();
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("AmbiguityPicker — content", () => {
  it("renders every candidate with breadcrumb + Select button", () => {
    const onPick = vi.fn();
    const onClose = vi.fn();
    render(
      <AmbiguityPicker
        candidates={makeCandidates()}
        onClose={onClose}
        onPick={onPick}
      />,
    );
    for (const c of makeCandidates()) {
      expect(screen.getByText(c.canonical_name)).toBeInTheDocument();
    }
    const selectButtons = screen.getAllByRole("button", { name: /select/i });
    expect(selectButtons).toHaveLength(3);
  });

  it("clicking a Select button fires onPick with the candidate", async () => {
    const onPick = vi.fn();
    const onClose = vi.fn();
    render(
      <AmbiguityPicker
        candidates={makeCandidates()}
        onClose={onClose}
        onPick={onPick}
      />,
    );
    const user = userEvent.setup();
    const betaSelect = screen.getAllByRole("button", { name: /select/i })[1];
    await user.click(betaSelect);
    expect(onPick).toHaveBeenCalledTimes(1);
    const firstCallArg = onPick.mock.calls[0]?.[0];
    expect(firstCallArg).toMatchObject({ id: 2 });
  });
});