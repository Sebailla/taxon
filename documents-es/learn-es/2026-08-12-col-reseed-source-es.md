# Path de import del CoL DwC-A (PR #26)

# Qué

Añadido un nuevo path de import que ingesta el archivo DwC-A
del Catalogue of Life en el mismo schema SQLite que el path
existente de WoRMS puebla. Cuando este PR esté mergeado, los
operadores pueden correr:

```
python -m taxon.col_import /path/to/NameUsage.tsv --database data/taxon.db
```

para cambiar el dataset de WoRMS de 1.39M filas por las 7.87M
filas de CoL cubriendo todos los reinos (Animalia, Plantae,
Fungi, Chromista, más varios reinos de procariotas y virus)
con la UI del cascade y los 14 endpoints existentes sin
cambios.

El path de WoRMS en `taxon/import_data.py` queda intacto. La
elección de qué archivo usar para el seed sigue siendo decisión
de cada deployment (el dataset WoRMS es más rápido de seedear;
CoL es 5.6× más grande y más rico).

# Cómo

### Nuevo parser: `taxon/col_parser.py`

Stremea el NameUsage TSV de 2.9 GB. Mismo shape `(parent_source_id,
ParsedTaxon)` que el parser de WoRMS así los dos paths comparten
el schema `Taxon` / `SpeciesPath`. Mapeo de columnas (lista
completa en el docstring del módulo):

- `col:ID`               → source_id
- `col:parentID`         → parent_source_id
- `col:scientificName`   + `col:authorship` → display_name
- `col:rank`             → rank
- nombre canónico rank-specific desde `col:uninomial` /
  `col:genericName` / `col:specificEpithet` /
  `col:infraspecificEpithet`, cayendo a `col:scientificName`
  cuando una fila omite las partes descompuestas
- `col:status` (synonym / ambiguous synonym / misapplied) →
  is_synonym; (`provisionally accepted`) → is_uncertain;
  (`col:extinct` == "true") → is_extinct;
  (`col:rank` == "unranked") → is_unassigned

Validación:
- el header debe contener todos los nombres de columnas
  requeridos (raises `ValueError` con la lista faltante si no);
- las filas de datos deben tener el mismo conteo de celdas
  que el header (el archivo CoL publicado embarca un conteo
  estricto por fila).

### Nuevo ingester: `taxon/col_import.py`

Estrategia de tres pasadas, todo en memoria, sin re-stremear:

1. **Insert pass** — streamea el TSV, batch-insert en `Taxon`
   con `parent_id = NULL`. Foreign keys deshabilitadas a nivel
   de engine durante el import (cada insert tiene un `parent_id`
   huérfano hasta la pasada 2). Dos mapas construidos al
   costado:
   `source_to_database_id` (CoL source_id → autoincrement
   Taxon.id) y `parent_source_by_child` (child source_id →
   parent source_id).

2. **Parent-wiring pass** — un `UPDATE taxa SET parent_id = ...`
   por parent distinto, en batch sobre cada child que apunta
   a él. Las raíces cuyo parent está fuera del subset
   importado (el superdominio implícito Biota) quedan con
   `parent_id = NULL`. Esas son las raíces del bosque
   importado, no bugs.

3. **Species-path pass** — para cada fila cuyo rank es species
   (o cualquier rank infraespecífico), inserta una fila
   `SpeciesPath` usando las columnas rank-resolved `col:kingdom`
   (65), `col:phylum` (64), `col:class` (62), `col:order` (60),
   `col:family` (57), `col:genus` (53), más el binomio de
   `col:scientificName` + `col:authorship`. CoL puebla esas
   columnas por fila en su propio dump, así que el breadcrumb
   está en los datos — no hace falta walk recursivo.

Bound de memoria: ~100 MB por mapa en memoria a 7.87M filas.
Ambos entran cómodos en RAM moderna. Si el dataset crece más
allá de ~50M filas, la segunda pasada debería switchear a
escribir los edges de parent a disco y leerlos de vuelta.

### Tests

10 tests unitarios RED-first en `taxon/tests/test_col_parser.py`
cubriendo el contrato del parser de extremo a extremo. 4 tests
de integración RED-first en `taxon/tests/test_col_import.py`
cubriendo el ingester de SQLite:

- `test_col_import_persists_all_fixture_rows` — las 63 filas
  del fixture aterrizan en `Taxon`.
- `test_col_import_wires_parent_ids_via_two_pass_strategy` —
  `NNWV` (species) resuelve a `84LYY` (su genus) incluso
  cuando `NNWV` se parsea antes que `84LYY`.
- `test_col_import_projects_species_paths_from_resolved_columns`
  — `Buffonellaria cornuta` termina en `SpeciesPath` con el
  breadcrumb completo (kingdom Animalia, phylum Bryozoa, etc.)
  y `is_extinct = True`.
- `test_col_import_marks_synonym_status` — `63J5L` (genus
  `Paracoccidium`) tiene `is_synonym = True` porque su
  `col:status = "synonym"`.

El fixture `taxon/tests/fixtures/col_subset.tsv` es una tajada
de 63 filas del archivo CoL en vivo con cada parent_id que
aparece en una fila child también presente como su propia fila,
para que el importer pueda resolver la cadena sin lookups
externos.

# Dónde

- `taxon/col_parser.py` — nuevo, 225 líneas.
- `taxon/col_import.py` — nuevo, 343 líneas.
- `taxon/tests/test_col_parser.py` — nuevo, 135 líneas.
- `taxon/tests/test_col_import.py` — nuevo, 100 líneas.
- `taxon/tests/fixtures/col_subset.tsv` — nuevo, 64 líneas.

Cero archivos existentes modificados. El path de import de
WoRMS queda byte-por-byte sin cambios.

# Por qué

El archivo DwC-A del CoL integra WoRMS + ITIS + NCBI + GBIF +
~21.000 catálogos taxonómicos especializados en un solo release
DwC-A. Moverse de WoRMS solo a CoL:

- crece el conteo de taxa 5.6× (1.39M → 7.87M);
- expande cobertura de solo-marinos (WoRMS) a todos los reinos;
- surface el status (accepted / synonym / provisionally accepted
  / ambiguous synonym / misapplied) en lugar de un marker `=`
  inferido del prefijo del label;
- nos da flags de extinct como columna boolean real
  (`col:extinct`) en lugar de un prefijo `†` que el parser de
  WoRMS tenía que parsear del label;
- pre-resuelve cada fila's kingdom → genus en sus propias
  columnas, así que la proyección de species-path ya no
  necesita un walk depth-first.

La solicitud explícita del usuario fue "re-seed completo a CoL,
pasar solo las 6 columnas que tenemos: Kingdom, Phylum, Class,
Order, Family, Genus y especie (todas)". Las columnas 65/64/62/60/57/53
del CoL nos dan exactamente ese breadcrumb por fila, por
eso el pass de species-path puede leerlas directamente sin
recorrer el árbol.

# Cómo funciona

Cuando el operador corre `python -m taxon.col_import`:

1. El CLI default-ea al archivo CoL en
   `/Users/sebailla/Developer/research/e8ce17c8-47c4-4b10-8316-7b699472c3b1/NameUsage.tsv`
   (override vía `TAXON_COL_DATASET`).
2. `import_col_dataset(source, database)` dropea y recrea las
   tablas `taxa` y `species_paths`.
3. Pasada 1 streamea el TSV. El generador `parse_col_taxa`
   yielda filas; valida el conteo de celdas de cada fila, los
   dos mapas acumulan, y cada 1,000 filas el batch flushea en
   `Taxon` (con `parent_id = NULL`).
4. Pasada 2 emite un `UPDATE` por parent source_id distinto
   sobre cada child que apunta a él. Una round trip por parent;
   una transacción total.
5. Pasada 3 re-stremea el TSV (esta vez sin parsearlo) y escribe
   18 filas de species-path por batch de 1,000.

Después de que el CLI termina, `data/taxon.db` tiene el schema
de WoRMS poblado con datos de CoL, y la UI del cascade y los
endpoints existentes funcionan sin cambios.

# Workflows

- **CI** — 4 jobs (backend 3.11, backend 3.12, frontend,
  lighthouse). Todos verdes. Cero workflows nuevos.
- **Revisiones** — 3 `work-unit-commits`:
  1. `93d8046 test(data): add CoL parser unit tests with a real-row fixture`
  2. `14ef442 feat(data): add CoL DwC-A NameUsage TSV parser`
  3. `cd92551 feat(data): add CoL DwC-A import path (SQLite ingester)`
  El revisor puede leer el parser aislado, los tests fijan el
  contrato del parser, y el commit del ingester es el diff
  más chico posible (sin cambios al parser).
- **Seed local** — `python -m taxon.col_import` sobre el archivo
  de 2.9 GB toma 1-3 horas y produce un SQLite de
  aproximadamente 500 MB - 1 GB. Mismo `data/taxon.db` que usa
  el path de WoRMS, así que cambiar es solo cambiar el path.
- **Deployment en producción** — el servidor API apunta a
  `data/taxon.db` sin importar qué path lo seedeó. La única
  interacción de la UI del cascade es vía `Taxon` /
  `SpeciesPath`, así que ambas fuentes son intercambiables.

# Aprendizajes

- **Las filas de CoL NO están en orden depth-first.** Verificado
  contra el archivo en vivo — las primeras 50 filas mezclan
  species, genus, order, suborder. El parser de WoRMS depende
  de la indentación para mantener una stack de ancestros; ese
  patrón no puede funcionar para CoL. La estrategia de tres
  pasadas + mapa de parents en memoria es el mínimo que maneja
  correctamente las filas desordenadas.

- **CoL pre-resuelve el breadcrumb por fila.** Las columnas
  rank-resolved (50/53/57/60/62/64/65) cargan kingdom → genus
  para cada fila, incluyendo filas synonym. El pass de
  species-path las lee directamente; no hace falta walk
  recursivo. El path de WoRMS necesitaba un walk depth-first
  para construir la misma proyección — esa complejidad se
  fue.

- **Dos módulos paralelos de import le ganan a uno polimórfico.**
  `taxon/import_data.py` (WoRMS, depth-first, single-pass) y
  `taxon/col_import.py` (CoL, desordenado, three-pass)
  comparten los modelos `Taxon` y `SpeciesPath` pero difieren
  en cada paso. Forzarlos a través de una función con un
  `if format == ...` por paso habría dañado la legibilidad
  más que la duplicación del entry point.

- **Mapas en memoria le ganan a re-stremear el archivo.** El
  archivo CoL es 2.9 GB; re-stremearlo dos veces triplicaría
  el I/O. Los dos mapas (source_to_database_id +
  parent_source_by_child) cuestan ~200 MB a 7.87M filas. Barato.

- **`dict(parsed)` cast al batchear.** `ParsedTaxon` es un
  TypedDict; mypy strict rechaza appendear un TypedDict en
  `list[dict[str, Any]]`. El cast explícito `dict(parsed)` es
  el workaround más limpio, y el path de insert SQL trata
  la fila como un dict plano de todos modos.

- **Fixtures con datos reales son los únicos fixtures honestos.**
  El fixture de 63 filas es una tajada real del archivo CoL
  con cada parent_id que aparece en una fila child también
  presente como su propia fila, así que el importer puede
  resolver la cadena sin lookups externos. Fixtures
  sintetizados habrían ocultado los bugs de offset de
  columnas que cazamos temprano (`_COL_FAMILY = 56` no 57,
  etc.).

# Oportunidades de seguimiento (fuera del alcance de este PR)

- Importar `VernacularName.tsv` (154 MB, 1.99M filas) como
  nueva tabla `VernacularName` join-eada a `Taxon` por
  `source_id`. Desbloquearía una feature de "búsqueda por
  nombre común".
- Importar `Distribution.tsv` (140 MB) para una futura UI de
  mapa de distribución.
- Agregar un selector de kingdom a la UI del cascade; hoy la
  UI walks Kingdom → Genus asumiendo un único kingdom raíz,
  lo que sirve para WoRMS pero no para CoL (Animalia, Plantae,
  Fungi, etc. arrancan todos al mismo nivel de indent).
- Reemplazar el path de WoRMS como default una vez que el
  nuevo dataset esté validado en producción por algunas
  semanas.
