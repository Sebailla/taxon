## Exploración: cascade-checklistbank

### Estado actual

El backend del cascade sirve actualmente tres endpoints con reconocimiento de ruta (`GET /api/kingdoms`, `GET /api/path-children`, `GET /api/species-list`) respaldados por la API de Especies de GBIF (`https://api.gbif.org/v1`). La implementación aterrizó en tres PRs fusionados a `develop`:

- `f958aa1` — `feat(gbif): add GBIF client and taxon parser` (`taxon/gbif.py`).
- `aedbaa0` — `feat(gbif): route cascade endpoints through GBIF client` (`taxon/api/router.py` conectado mediante `Depends(_get_gbif_client)`).
- `d51c50a` — `feat(gbif): add path resolver with rank-aware tier selection` (`taxon/api/gbif_path_children.py`).
- Corrección `4bed7ff` — agregó `class` a `CASCADE_TIERS`.
- Limpieza `222efe3` — reformateo.

**Fallo en la prueba de humo (motivo del pivote).** El servidor de desarrollo en vivo devolvió solo 4 filos bajo `Animalia` (Arthropoda, Chordata, Cnidaria, Mollusca): el backbone de GBIF está incompleto respecto al dominio del usuario. La versión COL2024 de ChecklistBank expone 34 filos reales bajo `Animalia`, además de la raíz faltante anteriormente (`Biota`) y el nivel de subfilo que GBIF colapsa. El usuario ha confirmado el pivote hacia CLB.

**Forma del código que necesita cambiar:**

- `taxon/gbif.py` — `GbifClient` (4 métodos: `get_taxon`, `get_children`, `search`, `_request`), dataclass `GbifTaxon` (16 campos con clave entera `key`/`nub_key`), `GBIF_BASE_URL = "https://api.gbif.org/v1"`. Total 236 líneas.
- `taxon/api/gbif_path_children.py` — resolvedor `list_path_children` (326 líneas). Contratos clave:
  - `CASCADE_TIERS = ("kingdom", "phylum", "class", "order", "family", "genus", "species")` (7 niveles).
  - `_resolve_deepest` recorre la ruta mediante `_search_under_parent` usando los filtros `higherTaxonKey` y `rank`.
  - Filtra los hijos a `cascade_ranks_lower = {r.lower() for r in RANK_TO_DISPLAY_LEVEL}`.
  - `next_rank_hint` es un dict hardcodeado de 7 elementos que mapea rango GBIF → siguiente rango.
  - `_to_taxon_row` conecta filas GBIF al `TaxonRow` heredado (contrato de entrada de la UI del cascade).
- `taxon/api/router.py` — tres endpoints del cascade (`/kingdoms`, `/path-children`, `/species-list`) conectados mediante `Depends(_get_gbif_client)`. `/kingdoms` usa `gbif.search(name="", rank="KINGDOM", accepted_only=True, limit=100)` y deduplica por `nub_key`. Las pruebas sobrescriben `_get_gbif_client` con `app.dependency_overrides[_get_gbif_client] = lambda: client` para inyectar `_StubClient`.
- `taxon/tests/test_gbif.py` (257 líneas), `taxon/tests/test_gbif_path_children.py` (409 líneas), `taxon/tests/test_api_gbif_router.py` (335 líneas) — todas usan `httpx.MockTransport` con `_StubClient` para imitar a GBIF.
- `frontend/src/components/Cascade.tsx` (359 líneas) + `frontend/src/components/Cascade.state.ts` (175 líneas) — reductor dirigido por ruta, un desplegable por respuesta no-hoja, `nextRankHint` usado para etiquetar el siguiente desplegable. **El cascade no asume un conteo fijo de niveles** — renderiza N desplegables donde N depende de cuántas instantáneas no-hoja devuelva el backend.
- `frontend/src/api.ts` — wrappers tipados `fetchKingdoms()`, `fetchPathChildren()`, `fetchSpeciesList()`.
- `taxon.pen` — archivo de diseño Pencil para la UI del cascade (cifrado; se accede solo vía Pencil MCP).

**Lo que devuelve la API CLB en vivo (verificado con curl):**

- `GET /dataset/COL2024/tree` → `{"total":2, "result":[{id:"5T6MX", rank:"unranked", name:"Biota", childCount:7}, {id:"V", rank:"unranked", name:"Viruses", childCount:31}]}`.
- `GET /dataset/COL2024/tree/5T6MX/children?limit=10` → 7 reinos bajo Biota (Animalia=N, Archaea=R, Bacteria, Chromista=C, Fungi=F, Plantae=P, Protozoa=Z).
- `GET /dataset/COL2024/tree/N/children?limit=100` → 34 filos bajo Animalia (Acanthocephala, Annelida, Arthropoda, … Xenacoelomorpha).
- `GET /dataset/COL2024/tree/CH2/children?limit=100` → 3 subfilos bajo Chordata (Cephalochordata, Tunicata, Vertebrata).
- `GET /dataset/COL2024/tree/8V4V3/children` → 2 infrafilos bajo Vertebrata (Agnatha, Gnathostomata).
- `GET /dataset/COL2024/tree/BMGVD/children` → 2 subclases bajo Mammalia (Prototheria, Theria).
- `GET /dataset/COL2024/nameusage/search?q=Panthera&rank=genus&limit=5` → devuelve el género con un array `classification[]` que contiene el id/nombre/rango de cada ancestro (así el resolvedor puede encontrar ancestros sin llamadas `higherTaxonKey` por nivel).
- `GET /dataset/COL2024/nameusage/search?q=&rank=kingdom&limit=20` → 18 resultados (algunos duplicados que el resolvedor debe deduplicar por ID).

**Diferencias de forma (GBIF → CLB):**

| Concepto | GBIF | CLB |
| --- | --- | --- |
| Tipo de ID | `int` (ej. 1, 44, 9703) | `str` opaco (ej. "5T6MX", "CH2", "8V4V3") |
| Clave canónica | `nubKey` (entero) | ninguna — `id` es la única clave estable por dataset |
| Raíz | 8 reinos directos | Biota (sin rango) → 7 reinos; Viruses (sin rango) → 31 reinos |
| Granularidad | 6 rangos principales (sin subfilo) | nivel real de subfilo (3 subfilos bajo Chordata) |
| Filtro de búsqueda | `?higherTaxonKey=` | no soportado — debe recorrer hijos por `id` |
| Nombres de campo | `canonicalName`, `scientificName`, `parentKey`, `numDescendants`, `kingdom`/`phylum`/`order`/`family`/`genus`/`species` (migas de pan) | `name`, `labelHtml`, `parentId`, `count` (descendientes), `childCount` (hijos directos), `authorship`, `rank`, `status` |
| Migas de pan | reino/filo/… pre-resueltos en la fila | array `classification[]` solo en resultados de búsqueda — `/tree/{id}/children` NO incluye ancestros |
| Endpoint de búsqueda | `/v1/species/search` | `/dataset/COL2024/nameusage/search` |
| Endpoint de hijos | `/v1/species/{key}/children` | `/dataset/COL2024/tree/{id}/children` |
| Detalle del taxón | `/v1/species/{key}` | `/dataset/COL2024/taxon/{id}/info` (más pesado — solo cuando se necesita) |

**Estado del issue #32.** Cerrado. Su cuerpo describía la migración a GBIF (3 cortes) — el enfoque que el usuario eligió en su momento. El nuevo cambio es un *pivote* (API diferente + forma del cascade diferente), por lo que obtiene un nombre de cambio fresco `cascade-checklistbank` y un nuevo issue, no una reutilización del #32.

**Restricciones operativas heredadas de Engram `sdd-init/taxon` (observación #3566):**

- Cada artefacto OpenSpec DEBE tener un espejo en español bajo `/documents-es/openspec/changes/cascade-checklistbank/` con el sufijo `-es`.
- Commits convencionales (`type(scope): description`), sin atribución de IA, en inglés.
- El diseño de UI DEBE ser authored en Pencil MCP y auditado bajo `impeccable` ANTES de que aterrice cualquier código de frontend.
- Worktree desde `develop` en `../taxon-worktrees/cascade-checklistbank`.
- Todos los PRs apuntan a `develop`. Tras fusionar: `/learn-es/2026-08-14-cascade-checklistbank.md`.
- Habilidad branch-pr: el repo taxon NO usa etiquetas `status:approved` ni `type:*` — usar el flujo real (PR #29/#30/#31 como referencia).

### Áreas afectadas

- `taxon/gbif.py` — reemplazar el cliente GBIF. Misma forma (cliente HTTP sin estado + dataclass), nuevos nombres de campos, claves string. Renombrar a `taxon/checklistbank.py` (preferido) o mantener el nombre del módulo y reemplazar el contenido (diff más barato). El `Depends(_get_gbif_client)` del router debe renombrarse en sincronía.
- `taxon/api/gbif_path_children.py` — reescribir el resolvedor. La búsqueda de CLB NO soporta `higherTaxonKey`, así que el recorrido debe usar `/tree/{id}/children` más coincidencia por nombre. Además: el mapeo `next_rank_hint` cambia (Biota → kingdom; kingdom → phylum; phylum → subphylum/class; subphylum → class; class → order; …). Renombrar a `taxon/api/clb_path_children.py` es consistente con el renombre del módulo pero duplica el diff; alternativa más barata es mantener el nombre del módulo y actualizar el cuerpo.
- `taxon/api/router.py` — cambian los cuerpos de tres endpoints. `/api/kingdoms` ahora son los 7 reinos de CLB bajo Biota (o incluye Biota + reinos). La sobrescritura de dependencia `_get_gbif_client` debe renombrarse (o aliasarse).
- `taxon/api/schemas.py` — `PathChildrenEnvelope`, `TaxonResponse`, `SpeciesListItem` no cambian (son el contrato público). No se necesita cambio de esquema a menos que expongamos Biota como fila.
- `taxon/tests/test_gbif.py` — reemplazar por `test_checklistbank.py`. Nuevo `_StubClient` que mockea `/dataset/COL2024/tree/{id}/children` y `/dataset/COL2024/nameusage/search`.
- `taxon/tests/test_gbif_path_children.py` — reemplazar por `test_clb_path_children.py`. Nuevas constantes de niveles (8 niveles incluyendo Biota). Pruebas para el bucket de subfilo (padre: phylum → next_rank_hint = "subphylum" o "class").
- `taxon/tests/test_api_gbif_router.py` — reemplazar por `test_api_clb_router.py`. Nuevas formas de mock (IDs string, `parentId`/`childCount`/`labelHtml`).
- `frontend/src/api.ts` — `fetchKingdoms()` se convierte en `fetchRoots()` (devuelve Biota + Viruses) o se mantiene como `fetchKingdoms()` y solo devuelve reinos. El primer desplegable del cascade muestra "Biota" → reinos (8 opciones). Esto necesita una decisión de producto.
- `frontend/src/components/Cascade.tsx` — debe manejar Biota como un nivel real en la ruta (Biota → Animalia → Chordata → Vertebrata → Mammalia → Carnivora → Felidae → Panthera → species). La lógica de path-key del reductor es agnóstica a la ruta, así que el único cambio es en la inferencia de etiquetas y cómo la fetch raíz devuelve sus filas.
- `frontend/src/components/Cascade.state.ts` — `nextRankHint: string | null` ya es agnóstico al rango. No se necesita cambio estructural si el backend devuelve "subphylum" como el siguiente hint.
- `frontend/tests/Cascade.pathAware.test.tsx`, `frontend/tests/Cascade.ui.test.tsx`, `frontend/tests/api.test.ts` — actualización de fixtures. Las rutas mock ahora incluyen Biota.
- `taxon.pen` (cifrado) — archivo de diseño Pencil MCP. El visual del cascade gana una ranura extra de desplegable (Biota) y la etiqueta del nivel de subfilo. **Debe actualizarse bajo la auditoría `impeccable` ANTES de que aterrice el código de frontend**, según AGENTS.md §5.
- `openspec/changes/cascade-checklistbank/` — proposal.md, design.md, tasks.md, exploration.md, más deltas de specs.
- `documents-es/openspec/changes/cascade-checklistbank/` — espejos en español (sufijo `-es`).
- `learn-es/2026-08-14-cascade-checklistbank.md` — entrada de aprendizaje post-fusión.

### Enfoques

1. **Migración completa: reemplazar cliente, resolvedor y endpoints del router con equivalentes CLB.** Eliminar el módulo `taxon/gbif.py` (renombrar → `taxon/checklistbank.py`); mantener sin cambios la lógica de renderizado de niveles de la UI del cascade (ya era agnóstica a la ruta).
   - Pros: única fuente de verdad; elimina 4 archivos de plomería GBIF ahora muertos (`gbif.py`, `test_gbif.py`, `test_gbif_path_children.py`, `test_api_gbif_router.py`); las pruebas se mantienen honestas. La UI del Cascade obtiene Biota + subphylum "gratis" porque renderiza N desplegables a partir de instantáneas, no un conteo fijo de niveles.
   - Contras: cada símbolo nombrado de GBIF en el código debe renombrarse (`GbifClient` → `ChecklistBankClient`, `GbifTaxon` → `ChecklistBankTaxon`, `_get_gbif_client` → `_get_checklistbank_client`, etc.). El diseño Pencil gana un nivel extra — una pasada de diseño de UI pequeña pero real.
   - Esfuerzo: Medio (3 PRs — ver estrategia de cadena abajo).

2. **Híbrido: mantener cliente GBIF + agregar adaptador CLB.** Mantener `taxon/gbif.py` para endpoints heredados; agregar `taxon/checklistbank.py` en paralelo. El router elige uno basándose en un feature flag o parámetro de consulta. El frontend mantiene el mismo contrato GBIF para la mayoría de usuarios y expone CLB solo detrás de `?source=clb`.
   - Pros: radio de impacto bajo; el rollback es un flip de flag; la superficie de 8 reinos heredada sigue funcionando.
   - Contras: duplica la superficie de pruebas; dos fuentes de verdad; el usuario dijo "el backbone de GBIF está incompleto, pivote" — mantener GBIF como fallback defeats the purpose. Dos APIs = dos comportamientos de cascade que mantener consistentes.
   - Esfuerzo: Alto (3-4 PRs de plomería, más una carga de mantenimiento continua).

3. **Endpoints paralelos solo-CLB, mantener GBIF en todo lo demás.** Agregar `/api/clb/path-children` y `/api/clb/kingdoms`; montarlos bajo un nuevo prefijo. `fetchKingdoms()` y `fetchPathChildren()` del frontend cambian a las nuevas URLs. El viejo `/api/path-children` queda respaldado por GBIF para cualquier consumidor que dependa del comportamiento previo.
   - Pros: igual que Híbrido (rollback) pero más aislado.
   - Contras: el usuario no tiene ningún consumidor que dependa de GBIF; los endpoints heredados se vuelven código muerto. La superficie de URLs `/api/clb/...` es torpe.
   - Esfuerzo: Medio-Alto (3-4 PRs).

### Recomendación

**Enfoque 1 (migración completa).** Reemplazar GBIF con CLB de extremo a extremo. El código base no tiene ningún consumidor de GBIF además del router del cascade; los enfoques híbrido o paralelo dejan código muerto y una segunda fuente de verdad. El diseño agnóstico a la ruta de la UI del Cascade (un desplegable por instantánea no-hoja, etiquetado por `nextRankHint`) absorbe Biota + subphylum sin cambio en la lógica de UI — solo el diseño Pencil gana una ranura.

**Estrategia de cadena — 3 PRs (dentro del presupuesto de 400 líneas):**

- **PR #1 — `feat(checklistbank): add CLB client and taxon parser`** (~250 líneas). Nuevo `taxon/checklistbank.py` (~200 líneas) + `taxon/tests/test_checklistbank.py` (~250 líneas, 9-10 pruebas RED-first). Refleja la forma del `taxon/gbif.py` + `taxon/tests/test_gbif.py` existente para que los revisores familiarizados con el corte GBIF puedan comparar lado a lado.
- **PR #2 — `feat(checklistbank): path resolver with Biota root + subphylum tier`** (~400 líneas). Nuevo `taxon/api/clb_path_children.py` (~280 líneas, reemplaza `gbif_path_children.py`) + `taxon/tests/test_clb_path_children.py` (~350 líneas, 11-12 pruebas incluyendo raíz Biota, bucket de subfilo, cadena Chordata → Vertebrata → Mammalia). La tupla de 8 niveles se convierte en `(biota, kingdom, phylum, subphylum, class, order, family, genus, species)` — subphylum es el nuevo nivel.
- **PR #3 — `feat(api): route cascade endpoints through ChecklistBank client`** (~350 líneas). Conectar `taxon/api/router.py` a `Depends(_get_checklistbank_client)`; actualizar `taxon/tests/test_api_checklistbank_router.py` (350 líneas, 4 pruebas); eliminar `taxon/gbif.py` + `taxon/tests/test_gbif.py` + `taxon/tests/test_gbif_path_children.py` + `taxon/tests/test_api_gbif_router.py` (~1.200 líneas de eliminaciones). Tras este PR, el código GBIF se elimina por completo.

**Luego un corte de UI separado (PR #4, fuera del cambio SDD si excede el presupuesto):**

- **PR #4 — `feat(frontend): render Biota + subphylum in the cascade UI.** Pasada de diseño Pencil primero bajo `impeccable`. Actualizar `frontend/src/components/Cascade.tsx` (inferencia de etiquetas para "subphylum" y "biota"), actualizar `frontend/src/api.ts` (`fetchKingdoms` se convierte en `fetchRoots` que devuelve Biota + Viruses), actualizar fixtures de prueba. Este es un PR encadenado que aterriza tras PR #3 una vez que el backend esté verde.

**Diff total estimado (excluyendo eliminaciones):** ~1.400-1.600 líneas añadidas a través de 3 PRs de backend, más ~150-200 líneas de frontend en PR #4. Cada PR permanece por debajo del presupuesto de 400 líneas si los commits se dividen según la habilidad `work-unit-commits` (parser + cliente en un commit; pruebas + parser en el siguiente; swap del router + eliminaciones de pruebas en el tercero).

**Base auto-encadenada.** PR #1 → PR #2 → PR #3 → PR #4 encadenados desde `develop`. El diseño Pencil para PR #4 vive en un worktree hermano desde `develop` para que no bloquee la cadena del backend.

### Riesgos

- **Limitación de tasa / disponibilidad de CLB.** CLB es un endpoint público de solo lectura sin auth, pero sí impone límites de tasa (5-10 req/s por IP). El peor caso del cascade (Animalia → filos → Chordata → subfilo → clase → subclase → …) puede ser 8-9 requests de profundidad por clic de desplegable. Recomendar una caché TTL por request (60-120s) en el resolvedor. Esfuerzo: pequeño, puede ser un PR de seguimiento si las pruebas de carga muestran la necesidad.
- **El nivel de subfilo rompe rutas que previamente funcionaban.** Un usuario con una URL guardada `path=Animalia|Chordata|Mammalia|Carnivora|Felidae|Panthera` (forma GBIF) ahora necesitaría `path=Animalia|Chordata|Vertebrata|Mammalia|Carnivora|Felidae|Panthera` (forma CLB — subfilo Vertebrata insertado). El helper de migas de pan ya elimina un Biota inicial; la inserción de subfilo es un cambio de ruta *más profundo*, no al inicio. Mitigación: mantener el resolvedor tolerante a un subfilo faltante (tratar subphylum como opcional; si `Chordata` → `Vertebrata` no devuelve coincidencias, fallback a `Chordata` → `Mammalia` directamente usando `/tree/{id}/children?rank=class`).
- **El diseño Pencil + auditoría impeccable bloquea la UI.** Según AGENTS.md §5, PR #4 no puede aterrizar antes de que el diseño sea revisado. Esta es una dependencia serial que añade 1-2 días al corte del frontend pero es no-negociable.
- **Subfilos bajo la mayoría de los filos están ausentes.** El árbol de CLB tiene 3 subfilos bajo Chordata pero 0 bajo Arthropoda (el filo con más especies). El nivel "subphylum" estará vacío para la mayoría de cadenas — el resolvedor debe manejar con gracia "sin subfilos, aquí están las clases" sin romper el reductor. Recomendación: cuando un filo tiene 0 hijos de subfilo, tratar al filo como el padre del *siguiente* nivel (es decir, devolver `next_rank_hint = "class"` en lugar de `next_rank_hint = "subphylum"` para un nivel de subfilo vacío).
- **Las fixtures de prueba necesitarán actualización.** Las 257 + 409 + 335 líneas de prueba para formas de cascade GBIF no pueden reutilizarse para formas CLB (IDs string, nuevos nombres de campos). Efecto neto: ~1.000 líneas de reescritura de fixtures de prueba. Mitigación: los contratos de prueba (la ruta camina hasta la hoja, `next_rank_hint` se propaga, 404 en segmento malo) son los mismos — solo cambian las formas de las fixtures.
- **La API en vivo puede cambiar.** CoL lanza un nuevo dataset anualmente (COL2025 esperado). El resolvedor debe usar una clave mágica (el brief menciona `3LR` para latest, `COL2024` para el lanzamiento anual) y la propuesta debe pinear la clave del dataset para reproducibilidad mientras documenta cómo actualizar.
- **Código GBIF como remanente.** PR #3 elimina `taxon/gbif.py`, los tres archivos de prueba y la sobrescritura de dependencia `_get_gbif_client`. Los revisores deben confirmar que el código muerto se ha ido, no solo ensombrecido.

### Listo para propuesta

Sí, con tres confirmaciones para registrar en la propuesta:

1. **Lista de niveles** — `(biota, kingdom, phylum, subphylum, class, order, family, genus, species)` (9 niveles). El nivel de subfilo se muestra cuando está presente, se oculta en caso contrario (el resolvedor emite `next_rank_hint = "class"` para un filo sin hijos de subfilo).
2. **Comportamiento del nivel raíz** — el primer desplegable muestra Biota + Viruses como 2 opciones (no 8 reinos directamente); al elegir Biota se revelan sus 7 reinos en el siguiente desplegable. El comportamiento anterior de "desplegable de reinos = 8 opciones" se elimina.
3. **Pinning de la clave del dataset** — pinear a `COL2024` para el primer lanzamiento; documentar la ruta de la clave mágica `3LR` para una actualización futura.

El orquestador debe decirle al usuario que la fase de propuesta puede lanzarse con esas tres decisiones incorporadas, y que PR #4 (frontend) es una cadena separada porque depende de Pencil + revisión impeccable.

El orquestador NO debe proceder a propuesta sin confirmar estas tres decisiones con el usuario primero — son elecciones de forma del cascade orientadas al usuario que la propuesta no puede hacer sola.