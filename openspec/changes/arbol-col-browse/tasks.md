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

- [ ] 2.1 Open `taxon.pen` via Pencil MCP (`get_app_state`); add the "Taxonomic Tree Browse" page: caret row, indent by rank, `rank: Name Authorship • N spp.` row format, `Find taxon` header, `Source` + `Extant only` filter affordances; reuse existing `taxon.pen` design tokens.
- [ ] 2.2 Run an `impeccable` audit pass on the new page; document the outcome in `openspec/changes/arbol-col-browse/design.md` under "Pencil Audit".
- [ ] 2.3 Export `taxon.pen` HTML preview via `pencil export_html`; attach as the visual reference for PR 3.
- [ ] 2.4 Refine the design per `impeccable` findings; commit final Pencil screenshot at `documents-es/openspec/changes/arbol-col-browse/pencil-preview-es.md` with brief neutral Spanish caption per AGENTS.md §1.

## Phase 3: Frontend TaxonomicTree (PR 3)

- [ ] 3.1 RED — write `frontend/tests/api.treeChildren.test.ts` covering URL builder (`/api/tree/children?parent_id={id}&limit=200`) and 200/404 decode envelope.
- [ ] 3.2 GREEN — add `fetchTreeNode(parentId, init?)` + `fetchTreeSearch(q, init?)` to `frontend/src/api.ts`.
- [ ] 3.3 RED — write `frontend/tests/api.treeSearch.test.ts` covering 200ms debounce (rapid keys collapse to one request) + 200/empty decode.
- [ ] 3.4 GREEN — implement the 200ms debounce wrapper for `fetchTreeSearch`.
- [ ] 3.5 RED — write `frontend/tests/TaxonomicTree.test.tsx` covering caret toggle (`aria-expanded` reflects state), row format `rank: Name Authorship • N spp.`, indent by depth, keyboard navigation (Enter to expand, ArrowDown/Up move focus), `aria-level` per row, lazy fetch on first expand + cache hit on re-expand.
- [ ] 3.6 GREEN — create `frontend/src/store/taxonomicTree.ts` (Zustand) with state `{childrenByParentId: Map, expandedIds: Set, rootIds: number[] | null}` + actions `ensureChildren`, `toggleExpand`, `search`, `select`.
- [ ] 3.7 GREEN — create `frontend/src/components/TaxonomicTree.tsx` rendering caret rows + `Find taxon` header + `Source` + `Extant only` checkboxes; on expand dispatch `path:change` CustomEvent and write explored path to `useCascadePath.getState().setPath(...)`.
- [ ] 3.8 GREEN — modify `frontend/src/App.tsx`: import `TaxonomicTree` instead of `Cascade`; mount in the same grid slot; keep the breadcrumb-links `useEffect` (lines 119–142) and the `path:change` listener (lines 150–159) verbatim.
- [ ] 3.9 GREEN — rename `Breadcrumb.tsx` aria-label `Resolved species breadcrumb` → `Cascade path breadcrumb` (Verify-Report §11 ISSUE #3).
- [ ] 3.10 REFACTOR — delete `frontend/src/components/Cascade.tsx` + `frontend/src/components/Cascade.state.ts` + every `frontend/tests/cascade*.test.tsx` and `frontend/tests/Cascade.*.test.tsx`; re-grep `from.*Cascade` first and surface any cross-importing test.
- [ ] 3.11 GREEN — add `frontend/tests/App.taxonLinks.test.tsx` verifying the breadcrumb-links panel keeps working end-to-end after the Cascade replacement.
- [ ] 3.12 RED — write `frontend/tests/TaxonomicTree.a11y.test.tsx` using `vitest-axe` to assert no axe violations on the rendered tree.
- [ ] 3.13 GREEN — fix every a11y issue flagged by the axe scan.
- [ ] 3.14 Post-merge — after PR 3 merges to `develop` with green CI, create `/learn-es/YYYY-MM-DD-arbol-col-browse.md` following the required structure per AGENTS.md §2.

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
