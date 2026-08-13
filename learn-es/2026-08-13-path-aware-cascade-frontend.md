# Path-aware cascade frontend (PR #29)

## What

Refactored the Cascade component from a six fixed-rank ladder (Kingdom → Phylum → Class → Order → Family → Genus → Species) to a dynamic N-dropdown render driven by the backend's path-aware endpoints (`/api/path-children` and `/api/species-list`).

The new component walks the user-selected path segment by segment. Each segment asks the backend for the children of the deepest resolved taxon, plus a `next_rank_hint` that labels the next dropdown. When `next_rank_hint` is `null` the cascade has reached a genus row and auto-loads the species list via `/api/species-list`.

## Why

After the CoL re-seed (PR #26) the backend exposed the path-aware endpoints (PR #27, PR #28) but the frontend still assumed the legacy six fixed-rank ladder. The cascade returned empty lists for every path with intermediate ranks (subphylum, infraphylum, gigaclass, parvphylum, ...).

The frontend needed to track an arbitrary number of ranks and let the backend label the dropdowns with whatever the data has, instead of hardcoding labels.

## How

### State machine — `frontend/src/components/Cascade.state.ts`

The reducer is extracted from the component so it can be tested in isolation. The state shape:

- `path: string[]` — dense list of canonical names the user has picked so far. Empty means "show the root kingdom dropdown".
- `levelByPath: Record<string, LevelSnapshot>` — snapshot per path prefix. Keys are `path.join("|")`. The first key is `""` (root kingdom list); each subsequent key extends the path by one segment. The cascade renders one dropdown per key in insertion order.
- `species: TaxonResponse[]` — loaded separately when the cascade reaches a genus (deepest snapshot has `next_rank_hint === null`).

The reducer:

- `set-path` — keep snapshots for prefixes that are still valid; drop everything strictly beyond the new path length. Insert a placeholder `{children: [], nextRankHint: undefined}` for the new deepest path so the dropdown can render a "Loading children…" placeholder while the fetch is in flight. Reset `speciesStatus` to "loading" so the SpeciesList below does not show a stale "No children." state.
- `set-current-level` — cache the fetched snapshot under its path key so ancestor dropdowns stay populated after a descendant pick.
- `set-current-level-status` — flip the async status to "error" when the last fetch returned a non-OK result.
- `set-include` — update the inclusion toggles (synonyms, extinct, uncertain, unassigned).
- `set-species` + `set-species-status` — populate the species list and clear the loading state.

### Component — `frontend/src/components/Cascade.tsx`

Two `useEffect`s drive the lifecycle:

1. **Path-children effect** — fires on every `state.path` change. Calls `fetchPathChildren(densePath(state.path))` and dispatches `set-current-level` with the response. Aborts in-flight requests when a new selection supersedes them (`AbortController` cleanup).
2. **Species-list effect** — fires on every `state.path`/`state.levelByPath`/`state.include` change. Returns early when the path is empty or the snapshot is missing. Returns early when `nextRankHint !== null` (not a leaf yet) or when the snapshot has no species children (the leaf is a non-genus taxon). Only when the deepest snapshot is a confirmed genus with species children does it call `fetchSpeciesList`.

The render produces N dropdowns:

- For the empty path, a single "Kingdom" dropdown.
- For a non-empty path, one dropdown per path segment (the dropdown at index `i` shows the children of the taxon at `path.slice(0, i)` — the snapshot under the previous prefix). After the loop, a `next` dropdown shows the children of the deepest resolved taxon so the user has a single, unambiguous way to extend the path.

Each dropdown carries a visible label and an `aria-label`. Disabled dropdowns carry `disabled` so screen readers announce the unavailability. The previous `disabled → enabled` focus behaviour (PR #18) is kept per the a11y audit followup.

### API client — `frontend/src/api.ts`

Two new helpers:

- `fetchPathChildren(parentSegments, init)` — calls `GET /api/path-children?path=<segments>` (segments joined with `|`, each URL-encoded). Resolves to `ApiResult<PathChildrenResponse>`.
- `fetchSpeciesList(pathSegments, init)` — calls `GET /api/species-list?path=<segments>` with optional `include` and `cursor` query params. Resolves to `ApiResult<SpeciesListResponse>`.

The legacy `encodeSegments` helper (used by the legacy six rank-named endpoints) is left untouched. The path-aware helpers use a separate `.join("|")` because the backend expects `|` as the segment separator in the URL query string.

## Where

- `frontend/src/components/Cascade.tsx` — rewrite, 320 lines.
- `frontend/src/components/Cascade.state.ts` — new, 175 lines. Pure reducer + helpers, no React imports, testable in isolation.
- `frontend/src/api.ts` — added `PathChildrenResponse` type, `fetchPathChildren`, `fetchSpeciesList`.
- `frontend/tests/Cascade.pathAware.test.tsx` — new, 309 lines, 4 tests: init render, chain through intermediate ranks, reach species after genus, reset children on parent change.
- `frontend/tests/Cascade.ui.test.tsx` — new, 231 lines, 3 tests: loading state per dropdown, empty children state, inclusion toggles land the species fetch.
- `frontend/tests/Cascade.test.tsx.legacy` — old six-rank specs, renamed.
- `frontend/tests/CascadeFocus.test.tsx.legacy` — old `/api/kingdoms` spec, renamed.

## Verification

- `npm test` (Vitest) — 55/55 passing.
- `npm run typecheck` (tsc --noEmit) — clean.
- `npm run lint` (eslint) — clean.
- `npm run build` (Vite production build) — succeeds.
- CI — 4 jobs green: backend 3.11, backend 3.12, frontend, lighthouse.

## Workflows

- **CI** — same 4-job workflow as before. No new jobs.
- **Reviews** — 2 `work-unit-commits`:
  1. `426c917 test(frontend): mark legacy six-rank cascade specs as historical` — renames the obsolete specs to `.legacy` so the test discovery skips them.
  2. `4b193d9 feat(frontend): wire cascade to the path-aware backend API` — the cascade refactor with RED-first tests included.
- **Manual smoke test** — the cascade UI now walks through CoL's intermediate ranks. The chain `Animalia → Chordata → subphylum Vertebrata → genus Gadus → species Gadus morhua` lands species in the SpeciesList with the inclusion toggles preserved.

## Lessons learned

- **Disabled select race condition.** Vitest's `findByRole("combobox", { name: "Kingdom" })` returns the *first* matching element, which is the disabled placeholder. The next `selectOptions` call then fails because the select is disabled. The fix is to wait for the option, not the combobox: `await screen.findByRole("option", { name: "Animalia" }); await user.selectOptions(screen.getByRole("combobox", { name: "Kingdom" }), "Animalia")`. The first call waits for the in-flight fetch to resolve; the second is a synchronous `getByRole` against the now-enabled select. This pattern was flaky in CI before the fix.

- **Deterministic mocks via `mockResolvedValueOnce` chains.** The previous test mocked the fetch function with a single `mockImplementation` that branched on URL. The branch order was fragile: a single reorder broke the suite. Replacing the `if` ladder with a `mockResolvedValueOnce` chain tied to the firing order (initial kingdom → Animalia → Chordata → subphylum → genus → species list) made the test deterministic and self-documenting.

- **State machine extracted leaves the component lean.** Moving the reducer to `Cascade.state.ts` cut the component from a single tangled file to a clean render + two useEffects. The reducer is now Vite-HMR-friendly (no React imports means `react-refresh` does not trip on it) and the path-aware logic is testable in isolation without a DOM.

- **The reducer does not see the response; the useEffect does.** The reducer is pure and synchronous. The `useEffect` is the one that fetches and dispatches. This separation kept the reducer simple and the test fixtures trivial — a test that exercises the reducer only needs to pass actions and assert on the resulting state.

- **The `next` dropdown is the picker, not a display.** The dropdown at index `i` shows the children of the taxon at `path.slice(0, i)` — i.e. the user can re-select the same segment to change the parent. The `next` dropdown is distinct: it shows the children of the deepest resolved taxon and is the affordance for extending the path. Mixing the two (i.e. reusing the loop's last dropdown as the picker) leads to a confusing UX where the user cannot tell which dropdown is "the next one".

## Follow-up PRs (not in this commit)

- **PR #27c** — deprecate the six legacy rank-named endpoints (`/api/{kingdom}/phyla`, `/api/{kingdom}/{phylum}/classes`, etc.) once the frontend migration is stable in production. Add a deprecation warning to the response, remove them after one release.
- **PR #27d** — replace the `next` dropdown with a "Continue" picker that opens an autocomplete list of the next segment. The current implementation renders one dropdown per ancestor plus the `next` picker; a coalesced autocomplete would shrink the UI for very deep chains.
