# Cascade resolver: display_level computed at query time (PR #62)

## Qué

El resolver de cascada añadido en el PR #58 filtraba filas de taxonomía por la columna `Taxon.display_level`. El importador indented (`taxon.indented_import`, GBIF Backbone / CLB) deja esa columna en `NULL` por diseño — decisión documentada en el docstring del módulo, líneas 22-24. El resultado: la cascada devolvía 404 para cualquier linaje sembrado por el importador indented. El PR #62 cierra el gap computando el bucket de display en tiempo de query, no desnormalizando.

## Cómo

Tres piezas se modificaron en lockstep.

**1. Registrar la función Python como SQL function.** En `taxon/api/__init__.py:_build_engine`, una sola línea enganchada al evento `connect` del engine SQLAlchemy:

```python
@event.listens_for(engine, "connect")
def _register_sqlite_functions(dbapi_connection, _):
    conn = dbapi_connection
    conn.create_function("taxonomy_display_level", 1, display_level)
```

El registro aplica a cualquier engine que la fábrica construya (StaticPool en memoria para tests, SQLite en archivo para producción). No hay un solo punto de verdad para esto más arriba — la fábrica `_build_engine` es ese punto.

**2. Construir el `case` que coalesce columna o función.** En `taxon/api/hierarchy.py`, helper nuevo:

```python
def _effective_display_level() -> Case[str | None]:
    return case(
        (Taxon.display_level.isnot(None), Taxon.display_level),
        else_=func.taxonomy_display_level(Taxon.rank),
    )
```

Devuelve un `Case[str | None]` para que mypy acepte la expresión sin rehuir el modo estricto.

**3. Cambiar el filtro en el resolver.** Donde antes había `func.lower(Taxon.display_level) == bucket.lower()`, ahora hay `func.lower(_effective_display_level()) == bucket.lower()`. Un solo call site en `hierarchy.py:resolve_path_by_display_level`.

## Dónde

- `taxon/api/__init__.py` — `+19 / -2` líneas. Registra la SQL function en `_build_engine`.
- `taxon/api/hierarchy.py` — `+30 / -3` líneas. Añade `_effective_display_level()`, reemplaza el filtro en `resolve_path_by_display_level`.
- `taxon/api/sqlite_resolver.py` — `+5 / -17` líneas. Actualiza el docstring del módulo (elimina el párrafo "Gotcha" porque ya no aplica).
- `taxon/tests/test_api_sqlite_only_indented_fixtures.py` — `+165` líneas, archivo nuevo. Tres tests:
  - `test_indented_seeded_rows_have_null_display_level`: pinea la premisa de diseño del importador.
  - `test_path_children_resolves_phylum_through_indented_seed`: RED antes del fix, GREEN después.
  - `test_species_list_resolves_genus_through_indented_seed`: RED antes, GREEN después.

## Por qué

La opción "rellenar la columna en el importer" estaba descartada desde el principio: contradice el docstring del módulo `indented_import`. Su comentario líneas 22-24 es explícito: "is intentionally left null by the importer — `taxon.taxonomy.display_level` is applied at query time, matching the historical WoRMS importer". Forzar la desnormalización revertiría una decisión deliberada y arrastraría un segundo problema (toda extensión futura a `RANK_TO_DISPLAY_LEVEL` exige un reimport del árbol entero).

La opción "computar en Python tras la query" también se descartó: el resolver ya tiene varias queries encadenadas y un loop para los roll-ups de phylum y familia. Insertar un `if row.display_level is None: row.display_level = display_level(row.rank)` post-fetch dispersa la lógica en tres lugares. La SQL function aplica el coalesce por fila en el mismo plan de ejecución.

La opción "registrar la función y usar `case`" deja una sola decisión concentrada en `_effective_display_level()`. Si mañana cambia el shape (por ejemplo, agregar una jerarquía de buckets), un solo lugar para editar.

## Cómo funciona

1. La cascada UI pide `/api/path-children?path=Biota|Animalia`.
2. El handler llama `resolve_path_by_display_level(session, ["Animalia"])`.
3. La query SQL resultante es, simplificada:
   ```sql
   SELECT * FROM taxa
   WHERE lower(name) = 'animalia'
     AND lower(CASE WHEN display_level IS NOT NULL
                    THEN display_level
                    ELSE taxonomy_display_level(rank)
               END) = 'kingdom'
   ```
4. Para filas sembradas por `taxon.import_data` (WoRMS DwC-A), la columna está poblada y el `case` la devuelve.
5. Para filas sembradas por `taxon.indented_import` (GBIF/CLB), la columna es `NULL` y la SQL function `taxonomy_display_level('kingdom')` devuelve `'kingdom'`.
6. El resto de la cascada ve el mismo bucket en ambos casos y avanza igual.

El `TaxonRow` que el resolver produce hacia el router nunca expuso `display_level` (es interno al `Taxon` ORM); el wire payload (`next_tiers`, `PathChildrenEnvelope`, `SpeciesListResponse`) es byte-for-byte idéntico al del PR #58.

## Workflows

- **CI**: pytest 150 verde (147 baseline + 3 tests nuevos), ruff format check 45 files, ruff check clean, mypy strict sin issues (32 source files, +1 por el archivo de tests). Vitest 69/69.
- **Strict TDD**: los tres tests nuevos son RED-first. Confirmamos el fallo antes del fix corriendo pytest, escribimos el fix, corrimos pytest de nuevo y vimos pasar.
- **Branching**: rama `fix/display-level-query-time` desde `develop`, worktree en `../taxon-worktrees/fix-display-level-query-time`, merge de vuelta por ort tras CI verde.

## Lecciones aprendidas

- **Respetar las decisiones de diseño declaradas en el docstring.** El módulo `indented_import` ya había pensado el trade-off: `display_level` queda NULL porque es una función pura sobre un whitelist estático de 80 rangos. La solución correcta fue adaptarse a la decisión, no revertirla. El docstring actuó como contrato explícito entre módulos.
- **Las SQL functions registradas vía `event.listens_for(engine, "connect")` viven en el dbapi connection, no en el engine.** El handler se ejecuta en cada nueva conexión SQLite que el engine abre. Para StaticPool con `poolclass=StaticPool` eso significa exactamente una (test in-memory); para file-backed, una por proceso hasta el primer reset. Suficiente para el ciclo de vida de pytest.
- **El `case` se evalúa por fila; `coalesce` no.** SQLite evalúa `COALESCE(a, b)` con短路 de la primera expresión no-NULL, pero la SQL function Python solo se invoca cuando SQLite decide evaluar el segundo argumento — y hay versiones donde el call no se hace si la columna devuelve texto vacío en lugar de `NULL`. El `case((cond, expr), else_=fn)` deja explícita la semántica.
- **El vale de la cobertura del resolver.** Los 12 tests contractuales del PR #58 con semillas WoRMS no detectaban el gotcha porque sembraban con el importador que sí poblaba la columna. Cuando el fix necesitó un test que sembrara con el otro importador, fue trivial añadirlo en un archivo aparte. Mantener tests que cubren el contrato del resolver con un importador es un buen patrón; cubrirlos con los dos es mejor.

## Follow-up PRs (no en este commit)

- **Migración de los 12 tests de `test_api_sqlite_only_router.py` y los 3 nuevos de `test_api_sqlite_only_indented_fixtures.py` para que ambos puedan sembrarse con `taxon.indented_import`.** Hoy conviven, pero los de Wiorms siguen necesitando `taxon.import_data`. Es opcional — la coexistencia funciona bien.
- **Run del import GBIF Backbone completo** (7,7 M de filas, ~789 MB). El query-time coalesce elimina la necesidad de un UPDATE post-import, así que el flujo es `import_indented_dataset --database $DB` y listo. Tarea operativa.
