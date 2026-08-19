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

import { z } from "zod";

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

/**
 * Tree node payload — the items the TaxonomicTree (PR 3) renders.
 *
 * Extends :interface:`TaxonResponse` with the three fields the
 * taxonomy tree needs but the legacy cascade does not:
 *
 * - ``has_children`` — pre-computed via EXISTS so the row's caret
 *   can render without a second fetch.
 * - ``species_count`` — descendant species count, ``null`` when the
 *   parent has >100k direct children (the recursive CTE would block
 *   the response).
 * - ``authorship`` — the citation tail split from ``display_name``
 *   so the row can render ``rank: Name Authorship • N spp.`` without
 *   re-parsing the display name on every render.
 */
export interface TreeNodeResponse extends TaxonResponse {
  has_children: boolean;
  species_count: number | null;
  authorship: string;
}

/**
 * One cascade tier below the parent in
 * ``GET /api/tree/children?parent_id={id}``.
 *
 * Mirrors the backend's ``TreeNodeTier`` in ``taxon/api/schemas.py``.
 * The frontend renders one tier group per :attr:`rank`; the rows
 * arrive paginated inside :attr:`children`, capped at the requested
 * ``tier_limit``. :attr:`next_cursor` is non-empty when more rows
 * exist so :func:`fetchTierPage` can advance.
 */
export interface TreeNodeTier {
  rank: string;
  label: string;
  examples: string[];
  children: TreeNodeResponse[];
  next_cursor: string | null;
}

/**
 * Envelope of ``GET /api/tree/children?parent_id=N``.
 *
 * Mirrors the backend's ``TreeChildrenResponse``: the parent
 * (the taxon the request resolved to) + the direct children +
 * an opaque ``next_cursor`` (always ``null`` for the first PR; the
 * 200-row cap fits in a single page).
 *
 * ``next_tiers`` is additive — older clients see ``null`` and keep
 * working. When the parent has non-direct descendants at multiple
 * ranks, the backend returns one :class:`TreeNodeTier` per bucket
 * (phylum / class / order / family / genus / species). The frontend
 * renders one tier group per entry; each tier carries its own
 * paginated ``children`` + ``next_cursor`` so the load-more can
 * advance per tier independently.
 */
export interface TreeChildrenResponse {
  parent: TreeNodeResponse;
  children: TreeNodeResponse[];
  next_tiers: TreeNodeTier[] | null;
  next_cursor: string | null;
}

/**
 * Envelope of ``GET /api/tree/search?q=…``.
 *
 * Mirrors the backend's ``TreeSearchResponse``. The backend caps
 * the result at 8 items (exact > prefix > substring ranking) so
 * the frontend never has to truncate.
 */
export interface TreeSearchResponse {
  items: TreeNodeResponse[];
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

const workspaceSpeciesSchema = z.object({
  genus: z.string(),
  epithet: z.string(),
  explored_at: z.string(),
});
const exploredListSchema = z.object({ species: z.array(workspaceSpeciesSchema) });
const folderSchema = z.object({ path: z.string(), exists: z.boolean().default(true) });
const visitedListSchema = z.object({
  genus: z.string(),
  epithet: z.string(),
  sources: z.array(z.object({ source: z.string(), visited_at: z.string() })),
});

export type ExploredListResponse = z.infer<typeof exploredListSchema>;
export type SpeciesFolderResponse = z.infer<typeof folderSchema>;
export type LinkVisitedListResponse = z.infer<typeof visitedListSchema>;

export function speciesKey(genus: string, epithet: string): string {
  return encodeURIComponent(`${genus}|${epithet}`);
}

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

async function apiRequest<T>(
  path: string,
  method: "GET" | "POST" | "DELETE",
  schema?: z.ZodType<T>,
): Promise<ApiResult<T>> {
  try {
    const res = await fetch(`${DEFAULT_BASE_URL}${path}`, {
      method,
      headers: { Accept: "application/json" },
    });
    if (res.status === 200 || res.status === 201) {
      const parsed = schema?.safeParse(await res.json());
      if (parsed && !parsed.success) {
        return { status: "error", detail: `Invalid response: ${parsed.error.message}` };
      }
      return { status: "ok", data: parsed?.data as T };
    }
    if (res.status === 204) return { status: "ok", data: undefined as T };
    const body = (await res.json().catch(() => ({}))) as { detail?: string };
    if (res.status === 404) return { status: "not-found", detail: body.detail ?? "not found" };
    return { status: "error", detail: body.detail ?? `HTTP ${res.status}` };
  } catch (err) {
    return { status: "error", detail: err instanceof Error ? err.message : "network error" };
  }
}

export function fetchExploredList(): Promise<ApiResult<ExploredListResponse>> {
  return apiRequest("/explored/list", "GET", exploredListSchema);
}
export function postExplored(genus: string, epithet: string): Promise<ApiResult<z.infer<typeof workspaceSpeciesSchema>>> {
  return apiRequest(`/explored/${encodeURIComponent(genus)}/${encodeURIComponent(epithet)}`, "POST", workspaceSpeciesSchema);
}
export function deleteExplored(genus: string, epithet: string): Promise<ApiResult<void>> {
  return apiRequest(`/explored/${encodeURIComponent(genus)}/${encodeURIComponent(epithet)}`, "DELETE");
}
export function fetchSpeciesFolder(genus: string, epithet: string): Promise<ApiResult<SpeciesFolderResponse>> {
  return apiRequest(`/species-folder/${encodeURIComponent(genus)}/${encodeURIComponent(epithet)}`, "GET", folderSchema);
}
export function createSpeciesFolder(genus: string, epithet: string): Promise<ApiResult<SpeciesFolderResponse>> {
  return apiRequest(`/species-folder/${encodeURIComponent(genus)}/${encodeURIComponent(epithet)}`, "POST", folderSchema);
}
export function fetchLinkVisited(genus: string, epithet: string): Promise<ApiResult<LinkVisitedListResponse>> {
  return apiRequest(`/link-visited/${encodeURIComponent(genus)}/${encodeURIComponent(epithet)}`, "GET", visitedListSchema);
}
export function postLinkVisited(genus: string, epithet: string, source: string): Promise<ApiResult<void>> {
  return apiRequest(`/link-visited/${encodeURIComponent(genus)}/${encodeURIComponent(epithet)}/${encodeURIComponent(source)}`, "POST");
}
export function deleteLinkVisited(genus: string, epithet: string, source: string): Promise<ApiResult<void>> {
  return apiRequest(`/link-visited/${encodeURIComponent(genus)}/${encodeURIComponent(epithet)}/${encodeURIComponent(source)}`, "DELETE");
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

/** Default row cap per ``/api/tree/children`` request.

The backend defaults to 200 rows per call. The frontend reuses
this value when building the URL inline so the lazy fetch and
the cache invalidation share the same constant.
*/
export const TREE_CHILDREN_DEFAULT_LIMIT = 200;

/** Hard cap for the search dropdown (8 results per the spec). */
export const TREE_SEARCH_DEFAULT_LIMIT = 8;

/**
 * Build the URL for ``GET /api/tree/children`` with the agreed
 * query-string order.
 *
 * The canonical order is ``parent_id``, ``limit``, ``include_extinct``,
 * then the optional ``tier`` + ``cursor`` pair (when paginating
 * per-tier rows). The function is exported because both the
 * tree component and the store cache use it inline; the test suite
 * pins the exact wire shape without going through ``fetch``.
 *
 * The returned path is RELATIVE (no ``/api`` prefix) because the
 * ``apiGet`` helper prepends ``/api`` before issuing the request.
 * The test suite asserts the URL exactly as ``fetch`` sees it --
 * the ``/api`` prefix is the helper's concern, not the
 * URL-builder's.
 */
export function buildTreeChildrenUrl(args: {
  parentId: number;
  limit?: number;
  includeExtinct?: boolean;
  tier?: string;
  cursor?: string | null;
  tierLimit?: number;
}): string {
  const params = new URLSearchParams();
  params.set("parent_id", String(args.parentId));
  params.set("limit", String(args.limit ?? TREE_CHILDREN_DEFAULT_LIMIT));
  if (args.includeExtinct === false) {
    params.set("include_extinct", "false");
  }
  if (args.tier !== undefined) {
    params.set("tier", args.tier);
  }
  if (args.cursor !== undefined && args.cursor !== null) {
    params.set("cursor", args.cursor);
  }
  if (args.tierLimit !== undefined) {
    params.set("tier_limit", String(args.tierLimit));
  }
  return `/tree/children?${params.toString()}`;
}

/**
 * Fetch the paginated page for a single tier below a parent.
 *
 * Routes through ``/api/tree/children?parent_id=...&tier=...&cursor=...&tier_limit=...``.
 * The backend narrows the ``next_tiers`` envelope to the single
 * tier the client asked for and returns its children slice + the
 * next opaque cursor (or ``null`` at the last page). The component
 * uses this with ``cursor = null`` on the first expand and with the
 * cached cursor on every subsequent :func:`loadMore` call.
 *
 * ``parentId = 0`` is the documented sentinel for the root list
 * (rows with ``parent_id IS NULL``); the backend translates it to
 * the IS-NULL query.
 *
 * The ``tier_limit`` query param is always present (defaulted to 50
 * here so the URL the store builds is fully determined — the
 * backend clamps above 200 silently and rejects below 1 with 4xx).
 */
export const FETCH_TIER_PAGE_DEFAULT_LIMIT = 50;

export async function fetchTierPage(
  parentId: number,
  tier: string,
  cursor: string | null,
  init?: { signal?: AbortSignal; tierLimit?: number },
): Promise<ApiResult<TreeChildrenResponse>> {
  const url = buildTreeChildrenUrl({
    parentId,
    tier,
    cursor: cursor ?? "",
    tierLimit: init?.tierLimit ?? FETCH_TIER_PAGE_DEFAULT_LIMIT,
  });
  return apiGet<TreeChildrenResponse>(url, init);
}

/**
 * Fetch the direct children of a parent taxon.
 *
 * ``parentId = 0`` is the documented sentinel for the root list
 * (rows with ``parent_id IS NULL``); the backend translates it to
 * the IS-NULL query. The frontend passes ``0`` from the
 * ``TaxonomicTree`` boot effect.
 *
 * The ``includeExtinct`` flag defaults to ``true`` (extinct rows
 * are visible). The TaxonomicTree's "Extant only" checkbox sets
 * it to ``false`` so the next fetch returns the filtered slice.
 */
export async function fetchTreeNode(
  parentId: number,
  init?: { signal?: AbortSignal; includeExtinct?: boolean; limit?: number },
): Promise<ApiResult<TreeChildrenResponse>> {
  const url = buildTreeChildrenUrl({
    parentId,
    limit: init?.limit,
    includeExtinct: init?.includeExtinct,
  });
  return apiGet<TreeChildrenResponse>(url, init);
}

/**
 * Fetch the search results for a free-text query.
 *
 * The backend caps the response at 8 items (the ``taxon-tree-search``
 * spec hard-caps the dropdown at 8). The frontend never sends a
 * different limit for the first PR; the optional parameter is
 * reserved for the eventual "Load more" affordance.
 */
export async function fetchTreeSearch(
  q: string,
  init?: { signal?: AbortSignal; limit?: number },
): Promise<ApiResult<TreeSearchResponse>> {
  const params = new URLSearchParams();
  params.set("q", q);
  params.set("limit", String(init?.limit ?? TREE_SEARCH_DEFAULT_LIMIT));
  return apiGet<TreeSearchResponse>(`/tree/search?${params.toString()}`, init);
}

/**
 * A debounced wrapper around the search fetch.
 *
 * The "Find taxon" input issues one request per keystroke. The
 * spec pins a 200ms debounce so the backend sees a single
 * request for the final value, not a flurry of intermediate
 * requests. The factory shape mirrors the React custom-hook
 * contract: the returned function is the debounced trigger, the
 * returned ``cancel`` clears the pending timer, and the Promise
 * resolves with the same ``ApiResult`` the fetch would have
 * returned.
 *
 * The wrapper is decoupled from React so the test suite can pin
 * the behaviour with fake timers (see ``api.treeSearch.test.ts``).
 * The TaxonomicTree subscribes the input's ``onChange`` to the
 * returned function and unsubscribes via ``cancel`` on unmount.
 */
export function createDebouncedSearch(deps: {
  fetch: (q: string) => Promise<ApiResult<TreeSearchResponse>>;
  delay: number;
}): {
  (q: string): Promise<ApiResult<TreeSearchResponse>>;
  cancel: () => void;
} {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let pendingResolve:
    | ((value: ApiResult<TreeSearchResponse>) => void)
    | null = null;
  let pendingReject: ((reason: unknown) => void) | null = null;

  function firePending(value: ApiResult<TreeSearchResponse>): void {
    const resolve = pendingResolve;
    const reject = pendingReject;
    pendingResolve = null;
    pendingReject = null;
    if (resolve !== null) {
      resolve(value);
    } else if (reject !== null) {
      // ``cancel`` was called but the fetch still resolved; the
      // caller has already moved on, so swallow the dangling
      // rejection silently.
      void reject;
    }
  }

  const debounced = (q: string): Promise<ApiResult<TreeSearchResponse>> => {
    if (timer !== null) {
      clearTimeout(timer);
    }
    return new Promise<ApiResult<TreeSearchResponse>>((resolve, reject) => {
      pendingResolve = resolve;
      pendingReject = reject;
      timer = setTimeout(() => {
        timer = null;
        void deps.fetch(q).then(firePending, (err: unknown) => {
          // Network failures are mapped to ``error`` by ``apiGet``,
          // so the fetch rarely rejects. If it does (e.g. an
          // unexpected programming error), surface the rejection
          // to the caller.
          firePending({
            status: "error",
            detail: err instanceof Error ? err.message : "unknown error",
          });
          void reject;
        });
      }, deps.delay);
    });
  };

  debounced.cancel = (): void => {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
    pendingResolve = null;
    pendingReject = null;
  };

  return debounced;
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