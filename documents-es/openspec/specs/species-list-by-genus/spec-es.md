# Especificación de lista-de-especies-por-género

## Propósito
Define la sexta lista de la cascada: las especies asociadas a un Género. Es la lista fija desplazable que se actualiza al elegir un Género, y es el punto de entrada para los flujos de búsqueda de especie y enlaces de despacho.

## Requisitos

### Requisito: Listar especies de un Género

El sistema DEBE devolver todas las especies asociadas a un Género, cada una con identificador estable, nombre canónico buscable, etiqueta literal de visualización y banderas de marcador que describen su estado.

#### Escenario: Listado predeterminado solo aceptadas
- DADO un Género con especies aceptadas y sinónimos
- CUANDO un cliente solicita la lista sin parámetros de filtro
- ENTONCES solo se devuelven las aceptadas
- Y los sinónimos quedan excluidos

#### Escenario: Forma de respuesta por especie
- DADA una especie devuelta en la lista
- CUANDO el cliente parsea la respuesta
- ENTONCES el elemento contiene `id`, `canonical_name`, `display_name` y `markers`
- Y `markers` es un objeto con las claves booleanas `is_synonym`, `is_extinct`, `is_uncertain`, `is_unassigned`

#### Escenario: Género vacío
- DADO un Género existente sin especies asociadas
- CUANDO un cliente solicita la lista de ese Género
- ENTONCES la respuesta es un arreglo JSON vacío
- Y el estado HTTP es 200

### Requisito: Filtros de inclusión amplían el resultado

El sistema DEBE aceptar un parámetro `include` cuyos valores seleccionan clases adicionales; un `include` ausente o vacío mantiene el resultado de solo aceptadas.

#### Escenario: Incluir solo sinónimos
- DADO un Género con aceptadas y sinónimos
- CUANDO un cliente solicita la lista con `include=synonyms`
- ENTONCES las aceptadas siguen devolviendose
- Y los sinónimos se añaden

#### Escenario: Combinar múltiples clases
- DADO un Género con aceptadas, sinónimos y extintas
- CUANDO un cliente solicita la lista con `include=synonyms,extinct`
- ENTONCES las tres clases se devuelven
- Y los valores desconocidos en `include` se ignoran sin error

#### Escenario: Valores de include desconocidos tolerados
- DADO un cliente que envía un valor de `include` no reconocido
- CUANDO se procesa la solicitud
- ENTONCES el valor se ignora
- Y la respuesta sigue siendo 200 con solo aceptadas

### Requisito: Tope de paginación

El sistema DEBE limitar cualquier respuesta a un máximo de 500 elementos, de modo que ninguna solicitud devuelva una carga útil sin límite.

#### Escenario: Por debajo del tope
- DADO un Género con menos de 500 especies
- CUANDO un cliente solicita la lista
- ENTONCES todas las especies se devuelven en una sola respuesta
- Y no se requieren metadatos de paginación

#### Escenario: Por encima del tope
- DADO un Género con más de 500 especies
- CUANDO un cliente solicita la lista
- ENTONCES la respuesta contiene como máximo 500 elementos
- Y la respuesta incluye un token `next_cursor` cuando hay más resultados
- Y ningún elemento más allá del tope aparece en la misma respuesta

#### Escenario: El cursor avanza
- DADA una respuesta anterior con `next_cursor`
- CUANDO un cliente solicita la siguiente página con ese cursor
- ENTONCES la respuesta devuelve el siguiente lote de hasta 500 elementos
- Y el orden entre páginas es determinista