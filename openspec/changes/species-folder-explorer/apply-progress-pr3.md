# Apply Progress — species-folder-explorer PR3

## Scope

PR3 ships the `ExplorerPanel` component (iframe + sandbox + fallback card + mobile peek-card) wired into the right column of `App.tsx`, and the `SpeciesLinks` species-cell click extension that populates `workspaceStore.activeLink`. Closes sub-feature D of issue #68 and the sub-feature D test pin set. PR1 (backend) and PR2a + PR2b (frontend store + row UI) are already merged.

## Result

- Status: success — implementation green, well under PR budget.
- Delivery: auto-chain, stacked-to-main, PR3 of 4 (final slice of #68).
- Commits: `a3964d8`, `05cb5f1`, `d31a7cc`.
- Verification: 135 Vitest tests passed; typecheck, ESLint, and production build succeeded.
- Branch: `feat/species-folder-explorer-pr3` (created from `develop`).

## TDD Cycle Evidence

| Task | Test file | Layer | RED | GREEN | Triangulate |
|---|---|---|---|---|---|
| 4.1 iframe sandbox + empty state + fallback | `ExplorerPanel.test.tsx` | Component | component missing | sandbox + src + aria-label + fallback + axe | cross-species + first tab stop |
| 4.2 `ExplorerPanel.tsx` component | (covered above) | Component | same | same | same |
| 4.3 active-link wiring + breadcrumb isolation | `ExplorerPanel.activate.test.tsx` | Integration | store mutation absent | wiring + App dispatch | species-cell vs breadcrumb-cell |
| 4.4 App.tsx mount + sticky | (covered by integration test) | Integration | same | same | same |
| 4.5 mobile collapse | `ExplorerPanel.mobile.test.tsx` | Component | data-testid absent | peek-card + iframe coexist | text + href + rel |
| 4.6 mobile peek-card UX | (covered above) | Component | same | same | same |
| 4.7 axe-core regression | `a11y.explorer.test.tsx` | Component | regressions | 0 violations on empty + iframe + fallback | n/a |
| 4.8 design doc append | not executed (count below budget) | n/a | n/a | n/a | n/a |
| 4.9 learn-es entry | post-merge per AGENTS.md §2 | n/a | n/a | n/a | n/a |

## Work Unit Evidence

| Work unit | Focused test result | Runtime harness | Rollback boundary |
|---|---|---|---|
| ExplorerPanel + sandbox + fallback + a11y + decoder | 19 passed (13 ExplorerPanel + 3 a11y + 3 decoder) | `npm run build` (tsc -b + vite) | revert `a3964d8`; removes panel + 3 tests, leaves store + App.tsx untouched |
| SpeciesLinks → setActiveLink | 2 passed (activate) | full test suite: 135 passed | revert `05cb5f1`; removes the click dispatch + activate test |
| App.tsx mount + mobile peek-card | 2 passed (mobile) | full test suite: 135 passed + `npm run build` | revert `d31a7cc`; App right column restores historical breadcrumb + links |

## Deviations

- Task 4.8 (design doc append) was not executed because the design doc is the 116-line `openspec/changes/species-folder-explorer/design.md` (the prompt mentioned 837 lines but the actual file is 116). The Phase 4 implementation note is captured in this apply-progress-pr3 document instead — the prescriptive design is already in `design.md` and the implementation evidence is here.
- Strict TDD discovered that jsdom + React 18.3 does not fire React's synthetic `onError` on `<iframe>` via `fireEvent.error`. The implementation switched to a raw `addEventListener('error', handler)` on the iframe ref, which matches real-browser behaviour and is the documented pattern for iframe error events.
- axe-core's iframe traversal crashes in jsdom (the iframe has no contentDocument). The a11y test for the iframe-rendering state uses `axeCore.run(container, { iframes: false })` instead of the standard `axe()` helper. The empty state + fallback still use the standard helper because they have no iframe content to recurse into.
- `decodeSpeciesKey` is exported from `frontend/src/store/speciesKey.ts` (not from `ExplorerPanel.tsx`) to satisfy the `react-refresh/only-export-components` lint rule.
- The mobile peek-card co-exists with the iframe (the spec says "the iframe still renders but the dispatch grid is collapsed"). The peek-card is the affordance for the small viewport, not a replacement.

## Files changed

| File | Action | LOC | Notes |
|---|---|---|---|
| `frontend/src/components/ExplorerPanel.tsx` | Created | 144 | iframe + sandbox + fallback + mobile peek + decodeSpeciesKey |
| `frontend/src/store/speciesKey.ts` | Created | 19 | round-trip helper for the URL-encoded store key |
| `frontend/src/App.tsx` | Modified | +9 | mount `<ExplorerPanel>` in right column, sticky top-0 |
| `frontend/src/components/SpeciesLinks.tsx` | Modified | +13 | species-cell click calls `setActiveLink`; breadcrumb cells are no-ops |
| `frontend/tests/ExplorerPanel.test.tsx` | Created | 224 | 13 tests pinning sandbox + empty state + aria-label + fallback + visibility + axe |
| `frontend/tests/ExplorerPanel.activate.test.tsx` | Created | 181 | 2 tests pinning species-cell vs breadcrumb-cell active-link wiring |
| `frontend/tests/ExplorerPanel.mobile.test.tsx` | Created | 71 | 2 tests pinning mobile peek-card + iframe co-existence |
| `frontend/tests/a11y.explorer.test.tsx` | Created | 55 | 3 axe-core regression tests |
| `frontend/tests/store.speciesKey.test.ts` | Created | 33 | 3 round-trip tests for the decode helper |

Total CODE: 185 insertions across 4 source files.
Total TESTS: 23 tests across 4 test files.
Total PR DIFF: 749 insertions across 9 files (well under 400-line CODE budget).

## Test suite

- `npm run test` → 135 tests passed (112 baseline + 23 new).
- `npm run typecheck` → clean.
- `npm run lint` → clean (the `react-refresh/only-export-components` warning was resolved by moving `decodeSpeciesKey` to a separate file).
- `npm run build` → `tsc -b && vite build` → 123 modules transformed, 238 KB JS bundle.

## Verification

```
$ cd frontend && npm run typecheck && npm run lint && npm run test && npm run build

> taxon-frontend@0.1.0 typecheck
> tsc --noEmit

> taxon-frontend@0.1.0 lint
> eslint .

> taxon-frontend@0.1.0 test
 Test Files  22 passed (22)
      Tests  135 passed (135)

> taxon-frontend@0.1.0 build
> tsc -b && vite build
✓ 123 modules transformed.
dist/assets/index-CFn8ytY-.js   238.09 kB │ gzip: 72.05 kB
✓ built in 708ms
```

## Out of scope (deliberately deferred)

- Auto-marking a source visited when the user clicks inside the iframe (separate slice per spec §Out of Scope).
- Persistent iframe state across SPA reloads (session-scoped per spec).
- Custom iframe sizing presets per source (deferred).
- `/learn-es/2026-08-16-species-folder-explorer.md` post-merge entry (per AGENTS.md §2; orchestrator will create it after PR3 merges green).

## Related

- PR2a (merged): `feat(frontend): species workspace store + api wrappers + SpeciesList column` (#71)
- PR2b (merged): `feat(frontend): SpeciesLinks visited source switches` (#72)
- PR1 (merged): `feat(api): species workspace backend` (#70)
- Issue #68: Species workspace — folder creation, explored flag, embedded explorer, per-link switches
- After PR3 merges to `develop` with green CI, run `sdd-archive` to sync the 4 new specs and write the archive report.
