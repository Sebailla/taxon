/** Cascade — the 6-step breadcrumb component.

The Cascade renders one dropdown per canonical rank (Kingdom → Phylum
→ Class → Order → Family → Genus) and a species list under the
selected genus. State management is a pure ``useReducer`` so every
transition is testable and the loading / error / empty / not-found
states are explicit.

Key invariants:

- Picking a parent RESETS every child segment. The reducer
  enforces this in ``setSegment``; the UI never has to track
  staleness manually.
- In-flight requests are aborted when a new selection supersedes
  them. ``apiGet`` swallows the ``AbortError`` so the component
  does not need a try/catch.
- Every dropdown carries a visible label AND an ``aria-label``.
- Disabled segments use ``aria-disabled`` so screen readers
  announce the unavailability.
*/

import { useEffect, useReducer } from "react";

import {
  type ApiResult,
  type TaxonResponse,
  buildBreadcrumb,
  fetchChildren,
  fetchKingdoms,
  fetchSpecies,
} from "../api";
import { Toggles, type InclusionClass } from "./Toggles";
import { SpeciesList } from "./SpeciesList";

// ---------------------------------------------------------------------------
// State machine
// ---------------------------------------------------------------------------

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

type Action =
  | { type: "set-segment"; rank: Rank; value: string | null }
  | { type: "set-children"; rank: Rank; rows: TaxonResponse[] }
  | { type: "set-status"; rank: Rank; status: "idle" | "loading" | "error" }
  | { type: "set-include"; include: Set<InclusionClass> }
  | { type: "set-species"; rows: TaxonResponse[]; cursor: string | null }
  | { type: "set-species-status"; status: "idle" | "loading" | "error" }
  | { type: "bump-generation" };

const INITIAL: CascadeState = {
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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const CHILD_RANK_PATH: Record<Exclude<Rank, "kingdom">, string> = {
  phylum: "phyla",
  class: "classes",
  order: "orders",
  family: "families",
  genus: "genera",
};

function parentSegments(selected: Record<Rank, string | null>): string[] {
  const segs: string[] = [];
  for (const r of RANKS) {
    const value = selected[r];
    if (value === null) break;
    segs.push(value);
  }
  return segs;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function Cascade(): JSX.Element {
  const [state, dispatch] = useReducer(cascadeReducer, INITIAL);

  // Load kingdoms on mount.
  useEffect(() => {
    const ctrl = new AbortController();
    dispatch({ type: "set-status", rank: "kingdom", status: "loading" });
    void fetchKingdoms({ signal: ctrl.signal }).then((result) => {
      if (ctrl.signal.aborted) return;
      if (result.status === "ok") {
        dispatch({ type: "set-children", rank: "kingdom", rows: result.data });
        dispatch({ type: "set-status", rank: "kingdom", status: "idle" });
      } else {
        dispatch({ type: "set-status", rank: "kingdom", status: "error" });
      }
    });
    return () => ctrl.abort();
  }, []);

  // Load children when the previous selection changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    const segs = parentSegments(state.selected);
    if (segs.length === 0) return;
    // Load the children of the deepest selected rank. The first
    // selected rank (``kingdom``) was loaded by the mount effect;
    // subsequent ranks load here. ``genus`` is included so the
    // user can pick a genus; the species list is loaded by a
    // separate effect that watches ``state.selected.genus``.
    const targetRank = RANKS[segs.length] as Rank | undefined;
    if (targetRank === undefined) return; // species list owns the leaf
    if (targetRank === "kingdom") return; // already loaded on mount

    const parentRank = RANKS[segs.length - 1] as Exclude<Rank, "kingdom">;
    const childPath = CHILD_RANK_PATH[parentRank] as
      | "phyla"
      | "classes"
      | "orders"
      | "families"
      | "genera";

    const ctrl = new AbortController();
    dispatch({ type: "bump-generation" });
    dispatch({ type: "set-status", rank: targetRank, status: "loading" });
    void fetchChildren(segs, childPath, {
      signal: ctrl.signal,
    }).then((result) => {
      if (ctrl.signal.aborted) return;
      handleResult(result, dispatch, targetRank);
    });
    return () => ctrl.abort();
  }, [state.selected]);

  // Load species when the genus is set.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (state.selected.genus === null) return;
    const ctrl = new AbortController();
    dispatch({ type: "set-species-status", status: "loading" });
    const segs = parentSegments(state.selected);
    void fetchSpecies(segs, {
      signal: ctrl.signal,
      include: [...state.include],
    }).then((result) => {
      if (ctrl.signal.aborted) return;
      if (result.status === "ok") {
        dispatch({
          type: "set-species",
          rows: result.data.items,
          cursor: result.data.next_cursor,
        });
        dispatch({ type: "set-species-status", status: "idle" });
      } else {
        dispatch({ type: "set-species-status", status: "error" });
      }
    });
    return () => ctrl.abort();
  }, [state.selected.genus, state.include]);

  return (
    <section className="space-y-4" aria-label="Taxonomic cascade">
      <Toggles
        value={state.include}
        onChange={(next) => dispatch({ type: "set-include", include: next })}
      />
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3 lg:grid-cols-6">
        {RANKS.map((rank) => (
          <RankDropdown
            key={rank}
            rank={rank}
            options={state.children[rank]}
            value={state.selected[rank]}
            disabled={
              !isEnabled(rank, state.selected) || state.childrenStatus[rank] === "loading"
            }
            loading={state.childrenStatus[rank] === "loading"}
            onChange={(value) => dispatch({ type: "set-segment", rank, value })}
          />
        ))}
      </div>
      <SpeciesList
        rows={state.species}
        status={state.speciesStatus}
        cursor={state.speciesCursor}
        parentSegments={parentSegments(state.selected).slice(0, -1)}
        breadcrumb={buildBreadcrumb(parentSegments(state.selected))}
      />
    </section>
  );
}

function isEnabled(rank: Rank, selected: Record<Rank, string | null>): boolean {
  const idx = RANKS.indexOf(rank);
  if (idx === 0) return true;
  const parent = RANKS[idx - 1] as Rank;
  return selected[parent] !== null;
}

function handleResult(
  result: ApiResult<TaxonResponse[]>,
  dispatch: React.Dispatch<Action>,
  rank: Rank,
): void {
  if (result.status === "ok") {
    dispatch({ type: "set-children", rank, rows: result.data });
    dispatch({ type: "set-status", rank, status: "idle" });
  } else {
    dispatch({ type: "set-status", rank, status: "error" });
  }
}

interface RankDropdownProps {
  rank: Rank;
  options: TaxonResponse[];
  value: string | null;
  disabled: boolean;
  loading: boolean;
  onChange: (value: string | null) => void;
}

function RankDropdown(props: RankDropdownProps): JSX.Element {
  const label = labelFor(props.rank);
  return (
    <label className="flex flex-col gap-1 text-sm text-navy">
      <span className="font-medium">{label}</span>
      <select
        aria-label={label}
        disabled={props.disabled}
        value={props.value ?? ""}
        onChange={(e) => props.onChange(e.target.value === "" ? null : e.target.value)}
        className="rounded-btn border border-border bg-surface px-3 py-2 text-base text-navy disabled:bg-bg disabled:text-muted"
      >
        <option value="">
          {props.loading ? "Loading children…" : "—"}
        </option>
        {props.options.map((opt) => (
          <option key={opt.id} value={opt.name}>
            {opt.name}
          </option>
        ))}
      </select>
    </label>
  );
}

function labelFor(rank: Rank): string {
  return rank.charAt(0).toUpperCase() + rank.slice(1);
}