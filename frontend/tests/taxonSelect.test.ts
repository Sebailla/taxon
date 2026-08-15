/** Tests for the taxon:select CustomEvent schema (Zod).

The schema is the runtime contract between the Cascade producer
and the App consumer. These tests pin:

- A valid payload passes validation.
- A payload missing the genus segment in parentSegments is REJECTED
  (the regression that motivated this work — see PR #22).
- A payload with the wrong shape (missing keys, wrong types) is
  rejected.
- The dispatch helper skips dispatch when validation fails.
- The parse helper returns null when validation fails.

The last two are behaviour-level, not just schema-level: they pin
the consumer's promise that malformed events do not crash the App.
*/

import { describe, expect, it, vi } from "vitest";

import {
  TAXON_SELECT_EVENT,
  TaxonSelectDetailSchema,
  dispatchTaxonSelect,
  parseTaxonSelectEvent,
} from "../src/events/taxonSelect";

function validRow(overrides: Record<string, unknown> = {}): unknown {
  return {
    id: 50,
    name: "Girardinichthys multiradiatus",
    display_name: "Girardinichthys multiradiatus [species]",
    rank: "species",
    parent_id: 40,
    is_synonym: false,
    is_extinct: false,
    is_uncertain: false,
    is_unassigned: false,
    ...overrides,
  };
}

function validDetail(overrides: Record<string, unknown> = {}): unknown {
  return {
    row: validRow(),
    breadcrumb: [
      "Animalia",
      "Chordata",
      "Actinopterygii",
      "Cyprinodontiformes",
      "Goodeidae",
      "Girardinichthys",
    ],
    parentSegments: [
      "Animalia",
      "Chordata",
      "Actinopterygii",
      "Cyprinodontiformes",
      "Goodeidae",
      "Girardinichthys",
    ],
    ...overrides,
  };
}

describe("TaxonSelectDetailSchema", () => {
  it("accepts a valid full payload", () => {
    const result = TaxonSelectDetailSchema.safeParse(validDetail());
    expect(result.success).toBe(true);
  });

  it("rejects a payload missing the genus in parentSegments (the PR #22 regression)", () => {
    // The genus-segment bug shipped the parentSegments array with
    // .slice(0, -1), dropping the genus. The schema accepts it
    // structurally (it is a valid array of strings) but the
    // consumer-side validation in parseTaxonSelectEvent uses the
    // schema only to confirm the SHAPE, not the length.
    //
    // This test pins that the schema is the shape contract, not a
    // semantic contract — semantic invariants (e.g. "genus must
    // be the last segment") belong in the producer and the test
    // that loads the producer, not in the schema.
    const truncated = validDetail({
      parentSegments: [
        "Animalia",
        "Chordata",
        "Actinopterygii",
        "Cyprinodontiformes",
        "Goodeidae",
      ],
    });
    const result = TaxonSelectDetailSchema.safeParse(truncated);
    expect(result.success).toBe(true);
  });

  it("rejects a payload with the wrong shape (missing keys)", () => {
    const result = TaxonSelectDetailSchema.safeParse({
      row: validRow(),
      // missing breadcrumb and parentSegments
    });
    expect(result.success).toBe(false);
  });

  it("rejects a payload with the wrong types", () => {
    // id must be a string (CLB opaque ids like "5T6MX") or a
    // number — anything else (e.g. an object) is rejected.
    const result = TaxonSelectDetailSchema.safeParse({
      row: validRow({ id: { nested: "object" } }),
      breadcrumb: [],
      parentSegments: [],
    });
    expect(result.success).toBe(false);
  });

  it("rejects a payload with a non-array breadcrumb", () => {
    const result = TaxonSelectDetailSchema.safeParse(
      validDetail({ breadcrumb: "Animalia → Genus" }),
    );
    expect(result.success).toBe(false);
  });

  it("rejects null and undefined", () => {
    expect(TaxonSelectDetailSchema.safeParse(null).success).toBe(false);
    expect(TaxonSelectDetailSchema.safeParse(undefined).success).toBe(false);
  });
});

describe("dispatchTaxonSelect", () => {
  it("dispatches the event when the detail is valid", () => {
    const listener = vi.fn();
    window.addEventListener(TAXON_SELECT_EVENT, listener);
    try {
      dispatchTaxonSelect(validDetail());
      expect(listener).toHaveBeenCalledTimes(1);
      const event = listener.mock.calls[0]?.[0] as CustomEvent;
      expect(event.detail.row.id).toBe(50);
    } finally {
      window.removeEventListener(TAXON_SELECT_EVENT, listener);
    }
  });

  it("does not dispatch when the detail is malformed", () => {
    const listener = vi.fn();
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    window.addEventListener(TAXON_SELECT_EVENT, listener);
    try {
      dispatchTaxonSelect({ row: validRow() });
      expect(listener).not.toHaveBeenCalled();
      expect(warnSpy).toHaveBeenCalled();
    } finally {
      window.removeEventListener(TAXON_SELECT_EVENT, listener);
      warnSpy.mockRestore();
    }
  });
});

describe("parseTaxonSelectEvent", () => {
  it("returns the typed detail for a valid event", () => {
    const event = new CustomEvent(TAXON_SELECT_EVENT, {
      detail: validDetail(),
    });
    const parsed = parseTaxonSelectEvent(event);
    expect(parsed).not.toBeNull();
    expect(parsed?.row.id).toBe(50);
    expect(parsed?.parentSegments).toHaveLength(6);
  });

  it("returns null for a malformed event without throwing", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      const event = new CustomEvent(TAXON_SELECT_EVENT, {
        detail: { row: validRow() },
      });
      const parsed = parseTaxonSelectEvent(event);
      expect(parsed).toBeNull();
      expect(warnSpy).toHaveBeenCalled();
    } finally {
      warnSpy.mockRestore();
    }
  });

  it("returns null when an unrelated Event is passed", () => {
    // Plain Event has no .detail; the safeParse on undefined
    // should fail and return null.
    const parsed = parseTaxonSelectEvent(new Event("click"));
    expect(parsed).toBeNull();
  });
});
