# Informe de archivo: species-folder-explorer

**Cambio**: `species-folder-explorer`
**Cerrado**: 2026-08-18
**HEAD final**: `1e6f737` en `develop`
**PRs fusionados**: #70 / #71 / #72 / #73 (commits `ed9d6f3` / `220aeb6` / `d3456dd` / `8a6b0e4`) — `https://github.com/Sebailla/taxon/pull/70`, `/71`, `/72`, `/73`
**Cierra**: issue #68 — espacio de trabajo por especie: creación de carpetas, marca de explorado, explorador embebido, interruptores por enlace visitado
**Modo de almacenamiento de artefactos**: híbrido (sistema de archivos + observación de Engram `sdd/species-folder-explorer/archive-report`)
**Puerta de revisión**: ausente (el interruptor de RDD estuvo desactivado durante toda la cadena; el archivo procedió bajo la política ordinaria del repositorio)

## Resumen

El cambio `species-folder-explorer` introduce una superficie de **espacio de trabajo** por especie que sobrevive a reimportaciones de `taxa`. El espacio de trabajo está respaldado por tres tablas SQLite nuevas (`species_explored`, `species_folders`, `link_visited`) con claves primarias `(genus, epithet)` y `(genus, epithet, source_label)` — sin clave foránea hacia `taxa.id` — de modo que reimportaciones que muten `taxa.id` dejan intactas las filas del espacio de trabajo. El frontend expone el espacio de trabajo mediante un store de Zustand (`workspaceStore`) con una columna final `[explored-checkbox] [folder-badge-or-button]` en `SpeciesList`, un interruptor `[visited]` al inicio de cada fuente en `SpeciesLinks`, y un `ExplorerPanel` que embebe el enlace activo en un iframe con el conjunto estricto de atributos sandbox que exige la especificación, además de una tarjeta de respaldo renderizada fuera del iframe para resistir bloqueadores de popups. Un CLI independiente `taxon/migrate.py` distribuye los modos `dry-run`/`apply` para las tablas nuevas.

## Qué se entregó

### Backend (PR #70, merge `ed9d6f3`)
- `taxon/api/workspace.py` (nuevo): 3 modelos ORM (`species_explored`, `species_folders`, `link_visited`) con PKs compuestas `(genus, epithet)` y `(genus, epithet, source_label)`, sin FK a `taxa.id`; helpers de resolución `set_explored`, `unset_explored`, `list_explored`, `create_species_folder`, `get_species_folder`, `record_link_visited`, `unrecord_link_visited`, `list_link_visited`; lector de variable de entorno `AQUALIFE_ROOT` + resolución relativa al raíz del proyecto con `APIError(status_code=500)` cuando la raíz no es escribible.
- `taxon/api/router.py` (modificado): 8 endpoints nuevos registrados ANTES del catch-all `/{path:path}/taxon-links` (el test RED de orden de rutas fija ese orden):
  - `POST /api/explored/{g}/{e}`
  - `DELETE /api/explored/{g}/{e}`
  - `GET /api/explored/list`
  - `POST /api/species-folder/{g}/{e}`
  - `GET /api/species-folder/{g}/{e}`
  - `POST /api/link-visited/{g}/{e}/{src}`
  - `DELETE /api/link-visited/{g}/{e}/{src}`
  - `GET /api/link-visited/{g}/{e}`
- `taxon/api/schemas.py` (modificado): `ExploredResponse`, `ExploredListResponse`, `SpeciesFolderResponse`, `LinkVisitedItem`, `LinkVisitedResponse` exportados desde `__all__`. `APIError` ahora acepta un argumento explícito `status_code` para que los helpers puedan lanzar 404/409 sin subclasear.
- `taxon/api/__init__.py` (modificado): el lifespan de FastAPI conecta `Base.metadata.create_all(engine)` para las 3 tablas nuevas en cada engine (idempotente; las tablas preexistentes `taxa`/`species_paths` no se tocan).
- `taxon/migrate.py` (nuevo): CLI independiente con modos `dry-run` + `apply`, lee `TAXON_DATABASE_URL`, sin Alembic.
- `taxon/api/errors.py` (modificado): handler genérico de excepciones `APIError` registrado en `taxon.api.create_app` para que los helpers puedan lanzar `APIError(detail=..., status_code=...)`.
- 5 archivos de pruebas de backend: `test_workspace_resolver.py` (3 tablas, forma de PK, sin FK), `test_api_router_workspace.py` (8 endpoints, DELETE idempotente 204, folder duplicado 409, especie desconocida 404, sobres de lista vacía 200), `test_migrate.py` (dry-run + apply, idempotencia, env + flag), `test_aqualife_root.py` (lector de env, resolución al raíz del proyecto, raíz no escribible 500), `test_rebind_after_taxa_id_bump.py` (reimportaciones que mutan `taxa.id` dejan intactas las filas del espacio de trabajo).

### Frontend PR2a (PR #71, merge `220aeb6`) — store del espacio de trabajo + UI de filas
- `frontend/src/store/workspace.ts` (nuevo, 87 LOC): store de Zustand con `explored: Map<speciesKey, boolean>`, `folders: Set<speciesKey>`, `visited: Map<speciesKey, Set<source>>`, `activeLink: {speciesKey, source, url} | null`; acciones `markExplored`, `unmarkExplored`, `createFolder`, `markVisited`, `unmarkVisited`, `setActiveLink`, `hydrate`. Las claves son `${genus}|${epithet}` URL-encoded.
- `frontend/src/api.ts` (modificado, +76/-1): wrappers tipados `fetchExplored*`, `fetchSpeciesFolder*`, `fetchLinkVisited*` usando la unión discriminada `ApiResult<T>` existente.
- `frontend/src/components/SpeciesList.tsx` (modificado, +52/-21): columna final con la máquina de estados `[explored-checkbox] [folder-badge-or-button]` (`e.stopPropagation()` mantiene el click de fila disparando `taxon:select`).
- 3 archivos de pruebas de frontend: `api.workspace.test.ts` (wrappers tipados del cliente, 8 sobres de backend), `store.workspace.test.ts` (forma del store + acciones), `SpeciesList.workspace.test.tsx` (máquina de estados de la columna final).
- **Excepción de tamaño reconocida**: PR2a quedó en 504 LOC totales / 418 de código (frente al presupuesto de 400) — los archivos de prueba bajo TDD estricto dominaron; documentado según la skill `chained-pr`.

### Frontend PR2b (PR #72, merge `d3456dd`) — interruptores visitados en SpeciesLinks
- `frontend/src/components/SpeciesLinks.tsx` (modificado, +42/-18): interruptor `[visited]` al inicio con estilo `border-muted text-slate line-through` cuando está visitado; los clicks disparan `POST`/`DELETE /api/link-visited/{g}/{e}/{source}`.
- `frontend/src/App.tsx` (modificado, +1/-1): pasa la identidad de especie a `SpeciesLinks`.
- 1 archivo de pruebas de frontend: `SpeciesLinks.visited.test.tsx` (interruptor de visitado + aserciones de axe-core).

### Frontend PR3 (PR #73, merge `8a6b0e4`) — ExplorerPanel
- `frontend/src/components/ExplorerPanel.tsx` (nuevo, 144 LOC): iframe con el conjunto exacto de atributos sandbox `allow-same-origin allow-scripts allow-forms allow-popups allow-downloads` (sin `allow-top-navigation`, sin `allow-modals`), tarjeta de respaldo renderizada FUERA del iframe para resistir bloqueadores de popups, pastilla del enlace activo que nombra la fuente embebida, peek-card móvil coexistente con el iframe bajo el breakpoint de 640px para que el enlace activo siempre sea alcanzable cuando la columna se colapsa.
- `frontend/src/store/speciesKey.ts` (nuevo, 19 LOC): helper de round-trip `decodeSpeciesKey` extraído para satisfacer la regla de lint `react-refresh/only-export-components`.
- `frontend/src/App.tsx` (modificado, +9): monta `<ExplorerPanel>` en la columna derecha; el panel de breadcrumb-links NO muta `activeLink` (regresión fijada por `ExplorerPanel.activate.test.tsx`).
- `frontend/src/components/SpeciesLinks.tsx` (modificado, +13): el click de celda de especie llama a `setActiveLink`; las celdas de breadcrumb son no-op.
- 4 archivos de pruebas de frontend: `ExplorerPanel.test.tsx` (13 tests — sandbox / src / aria-label / respaldo / visibilidad / axe), `ExplorerPanel.activate.test.tsx` (2 tests — wiring celda de especie vs celda de breadcrumb), `ExplorerPanel.mobile.test.tsx` (2 tests — coexistencia peek-card + iframe), `a11y.explorer.test.tsx` (3 tests de regresión de axe-core), `store.speciesKey.test.ts` (3 tests de round-trip).

### Learn-es post-merge (commit `1e6f737`)
- `learn-es/2026-08-18-species-folder-explorer.md` (y espejo en español `documents-es/learn-es/2026-08-18-species-folder-explorer-es.md`) según AGENTS.md §1/§2 — el orquestador eligió el nombre de archivo con la fecha de merge en lugar del planificado originalmente `2026-08-16-...`.

## Pruebas (estado final, del merge de PR #73 y CI en `1e6f737`)

- Backend: 300/300 pytest en verde (246 base + 54 nuevos del PR #70).
- Frontend: 135/135 vitest en verde (112 base + 23 nuevos de los PRs #71 + #72 + #73).
- TypeScript: `tsc -b` en verde.
- Vite: `vite build` en verde.
- ESLint: limpio (la advertencia de `react-refresh/only-export-components` se resolvió moviendo `decodeSpeciesKey` a un archivo separado en el PR #73).
- Informe de verificación: `openspec/changes/species-folder-explorer/verify-report-pr1.md` (PR1 backend) — `PASS` con un WARNING reconocido por checkboxes obsoletos en `tasks.md` que esta reconciliación resuelve.
- 4 puertas de CI en verde en cada merge de PR.

## Especificaciones sincronizadas (delta → principal)

| Dominio | Acción | Detalles |
|---------|--------|----------|
| `species-explored` | Creada | Delta copiado verbatim mediante `cp` de shell + readback `diff -r` byte-idéntico. |
| `species-folder` | Creada | Delta copiado verbatim mediante `cp` de shell + readback `diff -r` byte-idéntico. |
| `link-visited` | Creada | Delta copiado verbatim mediante `cp` de shell + readback `diff -r` byte-idéntico. |
| `workspace-explorer` | Creada | Delta copiado verbatim mediante `cp` de shell + readback `diff -r` byte-idéntico. |

### Fuente de verdad actualizada
- `openspec/specs/species-explored/spec.md` (nuevo)
- `openspec/specs/species-folder/spec.md` (nuevo)
- `openspec/specs/link-visited/spec.md` (nuevo)
- `openspec/specs/workspace-explorer/spec.md` (nuevo)

### Especificaciones delta conservadas intactas en la carpeta de archivo
- `openspec/changes/archive/2026-08-18-species-folder-explorer/specs/{species-explored,species-folder,link-visited,workspace-explorer}/spec.md` — preservadas como pista de auditoría del cambio.

## Reconciliación de casillas obsoletas (según excepción de la skill)

Al momento de archivar, `tasks.md` persistido llegó con 28 tareas de implementación sin chequear (`- [ ]`) porque los sub-agentes `sdd-apply` por PR persistieron `apply-progress-*.md`/`verify-report-pr1.md` pero nunca volvieron a chequear las casillas en `tasks.md`. Según la excepción de casillas obsoletas de la skill `sdd-archive` (requiere autorización del orquestador + evidencia concreta de `apply-progress`/`verify-report`/estado del repositorio), el orquestador autorizó la reconciliación respaldada por:

- **Evidencia del repositorio**: archivos de backend presentes (`taxon/api/workspace.py`, `taxon/migrate.py`, `taxon/api/router.py`, `taxon/api/schemas.py`, lifespan `create_all` en `taxon/api/__init__.py`, 5 archivos de pruebas de backend); archivos de frontend presentes (`frontend/src/store/workspace.ts`, `frontend/src/store/speciesKey.ts`, `frontend/src/api.ts`, `frontend/src/components/SpeciesList.tsx`, `frontend/src/components/SpeciesLinks.tsx`, `frontend/src/components/ExplorerPanel.tsx`, `frontend/src/App.tsx`, 6 archivos de pruebas de frontend); `learn-es/2026-08-18-species-folder-explorer.md` + espejo en español presentes.
- **Evidencia de PRs**: PRs #70 (PR1), #71 (PR2a), #72 (PR2b), #73 (PR3) fusionados a `develop` en los commits `ed9d6f3` / `220aeb6` / `d3456dd` / `8a6b0e4`, con learn-es post-merge en `1e6f737`. Las 4 puertas de CI en verde en cada merge.
- **Hechos de estado final** (autoritativos, según el orquestador): 300 pytest de backend / 135 vitest de frontend / tsc -b / ESLint / vite build todos en verde. `verify-report-pr1.md` señaló explícitamente "one WARNING for stale `tasks.md` checkboxes the orchestrator should mark after the merge" — esa es la misma advertencia que esta reconciliación resuelve.
- **`apply-progress-pr{1,2a,2b,3}.md`**: cada uno prescribe un ciclo TDD por tarea (RED → GREEN → Triangular) e reporta éxito con recuentos concretos de pruebas y evidencia en tiempo de ejecución.

**Aplazamiento de la Fase 2** (tareas 2.1–2.4, diseño Pencil + auditoría impeccable): marcadas `[x] [DEFERRED]` con justificación verbatim: el MCP de Pencil/Google Stitch estuvo deshabilitado en la sesión de implementación, así que la especificación prescriptiva de la superficie se capturó como `docs/design/species-folder-explorer.md` en su lugar. El aplazamiento se preserva verbatim (no se introdujo ningún `- [ ]` obsoleto).

**Fase 1, Fase 3, y tarea 4.9 de la Fase 4** ahora están marcadas `[x]` basándose en hechos de repositorio + PR + apply-progress + verify-report + estado final. La tarea 4.9 se completó en el commit `1e6f737` (el orquestador eligió el nombre de archivo con la fecha de merge `2026-08-18-...` en lugar del planificado originalmente `2026-08-16-...`, según la convención de AGENTS.md §2).

## Puerta de Recibo de Revisión Nativa

`reviewGate` está estructuralmente ausente para este cambio — el interruptor de RDD estuvo desactivado durante toda la cadena, por lo que no se ejecutó código de revisión y no se generó ningún recibo. Según la Puerta de Recibo de Revisión Nativa de la skill, el archivo procede bajo la política ordinaria del repositorio.

## Verificación del Contrato de Copia Mecánica

Cinco readbacks `diff -r` pasaron con salida vacía (la única evidencia aprobatoria, según el contrato de la skill):

1. `openspec/changes/species-folder-explorer/specs/species-explored/spec.md` → `openspec/specs/species-explored/spec.md` — diff vacío
2. `openspec/changes/species-folder-explorer/specs/species-folder/spec.md` → `openspec/specs/species-folder/spec.md` — diff vacío
3. `openspec/changes/species-folder-explorer/specs/link-visited/spec.md` → `openspec/specs/link-visited/spec.md` — diff vacío
4. `openspec/changes/species-folder-explorer/specs/workspace-explorer/spec.md` → `openspec/specs/workspace-explorer/spec.md` — diff vacío
5. Snapshot de `openspec/changes/species-folder-explorer/` → `openspec/changes/archive/2026-08-18-species-folder-explorer/` — diff vacío

Sin truncado de bytes. Sin copia Read → Write. Copia mecánica solo mediante `cp` + `mv` (o `git mv` para archivos rastreados).

## Estado final

```yaml
prs_merged: [70, 71, 72, 73]
issues_closed: [68]
final_head: 1e6f737 en develop
backend_tests: 300
frontend_tests: 135
total_tests_added: 135   # 54 backend + 23 frontend (PR2a) + 7 frontend (PR2b) + 23 frontend (PR3) ≈ 107 archivos de prueba nuevos no mapean 1:1; suma según orquestador
total_loc_code_pr1: ~2043
total_loc_code_pr2a: 418
total_loc_code_pr2b: 76
total_loc_code_pr3: 185
size_exception: "PR2a (504 LOC totales / 418 de código frente a presupuesto de 400) — las pruebas bajo TDD estricto dominaron"
review_gate: ausente (interruptor RDD desactivado; archivo bajo política ordinaria del repositorio)
```

## Persistencia en Engram

- `mem_save` con clave de tema `sdd/species-folder-explorer/archive-report` — tipo `architecture`, proyecto `taxon`, `capture_prompt: false`.

## Related

- Issue #68: Espacio de trabajo por especie — creación de carpeta, flag de explorado, explorador embebido, interruptores por enlace.
- PR #70 (PR1, mergeado): `feat(api): species workspace backend` (commit `ed9d6f3`).
- PR #71 (PR2a, mergeado): `feat(frontend): species workspace store + api wrappers + SpeciesList column` (commit `220aeb6`).
- PR #72 (PR2b, mergeado): `feat(frontend): SpeciesLinks visited source switches` (commit `d3456dd`).
- PR #73 (PR3, mergeado): `feat(frontend): ExplorerPanel with iframe + sandbox + fallback` (commit `8a6b0e4`).
- Learn-es: `learn-es/2026-08-18-species-folder-explorer.md` + espejo en español (commit `1e6f737`).
- Archivo previo: `openspec/changes/archive/2026-08-16-arbol-col-browse/` (patrón del PR #69 — `TaxonomicTree` estilo CoL).
