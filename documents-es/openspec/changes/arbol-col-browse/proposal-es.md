# Propuesta: arbol-col-browse

## Intención

La cascada de 7 desplegables (`frontend/src/components/Cascade.tsx`) se rompe en `data/col.db` (importación CoL de 1,65 GB): no hay filas con rango `biota`, por lo que el resolvedor recorre una raíz sintetizada que ya no existe. Reemplazar la cascada lineal por un árbol jerárquico estilo CoL (`frontend/src/components/TaxonomicTree.tsx`) que carga hijos de forma diferida por `parent_id`, indenta por rango, renderiza filas con formato `rank: Nombre Autoría • N spp.` y expone "Find taxon" + `Source` + `Extant only`. Cierra el issue #67. La invariante de `breadcrumb-dinamico` se mantiene verbatim.

## Alcance

### Dentro del Alcance
- Backend: `GET /api/tree/children?parent_id={id}` + `GET /api/tree/search?q={q}`; nuevos `taxon/api/tree.py` + `taxon/api/search.py`; extensiones de esquema.
- Frontend: reemplazar `Cascade.tsx` + `Cascade.state.ts` por `TaxonomicTree.tsx` + `TaxonomicTree.state.ts` (caché Zustand indexada por `parent_id`).
- Frontend: `<input>` "Find taxon" con debounce de 200ms; checkboxes `Source` + `Extant only`; seguir emitiendo `path:change` y escribiendo `cascadePath`.
- `documents-es/openspec/changes/arbol-col-browse/proposal-es.md` según AGENTS.md §1.

### Fuera del Alcance
- `species-search-links`, `species-lookup`, `species-list-by-genus`, `inclusion-filters` (verbatim).
- Renombrado de `aria-label` en `Breadcrumb.tsx`; persistencia entre recargas; `species-folder-explorer`.
- Cableado del filtro `Source` (no-op CoL-only en el primer PR); materialización de `species_count` (lazy + proyección posterior).

## Capacidades

### Nuevas Capacidades
- `taxonomic-tree-browse`: árbol jerárquico estilo CoL con expansión lazy, filas con caret, indentación por rango, filas `rank: Nombre Autoría • N spp.`, filtros `Source` + `Extant only`, dispatch `path:change`.
- `taxon-tree-search`: búsqueda LIKE sobre `name`/`display_name` con relevancia rankeada (exacta > prefijo > subcadena), debounce 200ms, límite 8, contrato preparado para FTS.

### Capacidades Modificadas
- `taxonomy-hierarchy`: añadir los endpoints `GET /api/tree/children?parent_id={id}` y `GET /api/tree/search?q={q}`. La semántica existente del resolvedor de camino se mantiene verbatim.

## Enfoque

**Enfoque 3 (híbrido).** El backend añade los dos endpoints de árbol; el `/{path:path}/taxon-links` existente sigue alimentando el panel breadcrumb-links. El direccionamiento por `parent_id` evita el bug de `Biota`. `authorship` es una división derivada (`name` vs cola de `display_name`); `species_count` es una CTE recursiva sobre `taxa` (lazy `null` para nodos con >100k hijos directos, se rellena bajo demanda). El chip "extinct" de `<Toggles>` se pliega en el nuevo checkbox "Extant only". TDD estricto según `openspec/config.yaml strict_tdd: true`. El diseño Pencil + auditoría impeccable cierran la puerta del PR frontend según AGENTS.md §5.

## Áreas Afectadas

| Área | Impacto |
|------|---------|
| `frontend/src/components/Cascade.tsx` + `Cascade.state.ts` | Eliminado |
| `frontend/src/components/TaxonomicTree.tsx` + `TaxonomicTree.state.ts` | Nuevo |
| `frontend/src/App.tsx`, `api.ts`, `Toggles.tsx` | Modificado |
| `frontend/tests/` | Modificado (eliminar tests cascade; añadir tests tree) |
| `taxon/api/tree.py` + `taxon/api/search.py` | Nuevo |
| `taxon/api/schemas.py`, `router.py`, `sqlite_resolver.py` | Modificado (`list_tree_children`, sin síntesis Biota) |
| `taxon/tests/test_api_router_tree.py` | Nuevo |
| `openspec/specs/taxonomy-hierarchy/spec.md` | Modificado (MODIFIED Requirements) |
| `taxon.pen` | Modificado (diseño + auditoría impeccable) |
| `documents-es/openspec/changes/arbol-col-browse/proposal-es.md` | Nuevo (espejo en español) |

## Riesgos

| Riesgo | Prob | Mitigación |
|--------|------|------------|
| Coste de `species_count` en nodos profundos (Eukaryota → 2,4M especies) | Media | `null` lazy >100k hijos; caché en parent_fetch; proyección posterior |
| El filtro `Source` no tiene backend | Baja | enviar UI como no-op (CoL-only) en el primer PR |
| Eliminación del Cascade rompe un test con import cruzado | Baja | re-grepear `from.*Cascade` antes de eliminar |
| Pencil + impeccable + TDD = cadena de 3 puertas | Media | slice Pencil primero; PR bloqueado sin firma de diseño |
| PR frontend se acerca al presupuesto de 400 líneas | Media | pronóstico de PR encadenados en `sdd-tasks` (Pencil/visual, tests, App wiring) |
| Sin índice FTS sobre `name`/`display_name` a escala | Media | debounce 200ms + tope `LIMIT 8`; FTS en seguimiento |

## Plan de Rollback

Cada PR es aditivo: el PR backend añade los nuevos endpoints sin tocar el resolvedor de camino; el PR frontend añade el nuevo componente antes de eliminar `Cascade`. `git revert <merge-commit>` por PR deshace quirúrgicamente. Los 2 fallos CRITICAL en `cascadeDynamicTiers.test.tsx` se cierran de forma natural con la eliminación del Cascade — no se requiere un PR de arreglo separado.

## Dependencias

- `taxon.api.hierarchy.resolve_path_by_display_level` (verbatim, alimenta `taxon-links`).
- `docs/sources/templates.md` (verbatim, sustitución de 13 enlaces).
- Pase de diseño `taxon.pen` + auditoría `impeccable` según AGENTS.md §5.

## Criterios de Éxito

- [ ] `GET /api/tree/children?parent_id=2` devuelve `id`, `name`, `authorship`, `rank`, `has_children`, `species_count`, `parent_id`, flags marcadores.
- [ ] `GET /api/tree/search?q=Euk` devuelve ≤8 elementos rankeados exacta > prefijo > subcadena; debounce 200ms en cliente.
- [ ] `GET /api/tree/children?parent_id=2&include=extant_only` devuelve solo filas con `is_extinct=false`.
- [ ] El árbol explora `Eukaryota → Animalia → Chordata` sin el bug de `Biota`; las raíces son filas `domain` reales.
- [ ] El CustomEvent `path:change` se dispara en cada exploración; el panel breadcrumb-links renderiza 13 enlaces.
- [ ] Los tests de `breadcrumb-dinamico` siguen verdes; `cascadeDynamicTiers.test.tsx` eliminado.
- [ ] Suites `pytest` + `vitest` verdes; CI en `develop` verde.
- [ ] Entrada `/learn-es/YYYY-MM-DD-arbol-col-browse.md` creada tras la fusión.
- [ ] Pase de diseño Pencil + auditoría impecable fusionado antes de cualquier código frontend.
