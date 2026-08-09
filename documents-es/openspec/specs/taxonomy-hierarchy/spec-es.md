# Especificación de taxonomía-jerárquica

## Propósito
Define cómo se expone la cascada taxonómica (Reino → Filo → Clase → Orden → Familia → Género). Los identificadores son nombres de ruta codificados como URL, de modo que cada enlace refleja la ruta recorrida por el usuario. Esta capacidad es la columna vertebral de las demás.

## Requisitos

### Requisito: Navegación de jerarquía por ruta

El sistema DEBE exponer una ruta por nombre codificado como URL por cada nivel de la cascada, para que un cliente recorra la taxonomía desde un Reino hasta un Género añadiendo un segmento por rango.

#### Escenario: Listar hijos de un Reino
- DADO un Reino existente en el conjunto de datos
- CUANDO un cliente solicita los Filos de ese Reino por nombre de ruta
- ENTONCES la respuesta es un arreglo JSON de hijos
- Y cada elemento incluye `id`, `name`, `display_name`
- Y los elementos están ordenados alfabéticamente por `name`

#### Escenario: Listar hijos en cualquier rango
- DADO un taxón padre existente en cualquier rango canónico
- CUANDO un cliente solicita los hijos en el siguiente rango inferior
- ENTONCES la respuesta devuelve solo los hijos directos de ese padre
- Y el resultado es vacío cuando el padre no tiene hijos en ese rango

#### Escenario: 404 cuando el ancestro no existe
- DADO un segmento de la ruta que no coincide con ningún nombre de taxón
- CUANDO un cliente solicita una ruta que contiene ese segmento
- ENTONCES el sistema devuelve HTTP 404
- Y el cuerpo indica qué segmento no fue encontrado

### Requisito: Semántica de identificadores por nombre de ruta

El sistema DEBE coincidir los segmentos sin distinción de mayúsculas contra el nombre canónico de cada taxón, preservando el `display_name` literal (citas de autor y marcadores incluidos) en las respuestas.

#### Escenario: Coincidencia sin distinción de mayúsculas
- DADO un Reino llamado "Animalia" en el conjunto de datos
- CUANDO un cliente solicita la ruta con el segmento `animalia`
- ENTONCES el sistema lo resuelve al mismo Reino que `Animalia`
- Y devuelve los mismos hijos

#### Escenario: Preservación literal de la visualización
- DADO un taxón cuyo nombre canónico fue normalizado pero cuya etiqueta conserva citas de autor
- CUANDO un cliente solicita cualquier ruta descendente de ese taxón
- ENTONCES el campo `display_name` DEBE ser igual a la etiqueta de origen exactamente como fue capturada

#### Escenario: Segmento ambiguo rechazado
- DADO un segmento que se resuelve a múltiples táxones con el mismo nombre bajo diferentes padres
- CUANDO un cliente solicita una ruta con ese segmento desnudo
- ENTONCES el sistema devuelve HTTP 409
- Y el cuerpo lista las rutas candidatas para desambiguar

### Requisito: Forma y orden estables de la respuesta

El sistema DEBE devolver una forma JSON estable para cada endpoint de jerarquía y DEBE ordenar los hijos de manera determinista, de modo que dos solicitudes equivalentes produzcan los mismos bytes.

#### Escenario: Orden determinista
- DADO un taxón padre con hijos A, B, C bajo el mismo rango
- CUANDO el cliente emite la misma solicitud dos veces
- ENTONCES ambas respuestas devuelven los hijos en el mismo orden
- Y el orden es alfabético por `name` canónico

#### Escenario: Estabilidad del esquema
- DADO el esquema del endpoint de jerarquía publicado
- CUANDO el cliente parsea la respuesta
- ENTONCES cada elemento contiene exactamente las claves `id`, `name`, `display_name`
- Y no se introducen claves inesperadas entre versiones sin un incremento de versión documentado