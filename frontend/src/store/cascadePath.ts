/** Zustand store for the cascade path.

The breadcrumb (``Breadcrumb.tsx``) writes the picked path through
``setPath``; the App's panel effect reads it via the Zustand
subscriber. The path is the only mid-cascade state the App needs
to render the breadcrumb-links panel before the user has resolved
a species.

We use Zustand's vanilla flavour (``createStore``) instead of the
React hook flavour because:

- The store is read from a non-React event handler (the App's
  ``path:change`` listener) AND from a React ``useEffect``.
  Vanilla gives us a single source of truth that both can read.
- The path rarely changes; subscribers fire only when the path
  actually changes (Zustand uses reference equality on the
  selector by default; we keep the array identity stable when
  no entry changed).

The store is a singleton — import the ``useCascadePath`` named
export from anywhere in the frontend tree.
*/

import { createStore } from "zustand/vanilla";

/**
 * Public store shape.
 *
 * - ``path``: the dense cascade path (``["Biota", "Animalia", ...]``).
 * - ``setPath(p)``: replace the path; subscribers fire when the
 *   reference changes (Zustand's default shallow equality).
 */
export interface CascadePathState {
  path: string[];
  setPath: (path: string[]) => void;
}

/**
 * Helper: shallow array equality (length + every entry).
 *
 * Zustand's default selector equality is reference equality. The
 * Cascade reducer always returns a fresh array on ``set-path``,
 * so reference equality alone would fire the subscriber on every
 * state update. Compare arrays by content so a no-op replace
 * (``setPath(["A"])`` when ``path === ["A"]``) does not refire.
 */
function arraysEqual(a: readonly string[], b: readonly string[]): boolean {
  if (a === b) return true;
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

export const useCascadePath = createStore<CascadePathState>((set) => ({
  path: [],
  setPath: (next) => {
    set((prev) => {
      if (arraysEqual(prev.path, next)) {
        // No-op — keep the reference stable so subscribers don't
        // refire on a redundant setPath call.
        return prev;
      }
      return { path: next };
    });
  },
}));