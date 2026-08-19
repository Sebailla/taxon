# Propuesta: descendant-counts-projection

## Intención

`/api/tree/children` devuelve `species_count=None` para cualquier taxón padre cuyo conteo de hijos directos supere `SPECIES_COUNT_LAZY_NULL_THRESHOLD` (1M). En el árbol de CoL, `Animalia`, `Eukaryota` y `Methanobacteriota` son los únicos padres en esa situación hoy; la interfaz muestra `?` para "cantidad de descendientes" en esas filas de forma indefinida. El CTE recursivo que calcula el conteo es demasiado costoso para ejecutarse bajo demanda en cualquiera de ellos, así que permanecen como lazy-null hasta el próximo cambio de especificación o de esquema.

Materializamos una nueva tabla `taxon_descendant_counts` que almacena en caché `(species_count, total_count)` exactamente para los padres que superan el umbral y servimos `species_count` desde la caché en cada lectura. La primera petición de un padre que necesita la proyección dispara una reconstrucción síncrona; cada petición posterior (y cada reinicio) lee la fila cacheada. `import_data` reconstruye la caché tras una reimportación de CoL para que la proyección esté siempre fresca en el siguiente arranque; `python -m taxon.migrate apply-projection` se conserva como vía de escape manual.

## Alcance

### Dentro del Alcance
- Nueva tabla SQLAlchemy `taxon_descendant_counts(taxon_id PK, species_count INT, total_count INT, computed_at TIMESTAMP)` creada por `taxon.migrate` para que el ciclo de vida coincida con el resto de las tablas del workspace.
- Helper `_rebuild_descendant_counts(taxon_id)` que recorre el subárbol una vez y hace upsert de la fila. Limitado por la población de descendientes, no por toda la tabla `taxa`.
- Materialización bajo demanda: la primera llamada a `_count_descendant_species(session, parent_id)` para un padre con `direct_children_count > SPECIES_COUNT_LAZY_NULL_THRESHOLD` ejecuta la reconstrucción síncrona y escribe la fila. Las llamadas siguientes (y los reinicios) leen la tabla.
- Ruta de lectura: `_count_descendant_species` consulta primero la tabla; ante un acierto devuelve `species_count` directamente sin invocar la guarda de umbral ni el CTE recursivo. Ante un fallo de caché para cualquier otro padre se conserva el comportamiento actual de umbral + CTE.
- `_batch_species_counts` honra la misma caché: una sola lectura por `parent_id` del lote, sin CTE.
- `import_data` invoca la reconstrucción para todo padre con `direct_children_count > SPECIES_COUNT_LAZY_NULL_THRESHOLD` después de una reimportación de CoL.
- Subcomando `python -m taxon.migrate apply-projection` para reejecuciones manuales sin reimportación completa.
- Pruebas red-first en `taxon/tests/test_descendant_counts_projection.py`; el precedente más cercano es `taxon/tests/test_species_count_lazy_null.py`.
- Espejo en español en `documents-es/openspec/descendant-counts-projection/proposal-es.md` según AGENTS.md §1.

### Fuera del Alcance
- Ningún endpoint público nuevo; la superficie de la API (`/api/tree/children`) no cambia.
- Ninguna migración de esquema para archivos `taxon.db` antiguos; la proyección es puramente aditiva.
- Ningún backend distinto de SQLite en este cambio.
- Ningún cambio en `SPECIES_COUNT_LAZY_NULL_THRESHOLD`.
- Ningún TTL sobre la fila cacheada; la invalidación ocurre solo vía `import_data` y el subcomando manual.
- Ningún trabajo de frontend; la UI ya renderiza un conteo numérico cuando `species_count` no es `None`.

## Capacidades

### Nuevas Capacidades
- `descendant-counts-projection`: una proyección persistente y materializada de forma perezosa de `(species_count, total_count)` indexada por `taxon_id`, que cubre exactamente los padres cuyo conteo de hijos directos supera `SPECIES_COUNT_LAZY_NULL_THRESHOLD`. Requiere spec completa nueva.

### Capacidades Modificadas
- `taxonomic-tree-browse`: `_count_descendant_species` y `_batch_species_counts` leen `taxon_descendant_counts` antes de la guarda de umbral y del CTE recursivo. La superficie del conteo de especies deja de ser lazy-null para los padres proyectados en el momento en que aterriza la primera petición. Requiere spec delta.

## Enfoque

Un único PR de backend, rama desde `develop`, dirigido a `develop`.

1. **Esquema.** Añadir `TaxonDescendantCount` a `taxon/schema.py`; extender `Base.metadata` para que `taxon.migrate apply` lo recoja mediante `create_all`. Las decisiones de índices compuestos se difieren a sdd-spec.
2. **Helper de reconstrucción.** `_rebuild_descendant_counts(session, parent_id)` ejecuta el CTE recursivo existente (el mismo que ya usa `_count_descendant_species`) una vez y hace upsert de la fila. Envuelto en una única transacción para que una escritura parcial nunca envenene la caché.
3. **Lectura de caché.** `_count_descendant_species` incorpora una consulta previa: `SELECT species_count FROM taxon_descendant_counts WHERE taxon_id = :pid`. Acierto → devuelve el número. Fallo → continúa por la ruta de umbral + CTE existente; en la rama de umbral, ejecuta la reconstrucción síncrona y escribe la fila antes de devolver. El dict `_cache` con alcance de petición se conserva.
4. **Ruta por lotes.** `_batch_species_counts` lanza un `SELECT taxon_id, species_count FROM taxon_descendant_counts WHERE taxon_id IN (...)` antes del trabajo del CTE existente y luego resuelve los padres restantes como hoy.
5. **Presupuesto de reconstrucción.** La reconstrucción síncrona debe completarse dentro del SLO por petición (1s para `/api/tree/children`). Si la reconstrucción excediera el presupuesto, se recurre a la ruta de CTE por lotes existente y se omite la escritura. La decisión es local al helper y se manifiesta como `species_count=None` en la primera petición.
6. **Invalidación.** `taxon/import_data.py` reconstruye la proyección para todo padre con `direct_children_count > SPECIES_COUNT_LAZY_NULL_THRESHOLD` tras una reimportación de CoL exitosa. `taxon/migrate.py` incorpora un subcomando `apply-projection` que itera el mismo conjunto de padres y reconstruye cada fila.
7. **Pruebas.** Red-first en `taxon/tests/test_descendant_counts_projection.py`: acierto de caché devuelve desde la tabla sin CTE; fallo de caché reconstruye y escribe; fallo de reconstrucción deja la tabla intacta; `_batch_species_counts` combina filas cacheadas con resultados del CTE; `import_data` dispara la reconstrucción; el subcomando `apply-projection` es idempotente.

## Áreas Afectadas

| Área | Impacto | Descripción |
|------|---------|-------------|
| `taxon/schema.py` | Modificado | Nueva clase ORM `TaxonDescendantCount` en `Base.metadata`. |
| `taxon/api/tree.py` | Modificado | `_count_descendant_species` lee la tabla primero; la rama de umbral dispara una reconstrucción síncrona. |
| `taxon/api/_tree_tiers.py` | Modificado | `_batch_species_counts` precarga filas cacheadas de la tabla antes de ejecutar el CTE. |
| `taxon/import_data.py` | Modificado | Reconstruye la proyección para todo padre con `direct_children_count > SPECIES_COUNT_LAZY_NULL_THRESHOLD` tras una reimportación de CoL. |
| `taxon/migrate.py` | Modificado | Nuevo subcomando `apply-projection`. |
| `taxon/api/_projection.py` | Nuevo | `_rebuild_descendant_counts`, `_diff_threshold_parents`, helpers de la capa de caché. |
| `taxon/tests/test_descendant_counts_projection.py` | Nuevo | Pruebas red-first para la caché, la reconstrucción y la caída al SLO. |
| `taxon/tests/test_species_count_lazy_null.py` | Modificado | Las pruebas existentes se mantienen en verde; el comportamiento de umbral no cambia para padres no proyectados. |
| `openspec/specs/descendant-counts-projection/spec.md` | Nuevo | Spec completa para la capacidad de proyección. |
| `openspec/specs/taxonomic-tree-browse/spec.md` | Modificado | El delta añade la ruta de lectura con caché en `_count_descendant_species`. |
| `documents-es/openspec/descendant-counts-projection/proposal-es.md` | Nuevo | Espejo en español según AGENTS.md §1. |
| `learn-es/2026-08-19-descendant-counts-projection.md` | Nuevo | Entrada de aprendizaje tras el merge. |

## Riesgos

| Riesgo | Probabilidad | Mitigación |
|--------|--------------|------------|
| La latencia de la primera petición de un padre que dispara una reconstrucción síncrona supera el SLO de 1s de `/api/tree/children`. | Media | La reconstrucción está limitada por la población de descendientes de un único padre; si el coste previsto excede el presupuesto, el helper cae a la ruta de CTE por lotes existente y omite la escritura. La decisión queda documentada en la spec. |
| La caché de `taxon_descendant_counts` queda obsoleta tras una reimportación que no pasa por `import_data` (SQL manual, restauración desde backup). | Baja | El subcomando `apply-projection` es la vía de escape documentada; la columna `computed_at` del esquema hace que la obsolescencia sea observable. |
| La proyección apunta a los mismos padres que `SPECIES_COUNT_LAZY_NULL_THRESHOLD`; el desfase entre ambos produciría conteos inconsistentes. | Baja | Ambas rutas leen la misma constante de umbral desde `taxon/api/tree.py`; una única fuente de verdad las mantiene sincronizadas. |

## Plan de Rollback

El riesgo de PR destructivo es bajo porque el cambio es puramente aditivo: la nueva tabla convive con `taxa` y la ruta de lectura cae al CTE existente cuando la fila falta. **Rollback en caliente**: `git revert <merge-commit>` en `develop`; la tabla puede eliminarse con `DROP TABLE taxon_descendant_counts;` y la ruta de lectura vuelve al comportamiento previo al cambio. **Rollback completo** cuando el revert no sea viable: eliminar la tabla, revertir `taxon/api/tree.py`, `taxon/api/_tree_tiers.py`, `taxon/import_data.py`, `taxon/migrate.py` y borrar `taxon/api/_projection.py` junto al nuevo archivo de pruebas en un único PR de seguimiento ramificado desde un commit conocido como válido en `develop`. La semántica de `SPECIES_COUNT_LAZY_NULL_THRESHOLD` no cambia, de modo que la UI vuelve a lazy-null para los padres proyectados sin más código.

## Dependencias

- `taxon.schema.Base` y `taxon.migrate.create_all` para la nueva tabla (sin Alembic).
- El CTE recursivo existente en `taxon/api/tree.py` se reutiliza dentro del helper de reconstrucción; no se introduce SQL nuevo.
- Hook post-importación en `taxon/import_data.py`.
- `pytest` + `httpx` (ya en las dependencias) para las pruebas nuevas.
- Worktree en `../taxon-worktrees/descendant-counts-projection` desde `develop`.

## Criterios de Éxito

- [ ] `_count_descendant_species` devuelve `species_count` desde `taxon_descendant_counts` para `Animalia`, `Eukaryota` y `Methanobacteriota` tras la primera petición; ningún CTE se ejecuta en lecturas posteriores.
- [ ] La latencia de la primera petición de un padre proyectado se mantiene por debajo del SLO de 1s de `/api/tree/children`; la ruta de caída se ejercita cuando no se cumple.
- [ ] `python -m taxon.migrate apply` crea `taxon_descendant_counts` en una base de datos nueva.
- [ ] `python -m taxon.migrate apply-projection` reconstruye todo padre que supere el umbral y es idempotente en una segunda ejecución.
- [ ] `import_data` dispara la reconstrucción para todo padre que supere el umbral tras una reimportación de CoL.
- [ ] Todas las pruebas en `taxon/tests/test_descendant_counts_projection.py` y `taxon/tests/test_species_count_lazy_null.py` pasan en verde en `develop`.
- [ ] Entrada `/learn-es/2026-08-19-descendant-counts-projection.md` creada tras CI en verde.
