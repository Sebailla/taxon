# Apply Progress — species-folder-explorer PR2b

## Scope

PR2b ships the `SpeciesLinks` leading switch that consumes `workspaceStore.visitedLinks` and styles visited sources with `border-muted text-slate line-through`. App.tsx is updated to pass species identity into `SpeciesLinks`. PR2a (store + api + SpeciesList trailing column) is already merged via PR #71. ExplorerPanel remains deferred to PR3.

## Result

- Status: success — implementation green, well under PR budget.
- Delivery: auto-chain, stacked-to-main, PR2b of 4 (PR2 split into 2 slices for budget discipline).
- Commits: `e1d5b2b` (cherry-picked as `4297214`).
- Verification: 112 Vitest tests passed; typecheck, ESLint, and production build succeeded.

## TDD Cycle Evidence

| Task | Test file | Layer | RED | GREEN | Triangulate |
|---|---|---|---|---|---|
| SpeciesLinks visited switch | `SpeciesLinks.visited.test.tsx` | Component | switch absent and axe exposed invalid listitem role | switch rendered with visited styling | mark/unmark and cross-species isolation |

## Work Unit Evidence

| Work unit | Focused test result | Runtime harness | Rollback boundary |
|---|---|---|---|
| SpeciesLinks switches | 3 passed | full Vite build OK | revert `4297214`; restores historical link cells |

## Deviations

- PR2 (originally planned ≤350 LOC) was 510 LOC end-to-end; split into PR2a (418 LOC code / 504 LOC with docs, merged via PR #71) + PR2b (76 LOC code, this PR).
- `App.tsx` passes species identity into `SpeciesLinks` but does NOT mount `ExplorerPanel` — that remains PR3's responsibility.
- The store uses URL-encoded `${genus}|${epithet}` keys and never reads `taxa.id` (re-bind discipline pinned by PR1).
- React tests emit async Zustand `act(...)` warnings; no assertion or accessibility failure remains.

## Files changed

- `frontend/src/components/SpeciesLinks.tsx` (+42/-18) — leading visited switch with `border-muted text-slate line-through` styling when visited
- `frontend/src/App.tsx` (+1/-1) — passes species identity into `SpeciesLinks`
- `frontend/tests/SpeciesLinks.visited.test.tsx` (+50) — visited switch + axe-core assertions

Total: 76 insertions, 18 deletions across 3 files.

## Related

- PR #71 (PR2a, merged): `feat(frontend): species workspace store + api wrappers + SpeciesList column`
- PR #70 (PR1, merged): `feat(api): species workspace backend`
- Issue #68: Species workspace — folder creation, explored flag, embedded explorer, per-link switches
- PR3 (pending): ExplorerPanel with iframe + sandbox + fallback card + design doc + learn-es entry
