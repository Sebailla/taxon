# Projection materializada de `species_count` para taxones sobre el umbral

## What

Se añade la tabla `taxon_descendant_counts(taxon_id PK, species_count, total_count, computed_at)` que cachea el conteo de especies descendientes para todo taxón cuyo fanout de hijos directos supera `SPECIES_COUNT_LAZY_NULL_THRESHOLD` (1M). Antes del cambio, padres como `Animalia` (22,711 descendientes / 950k especies) devolvían `species_count=null` porque la CTE recursiva reventaba el SLO por-request. Después, la primera request dispara un rebuild síncrono (limitado por el SLO), se cachea el resultado, y las requests siguientes leen la tabla en O(1) — sin CTE, sin threshold guard.

## How

- Nueva clase ORM `TaxonDescendantCount` en `taxon/schema.py`, mapeada a `taxon_descendant_counts`. PK es `taxon_id` (FK a `taxa.id`); la FK hace que un re-import que borre `taxa` cascade las projection rows sin dejar basura.
- Nuevo módulo `taxon/api/projections.py` con la superficie: `register_display_level`, `lookup_one`, `lookup_many`, `materialize_for_parent`, `materialize_all`, `_table_exists`, `_projected_parent_ids`. `REBUILD_BUDGET_SECONDS = 1.0` por defecto. Los offline callers (`apply-projection`, `import_data`) pasan `budget_seconds=None` para saltarse el SLO guard.
- `_count_descendant_species` en `taxon/api/tree.py` consulta `lookup_one` antes de caer al threshold guard. Cache hit devuelve `species_count` en O(1). Cache miss + parent sobre el umbral dispara `materialize_for_parent` síncronamente.
- `_batch_species_counts` en `taxon/api/_tree_tiers.py` consulta `lookup_many` y excluye los parents cacheados del seed union de la CTE. Las filas cacheadas ganan estructuralmente — la CTE no las alcanza.
- `taxon/migrate.py` amplía `_run_apply` con `PROJECTION_TABLES` (union de `WORKSPACE_TABLES + PROJECTION_TABLES`) y añade el subcommand `apply-projection --threshold N --budget-seconds S`.
- `taxon/import_data.py` engancha `_rebuild_descendant_counts_projection` al final de `import_dataset`, después de `_populate_species_paths`.
- `taxon/api/projections.register_display_level` cierra el gap de registro del SQLite user function `taxonomy_display_level` en los engines bare de `taxon.migrate` e `taxon.import_data` (que no heredan el listener del FastAPI factory).

## Where

- `taxon/schema.py` — `TaxonDescendantCount` (37 LOC).
- `taxon/api/projections.py` — nuevo módulo, 275 LOC.
- `taxon/api/tree.py` — `_count_descendant_species` con cache pre-check (37 LOC nuevos).
- `taxon/api/_tree_tiers.py` — `_batch_species_counts` con cache merge (17 LOC nuevos).
- `taxon/migrate.py` — widening + `apply-projection` subcommand (95 LOC nuevos).
- `taxon/import_data.py` — post-import rebuild hook (37 LOC nuevos).
- `taxon/tests/test_descendant_counts_projection.py` — 167 LOC nuevos, 3 tests red-first del registration gap.
- `taxon/tests/test_migrate.py` — 72 LOC nuevos (workspace+projection table check + bare-engine regression).
- `taxon/tests/test_schema.py` — 75 LOC nuevos (schema contract).
- `taxon/tests/test_species_count_lazy_null.py` — 79 LOC actualizados (semántica nueva).
- `openspec/changes/descendant-counts-projection/{proposal,design,specs/*,tasks}.md` + mirrors ES.
- `openspec/specs/taxonomic-tree-browse/spec.md` — prune del "Out of Scope" stale.

## Why

El lazy-null fallback mantenía el response barato pero también mantenía `Animalia` invisible en el tree UI. Los operadores no podían ver cuántas especies cuelgan del kingdom tier sin pagar el coste de la CTE cada request. Materializar una vez y servir el cache forever cambia el comportamiento visible para los parents del long-tail y elimina la necesidad de la batched CTE para los ids cacheados.

El prefijo del threshold (1M direct children) es deliberado: la población inicial — `Animalia`, `Eukaryota`, `Methanobacteriota`, y futuros re-imports que pasen el corte — son exactamente los nodos cuyo subtree es demasiado caro para correr la CTE por-request. La projection deja la tabla vacía para todo lo demás (zero overhead) y la puebla on-demand + cache para los que sí lo necesitan.

## How it works en producción

1. Un cliente hace `GET /api/tree/children?parent_id=X` para un padre sobre el threshold.
2. `_count_descendant_species(X)` llama `lookup_one(session, X)`. Cache miss (primera vez).
3. La función cae al threshold guard: `direct_count > threshold` ⇒ dispara `materialize_for_parent(session, X, budget_seconds=1.0)`.
4. `materialize_for_parent` corre la misma CTE recursiva que el helper pre-change, mide `perf_counter()` antes/después, y commitea la fila solo si cabe en 1s. Si no cabe, devuelve `None` y la projection queda vacía para ese padre.
5. La CTE llama `taxonomy_display_level(rank)` — función SQLite user function que el FastAPI factory registra via `connect` listener. Los offline callers (migrate, import_data) usan `register_display_level(engine)` para tener el mismo registro.
6. El resultado persiste en `taxon_descendant_counts`. La próxima request para el mismo padre lee la fila en O(1) sin CTE ni threshold.
7. `import_data` ejecuta `_rebuild_descendant_counts_projection` al final de cada re-import CoL, con `budget_seconds=None` (debe completar la población sí o sí).
8. `python -m taxon.migrate apply-projection [--threshold N] [--budget-seconds S]` permite un rebuild manual offline.

## Workflows

- CI: `pytest taxon/tests/` corre 285 tests (incluido el regression net `test_apply_projection_populates_rows_on_bare_engine` para el registration gap). `ruff check`, `ruff format --check`, `mypy taxon` verdes.
- Operador: `python -m taxon.migrate apply` crea ahora también la tabla de projection en una DB fresca. `python -m taxon.migrate apply-projection` la rellena manualmente sin re-importar.
- Re-import CoL: `python -m taxon.import_data` reescribe las filas de la projection al final, con `budget_seconds=None` (sin SLO guard — la operación es offline).
- Migración desde `taxon.db` legacy: `python -m taxon.migrate apply` crea `taxon_descendant_counts`. La primera request para cada padre sobre el threshold dispara el rebuild on-demand.

## Aprendido

- **El gap de registro de `taxonomy_display_level` es invisible para los tests del API.** Solo el FastAPI factory wireaba la función; `taxon.migrate` y `taxon.import_data` construyen engines bare sin el listener. El sub-process test `test_apply_projection_populates_rows_on_bare_engine` es la red determinista — sin él, el CLI reventaría con `OperationalError: no such function` en producción.
- **La semántica de `_count_descendant_species` cambió intencionalmente.** Pre-change: "sobre el umbral ⇒ `None`". Post-change: "sobre el umbral ⇒ rebuild síncrono + cache; solo `None` cuando el rebuild excede el SLO". Dos tests existentes (`test_species_count_is_null_above_threshold`, `test_lazy_null_helper_returns_none_for_threshold_below_fanout`) pinneaban la semántica vieja y se actualizaron en commit `5c7a6fe` para pin la nueva.
- **`from X import Y` dentro de una función es monkey-patcheable desde `X.Y`.** Python re-importa el símbolo al namespace local cada vez que la línea se ejecuta. Eso permitió `monkeypatch.setattr(projections_mod, "materialize_for_parent", _slow)` en `test_lazy_null_helper_returns_none_when_rebuild_exceeds_budget` sin tocar el wrapper de la función tree.
- **El SDD cycle no commitea los artefactos.** Las fases `sdd-propose`, `sdd-spec`, `sdd-design`, `sdd-tasks` escriben archivos via la tool `write` pero el orchestrator debe `git add` antes del PR. En este cambio, los artefactos quedaron untracked hasta que añadí el commit `aae749f` retroactivamente.
- **Los artefactos de SDD pueden contar contra el review budget.** Los 2005 LOC de proposal/spec/design/tasks + mirrors ES son artefactos de proceso — el reviewer real sólo necesita mirar las ~1300 LOC de código + tests. Worth flagging en futuros changes para evitar la sorpresa del `size:exception`.
- **El umbral asimétrico entre `_count_descendant_species` (1M) y `_batch_species_counts` (100k)** es pre-existente y no se toca en este change. La cache gana en ambos caminos porque `lookup_one`/`lookup_many` corren antes de cualquier threshold guard, así que la asimetría queda oculta.