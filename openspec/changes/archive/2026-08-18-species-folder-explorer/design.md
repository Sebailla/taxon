# Design: species-folder-explorer

> **Closes issue #68.** Four coupled sub-features ship across 3 chained PRs, each ≤350 LOC.

## 1. Architecture

```
SPA ──► FastAPI ──► schema (3 new tables) ──► SQLite
    ──► workspace.py (resolver + AQUALIFE_ROOT)
    ──► migrate.py (dry-run/apply)
    ──► ./Proyecto-Aqualife/  (filesystem)
```

| Component | Role |
|-----------|------|
| `App.tsx` | Mounts `<ExplorerPanel>`; calls `hydrate()` on mount. |
| `workspaceStore` (zustand) | Truth for explored/folders/visited Maps + activeLink. Optimistic + reconcile. |
| `taxon/api/workspace.py` | Resolves species via `resolve_path_by_display_level`; re-binds FK by `(genus, epithet)`; reads `AQUALIFE_ROOT`; `Path.mkdir(parents=True, exist_ok=True)`. |
| `taxon/schema.py` (+3) | `species_explored`, `species_folders`, `link_visited`. FKs to `taxa.id`; re-bind columns. |
| `taxon/migrate.py` | `python -m taxon.migrate {dry-run\|apply}` calls `create_all` for 3 new tables only. |
| `lifespan` | Extends `taxon/api/__init__.py:140-145` so all SQLite engines call `create_all` at app start. |

## 2. Storage

```sql
CREATE TABLE species_explored (
  genus TEXT NOT NULL, epithet TEXT NOT NULL,
  explored_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (genus, epithet));
CREATE TABLE species_folders (
  genus TEXT NOT NULL, epithet TEXT NOT NULL,
  path TEXT NOT NULL UNIQUE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (genus, epithet));
CREATE TABLE link_visited (
  genus TEXT NOT NULL, epithet TEXT NOT NULL,
  source_label TEXT NOT NULL,
  visited_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (genus, epithet, source_label));
CREATE INDEX ix_link_visited_source ON link_visited(source_label);
CREATE INDEX ix_species_explored_ge ON species_explored(genus, epithet);
CREATE INDEX ix_species_folders_ge  ON species_folders(genus, epithet);
```

`(genus, epithet)` columns exist because `taxon/import_data.py` rebuilds `taxa` on every run, bumping `taxa.id` — pure FKs would orphan on re-import. `link_visited` keys on `(species_id, source_label)` (template-stable; URLs change per substitution).

## 3. API contract

All endpoints registered BEFORE the `/{path:path}/taxon-links` catch-all at `router.py:834-894`.

| Method | Path | Status |
|--------|------|--------|
| POST   | `/api/explored/{g}/{e}`            | 200 / 404 |
| DELETE | `/api/explored/{g}/{e}`            | 204 (idempotent) |
| GET    | `/api/explored/list`               | 200 `{species:[]}` |
| POST   | `/api/species-folder/{g}/{e}`      | 201 / 409 / 500 |
| GET    | `/api/species-folder/{g}/{e}`      | 200 / 404 |
| POST   | `/api/link-visited/{g}/{e}/{src}`  | 204 / 404 / 422 |
| DELETE | `/api/link-visited/{g}/{e}/{src}`  | 204 (idempotent) |
| GET    | `/api/link-visited/{g}/{e}`        | 200 `{sources:[]}` |

Uniform `ErrorResponse` body `{"detail": str}`. New Pydantic: `ExploredResponse(SpeciesLookupResponse)`, `SpeciesFolderResponse`, `LinkVisitedItem`, `LinkVisitedResponse`, `ExploredListResponse`.

## 4. Frontend state

`frontend/src/store/workspace.ts` (zustand), sibling to `cascadePath` + `taxonomicTree`:

```ts
interface WorkspaceState {
  explored: Map<string, {explored_at: string}>;        // key = `${g}|${e}` (URL-encoded)
  folders:  Map<string, {path: string}>;
  visited:  Map<string, Set<string>>;                  // key → set of source_label
  pending:  {explored: Set<string>; folders: Set<string>; visited: Set<string>};
  activeLink: {speciesKey: string; source: string; url: string} | null;
  markExplored/unmarkExplored/createFolder/markVisited/unmarkVisited/setActiveLink/hydrate;
}
```

Every mutation: optimistic Map/Set update → fire → reconcile on 2xx → rollback + toast on non-2xx. Hydrate on `App.tsx` mount: one `GET /api/explored/list` + lazy per-species `GET /api/link-visited/{g}/{e}`. `cascadePath` untouched. `activeLink` only fires from `SpeciesLinks` species-panel clicks.

## 5. UI flow

**SpeciesList row trailing column** (PR2): right of `MarkerBadges`, outside the row `<button>`, `e.stopPropagation()` so row click still fires `taxon:select`. States: explored checkbox + `Create folder` button (no row) OR + `📁 folder` badge (row exists, non-clickable).

**SpeciesLinks cell leading column** (PR2): `<input type="checkbox" role="switch" aria-checked aria-label="Mark {source} as visited">` outside the `<a>`. When visited, cell flips to `border-muted text-slate line-through`. `target="_blank"` anchor stays.

**ExplorerPanel** (PR3): new component in right column, `sticky top-0`, below `<SpeciesLinks>`. States: empty (`activeLink === null` → "Pick a source to embed."), iframe (`sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-downloads"`, `aria-label="Embedded search result for {genus} {epithet} ({source})"`, `onError` → fallback), fallback (amber card + `<a target="_blank" rel="noopener noreferrer">Open in new tab</a>` OUTSIDE the iframe for popup-blocker resilience).

## 6. `AQUALIFE_ROOT`

`resolve_aqualife_root()`: (1) `os.environ.get("AQUALIFE_ROOT", None)` → default `"./Proyecto-Aqualife/"`; (2) resolve relative paths against **project root** (NOT `cwd`) — walk up from module `__file__` to `pyproject.toml`; (3) `Path(root).mkdir(parents=True, exist_ok=True)`; (4) `PermissionError` → `APIError(detail="AQUALIFE_ROOT not writable: <path> from cwd <cwd>", status_code=500)`. Pinned tests: subfolder, unwritable, env var absolute.

## 7. Migration

**In lifespan**: extend `taxon/api/__init__.py:_lifespan` so all SQLite engines call `Base.metadata.create_all(engine)` (currently `:memory:` only). Idempotent — skips existing tables.

**Standalone `taxon/migrate.py`**: `python -m taxon.migrate {dry-run|apply}` reads `TAXON_DATABASE_URL`, inspects the 3 missing tables, prints summary (dry-run) or applies. No Alembic.

## 8. PR split + risk

| PR | Scope | LOC | Risk | Key tests | Rollback |
|----|-------|-----|------|-----------|----------|
| **PR1 backend** | 3 ORM + workspace.py + 7 endpoints + lifespan + migrate.py + schemas + 3 test files | **~310** | Med | `test_workspace_resolver.py` (~10), `test_api_router_workspace.py` (~8), `test_migrate.py` (~3) | `git revert`; tables additive |
| **PR2 frontend store + rows** | workspaceStore.ts + api.ts + SpeciesList trailing + SpeciesLinks leading + 4 vitest | **~280** | Med | `workspace.store.test.ts`, `api.workspace.test.ts`, `SpeciesList.workspace.test.tsx`, `SpeciesLinks.visited.test.tsx` | `git revert`; store additive |
| **PR3 explorer + design** | ExplorerPanel.tsx + App.tsx mount + test + design doc + ES mirror + learn-es | **~150 code + ~1200 docs** | Low | `ExplorerPanel.test.tsx` (iframe src / sandbox / aria-label / fallback) | `git revert`; mount no-op |

Each ≤350 LOC. `auto-chain`: PR1 → PR2 → PR3.

## 9. Drift recovery

`sdd_task_result_empty` (transport failure) masked spec drift in `arbol-col-browse` PR3. **Every MUST requirement gets a dedicated RED test pinned before the green commit.**

**~35 pinned tests, one per WHEN/THEN clause** in the 4 specs (`species-folder`, `link-visited`, `species-explored`, `workspace-explorer`). Key inventory: `test_post_species_folder_{returns_201_with_path, repeat_returns_409}`, `test_resolve_root_{from_subfolder_uses_project_root, unwritable_returns_500}`, `test_rebind_after_taxa_id_bump`, `test_ascii_segments_join_verbatim`, `test_{dry_run_reports_missing_tables, apply_creates_three_tables, fresh_db_serves_after_lifespan}`, `test_post_{explored, link_visited}_{returns_*, idempotent}`, `test_delete_*_{returns_204, missing_returns_204}`, `test_get_*_list_{200, empty}`, `test_*_keys_on_source_not_url`, `test_iframe_sandbox_attribute_exact`, `test_{empty_state_when_no_active_link, click_sets_active_link, breadcrumb_link_does_not_activate, fallback_on_iframe_error, fallback_button_keyboard_reachable, aria_label_updates_on_active_link_change, panel_mounted_in_right_column_sticky}`, `test_hydrate_restores_explored_after_reload`. A11y: `*.a11y.test.tsx` per surface (axe-core 0 violations).

## 10. Out of scope

Cloud sync, multi-device, auth. Subspecies folder nesting. `Content-Disposition` interception. Auto-mark visited on click. `taxa.is_explored` column. Alembic dependency. `.pen` page (Pencil MCP disabled; markdown + audit IS the design surface). `GET /api/link-visited/list` (per-species hydrate only).

## 11. Phase 4 (PR3) implementation note

The prescriptive design became the following code surface in PR3 of #68
(see `apply-progress-pr3.md` for the full closure log):

### 11.1 `ExplorerPanel.tsx`

Renders the iframe + sandbox + fallback card + mobile peek-card + active-link
pill. Subscribes to `workspaceStore.activeLink`. The fallback card is rendered
ONLY when the iframe fires its native `error` event (Wikipedia / Scholar / BHL
all send `X-Frame-Options: SAMEORIGIN`); the iframe is hidden via
`style={{ display: "none" }}` and the fallback `<a target="_blank" rel="noopener
noreferrer">Open in new tab</a>` takes its place. The fallback anchor is the
first tab stop inside the card so keyboard focus lands on it first.

### 11.2 `decodeSpeciesKey` helper

`frontend/src/store/speciesKey.ts` exports the round-trip helper for the
URL-encoded `${genus}|${epithet}` key. The store writes
`encodeURIComponent("${genus}|${epithet}")`; the panel reads back via
`decodeURIComponent` + `split("|")`. The helper is exported from a separate
file because the `react-refresh/only-export-components` lint rule forbids
mixing component and helper exports in the same `.tsx` file.

### 11.3 `SpeciesLinks` species-cell click

The `SourceLink` component now reads `setActiveLink` and dispatches
`{speciesKey: key, source: link.source, url: link.url}` on click when both
`genus` and `epithet` are known. The breadcrumb-links panel (no genus / epithet
props) does NOT mutate `activeLink` because the `key` is `null` and the
`setActiveLink` call is skipped. The `target="_blank"` anchor behaviour is
preserved in both branches.

### 11.4 `App.tsx` mount

`<ExplorerPanel>` is mounted inside the right column, wrapped in a
`<div className="sticky top-0">` so the embedded page stays visible while the
user scrolls the dispatch grid. The mount does NOT move the existing
`<Breadcrumb>` / `<SpeciesLinks>` rendering — the panel is an additive slot
below them.

### 11.5 Strict TDD discoveries

- jsdom + React 18.3 does NOT fire React's synthetic `onError` on `<iframe>`
  via `fireEvent.error`. The implementation switched to a raw
  `addEventListener('error', handler)` on the iframe ref, which matches what
  real browsers do (the spec says the listener attaches at the raw iframe
  element, not the synthetic dispatch root).
- axe-core's iframe traversal crashes in jsdom because the iframe has no
  `contentDocument`. The a11y test for the iframe-rendering state uses
  `axeCore.run(container, { iframes: false })` instead of the standard `axe()`
  helper. Empty + fallback states use the standard helper because they have no
  iframe content to recurse into.
- 23 new tests across 4 files pin the 5 MUST clauses from
  `workspace-explorer/spec.md` (sandbox + empty state + active-link wiring +
  breadcrumb isolation + fallback + aria-label + mobile peek + axe-core).
  135 tests pass in total.