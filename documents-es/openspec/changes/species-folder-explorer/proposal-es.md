# Propuesta: species-folder-explorer

## Intención

Cierra el issue #68. La SPA `taxon` hoy despacha 13 URLs de fuentes de búsqueda en pestañas nuevas y olvida todo entre sesiones. Este change agrega una **capa de workspace por especie**: un flag `explored` persistente, creación de carpeta bajo demanda reflejando el breadcrumb de la especie, switches "done" por enlace, y un iframe embebido atado al enlace actualmente activo — todo gateado por el workspace local del usuario en `./Proyecto-Aqualife/`. Cuando esto aterrice, el usuario podrá elegir una especie, marcarla como explorada, crear su carpeta en `Animalia/Chordata/.../Panthera tigris/`, alternar switches por fuente a medida que visita cada enlace, y leer esas fuentes dentro de un `<iframe>` sin perder el contexto de la SPA.

## Alcance

### En alcance
- **A. Flag `explored` persistente por especie** — tabla backend `species_explored(genus TEXT, epithet TEXT, explored_at TIMESTAMP, PK(genus, epithet))`, `POST/DELETE /api/explored/{genus}/{epithet}`, columna de checkbox al final en las filas de `SpeciesList`.
- **B. API + UI de creación de carpeta** — tabla backend `species_folders(genus TEXT, epithet TEXT, path TEXT, created_at TIMESTAMP, PK(genus, epithet))`, `POST /api/species-folder/{genus}/{epithet}` (crea carpeta anidada bajo `AQUALIFE_ROOT`), `GET /api/species-folder/{genus}/{epithet}` (chequeo de existencia), badge de carpeta / botón create-folder al final en filas de `SpeciesList`.
- **C. Switches "done" por enlace** — tabla backend `link_visited(genus TEXT, epithet TEXT, source_label TEXT, visited_at TIMESTAMP, PK(genus, epithet, source_label))`, `POST /api/link-visited/{genus}/{epithet}/{source}`, `DELETE /api/link-visited/{genus}/{epithet}/{source}`, `GET /api/link-visited/{genus}/{epithet}` (hydrate), switch `[visited]` al inicio en cada celda de `SpeciesLinks` con estilo `border-muted text-slate strikethrough` cuando está activo.
- **D. Explorer embebido** — nuevo `ExplorerPanel.tsx` que renderiza `<iframe sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-downloads" src={activeLink?.url ?? ""} aria-label={...}>` con tarjeta fallback `target="_blank"` cuando la fuente rechaza embedding.
- Mirrors en español sobre cada artefacto (AGENTS.md §1).
- Entrada `learn-es/2026-08-15-species-folder-explorer.md` + mirror español tras CI verde (AGENTS.md §2).

### Fuera de alcance
- Sincronización en la nube, multi-device, auth (SQLite local single-user según issue #68).
- Anidamiento de carpetas para subespecies — la carpeta se detiene en `species`, espejando `taxon/api/sqlite_resolver.py::list_kingdoms::_flatten_species_subtree`.
- Extracción de recetas de resultados de búsqueda — drag-and-drop desde el iframe a la carpeta del OS alcanza.
- Página de diseño `.pen` — Pencil MCP deshabilitado; el diseño va vía markdown prescriptivo `docs/design/species-folder-explorer.md` (precedente de arbol-col-browse).

## Enfoque

**Modelo de storage — 3 tablas nuevas, todas con columnas de re-bind `(genus, epithet)` para sobrevivir re-imports.**

El proyecto no tiene Alembic y `taxon/import_data.py` reconstruye `taxa` desde cero en cada corrida, lo cual bumpea `taxa.id`. El flag explored DEBE ser ortogonal a ese churn (si no, los re-imports borran el estado del usuario) — así que vive en su propia tabla. Las otras dos tablas siguen el mismo patrón.

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

Las claves primarias son `(genus, epithet)` (y `(genus, epithet, source_label)` para `link_visited`) — NO `species_id INTEGER REFERENCES taxa(id)`. El schema es intencionalmente ortogonal a `taxa` para que los re-imports que recrean `taxa` con un `id` autoincrement nuevo no invaliden el estado del workspace. El endpoint camina primero por `(genus, epithet)` (el resolver devuelve el `name` canónico y el `parent_id` desde `resolve_path_by_display_level`) y crea o actualiza la fila keyed en el par `(genus, epithet)`. `source` es estable respecto al template (`docs/sources/templates.md`); las URLs cambian por substitución.

**Mecanismo de migración — runtime `Base.metadata.create_all(engine)` en el lifespan de FastAPI + script standalone `taxon/migrate.py`.**

Sin dependencia de Alembic agregada. El lifespan llama `Base.metadata.create_all(engine)` para las tres tablas nuevas al arrancar la app (espejando el bootstrap de tests existente en `taxon/api/__init__.py:145` para `sqlite:///:memory:`). Un script standalone `python -m taxon.migrate {dry-run|apply}` existe para el caso raro del operador (CI / DB fresca) donde el schema debe aplicarse sin bootear la API; usa el mismo `create_all` y emite un resumen de una línea. Esto se mantiene consistente con cómo `taxon/import_data.py` construye `taxa` / `species_paths` out-of-band.

**Superficie API — 5 endpoints nuevos, registrados ANTES del catch-all `/{path:path}/taxon-links` (disciplina de regresión de `test_api_router_tree::test_tree_endpoints_registered_before_taxon_links_catchall`):**

| Método | Path | Propósito |
|--------|------|-----------|
| `POST` | `/api/explored/{genus}/{epithet}` | setear flag explored (idempotente, retorna fila de la especie) |
| `DELETE` | `/api/explored/{genus}/{epithet}` | des-setear flag explored |
| `POST` | `/api/species-folder/{genus}/{epithet}` | resolver breadcrumb + `mkdir -p`, insertar fila `species_folders`, retornar `{path}` |
| `GET` | `/api/species-folder/{genus}/{epithet}` | chequeo de existencia (200 `{path}` o 404) |
| `POST` | `/api/link-visited/{genus}/{epithet}/{source}` | upsert del set visited (idempotente) |
| `DELETE` | `/api/link-visited/{genus}/{epithet}/{source}` | des-setear fuente visited |
| `GET` | `/api/link-visited/{genus}/{epithet}` | hidratar set visited para una especie |

`POST/DELETE` matchea el patrón del flag explored (sin atajo `PUT`). El helper resolver es el nuevo módulo `taxon/api/workspace.py` que también posee el lector de la env var `AQUALIFE_ROOT` (`os.environ.get("AQUALIFE_ROOT", "./Proyecto-Aqualife/")`). Modelos Pydantic `ExploredResponse`, `SpeciesFolderResponse`, `LinkVisitedRequest`, `LinkVisitedResponse` agregados a `taxon/api/schemas.py`.

**Estado frontend — nuevo store Zustand `frontend/src/store/workspace.ts`, hermano de `cascadePath` + `taxonomicTree`.**

Forma: `{exploredBySpeciesId: Map<number, boolean>, foldersBySpeciesId: Map<number, string>, visitedByKey: Map<number, Set<string>>, activeLink: {speciesId: number, source: string, url: string} | null, markExplored, unmarkExplored, createFolder, markVisited, unmarkVisited, setActiveLink, hydrate}`. Las mutaciones son optimistic-then-reconcile (refleja la fila canónica de la respuesta del backend en el Map/Set local). `hydrate()` corre en el mount de App: `GET /api/link-visited/list` (tabla completa) + lazy per-row `GET /api/species-folder/{g}/{e}` sólo cuando una fila se monta. `cascadePath` queda intacto: el workspace es per-species, no per-cascade-step.

**UI frontend — adiciones a nivel de fila + nuevo panel explorer.**

Las filas de `SpeciesList.tsx` ganan una columna al final `[checkbox-explored] [badge-o-botón-carpeta]` a la derecha del `MarkerBadges` existente. Las celdas de `SpeciesLinks.tsx` ganan un switch `[visited]` al inicio (primer tab stop — keyboard-first, matchea mejor la semántica "toggle state" del switch que trailing). El nuevo `ExplorerPanel.tsx` se monta dentro de la columna derecha de `App.tsx` debajo de `<SpeciesLinks>`/`<Breadcrumb>`, `sticky top-0`, renderiza `aria-label="Embedded search result for {species}"`, y muestra una tarjeta placeholder "esta fuente rechaza embedding" con un botón "Abrir en nueva pestaña" cuando el `onError` del iframe dispara (rechazo X-Frame-Options / CSP — Wikipedia, Scholar, BHL todos envían `SAMEORIGIN`).

**Convención `AQUALIFE_ROOT` — env var con default relativo.**

`os.environ.get("AQUALIFE_ROOT", "./Proyecto-Aqualife/")` en `taxon/api/workspace.py`. En el startup de `create_app`, `Path(root).mkdir(parents=True, exist_ok=True)`; rechazar root no escribible con un envelope de error claro. Espeja el precedente de `TAXON_DATABASE_URL`. La env var es obligatoria cuando se corre desde un subfolder de worktree — pineado con un test que corre desde `tmp_path` y afirma el envelope de error cuando `cwd != project_root`.

**Sandbox del iframe + fallback.**

`sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-downloads"` (sin `allow-top-navigation` — evita que el iframe navegue la SPA). Los downloads rutean por el flujo default de download del browser (Content-Disposition no se intercepta). Safari los controla más estrictamente; la tarjeta fallback `target="_blank"` cubre el modo de falla. El botón fallback es un `<a>` regular renderizado fuera del iframe para que funcione sin importar el estado del popup-blocker.

**Diseño — markdown prescriptivo, sin página `.pen`.**

Pencil MCP está deshabilitado en esta sesión (verificado, `MCP error -32603: failed to connect to running Pencil app`). Mismo precedente que `arbol-col-browse` (issue #67, archivado 2026-08-16). La fase de diseño escribe `docs/design/species-folder-explorer.md` + mirror español `documents-es/docs/design/species-folder-explorer-es.md` con specs de implementación línea por línea para `ExplorerPanel`, la columna trailing de `SpeciesList`, y el switch leading de `SpeciesLinks`. El audit del skill `impeccable` se aplica al markdown ANTES de que se escriba cualquier código de frontend (AGENTS.md §5).

## Capacidades

### Capacidades nuevas
- `species-folder`: persistencia backend + affordance UI para creación de carpeta reflejando el breadcrumb bajo `AQUALIFE_ROOT`.
- `link-visited`: persistencia backend + affordance UI para switches visited por (species, source) con estilo disabled strikethrough.
- `species-explored`: persistencia backend + affordance UI para el checkbox explored por especie.
- `workspace-explorer`: nuevo `ExplorerPanel.tsx` que renderiza el iframe sandboxed atado al enlace activo, con fallback `target="_blank"` para rechazos de X-Frame-Options / CSP.

### Capacidades modificadas
- Ninguna (los specs existentes `taxonomy-hierarchy` y `species-search-links` quedan verbatim; el contrato del resolver no cambia y el dispatch de 13 enlaces no cambia).

## Áreas afectadas

| Área | Impacto |
|------|---------|
| `taxon/schema.py` | Modelos nuevos `SpeciesExplored`, `SpeciesFolder`, `LinkVisited` |
| `taxon/api/workspace.py` | Nuevo (resolver + lector de `AQUALIFE_ROOT`) |
| `taxon/api/router.py` | +5–7 endpoints, registrados ANTES del catch-all `/{path:path}/taxon-links` |
| `taxon/api/schemas.py` | +`ExploredResponse`, `SpeciesFolderResponse`, `LinkVisitedRequest`, `LinkVisitedResponse` |
| `taxon/migrate.py` | Nuevo (script standalone `dry-run` / `apply`) |
| `taxon/tests/` | +`test_workspace_resolver.py`, +`test_api_router_workspace.py`, +`test_migrate.py` |
| `frontend/src/store/workspace.ts` | Nuevo |
| `frontend/src/api.ts` | +`setExplored`, `unsetExplored`, `createSpeciesFolder`, `getSpeciesFolder`, `recordLinkVisited`, `unrecordLinkVisited`, `listLinkVisited` |
| `frontend/src/components/SpeciesList.tsx` | Columna al final `[checkbox-explored] [badge-o-botón-carpeta]` |
| `frontend/src/components/SpeciesLinks.tsx` | Switch `[visited]` al inicio por celda |
| `frontend/src/components/ExplorerPanel.tsx` | Nuevo |
| `frontend/src/App.tsx` | Montar `<ExplorerPanel>` en columna derecha |
| `frontend/tests/` | +`SpeciesList.workspace.test.tsx`, +`SpeciesLinks.visited.test.tsx`, +`ExplorerPanel.test.tsx`, +`workspace.store.test.ts`, +`api.workspace.test.ts` |
| `docs/design/species-folder-explorer.md` | Nuevo (diseño prescriptivo + audit impeccable) |
| `documents-es/docs/design/species-folder-explorer-es.md` | Nuevo (mirror español) |
| `openspec/specs/species-folder/spec.md` | Nuevo |
| `openspec/specs/link-visited/spec.md` | Nuevo |
| `openspec/specs/species-explored/spec.md` | Nuevo |
| `openspec/specs/workspace-explorer/spec.md` | Nuevo |
| `learn-es/2026-08-15-species-folder-explorer.md` | Nuevo (tras CI verde) |
| `documents-es/learn-es/2026-08-15-species-folder-explorer-es.md` | Nuevo (mirror español) |

## Riesgos

| Riesgo | Prob | Mitigación |
|------|-----|------------|
| Sin tooling de migración Alembic | Med | alternativa explícita: `Base.metadata.create_all` en lifespan + script `taxon/migrate.py`. Sin dependencia de Alembic agregada. |
| Churn de schema por re-imports (`taxon/import_data.py` reconstruye `taxa`, bumpea `id`) | Alta | cada tabla nueva carga columnas de re-bind `(genus, epithet)`; el endpoint camina por nombre y re-vincula FK en cada lectura. Pineado con un test. |
| Mismatch de cwd de `AQUALIFE_ROOT` (subfolder de worktree resuelve `./Proyecto-Aqualife/` a la ruta equivocada) | Med | env var obligatoria + `Path(root).mkdir(parents=True, exist_ok=True)` + envelope de error explícito cuando no resuelve. Pineado con un test que corre desde `tmp_path`. |
| Rechazo X-Frame-Options / CSP (Wikipedia, Scholar, BHL todos envían `SAMEORIGIN`) | Alta | tarjeta fallback `target="_blank"` es OBLIGATORIA, no opcional. El `<a>` fallback se renderiza fuera del iframe para que el estado del popup-blocker no importe. |
| Sandbox del iframe + downloads (Safari controla downloads iniciados por iframe más estrictamente) | Med | flujo de download default del browser; fallback `<a target="_blank">` siempre alcanzable. |
| Fallo de transporte enmascarando violaciones MUST (precedente del PR3 de arbol-col-browse) | Med | cada requisito MUST (uno por cláusula WHEN/THEN en los 4 specs nuevos) recibe un test dedicado pineando el contrato ANTES del commit verde. `sdd-verify` corre como pasada independiente. |
| Budget de review de PR de 400 líneas | Med | split explícito en 3 PRs chained (ver Estrategia de delivery); cada PR queda en ≤350 LOC. |
| Strict TDD requiere pineo de test por requisito | Med | la propuesta enumera el conteo de tests por PR (ver Hitos). |
| Pencil MCP deshabilitado — sin página `.pen` | Med | design doc prescriptivo + audit impeccable ANTES del código (gate AGENTS.md §5). |
| Interacción `cascadePath` ↔ `workspaceStore` (workspace es per-species, cascadePath es per-cascade-step) | Baja | `setActiveLink` del active-link sólo dispara desde clicks de enlaces de especie; el panel per-taxon breadcrumb-links mantiene estado pero NO activa el iframe (con scope sólo a especie — ver explore §"Active-link state scope" pregunta 8). Pineado en spec. |

## Fuera de alcance

- Sincronización en la nube, multi-device, auth (SQLite local single-user según issue #68).
- Anidamiento de carpetas para subespecies (la carpeta se detiene en especie; espeja `taxon/api/sqlite_resolver.py::_flatten_species_subtree`).
- Extracción de recetas de resultados de búsqueda (usuario drag-and-drop desde iframe a carpeta del OS).
- Columna desnormalizada `taxa.is_explored` (opción (a) de explore §11 — la tabla nueva es más segura contra churn de re-import).
- Dependencia Alembic y migraciones versionadas por Alembic.
- Página de diseño `.pen` (Pencil MCP deshabilitado; diseño markdown + audit impeccable la reemplaza).

## Hitos

1. **Decisiones capturadas aquí**: 3 tablas nuevas (ortogonales a `Taxon`, re-bind por `(genus, epithet)`); `Base.metadata.create_all` runtime + script `taxon/migrate.py` (sin Alembic); 3 PRs chained (PR1 backend ≤350, PR2 frontend store + filas ≤350, PR3 explorer + diseño + learn-es ≤350).
2. **Design doc + audit impeccable** — `docs/design/species-folder-explorer.md` + mirror español auditado por `impeccable` ANTES de cualquier código (gate AGENTS.md §5).
3. **Backend PR1** (`feat/species-folder-explorer-backend`, ≤350 LOC, target `develop`):
   - 3 modelos SQLAlchemy nuevos + llamada `create_all` en lifespan.
   - Resolver `taxon/api/workspace.py` + lector de env var `AQUALIFE_ROOT`.
   - 5 endpoints (POST/DELETE explored, POST/GET species-folder, POST/DELETE/GET link-visited), registrados antes del catch-all.
   - 4 modelos Pydantic nuevos.
   - Script `taxon/migrate.py` (dry-run / apply).
   - Tests backend: `test_workspace_resolver.py` (~10 tests pineando re-bind por nombre + race de mkdir + resolución de env var desde subfolder), `test_api_router_workspace.py` (~8 tests pineando WHEN/THEN de cada endpoint), `test_migrate.py` (script dry-run vs apply).
4. **Frontend PR2** (`feat/species-folder-explorer-frontend`, ≤350 LOC, target `develop`):
   - `frontend/src/store/workspace.ts` + `hydrate()` en mount de App.
   - Extensiones de `frontend/src/api.ts` (7 métodos nuevos sobre el cliente tipado).
   - Columna al final en `SpeciesList` + switch al inicio en `SpeciesLinks`.
   - Tests Vitest + axe-core: `SpeciesList.workspace.test.tsx`, `SpeciesLinks.visited.test.tsx`, `workspace.store.test.ts`, `api.workspace.test.ts`.
5. **Frontend PR3** (`feat/species-folder-explorer-explorer`, ≤350 LOC, target `develop`):
   - `ExplorerPanel.tsx` con iframe `sandbox="..."` + tarjeta fallback `target="_blank"` + `aria-label`.
   - `App.tsx` monta `<ExplorerPanel>` en columna derecha.
   - `ExplorerPanel.test.tsx` (iframe src / sandbox / aria-label / fallback).
   - `docs/design/species-folder-explorer.md` + mirror español (si no está ya en el setup del PR1).
   - Entrada `learn-es/2026-08-15-species-folder-explorer.md` + mirror español (DESPUÉS de CI verde según AGENTS.md §2).
6. **sdd-archive** — una vez que PR3 esté verde y mergeado, correr `sdd-archive` para sincronizar los 4 specs nuevos y escribir `archive-report.md` + mirror español `documents-es/openspec/changes/species-folder-explorer/archive-report-es.md`.

## Estrategia de delivery

3 PRs chained stacked-to-main, `auto-chain` según la cache de pre-flight del orchestrator. Cada PR queda en ≤350 LOC (bien debajo del budget de review de 400 líneas).

- **PR1 backend (≤350 LOC)** — tablas + endpoints + migración en lifespan + script `taxon/migrate.py` + pytest backend. Cierra la superficie backend de las sub-features A/B/C.
- **PR2 frontend-store + row UI (≤350 LOC)** — `workspaceStore` + extensiones `api.ts` + columna al final de `SpeciesList` + switch al inicio de `SpeciesLinks` + vitest + axe-core. Cierra la superficie frontend de las sub-features A/B/C.
- **PR3 frontend-explorer + diseño + learn-es (≤350 LOC)** — `ExplorerPanel.tsx` + mount en `App.tsx` + `ExplorerPanel.test.tsx` + design doc + mirror español + entrada `learn-es`. Cierra la sub-feature D.
- **Sin cleanup PR** — sin archivos obsoletos a borrar (según issue §"Proposed approach").

El pase de diseño Pencil + impeccable es un GATE DURO antes de PR1 (AGENTS.md §5) — `sdd-design` escribe el markdown prescriptivo y lo audita ANTES de cualquier código.

## Dependencias

- `taxon.api.hierarchy.resolve_path_by_display_level` (verbatim, conduce el walk del breadcrumb para anidamiento de carpetas).
- `docs/sources/templates.md` (verbatim, substitución de 13 enlaces; conteo canónico 13, no 12).
- Patrones de `taxon.api.sqlite_resolver` + helper `_to_row` para construcción de `TaxonRow`.
- Pase de diseño Pencil + impeccable según AGENTS.md §5 (ANTES del código de frontend).

## Criterios de éxito

- [ ] `POST /api/explored/{g}/{e}` setea el flag explored (idempotente); `DELETE` lo des-setea. Ambos round-trippean la fila de la especie.
- [ ] `POST /api/species-folder/{g}/{e}` crea la carpeta anidada bajo `AQUALIFE_ROOT` y persiste el path en `species_folders`. Re-correr retorna 409 (chequeo de idempotencia pineado por test).
- [ ] `GET /api/species-folder/{g}/{e}` retorna el path o 404.
- [ ] `POST /api/link-visited/{g}/{e}/{source}` hace upsert (idempotente sobre `(species_id, source)`); `DELETE` lo remueve.
- [ ] `GET /api/link-visited/{g}/{e}` retorna el set visited para una especie.
- [ ] En re-import que bumpea `taxa.id`, las tres tablas nuevas re-vinculan por nombre — sin filas huérfanas (pineado con un test que muta `taxa.id` y re-camina).
- [ ] La env var `AQUALIFE_ROOT` resuelve correctamente cuando se corre desde `tmp_path` (test de subfolder) — o falla con un envelope de error claro.
- [ ] La columna al final de la fila de `SpeciesList` alterna `[checkbox-explored]` y `[badge-o-botón-carpeta]`. El badge de carpeta reemplaza al botón tras el primer create.
- [ ] El switch al inicio de la celda de `SpeciesLinks` alterna el estado visited; el estilo pasa a `border-muted text-slate strikethrough` cuando está activo.
- [ ] El iframe `src` del `<ExplorerPanel>` matchea `activeLink.url`; los atributos sandbox son exactos; el `aria-label` está presente; la tarjeta fallback renderiza cuando `iframe.onError` dispara.
- [ ] axe-core: 0 violaciones en los renders de `SpeciesList`, `SpeciesLinks`, `ExplorerPanel`.
- [ ] Suites `pytest` + `vitest run` verdes; `tsc -b && vite build` verde.
- [ ] Entrada `/learn-es/2026-08-15-species-folder-explorer.md` + mirror español creados tras CI verde en `develop`.
- [ ] `sdd-archive` completa; 4 specs nuevos sincronizados en `openspec/specs/`; archive-report + mirror español escritos.