# Propuesta: cascade-checklistbank

## Intención

El backend del cascade sirve actualmente Reino→Filo→Clase→Orden→Familia→Género desde la API de Especies de GBIF. La prueba de humo en vivo devolvió solo 4 filos bajo `Animalia` (Arthropoda, Chordata, Cnidaria, Mollusca) — el backbone de GBIF está incompleto para el dominio del usuario. La versión `COL2024` de ChecklistBank expone 34 filos reales bajo `Animalia`, además del nivel raíz faltante (`Biota`) y el nivel de subfilo que GBIF colapsa. Migramos el backend del cascade de extremo a extremo a `https://api.checklistbank.org` contra el dataset `COL2024`, añadimos Biota como raíz visible y subfilo como nivel intermedio real, y actualizamos la UI del cascade para renderizar ambos. El intento previo rastreado bajo el issue #32 usó GBIF y falló en la fase de prueba de humo; este cambio es el pivote, no una re-edición del #32.

## Alcance

### En alcance
- Reemplazar `taxon/gbif.py` con `taxon/checklistbank.py` (módulo nuevo, nuevos nombres de campos, IDs opacos `str`).
- Reescribir `taxon/api/gbif_path_children.py` → `taxon/api/clb_path_children.py` con la tupla de 9 niveles `(biota, kingdom, phylum, subphylum, class, order, family, genus, species)`.
- Actualizar `taxon/api/router.py`: los endpoints del cascade se enlazan a `Depends(_get_checklistbank_client)`.
- `/api/kingdoms` devuelve Biota + Viruses (nivel raíz, 2 opciones). Al elegir Biota se revelan 7 reinos en el siguiente desplegable.
- Subfilo se renderiza cuando está presente (Chordata → subfilo Vertebrata → clase Mammalia); se omite con `next_rank_hint = "class"` cuando el filo padre no tiene hijos de subfilo (p. ej. Arthropoda).
- Pinear la clave del dataset a `COL2024`; documentar la ruta de actualización con la clave mágica `3LR` solo en comentarios de código.
- Eliminar `taxon/gbif.py`, `taxon/tests/test_gbif.py`, `taxon/tests/test_gbif_path_children.py`, `taxon/tests/test_api_gbif_router.py` después de que el swap del router esté en verde.
- Corte de frontend (`Cascade.tsx`, `api.ts`, fixtures) para renderizar Biota + subfilo, bloqueado por Pencil MCP + auditoría `impeccable` según AGENTS.md §5.
- Espejo en español en `documents-es/openspec/changes/cascade-checklistbank/proposal-es.md` según AGENTS.md §1.

### Fuera de alcance
- Caché TTL/de respuestas en el resolvedor (PR de seguimiento si las pruebas de carga muestran la necesidad).
- Heurísticas más estrictas de dedup de reinos más allá del dedup por id ya presente en `_resolve_deepest`.
- Salto a `COL2025` o cualquier versión futura de CoL.
- Cascade de reinos de virus más allá del desplegable raíz.
- Cualquier cambio en el esquema público de respuesta (`PathChildrenEnvelope`, `TaxonResponse`, `SpeciesListItem`).
- Cerrar o comentar el issue #32.

## Capacidades

### Capacidades nuevas
- Ninguna.

### Capacidades modificadas
- `taxonomy-hierarchy`: el backend cambia GBIF → ChecklistBank; el conjunto efectivo de niveles pasa a 9 (raíz Biota + subfilo); el endpoint raíz devuelve 2 opciones (Biota, Viruses) en lugar de 8 reinos; subfilo aparece solo cuando está presente. El esquema público de respuesta (`id`/`name`/`display_name`, ordenación alfabética, semántica 404/409) no se modifica. Delta de spec requerido.

## Enfoque

Reemplazo de extremo a extremo GBIF → CLB en tres PRs de backend encadenados (cada uno bajo el presupuesto de 400 líneas), más un PR de frontend después de que Pencil + `impeccable` lo aprueben.

**Cadena de backend (PR #1 → PR #2 → PR #3, todos desde `develop`, todos hacia `develop`):**

- **PR #1 — `feat(checklistbank): add CLB client and taxon parser`** (~250 líneas). Nuevo `taxon/checklistbank.py` reflejando la forma de `taxon/gbif.py`: `ChecklistBankClient` (4 métodos: `get_taxon`, `get_children`, `search`, `_request`) + dataclass `ChecklistBankTaxon` (`id`, `name`, `labelHtml`, `parentId`, `count`, `childCount`, `authorship`, `rank`, `status`). Pruebas en `taxon/tests/test_checklistbank.py` usan `httpx.MockTransport` con `_StubClient` que imita `/dataset/COL2024/tree/{id}/children` y `/dataset/COL2024/nameusage/search`. RED-first: 9–10 pruebas.
- **PR #2 — `feat(checklistbank): path resolver with Biota root + subphylum tier`** (~400 líneas). Nuevo `taxon/api/clb_path_children.py` (~280 líneas) con tupla de 9 niveles. `_resolve_deepest` recorre vía `/tree/{id}/children` + coincidencia por nombre (la búsqueda CLB no tiene `higherTaxonKey`). Mapa `next_rank_hint`: biota→kingdom, kingdom→phylum, phylum→subphylum/class (cuando subfilo vacío), subphylum→class, class→order, order→family, family→genus, genus→species. Tolerancia a subfilo: filo con 0 hijos de subfilo → `next_rank_hint = "class"`. Pruebas en `taxon/tests/test_clb_path_children.py` (~350 líneas, 11–12 pruebas): raíz Biota, bucket de subfilo (Chordata → 3 subfilos, Arthropoda → 0 → se omite), cadena completa Mammalia, dedup por id opaco.
- **PR #3 — `feat(api): route cascade endpoints through ChecklistBank client`** (~350 líneas netas, ~1.200 líneas de eliminaciones). El router cambia `Depends(_get_gbif_client)` → `Depends(_get_checklistbank_client)`; pruebas renombradas; nuevo `taxon/tests/test_api_checklistbank_router.py` (4 pruebas). Eliminar `taxon/gbif.py` + 3 archivos de prueba. Los revisores deben confirmar que el código muerto se elimina, no se ensombrece.

**Corte de frontend (PR #4, cadena separada porque depende de Pencil + `impeccable`):**

- **PR #4 — `feat(frontend): render Biota + subphylum in the cascade UI**. Pasada de diseño Pencil en `taxon.pen` (un desplegable extra + etiqueta de subfilo) bajo auditoría `impeccable`. Actualizar `Cascade.tsx` con inferencia de etiquetas para "subphylum"/"biota"; `fetchKingdoms()` → `fetchRoots()` devuelve Biota + Viruses; fixtures añaden Biota. Rama desde `develop`, hacia `develop`. ~150–200 líneas.

**Worktrees.** `../taxon-worktrees/cascade-checklistbank-pr{1..4}`. Diseño Pencil para PR #4 en worktree hermano desde `develop` para no bloquear la cadena del backend. Commits divididos según `work-unit-commits` (parser+cliente / resolvedor+pruebas / swap del router+eliminaciones de pruebas) para mantenerse bajo 400 líneas modificadas por PR.

## Áreas afectadas

| Área | Impacto | Descripción |
|------|---------|-------------|
| `taxon/gbif.py` | Eliminado | Reemplazado por `taxon/checklistbank.py`; se elimina en PR #3. |
| `taxon/api/gbif_path_children.py` | Eliminado | Reemplazado por `taxon/api/clb_path_children.py`; se elimina en PR #3. |
| `taxon/api/router.py` | Modificado | Los endpoints del cascade cambian `Depends(_get_gbif_client)` → `Depends(_get_checklistbank_client)` en PR #3. |
| `taxon/api/schemas.py` | Ninguno | Esquema público sin cambios. |
| `taxon/checklistbank.py` | Nuevo | Cliente CLB + dataclass; PR #1. |
| `taxon/api/clb_path_children.py` | Nuevo | Resolvedor de 9 niveles con raíz Biota + bucket de subfilo; PR #2. |
| `taxon/tests/test_checklistbank.py` | Nuevo | Mocks de `_StubClient`; PR #1. |
| `taxon/tests/test_clb_path_children.py` | Nuevo | Pruebas del resolvedor incl. Biota + subfilo; PR #2. |
| `taxon/tests/test_api_checklistbank_router.py` | Nuevo | Integración del router; PR #3. |
| `taxon/tests/test_gbif.py`, `test_gbif_path_children.py`, `test_api_gbif_router.py` | Eliminados | Se eliminan en PR #3. |
| `frontend/src/api.ts` | Modificado | `fetchKingdoms()` → `fetchRoots()`; PR #4. |
| `frontend/src/components/Cascade.tsx` | Modificado | Inferencia de etiquetas para "subphylum"/"biota"; PR #4. |
| `frontend/src/components/Cascade.state.ts` | Ninguno | Reductor agnóstico a la ruta; absorbe nuevos nombres de rango. |
| `frontend/tests/*.test.tsx` | Modificado | Las rutas mock añaden Biota; PR #4. |
| `taxon.pen` | Modificado | Ranura extra de desplegable + etiqueta de subfilo; PR #4 bloqueado por `impeccable`. |
| `openspec/changes/cascade-checklistbank/` | Nuevo | proposal.md, design.md, tasks.md, deltas de specs. |
| `documents-es/openspec/changes/cascade-checklistbank/` | Nuevo | Espejos en español (sufijo `-es`). |
| `learn-es/2026-08-14-cascade-checklistbank.md` | Nuevo | Entrada de aprendizaje post-fusión. |

## Riesgos

| Riesgo | Probabilidad | Mitigación |
|--------|--------------|------------|
| Limitación de tasa de CLB (5–10 req/s por IP). Peor caso: 8–9 llamadas `/tree/{id}/children` encadenadas por clic de desplegable. | Media | Fuera de alcance para v1; seguimiento posterior. Si se observa durante la prueba de humo, añadir caché TTL de 60–120s en el resolvedor. |
| La inserción de subfilo rompe URLs con forma GBIF previamente guardadas. | Media | El resolvedor trata subfilo como opcional: filo con 0 hijos de subfilo → `next_rank_hint = "class"`; la UI colapsa el nivel. Las URLs antiguas guardadas obtienen 404 con mensaje claro. |
| Pencil + `impeccable` añade 1–2 días al PR #4. | Alta (cierto) | Dependencia serial según AGENTS.md §5; no negociable. La cadena de backend avanza en paralelo desde un worktree hermano. |
| Subfilos ausentes para la mayoría de los filos (Chordata tiene 3, Arthropoda tiene 0). | Media | El resolvedor omite el nivel emitiendo `next_rank_hint = "class"`; el reductor renderiza la cadena sin ranura de subfilo. |
| Deriva de la API en vivo cuando CoL lance `COL2025`. | Baja (~12 meses) | `COL2024` pineado en el cliente; ruta de actualización con clave mágica `3LR` documentada en comentario de código; el bump es un cambio de una línea. |
| Código GBIF muerto permanece (ensombrecido, no eliminado) en PR #3. | Baja | Los revisores confirman que `taxon/gbif.py`, los 3 archivos de prueba y la sobrescritura `_get_gbif_client` se eliminan físicamente. `grep -r "gbif\|Gbif"` debe devolver cero coincidencias tras la fusión. |
| El reductor del cascade asume longitud de ruta estable; Biota añade un segmento. | Baja | El reductor ya es agnóstico a la ruta (renderiza N desplegables a partir de N instantáneas no-hoja); `nextRankHint: string \| null` propaga cualquier cadena. Sin cambio estructural. |

## Plan de rollback

- **Rollback de PR #1**: revertir la fusión; `taxon/checklistbank.py` y sus pruebas son aditivos — sin cambio de comportamiento. Seguro.
- **Rollback de PR #2**: revertir la fusión. El resolvedor antiguo permanece hasta que PR #3 aterrice; el router sigue dependiendo del cliente antiguo hasta PR #3.
- **Rollback de PR #3**: PR destructivo. Revertir requiere un PR de seguimiento que reintroduzca `taxon/gbif.py`, los 3 archivos de prueba y vuelva a conectar `taxon/api/router.py` a `Depends(_get_gbif_client)`. Basar desde el commit justo antes de la fusión de PR #3 y re-aplicar cualquier cambio posterior al router.
- **Rollback de PR #4**: revertir la fusión. Los fetches del frontend caen al endpoint antiguo `/api/kingdoms` hasta que PR #4 se reaplique; el backend sigue en verde.
- **Rollback caliente** (un único PR aún no fusionado): `git revert <merge-commit>` en `develop`; hacer fast-forward de la rama del worktree; forzar push si está protegida. Para PR #3, el rollback caliente no es seguro por las eliminaciones — usar la rama de rollback completa.
- **Rollback de clave del dataset** (si `COL2024` se desactiva a mitad de año): bumpear `COL2024` → `3LR` en `taxon/checklistbank.py:DATASET_KEY`. Cambio de una línea; seguro de enviar sin ceremonia de PR.

## Dependencias

- `https://api.checklistbank.org` alcanzable desde el entorno dev (verificado: `GET /dataset/COL2024/tree` devolvió 200 con 2 raíces).
- `httpx` (ya es una dep) para el cliente nuevo; sin nuevas deps en runtime.
- `pytest` + `httpx.MockTransport` para pruebas.
- Pencil MCP + habilidad `impeccable` para la pasada de diseño de PR #4.
- Worktrees en `../taxon-worktrees/cascade-checklistbank-pr{1..4}` desde `develop`.
- Habilidad `branch-pr` para el flujo de apertura de PR (taxon no usa etiquetas `status:approved`/`type:*` — PR #29/#30/#31 como referencia).

## Criterios de éxito

- [ ] `curl "https://api.checklistbank.org/dataset/COL2024/tree"` devuelve 200 con `{total: 2, result: [{id:"5T6MX", name:"Biota", childCount:7}, {id:"V", name:"Viruses", childCount:31}]}`.
- [ ] `curl "http://localhost:8000/api/kingdoms"` devuelve 2 items: `{id:"5T6MX", name:"Biota", display_name:"Biota"}` y `{id:"V", name:"Viruses", display_name:"Viruses"}`.
- [ ] `curl "http://localhost:8000/api/path-children?path=Animalia|Chordata|Vertebrata|Mammalia|Carnivora|Felidae|Panthera"` resuelve a través de CLB y devuelve las 12 especies de Panthera (`P. leo`, `P. onca`, `P. pardus`, `P. tigris`, `P. uncia`, más 7 sinónimos históricos).
- [ ] Prueba de humo en vivo en el navegador: Biota → Animalia → Chordata → Vertebrata → Mammalia → Carnivora → Felidae → Panthera → 12 especies se renderizan. Animalia → Arthropoda muestra solo clases (ranura de subfilo colapsada).
- [ ] `grep -r "gbif\|Gbif\|GBIF" taxon/ frontend/src/ --include="*.py" --include="*.ts" --include="*.tsx"` devuelve cero coincidencias en `develop` tras la fusión de PR #3.
- [ ] La pasada de diseño Pencil en `taxon.pen` es revisada por `impeccable` y aprobada antes de que PR #4 aterrice.
- [ ] Los 3 PRs de backend aterrizan en verde en `develop` con CI pasando; ningún revisor señala la eliminación del código muerto GBIF.
- [ ] La entrada `/learn-es/2026-08-14-cascade-checklistbank.md` se crea tras CI en verde.