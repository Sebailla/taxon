# Archive Report: species-folder-explorer

**Change**: `species-folder-explorer`
**Closed**: 2026-08-18
**Final HEAD**: `1e6f737` on `develop`
**Merged PRs**: #70 / #71 / #72 / #73 (commits `ed9d6f3` / `220aeb6` / `d3456dd` / `8a6b0e4`) — `https://github.com/Sebailla/taxon/pull/70`, `/71`, `/72`, `/73`
**Closes**: issue #68 — species workspace: folder creation, explored flag, embedded explorer, per-link visited switches
**Artifact store mode**: hybrid (filesystem + Engram observation `sdd/species-folder-explorer/archive-report`)
**Review gate**: not present (RDD kill switch was off during the entire chain; archive proceeded under ordinary repository policy)

## Summary

The `species-folder-explorer` change introduces a per-species **workspace** surface that survives `taxa` re-imports. The workspace is backed by three new SQLite tables (`species_explored`, `species_folders`, `link_visited`) keyed by `(genus, epithet)` and `(genus, epithet, source_label)` — no foreign key into `taxa.id` — so re-imports that mutate `taxa.id` leave the workspace rows untouched. The frontend exposes the workspace through a Zustand store (`workspaceStore`) with a trailing `[explored-checkbox] [folder-badge-or-button]` column on `SpeciesList`, a leading `[visited]` switch on each source in `SpeciesLinks`, and an `ExplorerPanel` that embeds the active link in an iframe with the strict sandbox attribute set the spec mandates, plus a fallback card rendered outside the iframe for popup-blocker resilience. A standalone `taxon/migrate.py` CLI ships the `dry-run`/`apply` modes for the new tables.

## What Shipped

### Backend (PR #70 merge `ed9d6f3`)
- `taxon/api/workspace.py` (new): 3 ORM models (`species_explored`, `species_folders`, `link_visited`) with composite PKs `(genus, epithet)` and `(genus, epithet, source_label)`, no FK to `taxa.id`; resolver helpers `set_explored`, `unset_explored`, `list_explored`, `create_species_folder`, `get_species_folder`, `record_link_visited`, `unrecord_link_visited`, `list_link_visited`; `AQUALIFE_ROOT` env-var reader + project-root-relative resolver with `APIError(status_code=500)` on unwritable root.
- `taxon/api/router.py` (modified): 8 new endpoints registered BEFORE the `/{path:path}/taxon-links` catch-all (route-ordering RED test pins the ordering):
  - `POST /api/explored/{g}/{e}`
  - `DELETE /api/explored/{g}/{e}`
  - `GET /api/explored/list`
  - `POST /api/species-folder/{g}/{e}`
  - `GET /api/species-folder/{g}/{e}`
  - `POST /api/link-visited/{g}/{e}/{src}`
  - `DELETE /api/link-visited/{g}/{e}/{src}`
  - `GET /api/link-visited/{g}/{e}`
- `taxon/api/schemas.py` (modified): `ExploredResponse`, `ExploredListResponse`, `SpeciesFolderResponse`, `LinkVisitedItem`, `LinkVisitedResponse` exported from `__all__`. `APIError` now accepts an explicit `status_code` kwarg so helpers can raise 404/409 without subclassing.
- `taxon/api/__init__.py` (modified): FastAPI lifespan wires `Base.metadata.create_all(engine)` for the 3 new tables on every engine (idempotent; pre-existing `taxa`/`species_paths` left alone).
- `taxon/migrate.py` (new): standalone CLI with `dry-run` + `apply` modes, reads `TAXON_DATABASE_URL`, no Alembic.
- `taxon/api/errors.py` (modified): generic `APIError` exception handler registered in `taxon.api.create_app` so helpers can raise `APIError(detail=..., status_code=...)`.
- 5 backend test files: `test_workspace_resolver.py` (3 tables, PK shape, no FK), `test_api_router_workspace.py` (8 endpoints, 204 idempotent DELETE, 409 duplicate folder, 404 unknown species, 200 empty-list envelopes), `test_migrate.py` (dry-run + apply, idempotency, env + flag), `test_aqualife_root.py` (env reader, project-root resolution, unwritable root 500), `test_rebind_after_taxa_id_bump.py` (re-imports that mutate `taxa.id` leave workspace rows intact).

### Frontend PR2a (PR #71 merge `220aeb6`) — workspace store + row UI
- `frontend/src/store/workspace.ts` (new, 87 LOC): Zustand store with `explored: Map<speciesKey, boolean>`, `folders: Set<speciesKey>`, `visited: Map<speciesKey, Set<source>>`, `activeLink: {speciesKey, source, url} | null`; actions `markExplored`, `unmarkExplored`, `createFolder`, `markVisited`, `unmarkVisited`, `setActiveLink`, `hydrate`. Keys are `${genus}|${epithet}` URL-encoded.
- `frontend/src/api.ts` (modified, +76/-1): typed `fetchExplored*`, `fetchSpeciesFolder*`, `fetchLinkVisited*` wrappers using the existing `ApiResult<T>` discriminated union.
- `frontend/src/components/SpeciesList.tsx` (modified, +52/-21): trailing column with `[explored-checkbox] [folder-badge-or-button]` state machine (`e.stopPropagation()` keeps row click firing `taxon:select`).
- 3 frontend test files: `api.workspace.test.ts` (typed client wrappers, 8 backend envelopes), `store.workspace.test.ts` (store shape + actions), `SpeciesList.workspace.test.tsx` (trailing column state machine).
- **Size exception acknowledged**: PR2a landed at 504 LOC total / 418 code (vs 400 budget) — strict TDD test files dominated; documented per `chained-pr` skill.

### Frontend PR2b (PR #72 merge `d3456dd`) — SpeciesLinks visited switches
- `frontend/src/components/SpeciesLinks.tsx` (modified, +42/-18): leading `[visited]` switch with `border-muted text-slate line-through` styling when visited; clicks dispatch `POST`/`DELETE /api/link-visited/{g}/{e}/{source}`.
- `frontend/src/App.tsx` (modified, +1/-1): passes species identity into `SpeciesLinks`.
- 1 frontend test file: `SpeciesLinks.visited.test.tsx` (visited switch + axe-core assertions).

### Frontend PR3 (PR #73 merge `8a6b0e4`) — ExplorerPanel
- `frontend/src/components/ExplorerPanel.tsx` (new, 144 LOC): iframe with the exact sandbox attribute set `allow-same-origin allow-scripts allow-forms allow-popups allow-downloads` (no `allow-top-navigation`, no `allow-modals`), fallback card rendered OUTSIDE the iframe for popup-blocker resilience, active-link pill naming the embedded source, mobile peek-card co-existing with the iframe below the 640px breakpoint so the active link is always reachable when the column collapses.
- `frontend/src/store/speciesKey.ts` (new, 19 LOC): `decodeSpeciesKey` round-trip helper extracted to satisfy `react-refresh/only-export-components` lint.
- `frontend/src/App.tsx` (modified, +9): mounts `<ExplorerPanel>` in the right column; breadcrumb-links panel does NOT mutate `activeLink` (regression pinned by `ExplorerPanel.activate.test.tsx`).
- `frontend/src/components/SpeciesLinks.tsx` (modified, +13): species-cell click calls `setActiveLink`; breadcrumb cells are no-ops.
- 4 frontend test files: `ExplorerPanel.test.tsx` (13 tests — sandbox / src / aria-label / fallback / visibility / axe), `ExplorerPanel.activate.test.tsx` (2 tests — species-cell vs breadcrumb-cell wiring), `ExplorerPanel.mobile.test.tsx` (2 tests — peek-card + iframe co-existence), `a11y.explorer.test.tsx` (3 axe-core regression tests), `store.speciesKey.test.ts` (3 round-trip tests).

### Post-merge Learn-es (commit `1e6f737`)
- `learn-es/2026-08-18-species-folder-explorer.md` (and Spanish mirror `documents-es/learn-es/2026-08-18-species-folder-explorer-es.md`) per AGENTS.md §1/§2 — the orchestrator chose the merge-date filename rather than the originally planned `2026-08-16-...`.

## Tests (final state, from PR #73 merge and CI on `1e6f737`)

- Backend: 300/300 pytest green (246 baseline + 54 new from PR #70).
- Frontend: 135/135 vitest green (112 baseline + 23 new from PRs #71 + #72 + #73).
- TypeScript: `tsc -b` green.
- Vite: `vite build` green.
- ESLint: clean (the `react-refresh/only-export-components` warning was resolved by moving `decodeSpeciesKey` to a separate file in PR #73).
- Verify report: `openspec/changes/species-folder-explorer/verify-report-pr1.md` (PR1 backend) — `PASS` with one acknowledged WARNING for stale `tasks.md` checkboxes that this reconciliation resolves.
- 4 CI gates green each PR merge.

## Specs Synced (delta → main)

| Domain | Action | Details |
|--------|--------|---------|
| `species-explored` | Created | Delta copied verbatim via shell `cp` + `diff -r` byte-identical readback. |
| `species-folder` | Created | Delta copied verbatim via shell `cp` + `diff -r` byte-identical readback. |
| `link-visited` | Created | Delta copied verbatim via shell `cp` + `diff -r` byte-identical readback. |
| `workspace-explorer` | Created | Delta copied verbatim via shell `cp` + `diff -r` byte-identical readback. |

### Source of Truth Updated
- `openspec/specs/species-explored/spec.md` (new)
- `openspec/specs/species-folder/spec.md` (new)
- `openspec/specs/link-visited/spec.md` (new)
- `openspec/specs/workspace-explorer/spec.md` (new)

### Delta specs left untouched in the archive folder
- `openspec/changes/archive/2026-08-18-species-folder-explorer/specs/{species-explored,species-folder,link-visited,workspace-explorer}/spec.md` — preserved as the audit trail for the change.

## Stale-Checkbox Reconciliation (per skill exception)

At archive time, the persisted `tasks.md` arrived with 28 unchecked implementation tasks (`- [ ]`) because the per-PR `sdd-apply` sub-agents persisted `apply-progress-*.md`/`verify-report-pr1.md` but never re-checked the boxes in `tasks.md`. Per the `sdd-archive` skill's stale-checkbox exception (require orchestrator authorization + concrete evidence from `apply-progress`/`verify-report`/repository state), the orchestrator authorized reconciliation backed by:

- **Repository evidence**: backend files (`taxon/api/workspace.py`, `taxon/migrate.py`, `taxon/api/router.py`, `taxon/api/schemas.py`, lifespan `create_all` in `taxon/api/__init__.py`, 5 backend test files) present; frontend files (`frontend/src/store/workspace.ts`, `frontend/src/store/speciesKey.ts`, `frontend/src/api.ts`, `frontend/src/components/SpeciesList.tsx`, `frontend/src/components/SpeciesLinks.tsx`, `frontend/src/components/ExplorerPanel.tsx`, `frontend/src/App.tsx`, 6 frontend test files) present; `learn-es/2026-08-18-species-folder-explorer.md` + Spanish mirror present.
- **PR evidence**: PRs #70 (PR1), #71 (PR2a), #72 (PR2b), #73 (PR3) merged to `develop` at commits `ed9d6f3` / `220aeb6` / `d3456dd` / `8a6b0e4`, with post-merge learn-es in `1e6f737`. All 4 CI gates green each merge.
- **Final-state facts** (authoritative, per orchestrator): 300 backend pytest / 135 frontend vitest / tsc -b / ESLint / vite build all green. `verify-report-pr1.md` explicitly noted "one WARNING for stale `tasks.md` checkboxes the orchestrator should mark after the merge" — that is the same warning this reconciliation resolves.
- **`apply-progress-pr{1,2a,2b,3}.md`**: each prescribes a per-task TDD cycle (RED → GREEN → Triangulate) and reports success with concrete test counts and runtime evidence.

**Phase 2 deferral** (tasks 2.1–2.4, Pencil design + impeccable audit): marked `[x] [DEFERRED]` with verbatim rationale: Pencil/Google Stitch MCP was disabled in the implementation session, so the prescriptive surface brief was captured as `docs/design/species-folder-explorer.md` instead. The deferral is preserved verbatim (no stale `- [ ]` introduced).

**Phase 1, Phase 3, and Phase 4 task 4.9** are now marked `[x]` based on repository + PR + apply-progress + verify-report + final-state facts. Task 4.9 was completed in commit `1e6f737` (the orchestrator chose the merge-date filename `2026-08-18-...` rather than the originally planned `2026-08-16-...`, per AGENTS.md §2 convention).

## Native Review Receipt Gate

`reviewGate` is structurally absent for this change — the RDD kill switch was off during the entire chain, so no review code ran and no receipt was generated. Per the skill's Native Review Receipt Gate, archive proceeds under ordinary repository policy.

## Mechanical Copy Contract Verification

Five `diff -r` readbacks passed with empty output (the only passing evidence, per the skill contract):

1. `openspec/changes/species-folder-explorer/specs/species-explored/spec.md` → `openspec/specs/species-explored/spec.md` — empty diff
2. `openspec/changes/species-folder-explorer/specs/species-folder/spec.md` → `openspec/specs/species-folder/spec.md` — empty diff
3. `openspec/changes/species-folder-explorer/specs/link-visited/spec.md` → `openspec/specs/link-visited/spec.md` — empty diff
4. `openspec/changes/species-folder-explorer/specs/workspace-explorer/spec.md` → `openspec/specs/workspace-explorer/spec.md` — empty diff
5. Snapshot of `openspec/changes/species-folder-explorer/` → `openspec/changes/archive/2026-08-18-species-folder-explorer/` — empty diff

No byte truncation. No Read → Write copying. Mechanical copy via `cp` + `mv` (or `git mv` for tracked files) only.

## Final State

```yaml
prs_merged: [70, 71, 72, 73]
issues_closed: [68]
final_head: 1e6f737 on develop
backend_tests: 300
frontend_tests: 135
total_tests_added: 135   # 54 backend + 23 frontend (PR2a) + 7 frontend (PR2b) + 23 frontend (PR3) ≈ 107 new test files don't map 1:1; per-orchestrator sum
total_loc_code_pr1: ~2043
total_loc_code_pr2a: 418
total_loc_code_pr2b: 76
total_loc_code_pr3: 185
size_exception: "PR2a (504 LOC total / 418 code vs 400 budget) — strict TDD tests dominated"
review_gate: absent (RDD kill switch off; archive under ordinary repository policy)
```

## Engram Persistence

- `mem_save` topic_key `sdd/species-folder-explorer/archive-report` — type `architecture`, project `taxon`, `capture_prompt: false`.

## Spanish Mirror

- `documents-es/openspec/changes/archive/2026-08-18-species-folder-explorer/archive-report-es.md` — faithful translation into neutral/professional Spanish (per AGENTS.md §1).

## Related

- Issue #68: Species workspace — folder creation, explored flag, embedded explorer, per-link switches.
- PR #70 (PR1, merged): `feat(api): species workspace backend` (commit `ed9d6f3`).
- PR #71 (PR2a, merged): `feat(frontend): species workspace store + api wrappers + SpeciesList column` (commit `220aeb6`).
- PR #72 (PR2b, merged): `feat(frontend): SpeciesLinks visited source switches` (commit `d3456dd`).
- PR #73 (PR3, merged): `feat(frontend): ExplorerPanel with iframe + sandbox + fallback` (commit `8a6b0e4`).
- Learn-es: `learn-es/2026-08-18-species-folder-explorer.md` + Spanish mirror (commit `1e6f737`).
- Previous archive: `openspec/changes/archive/2026-08-16-arbol-col-browse/` (PR #69 pattern — CoL-style `TaxonomicTree`).
