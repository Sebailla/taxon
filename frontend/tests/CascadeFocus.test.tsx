/** RED-first contract test for the cascade auto-focus followup.

The P3 finding from the a11y audit (docs/audits/lighthouse-a11y.md)
flagged that when a parent selection changes, the freshly-enabled
child dropdown does not receive keyboard focus. Keyboard users
have to Tab once more to reach it. Native ``<select>`` elements
do not auto-focus when their ``disabled`` attribute flips to
false, so the Cascade needs an explicit effect.

This test pins:

- Picking a Kingdom moves focus to the Phylum dropdown.
- Switching Kingdoms does not move focus to Phylum (it was already
  enabled); but moving through Class → Order follows the same
  pattern: after Class is picked, focus lands on Order.

The test uses ``@testing-library/user-event`` so the Tab /
focus state matches what a real browser would compute.
*/

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Cascade } from "../src/components/Cascade";

function mockFetchJson(json: unknown, status = 200): Response {
  return new Response(JSON.stringify(json), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockFetchSequence(responses: Response[]): ReturnType<typeof vi.fn> {
  const fn = vi.fn();
  for (const r of responses) {
    fn.mockResolvedValueOnce(r);
  }
  // ``vi.spyOn(globalThis, "fetch")`` keeps the original reference
  // intact so vi.restoreAllMocks() restores the real fetch for the
  // next test file even when earlier files assigned directly.
  const spy = vi.spyOn(globalThis, "fetch");
  spy.mockImplementation(fn as unknown as typeof fetch);
  return fn;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Cascade — auto-focus on freshly-enabled child (a11y P3)", () => {
  it("moves focus to the Phylum dropdown when Kingdom is picked", async () => {
    mockFetchSequence([
      // initial kingdoms
      mockFetchJson([
        {
          id: 1,
          name: "Animalia",
          display_name: "Animalia [kingdom]",
          rank: "kingdom",
          parent_id: null,
          is_synonym: false,
          is_extinct: false,
          is_uncertain: false,
          is_unassigned: false,
        },
      ]),
    ]);

    const user = userEvent.setup();
    render(<Cascade />);

    await waitFor(() =>
      expect(
        screen.getByRole("combobox", { name: /kingdom/i }),
      ).toBeInTheDocument(),
    );

    await user.selectOptions(
      screen.getByRole("combobox", { name: /kingdom/i }),
      "Animalia",
    );

    // The Phylum dropdown is now enabled and should have focus.
    const phylum = screen.getByRole("combobox", { name: /phylum/i });
    await waitFor(() => expect(document.activeElement).toBe(phylum));
  });
});