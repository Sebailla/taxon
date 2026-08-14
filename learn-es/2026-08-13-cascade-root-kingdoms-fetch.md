# Cascade root fetches /api/kingdoms (PR #30)

## What

The Cascade component's mount effect now routes the root fetch (`state.path.length === 0`) through `fetchKingdoms` (`/api/kingdoms`) instead of `fetchPathChildren` (`/api/path-children?path=`). The rest of the chain still uses `fetchPathChildren` per segment.

## Why

The path-aware refactor (PR #29) shipped with `fetchPathChildren([])` as the root fetch. The backend's `/api/path-children` endpoint has a `min_length=1` constraint on the `path` query parameter — FastAPI returns a 422 when the path is empty. The root fetch always failed with 422, the reducer never received a snapshot, and the Kingdom dropdown stayed in the disabled "Loading children…" placeholder forever.

This was a latent bug — the unit tests mocked the fetch so the network failure was never exercised. The manual smoke test against the live dev server (after PR #29 landed) caught it immediately: the Kingdom dropdown rendered with no options because the network call was rejected.

## How

The fix lives in `Cascade.tsx`'s first `useEffect`. The fetcher is now conditional on `state.path.length`:

```ts
if (state.path.length === 0) {
  void fetchKingdoms({ signal: ctrl.signal }).then(...)
} else {
  void fetchPathChildren(densePath(state.path), { signal: ctrl.signal }).then(...)
}
```

Both branches share the same `onSuccess` (cache the snapshot under the path key) and `onError` (dispatch `set-current-level-status: error`) callbacks. The two fetcher signatures differ (`fetchKingdoms(init)` vs `fetchPathChildren(segments, init)`), so the split is the cleanest way to keep both call sites type-safe without a discriminator or cast.

The root snapshot also needs a `nextRankHint` of `"kingdom"` so the cascade knows what label to put on the next dropdown after the user picks a kingdom. The backend's `/api/kingdoms` returns a plain `TaxonResponse[]` (no envelope), so the effect constructs the snapshot manually:

```ts
onSuccess(result.data, "kingdom");  // nextRankHint = "kingdom"
```

For non-root segments, the snapshot comes straight from the path-children envelope:

```ts
onSuccess(result.data.children, result.data.next_rank_hint);
```

### Test fixtures

The test suites in `Cascade.pathAware.test.tsx` and `Cascade.ui.test.tsx` were updated to mock `/api/kingdoms` for the root fetch (returning a `TaxonResponse[]` array) and `/api/path-children` for the rest of the chain. The `mockFetchSequence` helper now accepts a tuple form `[urlMatcher, response]` so the root dispatch can match `/api/kingdoms` precisely and the rest of the chain can keep mocking by firing order:

```ts
mockFetchSequence([
  // /api/kingdoms — root kingdom list.
  ["/api/kingdoms", mockFetchJson([taxon(2, "Animalia", "kingdom")])],
  // /path-children?path=Animalia
  mockFetchJson({ parent: ..., children: [...], next_rank_hint: "phylum" }),
  // ...
]);
```

The bare-response form is kept for back-compat; the tuple form is opt-in per call site.

## Where

- `frontend/src/components/Cascade.tsx` — 56 lines changed (split the fetch into two branches, share success/error callbacks).
- `frontend/tests/Cascade.pathAware.test.tsx` — 89 lines changed (mockFetchSequence grew the tuple form, plus 4 test bodies updated to mock `/api/kingdoms` for the root).
- `frontend/tests/Cascade.ui.test.tsx` — 26 lines changed (2 test bodies updated).
- `.gitignore` — 1 line added (`frontend/pnpm-lock.yaml`). The project uses npm (`package-lock.json`) and pnpm creates the lockfile as a side effect of `pnpm install`.

## Verification

- 55/55 vitest tests pass.
- TypeScript clean (`tsc --noEmit`).
- ESLint clean.
- Manual smoke test against the live dev server: the Kingdom dropdown now lists all 23 CoL kingdoms (Animalia, Plantae, Fungi, Chromista, Protozoa, plus the virus realms Abadenavirae, Sangervirae, Trapavirae, etc.). Selection drives the next `/path-children` call as expected.

## Workflows

- **CI** — 4 jobs green: backend (3.11, 3.12), frontend (node 20), lighthouse.
- **Reviews** — single `fix` commit, no need for a chained PR.

## Lessons learned

- **The path-aware endpoint's `min_length=1` was a contract assumption that broke the root fetch.** The backend rejected the empty path with a 422 because the resolver has nothing to anchor on. The frontend's path-aware refactor silently consumed that 422 as a generic "not ok" and left the dropdown in the loading state. The fix is to use the dedicated `/api/kingdoms` endpoint for the root, which doesn't have this constraint.

- **Unit tests with mocked fetch can hide contract violations.** The mocks always return whatever the test wants, so 422s, 404s, and network failures are never exercised. Manual smoke tests against the live dev server are the only way to catch these. The rule going forward: any change that touches a fetcher needs a manual smoke test in the browser, even when the unit tests pass.

- **Two fetcher signatures are a clean split.** The root fetcher (`fetchKingdoms(init)`) and the path-aware fetcher (`fetchPathChildren(segments, init)`) have different signatures. Trying to unify them with a single conditional would require either a discriminated union or a type cast. The split is honest: two branches in the effect, two `if`s, no casts. The shared `onSuccess`/`onError` callbacks keep the dispatch logic DRY.

- **The `nextRankHint` is what the UI uses to label the next dropdown.** The root snapshot needs `nextRankHint = "kingdom"` so the cascade knows what label to put on the next dropdown after the user picks a kingdom. The backend's `/api/kingdoms` returns a plain `TaxonResponse[]` (no envelope), so the effect has to construct the snapshot manually. The non-root fetcher returns the envelope, so the snapshot comes straight from the response.

- **`pnpm install` creates a `pnpm-lock.yaml` even when the project uses npm.** The repo uses `package-lock.json` for reproducible installs. Running `pnpm install` (which pnpm prefers by default in some agents) creates a `pnpm-lock.yaml` as a side effect. Adding it to `.gitignore` keeps the repo clean of the wrong lockfile.

## Follow-up PRs (not in this commit)

- **PR #27d** — replace the dropdown pattern with an autocomplete picker for ranks with thousands of children (CoL's kingdom-level children are mostly species/unranked rows, so the dropdown is unmanageable). The current implementation renders one dropdown per ancestor plus the `next` picker; an autocomplete would collapse the UX for shallow chains.
- **Backend cleanup** — the `/api/kingdoms` endpoint is now the only one used by the frontend's root fetch. The deferral of the legacy six rank-named endpoints (PR #27c) is still pending; once the frontend stops hitting them, they can be removed.
