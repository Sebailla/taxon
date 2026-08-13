/** Cascade — the path-aware breadcrumb component.

The Cascade renders one dropdown per rank layer the backend has
served for the current path. The level count is dynamic — CoL
ships 40+ ranks with intermediate ranks (subphylum, gigaclass,
infraphylum, parvphylum, ...) that the previous six-fixed-rank
cascade skipped.

State (see ``Cascade.state.ts``):

- ``path`` — the dense list of canonical names the user has
  picked so far. The empty path means "show the root kingdom
  dropdown".
- ``levelByPath`` — snapshot per path segment. The cascade reads
  the keys in order to render N dropdowns. Picking a segment
  extends the path; the next /path-children call lands in a
  new snapshot under the new deepest key.
- ``species`` — loaded separately when the deepest segment has
  no children (the cascade reached a genus row).

Key invariants:

- Picking a segment updates the path; the next /path-children
  call fires with the cumulative path; the new dropdown renders
  with the response's children + next_rank_hint.
- When ``next_rank_hint`` is null (the deepest taxon has no
  children), the species list takes over via /api/.../species.
- Changing a parent segment clears every child snapshot so no
  stale state leaks across picks.
- In-flight requests are aborted when a new selection supersedes
  them. ``apiGet`` swallows the AbortError so the component does
  not need a try/catch.
- Each dropdown carries a visible label AND an ``aria-label``.
  Disabled dropdowns use ``aria-disabled`` so screen readers
  announce the unavailability.
- The previous ``disabled → enabled`` focus behaviour is kept
  per PR #18's a11y followup.
*/

import { useEffect, useReducer, useRef } from "react";

import { Toggles } from "./Toggles";
import { SpeciesList } from "./SpeciesList";
import {
  INITIAL,
  cascadeReducer,
  densePath,
  pathKey,
} from "./Cascade.state";
import {
  type TaxonResponse,
  buildBreadcrumb,
  fetchPathChildren,
  fetchSpeciesList,
} from "../api";

export function Cascade(): JSX.Element {
  const [state, dispatch] = useReducer(cascadeReducer, INITIAL);

  // When the path changes, ask the backend for the children of
  // the deepest resolved taxon. Abort the in-flight call when a
  // new selection supersedes it.
  useEffect(() => {
    const ctrl = new AbortController();
    const key = pathKey(state.path);
    void fetchPathChildren(densePath(state.path), { signal: ctrl.signal }).then(
      (result) => {
        if (ctrl.signal.aborted) return;
        if (result.status === "ok") {
          dispatch({
            type: "set-current-level",
            pathKey: key,
            snapshot: {
              children: result.data.children,
              nextRankHint: result.data.next_rank_hint,
            },
          });
        } else {
          dispatch({
            type: "set-current-level-status",
            status: "error",
          });
        }
      },
    );
    return () => ctrl.abort();
  }, [state.path]);

  // When the deepest snapshot has next_rank_hint === null the
  // cascade has reached a genus row — the children it returned
  // are species. Fetch the species list directly via the
  // path-aware /api/species-list endpoint so the SpeciesList below
  // can render the rows with the inclusion-filter support the
  // legacy build landed.
  useEffect(() => {
    if (state.path.length === 0) return;
    const key = pathKey(state.path);
    const snapshot = state.levelByPath[key];
    if (snapshot === undefined) return;
  // Only fetch the species list when the deepest snapshot is
  // a confirmed leaf (``next_rank_hint === null``). When the
  // hint is a string we are not at a leaf yet; when it is
  // ``undefined`` the snapshot is the loading placeholder and
  // the fetch is still in flight. Both cases early-return after
  // resetting the species status so the SpeciesList does not
  // stay stuck in the "Loading children…" placeholder.
  if (snapshot.nextRankHint !== null) {
    dispatch({ type: "set-species-status", status: "idle" });
    return;
  }
    // CoL classifies some phyla as leaves whose children are
    // genera. The cascade only auto-loads the species list when
    // the deepest snapshot is a confirmed genus (its children are
    // species-rank rows). When the deepest snapshot is a non-genus
    // leaf with no species children, we render the empty state
    // without dispatching an unnecessary fetch.
    const hasSpecies = snapshot.children.some(
      (child) => child.rank === "species",
    );
    if (!hasSpecies) return;
    const ctrl = new AbortController();
    dispatch({ type: "set-species-status", status: "loading" });
    void fetchSpeciesList(densePath(state.path), {
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
  }, [state.path, state.levelByPath, state.include]);

  // Render one dropdown per path segment. The dropdown for the
  // i-th segment shows the snapshot at ``path.slice(0, i + 1)`` —
  // i.e. the children of that segment's taxon. The last segment
  // carries the deepest snapshot (the one we just fetched); the
  // intermediate segments carry cached snapshots from earlier
  // picks.
  const dropdowns: Array<{
    key: string;
    label: string;
    options: TaxonResponse[];
    value: string | null;
    loading: boolean;
  }> = [];
  // The empty-path case: we render a single "Kingdom" dropdown
  // once the initial /path-children?path= response lands.
  if (state.path.length === 0) {
    const rootSnapshot = state.levelByPath[""];
    dropdowns.push({
      key: "kingdom",
      label: "Kingdom",
      options: rootSnapshot?.children ?? [],
      value: null,
      loading: rootSnapshot === undefined,
    });
  } else {
    // For each path segment we render a dropdown. The dropdown
    // at index i shows the children of the taxon at
    // ``path.slice(0, i)`` — i.e. the snapshot under the
    // **previous** prefix. Index 0 (Kingdom) shows the kingdoms,
    // which live under the empty-string key. Each dropdown carries
    // its segment's value (e.g. the Kingdom dropdown has value
    // ``path[0]``, the phylum dropdown has value ``path[1]``) so
    // the user can read the current path at a glance.
    //
    // After the loop, the "next" dropdown shows the children of
    // the deepest resolved taxon so the user has a single,
    // unambiguous way to extend the path. The "next" dropdown
    // is distinct from the loop's last dropdown: the loop
    // dropdown's value is the user's already-picked segment,
    // while the "next" dropdown's value is ``null`` (it is the
    // picker, not a display of state).
    for (let i = 0; i < state.path.length; i += 1) {
      const previousPrefix = state.path.slice(0, i);
      const previousKey = pathKey(previousPrefix);
      const snapshot = state.levelByPath[previousKey];
      const isLast = i === state.path.length - 1;
      const label = i === 0
        ? "Kingdom"
        : snapshot?.nextRankHint ?? inferDropdownLabel(snapshot);
      const value = state.path[i] ?? null;
      dropdowns.push({
        key: previousKey,
        label,
        options: snapshot?.children ?? [],
        value,
        loading: snapshot === undefined && isLast,
      });
    }
    // The "next" dropdown shows the children of the deepest
    // resolved taxon. The user selects a value to extend the
    // path; the dispatch then triggers a fetch for the new
    // deepest taxon and the cycle repeats.
    const deepestKey = pathKey(state.path);
    const deepestSnapshot = state.levelByPath[deepestKey];
    if (
      deepestSnapshot !== undefined &&
      deepestSnapshot.nextRankHint !== null &&
      deepestSnapshot.nextRankHint !== undefined
    ) {
      dropdowns.push({
        key: `${deepestKey}-next`,
        label: deepestSnapshot.nextRankHint.trim(),
        options: deepestSnapshot.children,
        value: null,
        loading: false,
      });
    }
  }

  return (
    <section className="space-y-4" aria-label="Taxonomic cascade">
      <Toggles
        value={state.include}
        onChange={(next) => dispatch({ type: "set-include", include: next })}
      />
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3 lg:grid-cols-6">
        {dropdowns.map((drop) => (
          <RankDropdown
            key={drop.key}
            label={drop.label}
            options={drop.options}
            value={drop.value}
            loading={drop.loading}
            onChange={(value) => {
              const index = dropdowns.indexOf(drop);
              const newPath = state.path.slice(0, index);
              if (value !== null) newPath.push(value);
              dispatch({ type: "set-path", path: newPath });
            }}
          />
        ))}
      </div>
      <SpeciesList
        rows={state.species ?? []}
        status={state.speciesStatus}
        cursor={state.speciesCursor}
        parentSegments={densePath(state.path)}
        breadcrumb={buildBreadcrumb(densePath(state.path))}
      />
    </section>
  );
}

interface RankDropdownProps {
  label: string;
  options: TaxonResponse[];
  value: string | null;
  loading: boolean;
  onChange: (value: string | null) => void;
}

/**
 * Best-effort label for a dropdown when the snapshot is loading
 * or when ``next_rank_hint`` is null.
 *
 * - ``undefined`` snapshot → "Loading…" (fetch still in flight).
 * - snapshot with ``next_rank_hint === null`` (leaf) → fall back
 *   to the rank of the first child so the label is informative
 *   ("genus") instead of "Segment 3".
 */
function inferDropdownLabel(
  snapshot: { children: TaxonResponse[]; nextRankHint: string | null | undefined } | undefined,
): string {
  if (snapshot === undefined) return "Loading…";
  if (snapshot.nextRankHint !== null && snapshot.nextRankHint !== undefined) {
    return snapshot.nextRankHint.trim();
  }
  if (snapshot.children.length === 0) return "—";
  return snapshot.children[0]?.rank ?? "—";
}

function RankDropdown(props: RankDropdownProps): JSX.Element {
  const selectRef = useRef<HTMLSelectElement | null>(null);

  // A11y followup: when the dropdown transitions from disabled to
  // enabled, move keyboard focus to it so keyboard users Tab once
  // instead of Tab + click.
  const wasDisabledRef = useRef<boolean>(props.loading);
  useEffect(() => {
    if (wasDisabledRef.current && !props.loading) {
      queueMicrotask(() => selectRef.current?.focus());
    }
    wasDisabledRef.current = props.loading;
  }, [props.loading]);

  return (
    <label className="flex flex-col gap-1 text-sm text-navy">
      <span className="font-medium">{props.label}</span>
      <select
        ref={selectRef}
        aria-label={props.label}
        disabled={props.loading}
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
