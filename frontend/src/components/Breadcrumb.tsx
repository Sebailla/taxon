/** Breadcrumb — the resolved species' lineage, Kingdom → … → Genus.

The breadcrumb is a horizontal ordered list with chevron separators
between segments. The visual treatment matches the Phase 3 design:
``font-mono`` text on a ``bg-surface`` card with a 1px ``border-border``.

Every segment is a ``<button type="button">``; clicking a segment
calls ``onSelect(trail.slice(0, idx + 1))`` so the parent App can
fetch the per-taxon search-source dispatch for that cascade step.
The deepest segment carries ``aria-current="page"`` so screen
readers announce it as the current step. When ``onSelect`` is
omitted the click is a no-op — the ``<nav>`` still renders.
*/

interface BreadcrumbProps {
  trail: string[];
  /** Called when a segment button is clicked. Receives the trail
   *  up to and including the clicked segment (1-based slice end). */
  onSelect?: (path: string[]) => void;
}

export function Breadcrumb({ trail, onSelect }: BreadcrumbProps): JSX.Element {
  const deepestIndex = trail.length - 1;
  return (
    <nav
      aria-label="Resolved species breadcrumb"
      className="rounded-card border border-border bg-surface p-4"
    >
      <h2 className="mb-2 text-sm font-medium text-slate">Breadcrumb</h2>
      <ol className="flex flex-wrap items-center gap-1 font-mono text-sm text-navy">
        {trail.map((segment, idx) => {
          const isDeepest = idx === deepestIndex;
          const handleClick = (): void => {
            onSelect?.(trail.slice(0, idx + 1));
          };
          return (
            <li key={`${segment}-${idx}`} className="flex items-center gap-1">
              {idx > 0 ? <span aria-hidden="true">›</span> : null}
              <button
                type="button"
                onClick={handleClick}
                aria-current={isDeepest ? "page" : undefined}
              >
                {segment}
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}