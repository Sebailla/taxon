# Delta para taxonomic-tree-browse

## MODIFIED Requirements

### Requisito: Expansión diferida almacena en caché por parent_id

El sistema DEBE obtener los hijos de un taxón padre exactamente una vez por `parent_id` y almacenarlos en caché durante la sesión. Cuando el `direct_children_count` del padre supere `SPECIES_COUNT_LAZY_NULL_THRESHOLD`, el sistema DEBE además consultar `taxon_descendant_counts` (ver `descendant-counts-projection`) antes del umbral y del CTE recursivo, de modo que `species_count` se sirva desde la caché sin invocar el CTE en lecturas posteriores.
(Anteriormente: el umbral devolvía `species_count=None` para cada padre cuyo `direct_children_count` superara el umbral; el CTE recursivo nunca se invocaba para esos padres.)

#### Escenario: La primera solicitud para un padre que supera el umbral dispara la reconstrucción

- DADO que no existe una fila en caché para el padre que supera el umbral en `taxon_descendant_counts`
- CUANDO el usuario expande la fila de ese padre
- ENTONCES el sistema emite `GET /api/tree/children?parent_id={id}` y ejecuta la reconstrucción de la caché en línea
- Y la respuesta incluye un `species_count` numérico
- Y existe una fila en `taxon_descendant_counts` después de la respuesta

#### Escenario: Las solicitudes posteriores leen la fila en caché

- DADO que existe una fila en caché para el padre que supera el umbral
- CUANDO el usuario expande la fila de ese padre
- ENTONCES el sistema emite `GET /api/tree/children?parent_id={id}` y devuelve `species_count` desde la fila en caché
- Y el CTE recursivo no se invoca

#### Escenario: Re-expandir lee la caché

- DADO que el padre ya se expandió
- CUANDO el usuario colapsa y vuelve a expandir
- ENTONCES no se dispara una nueva solicitud y los hijos en caché se renderizan de inmediato

## ADDED Requirements

### Requisito: El camino de lectura consulta la proyección antes del umbral

El sistema DEBE consultar `taxon_descendant_counts` para cada padre cuyo `direct_children_count` supere `SPECIES_COUNT_LAZY_NULL_THRESHOLD` antes de invocar el umbral o el CTE recursivo. Ante un acierto de caché, el sistema DEBE devolver `species_count` desde la fila en caché sin invocar el umbral ni el CTE. Ante una falta de caché, el sistema DEBE caer al camino existente de umbral + CTE; si se dispara la rama de umbral, el sistema DEBE ejecutar la reconstrucción sincrónica (ver `descendant-counts-projection`) y escribir la fila antes de devolver.

#### Escenario: El acierto de caché cortocircuita la rama de umbral

- DADO que existe una fila en `taxon_descendant_counts` para el padre
- CUANDO `_count_descendant_species` se ejecuta para ese padre
- ENTONCES la función devuelve el `species_count` en caché directamente
- Y el umbral no se consulta
- Y el CTE recursivo no se invoca

#### Escenario: La falta de caché cae al camino de umbral + CTE

- DADO que no existe una fila en `taxon_descendant_counts` para el padre
- CUANDO `_count_descendant_species` se ejecuta para ese padre
- ENTONCES el camino existente de umbral + CTE se ejecuta sin cambios
- Y si se dispara la rama de umbral, la reconstrucción escribe la fila antes de devolver

### Requisito: La lectura por lotes precarga las filas en caché

El sistema DEBE precargar las filas en caché desde `taxon_descendant_counts` en una única consulta con `IN`-list por cada lote que sirva el endpoint del árbol. El sistema DEBE fusionar las filas en caché con las filas resueltas por CTE de modo que la respuesta lleve un `species_count` numérico para cada padre en caché y el valor del CTE para cada otro padre. El sistema NO DEBE invocar el CTE recursivo para ningún padre cuya fila en caché esté presente.

#### Escenario: Un lote mixto devuelve conteos en caché y por CTE

- DADO que el lote contiene un padre que supera el umbral con una fila en caché y tres padres por debajo del umbral
- CUANDO `_batch_species_counts` resuelve el lote
- ENTONCES la respuesta lleva el `species_count` en caché para el padre que supera el umbral
- Y la respuesta lleva el `species_count` derivado del CTE para los tres padres por debajo del umbral
- Y el CTE recursivo no se invoca para el padre en caché

#### Escenario: La fila obsoleta en caché gana sobre el CTE

- DADO que existe una fila en caché para el padre
- CUANDO `_batch_species_counts` resuelve el padre
- ENTONCES la respuesta lleva el `species_count` en caché
- Y el valor del CTE (que puede diferir) se descarta

## REMOVED Requirements

### Requisito: El umbral devuelve species_count=None de forma incondicional

(Motivo: el comportamiento de lazy-null para los padres que superan el umbral se reemplaza por el camino de lectura consciente de la caché; la rama de umbral ahora solo se dispara ante una falta de caché, e incluso entonces la reconstrucción cortocircuita a una escritura cuando el costo se mantiene bajo el SLO. Los padres por encima del umbral aún pueden ver `species_count=None` si la reconstrucción excede el presupuesto, pero eso ahora es un estado de respaldo, no el estado estable.)
(Migración: los clientes que toleran `species_count=None` siguen funcionando. Los clientes que necesitan un valor numérico garantizado DEBEN precalentar la caché mediante `python -m taxon.migrate apply-projection` tras cualquier re-importación que no pase por `import_data`.)