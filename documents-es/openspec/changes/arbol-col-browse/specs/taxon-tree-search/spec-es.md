# Capacidad: taxon-tree-search

## Propósito

Un autocompletado "Find taxon" en el header del árbol permite saltar a cualquier taxón por nombre. La búsqueda llama a `GET /api/tree/search?q={q}` con debounce de 200ms y un tope fijo de 8 resultados. El ranking es coincidencia exacta > prefijo > subcadena para que el resultado más relevante quede arriba.

## Requisitos

### Requisito: Input de Búsqueda en el Header del Árbol

El sistema DEBE exponer un único input de texto etiquetado `Find taxon` en el header del árbol.

#### Escenario: El input se renderiza
- DADO que el header del árbol se monta
- ENTONCES se renderiza un `<input>` con `aria-label="Find taxon"`
- Y no existe ningún otro input de búsqueda en la vista del árbol

### Requisito: Debounce de Pulsaciones a 200ms

El sistema DEBE hacer debounce de cada cambio del input a 200ms; las pulsaciones rápidas se colapsan en un único request.

#### Escenario: Pulsaciones rápidas se colapsan
- DADO que el usuario teclea `E`, `u`, `k` dentro de 100ms cada una
- CUANDO la ventana de 200ms se cierra tras la última pulsación
- ENTONCES se dispara exactamente un `GET /api/tree/search?q=Euk`

#### Escenario: Una pausa dispara requests separados
- DADO que el usuario teclea `E`, pausa 300ms, luego teclea `u`
- ENTONCES se disparan dos requests: `q=E` y `q=Eu`

### Requisito: Contrato con el Backend

El sistema DEBE llamar a `GET /api/tree/search?q={q}&limit=8` y decodificar la respuesta como `{items: TreeNodeResponse[]}`.

#### Escenario: Respuesta decodificada
- DADO que el backend devuelve `{"items": [{"id": 1, "name": "Eukaryota", ...}]}`
- ENTONCES `items.length === 1`
- Y cada elemento tiene `id`, `name`, `display_name`, `rank`, `parent_id`

### Requisito: Relevancia Ordenada

El sistema DEBE ordenar resultados como coincidencia exacta > prefijo > subcadena. Los empates DEBEN romperse por longitud ascendente de `display_name`.

#### Escenario: La coincidencia exacta gana
- DADO que el dataset contiene `Panthera` (género) y `Panthera onca` (especie)
- CUANDO el usuario teclea `Panthera`
- ENTONCES `Panthera` es el primer elemento
- Y `Panthera onca` es el segundo

#### Escenario: El prefijo vence a la subcadena
- DADO que el dataset contiene `Eukarya` y `Pseudeukarya`
- CUANDO el usuario teclea `Euk`
- ENTONCES `Eukarya` es el primer elemento
- Y `Pseudeukarya` está ausente

### Requisito: Estado Vacío y Sin Resultados

El sistema NO DEBE mostrar dropdown cuando `q` está vacío y DEBE mostrar `No matches for "<q>"` cuando la respuesta tiene cero elementos.

#### Escenario: Input vacío oculta el dropdown
- DADO que el input está vacío
- ENTONCES no se renderiza ningún dropdown
- Y no se dispara ningún request

#### Escenario: Dropdown sin resultados
- DADO que el usuario teclea `Zzzqxx`
- CUANDO la respuesta devuelve `{"items": []}`
- ENTONCES el dropdown renderiza `No matches for "Zzzqxx"`

### Requisito: Objetivo de Rendimiento

El sistema DEBE mantener la latencia p95 de `GET /api/tree/search?q={q}` por debajo de 200ms contra `data/col.db`.

#### Escenario: p95 menor a 200ms
- DADO 100 búsquedas secuenciales con queries variadas
- CUANDO se calcula p95
- ENTONCES p95 ≤ 200ms

### Requisito: La Selección Navega al Nodo

El sistema DEBE navegar a un resultado al hacer clic o Enter: expandir el camino del árbol hasta ese nodo, hacer scroll hasta él y mover el foco a esa fila.

#### Escenario: Clic selecciona y navega
- DADO que el dropdown muestra resultados
- CUANDO el usuario hace clic en el primero
- ENTONCES cada ancestro se expande
- Y la fila elegida entra en vista (scroll)
- Y el foco se mueve a la fila elegida

#### Escenario: La tecla Enter selecciona
- DADO que el dropdown tiene foco
- CUANDO el usuario presiona Enter
- ENTONCES el resultado enfocado queda seleccionado
- Y la navegación coincide con el escenario de clic