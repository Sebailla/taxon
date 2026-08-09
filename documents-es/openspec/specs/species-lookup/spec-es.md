# Especificación de búsqueda-de-especie

## Propósito
Define cómo se resuelve un par `(género, epíteto)` a una única especie. Los nombres de género se repiten entre padres distintos en WoRMS, por lo que la ambigüedad es un caso conocido que el sistema DEBE exponer en lugar de adivinar. La respuesta 409 es el contrato que permite a la interfaz mostrar un selector de desambiguación.

## Requisitos

### Requisito: Resolver una especie única

El sistema DEBE resolver un par `(género, epíteto)` a una única especie cuando existe exactamente una coincidencia aceptada, devolviendo su registro completo.

#### Escenario: Resolución no ambigua
- DADO un par `(género, epíteto)` que coincide con una sola especie
- CUANDO un cliente solicita la especie por nombre de ruta
- ENTONCES el sistema devuelve HTTP 200
- Y el cuerpo contiene el `id`, `canonical_name`, `display_name`, `markers` y la ruta resuelta

#### Escenario: Resolución sin distinción de mayúsculas
- DADA una especie existente cuyos nombres canónicos coinciden con `Genus` y `epithet`
- CUANDO un cliente solicita la ruta con mayúsculas mezcladas como `GENUS`/`Epithet`
- ENTONCES el sistema resuelve a la misma especie
- Y devuelve la misma forma de respuesta

### Requisito: Ambigüedad devuelve 409 con candidatos

El sistema DEBE devolver HTTP 409 Conflict cuando un par `(género, epíteto)` se resuelve a más de una especie bajo diferentes padres, y el cuerpo DEBE contener un arreglo `candidates[]` para que el cliente presente un selector.

#### Escenario: Dos padres colisionan
- DADO un par `(género, epíteto)` compartido por dos especies bajo rutas distintas
- CUANDO un cliente solicita la especie por nombre de ruta
- ENTONCES el sistema devuelve HTTP 409
- Y el cuerpo tiene un arreglo `candidates[]`
- Y cada candidato lleva la ruta completa desde Reino hasta Género más `id`, `canonical_name` y `display_name`

#### Escenario: Orden de candidatos estable
- DADA una búsqueda ambigua con un conjunto de candidatos
- CUANDO la misma solicitud se emite de nuevo
- ENTONCES `candidates[]` devuelve los mismos elementos en el mismo orden
- Y el orden es alfabético por Reino, Filo, Clase, Orden, Familia y Género

#### Escenario: Resolver tras desambiguar
- DADA una respuesta 409 con dos candidatos de identificadores distintos
- CUANDO el cliente solicita la especie por su ruta completa específica
- ENTONCES el sistema devuelve HTTP 200 para esa especie
- Y no se genera un segundo 409 para la ruta ya cualificada

### Requisito: No encontrado devuelve 404

El sistema DEBE devolver HTTP 404 cuando el par `(género, epíteto)` no corresponde a ninguna especie en el conjunto de datos.

#### Escenario: Epíteto desconocido
- DADO que el Género existe pero ninguna especie bajo él tiene el epíteto solicitado
- CUANDO un cliente solicita la especie por nombre de ruta
- ENTONCES el sistema devuelve HTTP 404
- Y el cuerpo identifica el epíteto faltante

#### Escenario: Género desconocido
- DADO que el Género solicitado no existe en el conjunto de datos
- CUANDO un cliente solicita la especie por nombre de ruta
- ENTONCES el sistema devuelve HTTP 404
- Y el cuerpo identifica el género faltante

#### Escenario: Distinguir 404 de 409
- DADA una solicitud con cero coincidencias
- CUANDO el cliente recibe la respuesta
- ENTONCES el código es 404 (no 409)
- Y 409 queda reservado para ambigüedad con al menos dos candidatos