# Especificación: descendant-counts-projection

## Propósito

La capacidad `descendant-counts-projection` persiste una tabla `taxon_descendant_counts` que almacena en caché `(species_count, total_count)` para cada taxón padre cuyo `direct_children_count` supera `SPECIES_COUNT_LAZY_NULL_THRESHOLD`. La caché permite a `/api/tree/children` servir `species_count` en O(1) para esos padres (actualmente `Animalia`, `Eukaryota` y `Methanobacteriota`) en lugar de devolver `None` porque el CTE recursivo es demasiado costoso para ejecutarse bajo demanda. Las filas se pueblan sincrónicamente en la primera lectura de cada padre proyectado, se mantienen en caché durante la vida útil de la base de datos, y las reconstruye `import_data` tras una re-importación de CoL. Un subcomando independiente `python -m taxon.migrate apply-projection` vuelve a ejecutar la proyección bajo demanda.

## Requisitos

### Requisito: El esquema contiene una fila por cada padre proyectado

El sistema DEBE persistir una tabla `taxon_descendant_counts` con una fila por cada taxón cuyo `direct_children_count` supere `SPECIES_COUNT_LAZY_NULL_THRESHOLD`. La fila DEBE llevar `taxon_id` (PRIMARY KEY, FK hacia `taxa.id`), `species_count` (INT, descendientes con `rank='species'`), `total_count` (INT, todos los nodos descendientes) y `computed_at` (TIMESTAMP, reloj de pared al reconstruir). La tabla DEBE crearse mediante `taxon.migrate apply` vía `Base.metadata.create_all` y NO DEBE requerir Alembic.

#### Escenario: Una base de datos nueva obtiene la tabla al aplicar

- DADO una base de datos SQLite sin la tabla `taxon_descendant_counts`
- CUANDO el operador ejecuta `python -m taxon.migrate apply`
- ENTONCES la tabla existe con las cuatro columnas anteriores
- Y las tablas preexistentes `taxa` y `species_paths` quedan inalteradas

#### Escenario: Las filas preexistentes sobreviven al aplicar

- DADO una base de datos SQLite con `taxa` poblada
- CUANDO el operador ejecuta `python -m taxon.migrate apply`
- ENTONCES la tabla se crea si falta
- Y las filas preexistentes de `taxa` no se eliminan, alteran ni duplican

### Requisito: La primera lectura materializa la fila sincrónicamente

El sistema DEBE consultar `taxon_descendant_counts` antes del umbral y del CTE recursivo para cada padre cuyo `direct_children_count` supere `SPECIES_COUNT_LAZY_NULL_THRESHOLD`. Ante una falta de caché, el sistema DEBE ejecutar una reconstrucción sincrónica para ese padre dentro de la misma solicitud, escribir la fila resultante y devolver el `species_count` reconstruido. Ante un acierto de caché, el sistema DEBE devolver el `species_count` en caché sin invocar el umbral ni el CTE recursivo.

#### Escenario: La primera solicitud para Animalia materializa la fila

- DADO que no existe una fila en `taxon_descendant_counts` para `Animalia`
- CUANDO el endpoint del árbol sirve los hijos de `Animalia`
- ENTONCES la respuesta incluye `species_count` igual al conteo reconstruido
- Y después existe una fila en `taxon_descendant_counts` con ese `taxon_id`
- Y `computed_at` queda fijado al reloj de pared de la reconstrucción

#### Escenario: Las lecturas posteriores devuelven la fila en caché

- DADO que existe una fila en `taxon_descendant_counts` para `Animalia`
- CUANDO el endpoint del árbol sirve los hijos de `Animalia`
- ENTONCES la respuesta incluye `species_count` desde la fila en caché
- Y el CTE recursivo no se invoca
- Y `computed_at` no se modifica

### Requisito: La regla de población es una fila por cada padre que supera el umbral

El sistema DEBE poblar una fila por cada taxón cuyo `direct_children_count` supere `SPECIES_COUNT_LAZY_NULL_THRESHOLD`. Los padres por debajo del umbral NO DEBEN recibir fila. La decisión DEBE leer la misma constante `SPECIES_COUNT_LAZY_NULL_THRESHOLD` que lee el umbral, para que ambas rutas nunca discrepen.

#### Escenario: Los padres que superan el umbral obtienen filas

- DADO tres padres que superan el umbral (`Animalia`, `Eukaryota`, `Methanobacteriota`)
- CUANDO el operador ejecuta `python -m taxon.migrate apply-projection`
- ENTONCES la tabla contiene exactamente tres filas después de la ejecución
- Y el `taxon_id` de cada fila coincide con uno de los tres padres

#### Escenario: Los padres por debajo del umbral no obtienen fila

- DADO un padre con menos hijos directos que el umbral
- CUANDO el operador ejecuta `python -m taxon.migrate apply-projection`
- ENTONCES la tabla NO contiene una fila para ese padre
- Y una solicitud posterior del árbol para él cae al camino existente de umbral + CTE

### Requisito: La reconstrucción está acotada por el SLO por solicitud

El sistema DEBE acotar la reconstrucción sincrónica para que el endpoint del árbol cumpla su SLO por solicitud (1 s para `/api/tree/children`). Si el costo previsto o medido de la reconstrucción supera el presupuesto, el sistema DEBE caer al camino existente de CTE por lotes, omitir la escritura y dejar que el llamante observe `species_count=None` en la primera solicitud — el mismo comportamiento que devuelve el código previo al cambio.

#### Escenario: La reconstrucción dentro del presupuesto escribe la fila

- DADO que no existe una fila en caché para `Animalia`
- Y el costo previsto de la reconstrucción para `Animalia` está por debajo del presupuesto de 1 s
- CUANDO el endpoint del árbol sirve los hijos de `Animalia`
- ENTONCES la respuesta incluye un `species_count` numérico
- Y después existe una fila en `taxon_descendant_counts`

#### Escenario: La reconstrucción por encima del presupuesto omite la escritura

- DADO que no existe una fila en caché para un padre cuya reconstrucción prevista excede el presupuesto
- CUANDO el endpoint del árbol sirve los hijos de ese padre
- ENTONCES la respuesta incluye `species_count=None`
- Y no se escribe ninguna fila en `taxon_descendant_counts`
- Y la siguiente solicitud toma el mismo camino de respaldo hasta que la fila aparezca

### Requisito: `import_data` reconstruye cada padre proyectado tras una re-importación de CoL

El sistema DEBE reconstruir cada fila de `taxon_descendant_counts` como último paso de una re-importación de CoL exitosa invocada mediante `python -m taxon.import_data`. La reconstrucción DEBE hacer upsert de una fila por cada padre que supere el umbral y DEBE ser idempotente — ejecutarla dos veces sobre el mismo conjunto de datos DEBE dejar la tabla en el mismo estado.

#### Escenario: La re-importación de CoL deja la tabla fresca

- DADO que una re-importación de CoL finaliza correctamente
- CUANDO el script de importación retorna
- ENTONCES `taxon_descendant_counts` contiene una fila por cada padre que supera el umbral en el nuevo conjunto de datos
- Y el `computed_at` de cada fila es posterior al inicio de la importación

#### Escenario: La reconstrucción es idempotente sobre el mismo conjunto de datos

- DADO que `taxon_descendant_counts` ya refleja el conjunto de datos actual
- CUANDO el operador ejecuta `python -m taxon.import_data` (o re-importación equivalente) dos veces
- ENTONCES el conteo de filas no cambia tras ambas ejecuciones
- Y los valores de `species_count` y `total_count` no cambian entre ejecuciones

### Requisito: El subcomando `apply-projection` vuelve a ejecutar la proyección bajo demanda

El sistema DEBE exponer `python -m taxon.migrate apply-projection` como salida de escape manual. El subcomando DEBE escanear cada taxón cuyo `direct_children_count` supere `SPECIES_COUNT_LAZY_NULL_THRESHOLD`, hacer upsert de una fila por padre y salir con código cero en caso de éxito. Ejecutar el subcomando NO DEBE requerir una ejecución completa de `import_data` y DEBE ser seguro de invocar sobre una base de datos cuyas filas en caché estén obsoletas (por ejemplo, tras un cambio SQL manual o una restauración desde respaldo).

#### Escenario: La tabla obsoleta se recupera mediante apply-projection

- DADO que `taxon_descendant_counts` falta o está obsoleta (por ejemplo, filas anteriores a la mutación más reciente de `taxa`)
- CUANDO el operador ejecuta `python -m taxon.migrate apply-projection`
- ENTONCES la tabla se repuebla con una fila por cada padre actual que supera el umbral
- Y el `computed_at` de cada fila es el reloj de pared de la ejecución de apply-projection

#### Escenario: apply-projection es idempotente

- DADO que `taxon_descendant_counts` ya refleja el conjunto de datos actual
- CUANDO el operador ejecuta `python -m taxon.migrate apply-projection`
- ENTONCES el conteo de filas no cambia
- Y `species_count` y `total_count` de cada fila coinciden con los valores anteriores
- Y el script sale con código cero

### Requisito: El esquema se añade sin tocar las bases de datos legadas

El sistema DEBE tratar la proyección como puramente aditiva: los archivos `taxon.db` legados que carezcan de `taxon_descendant_counts` DEBEN seguir funcionando como si el cambio no existiera. La superficie de `/api/tree/children` NO DEBE cambiar (sin nuevos parámetros de consulta, sin nuevas claves en la respuesta, sin renombrados). Sobre una base de datos que carezca de la tabla, el camino de lectura DEBE detectar la ausencia y caer al camino existente de umbral + CTE.

#### Escenario: Una base de datos legada sirve las mismas respuestas que antes

- DADO un `taxon.db` sin `taxon_descendant_counts`
- CUANDO el endpoint del árbol sirve los hijos de cualquier padre
- ENTONCES la forma de la respuesta es idéntica al comportamiento previo al cambio
- Y para los padres por encima del umbral, `species_count=None` (igual que antes del cambio)

#### Escenario: Una base de datos legada pasa a ser consciente de la caché tras aplicar

- DADO un `taxon.db` sin `taxon_descendant_counts`
- CUANDO el operador ejecuta `python -m taxon.migrate apply`
- ENTONCES la tabla existe
- Y la siguiente solicitud para un padre que supera el umbral materializa una fila

## Fuera de alcance

- Un nuevo endpoint público — la proyección es interna; `/api/tree/children` no cambia.
- Una herramienta de migración de esquemas más allá de `taxon.migrate apply` — Alembic sigue fuera de alcance.
- Backends no SQLite — SQLite es el único destino.
- Un TTL en las filas en caché — `computed_at` es solo observabilidad; ninguna fila expira.
- Un cambio en `SPECIES_COUNT_LAZY_NULL_THRESHOLD` — la proyección adopta el valor que ya usa el umbral.
- Trabajo de frontend — la interfaz sigue mostrando `?` hasta que la caché resuelva; no hay cambios en el cliente.
- Una columna desnormalizada `species_count` en `taxa` — la proyección es su propia tabla.