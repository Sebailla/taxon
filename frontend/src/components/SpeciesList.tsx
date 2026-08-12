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
          <li key={row.id} className="list-none">
            <button
              type="button"
              onClick={() => {
                window.dispatchEvent(
                  new CustomEvent("taxon:select", {
                    detail: {
                      row,
                      breadcrumb: props.breadcrumb,
                      parentSegments: props.parentSegments,
                    },
                  }),
                );
              }}
              className="flex w-full items-center justify-between gap-3 rounded-btn border border-border bg-bg p-2 text-left hover:bg-surface"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate font-mono text-sm text-navy">{row.name}</p>
                {row.display_name !== row.name ? (
                  <p className="truncate text-xs text-slate">{row.display_name}</p>
                ) : null}
              </div>
              <MarkerBadges row={row} />
            </button>
          </li>
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