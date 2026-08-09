# Especificación de enlaces-de-búsqueda-de-especie

## Propósito
Define las URLs de despacho emitidas por especie para que un usuario pueda dispersarse a los mismos 12 orígenes de búsqueda que codificaba la hoja original. Las URLs DEBEN coincidir literalmente con `docs/sources/templates.md` para preservar la paridad. Sci-hub despacha hacia `https://sci-hub.ru/match/{q}` y sustituye la especie como cualquier otro origen.

## Requisitos

### Requisito: Emitir exactamente doce enlaces por especie

El sistema DEBE emitir exactamente 12 enlaces por especie, en el orden definido en `docs/sources/templates.md`, y NO DEBE añadir, eliminar ni reordenar enlaces entre solicitudes.

#### Escenario: Doce enlaces ordenados
- DADA una especie resuelta sin ambigüedad
- CUANDO el cliente solicita las URLs de despacho
- ENTONCES el cuerpo contiene un arreglo `links` de exactamente 12 elementos
- Y el orden coincide con el orden de filas en `docs/sources/templates.md`

#### Escenario: Orden estable entre solicitudes
- DADA la misma especie solicitada dos veces
- CUANDO se comparan ambas respuestas
- ENTONCES ambos arreglos `links` son iguales elemento a elemento
- Y ningún enlace se omite, duplica o reordena

#### Escenario: Cada enlace está completo
- DADO un elemento de enlace devuelto
- CUANDO el cliente parsea el elemento
- ENTONCES contiene exactamente las claves `source`, `label` y `url`
- Y `source` es uno de los 12 nombres del archivo de plantillas
- Y `url` es una cadena no vacía

### Requisito: Sustitución de URL desde las plantillas

El sistema DEBE sustituir `{q}` por la consulta de especie codificada con `urllib.parse.quote_plus(species, safe='')` para que los espacios se vuelvan `+` y los caracteres especiales se codifiquen en porcentaje. Las porciones fijas de cada plantilla DEBEN aparecer literalmente.

#### Escenario: Sustitución codificada como URL
- DADO un nombre de especie con un espacio, como `Genus species`
- CUANDO el cliente solicita las URLs de despacho
- ENTONCES cada `{q}` sustituido usa `+` en lugar del espacio
- Y cada parámetro fijo de cada plantilla se conserva byte a byte

#### Escenario: Caracteres especiales en porcentaje
- DADO un nombre de especie con un carácter no alfanumérico como `(`, `)` o `&`
- CUANDO el cliente solicita las URLs de despacho
- ENTONCES el carácter se codifica en porcentaje en cada `{q}` sustituido
- Y la estructura de la plantilla queda inalterada

#### Escenario: La URL de Fotos conserva sus parámetros
- DADA la plantilla de Fotos con parámetros fijos de seguimiento de la celda M9
- CUANDO el cliente solicita las URLs de despacho
- ENTONCES la URL de Fotos incluye cada parámetro fijo literalmente
- Y solo el segmento `{q}` se sustituye

### Requisito: Sci-hub sustituye la especie

El sistema DEBE emitir el enlace de Sci-hub usando la plantilla `https://sci-hub.ru/match/{q}` donde `{q}` se sustituye con la especie codificada en URL mediante `urllib.parse.quote_plus(species, safe='')`, de modo que los espacios se convierten en `+` y los caracteres especiales se codifican en porcentaje. El host DEBE ser `sci-hub.ru` y la ruta DEBE comenzar con `/match/`.

#### Escenario: La URL de Sci-hub sustituye la especie
- DADA una especie como `Girardinichthys multiradiatus` resuelta
- CUANDO el cliente solicita las URLs de despacho
- ENTONCES el `url` de Sci-hub es igual a `https://sci-hub.ru/match/Girardinichthys+multiradiatus`
- Y la especie aparece exactamente una vez en la URL

#### Escenario: La URL de Sci-hub difiere por especie
- DADAS dos especies distintas resueltas
- CUANDO el cliente solicita las URLs de despacho de cada una
- ENTONCES los `url` de Sci-hub difieren entre sí
- Y cada uno contiene el nombre URL-codificado de esa especie

#### Escenario: Los doce enlaces sustituyen la especie
- DADA una especie resuelta
- CUANDO el cliente solicita las URLs de despacho
- ENTONCES los doce enlaces contienen un segmento `{q}` sustituido
- Y ningún enlace queda exento de la sustitución