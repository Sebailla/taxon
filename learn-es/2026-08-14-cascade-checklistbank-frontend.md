# Cascade frontend wires to ChecklistBank (PR #42)

## What

The React `Cascade` now drives the ChecklistBank `COL2024` backend
through the path-aware `/api/path-children` endpoint the cascade-checklistbank
chain exposed. The first dropdown surfaces Biota + Viruses (the two
top-tier taxa CLB publishes), and each subsequent picker advances the
path one cascade tier with a capitalised label inferred from the
backend's `next_rank_hint`.

The same PR fixes the upstream resolver bug that crashed every path
starting with `["Biota"]`: the resolver now shortcuts the root tier
through `get_taxon("5T6MX")` / `get_taxon("V")` because CLB's
`/nameusage/search` returns HTTP 400 when filtered with `rank=biota`.

## Why

PRs #34 / #36 / #37 / #38 / #40 landed the CLB client, the path resolver
with the subphylum collapse rule, and the router swap. The frontend was
the last slice of the chain and it had been gated until the backend
landed. While reviewing the slice the smoke test revealed that the
resolved chain was broken at the root: any `?path=Biota` request
exploded with `HTTPStatusError 400` because the resolver tried to
search CLB with `rank=biota`, which CLB does not support. The whole
cascade UI was dead-on-arrival against the new backend.

Merging the in-flight `feat/cascade-checklistbank-router` branch first
gave us a known-good backend (179/179 pytest) on which to reproduce,
fix, and verify the wiring.

## How

### Backend root-tier shortcut (`taxon/api/clb_path_children.py`)

The walk used to start every path with `client.search(segment,
rank="biota")`. CLB rejects that with HTTP 400 because the root tier
is not searchable on its own. The new `_resolve_deepest` walks the
first segment against `_ROOT_TAXON_BY_NAME` (a two-entry dict mapping
`"biota"` and `"viruses"` to the well-known CLB ids `"5T6MX"` and
`"V"`), calls `client.get_taxon(root_id)` directly, and then advances
to the standard rank-anchored search for the remaining segments.

```python
_ROOT_TAXON_BY_NAME: dict[str, str] = {
    "biota": "5T6MX",
    "viruses": "V",
}

if root_id := _ROOT_TAXON_BY_NAME.get(segments[0].lower()):
    current = client.get_taxon(root_id)
    ...
```

CLB publishes the root tier under `rank="unranked"`, not
`rank="biota"`. The next-tier mapper `_next_tier_for` used to do a
flat dict lookup against `CASCADE_TIERS`. With the new shortcut
returning `unranked` rank rows, the lookup missed. Fix:

```python
def _normalize_root_rank(rank: str) -> str:
    if rank.lower() == "unranked":
        return "biota"
    return rank
```

`_next_tier_for` calls it before the lookup so a single
keyspace spans the tuple.

### Backend tests (`taxon/tests/test_clb_path_children.py`)

`test_root_path_returns_biota_children` was rewritten: instead of
mocking `/nameusage/search?q=Biota&rank=biota` (which CLB would
reject in production), the test now mocks `/nameusage/5T6MX` with a
flat-then-nested row payload and verifies the resolver walks through
`get_taxon` to the seven kingdoms via `/tree/5T6MX/children?rank=kingdom`.

`test_root_path_returns_viruses_children` is new and mirrors the
Biota test against the Viruses root. Both tests use a new
`_get_taxon_200` helper that emits the nested `name.scientificName`
+ `name.rank` shape CLB's `GET /nameusage/{id}` returns (the
flat-then-nested shape pattern is also what the parser handles).

### Frontend wiring (`frontend/src/api.ts`, `frontend/src/components/Cascade.tsx`)

`api.ts` now exposes `fetchRoots()` with `fetchKingdoms` kept as a
deprecated alias. The endpoint URL did not change; the rename makes
the contract honest ("CLB returns cascade roots — the cascade UI does
the bucketing") and protects callers from misreading
`TaxonResponse[]` as kingdom-rank rows.

`Cascade.tsx` renders one dropdown per path segment in a single loop,
plus one trailing slot for the deepest `next_rank_hint`. The loop
keying is `parentPrefix = state.path.slice(0, i)` and the picker at
index `i` shows the children of `state.levelByPath[parentKey]`. The
biota root tier becomes "Biota" with the two CLB-root rows; the
trailing slot is capitalised from `next_rank_hint` so the dropdown
labels stay stable across the 9-tier tuple (`"phylum" → "Phylum"`,
`"subphylum" → "Subphylum"`).

### Frontend tests

`cascadeRoots.test.tsx` and `cascadeSubphylum.test.tsx` are new and
cover the two contract additions (root tier rendering and the
`next_rank_hint` → capitalised label flow). `api.test.ts` gained a
`fetchRoots` happy-path test plus a deprecated-alias test.

The `.legacy` files on the previous PR had been renamed to keep them
out of the runner after the GBIF→CLB migration broke their fixed-rank
assumptions. The two that still carried signal
(`Cascade.pathAware.test.tsx`, `Cascade.ui.test.tsx`) were resurrected
with the Biota root + 9-tier tuple. `CascadeFocus.test.tsx.legacy` was
pure bookkeeping and got deleted.

## Where

- `taxon/api/clb_path_children.py` — root-tier shortcut, `_normalize_root_rank`.
- `taxon/tests/test_clb_path_children.py` — updated Biota test, new Viruses test, new `_get_taxon_200` helper.
- `frontend/src/api.ts` — `fetchRoots` + `fetchKingdoms` alias + module-level docstring documenting the chain.
- `frontend/src/components/Cascade.tsx` — N+1 dropdown render loop, `capitalize` helper.
- `frontend/tests/cascadeRoots.test.tsx` — new.
- `frontend/tests/cascadeSubphylum.test.tsx` — new.
- `frontend/tests/api.test.ts` — `fetchRoots` + alias tests.
- `frontend/tests/Cascade.pathAware.test.tsx` — restored from `.legacy`, updated for the Biota root tier.
- `frontend/tests/Cascade.ui.test.tsx` — restored from `.legacy`, updated for the Biota root tier.

## Verification

- Backend `pytest taxon/tests/` — 179/179 green.
- Frontend `vitest` — 61/61 green.
- `tsc --noEmit` clean.
- `eslint .` clean.
- `npm run build` clean.
- CI: 4/4 jobs green on the PR (backend 3.11, backend 3.12, frontend node 20, lighthouse a11y).
- Manual Playwright smoke test against the live dev server:
  - Biota → Animalia loads 34 phyla (vs 4 under GBIF).
  - Animalia → Chordata loads three Chordata classes
    (Cephalochordata, Tunicata, Vertebrata).

## Workflows

- **Branching**: PR #42 followed `develop` as integration base per AGENTS.md §4. Worktree path `../taxon-worktrees/cascade-checklistbank-frontend`.
- **Commit shape**: single `feat(cascade): wire frontend to ChecklistBank cascade backend` commit (one merge commit + the merge of `feat/cascade-checklistbank-router` to bring the backend in). Per `work-unit-commits`, the work unit covers one reviewer-loadable slice: the bug fix and the wiring travel together because the wiring could not survive without the bug fix.
- **TDD**: backend fix followed strict TDD — failing `test_root_path_returns_biota_children` first, impl in `_resolve_deepest`, green. Same shape for Viruses.

## Lessons learned

- **CLB does not search the root tier.** When the documented cascade
  tuple has a rank that is *de jure* part of the dataset but
  *de facto* outside the search index, the resolver must know about
  it through a hard-coded id rather than through the same name-based
  walk the rest of the tree uses. The walk's generalisation ("search
  by name + rank-anchor") breaks at the root because CLB has not
  assigned the root tier a Linnaean rank; the cascade had to model
  that gap explicitly.
- **CLB's published rank labels do not match the cascade tier tuple.**
  The root tier is published as `rank="unranked"`, not
  `rank="biota"`. The resolver used to assume equality between the
  two. Centralising the rank normalisation into one helper
  (`_normalize_root_rank`) keeps the rest of the resolver's keyspace
  consistent — every other rank CLB returns maps cleanly to the
  cascade tuple.
- **Always run the smoke test against the live backend before opening the PR.** The unit tests for `test_root_path_returns_biota_children` had been green for months even though the production path `?path=Biota` was a 400. The mocks for the wrong (`search`-based) shape hid the bug. Manual smoke tests on real CLB are the only way to surface this kind of contract drift; the rule going forward: any change to the resolver needs a manual smoke test in the browser, even when unit tests are green.
- **The `.legacy` rename was a signal, not a deletion.** When renaming a test file to `.legacy` to keep its assertions from running against a new contract, the burden of resurrection falls on whoever touches the legacy code. Two of the three legacy files in this PR were still useful and got updated; the third was bookkeeping and was deleted.

## Follow-up PRs (not in this commit)

- **Issue #43** — the cascade 9-tier tuple does not name `infraphylum`
  or `parvphylum`, both of which CoL publishes between subphylum and
  class. The cascade dead-ends at Chordata → Vertebrata →
  Agnatha / Gnathostomata. Three approaches are listed in the
  issue; this PR fixes the upstream blocker (root-tier 400) and
  lands the frontend wiring but does not pick a side on the
  infraphylum problem.
- **Cleanup of artifacts in main checkout.** `pencil.pen`,
  `.playwright-mcp/`, `cascade-animalia-select.png`, and the
  auto-regenerated `.atl/skill-registry.md` were left behind when
  the worktree branch was created. Separate cleanup PR.
