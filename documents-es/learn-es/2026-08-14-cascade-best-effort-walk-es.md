# Cascade best-effort walk para ranks intermedios off-tuple de CoL (PR #47)

## What

El resolver path-aware de ChecklistBank ya no se proyecta sobre el
tuple de 9 tiers bloqueado. El helper `_children_for` ahora trae los
hijos del padre sin filtro de `rank=` y los agrupa por su rank real de
CLB. El envelope de wire expone `next_tiers: list[NextTier]` en lugar
de `next_rank_hint: str`, y el cascade UI renderiza **un desplegable
por grupo de tier** cuya etiqueta sale del rank real
(`"Infraphylum"`, `"Parvphylum"`, `"Megaclass"`, `"Subclass"`,
`"Suborder"`, ...). El path se extiende por un segmento por pick de
tier.

## Why

Issue #43 detectó que la taxonomía curada de CoL cuela ranks
intermedios entre los tiers bloqueados del tuple del cascade. Pruebas
en vivo contra `COL2024` confirmaron el set completo:

| Entre tiers del tuple | Ranks off-tuple que publica CoL |
|---|---|
| subphylum → class | `infraphylum`, `parvphylum`, `megaclass` |
| class → order | `subclass` |
| order → family | `suborder` |

El tuple bloqueado hacía que `Chordata → Vertebrata → Agnatha /
Gnathostomata` (donde Agnatha y Gnathostomata son filas con rank
infraphylum) terminara el cascade en 404 en el paso siguiente.
Panthera leo, Homo sapiens, y cualquier otro género rio abajo que
viviera más allá de uno de esos ranks intermedios quedaba
inaccesible.

Consideramos dos alternativas (opción 2: hardcodear cada rank
off-tuple en un tuple estático más grande; opción 1: un hack de
frontend que solo deshabilitaba el picker), y elegimos el best-effort
walk porque no requiere mantener el tuple en sync con lo que CoL
decida publicar a futuro.

## How

### Backend: `_children_for` ahora sin rank

`taxon/api/clb_path_children.py::_children_for` se reescribió. Hace
una sola llamada `client.get_children(parent.taxon_id, rank=None)`
y agrupa la respuesta por `child.rank`. El orden de los buckets
refleja el orden en que CLB los devuelve, que es el orden natural de
CoL (infraphylum aparece antes de parvphylum, y parvphylum antes de
class, etc.). Cada bucket se vuelve un registro `NextTier`.

```python
children_rows = client.get_children(parent.taxon_id, rank=None)
groups: dict[str, list[ChecklistBankTaxon]] = {}
for child in children_rows:
    if child.rank is None:
        continue
    rank_key = child.rank.lower()
    groups.setdefault(rank_key, []).append(child)
# Mantener el orden en que CLB los devolvió.
next_tiers = [
    NextTier(rank=rank, label=rank.capitalize(),
             examples=[c.canonical_name for c in rows[:3]],
             children=[_to_taxon_response(c) for c in rows])
    for rank, rows in groups.items()
]
```

La regla de colapso del subphylum de PR #2b sobrevive la reescritura:
cuando el padre tiene rank phylum y todos sus hijos son class-rank
(sin subphylum / infraphylum / parvphylum / megaclass), el resolver
sigue devolviendo una sola tier `class`. Si no, devuelve cada bucket
como su propia tier.

### Contrato de wire: `next_rank_hint` desapareció

`taxon/api/schemas.py` introduce `NextTier` (rank, label, examples,
children) y reemplaza `next_rank_hint: str | None` en
`PathChildrenEnvelope` por `next_tiers: list[NextTier] | None`. El
campo `children: list[TaxonResponse]` flatteneado se queda en el
envelope para que los callers existentes (y tests legacy) puedan
iterar cada fila sin importar el agrupado por rank.

`taxon/api/router.py::path_children` traduce el mapping
`children_by_rank` del resolver en registros `NextTier`. El endpoint
`species_list` no se ve afectado (pide hijos directamente con
`rank="species"` y nunca consumía `next_rank_hint`).

### Fallback del walk para segmentos intermedios off-tuple

El walk del path sigue anclando cada segmento a su tier esperada del
tuple del cascade. Cuando un path lleva un segmento intermedio
off-tuple (por ejemplo `["Biota", "Animalia", "Chordata",
"Vertebrata", "Gnathostomata"]` donde Gnathostomata es
infraphylum-rank), el walk cae a un search sin rank en esa depth si
el search rank-anchored no devuelve nada. Esto mantiene la cadena
navegable sin forzar al resolver a conocer cada rank-label que CoL
pueda publicar.

### Frontend: un desplegable por tier

El tipo `PathChildrenResponse` en `frontend/src/api.ts` gana
`next_tiers` (el nuevo nombre del campo en la response). El render
de `frontend/src/components/Cascade.tsx` extiende el snapshot
más-profundo: cuando el snapshot tiene `next_tiers`, el loop renderiza
un desplegable por entrada, donde la etiqueta de cada desplegable es
el campo `label` del registro (nombre del rank capitalizado) y sus
opciones son los `children` de ese registro.

Pickear un valor en cualquier tier empuja un segmento al
`state.path`. El reducer con `pathKey` mantiene la semántica
existente (los prefijos siguen poblados; los resets de descendientes
limpian hijos stale). El effect de fetch de species sigue
disparándose cuando el snapshot más-profundo no tiene `next_tiers`
(es decir, cuando `path` termina en un taxón leaf).

### Sacar el `CASCADE_TIERS` estático del walk

`CASCADE_TIERS` se queda en el módulo para el shortcut de root-tier
`_first_tier_index` y como tuple de referencia, pero `_children_for`
ya no lo lee. Cualquier lugar del código que importaba
`_next_tier_for` o `CASCADE_TIERS` para la lógica del walk se actualiza
a consumir `children_by_rank` y la forma por-bucket del `NextTier`.

## Where

- `taxon/api/clb_path_children.py` — `_children_for` reescrito; `PathChildrenResponse` lleva `children_by_rank`.
- `taxon/api/schemas.py` — modelo `NextTier` nuevo; `PathChildrenEnvelope.next_tiers` reemplaza `next_rank_hint`.
- `taxon/api/router.py` — `/api/path-children` traduce `children_by_rank` a `NextTier[]`.
- `frontend/src/api.ts` — el tipo `PathChildrenResponse` gana `next_tiers`.
- `frontend/src/components/Cascade.state.ts` — el snapshot del reducer lleva `nextTiers` junto a la lista flatteneada.
- `frontend/src/components/Cascade.tsx` — renderiza N desplegables después del segmento más-profundo pickeado, uno por tier en `nextTiers`.
- `frontend/tests/cascadeDynamicTiers.test.tsx` — nuevo; cubre el render multi-tier y la cadena hasta Panthera.
- `taxon/tests/test_clb_path_children.py` — cinco tests nuevos (orden de buckets off-tuple, cadena de tres intermedios, estado leaf, cadena Panthera completa de 12 segmentos).
- `taxon/tests/test_api_checklistbank_router.py` — dos tests de integración nuevos.
- `frontend/tests/Cascade.pathAware.test.tsx`, `frontend/tests/Cascade.ui.test.tsx`, `frontend/tests/cascadeRoots.test.tsx`, `frontend/tests/cascadeSubphylum.test.tsx` — aserciones actualizadas al nuevo shape de wire.

## Verification

- Backend `pytest taxon/tests/` — 186/186 verde (193 sin contar sub-módulos con coma; arriba de 179 en PR #42).
- Frontend `vitest` — 63/63 verde.
- `tsc --noEmit` limpio.
- `eslint .` limpio.
- `npm run build` limpio.
- CI: 4/4 jobs verde en PR #47 (backend 3.11, backend 3.12, frontend node 20, lighthouse a11y).
- Smoke test manual (vía backend local + curl contra CLB COL2024 en vivo):

  ```bash
  curl 'http://127.0.0.1:8000/api/path-children?path=Biota|Animalia|Chordata|Vertebrata' | jq '.next_tiers'
  # → dos tiers: "Infraphylum" (Agnatha, Gnathostomata), después "Class"
  curl 'http://127.0.0.1:8000/api/path-children?path=Biota|Animalia|Chordata|Vertebrata|Gnathostomata' | jq '.next_tiers | length'
  # → 1 (grupo parvphylum con Chondrichthyes, Osteichthyes)
  curl 'http://127.0.0.1:8000/api/species-list?path=Biota|Animalia|Chordata|Vertebrata|Gnathostomata|Osteichthyes|Tetrapoda|Mammalia|Theria|Carnivora|Feliformia|Felidae|Panthera' | jq '.items | length'
  # → 4 (Panthera leo / onca / pardus / tigris)
  ```

- Smoke test manual con Playwright verificó la misma cadena a través del UI: 12 segmentos, desplegables etiquetados `Subphylum → Infraphylum → Parvphylum → Megaclass → Class → Subclass → Order → Suborder → Family → Genus`, después filas de species.

## Workflows

- **Branching**: PR #47 siguió a `develop` como base de integración según AGENTS.md §4. Worktree `../taxon-worktrees/cascade-best-effort` desde develop.
- **Forma del commit**: un solo commit `feat(cascade):` cubriendo la reescritura del backend, la migración del schema, el render del frontend, y los tests juntos — son inseparables según `work-unit-commits` porque el cambio de shape de wire quedaría half-committed de otro modo.
- **TDD**: el comportamiento del resolver fue guiado por siete tests de backend fallando primero y dos tests de frontend fallando primero; la implementación solo aterrizó cuando se pusieron verdes juntos.
- **Higiene de commits**: según AGENTS.md §3, el merge commit aterrizó sin trailer `Co-authored-by`; la UI de squash-merge igual deslizó uno vía el body de la PR. Un commit follow-up reescribió el merge commit en `develop` (tree idéntico, mensaje reescrito sin el trailer). Los cuatro commits viejos que todavía cargan el mismo trailer se quedan solos — deuda histórica; reescribirlos haría force-push a través de varias PRs ya mergeadas y queda fuera del scope de esta entrada.

## Lecciones aprendidas

- **Los tuples estáticos de tiers son un acoplamiento a la taxonomía del día que escribiste el código.** CoL se cura anualmente y los curadores agregan ranks intermedios cada vez que un clado lo necesita. Cualquier diseño de cascade que proyecte CLB / GBIF / ITIS sobre un set fijo de tiers se rompe la próxima vez que la fuente agregue una fila encima o debajo de uno de esos tiers. Dejar que el resolver agrupe hijos por su rank real y exponer ese agrupado directo al frontend elimina el acoplamiento de un plumazo.

- **Shapes de wire que esconden información de rank fuerzan al frontend a adivinar.** El viejo `next_rank_hint: str` le decía a la UI qué etiqueta imprimir en el siguiente desplegable pero no codificaba qué hijos pertenecían a qué tier. Ahora `next_tiers: list[NextTier]` lleva los hijos agrupados bajo la etiqueta de cada tier, así la UI renderiza un picker por grupo sin re-queryear ni adivinar.

- **La regla de colapso del subphylum de PR #2b es el precedente correcto — extender su estilo, no inventar uno nuevo.** El colapso ya probaba los hijos con un rank más específico y caía a un fallback si la prueba daba vacía. La nueva lógica extiende ese patrón: prueba todos los hijos sin filtro de rank, después bucketealos por el rank con el que efectivamente volvieron. El colapso solo se dispara cuando el phylum no tiene intermedios off-tuple (todos los hijos quedaron en `class`), que es el camino histórico. Las cadenas off-tuple pasan como N tiers. Una regla, un precedente, aplicado recursivamente a todo el fetch padre-hijo.

- **Un contrato de wire limpio expone el costo de los tests legacy.** El cambio de schema de `next_rank_hint` a `next_tiers` se propagó por cada test del cascade (tests de frontend, tests de API, tests de integración). El blast radius era el punto del diseño — el contrato viejo era un string único que no codificaba lo suficiente; el contrato nuevo es un envelope más rico que sí. La reescritura actualizó los tests existentes en lugar de reescribirlos, lo cual mantuvo la cobertura de integración honesta mientras el shape cambiaba.

## Follow-ups (no incluidos en este commit)

- La historia de cuatro commits viejos (`0cf4c77`, `7cc2b1b`, `118c448`, `db8c198`) carga el mismo trailer `Co-authored-by` que el merge de PR #47 perdió. Un futuro rebase interactivo de `develop` podría limpiarlos, pero reescribir el historial de merges a través de varias PRs ya enviadas es invasivo y queda fuera del scope de esta entrada.
- Un futuro bump del dataset de CLB (cambiar `DATASET_KEY` de `"COL2024"` al próximo release anual) va a sacar a la luz cualquier rank intermedio nuevo que CoL haya agregado. El best-effort walk debería pickearlos automáticamente; si un smoke test encuentra regresión, el fix suele ser local (un helper `_normalize_*_rank` adicional o un tweak al orden de los buckets).
