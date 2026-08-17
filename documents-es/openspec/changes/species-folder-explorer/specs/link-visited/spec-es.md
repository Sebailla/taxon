# Especificación: link-visited

## Propósito

La capacidad `link-visited` permite al usuario marcar fuentes de búsqueda individuales como visitadas para una especie dada y persiste ese estado entre sesiones para que pueda reanudar una sesión de investigación sin perder progreso. El estado se indexa en `(genus, epithet, source_label)` donde `source_label` es el nombre canónico de `docs/sources/templates.md` (el despacho de 13 enlaces). El estado se almacena en una tabla separada para que los switches de visitada sobrevivan a las re-importaciones de `taxa` mediante la misma disciplina de re-vinculación `(genus, epithet)` que usan las especificaciones hermanas. Cierra la subcaracterística C del issue #68.

## Requisitos

### Requisito: Marcar una Fuente como Visitada es Idempotente

El sistema DEBE exponer `POST /api/link-visited/{genus}/{epithet}/{source}` que hace upsert de una fila `(species_id, source_label)` en `link_visited` y devuelve HTTP 204. El endpoint DEBE ser idempotente — re-publicar el mismo triple NO DEBE lanzar excepción y DEBE refrescar `visited_at` al timestamp actual.

#### Escenario: El primer POST devuelve 204 y persiste

- DADO que `Panthera tigris` se resuelve a una especie y `Wikipedia` está en la lista de plantillas
- CUANDO el cliente publica `POST /api/link-visited/Panthera/tigris/Wikipedia`
- ENTONCES la respuesta es HTTP 204
- Y existe una fila en `link_visited` con `species_id` vinculado a `Panthera tigris` y `source_label="Wikipedia"`

#### Escenario: El POST repetido refresca visited_at

- DADO que existe una fila en `link_visited` para `Panthera tigris / Wikipedia`
- CUANDO el cliente publica `POST /api/link-visited/Panthera/tigris/Wikipedia` de nuevo
- ENTONCES la respuesta es HTTP 204 (sin 409)
- Y el `visited_at` de la fila se actualiza al nuevo timestamp

### Requisito: Desmarcar una Fuente como Visitada Elimina la Fila

El sistema DEBE exponer `DELETE /api/link-visited/{genus}/{epithet}/{source}` que elimina la fila `(species_id, source_label)` y devuelve HTTP 204. El endpoint DEBE ser idempotente — eliminar una fila inexistente DEBE devolver 204 (no 404).

#### Escenario: La eliminación de fila existente devuelve 204

- DADO que existe una fila en `link_visited` para `Panthera tigris / Wikipedia`
- CUANDO el cliente elimina `DELETE /api/link-visited/Panthera/tigris/Wikipedia`
- ENTONCES la respuesta es HTTP 204
- Y la fila ya no existe

#### Escenario: La eliminación de fila ausente es no-op

- DADO que no existe una fila en `link_visited` para `Panthera tigris / Wikipedia`
- CUANDO el cliente elimina `DELETE /api/link-visited/Panthera/tigris/Wikipedia`
- ENTONCES la respuesta es HTTP 204 (sin 404)

### Requisito: Hidratar el Conjunto de Visitadas por Especie

El sistema DEBE exponer `GET /api/link-visited/{genus}/{epithet}` que devuelve el conjunto de visitadas como `{"sources": [{"source": str, "visited_at": str}, ...]}` con HTTP 200. La lista DEBE estar vacía (no 404) cuando no hay filas.

#### Escenario: Filas existentes devuelven lista

- DADO que `link_visited` tiene filas para `Panthera tigris` con fuentes `Wikipedia`, `Google`
- CUANDO el cliente solicita `GET /api/link-visited/Panthera/tigris`
- ENTONCES el cuerpo contiene `{"sources": [{"source": "Wikipedia", ...}, {"source": "Google", ...}]}`

#### Escenario: Sin filas devuelve lista vacía

- DADO que no existen filas en `link_visited` para `Panthera tigris`
- CUANDO el cliente solicita `GET /api/link-visited/Panthera/tigris`
- ENTONCES la respuesta es HTTP 200 con `{"sources": []}` (arreglo vacío, no 404)

### Requisito: El Recorrido `(genus, epithet)` Sobrevive a las Re-Importaciones

El sistema DEBE caminar por `(genus, epithet)` en cada lectura y escritura de link-visited para que las re-importaciones que incrementan `taxa.id` dejen intacto el conjunto de visitadas. La tabla `link_visited` DEBE tener `PRIMARY KEY (genus, epithet, source_label)` SIN foreign key a `taxa.id`; el triple `(genus, epithet, source_label)` es la identidad durable. El endpoint resuelve el nombre de la especie vía `resolve_path_by_display_level` y matchea las filas directamente por el triple.

#### Escenario: El conjunto de visitadas sobrevive al incremento manual de `taxa.id`

- DADO que existen filas en `link_visited` para `(Panthera, tigris, Wikipedia)` y `(Panthera, tigris, Google)`
- CUANDO el fixture de test muta `taxa.id` para `Panthera tigris` (simulando re-importación)
- Y el cliente solicita `GET /api/link-visited/Panthera/tigris`
- ENTONCES la respuesta aún contiene `Wikipedia` y `Google`
- Y no se requiere operación de re-vinculación (la fila está keyed en `(genus, epithet, source_label)`, no en `taxa.id`)

### Requisito: La Etiqueta de Fuente es el Nombre Canónico de la Plantilla

El sistema DEBE indexar el conjunto de visitadas por la cadena `source` de `docs/sources/templates.md` (uno de los 13 nombres canónicos: Wikipedia, Google, BHL, ResearchGate, Plos, Academia, Scielo, Scholar, Youtube, Zootaxa, Photos, Sci-hub, Scribd). El endpoint NO DEBE indexar por la `url` sustituida (las URLs cambian por consulta de especie).

#### Escenario: La URL cambia pero la fuente se mantiene

- DADO que el usuario marca `Wikipedia` como visitada para `Panthera tigris`
- CUANDO el mismo usuario abre una especie diferente (`Panthera leo`) e inspecciona el conjunto de visitadas
- ENTONCES la fila `Wikipedia` para `Panthera leo` es independiente (sin fuga entre especies)
- Y el conjunto de visitadas se indexa por `(species_id, source)`, no por URL

## Fuera de Alcance

- Sincronización en la nube, multidispositivo, autenticación — SQLite local monousuario según el issue #68.
- Timestamps de visita por fuente expuestos en la UI — solo se muestra el estado del toggle; `visited_at` es metadato para auditoría.
- Marcar automáticamente una fuente como visitada cuando el usuario hace clic en el enlace embebido dentro de `<ExplorerPanel>` — el manejador de clic llama explícitamente al endpoint de toggle; la detección automática es una rebanada separada.
- Aislamiento multiusuario — workspace monousuario.
- Expiración automática del estado de visitada — las entradas persisten indefinidamente hasta que el usuario las elimine.
