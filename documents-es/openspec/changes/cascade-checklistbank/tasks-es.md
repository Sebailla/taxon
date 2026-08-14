# Tareas: cascade-checklistbank

## Pronóstico de Carga de Revisión

Decisión necesaria antes de aplicar: No
PRs encadenados recomendados: Sí
Estrategia de cadena: feature-branch-chain
Riesgo de presupuesto de 400 líneas: Medio

Cinco PRs encadenados (PR #1 → PR #2a → PR #2b → PR #3 → PR #4); cada
uno apunta a `develop` según AGENTS.md §4. El usuario aprobó
`size:exception` para el PR #1; el PR #2a se estimó en ~420 LOC en el
pronóstico de diseño y se divide mediante commits por unidad de trabajo
para que ningún commit hijo supere el límite de 400 líneas. El PR #4 va
en una cadena aparte porque depende de Pencil MCP y la revisión de
`impeccable` según AGENTS.md §5. La estrategia de entrega resuelta por
el orquestador es `auto-chain`; no se requiere decisión adicional.

### Unidades de Trabajo Sugeridas

| Unidad | Objetivo | PR probable | Comando de prueba focal | Andamiaje de ejecución | Frontera de rollback |
|--------|----------|-------------|-------------------------|------------------------|----------------------|
| 1 | Cliente CLB + dataclass + parser (sin cambios en el router) | PR #1 | `pytest taxon/tests/test_checklistbank.py -v` → todos pasan | N/A (aún no hay router) | Eliminar `taxon/checklistbank.py` + `taxon/tests/test_checklistbank.py`; ningún otro archivo tocado |
| 2a | Recorrido central del resolver de 9 niveles (raíz Biota + 7 reinos + filos + clases + órdenes + familias + géneros + especies) | PR #2a | `pytest taxon/tests/test_clb_path_children.py::test_resolve_deepest_mammalia_chain -v` → 1 pasa; `pytest taxon/tests/test_clb_path_children.py -k "not subphylum_collapse"` → todos pasan | N/A (aún no hay router) | Eliminar `taxon/api/clb_path_children.py` + el archivo de pruebas; no existe cableado en el router |
| 2b | Regla de colapso de subfilo (Chordata → 3 subfilos, Arthropoda → omitir) | PR #2b | `pytest taxon/tests/test_clb_path_children.py -k subphylum_collapse -v` → todos pasan | N/A (aún no hay router) | Revertir solo la sonda de colapso de `_children_for` + sus 2–3 pruebas; el núcleo del resolver permanece |
| 3 | Cambio del router + eliminación de GBIF | PR #3 | `pytest taxon/tests/ -v` → todos pasan; `pytest taxon/tests/test_api_clb_router.py -v` → 4 pruebas pasan | `curl "http://localhost:8000/api/kingdoms"` → 2 elementos `{id:"5T6MX", name:"Biota"}` + `{id:"V", name:"Viruses"}`; `curl "http://localhost:8000/api/path-children?path=Animalia\|Chordata\|Vertebrata\|Mammalia\|Carnivora\|Felidae\|Panthera"` → 12 especies de Panthera | Restaurar `taxon/gbif.py` + 3 archivos de prueba + recablear `taxon/api/router.py`; PR destructivo — ver §Plan de Rollback de la propuesta |
| 4 | Frontend: renderizar Biota + subfilo | PR #4 | `vitest run frontend/tests/api.test.ts frontend/tests/Cascade.pathAware.test.tsx frontend/tests/Cascade.ui.test.tsx` → todos pasan | `curl "http://localhost:8000/api/kingdoms"` + smoke en navegador: Biota → Animalia → Chordata → Vertebrata → Mammalia → Carnivora → Felidae → Panthera → 12 especies renderizadas; la ruta Arthropoda omite la ranura de subfilo | Revertir solo archivos del frontend; el backend no se ve afectado |

## Fase 1: PR #1 — `feat(checklistbank): add CLB client and taxon parser`

Depende de: nada (primer PR de la cadena). Apunta a `develop`.
Rama: `../taxon-worktrees/cascade-checklistbank-pr1`.
LOC: ~450 (size:exception aprobada por el usuario — ver §Riesgos de la propuesta).

Commits por unidad de trabajo dentro del PR #1 (según la habilidad `work-unit-commits`):

- [ ] 1.1 Crear `taxon/checklistbank.py` con `DATASET_KEY = "COL2024"` (con comentario sobre 3LR), `CLB_BASE_URL`, dataclass `ChecklistBankTaxon` (`id`, `name`, `label_html`, `parent_id`, `count`, `child_count`, `authorship`, `rank`, `status`) y `ChecklistBankClient` con `__init__`, `get_taxon`, `get_children`, `search`, `_request`. `get_children` acepta `rank: str | None` para la sonda de subfilo en el PR #2b.
  - Prueba: RED-first `taxon/tests/test_checklistbank.py` con `_StubClient` usando `httpx.MockTransport`. Cubre (a) `get_taxon` feliz + 404 → `None`; (b) `get_children` parsea `result[]`, aplica el parámetro `rank`, retorna lista vacía cuando CLB retorna `total:0`; (c) `search` retorna coincidencias con jerarquías de clasificación; (d) `_request` surface errores 4xx/5xx como `None` para 404, lanza para 5xx; (e) pruebas de la constante `DATASET_KEY`; (f) el parser maneja campos opcionales ausentes (`label_html=None`, `count=None`).
  - Verificar: `pytest taxon/tests/test_checklistbank.py -v` → todos pasan.
  - Rollback: eliminar `taxon/checklistbank.py` + `taxon/tests/test_checklistbank.py`. El router sigue dependiendo de `_get_gbif_client`. Seguro.
- [ ] 1.2 Verificar: `ruff check taxon/checklistbank.py taxon/tests/test_checklistbank.py && ruff format --check taxon/checklistbank.py taxon/tests/test_checklistbank.py && mypy taxon/checklistbank.py` → cero errores.
- [ ] 1.3 Verificar: smoke en vivo `curl -sf "https://api.checklistbank.org/dataset/COL2024/tree" | jq '.total'` → `2`.

## Fase 2: PR #2a — `feat(checklistbank): path resolver core walk`

Depende de: PR #1 fusionado en `develop`. Apunta a `develop`.
Rama: `../taxon-worktrees/cascade-checklistbank-pr2a`.
LOC: ~280 módulo + ~140 pruebas = ~420 (ligeramente sobre el presupuesto; los commits divididos según `work-unit-commits` mantienen cada commit hijo bajo las 400 LOC).

Commits por unidad de trabajo dentro del PR #2a:

- [ ] 2a.1 Crear `taxon/api/clb_path_children.py` con `CASCADE_TIERS = ("biota", "kingdom", "phylum", "subphylum", "class", "order", "family", "genus", "species")`, mapa `TIER_DEPTH`, dataclass `PathChildrenResponse`, dataclass `TaxonRow`, parser `_to_taxon_row`. Stub de `_resolve_deepest` y `_children_for` (aún sin regla de colapso — el PR #2b la completa; por ahora el filo retorna `next-rank hint = "subphylum"` sin condiciones).
  - Prueba: RED-first `taxon/tests/test_clb_path_children.py` con `test_cascade_tiers_constant` (9 elementos incluyendo "biota" + "subphylum"), `test_tier_depth_index`, `test_to_taxon_row_parses_clb_fields`, `test_path_children_response_shape`. ~80 LOC de pruebas.
  - Verificar: `pytest taxon/tests/test_clb_path_children.py -v` → 4 pasan.
  - Rollback: eliminar `taxon/api/clb_path_children.py` + `taxon/tests/test_clb_path_children.py`. El router aún no está cableado. Seguro.
- [ ] 2a.2 Implementar `_resolve_deepest(segments, client)` según el §Algoritmo de Recorrido del Resolver del diseño: alternar `client.search(segment, rank=R)` (vincula nombre → id) y `client.get_children(parent_id)` (encuentra el id del siguiente segmento por coincidencia de nombre, insensible a mayúsculas). Retorna la coincidencia más profunda o `None` si algún segmento falla al vincular.
  - Prueba: RED-first `test_resolve_deepest_biota_root_returns_biota_node`, `test_resolve_deepest_animalia_walks_one_step`, `test_resolve_deepest_mammalia_chain` (Animalia|Chordata|Mammalia → 4 segmentos → retorna Mammalia), `test_resolve_deepest_unknown_segment_returns_none`. ~60 LOC de pruebas.
  - Verificar: `pytest taxon/tests/test_clb_path_children.py -v` → 8 pasan.
  - Rollback: revertir solo este commit; `_resolve_deepest` retorna `None` para cualquier recorrido no trivial — el módulo + dataclass de 2a.1 siguen pasando pruebas.
- [ ] 2a.3 Implementar `_children_for(current, client)` sin colapso (siempre retorna `rank=next_tier`, incluso cuando el siguiente nivel es `subphylum`). Cablear `list_path_children(segments, client=None)` para llamar a `_resolve_deepest` y luego a `_children_for`; emitir `PathChildrenResponse`.
  - Prueba: RED-first `test_list_path_children_animalia_returns_phyla`, `test_list_path_children_felidae_returns_panthera_with_next_hint_species`, `test_list_path_children_root_biota_returns_seven_kingdoms_with_next_hint_kingdom`. ~60 LOC de pruebas.
  - Verificar: `pytest taxon/tests/test_clb_path_children.py -v` → 11 pasan.
  - Rollback: revertir solo este commit; 2a.1+2a.2 mantienen la dataclass + el recorrido.
- [ ] 2a.4 Verificar: `ruff check taxon/api/clb_path_children.py taxon/tests/test_clb_path_children.py && ruff format --check . && mypy taxon/api/clb_path_children.py` → cero errores.

## Fase 3: PR #2b — `feat(checklistbank): subphylum collapse rule`

Depende de: PR #2a fusionado en `develop`. Apunta a `develop`.
Rama: `../taxon-worktrees/cascade-checklistbank-pr2b`.
LOC: ~50 sonda de colapso + ~200 pruebas de colapso = ~250.

Commits por unidad de trabajo dentro del PR #2b:

- [ ] 2b.1 Reemplazar la rama del filo en `_children_for` con una sonda de colapso: cuando `next_rank == "subphylum"`, llamar a `client.get_children(current.id, rank="subphylum")`; si está vacío, llamar a `client.get_children(current.id, rank="class")` y emitir `next_rank_hint = "order"`; si no está vacío, retornar subfilos con `next_rank_hint = "class"`. Sin descenso recursivo (§Regla de Colapso de Subfilo del diseño).
  - Prueba: RED-first `test_subphylum_collapse_chordata_returns_three_subphyla_with_next_hint_class`, `test_subphylum_collapse_arthropoda_returns_classes_with_next_hint_order`, `test_subphylum_collapse_empty_subphylum_and_empty_class_returns_empty_with_next_hint_order`. ~80 LOC de pruebas.
  - Verificar: `pytest taxon/tests/test_clb_path_children.py -k subphylum_collapse -v` → 3 pasan.
  - Rollback: revertir solo este commit; la sonda de colapso desaparece, volviendo a la semántica "siempre retorna subfilo".
- [ ] 2b.2 Añadir cobertura para `_to_taxon_row` y `PathChildrenResponse` llevando `rank="subphylum"` para filas de subfilo; añadir `test_phylum_with_subphyla_propagates_next_hint_class` y `test_phylum_without_subphyla_propagates_next_hint_order`. ~120 LOC de pruebas.
  - Verificar: `pytest taxon/tests/test_clb_path_children.py -v` → 17+ pasan.
- [ ] 2b.3 Verificar: `ruff check . && ruff format --check . && mypy taxon/api/clb_path_children.py` → cero errores.

## Fase 4: PR #3 — `feat(api): route cascade endpoints through ChecklistBank client`

Depende de: PR #1, PR #2a, PR #2b fusionados en `develop`. Apunta a `develop`.
Rama: `../taxon-worktrees/cascade-checklistbank-pr3`.
LOC: ~200 pruebas nuevas + cambio de router → ~−700 neto (1,200 eliminaciones − 500 inserciones).

Commits por unidad de trabajo dentro del PR #3:

- [ ] 3.1 Cablear `taxon/api/router.py`: añadir la dependencia `_get_checklistbank_client()` que retorna un `ChecklistBankClient`; añadir un endpoint `get_roots` (`/api/kingdoms`) que llama a `client.search(q="", rank="biota")` y retorna Biota + Viruses (id + name + display_name + rank + next_rank_hint="kingdom"/"viruses"). Mantener la superficie URL existente de `/api/kingdoms` — la semántica cambia, el contrato se amplía.
  - Prueba: RED-first `taxon/tests/test_api_clb_router.py::test_kingdoms_returns_biota_and_viruses` (sobrescribir `_get_checklistbank_client` con un stub que retorna 2 resultados). ~50 LOC de pruebas.
  - Verificar: `pytest taxon/tests/test_api_clb_router.py -v` → 1 pasa.
  - Rollback: revertir este commit; la ruta antigua `_get_gbif_client` queda intacta. Seguro.
- [ ] 3.2 Recablear `/api/path-children` y `/api/species-list` de `Depends(_get_gbif_client)` + `GbifClient` a `Depends(_get_checklistbank_client)` + `ChecklistBankClient`. Los cuerpos llaman a `clb_path_children.list_path_children(...)`. Añadir pruebas RED: `test_path_children_resolves_mammalia_chain_via_clb`, `test_path_children_subphylum_collapse_arthropoda_via_clb`, `test_species_list_returns_panthera_species_via_clb`.
  - Verificar: `pytest taxon/tests/test_api_clb_router.py -v` → 4 pasan.
  - Rollback: revertir este commit; el router depende de GBIF nuevamente. Seguro siempre que 3.1 también se revierta.
- [ ] 3.3 Eliminar `taxon/gbif.py`, `taxon/api/gbif_path_children.py`, `taxon/tests/test_gbif.py`, `taxon/tests/test_gbif_path_children.py`, `taxon/tests/test_api_gbif_router.py`. Remover `_get_gbif_client` de `taxon/api/router.py`. Verificar que `grep -r "gbif\|Gbif\|GBIF" taxon/ frontend/src/ --include="*.py" --include="*.ts" --include="*.tsx"` retorna cero coincidencias.
  - Verificar: `pytest taxon/tests/ -v` → todos pasan (sin imports huérfanos, sin símbolos sombreados).
  - Rollback: NO es seguro revertir solo. Debe emparejarse con un PR de seguimiento que reintroduzca el cliente GBIF + las pruebas + recablee el router (ver §Plan de Rollback de la propuesta).
- [ ] 3.4 Verificar: `ruff check . && ruff format --check . && mypy taxon/` → cero errores.
- [ ] 3.5 Andamiaje de ejecución:
  - Iniciar `uvicorn taxon.main:app --reload` desde la raíz del worktree.
  - `curl -sf "http://localhost:8000/api/kingdoms" | jq 'length'` → `2`; el primer item `.name` → `"Biota"`.
  - `curl -sf "http://localhost:8000/api/path-children?path=Animalia|Chordata|Vertebrata|Mammalia|Carnivora|Felidae|Panthera" | jq '.children | length'` → `>=12`.
  - `curl -sf "http://localhost:8000/api/path-children?path=Animalia|Arthropoda" | jq '.next_rank_hint'` → `"order"` (subfilo colapsado).

## Fase 5: PR #4 — `feat(frontend): render Biota + subphylum in the cascade UI`

Depende de: PR #3 fusionado en `develop`, diseño en Pencil sobre `taxon.pen` auditado bajo `impeccable` (AGENTS.md §5). Apunta a `develop`.
Rama: `../taxon-worktrees/cascade-checklistbank-pr4`.
LOC: ~350 (código + pruebas; el diseño en Pencil es un artefacto del worktree hermano, no parte del diff de este PR).

Commits por unidad de trabajo dentro del PR #4:

- [ ] 4.0 (Pre-PR, en worktree hermano) Abrir `taxon.pen` vía Pencil MCP, añadir una ranura extra de dropdown para el nivel raíz Biota, añadir la etiqueta del nivel "subphylum" en la capa de etiquetas de nivel. Ejecutar una pasada de auditoría `impeccable` sobre el `taxon.pen` actualizado (jerarquía, accesibilidad, tipografía, color, movimiento, anti-patrones). Iterar hasta que esté limpio. Documentar la aprobación en `taxon/docs/design/approval-cascade-checklistbank.md` (fecha + firma). Esta tarea NO pertenece al PR #4; debe completarse ANTES de que el PR #4 comience.
- [ ] 4.1 Actualizar `frontend/src/api.ts`: renombrar `fetchKingdoms()` → `fetchRoots()`; retornar forma `{ roots: TaxonResponse[] }` (Biota + Viruses, cada uno con `rank` + `next_rank_hint`). Mantener las firmas de `fetchPathChildren()` + `fetchSpeciesList()` sin cambios.
  - Prueba: RED-first `frontend/tests/api.test.ts`: `test_fetch_roots_returns_biota_and_viruses`, `test_fetch_roots_404_returns_not_found`, `test_fetch_path_children_unaffected`. ~50 LOC de pruebas.
  - Verificar: `vitest run frontend/tests/api.test.ts` → todos pasan.
  - Rollback: revertir este commit; `fetchKingdoms` retorna y `Cascade.tsx` sigue funcionando contra `/api/kingdoms`. El backend no se ve afectado.
- [ ] 4.2 Actualizar `frontend/src/components/Cascade.tsx`: cambiar la carga inicial de `fetchKingdoms()` → `fetchRoots()`; añadir inferencia de etiqueta para `"subphylum"` y `"biota"` en el capitalizador de nombres de nivel; añadir un mapa `RANK_LABEL_OVERRIDES` (insensible a mayúsculas). El reducer (`Cascade.state.ts`) es agnóstico al path — sin cambios.
  - Prueba: RED-first `frontend/tests/Cascade.pathAware.test.tsx`: `test_path_aware_renders_biota_dropdown_first`, `test_path_aware_subphylum_appears_for_chordata`, `test_path_aware_subphylum_collapsed_for_arthropoda`. Actualizar `frontend/tests/Cascade.ui.test.tsx`: mockear `/api/kingdoms` → `/api/roots` retornando Biota + Viruses. ~150 LOC de pruebas.
  - Verificar: `vitest run frontend/tests/` → todos pasan.
  - Rollback: revertir este commit; Cascade vuelve a la semántica reino-como-raíz. El backend no se ve afectado.
- [ ] 4.3 Verificar: `npm run lint && npm run typecheck && vitest run` → cero errores.
- [ ] 4.4 Andamiaje de ejecución:
  - Backend corriendo localmente (backend del PR #3).
  - Smoke en navegador: Biota → Animalia → Chordata → Vertebrata → Mammalia → Carnivora → Felidae → Panthera → 12 especies renderizadas (8 dropdowns).
  - Smoke en navegador: Biota → Animalia → Arthropoda → Insecta → Lepidoptera → Bombycidae → Bombyx (7 dropdowns; ranura de subfilo colapsada — solo 7 niveles visibles).

## Fase 6: Post-fusión (después de PR #3 verde)

- [ ] 6.1 Crear `learn-es/2026-08-14-cascade-checklistbank.md` con secciones: Qué / Cómo / Dónde / Por qué / Cómo funciona / Flujos de trabajo. Disparador: PR #3 fusionado verde en `develop`.
- [ ] 6.2 Confirmar que `grep -r "gbif\|Gbif\|GBIF" taxon/ frontend/src/ --include="*.py" --include="*.ts" --include="*.tsx"` retorna cero coincidencias en `develop`.

## Convenciones

- Worktrees en `../taxon-worktrees/cascade-checklistbank-pr{1,2a,2b,3,4}` ramificados desde `develop`.
- Commits convencionales en inglés; sin atribución a IA. Tipos permitidos: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `build`, `ci`, `perf`, `style`.
- TDD estricto según `openspec/config.yaml`: cada tarea de producción tiene una prueba RED-first antes de GREEN.
- El portón de Pencil + `impeccable` aplica solo al PR #4 — la cadena de backend (#1 → #2a → #2b → #3) está desbloqueada.
- Espejo en español de este archivo: `documents-es/openspec/changes/cascade-checklistbank/tasks-es.md` (creado al momento de escritura, traducción fiel, registro neutro/profesional).