# Tareas: species-folder-explorer

## Pronóstico de carga de revisión

| Campo | Valor |
|-------|-------|
| Líneas modificadas estimadas (PR1 backend) | ~310 LOC |
| Líneas modificadas estimadas (PR2 frontend store + filas) | ~330 LOC |
| Líneas modificadas estimadas (PR3 frontend explorer) | ~290 LOC |
| Riesgo de presupuesto 400 líneas (por PR) | Bajo (cada PR ≤350 LOC) |
| PRs encadenados recomendados | Sí — auto-chain según prefiltro |
| Decisión necesaria antes de aplicar | No |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Low

### Unidades de trabajo sugeridas

| Unidad | Objetivo | PR probable | Comando de prueba enfocado | Entorno de ejecución | Límite de rollback |
|--------|----------|-------------|---------------------------|----------------------|---------------------|
| 1 | Backend: 3 tablas + 7 endpoints + `create_all` en lifespan + `taxon/migrate.py` + AQUALIFE_ROOT + esquemas | PR 1 (`feat(api): species-folder-explorer backend`) | `pytest -v taxon/tests/test_api_router_workspace.py taxon/tests/test_workspace_resolver.py taxon/tests/test_migrate.py` | `python -m taxon.main` contra `data/col.db` + `curl -X POST http://localhost:8000/api/explored/Panthera/tigris` | Reversión de PR 1: 3 tablas aditivas + 7 endpoints eliminados; `taxa`/`species_paths` sin tocar. |
| 2 | Frontend: `workspaceStore` + extensiones de `api.ts` + columna trailing de `SpeciesList` + switch leading de `SpeciesLinks` + vitest + axe-core | PR 2 (`feat(frontend): workspace store + row chips`) | `npm run typecheck && npm test -- workspace store SpeciesList SpeciesLinks api.workspace` | `npm run dev` contra el backend vivo de PR 1; navegar Animalia → Chordata → Panthera; alternar checkbox de explorada | Reversión de PR 2: store aditivo; chips eliminados; `SpeciesList`/`SpeciesLinks` mantienen forma histórica. Backend PR 1 permanece. |
| 3 | Frontend: `ExplorerPanel.tsx` + montaje en `App.tsx` + `ExplorerPanel.test.tsx` + doc de diseño + espejo en español + entrada `learn-es` | PR 3 (`feat(frontend): explorer panel + workspace design`) | `npm run typecheck && npm test -- ExplorerPanel` | `npm run dev` contra el backend vivo de PR 1; clic en un enlace `Wikipedia`; observar sandbox del iframe + tarjeta de fallback | Reversión de PR 3: panel desmontado; columna derecha de `App.tsx` restaura breadcrumb + enlaces. PR 1 + PR 2 permanecen. |

## Fase 1: Tablas backend + endpoints + migrate.py (PR1, ≤350 LOC)

- [ ] 1.1 ROJO — escribir `taxon/tests/test_workspace_resolver.py` afirmando que las 3 tablas nuevas (`species_explored`, `species_folders`, `link_visited`) son creadas por `Base.metadata.create_all(engine)` con la PK documentada + forma de columnas: `species_explored.PRIMARY KEY (genus, epithet)`, `species_folders.PRIMARY KEY (genus, epithet)`, `link_visited.PRIMARY KEY (genus, epithet, source_label)`, NINGUNA con FK a `taxa.id`.
- [ ] 1.2 ROJO — escribir `taxon/tests/test_api_router_workspace.py` para `POST/DELETE /api/explored/{g}/{e}`, `GET /api/explored/list`, `POST/GET /api/species-folder/{g}/{e}`, `POST/DELETE/GET /api/link-visited/{g}/{e}/{source}` — caminos felices + DELETE idempotente 204 + carpeta duplicada 409 + especie desconocida 404 + envelopes lista vacía 200 `{"species": []}` / `{"sources": []}`.
- [ ] 1.3 ROJO — escribir `taxon/tests/test_migrate.py` afirmando que `python -m taxon.migrate dry-run` imprime un resumen nombrando las 3 tablas faltantes sin aplicar, Y `apply` crea las 3 tablas sin eliminar `taxa` / `species_paths`.
- [ ] 1.4 ROJO — escribir `taxon/tests/test_aqualife_root.py` afirmando el lector de la variable de entorno + resolución relativa a la raíz del proyecto (no al cwd) + envelope 500 ruidoso de fallo cuando la ruta resuelta es irresoluble o no escribible, y verificando que el segmento `path` se une con `os.sep` literalmente desde los segmentos canónicos `name`.
- [ ] 1.5 VERDE — añadir los 3 modelos ORM a `taxon/api/workspace.py` (o `taxon/schema.py` si la convención del proyecto lo requiere) con PK `(genus, epithet)` / `(genus, epithet, source_label)`, SIN FK a `taxa.id`, y las columnas `explored_at` / `path` / `created_at` / `visited_at`.
- [ ] 1.6 VERDE — añadir los helpers de resolución: `set_explored`, `unset_explored`, `list_explored`, `create_species_folder`, `get_species_folder`, `record_link_visited`, `unrecord_link_visited`, `list_link_visited`. Cada uno recorre por `(genus, epithet)` (y `source_label` para `link_visited`); nunca toca `taxa.id`.
- [ ] 1.7 VERDE — añadir los esquemas Pydantic `ExploredResponse`, `SpeciesFolderResponse`, `LinkVisitedResponse`, `LinkVisitedListResponse`, `ExploredListResponse` a `taxon/api/schemas.py`; exportar desde `__all__`.
- [ ] 1.8 VERDE — registrar los 8 endpoints en `taxon/api/router.py` ANTES del catch-all `/{path:path}/taxon-links` (disciplina de regresión según `test_api_router_tree::test_tree_endpoints_registered_before_taxon_links_catchall`).
- [ ] 1.9 VERDE — cablear `Base.metadata.create_all(engine)` para las 3 tablas nuevas dentro del lifespan de FastAPI en `taxon/api/__init__.py`; la llamada DEBE ser idempotente y NO DEBE tocar `taxa` / `species_paths`.
- [ ] 1.10 VERDE — implementar el script autónomo `taxon/migrate.py` con modos `dry-run` + `apply` (CLI a nivel de módulo Python, sin Alembic) que lea `TAXON_DATABASE_URL` y emita el resumen de una línea documentado.
- [ ] 1.11 VERDE — implementar el lector de la variable de entorno `AQUALIFE_ROOT` + resolución relativa a la raíz del proyecto en `taxon/api/workspace.py`; rechazar raíz no escribible con `APIError(status_code=500, detail="AQUALIFE_ROOT not writable: <path> from cwd <cwd>")`.
- [ ] 1.12 ROJO — escribir `taxon/tests/test_rebind_after_taxa_id_bump.py` afirmando que re-importaciones que recrean `taxa` (mutando `taxa.id` de `Panthera tigris`) NO invalidan las 3 filas nuevas del workspace — el recorrido por `(genus, epithet)` es el contrato.
- [ ] 1.13 REFACTOR — extraer los helpers de resolución + lector de `AQUALIFE_ROOT` en `taxon/api/workspace.py`; mantener `pytest` + `pytest-cov` en verde; commit.

## Fase 2: Diseño Pencil + auditoría impecable (PR 2, solo diseño)

- [x] 2.1 [POSPUESTO] El diseño en Pencil no se ejecutó porque Pencil/Google Stitch MCP está deshabilitado en esta sesión; el brief prescriptivo de superficie fue capturado como `docs/design/species-folder-explorer.md` en su lugar (837 líneas, especificación línea por línea de traducción para el implementador). Un issue de seguimiento puede rehacer la página Pencil `.pen` en una rebanada futura.
- [x] 2.2 [POSPUESTO] Misma justificación que 2.1; no hay página Pencil para auditar.
- [x] 2.3 [POSPUESTO] Misma justificación que 2.1.
- [x] 2.4 [POSPUESTO] Misma justificación que 2.1.

## Fase 3: Frontend workspaceStore + UI de filas (PR2, ≤350 LOC)

- [ ] 3.1 ROJO — escribir `frontend/tests/api.workspace.test.ts` cubriendo los wrappers tipados del cliente para los 8 endpoints del backend (envelopes 200 / 201 / 204 / 404 / 409 / 500) usando la unión discriminada `ApiResult<T>` existente.
- [ ] 3.2 VERDE — añadir los métodos tipados `fetchExplored*`, `fetchSpeciesFolder*`, `fetchLinkVisited*` a `frontend/src/api.ts`; la convención de `speciesKey` es `${genus}|${epithet}` con tubería codificada para URL.
- [ ] 3.3 ROJO — escribir `frontend/tests/store.workspace.test.ts` cubriendo la forma del store zustand (`explored: Map<speciesKey, boolean>`, `folders: Set<speciesKey>`, `visited: Map<speciesKey, Set<source>>`, `activeLink: {speciesKey, source, url} | null`) y las acciones `markExplored`, `unmarkExplored`, `createFolder`, `markVisited`, `unmarkVisited`, `setActiveLink`, `hydrate`.
- [ ] 3.4 VERDE — crear el store zustand `frontend/src/store/workspace.ts` con la forma documentada + acciones + hook de hidratación (eager en el montaje de `App.tsx`: un `GET /api/explored/list` + perezosos por especie `GET /api/link-visited/{g}/{e}`).
- [ ] 3.5 ROJO — escribir `frontend/tests/SpeciesList.workspace.test.tsx` cubriendo la máquina de estados de la columna trailing `[explored-checkbox] [folder-badge-or-button]`: desmarcado + botón → clic dispara `POST /api/species-folder/...` → marcado + badge (sin botón). Confirma que `e.stopPropagation()` mantiene el clic de fila disparando `taxon:select`.
- [ ] 3.6 VERDE — extender `SpeciesList.tsx` con la columna trailing; el checkbox de explorada se cablea al workspace store; el botón/badge de carpeta se cablea al endpoint `POST /api/species-folder/{g}/{e}`.
- [ ] 3.7 ROJO — escribir `frontend/tests/SpeciesLinks.visited.test.tsx` cubriendo el switch leading `[visited]` + el estado visual `border-muted text-slate line-through` cuando está activo, más el clic despachando `POST` / `DELETE /api/link-visited/{g}/{e}/{source}`.
- [ ] 3.8 VERDE — extender `SpeciesLinks.tsx` con el switch leading + el estado visual documentado; los clics despachan los endpoints `link-visited` y reconcilian vía el workspace store.
- [ ] 3.9 ROJO — escribir `frontend/tests/a11y.workspace.test.tsx` usando `vitest-axe` afirmando 0 violaciones de axe-core en la fila de `SpeciesList` + la celda de `SpeciesLinks` + los controles chip/switch.
- [ ] 3.10 VERDE — corregir cada issue de a11y señalado por axe (asociaciones de etiquetas, role="switch", aria-checked, orden de foco); pinear con vitest.
- [ ] 3.11 REFACTOR — mantener PR 2 ≤350 LOC; diferir `ExplorerPanel` + sus tests a PR 3.

## Fase 4: Frontend ExplorerPanel + doc de diseño + learn-es (PR3, ≤350 LOC)

- [ ] 4.1 ROJO — escribir `frontend/tests/ExplorerPanel.test.tsx` cubriendo: el iframe renderiza cuando `activeLink` está establecido versus muestra el marcador de estado vacío cuando es null; el atributo `sandbox` coincide con el conjunto exacto `allow-same-origin allow-scripts allow-forms allow-popups allow-downloads`; el `aria-label` dice `Embedded search result for {genus} {epithet} ({source})`; un botón obvio `<a target="_blank" rel="noopener noreferrer">Open in new tab</a>` se renderiza cuando `iframe.onError` se dispara (la tarjeta de fallback); el botón de fallback es alcanzable desde el foco de teclado.
- [ ] 4.2 VERDE — crear `frontend/src/components/ExplorerPanel.tsx` con iframe + sandbox + tarjeta de fallback (renderizada fuera del iframe para resiliencia ante bloqueadores de popups) + una etiqueta de enlace activo que nombre la fuente embebida.
- [ ] 4.3 ROJO — escribir `frontend/tests/ExplorerPanel.activate.test.tsx` cubriendo: un clic en el panel de enlaces de especie de `SpeciesLinks` establece `activeLink`; el panel de enlaces de miga de pan por taxón NO muta `activeLink`; el foco se mueve al iframe en la activación; `aria-live="polite"` anuncia la carga + el fallback.
- [ ] 4.4 VERDE — cablear `ExplorerPanel` en la columna derecha de `App.tsx` POR DEBAJO de `<SpeciesLinks>` / `<Breadcrumb>`; montar vía el estado `activeLink` del workspace store; el panel de enlaces de miga de pan de `cascadePath` NO muta `activeLink`.
- [ ] 4.5 ROJO — escribir `frontend/tests/ExplorerPanel.mobile.test.tsx` cubriendo el comportamiento de colapso móvil a tarjeta-peek (punto de quiebre de colapso de columna en <640px); el panel se encoge a tarjeta-peek; el iframe aún renderiza pero la grid de despacho está colapsada.
- [ ] 4.6 VERDE — implementar la tarjeta-peek responsiva para pantallas por debajo de 640px (punto de quiebre móvil): la columna derecha colapsa a una tarjeta-peek sticky con la etiqueta del enlace activo y un enlace "abrir en nueva pestaña".
- [ ] 4.7 VERDE — test de regresión axe-core para `ExplorerPanel` cubriendo el iframe + la tarjeta de fallback + la etiqueta de enlace activo (0 violaciones).
- [ ] 4.8 VERDE — finalizar el doc de diseño: `docs/design/species-folder-explorer.md` (ya con 837 líneas) + espejo en español `documents-es/docs/design/species-folder-explorer-es.md` (ya con 6103 palabras).
- [ ] 4.9 Post-merge — después de que PR 3 se fusione a `develop` con CI verde, crear `/learn-es/2026-08-16-species-folder-explorer.md` según AGENTS.md §2; el espejo en español en `/documents-es/learn-es/2026-08-16-species-folder-explorer-es.md`.

## Matriz de amenazas → mapeo de pruebas ROJO

| Frontera | Tarea de prueba ROJO | Estado |
|----------|----------------------|--------|
| Re-importación caótica (bump de taxa.id) NO invalida filas del workspace | 1.12 | cubierta |
| Discrepancia de cwd de `AQUALIFE_ROOT` (resolución de subcarpeta de worktree) | 1.4 | cubierta |
| Endpoint de carpeta falla ruidosamente sobre raíz irresoluble / no escribible | 1.4 | cubierta |
| Creación de carpeta duplicada devuelve 409 | 1.2 | cubierta |
| DELETE idempotente sobre fila faltante devuelve 204 | 1.2 | cubierta |
| Rechazo de iframe `X-Frame-Options` / CSP → tarjeta de fallback | 4.1 | cubierta |
| Panel de enlaces de miga de pan por taxón NO activa el iframe | 4.3 | cubierta |
| Colapso móvil a tarjeta-peek | 4.5 | cubierta |
| axe-core aria-required-children en `ExplorerPanel` | 4.7 | cubierta |
| Deriva por fallo de transporte (precedente de arbol-col-browse PR3) | cada tarea | cada tarea DEBE tener una prueba ROJO dedicada antes del commit en verde |
