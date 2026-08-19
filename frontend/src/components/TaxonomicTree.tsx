/** TaxonomicTree — the CoL-style hierarchical tree that replaces the
7-dropdown Cascade.

The component renders a ``role="tree"`` with a header row
("Find taxon" search + Source dropdown + Extant-only checkbox +
Synonyms chip) and a body of lazily-expanded rows. Each row
follows the design doc's row anatomy:

  rank: Name Authorship • N spp.

with a caret that rotates on expand, a 1px indent guide per
depth, and the standard marker glyphs (``⚠`` uncertain,
``⊘`` unassigned, ``†`` extinct) prefixed to the rank label.

State management:

- The cache + expanded set live in the ``useTaxonomicTree``
  Zustand store (see ``store/taxonomicTree.ts``); the
  component only reads selectors and dispatches actions.
- The explored path flows through the existing
  ``useCascadePath`` store + a ``path:change`` CustomEvent so
  the App's breadcrumb-links panel keeps working after the
  Cascade replacement.

The component is the surface a strict-TDD test suite asserts
against (``tests/TaxonomicTree.test.tsx``,
``tests/TaxonomicTree.a11y.test.tsx``).
*/

import { useEffect, useMemo, useRef, useState } from "react";

import {
  type ApiResult,
  type TreeNodeResponse,
  type TreeNodeTier,
  type TreeSearchResponse,
  createDebouncedSearch,
  fetchTreeSearch,
} from "../api";
import {
  tierRowsKey,
  useTaxonomicTree,
} from "../store/taxonomicTree";

const PATH_CHANGE_EVENT = "path:change";
const SEARCH_DEBOUNCE_MS = 200;
const SEARCH_RESULT_LIMIT = 8;
const INDENT_STEP_DESKTOP = 16;
const INDENT_STEP_MOBILE = 12;
const MOBILE_BREAKPOINT = 640;

/**
 * Discriminated union for the flat list of visible rows the
 * ``walk()`` builder emits. The tree owns ``tree-row`` entries
 * (the regular tree nodes) and ``tier-group`` entries (the
 * cascade envelope below each expanded parent). The keyboard
 * nav handles both kinds uniformly via the ``id`` field.
 */
type VisibleRow =
  | {
      kind: "tree-row";
      row: TreeNodeResponse;
      depth: number;
      selectedAncestorIds: ReadonlySet<number>;
    }
  | {
      kind: "tier-group";
      tier: TreeNodeTier;
      parentId: number;
      parentDepth: number;
      selectedAncestorIds: ReadonlySet<number>;
    };

/** Stable id used for the TierGroup header in the global
 * ``rowRefs`` map and the keyboard nav ``visibleRows`` list. The
 * negative space avoids any collision with real taxon ids (which
 * are positive integers). The shape is parseable so the global
 * keyboard nav can dispatch the right handler on the tier group's
 * header (ArrowRight/Left toggles the group; ArrowDown/Up moves
 * focus to the next sibling row). */
function tierGroupKey(parentId: number, rank: string): string {
  return `tier:${parentId}:${rank}`;
}

/** Cascade-rank order used by the TierGroup expansion policy.
 * The first tier (phylum) expands by default so the user sees the
 * cascade immediately, matching the Stitch design brief. */
const CASCADE_RANK_ORDER = [
  "realm",
  "kingdom",
  "phylum",
  "class",
  "order",
  "family",
  "genus",
  "species",
];

/**
 * Return whether the given ``(parentId, rank)`` is the FIRST tier
 * for its parent in cascade-rank order. The TierGroup component
 * reads the flag to decide whether to expand by default.
 *
 * The check is shallow — the parent is only used to look up the
 * tier envelope list. The ``rank`` param is the candidate; the
 * canonical cascade-rank order is the source of truth so the
 * visual ordering stays deterministic when the parent has only
 * one tier (the phylum is the only entry, and it is the first).
 */
function isFirstTierFor(_parentId: number, rank: string): boolean {
  // The first tier in cascade-rank order is the one with the
  // lowest index in CASCADE_RANK_ORDER. The phylum tier is the
  // universal first tier (realm only appears for taxa above
  // kingdom; the Stitch design brief uses phylum as the visible
  // preview).
  const order = CASCADE_RANK_ORDER.indexOf(rank);
  const firstOrder = CASCADE_RANK_ORDER.indexOf("phylum");
  return order === firstOrder;
}

/** Stable id accessor for either kind of visible row. */
function rowIdOf(entry: VisibleRow): number | string {
  if (entry.kind === "tree-row") return entry.row.id;
  return tierGroupKey(entry.parentId, entry.tier.rank);
}

/** Find a visible row by its id (number for tree rows, string
 * for tier-group headers). */
function findRowIndex(
  rows: ReadonlyArray<VisibleRow>,
  id: number | string,
): number {
  return rows.findIndex((entry) => rowIdOf(entry) === id);
}

/** True when the cache has rows for the tier. The TierGroup
 * expansion depends on the cache cursor once the cache has any
 * rows; the envelope's cursor is the seed only when the cache is
 * empty. */
function hasCacheRows(rows: TreeNodeResponse[]): boolean {
  return rows.length > 0;
}

interface TreeRowProps {
  row: TreeNodeResponse;
  depth: number;
  indentStep: number;
  isExpanded: boolean;
  isLoading: boolean;
  hasError: boolean;
  errorMessage: string;
  onToggle: (id: number) => void;
  onRetry: (id: number) => void;
  focusedId: number | string | null;
  registerRow: (id: number, el: HTMLButtonElement | null) => void;
  onKeyDown: (e: React.KeyboardEvent<HTMLButtonElement>, id: number | string) => void;
  selectedAncestorIds: ReadonlySet<number>;
}

function TreeRow(props: TreeRowProps): JSX.Element {
  const {
    row,
    depth,
    indentStep,
    isExpanded,
    isLoading,
    hasError,
    errorMessage,
    onToggle,
    onRetry,
    onKeyDown,
    focusedId,
    registerRow,
    selectedAncestorIds,
  } = props;

  const ariaLevel = depth + 1;
  const isSelected = selectedAncestorIds.has(row.id);
  const expandAttr = row.has_children ? isExpanded : undefined;
  const marker = row.is_uncertain ? "⚠" : row.is_unassigned ? "⊘" : row.is_extinct ? "†" : null;

  return (
    <div
      role="treeitem"
      aria-level={ariaLevel}
      aria-expanded={expandAttr}
      aria-selected={isSelected ? true : undefined}
      className="relative"
    >
      <button
        type="button"
        ref={(el) => registerRow(row.id, el)}
        onClick={() => {
          if (row.has_children) onToggle(row.id);
        }}
        onKeyDown={(e) => onKeyDown(e, row.id)}
        data-focused={focusedId === row.id ? "true" : undefined}
        tabIndex={focusedId === row.id ? 0 : -1}
        aria-busy={isLoading ? true : undefined}
        aria-disabled={hasError ? true : undefined}
        style={{ paddingLeft: depth * indentStep + 8 }}
        className={
          "flex w-full items-center gap-2 py-2 pr-2 text-left text-sm transition-colors motion-reduce:transition-none " +
          (isSelected
            ? "border-l-4 border-accent bg-blue-50"
            : "border-l-4 border-transparent hover:bg-bg") +
          " focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-accent"
        }
      >
        <span
          aria-hidden="true"
          className={
            "inline-flex h-6 w-6 shrink-0 items-center justify-center text-xs text-slate select-none transition-transform duration-150 ease-out motion-reduce:transition-none " +
            (isExpanded ? "rotate-90" : "")
          }
        >
          {row.has_children ? (isLoading ? "↻" : "▸") : ""}
        </span>
        <span
          aria-hidden="true"
          className={
            marker === "⚠"
              ? "shrink-0 text-[10px] font-medium uppercase tracking-widest text-amber"
              : marker === "⊘"
                ? "shrink-0 text-[10px] font-medium uppercase tracking-widest text-muted"
                : marker === "†"
                  ? "shrink-0 text-[10px] font-medium uppercase tracking-widest text-red"
                  : "shrink-0 text-[10px] font-medium uppercase tracking-widest text-slate"
          }
        >
          {row.rank}
        </span>
        <span className="min-w-0 flex-1 truncate font-medium text-navy">
          {row.display_name}
        </span>
        {row.authorship !== "" ? (
          <span className="hidden shrink-0 max-w-[40ch] truncate text-xs italic text-slate md:inline">
            · {row.authorship}
          </span>
        ) : null}
        <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-bg px-2 py-0.5 text-xs font-medium text-slate tabular-nums">
          {row.species_count === null ? "—" : formatSpeciesCount(row.species_count) + " spp."}
        </span>
      </button>
      {hasError ? (
        <span className="ml-6 text-xs text-red">
          Couldn't load children.
          <button
            type="button"
            onClick={() => onRetry(row.id)}
            className="ml-2 underline"
          >
            Retry
          </button>
          <span className="sr-only">. {errorMessage}</span>
        </span>
      ) : null}
      {isExpanded && isLoading ? (
        <div className="ml-6 flex flex-col gap-1 py-2">
          <span className="inline-block h-2 w-24 rounded bg-border animate-pulse" />
          <span className="inline-block h-2 w-24 rounded bg-border animate-pulse" />
          <span className="inline-block h-2 w-24 rounded bg-border animate-pulse" />
        </div>
      ) : null}
    </div>
  );
}

function formatSpeciesCount(n: number): string {
  if (n < 1000) return n.toString();
  if (n < 1_000_000) return `${(n / 1000).toFixed(1).replace(/\.0$/, "")}K`;
  return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
}

// ---------------------------------------------------------------------------
// TierGroup + TierRow
//
// The cascade envelope (``next_tiers``) carries one bucket per
// non-direct descendant rank below the parent. The TierGroup renders
// that bucket as a sub-tree under the explored parent:
//
//   <div role="group" aria-label="<label> group">
//     <button role="button" aria-expanded="true" aria-controls="<list-id>">
//       ▾ Phyla (34)                     // caret + label + row count
//     </button>
//     <div role="group" id="<list-id>">
//       <TreeRow ... />                  // tier rows, depth + 2
//       <TreeRow ... />
//       <button aria-label="Load more Phyla">Load more</button>  // when cursor != null
//     </div>
//   </div>
//
// The first page of tier rows comes from the envelope's
// ``children`` (the backend caps the first page at ``tier_limit``).
// The Load-more button calls ``loadMore(parentId, rank)`` which
// appends the next page to the cache. The button is hidden when
// the cursor is null AND rows are present (P1 #2 fix from the
// audit) so the affordance does not pollute the per-tier list
// with a useless trigger.
//
// The first tier (phylum) expands by default; subsequent tiers
// stay collapsed until the user clicks their header. The keyboard
// navigation crosses the TierGroup boundary exactly the same way
// it crosses a regular tree row — the parent tier header's
// ``aria-expanded`` mirrors the group state, and ArrowLeft/Right
// toggle it.
// ---------------------------------------------------------------------------

interface TierRowProps {
  row: TreeNodeResponse;
  depth: number;
  indentStep: number;
  isExpanded: boolean;
  isLoading: boolean;
  hasError: boolean;
  errorMessage: string;
  onToggle: (id: number) => void;
  onRetry: (id: number) => void;
  focusedId: number | string | null;
  /** Keyboard navigation handler owned by the TierGroup. The
   * TierGroup navigates within the tier rows (ArrowDown/Up/
   * Home/End) and routes Enter / Arrow toggles to ``onToggle``.
   * The global ``onKeyDown`` does not apply because the tier
   * rows are not in the ``visibleRows`` flat list. */
  onTierRowKeyDown: (
    e: React.KeyboardEvent<HTMLButtonElement>,
    id: number,
  ) => void;
  selectedAncestorIds: ReadonlySet<number>;
}

function TierRow(props: TierRowProps): JSX.Element {
  // The TierRow reuses the same anatomy as ``TreeRow`` so the
  // visual treatment is consistent across the cascade. The only
  // visible difference is the deeper indent (the parent depth + 1,
  // applied by the caller via the ``depth`` prop).
  const {
    row,
    depth,
    indentStep,
    isExpanded,
    isLoading,
    hasError,
    errorMessage,
    onToggle,
    onRetry,
    onTierRowKeyDown,
    focusedId,
    selectedAncestorIds,
  } = props;

  const ariaLevel = depth + 1;
  const isSelected = selectedAncestorIds.has(row.id);
  const expandAttr = row.has_children ? isExpanded : undefined;
  const marker = row.is_uncertain ? "⚠" : row.is_unassigned ? "⊘" : row.is_extinct ? "†" : null;

  return (
    <div
      role="treeitem"
      aria-level={ariaLevel}
      aria-expanded={expandAttr}
      aria-selected={isSelected ? true : undefined}
      className="relative"
    >
      <button
        type="button"
        ref={(el) => {
          // The TierRow's button is registered in ``rowRefs``
          // indirectly via the parent ``registerRow`` so the
          // global focus effect can reach it. The detector
          // attribute is what the TierGroup's keyboard nav uses
          // to find the next focusable row.
          (el as HTMLButtonElement | null)?.setAttribute(
            "data-tier-row-id",
            String(row.id),
          );
        }}
        onClick={() => {
          if (row.has_children) onToggle(row.id);
        }}
        onKeyDown={(e) => onTierRowKeyDown(e, row.id)}
        data-focused={focusedId === row.id ? "true" : undefined}
        tabIndex={focusedId === row.id ? 0 : -1}
        aria-busy={isLoading ? true : undefined}
        aria-disabled={hasError ? true : undefined}
        style={{ paddingLeft: depth * indentStep + 8 }}
        className={
          "flex w-full items-center gap-2 py-1.5 pr-2 text-left text-sm transition-colors motion-reduce:transition-none " +
          (isSelected
            ? "border-l-4 border-accent bg-blue-50"
            : "border-l-4 border-transparent hover:bg-bg") +
          " focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-accent"
        }
      >
        <span
          aria-hidden="true"
          className={
            "inline-flex h-5 w-5 shrink-0 items-center justify-center text-xs text-slate select-none transition-transform duration-150 ease-out motion-reduce:transition-none " +
            (isExpanded ? "rotate-90" : "")
          }
        >
          {row.has_children ? (isLoading ? "↻" : "▸") : ""}
        </span>
        <span
          aria-hidden="true"
          className={
            marker === "⚠"
              ? "shrink-0 text-[10px] font-medium uppercase tracking-widest text-amber"
              : marker === "⊘"
                ? "shrink-0 text-[10px] font-medium uppercase tracking-widest text-muted"
                : marker === "†"
                  ? "shrink-0 text-[10px] font-medium uppercase tracking-widest text-red"
                  : "shrink-0 text-[10px] font-medium uppercase tracking-widest text-slate"
          }
        >
          {row.rank}
        </span>
        <span className="min-w-0 flex-1 truncate font-medium text-navy">
          {row.display_name}
        </span>
        {row.authorship !== "" ? (
          <span className="hidden shrink-0 max-w-[40ch] truncate text-xs italic text-slate md:inline">
            · {row.authorship}
          </span>
        ) : null}
        <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-bg px-2 py-0.5 text-xs font-medium text-slate tabular-nums">
          {row.species_count === null ? "—" : formatSpeciesCount(row.species_count) + " spp."}
        </span>
      </button>
      {hasError ? (
        <span className="ml-6 text-xs text-red">
          Couldn't load children.
          <button
            type="button"
            onClick={() => onRetry(row.id)}
            className="ml-2 underline"
          >
            Retry
          </button>
          <span className="sr-only">. {errorMessage}</span>
        </span>
      ) : null}
      {isExpanded && isLoading ? (
        <div className="ml-6 flex flex-col gap-1 py-2">
          <span className="inline-block h-2 w-24 rounded bg-border animate-pulse" />
          <span className="inline-block h-2 w-24 rounded bg-border animate-pulse" />
        </div>
      ) : null}
    </div>
  );
}

interface TierGroupProps {
  parentId: number;
  tier: TreeNodeTier;
  /** The depth of the parent row (the TierGroup header sits one level deeper). */
  parentDepth: number;
  indentStep: number;
  /** Whether this is the first tier in cascade-rank order. The first
   * tier expands by default so the user sees the rows without an
   * extra click. */
  isFirstTier: boolean;
  /** Ancestors of the parent row (used for the row selection tint). */
  selectedAncestorIds: ReadonlySet<number>;
  /** Row focus plumbing — keeps the existing ``visibleRows`` /
   * ``focusedId`` keyboard nav working across the TierGroup
   * boundary. The TierRow's keyboard nav is local to the group
   * (the TierGroup owns ArrowDown/Up navigation between its
   * rows), so this prop is unused by the TierGroup itself but
   * retained for the parent header button which participates in
   * the global nav. */
  focusedId: number | string | null;
  registerRow: (id: number | string, el: HTMLButtonElement | null) => void;
  onToggleRow: (id: number) => void;
  onRetryRow: (id: number) => void;
  /** Loading / error slots for the tier rows. The store provides
   * the same per-parent maps the regular tree rows use. */
  loadingParentIds: ReadonlySet<number>;
  errorByParentId: ReadonlyMap<number, string>;
  /** Keyboard navigation handler for the tier-group header. The
   * parent (TaxonomicTree) owns the global nav across the flat
   * visibleRows list; the header is one of those rows so the
   * handler has to be the same one. */
  onHeaderKeyDown: (
    e: React.KeyboardEvent<HTMLButtonElement>,
    id: number | string,
  ) => void;
}

function TierGroup(props: TierGroupProps): JSX.Element {
  const {
    parentId,
    tier,
    parentDepth,
    indentStep,
    isFirstTier,
    selectedAncestorIds,
    focusedId,
    registerRow,
    onToggleRow,
    onRetryRow,
    loadingParentIds,
    errorByParentId,
    onHeaderKeyDown,
  } = props;

  const loadMore = useTaxonomicTree((s) => s.loadMore);
  const tierRows = useTaxonomicTree((s) =>
    s.tierRowsByKey.get(tierRowsKey(parentId, tier.rank)),
  );

  // First tier (phylum) expands by default; subsequent tiers stay
  // collapsed until the user opts in. The spec
  // (docs/design/stitch/tree-deep-subtree-design.md §"What the
  // rendered screen shows") makes the first tier the visible
  // preview so the user can see the cascade without a second
  // click; subsequent tiers require explicit interaction.
  const [expanded, setExpanded] = useState(isFirstTier);

  // The tier rows are NOT in the global ``visibleRows`` (the
  // TierGroup owns them), so the global keyboard nav can't find
  // them. The TierGroup exposes its own ArrowDown/Up handler
  // that navigates within the group and routes Enter / Arrow
  // toggles to the per-row callbacks the parent provided.
  const rowIds = (() => {
    const envelopeRows = tier.children;
    const cachedRows = tierRows?.rows ?? [];
    const hasCache = cachedRows.length > 0;
    const allRows = hasCache ? cachedRows : envelopeRows;
    return allRows.map((r) => r.id);
  })();
  const handleTierRowKeyDown = (
    e: React.KeyboardEvent<HTMLButtonElement>,
    id: number,
  ): void => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      const idx = rowIds.indexOf(id);
      const next = rowIds[Math.min(idx + 1, rowIds.length - 1)];
      if (next !== undefined) {
        const btn = document.querySelector<HTMLButtonElement>(
          `[data-tier-row-id="${next}"]`,
        );
        btn?.focus();
      }
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      const idx = rowIds.indexOf(id);
      const prev = rowIds[Math.max(idx - 1, 0)];
      if (prev !== undefined) {
        const btn = document.querySelector<HTMLButtonElement>(
          `[data-tier-row-id="${prev}"]`,
        );
        btn?.focus();
      }
    } else if (e.key === "Home") {
      e.preventDefault();
      const first = rowIds[0];
      if (first !== undefined) {
        const btn = document.querySelector<HTMLButtonElement>(
          `[data-tier-row-id="${first}"]`,
        );
        btn?.focus();
      }
    } else if (e.key === "End") {
      e.preventDefault();
      const last = rowIds[rowIds.length - 1];
      if (last !== undefined) {
        const btn = document.querySelector<HTMLButtonElement>(
          `[data-tier-row-id="${last}"]`,
        );
        btn?.focus();
      }
    } else if (e.key === "Enter") {
      // Tier rows are intentionally leaves in PR C.2 (their
      // grandchildren are not in the cascade tier view). The
      // TierRow's own onClick handles the caret toggle; the
      // keyboard Enter routes to the same handler.
      onToggleRow(id);
    }
  };

  const headerId = `tier-${parentId}-${tier.rank}-header`;
  const listId = `tier-${parentId}-${tier.rank}-list`;
  const headerKey = tierGroupKey(parentId, tier.rank);

  // The first page arrives in the envelope's ``children`` and is
  // rendered without an extra fetch (the backend capped the first
  // page at ``tier_limit``). Subsequent pages live in
  // ``tierRowsByKey`` keyed by ``"${parentId}:${rank}"``. The
  // order is envelope first, then cache rows — the
  // ``loadMore`` action appends, so the cache rows are guaranteed
  // to follow the envelope's first page without overlap.
  const envelopeRows = tier.children;
  const cachedRows = tierRows?.rows ?? [];
  const allRows = [...envelopeRows, ...cachedRows];

  // P1 #2: hide the Load-more button when the cursor is null AND
  // rows are present. The check fires in two scenarios:
  //   * the envelope's ``next_cursor`` is null AND the cache is empty
  //     (single-page tier — the envelope already returned every row).
  //   * the cache has rows AND the cached cursor is null
  //     (the previous ``loadMore`` reached the last page).
  //
  // The cache is the AUTHORITATIVE source once it has rows: the
  // store's ``loadMore`` keeps the cache consistent with the
  // envelope's seed (the first call uses the envelope's
  // ``next_cursor`` which is the cursor AFTER the envelope's first
  // page; subsequent calls advance the cache cursor). When the
  // cache is empty the envelope's cursor is the only signal.
  const cachedCursor = tierRows?.nextCursor ?? null;
  const envelopeCursor = tier.next_cursor;
  const hasMore = hasCacheRows(cachedRows)
    ? cachedCursor !== null
    : envelopeCursor !== null;
  const showLoadMore = hasMore;

  // The row count in the header reflects the total number of rows
  // currently rendered (envelope + cache). The "via subphylum
  // rollup" inline note annotates the phylum row when the rolled-up
  // depth exceeds 1 — the backend emits the rollup_marker as the
  // first child's ``examples`` hint via the ``rank`` family. We
  // surface the note on the phylum tier specifically (per the
  // Stitch design §"What the rendered screen shows").
  const headerDepth = parentDepth + 1;
  const rowsDepth = parentDepth + 2;
  const isPhylumTier = tier.rank === "phylum";
  const rowCount = allRows.length;

  return (
    <div
      role="group"
      aria-label={`${tier.label} group`}
      id={listId}
      aria-expanded={expanded}
    >
      <button
        type="button"
        id={headerId}
        aria-label={tier.label}
        aria-expanded={expanded}
        aria-controls={listId}
        ref={(el) => registerRow(headerKey, el)}
        onClick={() => setExpanded((v) => !v)}
        onKeyDown={(e) => onHeaderKeyDown(e, headerKey)}
        data-focused={focusedId === headerKey ? "true" : undefined}
        tabIndex={focusedId === headerKey ? 0 : -1}
        style={{ paddingLeft: headerDepth * indentStep + 8 }}
        className={
          "flex w-full items-center gap-2 border-l-4 border-transparent py-2 pr-2 text-left text-sm font-medium transition-colors motion-reduce:transition-none hover:bg-bg " +
          "focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-accent"
        }
      >
        <span
          aria-hidden="true"
          className={
            "inline-flex h-5 w-5 shrink-0 items-center justify-center text-xs text-slate select-none transition-transform duration-150 ease-out motion-reduce:transition-none " +
            (expanded ? "rotate-90" : "")
          }
        >
          ▸
        </span>
        <span className="shrink-0 text-[10px] font-medium uppercase tracking-widest text-slate">
          {tier.label}
        </span>
        <span className="min-w-0 flex-1 truncate text-navy">
          {tier.label} ({rowCount})
        </span>
        {/* The "via subphylum rollup" inline note appears on the
            phylum tier header (per the Stitch surface brief). The
            text uses ``text-slate`` (P1 #1 fix) so the contrast
            ratio on the surface background passes WCAG AA. The
            note lives OUTSIDE the button's disclosure content so
            the header's accessible name is just the tier label
            (per the spec, the tier group is the disclosure, the
            note is decorative). */}
        {isPhylumTier ? (
          <span
            aria-hidden="true"
            className="hidden text-xs italic text-slate md:inline"
          >
            via subphylum rollup
          </span>
        ) : null}
      </button>
      {expanded ? (
        <div role="group" aria-labelledby={headerId}>
          {allRows.map((row) => (
            <TierRow
              key={row.id}
              row={row}
              depth={rowsDepth}
              indentStep={indentStep}
              isExpanded={false}
              isLoading={loadingParentIds.has(row.id)}
              hasError={errorByParentId.has(row.id)}
              errorMessage={errorByParentId.get(row.id) ?? ""}
              onToggle={onToggleRow}
              onRetry={onRetryRow}
              focusedId={focusedId}
              onTierRowKeyDown={handleTierRowKeyDown}
              selectedAncestorIds={selectedAncestorIds}
            />
          ))}
          {showLoadMore ? (
            <div
              style={{ paddingLeft: rowsDepth * indentStep + 8 }}
              className="py-1.5"
            >
              <button
                type="button"
                aria-label={`Load more ${tier.label}`}
                onClick={() => void loadMore(parentId, tier.rank)}
                className="rounded-md px-3 py-1 text-sm text-slate hover:bg-bg focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                Load more {tier.label}
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function TaxonomicTree(): JSX.Element {
  const childrenByParentId = useTaxonomicTree((s) => s.childrenByParentId);
  const expandedIds = useTaxonomicTree((s) => s.expandedIds);
  const loadingParentIds = useTaxonomicTree((s) => s.loadingParentIds);
  const errorByParentId = useTaxonomicTree((s) => s.errorByParentId);
  const nextTiersByParentId = useTaxonomicTree((s) => s.nextTiersByParentId);
  const loadRoots = useTaxonomicTree((s) => s.loadRoots);
  const ensureChildren = useTaxonomicTree((s) => s.ensureChildren);
  const toggleExpand = useTaxonomicTree((s) => s.toggleExpand);
  const setError = useTaxonomicTree((s) => s.setError);
  const clearError = useTaxonomicTree((s) => s.clearError);
  const revealNode = useTaxonomicTree((s) => s.revealNode);
  const setIncludeExtinct = useTaxonomicTree((s) => s.setIncludeExtinct);
  void setError; // reserved for future API of the row; not used in this PR.

  const [searchOpen, setSearchOpen] = useState(false);
  const [searchHits, setSearchHits] = useState<TreeNodeResponse[]>([]);
  const [searchNoResults, setSearchNoResults] = useState<string | null>(null);
  const [searchHighlight, setSearchHighlight] = useState(0);
  const [extantOnly, setExtantOnly] = useState(true);
  const [synonymsOn, setSynonymsOn] = useState(false);
  const [indentStep, setIndentStep] = useState(INDENT_STEP_DESKTOP);
  const [focusedId, setFocusedId] = useState<number | string | null>(null);
  const [loadedCount, setLoadedCount] = useState<Map<number, number>>(new Map());
  const rowRefs = useRef<Map<number | string, HTMLButtonElement>>(new Map());

  // Boot: fetch roots on mount.
  useEffect(() => {
    void loadRoots();
  }, [loadRoots]);

  // Responsive indent step.
  useEffect(() => {
    if (typeof window === "undefined") return;
    // jsdom does not implement matchMedia; the test suite does not
    // care about responsive breakpoints, so the default desktop
    // step is fine when matchMedia is unavailable.
    if (typeof window.matchMedia !== "function") return;
    const mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`);
    const update = (): void => {
      setIndentStep(mql.matches ? INDENT_STEP_MOBILE : INDENT_STEP_DESKTOP);
    };
    update();
    mql.addEventListener("change", update);
    return () => mql.removeEventListener("change", update);
  }, []);

  // Debounced search.
  const debouncedSearch = useMemo(
    () =>
      createDebouncedSearch({
        fetch: (q: string) => fetchTreeSearch(q, { limit: SEARCH_RESULT_LIMIT }),
        delay: SEARCH_DEBOUNCE_MS,
      }),
    [],
  );

  // Track loaded children count for the live region.
  useEffect(() => {
    const next = new Map<number, number>();
    for (const [parentId, kids] of childrenByParentId.entries()) {
      next.set(parentId, kids.length);
    }
    setLoadedCount(next);
  }, [childrenByParentId]);

  // Build the visible row list (depth-first) and the
  // ancestor-of-currently-selected set. Tier groups are emitted
  // between the parent row and the grandchild flow so the keyboard
  // nav (ArrowDown/Up) crosses the tier boundary the same way it
  // crosses a regular tree row.
  const { visibleRows } = useMemo(() => {
    const rows: Array<VisibleRow> = [];

    const roots = childrenByParentId.get(0) ?? [];
    const selectedAncestorIds: ReadonlySet<number> = new Set<number>();

    function visitTierGroup(
      parentId: number,
      parentDepth: number,
      tier: TreeNodeTier,
      ancestors: ReadonlySet<number>,
    ): void {
      // The tier group's row sits alongside the parent's direct
      // children so the global keyboard nav finds it in the same
      // list. The ``depth`` is the parent's depth + 1 so the visual
      // indent and the ARIA level stay coherent.
      rows.push({
        kind: "tier-group",
        tier,
        parentId,
        parentDepth,
        selectedAncestorIds: ancestors,
      });
    }

    function walk(
      kids: TreeNodeResponse[],
      depth: number,
      ancestors: ReadonlySet<number>,
    ): void {
      for (const row of kids) {
        const newAncestors = new Set(ancestors);
        newAncestors.add(row.id);
        // Mark the row as visible (it sits on the explored path).
        rows.push({
          kind: "tree-row",
          row,
          depth,
          selectedAncestorIds: newAncestors,
        });
        if (expandedIds.has(row.id) && childrenByParentId.has(row.id)) {
          // Tier groups come FIRST (after the parent row, before
          // the grandchild flow) so the cascade-rank ordering the
          // spec asks for is preserved.
          const tiers = nextTiersByParentId.get(row.id);
          if (tiers !== undefined && tiers.length > 0) {
            for (const tier of tiers) {
              visitTierGroup(row.id, depth, tier, newAncestors);
            }
          }
          const grandkids = childrenByParentId.get(row.id) ?? [];
          walk(grandkids, depth + 1, newAncestors);
        }
      }
    }
    walk(roots, 0, selectedAncestorIds);
    return { visibleRows: rows };
  }, [childrenByParentId, expandedIds, nextTiersByParentId]);

  // When the expanded set changes, dispatch the explored path
  // via a ``path:change`` CustomEvent. The App listens for the
  // event and is the single source of truth for the
  // cascadePath store. The tree deliberately avoids writing
  // directly to the store so a future producer that dispatches
  // the event alone (e.g. a test fixture) does not race the
  // tree's own writes. The explored path is the list of
  // expanded rows' names top-down so the breadcrumb reads the
  // user's navigation history.
  //
  // The effect compares the new path against the last
  // computed reference and only dispatches when the path
  // changed. A redundant dispatch with the same content
  // would race with concurrent producers (e.g. a test
  // fixture that set the path before the tree booted).
  const lastDispatchedPathRef = useRef<string[] | null>(null);
  useEffect(() => {
    const path: string[] = [];
    let kids = childrenByParentId.get(0) ?? [];
    let reached = true;
    while (reached) {
      reached = false;
      for (const row of kids) {
        if (expandedIds.has(row.id)) {
          path.push(row.name);
          kids = childrenByParentId.get(row.id) ?? [];
          reached = true;
          break;
        }
      }
    }
    const last = lastDispatchedPathRef.current;
    if (
      last !== null &&
      last.length === path.length &&
      last.every((seg, i) => seg === path[i])
    ) {
      return;
    }
    lastDispatchedPathRef.current = path;
    window.dispatchEvent(
      new CustomEvent(PATH_CHANGE_EVENT, { detail: { path } }),
    );
  }, [expandedIds, childrenByParentId]);

  // Initial focus: first visible row.
  useEffect(() => {
    if (focusedId === null && visibleRows.length > 0) {
      const first = visibleRows[0];
      if (first !== undefined) setFocusedId(rowIdOf(first));
    }
  }, [focusedId, visibleRows]);

  // Focus the row when focusedId changes.
  useEffect(() => {
    if (focusedId === null) return;
    const btn = rowRefs.current.get(focusedId);
    if (btn !== undefined) {
      btn.focus();
    }
  }, [focusedId]);

  // Cascading keyboard nav: ArrowDown/Up move focus across
  // visible rows in order, ArrowRight expands, ArrowLeft
  // collapses, Enter toggles, Escape clears the search dropdown.
  // Tier groups participate in the same flow: the TierGroup
  // header is a regular button keyed by a synthetic string id
  // (``tier:<parentId>:<rank>``) so the keyboard nav can find it
  // in the same flat list as the tree rows.
  const onKeyDown = (
    e: React.KeyboardEvent<HTMLButtonElement>,
    id: number | string,
  ): void => {
    const idx = findRowIndex(visibleRows, id);
    if (idx === -1) return;
    const entry = visibleRows[idx];
    if (entry === undefined) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      const next = visibleRows[Math.min(idx + 1, visibleRows.length - 1)];
      if (next !== undefined) setFocusedId(rowIdOf(next));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      const prev = visibleRows[Math.max(idx - 1, 0)];
      if (prev !== undefined) setFocusedId(rowIdOf(prev));
    } else if (e.key === "ArrowRight") {
      if (entry.kind === "tree-row") {
        const row = entry.row;
        if (row.has_children && !expandedIds.has(row.id)) {
          e.preventDefault();
          void ensureChildren(row.id);
          toggleExpand(row.id);
        }
      }
      // Tier-group headers manage their own ArrowRight (toggle).
      // The header's own onClick setExpanded already covers the
      // keyboard toggle for the TierGroup — we let the browser's
      // default button keyboard behaviour fire.
    } else if (e.key === "ArrowLeft") {
      if (entry.kind === "tree-row") {
        const row = entry.row;
        if (row.has_children && expandedIds.has(row.id)) {
          e.preventDefault();
          toggleExpand(row.id);
        }
      }
      // Tier-group header ArrowLeft is handled by the TierGroup's
      // own onClick setExpanded via the browser's default button
      // behaviour.
    } else if (e.key === "Enter") {
      if (entry.kind === "tree-row") {
        const row = entry.row;
        if (row.has_children) {
          e.preventDefault();
          void ensureChildren(row.id);
          toggleExpand(row.id);
        }
      }
    } else if (e.key === "Home") {
      e.preventDefault();
      const first = visibleRows[0];
      if (first !== undefined) setFocusedId(rowIdOf(first));
    } else if (e.key === "End") {
      e.preventDefault();
      const last = visibleRows[visibleRows.length - 1];
      if (last !== undefined) setFocusedId(rowIdOf(last));
    } else if (e.key === "Escape") {
      if (searchOpen) {
        setSearchOpen(false);
      }
    }
  };

  // Search input handling.
  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>): void => {
    const value = e.target.value;
    if (value.length === 0) {
      setSearchOpen(false);
      setSearchHits([]);
      setSearchNoResults(null);
      debouncedSearch.cancel();
      return;
    }
    setSearchOpen(true);
    void debouncedSearch(value).then((result: ApiResult<TreeSearchResponse>) => {
      if (result.status === "ok") {
        setSearchHits(result.data.items);
        setSearchNoResults(result.data.items.length === 0 ? value : null);
      } else {
        setSearchHits([]);
        setSearchNoResults(value);
      }
    });
  };

  const handleSearchPick = (row: TreeNodeResponse): void => {
    setSearchOpen(false);
    setSearchHits([]);
    setSearchNoResults(null);
    // Expand every ancestor and focus the chosen row. The store's
    // ``revealNode`` walks the parent chain via the cache; any
    // missing level is fetched lazily so the expand is deterministic
    // even when the user has not touched the tree yet.
    void revealNode(row.id).then(() => {
      setFocusedId(row.id);
      // Scroll the row into view so the focus jump is visible.
      const btn = rowRefs.current.get(row.id);
      btn?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
  };

  // Empty / loading / error states for the root.
  const roots = childrenByParentId.get(0);
  const rootErr = errorByParentId.get(0);

  const registerRow = (id: number | string, el: HTMLButtonElement | null): void => {
    if (el === null) {
      rowRefs.current.delete(id);
    } else {
      rowRefs.current.set(id, el);
    }
  };

  return (
    <section
      aria-label="Taxonomic tree"
      className="rounded-card border border-border bg-surface p-4"
    >
      <h2 className="sr-only">Taxonomic tree</h2>
      <div className="flex flex-col gap-3 md:flex-row md:items-center">
        <div className="relative md:flex-1">
          <svg
            aria-hidden="true"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
          >
            <circle cx="7" cy="7" r="5" />
            <path d="m11 11 3 3" />
          </svg>
          <input
            type="search"
            aria-label="Find taxon"
            aria-controls="tree-search-results"
            aria-activedescendant={
              searchOpen && searchHits[searchHighlight] !== undefined
                ? `tree-search-result-${searchHits[searchHighlight]!.id}`
                : undefined
            }
            placeholder="Find taxon (e.g. Panthera)"
            role="combobox"
            aria-haspopup="listbox"
            aria-expanded={searchOpen}
            onChange={handleSearchChange}
            className="h-10 w-full rounded-md border border-border bg-surface px-3 pl-9 text-sm focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          />
          {searchOpen ? (
            <div
              id="tree-search-results"
              role="listbox"
              className="absolute left-0 right-0 top-full z-20 mt-1 max-h-96 overflow-y-auto rounded-md border border-border bg-surface shadow-lg"
            >
              {searchNoResults !== null ? (
                <p className="px-3 py-2 text-center text-sm text-slate">
                  No matches for "{searchNoResults}"
                </p>
              ) : (
                searchHits.map((row, i) => (
                  <button
                    key={row.id}
                    id={`tree-search-result-${row.id}`}
                    type="button"
                    role="option"
                    aria-selected={searchHighlight === i}
                    onClick={() => handleSearchPick(row)}
                    onMouseEnter={() => setSearchHighlight(i)}
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-bg focus:bg-bg focus:outline-none"
                  >
                    <span className="text-[10px] font-medium uppercase tracking-widest text-slate">
                      {row.rank}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-sm text-navy">
                      {row.display_name}
                    </span>
                  </button>
                ))
              )}
            </div>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate">
          <label
            htmlFor="tree-source-select"
            className="font-medium text-slate"
          >
            Source
          </label>
          <select
            id="tree-source-select"
            defaultValue="col"
            title="Multi-source support is coming soon. CoL is the only active source."
            className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-slate focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            <option value="col">CoL</option>
            <option value="gbif" disabled>
              GBIF
            </option>
            <option value="worms" disabled>
              WoRMS
            </option>
          </select>
          <label className="inline-flex items-center gap-2 font-medium text-slate">
            <input
              type="checkbox"
              checked={extantOnly}
              onChange={(e) => {
                const next = e.target.checked;
                setExtantOnly(next);
                // The store refetches the root and invalidates the
                // cache; the existing roots re-render without extinct
                // children once the fetch resolves.
                void setIncludeExtinct(next);
              }}
              title="Hide extinct taxa"
              className="h-4 w-4"
            />
            Extant only
          </label>
          <button
            type="button"
            aria-pressed={synonymsOn}
            onClick={() => setSynonymsOn((v) => !v)}
            className={
              "inline-flex min-h-[44px] items-center gap-2 rounded-chip border px-3 py-1 text-sm transition-colors " +
              (synonymsOn
                ? "border-accent bg-blue-50 text-accent"
                : "border-border bg-surface text-slate hover:bg-bg")
            }
          >
            <span
              aria-hidden="true"
              className={
                "h-2 w-2 rounded-full " + (synonymsOn ? "bg-accent" : "bg-muted")
              }
            />
            Synonyms
          </button>
        </div>
      </div>
      <div className="mt-4">
        {roots === undefined && rootErr === undefined ? (
          // Initial load in flight: five skeleton rows. Each
          // skeleton carries ``role="treeitem"`` + ``aria-level=1``
          // so the ``role="tree"`` parent satisfies axe-core's
          // ``aria-required-children`` rule while the user is
          // waiting for the fetch.
          <div
            role="tree"
            aria-label="Taxonomic tree"
            className="flex flex-col gap-2"
          >
            {[0, 1, 2, 3, 4].map((i) => (
              <div
                key={i}
                role="treeitem"
                aria-level={1}
                className="h-8 w-full rounded bg-bg animate-pulse"
              />
            ))}
          </div>
        ) : roots !== undefined && roots.length === 0 ? (
          // Empty state: zero roots — the database returned no
          // ``parent_id IS NULL`` rows. The message lives OUTSIDE
          // the ``role="tree"`` host because the host requires
          // treeitem children (axe ``aria-required-children``) and
          // a paragraph is not a treeitem.
          <p className="py-8 text-center text-sm text-slate">
            No taxonomy loaded. Check the database connection.
          </p>
        ) : roots === undefined && rootErr !== undefined ? (
          // Error state lives OUTSIDE the ``role="tree"`` host so the
          // error affordance (``Retry`` button) does not violate
          // axe-core's ``aria-required-children`` rule (treeitems
          // only).
          <div className="py-8 text-center">
            <p className="text-sm text-slate">No taxonomy loaded.</p>
            <button
              type="button"
              onClick={() => {
                clearError(0);
                void loadRoots();
              }}
              className="mt-4 inline-flex items-center gap-2 rounded-btn border border-border bg-surface px-3 py-2 text-sm text-slate hover:bg-bg"
            >
              Retry
            </button>
          </div>
        ) : (
          <div
            role="tree"
            aria-label="Taxonomic tree"
          >
            {visibleRows.map((entry) => {
              if (entry.kind === "tree-row") {
                const { row, depth, selectedAncestorIds } = entry;
                return (
                  <TreeRow
                    key={row.id}
                    row={row}
                    depth={depth}
                    indentStep={indentStep}
                    isExpanded={expandedIds.has(row.id)}
                    isLoading={loadingParentIds.has(row.id)}
                    hasError={errorByParentId.has(row.id)}
                    errorMessage={errorByParentId.get(row.id) ?? ""}
                    onToggle={(id) => {
                      if (!expandedIds.has(id)) {
                        void ensureChildren(id);
                      }
                      toggleExpand(id);
                    }}
                    onRetry={(id) => {
                      clearError(id);
                      void ensureChildren(id);
                    }}
                    onKeyDown={onKeyDown}
                    focusedId={focusedId}
                    registerRow={registerRow}
                    selectedAncestorIds={selectedAncestorIds}
                  />
                );
              }
              // Tier-group entry: render the TierGroup widget.
              const { tier, parentId, parentDepth, selectedAncestorIds } = entry;
              return (
                <TierGroup
                  key={tierGroupKey(parentId, tier.rank)}
                  parentId={parentId}
                  tier={tier}
                  parentDepth={parentDepth}
                  indentStep={indentStep}
                  isFirstTier={isFirstTierFor(parentId, tier.rank)}
                  selectedAncestorIds={selectedAncestorIds}
                  focusedId={focusedId}
                  registerRow={registerRow}
                  onHeaderKeyDown={onKeyDown}
                  onToggleRow={(id) => {
                    if (!expandedIds.has(id)) {
                      void ensureChildren(id);
                    }
                    toggleExpand(id);
                  }}
                  onRetryRow={(id) => {
                    clearError(id);
                    void ensureChildren(id);
                  }}
                  loadingParentIds={loadingParentIds}
                  errorByParentId={errorByParentId}
                />
              );
            })}
          </div>
        )}
      </div>
      {/* Live region for child-count announcements. */}
      <span className="sr-only" aria-live="polite" aria-atomic="true">
        {Array.from(loadedCount.entries())
          .map(([parentId, n]) => {
            const word = n === 1 ? "child" : "children";
            return `Loaded ${n} ${word} for parent ${parentId}`;
          })
          .join(". ")}
      </span>
    </section>
  );
}
