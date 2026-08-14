/** Cascade — the path-aware cascade against the ChecklistBank backend.

The Cascade renders one dropdown per tier group the CLB resolver
served for the current path. CLB publishes children at off-tuple
intermediate ranks (``infraphylum``, ``parvphylum``,
``megaclass``, ``subclass``, ``suborder``) so the legacy locked
9-tier tuple projection dead-ended at any off-tuple tier
(Issue #43). The new resolver fetches children with no rank
filter, groups them by their actual CLB rank, and emits
``next_tiers`` (one ``NextTier`` per rank group) in the wire
envelope. The cascade renders one dropdown per entry in
``next_tiers``; the dropdown label comes from the tier's own
``label`` field (capitalised from the CLB rank — "Infraphylum",
"Parvphylum", "Megaclass", "Subclass", "Suborder"). The
subphylum collapse rule (PR #2b) is preserved at the phylum
tier: when the phylum has only class-rank children, the resolver
emits a single ``class`` tier so the UI does not show an empty
subphylum picker.

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
  with the response's ``next_tiers``.
- ``next_tiers`` is ``null`` (the deepest taxon has no
  children at any rank), an empty array (defensive — backend
  shouldn't emit this), or a list of ``NextTier`` records. The
  species list takes over when ``next_tiers`` is ``null``.
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
  type NextTier,
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
  //    ``next_tiers`` for the root snapshot is a single "kingdom"
  //    tier so the renderer can render the second dropdown
  //    labelled "Kingdom" once the user picks Biota.
  // 2. **Path = [biota-name]`` — fetch the children of the
  //    picked root via ``/api/path-children?path=<biota-name>``;
  //    the response carries the kingdoms (or the virus realms,
  //    if Viruses was picked).
  //
  // Both paths share the ``onSuccess`` / ``onError`` callbacks
  // so the dispatch logic stays DRY.
  useEffect(() => {
    const ctrl = new AbortController();
    const key = pathKey(state.path);
    const onSuccess = (
      children: TaxonResponse[],
      nextTiers: NextTier[] | null,
    ) => {
      if (ctrl.signal.aborted) return;
      dispatch({
        type: "set-current-level",
        pathKey: key,
        snapshot: { children, nextTiers },
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
          // tree, so we wrap the roots in a single "kingdom"
          // tier here; the backend's ``/api/path-children``
          // calls will report their own tiers for everything
          // below.
          onSuccess(result.data, [
            {
              rank: "kingdom",
              label: "Kingdom",
              examples: result.data.map((row) => row.name).slice(0, 3),
              children: result.data,
            },
          ]);
        } else {
          onError();
        }
      });
      return () => ctrl.abort();
    }
    void fetchPathChildren(densePath(state.path), { signal: ctrl.signal }).then(
      (result) => {
        if (result.status === "ok") {
          onSuccess(result.data.children, result.data.next_tiers);
        } else {
          onError();
        }
      },
    );
    return () => ctrl.abort();
  }, [state.path]);

  // When the deepest snapshot has ``next_tiers === null`` the
  // cascade has reached a leaf — the deepest taxon has no
  // children at any rank. Fetch the species list directly via
  // the path-aware /api/species-list endpoint so the SpeciesList
  // below can render the rows with the inclusion-filter support
  // the legacy build landed.
  useEffect(() => {
    if (state.path.length === 0) return;
    const key = pathKey(state.path);
    const snapshot = state.levelByPath[key];
    if (snapshot === undefined) return;
    // Only fetch the species list when the deepest snapshot is
    // a confirmed leaf (``next_tiers === null``). When the
    // tiers are an array we are not at a leaf yet; when
    // tiers is undefined the snapshot is the loading
    // placeholder and the fetch is still in flight. Both
    // cases early-return after resetting the species status
    // so the SpeciesList does not stay stuck in the "Loading
    // children…" placeholder.
    if (snapshot.nextTiers !== null) {
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
  // ``next_tiers = [{rank: "kingdom", label: "Kingdom", ...}]``
  // for the root tier.
  //
  // Off-tuple intermediate ranks (Issue #43): the resolver
  // emits one ``NextTier`` per rank group, so the cascade can
  // append a dropdown for every group. When the user picks
  // Chordata and the next snapshot reports
  // ``next_tiers = [{rank: "subphylum", label: "Subphylum", ...}]``,
  // the cascade renders one "Subphylum" picker; when it
  // reports infraphylum + class, the cascade renders two
  // pickers ("Infraphylum", "Class"). Each picker extends the
  // path by one segment.
  type DropdownDescriptor = {
    key: string;
    label: string;
    options: TaxonResponse[];
    value: string | null;
    loading: boolean;
  };
  const dropdowns: DropdownDescriptor[] = [];

  // Always render at least the root "Biota" slot so the user
  // can pick (or re-pick) the top tier.
  for (let i = 0; i <= state.path.length; i += 1) {
    // The picker at index ``i`` selects ``path[i]``. Its
    // options are the children of the parent segment, which
    // live in ``levelByPath[pathKey(path.slice(0, i))]``.
    const parentPrefix = state.path.slice(0, i);
    const parentKey = pathKey(parentPrefix);
    const parentSnapshot = state.levelByPath[parentKey];
    const parentTiers = parentSnapshot?.nextTiers ?? null;
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
    // - i > 0: the first tier from the parent's ``next_tiers``
    //   so "kingdom" → "Kingdom", "phylum" → "Phylum", etc.
    //   When the parent has multiple tier groups (off-tuple
    //   intermediates), only the FIRST group's label surfaces
    //   here — the cascade renders additional pickers below
    //   this one for the remaining groups.
    const label = i === 0
      ? "Biota"
      : parentTiers && parentTiers.length > 0
        ? parentTiers[0]?.label ?? "—"
        : inferDropdownLabel(parentSnapshot);
    dropdowns.push({
      key: i === 0 ? "biota" : parentKey,
      label,
      options: parentSnapshot?.children ?? [],
      value: isDeepest ? null : value,
      loading,
    });
  }

  // Append one dropdown per remaining tier group when the
  // deepest snapshot reports ``next_tiers`` with multiple
  // entries. The path has already advanced past the deepest
  // picked segment, so these dropdowns all sit at
  // ``state.path.length`` and extend the path by one segment
  // each. The label of each dropdown comes from the tier's
  // own ``label`` field (e.g. "Infraphylum", "Subclass").
  const deepestKey = pathKey(state.path);
  const deepestSnapshot = state.levelByPath[deepestKey];
  if (
    deepestSnapshot !== undefined &&
    Array.isArray(deepestSnapshot.nextTiers) &&
    deepestSnapshot.nextTiers.length > 1
  ) {
    const tiers: NextTier[] = deepestSnapshot.nextTiers;
    // Skip the first tier — the dropdown for ``path[i]`` is
    // already rendered by the loop above (it shows the first
    // group's options). The remaining tiers need their own
    // dropdowns so the user can pick each one.
    for (let i = 1; i < tiers.length; i += 1) {
      const tier = tiers[i];
      if (tier === undefined) continue;
      dropdowns.push({
        key: `${deepestKey}::tier::${i}`,
        label: tier.label,
        options: tier.children,
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
 * or when ``next_tiers`` is null.
 *
 * - ``undefined`` snapshot → "Loading…" (fetch still in flight).
 * - snapshot with ``next_tiers === null`` (leaf) → fall back
 *   to the rank of the first child so the label is informative
 *   ("genus") instead of "Segment 3".
 */
function inferDropdownLabel(
  snapshot:
    | { children: TaxonResponse[]; nextTiers: NextTier[] | null | undefined }
    | undefined,
): string {
  if (snapshot === undefined) return "Loading…";
  if (
    snapshot.nextTiers !== null &&
    snapshot.nextTiers !== undefined &&
    snapshot.nextTiers.length > 0
  ) {
    return snapshot.nextTiers[0]?.label ?? "—";
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
