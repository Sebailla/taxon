/** Toggles — 4 inclusion-class chips with OR semantics.

The species list defaults to accepted-only. Each toggle chip widens
the result set per the inclusion-filters spec: enabling ``extinct``
adds extinct species to the response; enabling ``synonyms`` adds
synonyms; enabling multiple chips is a union (OR), never an
intersection.

Accessibility:

- Each chip is a real ``<button>`` with ``aria-pressed`` reflecting
  the on/off state. Screen readers announce "pressed / not pressed".
- The chip group carries an ``aria-label`` so the toggle set has a
  discoverable name.
- Focus rings render via the global ``:focus-visible`` rule in
  ``src/index.css``.
*/

import type { InclusionClass } from "../api";

export type { InclusionClass };

interface TogglesProps {
  value: Set<InclusionClass>;
  onChange: (next: Set<InclusionClass>) => void;
}

const TOGGLES: ReadonlyArray<{ key: InclusionClass; label: string }> = [
  { key: "extinct", label: "Extinct" },
  { key: "synonyms", label: "Synonyms" },
  { key: "uncertain", label: "Uncertain" },
  { key: "unassigned", label: "Unassigned" },
];

export function Toggles({ value, onChange }: TogglesProps): JSX.Element {
  const handleClick = (key: InclusionClass): void => {
    const next = new Set(value);
    if (next.has(key)) {
      next.delete(key);
    } else {
      next.add(key);
    }
    onChange(next);
  };

  return (
    <fieldset
      className="flex flex-wrap items-center gap-2"
      aria-label="Include in species list"
    >
      <legend className="mr-2 text-sm font-medium text-navy">
        Include in species list
      </legend>
      {TOGGLES.map((toggle) => {
        const active = value.has(toggle.key);
        return (
          <button
            key={toggle.key}
            type="button"
            aria-pressed={active}
            onClick={() => handleClick(toggle.key)}
            className={
              "inline-flex items-center gap-2 rounded-chip border px-3 py-1 text-sm transition-colors " +
              (active
                ? "border-accent bg-blue-50 text-accent"
                : "border-border bg-surface text-slate hover:bg-bg")
            }
          >
            <span
              aria-hidden="true"
              className={
                "h-2 w-2 rounded-full " + (active ? "bg-accent" : "bg-muted")
              }
            />
            {toggle.label}
          </button>
        );
      })}
    </fieldset>
  );
}