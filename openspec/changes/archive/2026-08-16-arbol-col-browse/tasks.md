# Tasks: arbol-col-browse

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | Backend ~300 LOC + Frontend ~400 LOC + Pencil design ~50 LOC (outside budget) |
| 400-line budget risk | Medium (combined scope); Low per individual PR |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (backend) → PR 2 (Pencil + impeccable) → PR 3 (frontend) |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Backend tree endpoints + schemas + recursive CTE + authorship split + lazy-null fallback | PR 1 (`feat(api): add tree browse endpoints`) | `pytest -v taxon/tests/test_api_router_tree.py` | `curl /api/tree/children?parent_id=5T6MX` after `python -m taxon.main` against `data/col.db` | Revert PR 1: endpoints removed, no consumer yet. |
| 2 | Pencil design + impeccable audit for `TaxonomicTree` in `taxon.pen` | PR 2 (`feat(design): taxonomic tree Pencil design + impeccable audit`) | `n/a (no code)` | `pencil screenshot` of the new tree page via Pencil MCP | Revert PR 2: `.pen` reverted, no consumer yet. |
| 3 | Frontend `TaxonomicTree.tsx` + Zustand store + replace `Cascade` in `App.tsx` + delete Cascade tests + Breadcrumb aria rename | PR 3 (`feat(frontend): taxonomic tree browse component`) | `npm run typecheck && npm test` | `npm run dev` against the live backend from PR 1, navigate Archaea → … → genus | Revert PR 3: Cascade restored in `App.tsx`, frontend reverts to broken-dropdown state. Backend PR 1 stays. |

## Phase 1: Backend tree endpoints (PR 1)

- [x] 1.1 RED — write `taxon/tests/test_api_router_tree.py` asserting `GET /api/tree/children?parent_id=5T6MX` returns 200 + 5 root rows (Archaea/Bacteria/Eukaryota/Viruses/?incertae sedis) with `has_children`, `species_count`, `authorship`; assert `GET /api/tree/search?q=Euk` returns ranked results.
- [x] 1.2 GREEN — add `TreeNodeResponse`, `TreeChildrenResponse`, `TreeSearchResponse`, `TreeSearchHit` to `taxon/api/schemas.py`; export from `__all__`.
- [x] 1.3 GREEN — add `list_tree_children(parent_id, include, limit, cursor)`, `search_taxon(q, limit, include_extinct)`, and `_split_authorship(name, display_name)` helpers to `taxon/api/tree.py`.
- [x] 1.4 GREEN — register `GET /api/tree/children` and `GET /api/tree/search` in `taxon/api/router.py` **before line 654** (the `{path:path}` catch-all shadowing comment); reuse `get_db`; use `Annotated[..., Query(...)]` for params.
- [x] 1.5 RED — add `test_species_count_lazy_null.py` asserting nodes with >100k direct children return `species_count=null`; benchmark the threshold against `data/col.db` and record the actual measured value in `openspec/changes/arbol-col-browse/design.md`.
- [x] 1.6 GREEN — implement the threshold check inside `list_tree_children`.
- [x] 1.7 RED — add `test_search_ranking.py` asserting exact > prefix > substring with `display_name` length tie-break.
- [x] 1.8 GREEN — implement the ranking inside `search_taxon`.
- [x] 1.9 RED — add `test_tree_endpoints_route_order.py` (route registration order) asserting `/api/tree/children` and `/api/tree/search` register BEFORE `/{path:path}/taxon-links` catch-all.
- [x] 1.10 REFACTOR — extract the recursive CTE for `species_count` into a private helper; ensure `pytest` + `pytest-cov` stay green; commit.

## Phase 2: Pencil design + impeccable (PR 2, design-only)

- [x] 2.1 [DEFERRED] Pencil design was not executed because Pencil MCP was disabled in this session; the prescriptive surface brief was captured as `docs/design/taxonomic-tree-browse.md` instead (784 lines, line-by-line translation spec for the implementer). A follow-up issue may redo the Pencil `.pen` page in a future slice.
- [x] 2.2 [DEFERRED] Same rationale as 2.1; no Pencil page to audit.
- [x] 2.3 [DEFERRED] Same rationale as 2.1.
- [x] 2.4 [DEFERRED] Same rationale as 2.1.

## Phase 3: Frontend TaxonomicTree (PR 3)

- [x] 3.1 RED — `frontend/tests/api.treeChildren.test.ts` exists (15 tests, merged in PR #69).
- [x] 3.2 GREEN — `fetchTreeNode`, `fetchTreeSearch` in `frontend/src/api.ts` (merged in PR #69).
- [x] 3.3 RED — `frontend/tests/api.treeSearch.test.ts` exists (5 tests, merged in PR #69).
- [x] 3.4 GREEN — `createDebouncedSearch` in `frontend/src/api.ts` (merged in PR #69).
- [x] 3.5 RED — `frontend/tests/TaxonomicTree.test.tsx` exists (11 tests including the drift-fix scenarios, merged in PR #69).
- [x] 3.6 GREEN — `frontend/src/store/taxonomicTree.ts` exists with `loadRoots`, `ensureChildren`, `toggleExpand`, `revealNode`, `setIncludeExtinct` (merged in PR #69).
- [x] 3.7 GREEN — `frontend/src/components/TaxonomicTree.tsx` exists (618 LOC, merged in PR #69).
- [x] 3.8 GREEN — `frontend/src/App.tsx` mounts `<TaxonomicTree>` in the Cascade slot (merged in PR #69).
- [x] 3.9 GREEN — `Breadcrumb.tsx` aria-label kept verbatim as `Cascade path breadcrumb` (merged in PR #69).
- [x] 3.10 REFACTOR — `Cascade.tsx` + `Cascade.state.ts` + 6 cascade test files deleted (merged in PR #69).
- [x] 3.11 GREEN — `frontend/tests/App.taxonLinks.test.tsx` updated (2 tests, merged in PR #69).
- [x] 3.12 RED — `frontend/tests/TaxonomicTree.a11y.test.tsx` exists (1 axe-core test, merged in PR #69).
- [x] 3.13 GREEN — a11y fixes shipped: `aria-activedescendant` on search comb, skeletons `role="treeitem"`, empty + error hoisted out of `role="tree"` host (merged in PR #69).
- [x] 3.14 Post-merge — `learn-es/2026-08-16-arbol-col-browse-pr3-drift-fixes.md` exists with Spanish mirror (committed in `69d00e2`).

---

## Reconciliation Note

Reconciled by `sdd-archive` at close: Phase 1 + Phase 3 implemented in PR #69 (merged `3fc2eb1`). Phase 2 deferred (Pencil MCP disabled in session; prescriptive design captured as `docs/design/taxonomic-tree-browse.md` instead). Reconciliation authorized by user per the sdd-archive skill's stale-checkbox exception, backed by repository evidence: backend tree endpoints + schemas merged in PR #69, frontend `TaxonomicTree.tsx` (618 LOC) + `taxonomicTree.ts` store + 5 test files merged in PR #69, `Breadcrumb.tsx` aria-label verbatim at line 26, Cascade files absent in `frontend/src/components/` and `frontend/tests/`, learn-es entry committed in `69d00e2`.

## Threat Matrix → RED Tests Mapping

| Boundary | RED test task | Status |
|----------|---------------|--------|
| Route registration order (`/api/tree/*` before `/{path:path}/taxon-links`) | 1.9 | covered |
| `species_count` lazy-null at >100k direct children | 1.5 | covered |
| Search ranking (exact > prefix > substring + display_name length tie-break) | 1.7 | covered |
| Backend happy path (root rows + authorship + has_children) | 1.1 | covered |
| Frontend URL builder + decode | 3.1 | covered |
| Frontend debounce | 3.3 | covered |
| Frontend tree UI (caret, indent, row format, a11y) | 3.5, 3.12 | covered |
| App integration (breadcrumb-links after Cascade delete) | 3.11 | covered |
