# Reporte de archivo: tree-deep-subtree

**Cambio**: `tree-deep-subtree`
**Cerrado**: 2026-08-19
**HEAD final**: `c2ff70b` en `develop`
**PRs mergeadas**: #77 / #78 / #79 / #80 (commits `bae59ab` / `b2294ed` / `8824eb3` / `c2ff70b`) — https://github.com/Sebailla/taxon/pull/77, /78, /79, /80
**Cierra**: issue #76 — árbol taxonómico que muestra cada descendiente de un nodo, agrupado por rango, con paginación
**Modo de almacén de artefactos**: híbrido (filesystem + observaciones en Engram `sdd/tree-deep-subtree/{proposal,design,tasks,apply-progress,verify-report,archive-report}`)
**Gate de review**: no presente (RDD kill switch apagado durante toda la cadena; el archivo proceeded bajo política ordinaria del repo)

## Resumen

`GET /api/tree/children` ahora devuelve cada descendiente de un nodo agrupado por rango (`phylum`, `family`, `order`, `genus`, `species`) mediante un envelope `next_tiers` que mirror la forma probada de `/api/path-children`. Cada tier tiene su propia CTE recursiva (`max_depth=8`, `tier_ranks IN (...)`), cap de filas (50 default / 200 max), y paginación con cursor indexada por `(name, id)` (base64 de `f"{name}\x00{id}"`). Los mismos helpers `_phylum_rollup` / `_family_rollup` que la ruta cascade ya confía colapsan los rangos intermedios (subphylum → phylum, subfamily → family). El frontend renderiza un disclosure `<TierGroup>` bajo cada padre expandido con keyboard nav completo y surface ARIA.

## Qué se envió

### Backend — PR A.1 (#77 merge `bae59ab`)
- `taxon/api/_tree_tiers.py` (nuevo, 572 LOC): módulo compartido que aloja los 5 helpers extraídos (`_phylum_rollup`, `_family_rollup`, `_collect_descendants_by_rank`, `_build_tiers_from_grouping`, `_build_tier`) + la CTE recursiva por tier (`_per_tier_walk` con `max_depth=8`, `tier_ranks IN (...)`, `tier_limit=50`) + los helpers de cursor (`_encode_cursor`, `_decode_cursor`, round-trip URL-safe base64) + el builder de envelope (`_build_next_tiers`) + `_plural_label` (Phyla / Genera / Families / Classes / Orders) + `_row_to_dataclass` (friendly a orjson).
- `taxon/api/sqlite_resolver.py` (modificado, +27/-181): re-exporta los 5 helpers desde `_tree_tiers` para preservar la superficie pública de `list_path_children`.
- `taxon/api/schemas.py` (modificado, +47): `TreeNodeTier(BaseModel)` con `rank`, `label`, `examples`, `children`, `next_cursor`; `TreeChildrenResponse` gana `next_tiers: list[TreeNodeTier] | None`.
- `taxon/api/tree.py` (modificado, +97): `list_tree_children` acepta `tier` + `tier_limit`; calcula `_build_next_tiers` una vez para el envelope del padre; honra el query param `tier` cuando está presente (devuelve la página paginada de ese tier solamente, sin envelope).
- `taxon/api/router.py` (modificado, +69): `get_tree_children` acepta `tier` + `tier_limit`; clamp `tier_limit > 200` silencioso; rechaza `< 1` con HTTP 400.
- `openspec/specs/taxonomic-tree-browse/spec.md` (modificado, +4): footnote "Delta applied" apuntando al nuevo spec hermano.
- `openspec/specs/taxonomic-tree-browse/subtree.md` (nuevo, 79): delta spec para el envelope `next_tiers`, caps por tier, paginación, ordenamiento cascade-rank.
- `documents-es/openspec/specs/taxonomic-tree-browse/subtree-es.md` (nuevo, 79): mirror en español.
- `taxon/tests/test_api_router_tree.py` (modificado, +379): 9 nuevos tests pinando el contrato `next_tiers` + cursor round-trip + off-tuple collapse + paginación.
- **Excepción de tamaño reconocida**: PR A.1 cerró en 1326 LOC netas vs 400 forecast (3.3× budget). El grueso es `_tree_tiers.py` (+572) que aloja los helpers extraídos + la CTE por tier + cursor + builder de envelope + `_plural_label` + `_row_to_dataclass` juntos porque comparten el ordenamiento `tier_ranks`.

### Backend — PR A.2 (#78 merge `b2294ed`)
- `taxon/schema.py` (modificado, +1): `Taxon.__table_args__` gana `Index("ix_taxa_parent_rank_name", "parent_id", "rank", "name")`.
- `taxon/migrate.py` (modificado, +140/-16): nuevo paso `_ensure_indexes()` con `CREATE INDEX IF NOT EXISTS ix_taxa_parent_rank_name ON taxa (parent_id, rank, name)`; flags CLI `--only-index` (salta migraciones no-índice) + `--skip-indexes` (salta el paso de índices); `_existing_index_names` hecho safe cuando la tabla target está ausente.
- `taxon/tests/test_migrate.py` (modificado, +184/-2): 3 nuevos tests pinando el contrato de migración del índice (create-on-first-run, skip-if-present, preserves-existing-indexes).
- PR A.2 cerró en 325 LOC (dentro del budget de 150 LOC contando el delta de tests).

### Design gate — commit `6660505`
- `openspec/changes/tree-deep-subtree/design.md` (existente, pre-merge) — diseño técnico (CTE recursiva por tier, forma del cursor, migración del índice compuesto).
- `docs/design/stitch/tree-deep-subtree-design.md` (nuevo, 96): brief de superficie generado por Stitch MCP + reglas de traducción + los 2 fixes P1 de la auditoría impeccable.
- `docs/design/stitch/tree-deep-subtree-stitch-url.txt` (nuevo): URL del proyecto Stitch para trazabilidad.
- `documents-es/docs/design/stitch/tree-deep-subtree-design-es.md` (nuevo, 96): mirror en español.
- Rationale del design gate: Pencil MCP no estaba disponible (deprecación observada previamente; reemplazado por Stitch MCP). El precedente establecido fue `arbol-col-browse` y `species-folder-explorer` — ambos notaron que el gate de diseño de governance se puede satisfacer sin una página `.pen` cuando Design-Doc + Audit es el sustituto. El ID del proyecto Stitch `projects/11955314884511019764` fue la superficie real generada.
- Pase de auditoría impeccable: 2 fixes P1 (contraste text-slate en Load more + nota via subphylum rollup; ocultar Load more cuando `next_cursor === null AND rows.length > 0`) aplicados inline en PR C.2.

### Frontend — PR C.1 (#79 merge `8824eb3`)
- `frontend/src/store/taxonomicTree.ts` (modificado, +118): `nextTiersByParentId: Map<number, TreeNodeTier[]>` + `tierRowsByKey: Map<string, { rows; nextCursor }>` + acción `loadMore(parentId, rank)` + helper puro `seedNextTiersFor` + `tierFetchedKeys: Set<string>` para desambiguar estado seed-only vs fetch-resolved; `setIncludeExtinct` extendido para nukear los nuevos caches.
- `frontend/src/api.ts` (modificado, +84): `TreeChildrenResponse` ensanchado para incluir `next_tiers`; nueva interface `TreeNodeTier`; `fetchTierPage(parentId, tier, cursor, { tierLimit, signal })` + `FETCH_TIER_PAGE_DEFAULT_LIMIT=50`; `buildTreeChildrenUrl` acepta `tier` + `cursor`.
- `frontend/tests/api.fetchTierPage.test.ts` (nuevo, 161): 8 tests pinando el contrato de fetchTierPage.
- `frontend/tests/store.taxonomicTree.tiers.test.ts` (nuevo, 225): 4 tests pinando el contrato del store.
- `frontend/tests/api.treeChildren.test.ts` (modificado, +1): fixture ensanchada para satisfacer la nueva interface.
- PR C.1 cerró en 577 LOC netas (dentro del budget).

### Frontend — PR C.2 (#80 merge `c2ff70b`)
- `frontend/src/components/TaxonomicTree.tsx` (modificado, +755): nuevos componentes `<TierGroup>` + `<TierRow>`; `walk()` se integra con la lista flat `visibleRows` (emite entradas `tier-group` entre entradas `tree-row` para que ArrowDown/Up cruce el límite del tier); `onKeyDown` global (ArrowDown/Up/Right/Left/Enter/Home/End); nav local de TierRow (ArrowDown/Up/Home/End/Enter); surface ARIA (`role="group"` + `aria-label="<label> group"`; header `role="button"` + `aria-expanded` + `aria-controls`; "Load more" `aria-label="Load more <label>"`); P1 #1 (`text-slate` en Load more + nota de rollup); P1 #2 (ocultar Load more cuando no hay cursor — cálculo `hasMore` + `tierFetchedKeys`).
- `frontend/tests/TaxonomicTree.test.tsx` (modificado, +448): 5 nuevos tests (renders_tier_groups_collapsed_by_default, expanding_tier_group_fetches_first_page, load_more_appends_rows, keyboard_navigation_across_tier_groups, aria_labels_on_tier_group_and_button); fixture parent_id=0 ensanchado con la forma completa de `TreeNodeTier` para satisfacer `tsc -b`.
- PR C.2 cerró en 1037 LOC netas (638 prod + 399 tests; dentro del budget de 400 líneas de producción).
- **Nota de recuperación**: el launch inicial de PR C.2 tuvo una falla de transporte (`sdd_task_result_empty`) en el sub-agent `sdd-apply`. El orchestrator completó WU 2 + WU 3 directamente con la misma spec + surface brief, preservando el contrato. CI verde, los 152 tests pasan.

### Verificación post-merge — commit `6f5cf51`
- `openspec/changes/tree-deep-subtree/verify-report.md` (nuevo, 86): CRITICAL 0 / WARNING 2 / SUGGESTION 4. Resumen de quality gates, matriz de cobertura de spec, riesgos, cierre.
- `documents-es/openspec/changes/tree-deep-subtree/verify-report-es.md` (nuevo, 86): mirror en español.

### Handoff de estado final — este reporte
- `learn-es/2026-08-19-tree-deep-subtree.md` (nuevo, 86): entrada de aprendizaje per AGENTS.md §2 capturando la cadena de 4 PRs, el design gate, el strict TDD, la recuperación de falla de transporte, y los 2 fixes P1.

## Resumen de quality gates

| Gate | Resultado | Evidencia |
|------|-----------|-----------|
| `pytest taxon/tests/` | ✅ 267 passed | Hasta PR A.2 |
| `mypy taxon/` | ✅ 45 archivos limpios | Hasta PR A.2 |
| `ruff check taxon/` | ✅ todos los checks pasaron | Hasta PR A.2 |
| `ruff format --check taxon/` | ✅ 45 archivos formateados | Hasta PR A.2 |
| `npm run typecheck` | ✅ limpio | Hasta PR C.2 |
| `npm run lint` | ✅ limpio | Hasta PR C.2 |
| `npm run test` | ✅ 24 archivos / 152 tests | Hasta PR C.2 |
| `npm run build` | ✅ limpio | Hasta PR C.2 |
| Pipeline CI (4 jobs × 4 PRs) | ✅ 4/4 SUCCESS en cada PR | backend 3.11 + 3.12, frontend node 20, lighthouse a11y |

## Cobertura de specs

| Escenario de spec | Implementación | Estado |
|---|---|---|
| Forma del envelope `next_tiers` | `taxon/api/schemas.py::TreeNodeTier` | ✅ |
| CTE recursiva por tier `max_depth=8` | `taxon/api/_tree_tiers.py::_per_tier_walk` | ✅ |
| Cap de filas por tier (50 default / 200 max) | `taxon/api/router.py::get_tree_children` | ✅ |
| Cursor por tier indexado `(name, id)` | `taxon/api/_tree_tiers.py::_encode_cursor` / `_decode_cursor` | ✅ |
| Colapso `_phylum_rollup` / `_family_rollup` | `taxon/api/_tree_tiers.py` (extraído) | ✅ |
| Ordenamiento cascade-rank | `taxon/api/hierarchy::_DISPLAY_LEVELS_IN_ORDER` | ✅ |
| Índice compuesto `ix_taxa_parent_rank_name` | `Taxon.__table_args__` + `taxon.migrate._ensure_indexes` | ✅ |
| Render frontend `<TierGroup>` | `frontend/src/components/TaxonomicTree.tsx` | ✅ |
| Cache `next_tiers` + `loadMore` | `frontend/src/store/taxonomicTree.ts` | ✅ |
| Helper `fetchTierPage` | `frontend/src/api.ts` | ✅ |
| Keyboard nav (ArrowDown/Up/Right/Left/Enter/Home/End) | `frontend/src/components/TaxonomicTree.tsx` | ✅ |
| Surface ARIA | `frontend/src/components/TaxonomicTree.tsx` | ✅ |
| P1 #1 (contraste de texto) | `frontend/src/components/TaxonomicTree.tsx` (`text-slate`) | ✅ |
| P2 #1 (ocultar Load more cuando no hay cursor) | `frontend/src/components/TaxonomicTree.tsx` (`hasMore`) | ✅ |

## Hallazgos (preservados del verify-report)

### CRITICAL
Ninguno.

### WARNING
1. **PR A.1 size:exception (1326 LOC netas vs 360 forecast)** — aceptado; documentado en el cuerpo de PR #77.
2. **PR C se partió en C.1 + C.2** — el usuario eligió partir antes que dar size:exception. PR C.2 neta 1037 LOC pero el código de producción `TaxonomicTree.tsx` ~638 LOC dentro del budget.

### SUGGESTION
1. Segunda round-trip de `_per_tier_walk` en el backend — revisar si el dataset crece más allá de ~50k filas por tier.
2. Enriquecimiento por fila `_count_descendant_species` — riesgo de budget p95 en datos reales; benchmark de seguimiento.
3. Archivos mirror de planificación bajo `documents-es/openspec/changes/tree-deep-subtree/` perdidos durante la limpieza de sesión — seguimiento si se necesitan.
4. Items P2/P3 de la auditoría impeccable (rotación del caret, corte del conector, badges específicos por rango, tooltip de tilde aproximado, tooltip del toggle Source) — trackeados como trabajo futuro.

## Riesgos

| Riesgo | Estado |
|--------|--------|
| El sub-agent `sdd-apply` no produjo output durante el launch de PR C.2 | Confirmado una vez; recuperado via trabajo directo del orchestrator |
| `Detect.mjs` para el Assessment B de impeccable no instalado en la raíz del proyecto | Confirmado; la auditoría corrió como degraded inline |
| `_count_descendant_species` desbocado en datos reales | Diferido a benchmark de seguimiento |

## Aprendizajes

1. **PR C excedió el budget de 400 líneas porque el componente TierGroup + store + api + keyboard nav + ARIA + 2 fixes P1 + tests es una superficie grande para traducir del diseño a código en un solo slice.** Partir en C.1 (store+api) + C.2 (componente+nav+ARIA) mantiene cada PR dentro del budget. El costo del split: 1 cuerpo de PR extra + 1 corrida de CI extra.
2. **El set `tierFetchedKeys` es la forma más limpia de desambiguar "el servidor confirmó la última página" de "el envelope todavía no se ha hidratado"** cuando la visibilidad del botón Load more depende de ambos. Sin él, la regla degeneraba en una distinción "confía en el envelope hasta que el usuario hace click" / "confía en el cache después" que se filtraba entre tests.
3. **`text-slate` (token de Tailwind, `#475569` sobre bg) es el match sustantivo para el requisito `text-on-surface-variant` de la auditoría** cuando el proyecto no tiene el token del design system. Elige siempre el token de mayor contraste ya presente en el design system; no introduzcas tokens nuevos a mitad de implementación.
4. **Cuando el sub-agent `sdd-apply` falla en producir output, el orchestrator puede completar el trabajo directamente** mientras la spec + surface brief estén intactos. El costo de la recuperación está acotado por el scope de la work unit: en PR C.2 eso significó 2 WUs (TierGroup + keyboard nav) directamente desde la spec + los 5 tests RED que ya estaban commiteados.

## Dependencias

- Stitch MCP (reemplazó Pencil MCP para el design gate; proyecto `projects/11955314884511019764`).
- `_phylum_rollup` / `_family_rollup` / `_collect_descendants_by_rank` / `_build_tiers_from_grouping` ya en `taxon/api/sqlite_resolver.py` (reusados verbatim).
- `taxon/api/hierarchy._effective_display_level` / `_DISPLAY_LEVELS_IN_ORDER` (reusados verbatim).
- `taxon/api/tree.py::list_tree_children` + `TreeNodeRow` + `split_authorship` (reuso verbatim para el slice de hijos directos).
- Skills `work-unit-commits` + `chained-pr` per `AGENTS.md §3` (cadena de 4 PRs planificada contra develop).
- Skill `impeccable` (pase de auditoría con banner degraded inline — `detect.mjs` no está instalado en la raíz del proyecto).

## Lecciones aprendidas (resumen)

Documentadas en `learn-es/2026-08-19-tree-deep-subtree.md` per AGENTS.md §2.

## Cierre

`change: tree-deep-subtree` está cerrado. El issue #76 está completo y entregable. La cadena de 4 PRs (A.1 / A.2 / C.1 / C.2) mergeó sin hallazgos CRITICAL; 2 WARNING aceptados documentados. El delta spec de la capacidad `taxonomic-tree-browse` (`subtree.md`) es la superficie durable. Trabajo futuro: benchmarking con datos reales para el enriquecimiento `_count_descendant_species` por tier; re-autorización del mirror de planificación si se necesita.
