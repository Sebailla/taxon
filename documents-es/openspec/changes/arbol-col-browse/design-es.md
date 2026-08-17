# Diseño: arbol-col-browse

## Enfoque técnico

**Enfoque 3 (híbrido).** El backend añade `GET /api/tree/children?parent_id={id}` y `GET /api/tree/search?q={q}`. La ruta existente `/{path:path}/taxon-links` sigue alimentando el panel de enlaces del breadcrumb; las invariantes de `breadcrumb-dinamico` se mantienen verbatim. El direccionamiento por `parent_id` evita el bug de síntesis de `Biota`; `authorship` se deriva del corte de `display_name`; `species_count` se calcula mediante una CTE recursiva con `null` diferido para nodos con más de 100k hijos directos. El frontend sustituye `Cascade.tsx` + `Cascade.state.ts` por `TaxonomicTree.tsx` + una caché de árbol en Zustand indexada por `parent_id`. El camino explorado fluye por el store `cascadePath` + el `CustomEvent path:change`.

## Decisiones de arquitectura

| # | Elección | Decisión |
|---|----------|----------|
| 1 | `parent_id` (int) evita la síntesis de Biota; estable entre CLB/CoL/Viruses | `parent_id={id:int}` |
| 2 | La CTE viva conserva exactitud; sin re-importación de `species_paths` | CTE recursiva, `null` cuando hijos directos > 100k |
| 3 | No hay columna en BD; `display_name` lleva la citación | Cortar la cola de `display_name` tras `name` en tiempo de consulta |
| 4 | Caché perezosa sobrevive al unmount; `cascadePath` alimenta el breadcrumb | `childrenByParent: Map<id, TreeNode[]>` + `expandedIds: Set<id>` + el `cascadePath` existente |
| 5 | Un round-trip por caret es costoso | `has_children` precalculado en la consulta del padre vía `EXISTS` |
| 6 | Sin backend; el no-op oculta la brecha multi-fuente | UI no-op CoL-only en el primer PR |
| 7 | `openspec/config.yaml strict_tdd: true` | Tests primero |

## Flujo de datos

```
[ clic en caret ] → store TaxonomicTree (expandedIds.add)
  → fetchTreeNode(parent_id) → GET /api/tree/children
    list_tree_children + CTE species_count + split_authorship
    → TreeChildrenResponse{parent, children[], next_cursor}
  → render filas: rango: Nombre Citación • N spp.

[ camino explorado ] → useCascadePath.setPath(segments)
  + window.dispatchEvent('path:change', {path})
  → App.tsx → fetchTaxonLinks → /api/{path}/taxon-links
  → <SpeciesLinks links={...}/> renderiza la cuadrícula de 13 enlaces
```

## Cambios de archivos

- **Crear** `taxon/api/tree.py` (`list_tree_children`, `search_taxon`, `_split_authorship`, CTE recursiva); `taxon/tests/test_api_router_tree.py` (RED primero); `frontend/src/components/TaxonomicTree.tsx`; `frontend/src/store/taxonomicTree.ts` (`childrenByParent` + `expandedIds`); `frontend/tests/TaxonomicTree.test.tsx`; `frontend/tests/api.treeChildren.test.ts`; `frontend/tests/api.treeSearch.test.ts`.
- **Modificar** `taxon/api/router.py` (registrar `/api/tree/*` ANTES del catch-all `/{path:path}/taxon-links` en la línea 654); `taxon/api/schemas.py` (añadir `TreeNodeResponse`, `TreeChildrenResponse`, `TreeSearchResponse`; exportar en `__all__`); `frontend/src/App.tsx` (montar `<TaxonomicTree>` en lugar de `<Cascade>`; mantener verbatim el listener `path:change` líneas 150–159 y el `useEffect` de breadcrumb-links líneas 119–142); `frontend/src/api.ts` (añadir `fetchTreeNode`, `fetchTreeSearch`); `frontend/src/components/Breadcrumb.tsx` (renombrar `aria-label="Resolved species breadcrumb"` → `"Cascade path breadcrumb"` según Verify-Report §11 ISSUE #3). El chip "extinct" de `<Toggles>` se pliega en el nuevo checkbox "Extant only" dentro de `TaxonomicTree.tsx`.
- **Borrar** `frontend/src/components/Cascade.tsx`; `frontend/src/components/Cascade.state.ts`; `frontend/tests/cascadeDynamicTiers.test.tsx`; `Cascade.pathAware.test.tsx`; `Cascade.ui.test.tsx`; `cascadeRoots.test.tsx`; `cascadeSubphylum.test.tsx`; `Cascade.test.tsx.legacy`.
- **Docs**: `documents-es/openspec/changes/arbol-col-browse/design-es.md`.

## Interfaces / contratos

```python
# taxon/api/schemas.py
class TreeNodeResponse(TaxonResponse):
    has_children: bool
    species_count: int | None  # null cuando hijos directos > 100k
    authorship: str

class TreeChildrenResponse(_ORMBase):
    parent: TreeNodeResponse
    children: list[TreeNodeResponse]
    next_cursor: str | None

class TreeSearchResponse(_ORMBase):
    items: list[TreeNodeResponse]
```

```
# GET /api/tree/children?parent_id={int}&limit={n}&cursor={c}&include_extinct={bool}
# 200 → TreeChildrenResponse; 404 cuando parent_id no existe
# GET /api/tree/search?q={str}&limit={8}
# 200 → TreeSearchResponse (ranked exact > prefix > substring)
```

```sql
-- CTE recursiva para species_count (taxon/api/tree.py)
WITH RECURSIVE descendants(id) AS (
  SELECT id FROM taxa WHERE parent_id = :parent
  UNION ALL
  SELECT t.id FROM taxa t JOIN descendants d ON t.parent_id = d.id
)
SELECT COUNT(*) FROM descendants d
JOIN taxa t ON t.id = d.id
WHERE LOWER(t.display_level) = 'species';
```

```python
# taxon/api/tree.py
def _split_authorship(name: str, display_name: str) -> str:
    if display_name.startswith(name):
        return display_name[len(name):].strip()
    return display_name
```

## Estrategia de pruebas

| Capa | Qué | Cómo |
|------|-----|------|
| Unit (pytest) | `list_tree_children`, CTE recursiva, `_split_authorship`, fallback null, ranking, sobres de error (400/404/422) | `test_api_router_tree.py`; SQLite en memoria; RED primero |
| Unit (vitest) | Toggle de caret, formato de fila, indentado, teclado Enter/Arrow, `aria-level`/`aria-expanded`, reintento, estado vacío, payload `path:change` | `@testing-library/react`, `fetch` mockeado |
| Integration (vitest) | Cableado de App: listener `path:change`, refetch de breadcrumb-links | `App.taxonLinks.test.tsx` |
| A11y (vitest-axe) | Contraste, orden de foco, etiquetas aria en `TaxonomicTree` | `TaxonomicTree.a11y.test.tsx` |

## Matriz de amenazas

| Frontera | Aplicabilidad | Respuesta de diseño | Pruebas RED planeadas |
|----------|---------------|---------------------|-----------------------|
| Rutas tipo doc (.sh, .md ejecutable) | N/A — sin estos archivos | — | — |
| Selección de repo Git | N/A — sin `git -C` | — | — |
| Automatización de commit / push / PR | N/A — sin automatización | — | — |
| **Orden de registro de rutas** | **Aplicable** — `/api/tree/*` debe registrarse ANTES del catch-all `/{path:path}/taxon-links` (línea 654) para evitar shadowing | Agrupar `/tree/*`; insertar por encima del catch-all | RED: `GET /api/tree/children?parent_id=2` → 200; RED: `GET /api/tree/search?q=Euk` → 200. Seguro: registrado primero. Fallo: el catch-all absorbe → 404 |

## Migración / despliegue

Sin migración de datos. El PR de backend añade dos endpoints de forma aditiva. El PR de frontend monta `TaxonomicTree` en el mismo slot de la cuadrícula y luego borra `Cascade` en un slice encadenado, de modo que `develop` nunca vea un estado intermedio roto. La síntesis de Biota en `/api/kingdoms` se mantiene (sin uso pero inocua; su borrado es un follow-up). Rollback: `git revert <merge-commit>` por PR. Pencil + `impeccable` gatean el PR de frontend según AGENTS.md §5.

## Preguntas abiertas

- [ ] Confirmar el umbral perezoso de 100k hijos directos para el `null` de `species_count` frente a `data/col.db` (benchmark en apply).
- [ ] Confirmar que el no-op de `Source` en el primer PR es aceptable; el backend multi-fuente queda fuera de alcance.
- [ ] Pencil: ¿página `.pen` dedicada al árbol, o compartir `taxon.pen`? Decidir antes del PR de frontend.
