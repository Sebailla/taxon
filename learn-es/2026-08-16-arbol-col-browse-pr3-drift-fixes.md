# Árbol CoL — drift fixes de PR3 (PR #69)

## Qué

Fix de drift del PR3 del change SDD `arbol-col-browse` (issue #67, reemplazar los 7 dropdowns del Cascade por un árbol jerárquico CoL-style). El sub-agente `sdd-apply` reportó `sdd_task_result_empty` (transport-level) y aplicó bytes sin commitearlos; el código aplicado pasaba los tests existentes pero incumplía 3 requisitos MUST del spec. El PR cierra el change con 7 commits de work-unit + un fix-up de formatter.

## Cómo

- **Backend (`taxon/api/tree.py`)** — los endpoints `/api/tree/children` y `/api/tree/search` aceptaban `include_extinct` pero lo descartaban silenciosamente (`_ = include_extinct`). Añadido el `WHERE Taxon.is_extinct IS FALSE` en `list_tree_children` (path raíz + path no-raíz) y en `search_taxon`. Batch del `has_children EXISTS` a UN solo query con `parent_id IN (...)` por response — el código previo corría un EXISTS por hijo (200 EXISTS queries extra por expand de 200 rows, ~600 queries total combinando con el count y la CTE recursiva).
- **Store zustand (`frontend/src/store/taxonomicTree.ts`)** — agregadas dos acciones:
  - `revealNode(targetId)`: walks el parent chain backwards desde `targetId`. Para cada nivel busca `parent_id` en el cache `childrenByParentId`; si no está, hace `fetchTreeNode(targetId)` que devuelve la envoltura `parent` del backend y entrega el siguiente `parent_id`. Termina cuando llega a un nodo con `parent_id = null` (raíz). Después expande cada nodo de la cadena y llama `ensureChildren` para garantizar la cache.
  - `setIncludeExtinct(value)`: invalida el cache completo (`childrenByParentId`, `expandedIds`, `rootIds`, `errorByParentId`, `loadingParentIds`) y vuelve a llamar `loadRoots()` con el flag nuevo. Las filas ya cacheadas se refetchan perezosamente al próximo expand.
- **Componente (`frontend/src/components/TaxonomicTree.tsx`)** — tres cambios:
  - `handleSearchPick(row)`: ahora llama `revealNode(row.id)` + `setFocusedId(row.id)` + `scrollIntoView({block: "nearest", behavior: "smooth"})`. Antes era un no-op (`void row; setSearchOpen(false)`).
  - El checkbox "Extant only" dispara `setIncludeExtinct(e.target.checked)` en el `onChange`. Estado inicial `true` (default) en vez de `false`.
  - Split del render del árbol en tres ramas (skeleton / empty + error / rows) para que el host `role="tree"` solo contenga treeitems. Skeletons ahora cargan `role="treeitem"` + `aria-level={1}`. Empty + error blocks hoisted fuera del host (cumplir axe `aria-required-children`).
- **Search input a11y** — agregado `aria-activedescendant={searchOpen ? `tree-search-result-${searchHits[searchHighlight].id}` : undefined}` en el combobox + `id` por cada `<button role="option">` del listbox. Cumple design §11.
- **Test a11y (`frontend/tests/a11y.test.tsx`)** — wrap del `render(<App />)` en `await act(async () => {...})` para silenciar el warning `An update to TaxonomicTree inside a test was not wrapped in act(...)` que dispara el `loadRoots` effect del TaxonomicTree en mount.

## Dónde

- `taxon/api/tree.py` — fix `include_extinct`, batch `has_children`, búsqueda batch de `parents_seen` en `search_taxon`.
- `taxon/api/router.py` — registro de `/api/tree/children` y `/api/tree/search` ANTES del catch-all `/{path:path}/taxon-links`.
- `taxon/api/schemas.py` — modelos `TreeNodeResponse`, `TreeChildrenResponse`, `TreeSearchResponse`.
- `taxon/tests/test_api_router_tree.py` — agregado `_extinct_fixture` (usa el prefijo `†` daga que reconoce el parser) + 2 escenarios (`include_extinct=false` oculta filas extintas; default las incluye).
- `taxon/tests/test_search_ranking.py` — 6 tests del helper de ranking exact/prefix/substring.
- `taxon/tests/test_species_count_lazy_null.py` — 5 tests del threshold lazy-null a 100k hijos directos.
- `frontend/src/components/TaxonomicTree.tsx` — search pick + extant-only + render split + a11y aria-activedescendant.
- `frontend/src/store/taxonomicTree.ts` — store zustand con `revealNode`, `setIncludeExtinct`, `includeExtinct` flag.
- `frontend/src/api.ts` — `fetchTreeNode`, `fetchTreeSearch`, `buildTreeChildrenUrl`, `createDebouncedSearch`.
- `frontend/src/App.tsx` — wire del `<TaxonomicTree>` en el slot del `<Cascade>`; preserva el contrato del evento `path:change` para el panel breadcrumb-links.
- `frontend/src/components/Breadcrumb.tsx` — sin cambios funcionales (sólo imports limpios).
- `frontend/tests/TaxonomicTree.test.tsx` — 9 tests base + 2 nuevos (`search pick expands ancestors and focuses the chosen row`, `extant-only checkbox triggers a refetch with include_extinct=false`).
- `frontend/tests/TaxonomicTree.a11y.test.tsx` — 1 test axe-core sobre los 5 root rows.
- `frontend/tests/api.treeChildren.test.ts` — 15 tests del typed client wrapper.
- `frontend/tests/api.treeSearch.test.ts` — 5 tests del debounce wrapper.
- `frontend/tests/a11y.test.tsx` — wrap en `act()` para el App render.
- `docs/design/taxonomic-tree-browse.md` — design doc prescriptive (reemplaza el `.pen` page porque el Pencil MCP estaba caído).
- `documents-es/docs/design/` — mirror español.
- `openspec/changes/arbol-col-browse/{proposal,design,tasks}.md` — artefactos SDD.
- `openspec/changes/arbol-col-browse/specs/{taxonomic-tree-browse,taxon-tree-search,taxonomy-hierarchy}/spec.md` — spec deltas.
- `documents-es/openspec/changes/arbol-col-browse/` — mirrors.

## Por qué

El PR3 cerró el ciclo del change `arbol-col-browse`. El sub-agente previo había producido código que pasaba los tests existentes pero NO los requisitos del spec (search pick navigation, extant-only filter, include_extinct server-side). Si el `sdd-verify` formal se hubiera corrido, habría atrapado los3 MUST inmediatamente — el transport failure enmascaró el gatekeeper. Se arranca el nuevo ciclo partiendo de los bytes aplicados + tests rojos contra los WHEN/THEN del spec + fixes verdes + suite completa verde. Esto cierra #67.

## Cómo funciona en producción

1. El usuario abre la app. El `<TaxonomicTree>` se monta en el slot del `<Cascade>` y dispara `loadRoots()` en `useEffect`. El store lleva `includeExtinct: true` por default, así que el fetch a `/api/tree/children?parent_id=0&limit=200` incluye las 5 filas de CoL con `parent_id IS NULL` (Archaea, Bacteria, Eukaryota, Viruses, ?incertae sedis).
2. El usuario hace click en el caret de Eukaryota. El store llama `ensureChildren(5)` (fetch + cache), `toggleExpand(5)`. El `useEffect([expandedIds, childrenByParentId])` despacha `path:change` con `detail.path = ["Eukaryota"]`. El `App` lo escucha y actualiza `useCascadePath.setPath`. El panel breadcrumb-links renderiza los 13 enlaces referidos a Eukaryota.
3. El usuario escribe "Pan" en el input search. El debounce de 200ms colapsa los keystrokes en UN fetch a `/api/tree/search?q=Pan&limit=8`. Los hits renderizan en el listbox con `aria-activedescendant` siguiendo al highlighted row.
4. El usuario hace click en el primer hit (Panthera, id=42). `handleSearchPick(42)` invoca `revealNode(42)` que walks la cadena de padres hasta la raíz, expandiendo cada uno y fetcheando los `parent_id` faltantes con `fetchTreeNode`. Cuando termina, `setFocusedId(42)` mueve el focus al row de Panthera y `scrollIntoView({block: "nearest", behavior: "smooth"})` lo trae al viewport.
5. El usuario marca el checkbox "Extant only". El handler llama `setIncludeExtinct(false)`. El store invalida el cache entero y re-llama `loadRoots()` con el flag nuevo. El fetch a `/api/tree/children?parent_id=0&limit=200&include_extinct=false` ahora excluye las filas con `is_extinct=true` server-side (no client-side filter). El árbol re-renderiza sin filas extintas en cualquier profundidad.
6. Si una fila tiene un fetch fallido (network o 5xx), la celda renderiza una `<span>` con "Couldn't load children" + botón "Retry" que limpia el error y re-llama `ensureChildren(parentId)`. Las demás filas expandidas no se tocan.

## Workflows

- **Work-unit commits** (skill `work-unit-commits`) — 7 commits en `feat/arbol-col-browse` con un concern por commit: fix include_extinct, search-pick wiring, App + Breadcrumb + api.ts wiring, Cascade deletion, backend PR1 surface, frontend tests + docs, style formatter.
- **Strict TDD** (active per `openspec/config.yaml`) — para los 3 fixes MUST: test rojo primero (pinning WHEN/THEN del spec), luego implementación verde, luego verificar suite completa.
- **Sub-agent recovery pattern** — `sdd_task_result_empty` no es "work failure" sino "transport failure". El recovery: `git status` + diff-stat en el worktree para confirmar qué se aplicó, leer cada archivo nuevo, evaluar contra los WHEN/THEN del spec, escribir tests rojos contra el gap, implementar verde, commitear, abrir PR. Documentado en la memoria Engram topic `sdd/arbol-col-browse/pr3-drift-fixes`.
- **Verify stack local** — `pytest` (192/192), `vitest run` (99/99), `tsc -b && vite build`, `ruff format --check .`, `ruff check .`. El formatter fue el gap que rompió el primer push a CI (3 archivos sin wrapping).
- **CI gates** — backend py3.11, backend py3.12, frontend node20, lighthouse a11y. Los 4 verdes después del fix-up de formatter (commit `c5c50f2`).
- **PR honesto** — el body del PR documenta el drift del sub-agente explícitamente (tabla "sub-agent state vs this PR") para que el reviewer entienda qué se aplicó vs qué se tuvo que rehacer.
- **Cleanup post-merge** — borrar `../taxon-worktrees/arbol-col-browse/`.