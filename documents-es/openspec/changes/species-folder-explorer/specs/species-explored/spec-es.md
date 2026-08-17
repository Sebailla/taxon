# Especificación: species-explored

## Propósito

La capacidad `species-explored` permite al usuario marcar una especie como explorada, persiste esa marca entre sesiones y sobrevive al churn de re-importación conocido del proyecto al mantener el estado de explorada en una tabla separada en lugar de como una columna en `taxa`. La marca se expone como una casilla en la columna final de cada fila de `SpeciesList`, junto al badge/botón de carpeta de la especificación `species-folder`. Cierra la subcaracterística A del issue #68.

## Requisitos

### Requisito: Marcar la Marca de Explorado es Idempotente

El sistema DEBE exponer `POST /api/explored/{genus}/{epithet}` que hace upsert de una fila en `species_explored` y devuelve HTTP 200 con la fila de especie resuelta (la misma forma que devuelve `species-lookup`). El endpoint DEBE ser idempotente — re-publicar el mismo `(genus, epithet)` NO DEBE lanzar excepción y DEBE refrescar `explored_at` al timestamp actual.

#### Escenario: El primer POST devuelve 200 con la fila de especie

- DADO que `Panthera tigris` se resuelve a una especie
- CUANDO el cliente publica `POST /api/explored/Panthera/tigris`
- ENTONCES la respuesta es HTTP 200
- Y el cuerpo contiene el `id` de la especie, `canonical_name`, `display_name`, `markers` y `breadcrumb`
- Y existe una fila en `species_explored` con `genus="Panthera"`, `epithet="tigris"`

#### Escenario: El POST repetido refresca explored_at

- DADO que existe una fila en `species_explored` para `Panthera tigris`
- CUANDO el cliente publica `POST /api/explored/Panthera tigris` de nuevo
- ENTONCES la respuesta es HTTP 200 (sin 409)
- Y el `explored_at` de la fila se actualiza al nuevo timestamp

### Requisito: Desmarcar la Marca de Explorado Elimina la Fila

El sistema DEBE exponer `DELETE /api/explored/{genus}/{epithet}` que elimina la fila en `species_explored` y devuelve HTTP 204. El endpoint DEBE ser idempotente — eliminar una fila inexistente DEBE devolver 204 (no 404).

#### Escenario: La eliminación de fila existente devuelve 204

- DADO que existe una fila en `species_explored` para `Panthera tigris`
- CUANDO el cliente elimina `DELETE /api/explored/Panthera/tigris`
- ENTONCES la respuesta es HTTP 204
- Y la fila ya no existe

#### Escenario: La eliminación de fila ausente es no-op

- DADO que no existe una fila en `species_explored` para `Panthera tigris`
- CUANDO el cliente elimina `DELETE /api/explored/Panthera/tigris`
- ENTONCES la respuesta es HTTP 204 (sin 404)

### Requisito: Esquema Caminado por `(genus, epithet)` Sobrevive a Re-Importaciones

El sistema DEBE caminar por `(genus, epithet)` en cada lectura y escritura para que las re-importaciones que incrementan `taxa.id` dejen intacta la marca de explorada. La tabla `species_explored` DEBE tener `PRIMARY KEY (genus, epithet)` SIN foreign key a `taxa.id`; el par `(genus, epithet)` es la identidad durable de la fila del workspace. El endpoint resuelve el nombre de la especie vía `resolve_path_by_display_level` y matchea la fila directamente por el par `(genus, epithet)`.

#### Escenario: La re-importación preserva la marca de explorada sin re-vinculación de FK

- DADO que existe una fila en `species_explored` para `(Panthera, tigris)`
- CUANDO el fixture de test muta `taxa.id` para `Panthera tigris` (simulando re-importación)
- Y el cliente solicita `GET /api/explored/list` o inspecciona la fila de otro modo
- ENTONCES `Panthera tigris` aún aparece como explorada
- Y no se requiere operación de re-vinculación (la fila está keyed en `(genus, epithet)`, no en `taxa.id`)

### Requisito: El Endpoint GET /list Hidrata el Workspace

El sistema DEBE exponer `GET /api/explored/list` que devuelve el conjunto completo de exploradas como `{"species": [{"genus": str, "epithet": str, "explored_at": str}, ...]}` con HTTP 200. La lista DEBE estar vacía (no 404) cuando no hay filas. La acción de hidratación del frontend llama a este endpoint en el montaje de la App para que las casillas de explorada reflejen el estado persistido en el primer render.

#### Escenario: Filas existentes devuelven lista

- DADO que `species_explored` tiene filas para `Panthera tigris` y `Panthera leo`
- CUANDO el cliente solicita `GET /api/explored/list`
- ENTONCES el cuerpo contiene ambas entradas con `genus`, `epithet`, `explored_at`

#### Escenario: Sin filas devuelve lista vacía

- DADO que no existen filas en `species_explored`
- CUANDO el cliente solicita `GET /api/explored/list`
- ENTONCES la respuesta es HTTP 200 con `{"species": []}` (arreglo vacío, no 404)

### Requisito: Supervivencia Entre Recargas

El sistema DEBE persistir la marca de explorada en la base de datos SQLite para que una recarga del frontend (refresh del navegador) restaure el mismo estado de casilla. El endpoint de hidratación DEBE ser la única fuente de verdad para el mapa `workspaceStore.exploredBySpeciesId` del frontend; el store NO DEBE mantener una marca solo local no autenticada.

#### Escenario: La recarga restaura el estado de explorada

- DADO que el usuario marca `Panthera tigris` como explorada en la SPA
- Y el usuario refresca el navegador
- CUANDO la SPA se vuelve a montar y la acción `workspaceStore.hydrate()` se ejecuta
- ENTONCES `useWorkspace.getState().exploredBySpeciesId` contiene la entrada para `Panthera tigris`
- Y la fila de `SpeciesList` renderiza la casilla como marcada

## Fuera de Alcance

- Una columna desnormalizada `taxa.is_explored` — evitada explícitamente para sobrevivir al churn de re-importación.
- Sincronización en la nube, multidispositivo, autenticación — SQLite local monousuario según el issue #68.
- Operaciones en lote (marcar todas las especies de un género como exploradas) — toggle de una sola especie.
- Semántica de "explorada" basada en ventana de tiempo o sesión — la marca es binaria y persiste indefinidamente.
- Filtros de workspace a nivel "explorada" (p. ej. mostrar solo especies no exploradas) — la marca se persiste pero ningún filtro de UI está en este alcance.
