/** Runtime contract for the ``taxon:select`` CustomEvent.

The Cascade dispatches this event when the user clicks a species
row; the App listens for it to render the breadcrumb and fetch the
search-source dispatch links. Before this file, the contract was
implicit — both ends agreed on the shape by convention, and the
type cast ``(e as CustomEvent<{...}>).detail`` skipped any
runtime validation. The genus-segment bug shipped in PR #22 was
the direct consequence.

This module provides:

- ``TaxonResponseSchema`` — Zod schema mirroring ``TaxonResponse``.
- ``TaxonSelectDetailSchema`` — the full event payload.
- ``TaxonSelectDetail`` — TS type derived from the schema.
- ``dispatchTaxonSelect(detail)`` — validates before dispatch; the
  dispatch is skipped (with a console warning) when the detail is
  malformed, so a buggy producer cannot break the App.
- ``parseTaxonSelectEvent(event)`` — validates an incoming event;
  returns the typed detail or ``null`` when malformed, so a buggy
  producer cannot crash the listener.

The schemas are written by hand (no codegen) because the source
type surface is small. If the API grows past ~5 events of this
shape, consider extracting the schemas to a shared package or
codegen via ``ts-to-zod``.
*/

import { z } from "zod";

/** Mirror of the ``TaxonResponse`` interface in ``api.ts``. */
export const TaxonResponseSchema = z.object({
  // The CLB resolver returns opaque string ids (``"5T6MX"``,
  // ``"6V6DZ"``, ``"CH2"`` …) — they are not numeric.
  id: z.union([z.string(), z.number()]),
  name: z.string(),
  display_name: z.string(),
  rank: z.string(),
  parent_id: z.union([z.string(), z.number()]).nullable(),
  is_synonym: z.boolean(),
  is_extinct: z.boolean(),
  is_uncertain: z.boolean(),
  is_unassigned: z.boolean(),
});

/** Full payload of the ``taxon:select`` CustomEvent. */
export const TaxonSelectDetailSchema = z.object({
  row: TaxonResponseSchema,
  breadcrumb: z.array(z.string()),
  parentSegments: z.array(z.string()),
});

export type TaxonSelectDetail = z.infer<typeof TaxonSelectDetailSchema>;

/** Constant event name so producer and consumer cannot drift. */
export const TAXON_SELECT_EVENT = "taxon:select";

/**
 * Dispatch the ``taxon:select`` event after validating the detail.
 *
 * If the detail fails schema validation, the dispatch is skipped
 * and a console warning is logged. This keeps a buggy producer
 * from corrupting the App's state machine.
 */
export function dispatchTaxonSelect(detail: unknown): void {
  const result = TaxonSelectDetailSchema.safeParse(detail);
  if (!result.success) {
    console.warn(
      "[taxon] dispatchTaxonSelect: detail failed schema validation, skipping dispatch",
      result.error.flatten(),
    );
    return;
  }
  window.dispatchEvent(
    new CustomEvent(TAXON_SELECT_EVENT, { detail: result.data }),
  );
}

/**
 * Parse an incoming ``taxon:select`` event into a typed detail.
 *
 * Returns ``null`` when the detail fails validation. The caller
 * should treat ``null`` as "ignore this event" — a malformed
 * event must never crash the listener.
 */
export function parseTaxonSelectEvent(
  event: Event,
): TaxonSelectDetail | null {
  const customEvent = event as CustomEvent;
  const result = TaxonSelectDetailSchema.safeParse(customEvent.detail);
  if (!result.success) {
    console.warn(
      "[taxon] parseTaxonSelectEvent: detail failed schema validation, ignoring",
      result.error.flatten(),
    );
    return null;
  }
  return result.data;
}
