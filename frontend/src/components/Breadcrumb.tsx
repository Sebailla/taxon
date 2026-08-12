/** Breadcrumb — the resolved species' lineage, Kingdom → … → Genus.

The breadcrumb is a horizontal ordered list with chevron separators
between segments. The visual treatment matches the Phase 3 design:
``font-mono`` text on a ``bg-surface`` card with a 1px ``border-border``.
*/

interface BreadcrumbProps {
  trail: string[];
}

export function Breadcrumb({ trail }: BreadcrumbProps): JSX.Element {
  return (
    <nav
      aria-label="Resolved species breadcrumb"
      className="rounded-card border border-border bg-surface p-4"
    >
      <h2 className="mb-2 text-sm font-medium text-slate">Breadcrumb</h2>
      <ol className="flex flex-wrap items-center gap-1 font-mono text-sm text-navy">
        {trail.map((segment, idx) => (
          <li key={`${segment}-${idx}`} className="flex items-center gap-1">
            {idx > 0 ? <span aria-hidden="true">›</span> : null}
            <span>{segment}</span>
          </li>
        ))}
      </ol>
    </nav>
  );
}