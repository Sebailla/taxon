/** SpeciesList — the scrollable list under the selected genus.

Renders the canonical name (mono font) + the display name with the
author citation + a small badge for each marker flag. Handles
loading / error / empty / not-found states per the spec.

Empty / loading states follow the impeccable audit's feedback
matrix from the Phase 3 design.

The list is a fixed max-height with scroll overflow; long species
lists (some genera in WoRMS have 500+) cap at the page size from
the API and offer a "Load more" affordance when ``cursor`` is set.
*/

import type { TaxonResponse } from "../api";
import { speciesKey } from "../api";
import { dispatchTaxonSelect } from "../events/taxonSelect";
import { useWorkspace } from "../store/workspace";

interface SpeciesListProps {
  rows: TaxonResponse[];
  status: "idle" | "loading" | "error";
  cursor: string | null;
  /** Parent-path segments used by the App to call ``fetchLinks``. */
  parentSegments: string[];
  /** Breadcrumb computed by the reducer's parent-path walk. */
  breadcrumb: string[];
  onLoadMore?: () => void;
}

export function SpeciesList(props: SpeciesListProps): JSX.Element {
  if (props.rows.length === 0 && props.status === "loading") {
    return (
      <p className="rounded-card border border-border bg-surface p-4 text-sm text-slate">
        Loading children…
      </p>
    );
  }

  if (props.rows.length === 0 && props.status === "error") {
    return (
      <p className="rounded-card border border-red bg-red-50 p-4 text-sm text-red">
        Network error. Try again.
      </p>
    );
  }

  if (props.rows.length === 0) {
    return (
      <p className="rounded-card border border-border bg-surface p-4 text-sm text-slate">
        No children.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <ul
        aria-label="Species list"
        className="max-h-96 space-y-2 overflow-y-auto rounded-card border border-border bg-surface p-2"
      >
        {props.rows.map((row) => (
          <SpeciesRow key={row.id} row={row} props={props} />
        ))}
      </ul>
      {props.cursor !== null && props.onLoadMore ? (
        <button
          type="button"
          onClick={props.onLoadMore}
          className="rounded-btn border border-border bg-surface px-3 py-1 text-sm text-slate hover:bg-bg"
        >
          Load more
        </button>
      ) : null}
    </div>
  );
}

function SpeciesRow({ row, props }: { row: TaxonResponse; props: SpeciesListProps }): JSX.Element {
  const [genus, ...epithetParts] = row.name.split(" ");
  const epithet = epithetParts.join(" ");
  const key = speciesKey(genus, epithet);
  const explored = useWorkspace((state) => state.explored.has(key));
  const folder = useWorkspace((state) => state.folders.get(key));
  const toggleExplored = useWorkspace((state) => state.toggleExplored);
  const createFolder = useWorkspace((state) => state.createFolder);

  return (
    <li className="flex list-none items-center gap-2 rounded-btn border border-border bg-bg p-2">
      <button type="button" onClick={() => dispatchTaxonSelect({ row, breadcrumb: props.breadcrumb, parentSegments: props.parentSegments })} className="flex min-w-0 flex-1 items-center justify-between gap-3 text-left">
        <div className="min-w-0 flex-1">
          <p className="truncate font-mono text-sm text-navy">{row.name}</p>
          {row.display_name !== row.name ? <p className="truncate text-xs text-slate">{row.display_name}</p> : null}
        </div>
        <MarkerBadges row={row} />
      </button>
      <input type="checkbox" checked={explored} aria-label={`Mark ${row.name} as explored`} onChange={() => void toggleExplored(genus, epithet)} />
      {folder ? (
        <span title={folder} className="rounded-chip border border-border px-2 py-0.5 text-xs text-slate">folder</span>
      ) : (
        <button type="button" aria-label={`Create folder for ${row.name}`} onClick={() => void createFolder(genus, epithet)} className="rounded-btn border border-border px-2 py-1 text-xs text-slate">Create folder</button>
      )}
    </li>
  );
}

function MarkerBadges({ row }: { row: TaxonResponse }): JSX.Element | null {
  const badges: Array<{ key: string; label: string; className: string }> = [];
  if (row.is_extinct) {
    badges.push({
      key: "extinct",
      label: "† extinct",
      className: "border-red bg-red-50 text-red",
    });
  }
  if (row.is_synonym) {
    badges.push({
      key: "synonym",
      label: "= synonym",
      className: "border-amber bg-amber-50 text-amber",
    });
  }
  if (row.is_uncertain) {
    badges.push({
      key: "uncertain",
      label: "? uncertain",
      className: "border-border bg-bg text-slate",
    });
  }
  if (row.is_unassigned) {
    badges.push({
      key: "unassigned",
      label: "unassigned",
      className: "border-border bg-bg text-slate",
    });
  }
  if (badges.length === 0) return null;
  return (
    <div className="flex shrink-0 gap-1">
      {badges.map((b) => (
        <span
          key={b.key}
          className={
            "inline-flex items-center rounded-chip border px-2 py-0.5 text-xs " +
            b.className
          }
        >
          {b.label}
        </span>
      ))}
    </div>
  );
}