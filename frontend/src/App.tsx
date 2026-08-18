/** App — the root component.

Composes the cascade UI with the breadcrumb of the resolved species
and the 12-link dispatch grid. Layout matches the Phase 3 design:
two-column on desktop (cascade + list on the left, breadcrumb +
links on the right), single-column on mobile.

The App owns three pieces of state:

- ``resolved`` — the species the user clicked. Set by the
  ``taxon:select`` CustomEvent (post-resolution only).
- ``links`` / ``linksStatus`` — the 12 dispatch URLs for the
  resolved species. Fetched on ``taxon:select`` and on any
  path-change that invalidates them.
- ``cascadePath`` — the mid-cascade path broadcast by the
  ``path:change`` CustomEvent. Drives the breadcrumb visibility
  AND the per-taxon breadcrumb-links panel.

The breadcrumb-links panel and the species-links panel are
mutually exclusive (last-clicked wins): a species click resets
``cascadePath``'s panel; a segment click resets the species
panel. Each panel uses its own ``AbortController`` so a stale
fetch never resolves into a stale render.
*/

import { useEffect, useState } from "react";

import type {
  ApiResult,
  SearchLinkItem,
  SpeciesLookupResponse,
  TaxonLinksResponse,
} from "./api";
import { fetchLinks, fetchTaxonLinks } from "./api";
import { TAXON_SELECT_EVENT, parseTaxonSelectEvent } from "./events/taxonSelect";
import { TaxonomicTree } from "./components/TaxonomicTree";
import { SpeciesLinks } from "./components/SpeciesLinks";
import { Breadcrumb } from "./components/Breadcrumb";
import { ExplorerPanel } from "./components/ExplorerPanel";
import { useCascadePath } from "./store/cascadePath";

/** CustomEvent name the TaxonomicTree (and the legacy Cascade) emits
 *  whenever the explored path changes. The App listens for it to
 *  keep the path in sync with the Zustand store. The
 *  TaxonomicTree owns the constant; the App re-exports it for
 *  ergonomic test imports. */
export const PATH_CHANGE_EVENT = "path:change";

type BreadcrumbLinksState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ok"; data: TaxonLinksResponse }
  | { status: "error"; detail: string };

export function App(): JSX.Element {
  const [resolved, setResolved] = useState<SpeciesLookupResponse | null>(null);
  const [links, setLinks] = useState<SearchLinkItem[] | null>(null);
  const [linksStatus, setLinksStatus] = useState<"idle" | "loading" | "error">(
    "idle",
  );
  const [parentSegments, setParentSegments] = useState<string[]>([]);
  const cascadePath = useCascadePath((state) => state.path);
  const [breadcrumbLinks, setBreadcrumbLinks] =
    useState<BreadcrumbLinksState>({ status: "idle" });

  // Listen for species selection: the Cascade emits a (row, breadcrumb)
  // pair whenever the user clicks a species row. The detail is
  // validated through a Zod schema in parseTaxonSelectEvent so a
  // malformed event (from a future producer that drifted from the
  // contract) cannot crash the App.
  useEffect(() => {
    const handler = (e: Event): void => {
      const detail = parseTaxonSelectEvent(e);
      if (detail === null) return;
      setResolved({
        id: detail.row.id,
        canonical_name: detail.row.name,
        display_name: detail.row.display_name,
        markers: {
          is_synonym: detail.row.is_synonym,
          is_extinct: detail.row.is_extinct,
          is_uncertain: detail.row.is_uncertain,
          is_unassigned: detail.row.is_unassigned,
        },
        breadcrumb: detail.breadcrumb,
      });
      setParentSegments(detail.parentSegments);
      // Last-clicked wins: a species click clears the breadcrumb
      // panel so the two panels never coexist.
      setBreadcrumbLinks({ status: "idle" });
    };
    window.addEventListener(TAXON_SELECT_EVENT, handler);
    return () => window.removeEventListener(TAXON_SELECT_EVENT, handler);
  }, []);

  // Load links whenever the resolved species or its parent path changes.
  useEffect(() => {
    if (resolved === null) return;
    const ctrl = new AbortController();
    setLinksStatus("loading");
    const epithet = resolved.canonical_name.split(/\s+/).slice(1).join(" ");
    void fetchLinks(parentSegments, epithet, { signal: ctrl.signal }).then(
      (result) => {
        if (ctrl.signal.aborted) return;
        if (result.status === "ok") {
          setLinks(result.data.links);
          setLinksStatus("idle");
        } else {
          setLinks(null);
          setLinksStatus("error");
        }
      },
    );
    return () => ctrl.abort();
  }, [resolved, parentSegments]);

  // Breadcrumb-links panel: keyed by the path reference so every
  // distinct pick fires a fresh fetch and the previous in-flight
  // one is aborted on cleanup. The path comes from the Zustand
  // store which is fed by both the Cascade reducer (real user
  // picks) and the App's own ``path:change`` listener
  // (event-driven picks from tests or future producers).
  //
  // The store's ``setPath`` is a no-op for an identical-content
  // array, so the cascadePath reference is stable across
  // redundant dispatches and the effect does not refire.
  useEffect(() => {
    if (cascadePath.length === 0) {
      // No path = no panel; clear any stale data.
      setBreadcrumbLinks({ status: "idle" });
      return;
    }
    const ctrl = new AbortController();
    setBreadcrumbLinks({ status: "loading" });
    void fetchTaxonLinks(cascadePath, { signal: ctrl.signal }).then(
      (result: ApiResult<TaxonLinksResponse>) => {
        if (ctrl.signal.aborted) return;
        if (result.status === "ok") {
          setBreadcrumbLinks({ status: "ok", data: result.data });
        } else if (result.status === "not-found") {
          setBreadcrumbLinks({ status: "error", detail: result.detail });
        } else if (result.status === "error") {
          setBreadcrumbLinks({ status: "error", detail: result.detail });
        } else {
          setBreadcrumbLinks({ status: "error", detail: "unknown error" });
        }
      },
    );
    return () => ctrl.abort();
  }, [cascadePath]);

  // Listen for ``path:change`` events so any producer
  // (the Cascade in production, tests in development) can
  // drive the panel. The Cascade also writes through the
  // Zustand store directly, but listening here keeps the
  // App correct even if a future producer skips the store
  // and dispatches the event alone.
  useEffect(() => {
    const handler = (e: Event): void => {
      const custom = e as CustomEvent<{ path?: string[] }>;
      const detail = custom.detail;
      if (!detail || !Array.isArray(detail.path)) return;
      useCascadePath.getState().setPath(detail.path);
    };
    window.addEventListener(PATH_CHANGE_EVENT, handler);
    return () => window.removeEventListener(PATH_CHANGE_EVENT, handler);
  }, []);

  // The breadcrumb is visible whenever the cascade path has at
  // least one entry, regardless of whether a species has been
  // resolved yet (Task 4.6 — drop the resolved !== null gate).
  const breadcrumbTrail = cascadePath;
  const breadcrumbHandler = (trail: string[]): void => {
    // The click handler is a no-op now: the segment click already
    // set the cascade path via the Cascade's reducer dispatch, so
    // by the time the App's handler runs, ``cascadePath`` is
    // already updated. We keep the handler as a thin wrapper so
    // future PRs can layer analytics or side-effects on top.
    void trail;
  };

  return (
    <main className="mx-auto min-h-screen max-w-page px-6 py-8">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold text-navy">Taxon</h1>
        <p className="text-sm text-slate">Species search dispatcher</p>
      </header>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
        <div>
          <TaxonomicTree />
        </div>

        <aside className="space-y-6">
          {breadcrumbTrail.length > 0 ? (
            <Breadcrumb
              trail={breadcrumbTrail}
              onSelect={breadcrumbHandler}
            />
          ) : null}
          {/* Last-clicked wins: show species links ONLY when the
              breadcrumb panel is idle; show breadcrumb links when
              they are loading / ok / error. */}
          {resolved !== null && breadcrumbLinks.status === "idle" ? (
            <>
              {links !== null ? <SpeciesLinks links={links} genus={resolved.canonical_name.split(/\s+/)[0]} epithet={resolved.canonical_name.split(/\s+/).slice(1).join(" ")} /> : null}
              {links === null && linksStatus === "loading" ? (
                <p className="rounded-card border border-border bg-surface p-4 text-sm text-slate">
                  Loading links…
                </p>
              ) : null}
              {links === null && linksStatus === "error" ? (
                <p className="rounded-card border border-red bg-red-50 p-4 text-sm text-red">
                  Could not load links.
                </p>
              ) : null}
            </>
          ) : null}
          {breadcrumbLinks.status === "ok" ? (
            <SpeciesLinks links={breadcrumbLinks.data.links} />
          ) : null}
          {breadcrumbLinks.status === "loading" &&
          resolved === null ? (
            <p className="rounded-card border border-border bg-surface p-4 text-sm text-slate">
              Loading links…
            </p>
          ) : null}
          {breadcrumbLinks.status === "error" ? (
            <p className="rounded-card border border-red bg-red-50 p-4 text-sm text-red">
              Could not load links: {breadcrumbLinks.detail}
            </p>
          ) : null}
          {/* Embedded explorer panel. The panel reads the workspace
              store's ``activeLink`` (set by SpeciesLinks species-cell
              clicks) and renders the iframe + fallback card. The
              sticky + top-0 keeps the embedded page visible while
              the user scrolls the dispatch grid. */}
          <div className="sticky top-0">
            <ExplorerPanel />
          </div>
        </aside>
      </div>
    </main>
  );
}