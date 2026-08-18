/** SpeciesLinks — the 12 dispatch URLs rendered as a button grid.

Each link opens in a new tab (``target="_blank"``) with
``rel="noopener noreferrer"`` so the SPA cannot be hijacked through
``window.opener``. The button grid mirrors the Phase 3 design:

- 4×3 grid on desktop, 2-column on mobile.
- Sci-hub is visually separated (a top border + label suffix) so
  the user knows it is a different category of source.
- Each button has a visible external-link icon for affordance.

The links come pre-resolved from the API client (the backend
performs the ``{q}`` substitution); the component is a pure
renderer with no fetching logic.
*/

import type { SearchLinkItem } from "../api";
import { speciesKey } from "../api";
import { useWorkspace } from "../store/workspace";

interface SpeciesLinksProps {
  links: SearchLinkItem[];
  genus?: string;
  epithet?: string;
}

export function SpeciesLinks({ links, genus, epithet }: SpeciesLinksProps): JSX.Element {
  if (links.length === 0) {
    return (
      <div className="rounded-card border border-border bg-surface p-4">
        <p className="text-sm text-slate">No links available.</p>
      </div>
    );
  }

  return (
    <section aria-label="Search source dispatch" className="space-y-3">
      <h2 className="text-sm font-medium text-navy">Search source dispatch</h2>
      <div
        className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4"
        role="list"
      >
        {links.map((link) => (
          <SourceLink key={link.source + link.url} link={link} genus={genus} epithet={epithet} />
        ))}
      </div>
    </section>
  );
}

function SourceLink({ link, genus, epithet }: { link: SearchLinkItem; genus?: string; epithet?: string }): JSX.Element {
  const isScihub = link.source === "Sci-hub";
  const key = genus && epithet ? speciesKey(genus, epithet) : null;
  const visited = useWorkspace((state) => key !== null && (state.visitedLinks.get(key)?.has(link.source) ?? false));
  const toggleVisited = useWorkspace((state) => state.toggleVisited);
  const setActiveLink = useWorkspace((state) => state.setActiveLink);
  return (
    <div role="listitem" className={`flex items-center gap-2 rounded-btn border bg-surface px-3 py-2 text-sm ${visited ? "border-muted text-slate line-through" : isScihub ? "border-red text-navy" : "border-border text-navy"}`}>
      {genus && epithet ? (
        <input type="checkbox" role="switch" checked={visited} aria-checked={visited} aria-label={`Mark ${link.source} as visited`} onChange={() => void toggleVisited(genus, epithet, link.source)} />
      ) : null}
      <a
        href={link.url}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={`${link.label} (opens in a new tab)`}
        onClick={() => {
          // Populating ``activeLink`` is the contract for the
          // "Embedded search result" explorer panel. The
          // species-cell click is the ONLY trigger that mutates
          // the active link — the per-taxon breadcrumb-links panel
          // does NOT have genus/epithet props, so the click is a
          // no-op there. The new tab still opens via the anchor's
          // ``target="_blank"`` attribute.
          if (key !== null) {
            setActiveLink({ speciesKey: key, source: link.source, url: link.url });
          }
        }}
        className="inline-flex min-w-0 flex-1 items-center justify-between gap-2 hover:underline"
      >
        <span>{link.label}</span>
        <ExternalLinkIcon />
      </a>
    </div>
  );
}

function ExternalLinkIcon(): JSX.Element {
  return (
    <svg
      aria-hidden="true"
      className="h-4 w-4 text-muted"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
    >
      <path d="M11 3h6v6" />
      <path d="M17 3 9 11" />
      <path d="M15 13v4H3V5h4" />
    </svg>
  );
}