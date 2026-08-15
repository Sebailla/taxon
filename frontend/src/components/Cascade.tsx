/** Cascade — the path-aware cascade against the ChecklistBank backend.

The Cascade renders **exactly 7 fixed dropdowns** in this order:

  1. Biota   — populated from ``GET /api/kingdoms``.
  2. Kingdom — kingdom-rank children of the picked Biota.
  3. Phylum  — phylum-rank children of the picked Kingdom.
  4. Class   — class-rank children of the picked Phylum.
  5. Order   — order-rank children of the picked Class.
  6. Family  — family-rank children of the picked Order.
  7. Genus   — genus-rank children of the picked Family.

When a parent has no children at the rank the next dropdown
expects, that dropdown stays rendered but is **disabled** with a
"No <rank> available" placeholder. CoL inter-tier intermediates
(subphylum, infraphylum, parvphylum, megaclass, subclass,
suborder) are never exposed as dropdowns — they only shape the
path the backend walks internally. The phylum-class aggregation
rule (this PR) makes the backend descend into every subphylum
under a phylum and aggregate the class-rank children into a
single ``class`` tier so the cascade UI renders one dropdown
with every class under the phylum regardless of the subphylum
hierarchy.

State (see ``Cascade.state.ts``):

- ``path`` — the dense list of canonical names the user has
  picked so far. The empty path means "show the Biota/Viruses
  dropdown".
- ``levelByPath`` — snapshot per path segment. The cascade
  reads each snapshot's ``next_tiers`` to find the rank group
  the next dropdown expects.
- ``species`` — loaded separately when the deepest segment has
  species-rank children (``next_tiers === null`` and the
  snapshot contains at least one species row).

Key invariants:

- Picking a segment updates the path; the next /path-children
  call fires with the cumulative path; the new snapshot is
  cached under the new deepest key.
- Each dropdown looks up its tier by ``rank === "<expected-rank>"``
  in the parent snapshot's ``next_tiers``. When the tier is
  missing (or the parent snapshot is still loading) the dropdown
  renders disabled.
- Changing a parent segment clears every child snapshot so no
  stale state leaks across picks.
- In-flight requests are aborted when a new selection supersedes
  them. ``apiGet`` swallows the AbortError so the component does
  not need a try/catch.
- Each dropdown carries a visible label AND an ``aria-label``.
  Disabled dropdowns use ``disabled`` so screen readers announce
  the unavailability.
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

/** The seven fixed tier slots the cascade renders, in order. */
const FIXED_TIERS: ReadonlyArray<{
  /** CLB rank string the parent snapshot must expose in ``next_tiers``. */
  readonly rank: string;
  /** User-facing dropdown label. */
  readonly label: string;
}> = [
  { rank: "biota", label: "Biota" },
  { rank: "kingdom", label: "Kingdom" },
  { rank: "phylum", label: "Phylum" },
  { rank: "class", label: "Class" },
  { rank: "order", label: "Order" },
  { rank: "family", label: "Family" },
  { rank: "genus", label: "Genus" },
] as const;

export function Cascade(): JSX.Element {
  const [state, dispatch] = useReducer(cascadeReducer, INITIAL);

  // When the path changes, ask the backend for the children of
  // the deepest resolved taxon. Abort the in-flight call when a
  // new selection supersedes it.
  //
  // The empty path is the cascade root. The roots come from
  // ``/api/kingdoms`` (CLB returns Biota + Viruses).
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
          // Wrap them in a single "kingdom" tier so the dropdown
          // for the picked Biota can render kingdom-rank
          // children on the next /path-children call.
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

  // When the deepest snapshot is a confirmed leaf (no children
  // at any rank) AND the deepest taxon is a genus (its children
  // include species-rank rows), fetch the species list directly
  // via the path-aware /api/species-list endpoint so the
  // SpeciesList below can render the rows with the
  // inclusion-filter support the legacy build landed.
  useEffect(() => {
    if (state.path.length === 0) return;
    const key = pathKey(state.path);
    const snapshot = state.levelByPath[key];
    if (snapshot === undefined) return;
    // Only fetch the species list when the deepest snapshot is
    // a confirmed leaf. The CLB resolver can return any of:
    //
    // - ``null`` (no children at all — confirmed leaf),
    // - ``[]`` (children but no recognised next tier — leaf),
    // - ``[{rank: "species", ...}]`` (the genus has species
    //   children wrapped in a species tier — leaf for our
    //   seven-fixed-tier cascade).
    //
    // Any other shape (a non-species tier) means the deepest
    // taxon is NOT a leaf yet, so the species list stays idle.
    const isLeaf =
      snapshot.nextTiers === null ||
      snapshot.nextTiers === undefined ||
      snapshot.nextTiers.length === 0 ||
      snapshot.nextTiers.every((tier) => tier.rank === "species");
    if (!isLeaf) {
      dispatch({ type: "set-species-status", status: "idle" });
      return;
    }
    // Leaf with no species-rank children: reset the species
    // status to ``idle`` so the SpeciesList renders the "No
    // children." empty state instead of staying stuck on the
    // loading placeholder the set-path reducer set.
    if (!snapshot.children.some((child) => child.rank === "species")) {
      dispatch({ type: "set-species-status", status: "idle" });
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

  // Render the seven fixed dropdowns. Each ``dropdowns[i]`` is
  // the picker for ``path[i]``:
  //
  // - Slot 0 (Biota): the options are the root snapshot's
  //   ``children`` directly. The root snapshot is fetched from
  //   ``/api/kingdoms`` and the cascade wraps its result in a
  //   single ``kingdom`` tier so the slot-1 picker can read
  //   kingdom-rank children from there.
  // - Slot i > 0: the options come from the **parent** snapshot's
  //   ``next_tiers`` tier whose ``rank === FIXED_TIERS[i].rank``.
  //   The parent of slot-i is the snapshot at
  //   ``path.slice(0, i-1)`` — the snapshot that the previous
  //   slot's pick populated. The user picked ``path[i]`` from
  //   that parent's children list.
  // - Its value is the segment already chosen (or ``null`` while
  //   the user is still picking the deepest slot).
  // - Its ``loading`` flag is true when the parent snapshot is
  //   missing (the /path-children call is still in flight).
  //
  // When the parent snapshot is missing OR does not expose a
  // tier with the expected rank, the dropdown renders disabled.
  // The seven slots are always rendered — no tier outside the
  // fixed seven ever appears.
  type DropdownDescriptor = {
    key: string;
    label: string;
    options: TaxonResponse[];
    value: string | null;
    loading: boolean;
    pending: boolean;
  };
  const dropdowns: DropdownDescriptor[] = FIXED_TIERS.map((tier, i) => {
    const isDeepest = i === state.path.length;
    const value = state.path[i] ?? null;
    // The parent snapshot for slot-i is the snapshot at the path
    // of the previous picked segment. When ``path`` is empty,
    // slot-0's parent is the root snapshot (``levelByPath[""]``).
    // When ``path = ["Biota"]``, slot-1's parent is the Biota
    // snapshot (``levelByPath["Biota"]``). Slot-i never reads
    // options from the parent until slot-(i-1) has been picked
    // — the pending flag short-circuits the read so slots stay
    // disabled until the user advances the cascade in order.
    const pending = i > state.path.length;
    const parentPrefix = state.path.slice(0, i);
    const parentKey = pathKey(parentPrefix);
    const parentSnapshot = state.levelByPath[parentKey];
    let options: TaxonResponse[] = [];
    if (!pending) {
      if (i === 0) {
        // The root snapshot IS the list of cascade roots (Biota,
        // Viruses).
        options = parentSnapshot?.children ?? [];
      } else {
        // Slot-i looks at the snapshot of the picked segment
        // ``path[i-1]``. That snapshot's ``next_tiers`` carries
        // one tier per CLB rank group of the segment's children;
        // the slot reads the tier whose ``rank`` matches the
        // expected rank for this slot.
        const parentTiers = parentSnapshot?.nextTiers ?? null;
        const tierForRank =
          parentTiers === null || parentTiers === undefined
            ? null
            : parentTiers.find((t) => t.rank === tier.rank) ?? null;
        options = tierForRank?.children ?? [];
      }
    }
    const loading = parentSnapshot === undefined && isDeepest;
    return {
      key: `slot-${i}-${tier.rank}`,
      label: tier.label,
      options,
      value: isDeepest ? null : value,
      loading,
      pending,
    };
  });

  return (
    <section className="space-y-4" aria-label="Taxonomic cascade">
      <Toggles
        value={state.include}
        onChange={(next) => dispatch({ type: "set-include", include: next })}
      />
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3 lg:grid-cols-7">
        {dropdowns.map((drop, index) => (
          <RankDropdown
            key={drop.key}
            label={drop.label}
            options={drop.options}
            value={drop.value}
            loading={drop.loading}
            pending={drop.pending}
            onChange={(value) => {
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
  pending: boolean;
  onChange: (value: string | null) => void;
}

function RankDropdown(props: RankDropdownProps): JSX.Element {
  const selectRef = useRef<HTMLSelectElement | null>(null);

  // A11y followup: when the dropdown transitions from disabled to
  // enabled, move keyboard focus to it so keyboard users Tab once
  // instead of Tab + click.
  const wasDisabledRef = useRef<boolean>(props.loading || props.pending);
  useEffect(() => {
    const nowDisabled = props.loading || props.pending;
    if (wasDisabledRef.current && !nowDisabled) {
      queueMicrotask(() => selectRef.current?.focus());
    }
    wasDisabledRef.current = nowDisabled;
  }, [props.loading, props.pending]);

  const isDisabled =
    props.loading || props.pending || props.options.length === 0;

  return (
    <label className="flex flex-col gap-1 text-sm text-navy">
      <span className="font-medium">{props.label}</span>
      <select
        ref={selectRef}
        aria-label={props.label}
        disabled={isDisabled}
        value={props.value ?? ""}
        onChange={(e) => props.onChange(e.target.value === "" ? null : e.target.value)}
        className="rounded-btn border border-border bg-surface px-3 py-2 text-base text-navy disabled:bg-bg disabled:text-muted"
      >
        <option value="">
          {props.loading
            ? "Loading…"
            : props.pending
              ? `Pick ${FIXED_TIERS[Math.max(0, FIXED_TIERS.findIndex((t) => t.label === props.label) - 1)]?.label ?? "previous"} first`
              : props.options.length === 0
                ? `No ${props.label.toLowerCase()} available`
                : "—"}
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
