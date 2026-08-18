# Diseño: species-folder-explorer

> **Cierra el issue #68.** Cuatro subcaracterísticas acopladas se entregan en 3 PRs encadenados, cada uno ≤350 LOC.

## 1. Arquitectura

```
SPA ──► FastAPI ──► schema (3 tablas nuevas) ──► SQLite
    ──► workspace.py (resolvedor + AQUALIFE_ROOT)
    ──► migrate.py (dry-run/apply)
    ──► ./Proyecto-Aqualife/
```

| Componente | Rol |
|------------|-----|
| `App.tsx` | Monta `<ExplorerPanel>`; llama `hydrate()` al montar. |
| `workspaceStore` (zustand) | Verdad para Maps explored/folders/visited + activeLink. Optimista + reconcilia. |
| `taxon/api/workspace.py` | Resuelve especie vía `resolve_path_by_display_level`; re-vincula FK por `(genus, epithet)`; lee `AQUALIFE_ROOT`; `Path.mkdir(parents=True, exist_ok=True)`. |
| `taxon/schema.py` (+3) | `species_explored`, `species_folders`, `link_visited`. FKs a `taxa.id`. |
| `taxon/migrate.py` | `python -m taxon.migrate {dry-run\|apply}` llama `create_all` solo para las 3 tablas nuevas. |
| `lifespan` | Extiende `taxon/api/__init__.py:140-145` para que todos los engines SQLite llamen `create_all` al arrancar. |

## 2. Almacenamiento

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

Las columnas `(genus, epithet)` existen porque `taxon/import_data.py` reconstruye `taxa` en cada ejecución, desplazando `taxa.id` — FKs puras quedarían huérfanas en cada re-import. `link_visited` se clavea en `(species_id, source_label)` (estable por plantilla; las URLs cambian por sustitución).

## 3. Contrato de la API

Todos los endpoints se registran ANTES del catch-all `/{path:path}/taxon-links` en `router.py:834-894`.

| Método | Ruta | Estado |
|--------|------|--------|
| POST   | `/api/explored/{g}/{e}`            | 200 / 404 |
| DELETE | `/api/explored/{g}/{e}`            | 204 (idempotente) |
| GET    | `/api/explored/list`               | 200 `{species:[]}` |
| POST   | `/api/species-folder/{g}/{e}`      | 201 / 409 / 500 |
| GET    | `/api/species-folder/{g}/{e}`      | 200 / 404 |
| POST   | `/api/link-visited/{g}/{e}/{src}`  | 204 / 404 / 422 |
| DELETE | `/api/link-visited/{g}/{e}/{src}`  | 204 (idempotente) |
| GET    | `/api/link-visited/{g}/{e}`        | 200 `{sources:[]}` |

Cuerpo `ErrorResponse` uniforme `{"detail": str}`. Pydantic nuevo: `ExploredResponse(SpeciesLookupResponse)`, `SpeciesFolderResponse`, `LinkVisitedItem`, `LinkVisitedResponse`, `ExploredListResponse`.

## 4. Estado del frontend

`frontend/src/store/workspace.ts` (zustand), hermano de `cascadePath` + `taxonomicTree`:

```ts
interface WorkspaceState {
  explored: Map<string, {explored_at: string}>;        // clave = `${g}|${e}` (URL-codificado)
  folders:  Map<string, {path: string}>;
  visited:  Map<string, Set<string>>;
  pending:  {explored: Set<string>; folders: Set<string>; visited: Set<string>};
  activeLink: {speciesKey: string; source: string; url: string} | null;
  markExplored/unmarkExplored/createFolder/markVisited/unmarkVisited/setActiveLink/hydrate;
}
```

Cada mutación: actualización optimista de Map/Set → dispara → reconcilia en 2xx → rollback + toast en no-2xx. Hidrata al montar `App.tsx`: un `GET /api/explored/list` + `GET /api/link-visited/{g}/{e}` perezoso por especie. `cascadePath` intacto. `activeLink` solo desde clics en panel de especies.

## 5. Flujo de UI

**Columna final en SpeciesList** (PR2): a la derecha de `MarkerBadges`, fuera del `<button>` de fila, `e.stopPropagation()` para que el clic de fila siga disparando `taxon:select`. Estados: checkbox de explorado + botón `Create folder` (sin fila) O + insignia `📁 folder` (fila existe, no clickeable).

**Columna inicial en SpeciesLinks** (PR2): `<input type="checkbox" role="switch" aria-checked aria-label="Mark {source} as visited">` fuera del `<a>`. Cuando está visitada, la celda cambia a `border-muted text-slate line-through`. El ancla `target="_blank"` permanece.

**ExplorerPanel** (PR3): nuevo en la columna derecha, `sticky top-0`, debajo de `<SpeciesLinks>`. Estados: vacío (`activeLink === null` → "Pick a source to embed."), iframe (`sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-downloads"`, `aria-label="Embedded search result for {genus} {epithet} ({source})"`, `onError` → fallback), fallback (tarjeta ámbar + `<a target="_blank" rel="noopener noreferrer">Open in new tab</a>` FUERA del iframe).

## 6. `AQUALIFE_ROOT`

`resolve_aqualife_root()`: (1) `os.environ.get("AQUALIFE_ROOT", None)` → default `"./Proyecto-Aqualife/"`; (2) resuelve rutas relativas contra la **raíz del proyecto** (NO contra `cwd`) — caminando desde `__file__` del módulo hasta `pyproject.toml`; (3) `Path(root).mkdir(parents=True, exist_ok=True)`; (4) `PermissionError` → `APIError(detail="AQUALIFE_ROOT not writable: <path> from cwd <cwd>", status_code=500)`. Tests fijados: subcarpeta, no escribible, variable de entorno absoluta.

## 7. Migración

**En lifespan**: extiende `taxon/api/__init__.py:_lifespan` para que todos los engines SQLite llamen `Base.metadata.create_all(engine)` (actualmente solo `:memory:`). Idempotente — omite tablas existentes.

**Script independiente `taxon/migrate.py`**: `python -m taxon.migrate {dry-run|apply}` lee `TAXON_DATABASE_URL`, inspecciona las 3 tablas faltantes, imprime resumen (dry-run) o aplica. Sin Alembic.

## 8. División de PRs + riesgo

| PR | Alcance | LOC | Riesgo | Tests clave | Rollback |
|----|---------|-----|--------|-------------|----------|
| **PR1 backend** | 3 ORM + workspace.py + 7 endpoints + lifespan + migrate.py + schemas + 3 test files | **~310** | Med | `test_workspace_resolver.py` (~10), `test_api_router_workspace.py` (~8), `test_migrate.py` (~3) | `git revert`; aditivo |
| **PR2 store frontend + filas** | workspaceStore.ts + api.ts + trailing SpeciesList + leading SpeciesLinks + 4 vitest | **~280** | Med | `workspace.store.test.ts`, `api.workspace.test.ts`, `SpeciesList.workspace.test.tsx`, `SpeciesLinks.visited.test.tsx` | `git revert`; aditivo |
| **PR3 explorador + diseño** | ExplorerPanel.tsx + montaje App.tsx + test + doc diseño + espejo ES + learn-es | **~150 código + ~1200 docs** | Bajo | `ExplorerPanel.test.tsx` (iframe src / sandbox / aria-label / fallback) | `git revert`; no-op |

Cada uno ≤350 LOC. `auto-chain`: PR1 → PR2 → PR3.

## 9. Recuperación de drift

`sdd_task_result_empty` (fallo de transporte) enmascaró drift de spec en `arbol-col-browse` PR3. **Cada requisito MUST recibe un test RED dedicado fijado antes del commit verde.**

**~35 tests fijados, uno por cláusula WHEN/THEN** en las 4 specs. Inventario clave: `test_post_species_folder_{returns_201_with_path, repeat_returns_409}`, `test_resolve_root_{from_subfolder_uses_project_root, unwritable_returns_500}`, `test_rebind_after_taxa_id_bump`, `test_ascii_segments_join_verbatim`, `test_{dry_run_reports_missing_tables, apply_creates_three_tables, fresh_db_serves_after_lifespan}`, `test_post_*_{returns_*, idempotent}`, `test_delete_*_{returns_204, missing_returns_204}`, `test_get_*_list_{200, empty}`, `test_*_keys_on_source_not_url`, `test_iframe_sandbox_attribute_exact`, `test_{empty_state_when_no_active_link, click_sets_active_link, breadcrumb_link_does_not_activate, fallback_on_iframe_error, fallback_button_keyboard_reachable, aria_label_updates_on_active_link_change, panel_mounted_in_right_column_sticky}`, `test_hydrate_restores_explored_after_reload`. A11y: `*.a11y.test.tsx` por superficie (axe-core 0 violaciones).

## 10. Fuera de alcance

Nube, multi-dispositivo, auth. Subespecies. Intercepción de `Content-Disposition`. Auto-marcado de visitado. Columna `taxa.is_explored`. Alembic. Página `.pen` (Pencil deshabilitado; el markdown + auditoría ES la superficie de diseño). `GET /api/link-visited/list` (solo hidratación por especie).

## 11. Nota de implementación de Fase 4 (PR3)

El diseño prescriptivo se convirtió en la siguiente superficie de código en el PR3 de #68 (ver `apply-progress-pr3-es.md` para el log de cierre completo):

### 11.1 `ExplorerPanel.tsx`

Renderiza el iframe + sandbox + tarjeta de respaldo + peek-card móvil + pill de enlace activo. Se suscribe a `workspaceStore.activeLink`. La tarjeta de respaldo se renderiza SOLO cuando el iframe dispara su evento `error` nativo (Wikipedia / Scholar / BHL envían `X-Frame-Options: SAMEORIGIN`); el iframe se oculta con `style={{ display: "none" }}` y el `<a target="_blank" rel="noopener noreferrer">Open in new tab</a>` toma su lugar. El ancla de respaldo es el primer tab stop dentro de la tarjeta para que el foco de teclado aterrice primero allí.

### 11.2 Helper `decodeSpeciesKey`

`frontend/src/store/speciesKey.ts` exporta el helper de round-trip para la clave URL-encoded `${genus}|${epithet}`. El store escribe `encodeURIComponent("${genus}|${epithet}")`; el panel lee de vuelta vía `decodeURIComponent` + `split("|")`. El helper se exporta desde un archivo separado porque la regla de lint `react-refresh/only-export-components` prohíbe mezclar exports de componentes y helpers en el mismo `.tsx`.

### 11.3 Clic en celda de especie de `SpeciesLinks`

El componente `SourceLink` ahora lee `setActiveLink` y despacha `{speciesKey: key, source: link.source, url: link.url}` en el clic cuando se conocen tanto `genus` como `epithet`. El panel de enlaces de breadcrumb (sin props de genus / epithet) NO muta `activeLink` porque `key` es `null` y la llamada a `setActiveLink` se omite. El comportamiento del anchor `target="_blank"` se preserva en ambas ramas.

### 11.4 Montaje en `App.tsx`

`<ExplorerPanel>` se monta dentro de la columna derecha, envuelto en un `<div className="sticky top-0">` para que la página embebida permanezca visible mientras el usuario desplaza la grilla de despacho. El montaje NO mueve el renderizado existente de `<Breadcrumb>` / `<SpeciesLinks>` — el panel es un slot aditivo debajo de ellos.

### 11.5 Descubrimientos de TDD Estricto

- jsdom + React 18.3 NO dispara el `onError` sintético de React en `<iframe>` mediante `fireEvent.error`. La implementación cambió a un `addEventListener('error', handler)` crudo en la ref del iframe, que coincide con lo que hacen los navegadores reales (el spec dice que el listener se asocia al elemento iframe crudo, no a la raíz de dispatch sintético).
- El recorrido de iframes de axe-core falla en jsdom porque el iframe no tiene `contentDocument`. La prueba a11y para el estado de renderizado del iframe usa `axeCore.run(container, { iframes: false })` en vez del helper estándar `axe()`. Los estados vacío + fallback usan el helper estándar porque no tienen contenido de iframe en el que recursar.
- 23 tests nuevos en 4 archivos pinean las 5 cláusulas MUST de `workspace-explorer/spec.md` (sandbox + estado vacío + cableado active-link + aislamiento breadcrumb + fallback + aria-label + peek móvil + axe-core). 135 tests pasan en total.