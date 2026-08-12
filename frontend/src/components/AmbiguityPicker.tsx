/** AmbiguityPicker — modal shown when a (genus, epithet) lookup 409s.

The backend returns ``candidates[]`` with each candidate's full
Kingdom → … → Genus breadcrumb so the user can disambiguate. The
modal:

- Renders each candidate as a row with the breadcrumb + canonical
  name + display name.
- Closes on Escape (focus trap) and on backdrop click.
- Calls ``onPick`` with the chosen candidate; the parent component
  is responsible for the post-pick state transition.
*/

import { useEffect } from "react";

import type { AmbiguityCandidate } from "../api";

interface AmbiguityPickerProps {
  candidates: AmbiguityCandidate[];
  onClose: () => void;
  onPick: (candidate: AmbiguityCandidate) => void;
}

export function AmbiguityPicker(props: AmbiguityPickerProps): JSX.Element {
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === "Escape") props.onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [props]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="ambiguity-title"
      className="fixed inset-0 z-10 flex items-center justify-center bg-navy/50"
      onClick={(e) => {
        if (e.target === e.currentTarget) props.onClose();
      }}
    >
      <div className="w-full max-w-lg rounded-card border border-border bg-surface p-6 shadow-lg">
        <h2
          id="ambiguity-title"
          className="mb-2 text-base font-semibold text-navy"
        >
          Ambiguous — pick one
        </h2>
        <p className="mb-4 text-sm text-slate">
          Multiple species match the (genus, epithet) pair. Pick the one
          you meant.
        </p>
        <ul className="space-y-2" aria-label="Ambiguity candidates">
          {props.candidates.map((c) => (
            <li
              key={c.id}
              className="flex items-start justify-between gap-3 rounded-btn border border-border bg-bg p-3"
            >
              <div className="min-w-0 flex-1">
                <p className="font-mono text-sm text-navy">{c.canonical_name}</p>
                <p className="text-xs text-slate">{c.display_name}</p>
                <p className="mt-1 font-mono text-xs text-slate">
                  {c.breadcrumb.join(" › ")}
                </p>
              </div>
              <button
                type="button"
                onClick={() => props.onPick(c)}
                className="rounded-btn border border-accent bg-blue-50 px-3 py-1 text-sm text-accent hover:bg-accent hover:text-surface"
              >
                Select
              </button>
            </li>
          ))}
        </ul>
        <div className="mt-4 flex justify-end">
          <button
            type="button"
            onClick={props.onClose}
            className="rounded-btn border border-border bg-surface px-3 py-1 text-sm text-slate hover:bg-bg"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}