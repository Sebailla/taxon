/** AmbiguityPicker — modal shown when a (genus, epithet) lookup 409s.

The backend returns ``candidates[]`` with each candidate's full
Kingdom → … → Genus breadcrumb so the user can disambiguate. The
modal:

- Renders each candidate as a row with the breadcrumb + canonical
  name + display name.
- Closes on Escape (focus trap) and on backdrop click.
- Calls ``onPick`` with the chosen candidate; the parent component
  is responsible for the post-pick state transition.
- Traps keyboard focus inside the dialog while it is open (WCAG
  modal pattern). Tab moves focus to the next focusable element
  inside the dialog; at the end of the list, focus wraps back to
  the first element. Shift+Tab does the reverse. The first element
  receives focus when the dialog opens.
*/

import { useEffect, useRef } from "react";

import type { AmbiguityCandidate } from "../api";

interface AmbiguityPickerProps {
  candidates: AmbiguityCandidate[];
  onClose: () => void;
  onPick: (candidate: AmbiguityCandidate) => void;
}

export function AmbiguityPicker(props: AmbiguityPickerProps): JSX.Element {
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const lastFocusedRef = useRef<Element | null>(null);

  // Capture the trigger element so we can restore focus when the
  // dialog closes. WAI-ARIA APG recommends this for modal dialogs.
  useEffect(() => {
    lastFocusedRef.current = document.activeElement;
    return () => {
      const last = lastFocusedRef.current;
      if (
        last !== null &&
        last instanceof HTMLElement &&
        document.body.contains(last)
      ) {
        last.focus();
      }
    };
  }, []);

  // Move focus to the first focusable element inside the dialog
  // on mount. WAI-ARIA APG requires focus to start inside the dialog.
  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog === null) return;
    const first = dialog.querySelector<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    first?.focus();
  }, []);

  // Trap Tab / Shift+Tab inside the dialog. We compute the focusable
  // list on every keydown so the trap reflects the DOM at the moment
  // the user pressed Tab (a candidate row could be removed mid-session).
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === "Escape") {
        e.preventDefault();
        props.onClose();
        return;
      }
      if (e.key !== "Tab") return;
      const dialog = dialogRef.current;
      if (dialog === null) return;
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((el) => !el.hasAttribute("disabled"));
      if (focusable.length === 0) return;
      const first = focusable[0]!;
      const last = focusable[focusable.length - 1]!;
      const active = document.activeElement;
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [props]);

  return (
    <div
      ref={dialogRef}
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
                className="min-h-[44px] rounded-btn border border-accent bg-blue-50 px-3 py-1 text-sm text-accent hover:bg-accent hover:text-surface"
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
            className="min-h-[44px] rounded-btn border border-border bg-surface px-3 py-1 text-sm text-slate hover:bg-bg"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}