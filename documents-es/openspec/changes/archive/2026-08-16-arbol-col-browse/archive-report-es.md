# Informe de Archivo: arbol-col-browse

**Cambio**: `arbol-col-browse`
**Cerrado**: 2026-08-16
**HEAD final**: `69d00e2` en `develop`
**PR fusionado**: #69 (commit `3fc2eb1`) — https://github.com/Sebailla/taxon/pull/69
**Cierra**: issue #67 — reemplazar la cascada de 7 desplegables por un árbol taxonómico jerárquico estilo CoL
**Modo de almacén de artefactos**: híbrido (sistema de archivos + observación Engram `sdd/arbol-col-browse/archive-report`)

## Resumen

El cambio `arbol-col-browse` reemplaza `frontend/src/components/Cascade.tsx` (cascada lineal de 7 desplegables que fallaba sobre `data/col.db` por la ausencia del rango `biota`) por un árbol taxonómico jerárquico estilo CoL (`TaxonomicTree`) que carga hijos perezosamente por `parent_id`, indenta por rango, renderiza filas con el formato `rango: Nombre Autoría • N spp.` y expone los filtros `Source` + `Extant only`. El camino explorado fluye a través del store Zustand `cascadePath` y un evento personalizado `path:change` para que el panel de enlaces de la ruta siga funcionando. El direccionamiento por `parent_id` esquiva el bug de síntesis de `Biota`.

## Lo que se envió

### Backend (PR #69, merge `3fc2eb1`)
- `taxon/api/tree.py` (nuevo): `list_tree_children(parent_id, include, limit, cursor)`, `search_taxon(q, limit, include_extinct)`, `_split_authorship(name, display_name)`, CTE recursivo para `species_count` con `null` perezoso >100k hijos directos.
- `taxon/api/router.py` (modificado): `GET /api/tree/children` y `GET /api/tree/search` registrados ANTES del catch-all `/{path:path}/taxon-links` (el test RED 1.9 cubre el orden de registro y el sombreado).
- `taxon/api/schemas.py` (modificado): `TreeNodeResponse`, `TreeChildrenResponse`, `TreeSearchResponse`, `TreeSearchHit` exportados desde `__all__`. `TreeNodeResponse` extiende `TaxonResponse` con `has_children`, `species_count`, `authorship` sin mutar la forma canónica.

### Frontend (PR #69, merge `3fc2eb1`)
- `frontend/src/components/TaxonomicTree.tsx` (nuevo, 618 LOC): filas con caret, cabecera `Find taxon` con combobox `aria-activedescendant`, casillas `Source` + `Extant only`, esqueletos `role="treeitem"`, estados vacío y de error izados fuera del host `role="tree"`.
- `frontend/src/store/taxonomicTree.ts` (nuevo): store Zustand con `childrenByParentId: Map`, `expandedIds: Set`, `rootIds` y acciones `loadRoots`, `ensureChildren`, `toggleExpand`, `revealNode`, `setIncludeExtinct`, `clear`.
- `frontend/src/api.ts` (modificado): `fetchTreeNode(parentId, init?)`, `fetchTreeSearch(q, init?)`, `createDebouncedSearch` con debounce de 200ms.
- `frontend/src/App.tsx` (modificado): monta `<TaxonomicTree>` en el slot de Cascade; los efectos de breadcrumb-links y el listener `path:change` se conservan verbatim.
- `frontend/src/components/Breadcrumb.tsx` (modificado): `aria-label` se conserva verbatim como `Cascade path breadcrumb` (línea 26).

### Eliminaciones (PR #69, merge `3fc2eb1`)
- `frontend/src/components/Cascade.tsx`
- `frontend/src/components/Cascade.state.ts`
- 6 archivos de prueba de Cascade (cascadeDynamicTiers, Cascade.pathAware, Cascade.ui, cascadeRoots, cascadeSubphylum, Cascade.test.tsx.legacy).

### Pruebas (estado final, desde el merge de PR #69 y la CI en `69d00e2`)
- Backend: 192/192 pytest verde.
- Frontend: 99/99 vitest verde.
- TypeScript: `tsc -b` verde.
- Vite: build verde.
- Lint: `ruff format` + `ruff check` verde.
- Lighthouse a11y verde.
- 4 puertas de CI verdes (backend py3.11, backend py3.12, frontend node20, lighthouse a11y).

### Entrada en learn-es
- `learn-es/2026-08-16-arbol-col-browse-pr3-drift-fixes.md` (commiteado en `69d00e2`) con espejo en español en `documents-es/learn-es/2026-08-16-arbol-col-browse-pr3-drift-fixes.md` (conforme a AGENTS.md §1).

## Especificaciones sincronizadas (delta → principal)

| Dominio | Acción | Detalles |
|---------|--------|----------|
| `taxonomy-hierarchy` | MODIFIED + ADDED | MODIFIED: `Hierarchy Browse by Path`, `Stable Response Shape and Ordering`. ADDED: `Parent-id Children Endpoint`, `Tree Search Endpoint`, `species_count Lazy Semantics`, `Path-Resolver Endpoints Stay Verbatim`. Las `## ADDED Requirements` existentes (Permanent Breadcrumb, Clickable Breadcrumb Segment) se conservan verbatim. |
| `taxonomic-tree-browse` | Creada | Delta copiado verbatim vía `cp` de shell + readback `diff -r` byte-idéntico. |
| `taxon-tree-search` | Creada | Delta copiado verbatim vía `cp` de shell + readback `diff -r` byte-idéntico. |

### Fuente de verdad actualizada
- `openspec/specs/taxonomy-hierarchy/spec.md`
- `openspec/specs/taxonomic-tree-browse/spec.md` (nuevo)
- `openspec/specs/taxon-tree-search/spec.md` (nuevo)

## Reconciliación de casillas obsoletas (conforme a la excepción de la skill)

El `openspec/changes/arbol-col-browse/tasks.md` persistido llegó al archivo con 18 tareas sin marcar (`- [ ]`) porque el sub-agente `sdd-apply` previo falló con `sdd_task_result_empty` (fallo de transporte) y nunca persistió su progreso. Conforme a la excepción de la skill `sdd-archive` para casillas obsoletas (que requiere autorización del usuario + evidencia concreta desde `apply-progress`/`verify-report`/estado del repositorio), el usuario autorizó la reconciliación respaldada por:

- **Evidencia del repositorio**: archivos de backend (`taxon/api/tree.py`, `router.py`/`schemas.py` modificados) presentes; archivos de frontend (`TaxonomicTree.tsx` 618 LOC, store `taxonomicTree.ts`, 5 archivos de prueba) presentes; `aria-label` de `Breadcrumb.tsx` verbatim en línea 26; `Cascade.tsx` + `Cascade.state.ts` + 6 archivos de prueba de Cascade ausentes; entrada de learn-es + espejo en español presentes.
- **Evidencia del PR**: PR #69 fusionado a `develop` en `3fc2eb1` con 4 puertas de CI verdes; el cuerpo del commit de merge documenta la desviación por fallo de transporte del sub-agente que este cambio recuperó.
- **Hechos de estado final**: 192 pytest + 99 vitest + tsc-b + ruff + 4 puertas de CI verdes.

**Aplazamiento de Fase 2**: 4 tareas (2.1–2.4, diseño Pencil + auditoría impecable) marcadas como `[x] [DEFERRED]` con justificación verbatim: Pencil MCP estuvo deshabilitado en la sesión de implementación, por lo que el brief prescriptivo de superficie se capturó como `docs/design/taxonomic-tree-browse.md` (784 líneas, especificación de traducción línea por línea para el implementador) en lugar de una página `.pen`. Un issue de seguimiento podrá rehacer la página `.pen` de Pencil en una rebanada futura. Este aplazamiento también se registra verbatim en la nota de reconciliación añadida al final de `tasks.md`.

**Reconciliación de Fase 3**: 14 tareas (3.1–3.14) marcadas como `[x]` basándose en evidencia del repositorio (existencia de archivos + PR fusionado) y la autorización del usuario para la reconciliación de casillas obsoletas. Evidencia:
- 3.1 RED — `frontend/tests/api.treeChildren.test.ts` existe (15 pruebas)
- 3.2 GREEN — `fetchTreeNode`, `fetchTreeSearch` en `frontend/src/api.ts`
- 3.3 RED — `frontend/tests/api.treeSearch.test.ts` existe (5 pruebas)
- 3.4 GREEN — `createDebouncedSearch` en `frontend/src/api.ts`
- 3.5 RED — `frontend/tests/TaxonomicTree.test.tsx` existe (11 pruebas incluyendo los escenarios de recuperación de desviación)
- 3.6 GREEN — `frontend/src/store/taxonomicTree.ts` contiene `loadRoots`, `ensureChildren`, `toggleExpand`, `revealNode`, `setIncludeExtinct`
- 3.7 GREEN — `frontend/src/components/TaxonomicTree.tsx` (618 LOC)
- 3.8 GREEN — `frontend/src/App.tsx` monta `<TaxonomicTree>` en el slot de Cascade
- 3.9 GREEN — `aria-label` de `Breadcrumb.tsx` verbatim como `Cascade path breadcrumb`
- 3.10 REFACTOR — `Cascade.tsx` + `Cascade.state.ts` + 6 archivos de prueba de Cascade eliminados
- 3.11 GREEN — `frontend/tests/App.taxonLinks.test.tsx` actualizado (2 pruebas)
- 3.12 RED — `frontend/tests/TaxonomicTree.a11y.test.tsx` existe (1 prueba axe-core)
- 3.13 GREEN — arreglos de a11y: `aria-activedescendant` en el combobox de búsqueda, esqueletos `role="treeitem"`, vacío + error izados fuera del host `role="tree"`
- 3.14 Post-merge — entrada de learn-es commiteada en `69d00e2` con espejo en español

**Estado final de tareas**: 28/28 tareas de implementación marcadas `[x]`, 0 sin marcar. Nota de reconciliación añadida al final de `tasks.md`.

## Narrativa de la desviación

El cuerpo del PR #69 documenta que el sub-agente `sdd-apply` previo falló con `sdd_task_result_empty` (fallo de transporte) y nunca persistió el progreso de sus casillas. El cambio capturó los 14 pasos de implementación de la Fase 3 + pruebas + arreglos de a11y + entrada de learn-es en los commits de recuperación de desviación que componen el PR #69, pero el `tasks.md` persistido siguió mostrando `- [ ]` porque la fase apply nunca cerró. Este archivo reconcilió las casillas obsoletas conforme a la autorización del usuario, restaurando la trazabilidad de auditoría para que coincida con el estado final real.

## Contenido del archivo

- proposal.md ✅
- exploration.md ✅
- specs/ ✅ (3 especificaciones delta — ya fusionadas en las especificaciones principales arriba)
- design.md ✅
- tasks.md ✅ (28/28 tareas marcadas como completas; nota de reconciliación añadida)
- archive-report.md ✅ (este archivo; solo aditivo, excluido del readback de snapshot/diff)

## Evidencia del contrato de copia mecánica

- Sincronización de specs (`taxonomic-tree-browse`, `taxon-tree-search`): salida vacía de `diff -r` entre origen y destino para ambos archivos. Copia mecánica byte-idéntica.
- Movimiento al archivo (`arbol-col-browse` → `archive/2026-08-16-arbol-col-browse`): salida vacía de `diff -r` entre el snapshot previo al movimiento y la carpeta archivada. Movimiento byte-idéntico vía `git mv`.
- Fusión de `taxonomy-hierarchy/spec.md`: ediciones quirúrgicas in-place (reemplazo del requisito MODIFIED + anexado ADDED) conservando verbatim la sección ADDED de breadcrumb existente.

## Jerarquía de autoridad de estado final aplicada

Conforme a la jerarquía de Autoridad de Estado Final de `sdd-archive`:
- Autoridad nativa de revisión: no aplicable (interruptor de RD apagado; sin `reviewGate` que validar; proceder bajo política ordinaria del repositorio).
- Artefacto de tareas persistido: reconciliado conforme a la excepción de la skill; estado final 28/28 completas.
- Hechos de estado final explícitos del orquestador: 192/192 pytest, 99/99 vitest, tsc-b verde, ruff format + check verde, 4 puertas de CI verdes, PR #69 fusionado en `3fc2eb1`, learn-es en `69d00e2`.
- Snapshots intermedios (`verify-report`, `apply-progress`): no se confiaron para afirmaciones de estado final; sus snapshots intermedios fueron superados por los hechos de estado final anteriores cuando de otro modo habrían discrepado.

## Riesgos

- El diseño Pencil + auditoría impecable de la Fase 2 se aplazó (no existe página `.pen` para `taxonomic-tree-browse`). El diseño se capturó prescriptivamente en `docs/design/taxonomic-tree-browse.md` y se envió. Un issue de seguimiento podrá rehacer la página `.pen` de Pencil en una rebanada futura si el equipo desea un artefacto visual para que `impeccable` lo audite.

## Ciclo SDD completo

El cambio fue completamente planificado, implementado, verificado (4 puertas de CI verdes) y archivado. Listo para el siguiente cambio.
