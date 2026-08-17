# Árbol CoL — correcciones de drift del PR3 (PR #69)

## Qué

Corrección del drift del PR3 del change SDD `arbol-col-browse` (issue #67, reemplazar los siete dropdowns del Cascade por un árbol jerárquico estilo Catalogue of Life). El sub-agente `sdd-apply` devolvió `sdd_task_result_empty` (fallo de transporte) y dejó los bytes aplicados sin commitear; el código pasaba los tests existentes, pero no cumplía tres requisitos MUST del spec. El PR cierra el change con siete commits por unidad de trabajo y un fix-up de formato.

## Cómo

- **Backend (`taxon/api/tree.py`)** — los endpoints `/api/tree/children` y `/api/tree/search` aceptaban `include_extinct` pero lo descartaban en silencio (`_ = include_extinct`). Se añadió el `WHERE Taxon.is_extinct IS FALSE` en `list_tree_children` (camino raíz y camino no raíz) y en `search_taxon`. Se agrupó la consulta `has_children EXISTS` en un único `parent_id IN (...)` por respuesta; el código previo ejecutaba un EXISTS por hijo (doscientos EXISTS extra por expand, alrededor de seiscientas queries combinando con el `count(*)` y la CTE recursiva).
- **Store zustand (`frontend/src/store/taxonomicTree.ts`)** — se agregaron dos acciones:
  - `revealNode(targetId)`: recorre la cadena de padres hacia atrás desde `targetId`. Para cada nivel busca `parent_id` en la caché `childrenByParentId`; si no está, llama a `fetchTreeNode(targetId)` cuya respuesta incluye la envoltura `parent` y entrega el siguiente `parent_id`. Termina al llegar a un nodo con `parent_id = null` (raíz). Luego expande cada nodo de la cadena y llama a `ensureChildren` para garantizar la caché.
  - `setIncludeExtinct(value)`: invalida la caché completa (`childrenByParentId`, `expandedIds`, `rootIds`, `errorByParentId`, `loadingParentIds`) y vuelve a llamar a `loadRoots()` con la bandera nueva. Las filas ya cacheadas se vuelven a fetchar de forma perezosa en el siguiente expand.
- **Componente (`frontend/src/components/TaxonomicTree.tsx`)** — tres cambios:
  - `handleSearchPick(row)`: ahora llama a `revealNode(row.id)`, `setFocusedId(row.id)` y `scrollIntoView({block: "nearest", behavior: "smooth"})`. Antes era un no-op (`void row; setSearchOpen(false)`).
  - El checkbox "Extant only" dispara `setIncludeExtinct(e.target.checked)` en el `onChange`. Estado inicial `true` (por defecto) en lugar de `false`.
  - Se separó el render del árbol en tres ramas (skeleton / empty + error / rows) para que el host `role="tree"` sólo contenga treeitems. Los skeletons llevan ahora `role="treeitem"` y `aria-level={1}`. Los bloques empty y error se elevan fuera del host para cumplir con la regla axe `aria-required-children`.
- **Accesibilidad del input de búsqueda** — se agregó `aria-activedescendant={searchOpen ? `tree-search-result-${searchHits[searchHighlight].id}` : undefined}` en el combobox y un `id` por cada `<button role="option">` del listbox, conforme al §11 del design.
- **Test de accesibilidad (`frontend/tests/a11y.test.tsx`)** — se envolvió el `render(<App />)` en `await act(async () => {...})` para silenciar el aviso `An update to TaxonomicTree inside a test was not wrapped in act(...)` que dispara el efecto `loadRoots` del `TaxonomicTree` al montar.

## Dónde

- `taxon/api/tree.py` — fix `include_extinct`, batch de `has_children`, búsqueda batcheada de `parents_seen` en `search_taxon`.
- `taxon/api/router.py` — registro de `/api/tree/children` y `/api/tree/search` antes del catch-all `/{path:path}/taxon-links`.
- `taxon/api/schemas.py` — modelos `TreeNodeResponse`, `TreeChildrenResponse`, `TreeSearchResponse`.
- `taxon/tests/test_api_router_tree.py` — se añadió `_extinct_fixture` (usa el prefijo `†` daga que reconoce el parser) y dos escenarios (`include_extinct=false` oculta filas extintas; por defecto las incluye).
- `taxon/tests/test_search_ranking.py` — seis tests del helper de ranking exact / prefix / substring.
- `taxon/tests/test_species_count_lazy_null.py` — cinco tests del umbral de lazy-null a cien mil hijos directos.
- `frontend/src/components/TaxonomicTree.tsx` — search pick, extant-only, separación del render y `aria-activedescendant`.
- `frontend/src/store/taxonomicTree.ts` — store zustand con `revealNode`, `setIncludeExtinct` y la bandera `includeExtinct`.
- `frontend/src/api.ts` — `fetchTreeNode`, `fetchTreeSearch`, `buildTreeChildrenUrl` y `createDebouncedSearch`.
- `frontend/src/App.tsx` — cableado del `<TaxonomicTree>` en el slot del `<Cascade>`; preserva el contrato del evento `path:change` para el panel breadcrumb-links.
- `frontend/src/components/Breadcrumb.tsx` — sin cambios funcionales (sólo limpieza de imports).
- `frontend/tests/TaxonomicTree.test.tsx` — nueve tests base más dos nuevos (search pick expande ancestros y enfoca la fila elegida; extant-only dispara un refetch con `include_extinct=false`).
- `frontend/tests/TaxonomicTree.a11y.test.tsx` — un test de axe-core sobre las cinco filas raíz.
- `frontend/tests/api.treeChildren.test.ts` — quince tests del wrapper del cliente tipado.
- `frontend/tests/api.treeSearch.test.ts` — cinco tests del wrapper de debounce.
- `frontend/tests/a11y.test.tsx` — envoltura en `act()` para el render del App.
- `docs/design/taxonomic-tree-browse.md` — design doc prescriptivo (reemplaza la página `.pen` porque el MCP de Pencil estaba caído).
- `documents-es/docs/design/` — espejo en español.
- `openspec/changes/arbol-col-browse/{proposal,design,tasks}.md` — artefactos SDD.
- `openspec/changes/arbol-col-browse/specs/{taxonomic-tree-browse,taxon-tree-search,taxonomy-hierarchy}/spec.md` — deltas de spec.
- `documents-es/openspec/changes/arbol-col-browse/` — espejos.

## Por qué

El PR3 cerró el ciclo del change `arbol-col-browse`. El sub-agente previo había producido código que pasaba los tests existentes pero NO los requisitos del spec (navegación del search pick, filtro extant-only, `include_extinct` en el servidor). Si el `sdd-verify` formal se hubiera ejecutado, habría atrapado los tres MUST de inmediato — el fallo de transporte enmascaró el gatekeeper. Se arrancó un nuevo ciclo partiendo de los bytes aplicados y se escribieron tests rojos contra los WHEN / THEN del spec, seguidos de fixes verdes y la suite completa en verde. Esto cierra el #67.

## Cómo funciona en producción

1. El usuario abre la app. El `<TaxonomicTree>` se monta en el slot del `<Cascade>` y dispara `loadRoots()` en un `useEffect`. El store lleva `includeExtinct: true` por defecto, así que el fetch a `/api/tree/children?parent_id=0&limit=200` incluye las cinco filas de CoL con `parent_id IS NULL` (Archaea, Bacteria, Eukaryota, Viruses, ?incertae sedis).
2. El usuario hace click en el caret de Eukaryota. El store llama a `ensureChildren(5)` (fetch y caché), `toggleExpand(5)`. El `useEffect([expandedIds, childrenByParentId])` despacha `path:change` con `detail.path = ["Eukaryota"]`. El `App` lo escucha y actualiza `useCascadePath.setPath`. El panel breadcrumb-links renderiza los trece enlaces referidos a Eukaryota.
3. El usuario escribe "Pan" en el input de búsqueda. El debounce de doscientos milisegundos colapsa los keystrokes en un único fetch a `/api/tree/search?q=Pan&limit=8`. Los hits se renderizan en el listbox con `aria-activedescendant` siguiendo a la fila resaltada.
4. El usuario hace click en el primer hit (Panthera, id=42). `handleSearchPick(42)` invoca `revealNode(42)` que recorre la cadena de padres hasta la raíz, expandiendo cada uno y fetcheando los `parent_id` faltantes con `fetchTreeNode`. Cuando termina, `setFocusedId(42)` mueve el foco a la fila de Panthera y `scrollIntoView({block: "nearest", behavior: "smooth"})` la trae al viewport.
5. El usuario marca el checkbox "Extant only". El handler llama a `setIncludeExtinct(false)`. El store invalida toda la caché y vuelve a llamar a `loadRoots()` con la bandera nueva. El fetch a `/api/tree/children?parent_id=0&limit=200&include_extinct=false` ahora excluye las filas con `is_extinct=true` del lado del servidor (no es un filtro del cliente). El árbol se vuelve a renderizar sin filas extintas a cualquier profundidad.
6. Si una fila tiene un fetch fallido (red o 5xx), la celda renderiza un `<span>` con "Couldn't load children" más un botón "Retry" que limpia el error y vuelve a llamar a `ensureChildren(parentId)`. Las demás filas expandidas no se tocan.

## Workflows

- **Commits por unidad de trabajo** (skill `work-unit-commits`) — siete commits en `feat/arbol-col-browse` con un concern por commit: fix include_extinct, cableado del search pick, App + Breadcrumb + api.ts wiring, borrado del Cascade, superficie PR1 del backend, tests frontend y docs, fix de formato.
- **TDD estricto** (activo por `openspec/config.yaml`) — para los tres fixes MUST: test rojo primero (pineando los WHEN / THEN del spec), luego implementación verde, luego verificación de la suite completa.
- **Patrón de recuperación del sub-agente** — `sdd_task_result_empty` no es "fallo de trabajo" sino "fallo de transporte". La recuperación: `git status` y `git diff --stat` en el worktree para confirmar qué se aplicó, leer cada archivo nuevo, evaluarlo contra los WHEN / THEN del spec, escribir tests rojos contra la brecha, implementar verde, commitear, abrir PR. Documentado en la memoria Engram con topic `sdd/arbol-col-browse/pr3-drift-fixes`.
- **Stack de verificación local** — `pytest` (192/192), `vitest run` (99/99), `tsc -b && vite build`, `ruff format --check .` y `ruff check .`. El formateador fue la brecha que rompió el primer push a CI (tres archivos sin envoltura adecuada).
- **Compuertas de CI** — backend py3.11, backend py3.12, frontend node20 y lighthouse a11y. Las cuatro en verde tras el fix-up de formato (commit `c5c50f2`).
- **PR honesto** — el cuerpo del PR documenta explícitamente el drift del sub-agente (tabla "sub-agent state vs this PR") para que la persona revisora entienda qué se aplicó y qué hubo que rehacer.
- **Limpieza post-merge** — borrar `../taxon-worktrees/arbol-col-browse/`.