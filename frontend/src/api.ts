/** Typed API client for the taxon backend.

The client wraps the seven endpoints shipped in Sub-PRs 2A/2B/2C
plus the ChecklistBank-aware endpoints shipped in the
``cascade-checklistbank`` chain:

- ``GET /api/kingdoms``                                  — list cascade roots.
  CLB returns the two top-tier taxa (``Biota``, ``Viruses``); the
  UI renders a ``Biota`` dropdown that drives the kingdom choice.
- ``GET /api/path-children?path=A|B|...``                 — children of the
  deepest taxon the path resolves to. The CLB resolver walks a
  best-effort path and groups children by their actual rank
  label; the wire envelope exposes ``next_tiers`` (list of
  ``{rank, label, examples, children}``) so the cascade UI
  renders one dropdown per rank group. Off-tuple intermediate
  ranks (``infraphylum``, ``parvphylum``, ``megaclass``,
  ``subclass``, ``suborder``) become their own tier groups.
- ``GET /api/species-list?path=...``                     — paginated species
  under the deepest genus in the path.
- ``GET /api/{kingdom}/phyla``                          — list phyla (legacy).
- ``GET /api/{kingdom}/{phylum}/classes``                — list classes.
- ``GET /api/{kingdom}/{phylum}/{class}/orders``         — list orders.
- ``GET /api/{kingdom}/{phylum}/{class}/{order}/families`` — list families.
- ``GET /api/{kingdom}/{phylum}/{class}/{order}/{family}/genera`` — list genera.
- ``GET /api/{kingdom}/{phylum}/{class}/{order}/{family}/{genus}/species``
                                                       — paginated species list.
- ``GET /api/{path}/{genus}/{epithet}``                  — species by breadcrumb.
- ``GET /api/species/{genus}/{epithet}``                 — species by pair (may 409).
- ``GET /api/{path}/{genus}/{epithet}/links``            — 12 dispatch URLs.

Every request resolves through :func:`apiGet` which translates the
HTTP status into a discriminated union the React components can
branch on:

- 200 → ``Ok(data)``.
- 404 → ``NotFound``.
- 409 → ``Ambiguous(candidates)``.
- 5xx / network → ``Error``.

The client never throws on HTTP errors — callers explicitly branch
on the result type. This keeps the component code declarative and
testable.
*/

// ---------------------------------------------------------------------------
// Public types (mirror of taxon/api/schemas.py)
// ---------------------------------------------------------------------------

export interface TaxonResponse {
  id: number;
  name: string;
  display_name: string;
  rank: string;
  parent_id: number | null;
  is_synonym: boolean;
  is_extinct: boolean;
  is_uncertain: boolean;
  is_unassigned: boolean;
}

export interface SpeciesListResponse {
  items: TaxonResponse[];
  next_cursor: string | null;
}

export interface SpeciesLookupResponse {
  // CLB resolver returns opaque string ids (``"5T6MX"``,
  // ``"6V6DZ"`` …). Numeric ids are still supported for
  // backward-compat with the legacy GBIF-shaped envelope.
  id: string | number;
  canonical_name: string;
  display_name: string;
  markers: {
    is_synonym: boolean;
    is_extinct: boolean;
    is_uncertain: boolean;
    is_unassigned: boolean;
  };
  breadcrumb: string[];
}

export interface SearchLinkItem {
  source: string;
  label: string;
  url: string;
}

export interface LinksResponse {
  species: SpeciesLookupResponse;
  links: SearchLinkItem[];
}

/** Envelope returned by ``GET /api/{path}/taxon-links``.

Mirrors the backend's ``TaxonLinksResponse`` in
``taxon/api/schemas.py``: the deepest taxon resolved by the
path + the 13 search-source dispatch links substituted with
that taxon's canonical ``name``. Used by the per-taxon
breadcrumb-links panel — every segment click resolves the
path to its deepest taxon and renders the same link grid the
species row produces.
*/
export interface TaxonLinksResponse {
  taxon: TaxonResponse;
  links: SearchLinkItem[];
}

export interface NextTier {
  rank: string;
  label: string;
  examples: string[];
  children: TaxonResponse[];
}

export interface PathChildrenResponse {
  parent: TaxonResponse;
  children: TaxonResponse[];
  next_tiers: NextTier[] | null;
}

export interface AmbiguityCandidate {
  id: number;
  canonical_name: string;
  display_name: string;
  breadcrumb: string[];
}

export type InclusionClass = "synonyms" | "extinct" | "uncertain" | "unassigned";

/** Discriminated union of every API result.

The React components branch on ``status`` rather than catching
exceptions; this keeps the state machine explicit and testable.
*/

export type ApiResult<T> =
  | { status: "ok"; data: T }
  | { status: "not-found"; detail: string }
  | { status: "ambiguous"; candidates: AmbiguityCandidate[] }
  | { status: "error"; detail: string };

// ---------------------------------------------------------------------------
// Low-level fetch helper
// ---------------------------------------------------------------------------

const DEFAULT_BASE_URL = "/api";

async function apiGet<T>(
  path: string,
  init?: { signal?: AbortSignal },
): Promise<ApiResult<T>> {
  try {
    const res = await fetch(`${DEFAULT_BASE_URL}${path}`, {
      signal: init?.signal,
      headers: { Accept: "application/json" },
    });
    if (res.status === 200) {
      const data = (await res.json()) as T;
      return { status: "ok", data };
    }
    if (res.status === 404) {
      const body = (await res.json().catch(() => ({}))) as { detail?: string };
      return {
        status: "not-found",
        detail: body.detail ?? "not found",
      };
    }
    if (res.status === 409) {
      const body = (await res.json()) as {
        detail?: string;
        candidates?: AmbiguityCandidate[];
      };
      return {
        status: "ambiguous",
        candidates: body.candidates ?? [],
      };
    }
    const body = (await res.json().catch(() => ({}))) as { detail?: string };
    return {
      status: "error",
      detail: body.detail ?? `HTTP ${res.status}`,
    };
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      // The caller aborted; surface as a non-error so the component
      // can clear its loading state without an alert.
      return { status: "not-found", detail: "aborted" };
    }
    return {
      status: "error",
      detail: err instanceof Error ? err.message : "network error",
    };
  }
}

// ---------------------------------------------------------------------------
// High-level API methods
// ---------------------------------------------------------------------------

export async function fetchRoots(
  init?: { signal?: AbortSignal },
): Promise<ApiResult<TaxonResponse[]>> {
  return apiGet<TaxonResponse[]>("/kingdoms", init);
}

/**
 * Deprecated alias for ``fetchRoots``.
 *
 * Keep the old name alive so external callers (and legacy tests)
 * can still resolve ``/api/kingdoms`` through the typed client.
 * The endpoint returns cascade roots (Biota + Viruses under
 * ChecklistBank), not kingdom-rank taxa; the label "Kingdoms"
 * is a historical artifact from the GBIF-backed resolver that
 * pre-dated the CLB migration.
 */
export const fetchKingdoms = fetchRoots;

export async function fetchChildren(
  parentSegments: string[],
  rank: "phyla" | "classes" | "orders" | "families" | "genera",
  init?: { signal?: AbortSignal },
): Promise<ApiResult<TaxonResponse[]>> {
  return apiGet<TaxonResponse[]>(
    `/${encodeSegments(parentSegments)}/${rank}`,
    init,
  );
}

/**
 * Path-aware cascade helper. Walks the caller-supplied path of
 * canonical names and returns the direct children of the deepest
 * resolved taxon, regardless of rank name. ``next_tiers`` carries
 * one ``NextTier`` per distinct rank group below the parent; the
 * cascade UI renders one dropdown per group with the dropdown's
 * label taken from ``tier.label``. ``next_tiers`` is ``null`` when
 * the deepest taxon has no children (the cascade has reached a
 * leaf).
 *
 * This is the building block for the dynamic cascade: each call
 * returns the children for the next dropdown. The frontend renders
 * a new dropdown per tier group in ``next_tiers`` until the array
 * is null, at which point it loads the species list for the
 * deepest taxon via :func:`fetchSpeciesList`.
 */
export async function fetchPathChildren(
  parentSegments: string[],
  init?: { signal?: AbortSignal },
): Promise<ApiResult<PathChildrenResponse>> {
  const path = parentSegments.map(encodeURIComponent).join("|");
  return apiGet<PathChildrenResponse>(`/path-children?path=${path}`, init);
}

export async function fetchSpecies(
  parentSegments: string[],
  init?: {
    signal?: AbortSignal;
    include?: InclusionClass[];
    cursor?: string;
  },
): Promise<ApiResult<SpeciesListResponse>> {
  const params = new URLSearchParams();
  if (init?.include && init.include.length > 0) {
    params.set("include", init.include.join(","));
  }
  if (init?.cursor) {
    params.set("cursor", init.cursor);
  }
  const query = params.toString();
  const tail = query.length > 0 ? `?${query}` : "";
  return apiGet<SpeciesListResponse>(
    `/${encodeSegments(parentSegments)}/species${tail}`,
    init,
  );
}

/**
 * Path-aware species-list resolver.
 *
 * Walks the caller-supplied path (same contract as
 * :func:`fetchPathChildren`) and returns the species-rank children
 * of the deepest resolved taxon, paginated. Used by the cascade
 * when the deepest snapshot has ``next_tiers = null`` —
 * i.e. the cascade has reached a genus row and the frontend
 * needs the species under it.
 *
 * The path must include the genus as the last segment. The
 * resolver walks the path case-insensitively and returns a 404
 * (translated to ``ApiResult.not-found``) when any segment does
 * not resolve.
 */
export async function fetchSpeciesList(
  pathSegments: string[],
  init?: {
    signal?: AbortSignal;
    include?: InclusionClass[];
    cursor?: string;
  },
): Promise<ApiResult<SpeciesListResponse>> {
  const path = pathSegments.map(encodeURIComponent).join("|");
  const params = new URLSearchParams();
  if (init?.include && init.include.length > 0) {
    params.set("include", init.include.join(","));
  }
  if (init?.cursor) {
    params.set("cursor", init.cursor);
  }
  const query = params.toString();
  const tail = query.length > 0 ? `?${query}` : "";
  return apiGet<SpeciesListResponse>(`/species-list?path=${path}${tail}`, init);
}

/**
 * Path-aware taxon-links resolver.
 *
 * Walks the caller-supplied cascade path (no epithet) and
 * returns the 13-link substitution for the deepest taxon the
 * resolver lands on. Used by the breadcrumb segment click —
 * clicking a segment asks for the links whose ``{q}`` is the
 * canonical name of that taxon's row, not of any species
 * below it.
 *
 * The path is encoded with ``encodeURIComponent`` per
 * segment, then joined with ``%7C`` (the percent-encoded
 * pipe). The backend captures the whole suffix as a single
 * ``{path:path}`` segment and splits on ``|`` server-side;
 * leaving the pipe un-encoded would technically still work
 * for the path-children query-string endpoint, but the
 * ``{path:path}`` capture encodes the separator so the
 * captured string round-trips deterministically through any
 * proxy that strips query strings.
 *
 * The backend enforces a 1–7 segment cap. The client treats
 * any 4xx response that does not carry the discriminated
 * union we know about as a generic ``error`` so the App
 * panel can show the server message.
 */
export async function fetchTaxonLinks(
  pathSegments: string[],
  init?: { signal?: AbortSignal },
): Promise<ApiResult<TaxonLinksResponse>> {
  const path = pathSegments
    .map((s) =>
      encodeURIComponent(s).replace(/[!'()*]/g, (c) =>
        `%${c.charCodeAt(0).toString(16).toUpperCase().padStart(2, "0")}`,
      ),
    )
    .join("%7C");
  return apiGet<TaxonLinksResponse>(`/${path}/taxon-links`, init);
}

export async function fetchSpeciesByPair(
  genus: string,
  epithet: string,
  init?: { signal?: AbortSignal },
): Promise<ApiResult<SpeciesLookupResponse>> {
  return apiGet<SpeciesLookupResponse>(
    `/species/${encodeURIComponent(genus)}/${encodeURIComponent(epithet)}`,
    init,
  );
}

export async function fetchLinks(
  parentSegments: string[],
  epithet: string,
  init?: { signal?: AbortSignal },
): Promise<ApiResult<LinksResponse>> {
  // Drop the cascade root (``Biota`` / ``Viruses``) so the path
  // matches the backend's 6-segment contract:
  // ``/{kingdom}/{phylum}/{class}/{order}/{family}/{genus}/{epithet}/links``.
  // The cascade always starts with the CLB superdomain as the
  // first pick, so the segments after the first are the breadcrumb.
  const breadcrumb =
    parentSegments[0]?.toLowerCase() === "biota" ||
    parentSegments[0]?.toLowerCase() === "viruses"
      ? parentSegments.slice(1)
      : parentSegments;
  return apiGet<LinksResponse>(
    `/${encodeSegments([...breadcrumb, epithet])}/links`,
    init,
  );
}

// ---------------------------------------------------------------------------
// Pure helpers (testable without React)
// ---------------------------------------------------------------------------

/** Encode the cascade path into the URL-encoded segments the API expects.

``encodeURIComponent`` leaves some characters un-encoded (notably
``()``, ``!``, ``*``, ``'``). The taxon backend expects every byte
to be percent-encoded so the resolver can match the canonical
``name`` column byte-for-byte. This helper uses a fixed
``encodeURI`` style regex over the full segment so the encoding is
deterministic.
*/
export function encodeSegments(segments: string[]): string {
  return segments
    .map((s) => encodeURIComponent(s).replace(/[!'()*]/g, (c) => {
      return `%${c.charCodeAt(0).toString(16).toUpperCase().padStart(2, "0")}`;
    }))
    .join("/");
}

/** Split a species canonical name (``Genus epithet``) into the pair. */
export function splitSpeciesName(canonical: string): {
  genus: string;
  epithet: string;
} {
  const parts = canonical.trim().split(/\s+/);
  if (parts.length < 2) {
    return { genus: canonical, epithet: "" };
  }
  return { genus: parts[0] ?? "", epithet: parts.slice(1).join(" ") };
}

/** Build the inclusion-class CSV from a Set of toggles. */
export function inclusionCsv(include: Set<InclusionClass>): string {
  return Array.from(include).join(",");
}

/**
 * Build the breadcrumb trail from the parent-path segments. The first
 * segment is dropped when it is the Biota superdomain so the
 * breadcrumb reads Kingdom → … → Genus, mirroring the Phase 3 design
 * and the backend's ``build_breadcrumb`` helper.
 */
export function buildBreadcrumb(segments: string[]): string[] {
  if (segments.length === 0) return [];
  const trail = [...segments];
  if (trail[0]?.toLowerCase() === "biota") {
    trail.shift();
  }
  return trail;
}