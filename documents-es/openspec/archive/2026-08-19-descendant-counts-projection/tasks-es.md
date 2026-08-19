# Tareas: descendant-counts-projection

## Pronóstico de carga de revisión

| Campo | Valor |
|-------|-------|
| Líneas modificadas estimadas | ~845 en total (producción ~340 + pruebas ~505; los espejos en español se excluyen del presupuesto) |
| Riesgo de presupuesto de 400 líneas | Medio (PR #2 ~440 LOC es borderline; los commits por unidad de trabajo de `work-unit-commits` mantienen cada commit hijo en ≤ 400 LOC) |
| PRs encadenados recomendados | Sí |
| División sugerida | PR #1 → PR #2 → PR #3 |
| Estrategia de entrega | ask-on-risk |
| Estrategia de cadena | stacked-to-main |

Decisión necesaria antes de aplicar: Sí
PRs encadenados recomendados: Sí
Estrategia de cadena: pending
Riesgo de presupuesto de 400 líneas: Medio

### Unidades de trabajo sugeridas

| Unidad | Objetivo | PR probable | Comando de prueba focalizado | Arnés de ejecución | Límite de reversión |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Esquema + ORM + ampliación de `PROJECTION_TABLES` + CLI `apply-projection` + `register_display_level` | PR #1 | `pytest taxon/tests/test_migrate.py taxon/tests/test_descendant_counts_projection.py::test_apply_creates_taxon_descendant_counts_table taxon/tests/test_descendant_counts_projection.py::test_apply_projection_runs_the_cte_on_a_bare_engine -v` | `python -m taxon.migrate apply --database-url sqlite:///$TMP/col.db` → sale 0, existe `taxon_descendant_counts`; `python -m taxon.migrate apply-projection` → sale 0 en BD vacía | Eliminar `taxon/api/projections.py` (sin consumidores aún), revertir `taxon/schema.py`, revertir `taxon/migrate.py`, eliminar la tabla `taxon_descendant_counts`. La ruta de lectura de la API queda intacta — comportamiento previo preservado. |
| 2 | Motor de materialización (`projections.py`): reconstrucción + búsqueda + guarda SLO | PR #2 | `pytest taxon/tests/test_descendant_counts_projection.py -v` (excluyendo la prueba de engine pelado del PR #1) | N/A (helpers puros de SQLAlchemy, ejercitados vía TestClient en PR #3) | Revertir `taxon/api/projections.py` + pruebas; la superficie CLI del PR #1 sigue funcionando contra una proyección vacía. |
| 3 | Integración API + reconstrucción de `import_data` | PR #3 | `pytest taxon/tests/ -v` (todo verde); `pytest taxon/tests/test_species_count_lazy_null.py -v` (sin cambios, guarda de regresión) | `uvicorn taxon.api:create_app --reload` + `curl "/api/tree/children?parent_id={animalia_id}"` → `species_count` es entero no nulo tras la primera petición; `python -m taxon.import_data` sobre `data/taxon.db` reconstruye la proyección | Revertir `taxon/api/tree.py` + `taxon/api/_tree_tiers.py` + `taxon/import_data.py`; el CLI del PR #1 queda como único escritor de la tabla. |

## Fase 1 — PR #1: Cimientos (esquema + ORM + superficie CLI) (~270 LOC)

**Worktree**: `../taxon-worktrees/descendant-counts-projection-pr1`.
**Rama**: `feat/descendant-counts-projection-pr1`.
**Base / Destino**: `develop` según AGENTS.md §4.
**Depende de**: nada.
**TDD estricto**: cada unidad de trabajo a continuación comienza con una prueba RED (commit RED → GREEN → refactor).

### 1. Agregar la clase ORM `TaxonDescendantCount` en `taxon/schema.py`

**Archivos**: `taxon/schema.py`, `taxon/tests/test_schema.py`.
**Aceptación**:
- [x] La clase `TaxonDescendantCount` existe en `Base.metadata` con `__tablename__ = "taxon_descendant_counts"`.
- [x] Cuatro columnas: `taxon_id` (PK, FK a `taxa.id`), `species_count` (INT, NOT NULL), `total_count` (INT, NOT NULL), `computed_at` (String, NOT NULL).
- [x] El default de `computed_at` es `lambda: datetime.now(UTC).isoformat(timespec="seconds")` (cadena ISO-8601 — SQLite no tiene TIMESTAMP, coincide con `SpeciesExplored.explored_at`).
- [x] Sin índices secundarios: `taxon_id` es la PK (B-tree rowid); cada acceso es una búsqueda por punto o lista `IN` sobre PKs.
**Pruebas**: `taxon/tests/test_schema.py` — RED-first: `test_taxon_descendant_count_table_exists_with_four_columns`, `test_taxon_descendant_count_pk_is_taxon_id`, `test_taxon_descendant_count_computed_at_default_is_iso8601_string`. `pytest taxon/tests/test_schema.py -v`.
**Notas**:
- Commit convencional: `feat(schema): add TaxonDescendantCount for cached descendant counts`.
- Colocar la clase justo después de `SpeciesPath` (línea 56) para que el vecino de ciclo de vida sea correcto; la proyección tiene FK hacia `taxa.id` y se invalida por una reimportación — mismo ciclo de vida que `SpeciesPath`, NO como los modelos del workspace.
- Importar `datetime, UTC` desde `datetime` (no `from datetime import datetime, UTC` si el módulo aún no lo hace — revisar primero los imports existentes para evitar duplicación).
- **Secuencial**: sin escritores en paralelo; este commit debe aterrizar antes de que exista cualquier consumidor de la clase.

### 2. Agregar la constante `PROJECTION_TABLES` + helper `register_display_level` para engine pelado

**Archivos**: `taxon/api/projections.py` (nuevo módulo — esqueleto vacío), `taxon/api/workspace.py` (NO modificado).
**Aceptación**:
- [x] Existe `taxon/api/projections.py` con una única constante exportada `PROJECTION_TABLES: tuple[str, ...] = ("taxon_descendant_counts",)`.
- [x] `PROJECTION_TABLES` es importable como `from taxon.api.projections import PROJECTION_TABLES`.
- [x] Se exporta un stub `register_display_level(engine: Engine) -> None`. Adjunta la función de usuario SQLite `taxonomy_display_level(rank)` a cada nueva conexión vía `@event.listens_for(engine, "connect")`, replicando el listener de la factoría FastAPI en `taxon/api/__init__.py:92-95`. El cuerpo delega en `taxon.taxonomy.display_level`.
- [x] Importar el módulo no produce efectos colaterales (sin creación de engine, sin I/O a BD).
**Pruebas**: RED-first en un nuevo `taxon/tests/test_descendant_counts_projection.py` (el archivo completo llega en PR #2 — para este commit solo existe la prueba de registro en engine pelado como `test_register_display_level_attaches_function_to_bare_engine` — ver tarea 6).
**Notas**:
- Commit convencional: `feat(projections): add PROJECTION_TABLES tuple + register_display_level helper`.
- El módulo es `projections.py` (público), NO `_projection.py` como lo nombraba la propuesta — ADR-1 en `design.md:43-49`. `migrate.py` e `import_data.py` importan desde fuera de `taxon/api/`, así que la convención de prefijo de subrayado privado usada por `_tree_tiers.py` no aplica.
- El helper se invoca desde `taxon/migrate.py` y `taxon/import_data.py` en la tarea 3 del PR #1 y en el PR #3 respectivamente. Sin él, ambos engines pelados lanzan `sqlite3.OperationalError: no such function: taxonomy_display_level` cuando se ejecuta `materialize_all` — el diseño nombra esto como el punto de integración de mayor riesgo (`design.md:365-403`).
- NO agregar aún `lookup_one`, `lookup_many`, `materialize_*` — esas funciones llegan en el PR #2.
- **Secuencial**: este commit aterriza antes de la tarea 3 del PR #1 (CLI) para que el helper esté disponible.

### 3. Ampliar `_run_apply` para incluir `PROJECTION_TABLES` + registrar `taxonomy_display_level` en el engine de la CLI

**Archivos**: `taxon/migrate.py`, `taxon/tests/test_migrate.py`.
**Aceptación**:
- [x] `taxon/migrate.py::main` pasa `WORKSPACE_TABLES + PROJECTION_TABLES` a `_run_apply` (para que el `apply` simple cree `taxon_descendant_counts` junto a las tres tablas del workspace).
- [x] `WORKSPACE_TABLES` permanece SIN CAMBIOS — su docstring fija su significado a las tres tablas del workspace que sobreviven a reimportaciones (`taxon/api/workspace.py:43-50`); ampliamos el punto de llamada del `apply`, NO la constante.
- [x] El engine de la CLI en `taxon/migrate.py:233` invoca `register_display_level(engine)` después de `create_engine(...)` para que el CTE recursivo funcione fuera de banda.
- [x] La CLI aún NO gana un subcomando `apply-projection` — ese llega en la tarea 5.
**Pruebas**: `taxon/tests/test_migrate.py` — actualización RED-first: `test_apply_creates_three_new_tables` se renombra a `test_apply_creates_all_migrated_tables` y ahora también asegura `taxon_descendant_counts` en el conjunto resultante; agregar `test_apply_creates_taxon_descendant_counts_on_fresh_db` (pin de una sola tabla, escenario de la especificación `Fresh DB gains the table on apply`). `pytest taxon/tests/test_migrate.py -v`.
**Notas**:
- Commit convencional: `feat(migrate): include PROJECTION_TABLES in apply + register display_level on CLI engine`.
- La interfaz de `_run_apply` (`taxon/migrate.py:158`) NO cambia — la única ampliación está en el punto de llamada en `main`. Esto mantiene el helper reutilizable y testeable.
- `register_display_level(engine)` es idempotente (SQLite permite re-registrar el mismo nombre de función), así que llamarlo dos veces sobre el mismo engine (una vez aquí, otra si la tarea 5 del PR #1 también lo cablea) es seguro — pero la tarea 5 del PR #1 NO re-registrará; solo uno de los dos llamadores debe registrar.
- La llamada a `register_display_level` es el arreglo de engine pelado que evita `OperationalError: no such function: taxonomy_display_level` cuando los llamadores de la CLI alcancen el trabajo de CTE del PR #2.
- **Secuencial**: debe aterrizar antes de la tarea 4 del PR #1 (subcomando CLI) porque el subcomando usa el mismo engine.

### 4. Prueba RED-first para el subcomando `apply-projection`

**Archivos**: `taxon/tests/test_migrate.py`.
**Aceptación**:
- [x] `test_apply_projection_exits_zero_on_empty_db` — RED: `python -m taxon.migrate apply-projection --database-url sqlite:///...` contra una BD vacía sale con código no cero (actualmente el subcomando no existe → error de argparse → salida no cero). La prueba fija el contrato.
- [x] `test_apply_projection_respects_threshold_flag` — RED: pasar `--threshold=1` contra una BD poblada; argparse debe aceptar la bandera. Falla actualmente porque la bandera no se reconoce.
- [x] `test_apply_projection_is_idempotent_via_cli` — RED: invocar dos veces sale con código cero en ambas. Falla porque el subcomando no existe.
**Pruebas**: Las tres son RED en este commit. `pytest taxon/tests/test_migrate.py -v` las muestra fallando con los errores esperados de argparse / código de salida.
**Notas**:
- Commit convencional: `test(migrate): pin apply-projection CLI contract (RED)`.
- Estas pruebas usan el mismo arnés de `subprocess` + `tmp_path` que el `test_migrate.py` existente (ver fixtures `_run` + `env_with_pythonpath`, líneas 66-93).
- TDD estricto: este commit DEBE ser su propio commit (solo RED) para que el commit GREEN de la tarea 5 tenga un diff claro.

### 5. Agregar el subparser `apply-projection` en `taxon/migrate.py`

**Archivos**: `taxon/migrate.py`, `taxon/tests/test_migrate.py`.
**Aceptación**:
- [x] `python -m taxon.migrate apply-projection --database-url sqlite:///...` sale con código 0 en una BD poblada y en una BD vacía.
- [x] El subparser acepta `--threshold INT` (default `SPECIES_COUNT_LAZY_NULL_THRESHOLD`); el valor acota la población (solo los padres cuyo `direct_children_count` supere el valor obtienen filas).
- [x] El subparser acepta `--budget-seconds FLOAT` (default `None` — desactiva la guarda SLO para llamadores fuera de banda; ver ADR-2 en `design.md:60-82`).
- [x] Las tres pruebas RED de la tarea 4 ahora pasan GREEN.
- [x] El subcomando invoca `register_display_level(engine)` (el re-registro idempotente es aceptable; solo uno de los tres llamadores realmente necesita la llamada — mantener el punto de llamada explícito por claridad).
**Pruebas**: `taxon/tests/test_migrate.py` — las tres pruebas RED de la tarea 4 ahora pasan. También agregar `test_apply_projection_creates_taxa_table_on_empty_db_for_cte` para confirmar que el subcomando puede ejecutar un CTE en memoria contra la tabla `taxa` recién creada (sin datos — solo ejercita el cableado SQL).
**Notas**:
- Commit convencional: `feat(migrate): add apply-projection subcommand + --threshold/--budget-seconds flags`.
- Esqueleto de implementación: `apply-projection` invoca `materialize_all` desde `taxon/api/projections.py`. El PR #1 entrega un stub `materialize_all(session, threshold, budget_seconds=None) -> int` que devuelve `0` (sin filas escritas). La implementación completa llega en PR #2 — PR #1 solo necesita que el cableado CLI sea honesto sobre el contrato.
- Posición del subparser: entre `dry-run` y `apply` está bien, o después de `apply` — argparse no le importa. Coincidir con el orden existente (dry-run → apply → apply-projection) para que el listado de ayuda sea predecible.
- **Secuencial**: la tarea 5 aterriza después de la tarea 4 (RED-first). PR #1 cierra cuando las tareas 1+2+3+4+5 aterrizan como 5 commits.

### 6. Prueba de registro en engine pelado (atrapa la brecha de `taxonomy_display_level`)

**Archivos**: `taxon/tests/test_descendant_counts_projection.py` (archivo nuevo).
**Aceptación**:
- [x] `test_register_display_level_attaches_function_to_bare_engine` — crear un `create_engine("sqlite:///:memory:")` pelado (SIN listener), luego invocar `register_display_level(engine)`. Abrir una conexión y ejecutar `SELECT taxonomy_display_level('species')` — debe devolver `"species"`.
- [x] `test_register_display_level_is_idempotent` — invocar `register_display_level(engine)` dos veces sobre el mismo engine no lanza excepción.
- [x] `test_register_display_level_fails_on_unregistered_engine` — un engine pelado sin el registro lanza `OperationalError: no such function: taxonomy_display_level` cuando se ejecuta el CTE. Fija la brecha.
**Pruebas**: Las tres son la semilla del nuevo archivo de pruebas. `pytest taxon/tests/test_descendant_counts_projection.py -v`.
**Notas**:
- Commit convencional: `test(projections): pin register_display_level on bare engine`.
- Esta es la prueba que `design.md:402-403` nombra explícitamente como red de seguridad para la brecha de registro de `taxonomy_display_level`. Es el punto de integración de mayor riesgo en el cambio — invisible para las pruebas unitarias del engine de la API, solo aflora cuando corre la CLI.
- RED-first: el helper aún no existe (la tarea 2 lo entrega), así que la tarea 6 debe commitearse DESPUÉS de la tarea 2. Orden: 1 → 2 → 6 → 3 → 4 → 5.

PR #1 cierra con 6 commits de unidad de trabajo (1 + 2 + 6 + 3 + 4 + 5), ~270 LOC en total. El cuerpo del PR debe mencionar que la brecha de `register_display_level` está cerrada y que el subcomando CLI está cableado pero es un no-op hasta PR #2.

## Fase 2 — PR #2: Motor de materialización (`projections.py`) (~440 LOC, borderline)

**Worktree**: `../taxon-worktrees/descendant-counts-projection-pr2`.
**Rama**: `feat/descendant-counts-projection-pr2`.
**Base / Destino**: `develop` (después de que PR #1 se fusione).
**Depende de**: PR #1 fusionado (para que existan el esquema + el andamiaje CLI).

### 7. Helpers de búsqueda RED-first (`lookup_one`, `lookup_many`, `_table_exists`)

**Archivos**: `taxon/api/projections.py`, `taxon/tests/test_descendant_counts_projection.py`.
**Aceptación**:
- [x] `lookup_one(session, taxon_id) -> int | None` devuelve el `species_count` cacheado o `None` en caso de fallo.
- [x] `lookup_one` captura `OperationalError: no such table: taxon_descendant_counts` y devuelve `None` — el escenario de BD legada (sección de especificación Schema Adds Without Touching Legacy Databases).
- [x] `lookup_many(session, taxon_ids) -> dict[int, int]` ejecuta UN solo `SELECT` con lista `IN`; los ids ausentes simplemente faltan en el dict; entrada vacía devuelve `{}` sin viaje de ida y vuelta.
- [x] `_table_exists(session, name) -> bool` devuelve `False` para una tabla ausente (usado por la ruta de lectura en BD legadas).
- [x] Sin mutación de sesión — ambos helpers son lecturas puras.
**Pruebas**: RED-first en `taxon/tests/test_descendant_counts_projection.py`:
- `test_lookup_one_returns_none_when_table_absent` (BD legada — usar un engine en memoria sin `create_all`).
- `test_lookup_one_returns_cached_value_after_write` (escribir una fila, buscarla).
- `test_lookup_many_returns_empty_dict_for_empty_input` (sin viaje de ida y vuelta a BD — asegurar mediante parchear `session.execute`).
- `test_lookup_many_excludes_missing_ids` (mezcla de presentes + ausentes).
- `test_table_exists_returns_false_for_missing_table` (BD legada).
**Notas**:
- Commit convencional: `feat(projections): add lookup_one + lookup_many read helpers (RED-first)`.
- `lookup_one` es el PRIMER punto de integración en la ruta de lectura — `tree.py` lo invocará antes de la guarda de umbral en PR #3. La firma debe ser definitiva en este commit porque el diff de `tree.py` del PR #3 depende de ella.
- Usar `text("SELECT taxon_id, species_count FROM taxon_descendant_counts WHERE taxon_id = :pid")` — nunca interpolar el id.
- **Secuencial**: sin escritores en paralelo. PR #3 solo aterrizará después de que este PR se fusione.

### 8. RED-first `_projected_parent_ids` (predicado de población)

**Archivos**: `taxon/api/projections.py`, `taxon/tests/test_descendant_counts_projection.py`.
**Aceptación**:
- [x] `_projected_parent_ids(session, threshold) -> list[int]` devuelve cada id de taxón cuyo `direct_children_count` supere `threshold`.
- [x] La constante de umbral se importa desde `taxon.api.tree.SPECIES_COUNT_LAZY_NULL_THRESHOLD` — fuente única de verdad (sección de especificación Population Rule).
- [x] Resultado vacío devuelve `[]` (sin error).
- [x] La consulta es `SELECT parent_id FROM taxa WHERE parent_id IS NOT NULL GROUP BY parent_id HAVING count(*) > :threshold` — parámetro ligado, nunca interpolado.
**Pruebas**: RED-first en `taxon/tests/test_descendant_counts_projection.py`:
- `test_projected_parent_ids_returns_only_above_threshold` (construir un fixture con 3 padres: 5 hijos, 100 hijos, 1000 hijos; con threshold=50 → solo el último).
- `test_projected_parent_ids_skips_root_with_null_parent_id` (un taxón raíz cuyo `parent_id IS NULL` nunca es un "padre" para esta proyección).
- `test_projected_parent_ids_uses_spec_constant` (monkeypatch `SPECIES_COUNT_LAZY_NULL_THRESHOLD = 50`, confirmar que la consulta lo lee).
**Notas**:
- Commit convencional: `feat(projections): add _projected_parent_ids population predicate`.
- La consulta NO debe usar `SELECT COUNT(*) FROM taxa WHERE parent_id = :pid` en un bucle — eso sería N+1. La consulta agrupada con `HAVING` es la forma de un solo viaje de ida y vuelta.
- Este helper es compartido por `materialize_all` (tarea 10 del PR #2) y puede ser reutilizado por `import_data` (tarea 13 del PR #3).

### 9. RED-first `materialize_for_parent` + guarda de presupuesto SLO

**Archivos**: `taxon/api/projections.py`, `taxon/tests/test_descendant_counts_projection.py`.
**Aceptación**:
- [x] `materialize_for_parent(session, parent_id, *, budget_seconds=REBUILD_BUDGET_SECONDS) -> int | None` reconstruye la fila para `parent_id` y devuelve `species_count`.
- [x] Usa `time.perf_counter()` para medir el tiempo transcurrido del CTE (ADR-2: medir, no predecir).
- [x] Bajo presupuesto (`elapsed <= budget_seconds`): INSERT la fila, `session.commit()`, devuelve `species_count`.
- [x] Sobre presupuesto: `session.rollback()`, SIN fila escrita, devuelve `None` — la respuesta previa al cambio.
- [x] Idempotente: re-ejecutar sobre una fila existente hace upsert sobre la PK (sin duplicado, sin acumulación).
- [x] `REBUILD_BUDGET_SECONDS: Final[float] = 1.0` — coincide con el SLO de 1s de `/api/tree/children` documentado en `taxon/api/tree.py:67-69`.
**Pruebas**: RED-first en `taxon/tests/test_descendant_counts_projection.py`:
- `test_rebuild_under_budget_writes_row` (fixture pequeño, presupuesto por defecto → fila existe tras la llamada; `computed_at` es reciente).
- `test_rebuild_over_budget_skips_write_and_returns_none` (inyectar `budget_seconds=0.0` para forzar la rama sobre-presupuesto de forma determinista — sin sleeps, sin timing flaky. Asegurar que se devuelve `None` Y que no hay fila en la tabla).
- `test_rebuild_is_idempotent_on_existing_row` (invocar dos veces; conteo de filas = 1; los valores pueden diferir si el fixture cambia pero el conteo es constante).
- `test_rebuild_sets_computed_at_iso8601_string` (asegurar formato `datetime.now(UTC).isoformat(timespec="seconds")`).
**Notas**:
- Commit convencional: `feat(projections): add materialize_for_parent with measured SLO budget`.
- La prueba sobre-presupuesto (`budget_seconds=0.0`) es la alternativa determinista del diseño — `design.md:412` fija esto como el enfoque de prueba (sin timing flaky).
- El texto del CTE refleja `tree.py:212-227` byte por byte para que ambas rutas recorran la misma forma. La profundidad de recursión y la búsqueda `taxonomy_display_level` coinciden.
- **Secuencial**: PR #3 (integración con `tree.py`) consume `materialize_for_parent` vía `_count_descendant_species` después de que este PR aterrice.

### 10. RED-first `materialize_all` (población por lotes)

**Archivos**: `taxon/api/projections.py`, `taxon/tests/test_descendant_counts_projection.py`.
**Aceptación**:
- [x] `materialize_all(session, threshold=SPECIES_COUNT_LAZY_NULL_THRESHOLD, *, budget_seconds=None) -> int` reconstruye cada fila para cada padre proyectado y devuelve el número de filas escritas.
- [x] Itera sobre `_projected_parent_ids(session, threshold)` y llama a `materialize_for_parent` por cada padre.
- [x] `budget_seconds=None` (el default) DESACTIVA la guarda SLO para llamadores fuera de banda — `apply-projection` e `import_data` no están sirviendo una petición y deben completar la población (la sección Rebuild Bounded by the Per-Request SLO de la especificación se limita al endpoint del árbol).
- [x] Todo el lote corre en una sola transacción (un único `session.commit()` al final) para que un fallo parcial haga rollback.
**Pruebas**: RED-first en `taxon/tests/test_descendant_counts_projection.py`:
- `test_materialize_all_populates_only_above_threshold_parents` (3 padres — 5, 100, 1000 hijos; threshold=50 → 1 fila escrita, devuelve 1).
- `test_materialize_all_is_idempotent` (invocar dos veces; conteo de filas sin cambios, valores de `species_count` + `total_count` sin cambios).
- `test_materialize_all_disables_slo_guard_by_default` (pasar un fixture lo suficientemente grande para que el presupuesto por defecto lo saltaría; `budget_seconds=None` → fila escrita de todas formas).
- `test_materialize_all_returns_zero_on_empty_database` (sin padres proyectados → devuelve 0, sin error).
**Notas**:
- Commit convencional: `feat(projections): add materialize_all batch population`.
- El escape `budget_seconds=None` es la ÚNICA asimetría que el diseño señala explícitamente en `design.md:282-287` — la ruta de petición está acotada, la ruta fuera de banda está sin acotar.
- El stub `materialize_all` que el PR #1 tarea 5 retornaba `0`; el PR #2 tarea 10 reemplaza el stub con la implementación real. Tras este commit, el subcomando CLI del PR #1 puebla filas reales.
- El cuerpo del PR #2 debe mencionar que este es el PRIMER escritor real — PR #1 entrega una CLI que dice "0 filas" hasta que esto aterrice.

### 11. Cierre del PR #2: extender `_table_exists` para cubrir la ruta de lectura de BD legada

**Archivos**: `taxon/api/projections.py`, `taxon/tests/test_descendant_counts_projection.py`.
**Aceptación**:
- [x] Las tres pruebas CLI del PR #1 tarea 4 (`test_apply_projection_exits_zero_on_empty_db`, `test_apply_projection_respects_threshold_flag`, `test_apply_projection_is_idempotent_via_cli`) ahora salen con código cero Y pueblan filas (cuando el umbral se alcanza) vía el `materialize_all` real.
- [x] `test_apply_projection_runs_the_cte_on_a_bare_engine` (la prueba de engine pelado del PR #1 tarea 6) ahora ejercita `materialize_all` de extremo a extremo contra un engine CLI pelado — confirma que la brecha de registro de `taxonomy_display_level` está cerrada.
- [x] `pytest taxon/tests/test_migrate.py taxon/tests/test_descendant_counts_projection.py -v` → todo verde.
- [x] `pytest taxon/tests/test_species_count_lazy_null.py -v` → sin cambios, sigue verde (sin regresión en la ruta previa al cambio).
**Pruebas**: Todas las pruebas RED de las tareas 7-10 ahora pasan GREEN. Las dos pruebas CLI que estaban stub en PR #1 (tarea 5) ahora ejercitan la implementación real.
**Notas**:
- Commit convencional: `feat(projections): wire materialize_all into apply-projection CLI`.
- Este commit reemplaza el stub `materialize_all` entregado en la tarea 5 del PR #1 con la implementación real. El diff es pequeño (~10 LOC) pero el cambio semántico es grande: las filas ahora se persisten en cada ejecución de `apply-projection`.
- Tras PR #2, `taxon_descendant_counts` tiene filas para cada padre que supera el umbral en la BD. El cambio de UI (Animalia deja de ser `?`) aterriza en PR #3.
- PR #2 cierra con ~440 LOC (180 módulo + 260 pruebas). Borderline sobre el presupuesto de 400 líneas — la división de commits por `work-unit-commits` mantiene cada commit hijo ≤ 400 LOC.

## Fase 3 — PR #3: Integración API + reconstrucción de `import_data` (~135 LOC)

**Worktree**: `../taxon-worktrees/descendant-counts-projection-pr3`.
**Rama**: `feat/descendant-counts-projection-pr3`.
**Base / Destino**: `develop` (después de que PR #2 se fusione).
**Depende de**: PR #2 fusionado (para que `projections.py` tenga los helpers `materialize_*` reales).

### 12. Cablear pre-chequeo de `lookup_one` + ganchos de reconstrucción en `_count_descendant_species`

**Archivos**: `taxon/api/tree.py`, `taxon/tests/test_api_router_tree.py`, `taxon/tests/test_descendant_counts_projection.py`.
**Aceptación**:
- [x] `_count_descendant_species` consulta `lookup_one(session, parent_id)` inmediatamente después del atajo de caché con scope de petición (después de la línea 190 de `tree.py`), ANTES de la guarda `direct_count > threshold` (línea 198).
- [x] Acierto de caché: devolver `cached` directamente, poblar `_cache[parent_id]` para el scope de petición, saltarse la guarda de umbral Y el CTE.
- [x] Fallo de caché: cae a la ruta existente de umbral + CTE sin cambios. Si la rama de umbral se dispara, invoca `materialize_for_parent(session, parent_id)` y devuelve su resultado (`None` cuando sobre presupuesto, `int` cuando bajo presupuesto).
- [x] La segunda guarda de umbral en `tree.py:236-239` (total_count > threshold) recibe el mismo tratamiento — en lugar de re-recorrer, el helper escribe el `(species_count, total_count)` ya conocido mediante un `_persist_cached_count(session, parent_id, species_count, total_count, elapsed) -> None` pequeño que respeta el mismo presupuesto SLO.
- [x] Regresión: `pytest taxon/tests/test_species_count_lazy_null.py -v` → sin cambios, sigue verde.
**Pruebas**: RED-first en `taxon/tests/test_descendant_counts_projection.py`:
- `test_cache_hit_returns_without_running_cte` (pre-insertar una fila en `taxon_descendant_counts`; parchear `session.execute` para contar invocaciones de CTE; asegurar cero).
- `test_cache_hit_skips_threshold_guard` (padre cuyo `direct_count > SPECIES_COUNT_LAZY_NULL_THRESHOLD` pero tiene una fila cacheada → devuelve el valor cacheado, sin `None`).
- `test_first_read_materializes_row_and_sets_computed_at` (sin fila cacheada → llamar → asegurar que se devuelve `species_count` Y que existe una fila Y que `computed_at` es reciente).
- `test_cache_miss_below_threshold_uses_existing_cte_path` (sin fila cacheada, padre por debajo del umbral → la ruta CTE existente corre sin cambios, SIN fila escrita — solo los padres que superan el umbral obtienen caché).
- `test_rebuild_total_count_guard_writes_row_when_under_budget` (padre cuyo conteo de hijos directos está por debajo del umbral pero cuyo subárbol recursivo supera el umbral → segunda guarda se dispara → `_persist_cached_count` escribe la fila).
**Notas**:
- Commit convencional: `feat(tree): consult projection cache before threshold guard`.
- `_persist_cached_count` reside en `taxon/api/projections.py` (un helper escritor pequeño, ~12 LOC). Está co-localizado con `materialize_for_parent` porque ambos comparten la disciplina de medición SLO.
- El dict `_cache` con scope de petición en `tree.py:189-190` se preserva sin cambios (es más barato que una consulta a BD).
- **Secuencial**: este commit aterriza antes de la tarea 13 (integración por lotes) porque el helper por fila es la integración más simple; las pruebas de integración por lotes se construyen sobre la misma ruta `_persist_cached_count`.

### 13. Cablear pre-carga de `lookup_many` en `_batch_species_counts`

**Archivos**: `taxon/api/_tree_tiers.py`, `taxon/tests/test_descendant_counts_projection.py`.
**Aceptación**:
- [x] `_batch_species_counts` invoca `lookup_many(session, parent_ids)` inmediatamente después de la lectura de `direct_counts` en `_tree_tiers.py:446`.
- [x] Los ids cacheados se escriben en `result` y SE EXCLUYEN de `eligible` para que no aporten fila semilla al CTE recursivo.
- [x] El texto del CTE en `_tree_tiers.py:467-485` es idéntico byte a byte a la versión previa al cambio (sin reescritura de SQL, sin nuevos joins).
- [x] El bucle de agregación en las líneas 486-487 solo escribe en ids que fueron sembrados — forzando estructuralmente que "la fila cacheada obsoleta gana sobre el CTE".
- [x] Regresión: las pruebas de niveles por lotes en `taxon/tests/test_api_router_tree.py` siguen verdes sin cambios.
**Pruebas**: RED-first en `taxon/tests/test_descendant_counts_projection.py`:
- `test_batch_merges_cached_and_cte_counts` (lote mixto: 1 cacheado + 3 sub-umbral → el resultado lleva el valor cacheado para el id cacheado + el valor del CTE para los demás).
- `test_batch_excludes_cached_ids_from_cte_seed` (capturar el SQL semilla generado; asegurar que el id cacheado está ausente del `UNION ALL`).
- `test_batch_returns_all_cached_when_threshold_exceeded_for_none` (todos los padres del lote tienen filas cacheadas; el CTE nunca corre; `eligible` está vacío; retorna temprano según `tree_tiers.py:457-458`).
- `test_batch_cached_stale_row_wins_over_cte` (existe fila cacheada con valor X; el CTE resolvería a valor Y; el resultado lleva X).
**Notas**:
- Commit convencional: `feat(tree-tiers): pre-load cached rows in batch species counts`.
- El cambio es ~15 LOC net (una nueva consulta, un pequeño ajuste al bucle). El texto del CTE queda sin cambios — `design.md:131-138` fija esta restricción.
- **Secuencial**: este commit puede aterrizar en paralelo con la tarea 12 en el MISMO PR (#3) pero DEBE ser un commit separado para que el foco de revisión sea por archivo.

### 14. Agregar `register_display_level` + `materialize_all` post-import en `taxon/import_data.py`

**Archivos**: `taxon/import_data.py`, `taxon/tests/test_import.py` (o `test_descendant_counts_projection.py`).
**Aceptación**:
- [x] `_sqlite_engine` (línea 75) invoca `register_display_level(engine)` ANTES del listener existente `enable_foreign_keys` para que la función se registre en cada nueva conexión.
- [x] `import_dataset` invoca `materialize_all` después de `_populate_species_paths(engine)` (línea 71) y ANTES del `return counts` (línea 72). La llamada usa un `Session(engine)` fresco para que la ruta por lotes fuera de banda sea independiente de cualquier sesión en poder del llamador.
- [x] Un fixture pequeño (`test_rebuild_after_import_dataset_populates_threshold_parents`) construye un dataset donde un padre supera el umbral; tras el retorno de `import_dataset`, la fila está presente con un `computed_at` fresco.
- [x] Regresión: `pytest taxon/tests/test_import.py -v` → verde sin cambios (las pruebas existentes no aseguran sobre `taxon_descendant_counts`).
**Pruebas**: RED-first en `taxon/tests/test_descendant_counts_projection.py`:
- `test_import_dataset_triggers_rebuild` (fixture sintético, padre que supera el umbral → fila presente tras la llamada).
- `test_import_dataset_rebuild_is_idempotent` (invocar `import_dataset` dos veces sobre la misma fuente; conteo de filas + valores sin cambios).
- `test_import_dataset_rebuild_does_not_drop_rows_after_drop_all` (`import_dataset` invoca `drop_all` y luego `create_all` → la tabla de proyección se recrea vacía; la población post-import es fresca, no obsoleta).
**Notas**:
- Commit convencional: `feat(import_data): rebuild projection after CoL re-import`.
- La llamada a `register_display_level` aquí es el SEGUNDO sitio de registro (la tarea 3 del PR #1 registra en el engine CLI; la tarea 14 del PR #3 registra en el engine de import). El re-registro es idempotente — SQLite permite que `create_function` sobrescriba sin lanzar.
- `import_dataset` elimina + crea TODAS las tablas (`import_data.py:46-47`), así que la tabla de proyección está fresca en cada import — no hay ventana de fila obsoleta (sección Migration / Rollout del diseño).
- La llamada `materialize_all` post-import usa `budget_seconds=None` (el default) para que la guarda SLO esté desactivada — los imports son llamadores por lotes fuera de banda.

### 15. Actualizar la línea legada `Out of Scope` en `taxonomic-tree-browse/spec.md`

**Archivos**: `openspec/specs/taxonomic-tree-browse/spec.md`.
**Aceptación**:
- [x] La línea `species_count materialization at deep nodes` se elimina de la sección `Out of Scope` (la línea existe al final del archivo; verificar con `rg "species_count materialization" openspec/specs/`).
- [x] La especificación delta en `openspec/changes/descendant-counts-projection/specs/taxonomic-tree-browse/spec.md` ya registra el requisito superado — no se necesita edición en la especificación delta.
- [x] `git diff openspec/specs/taxonomic-tree-browse/spec.md` muestra solo la eliminación.
**Pruebas**: Ninguna — solo documentación.
**Notas**:
- Commit convencional: `docs(specs): prune superseded Out-of-Scope line for projection`.
- Se rastrea como su propia tarea para que no se olvide al momento del archivo (la sección Risks Carried From The Spec del diseño nombra este riesgo).
- Este commit aterriza DENTRO del PR #3 (o como PR de seguimiento solo de docs — el orquestador decide).

### 16. Cierre del PR #3 + verificar que no hay regresión

**Archivos**: `taxon/tests/test_species_count_lazy_null.py` (sin ediciones — guarda).
**Aceptación**:
- [x] `pytest taxon/tests/ -v` → todo verde en `develop`.
- [x] `pytest taxon/tests/test_species_count_lazy_null.py -v` → verde sin cambios (guarda de regresión para el comportamiento previo al cambio).
- [x] `mypy taxon/` → cero errores.
- [x] `ruff check taxon/` → cero errores.
- [x] Arnés de ejecución: `uvicorn taxon.api:create_app --reload` contra `data/col.db`; `curl "/api/tree/children?parent_id={animalia_id}"` → `species_count` es un entero no nulo (era `null` antes del cambio). Segunda llamada → valor idéntico, sin línea de log del CTE.
- [x] Arnés de ejecución: `python -m taxon.import_data` sobre `data/taxon.db` reconstruye la proyección; el `apply-projection` posterior es un no-op (conteo de filas sin cambios).
**Pruebas**: Los comandos del arnés arriba.
**Notas**:
- Commit convencional: `test(tree): verify species_count cache integration (regression guard)`.
- Este es el commit final del PR #3. Tras este, el cambio de UI es observable y `Animalia` ya no se renderiza como `?` para siempre.

PR #3 cierra con 5 commits (12 + 13 + 14 + 15 + 16), ~135 LOC en total. Bien por debajo del tope de 400 líneas.

## Fase 4 — Post-fusión

### 17. Entrada en `learn-es` (tras PR #3 verde en `develop`)

- [x] 17.1 Escribir `/learn-es/2026-08-19-descendant-counts-projection.md` según la estructura de AGENTS.md §2 (Qué / Cómo / Dónde / Por qué / Cómo funciona / Workflows) en español neutro/profesional. Disparador: PR #3 se fusiona verde a `develop`.
- [x] 17.2 Commit convencional: `docs(learn-es): entry for descendant-counts-projection change`.

## Ruta crítica

1. **PR #1** (6 commits, ~270 LOC) — esquema + ORM + `register_display_level` + andamiaje CLI `apply-projection` + prueba de engine pelado. Primer PR de la cadena.
2. **PR #2** (5 commits, ~440 LOC, borderline) — módulo `projections.py`: `lookup_one`, `lookup_many`, `_projected_parent_ids`, `materialize_for_parent`, `materialize_all`, guarda de presupuesto SLO. Requiere PR #1 en `develop`.
3. **PR #3** (5 commits, ~135 LOC) — pre-chequeo de caché en `tree.py` + pre-carga por lotes en `_tree_tiers.py` + reconstrucción de `import_data` + poda de `Out of Scope` + arnés de regresión. Requiere PR #2 en `develop`.

## Referencia de convenciones

- Commits convencionales según `AGENTS.md §3`; mensaje en inglés; sin atribución de IA.
- Un worktree por PR en `../taxon-worktrees/descendant-counts-projection-pr{1..3}`; base = `develop`; nunca commitear a `main`.
- TDD estricto según `openspec/config.yaml`: cada tarea de producción tiene una prueba RED-first antes del GREEN.
- Los commits RED se entregan primero como commits independientes para que el commit GREEN muestre el diff con claridad.
- Solo secuencial: sin escritores en paralelo, sin PRs en paralelo. Un worktree a la vez.
- Espejo en español de este archivo: `documents-es/openspec/descendant-counts-projection/tasks-es.md` (creado al momento de escritura, traducción fiel, registro neutro/profesional).
- El espejo en español de cada PR que lleva artefactos aterriza en el MISMO PR según AGENTS.md §1.
- Puerta previa al PR: no se necesita revisión de Pencil MCP / `impeccable` — cambio solo de backend.

## Decisiones abiertas que requieren entrada del usuario

El orquestador presentará la siguiente decisión antes de `sdd-apply` porque la estrategia de entrega es `ask-on-risk` y el PR #2 está borderline en ~440 LOC (40 líneas por encima del tope de 400):

**¿Qué estrategia de cadena debemos usar para la cadena de 3 PRs?**

| Opción | Compromiso |
|--------|----------|
| `stacked-to-main` | Cada PR se fusiona a `develop` en orden. Iteración rápida. El riesgo sobre el presupuesto del PR #2 se mitiga con la división por `work-unit-commits` por commit (cada commit hijo ≤ 400 LOC). |
| `feature-branch-chain` | La rama tracker `feature/projection` acumula la integración. PR #1 apunta al tracker, PR #2 apunta a la rama de PR #1, PR #3 apunta a la rama de PR #2. Solo el tracker se fusiona a `develop`. Mejor para control de reversión. |
| `size:exception` | PR único con aprobación del maintainer. El más rápido pero pierde el foco por PR. Solo viable si el revisor está cómodo revisando ~845 LOC de una sola vez. |

El usuario debe elegir una antes de que corra `sdd-apply`.
