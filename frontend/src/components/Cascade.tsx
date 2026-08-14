/** Cascade — the path-aware cascade against the ChecklistBank backend.

The Cascade renders one dropdown per tier the CLB resolver has
served for the current path. CLB exposes a 9-tier tuple
(biota → kingdom → phylum → subphylum → class → order → family
→ genus → species); the subphylum tier collapses to ``class``
when the parent phylum has zero subphylum children (PR #2b in
the ``cascade-checklistbank`` chain), so the cascade sometimes
skips a slot. Two top-tier dropdowns (Biota + Viruses) come
from the root ``/api/kingdoms`` endpoint and feed the first
``/path-children`` call.

State (see ``Cascade.state.ts``):

- ``path`` — the dense list of canonical names the user has
  picked so far. The empty path means "show the root
  Biota/Viruses dropdown".
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
- ``next_rank_hint`` is one of the cascade tier labels
  (``biota``, ``kingdom``, ``phylum``, ``subphylum``, ``class``,
  ``order``, ``family``, ``genus``, ``species``) or ``null``
  when the deepest taxon has no children. The cascade
  capitalises the hint into the dropdown header so the label
  is stable for every tier.
- When ``next_rank_hint`` is null (the deepest taxon has no
  children), the species list takes over via /api/species-list.
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
  fetchRoots,
  fetchPathChildren,
  fetchSpeciesList,
} from "../api";

export function Cascade(): JSX.Element {
  const [state, dispatch] = useReducer(cascadeReducer, INITIAL);

  // When the path changes, ask the backend for the children of
  // the deepest resolved taxon. Abort the in-flight call when a
  // new selection supersedes it.
  //
  // The empty path is the cascade root. Two paths lead here:
  //
  // 1. **Path = []** — fetch the cascade roots via
  //    ``/api/kingdoms`` (CLB returns Biota + Viruses). The
  //    snapshot's ``nextRankHint`` is ``"kingdom"`` so the
  //    renderer can render the second root dropdown labelled
  //    "Kingdom" once the user picks Biota.
  // 2. **Path = [biota-name]** — fetch the children of the
  //    picked root via ``/api/path-children?path=<biota-name>``;
  //    the response carries the kingdoms (or the virus realms,
  //    if Viruses was picked).
  //
  // Both paths share the ``onSuccess`` / ``onError`` callbacks
  // so the dispatch logic stays DRY.
  useEffect(() => {
    const ctrl = new AbortController();
    const key = pathKey(state.path);
    const onSuccess = (children: TaxonResponse[], nextRankHint: string | null) => {
      if (ctrl.signal.aborted) return;
      dispatch({
        type: "set-current-level",
        pathKey: key,
        snapshot: { children, nextRankHint },
      });
    };
    const onError = () => {
      if (ctrl.signal.aborted) return;
      dispatch({
        type: "set-current-level-status",
        status: "error",
      });
    };
    if (state.path.length === 0) {
      void fetchRoots({ signal: ctrl.signal }).then((result) => {
        if (result.status === "ok") {
          // CLB returns the two top-tier taxa (Biota, Viruses).
          // The next dropdown picks a kingdom from the Biota
          // tree, so we hardcode ``nextRankHint = "kingdom"``
          // here; the backend's ``/api/path-children`` calls
          // will report their own hints for everything below.
          onSuccess(result.data, "kingdom");
        } else {
          onError();
        }
      });
      return () => ctrl.abort();
    }
    void fetchPathChildren(densePath(state.path), { signal: ctrl.signal }).then(
      (result) => {
        if (result.status === "ok") {
          onSuccess(result.data.children, result.data.next_rank_hint);
        } else {
          onError();
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

  // Render the cascade. Each ``dropdowns[i]`` is the picker for
  // ``path[i]`` — its label is the tier name the picker advances
  // into, its options are the children of the segment picked at
  // index ``i - 1`` (or, for ``i === 0``, the cascade roots), and
  // its value is the segment already chosen (or ``null`` while
  // the user is still picking).
  //
  // The Biota root tier (added in the ``cascade-checklistbank``
  // chain) is the first slot. Picking Biota or Viruses fills
  // the second slot with kingdom-rank children (Animalia, etc.)
  // and labels it "Kingdom" — the CLB resolver reports
  // ``next_rank_hint = "kingdom"`` for the root tier.
  //
  // A "next" trailing slot appears after the deepest picked
  // segment whenever the deepest snapshot reports a non-null
  // ``next_rank_hint``. The trailing slot is the picker the user
  // uses to extend the path by one segment; its options are the
  // children of the deepest resolved taxon.
  const dropdowns: Array<{
    key: string;
    label: string;
    options: TaxonResponse[];
    value: string | null;
    loading: boolean;
  }> = [];

  // Always render at least the root "Biota" slot so the user
  // can pick (or re-pick) the top tier.
  for (let i = 0; i <= state.path.length; i += 1) {
    // The picker at index ``i`` selects ``path[i]``. Its
    // options are the children of the parent segment, which
    // live in ``levelByPath[pathKey(path.slice(0, i))]``.
    const parentPrefix = state.path.slice(0, i);
    const parentKey = pathKey(parentPrefix);
    const parentSnapshot = state.levelByPath[parentKey];
    const parentRankHint = parentSnapshot?.nextRankHint ?? null;
    const isDeepest = i === state.path.length;
    const value = state.path[i] ?? null;
    // ``loading`` is true when this slot's options are still
    // being fetched (the parent snapshot is missing) AND the
    // slot is the one we are currently fetching. Once the user
    // has picked ``path[i]`` the slot is "stale" but its
    // options are already on screen, so loading is false.
    const loading = parentSnapshot === undefined && isDeepest;
    // The dropdown label is the tier the picker will land on.
    // - i === 0: "Biota" (the cascade root tier).
    // - i > 0: capitalise the parent's next_rank_hint so
    //   "kingdom" → "Kingdom", "phylum" → "Phylum", etc.
    const label = i === 0
      ? "Biota"
      : parentRankHint
        ? capitalize(parentRankHint)
        : inferDropdownLabel(parentSnapshot);
    dropdowns.push({
      key: i === 0 ? "biota" : parentKey,
      label,
      options: parentSnapshot?.children ?? [],
      value: isDeepest ? null : value,
      loading,
    });
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
 * Capitalise the first letter of ``s`` so a CLB next-rank hint
 * like ``"kingdom"`` renders as the dropdown header ``"Kingdom"``.
 *
 * The cascade uses this helper to keep dropdown labels stable
 * across the 9-tier tuple: every tier (biota, kingdom, phylum,
 * subphylum, class, order, family, genus, species) shows up as
 * a regular noun without the resolver having to maintain a
 * tier-to-label table.
 */
function capitalize(s: string | null | undefined): string {
  if (s === null || s === undefined || s.length === 0) return "";
  return s.charAt(0).toUpperCase() + s.slice(1);
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
