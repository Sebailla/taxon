# Delta para taxonomy-hierarchy

## Requisitos AÑADIDOS

### Requisito: Biota como nivel raíz

El sistema DEBE exponer un nivel raíz por encima de Reino consistente en exactamente dos opciones: `Biota` (id `"5T6MX"`) y `Viruses` (id `"V"`). Elegir `Biota` revela los siete reinos que contiene en el siguiente desplegable; elegir `Viruses` revela los reinos virales. El endpoint raíz DEBE devolver filas con `rank="root"` (o `rank="biota"`) y `next_rank_hint` igual a `"kingdom"` para `Biota` o `"viruses"` para `Viruses`.

#### Escenario: El desplegable raíz muestra Biota y Viruses

- DADO un cliente que solicita `GET /api/kingdoms` (o `GET /api/roots`)
- CUANDO el resolvedor consulta ChecklistBank `COL2024`
- ENTONCES la respuesta contiene exactamente dos elementos: `{id:"5T6MX", name:"Biota", display_name:"Biota"}` y `{id:"V", name:"Viruses", display_name:"Viruses"}`
- Y cada elemento lleva `rank="root"` y el `next_rank_hint` apropiado

#### Escenario: Elegir Biota revela los siete reinos

- DADO un cliente que elige `Biota` en la UI del cascade
- CUANDO la siguiente llamada pide los hijos en el nivel de reino
- ENTONCES el resolvedor consulta `/dataset/COL2024/tree/5T6MX/children` y devuelve los siete reinos (Animalia, Archaea, Bacteria, Chromista, Fungi, Plantae, Protozoa)

### Requisito: Regla de visibilidad del nivel subfilo

El sistema DEBE renderizar el nivel `subphylum` solo cuando el Filo padre tenga hijos de subfilo. Cuando un Filo no tenga hijos de subfilo (p. ej. Arthropoda), el resolvedor DEBE colapsar el nivel y devolver directamente los hijos de Clase con `next_rank_hint="order"`. Cuando un Filo tenga hijos de subfilo (p. ej. Chordata), el resolvedor DEBE devolverlos con `rank="subphylum"` y `next_rank_hint="class"`.

#### Escenario: Chordata expone sus tres subfilos

- DADO que la ruta padre se resuelve a `Chordata` (id `"CH2"`)
- CUANDO la UI del cascade solicita el siguiente nivel
- ENTONCES el resolvedor consulta `/dataset/COL2024/tree/CH2/children` y devuelve tres subfilos: Cephalochordata, Tunicata, Vertebrata
- Y cada elemento lleva `rank="subphylum"` y `next_rank_hint="class"`

#### Escenario: Arthropoda se salta el subfilo y devuelve directamente las clases

- DADO que la ruta padre se resuelve a `Arthropoda`
- CUANDO la UI del cascade solicita el siguiente nivel
- ENTONCES el resolvedor detecta cero hijos de subfilo y consulta directamente `/dataset/COL2024/tree/{arthropoda_id}/children?rank=class`
- Y la respuesta contiene Insecta, Crustacea, Arachnida (y otras clases) con `rank="class"` y `next_rank_hint="order"`
- Y no se emite ninguna fila de subfilo (el nivel está colapsado)

### Requisito: Fijar la clave del dataset

El sistema DEBE fijar la clave del dataset de ChecklistBank a `"COL2024"` en cada solicitud. El cliente DEBE aceptar un parámetro `dataset_key` cuyo valor por defecto es `"COL2024"`. Fijar `COL2024` produce IDs de taxón deterministas y reproducibles. La clave mágica `3LR` NO DEBE usarse en la v1; DEBE documentarse únicamente en comentarios de código como ruta de actualización futura.

#### Escenario: La clave por defecto del dataset es COL2024

- DADO un cliente que omite el parámetro `dataset_key`
- CUANDO el resolvedor emite una solicitud a ChecklistBank
- ENTONCES cada URL apunta a `/dataset/COL2024/...` y los IDs de respuesta son estables entre ejecuciones

#### Escenario: 3LR está documentado pero no se usa

- DADO un revisor que lee `taxon/checklistbank.py`
- CUANDO busca `3LR`
- ENTONCES el literal aparece solo dentro de un comentario de código cerca de `DATASET_KEY = "COL2024"`
- Y ninguna URL de solicitud contiene `3LR`

### Requisito: Identificador compuesto de taxón

El sistema DEBE identificar cada taxón del cascade con una clave compuesta consistente en `taxon_id` (el ID opaco de ChecklistBank como cadena, p. ej. `"N"`, `"CH2"`, `"RT"`) y `dataset_key` (siempre `"COL2024"` en la v1). El `nub_key` entero de GBIF NO DEBE aparecer en el contrato público.

#### Escenario: Cada fila de taxón lleva taxon_id y dataset_key

- DADO que una ruta padre se resuelve a un clado en `COL2024`
- CUANDO la UI del cascade recibe la lista de hijos
- ENTONCES cada elemento expone `id` igual al ID opaco de CLB (p. ej. `"N"` para Animalia, `"CH2"` para Chordata)
- Y el sobre de respuesta expone `dataset_key: "COL2024"`
- Y la respuesta NO contiene ningún campo entero `nub_key` ni `key`

## Requisitos MODIFICADOS

### Requisito: Navegación de jerarquía por ruta

El sistema DEBE exponer una ruta por nombre codificado como URL por cada nivel del cascade, de modo que un cliente recorra la taxonomía desde el nivel raíz `Biota` hasta un Género, con `subphylum` opcional como nivel intermedio. El conjunto efectivo de niveles es `(biota, kingdom, phylum, subphylum, class, order, family, genus, species)` (nueve niveles). El nivel `subphylum` aparece solo cuando el Filo padre tiene hijos de subfilo; en caso contrario, la ruta lo omite.
(Anteriormente: el conjunto de niveles era `(kingdom, phylum, class, order, family, genus, species)` (siete niveles) sin nivel raíz ni subfilo.)

#### Escenario: Animalia se resuelve a sus 34 filos

- DADO que la ruta padre se resuelve a `Animalia`
- CUANDO la UI del cascade elige Animalia
- ENTONCES el siguiente desplegable muestra Chordata, Arthropoda, Cnidaria, … (los 34 filos)
- Y cada elemento lleva `rank="phylum"` y un `next_rank_hint` que refleja la presencia de subfilo

#### Escenario: Felidae revela Panthera como género

- DADO la ruta `Animalia|Chordata|Vertebrata|Mammalia|Carnivora|Felidae`
- CUANDO la UI del cascade elige Felidae
- ENTONCES Panthera aparece como género
- Y la respuesta lleva `next_rank_hint="species"`

#### Escenario: Subfilo es opcional en la ruta

- DADO que la ruta padre se resuelve a `Arthropoda`
- CUANDO la UI del cascade solicita el siguiente nivel
- ENTONCES la respuesta lleva `next_rank_hint="class"` (nivel subfilo colapsado)
- Y la siguiente solicitud en `Animalia|Arthropoda|Insecta` devuelve los órdenes bajo Insecta

### Requisito: Semántica de identificadores por nombre de ruta

El sistema DEBE coincidir los segmentos sin distinción de mayúsculas contra el nombre canónico de cada taxón, preservando el `display_name` literal (citas de autor y marcadores incluidos) en las respuestas. La ruta PUEDE contener 6 o 7 segmentos según si el linaje atraviesa un subfilo (p. ej. `Chordata|Vertebrata|Mammalia` son tres segmentos incluyendo subfilo; `Arthropoda|Insecta|Lepidoptera` son tres segmentos saltando subfilo).
(Anteriormente: las rutas siempre tenían exactamente siete segmentos, uno por rango desde Reino hasta Especie.)

#### Escenario: El linaje de Chordata usa 7 segmentos para llegar a Panthera

- DADO la ruta `Animalia|Chordata|Vertebrata|Mammalia|Carnivora|Felidae|Panthera` (7 segmentos incluyendo subfilo)
- CUANDO la UI del cascade la resuelve
- ENTONCES el resolvedor recorre Chordata → Vertebrata → Mammalia → Carnivora → Felidae → Panthera vía `/dataset/COL2024/tree/{id}/children`
- Y devuelve las 12 especies de Panthera en la hoja

#### Escenario: El linaje de Arthropoda usa 6 segmentos para llegar a Bombyx

- DADO la ruta `Animalia|Arthropoda|Insecta|Lepidoptera|Bombycidae|Bombyx` (6 segmentos, subfilo omitido)
- CUANDO la UI del cascade la resuelve
- ENTONCES el resolvedor recorre Arthropoda → Insecta → Lepidoptera → Bombycidae → Bombyx y devuelve las especies
- Y el resolvedor nunca inserta un segmento de subfilo para Arthropoda

#### Escenario: Falta el parámetro path y devuelve 400

- DADO una solicitud que omite el parámetro de consulta `path`
- CUANDO el cliente llama a `GET /api/path-children`
- ENTONCES la respuesta es HTTP 400
- Y el cuerpo de la respuesta contiene un error `missing path` que explica el parámetro requerido

## Requisitos ELIMINADOS

### Requisito: Raíz de ocho reinos de GBIF

(Razón: el cascade ya no obtiene datos de la API de Especies de GBIF; el comportamiento anterior donde `/api/kingdoms` devolvía ocho reinos directamente se reemplaza por el desplegable raíz Biota + Viruses desde ChecklistBank `COL2024`. El campo entero `nub_key` de GBIF también se elimina del contrato público.)
(Migración: los clientes que consumen `/api/kingdoms` DEBEN tratar la respuesta como el nivel raíz (Biota + Viruses) y solicitar el siguiente desplegable para descubrir los reinos. Cualquier cliente que tenga codificados ocho reinos o espere un `nub_key` DEBE actualizarse para usar el identificador compuesto `taxon_id` + `dataset_key`.)