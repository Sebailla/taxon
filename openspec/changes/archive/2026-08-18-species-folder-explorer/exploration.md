# Exploration — species-folder-explorer

> Closes issue #68. Four coupled sub-features (A. explored flag, B. folder creation, C. per-link switches, D. embedded explorer) for the `species-folder-explorer` change, planned AFTER `arbol-col-browse` (issue #67) lands in `develop` (PR #69 merged at `3fc2eb1`, archived at `openspec/changes/archive/2026-08-16-arbol-col-browse/`).

## Current state

### 1. `SpeciesList.tsx` shape (`frontend/src/components/SpeciesList.tsx`)

- **Component contract** (`SpeciesListProps`, lines 18–27): `rows: TaxonResponse[]`, `status: "idle" | "loading" | "error"`, `cursor: string | null`, `parentSegments: string[]`, `breadcrumb: string[]`, optional `onLoadMore`.
- **State**: pure render — no internal state, no hooks consumed. All state is owned by `App.tsx` and passed in.
- **Row click contract** (`dispatchTaxonSelect`, lines 64–70): on click, dispatches the `taxon:select` window CustomEvent with `{row, breadcrumb, parentSegments}` validated through the Zod `TaxonSelectDetailSchema` in `frontend/src/events/taxonSelect.ts`. `App.tsx` (lines 70–93) listens for `TAXON_SELECT_EVENT` and updates `resolved` + `parentSegments`.
- **Row layout** (lines 60–82): a `<ul aria-label="Species list">` of `<button type="button">` rows. Each row renders `name` (`font-mono text-sm text-navy`, truncated) and conditional `display_name` (when `display_name !== name`), with a trailing `<MarkerBadges>` slot.
- **Marker badges** (`MarkerBadges`, lines 97–142): four flags from `TaxonResponse`: `is_extinct` (`† extinct`, red), `is_synonym` (`= synonym`, amber), `is_uncertain` (`? uncertain`, slate), `is_unassigned` (`unassigned`, slate). The slot is a `flex gap-1` chip group on the right of each row.
- **Empty/loading/error states** (lines 30–52): distinct `<p>` cards with `rounded-card border` styling; `cursor` non-null triggers a `Load more` button below the list.
- **Where new columns attach**: the row is currently `[name / display_name] [MarkerBadges]`. A trailing column for `[explored-checkbox] [folder-badge-or-button]` will sit on the right of `MarkerBadges`; a leading switch column for `[visited]` does **NOT** apply here (sub-feature C targets `SpeciesLinks`, not `SpeciesList`).

### 2. `SpeciesLinks.tsx` shape (`frontend/src/components/SpeciesLinks.tsx`)

- **Component contract** (`SpeciesLinksProps`, lines 19–21): single `links: SearchLinkItem[]` prop.
- **Render layout** (lines 32–44): `<section aria-label="Search source dispatch">` with a 4-column responsive grid (`grid-cols-2 sm:grid-cols-3 lg:grid-cols-4`), each cell rendered by `SourceLink` (lines 47–65).
- **Anchor semantics**: `target="_blank" rel="noopener noreferrer"` — opens in new tab, opener hijacking prevented.
- **Sci-hub visual separation** (line 48 + line 58): `border-red` instead of `border-border`. **No state today** — the link is always clickable.
- **`SearchLinkItem` interface** (`frontend/src/api.ts`, lines 82–86): `{ source: string; label: string; url: string }`. `source` is the canonical name from `docs/sources/templates.md` ("Wikipedia", "Google", "BHL", "ResearchGate", "Plos", "Academia", "Scielo", "Scholar", "Youtube", "Zootaxa", "Photos", "Sci-hub", "Scribd" — 13 items). `label == source` for the species-links case; per-taxon links carry the same shape.
- **Two callers** (both render `<SpeciesLinks>`):
  1. `App.tsx:205` — `links` state from `fetchLinks(parentSegments, epithet)` (species-links panel, last-clicked wins over the breadcrumb panel).
  2. `App.tsx:219` — `breadcrumbLinks.data.links` from `fetchTaxonLinks(cascadePath)` (per-taxon breadcrumb-links panel from `breadcrumb-dinamico` PR #66).
- **Sub-feature C attaches here**: each cell needs a leading `[visited]` switch; the visited-state must persist across both consumers (the species-links panel and the per-taxon breadcrumb-links panel).
- **Sub-feature D attaches here**: the currently-active link URL must be available to the `<ExplorerPanel>` so the iframe can load it. The cleanest seam is to lift the active-link state into a store the explorer subscribes to.

### 3. `resolve_path_by_display_level` (`taxon/api/hierarchy.py`, lines 292–338)

- **Signature**: `def resolve_path_by_display_level(session: Session, segments: list[str]) -> TaxonRow | None`.
- **Returns**: `TaxonRow` (frozen dataclass at lines 71–88, fields `id`, `name`, `display_name`, `rank`, `parent_id`, plus the four marker flags), or `None` when any segment fails to resolve.
- **Error semantics**: `None` propagates to the caller; the router raises `NotFoundError(f"taxon not found: {segments[-1]!r}")` (see `router.py:184` and `router.py:884`). There is no 422 for bad input; the resolver is total (returns `None` on every failure mode).
- **Walk mechanics**: each segment is matched against `Taxon` whose `display_level` is either one bucket below the previously-matched row's bucket OR the same bucket (off-tuple intermediates: subphylum, infraphylum, parvphylum, subfamily, tribe, subtribe, infratribe). The first segment anchors unanchored (parent unknown); subsequent segments anchor on the previous match's `id`. Case-insensitive name match via `func.lower(Taxon.name) == segment.lower()`.
- **Bucket order** (`_DISPLAY_LEVELS_IN_ORDER`, lines 204–213): `("realm", "kingdom", "phylum", "class", "order", "family", "genus", "species")`. First segment anchors on `kingdom`.
- **Reuse story for sub-feature B (folder creation)**: the endpoint receives `(genus, epithet)` as path params (mirroring `/{kingdom}/.../{genus}/{epithet}`'s breadcrumb-shaped lookup), resolves the full breadcrumb via `resolve_path_by_display_level([kingdom, phylum, class, order, family, genus, epithet])` (where the epithet is the last segment at the species bucket), and joins `taxon.name` segments with `os.sep` to build the folder path. The function does NOT synthesize a Biota root — the resolver starts at the kingdom bucket. The breadcrumb builder at `taxon/api/species.py::build_breadcrumb` (re-exported) gives the same path in the form `App.tsx` consumes.

### 4. `taxon/api/router.py` + `taxon/api/schemas.py` surface

**Routers (16 GET, 0 POST, 0 DELETE — verified line-by-line against `router.py`):**

| Method | Path | Function | Lines | Notes |
|--------|------|----------|-------|-------|
| GET | `/_meta` | `api_meta` | 132–135 | Smoke probe; returns `{"phase": "2C"}` (stale, but kept per docstring). |
| GET | `/path-children` | `path_children` | 138–185 | Query: `path: str`. Pydantic: `PathChildrenEnvelope`. |
| GET | `/species-list` | `species_list` | 188–246 | Query: `path: str, include: str \| None, cursor: str \| None`. Pydantic: `SpeciesListResponse`. |
| GET | `/kingdoms` | `list_kingdoms` | 249–263 | Synthesises Biota + Viruses with opaque CLB ids `5T6MX` / `V`. |
| GET | `/{kingdom}/phyla` | `list_phyla` | 295–304 | Legacy path-shape. |
| GET | `/{kingdom}/{phylum}/classes` | `list_classes` | 307–317 | Legacy path-shape. |
| GET | `/{kingdom}/{phylum}/{class_name}/orders` | `list_orders` | 320–332 | Legacy path-shape. |
| GET | `/{kingdom}/{phylum}/{class_name}/{order_name}/families` | `list_families` | 335–347 | Legacy path-shape. |
| GET | `/{kingdom}/{phylum}/{class_name}/{order_name}/{family_name}/genera` | `list_genera` | 350–367 | Legacy path-shape. |
| GET | `/{kingdom}/{phylum}/{class_name}/{order_name}/{family_name}/{genus_name}/species` | `list_species` | 370–427 | Legacy path-shape, paginated, include filter. |
| GET | `/{kingdom}/.../{genus_name}/{epithet}` | `lookup_species` | 541–574 | Breadcrumb-shaped species lookup. |
| GET | `/species/{genus_name}/{epithet}` | `lookup_species_by_pair` | 577–602 | Pair-only; can return 409 with `candidates[]`. |
| GET | `/{kingdom}/.../{genus_name}/{epithet}/links` | `species_links` | 605–647 | The 13-link dispatch (issue #68 calls it 12; actual count is 13 per `templates.md`). |
| GET | `/tree/children` | `get_tree_children` | 676–770 | Parent-id tree expand; `parent_id=0` for roots. |
| GET | `/tree/search` | `get_tree_search` | 773–831 | "Find taxon" autocomplete. |
| GET | `/{path:path}/taxon-links` | `taxon_links` | 834–894 | Per-taxon dispatch for breadcrumb segments (no epithet). |

**Routing conventions** (verified throughout):
- `router = APIRouter(prefix="/api")` (line 107). Every endpoint lives under `/api`.
- Path params use `Annotated[..., Path(min_length=1)]`; `class_name`, `order_name`, `family_name`, `genus_name`, `epithet` carry `alias=...` to keep the Python identifier readable while keeping the URL segment name unchanged.
- Query params use `Annotated[..., Query(description=...)]` with `min_length` / `max_length` / `ge` / `le` validators where applicable.
- Session dep: `Annotated[Session, Depends(get_db)]`.
- Error envelopes: `NotFoundError` → 404, `AmbiguousError` → 409 with `candidates[]`; both render via the `_error_response` helper in `taxon/api/__init__.py:106-123` (uniform `{detail: str, candidates?: [...]}` body).
- Route-ordering matters: tree endpoints MUST be registered before the `/{path:path}/taxon-links` catch-all or the literal `tree/children` will be eaten. The same applies to any new endpoint with literal segments — register BEFORE catch-alls.

**Pydantic models** (`taxon/api/schemas.py`, all in `__all__`):
- `TaxonResponse` (line 46) — single taxon: `id: int|str`, `name`, `display_name`, `rank`, `parent_id`, four marker flags.
- `SpeciesPathResponse` (line 72) — materialised breadcrumb with rank columns.
- `MarkerFlags` (line 139) — nested marker group.
- `SpeciesListItem` (line 153) — same shape as `TaxonResponse` plus `parent_segments: list[str]`.
- `SpeciesListResponse` (line 178) — `{items, next_cursor}`.
- `SpeciesLookupResponse` (line 191) — `{id, canonical_name, display_name, markers, breadcrumb}`.
- `AmbiguityCandidate` (line 207) — 409 candidate payload.
- `SearchLinkItem` (line 221) — `{source, label, url}` (the `link_visited` table will key on `source`).
- `LinksResponse` (line 235) — `{species, links}` envelope.
- `TaxonLinksResponse` (line 248) — `{taxon, links}` envelope (per-taxon dispatch).
- `NextTier` (line 264), `PathChildrenEnvelope` (line 293) — cascade envelope.
- `TreeNodeResponse` (line 318), `TreeChildrenResponse` (line 336), `TreeSearchHit` (line 352), `TreeSearchResponse` (line 372) — tree surface.
- `_ORMBase` mixin (line 34) carries `model_config = ConfigDict(from_attributes=True)`.
- `HealthResponse` (line 100), `CandidateRef` (line 106), `ErrorResponse` (line 118) — health + error envelopes.

**No `POST` / `DELETE` exists today.** The change adds the first POST/DELETE endpoints; the pattern for `Annotated[..., Path]` + `Depends(get_db)` + raising `NotFoundError`/`APIError` carries over verbatim.

### 5. Alembic migrations

**There are NO Alembic migrations in this project.** The only DB-management code paths are:

- `taxon/schema.py` (full file, 55 lines) — SQLAlchemy 2.0 typed DeclarativeBase with two models: `Taxon` (table `taxa`) and `SpeciesPath` (table `species_paths`). The `Base.metadata.create_all(engine)` call lives at `taxon/api/__init__.py:145` and ONLY fires for `sqlite:///:memory:` (tests). File-backed engines assume the schema already exists (created out-of-band by `python -m taxon.import_data`).
- `taxon/import_data.py` (14369 bytes) — GBIF/WoRMS dataset importer; builds the `taxa` + `species_paths` tables at import time. **No `species_folders`, `link_visited`, `explored_flags`, or `is_explored` columns exist** — verified by `sqlite3 data/col.db ".tables"` returning only `species_paths` and `taxa`, and `rg 'is_explored|explored_flags|species_folders|link_visited'` returning zero matches in `taxon/` or `docs/`.

**Implication for issue #68's milestone list**: the milestone "Alembic migration `0010_add_species_folders_link_visited_explored.py`" must be replaced with **either**:
- (a) a hand-rolled `python -m taxon.migrate` script that uses `Base.metadata.create_all(...)` for the new tables + an `ALTER TABLE taxa ADD COLUMN is_explored BOOLEAN NOT NULL DEFAULT 0` if the explored flag is materialised on `taxa`, **or**
- (b) a runtime-only approach: the new tables are created at app startup via `Base.metadata.create_all(engine)` in the lifespan (with a one-line schema-version check), and the change ships with no migration script.

This is a real fork — `sdd-propose` must decide.

### 6. Frontend store patterns

**`frontend/src/store/cascadePath.ts` (62 lines, full file):**

- Zustand `create<CascadePathState>` with the state interface (lines 27–30): `{path: string[], setPath(path: string[]): void}`.
- `setPath` is a no-op replace (lines 52–61): when `arraysEqual(prev.path, next)` it returns `prev` so subscribers don't refire on a redundant call.
- Export is `useCascadePath` (line 50) — a typed hook that doubles as the vanilla store (`useCascadePath.getState()`, `useCascadePath.subscribe()`).
- The same file is imported by `App.tsx` (line 39), `frontend/src/components/Breadcrumb.tsx` (no — breadcrumb is local-prop), and tests use the store directly via `useTaxonomicTree.setState(...)` patterns.

**`frontend/src/store/taxonomicTree.ts` (267 lines, full file):**

- Zustand `create<TreeState>` with the full interface (lines 43–67): `childrenByParentId: Map<number, TreeNodeResponse[]>`, `expandedIds: Set<number>`, `rootIds: number[] | null`, `loadingParentIds: Set<number>`, `errorByParentId: Map<number, string>`, `includeExtinct: boolean`; actions `loadRoots`, `ensureChildren`, `toggleExpand`, `setError`, `clearError`, `revealNode`, `setIncludeExtinct`.
- Pattern: every mutation constructs a fresh `Map` / `Set` (e.g. lines 90–93 `const next = new Map(get().childrenByParentId); next.set(0, result.data.children); set({...})`) so the Zustand shallow-equality check fires on real changes only.
- Async actions are `Promise<void>`-returning; the caller awaits the promise (e.g. `TaxonomicTree.test.tsx` awaits `revealNode`).

**Plan for a new `workspaceStore`** (`frontend/src/store/workspace.ts`):

- Shape (proposed): `{exploredBySpeciesId: Map<number, boolean>, foldersBySpeciesId: Map<number, string>, visitedByKey: Map<string, Set<string>>, activeLink: {speciesId: number, source: string, url: string} | null, setExplored(speciesId, value), createFolder(speciesId): Promise<void>, setFolderPath(speciesId, path), toggleVisited(speciesId, source), setActiveLink(speciesId, source)}`.
- Persistence model: the store is the cache; the backend is the source of truth. Every mutation calls a backend endpoint that returns the canonical row, then the store mirrors it. A single `hydrate()` action fetches all the user's workspace rows on app mount (`GET /api/workspace?genus=…&epithet=…` for the currently-resolved species, scoped to keep the wire payload small; or `GET /api/explored/list` + `GET /api/link-visited/list` for a full hydrate).
- The store sits alongside `cascadePath` and `taxonomicTree`; no merging into either. The `SpeciesList` row reads `useWorkspace((s) => s.exploredBySpeciesId.get(row.id))` and calls `setExplored(row.id, !current)` on checkbox change. `SpeciesLinks` reads `useWorkspace((s) => s.visitedByKey.get(`${speciesId}`))` (a `Set<string>` of source labels).
- The iframe's URL is `useWorkspace((s) => s.activeLink?.url ?? null)`; setting activeLink is the act of clicking a `SpeciesLinks` cell (the click handler does both `window.open(url, "_blank", "noopener,noreferrer")` and `setActiveLink(speciesId, source, url)`).

### 7. `./Proyecto-Aqualife/` filesystem convention

- **Does not exist** on the local filesystem today (`ls Proyecto-Aqualife` → not present). The project also has no `os.makedirs('./Proyecto-Aqualife/...')` calls anywhere in the repo — `rg 'AQUALIFE_ROOT|Proyecto-Aqualife|os\.makedirs'` returns zero matches.
- **Env var reading pattern** (verified in `taxon/api/__init__.py:59` and `taxon/import_data.py:203,208`): `os.environ.get("TAXON_*", DEFAULT)` — same shape as `TAXON_DATABASE_URL`, `TAXON_TEMPLATES`, `TAXON_DATASET`, `TAXON_DATABASE`. The convention is `TAXON_*` env vars with a relative-path default that resolves against `Path(".")`.
- **No `python-dotenv`** in the project dependencies (verified in `pyproject.toml:11-23`: only `fastapi`, `pydantic`, `sqlalchemy`, `uvicorn`). The env var pattern is `os.environ.get()` directly — no `.env` loader.
- **Default root** (per issue #68's body): `./Proyecto-Aqualife/` relative to the project root (`/Users/<user>/Developer/taxon/`).
- **Plan for the `AQUALIFE_ROOT` env var**: add `os.environ.get("AQUALIFE_ROOT", "./Proyecto-Aqualife/")` to a new helper module `taxon/api/workspace.py` (or `taxon/api/folders.py`), exported from `taxon.api.__init__`. On `create_app` startup, ensure the directory exists with `Path(root).mkdir(parents=True, exist_ok=True)` and reject an unwriteable root with a clear error envelope. Mirror the `TAXON_DATABASE_URL` precedent: env var + sensible default + no dotenv.

### 8. Search-source templates (`docs/sources/templates.md`)

13 templates, in row order, parsed by `taxon/search_links.py::load_templates` (the regex at line 11 enforces the table syntax; the function at line 41 raises `ValueError` if `len != 13`):

| # | source (canonical key) | URL pattern |
|---|------------------------|-------------|
| 1 | Wikipedia | `http://es.Wikipedia.org/wiki/Special:Search?search={q}` |
| 2 | Google | `http://Google.com/search?q={q}` |
| 3 | BHL | `http://biodiversitylibrary.org/search?SearchTerm={q}` |
| 4 | ResearchGate | `http://researchgate.net/search?q={q}` |
| 5 | Plos | `http://journals.plos.org/plosone/search?filterJournals=PLoSONE&q={q}&page=1` |
| 6 | Academia | `http://academia.edu/people/search?utf8=%E2%9C%93&q={q}` |
| 7 | Scielo | `http://search.scielo.org/?q={q}` |
| 8 | Scholar | `http://scholar.google.com/scholar?hl=es&as_sdt=0%2C5&q={q}&btnG=` |
| 9 | Youtube | `http://youtube.com/results?search_query={q}` |
| 10 | Zootaxa | `http://mapress.com/j/zt/search/search?query={q}` |
| 11 | Photos | long Google Images URL (preserved verbatim) |
| 12 | Sci-hub | `https://sci-hub.ru/match/{q}` |
| 13 | Scribd | `https://es.scribd.com/search?query={q}` |

The `link_visited.source_label` column is exactly the `source` string above. The `SpeciesLinks` cell renders the `label` (which is `source` for both endpoints per `search_links.py:53` — `SearchLink.label == source`).

**Note for #68's wording**: the issue says "12 dispatch URLs" and "13 links". Both are correct — the species-links endpoint emits 13 (per `templates.md` and the `len(templates) != 13` guard at `search_links.py:41`), while older comments in `router.py:17,619` describe them as "12 dispatch URLs" because the original spreadsheet shipped with 12 and Sci-hub was added later. Use **13** everywhere in the new spec.

### 9. Iframe sandbox + Content-Disposition (research note, not exhaustive)

The design phase MUST close these specifics; the exploration captures only the territory:

- **Iframe sandbox attributes**: a permissive-but-not-top-level-navigation combo for downloads is `sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-downloads"`. The flags enable: same-origin (so the iframe's scripts can read/write the iframe's own cookies/storage), scripts (so the third-party page works), forms (so search inputs work), popups (so `<a target="_blank">` clicks inside the iframe open in a new tab), and downloads (so a `<a href="...pdf" download>` triggers a download). The flag NOT enabled is `allow-top-navigation` — the iframe must not be able to navigate the parent (prevents hijacking the SPA via the embedded source).
- **Cross-origin download routing**: `<a href="..." download>` inside the iframe fires a download event; the browser handles the file system write. The Content-Disposition header (`attachment; filename="..."` vs `inline`) controls whether the iframe treats the response as a download or a navigation. For the user's "save into the species folder" workflow, the iframe's default browser download is the right primitive — the SPA's iframe does not need to intercept the download via `Content-Disposition` parsing. A drag-and-drop from the iframe into the OS file explorer works because the iframe runs in a separate browsing context.
- **X-Frame-Options / CSP frame-ancestors**: many sites (Wikipedia, Google Scholar, BHL) send `X-Frame-Options: SAMEORIGIN` or `Content-Security-Policy: frame-ancestors 'self'` and will refuse to render inside any iframe. The fallback is `target="_blank"` (already wired) — the iframe can show a "this source refuses embedding" message with a button that opens the URL in a new tab. Issue #68 acknowledges this explicitly ("accept those limitations").
- **Browser limitations**: Safari and Firefox both gate iframe-initiated downloads more strictly than Chrome. The SPA's `target="_blank"` fallback covers the failure mode uniformly.
- **Sandboxed iframe + the SPA's own React tree**: the SPA MUST not place the iframe inside the `<form>` / `<dialog>` / `<main>` `role=main` element if it intends to render the explorer's content; an `aria-label` on the iframe (`aria-label="Embedded search result for {species}"`) is required to pass axe-core.

### 10. Pencil MCP availability

- **The Pencil MCP is disabled in this session.** A direct probe (`pencil_get_app_state`) returned `MCP error -32603: failed to connect to running Pencil app: visual_studio_code after 3 retries: transport not connected to app: visual_studio_code`. `list_mcp_resources` confirms `pencil` is reachable but has no resource surface to query.
- **Precedent**: `arbol-col-browse` (issue #67, archived 2026-08-16) hit the exact same state and resolved it by writing a prescriptive `docs/design/taxonomic-tree-browse.md` (784 lines) instead of a `.pen` page. The `archive-report.md:115` notes the deferral verbatim and reserves the right to redo the `.pen` page in a future slice.
- **Carry the pattern forward**: this change will NOT have a `.pen` page. The design phase writes `docs/design/species-folder-explorer.md` + Spanish mirror `documents-es/docs/design/species-folder-explorer-es.md`, with line-by-line implementation specs for the new components (`ExplorerPanel.tsx`, the new switches in `SpeciesList` / `SpeciesLinks`). The `impeccable` skill audit is still applied to the prescriptive markdown (per AGENTS.md §5 the audit happens BEFORE implementation — the markdown is the design input).

### 11. `data/col.db` schema surface (verified `sqlite3 data/col.db ".schema"`)

**Only two tables exist**:

- `taxa` — 11 columns: `id INTEGER PK autoincrement`, `source_id VARCHAR NOT NULL UNIQUE` (CLB/CoL identifier, e.g. `5T6MX`), `parent_id INTEGER FK→taxa.id`, `rank VARCHAR NOT NULL`, `name VARCHAR NOT NULL`, `display_name VARCHAR NOT NULL`, `display_level VARCHAR` (NULL in `col.db`, populated in `taxon.db`; resolved via the `taxonomy_display_level` SQL function), `is_synonym`, `is_extinct`, `is_uncertain`, `is_unassigned` — all `BOOLEAN NOT NULL`. Indices: `ix_taxa_parent_name (parent_id, name)`, `ix_taxa_rank (rank)`, `ix_taxa_display_level (display_level)`.
- `species_paths` — 11 columns: `id INTEGER PK autoincrement`, `species_id VARCHAR FK→taxa.source_id UNIQUE` (note: FK is to `source_id`, not `id`!), `kingdom`, `phylum`, `class_name`, `"order"`, `family`, `genus` — all `VARCHAR NULL`, `species VARCHAR NOT NULL`, `display_name VARCHAR NOT NULL`, plus the four marker flags. Index: `ix_species_paths_species (species)`. **0 rows** in `col.db` (only populated by the WoRMS importer; the CoL re-import left it empty).

**Storage decision for the `explored` flag**: two viable shapes:
- (a) Add `is_explored BOOLEAN NOT NULL DEFAULT 0` to the `taxa` table (denormalised). Pro: single-row reads via the existing `Taxon` ORM model; no join. Con: re-imports (the importer recreates the `taxa` table) wipe the flag — must be re-applied or the importer must be taught to preserve it.
- (b) New `explored_flags(species_id INTEGER FK→taxa.id, explored_at TIMESTAMP)` table. Pro: orthogonal to `Taxon`; re-imports safe. Con: extra join on every species-list row read, or a per-row hydrate (cached in the `workspaceStore`).

**Recommendation for `sdd-propose` to confirm**: option (b) is the safer choice given the project's known import-time schema churn (`taxon/import_data.py` and `taxon/indented_import.py` both build the `taxa` table from scratch on each run — see `learn-es/2026-08-16-arbol-col-browse-pr3-drift-fixes.md` for the data-pipeline fragility). The species_folders and link_visited tables are unambiguously new (no schema churn concerns); the explored flag is the only column-vs-table fork.

**FK target**: the `species_folders.species_id` column must FK to `taxa.id` (autoincrement integer), NOT `taxa.source_id` (CLB opaque string). The `link_visited.species_id` should also FK to `taxa.id` for consistency. The `species_paths.species_id` FK to `source_id` is a precedent only for the importer's projection, not a general rule.

## Integration points

**Backend**:
- `taxon/schema.py` — add three SQLAlchemy models (or extend `MarkerColumns` if option (a) is chosen for explored). Use `Base.metadata.create_all(engine)` semantics; add a migration step or fold into the lifespan.
- `taxon/api/router.py` — register **four new endpoints** BEFORE the `/{path:path}/taxon-links` catch-all (lines 834–894) so the literal route segments aren't shadowed. Each endpoint takes `(genus, epithet)` as path params OR a path-shaped `{path:path}` capture; the proposal phase must pick.
  - `POST /api/explored/{genus}/{epithet}` → toggle explored = True; returns the species row.
  - `DELETE /api/explored/{genus}/{epithet}` → toggle explored = False; returns the species row.
  - `POST /api/species-folder/{genus}/{epithet}` → resolve breadcrumb via `resolve_path_by_display_level`, mkdir `Path(AQUALIFE_ROOT) / "Animalia" / "Chordata" / ... / "Panthera tigris"`, insert `species_folders` row, return `{path: str}`.
  - `GET /api/species-folder/{genus}/{epithet}` → read existing row; 404 if no folder yet.
  - `POST /api/link-visited/{genus}/{epithet}` → upsert `{source, visited_at}`; idempotent.
  - Optional: `GET /api/link-visited/{genus}/{epithet}` → list of `{source, visited_at}` for the species; the SPA hydrates the visited set on mount.
- `taxon/api/schemas.py` — add `ExploredResponse`, `SpeciesFolderResponse`, `LinkVisitedRequest`, `LinkVisitedResponse`. Export from `__all__`.
- `taxon/api/workspace.py` (new) — the resolver: `set_explored`, `unset_explored`, `create_species_folder`, `record_link_visited`, `unrecord_link_visited`, `list_link_visited`. Plus the `AQUALIFE_ROOT` env var reader.

**Frontend**:
- `frontend/src/components/SpeciesList.tsx` — add the trailing `[explored-checkbox] [folder-badge-or-button]` column. New props `onExploredChange(row, value)`, `onCreateFolder(row)`. New `MarkerBadges` doesn't change.
- `frontend/src/components/SpeciesLinks.tsx` — add the leading `[visited]` switch to each `SourceLink`. New props `visited: Set<string>`, `onToggleVisited(source, value)`. The visited styling: `border-muted` + `text-slate` + strikethrough (per issue #68's spec).
- `frontend/src/components/ExplorerPanel.tsx` (new) — `<iframe sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-downloads" src={activeLink?.url ?? ""} aria-label={...} />`. Mounts inside `App.tsx`'s right column. Renders a "no source selected" state when `activeLink` is null. A "X-Frame-Options blocked" fallback renders when the iframe's `onError` fires (the iframe load fails for any reason). The panel is `sticky top-0` so it stays visible while the user scrolls the dispatch grid.
- `frontend/src/store/workspace.ts` (new) — see §6.
- `frontend/src/api.ts` — add `setExplored`, `unsetExplored`, `createSpeciesFolder`, `getSpeciesFolder`, `recordLinkVisited`, `listLinkVisited`, `unrecordLinkVisited`. The `ApiResult<T>` discriminated union stays; new methods follow `fetchRoots`'s shape.
- `frontend/src/App.tsx` — mount `<ExplorerPanel>` below the `<SpeciesLinks>` / `<Breadcrumb>` block; the panel renders whenever `activeLink` is non-null (i.e. the user clicked a link). The `cascadePath` Zustand store stays; no changes to the existing `path:change` listener.

**Tests**:
- Backend (`taxon/tests/`): `test_workspace_resolver.py` (unit, the new helpers), `test_api_router_workspace.py` (integration via FastAPI TestClient + `sqlite:///:memory:` with the new tables created via `Base.metadata.create_all`); expand `test_api_sqlite_only_router.py` if the schema changes.
- Frontend (`frontend/tests/`): `SpeciesList.workspace.test.tsx` (explored checkbox + folder button + reload persistence), `SpeciesLinks.visited.test.tsx` (switch toggle + disabled styling), `ExplorerPanel.test.tsx` (iframe `src` matches the active link; sandbox attributes; aria-label; fallback for X-Frame-Options block), `workspace.store.test.ts` (set / unset / optimistic update / hydrate), `api.workspace.test.ts` (every new method's URL + decode).

**OpenSpec specs** (delta specs, per `openspec/config.yaml`'s archive-required workflow):
- New `openspec/specs/species-folder/spec.md` (sub-feature B: folder creation + persistence).
- New `openspec/specs/link-visited/spec.md` (sub-feature C: per-link visited switch + persistence).
- New `openspec/specs/species-explored/spec.md` (sub-feature A: explored flag + persistence).
- Delta to `openspec/specs/taxonomy-hierarchy/spec.md` (no change — the resolver contract is preserved; this change uses `resolve_path_by_display_level` verbatim).
- Delta to `openspec/specs/species-search-links/spec.md` (no change — the 13-link dispatch stays; only the surrounding UI grows).

**Learn-es entry** (`learn-es/2026-08-15-species-folder-explorer.md` + Spanish mirror `documents-es/learn-es/2026-08-15-species-folder-explorer-es.md`): written after green CI per AGENTS.md §2.

## Constraints discovered

1. **No Alembic** (verified). The migration plan must be a `python -m taxon.migrate` script OR a `Base.metadata.create_all(engine)` call folded into the lifespan for the new tables (the latter is consistent with how the test path bootstraps the schema; the former is consistent with how `taxon/import_data.py` builds the `taxa` / `species_paths` tables out of band).
2. **`Proyecto-Aqualife/` does not exist on the filesystem** (verified). The folder is the user's project-root-relative workspace and will be created on first `POST /api/species-folder/{g}/{e}`.
3. **No `python-dotenv`** in `pyproject.toml`. The env var pattern is `os.environ.get("TAXON_*", DEFAULT)` directly — same as `TAXON_DATABASE_URL`, `TAXON_TEMPLATES`, `TAXON_DATABASE`, `TAXON_DATABASE_URL`.
4. **`cascadePath` store stays** — `App.tsx` is mid-cascade state. The new `workspaceStore` is a separate concern (per-species workspace data) and lives alongside `cascadePath` + `taxonomicTree`. No merging.
5. **`/api/{path:path}/taxon-links` catch-all must stay registered last** (per the regression test `test_api_router_tree::test_tree_endpoints_registered_before_taxon_links_catchall`, see `archive-report.md` for the precedent). Every new workspace endpoint MUST be registered BEFORE that catch-all.
6. **`SearchLink.label == source`** for both endpoints (`search_links.py:53`). The visited state keys on `source`, never on `url` (which changes per substitution).
7. **13 templates, not 12** (issue #68 says both). The canonical count is 13; the comment drift in `router.py:17,619` is stale.
8. **`TaxonRow` is a frozen dataclass**, not an ORM row. New helpers in `taxon/api/workspace.py` MUST construct `TaxonRow` via the same `_to_row` pattern at `hierarchy.py:92` (or import the helper).
9. **`Taxon.id` is autoincrement int; `Taxon.source_id` is the CLB/CoL opaque string**. FK targets in the new tables must be `taxa.id` (integer) for `species_folders.species_id`, `link_visited.species_id`, and `explored_flags.species_id` (if option (b) is chosen).
10. **`species_paths` is empty in `col.db`** — the breadcrumb builder at `species.py::build_breadcrumb` walks the parent chain via `Taxon.parent_id`, not via `species_paths`, so the breadcrumb is still resolvable. The new code does NOT depend on `species_paths`.
11. **Pencil MCP disabled** — design goes through `docs/design/species-folder-explorer.md` prescriptive markdown, NOT a `.pen` page (same precedent as `arbol-col-browse`).
12. **Strict TDD active** (`openspec/config.yaml` `strict_tdd: true`): every task writes the test file first (RED), asserts failure, implements minimum (GREEN), refactors. The previous `arbol-col-browse` PR3 drift teaches that the apply phase transport failure can mask a MUST violation — every backend and frontend MUST requirement gets a dedicated test pinning the WHEN/THEN contract.
13. **PR-review budget is 400 lines** (`additions + deletions`, goldens excluded). The previous `arbol-col-browse` PR3 fit in 3 chained PRs (backend, frontend, learn-es); this change's PR strategy is `auto-chain` per the orchestrator's pre-flight cache.

## Open questions for spec/design

1. **Storage shape for the explored flag**: column on `taxa` (denormalised; re-import-fragile) vs new `explored_flags` table (orthogonal; extra join). The proposal phase MUST pick. Recommendation from exploration: new table (orthogonal to `taxon/import_data.py` rebuilds).
2. **Folder-creation failure semantics**: when `os.makedirs` raises `PermissionError` (read-only filesystem, non-writable parent), does the endpoint return 500, 503, or 409 with a retry hint? The error envelope should be uniform with `ErrorResponse` (`{detail: str}`) — pick the status.
3. **Folder path normalisation**: the breadcrumb walk via `resolve_path_by_display_level` returns canonical `name` (citation-free); is `os.sep` join + lower-case + percent-decode the right path, or do we want `safe_name` (`re.sub(r"[^\w\s-]", "_", segment)`) to handle the rare non-ASCII segment? The species `Panthera tigris` is fine; the user-visible path may want spaces preserved or replaced. Pick a policy and pin it as a test.
4. **Folder de-duplication across re-imports**: the species_folders row PK is `species_id INTEGER`; re-import of `data/taxon.db` may bump `taxa.id` (autoincrement resets when the table is recreated). Does the endpoint walk the species by `(genus, epithet)` first and re-bind the row, or fail with a stale-PK error? Pick a reconciliation policy.
5. **Link visited endpoint shape**: `POST /api/link-visited/{genus}/{epithet}` body `{source: "Wikipedia"}` → idempotent set; `DELETE` for unset. Or one `PUT` with `{visited: true|false}`. The `POST/DELETE` pattern matches the explored-flag endpoints; the `PUT` is one fewer endpoint but less REST-pure. Pick.
6. **Workspace hydrate endpoint**: on app mount, does the SPA fetch one envelope (`GET /api/workspace`) or many (`GET /api/explored/list` + `GET /api/link-visited/list`)? One envelope keeps the wire surface smaller; many keep the endpoint contracts narrower. Pick. The species-folder endpoint can be lazy-fetched on `SpeciesList` mount (no global list needed; the row only knows about its own species).
7. **Iframe X-Frame-Options fallback UX**: when a source refuses embedding, render (a) a blank iframe + console error, (b) a "this source refuses embedding — open in new tab" placeholder card with a button, (c) auto-open in new tab and show a toast. (b) is the most discoverable and matches the issue #68 "graceful degradation" wording. Pick.
8. **Active-link state scope**: when the user clicks a link in the per-taxon breadcrumb-links panel (segment click, no epithet), does the explorer activate? If yes, the iframe URL substitutes the segment's canonical `name`, not any species name — the substitution target is the segment. If no, the explorer only activates after a species click. Issue #68 says "all of this is gated by the per-link switch: only the currently-active link's URL is loaded into the iframe" — but it doesn't say which link set counts as "active". Pick: species-only (cleaner) or both (richer).
9. **`<ExplorerPanel>` sticky behaviour**: `sticky top-0` keeps the iframe visible during scroll; some browsers throttle sticky iframes and the iframe re-loads on every scroll. `position: fixed` on a separate column keeps it always-visible but eats the layout. Pick the layout.
10. **`<SpeciesLinks>` switch position**: leading `[visited]` switch (before the link label) makes the switch the first tab stop, which is good for keyboard nav but breaks the "click the link to open" muscle memory. Trailing `[visited]` switch (after the label) preserves the click affordance but adds visual noise. Pick.
11. **Sandbox attribute set**: the exploration flags `allow-same-origin allow-scripts allow-forms allow-popups allow-downloads`. If the user wants to download images from Google Images, `allow-popups` is required (Google serves image downloads through a popup). Confirm via test against the live site OR accept the issue #68 caveat.
12. **Source-label vs URL key for `link_visited`**: `source` is stable (template-driven) and human-readable; `url` changes per substitution (contains the species query). Keying on `source` is right; confirm.
13. **Workspace state on app load**: hydrate eagerly on App mount (`useEffect` that calls the hydrate endpoints), or lazily as the user scrolls into a species row. Eager keeps the visited switch always current; lazy keeps the cold-start time small. Pick.

## Risks flagged

- **Filesystem race on first folder creation**: `os.makedirs` is not atomic across processes. If two SPA instances start (e.g. the user opens two tabs), both POST to the endpoint; the row insert is idempotent on `species_id PK`, but the second POST returns 409 instead of 201. Pin the behaviour with a test.
- **`AQUALIFE_ROOT` not set + cwd ≠ project root**: if the user runs `python -m taxon.main` from a worktree subfolder (common in `develop` workflow), `./Proyecto-Aqualife/` resolves to `<worktree>/Proyecto-Aqualife/`, not `<project>/Proyecto-Aqualife/`. The endpoint MUST fail loudly (503 or 500 with `AQUALIFE_ROOT not resolvable from cwd <cwd>`) or accept an absolute path. Pin with a test that runs from a subfolder and asserts the error envelope.
- **X-Frame-Options / CSP rejection**: many sources (Wikipedia, Google Scholar, BHL) will refuse to load in any iframe. The graceful-degradation fallback is required, not optional. Without it, the explorer panel looks broken (blank iframe) on the most-used sources. Mitigation: the `target="_blank"` fallback must be obvious (a button + tooltip, not a hidden affordance).
- **Iframe sandbox + downloads**: Safari gates iframe-initiated downloads more strictly than Chrome/Firefox. The SPA's `target="_blank"` fallback covers Safari users — but the fallback must be reachable from inside the iframe (popups blocked in some configs). Mitigation: keep the `target="_blank"` link rendered as a regular `<a>` outside the iframe so the user can always escape.
- **Schema churn from re-imports**: the importer recreates `taxa` (and bumps `id`); any FK from the new tables to `taxa.id` becomes stale on re-import. The folder-creation endpoint MUST walk by `(genus, epithet)` not by raw `taxa.id`. The species_folders row needs `genus TEXT, epithet TEXT` columns (or a re-bind on every read) so re-imports can recover the FK. Pin with a test.
- **Transport failure masking MUST violations**: the previous `arbol-col-browse` PR3 taught that `sdd_task_result_empty` (transport-level) can mask spec drift. The proposal phase MUST enumerate every MUST requirement explicitly (one per WHEN/THEN clause in the deltas); the apply phase MUST pin each with a dedicated test before the green commit.
- **400-line budget risk**: backend PR1 (3 new tables + 4-6 new endpoints + 8-12 tests) is ~250-350 lines; frontend PR2 (SpeciesList trailing column + SpeciesLinks leading switch + ExplorerPanel + workspaceStore + api.ts extensions + 4-6 test files) is ~600-900 lines — **above budget**. The orchestrator's pre-flight cached `auto-chain` + `review=400` budget mandates chained PRs. The proposal phase MUST forecast the budget and split. Recommended split: PR1 backend (≤350), PR2 frontend workspace store + SpeciesList + SpeciesLinks changes (≤350), PR3 ExplorerPanel + design-doc + learn-es (≤350). The Pencil + impeccable design pass is a hard gate per AGENTS.md §5 and must land BEFORE PR1 starts.
- **Strict TDD requires per-requirement test pinning**: every WHEN/THEN clause in the new specs MUST have at least one test before the green commit. Skipping this is exactly what produced the previous drift. The proposal phase MUST enumerate the test count.
- **No `.pen` page**: the prescriptive design doc is the only design surface this change ships. If the design drift between the doc and the implementation isn't caught by `impeccable` before code, the result is a feature whose UX is a coin-flip (per the `arbol-col-browse` PR3 drift narrative). The proposal phase MUST reserve a verification step where the implementer's components are re-checked against the prescriptive design before the PR opens.
- **`cascadePath` ↔ `workspaceStore` interaction**: the workspace store is per-species; the cascadePath is per-cascade-step. A user who clicks a breadcrumb segment (cascadePath updates) without clicking a species has no species_id for the workspace store. The explorer panel's `activeLink` must either key on `(cascadePath, source)` (path-level) or stay null until a species is resolved. The risk is the explorer activates on a non-species segment and substitutes the segment name, which the user might find surprising. The design phase MUST scope the activation rule.

## Ready for Proposal

**Yes** — the orchestrator should launch `sdd-propose` next. The exploration covers every dimension issue #68 calls out: backend (router / schema / resolver), frontend (SpeciesList / SpeciesLinks / new ExplorerPanel / workspaceStore), data model (new tables + the explored-flag column-vs-table fork), filesystem (`AQUALIFE_ROOT`), iframe sandbox + X-Frame-Options graceful degradation, Pencil-MCP-disabled design precedent, and OpenSpec delta structure. The proposal phase MUST decide the storage shape (column vs table) and the PR chain split before the design phase starts.
