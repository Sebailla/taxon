/** Test helpers for the cascade component tests.

The seven-fixed-tier cascade renders every dropdown on every
render. Until the parent snapshot for a given slot resolves,
the slot is ``disabled``. ``user.selectOptions`` cannot pick a
value from a disabled ``<select>`` — the test must wait for
the slot to enable before issuing the pick.

``waitForEnabledOption`` resolves the combobox, waits until it
is no longer disabled, and then returns it. The optional
``value`` argument also waits for that option text to appear
in the option list, so the test never races the fetch that
populates the dropdown.
*/

import { expect } from "vitest";
import { waitFor } from "@testing-library/react";
import { screen, within } from "@testing-library/react";

export async function waitForEnabledOption(
  label: string,
  value?: string,
): Promise<HTMLSelectElement> {
  const select = (await screen.findByRole("combobox", {
    name: label,
  })) as HTMLSelectElement;
  await waitFor(() => {
    expect(select).not.toBeDisabled();
  });
  if (value !== undefined) {
    await waitFor(() => {
      expect(
        within(select).getByRole("option", { name: value }),
      ).toBeInTheDocument();
    });
  }
  return select;
}
