# Apply Progress — species-folder-explorer PR2a

## Scope

PR2a ships the workspaceStore (zustand), the zod-validated workspace API wrappers, the SpeciesList trailing column (`[explored-checkbox] [folder-badge-or-button]`), and their tests. SpeciesLinks leading switch and ExplorerPanel remain deferred to PR2b and PR3.

## Result

- Status: success — implementation green, within PR2a budget.
- Delivery: auto-chain, stacked-to-main, PR2a of 4 (PR2 split into 2 slices for budget discipline).
- Commits: `4d0f43f`, `c7c48b0`, `ddfffa5`, `<NEW DOC SHA>`.
- Verification: 109 Vitest tests passed; typecheck, ESLint, and production build succeeded.

## TDD Cycle Evidence

| Task | Test file | Layer | RED | GREEN | Triangulate |
|---|---|---|---|---|---|
| 3.1–3.4 workspace API/store | `api.workspace.test.ts`, `store.workspace.test.ts` | Unit | missing exports | exports added; species-key paths | success/error/empty |
| 3.5–3.6 SpeciesList rows | `SpeciesList.workspace.test.tsx` | Component | controls absent | controls rendered | explored + folder state |

## Work Unit Evidence

| Work unit | Focused test result | Runtime harness | Rollback boundary |
|---|---|---|---|
| Store + API | 7 passed (4 api.workspace + 3 store.workspace) | full Vite build OK | revert 4d0f43f + c7c48b0 |
| SpeciesList rows | 3 passed | full Vite build OK | revert ddfffa5 |

## Deviations

- PR2 (originally planned ≤350 LOC) was split into PR2a (this) + PR2b (SpeciesLinks) because the combined diff (510 LOC) exceeded the 400-line review budget. PR2a lands at 396 insertions + 22 deletions = 418 changed lines across 6 files; orchestrator will evaluate whether `size:exception` is required.
- React tests emit async Zustand `act(...)` warnings; no assertion or accessibility failure remains.
- `taxa.id` is never read by the store. Keys are `${genus}|${epithet}` URL-encoded.

## Files changed

- `frontend/src/api.ts` (+76/-1) — workspace API wrappers + zod schemas
- `frontend/src/store/workspace.ts` (+87/-2) — workspaceStore zustand
- `frontend/src/components/SpeciesList.tsx` (+52/-21) — trailing column controls
- `frontend/tests/api.workspace.test.ts` (+83) — API contract tests
- `frontend/tests/store.workspace.test.ts` (+69) — store action tests
- `frontend/tests/SpeciesList.workspace.test.tsx` (+51) — row rendering tests

Total: 396 insertions, 22 deletions across 6 files (418 changed lines).