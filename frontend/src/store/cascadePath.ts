/** Zustand store for the cascade path.

The breadcrumb (``Breadcrumb.tsx``) writes the picked path through
``setPath``; the App's panel effect reads it via the Zustand
subscriber. The path is the only mid-cascade state the App needs
to render the breadcrumb-links panel before the user has resolved
a species.

We use Zustand's react flavour (``create``) which produces a typed
hook that doubles as the vanilla store API (``useCascadePath.getState``
and ``useCascadePath.subscribe``). That keeps a single source of
truth that both React components (``useCascadePath((s) => s.path)``)
and the Cascade's reducer consumer (which reads via ``getState``)
can use. The path rarely changes; the ``setPath`` reducer skips
no-op replaces so a redundant call does not refire subscribers.
*/

import { create } from "zustand";

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

export const useCascadePath = create<CascadePathState>((set) => ({
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