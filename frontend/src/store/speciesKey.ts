/** Helper for the workspace store's `speciesKey` round-trip.

The store keys are ``encodeURIComponent("${genus}|${epithet}")`` so the
pipe separates the two segments after ``decodeURIComponent``. When the
epithet is empty (the species has no epithet), the pair collapses to
the genus alone. The wildcard URL bar carries the pipe un-encoded
sometimes (e.g. a paste from the terminal) so the decoder tolerates
either form.
*/

/** Decode the URL-encoded speciesKey back into the ``Genus epithet`` pair. */
export function decodeSpeciesKey(key: string): { genus: string; epithet: string } {
  const decoded = decodeURIComponent(key);
  const parts = decoded.split("|");
  return {
    genus: parts[0] ?? decoded,
    epithet: parts[1] ?? "",
  };
}
