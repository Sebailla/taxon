# Tareas: arbol-col-browse

## Pronóstico de carga de revisión

| Campo | Valor |
|-------|-------|
| Líneas modificadas estimadas | Backend ~300 LOC + Frontend ~400 LOC + diseño Pencil ~50 LOC (fuera de presupuesto) |
| Riesgo de presupuesto 400 líneas | Medio (alcance combinado); Bajo por PR individual |
| PRs encadenados recomendados | Sí |
| División sugerida | PR 1 (backend) → PR 2 (Pencil + impecable) → PR 3 (frontend) |
| Estrategia de entrega | auto-chain |
| Estrategia de encadenamiento | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Medium

### Unidades de trabajo sugeridas

| Unidad | Objetivo | PR probable | Comando de prueba enfocado | Entorno de ejecución | Límite de rollback |
|--------|----------|-------------|---------------------------|----------------------|---------------------|
| 1 | Endpoints de árbol de backend + esquemas + CTE recursivo + split de autoría + fallback lazy-null | PR 1 (`feat(api): add tree browse endpoints`) | `pytest -v taxon/tests/test_api_router_tree.py` | `curl /api/tree/children?parent_id=5T6MX` tras `python -m taxon.main` contra `data/col.db` | Reversión de PR 1: endpoints eliminados, sin consumidor todavía. |
| 2 | Diseño en Pencil + auditoría impecable para `TaxonomicTree` en `taxon.pen` | PR 2 (`feat(design): taxonomic tree Pencil design + impeccable audit`) | `n/a (sin código)` | `pencil screenshot` de la nueva página de árbol vía Pencil MCP | Reversión de PR 2: `.pen` revertido, sin consumidor todavía. |
| 3 | `TaxonomicTree.tsx` + store Zustand + reemplazo de `Cascade` en `App.tsx` + eliminación de pruebas de Cascade + renombrado aria de Breadcrumb | PR 3 (`feat(frontend): taxonomic tree browse component`) | `npm run typecheck && npm test` | `npm run dev` contra el backend de PR 1, navegar Archaea → … → genus | Reversión de PR 3: Cascade restaurado en `App.tsx`, frontend revierte al estado de dropdowns roto. Backend PR 1 permanece. |

## Fase 1: Endpoints de árbol de backend (PR 1)

- [ ] 1.1 ROJO — escribir `taxon/tests/test_api_router_tree.py` afirmando que `GET /api/tree/children?parent_id=5T6MX` devuelve 200 + 5 filas raíz (Archaea/Bacteria/Eukaryota/Viruses/?incertae sedis) con `has_children`, `species_count`, `authorship`; afirmar que `GET /api/tree/search?q=Euk` devuelve resultados clasificados.
- [ ] 1.2 VERDE — añadir `TreeNodeResponse`, `TreeChildrenResponse`, `TreeSearchResponse`, `TreeSearchHit` a `taxon/api/schemas.py`; exportar desde `__all__`.
- [ ] 1.3 VERDE — añadir los helpers `list_tree_children(parent_id, include, limit, cursor)`, `search_taxon(q, limit, include_extinct)` y `_split_authorship(name, display_name)` a `taxon/api/tree.py`.
- [ ] 1.4 VERDE — registrar `GET /api/tree/children` y `GET /api/tree/search` en `taxon/api/router.py` **antes de la línea 654** (comentario de sombreado del catch-all `{path:path}`); reutilizar `get_db`; usar `Annotated[..., Query(...)]` para parámetros.
- [ ] 1.5 ROJO — añadir `test_species_count_lazy_null.py` afirmando que nodos con más de 100k hijos directos devuelven `species_count=null`; medir el umbral contra `data/col.db` y registrar el valor medido en `openspec/changes/arbol-col-browse/design.md`.
- [ ] 1.6 VERDE — implementar la comprobación de umbral dentro de `list_tree_children`.
- [ ] 1.7 ROJO — añadir `test_search_ranking.py` afirmando exact > prefijo > subcadena con desempate por longitud de `display_name`.
- [ ] 1.8 VERDE — implementar la clasificación dentro de `search_taxon`.
- [ ] 1.9 ROJO — añadir `test_tree_endpoints_route_order.py` (orden de registro de rutas) afirmando que `/api/tree/children` y `/api/tree/search` se registran ANTES del catch-all `/{path:path}/taxon-links`.
- [ ] 1.10 REFACTOR — extraer el CTE recursivo de `species_count` en un helper privado; mantener `pytest` + `pytest-cov` en verde; commit.

## Fase 2: Diseño Pencil + impecable (PR 2, solo diseño)

- [ ] 2.1 Abrir `taxon.pen` vía Pencil MCP (`get_app_state`); añadir la página "Taxonomic Tree Browse": fila de caret, indentado por rango, formato de fila `rank: Name Authorship • N spp.`, encabezado `Find taxon`, controles `Source` + `Extant only`; reutilizar tokens de diseño existentes en `taxon.pen`.
- [ ] 2.2 Ejecutar una pasada de auditoría `impeccable` sobre la nueva página; documentar el resultado en `openspec/changes/arbol-col-browse/design.md` bajo "Pencil Audit".
- [ ] 2.3 Exportar la vista previa HTML de `taxon.pen` mediante `pencil export_html`; adjuntarla como referencia visual para PR 3.
- [ ] 2.4 Refinar el diseño siguiendo los hallazgos de `impeccable`; commitear la captura final en `documents-es/openspec/changes/arbol-col-browse/pencil-preview-es.md` con un breve epígrafe en español neutro según AGENTS.md §1.

## Fase 3: TaxonomicTree de frontend (PR 3)

- [ ] 3.1 ROJO — escribir `frontend/tests/api.treeChildren.test.ts` cubriendo el constructor de URL (`/api/tree/children?parent_id={id}&limit=200`) y la envolvente de decodificación 200/404.
- [ ] 3.2 VERDE — añadir `fetchTreeNode(parentId, init?)` + `fetchTreeSearch(q, init?)` a `frontend/src/api.ts`.
- [ ] 3.3 ROJO — escribir `frontend/tests/api.treeSearch.test.ts` cubriendo el debounce de 200 ms (teclas rápidas colapsan en una sola petición) + decodificación 200/vacío.
- [ ] 3.4 VERDE — implementar el wrapper de debounce de 200 ms para `fetchTreeSearch`.
- [ ] 3.5 ROJO — escribir `frontend/tests/TaxonomicTree.test.tsx` cubriendo toggle de caret (`aria-expanded` refleja el estado), formato de fila `rank: Name Authorship • N spp.`, indentado por profundidad, navegación por teclado (Enter expande, ArrowDown/Up mueve foco), `aria-level` por fila, fetch perezoso en la primera expansión + acierto de caché al re-expandir.
- [ ] 3.6 VERDE — crear `frontend/src/store/taxonomicTree.ts` (Zustand) con estado `{childrenByParentId: Map, expandedIds: Set, rootIds: number[] | null}` + acciones `ensureChildren`, `toggleExpand`, `search`, `select`.
- [ ] 3.7 VERDE — crear `frontend/src/components/TaxonomicTree.tsx` que renderice filas con caret + encabezado `Find taxon` + checkboxes `Source` + `Extant only`; al expandir, despachar CustomEvent `path:change` y escribir la ruta explorada mediante `useCascadePath.getState().setPath(...)`.
- [ ] 3.8 VERDE — modificar `frontend/src/App.tsx`: importar `TaxonomicTree` en lugar de `Cascade`; montar en el mismo slot de grid; mantener literalmente el `useEffect` de breadcrumb-links (líneas 119–142) y el listener `path:change` (líneas 150–159).
- [ ] 3.9 VERDE — renombrar el aria-label de `Breadcrumb.tsx` `Resolved species breadcrumb` → `Cascade path breadcrumb` (Verify-Report §11 ISSUE #3).
- [ ] 3.10 REFACTOR — eliminar `frontend/src/components/Cascade.tsx` + `frontend/src/components/Cascade.state.ts` + cada `frontend/tests/cascade*.test.tsx` y `frontend/tests/Cascade.*.test.tsx`; ejecutar previamente `rg "from.*Cascade"` para detectar cualquier test que los importe.
- [ ] 3.11 VERDE — añadir `frontend/tests/App.taxonLinks.test.tsx` verificando que el panel de breadcrumb-links sigue funcionando de extremo a extremo tras el reemplazo de Cascade.
- [ ] 3.12 ROJO — escribir `frontend/tests/TaxonomicTree.a11y.test.tsx` usando `vitest-axe` para afirmar que no hay violaciones de axe en el árbol renderizado.
- [ ] 3.13 VERDE — corregir todos los problemas de accesibilidad detectados por el escaneo axe.
- [ ] 3.14 Post-merge — tras fusionar PR 3 a `develop` con CI en verde, crear la entrada `/learn-es/YYYY-MM-DD-arbol-col-browse.md` siguiendo la estructura requerida por AGENTS.md §2.

## Matriz de amenazas → mapeo de pruebas ROJAS

| Frontera | Tarea de prueba ROJA | Estado |
|----------|----------------------|--------|
| Orden de registro de rutas (`/api/tree/*` antes de `/{path:path}/taxon-links`) | 1.9 | cubierto |
| `species_count` lazy-null en >100k hijos directos | 1.5 | cubierto |
| Clasificación de búsqueda (exact > prefijo > subcadena + desempate por longitud de `display_name`) | 1.7 | cubierto |
| Camino feliz de backend (filas raíz + autoría + has_children) | 1.1 | cubierto |
| Constructor de URL y decodificación en frontend | 3.1 | cubierto |
| Debounce en frontend | 3.3 | cubierto |
| UI del árbol (caret, indentado, formato de fila, accesibilidad) | 3.5, 3.12 | cubierto |
| Integración con App (breadcrumb-links tras eliminar Cascade) | 3.11 | cubierto |
