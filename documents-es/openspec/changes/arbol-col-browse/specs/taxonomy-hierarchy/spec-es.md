# Delta para taxonomy-hierarchy

## Requisitos MODIFIED

### Requisito: Navegación de Jerarquía por Camino

El sistema DEBE exponer una ruta URL-encoded por nivel de cascada con un segmento de camino por rango, de modo que un cliente pueda navegar desde Kingdom hasta Genus añadiendo un segmento por rango. Los endpoints resueltos por camino (`/{path:path}/taxon-links` y `/api/path-children?path=…`) DEBEN permanecer verbatim para que el panel breadcrumb-links y el despacho de especies sigan funcionando.
(Previamente: la capacidad sólo exponía endpoints por nombre de camino; el árbol añade direccionamiento por parent-id junto a ellos.)

#### Escenario: Listar hijos de un Kingdom
- DADO que existe un Kingdom
- CUANDO un cliente solicita los Phyla de ese Kingdom por nombre de camino
- ENTONCES la respuesta es un array JSON de hijos ordenados alfabéticamente por `name`
- Y cada elemento incluye `id`, `name`, `display_name`

#### Escenario: Listar hijos en cualquier rango
- DADO que existe un taxón padre en cualquier rango canónico
- CUANDO un cliente solicita los hijos en el siguiente rango hacia abajo
- ENTONCES la respuesta devuelve sólo los hijos directos de ese padre (vacío si no hay)

#### Escenario: 404 cuando el ancestro es desconocido
- DADO que un segmento del camino no coincide con ningún nombre de taxón
- CUANDO un cliente solicita un camino con ese segmento
- ENTONCES el sistema devuelve HTTP 404 con un cuerpo que nombra el segmento que falla

### Requisito: Forma de Respuesta Estable y Orden Determinista

El sistema DEBE devolver una forma JSON estable para cada endpoint de jerarquía y ordenar los hijos de forma determinista. Los nuevos endpoints del árbol extienden `TaxonResponse` con `has_children`, `species_count` y `authorship` y NO DEBEN mutar la forma canónica de `TaxonResponse`.
(Previamente: `TaxonResponse` llevaba `id`, `name`, `display_name`, `rank`, `parent_id` y marcadores. Los endpoints del árbol añaden tres campos derivados.)

#### Escenario: Orden determinista
- DADO que un padre tiene hijos A, B, C en el mismo rango
- CUANDO el cliente emite el mismo request dos veces
- ENTONCES ambas respuestas devuelven los hijos en el mismo orden alfabético por `name` canónico

#### Escenario: Estabilidad del esquema
- DADO que el esquema del endpoint de jerarquía está publicado
- CUANDO el cliente parsea la respuesta
- ENTONCES cada elemento contiene exactamente las claves `id`, `name`, `display_name`
- Y no aparecen claves inesperadas sin un version bump documentado

## Requisitos ADDED

### Requisito: Endpoint de Hijos por parent-id

El sistema DEBE exponer `GET /api/tree/children?parent_id={id}&limit={n}&cursor={c}` devolviendo `{parent: TaxonResponse, children: list[TreeNodeResponse], next_cursor: str | None}`. `TreeNodeResponse` extiende `TaxonResponse` con `has_children: bool`, `species_count: int | None` y `authorship: str`.

#### Escenario: Hijos con campos derivados
- DADO que un taxón padre tiene hijos directos
- CUANDO un cliente solicita `/api/tree/children?parent_id=2`
- ENTONCES la respuesta es 200 con cada hijo llevando `has_children`, `species_count`, `authorship`
- Y `next_cursor` no está vacío cuando se excede `limit`

#### Escenario: 404 ante parent desconocido
- DADO que el `parent_id` no coincide con ningún taxón
- CUANDO un cliente solicita `/api/tree/children?parent_id=999999`
- ENTONCES el sistema devuelve HTTP 404 con un cuerpo que identifica el parent id faltante

### Requisito: Endpoint de Búsqueda del Árbol

El sistema DEBE exponer `GET /api/tree/search?q={q}&limit=8` devolviendo `{items: list[TreeNodeResponse]}` con ranking coincidencia exacta > prefijo > subcadena. Los empates DEBEN romperse por longitud ascendente de `display_name`.

#### Escenario: Resultados ordenados
- DADO que el dataset contiene `Panthera` y `Panthera onca`
- CUANDO el cliente solicita `/api/tree/search?q=Panthera`
- ENTONCES la respuesta es 200 con `items[0].name === "Panthera"` y como máximo 8 entradas

#### Escenario: Query vacía devuelve lista vacía
- DADO que `q` está vacío o es whitespace
- CUANDO el cliente solicita el endpoint
- ENTONCES la respuesta es 200 con `{"items": []}` y sin error SQL

### Requisito: Semántica Perezosa de species_count

El sistema DEBE calcular `species_count` como el conteo de especies descendientes vía CTE recursivo. Para padres con más de 100,000 hijos directos, el sistema DEBE devolver `species_count: null` para mantener la respuesta por debajo de 100ms; la UI renderiza `—` en lugar del conteo.

#### Escenario: Null perezoso para nodos enormes
- DADO que un padre tiene más de 100,000 hijos directos
- CUANDO el cliente solicita los hijos
- ENTONCES cada hijo lleva `species_count: null` y el request completa en menos de 100ms

#### Escenario: Agregado se llena para nodos pequeños
- DADO que un padre tiene menos de 100,000 hijos directos
- CUANDO el cliente solicita los hijos
- ENTONCES cada hijo lleva un entero `species_count` igual al conteo de descendientes

### Requisito: Endpoints Resueltos por Camino Permanecen Verbatim

El sistema DEBE mantener `/{path:path}/taxon-links` y `/api/path-children?path=…` sin cambios para que el panel breadcrumb-links y el flujo de despacho de especies sigan funcionando.

#### Escenario: El path-resolver devuelve 13 enlaces
- DADO que el usuario hace clic en un segmento del breadcrumb
- CUANDO la App llama a `/{path:path}/taxon-links`
- ENTONCES la respuesta es `TaxonLinksResponse{taxon, links}` con exactamente 13 elementos sustituidos con el `name` canónico del taxón más profundo

#### Escenario: path-children devuelve next_tiers
- DADO que la App necesita hermanos de cascada en un camino
- CUANDO se llama al endpoint path-children
- ENTONCES la respuesta es `PathChildrenEnvelope{parent, children, next_tiers}` con `next_tiers` agrupando hijos por etiqueta de rango