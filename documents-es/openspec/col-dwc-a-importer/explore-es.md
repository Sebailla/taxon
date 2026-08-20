# Exploración: migración WoRMS → Catalogue of Life DwC-A

> **Nota**: este `explore.md` lo produjo directamente el orchestrator en una sesión con SDD latcheado (la tarea `sdd-apply` previa en esta conversación devolvió `sdd_task_result_empty` y el pipeline SDD permanece latcheado hasta que se inicie una sesión nueva). El contenido documenta el descubrimiento que habría producido un sub-agent `sdd-explore` formal. **Debe re-producirse mediante una invocación nueva de `sdd-explore` en la próxima sesión, antes de la fase de propuesta.** El SDD latcheado de la próxima sesión no puede re-armarse aquí.

## Intención

El repo hoy importa WoRMS (World Register of Marine Species), un dump de texto basado en indentación. El usuario quiere migrar a Catalogue of Life (CoL), que distribuye sus datos como Darwin Core Archive (DwC-A), un formato estándar de biodiversidad. La migración es reemplazo total (sin fallback de WoRMS), cubre backend + frontend, y el DwC-A real se descarga durante la fase de apply.

Decisiones de producto capturadas (ver Engram `sdd/col-dwc-a-importer/context`):

1. **Fuente**: DwC-A (Darwin Core Archive). Recomendado por sobre Annual Checklist Archive (snapshot anual) y la API de COL (operacionalmente más pesada, rate-limited).
2. **Alcance**: Backend + frontend. Los campos específicos de CoL (e.g. `nameAccordingTo`, `taxonomicStatus`) aparecen en la UI solo si la fase de diseño lo decide.
3. **Compatibilidad**: WoRMS reemplazado totalmente. `python -m taxon.import_data` solo entiende DwC-A después de la migración.
4. **Dataset**: el DwC-A real se descarga durante la fase de apply.

## Alcance de esta exploración

Tres archivos de producción cambian. El resto se queda.

### Lo que se queda

| Archivo | Razón |
|---------|-------|
| `taxon/schema.py` | Las clases ORM `Taxon` / `SpeciesPath` / `TaxonDescendantCount` ya cargan `is_synonym`, `parent_id`, `rank`, `display_name`, `display_level`, marker columns — la mayor parte de lo que mapea DwC-A. No se requieren adiciones al schema en este primer corte. |
| `taxon/taxonomy.py` | La whitelist `RANK_TO_DISPLAY_LEVEL` ya cubre kingdom → family → species. **Puede requerir** añadidos para rangos de CoL: `subtribe`, `infratribe`, `parvorder`, `superorder`, `infraorder`, `superfamily`, `variety`, `form`, `subform`, `forma_specialis`, `section`, `subsection`. Por decidir en diseño. |
| `taxon/api/tree.py` | Código del read-path (endpoint tree children). Sin cambios. Ya lee de la tabla `taxa` igual. |
| `taxon/api/_tree_tiers.py` | Tier walker (envoltorio de subtree por tier). Sin cambios. |
| `taxon/api/projections.py` | Proyección `taxon_descendant_counts` + helpers (`materialize_for_parent`, `register_display_level`, etc.). Sin cambios. El importer de CoL debe seguir llamando `_rebuild_descendant_counts_projection` al final de un import exitoso (cableado idéntico al PR #86). |
| `taxon/api/__init__.py` | Factory FastAPI + lifespan. Sin cambios. Ya bootstrap `taxon_descendant_counts` (PR #89). |
| `taxon/api/database_url.py` | Resolución de URL con fallback. Sin cambios. |
| `taxon/api/workspace.py` | Tablas del species-folder-explorer. Sin cambios. |
| `taxon/migrate.py` | Subcomandos `apply` + `apply-projection`. Sin cambios. |
| `taxon/api/router.py`, schemas, etc. | Toda la superficie de la API. Sin cambios. |
| `openspec/changes/archive/2026-08-19-descendant-counts-projection/` | Artefactos SDD archivados. No afectados. |
| Todas las entradas `learn-es/*.md` | Historia. No afectada. |

### Lo que cambia

| Archivo | Acción | Razón |
|---------|--------|-------|
| `taxon/parser.py` | **Reemplazar** con `taxon/dwc_parser.py` | El regex de indentación WoRMS de 178 líneas es estructuralmente incompatible con el TSV plano de CoL. Archivo separado porque el parser WoRMS puede ser útil históricamente; el nuevo parser merece su propio módulo. |
| `taxon/import_data.py` | **Reemplazar** con `taxon/col_importer.py` | Importer nuevo: descarga del zip (opcional), stream del `taxon.txt` descomprimido, inserts SQL batch, orden por nivel jerárquico para resolución de FK, llamada de fin de import a `_rebuild_descendant_counts_projection`. |
| `taxon/tests/test_parser.py` | **Reemplazar** con `taxon/tests/test_dwc_parser.py` | Tests para el nuevo parser DwC. |
| `taxon/tests/test_import.py` | **Reemplazar** con `taxon/tests/test_col_importer.py` | Tests para el nuevo importer. |
| Docstrings que referencian WoRMS | **Editar** | Varios archivos (e.g. `import_data.py:1`, `parser.py:1`) mencionan WoRMS — actualizar para mencionar CoL DwC-A. |
| Constante `DEFAULT_SOURCE` | **Cambiar** | De `/Users/sebailla/Developer/research/worm/dataset-2011.txt` a una URL de CoL DwC-A (por decidir en diseño — probablemente `https://www.checklistbank.org/dataset/3/export/dwca` o un mirror descargable). |

### Lo que se queda pero necesita investigación nueva en propuesta/diseño

- Nombres exactos de columna en `taxon.txt` para el DwC-A de CoL (ver "Schema reference" abajo).
- Si el DwC-A de CoL carga valores de `taxonRank` que mapean limpio sobre `RANK_TO_DISPLAY_LEVEL` o requieren añadidos.
- El mapping de `taxonomicStatus` a `is_synonym` (y la ausencia de flag para "invalid" — ¿se excluyen del tree?).
- Si se registra la authorship citation en `display_name` (comportamiento actual: WoRMS lo strippea vía regex; DwC-A lo tiene como columna separada `scientificNameAuthorship`).
- Comportamiento pre-import: drop-all o upsert? El importer WoRMS actual hace drop y recrea (idempotente). DwC-A debe hacer lo mismo.

## Schema reference (clase Darwin Core Taxon)

Los términos DwC relevantes para `taxon.txt` (extraídos de `https://dwc.tdwg.org/terms/`):

| Término DwC | Mapea a columna `Taxon` | Notas |
|-------------|------------------------|-------|
| `taxonID` | `source_id` | El importer WoRMS usa `{namespace}:{id}` (e.g. `worms:123`); DwC-A típicamente usa `COL:123` o solo numérico/UUID. |
| `parentNameUsageID` | resuelve a `parent_id` | FK a `taxa.id` luego de resolver el source_id. NULL para kingdom-tier o virtual roots. |
| `acceptedNameUsageID` | dependiente del contexto | NULL → este row ES el accepted taxon. No-NULL → este row es un synonym; `parent_id` debe apuntar al parent del *accepted* taxón, e `is_synonym = True`. |
| `scientificName` | `display_name` | Incluye la authorship citation, e.g. `Animalia Linnaeus, 1758`. |
| `scientificNameAuthorship` | (extraer de scientificName) | Columna separada en DwC-A — el parser WoRMS la extraía de un paréntesis trailing. |
| `taxonRank` | `rank` | String literal, e.g. `kingdom`, `phylum`. |
| `taxonomicStatus` | `is_synonym` | Valores: `accepted`, `synonym`, `invalid`, `misapplied`, `doubtful`. Filas `accepted` forman el tree primario; filas `synonym` con `is_synonym = True` pero `parent_id` apuntando al accepted taxón (o su parent). |
| `nameAccordingTo` | (columna opcional nueva) | Fuente bibliográfica de la decisión taxonómica. Podría ir en una futura columna `Taxon.source` o descartarse en este primer corte. |
| `acceptedNameUsage` | (sin mapping) | Nombre verboso del accepted taxon. Mismo contenido que `scientificName` si el row ES el accepted. |
| `taxonRemarks`, `taxonConceptID`, `namePublishedIn` | no en este primer corte | Diferir a propuesta de seguimiento. |

## Desafíos del mapping (preliminar)

1. **Resolución del FK `parent_id`**: `taxa.parent_id` actualmente es `INTEGER` que referencia `taxa.id`. DwC-A da `parentNameUsageID` como string (el source_id del parent). El importer necesita o bien:
   - (a) Dos pasadas: insertar accepted taxa primero (resolviendo `source_id → id` en un dict), luego segunda pasada para synonyms.
   - (b) Ordenar por profundidad jerárquica antes de insertar (taxa raíz al frente, hojas al fondo).
   - La opción (a) es más robusta y matchea el patrón de aceptación lazy.

2. **Synonyms requieren manejo especial**: una fila de synonym tiene su propio `sourceID`, su propio `scientificName`, y un `acceptedNameUsageID` apuntando al source_id del accepted taxon. El `parent_id` para el synonym debería ser **el mismo parent que el accepted taxon** (en la UI del tree, un synonym es sibling del accepted taxon, no hijo). La spec DwC es ambigua acá; el importer WoRMS marcaba synonyms como hijos de su accepted name. **Esto es un cambio de comportamiento**: los synonyms bajo CoL deben mirrorear el parent del accepted taxon, no el accepted taxon mismo.

3. **Resolución de `display_level`**: CoL DwC-A puede cargar un `verbatimTaxonRank` o similar que mapee directo sobre `display_level`. El importer WoRMS dejaba `display_level` NULL y dejaba que la función SQL `taxonomy_display_level` resolviera desde `rank`. El importer CoL puede hacer lo mismo (sin cambio de schema) o precomputar al insertar para una pequeña ganancia de read-time. Diferir la decisión a diseño.

4. **Extracción de authorship**: con WoRMS la authorship era un paréntesis trailing en la línea. `scientificNameAuthorship` de DwC-A es columna separada — más fácil. Pero el canonical name (`Taxon.name` en el schema) es la forma *sin author*. Necesita un helper que strippee la authorship trailing de `scientificName` (ya existe en `taxonomy.py` como `display_level`; no es exactamente lo mismo — un nuevo helper `strip_authorship(name, authorship)`).

## Riesgo hot spots

1. **Dataset de 7M filas**. El importer WoRMS streamea vía parsing basado en stack. El importer DwC-A debe hacer lo mismo (leer línea por línea, batch SQL inserts cada `BATCH_SIZE = 1_000` filas). Memoria acotada por el tamaño del batch.

2. **Orden por foreign key**. DwC-A es plano — sin indentación que guíe inserts parent-first. La estrategia de dos pasadas (u ordenamiento topológico) es obligatoria. NO se puede "wait but fix after": cada row con parent_id no resuelto crashea el `INSERT`.

3. **Descarga del zip para `apply-projection` y runtime**. El archivo DwC-A comprimido pesa ~600MB, ~2GB expandido. El CLI puede querer default a un archivo ya descargado (e.g. `/Users/sebailla/Developer/research/col/col-dwca.zip`) y aceptar un flag `--download` para el primer arranque. Fallos de red durante el import no deben corromper la DB — envolver toda la transacción en una sola llamada `Base.metadata.create_all`.

4. **Drift del schema `meta.xml`**. El schema DwC-A es estable, pero los releases anuales de CoL pueden renombrar o repurposar columnas (e.g. valores de `taxonRank`). El parser debe ser tolerante: columnas faltantes defaultan a NULL/empty, rangos desconocidos caen en `RANK_TO_DISPLAY_LEVEL` como `None` (excluidos del cascade).

5. **Las proyecciones `_batch_species_counts` y `species_paths`**. Ambas corren hoy después de `_populate_species_paths`. El importer CoL debe llamarlas en el mismo orden — primero paths, luego projection rebuild — para que los datos lleguen antes de que la projection los lea.

## Decisión a nivel schema: ¿extendemos `Taxon`?

**No, en este primer corte.** El schema `Taxon` existente puede llevar datos de CoL sin migración. Si la fase de diseño decide exponer metadata específica de CoL (e.g. `source`, `taxonConceptID`), eso es follow-up.

Sin embargo, la lógica de `_extract_markers` y citation-parsing de `taxon/parser.py` NO necesita portarse. El campo `taxonomicStatus` de DwC-A es la fuente de `is_synonym` (sin regex). `scientificNameAuthorship` ya está separado. El nuevo parser es principalmente un lector TSV con mapping de columnas.

## Out of scope (diferido a follow-ups)

- Endpoints públicos nuevos (e.g. búsqueda por autor, mapa de distribución).
- Visualización en frontend de campos específicos de CoL.
- Extensiones de schema (e.g. distribución, estado de conservación, taxonRemarks).
- Dos pasadas por el dataset para re-imports parciales (insertar solo taxa *nuevos* sin reconstruir la DB entera).
- API/Annual formats — solo DwC-A en este change.

## Preguntas abiertas para la fase de propuesta

1. La URL exacta del archivo DwC-A para el último release anual (por decidir; marcar esto para verificación antes del apply).
2. El conjunto de valores de `taxonRank` en CoL que necesitan añadirse a `RANK_TO_DISPLAY_LEVEL` (por decidir — generar desde una muestra del dataset).
3. Si `scientificName` carga marcadores infragenéricos (CoL a veces agrega `(Subgenus)` o `[unranked]` al nombre). Si sí, el importer los strippea en las cuatro columnas booleanas existentes (`is_synonym`, `is_extinct`, `is_uncertain`, `is_unassigned`) y en `display_name`.
4. Comportamiento de filas con `taxonomicStatus = "invalid"` — descartar o mantener con flag `is_invalid` (no hay flag actual, requeriría extensión de schema).

## Alcance estimado (aprox)

- `taxon/dwc_parser.py`: ~150 líneas (mapping de columnas + resolución en dos pasadas + strip de authorship + manejo de synonyms).
- `taxon/col_importer.py`: ~150 líneas (apertura del zip + stream TSV + inserts batch + llamada a projection).
- `taxon/tests/test_dwc_parser.py`: ~300 líneas (red-first para cada edge case del mapping de columnas).
- `taxon/tests/test_col_importer.py`: ~250 líneas (red-first para inserts batch, orden jerárquico, idempotencia).
- Docs + mirrors ES + artefactos OpenSpec: ~250 líneas.
- Total: ~1100 líneas, cómodamente bajo el budget de 400 líneas si se separa por concern (parser, importer, tests, docs).

## Decisión abierta antes del apply: chain strategy

Siguiendo el preflight SDD, el forecast de entregabilidad será `medium-high` porque los cambios de schema están concentrados en dos archivos (`parser.py` → `dwc_parser.py`, `import_data.py` → `col_importer.py`) pero la superficie de tests es amplia. El usuario eligió previamente `size:exception` para el PR #86 — lo mismo puede aplicar acá.

Por decidir en la fase de propuesta: chain `stacked-to-main`, `feature-branch-chain`, o `size:exception`.

## Material de referencia

- DwC Quick Reference: <https://dwc.tdwg.org/terms/>
- API ChecklistBank de CoL: <https://www.checklistbank.org>
- Endpoint de export DwC-A de CoL: <https://www.checklistbank.org/dataset/3/export/dwca> (devuelve 403 en curl headless con challenge anti-bot; el export del dataset es real y está disponible para usuarios logueados vía la GUI).