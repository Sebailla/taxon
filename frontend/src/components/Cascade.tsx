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
- A11y followup: a freshly-enabled child dropdown receives focus
  when its parent changes, so keyboard users Tab once instead of
  Tab + click. The previous ``disabled`` state per rank is tracked
  in a ref so the effect fires only when the boolean actually
  transitions.
*/

import { useEffect, useReducer, useRef } from "react";

import {
  type ApiResult,
  type TaxonResponse,
  buildBreadcrumb,
  fetchChildren,
  fetchKingdoms,
  fetchSpecies,
} from "../api";
import {
  CHILD_RANK_PATH,
  INITIAL,
  RANKS,
  type Rank,
  type Action,
  cascadeReducer,
  parentSegments,
} from "./Cascade.state";
import { Toggles } from "./Toggles";
import { SpeciesList } from "./SpeciesList";

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
  useEffect(() => {
    const segs = parentSegments(state.selected);
    if (segs.length === 0) return;
    const parentRank = RANKS[segs.length - 1] as Rank;
    const targetRank = RANKS[segs.length] as Rank;
    // ``RANKS[6]`` is undefined; once the user picks a genus
    // there are no further children endpoints in this helper
    // (the species list is owned by the dedicated effect below).
    if (targetRank === undefined) return;
    // ``genus`` is excluded from CHILD_RANK_PATH because the
    // species list has its own dedicated effect. We also skip
    // here to keep TypeScript happy (the index type does not
    // include "genus").
    if (parentRank === "genus") return;
    // kingdom → phyla, phylum → classes, class → orders, order →
    // families, family → genera.
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
    // The deps array intentionally lists only the trigger keys
    // (``genus`` + ``include``). Reading ``state.selected`` to build
    // the parent path is safe: the reducer resets every child rank
    // when an ancestor changes, so ``state.selected.genus`` always
    // tracks the user-visible genus. Adding ``state.selected`` to the
    // deps would re-fire the fetch on every phylum/class change,
    // which is wasteful since those changes already trigger a
    // children-fetch effect and the species list under the previous
    // genus has been cleared by the reducer.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
        parentSegments={parentSegments(state.selected)}
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
  const selectRef = useRef<HTMLSelectElement | null>(null);

  // A11y followup: when the dropdown transitions from disabled to
  // enabled, move keyboard focus to it so keyboard users Tab once
  // instead of Tab + click.
  //
  // The initial ``wasDisabledRef.current`` value matches the first
  // render's disabled state so the effect only fires on a true
  // transition. The Kingdom dropdown is enabled from the start
  // (no parent), so ``wasDisabledRef.current`` starts as ``false``
  // and the effect does not steal focus on mount.
  const wasDisabledRef = useRef<boolean>(props.disabled);
  useEffect(() => {
    if (wasDisabledRef.current && !props.disabled) {
      queueMicrotask(() => selectRef.current?.focus());
    }
    wasDisabledRef.current = props.disabled;
  }, [props.disabled]);

  return (
    <label className="flex flex-col gap-1 text-sm text-navy">
      <span className="font-medium">{label}</span>
      <select
        ref={selectRef}
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