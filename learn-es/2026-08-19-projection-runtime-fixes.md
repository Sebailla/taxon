# Projection lifespan bootstrap, budget bump, and commit boundary

## What

Tres fixes de runtime del change `descendant-counts-projection` (PR #86), descubiertos al levantar el server con `data/col.db` real y observar el comportamiento end-to-end. El change original pasó 285 tests pero la projection nunca se pobló en producción.

## How

- `taxon/api/__init__.py` — el `_lifespan` solo creaba las 3 `WORKSPACE_TABLES` en file-backed SQLite. La tabla `taxon_descendant_counts` no existía, y la primera request que intentaba materializar crasheaba con `OperationalError: no such table`. Widened: `Base.metadata.create_all(engine, tables=...)` ahora cubre `WORKSPACE_TABLES + PROJECTION_TABLES`, mismo patrón que `taxon.migrate._run_apply` ya tenía.
- `taxon/api/projections.py:REBUILD_BUDGET_SECONDS` — de 1.0s a 15.0s. El wall-clock real de un CTE walk sobre Eukaryota (5.6M descendants) en una máquina de desarrollo es 5-15s. Con 1.0s el SLO guard siempre disparaba y la projection quedaba vacía.
- `taxon/api/projections.py:materialize_for_parent` — reemplazó `session.flush()` por `session.commit()` después del upsert. El flush pone la row en la unidad-de-trabajo pero `taxon.api.db.get_db` cierra la sesión sin commit en teardown, lo que rollbackea la row. El commit interno es atómico por parent_id; callers que necesitan multi-step transaction deben usar `session.begin()` explícito.
- `taxon/tests/test_api_app.py` — dos tests red-first nuevos: `test_file_backed_lifespan_creates_projection_table` y `test_rebuild_budget_default_is_15_seconds`.

## Where

- `taxon/api/__init__.py:_lifespan` — la rama file-backed ahora incluye `PROJECTION_TABLES` en `create_all`.
- `taxon/api/projections.py:REBUILD_BUDGET_SECONDS` — 1.0 → 15.0.
- `taxon/api/projections.py:materialize_for_parent` — `session.flush()` → `session.commit()` en el upsert.
- `taxon/tests/test_api_app.py` — 2 tests nuevos, 46 LOC.

## Why

Los 285 tests del PR #86 pasaban porque los tests ejercitan los helpers vía bloques `session.begin()` o commits explícitos en setup. El path real (request HTTP) no commitea, así que `materialize_for_parent` escribía la row, el SLO guard la aceptaba, y la row se perdía cuando `get_db` cerraba la sesión. Lo mismo con `import_data._rebuild_descendant_counts_projection` — imprimía "Rebuilt N rows" pero la tabla quedaba vacía.

El `REBUILD_BUDGET_SECONDS = 1.0` era un optimistic guess sin medición real. El primer request a un padre sobre el umbral pagaba el rebuild, pero el CTE walk sobre el subtree real tarda más que 1s, así que la row nunca llegaba. 15s es el wall-clock observado en el runtime harness.

El lifespan bug era un oversight de scope: `taxon.migrate._run_apply` ya había sido widened para incluir `PROJECTION_TABLES` (PR #86), pero el `_lifespan` no recibió el mismo tratamiento. El design phase no marcó la asimetría.

## How it works en producción

1. Server arranca, `_lifespan` corre.
2. Para file-backed SQLite: `Base.metadata.create_all(engine, tables=managed_table_objs)` donde `managed_table_objs = [*WORKSPACE_TABLES, *PROJECTION_TABLES]`. Idempotente: si la tabla ya existe, no hace nada.
3. Cliente hace `GET /api/tree/children?parent_id=X` para un padre con >threshold directos.
4. `_count_descendant_species(X)` llama `lookup_one(session, X)` → cache miss.
5. Threshold guard fires → `materialize_for_parent(session, X)` corre la CTE recursiva, mide elapsed, y si cabe en 15s, escribe la row con `session.commit()`.
6. Request termina, `get_db` cierra la sesión — la row está persistida porque el commit ocurrió dentro del materialize.
7. Próxima request para el mismo parent: `lookup_one` devuelve el cached value en O(1).

## Workflows

- CI: 287 tests pass, 1 skipped (mismo skip que antes). ruff, format, mypy verdes.
- Operador: ya no necesita `python -m taxon.migrate apply` antes de arrancar — el lifespan lo hace.
- Runtime: el primer request para un padre sobre el threshold tarda hasta 15s (rebuild síncrono). El segundo es instant.

## Aprendido

- **Tests que no ejercitan el path completo son trampas.** Los tests del PR #86 usaban `session.begin()` o commits explícitos, así que el bug del `flush()` sin `commit()` nunca se manifestó. Un test que ejercite el path de la request completa (TestClient con lifespan) habría detectado el bug en CI.
- **Lifespan asymmetry entre FastAPI factory y migrate CLI es fácil de pasar por alto.** El design phase debe marcar explícitamente "ambos entry points deben crear la tabla X", no asumir simetría.
- **El threshold de 1M directos no captura ningún taxón del CoL real.** El max de directos en CoL es 94,443 (Cecidomyiidae). La projection NUNCA se activa en producción con este threshold. Esto es un bug de design, no de implementación — un follow-up proposal necesita redefinir el threshold como "total descendants > 1M" o un predicate distinto. El runtime test lo descubrió inmediatamente; los tests unit no.
- **Conventional commits saved time en debugging.** El PR body listó los 3 commits con sus concerns separados, así que el reviewer puede hacer checkout de cualquiera sin reordenar.
- **El fix de "1s → 15s" sigue siendo optimista.** Eukaryota tarda 12.5s. Si el dataset crece a 10M descendants, el threshold de 15s vuelve a quedar corto. Una mejor solución de fondo es async (fire-and-forget rebuild) o job scheduler — la siguiente iteración.
EOF