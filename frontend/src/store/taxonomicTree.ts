/** Zustand store for the TaxonomicTree surface.

The tree caches children by their parent's ``id`` so the lazy
fetch survives unmount and any subsequent re-expand reads from
cache. The store is the single source of truth for the tree view;
the ``TaxonomicTree`` component reads selectors and dispatches
actions via the imperative handle.

State:

- ``childrenByParentId`` — ``Map<parentId, TreeNodeResponse[]>``.
  The cache. Missing entries mean "fetch on first expand".
- ``nextTiersByParentId`` — ``Map<parentId, TreeNodeTier[]>`` seeded
  from the ``next_tiers`` envelope of the direct-children fetch.
  Missing entries mean "no tiers below the parent (true leaf)";
  the component renders nothing.
- ``tierRowsByKey`` — ``Map<key, {rows, nextCursor}>`` carrying the
  paginated rows for each ``(parentId, rank)`` pair. Keyed by
  ``"${parentId}:${rank}"`` so a parent's tier rows never collide.
- ``expandedIds`` — ``Set<id>`` of currently expanded rows. The
  component reads this to decide which rows to render and
  dispatches ``toggleExpand(id)`` to mutate.
- ``rootIds`` — the parent_id=0 fetch result. ``null`` until the
  first boot effect fires.
- ``loadingParentIds`` — parents whose fetch is in flight. The
  row paints ``aria-busy="true"`` while a parent is in this set.
- ``errorByParentId`` — ``Map<parentId, string>`` of deferred
  fetch errors. The row renders the retry link while a parent
  has a error entry.

Actions:

- ``loadRoots()`` — fires the parent_id=0 fetch and stores the
  children in ``childrenByParentId``.
- ``ensureChildren(parentId)`` — fetches and caches the children
  of a parent if the cache misses; idempotent on a cache hit.
- ``toggleExpand(id)`` — flips the expanded flag for ``id``.
- ``loadMore(parentId, rank)`` — calls :func:`fetchTierPage` for the
  cached tier slice and appends rows to ``tierRowsByKey``.
- ``setError(parentId, msg)`` — records an error for a parent
  so the retry link can render.

The store is intentionally focused on the tree. The
explored-path state (``cascadePath``) lives in its own store;
the component fans both out.
*/

import { create } from "zustand";

import {
  type ApiResult,
  fetchTierPage,
  fetchTreeNode,
  type TreeNodeResponse,
  type TreeNodeTier,
} from "../api";

export interface TierRowsEntry {
  rows: TreeNodeResponse[];
  nextCursor: string | null;
}

/** Build the cache key for the per-tier rows slice.

Format is documented in the store header (``"${parentId}:${rank}"``);
exported as a pure helper so the store actions and the test fixture
agree on the contract.
*/
export function tierRowsKey(parentId: number, rank: string): string {
  return `${parentId}:${rank}`;
}

/**
 * Merge the ``next_tiers`` envelope from a children response into
 * the cache. Returns a new ``Map`` so callers can stash it directly
 * into the store via ``set({ nextTiersByParentId })``; the cache is
 * left untouched when ``next_tiers`` is ``null`` (true-leaf parent
 * — no tiers to seed, but no overwrite either).
 */
function seedNextTiersFor(
  previous: Map<number, TreeNodeTier[]>,
  parentId: number,
  envelope: TreeNodeTier[] | null,
): Map<number, TreeNodeTier[]> {
  if (envelope === null) return previous;
  const next = new Map(previous);
  next.set(parentId, envelope);
  return next;
}

export interface TreeState {
  childrenByParentId: Map<number, TreeNodeResponse[]>;
  /** Per-parent tier envelope seeded from the children fetch. */
  nextTiersByParentId: Map<number, TreeNodeTier[]>;
  /** Per-tier paginated rows keyed by ``"${parentId}:${rank}"``. */
  tierRowsByKey: Map<string, TierRowsEntry>;
  expandedIds: Set<number>;
  rootIds: number[] | null;
  loadingParentIds: Set<number>;
  errorByParentId: Map<number, string>;
  /** The current include_extinct filter. The root and any subsequent
   * child fetch carries this flag so a toggle triggers a refetch of
   * every cached children slice. */
  includeExtinct: boolean;

  loadRoots: () => Promise<void>;
  ensureChildren: (parentId: number) => Promise<void>;
  toggleExpand: (id: number) => void;
  /** Fetch the next page for the cached tier slice. On the first call
   * (key missing) the cursor is empty so the backend returns the
   * first page; subsequent calls forward the cached cursor verbatim.
   * The rows are appended (not replaced) so the tier group keeps
   * already-rendered rows visible while the next page is in flight. */
  loadMore: (parentId: number, rank: string) => Promise<void>;
  setError: (parentId: number, msg: string) => void;
  clearError: (parentId: number) => void;
  /** Walk the parent chain for ``targetId`` and expand each node so the
   * target row becomes visible. Returns the chain ``[root, …, parent]``
   * once every fetch resolves; the caller focuses the target row. */
  revealNode: (targetId: number) => Promise<number[]>;
  /** Set the include_extinct flag and refetch every cached children
   * slice (root + any ancestor the user already expanded). Resets
   * the expanded set so the new filter renders deterministically. */
  setIncludeExtinct: (value: boolean) => Promise<void>;
}

export const useTaxonomicTree = create<TreeState>((set, get) => ({
  childrenByParentId: new Map(),
  nextTiersByParentId: new Map(),
  tierRowsByKey: new Map(),
  expandedIds: new Set(),
  rootIds: null,
  loadingParentIds: new Set(),
  errorByParentId: new Map(),
  includeExtinct: true,

  loadRoots: async () => {
    const { childrenByParentId, loadingParentIds, includeExtinct } = get();
    if (childrenByParentId.has(0)) return;
    const nextLoading = new Set(loadingParentIds);
    nextLoading.add(0);
    set({ loadingParentIds: nextLoading });
    const result: ApiResult<{
      parent: TreeNodeResponse;
      children: TreeNodeResponse[];
      next_tiers: TreeNodeTier[] | null;
      next_cursor: string | null;
    }> = await fetchTreeNode(0, { includeExtinct });
    const clearedLoading = new Set(get().loadingParentIds);
    clearedLoading.delete(0);
    if (result.status === "ok") {
      const next = new Map(get().childrenByParentId);
      next.set(0, result.data.children);
      const nextTiers = seedNextTiersFor(
        get().nextTiersByParentId,
        0,
        result.data.next_tiers,
      );
      set({
        childrenByParentId: next,
        nextTiersByParentId: nextTiers,
        rootIds: result.data.children.map((row) => row.id),
        loadingParentIds: clearedLoading,
      });
    } else {
      const errs = new Map(get().errorByParentId);
      errs.set(0, result.status === "ambiguous" ? "ambiguous" : result.detail);
      set({ loadingParentIds: clearedLoading, errorByParentId: errs });
    }
  },

  ensureChildren: async (parentId: number) => {
    const { childrenByParentId, loadingParentIds, includeExtinct } = get();
    if (childrenByParentId.has(parentId)) return;
    if (loadingParentIds.has(parentId)) return;
    const nextLoading = new Set(loadingParentIds);
    nextLoading.add(parentId);
    set({ loadingParentIds: nextLoading });
    const result = await fetchTreeNode(parentId, { includeExtinct });
    const clearedLoading = new Set(get().loadingParentIds);
    clearedLoading.delete(parentId);
    if (result.status === "ok") {
      const next = new Map(get().childrenByParentId);
      next.set(parentId, result.data.children);
      const nextTiers = seedNextTiersFor(
        get().nextTiersByParentId,
        parentId,
        result.data.next_tiers,
      );
      const errs = new Map(get().errorByParentId);
      errs.delete(parentId);
      set({
        childrenByParentId: next,
        nextTiersByParentId: nextTiers,
        loadingParentIds: clearedLoading,
        errorByParentId: errs,
      });
    } else {
      const errs = new Map(get().errorByParentId);
      errs.set(
        parentId,
        result.status === "ambiguous" ? "ambiguous" : result.detail,
      );
      set({ loadingParentIds: clearedLoading, errorByParentId: errs });
    }
  },

  toggleExpand: (id: number) => {
    const { expandedIds } = get();
    const next = new Set(expandedIds);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    set({ expandedIds: next });
  },

  /**
   * Fetch the next page for ``(parentId, rank)`` and append the rows
   * to the cached slice. On the first call the slice is missing —
   * the backend returns ``cursor = null`` so the cache is seeded
   * with the first page. Subsequent calls forward the cached cursor
   * (the backend returns the next opaque cursor or ``null`` at the
   * last page so the next call from the UI either starts again or
   * lands on the empty state).
   *
   * The cached ``next_cursor`` of the last tier entry in the source
   * envelope (``nextTiersByParentId``) is the seeded cursor on the
   * very first :func:`loadMore` so we don't double-fetch the first
   * page the children response already returned.
   */
  loadMore: async (parentId: number, rank: string) => {
    const key = tierRowsKey(parentId, rank);
    const cached = get().tierRowsByKey.get(key);
    let cursor: string | null = cached?.nextCursor ?? null;
    if (cached === undefined) {
      // Seed the cursor from the tier envelope the children fetch
      // already returned so the first :func:`loadMore` does not
      // re-request rows the backend already sent.
      const tiers = get().nextTiersByParentId.get(parentId);
      const tier = tiers?.find((t) => t.rank === rank);
      cursor = tier?.next_cursor ?? null;
    }
    const result = await fetchTierPage(parentId, rank, cursor);
    if (result.status !== "ok") return;
    const incoming = result.data.children;
    const nextRows = cached === undefined
      ? incoming
      : [...cached.rows, ...incoming];
    const nextMap = new Map(get().tierRowsByKey);
    nextMap.set(key, {
      rows: nextRows,
      nextCursor: result.data.next_cursor,
    });
    set({ tierRowsByKey: nextMap });
  },

  setError: (parentId: number, msg: string) => {
    const errs = new Map(get().errorByParentId);
    errs.set(parentId, msg);
    set({ errorByParentId: errs });
  },

  clearError: (parentId: number) => {
    const errs = new Map(get().errorByParentId);
    errs.delete(parentId);
    set({ errorByParentId: errs });
  },

  /**
   * Walk the parent chain from ``targetId`` to the root and expand
   * every node along the way. The action mutates ``expandedIds`` so
   * the tree re-renders with every ancestor open.
   *
   * Implementation: the chain is reconstructed backwards — for each
   * node in the chain we look up its parent in the
   * ``childrenByParentId`` cache; when a parent is missing the
   * action calls ``ensureChildren(parentId)`` so the next iteration
   * finds it. The returned promise resolves with the chain
   * ``[root, …, parent(targetId)]`` so the caller can focus the
   * target row.
   */
  revealNode: async (targetId: number): Promise<number[]> => {
    // Strategy: walk the parent chain BACKWARDS from ``targetId``
    // to the root. The cache (``childrenByParentId``) only knows
    // about nodes the user has expanded, so when the target is not
    // cached we ask the backend directly for ``targetId``'s
    // children — the response includes the ``parent`` envelope with
    // its ``parent_id``, which is the link we need to climb.
    //
    // The loop terminates when ``parent_id`` is ``null`` (the
    // target's parent is a root) or when the parent's own
    // ``childrenByParentId`` slot is already populated (we have
    // enough information to render the chain without further
    // fetches).
    const chain: number[] = [targetId];
    let safety = 0;
    while (safety < 32) {
      // Locate ``headParentId`` for the current head. We try the
      // cache first; if the head is not cached we fetch its
      // children so the backend hands us its ``parent`` envelope.
      const headId = chain[chain.length - 1]!;
      let headParentId: number | null | undefined;
      const cache = get().childrenByParentId;
      // Look up the head across every cached level. The head may
      // live as a child of any parent the user has expanded.
      let found: number | null | undefined = undefined;
      for (const [, kids] of cache) {
        const row = kids.find((r) => r.id === headId);
        if (row !== undefined) {
          found = row.parent_id;
          break;
        }
      }
      headParentId = found;
      if (headParentId === null) {
        // The head sits in the cache with ``parent_id`` null — it
        // IS the root, we are done.
        break;
      }
      if (headParentId === undefined) {
        // The head is not in the cache. Fetch its children so the
        // backend returns the ``parent`` envelope.
        const result = await fetchTreeNode(headId, {
          includeExtinct: get().includeExtinct,
        });
        if (result.status !== "ok") {
          // Cannot walk further; bail with what we have so the
          // caller can still focus the target row.
          break;
        }
        const newCache = new Map(get().childrenByParentId);
        newCache.set(headId, result.data.children);
        // The backend's ``parent`` envelope gives us the next
        // ancestor we need.
        headParentId = result.data.parent?.parent_id ?? null;
      }
      if (headParentId === null) break;
      chain.push(headParentId);
      safety += 1;
    }
    // Reverse so the root sits first.
    chain.reverse();
    // Expand every node in the chain and ensure each level's
    // children are cached so the next ancestor in the chain is
    // rendered.
    const nextExpanded = new Set(get().expandedIds);
    for (const id of chain) {
      nextExpanded.add(id);
      await get().ensureChildren(id);
    }
    set({ expandedIds: nextExpanded });
    return chain;
  },

  /**
   * Toggle the ``include_extinct`` filter and refetch every cached
   * children slice with the new flag. The expanded set is reset so
   * the user sees the filter take effect from the root down; the
   * focus is cleared so the next interaction does not retain a stale
   * pointer.
   */
  setIncludeExtinct: async (value: boolean): Promise<void> => {
    const { includeExtinct, childrenByParentId } = get();
    if (value === includeExtinct) return;
    set({
      includeExtinct: value,
      childrenByParentId: new Map(),
      nextTiersByParentId: new Map(),
      tierRowsByKey: new Map(),
      expandedIds: new Set(),
      rootIds: null,
      errorByParentId: new Map(),
      loadingParentIds: new Set(),
    });
    // Refetch the root with the new flag. Child slices are refetched
    // lazily on the next expand so the toggle does not pay for the
    // full subtree walk upfront.
    await get().loadRoots();
    void childrenByParentId;
  },
}));
