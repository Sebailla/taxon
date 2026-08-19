# Learn: tree-deep-subtree (issue #76)

## What

`GET /api/tree/children` ahora devuelve cada descendiente de un nodo agrupado por rango (`phylum`, `family`, `order`, `genus`, `species`) en un envelope `next_tiers` con paginación por tier indexada por `(name, id)`. El frontend React renderiza esos tier groups como componentes colapsables entre los hijos directos y los grandchildren, con keyboard nav y ARIA. Cierra el issue #76.

## How

**Backend (Python 3.11 + FastAPI + SQLAlchemy + SQLite):**
- Módulo compartido nuevo `taxon/api/_tree_tiers.py` (+572 LOC) que aloja los helpers de roll-up extraídos desde `sqlite_resolver.py` (`_phylum_rollup`, `_family_rollup`, `_collect_descendants_by_rank`, `_build_tiers_from_grouping`, `_build_tier`) + la CTE recursiva por tier (`_per_tier_walk` con `max_depth=8`, `tier_ranks IN (...)`) + el cursor opaco (`_encode_cursor` / `_decode_cursor`, base64 de `f"{name}\x00{id}"`) + el builder de envelope (`_build_next_tiers`).
- Schema `TreeNodeTier(BaseModel)` con `rank`, `label`, `examples`, `children: list[TreeNodeResponse]`, `next_cursor: str | None`. `TreeChildrenResponse` gana `next_tiers: list[TreeNodeTier] | None`.
- Router `get_tree_children` acepta `tier` + `tier_limit` query params; clamp `tier_limit > 200` silencioso; rechaza `< 1` con HTTP 400.
- Índice compuesto `ix_taxa_parent_rank_name (parent_id, rank, name)` declarado en `Taxon.__table_args__` + wireado en `taxon.migrate._ensure_indexes`. CLI flags `--only-index` y `--skip-indexes` añadidos.

**Frontend (React 18 + Vite + Tailwind 3 + Zustand):**
- Store `taxonomicTree` gana `nextTiersByParentId: Map<number, TreeNodeTier[]>` + `tierRowsByKey: Map<string, { rows; nextCursor }>` + acción `loadMore(parentId, rank)`. `setIncludeExtinct` extiende la disciplina de invalidación a los nuevos caches.
- `api.ts` ensancha `TreeChildrenResponse` con `next_tiers`; nuevo `fetchTierPage(parentId, tier, cursor, { tierLimit, signal })` con `FETCH_TIER_PAGE_DEFAULT_LIMIT=50`; `buildTreeChildrenUrl` acepta `tier` + `cursor`.
- Componente `<TierGroup>` en `TaxonomicTree.tsx` con header (caret + label + row count) + child rows + botón "Load more". El primer tier (`phylum`) expande por defecto; los subsiguientes colapsados.
- Keyboard nav global (ArrowDown/Up/Right/Left/Enter/Home/End) cruza el límite del tier group igual que cruza una fila regular; local TierRow nav maneja ArrowDown/Up/Home/End/Enter dentro del grupo.
- ARIA: tier group container `role="group"` + `aria-label="<label> group"`; header `role="button"` + `aria-expanded` + `aria-controls`; "Load more" button `aria-label="Load more <label>"`.

## Where

- `taxon/api/_tree_tiers.py` — nuevo módulo compartido (572 LOC)
- `taxon/api/sqlite_resolver.py` — re-exports de los helpers extraídos
- `taxon/api/schemas.py` — `TreeNodeTier` + `TreeChildrenResponse.next_tiers`
- `taxon/api/tree.py` — `list_tree_children` honra `tier` + `tier_limit`
- `taxon/api/router.py` — `get_tree_children` acepta query params
- `taxon/api/_tree_tiers.py::_per_tier_walk` — CTE recursiva por tier
- `taxon/schema.py` — `Index("ix_taxa_parent_rank_name", "parent_id", "rank", "name")`
- `taxon/migrate.py` — `_ensure_indexes()` + CLI flags `--only-index` / `--skip-indexes`
- `taxon/tests/test_api_router_tree.py` — 9 nuevos tests (`next_tiers` contract + cursors + off-tuple collapse)
- `taxon/tests/test_migrate.py` — 3 nuevos tests para el índice
- `frontend/src/components/TaxonomicTree.tsx` — `<TierGroup>` + `<TierRow>` + walk + global keyboard nav
- `frontend/src/store/taxonomicTree.ts` — `nextTiersByParentId` + `tierRowsByKey` + `loadMore` + `tierFetchedKeys`
- `frontend/src/api.ts` — `fetchTierPage` + `TreeNodeTier` + `FETCH_TIER_PAGE_DEFAULT_LIMIT`
- `frontend/tests/TaxonomicTree.test.tsx` — 5 nuevos tests del tier-group contract
- `frontend/tests/api.fetchTierPage.test.ts` — 8 nuevos tests
- `frontend/tests/store.taxonomicTree.tiers.test.ts` — 4 nuevos tests
- `openspec/specs/taxonomic-tree-browse/subtree.md` — delta spec
- `documents-es/openspec/specs/taxonomic-tree-browse/subtree-es.md` — mirror en español
- `docs/design/stitch/tree-deep-subtree-design.md` + `documents-es/docs/design/stitch/tree-deep-subtree-design-es.md` — surface brief Stitch + auditoría impeccable
- `openspec/changes/tree-deep-subtree/verify-report.md` + `documents-es/openspec/changes/tree-deep-subtree/verify-report-es.md` — reporte de verificación

## Why

El tree CoL-style (PR #69) solo mostraba los hijos directos de cada nodo. Expandir `Animalia` (uno de los 5 CoL roots) volcaba 22,711 filas alfabéticas (12,667 species + 9,889 genera + 103 families + 34 phyla) — el usuario nunca llegaba a la cascada phylum que la UI prometía (`Animalia → Chordata → Vertebrata → Mammalia`). El species-count badge quedaba `None` en cada hijo de Animalia porque el threshold lazy-null (>100k directos) se disparaba, así que el formato `rank: Name Authorship • N spp.` también degradaba. **Mismo problema en cada nodo profundo** (Eukaryota, Archaea, Bacteria).

La solución replica la forma probada de `/api/path-children`: cada padre expandido muestra sus descendientes agrupados por tier, con paginación por tier (50 default / 200 max) y cursor opaco `(name, id)` para que el ordenamiento alfabético sobreviva re-imports. Los roll-ups `_phylum_rollup` y `_family_rollup` que la cascada ya confía colapsan los rangos intermedios (subphylum → phylum, subfamily → family) para que el CoL indent-by-rank UI siga funcionando.

## How it works

**Flujo del usuario:**

1. Usuario abre `Eukaryota` en el árbol.
2. Aparecen 5 filas root (Animalia, Archaea, Bacteria, Fungi, Plantae) — los hijos directos del root.
3. Usuario expande `Animalia`. Direct children: 5 phyla (Arthropoda, Mollusca, Chordata, Nematoda, Priapulimorpha) + tier group "Phyla (34)".
4. El tier group "Phyla (34)" expande por defecto (primer tier). Carga la primera página de 50 phyla con la misma indent que una fila regular + 1 nivel.
5. Si la primera página llega a 50 filas y el header del tier tenía `next_cursor` no-nulo, aparece "Load more Phyla" — click → segunda página → appenda al cache.
6. Cuando el cache cursor vuelve null, el botón "Load more" desaparece (P1 #2 fix) — no se renderiza deshabilitado.
7. Keyboard nav: ArrowDown mueve el foco entre filas (incluyendo el header del tier group); ArrowRight/Left expande/colapsa el header; Home/End salta a la primera/última fila del active group.

**Flujo del backend:**

1. `GET /api/tree/children?parent_id={id}` → `list_tree_children` (sin `tier` query).
2. Carga direct children via `_children_query_base` (query base, mismo código que ya teníamos).
3. Construye `_build_next_tiers(parent_id, direct_children, tier_limit=50, cursor=None)`.
4. `_build_next_tiers` itera cada tier hijo (phylum, family, order, genus, species), corre la CTE recursiva por tier con `tier_ranks IN (...)` + `max_depth=8`.
5. Devuelve `TreeChildrenResponse` con `children: <direct>` + `next_tiers: [<tier1>, <tier2>, ...]`.

**Flujo del frontend:**

1. `TaxonomicTree` boot → `loadRoots()` → `fetchTreeSearch` no aplica, viene de `fetchTreeChildren`.
2. `walk()` (DFS del árbol) emite `VisibleRow` entries: `tree-row` para nodos regulares, `tier-group` para buckets del envelope.
3. Cuando el usuario toggle-expand un padre, `walk` emite los tier-groups ANTES de los grandchildren — preservando el cascade-rank order.
4. Cada `<TierGroup>` lee su `tierRowsByKey` del store; primer load = del envelope (`tier.children`); loads subsiguientes = de `loadMore(parentId, rank)` que llama `fetchTierPage` con el cursor opaco.

## Workflows

- **SDD pipeline**: `chain auto-chain stacked-to-main` con 4 PRs encadenadas. PR A.1 fue `size:exception` (1326 LOC vs 360 forecast por la extracción del módulo `_tree_tiers.py`). PR C original fue partido en C.1 (store+api) + C.2 (componente+nav+ARIA) por decisión del usuario para mantener cada PR dentro del budget.
- **Design gate**: Stitch MCP reemplazó Pencil (deprecado) para la superficie del tier group. Auditoría impecable ejecutó como degraded inline (single-context, sin `detect.mjs`). 2 fixes P1 aplicados inline (text-slate contrast en Load more + rollup note; hide Load more cuando no hay cursor).
- **Strict TDD**: cada PR siguió RED → GREEN → REFACTOR por work unit. PR C.2 tuvo un transport failure del sub-agent `sdd-apply` durante el launch — el orchestrator completó WU 2 + WU 3 directamente con la misma spec, manteniendo el surface brief como source of truth.
- **CI**: 4 jobs (backend py3.11 + py3.12, frontend node 20, lighthouse a11y) corren en cada PR. Todos verdes en las 4 PRs.
- **Mirror en español**: cada artefacto técnico tiene mirror en `documents-es/` per `AGENTS.md §1`. Los planning mirrors de proposal/design/explore se perdieron durante la limpieza de sesión — follow-up si se necesitan reautorizar.
- **RDD kill switch**: off por default; no se usó porque las PRs pasaron por review humano, no reviewer nativo.
- **Branching**: `feat/tree-deep-subtree-pr{1,2,3-1,3-2}` para PRs; `chore/tree-deep-subtree-verify` para PR D. Todos mergeados a `develop` (vía squash). `main` no se tocó.
