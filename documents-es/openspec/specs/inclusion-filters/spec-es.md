# Especificación de filtros-de-inclusión

## Propósito
Define los toggles que la interfaz expone para táxones extintos, sinónimos, inciertos y sin asignar, y la regla de que el comportamiento predeterminado devuelve solo táxones aceptados. El almacén conserva todos los táxones; los toggles solo cambian lo que la respuesta incluye.

## Requisitos

### Requisito: Toggles por clase de inclusión

El sistema DEBE exponer un toggle por clase — `extinct`, `synonyms`, `uncertain`, `unassigned` — para que el usuario decida de forma independiente si incluye cada clase en la lista de especies.

#### Escenario: Se exponen cuatro toggles
- DADO el panel de filtros renderizado
- CUANDO el panel se muestra
- ENTONCES aparecen exactamente cuatro toggles: `extinct`, `synonyms`, `uncertain`, `unassigned`
- Y cada toggle está desactivado por defecto

#### Escenario: El toggle amplía el resultado
- DADO el estado predeterminado de solo aceptadas
- CUANDO un usuario activa el toggle `extinct` y vuelve a consultar
- ENTONCES las extintas se añaden a la respuesta
- Y las aceptadas siguen presentes

#### Escenario: El toggle reduce el resultado
- DADO el toggle `synonyms` activado
- CUANDO el usuario lo desactiva y vuelve a consultar
- ENTONCES las sinónimas se eliminan de la respuesta
- Y la respuesta vuelve a solo aceptadas

### Requisito: Estado predeterminado de solo aceptadas

El sistema DEBE desactivar todos los toggles por defecto, de modo que una solicitud sin parámetros devuelva solo táxones aceptados. El valor predeterminado aplica cuando la solicitud no lleva `include` o lleva un valor vacío.

#### Escenario: Sin parámetro include
- DADO que el cliente envía una solicitud sin el parámetro `include`
- CUANDO se calcula la lista de especies
- ENTONCES solo se devuelven especies aceptadas
- Y no se devuelve ningún taxón extinto, sinónimo, incierto o sin asignar

#### Escenario: Parámetro include vacío
- DADO que el cliente envía `include=` (valor vacío)
- CUANDO se calcula la lista de especies
- ENTONCES solo se devuelven especies aceptadas
- Y la respuesta es idéntica a la solicitud sin parámetro

#### Escenario: Aplica en cada endpoint
- DADO que `species-list-by-genus` y `species-lookup` consumen el filtro
- CUANDO se invoca cualquiera sin un `include` explícito
- ENTONCES ambos devuelven solo aceptadas

### Requisito: Composición con semántica OR

El sistema DEBE tratar múltiples toggles activados como una unión: activar `extinct` y `synonyms` devuelve extintos y sinónimos junto a las aceptadas. La combinación DEBE ser OR, nunca AND.

#### Escenario: Dos toggles en unión
- DADOS los toggles `extinct` y `synonyms` activados
- CUANDO se calcula la lista de especies
- ENTONCES la respuesta contiene aceptadas, extintas y sinónimas
- Y no contiene solo la intersección

#### Escenario: Los cuatro toggles activados
- DADOS todos los toggles activados
- CUANDO se calcula la lista de especies
- ENTONCES la respuesta contiene todos los táxones del Género independientemente de su clase
- Y ningún taxón queda excluido por la lógica del filtro

#### Escenario: El filtro no muta los datos
- DADA una solicitud que activa el toggle `extinct`
- CUANDO se devuelve la respuesta
- ENTONCES el conjunto persistido queda inalterado
- Y las solicitudes posteriores sin el toggle ven solo aceptadas

### Requisito: Filtros de solo lectura

El sistema DEBE tratar los filtros como una proyección de solo lectura sobre los datos persistidos. NO DEBE existir endpoint de escritura que mute la clase de un taxón para fines de filtrado.

#### Escenario: No existe ruta de escritura
- DADA la API completamente descrita
- CUANDO el cliente enumera las operaciones
- ENTONCES ningún endpoint acepta una carga que alterne el estado de un taxón
- Y ningún endpoint muta el nombre canónico

#### Escenario: Toggles por solicitud
- DADO un cliente que activa `extinct`
- CUANDO otro cliente consulta sin el toggle
- ENTONCES ese otro cliente sigue viendo solo aceptadas
- Y el estado del primer cliente no se filtra