# Verify Report — species-folder-explorer PR1 (backend)

> **Scope**: PR1 of `species-folder-explorer` (issue #68, backend surface).
> 3 chained PRs (`auto-chain` per preflight cache); each ≤350 LOC.
> This report covers backend only — frontend PR2/PR3 (workspaceStore,
> SpeciesList trailing column, SpeciesLinks leading switch, ExplorerPanel,
> design doc + learn-es) is out of scope.
>
> **Commits verified**:
> - `1948bbc` — `feat(schema): add workspace ORM models with PK (genus, epithet) re-bind columns`
> - `61ee5f2` — `feat(api): add 8 workspace endpoints + Pydantic schemas + aqualife_root tests`
> - `cb631f7` — `docs(openspec): sync Spanish mirrors + fix species-folder spec line 11`
>
> **Verdict**: **PASS** (all spec MUST requirements covered with passing
> tests at runtime; all verify-stack checks green; one WARNING for stale
> `tasks.md` checkboxes the orchestrator should mark after the merge).

---

## 1. Change summary

| Field | Value |
|-------|-------|
| Change name | species-folder-explorer |
| Issue | #68 |
| PR | PR1 (backend) |
| Branch | feat/species-folder-explorer-pr1 |
| Strategy | `auto-chain` per preflight; PR1 → PR2 → PR3 |
| Specs in scope (PR1) | species-folder, link-visited, species-explored |
| Specs out of scope (PR3) | workspace-explorer |
| Authored LOC (PR1) | 2043 added / 2 deleted across 11 files |
| Persistence mode | `hybrid` (engram + openspec file) |

---

## 2. Completeness table

| Artifact | Status | Notes |
|----------|--------|-------|
| `proposal.md` (EN) | present | lines 1-206 |
| `proposal-es.md` (ES mirror) | present | same length, faithful translation |
| `design.md` (EN) | present | lines 1-117 |
| `design-es.md` (ES mirror) | present | |
| `tasks.md` (EN) | present, **STALE** | 13 phase-1 tasks remain `- [ ]` (un-checked) |
| `tasks-es.md` (ES mirror) | present | |
| `specs/species-folder/spec.md` | present, 7 requirements / 11 scenarios | line 11 fixed in `cb631f7` |
| `specs/species-folder/spec-es.md` | present | |
| `specs/link-visited/spec.md` | present, 5 requirements / 8 scenarios | |
| `specs/link-visited/spec-es.md` | present | |
| `specs/species-explored/spec.md` | present, 5 requirements / 8 scenarios | |
| `specs/species-explored/spec-es.md` | present | |
| `specs/workspace-explorer/spec.md` | present, **out of PR1 scope** | frontend PR3 |
| Implementation (`taxon/api/workspace.py`, `taxon/migrate.py`, `taxon/api/router.py`) | present | 2043 LOC added |
| Backend tests | present | 5 new files; 54 workspace tests |

---

## 3. Build / tests / coverage evidence

| Check | Command | Exit | Notes |
|-------|---------|------|-------|
| Full pytest | `python -m pytest --tb=short -q` | **0** | **246 / 246 passed in 13.57s** (54 new workspace tests + 192 pre-existing). `test_output_hash`: `e3e00b59dfdc0eb23ce8173eede4df256236f8e203e63d188c83d61275da9884` |
| ruff format | `ruff format --check .` | **0** | "57 files already formatted". `build_output_hash`: `d642ac445c009c50f49745da4dd05334f2c9e817132c16c3b6785e9b4da5831d` |
| ruff check | `ruff check .` | **0** | "All checks passed!". hash: `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` |

The 246-test result exceeds the user's baseline expectation of 246/246.

---

## 4. Spec compliance matrix

### 4.1 `species-folder/spec.md` (7 MUST requirements, 11 scenarios)

| # | Requirement | Scenario | Test (file:line) | Runtime result |
|---|-------------|----------|------------------|----------------|
| 1 | Create Folder Resolves Breadcrumb | First create returns 201 + path | `taxon/tests/test_api_router_workspace.py:145` `test_post_species_folder_returns_201_with_path` | PASS — `path` ends with `Panthera tigris`; `Path.is_dir()` checked |
| 1 | Create Folder Resolves Breadcrumb | Repeat returns 409 | `taxon/tests/test_api_router_workspace.py:158` `test_post_species_folder_repeat_returns_409` | PASS — 409 with `detail: str` |
| 2 | AQUALIFE_ROOT Resolves Project Root | Default root resolves against project root | `taxon/tests/test_aqualife_root.py:25` `test_default_root_resolves_against_project_root` | PASS — `os.chdir(tmp_path/subfolder)` then resolves to `<project_root>/Proyecto-Aqualife` |
| 2 | AQUALIFE_ROOT Resolves Project Root | Unwritable root fails 500 | `taxon/tests/test_aqualife_root.py:63` `test_unwritable_root_raises_api_error_500` | PASS — `APIError(status_code=500, detail="AQUALIFE_ROOT not writable: <path> from cwd <cwd>")` |
| 3 | Existence Check Returns Path or 404 | Existing row returns 200 | `taxon/tests/test_api_router_workspace.py:172` `test_get_species_folder_returns_path` | PASS |
| 3 | Existence Check Returns Path or 404 | Missing row returns 404 | `taxon/tests/test_api_router_workspace.py:182` `test_get_species_folder_missing_returns_404` | PASS |
| 4 | `(genus, epithet)` Survives Re-Imports | Folder row survives `taxa.id` bump | `taxon/tests/test_rebind_after_taxa_id_bump.py:149` `test_species_folder_row_survives_taxa_id_bump` | PASS — UPDATE `taxa.id` from 7 to 99; row still queryable by `(Panthera, tigris)` |
| 5 | Folder Path Rounds Clean for ASCII-Only | ASCII segments join verbatim | `taxon/tests/test_aqualife_root.py:125` `test_root_path_segments_join_verbatim_with_os_sep`; covered by `_species_folder_path` at `taxon/api/workspace.py:217-236` | PASS — literal mixed-case + spaces + punctuation preserved verbatim |
| 6 | Standalone Migrate Script | dry-run reports without mutating | `taxon/tests/test_migrate.py:85` `test_dry_run_reports_missing_tables`; `taxon/tests/test_migrate.py:154` `test_dry_run_after_apply_reports_no_missing` | PASS — `dry-run` stdout prints the 3 table names; DB unchanged |
| 6 | Standalone Migrate Script | apply creates 3 tables | `taxon/tests/test_migrate.py:104` `test_apply_creates_three_new_tables`; `taxon/tests/test_migrate.py:118` `test_apply_is_idempotent`; `taxon/tests/test_migrate.py:134` `test_apply_does_not_drop_pre_existing_tables` | PASS — `apply` creates `species_explored, species_folders, link_visited`; idempotent on second run; pre-existing `taxa` + `species_paths` preserved |
| 7 | FastAPI Lifespan Bootstraps Schema | Fresh DB serves after boot | `taxon/tests/test_workspace_resolver.py:61` `test_create_all_brings_up_three_new_tables` (covers the create_all call that the lifespan uses at `taxon/api/__init__.py:140-161`); runtime smoke `create_app(database_url='sqlite:///:memory:')` + `TestClient` boots and serves `/api/explored/list` empty + `/api/species-folder/...` 404 | PASS |

### 4.2 `link-visited/spec.md` (5 MUST requirements, 8 scenarios)

| # | Requirement | Scenario | Test (file:line) | Runtime result |
|---|-------------|----------|------------------|----------------|
| 1 | Mark Source Visited Is Idempotent | First POST returns 204 + persists | `taxon/tests/test_api_router_workspace.py:193` `test_post_link_visited_returns_204` | PASS |
| 1 | Mark Source Visited Is Idempotent | Repeat POST refreshes `visited_at` | `taxon/tests/test_api_router_workspace.py:199` `test_post_link_visited_idempotent` | PASS — both calls return 204 |
| 2 | Unmark Source Visited Removes Row | Existing row deletion returns 204 | `taxon/tests/test_api_router_workspace.py:213` `test_delete_link_visited_returns_204` | PASS |
| 2 | Unmark Source Visited Removes Row | Missing row deletion is no-op | `taxon/tests/test_api_router_workspace.py:220` `test_delete_link_visited_missing_returns_204` | PASS — 204 (not 404) |
| 3 | Hydrate Visited Set per Species | Existing rows return list | `taxon/tests/test_api_router_workspace.py:236` `test_get_link_visited_returns_rows` | PASS — list carries `Wikipedia` + `Google` with timestamps |
| 3 | Hydrate Visited Set per Species | No rows returns empty list | `taxon/tests/test_api_router_workspace.py:226` `test_get_link_visited_empty_envelope` | PASS — `{"sources": []}` (not 404) |
| 4 | `(genus, epithet)` Walk Survives Re-Imports | Visited set survives `taxa.id` bump | `taxon/tests/test_rebind_after_taxa_id_bump.py:169` `test_link_visited_rows_survive_taxa_id_bump` | PASS — `Wikipedia` + `Google` rows survive UPDATE `taxa.id` 7 → 99 |
| 5 | Source Label Is Template Canonical | URL changes but source stays | `taxon/tests/test_api_router_workspace.py:250` `test_get_link_visited_keys_on_source_label_not_url` | PASS — endpoint keys on `source` (canonical name), not on substituted URL |

### 4.3 `species-explored/spec.md` (5 MUST requirements, 8 scenarios)

| # | Requirement | Scenario | Test (file:line) | Runtime result |
|---|-------------|----------|------------------|----------------|
| 1 | Set Explored Flag Is Idempotent | First POST returns 200 with species row | `taxon/tests/test_api_router_workspace.py:77` `test_post_explored_returns_species_row` | PASS — body carries `id, canonical_name, display_name, markers, breadcrumb, genus, epithet, explored_at` |
| 1 | Set Explored Flag Is Idempotent | Repeat POST refreshes `explored_at` | `taxon/tests/test_api_router_workspace.py:88` `test_post_explored_idempotent_refines_timestamp` | PASS — both calls return 200; list still has 1 row |
| 2 | Unset Explored Flag Removes Row | Existing row deletion returns 204 | `taxon/tests/test_api_router_workspace.py:109` `test_delete_explored_returns_204` | PASS |
| 2 | Unset Explored Flag Removes Row | Missing row deletion is no-op | `taxon/tests/test_api_router_workspace.py:116` `test_delete_explored_missing_returns_204` | PASS — 204 (not 404) |
| 3 | `(genus, epithet)` Walk Survives Re-Imports | Re-import preserves explored flag | `taxon/tests/test_rebind_after_taxa_id_bump.py:130` `test_explored_row_survives_taxa_id_bump` | PASS |
| 4 | GET /list Endpoint Hydrates Workspace | Existing rows return list | `taxon/tests/test_api_router_workspace.py:129` `test_get_explored_list_returns_rows` | PASS |
| 4 | GET /list Endpoint Hydrates Workspace | No rows returns empty list | `taxon/tests/test_api_router_workspace.py:122` `test_get_explored_list_empty_envelope` | PASS — `{"species": []}` (not 404) |
| 5 | Cross-Reload Survival | Reload restores explored state | `taxon/tests/test_api_router_workspace.py:122 + :129` (hydrates via `/api/explored/list`); full browser reload survival is covered by the persistence contract (rows survive process restart via SQLite) + the `test_get_explored_list_returns_rows` / `test_post_explored_idempotent_refines_timestamp` pair. The frontend `hydrate()` action lives in PR2 (out of PR1 scope). | PASS (backend portion) |

### 4.4 Cross-spec structural invariants

| Invariant | Test (file:line) | Runtime result |
|-----------|------------------|----------------|
| `species_explored` PK = `(genus, epithet)` | `taxon/tests/test_workspace_resolver.py:72` `test_species_explored_primary_key_is_genus_epithet` | PASS |
| `species_folders` PK = `(genus, epithet)` | `taxon/tests/test_workspace_resolver.py:82` `test_species_folders_primary_key_is_genus_epithet` | PASS |
| `link_visited` PK = `(genus, epithet, source_label)` | `taxon/tests/test_workspace_resolver.py:92` `test_link_visited_primary_key_is_genus_epithet_source` | PASS |
| `species_explored` has NO FK to `taxa` | `taxon/tests/test_workspace_resolver.py:102` `test_species_explored_has_no_foreign_key_to_taxa` | PASS |
| `species_folders` has NO FK to `taxa` | `taxon/tests/test_workspace_resolver.py:107` `test_species_folders_has_no_foreign_key_to_taxa` | PASS |
| `link_visited` has NO FK to `taxa` | `taxon/tests/test_workspace_resolver.py:112` `test_link_visited_has_no_foreign_key_to_taxa` | PASS |
| `WORKSPACE_TABLES` enum is exact | `taxon/tests/test_workspace_resolver.py:56` `test_workspace_tables_constant_matches_metadata`; `taxon/tests/test_rebind_after_taxa_id_bump.py:209` `test_workspace_tables_constant_excludes_taxa_and_species_paths` | PASS |
| `species_folders.path` is UNIQUE | `taxon/tests/test_workspace_resolver.py:132` `test_species_folders_path_column_is_unique` | PASS |

**Coverage verdict**: every MUST scenario across the 3 backend specs has a covering test that passed at runtime. 0 CRITICAL `UNTESTED` / `FAILING` items.

---

## 5. Correctness table

| Behaviour | Source line | Test (file:line) | Notes |
|-----------|-------------|------------------|-------|
| POST `/api/explored/{g}/{e}` → 200 + species row | `taxon/api/router.py:854-884` | `test_api_router_workspace.py:77,88` | idempotent; refreshes `explored_at` |
| DELETE `/api/explored/{g}/{e}` → 204 (idempotent) | `taxon/api/router.py:887-897` | `test_api_router_workspace.py:109,116` | no 404 on missing |
| GET `/api/explored/list` → 200 `{species: []}` or rows | `taxon/api/router.py:900-922` | `test_api_router_workspace.py:122,129` | always 200, empty envelope when no rows |
| POST `/api/species-folder/{g}/{e}` → 201 (first) / 409 (dup) / 404 (unknown) | `taxon/api/router.py:925-950`; `taxon/api/workspace.py:284-311` | `test_api_router_workspace.py:145,158,166` | path persisted; `Path.mkdir(parents=True, exist_ok=True)` |
| GET `/api/species-folder/{g}/{e}` → 200 `{path}` / 404 | `taxon/api/router.py:953-978` | `test_api_router_workspace.py:172,182` | 404 when row missing |
| POST `/api/link-visited/{g}/{e}/{source}` → 204 | `taxon/api/router.py:981-1000` | `test_api_router_workspace.py:193,199,207` | idempotent; 404 when species unknown |
| DELETE `/api/link-visited/{g}/{e}/{source}` → 204 | `taxon/api/router.py:1003-1017` | `test_api_router_workspace.py:213,220` | idempotent |
| GET `/api/link-visited/{g}/{e}` → 200 `{sources: []}` or rows | `taxon/api/router.py:1020-1039` | `test_api_router_workspace.py:226,236,250` | sources sorted by `source_label` |

---

## 6. Design coherence table

| Design decision (`design.md` §) | Implementation | Notes |
|----------------------------------|----------------|-------|
| §2 Storage — PK `(genus, epithet)` for `species_explored` / `species_folders`; PK `(genus, epithet, source_label)` for `link_visited` | `taxon/api/workspace.py:62,84,107` | matches |
| §2 Storage — UNIQUE `species_folders.path` | `taxon/api/workspace.py:88` (`unique=True`) | matches |
| §2 Storage — NO FK to `taxa.id` | `taxon/api/workspace.py:65-66,86-87,111-113` (no `ForeignKey("taxa.id")`); structural test `test_workspace_resolver.py:102-129` | matches |
| §3 API contract — 8 endpoints, registered BEFORE `/{path:path}/taxon-links` catch-all | `taxon/api/router.py:854-1039` (workspace endpoints) precedes `taxon/api/router.py:1053-1111` (catch-all) | matches; OpenAPI registration order verified |
| §3 API contract — Uniform `ErrorResponse` body `{detail: str}` | `taxon/api/errors.py` `_handle_api_error` + `taxon/api/__init__.py:204-211` | matches |
| §3 API contract — Status codes per table | matches implementation; cross-checked against spec scenarios | matches |
| §5 UI flow (backend surface) — folder POST returns breadcrumb-joined path | `taxon/api/workspace.py:217-236` `_species_folder_path` calls `build_breadcrumb(session, species.id)` then `root.joinpath(*breadcrumb, leaf)` | matches |
| §6 `AQUALIFE_ROOT` — env var, project-root-relative, fail-loudly 500 | `taxon/api/workspace.py:150-176` `resolve_aqualife_root`; `taxon/api/errors.py` `APIError(status_code=500)` | matches |
| §7 Migration — lifespan `create_all` for 3 new tables + `taxon/migrate.py` standalone | `taxon/api/__init__.py:140-161` (lifespan); `taxon/migrate.py:65-74` (`_run_apply`) | matches |

No design deviation detected.

---

## 7. Runtime harness results

### 7.1 FastAPI lifespan smoke

Built `create_app(database_url="sqlite:///:memory:")` + `TestClient` in-memory app:

```
GET /api/explored/list           -> 200 {"species": []}
GET /api/species-folder/Panthera/tigris -> 404 {"detail": "species folder not found: Panthera 'tigris'"}
GET /api/link-visited/Panthera/tigris   -> 200 {"genus": "Panthera", "epithet": "tigris", "sources": []}
GET /api/_meta                          -> 200 {"phase": "2C"}
```

Lifespan bootstraps the 3 new tables; pre-existing endpoints unaffected.

### 7.2 Real `python -m taxon.migrate` against temp DB

| Stage | Output |
|-------|--------|
| `dry-run` (empty DB) | `[dry-run] missing tables: species_explored, species_folders, link_visited (run \`python -m taxon.migrate apply\` to create them)`. Exit 1. DB unchanged on disk (0 tables). |
| `apply` (empty DB) | `[apply] created 3 table(s): species_explored, species_folders, link_visited`. Exit 0. SQLite lists the 3 tables. |
| `apply` (second run, populated DB) | `[apply] all 3 workspace tables already present; no changes made`. Exit 0. Idempotent — no error, no table dropped. |

### 7.3 Edge cases (runtime, outside the test suite)

| Edge case | Behaviour observed | Spec scenario |
|-----------|--------------------|---------------|
| Unknown `(genus, epithet)` GET folder → 404 + `{detail: str}` | 404 `{"detail": "species folder not found: Nonexistentus 'species'"}` | species-folder §3 "Missing row returns 404" |
| Duplicate folder POST → 409 + `{detail: str}` | 409 `{"detail": "species folder already exists: Panthera 'tigris'"}` | species-folder §1 "Repeat create returns 409" |
| DELETE missing row → 204 (idempotent) | 204 for both `/api/explored/...` and `/api/link-visited/...` | species-explored §2 + link-visited §2 "Missing row deletion is a no-op" |
| AQUALIFE_ROOT unwriteable (chmod 555) → 500 + actionable detail | `APIError(status_code=500, detail="AQUALIFE_ROOT not writable: <path> from cwd <cwd>")` | species-folder §2 "Unwritable root fails loudly" |
| AQUALIFE_ROOT default, cwd = `tmp_path/subfolder` | Resolves to `<project_root>/Proyecto-Aqualife` (NOT `<cwd>/Proyecto-Aqualife`) | species-folder §2 "Default root resolves against project root, not cwd" |

---

## 8. Re-bind discipline verification

| Check | Result |
|-------|--------|
| Manual `taxa.id` bump for `Panthera tigris` (UPDATE 7 → 9999) | rows survive via `(genus, epithet)` key |
| `/api/explored/list` after bump | `Panthera tigris` still listed |
| `/api/species-folder/Panthera/tigris` after bump | returns same `path` (ends with `Panthera tigris`) |
| `/api/link-visited/Panthera/tigris` after bump | `Wikipedia` still in `sources` |
| `SpeciesExplored.__table__.foreign_keys` | empty |
| `SpeciesFolder.__table__.foreign_keys` | empty |
| `LinkVisited.__table__.foreign_keys` | empty |
| `assert not model.__table__.foreign_keys` | PASS (all 3 models) |

Pinned by `test_rebind_after_taxa_id_bump.py` (5 tests).

---

## 9. Endpoint registration order verification

OpenAPI route registration order (from `app.openapi()['paths']`, the
canonical source FastAPI uses at runtime):

```
0   /healthz
1   /api/_meta
2   /api/path-children
3   /api/species-list
4   /api/kingdoms
5   /api/{kingdom}/phyla
6   /api/{kingdom}/{phylum}/classes
7   /api/{kingdom}/{phylum}/{class_name}/orders
8   /api/{kingdom}/{phylum}/{class_name}/{order_name}/families
9   /api/{kingdom}/{phylum}/{class_name}/{order_name}/{family_name}/genera
10  /api/{kingdom}/{phylum}/{class_name}/{order_name}/{family_name}/{genus_name}/species
11  /api/{kingdom}/{phylum}/{class_name}/{order_name}/{family_name}/{genus_name}/{epithet}
12  /api/species/{genus_name}/{epithet}
13  /api/{kingdom}/{phylum}/{class_name}/{order_name}/{family_name}/{genus_name}/{epithet}/links
14  /api/tree/children                  (tree, PR-arbol-col-browse)
15  /api/tree/search                    (tree, PR-arbol-col-browse)
16  /api/explored/{genus}/{epithet}     (workspace, PR1)
17  /api/explored/list                  (workspace, PR1)
18  /api/species-folder/{genus}/{epithet}  (workspace, PR1)
19  /api/link-visited/{genus}/{epithet}/{source}  (workspace, PR1)
20  /api/link-visited/{genus}/{epithet}  (workspace, PR1)
21  /api/{path}/taxon-links             (catch-all)
```

| Prefix | First index | Catch-all index | Before catch-all? |
|--------|-------------|-----------------|-------------------|
| `/api/explored` | 16 | 21 | ✅ |
| `/api/species-folder` | 18 | 21 | ✅ |
| `/api/link-visited` | 19 | 21 | ✅ |
| `/api/tree` (pre-existing regression discipline) | 14 | 21 | ✅ |

No CRITICAL: workspace endpoints do not get shadowed by the catch-all.
Pinned by `test_api_router_workspace.py:265` `test_workspace_endpoints_registered_before_taxon_links_catchall`.

---

## 10. Issues

### 10.1 CRITICAL

**None.** Every MUST requirement across the 3 backend specs has at least
one test that passed at runtime. All verify-stack commands exit 0.

### 10.2 WARNING

| ID | Description | Suggested fix |
|----|-------------|---------------|
| W1 | `tasks.md` phase 1 (1.1 through 1.13) still shows `- [ ]` for all 13 task checkboxes despite the implementation being complete and all tests green. The sdd-apply sub-agent did not mark tasks complete on the file. Per `sdd-apply/SKILL.md` "Update `tasks.md` with `[x]` marks" (openspec persistence mode). | Mark all 13 phase-1 tasks as `[x]` in a follow-up docs commit (e.g. `docs(openspec): mark PR1 tasks complete after verify`). This is a documentation drift, NOT a code defect — the implementation is correct and tests pass. |

### 10.3 SUGGESTION

| ID | Description |
|----|-------------|
| S1 | `_lookup_species_by_pair` at `taxon/api/router.py:462-528` walks parent chains manually for each genus candidate. With ≥10 genera sharing a name this is O(N×D); a single CTE would be cheaper. Out of PR1 scope; consider for a follow-up perf PR. |
| S2 | `taxon/api/router.py:870` uses a local import (`from taxon.api.router import _species_response`) inside the endpoint body to dodge a cycle. A top-level `TYPE_CHECKING` import would make this cleaner without changing runtime behaviour. |
| S3 | `taxon/migrate.py:34` reads `DEFAULT_DATABASE_URL` from a hard-coded `sqlite:///./data/taxon.db`. If `data/` doesn't exist, `_resolve_database_url` creates the parent. Consider documenting the env var precedence more loudly (`TAXON_DATABASE_URL > --database-url > default`). |
| S4 | The `taxon/api/router.py:911` payload for `GET /api/explored/list` echoes `id=-1` because the workspace store keys on `(genus, epithet)`. Frontend (PR2) ignores the id; consider removing the field or making it nullable in `ExploredResponse` to avoid confusing API consumers. |

---

## 11. Final verdict

**PASS** — all 17 MUST requirements + 27 scenarios across the 3 backend
specs are covered by tests that passed at runtime; all 3 verify-stack
commands (`pytest`, `ruff format --check`, `ruff check`) exit 0; the
rebind discipline, endpoint registration order, AQUALIFE_ROOT
project-relative resolution, lifespan bootstrap, and standalone
`taxon.migrate` script all behave as specified.

The single WARNING (W1, stale `tasks.md` checkboxes) is a documentation
drift; the orchestrator should run a follow-up `docs(openspec)` commit
to mark the 13 phase-1 tasks `[x]` after the merge to `develop`. No
code change is required.

**Recommendation**: ready for `branch-pr` against `develop`.

---

## 12. Files written by this verification

- `openspec/changes/species-folder-explorer/verify-report-pr1.md` (this file)
- `documents-es/openspec/changes/species-folder-explorer/verify-report-pr1-es.md` (Spanish mirror, per AGENTS.md §1)

## 13. Engram observation

- `sdd/species-folder-explorer/verify-report-pr1` (topic_key; type=`architecture`; `capture_prompt=false`)
