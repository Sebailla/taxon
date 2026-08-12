/** Pure reducer + helpers for the Cascade component.

Extracted from ``Cascade.tsx`` so the component file exports only
components (Vite's ``react-refresh`` HMR requires that for fast
refresh to work cleanly). The reducer and helpers are pure, have
no React imports, and can be tested in isolation.

The contract is unchanged from the original in-file definition:

- ``RANKS`` — the 6-rank ordered list (Kingdom → Genus).
- ``Rank`` — the type union derived from ``RANKS``.
- ``cascadeReducer`` — pure reducer over ``CascadeState``.
- ``INITIAL`` — initial state for ``useReducer``.
- ``parentSegments`` — walks ``selected`` and returns the dense
  prefix (Kingdom → first null).
- ``CHILD_RANK_PATH`` — maps each parent rank to its children
  endpoint suffix (``kingdom → "phyla"``, etc.).

If you change behaviour here, mirror the change in the tests
under ``tests/Cascade.test.tsx``.
*/

import type { TaxonResponse } from "../api";
import type { InclusionClass } from "./Toggles";

export const RANKS = [
  "kingdom",
  "phylum",
  "class",
  "order",
  "family",
  "genus",
] as const;
export type Rank = (typeof RANKS)[number];

export interface CascadeState {
  /** Selected segment per rank. ``null`` means unselected. */
  selected: Record<Rank, string | null>;
  /** Children available per rank, keyed by the parent path. */
  children: Record<Rank, TaxonResponse[]>;
  /** Async status for each level — empty object means idle. */
  childrenStatus: Record<Rank, "idle" | "loading" | "error">;
  /** The active async request, used to abort stale calls. */
  generation: number;
  /** Inclusion toggles (default empty = accepted only). */
  include: Set<InclusionClass>;
  /** Species list for the current genus. */
  species: TaxonResponse[];
  /** Species-list cursor and load status. */
  speciesStatus: "idle" | "loading" | "error";
  speciesCursor: string | null;
}

export type Action =
  | { type: "set-segment"; rank: Rank; value: string | null }
  | { type: "set-children"; rank: Rank; rows: TaxonResponse[] }
  | { type: "set-status"; rank: Rank; status: "idle" | "loading" | "error" }
  | { type: "set-include"; include: Set<InclusionClass> }
  | { type: "set-species"; rows: TaxonResponse[]; cursor: string | null }
  | { type: "set-species-status"; status: "idle" | "loading" | "error" }
  | { type: "bump-generation" };

export const INITIAL: CascadeState = {
  selected: {
    kingdom: null,
    phylum: null,
    class: null,
    order: null,
    family: null,
    genus: null,
  },
  children: {
    kingdom: [],
    phylum: [],
    class: [],
    order: [],
    family: [],
    genus: [],
  },
  childrenStatus: {
    kingdom: "idle",
    phylum: "idle",
    class: "idle",
    order: "idle",
    family: "idle",
    genus: "idle",
  },
  generation: 0,
  include: new Set<InclusionClass>(),
  species: [],
  speciesStatus: "idle",
  speciesCursor: null,
};

/** Pure reducer; testable in isolation. */
export function cascadeReducer(state: CascadeState, action: Action): CascadeState {
  switch (action.type) {
    case "set-segment": {
      const next: CascadeState = {
        ...state,
        selected: { ...state.selected, [action.rank]: action.value },
      };
      // Reset every child of the changed rank.
      const idx = RANKS.indexOf(action.rank);
      for (let i = idx + 1; i < RANKS.length; i += 1) {
        const childRank = RANKS[i] as Rank;
        next.selected = { ...next.selected, [childRank]: null };
        next.children = { ...next.children, [childRank]: [] };
        next.childrenStatus = { ...next.childrenStatus, [childRank]: "idle" };
      }
      if (action.rank === "genus") {
        next.species = [];
        next.speciesCursor = null;
        next.speciesStatus = "idle";
      }
      return next;
    }
    case "set-children": {
      return {
        ...state,
        children: { ...state.children, [action.rank]: action.rows },
      };
    }
    case "set-status": {
      return {
        ...state,
        childrenStatus: { ...state.childrenStatus, [action.rank]: action.status },
      };
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
    case "bump-generation": {
      return { ...state, generation: state.generation + 1 };
    }
  }
}

/**
 * Walk the selected map and return the dense prefix (Kingdom →
 * first null). Used to build the API path for the children and
 * species endpoints.
 */
export function parentSegments(selected: Record<Rank, string | null>): string[] {
  const segs: string[] = [];
  for (const r of RANKS) {
    const value = selected[r];
    if (value === null) break;
    segs.push(value);
  }
  return segs;
}

/**
 * Maps the parent rank to the path segment of the children
 * endpoint. The endpoint ``/api/<kingdom>/<phyla>`` serves the
 * phylum children of a kingdom, so a kingdom has ``"phyla"`` as
 * its child rank. ``genus`` is excluded — the species list is
 * served by a dedicated effect, not by this map.
 */
export const CHILD_RANK_PATH: Record<Exclude<Rank, "genus">, string> = {
  kingdom: "phyla",
  phylum: "classes",
  class: "orders",
  order: "families",
  family: "genera",
};
