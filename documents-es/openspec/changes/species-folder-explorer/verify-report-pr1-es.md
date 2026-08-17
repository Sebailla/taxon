# Informe de verificación — species-folder-explorer PR1 (backend)

> **Alcance**: PR1 de `species-folder-explorer` (issue #68, superficie
> backend). 3 PR encadenados (`auto-chain` según caché de preflight); cada
> uno ≤350 LOC. Este informe cubre solo el backend — los PR frontend
> PR2/PR3 (workspaceStore, columna final de `SpeciesList`, switch inicial
> de `SpeciesLinks`, ExplorerPanel, doc de diseño + learn-es) quedan
> fuera del alcance.
>
> **Commits verificados**:
> - `1948bbc` — `feat(schema): add workspace ORM models with PK (genus, epithet) re-bind columns`
> - `61ee5f2` — `feat(api): add 8 workspace endpoints + Pydantic schemas + aqualife_root tests`
> - `cb631f7` — `docs(openspec): sync Spanish mirrors + fix species-folder spec line 11`
>
> **Veredicto**: **APROBADO** (todos los requisitos MUST del spec
> cubiertos con tests que pasaron en tiempo de ejecución; todas las
> verificaciones de la pila en verde; un WARNING por checkboxes
> obsoletos en `tasks.md` que el orquestador debería marcar después del
> merge).

---

## 1. Resumen del cambio

| Campo | Valor |
|-------|-------|
| Nombre del cambio | species-folder-explorer |
| Issue | #68 |
| PR | PR1 (backend) |
| Rama | feat/species-folder-explorer-pr1 |
| Estrategia | `auto-chain` según preflight; PR1 → PR2 → PR3 |
| Specs en alcance (PR1) | species-folder, link-visited, species-explored |
| Specs fuera de alcance (PR3) | workspace-explorer |
| LOC autorales (PR1) | 2043 añadidos / 2 eliminados en 11 archivos |
| Modo de persistencia | `hybrid` (engram + archivo openspec) |

---

## 2. Tabla de completitud

| Artefacto | Estado | Notas |
|-----------|--------|-------|
| `proposal.md` (EN) | presente | líneas 1-206 |
| `proposal-es.md` (espejo ES) | presente | misma extensión, traducción fiel |
| `design.md` (EN) | presente | líneas 1-117 |
| `design-es.md` (espejo ES) | presente | |
| `tasks.md` (EN) | presente, **OBSOLETO** | 13 tareas de la fase 1 siguen como `- [ ]` (sin marcar) |
| `tasks-es.md` (espejo ES) | presente | |
| `specs/species-folder/spec.md` | presente, 7 requisitos / 11 escenarios | línea 11 corregida en `cb631f7` |
| `specs/species-folder/spec-es.md` | presente | |
| `specs/link-visited/spec.md` | presente, 5 requisitos / 8 escenarios | |
| `specs/link-visited/spec-es.md` | presente | |
| `specs/species-explored/spec.md` | presente, 5 requisitos / 8 escenarios | |
| `specs/species-explored/spec-es.md` | presente | |
| `specs/workspace-explorer/spec.md` | presente, **fuera del alcance del PR1** | frontend PR3 |
| Implementación (`taxon/api/workspace.py`, `taxon/migrate.py`, `taxon/api/router.py`) | presente | 2043 LOC añadidos |
| Tests backend | presentes | 5 archivos nuevos; 54 tests del workspace |

---

## 3. Evidencia de build / tests / cobertura

| Verificación | Comando | Salida | Notas |
|--------------|---------|--------|-------|
| pytest completo | `python -m pytest --tb=short -q` | **0** | **246 / 246 pasaron en 13.57s** (54 tests nuevos del workspace + 192 preexistentes). `test_output_hash`: `e3e00b59dfdc0eb23ce8173eede4df256236f8e203e63d188c83d61275da9884` |
| ruff format | `ruff format --check .` | **0** | "57 files already formatted". `build_output_hash`: `d642ac445c009c50f49745da4dd05334f2c9e817132c16c3b6785e9b4da5831d` |
| ruff check | `ruff check .` | **0** | "All checks passed!". hash: `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` |

El resultado de 246 tests supera la expectativa base del usuario de 246/246.

---

## 4. Matriz de cumplimiento del spec

### 4.1 `species-folder/spec.md` (7 requisitos MUST, 11 escenarios)

| # | Requisito | Escenario | Test (archivo:línea) | Resultado en tiempo de ejecución |
|---|-----------|-----------|----------------------|----------------------------------|
| 1 | Create Folder Resolves Breadcrumb | First create returns 201 + path | `taxon/tests/test_api_router_workspace.py:145` `test_post_species_folder_returns_201_with_path` | APROBADO — `path` termina en `Panthera tigris`; `Path.is_dir()` verificado |
| 1 | Create Folder Resolves Breadcrumb | Repeat returns 409 | `taxon/tests/test_api_router_workspace.py:158` `test_post_species_folder_repeat_returns_409` | APROBADO — 409 con `detail: str` |
| 2 | AQUALIFE_ROOT Resolves Project Root | Default root resolves against project root | `taxon/tests/test_aqualife_root.py:25` `test_default_root_resolves_against_project_root` | APROBADO — `os.chdir(tmp_path/subfolder)` y resuelve a `<project_root>/Proyecto-Aqualife` |
| 2 | AQUALIFE_ROOT Resolves Project Root | Unwritable root fails 500 | `taxon/tests/test_aqualife_root.py:63` `test_unwritable_root_raises_api_error_500` | APROBADO — `APIError(status_code=500, detail="AQUALIFE_ROOT not writable: <path> from cwd <cwd>")` |
| 3 | Existence Check Returns Path or 404 | Existing row returns 200 | `taxon/tests/test_api_router_workspace.py:172` `test_get_species_folder_returns_path` | APROBADO |
| 3 | Existence Check Returns Path or 404 | Missing row returns 404 | `taxon/tests/test_api_router_workspace.py:182` `test_get_species_folder_missing_returns_404` | APROBADO |
| 4 | `(genus, epithet)` Survives Re-Imports | Folder row survives `taxa.id` bump | `taxon/tests/test_rebind_after_taxa_id_bump.py:149` `test_species_folder_row_survives_taxa_id_bump` | APROBADO — UPDATE `taxa.id` de 7 a 99; la fila sigue consultable por `(Panthera, tigris)` |
| 5 | Folder Path Rounds Clean for ASCII-Only | ASCII segments join verbatim | `taxon/tests/test_aqualife_root.py:125` `test_root_path_segments_join_verbatim_with_os_sep`; cubierto por `_species_folder_path` en `taxon/api/workspace.py:217-236` | APROBADO — se preservan literalmente mayúsculas/minúsculas, espacios y puntuación |
| 6 | Standalone Migrate Script | dry-run reports without mutating | `taxon/tests/test_migrate.py:85` `test_dry_run_reports_missing_tables`; `taxon/tests/test_migrate.py:154` `test_dry_run_after_apply_reports_no_missing` | APROBADO — el stdout de `dry-run` lista las 3 tablas; la DB no cambia |
| 6 | Standalone Migrate Script | apply creates 3 tables | `taxon/tests/test_migrate.py:104` `test_apply_creates_three_new_tables`; `taxon/tests/test_migrate.py:118` `test_apply_is_idempotent`; `taxon/tests/test_migrate.py:134` `test_apply_does_not_drop_pre_existing_tables` | APROBADO — `apply` crea `species_explored, species_folders, link_visited`; idempotente en segunda corrida; `taxa` + `species_paths` preexistentes se preservan |
| 7 | FastAPI Lifespan Bootstraps Schema | Fresh DB serves after boot | `taxon/tests/test_workspace_resolver.py:61` `test_create_all_brings_up_three_new_tables` (cubre la llamada `create_all` que usa el lifespan en `taxon/api/__init__.py:140-161`); smoke en runtime `create_app(database_url='sqlite:///:memory:')` + `TestClient` arranca y sirve `/api/explored/list` vacío + `/api/species-folder/...` 404 | APROBADO |

### 4.2 `link-visited/spec.md` (5 requisitos MUST, 8 escenarios)

| # | Requisito | Escenario | Test (archivo:línea) | Resultado en tiempo de ejecución |
|---|-----------|-----------|----------------------|----------------------------------|
| 1 | Mark Source Visited Is Idempotent | First POST returns 204 + persists | `taxon/tests/test_api_router_workspace.py:193` `test_post_link_visited_returns_204` | APROBADO |
| 1 | Mark Source Visited Is Idempotent | Repeat POST refreshes `visited_at` | `taxon/tests/test_api_router_workspace.py:199` `test_post_link_visited_idempotent` | APROBADO — ambas llamadas devuelven 204 |
| 2 | Unmark Source Visited Removes Row | Existing row deletion returns 204 | `taxon/tests/test_api_router_workspace.py:213` `test_delete_link_visited_returns_204` | APROBADO |
| 2 | Unmark Source Visited Removes Row | Missing row deletion is no-op | `taxon/tests/test_api_router_workspace.py:220` `test_delete_link_visited_missing_returns_204` | APROBADO — 204 (no 404) |
| 3 | Hydrate Visited Set per Species | Existing rows return list | `taxon/tests/test_api_router_workspace.py:236` `test_get_link_visited_returns_rows` | APROBADO — la lista contiene `Wikipedia` + `Google` con timestamps |
| 3 | Hydrate Visited Set per Species | No rows returns empty list | `taxon/tests/test_api_router_workspace.py:226` `test_get_link_visited_empty_envelope` | APROBADO — `{"sources": []}` (no 404) |
| 4 | `(genus, epithet)` Walk Survives Re-Imports | Visited set survives `taxa.id` bump | `taxon/tests/test_rebind_after_taxa_id_bump.py:169` `test_link_visited_rows_survive_taxa_id_bump` | APROBADO — las filas de `Wikipedia` + `Google` sobreviven al UPDATE `taxa.id` 7 → 99 |
| 5 | Source Label Is Template Canonical | URL changes but source stays | `taxon/tests/test_api_router_workspace.py:250` `test_get_link_visited_keys_on_source_label_not_url` | APROBADO — el endpoint indexa por `source` (nombre canónico), no por la URL sustituida |

### 4.3 `species-explored/spec.md` (5 requisitos MUST, 8 escenarios)

| # | Requisito | Escenario | Test (archivo:línea) | Resultado en tiempo de ejecución |
|---|-----------|-----------|----------------------|----------------------------------|
| 1 | Set Explored Flag Is Idempotent | First POST returns 200 with species row | `taxon/tests/test_api_router_workspace.py:77` `test_post_explored_returns_species_row` | APROBADO — el body lleva `id, canonical_name, display_name, markers, breadcrumb, genus, epithet, explored_at` |
| 1 | Set Explored Flag Is Idempotent | Repeat POST refreshes `explored_at` | `taxon/tests/test_api_router_workspace.py:88` `test_post_explored_idempotent_refines_timestamp` | APROBADO — ambas llamadas devuelven 200; la lista sigue teniendo 1 fila |
| 2 | Unset Explored Flag Removes Row | Existing row deletion returns 204 | `taxon/tests/test_api_router_workspace.py:109` `test_delete_explored_returns_204` | APROBADO |
| 2 | Unset Explored Flag Removes Row | Missing row deletion is no-op | `taxon/tests/test_api_router_workspace.py:116` `test_delete_explored_missing_returns_204` | APROBADO — 204 (no 404) |
| 3 | `(genus, epithet)` Walk Survives Re-Imports | Re-import preserves explored flag | `taxon/tests/test_rebind_after_taxa_id_bump.py:130` `test_explored_row_survives_taxa_id_bump` | APROBADO |
| 4 | GET /list Endpoint Hydrates Workspace | Existing rows return list | `taxon/tests/test_api_router_workspace.py:129` `test_get_explored_list_returns_rows` | APROBADO |
| 4 | GET /list Endpoint Hydrates Workspace | No rows returns empty list | `taxon/tests/test_api_router_workspace.py:122` `test_get_explored_list_empty_envelope` | APROBADO — `{"species": []}` (no 404) |
| 5 | Cross-Reload Survival | Reload restores explored state | `taxon/tests/test_api_router_workspace.py:122 + :129` (hidrata vía `/api/explored/list`); la supervivencia completa ante recarga de navegador está cubierta por el contrato de persistencia (las filas sobreviven al reinicio del proceso vía SQLite) + el par `test_get_explored_list_returns_rows` / `test_post_explored_idempotent_refines_timestamp`. La acción `hydrate()` del frontend vive en el PR2 (fuera del alcance del PR1). | APROBADO (porción backend) |

### 4.4 Invariantes estructurales cross-spec

| Invariante | Test (archivo:línea) | Resultado en tiempo de ejecución |
|------------|----------------------|----------------------------------|
| `species_explored` PK = `(genus, epithet)` | `taxon/tests/test_workspace_resolver.py:72` `test_species_explored_primary_key_is_genus_epithet` | APROBADO |
| `species_folders` PK = `(genus, epithet)` | `taxon/tests/test_workspace_resolver.py:82` `test_species_folders_primary_key_is_genus_epithet` | APROBADO |
| `link_visited` PK = `(genus, epithet, source_label)` | `taxon/tests/test_workspace_resolver.py:92` `test_link_visited_primary_key_is_genus_epithet_source` | APROBADO |
| `species_explored` SIN FK a `taxa` | `taxon/tests/test_workspace_resolver.py:102` `test_species_explored_has_no_foreign_key_to_taxa` | APROBADO |
| `species_folders` SIN FK a `taxa` | `taxon/tests/test_workspace_resolver.py:107` `test_species_folders_has_no_foreign_key_to_taxa` | APROBADO |
| `link_visited` SIN FK a `taxa` | `taxon/tests/test_workspace_resolver.py:112` `test_link_visited_has_no_foreign_key_to_taxa` | APROBADO |
| Enum `WORKSPACE_TABLES` exacto | `taxon/tests/test_workspace_resolver.py:56` `test_workspace_tables_constant_matches_metadata`; `taxon/tests/test_rebind_after_taxa_id_bump.py:209` `test_workspace_tables_constant_excludes_taxa_and_species_paths` | APROBADO |
| `species_folders.path` es UNIQUE | `taxon/tests/test_workspace_resolver.py:132` `test_species_folders_path_column_is_unique` | APROBADO |

**Veredicto de cobertura**: cada escenario MUST de los 3 specs del backend tiene un test que pasó en tiempo de ejecución. 0 ítems CRITICAL `UNTESTED` / `FAILING`.

---

## 5. Tabla de corrección

| Comportamiento | Línea en código fuente | Test (archivo:línea) | Notas |
|----------------|------------------------|----------------------|-------|
| POST `/api/explored/{g}/{e}` → 200 + fila de la especie | `taxon/api/router.py:854-884` | `test_api_router_workspace.py:77,88` | idempotente; refresca `explored_at` |
| DELETE `/api/explored/{g}/{e}` → 204 (idempotente) | `taxon/api/router.py:887-897` | `test_api_router_workspace.py:109,116` | sin 404 cuando falta |
| GET `/api/explored/list` → 200 `{species: []}` o filas | `taxon/api/router.py:900-922` | `test_api_router_workspace.py:122,129` | siempre 200, sobre vacío envelope |
| POST `/api/species-folder/{g}/{e}` → 201 (primera) / 409 (duplicada) / 404 (desconocida) | `taxon/api/router.py:925-950`; `taxon/api/workspace.py:284-311` | `test_api_router_workspace.py:145,158,166` | ruta persistida; `Path.mkdir(parents=True, exist_ok=True)` |
| GET `/api/species-folder/{g}/{e}` → 200 `{path}` / 404 | `taxon/api/router.py:953-978` | `test_api_router_workspace.py:172,182` | 404 cuando falta la fila |
| POST `/api/link-visited/{g}/{e}/{source}` → 204 | `taxon/api/router.py:981-1000` | `test_api_router_workspace.py:193,199,207` | idempotente; 404 cuando se desconoce la especie |
| DELETE `/api/link-visited/{g}/{e}/{source}` → 204 | `taxon/api/router.py:1003-1017` | `test_api_router_workspace.py:213,220` | idempotente |
| GET `/api/link-visited/{g}/{e}` → 200 `{sources: []}` o filas | `taxon/api/router.py:1020-1039` | `test_api_router_workspace.py:226,236,250` | fuentes ordenadas por `source_label` |

---

## 6. Tabla de coherencia con el diseño

| Decisión de diseño (`design.md` §) | Implementación | Notas |
|--------------------------------------|----------------|-------|
| §2 Storage — PK `(genus, epithet)` para `species_explored` / `species_folders`; PK `(genus, epithet, source_label)` para `link_visited` | `taxon/api/workspace.py:62,84,107` | coincide |
| §2 Storage — UNIQUE `species_folders.path` | `taxon/api/workspace.py:88` (`unique=True`) | coincide |
| §2 Storage — SIN FK a `taxa.id` | `taxon/api/workspace.py:65-66,86-87,111-113` (sin `ForeignKey("taxa.id")`); test estructural `test_workspace_resolver.py:102-129` | coincide |
| §3 API contract — 8 endpoints, registrados ANTES del catch-all `/{path:path}/taxon-links` | `taxon/api/router.py:854-1039` (endpoints del workspace) precede a `taxon/api/router.py:1053-1111` (catch-all) | coincide; orden de registro OpenAPI verificado |
| §3 API contract — Cuerpo uniforme `ErrorResponse` `{detail: str}` | `taxon/api/errors.py` `_handle_api_error` + `taxon/api/__init__.py:204-211` | coincide |
| §3 API contract — Códigos de estado según tabla | coinciden con la implementación; revisados contra escenarios del spec | coincide |
| §5 UI flow (superficie backend) — POST de carpeta devuelve ruta con join de breadcrumb | `taxon/api/workspace.py:217-236` `_species_folder_path` llama a `build_breadcrumb(session, species.id)` y luego `root.joinpath(*breadcrumb, leaf)` | coincide |
| §6 `AQUALIFE_ROOT` — variable de entorno, relativa al root del proyecto, falla ruidosamente con 500 | `taxon/api/workspace.py:150-176` `resolve_aqualife_root`; `taxon/api/errors.py` `APIError(status_code=500)` | coincide |
| §7 Migration — `create_all` del lifespan para las 3 tablas nuevas + script `taxon/migrate.py` | `taxon/api/__init__.py:140-161` (lifespan); `taxon/migrate.py:65-74` (`_run_apply`) | coincide |

No se detectan desviaciones del diseño.

---

## 7. Resultados del runtime harness

### 7.1 Smoke del lifespan de FastAPI

Construido `create_app(database_url="sqlite:///:memory:")` + app en memoria con `TestClient`:

```
GET /api/explored/list                -> 200 {"species": []}
GET /api/species-folder/Panthera/tigris -> 404 {"detail": "species folder not found: Panthera 'tigris'"}
GET /api/link-visited/Panthera/tigris  -> 200 {"genus": "Panthera", "epithet": "tigris", "sources": []}
GET /api/_meta                         -> 200 {"phase": "2C"}
```

El lifespan arranca las 3 tablas nuevas; los endpoints preexistentes quedan intactos.

### 7.2 `python -m taxon.migrate` real contra DB temporal

| Etapa | Salida |
|-------|--------|
| `dry-run` (DB vacía) | `[dry-run] missing tables: species_explored, species_folders, link_visited (run \`python -m taxon.migrate apply\` to create them)`. Exit 1. DB sin cambios en disco (0 tablas). |
| `apply` (DB vacía) | `[apply] created 3 table(s): species_explored, species_folders, link_visited`. Exit 0. SQLite lista las 3 tablas. |
| `apply` (segunda corrida, DB poblada) | `[apply] all 3 workspace tables already present; no changes made`. Exit 0. Idempotente — sin error, sin tablas soltadas. |

### 7.3 Casos borde (runtime, fuera del suite de tests)

| Caso borde | Comportamiento observado | Escenario del spec |
|------------|--------------------------|--------------------|
| GET folder con `(genus, epithet)` desconocido → 404 + `{detail: str}` | 404 `{"detail": "species folder not found: Nonexistentus 'species'"}` | species-folder §3 "Missing row returns 404" |
| POST folder duplicado → 409 + `{detail: str}` | 409 `{"detail": "species folder already exists: Panthera 'tigris'"}` | species-folder §1 "Repeat create returns 409" |
| DELETE sobre fila faltante → 204 (idempotente) | 204 tanto para `/api/explored/...` como para `/api/link-visited/...` | species-explored §2 + link-visited §2 "Missing row deletion is a no-op" |
| AQUALIFE_ROOT no escribible (chmod 555) → 500 + detalle accionable | `APIError(status_code=500, detail="AQUALIFE_ROOT not writable: <path> from cwd <cwd>")` | species-folder §2 "Unwritable root fails loudly" |
| AQUALIFE_ROOT por defecto, cwd = `tmp_path/subfolder` | Resuelve a `<project_root>/Proyecto-Aqualife` (NO a `<cwd>/Proyecto-Aqualife`) | species-folder §2 "Default root resolves against project root, not cwd" |

---

## 8. Verificación de la disciplina de re-bind

| Verificación | Resultado |
|--------------|-----------|
| Bump manual de `taxa.id` para `Panthera tigris` (UPDATE 7 → 9999) | las filas sobreviven vía la clave `(genus, epithet)` |
| `/api/explored/list` después del bump | `Panthera tigris` sigue listado |
| `/api/species-folder/Panthera/tigris` después del bump | devuelve la misma `path` (termina en `Panthera tigris`) |
| `/api/link-visited/Panthera/tigris` después del bump | `Wikipedia` sigue en `sources` |
| `SpeciesExplored.__table__.foreign_keys` | vacío |
| `SpeciesFolder.__table__.foreign_keys` | vacío |
| `LinkVisited.__table__.foreign_keys` | vacío |
| `assert not model.__table__.foreign_keys` | APROBADO (los 3 modelos) |

Fijado por `test_rebind_after_taxa_id_bump.py` (5 tests).

---

## 9. Verificación del orden de registro de endpoints

Orden de registro de rutas en OpenAPI (de `app.openapi()['paths']`, la
fuente canónica que FastAPI usa en tiempo de ejecución):

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

| Prefijo | Primer índice | Índice del catch-all | ¿Antes del catch-all? |
|---------|---------------|----------------------|------------------------|
| `/api/explored` | 16 | 21 | ✅ |
| `/api/species-folder` | 18 | 21 | ✅ |
| `/api/link-visited` | 19 | 21 | ✅ |
| `/api/tree` (disciplina de regresión preexistente) | 14 | 21 | ✅ |

Sin CRITICAL: los endpoints del workspace no quedan ocultos por el catch-all.
Fijado por `test_api_router_workspace.py:265` `test_workspace_endpoints_registered_before_taxon_links_catchall`.

---

## 10. Issues

### 10.1 CRITICAL

**Ninguno.** Cada requisito MUST de los 3 specs del backend tiene al
menos un test que pasó en tiempo de ejecución. Todas las verificaciones
de la pila salen con 0.

### 10.2 WARNING

| ID | Descripción | Fix sugerido |
|----|-------------|--------------|
| W1 | `tasks.md` fase 1 (1.1 al 1.13) sigue mostrando `- [ ]` para los 13 checkboxes de tareas pese a que la implementación está completa y todos los tests pasan en verde. El sub-agente `sdd-apply` no marcó las tareas como completas en el archivo. Según `sdd-apply/SKILL.md` "Update `tasks.md` with `[x]` marks" (modo de persistencia openspec). | Marcar las 13 tareas de la fase 1 como `[x]` en un commit de docs de seguimiento (p. ej. `docs(openspec): mark PR1 tasks complete after verify`). Es un drift documental, NO un defecto de código — la implementación es correcta y los tests pasan. |

### 10.3 SUGGESTION

| ID | Descripción |
|----|-------------|
| S1 | `_lookup_species_by_pair` en `taxon/api/router.py:462-528` recorre cadenas de padres manualmente para cada género candidato. Con ≥10 géneros compartiendo nombre esto es O(N×D); un único CTE sería más barato. Fuera del alcance del PR1; considerar para un PR de performance de seguimiento. |
| S2 | `taxon/api/router.py:870` usa un import local (`from taxon.api.router import _species_response`) dentro del cuerpo del endpoint para esquivar un ciclo. Un import a nivel de módulo con `TYPE_CHECKING` lo dejaría más limpio sin cambiar el comportamiento en runtime. |
| S3 | `taxon/migrate.py:34` lee `DEFAULT_DATABASE_URL` desde un `sqlite:///./data/taxon.db` hard-codeado. Si `data/` no existe, `_resolve_database_url` crea el padre. Considerar documentar la precedencia de variables más sonoramente (`TAXON_DATABASE_URL > --database-url > default`). |
| S4 | El payload de `taxon/api/router.py:911` para `GET /api/explored/list` hace eco de `id=-1` porque el store del workspace indexa por `(genus, epithet)`. El frontend (PR2) ignora el id; considerar quitar el campo o hacerlo nullable en `ExploredResponse` para no confundir a consumidores de la API. |

---

## 11. Veredicto final

**APROBADO** — los 17 requisitos MUST + 27 escenarios de los 3 specs del
backend están cubiertos por tests que pasaron en tiempo de ejecución; las
3 verificaciones de la pila (`pytest`, `ruff format --check`, `ruff check`)
salen con 0; la disciplina de re-bind, el orden de registro de endpoints,
la resolución de AQUALIFE_ROOT relativa al proyecto, el bootstrap del
lifespan y el script independiente `taxon.migrate` se comportan como
especifica el spec.

El único WARNING (W1, checkboxes obsoletos en `tasks.md`) es un drift
documental; el orquestador debería correr un commit de seguimiento
`docs(openspec)` para marcar las 13 tareas de la fase 1 como `[x]`
después del merge a `develop`. No se requieren cambios de código.

**Recomendación**: listo para `branch-pr` contra `develop`.

---

## 12. Archivos escritos por esta verificación

- `openspec/changes/species-folder-explorer/verify-report-pr1.md` (este informe, inglés)
- `documents-es/openspec/changes/species-folder-explorer/verify-report-pr1-es.md` (espejo español, según AGENTS.md §1)

## 13. Observación en Engram

- `sdd/species-folder-explorer/verify-report-pr1` (`topic_key`; tipo=`architecture`; `capture_prompt=false`)
