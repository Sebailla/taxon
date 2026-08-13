/** Typed API client for the taxon backend.

The client wraps the seven endpoints shipped in Sub-PRs 2A/2B/2C:

- ``GET /api/kingdoms``                                  — list kingdoms.
- ``GET /api/{kingdom}/phyla``                          — list phyla.
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
  id: number;
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

export interface PathChildrenResponse {
  parent: TaxonResponse;
  children: TaxonResponse[];
  next_rank_hint: string | null;
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

export async function fetchKingdoms(
  init?: { signal?: AbortSignal },
): Promise<ApiResult<TaxonResponse[]>> {
  return apiGet<TaxonResponse[]>("/kingdoms", init);
}

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
 * resolved taxon, regardless of rank name. ``next_rank_hint`` is
 * the rank that occurs most often among the children (the mode),
 * or ``null`` when the children are empty (the cascade has reached
 * a leaf).
 *
 * This is the building block for the dynamic cascade: each call
 * returns the children for the next dropdown. The frontend renders
 * a new dropdown per non-empty response until ``next_rank_hint``
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
 * when the deepest snapshot has ``next_rank_hint = null`` —
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
  return apiGet<LinksResponse>(
    `/${encodeSegments([...parentSegments, epithet])}/links`,
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