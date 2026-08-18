/** Unit tests for the workspace store's speciesKey round-trip helper.

The store keys are ``encodeURIComponent("${genus}|${epithet}")`` so
the pipe separates the two segments after ``decodeURIComponent``.
The duplex must handle the URL-encoded pipe (``%7C``) and the
literal pipe (``|``) equally; the helper is the only place that
knows the internal storage shape.
*/

import { describe, expect, it } from "vitest";

import { speciesKey } from "../src/api";
import { decodeSpeciesKey } from "../src/store/speciesKey";

describe("decodeSpeciesKey", () => {
  it("decodes the URL-encoded pipe back into the genus + epithet pair", () => {
    expect(decodeSpeciesKey(speciesKey("Panthera", "tigris"))).toEqual({
      genus: "Panthera",
      epithet: "tigris",
    });
  });

  it("returns an empty epithet when the encoded key has no pipe", () => {
    expect(decodeSpeciesKey(speciesKey("Animalia", ""))).toEqual({
      genus: "Animalia",
      epithet: "",
    });
  });

  it("collapses both segments to the genus when the key is empty", () => {
    expect(decodeSpeciesKey("")).toEqual({ genus: "", epithet: "" });
  });
});
