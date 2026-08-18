# Proposal: species-folder-explorer

## Intent

Closes issue #68. The `taxon` SPA currently dispatches 13 search-source URLs in new tabs and forgets everything between sessions. This change adds a **per-species workspace layer**: a persistent `explored` flag, on-demand folder creation mirroring the species breadcrumb, per-link "done" switches, and an embedded iframe explorer bound to the currently-active link — all gated by the user's local workspace at `./Proyecto-Aqualife/`. After this lands, the user can pick a species, mark it explored, create its folder under `Animalia/Chordata/.../Panthera tigris/`, toggle per-source switches as they visit each link, and read those sources inside an `<iframe>` without losing the SPA context.

## Scope

### In Scope
- **A. Persistent `explored` flag per species** — backend table `species_explored(genus TEXT, epithet TEXT, explored_at TIMESTAMP, PK(genus, epithet))`, `POST/DELETE /api/explored/{genus}/{epithet}`, checkbox trailing column on `SpeciesList` rows.
- **B. Folder creation API + UI** — backend table `species_folders(genus TEXT, epithet TEXT, path TEXT, created_at TIMESTAMP, PK(genus, epithet))`, `POST /api/species-folder/{genus}/{epithet}` (creates nested folder under `AQUALIFE_ROOT`), `GET /api/species-folder/{genus}/{epithet}` (existence check), trailing folder badge / create-folder button on `SpeciesList` rows.
- **C. Per-link "done" switches** — backend table `link_visited(genus TEXT, epithet TEXT, source_label TEXT, visited_at TIMESTAMP, PK(genus, epithet, source_label))`, `POST /api/link-visited/{genus}/{epithet}/{source}`, `DELETE /api/link-visited/{genus}/{epithet}/{source}`, `GET /api/link-visited/{genus}/{epithet}` (hydrate), leading `[visited]` switch on every `SpeciesLinks` cell with `border-muted text-slate strikethrough` styling when on.
- **D. Embedded explorer** — new `ExplorerPanel.tsx` rendering `<iframe sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-downloads" src={activeLink?.url ?? ""} aria-label={...}>` with `target="_blank"` fallback card when the source refuses embedding.
- Spanish mirrors on every artifact (AGENTS.md §1).
- `learn-es/2026-08-15-species-folder-explorer.md` + Spanish mirror after green CI (AGENTS.md §2).

### Out of Scope
- Cloud sync, multi-device, auth (single-user local SQLite per issue #68).
- Subspecies folder nesting — folder stops at `species`, mirroring `taxon/api/sqlite_resolver.py::list_kingdoms::_flatten_species_subtree`.
- Recipe extraction from search results — drag-and-drop from iframe into the OS folder is enough.
- `.pen` design page — Pencil MCP disabled; design goes through prescriptive markdown `docs/design/species-folder-explorer.md` (arbol-col-browse precedent).

## Approach

**Storage model — 3 new tables, all keyed with `(genus, epithet)` re-bind columns to survive re-imports.**

The project has no Alembic and `taxon/import_data.py` rebuilds `taxa` from scratch on every run, which bumps `taxa.id`. The explored flag MUST be orthogonal to that churn (otherwise re-imports wipe user state) — so it lives in its own table. The other two tables follow the same pattern.

```sql
species_explored(genus      TEXT NOT NULL,
                 epithet    TEXT NOT NULL,
                 explored_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                 PRIMARY KEY (genus, epithet))

species_folders(genus      TEXT NOT NULL,
                epithet    TEXT NOT NULL,
                path       TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (genus, epithet))

link_visited(genus        TEXT NOT NULL,
             epithet      TEXT NOT NULL,
             source_label TEXT NOT NULL,
             visited_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
             PRIMARY KEY (genus, epithet, source_label))
```

The primary keys are `(genus, epithet)` (and `(genus, epithet, source_label)` for `link_visited`) — NOT `species_id INTEGER REFERENCES taxa(id)`. The schema is intentionally orthogonal to `taxa` so re-imports that recreate `taxa` with a new autoincrement `id` do not invalidate the workspace state. The endpoint walks by `(genus, epithet)` first (the resolver returns the canonical `name` and `parent_id` from `resolve_path_by_display_level`) and creates or updates the row keyed on the `(genus, epithet)` pair. `source` is template-stable (`docs/sources/templates.md`); URLs change per substitution.

**Migration mechanism — runtime `Base.metadata.create_all(engine)` in the FastAPI lifespan + a standalone `taxon/migrate.py` script.**

No Alembic dependency added. The lifespan calls `Base.metadata.create_all(engine)` for the three new tables at app start (mirroring the existing `sqlite:///:memory:` test bootstrap at `taxon/api/__init__.py:145`). A standalone `python -m taxon.migrate {dry-run|apply}` script exists for the rare operator case (CI / fresh DB) where the schema must be applied without booting the API; it uses the same `create_all` and prints a one-line summary. This stays consistent with how `taxon/import_data.py` builds `taxa` / `species_paths` out-of-band.

**API surface — 5 new endpoints, registered BEFORE the `/{path:path}/taxon-links` catch-all (regression discipline from `test_api_router_tree::test_tree_endpoints_registered_before_taxon_links_catchall`):**

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/explored/{genus}/{epithet}` | set explored flag (idempotent, returns species row) |
| `DELETE` | `/api/explored/{genus}/{epithet}` | unset explored flag |
| `POST` | `/api/species-folder/{genus}/{epithet}` | resolve breadcrumb + `mkdir -p`, insert `species_folders` row, return `{path}` |
| `GET` | `/api/species-folder/{genus}/{epithet}` | existence check (200 `{path}` or 404) |
| `POST` | `/api/link-visited/{genus}/{epithet}/{source}` | upsert visited set (idempotent) |
| `DELETE` | `/api/link-visited/{genus}/{epithet}/{source}` | unset visited source |
| `GET` | `/api/link-visited/{genus}/{epithet}` | hydrate visited set for a species |

`POST/DELETE` matches the explored-flag pattern (no `PUT` shortcut). The resolver helper is the new `taxon/api/workspace.py` module which also owns the `AQUALIFE_ROOT` env var reader (`os.environ.get("AQUALIFE_ROOT", "./Proyecto-Aqualife/")`). Pydantic models `ExploredResponse`, `SpeciesFolderResponse`, `LinkVisitedRequest`, `LinkVisitedResponse` added to `taxon/api/schemas.py`.

**Frontend state — new `frontend/src/store/workspace.ts` Zustand store, sibling to `cascadePath` + `taxonomicTree`.**

Shape: `{exploredBySpeciesId: Map<number, boolean>, foldersBySpeciesId: Map<number, string>, visitedByKey: Map<number, Set<string>>, activeLink: {speciesId: number, source: string, url: string} | null, markExplored, unmarkExplored, createFolder, markVisited, unmarkVisited, setActiveLink, hydrate}`. Mutations are optimistic-then-reconcile (mirror the canonical row from the backend response into the local Map/Set). `hydrate()` runs on App mount: `GET /api/link-visited/list` (full table) + lazy per-row `GET /api/species-folder/{g}/{e}` only when a row mounts. `cascadePath` stays untouched — the workspace is per-species, not per-cascade-step.

**Frontend UI — row-level additions + new explorer panel.**

`SpeciesList.tsx` rows gain a trailing column `[explored-checkbox] [folder-badge-or-button]` to the right of the existing `MarkerBadges`. `SpeciesLinks.tsx` cells gain a leading `[visited]` switch (first tab stop — keyboard-first, matches the switch's "toggle state" semantics better than trailing). New `ExplorerPanel.tsx` mounts inside `App.tsx`'s right column below `<SpeciesLinks>`/`<Breadcrumb>`, `sticky top-0`, renders `aria-label="Embedded search result for {species}"`, and shows a "this source refuses embedding" placeholder card with an "Open in new tab" button when the iframe `onError` fires (X-Frame-Options / CSP rejection — Wikipedia, Scholar, BHL all send `SAMEORIGIN`).

**`AQUALIFE_ROOT` convention — env var with relative default.**

`os.environ.get("AQUALIFE_ROOT", "./Proyecto-Aqualife/")` in `taxon/api/workspace.py`. On `create_app` startup, `Path(root).mkdir(parents=True, exist_ok=True)`; reject unwriteable root with a clear error envelope. Mirrors `TAXON_DATABASE_URL` precedent. The env var is mandatory when running from a worktree subfolder — pinned with a test that runs from `tmp_path` and asserts the error envelope when `cwd != project_root`.

**Iframe sandbox + fallback.**

`sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-downloads"` (no `allow-top-navigation` — prevents the iframe from navigating the SPA). Downloads route through the browser's default download flow (Content-Disposition is not intercepted). Safari gates them more strictly; the `target="_blank"` fallback card covers the failure mode. The fallback button is a regular `<a>` rendered outside the iframe so it works regardless of popup-blocker state.

**Design — prescriptive markdown, no `.pen` page.**

Pencil MCP is disabled in this session (verified, `MCP error -32603: failed to connect to running Pencil app`). Same precedent as `arbol-col-browse` (issue #67, archived 2026-08-16). The design phase writes `docs/design/species-folder-explorer.md` + Spanish mirror `documents-es/docs/design/species-folder-explorer-es.md` with line-by-line implementation specs for `ExplorerPanel`, the `SpeciesList` trailing column, and the `SpeciesLinks` leading switch. The `impeccable` skill audit is applied to the markdown BEFORE any frontend code is written (AGENTS.md §5).

## Capabilities

### New Capabilities
- `species-folder`: backend persistence + UI affordance for breadcrumb-mirroring folder creation under `AQUALIFE_ROOT`.
- `link-visited`: backend persistence + UI affordance for per-(species, source) visited switches with strikethrough disabled styling.
- `species-explored`: backend persistence + UI affordance for the per-species explored checkbox.
- `workspace-explorer`: new `ExplorerPanel.tsx` rendering the sandboxed iframe bound to the active link, with `target="_blank"` fallback for X-Frame-Options / CSP rejections.

### Modified Capabilities
- None (the existing `taxonomy-hierarchy` and `species-search-links` specs stay verbatim; the resolver contract is unchanged and the 13-link dispatch is unchanged).

## Affected Areas

| Area | Impact |
|------|--------|
| `taxon/schema.py` | New models `SpeciesExplored`, `SpeciesFolder`, `LinkVisited` |
| `taxon/api/workspace.py` | New (resolver + `AQUALIFE_ROOT` reader) |
| `taxon/api/router.py` | +5–7 endpoints, registered BEFORE `/{path:path}/taxon-links` catch-all |
| `taxon/api/schemas.py` | +`ExploredResponse`, `SpeciesFolderResponse`, `LinkVisitedRequest`, `LinkVisitedResponse` |
| `taxon/migrate.py` | New (standalone `dry-run` / `apply` script) |
| `taxon/tests/` | +`test_workspace_resolver.py`, +`test_api_router_workspace.py`, +`test_migrate.py` |
| `frontend/src/store/workspace.ts` | New |
| `frontend/src/api.ts` | +`setExplored`, `unsetExplored`, `createSpeciesFolder`, `getSpeciesFolder`, `recordLinkVisited`, `unrecordLinkVisited`, `listLinkVisited` |
| `frontend/src/components/SpeciesList.tsx` | Trailing column `[explored-checkbox] [folder-badge-or-button]` |
| `frontend/src/components/SpeciesLinks.tsx` | Leading `[visited]` switch per cell |
| `frontend/src/components/ExplorerPanel.tsx` | New |
| `frontend/src/App.tsx` | Mount `<ExplorerPanel>` in right column |
| `frontend/tests/` | +`SpeciesList.workspace.test.tsx`, +`SpeciesLinks.visited.test.tsx`, +`ExplorerPanel.test.tsx`, +`workspace.store.test.ts`, +`api.workspace.test.ts` |
| `docs/design/species-folder-explorer.md` | New (prescriptive design + impeccable audit) |
| `documents-es/docs/design/species-folder-explorer-es.md` | New (Spanish mirror) |
| `openspec/specs/species-folder/spec.md` | New |
| `openspec/specs/link-visited/spec.md` | New |
| `openspec/specs/species-explored/spec.md` | New |
| `openspec/specs/workspace-explorer/spec.md` | New |
| `learn-es/2026-08-15-species-folder-explorer.md` | New (after green CI) |
| `documents-es/learn-es/2026-08-15-species-folder-explorer-es.md` | New (Spanish mirror) |

## Risks

| Risk | Lik | Mitigation |
|------|-----|------------|
| No Alembic migration tooling | Med | explicit alternative: `Base.metadata.create_all` in lifespan + `taxon/migrate.py` script. No Alembic dependency added. |
| Schema churn from re-imports (`taxon/import_data.py` rebuilds `taxa`, bumps `id`) | High | every new table carries `(genus, epithet)` re-bind columns; the endpoint walks by name and re-binds FK on each read. Pinned with a test. |
| `AQUALIFE_ROOT` cwd mismatch (worktree subfolder resolves `./Proyecto-Aqualife/` to wrong path) | Med | env var mandatory + `Path(root).mkdir(parents=True, exist_ok=True)` + explicit error envelope when unresolvable. Pinned with a test that runs from `tmp_path`. |
| X-Frame-Options / CSP rejection (Wikipedia, Scholar, BHL all send `SAMEORIGIN`) | High | `target="_blank"` fallback card is REQUIRED, not optional. The fallback `<a>` is rendered outside the iframe so popup-blocker state doesn't matter. |
| Iframe sandbox + downloads (Safari gates iframe downloads more strictly) | Med | browser default download flow; fallback `<a target="_blank">` always reachable. |
| Transport failure masking MUST violations (arbol-col-browse PR3 precedent) | Med | every MUST requirement (one per WHEN/THEN clause in the 4 new specs) gets a dedicated test pinning the contract BEFORE the green commit. `sdd-verify` runs as an independent pass. |
| 400-line PR-review budget | Med | explicit 3-chained-PR split (see Delivery strategy); each PR stays ≤350 LOC. |
| Strict TDD requires per-requirement test pinning | Med | proposal enumerates the test count by PR (see Milestones). |
| Pencil MCP disabled — no `.pen` page | Med | prescriptive design doc + impeccable audit BEFORE code (AGENTS.md §5 gate). |
| `cascadePath` ↔ `workspaceStore` interaction (workspace is per-species, cascadePath is per-cascade-step) | Low | active-link `setActiveLink` only fires from species-link clicks; per-taxon breadcrumb-links panel keeps state but does NOT activate the iframe (scoped to species only — see explore §"Active-link state scope" question 8). Pinned in spec. |

## Out of Scope

- Cloud sync, multi-device, auth (single-user local SQLite per issue #68).
- Subspecies folder nesting (folder stops at species; mirrors `taxon/api/sqlite_resolver.py::_flatten_species_subtree`).
- Recipe extraction from search results (user drag-and-drops from iframe to OS folder).
- `taxa.is_explored` denormalised column (option (a) from explore §11 — the new table is safer against re-import churn).
- Alembic dependency and Alembic-versioned migrations.
- `.pen` design page (Pencil MCP disabled; markdown design + impeccable audit replaces it).

## Milestones

1. **Decisions captured here**: 3 new tables (orthogonal to `Taxon`, re-bind by `(genus, epithet)`); runtime `Base.metadata.create_all` + `taxon/migrate.py` script (no Alembic); 3 chained PRs (PR1 backend ≤350, PR2 frontend store + rows ≤350, PR3 explorer + design + learn-es ≤350).
2. **Design doc + impeccable audit** — `docs/design/species-folder-explorer.md` + Spanish mirror audited by `impeccable` BEFORE any code (AGENTS.md §5 gate).
3. **Backend PR1** (`feat/species-folder-explorer-backend`, ≤350 LOC, target `develop`):
   - 3 new SQLAlchemy models + lifespan `create_all` call.
   - `taxon/api/workspace.py` resolver + `AQUALIFE_ROOT` env var reader.
   - 5 endpoints (POST/DELETE explored, POST/GET species-folder, POST/DELETE/GET link-visited), registered BEFORE catch-all.
   - 4 new Pydantic models.
   - `taxon/migrate.py` script (dry-run / apply).
   - Backend tests: `test_workspace_resolver.py` (~10 tests pinning name re-bind + mkdir race + env var resolution from subfolder), `test_api_router_workspace.py` (~8 tests pinning each endpoint's WHEN/THEN), `test_migrate.py` (script dry-run vs apply).
4. **Frontend PR2** (`feat/species-folder-explorer-frontend`, ≤350 LOC, target `develop`):
   - `frontend/src/store/workspace.ts` + `hydrate()` on App mount.
   - `frontend/src/api.ts` extensions (7 new methods on the typed client).
   - `SpeciesList` trailing column + `SpeciesLinks` leading switch.
   - Vitest + axe-core tests: `SpeciesList.workspace.test.tsx`, `SpeciesLinks.visited.test.tsx`, `workspace.store.test.ts`, `api.workspace.test.ts`.
5. **Frontend PR3** (`feat/species-folder-explorer-explorer`, ≤350 LOC, target `develop`):
   - `ExplorerPanel.tsx` with `sandbox="..."` iframe + `target="_blank"` fallback card + `aria-label`.
   - `App.tsx` mounts `<ExplorerPanel>` in right column.
   - `ExplorerPanel.test.tsx` (iframe src / sandbox / aria-label / fallback).
   - `docs/design/species-folder-explorer.md` + Spanish mirror (if not already in PR1's setup).
   - `learn-es/2026-08-15-species-folder-explorer.md` + Spanish mirror (AFTER green CI per AGENTS.md §2).
6. **sdd-archive** — once PR3 is green and merged, run `sdd-archive` to sync the 4 new specs and write `archive-report.md` + Spanish mirror `documents-es/openspec/changes/species-folder-explorer/archive-report-es.md`.

## Delivery strategy

3 chained PRs stacked-to-main, `auto-chain` per the orchestrator's pre-flight cache. Each PR is ≤350 LOC (well under the 400-line review budget).

- **PR1 backend (≤350 LOC)** — tables + endpoints + lifespan migration + `taxon/migrate.py` script + backend pytest. Closes sub-features A/B/C backend surface.
- **PR2 frontend-store + row UI (≤350 LOC)** — `workspaceStore` + `api.ts` extensions + `SpeciesList` trailing column + `SpeciesLinks` leading switch + vitest + axe-core. Closes sub-features A/B/C frontend surface.
- **PR3 frontend-explorer + design + learn-es (≤350 LOC)** — `ExplorerPanel.tsx` + `App.tsx` mount + `ExplorerPanel.test.tsx` + design doc + Spanish mirror + `learn-es` entry. Closes sub-feature D.
- **No cleanup PR** — no obsolete files to delete (per issue §"Proposed approach").

The Pencil + impeccable design pass is a HARD GATE before PR1 (AGENTS.md §5) — `sdd-design` writes the prescriptive markdown and audits it BEFORE any code.

## Dependencies

- `taxon.api.hierarchy.resolve_path_by_display_level` (verbatim, drives folder-nesting breadcrumb walk).
- `docs/sources/templates.md` (verbatim, 13-link substitution; canonical count 13 not 12).
- `taxon.api.sqlite_resolver` patterns + `_to_row` helper for `TaxonRow` construction.
- Pencil + impeccable design pass per AGENTS.md §5 (BEFORE frontend code).

## Success Criteria

- [ ] `POST /api/explored/{g}/{e}` sets the explored flag (idempotent); `DELETE` unsets it. Both round-trip the species row.
- [ ] `POST /api/species-folder/{g}/{e}` creates the nested folder under `AQUALIFE_ROOT` and persists the path in `species_folders`. Re-running returns 409 (idempotency check pinned by test).
- [ ] `GET /api/species-folder/{g}/{e}` returns the path or 404.
- [ ] `POST /api/link-visited/{g}/{e}/{source}` upserts (idempotent on `(species_id, source)`); `DELETE` removes.
- [ ] `GET /api/link-visited/{g}/{e}` returns the visited set for a species.
- [ ] On re-import that bumps `taxa.id`, all three new tables re-bind by name — no orphaned rows (pinned with a test that mutates `taxa.id` and re-walks).
- [ ] `AQUALIFE_ROOT` env var resolves correctly when running from `tmp_path` (subfolder test) — or fails with a clear error envelope.
- [ ] `SpeciesList` row trailing column toggles `[explored-checkbox]` and `[folder-badge-or-button]`. Folder badge replaces button after first create.
- [ ] `SpeciesLinks` cell leading switch toggles visited state; styling flips to `border-muted text-slate strikethrough` when on.
- [ ] `<ExplorerPanel>` iframe `src` matches `activeLink.url`; sandbox attributes exact; `aria-label` present; fallback card renders when `iframe.onError` fires.
- [ ] axe-core: 0 violations on `SpeciesList`, `SpeciesLinks`, `ExplorerPanel` renders.
- [ ] `pytest` + `vitest run` suites green; `tsc -b && vite build` green.
- [ ] `/learn-es/2026-08-15-species-folder-explorer.md` entry + Spanish mirror created after green CI on `develop`.
- [ ] `sdd-archive` completes; 4 new specs synced into `openspec/specs/`; archive-report + Spanish mirror written.