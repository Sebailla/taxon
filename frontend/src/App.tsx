/** App — the root component.

Composes the cascade UI with the breadcrumb of the resolved species
and the 12-link dispatch grid. Layout matches the Phase 3 design:
two-column on desktop (cascade + list on the left, breadcrumb +
links on the right), single-column on mobile.

The App owns the species selection state. The Cascade emits the
species + breadcrumb when a species row is clicked; the App stores
it and triggers the links fetch.
*/

import { useEffect, useState } from "react";

import type {
  SearchLinkItem,
  SpeciesLookupResponse,
} from "./api";
import { fetchLinks } from "./api";
import { TAXON_SELECT_EVENT, parseTaxonSelectEvent } from "./events/taxonSelect";
import { Cascade } from "./components/Cascade";
import { SpeciesLinks } from "./components/SpeciesLinks";
import { Breadcrumb } from "./components/Breadcrumb";

export function App(): JSX.Element {
  const [resolved, setResolved] = useState<SpeciesLookupResponse | null>(null);
  const [links, setLinks] = useState<SearchLinkItem[] | null>(null);
  const [linksStatus, setLinksStatus] = useState<"idle" | "loading" | "error">(
    "idle",
  );
  const [parentSegments, setParentSegments] = useState<string[]>([]);

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

  return (
    <main className="mx-auto min-h-screen max-w-page px-6 py-8">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold text-navy">Taxon</h1>
        <p className="text-sm text-slate">Species search dispatcher</p>
      </header>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
        <div>
          <Cascade />
        </div>

        <aside className="space-y-6">
          {resolved !== null ? <Breadcrumb trail={resolved.breadcrumb} /> : null}
          {links !== null ? <SpeciesLinks links={links} /> : null}
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
        </aside>
      </div>
    </main>
  );
}