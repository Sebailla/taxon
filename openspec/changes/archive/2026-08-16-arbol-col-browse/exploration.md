## Exploration: arbol-col-browse

Replaces the 7-fixed-dropdown linear cascade (`frontend/src/components/Cascade.tsx`) with a CoL-style hierarchical tree (`frontend/src/components/TaxonomicTree.tsx`) that lazy-loads children per parent, indents by rank, renders `rank: Name Authorship • N spp.` rows, and exposes a "Find taxon" search box with `Source` + `Extant only` filters. Closes issue #67. The new tree must work against `data/col.db` (1.65 GB CoL import) which currently breaks the cascade with `taxon not found: 'Biota'`.

### Current State

**Frontend (`develop` HEAD `38d8827`).** `App.tsx` composes three blocks: a `<Cascade>` (7 fixed `<RankDropdown>`s in a `md:grid-cols-3 lg:grid-cols-7`, fixed order biota → kingdom → phylum → class → order → family → genus), a `<Breadcrumb>` (path → `<button>` segments, persists for the picked segments), and a `<SpeciesLinks>` panel (last-clicked wins; `taxon:select` clears the breadcrumb panel, segment click clears the species panel). State is split across a `useReducer` inside `Cascade.tsx` (`levelByPath` snapshots cached per `pathKey`, plus a `species` projection), a Zustand singleton (`frontend/src/store/cascadePath.ts`) that also drives the App effect, and per-panel `AbortController`s for race safety. The Breadcrumb's 13-link grid is fetched via `GET /api/{path}/taxon-links` (resolver walks `resolve_path_by_display_level`).

**Backend (`taxon/api/router.py`).** The cascade reuses three endpoints: `GET /api/kingdoms` (synthesizes Biota + Viruses with hard-coded CLB opaque ids `5T6MX` / `V`), `GET /api/path-children?path=…` (returns `PathChildrenEnvelope{parent, children, next_tiers}`), and `GET /api/species-list?path=…`. The deep resolver is `resolve_path_by_display_level` in `taxon/api/hierarchy.py`: it walks each path segment against a row whose `display_level` is one bucket below the previously matched row (or the same bucket, for off-tuple intermediates like subphylum / infraphylum / parvphylum / subfamily / tribe / subtribe). The `Taxon` SQLAlchemy model exposes `id`, `source_id`, `parent_id`, `rank`, `name`, `display_name`, `display_level`, plus the four marker flags (`is_synonym`, `is_extinct`, `is_uncertain`, `is_unassigned`). `TaxonResponse` (the wire contract) mirrors this plus `parent_id` and a `str | int` id union (the SQLite resolver emits `int`, the CLB resolver emits opaque strings).

**Schema (verified by sqlite3 read on `data/col.db`).** `taxa` table has 11 columns: `id INTEGER PK`, `source_id VARCHAR UNIQUE`, `parent_id INTEGER FK→taxa.id`, `rank VARCHAR`, `name VARCHAR`, `display_name VARCHAR`, `display_level VARCHAR`, `is_synonym BOOLEAN`, `is_extinct BOOLEAN`, `is_uncertain BOOLEAN`, `is_unassigned BOOLEAN`. Plus `species_paths` (0 rows in `col.db`; empty in the re-import, must be repopulated before species-breadcrumb lookups work). Crucially:

- `col.db` has 5 rows with `parent_id IS NULL`: 1 `unranked` (`?incertae sedis`) + 3 `domain` (`Archaea Woese et al., 2024`, `Bacteria Woese et al., 2024`, `Eukaryota (Chatton, 1925) Whittaker & Margulis, 1978`) + 1 `unranked` (`Viruses`). **No `biota` rank rows.** The synthesized "Biota / Viruses" cascade roots therefore have no real `id` to anchor on.
- `col.db` has 0 rows with `display_level` populated (the column exists but is empty, even though `taxon.db` does populate it). The `taxonomy_display_level` SQL function is registered at connection time so a NULL `display_level` resolves through `RANK_TO_DISPLAY_LEVEL`; this is what `_effective_display_level` falls back to.
- **No `authorship` column exists anywhere.** Author citations are folded into `display_name` (e.g. `Eukaryota (Chatton, 1925) Whittaker & Margulis, 1978`) — the citation-free `name` column already separates them. The CoL tree's "Name Authorship" row is therefore a derived split: `name` (link) + citation tail of `display_name`.
- **No `species_count` materialised anywhere.** CoL exposes a count per node via a live `count`/`childCount` aggregate; the local DB has no equivalent column and no view. The "N spp." per row is a derived computation that must aggregate `count(*) FROM taxa WHERE display_level='species' AND ancestor_tree_contains(parent_id)`. With 4.8M species rows and the deepest subtrees 5+ levels deep, naive recursive scans are expensive; the substitution needs either a precomputed `path` projection (e.g. materialize `species_paths` with rank columns) or a `WITH RECURSIVE` query. The current `species_paths` table is empty for `col.db`, so this aggregation would also need to be populated as part of this change.
- Rank distribution (top 5): `species` 4,884,542; `unranked` 1,573,734; `genus` 460,668; `variety` 385,410; `subspecies` 358,311. Vast majority of the tree depth is the species tier.

**Why the cascade stops on `col.db`.** The current walk starts at the synthesized `Biota` root, but the data has no `biota` row. The first `resolve_path_by_display_level` call against `["Biota"]` matches `Biota` (= `5T6MX`, synthesized) to nothing in the DB, OR — if the frontend strips the prefix and walks `["Animalia"]` — starts at the `kingdom` bucket and works, but only after the user picks `Biota` first (a row that doesn't exist on `col.db`). The demo `curl /api/kingdoms` returns the synthesized rows, but the actual data begins at `domain` (`Eukaryota` → `Animalia` → `Chordata` → …). The Prism `Biota` synthesis is an artifact of the CLB contract; `col.db` is the CoL dump and uses `domain` as the top domain instead. The vitrine image confirms this: the tree root is `Archaea Woese et al., 2024`, `Bacteria Woese et al., 2024`, `Eukaryota (Chatton, 1925) Whittaker & Margulis, 1978`, and `Not assigned` — all `domain` rank, no `biota`.

**Breadcrumb scope (constraint from `breadcrumb-dinamico` archive).** The current `breadcrumb-dinamico` change (PR #65 + #66, merged to `develop`) makes the breadcrumb permanent (renders whenever `cascadePath.length > 0`) and gives each segment a `<button>` that fetches the per-taxon 13-link grid via `GET /api/{path}/taxon-links`. This change is **additive** and stays: the tree must continue to dispatch `path:change` (or anything equivalent) so the breadcrumblinks panel keeps working. The breadcrumb-taxon's endpoint keeps working because it walks via `resolve_path_by_display_level` which already folds intermediates into the parent bucket — so the tree's explored path (which can include subtree, etc.) becomes the breadcrumb naturally. The `cascadePath` Zustand store is the spherical-cow singleton; the tree can write the explored path through it.

**Out of scope (skating past from `breadcrumb-dinamico` proposal):** filesystem/iframe/switches (`species-folder-explorer`); `LinksResponse.links` contract changes; cross-reload persistence of the explored path.

### Affected Areas

- `frontend/src/components/Cascade.tsx` — replace with `TaxonomicTree.tsx`. The whole component (425 lines), its reducer (`Cascade.state.ts`, 175 lines), and every test file under `frontend/tests/` that imports `Cascade` (`cascadeDynamicTiers.test.tsx`, `Cascade.pathAware.test.tsx`, `Cascade.ui.test.tsx`, `cascadeRoots.test.tsx`, `cascadeSubphylum.test.tsx`, `Cascade.test.tsx.legacy`) get deleted. The Verified-CI confirmation note in `breadcrumb-dinamico/archive-report.md` (Known Issues #1) explicitly anticipates this: "When the planned change `arbol-col-browse` replaces the Cascade linear of 7 dropdowns with a column-browser tree, the entire `Cascade.tsx` + its test files will be deleted. The 2 CRITICAL failures will close naturally with that deletion."
- `frontend/src/App.tsx` — drop the `<Cascade>` import; mount `<TaxonomicTree>` in the same grid slot. The App's `path:change` listener (lines 150–159) and the breadcrumb-links `useEffect` (lines 119–142) stay verbatim; the tree only needs to keep emitting the same `path:change` CustomEvent payload (`{path: string[]}`) and the same `cascadePath` Zustand writes.
- `frontend/src/components/SpeciesList.tsx` — stays. The tree reaches a genus, the Cascade's existing `fetchSpeciesList` is invoked, and the species-list renders below the tree.
- `frontend/src/components/Toggles.tsx` — currently inside the cascade for the species-list filter. Move it next to `SpeciesList` (or fold it into `TaxonomicTree` adjacent to the species list), or keep it in its current position with the new tree layout. The "Extant only" checkbox in the reference image is `is_extinct=false` filter and overlaps with the existing `Toggles` "extinct" chip — they should be consolidated. The `Source` checkbox is a new filter (which subtree does the user want — the synthetic CLB view, the local `col.db` view, etc.) and is not present in the current backend.
- `frontend/src/api.ts` — add `fetchTreeNode(parentId, init?)` for the lazy children fetch. Keep `fetchRoots` (one query for the initial top-level the tree shows) and `fetchTaxonLinks` (still drives the breadcrumb panel and the species-links panel). Replace `fetchPathChildren` semantics with the new endpoint or alias it through a thin wrapper.
- `frontend/src/store/cascadePath.ts` — stays. The tree writes the explored path via `useCascadePath.getState().setPath(state.path)`.
- `frontend/src/components/Breadcrumb.tsx` — minor: rename `aria-label="Resolved species breadcrumb"` → `aria-label="Cascade path breadcrumb"` (the Verify-Report §11 ISSUE #3 warning). Otherwise no change.
- `taxon/api/router.py` — add `GET /api/tree/children?parent_id={id}` (or `GET /api/tree/node/{id}`). Keep `/{path:path}/taxon-links` (the breadcrumb-taxon's endpoint) untouched. The `/api/kingdoms` synthesis is no longer needed (the tree starts at `domain` from real data) but can stay for any consumer that still issues a top-level call.
- `taxon/api/hierarchy.py` — add a `list_children_for_tree(parent_id, include=None, limit=…, cursor=…)` that returns direct children of `parent_id` regardless of rank, plus a `species_count` aggregate per child. The aggregate needs a recursive CTE OR a precomputed projected path; the latter is re-usable by `breadcrumb-dinamico` / `species-search-links` / `taxonomy-hierarchy` specs.
- `taxon/api/schemas.py` — add `TreeNodeResponse{ id, name, display_name, rank, authorship, has_children, species_count, parent_id, is_synonym, is_extinct, is_uncertain, is_unassigned }`. Add `TreeChildrenResponse{ parent: TreeNodeResponse, children: list[TreeNodeResponse] }`. Add `TreeSearchResponse{ items: list[TreeNodeResponse] }` for the "Find taxon" autocomplete. Add `TreeSearchHit` shape for the search response.
- `taxon/api/search.py` (new) — `search_taxon(q, limit, include_extinct)` for the autocomplete. Uses `LIKE` over `name` + `display_name` with a ranked relevance score (exact match > prefix > substring). Re-uses the `Taxon` table; the index `ix_taxa_parent_name` already exists but no `ix_taxa_name` or `ix_taxa_display_name` — a name-FTS index is needed for production scale.
- `taxon/api/db.py` — `get_db` already exists; new endpoints re-use it. No change.
- `taxon/schema.py` — keep as is. The `authorship` and `species_count` fields are NOT new columns; they are derived at query time from `display_name` (authorship) and a recursive aggregation (species_count). If the recursive aggregation is too slow (>1s on Arthropoda), the schema gains a `species_path` projection (materialize rank columns per species + indices on each), but that is a separate change.
- `taxon/api/sqlite_resolver.py` — `list_path_children` stays (the breadcrumb-taxon's endpoint reuses it). Add a new `list_tree_children(parent_id, …)` helper that does NOT need the `Biota` synthesis and returns one row per direct child regardless of rank.
- `taxon/api/species.py` — `_list_species_page_under_parent` stays. The genus → species list fetch is unchanged.
- `taxon/tests/test_api_router.py` — delete or rename. Add `test_api_router_tree.py` for the new `/api/tree/children` and `/api/tree/search` endpoints.
- `frontend/tests/` — delete `cascadeDynamicTiers.test.tsx`, `Cascade.pathAware.test.tsx`, `Cascade.ui.test.tsx`, `cascadeRoots.test.tsx`, `cascadeSubphylum.test.tsx`, `Cascade.test.tsx.legacy` (all depend on the deleted Cascade). Add `TaxonomicTree.test.tsx` (caret rows, indent, lazy-fetch, keyboard, aria-name) + `TaxonomicTree.lazyFetch.test.tsx` (`AbortController` on retracted caret) + `api.treeChildren.test.ts` (URL + decode + 200/404) + `api.treeSearch.test.ts` (debounce + 200/empty) + `App.taxonLinks.test.tsx` + `Breadcrumb.dynamic.test.tsx` + `store.cascadePath.test.ts` stay (already in place).
- `openspec/changes/arbol-col-browse/` — proposal, design, specs deltas, tasks, verify-report, archive-report. The exploration.md lives here.
- `openspec/specs/taxonomy-hierarchy/spec.md` — append `## MODIFIED Requirements` for the path-resolution semantics (the current stable expectations stay; add a new requirement for the tree endpoint).
- `openspec/specs/species-search-links/spec.md` — no change (cross-taxon dispatch stays the same).
- `documents-es/openspec/changes/arbol-col-browse/` — Spanish mirror per AGENTS.md §1.
- `taxon.pen` (encrypted, Pencil MCP only) — design the tree first, audit under `impeccable`, then translate to code. Per AGENTS.md §5 this is a hard gate; the visual treatment of caret rows, indent, "N spp." badge, and the "Find taxon" header layout is what separates this from a generic data grid.
- `learn-es/YYYY-MM-DD-arbol-col-browse.md` — post-merge entry.

### Approaches

1. **Backend-driven tree endpoint `GET /api/tree/children?parent_id={id}` + `GET /api/tree/search?q=…`** — new endpoint takes the parent id (an `int` from the local SQLite resolver, not a name path) and returns direct children with `id`, `name`, `authorship`, `rank`, `has_children`, `species_count`. The frontend renders a single `<TaxonomicTree>` that lazily fetches on first expand and caches the result in a tree-state store. The "Find taxon" autocomplete hits a separate search endpoint. The cascade bug is bypassed entirely: the tree never touches the `Biota` synthesis or the path-resolver; it walks by parent id, which is the natural axis of the local DB.
   - **Pros**:
     - Single backend round-trip per expand; the cache lives in the frontend.
     - `has_children` is a cheap pre-filter (children count > 0) so the UI can render a leaf caret without an extra fetch.
     - `species_count` is computed once per row at the parent_fetch, not on every expand.
     - Parent-id addressing is stable across the Biota/CoL/Viruses synthesizer scenarios; the tree doesn't care which root(s) it starts from.
     - Reuses the existing `Taxon` model and the existing `ix_taxa_parent_name` index. Recursive CTE for `species_count` uses the existing `(parent_id, name)` index.
     - The tree's explored path IS the breadcrumb (the breadcrumb-dinamico invariant carries over verbatim).
     - The `Source` filter becomes a server-side `source` query param (`/api/tree/children?parent_id=…&source=…`) — extensible to multiple CoL datasets without a frontend fork.
     - The "Extant only" filter is `is_extinct=false` on the parent_fetch — one extra predicate, no UI churn.
   - **Cons**:
     - One new endpoint, which adds a Pydantic schema and 3–4 tests. ~80–120 lines of backend code total.
     - `species_count` aggregation with a recursive CTE against 4.8M species rows is non-trivial. The naive `WHERE parent_id=?` only counts direct children; a true descendant count requires walking the tree. With the existing `(parent_id, name)` index this is O(N) per node where N is the descendant count — at the root (Eukaryota, 2.4M species) that's measurably slow. Mitigations: (a) materialize the hierarchy depth column; (b) cap the propagation at N levels; (c) cache the count at the parent-fetch and memoize. The proposal phase must decide which; the safest is a "lazy species_count" that returns `null` unless the parent is on a "high-cost" path.
     - The `Source` filter is a new feature with no current backend support. Adding it requires understanding which "sources" the local DB is aware of (probably just "CoL" since `col.db` is the only source for the new tree). Late-bound: ship the filter plumbing but ship it as a no-op for the first PR.
     - The "Find taxon" autocomplete needs a FTS index for production scale; without it, the LIKE search scans 4.8M rows on every keystroke. Mitigation: debounce 200ms + response-time SLO + a `LIMIT 8` cap.
   - **Effort**: Medium-High. Backend: 1 PR (200–300 lines). Frontend: 1 PR (~400 lines, on the budget edge; consider chained). Pencil design + impeccable audit: 1 PR slice. Strict TDD per `openspec/config.yaml strict_tdd: true`.

2. **Two-step endpoint reusing the existing `path-children` + `taxon-links` (after fixing the resolver to start from `domain`)** — keep the path-resolver intact, fix the cascade bug by replacing the `Biota` synthesizer with a real `domain` lookup, and re-use `/api/path-children` for the tree's lazy expand (`?path=Biota|…|Eukaryota|…`). The tree stores the explored path, not a parent id, so the breadcrumb is free.
   - **Pros**:
     - Zero new endpoint; the existing `/api/path-children` envelope already returns `children` grouped by rank.
     - Breadcrumb is automatic (the path IS the breadcrumb).
     - Smaller backend diff (~20 lines of resolver fix; the `Biota` synthesizer becomes a real `domain` root lookup).
   - **Cons**:
     - Requires the path to be valid for every expand. If the user collapses one branch and reopens another, the path has to be rebuilt each time — the tree cannot "jump" from `Eukaryota/Animalia` directly to `Eukaryota/Fungi` without first collapsing `Animalia`.
     - The `next_tiers` roll-up rules (phylum → class roll-up, subphylum collapse, family → genus roll-up) actively hide intermediates, which is the OPPOSITE of what the tree wants. The tree needs every rank, not the roll-up.
     - Re-enabling the roll-up creates a different broken contract: the user sees only `class` under `Chordata`, not the subtree / Vertebrata / Gnathostomata / Osteichthyes path.
     - The `species_count` aggregate is still missing; this approach doesn't solve it.
     - Touches `taxon/api/sqlite_resolver.py` and `taxon/api/hierarchy.py` — broad blast radius for a visual change.
   - **Effort**: Medium (backend 1 PR, frontend 1 PR). Higher risk because the resolver is shared with `breadcrumb-dinamico` and `cascade-checklistbank`.

3. **Hybrid: new `GET /api/tree/children` for the lazy expand + re-use `/{path:path}/taxon-links` for the per-row 13-link grid** — split the responsibilities: the tree endpoint returns child rows with `species_count`; the breadcrumb-taxon's endpoint stays as the per-taxon dispatch resolver. The tree stores `(parent_id, expanded: boolean)` per row; the breadcrumb-taxon's endpoint is triggered by the explore path via the existing `path:change` plumbing.
   - **Pros**:
     - Combines the cleanest data shape (new tree endpoint) with the cleanest dispatch contract (existing `taxon-links`).
     - No regression in `breadcrumb-dinamico` behavior.
     - Recursive CTE for `species_count` is bounded to the tree's expanded scope (small N per expand).
     - Frontend renders the tree with the indenture and caret; the breadcrumb-links panel works as before.
   - **Cons**:
     - Two endpoints in flight (parent fetch + child fetch on expand); the frontend coordinates both.
     - The "Find taxon" autocomplete still needs a new search endpoint.
     - The `species_count` cache lives in the tree-state store; if the user collapses a level, the aggregated count is recomputed from the cache (already cheap).
   - **Effort**: Medium-High. Slightly larger than Approach 1 because the frontend splits its state into a tree cache + the breadcrumblinks panel, but the backend is identical to Approach 1.

### Recommendation

**Approach 3 (hybrid)** — backend adds `GET /api/tree/children?parent_id={id}` + `GET /api/tree/search?q={q}` (Approach 1's backend shape); the frontend's `TaxonomicTree` lazy-loads children from the new endpoint and the existing `/{path:path}/taxon-links` keeps feeding the breadcrumb-links panel. This is the cleanest combination of the cleanest data shape and the cleanest dispatch contract, and it leaves `breadcrumb-dinamico` verbatim.

Concretely:

- **Backend**: 1 PR adding `taxon/api/tree.py` with `list_tree_children(parent_id, include, limit, cursor)` returning a `TreeChildrenResponse`, and `search_taxon(q, limit, include_extinct)` returning a `TreeSearchResponse`. Reuses `taxon/api/hierarchy.py`'s `TaxonRow` and adds two new schema classes in `taxon/api/schemas.py`. Strict TDD: tests first (200/empty/404/cursor/authorship split/species_count aggregate at one level deep), then implementation.
- **Frontend**: 1 PR replacing `Cascade.tsx` + `Cascade.state.ts` with `TaxonomicTree.tsx` + `TaxonomicTree.state.ts` (zustand tree cache keyed by `parent_id`). The tree renders caret rows with the format `rank: Name Authorship • N spp.`. The "Find taxon" header row uses an `<input>` with debounce (200ms) → `fetchTreeSearch`. The `Source` + `Extant only` checkboxes are right-aligned in the same row, fed to the children fetch as query params. The `<Toggles>` "extinct" chip is folded into the "Extant only" checkbox (it's the same filter). The explored path is written to the existing `cascadePath` Zustand store via `useCascadePath.getState().setPath(state.path)`, and a `path:change` CustomEvent is dispatched on every explore so the App's breadcrumb-links panel keeps working.
- **Pencil + impeccable**: design first in `taxon.pen` (the existing Pencil file), audit under `impeccable` per AGENTS.md §5, then translate to code. The tree visual is the core deliverable; the design pass decides indent width, caret glyph, badge treatment, and the "Find taxon" header layout.
- **Tests**: 1 chained PR for `@vitest` (the new TaxonomicTree) + 1 PR for `pytest` (the new tree endpoints). The Breadcrumb/Breadcrumb.dynamic/store.cascadePath/api.taxonLinks/App.taxonLinks tests stay verbatim.
- **Spanish mirror**: `documents-es/openspec/changes/arbol-col-browse/proposal-es.md` + `design-es.md` + `tasks-es.md` + `verify-report-es.md` + `archive-report-es.md` per AGENTS.md §1. The exploration.md does not strictly require a mirror, but the sdd-init observation #3566 lists `explore.md` in the mirror list — emit one anyway.
- **Issue #67**: this is the implementation that closes it. The issue lists the same constraints the tree needs to satisfy (caret rows, indent, rank: Name Authorship • N spp., Find taxon, Source, Extant only).
- **Chained PR forecast**: backend (~300 lines including tests) followed by frontend (~400 lines including visuals + tests + Spanish mirror). Both slices fit the 400-line budget IF the Pencil design pass is parallel; otherwise the frontend slices into Pencil/visual first, then component tests, then App wiring. Plan for chained PRs.

### Risks

- **`species_count` cost at deep nodes.** Aggregation of species descendants at the deepest ranks (e.g. `Eukaryota` → 2.4M species recursive) is the dominant cost. The recursive CTE plus the existing `(parent_id, name)` index is O(N) per call where N is the descendant count. Mitigations: (a) lazy compute (return `null` for nodes with >100k direct children, fill in on demand); (b) cache at the parent; (c) materialize a `species_path` projection in a follow-up PR. The proposal phase must pick one.
- **`col.db` has no `display_level` populated, no `species_paths` rows, and no `biota` rank rows.** The tree must NOT depend on `display_level` being populated (the SQL function fallback is the only working path); the `species_paths` empty state means the breadcrumb lookup by full path will not work for species until a re-import lands; the missing `biota` rows mean the tree must start at `domain`, not at the synthesized `Biota` root. The tree's new endpoint should NOT consume the `Biota` synthesizer at all — it starts at real `domain` rows.
- **`authorship` is a derived field.** `display_name` carries the citation; the new endpoint must split the citation-off `name` (the existing `name` column) from the citation-tail. The split is `name` + substring of `display_name` after `name`. The PR must NOT introduce an `authorship` column on the DB.
- **`Source` filter has no current backend.** It is a new feature with no spec. The first PR can ship the filter UI as a no-op (always-on CoL source) and let a follow-up PR add the wiring when the multi-source support lands.
- **Cascade deletion closes the 2 CRITICAL failures from `breadcrumb-dinamico`/`cascade-checklistbank`.** Those tests live in `cascadeDynamicTiers.test.tsx`; deletion is safe and intentional. Risk: a regression test that somehow depends on the Cascade component shape (e.g. a test that imports `Cascade` for the breadcrumblinks panel) would break. Mitigation: re-grep across `frontend/tests/` for `from.*Cascade` imports before deleting.
- **Strict TDD + Pencil + impeccable is a 3-gate chain.** Pencil design → impeccable audit → test files → implementation. The PR cannot land if the design pass is skipped.
- **400-line budget.** Frontend is at the edge of the 400-line budget; the proposal + tasks phases must forecast and split if needed.
- **Spanish mirror rule.** Every artifact must have a Spanish mirror under `/documents-es/`. The proposal phase must call this out so the apply phase doesn't forget it.
- **The Postgres `display_level` function is registered on every SQLite connection via `_build_engine` (line 101 of `taxon/api/__init__.py`).** Any new endpoint that reads `display_level` must verify the connection that calls it has the function registered. The existing `get_db` dependency already does this, so new endpoints re-using it are safe.

### Ready for Proposal

**Yes.** The next phase is `sdd-propose`, which should land:

- Intent: replace the 7-dropdown Cascade with a CoL-style tree; close issue #67.
- Scope: backend adds `GET /api/tree/children?parent_id={id}` + `GET /api/tree/search?q={q}`; frontend replaces `Cascade.tsx` + `Cascade.state.ts` with `TaxonomicTree.tsx` + `TaxonomicTree.state.ts`; breadcrumb-links panel and `cascadePath` store stay verbatim; `breadcrumb-dinamico` spec + design stay verbatim.
- Approach: recommend Approach 3 (hybrid — new tree endpoint + reuse `taxon-links`).
- Affected areas: as listed above. The cascade-bug (`taxon not found: 'Biota'`) is bypassed because the new endpoint is parent-id addressed, not path-addressed.
- Spanish mirror: every artifact gets `-es.md` per AGENTS.md §1.
- PR split: backend (1 PR) + frontend (1 PR or 2 chained PRs if Pencil design + impeccable pushes the frontend over 400 lines). Pencil design + impeccable audit gates the frontend PR per AGENTS.md §5.
- Strict TDD: tests first, per `openspec/config.yaml strict_tdd: true`.
- Rollback: each PR is additive (new endpoint + new component); the old `Cascade.tsx` is deleted in the frontend PR. `git revert` per PR.
- Worktree: `../taxon-worktrees/arbol-col-browse` from `develop` (already created).

The orchestrator should tell the user:

1. The Cascade will be deleted; the breadcrumb-dinamico spec stays verbatim.
2. The new tree will start at `domain` (Archaea / Bacteria / Eukaryota) — the Biota synthesis is gone.
3. `species_count` will be a derived aggregation; the proposal phase must pick the cost-mitigation strategy.
4. The Pencil design + impeccable audit pass is the first slice, before any code.
5. The 2 CRITICAL failures in `cascadeDynamicTiers.test.tsx` close with the Cascade deletion — no separate fix PR needed.
