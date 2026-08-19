# Reporte de Verificación: descendant-counts-projection

## Estado: aprobado

La implementación coincide con la spec, el diseño y las tasks. CI verde en PR #86 (backend py3.11, backend py3.12, frontend, lighthouse). Los 285 casos pytest pasan localmente; 1 se salta (`test_default_used_when_no_argument_or_env` del archivo no relacionado `test_api_database_url.py` — se salta porque `data/col.db` no está en disco en el entorno de desarrollo).

## Conformidad con la Spec

### `descendant-counts-projection` (spec nueva)

| Requisito | Escenario | Conformidad |
|-----------|-----------|-------------|
| Schema | Una DB fresca gana la tabla al hacer `apply` | PASA — `test_apply_creates_workspace_and_projection_tables` verifica que `taxon_descendant_counts` existe tras `apply` |
| Materialización en primera lectura | Cache hit devuelve en O(1) | PASA — `test_lookup_one_returns_cached_value_after_write` + test de `_count_descendant_species` actualizado |
| Regla de población | El predicado de umbral lee `SPECIES_COUNT_LAZY_NULL_THRESHOLD` | PASA — `_projected_parent_ids` importa la constante |
| Rebuild acotado por SLO | Rebuild sobre presupuesto devuelve None, no se escribe fila | PASA — `test_lazy_null_helper_returns_none_when_rebuild_exceeds_budget` usa `budget_seconds=0.0` para forzar la rama |
| Rebuild por `import_data` | Rebuild tras importación | PASA — `_rebuild_descendant_counts_projection` corre después de `_populate_species_paths` |
| `apply-projection` como escape manual | El CLI puebla filas | PASA — `test_apply_projection_populates_rows_on_bare_engine` ejercita el CLI de extremo a extremo |
| Schema aditiva | Las DBs legacy sin la tabla siguen funcionando | PASA — `lookup_one`/`lookup_many`/`_table_exists` se protegen ante tabla ausente |

### `taxonomic-tree-browse` (delta)

| Cambio | Escenario | Conformidad |
|--------|-----------|-------------|
| Requisito MODIFICADO: el lazy-expand ahora consulta la projection antes del threshold guard | Cache hit devuelve sin CTE | PASA — `test_species_count_triggers_rebuild_when_above_threshold` |
| Requisito AÑADIDO: el cache hit devuelve `species_count` desde la tabla | Cache miss + padre sobre el umbral dispara rebuild | PASA — `test_species_count_triggers_rebuild_when_above_threshold` |
| Requisito AÑADIDO: el cache hit se salta el threshold guard | Cache hit bajo el umbral devuelve el valor cacheado | PASA — mismo test |
| Requisito ELIMINADO: lazy-null incondicional sobre el umbral | — | ELIMINADO en diseño + implementación; documentado en `apply-progress.md` |

## Conformidad con el Diseño

Sin desviaciones respecto a `design.md`. Cada decisión arquitectónica del diseño aterrizó:

- Helper de registro `register_display_level` (`design.md:387-403`)
- Pre-check de cache `lookup_one` en `_count_descendant_species` (`design.md:296-312`)
- Merge de cache `lookup_many` en `_batch_species_counts` (`design.md:326-342`)
- SLO guard mediante `REBUILD_BUDGET_SECONDS = 1.0` (`design.md:217-219`)
- Escape `budget_seconds=None` para callers offline (`design.md:282-287`)
- CLI `apply-projection` con `--threshold` y `--budget-seconds` (`design.md:94`)
- Rebuild post-import vía `import_data` (`design.md:282-287`)

## Riesgos cerrados

| Riesgo | Mitigación | Estado |
|--------|-----------|--------|
| Gap de registro (`design.md:402-403`) | `test_apply_projection_populates_rows_on_bare_engine` | CERRADO |
| Cambio semántico de `_count_descendant_species` | `test_species_count_lazy_null.py` actualizado al nuevo contrato | CERRADO |
| Asunción de forma de query en `_batch_species_counts` (riesgo 3 de tasks.md) | `lookup_many` corre antes del seed union; los ids cacheados se excluyen | CERRADO (el diseño pineó la CTE byte-idéntica) |

## Hallazgos

- **CRÍTICO:** ninguno.
- **ADVERTENCIA:** ninguna.
- **SUGERENCIA:** la asimetría de umbral pre-existente (100k vs 1M) está documentada como fuera de alcance y merece una propuesta de seguimiento en un cambio futuro.
- **SUGERENCIA:** el ciclo red-green del test `register_display_level` de `_count_descendant_species` queda cubierto tanto por `test_descendant_counts_projection.py` como por `test_apply_projection_populates_rows_on_bare_engine`; conviene consolidar si el segundo test crece.

## Aceptación

| Criterio | Cumplido |
|----------|----------|
| Migraciones de schema aplicadas | SÍ |
| Todos los tests pasan | SÍ (285/285, 1 saltado) |
| Lint limpio | SÍ |
| Type-check limpio | SÍ |
| Documentación / learn-es / artefactos SDD completos | SÍ |
| Compatibilidad hacia atrás con DBs legacy | SÍ (camino de tabla ausente probado) |
| PR revisado y mergeado | SÍ (#86) |