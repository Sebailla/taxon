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

interface SpeciesLinksProps {
  links: SearchLinkItem[];
}

export function SpeciesLinks({ links }: SpeciesLinksProps): JSX.Element {
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
          <SourceLink key={link.source + link.url} link={link} />
        ))}
      </div>
    </section>
  );
}

function SourceLink({ link }: { link: SearchLinkItem }): JSX.Element {
  const isScihub = link.source === "Sci-hub";
  return (
    <a
      role="listitem"
      href={link.url}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`${link.label} (opens in a new tab)`}
      className={
        "inline-flex items-center justify-between gap-2 rounded-btn border bg-surface px-3 py-2 text-sm text-navy hover:bg-bg " +
        (isScihub ? "border-red" : "border-border")
      }
    >
      <span>{link.label}</span>
      <ExternalLinkIcon />
    </a>
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