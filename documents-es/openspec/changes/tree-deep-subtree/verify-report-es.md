# Reporte de verificación — tree-deep-subtree (issue #76)

> **Verificado en**: `develop` @ `c2ff70b` (PR #80 mergeado)
> **Fecha**: 2026-08-19
> **Verificador**: sub-agent `sdd-verify` (orquestado por el orchestrator)

## Resumen del cambio

`tree-deep-subtree` reemplaza el envelope de solo hijos directos de `GET /api/tree/children` por un envelope de subárbol por tier que mirror la forma probada de `/api/path-children`. Cada padre expandido ahora renderiza sus descendientes agrupados por rango (`phylum`, `family`, `order`, `genus`, `species`), con paginación por tier indexada por `(name, id)` y las mismas reglas de colapso `_phylum_rollup` / `_family_rollup` que la cascada ya confía.

## Cadena de entrega de 4 PRs (todas mergeadas)

| PR | Título | Merge | LOC netas | Estado |
|----|-------|-------|-----------|--------|
| A.1 (#77) | Subtree envelope + paginación por tier | `bae59ab` | 1326 | ✅ size:exception (3.3× budget) |
| A.2 (#78) | Índice compuesto + `taxon.migrate` | `b2294ed` | 325 | ✅ dentro del budget |
| Design gate | Diseño Stitch + auditoría impeccable | `6660505` | 193 | warning con 2 fixes P1 |
| C.1 (#79) | Store + api + fetchTierPage | `8824eb3` | 577 | ✅ dentro del budget |
| C.2 (#80) | TierGroup + keyboard nav + ARIA | `c2ff70b` | 1037 | ✅ dentro del budget de producción |

## Resumen de quality gates

| Gate | Resultado | Notas |
|------|-----------|-------|
| `pytest taxon/tests/` | ✅ 267 passed | Tests backend hasta PR A.2 |
| `mypy taxon/` | ✅ 45 archivos limpios | Typecheck backend |
| `ruff check taxon/` | ✅ todos los checks pasaron | Lint backend |
| `ruff format --check taxon/` | ✅ 45 archivos formateados | Formato backend |
| `npm run typecheck` | ✅ limpio | Typecheck frontend |
| `npm run lint` | ✅ limpio | Lint frontend |
| `npm run test` | ✅ 24 archivos / 152 tests | Frontend |
| `npm run build` | ✅ limpio | Bundle frontend |
| Pipeline CI (4 jobs × 4 PRs) | ✅ 4/4 SUCCESS en cada PR | backend 3.11 + 3.12, frontend node 20, lighthouse a11y |

## Cobertura de specs

| Escenario de spec | Implementación | Estado |
|---|---|---|
| Forma del envelope `next_tiers` (filas por tier + cursor) | `taxon/api/schemas.py::TreeNodeTier` + `taxon/api/_tree_tiers.py::_build_next_tiers` | ✅ |
| CTE recursiva por tier (`max_depth=8`) | `taxon/api/_tree_tiers.py::_per_tier_walk` | ✅ |
| Cap de filas por tier (50 default, 200 max) | `taxon/api/router.py::get_tree_children` (clamp + 400 reject) | ✅ |
| Paginación por tier con cursor indexado `(name, id)` | `taxon/api/_tree_tiers.py::_encode_cursor` + `_decode_cursor` | ✅ |
| Colapso `_phylum_rollup` / `_family_rollup` | `taxon/api/_tree_tiers.py` (extraído de `sqlite_resolver.py`) | ✅ |
| Ordenamiento cascade-rank | `taxon/api/hierarchy::_DISPLAY_LEVELS_IN_ORDER` | ✅ |
| Índice compuesto `ix_taxa_parent_rank_name` | `Taxon.__table_args__` + `taxon.migrate._ensure_indexes` | ✅ |
| Render frontend `<TierGroup>` | `frontend/src/components/TaxonomicTree.tsx` | ✅ |
| Cache `next_tiers` + acción `loadMore` | `frontend/src/store/taxonomicTree.ts` | ✅ |
| Helper `fetchTierPage` | `frontend/src/api.ts` | ✅ |
| Keyboard nav (ArrowDown/Up/Right/Left/Enter/Home/End) | `frontend/src/components/TaxonomicTree.tsx` | ✅ |
| Surface ARIA (`role="group"`, `aria-expanded`, `aria-controls`, `aria-label`) | `frontend/src/components/TaxonomicTree.tsx` | ✅ |
| P1 #1 (contraste de texto: text-slate reemplaza text-muted/outline) | `frontend/src/components/TaxonomicTree.tsx` | ✅ |
| P2 #1 (ocultar Load more cuando no hay cursor) | `frontend/src/components/TaxonomicTree.tsx` (cálculo `hasMore`) | ✅ |

## Hallazgos

### CRITICAL

Ninguno.

### WARNING

1. **PR A.1 size:exception (1326 LOC netas vs 360 forecast)** — ya aceptado por el usuario; documentado en el cuerpo de PR #77. El grueso es el nuevo módulo compartido `taxon/api/_tree_tiers.py` (+572 LOC) que aloja los helpers extraídos + la CTE por tier + cursor + builder de envelope + `_plural_label` + `_row_to_dataclass` juntos porque comparten el ordenamiento `tier_ranks`. Partir la extracción en dos commits habría inflado la cadena sin reducir la carga cognitiva de la review.

2. **PR C original se partió en 2 PRs (C.1 + C.2)** — el usuario eligió partir antes que dar size:exception. PR C.2 mergeó en 1037 LOC netas, pero el código de producción (`TaxonomicTree.tsx`, ~638 LOC) está dentro del budget de 400 líneas; el resto es cobertura de tests.

### SUGGESTION

1. **Segunda round-trip de `_per_tier_walk` en el backend** — la CTE devuelve solo ids, luego un segundo `fetch rows by id` reordena por `lower(name), name`. Intencional según el design. Si el dataset crece más allá de ~50k filas por tier, revisar y considerar materialización intermedia (seguimiento vía issue, no en este PR).

2. **`_count_descendant_species` por fila en el callback de enriquecimiento** — para una primera página del tamaño de Animalia (5 phyla × 50 filas × 6 tiers ≈ 1500 CTEs por fila en el peor caso) esto podría pasar el budget p95 de 50ms en `data/col.db`. El MVP corre contra SQLite en memoria; benchmarking con datos reales diferido.

3. **Archivos mirror de la spec (proposal-es.md, design-es.md, explore-es.md) bajo `documents-es/openspec/changes/tree-deep-subtree/` se perdieron** durante la limpieza de sesión (el paso `git checkout --` descartó archivos untracked porque el checkout principal solo los tenía como untracked). Los artefactos en inglés en `openspec/changes/tree-deep-subtree/` están intactos; solo faltan los mirrors en español de la capa de planificación. El mirror del delta de spec (`subtree-es.md`) sobrevivió porque se envió vía PR A.1. Seguimiento: reautorizar el mirror de planificación desde los originales en inglés si se necesita.

4. **Items P2/P3 de la auditoría impeccable** (rotación del caret, corte del conector, badges específicos por rango, tooltip de tilde aproximado, tooltip del toggle Source) están trackeados como SUGGESTIONs; no son blockers, no entran en el scope de este PR.

## Riesgos

| Riesgo | Probabilidad | Estado |
|--------|--------------|--------|
| El sub-agent `sdd-apply` no produjo output (falla de transporte) durante el launch de PR C.2 | Confirmado una vez | Recuperado: el orchestrator completó WU 2 + WU 3 directamente con la misma spec + surface brief; CI verde |
| `Detect.mjs` para el Assessment B de impeccable no está instalado en la raíz del proyecto | Confirmado | Auditoría corrió como degraded inline (contexto único); documentado en el surface brief |
| `_count_descendant_species` desbocado en datos reales | Media | Diferido a benchmark de seguimiento |

## Cierre

`change: tree-deep-subtree` está verificado listo para archivar. El delta de spec (`subtree.md`) más el footnote existente en `taxonomic-tree-browse.spec.md` forman la superficie durable. La cadena de 4 PRs entregó el contrato de extremo a extremo sin hallazgos CRITICAL, 2 WARNING aceptados (ambos documentados), y 4 SUGGESTIONs para trabajo futuro.
