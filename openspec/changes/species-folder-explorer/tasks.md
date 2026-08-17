# Tasks: species-folder-explorer

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines (PR1 backend) | ~310 LOC |
| Estimated changed lines (PR2 frontend store + rows) | ~330 LOC |
| Estimated changed lines (PR3 frontend explorer) | ~290 LOC |
| 400-line budget risk (per PR) | Low (each PR ≤350 LOC) |
| Chained PRs recommended | Yes — auto-chain per preflight |
| Decision needed before apply | No |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|---------------------|
| 1 | Backend 3 tables + 7 endpoints + lifespan `create_all` + `taxon/migrate.py` + AQUALIFE_ROOT + schemas | PR 1 (`feat(api): species-folder-explorer backend`) | `pytest -v taxon/tests/test_api_router_workspace.py taxon/tests/test_workspace_resolver.py taxon/tests/test_migrate.py` | `python -m taxon.main` against `data/col.db` + `curl -X POST http://localhost:8000/api/explored/Panthera/tigris` | Revert PR 1: 3 additive tables + 7 endpoints removed; `taxa`/`species_paths` untouched. |
| 2 | Frontend `workspaceStore` + `api.ts` extensions + `SpeciesList` trailing column + `SpeciesLinks` leading switch + vitest + axe-core | PR 2 (`feat(frontend): workspace store + row chips`) | `npm run typecheck && npm test -- workspace store SpeciesList SpeciesLinks api.workspace` | `npm run dev` against live backend from PR 1; navigate Animalia → Chordata → Panthera; toggle explored checkbox | Revert PR 2: store additive; chips removed; `SpeciesList`/`SpeciesLinks` keep historical shape. Backend PR 1 stays. |
| 3 | Frontend `ExplorerPanel.tsx` + `App.tsx` mount + `ExplorerPanel.test.tsx` + design doc + Spanish mirror + `learn-es` entry | PR 3 (`feat(frontend): explorer panel + workspace design`) | `npm run typecheck && npm test -- ExplorerPanel` | `npm run dev` against live backend from PR 1; click a `Wikipedia` link; observe iframe sandbox + fallback card | Revert PR 3: panel unmounted; `App.tsx` right column restores breadcrumb + links. PR 1 + PR 2 stay. |

## Phase 1: Backend tables + endpoints + migrate.py (PR1, ≤350 LOC)

- [ ] 1.1 RED — write `taxon/tests/test_workspace_resolver.py` asserting the 3 new tables (`species_explored`, `species_folders`, `link_visited`) are created by `Base.metadata.create_all(engine)` with the documented PK + column shape: `species_explored.PRIMARY KEY (genus, epithet)`, `species_folders.PRIMARY KEY (genus, epithet)`, `link_visited.PRIMARY KEY (genus, epithet, source_label)`, NONE of them carries a FK to `taxa.id`.
- [ ] 1.2 RED — write `taxon/tests/test_api_router_workspace.py` for `POST/DELETE /api/explored/{g}/{e}`, `GET /api/explored/list`, `POST/GET /api/species-folder/{g}/{e}`, `POST/DELETE/GET /api/link-visited/{g}/{e}/{source}` — happy paths + 204 idempotent DELETE + 409 duplicate folder + 404 unknown species + 200 empty-list `{"species": []}` / `{"sources": []}` envelopes.
- [ ] 1.3 RED — write `taxon/tests/test_migrate.py` asserting `python -m taxon.migrate dry-run` prints a summary naming the 3 missing tables without applying, AND `apply` creates the 3 tables without dropping `taxa` / `species_paths`.
- [ ] 1.4 RED — write `taxon/tests/test_aqualife_root.py` asserting the env var reader + project-root-relative resolution (not cwd) + fail-loudly 500 envelope when the resolved path is unresolvable or unwritable, and verifying the `path` segment is `os.sep`-joined verbatim from the canonical `name` segments.
- [ ] 1.5 GREEN — add the 3 ORM models to `taxon/api/workspace.py` (or `taxon/schema.py` if the project convention requires it) with PK `(genus, epithet)` / `(genus, epithet, source_label)`, NO FK to `taxa.id`, and the `explored_at` / `path` / `created_at` / `visited_at` columns.
- [ ] 1.6 GREEN — add the resolver helpers: `set_explored`, `unset_explored`, `list_explored`, `create_species_folder`, `get_species_folder`, `record_link_visited`, `unrecord_link_visited`, `list_link_visited`. Each walks by `(genus, epithet)` (and `source_label` for `link_visited`); never touches `taxa.id`.
- [ ] 1.7 GREEN — add Pydantic schemas `ExploredResponse`, `SpeciesFolderResponse`, `LinkVisitedResponse`, `LinkVisitedListResponse`, `ExploredListResponse` to `taxon/api/schemas.py`; export from `__all__`.
- [ ] 1.8 GREEN — register the 8 endpoints in `taxon/api/router.py` BEFORE the `/{path:path}/taxon-links` catch-all (regression discipline per `test_api_router_tree::test_tree_endpoints_registered_before_taxon_links_catchall`).
- [ ] 1.9 GREEN — wire `Base.metadata.create_all(engine)` for the 3 new tables inside the FastAPI lifespan in `taxon/api/__init__.py`; the call MUST be idempotent and MUST NOT touch `taxa` / `species_paths`.
- [ ] 1.10 GREEN — implement `taxon/migrate.py` standalone script with `dry-run` + `apply` modes (Python module-level CLI, no Alembic) that reads `TAXON_DATABASE_URL` and emits the documented one-line summary.
- [ ] 1.11 GREEN — implement the `AQUALIFE_ROOT` env var reader + project-root-relative resolver in `taxon/api/workspace.py`; reject unwritable root with `APIError(status_code=500, detail="AQUALIFE_ROOT not writable: <path> from cwd <cwd>")`.
- [ ] 1.12 RED — write `taxon/tests/test_rebind_after_taxa_id_bump.py` pinning that re-imports that recreate `taxa` (mutating `taxa.id` of `Panthera tigris`) do NOT invalidate the 3 new workspace rows — the `(genus, epithet)` walk is the contract.
- [ ] 1.13 REFACTOR — extract the resolver helpers + `AQUALIFE_ROOT` reader into `taxon/api/workspace.py`; ensure `pytest` + `pytest-cov` stay green; commit.

## Phase 2: Pencil design + impeccable audit (PR 2, design-only)

- [x] 2.1 [DEFERRED] Pencil design was not executed because Pencil/Google Stitch MCP is disabled in this session; the prescriptive surface brief was captured as `docs/design/species-folder-explorer.md` instead (837 lines, line-by-line translation spec for the implementer). A follow-up issue may redo the Pencil `.pen` page in a future slice.
- [x] 2.2 [DEFERRED] Same rationale as 2.1; no Pencil page to audit.
- [x] 2.3 [DEFERRED] Same rationale as 2.1.
- [x] 2.4 [DEFERRED] Same rationale as 2.1.

## Phase 3: Frontend workspaceStore + row UI (PR2, ≤350 LOC)

- [ ] 3.1 RED — write `frontend/tests/api.workspace.test.ts` covering typed client wrappers for the 8 backend endpoints (200 / 201 / 204 / 404 / 409 / 500 envelopes) using the existing `ApiResult<T>` discriminated union.
- [ ] 3.2 GREEN — add `fetchExplored*`, `fetchSpeciesFolder*`, `fetchLinkVisited*` typed methods to `frontend/src/api.ts`; the speciesKey convention is `${genus}|${epithet}` URL-encoded pipe.
- [ ] 3.3 RED — write `frontend/tests/store.workspace.test.ts` covering the zustand workspace store shape (`explored: Map<speciesKey, boolean>`, `folders: Set<speciesKey>`, `visited: Map<speciesKey, Set<source>>`, `activeLink: {speciesKey, source, url} | null`) and the actions `markExplored`, `unmarkExplored`, `createFolder`, `markVisited`, `unmarkVisited`, `setActiveLink`, `hydrate`.
- [ ] 3.4 GREEN — create `frontend/src/store/workspace.ts` zustand store with the documented shape + actions + hydration hook (eager on `App.tsx` mount: one `GET /api/explored/list` + lazy per-species `GET /api/link-visited/{g}/{e}`).
- [ ] 3.5 RED — write `frontend/tests/SpeciesList.workspace.test.tsx` covering the trailing column `[explored-checkbox] [folder-badge-or-button]` state machine: unchecked + button → click triggers `POST /api/species-folder/...` → checked + badge (no button). Confirms `e.stopPropagation()` keeps the row click firing `taxon:select`.
- [ ] 3.6 GREEN — extend `SpeciesList.tsx` with the trailing column; the explored-checkbox is wired to the workspace store; the folder-button/badge is wired to the `POST /api/species-folder/{g}/{e}` endpoint.
- [ ] 3.7 RED — write `frontend/tests/SpeciesLinks.visited.test.tsx` covering the leading `[visited]` switch + `border-muted text-slate line-through` visual state when on, plus the click dispatching `POST` / `DELETE /api/link-visited/{g}/{e}/{source}`.
- [ ] 3.8 GREEN — extend `SpeciesLinks.tsx` with the leading switch + the documented visual state; clicks dispatch the `link-visited` endpoints and reconcile via the workspace store.
- [ ] 3.9 RED — write `frontend/tests/a11y.workspace.test.tsx` using `vitest-axe` asserting 0 axe-core violations on the `SpeciesList` row + the `SpeciesLinks` cell + the chip / switch controls.
- [ ] 3.10 GREEN — fix every a11y issue flagged by axe (label associations, role="switch", aria-checked, focus order); pin with vitest.
- [ ] 3.11 REFACTOR — keep PR 2 ≤350 LOC; defer the `ExplorerPanel` + its tests to PR 3.

## Phase 4: Frontend ExplorerPanel + design-doc + learn-es (PR3, ≤350 LOC)

- [ ] 4.1 RED — write `frontend/tests/ExplorerPanel.test.tsx` covering: iframe renders when `activeLink` is set vs. shows the empty-state placeholder when null; the `sandbox` attribute matches the exact set `allow-same-origin allow-scripts allow-forms allow-popups allow-downloads`; the `aria-label` reads `Embedded search result for {genus} {epithet} ({source})`; an obvious `<a target="_blank" rel="noopener noreferrer">Open in new tab</a>` button is rendered when `iframe.onError` fires (the fallback card); the fallback button is reachable from keyboard focus.
- [ ] 4.2 GREEN — create `frontend/src/components/ExplorerPanel.tsx` with iframe + sandbox + fallback card (rendered outside the iframe for popup-blocker resilience) + an active-link pill that names the embedded source.
- [ ] 4.3 RED — write `frontend/tests/ExplorerPanel.activate.test.tsx` covering: a `SpeciesLinks` species-panel click sets `activeLink`; the per-taxon breadcrumb-links panel does NOT mutate `activeLink`; focus moves to the iframe on activation; `aria-live="polite"` announces the load + the fallback.
- [ ] 4.4 GREEN — wire `ExplorerPanel` into `App.tsx` right column BELOW `<SpeciesLinks>` / `<Breadcrumb>`; mount via the workspace store's `activeLink` state; the `cascadePath` breadcrumb-links panel does NOT mutate `activeLink`.
- [ ] 4.5 RED — write `frontend/tests/ExplorerPanel.mobile.test.tsx` covering the mobile-collapse-to-peek-card behaviour (column-collapse breakpoint at <640px); the panel shrinks to a peek-card; the iframe still renders but the dispatch grid is collapsed.
- [ ] 4.6 GREEN — implement the responsive peek-card for screens below 640px (mobile breakpoint): the right column collapses to a sticky peek-card with the active link's label and an "open in new tab" link.
- [ ] 4.7 GREEN — axe-core regression test for `ExplorerPanel` covering the iframe + fallback card + active-link pill (0 violations).
- [ ] 4.8 GREEN — finalize the design doc: `docs/design/species-folder-explorer.md` (already 837 lines) + Spanish mirror `documents-es/docs/design/species-folder-explorer-es.md` (already 6103 words).
- [ ] 4.9 Post-merge — after PR 3 merges to `develop` with green CI, create `/learn-es/2026-08-16-species-folder-explorer.md` per AGENTS.md §2; the Spanish mirror at `/documents-es/learn-es/2026-08-16-species-folder-explorer-es.md`.

## Threat Matrix → RED Tests Mapping

| Boundary | RED test task | Status |
|----------|---------------|--------|
| Re-import churn (taxa.id bump) does NOT invalidate workspace rows | 1.12 | covered |
| `AQUALIFE_ROOT` cwd mismatch (worktree subfolder resolution) | 1.4 | covered |
| Folder endpoint fails loudly on unresolvable / unwritable root | 1.4 | covered |
| Duplicate folder creation returns 409 | 1.2 | covered |
| Idempotent DELETE on missing row returns 204 | 1.2 | covered |
| Iframe `X-Frame-Options` / CSP rejection → fallback card | 4.1 | covered |
| Per-taxon breadcrumb-links panel does NOT activate iframe | 4.3 | covered |
| Mobile collapse to peek-card | 4.5 | covered |
| axe-core aria-required-children on `ExplorerPanel` | 4.7 | covered |
| Transport-failure drift (arbol-col-browse PR3 precedent) | every task | each task MUST have a dedicated RED test before green commit |
