# Capacidad: taxonomic-tree-browse

## Propósito

Un árbol jerárquico estilo CoL reemplaza la cascada lineal de 7 menús desplegables. El árbol carga hijos de forma perezosa por `parent_id`, indenta por rango, renderiza filas `rank: Name Authorship • N spp.` y expone filtros `Source` + `Extant only`. El camino explorado fluye por el store Zustand `cascadePath` y un `CustomEvent` `path:change` para que el panel de breadcrumb-links de la App siga funcionando.

## Requisitos

### Requisito: Expansión Perezosa con Caché por parent_id

El sistema DEBE obtener los hijos de un taxón padre exactamente una vez por `parent_id` y almacenar en caché durante la sesión.

#### Escenario: La primera expansión obtiene los hijos
- DADO un taxón padre que no ha sido expandido
- CUANDO el usuario hace clic en su caret
- ENTONCES el sistema emite `GET /api/tree/children?parent_id={id}` y puebla la fila

#### Escenario: La re-expansión lee de la caché
- DADO que el padre ya fue expandido
- CUANDO el usuario colapsa y vuelve a expandir
- ENTONCES no se dispara un nuevo request y los hijos en caché se renderizan inmediatamente

### Requisito: Caret Según has_children

El sistema DEBE renderizar `▸`/`▾` en filas con `has_children=true` y ningún caret en filas hoja.

#### Escenario: Hoja sin caret
- DADO un taxón con `has_children=false`
- ENTONCES no aparece ningún glifo de caret y la fila no es activable por teclado para expandirse

### Requisito: Formato de Fila rank: Name Authorship • N spp.

El sistema DEBE renderizar cada fila como `rank: Name Authorship • N spp.` donde `Name` es la columna canónica `name`, `Authorship` es la cola de cita separada de `display_name`, y `N spp.` es el conteo derivado de descendientes.

#### Escenario: Authorship se separa de display_name
- DADO `name="Eukaryota"` y `display_name="Eukaryota (Chatton, 1925) Whittaker & Margulis, 1978"`
- ENTONCES la fila lee `domain: Eukaryota (Chatton, 1925) Whittaker & Margulis, 1978 • 2.4M spp.`

### Requisito: Indentación por Profundidad del Árbol

El sistema DEBE indentar cada fila por la profundidad jerárquica en el árbol explorado, calculada desde el estado del árbol (no desde `display_level`).

#### Escenario: Raíces en profundidad cero
- DADO que el árbol arranca
- ENTONCES cada fila raíz se sitúa en profundidad cero

#### Escenario: Hijo expandido indenta un nivel
- DADO que una fila raíz está expandida
- ENTONCES cada hijo directo se sitúa en profundidad uno

### Requisito: Las Filas Raíz Son parent_id IS NULL

El sistema DEBE tratar las filas con `parent_id IS NULL` como raíces del árbol y NO DEBE sintetizar una raíz `Biota`.

#### Escenario: Cinco raíces CoL
- DADO que el dataset contiene 5 filas con `parent_id IS NULL`
- ENTONCES se renderizan exactamente 5 filas raíz y no hay raíz `Biota` sintetizada

### Requisito: Filtro Extant Only

El sistema DEBE exponer una casilla `Extant only` que, cuando está marcada, oculta filas con `is_extinct=true`. El valor por defecto es desmarcada.

#### Escenario: Filtro apagado conserva extintas
- DADO que la casilla está desmarcada
- ENTONCES las filas con `is_extinct=true` son visibles

#### Escenario: Filtro encendido oculta extintas
- DADO que la casilla está marcada
- ENTONCES cada fila renderizada tiene `is_extinct=false`

### Requisito: Filtro Source (No-op Primer PR)

El sistema DEBE exponer una casilla `Source` como no-op (siempre CoL). No se envía ningún query param `source`.

#### Escenario: La casilla se renderiza
- DADO que el header se monta
- ENTONCES una casilla `Source` es visible y marcada por defecto

#### Escenario: El toggle es no-op
- CUANDO el usuario alterna la casilla
- ENTONCES el árbol no vuelve a fetchear

### Requisito: Despacho del Camino en Cada Expansión

El sistema DEBE escribir el camino explorado en el store Zustand `cascadePath` y disparar un `CustomEvent` `path:change` con `{path: string[]}` en cada expansión.

#### Escenario: El store y el evento se disparan
- DADO que el usuario expande una fila
- ENTONCES `useCascadePath.getState().path` es igual a los segmentos explorados
- Y `window.dispatchEvent` dispara `path:change` con `{path: [...]}`

### Requisito: Estado Vacío

El sistema DEBE renderizar "No taxonomy loaded" cuando el árbol no tiene filas raíz.

#### Escenario: Sin raíces
- DADO que ninguna fila tiene `parent_id IS NULL`
- ENTONCES se renderiza "No taxonomy loaded"

### Requisito: Estado de Error con Reintento

El sistema DEBE renderizar una acción de reintento en una fila caret cuando su fetch de hijos falla. Las demás filas DEBEN permanecer expandidas.

#### Escenario: Reintento en fallo
- DADO que el fetch de una fila caret devuelve 5xx o error de red
- ENTONCES la fila muestra un botón "Retry" que reemite el mismo request al hacer clic

### Requisito: Navegación por Teclado y ARIA

El sistema DEBE hacer las filas navegables por teclado (Enter alterna el caret, ArrowDown/Up mueve el foco) y DEBE exponer `aria-level` (profundidad de indentación) y `aria-expanded` (estado del caret).

#### Escenario: Enter alterna el caret
- DADO que una fila tiene foco
- CUANDO el usuario presiona Enter
- ENTONCES el caret se alterna y `aria-expanded` refleja el nuevo estado

## Fuera de Alcance

- Cableado backend del filtro `Source` (no-op primer PR; multi-source en seguimiento).
- Materialización de `species_count` en nodos profundos (lazy `null` >100k hijos directos).
- Persistencia entre recargas del estado expandido del árbol.
- El panel de lista de especies — el árbol llega a un género y delega en el fetch existente de especies.