/** Pure state machine for the path-aware Cascade component.

Extracted from ``Cascade.tsx`` so the component file exports only
components (Vite's ``react-refresh`` HMR requires that for fast
refresh to work cleanly). The reducer and helpers are pure, have
no React imports, and can be tested in isolation.

The cascade renders N dropdowns — one per rank layer the backend
has served. CoL ships 40+ ranks with intermediate ranks
(subphylum, gigaclass, infraphylum, parvphylum, megaclass,
subclass, suborder, ...) that the fixed six-rank ladder skipped.
Each layer keeps its own ``(children, next_tiers)`` snapshot so
the dropdowns for ancestor segments stay populated even after
the user picks a descendant — the user can then change a parent
and the descendant dropdowns reset.

The state machine:

- ``path`` is the dense list of canonical names the user has
  picked so far. The empty path means "show the root kingdom
  dropdown".
- ``levelByPath`` maps ``path.join("|")`` → ``(children,
  next_tiers)`` so each dropdown shows the children of its
  own path segment. The cascade reads the keys in order to
  render N dropdowns.
- ``species`` is loaded separately when the cascade reaches a
  leaf (a genus row whose children have ``next_tiers === null``).
*/

import type { NextTier, TaxonResponse } from "../api";
import type { InclusionClass } from "./Toggles";

export interface LevelSnapshot {
  children: TaxonResponse[];
  /**
   * Tier groups the backend returned for this level, or
   * ``null`` when the deepest taxon is a confirmed leaf
   * (no children at any rank). ``undefined`` while the
   * /path-children call is still in flight.
   */
  nextTiers: NextTier[] | null | undefined;
}

export interface CascadeState {
  /** Path of canonical names the user has picked so far. */
  path: string[];
  /**
   * Snapshot per path segment. Keys are the path up to and
   * including that segment, joined by ``|``. The first key is
   * the empty string (the kingdom list); each subsequent key
   * extends the path by one segment. The cascade renders one
   * dropdown per key in insertion order.
   */
  levelByPath: Record<string, LevelSnapshot>;
  /**
   * Async status for the most recent /path-children call.
   * ``"loading"`` while a new fetch is in flight; ``"error"``
   * when the last call returned a non-OK result.
   */
  currentLevelStatus: "idle" | "loading" | "error";
  /** Inclusion toggles (default empty = accepted only). */
  include: Set<InclusionClass>;
  /** Species list for the current genus (when the cascade has reached one). */
  species: TaxonResponse[];
  /** Species-list cursor and load status. */
  speciesStatus: "idle" | "loading" | "error";
  speciesCursor: string | null;
}

export type Action =
  | { type: "set-path"; path: string[] }
  | { type: "set-current-level"; pathKey: string; snapshot: LevelSnapshot }
  | { type: "set-current-level-status"; status: "idle" | "loading" | "error" }
  | { type: "set-include"; include: Set<InclusionClass> }
  | { type: "set-species"; rows: TaxonResponse[]; cursor: string | null }
  | { type: "set-species-status"; status: "idle" | "loading" | "error" }
  | { type: "clear-species" };

export const INITIAL: CascadeState = {
  path: [],
  levelByPath: {},
  currentLevelStatus: "loading",
  include: new Set<InclusionClass>(),
  species: [],
  speciesStatus: "idle",
  speciesCursor: null,
};

/** Path key used in ``levelByPath``. ``""`` for the root. */
export function pathKey(path: readonly string[]): string {
  return path.join("|");
}

/** Pure reducer; testable in isolation. */
export function cascadeReducer(state: CascadeState, action: Action): CascadeState {
  switch (action.type) {
    case "set-path": {
      // When the path changes (a dropdown emits a new value), we
      // keep the level snapshots for the path prefixes that are
      // still valid. Anything strictly beyond the new path's
      // length is dropped so a parent edit clears stale children.
      const newKey = pathKey(action.path);
      const nextLevelByPath: Record<string, LevelSnapshot> = {};
      // Walk prefixes of the new path and copy matching snapshots.
      for (let i = 0; i <= action.path.length; i += 1) {
        const prefix = action.path.slice(0, i);
        const k = pathKey(prefix);
        if (state.levelByPath[k] !== undefined) {
          nextLevelByPath[k] = state.levelByPath[k];
        }
        // Avoid unused-loop warning.
        void prefix;
      }
      // Mark the new deepest path as loading so the dropdown
      // shows the "Loading children…" placeholder until the
      // /path-children call returns. The placeholder's
      // ``nextTiers`` is undefined (not null) so the species
      // fetch below does not mistake "we haven't fetched yet"
      // for "we have reached a leaf".
      nextLevelByPath[newKey] = state.levelByPath[newKey] ?? {
        children: [],
        nextTiers: undefined,
      };
      const isNewDeepestLevel = !state.levelByPath[newKey];
      return {
        ...state,
        path: action.path,
        levelByPath: nextLevelByPath,
        currentLevelStatus: isNewDeepestLevel ? "loading" : "idle",
        species: [],
        speciesCursor: null,
        // Reset the species-list status to loading when the path
        // changes so the SpeciesList renders the "Loading children…"
        // placeholder instead of the misleading "No children."
        // state. The second useEffect below will either dispatch
        // "error" or a populated species list when the next-rank
        // snapshot resolves.
        speciesStatus: "loading",
      };
    }
    case "set-current-level": {
      // Cache the snapshot under its path key so ancestor
      // dropdowns stay populated after the user picks a
      // descendant.
      return {
        ...state,
        levelByPath: {
          ...state.levelByPath,
          [action.pathKey]: action.snapshot,
        },
        currentLevelStatus: "idle",
      };
    }
    case "set-current-level-status": {
      return { ...state, currentLevelStatus: action.status };
    }
    case "set-include": {
      return { ...state, include: action.include };
    }
    case "set-species": {
      return { ...state, species: action.rows, speciesCursor: action.cursor };
    }
    case "set-species-status": {
      return { ...state, speciesStatus: action.status };
    }
    case "clear-species": {
      return { ...state, species: [], speciesCursor: null, speciesStatus: "idle" };
    }
  }
}

/**
 * Walk ``path`` and return the dense prefix (every entry until
 * the first null). The path is always dense today; this helper
 * is kept for symmetry with the legacy ``parentSegments`` and
 * for the case where a future action introduces a null gap.
 */
export function densePath(path: string[]): string[] {
  return path.filter((segment) => segment !== null && segment !== undefined);
}
