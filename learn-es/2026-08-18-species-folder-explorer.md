# What

`taxon` change `species-folder-explorer` (issue #68, PRs #70 + #71 + #72 + #73) — adds a per-species workspace across 4 sub-features: explored flag toggle, per-species folder creation under `AQUALIFE_ROOT`, per-link visited switches with `link-visited` persistence, and an embedded `ExplorerPanel` that renders the active source in a sandboxed iframe with a fallback card when the source refuses embedding.

# How

- 4-PR auto-chain delivered against `develop` in stacked-to-main order (PR1 backend → PR2a frontend store+rows → PR2b SpeciesLinks switches → PR3 ExplorerPanel), each ≤ 400 LOC code, all green on CI.
- Backend (PR1, ~2,043 LOC including tests): FastAPI + SQLAlchemy + SQLite. 3 new tables (`species_explored`, `species_folders`, `link_visited`) with composite-PK re-bind keys `(genus, epithet)` — ZERO FK into `taxa.id`, pinned by `test_rebind_after_taxa_id_bump.py` (bumping `taxa.id` for Panthera tigris and asserting workspace rows survive).
- 8 endpoints (POST/DELETE `/api/explored/{g}/{e}`, GET `/api/explored/list`, POST/GET `/api/species-folder/{g}/{e}`, POST/DELETE/GET `/api/link-visited/{g}/{e}/{src}`) registered in `taxon/api/router.py` BEFORE the `/{path:path}/taxon-links` catch-all (regression discipline from `taxonomy-hierarchy`).
- Migration via runtime `Base.metadata.create_all(engine, tables=[workspace])` in the FastAPI lifespan + standalone `python -m taxon.migrate {dry-run|apply}` CLI. No Alembic dependency added.
- Frontend (PR2a + PR2b + PR3): React 18 + zustand 5 + zod + vitest + axe-core + vitest-axe.
- `workspaceStore` (zustand) holds `explored: Set<string>`, `folders: Map<string, string>`, `visitedLinks: Map<string, Set<string>>`, `activeLink: {speciesId, source, url} | null`. Species keys are `${genus}|${epithet}` URL-encoded pipes — never reads `taxa.id`.
- `api.ts` extensions wrap all 8 endpoints with zod response schemas and an `ApiResult<T>` discriminated union.
- `SpeciesList` gets a trailing column `[explored-checkbox] [folder-badge-or-button]`; `SpeciesLinks` gets a leading switch with `border-muted text-slate line-through` styling when visited.
- `ExplorerPanel` renders `<iframe sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-downloads">` with empty src when no active link, fallback `<a target="_blank" rel="noopener noreferrer">Open in new tab</a>` rendered OUTSIDE the iframe on `addEventListener('error')`. Mobile peek-card below 640px breakpoint.
- Strict RED → GREEN TDD per requirement: 4 spec MUST clauses for workspace-explorer pinned by `ExplorerPanel.test.tsx` (sandbox + empty + aria + fallback), `ExplorerPanel.activate.test.tsx` (species vs breadcrumb cell isolation), `ExplorerPanel.mobile.test.tsx` (responsive peek), `a11y.explorer.test.tsx` (axe-core regression).
- 246 → 359 tests across the chain (54 + 58 + 0 + 23 new). 112 → 135 frontend vitest.

# Where

- `taxon/api/workspace.py` — 3 ORM models + 8 resolver helpers + `AQUALIFE_ROOT` env var reader (resolves against PROJECT ROOT, fails 500 with path + cwd if unresolvable / unwritable).
- `taxon/migrate.py` — standalone `{dry-run|apply}` CLI.
- `taxon/api/__init__.py` — FastAPI lifespan wires `Base.metadata.create_all` for the workspace tables.
- `taxon/api/router.py` — 8 endpoints registered before the catch-all.
- `taxon/api/schemas.py` — 5 new Pydantic models (`ExploredResponse`, `SpeciesFolderResponse`, `LinkVisitedResponse`, `LinkVisitedListResponse`, `ExploredListResponse`).
- `taxon/tests/test_workspace_resolver.py`, `test_rebind_after_taxa_id_bump.py`, `test_api_router_workspace.py`, `test_aqualife_root.py`, `test_migrate.py` — backend tests (5 files).
- `frontend/src/store/workspace.ts` — workspaceStore (zustand) with explored / folders / visitedLinks / activeLink + actions.
- `frontend/src/store/speciesKey.ts` — `decodeSpeciesKey` round-trip helper (extracted to satisfy `react-refresh/only-export-components`).
- `frontend/src/api.ts` — `fetchExplored*`, `fetchSpeciesFolder*`, `fetchLinkVisited*` typed wrappers + zod schemas.
- `frontend/src/components/SpeciesList.tsx` — trailing column with explored checkbox + folder badge/button (consumes workspaceStore).
- `frontend/src/components/SpeciesLinks.tsx` — leading visited switch + species-cell click dispatches `setActiveLink` (breadcrumb cells do NOT).
- `frontend/src/components/ExplorerPanel.tsx` — iframe + sandbox + fallback card + empty state + active-link pill + mobile peek-card.
- `frontend/src/App.tsx` — mounts `<ExplorerPanel sticky top-0>` in the right column BELOW `<SpeciesLinks>`.
- `frontend/tests/` — 8 new test files: `api.workspace.test.ts`, `store.workspace.test.ts`, `SpeciesList.workspace.test.tsx`, `SpeciesLinks.visited.test.tsx`, `store.speciesKey.test.ts`, `ExplorerPanel.test.tsx`, `ExplorerPanel.activate.test.tsx`, `ExplorerPanel.mobile.test.tsx`, `a11y.explorer.test.tsx`.
- `openspec/changes/species-folder-explorer/` — proposal + design + tasks + 4 specs + apply-progress-pr1/pr2a/pr2b/pr3 + verify-report-pr1.
- `documents-es/openspec/changes/species-folder-explorer/` — Spanish mirrors of every artifact.
- `docs/design/species-folder-explorer.md` (+ ES mirror) — prescriptive design doc.

# Why

- **Re-bind discipline (`(genus, epithet)` over `taxa.id`)**: the species workspace must survive any future taxonomy rebuild or seed re-import that bumps `taxa.id`. Composite-PK keys are the contract; pinned by `test_rebind_after_taxa_id_bump.py`.
- **No Alembic, runtime `create_all`**: the project explicitly avoids Alembic to keep the dependency surface small. `taxon/migrate.py` is the standalone escape hatch for offline operators; runtime `create_all` handles dev + first-boot cases.
- **Sandbox attrs without `allow-top-navigation`**: prevents the iframe from navigating the SPA itself (a security requirement — embedded sources must not be able to redirect the parent). `allow-modals` also omitted to prevent surprise `alert()` calls from third-party pages.
- **Fallback card OUTSIDE the iframe**: popup-blocker state on the iframe must not hide the recovery action. The `<a target="_blank">` button is rendered as a sibling of the iframe so keyboard focus reaches it regardless of iframe load status.
- **Breadcrumb cells intentionally do NOT activate the iframe**: the breadcrumb-links panel renders a generic `taxon-links` panel without an epithet — clicking those links opens in a new tab (existing behaviour) but does NOT populate `activeLink`. Only species-link cells (which carry the substituted URL) populate it. This prevents the iframe from being hijacked by breadcrumb navigation.
- **4-PR auto-chain split (510 → 418/76/185 LOC)**: the original plan was 3 PRs each ≤ 350 LOC. PR2 ended at 510 LOC end-to-end and was split into PR2a + PR2b to respect the 400-line review budget. PR2a carried the size:exception (418 code / 504 with docs) — strictly TDD tests were the dominant contributor; PR2b + PR3 came in well under budget (76 + 185).
- **Pencil/Stitch design deferred**: per the `arbol-col-browse` precedent, the prescriptive design was captured as a markdown surface brief (`docs/design/species-folder-explorer.md`, 116 LOC) rather than a Pencil `.pen` page. No Pencil MCP available in this session.

# How it works

1. User resolves a species (e.g. Panthera tigris via Cascade → CoL-style TaxonomicTree).
2. SPA mounts `<ExplorerPanel>` in the right column with empty state ("Pick a source to embed"). workspaceStore is empty.
3. User clicks a species cell in `<SpeciesLinks>` for the Wikipedia link. The click handler:
   - calls `useWorkspace.getState().setActiveLink({speciesId, source: 'Wikipedia', url})` → store updates
   - opens the URL in a new tab via `target="_blank"` (existing behaviour preserved)
4. ExplorerPanel re-renders with `src=<url>`, `sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-downloads"`, `aria-label="Embedded search result for Panthera tigris (Wikipedia)"`.
5. Browser sends the request. If the source replies with `X-Frame-Options: SAMEORIGIN` or refuses embedding via CSP, the iframe fires its native `error` event → `addEventListener('error')` handler swaps the iframe for the fallback card with "Wikipedia — this source refuses embedding" + `<a target="_blank" rel="noopener noreferrer">Open in new tab</a>` (rendered outside the iframe, keyboard-reachable, never hidden).
6. If embedding succeeds, the user can interact with the embedded source. Clicking any link inside the embedded page triggers the browser's default download / navigation flow (out of SPA scope per spec §Out of Scope).
7. Meanwhile, the user can:
   - toggle the explored checkbox in `<SpeciesList>` → dispatches `POST /api/explored/{g}/{e}` (idempotent upsert, returns 204)
   - click the folder button in `<SpeciesList>` → dispatches `POST /api/species-folder/{g}/{e}` → creates a folder under `<AQUALIFE_ROOT>/Panthera/tigris/`. Subsequent visits show the badge instead of the button. Returns 409 on duplicate, 404 if species unknown, 500 if `AQUALIFE_ROOT` unwritable.
   - toggle the visited switch in `<SpeciesLinks>` → dispatches `POST/DELETE /api/link-visited/{g}/{e}/{src}` (idempotent 204). Visited sources get `border-muted text-slate line-through` styling.
8. On SPA reload, `workspaceStore.hydrate()` runs one eager `GET /api/explored/list` + lazy `GET /api/link-visited/{g}/{e}` per resolved species. activeLink resets to null (session-scoped per spec).
9. On mobile (<640px), the right column collapses to a sticky peek-card showing the active link label + "open in new tab" link. The iframe still renders but the dispatch grid is collapsed.

# Workflows

- **Git**: 4 PRs (PR1 backend → PR2a frontend store+rows → PR2b SpeciesLinks → PR3 ExplorerPanel), all stacked-to-main against `develop`, all conventional-commit work-unit commits, no `Co-Authored-By` trailers. PR2a carried an explicit `size:exception` (504 LOC total / 418 code vs 400 budget — strictly TDD tests were the dominant contributor).
- **CI**: backend `python 3.11 + 3.12` runs `ruff format --check` + `ruff check` + `mypy taxon/` + `pytest`. Frontend `node` runs `npm run typecheck` + `npm run lint` + `npm run test` + `npm run build`. All 4 PRs passed green.
- **Migration**: dev / first-boot rely on runtime `create_all`. Offline / CI operators run `python -m taxon.migrate dry-run` to preview, then `apply`. No Alembic.
- **Strict TDD discipline**: each MUST clause from the 4 specs (`species-explored`, `species-folder`, `link-visited`, `workspace-explorer`) has at least one dedicated RED test before the GREEN implementation commit. The `arbol-col-browse` PR3 precedent (transport failures that masked MUST drift) is the reason this discipline exists.
- **Spanish mirrors**: every OpenSpec artifact (`proposal.md`, `design.md`, `tasks.md`, `specs/*/spec.md`, `apply-progress-*.md`, `verify-report-pr1.md`) has a `-es` mirror under `documents-es/openspec/changes/species-folder-explorer/`. Same content, neutral/professional translation, mirrored at write time (not as follow-up).
- **AGENTS.md §2 learn-es**: this entry is the post-merge learn-es for the full change (one entry per closed PR / change, not per commit).

# Key learnings for future agents

1. **Re-bind keys over FKs**: when adding persistence tied to a domain entity, prefer composite natural keys (`(genus, epithet)`) over FK columns into mutable IDs. The discipline is pinned by a test that mutates the surrogate ID and asserts the new table survives — write that test FIRST.
2. **`addEventListener('error')` on iframes, not React `onError`**: jsdom + React 18.3 do not fire synthetic `onError` on `<iframe>` via `fireEvent.error`. Use raw `addEventListener('error', handler)` on the iframe ref. Tests use `fireEvent.error` on the ref's current.
3. **`axeCore.run(container, { iframes: false })` for iframe-rendering tests**: axe-core's iframe traversal crashes in jsdom because the iframe has no `contentDocument`. The iframe-rendering a11y test uses the raw `axeCore.run` with `iframes: false`; empty + fallback states use the standard `axe()` helper. Test-environment limitation, not production concern.
4. **`react-refresh/only-export-components` extraction**: when a `.tsx` file exports both a component and a helper, extract the helper to its own module (`store/speciesKey.ts` here) so the lint rule passes. Pure functions and helpers never cohabit a component file.
5. **`window.matchMedia` stub for breakpoint tests**: `ExplorerPanel.mobile.test.tsx` installs a `window.matchMedia` stub mimicking `max-width: 639px`. jsdom does not ship matchMedia by default; without the stub, the mobile branch never executes.
6. **Size:exception is a PR-split signal, not a code-quality signal**: PR2a was over budget because the strict-TDD test surface for the workspace store + SpeciesList column + axe pinning was dense. The honest move was splitting into PR2a + PR2b at 418/76 LOC, not trimming tests. PR3 came in at 185 LOC because the iframe surface is naturally thin (one component, one mount point).
7. **`POST /api/explored/{g}/{e}` and `POST /api/link-visited/{g}/{e}/{src}` are idempotent upserts (204)**: callers do not need to GET first. The DELETE is also 204 idempotent. This simplifies the frontend store — `markExplored` and `markVisited` are unconditional POSTs.
