# Phase 4 — Frontend implementation

## What

Implemented the React + Vite + TailwindCSS frontend that consumes
the API endpoints shipped in Sub-PRs 2A/2B/2C. The cascade UI
follows the Phase 3 design (`taxon.pen`) and resolves the two
follow-ups from the impeccable audit.

## How

- Scaffolded `frontend/` with Vite 5 + React 18 + TypeScript 5 in
  strict mode + TailwindCSS 3 + Vitest 2 + Testing Library +
  ESLint flat config.
- Typed API client (`api.ts`) wraps the seven endpoints. Every
  request resolves into a discriminated union (`Ok | NotFound |
  Ambiguous | Error`) so React components branch explicitly on
  status, never on exceptions.
- The Cascade is a pure `useReducer` state machine. The reducer
  enforces "reset every child when a parent changes" so the UI
  never has to track staleness manually. In-flight requests are
  aborted via `AbortController`; `apiGet` swallows the abort so
  the component does not need a try/catch.
- Inclusion toggles (`Toggles.tsx`) are real `<button>` elements
  with `aria-pressed`. Species list handles loading / error /
  empty states. Species links panel uses
  `<a target="_blank" rel="noopener noreferrer">`. Ambiguity
  picker is a modal with backdrop close + Escape close.
- App listens for the `taxon:select` custom event dispatched by
  SpeciesList; the event carries the breadcrumb and the parent
  segments so App can trigger the links fetch without a second
  round-trip.
- Design tokens from the audit (`accent`, `amber`, `bg`, `border`,
  `muted`, `navy`, `red`, `slate`, `surface`) live in
  `tailwind.config.js`. Badge backgrounds use `red-50`,
  `amber-50`, `green-50`, `blue-50` so the 10 hard-coded hex
  values from the design are gone.

## Where

- `frontend/package.json` — Vite + React 18 + TypeScript 5 + Vitest
  + TailwindCSS 3.
- `frontend/vite.config.ts` — dev server with `/api` proxy to
  `http://127.0.0.1:8000`.
- `frontend/vitest.config.ts` — JSDOM environment for component
  tests.
- `frontend/tailwind.config.js` — design tokens + red-50 /
  amber-50 / green-50 / blue-50 for marker badges.
- `frontend/src/index.css` — global focus ring via `:focus-visible`,
  body uses `system-ui, Inter, sans-serif` (system wins first).
- `frontend/src/api.ts` — typed client + `encodeSegments` (full
  percent-encoding incl. parens) + `splitSpeciesName` +
  `buildBreadcrumb` (drops Biota superdomain).
- `frontend/src/App.tsx` — root composition, event listener for
  `taxon:select`.
- `frontend/src/components/Cascade.tsx` — state machine + dropdowns.
- `frontend/src/components/Toggles.tsx` — 4 inclusion chips.
- `frontend/src/components/SpeciesList.tsx` — scrollable list with
  marker badges.
- `frontend/src/components/SpeciesLinks.tsx` — 12-button grid.
- `frontend/src/components/AmbiguityPicker.tsx` — modal.
- `frontend/src/components/Breadcrumb.tsx` — chevron-separated
  breadcrumb.
- `frontend/tests/api.test.ts` — 19 client tests.
- `frontend/tests/Cascade.test.tsx` — 9 component tests.

## Why

Phase 4 closes the implementation loop opened by Sub-PRs 2A/2B/2C
on the backend and Phase 3 on the design. Without the React
frontend, the cascade endpoints are reachable only via curl — the
taxon project is a read-only web dispatcher, so the frontend is
the user-facing surface.

The P2 follow-up (badge colors as Tailwind tokens) and P3
follow-up (system-ui fallback in the font stack) from the Phase 3
audit both land in this slice.

## How it works

1. App mounts; Cascade mounts. Cascade fires `fetchKingdoms()` on
   mount and stores the result in the reducer via
   `set-children`.
2. The user picks a Kingdom from the first dropdown. The reducer
   stores the selection and resets every child segment
   (`phylum`, `class`, `order`, `family`, `genus`). The effect
   for "load children" fires next and calls
   `fetchChildren(["Animalia"], "phyla")`.
3. The user walks down the cascade. Each selection triggers the
   next fetch. The previous request is aborted via
   `AbortController.abort()` on effect cleanup.
4. When a genus is selected, a separate effect fires
   `fetchSpecies(parentSegments, { include })` with the toggles
   forwarded as the CSV query param.
5. Clicking a species row dispatches a `taxon:select` custom
   event. App catches it, stores the resolved species, then
   fires `fetchLinks(parentSegments, epithet)`.
6. The 12-link grid renders. Sci-hub is visually separated with a
   red border. Every link opens in a new tab with
   `rel="noopener noreferrer"`.
7. If `fetchSpeciesByPair` returns 409, the modal appears with the
   candidate breadcrumbs. Clicking a candidate updates the
   resolved species and dismisses the modal.

## Workflows

- Dev server: `cd frontend && npm run dev` (port 5173, /api proxy
  to :8000).
- Tests: `npm test` (Vitest, 28 tests).
- Typecheck: `npx tsc --noEmit`.
- Build: `npm run build` (154 KB JS / 49 KB gzip).

## Acceptance evidence

| Evidence | Value |
| --- | --- |
| PR | https://github.com/Sebailla/taxon/pull/12 (squash-merged) |
| Issue | https://github.com/Sebailla/taxon/issues/11 (auto-closed) |
| Branch | `feat/species-search-dispatcher-frontend-impl` (deleted) |
| Worktree | `../taxon-worktrees/pr4-impl` (cleaned up) |
| Files changed | 18 (scaffold + components + tests) |
| Tests added | 28 (19 client + 9 component) |
| Tests passing | 28/28 locally; CI green on Python 3.11 + 3.12 |
| Typecheck | strict mode clean |
| Production build | 154 KB JS / 49 KB gzip / 11 KB CSS / 3 KB gzip |

## Deviations

- **Custom event for species selection.** The SpeciesList dispatches
  `window.dispatchEvent(new CustomEvent('taxon:select', ...))`
  rather than calling a callback prop. The App owns the
  selection state and listens via `addEventListener`. This keeps
  SpeciesList purely presentational and makes the event flow
  testable in isolation. Trade-off: a small leak of global state
  to `window` is acceptable for a single SPA.

- **`encodeSegments` includes extra characters.** The taxon
  backend stores species canonical names as `<genus> <epithet>`
  with parens around author citations. `encodeURIComponent` leaves
  `()`, `!`, `*`, `'` un-encoded by default; the helper re-encodes
  them so the byte-for-byte match on the backend works. Tracked
  inline with a comment.

- **State machine has a `generation` counter.** The reducer bumps
  `generation` whenever a new fetch starts; the effect captures
  the current generation and ignores stale responses. This is
  defensive — the `AbortController` already cancels the previous
  request, but the generation guard protects against a race
  where two effects fire in quick succession.

- **Sci-hub visual separation.** The .pen design calls out
  Sci-hub as a "separate source" visually. The React component
  uses a red border on the Sci-hub button (`border-red`) so the
  category is visible without relying on color alone — the
  `label="Sci-hub"` text is also rendered.

## Next steps

Phase 5 (Documentation & Cleanup) is the only remaining slice:

- README + Spanish mirror.
- ESLint + Vitest on CI workflow.
- Post-merge final `/learn-es/` entry covering the whole change.